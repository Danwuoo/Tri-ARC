from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch

from .prompting import PromptRequest

LOGGER = logging.getLogger("arc.llm.engine")

try:  # pragma: no cover - optional dependency
    from transformers import AutoModelForCausalLM, AutoTokenizer
    try:
        from transformers import BitsAndBytesConfig
    except Exception:  # pragma: no cover - not all installs provide bitsandbytes helpers
        BitsAndBytesConfig = None  # type: ignore
except Exception:  # pragma: no cover - transformers not installed
    AutoModelForCausalLM = None  # type: ignore
    AutoTokenizer = None  # type: ignore
    BitsAndBytesConfig = None  # type: ignore


class LLMEngineError(RuntimeError):
    """Raised when the local decoder cannot be initialised or sampled."""


@dataclass
class LLMGenerationResult:
    request: PromptRequest
    completion: str
    prompt_tokens: int
    completion_tokens: int
    runtime_s: float
    finish_reason: str
    truncated_prompt: bool = False


class BaseLLMEngine:
    name: str = "base"

    def generate(self, requests: Sequence[PromptRequest]) -> List[LLMGenerationResult]:  # pragma: no cover - interface
        raise NotImplementedError

    def shutdown(self) -> None:  # pragma: no cover - subclass hook
        return


class QwenCoderEngine(BaseLLMEngine):
    name = "qwen2.5-coder-7b"

    def __init__(
        self,
        model_path: str,
        *,
        tokenizer_path: Optional[str] = None,
        device: str = "auto",
        quantisation_bits: int = 4,
        dtype: str = "bfloat16",
        max_input_tokens: int = 1536,
    ) -> None:
        if AutoTokenizer is None or AutoModelForCausalLM is None:
            raise LLMEngineError("transformers is required to load the Qwen engine.")
        self.max_input_tokens = max(512, int(max_input_tokens))
        self._device_label = device
        self._dtype = self._resolve_dtype(dtype)
        self._device = torch.device(self._infer_device_label(device))
        quant_config = self._build_quant_config(quantisation_bits)
        resolved_tokenizer_path = tokenizer_path or model_path
        self.tokenizer = AutoTokenizer.from_pretrained(resolved_tokenizer_path, trust_remote_code=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        device_map = "auto" if device == "auto" else device
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=self._dtype,
            device_map=device_map,
            trust_remote_code=True,
            quantization_config=quant_config,
        )
        self.model.eval()
        if device_map == "auto" and hasattr(self.model, "hf_device_map"):
            first_device = next(iter(self.model.hf_device_map.values()))
            self._device = torch.device(self._coerce_device_label(first_device))
        LOGGER.info(
            "Loaded Qwen engine from %s (device=%s, dtype=%s, max_input=%d)",
            model_path,
            self._device,
            self._dtype,
            self.max_input_tokens,
        )

    def generate(self, requests: Sequence[PromptRequest]) -> List[LLMGenerationResult]:
        results: List[LLMGenerationResult] = []
        for request in requests:
            prompt_text = self.tokenizer.apply_chat_template(
                request.messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            tokenised = self.tokenizer(
                prompt_text,
                return_tensors="pt",
                padding=False,
                truncation=True,
                max_length=self.max_input_tokens,
            )
            truncated = tokenised["input_ids"].shape[-1] >= self.max_input_tokens
            inputs = {key: value.to(self._device) for key, value in tokenised.items()}
            start = time.perf_counter()
            try:
                with torch.no_grad():
                    generated = self.model.generate(
                        **inputs,
                        do_sample=True,
                        temperature=request.temperature,
                        top_p=request.top_p,
                        max_new_tokens=request.max_new_tokens,
                        pad_token_id=self.tokenizer.pad_token_id,
                        eos_token_id=self.tokenizer.eos_token_id,
                    )
            except torch.cuda.OutOfMemoryError as exc:  # pragma: no cover - hardware dependent
                if torch.cuda.is_available():  # defensive on CPU-only builds
                    torch.cuda.empty_cache()
                raise LLMEngineError(f"Qwen generation OOM on device {self._device_label}") from exc
            runtime = time.perf_counter() - start
            prompt_tokens = inputs["input_ids"].shape[-1]
            output_ids = generated[:, prompt_tokens:]
            completion_tokens = output_ids.shape[-1]
            decoded = self.tokenizer.decode(output_ids[0], skip_special_tokens=False)
            trimmed, stop_reason = _trim_completion(decoded, request.stop_sequences)
            finish_reason = stop_reason or ("eos" if completion_tokens and output_ids[0][-1].item() == self.tokenizer.eos_token_id else "length")
            cleaned = _normalise_completion(trimmed, self.tokenizer.eos_token or "")
            results.append(
                LLMGenerationResult(
                    request=request,
                    completion=cleaned,
                    prompt_tokens=int(prompt_tokens),
                    completion_tokens=int(completion_tokens),
                    runtime_s=runtime,
                    finish_reason=finish_reason,
                    truncated_prompt=truncated,
                )
            )
        return results

    def shutdown(self) -> None:
        try:  # pragma: no cover - defensive
            del self.model
        except AttributeError:
            pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _build_quant_config(self, bits: int):
        if bits == 4:
            if BitsAndBytesConfig is None:
                raise LLMEngineError("bitsandbytes is required for 4-bit quantisation.")
            return BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=self._dtype,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
        if bits not in {8, 16, 32}:
            raise LLMEngineError(f"Unsupported quantisation bit-width: {bits}.")
        return None

    def _resolve_dtype(self, label: str) -> torch.dtype:
        token = label.lower()
        if token in {"bf16", "bfloat16"}:
            return torch.bfloat16
        if token in {"fp16", "float16", "half"}:
            return torch.float16
        if token in {"fp32", "float32", "full"}:
            return torch.float32
        raise LLMEngineError(f"Unknown dtype '{label}'.")

    def _infer_device_label(self, label: str) -> str:
        if label == "auto":
            if torch.cuda.is_available():
                return "cuda:0"
            return "cpu"
        return label

    def _coerce_device_label(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            return f"cuda:{value}"
        if isinstance(value, (list, tuple)) and value:
            return self._coerce_device_label(value[0])
        return "cuda:0" if torch.cuda.is_available() else "cpu"


class StubLLMEngine(BaseLLMEngine):
    name = "stub"

    def __init__(self, *, reason: Optional[str] = None) -> None:
        self.reason = reason or "offline stub"

    def generate(self, requests: Sequence[PromptRequest]) -> List[LLMGenerationResult]:
        payload = {
            "rationale": "Stub engine mirrors the input grid; use identity pipeline.",
            "dsl": "(pipeline (apply identity))",
            "confidence": 0.55,
            "test_outputs": [],
            "notes": self.reason,
        }
        body = json.dumps(payload)
        return [
            LLMGenerationResult(
                request=request,
                completion=body,
                prompt_tokens=0,
                completion_tokens=len(body.split()),
                runtime_s=0.0,
                finish_reason="stub",
                truncated_prompt=False,
            )
            for request in requests
        ]


def _trim_completion(text: str, stop_sequences: Sequence[str]) -> Tuple[str, Optional[str]]:
    finish_reason: Optional[str] = None
    trimmed = text
    for token in stop_sequences:
        if not token:
            continue
        index = trimmed.find(token)
        if index >= 0:
            trimmed = trimmed[:index]
            finish_reason = "stop"
            break
    return trimmed.strip(), finish_reason


def _normalise_completion(text: str, eos_token: str) -> str:
    cleaned = text.replace("<|im_end|>", "").replace("<|im_start|>", "")
    if eos_token:
        cleaned = cleaned.replace(eos_token, "")
    return cleaned.strip()
