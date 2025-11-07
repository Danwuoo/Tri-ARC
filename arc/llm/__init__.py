from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from arc.common.grid import grids_equal, normalise_grid
from arc.core import (
    ModuleCapabilities,
    ModuleContext,
    ModuleError,
    ModuleResult,
    ModuleSolveStatus,
    ModuleTaskContext,
    SolverModule,
)
from arc.symbolic.dsl.exceptions import DSLParseError
from arc.symbolic.dsl.interpreter import DSLInterpreter, validate_program
from arc.symbolic.dsl.parser import parse_program
from arc.symbolic.dsl.runtime.errors import InterpreterFailure

from .engine import BaseLLMEngine, LLMEngineError, LLMGenerationResult, QwenCoderEngine, StubLLMEngine
from .prompting import LLMPromptContext, PromptBuilder, PromptVariant, build_default_variants

LOGGER = logging.getLogger("arc.llm.module")


@dataclass(frozen=True)
class SMTSettings:
    enabled: bool
    prefix: str
    secret: str

    @classmethod
    def from_config(cls, llm_cfg: Mapping[str, Any], root_cfg: Mapping[str, Any]) -> "SMTSettings":
        llm_smt = llm_cfg.get("smt", {}) or {}
        global_smt = root_cfg.get("smt", {}) or {}
        enabled = bool(llm_smt.get("issue_tokens", global_smt.get("issue_tokens", True)))
        prefix = str(llm_smt.get("token_prefix") or global_smt.get("token_prefix") or "smt:virtual-llm:")
        secret = str(
            llm_smt.get("virtual_secret")
            or global_smt.get("virtual_secret")
            or root_cfg.get("global", {}).get("seed", "tri-arc-llm")
        )
        return cls(enabled=enabled, prefix=prefix, secret=secret)


@dataclass(frozen=True)
class LLMModuleSettings:
    enabled: bool
    backend: str
    prompt_version: str
    model_path: Path
    tokenizer_path: Optional[Path]
    initial_candidates: int
    refinement_candidates: int
    temperature: float
    top_p: float
    max_input_tokens: int
    max_new_tokens: int
    quantisation_bits: int
    keep_failed_candidates: bool
    stop_sequences: Tuple[str, ...]
    prompt_variants: Tuple[Dict[str, Any], ...]
    dtype: str

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any], *, prompt_version: str) -> "LLMModuleSettings":
        model_path = Path(config.get("model_path", "models/Qwen2.5-Coder-7B-Instruct"))
        tokenizer_path = config.get("tokenizer_path")
        stop_sequences = tuple(config.get("stop_sequences", ["</json>", "</response>", "<|im_end|>"]))
        prompt_variants_cfg = tuple(config.get("prompt_variants") or ())
        return cls(
            enabled=bool(config.get("enabled", True)),
            backend=str(config.get("backend", "auto")).lower(),
            prompt_version=prompt_version,
            model_path=model_path,
            tokenizer_path=Path(tokenizer_path) if tokenizer_path else None,
            initial_candidates=max(1, int(config.get("initial_candidates", 8))),
            refinement_candidates=max(1, int(config.get("refinement_candidates", 4))),
            temperature=float(config.get("temperature_initial", 0.7)),
            top_p=float(config.get("top_p_initial", 0.9)),
            max_input_tokens=int(config.get("max_input_tokens", 1536)),
            max_new_tokens=int(config.get("max_new_tokens", 512)),
            quantisation_bits=int(config.get("quantisation_bits", 4)),
            keep_failed_candidates=bool(config.get("keep_failed_candidates", False)),
            stop_sequences=stop_sequences,
            prompt_variants=prompt_variants_cfg,
            dtype=str(config.get("dtype", "bfloat16")),
        )


@dataclass
class ParsedGeneration:
    dsl: str
    rationale: str
    model_confidence: float
    predictions: Sequence[Any]
    payload: Dict[str, Any]
    notes: Optional[str] = None


@dataclass
class CandidateVerification:
    passed: bool
    train_outputs: List[Dict[str, Any]]
    eval_outputs: List[Dict[str, Any]]
    train_accuracy: float
    total_train_examples: int
    issues: List[str] = field(default_factory=list)
    failure_reason: Optional[str] = None


class LLMModule(SolverModule):
    module_name = "llm"
    capabilities = ModuleCapabilities(
        supports_partial_results=True,
        supports_resume=False,
        requires_gpu=True,
        extras={"lane": "llm"},
    )

    def __init__(self, config: Dict[str, Any], *, prompt_version: Optional[str] = None) -> None:
        super().__init__(config)
        llm_cfg = config.get("llm", {}) or {}
        self._device_label = str(llm_cfg.get("device") or config.get("global", {}).get("device_map", {}).get("llm", "auto"))
        version = prompt_version or str(llm_cfg.get("prompt_version", "dsl-v1"))
        self._settings = LLMModuleSettings.from_mapping(llm_cfg, prompt_version=version)
        self._smt = SMTSettings.from_config(llm_cfg, config)
        self._engine: Optional[BaseLLMEngine] = None
        self._engine_name: str = "uninitialised"
        self._engine_warning: Optional[str] = None
        self._prompt_builder: Optional[PromptBuilder] = None
        self._interpreter: Optional[DSLInterpreter] = None
        self._smt_counter = 0

    # ------------------------------------------------------------------ #
    # Lifecycle hooks
    # ------------------------------------------------------------------ #
    def _on_initialize(self, context: ModuleContext) -> None:
        if not self._settings.enabled:
            context.logger.info("LLM lane disabled via configuration toggle.")
            return
        self._interpreter = DSLInterpreter(config=self.config)
        variants = self._resolve_variants()
        self._prompt_builder = PromptBuilder(
            prompt_version=self._settings.prompt_version,
            variants=variants,
            stop_sequences=self._settings.stop_sequences,
            default_temperature=self._settings.temperature,
            default_top_p=self._settings.top_p,
            default_max_new_tokens=self._settings.max_new_tokens,
        )
        self._engine = self._initialise_engine(context)

    def _on_prepare_task(self, task_context: ModuleTaskContext) -> ModuleTaskContext:
        namespace = task_context.module_context.shared_cache.setdefault(self.module_name, {})
        module_cache = namespace.setdefault(task_context.task_id, {})
        task_context.cache_namespace = module_cache
        task_context.metadata["module"] = self.module_name
        task_context.metadata["prompt_version"] = self._settings.prompt_version
        task_context.metadata["engine"] = self._engine_name
        return task_context

    def _on_solve(self, task_context: ModuleTaskContext) -> ModuleResult:
        if not self._settings.enabled:
            summary = {"reason": "module_disabled", "lane": self.module_name}
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        if self._prompt_builder is None or self._engine is None or self._interpreter is None:
            raise ModuleError("LLM module must be initialised before solving.")

        train_examples = list(task_context.task_payload.get("train_examples") or [])
        eval_examples = list(
            task_context.task_payload.get("eval_examples")
            or task_context.task_payload.get("test_examples")
            or []
        )
        if not train_examples:
            summary = {
                "lane": self.module_name,
                "prompt_version": self._settings.prompt_version,
                "reason": "no_train_examples",
            }
            task_context.cache_namespace["candidates"] = []
            task_context.cache_namespace["llm_summary"] = summary
            return ModuleResult(task_id=task_context.task_id, status=ModuleSolveStatus.SKIPPED, summary=summary)

        prompt_context = LLMPromptContext(task_id=task_context.task_id, train_examples=train_examples, eval_examples=eval_examples)
        requests = self._prompt_builder.build_requests(prompt_context, self._settings.initial_candidates)
        generations = self._engine.generate(requests)
        processed = self._process_generations(
            generations,
            train_examples=train_examples,
            eval_examples=eval_examples,
            task_id=task_context.task_id,
        )
        candidates = processed["candidates"]
        failures = processed["failures"]
        failure_counts = processed["failure_reasons"]

        task_context.cache_namespace["candidates"] = candidates
        task_context.cache_namespace["llm_failures"] = failures
        task_context.cache_namespace["llm_generations"] = [
            {
                "variant": result.request.variant,
                "finish_reason": result.finish_reason,
                "runtime_s": result.runtime_s,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "truncated_prompt": result.truncated_prompt,
            }
            for result in generations
        ]

        summary = {
            "lane": self.module_name,
            "prompt_version": self._settings.prompt_version,
            "engine": self._engine_name,
            "backend": self._settings.backend,
            "generated": len(generations),
            "verified": len(candidates),
            "failure_reasons": dict(failure_counts),
            "engine_warning": self._engine_warning,
        }
        task_context.cache_namespace["llm_summary"] = summary

        if candidates:
            status = ModuleSolveStatus.SUCCESS
        elif generations:
            status = ModuleSolveStatus.PARTIAL
        else:
            status = ModuleSolveStatus.FAILED
        return ModuleResult(task_id=task_context.task_id, status=status, candidates=candidates, summary=summary)

    def _on_shutdown(self, context: ModuleContext) -> None:
        if self._engine:
            try:
                self._engine.shutdown()
            except Exception as exc:  # pragma: no cover - defensive
                context.logger.debug("LLM engine shutdown raised %s", exc)
        self._engine = None
        self._prompt_builder = None
        self._interpreter = None
    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _resolve_variants(self) -> Tuple[PromptVariant, ...]:
        base = list(build_default_variants())
        if not self._settings.prompt_variants:
            return tuple(base)
        overrides = {
            str(entry.get("name", "")).lower(): entry
            for entry in self._settings.prompt_variants
            if isinstance(entry, Mapping)
        }
        resolved: List[PromptVariant] = []
        for variant in base:
            payload = overrides.get(variant.name.lower())
            if not payload:
                resolved.append(variant)
                continue
            updated = variant
            scalar_fields = {
                "temperature": float,
                "top_p": float,
                "max_new_tokens": int,
                "weight": float,
            }
            for key, caster in scalar_fields.items():
                if key in payload:
                    updated = replace(updated, **{key: caster(payload[key])})
            if "focus" in payload:
                updated = replace(updated, focus=str(payload["focus"]))
            if "description" in payload:
                updated = replace(updated, description=str(payload["description"]))
            if "instructions" in payload and isinstance(payload["instructions"], Sequence):
                instructions = tuple(str(item) for item in payload["instructions"] if item)
                if instructions:
                    updated = replace(updated, instructions=instructions)
            if "system_prompt" in payload:
                updated = replace(updated, system_prompt=str(payload["system_prompt"]))
            resolved.append(updated)
        return tuple(resolved)

    def _initialise_engine(self, context: ModuleContext) -> BaseLLMEngine:
        backend = self._settings.backend
        if backend in {"auto", "qwen", "qwen2", "qwen2.5"}:
            try:
                engine = QwenCoderEngine(
                    model_path=str(self._settings.model_path),
                    tokenizer_path=str(self._settings.tokenizer_path) if self._settings.tokenizer_path else None,
                    device=self._device_label,
                    quantisation_bits=self._settings.quantisation_bits,
                    dtype=self._settings.dtype,
                    max_input_tokens=self._settings.max_input_tokens,
                )
                self._engine_name = engine.name
                self._engine_warning = None
                return engine
            except LLMEngineError as exc:
                context.logger.warning("Qwen engine unavailable (%s)", exc)
                self._engine_warning = str(exc)
                if backend != "auto":
                    raise
                fallback = StubLLMEngine(reason=str(exc))
                self._engine_name = fallback.name
                return fallback
        if backend == "stub":
            engine = StubLLMEngine()
            self._engine_name = engine.name
            return engine
        raise ModuleError(f"Unknown llm backend '{backend}'.")

    def _process_generations(
        self,
        generations: Sequence[LLMGenerationResult],
        *,
        train_examples: Sequence[Mapping[str, Any]],
        eval_examples: Sequence[Mapping[str, Any]],
        task_id: str,
    ) -> Dict[str, Any]:
        verified: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []
        failure_reasons: Dict[str, int] = {}
        seen_hashes: set[str] = set()

        for index, generation in enumerate(generations):
            parsed, reason = self._parse_generation(generation)
            if not parsed:
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                failures.append(
                    {
                        "reason": reason,
                        "variant": generation.request.variant,
                        "finish_reason": generation.finish_reason,
                    }
                )
                continue

            digest = hashlib.sha1(parsed.dsl.strip().encode("utf-8")).hexdigest()
            if digest in seen_hashes:
                failure_reasons["duplicate_program"] = failure_reasons.get("duplicate_program", 0) + 1
                continue

            program, lint_issues, validation_error = self._prepare_program(parsed.dsl)
            if program is None:
                key = validation_error or "parse_error"
                failure_reasons[key] = failure_reasons.get(key, 0) + 1
                failures.append(
                    {
                        "reason": key,
                        "variant": generation.request.variant,
                        "issues": lint_issues,
                    }
                )
                continue

            verification = self._evaluate_program(program, train_examples, eval_examples, task_id)
            metadata = self._build_metadata(
                generation=generation,
                parsed=parsed,
                lint_issues=lint_issues,
                verification=verification,
                program_digest=digest,
            )

            if verification.passed:
                candidate = {
                    "candidate_id": f"llm-{task_id}-{index}",
                    "program": parsed.dsl,
                    "metadata": metadata,
                }
                token = self._issue_virtual_smt_token(task_id, index)
                if token:
                    candidate["smt_token"] = token
                verified.append(candidate)
                seen_hashes.add(digest)
            else:
                key = verification.failure_reason or "failed_verification"
                failure_reasons[key] = failure_reasons.get(key, 0) + 1
                metadata["note"] = key
                metadata["train_outputs"] = verification.train_outputs
                metadata["eval_outputs"] = verification.eval_outputs
                if self._settings.keep_failed_candidates:
                    failures.append({"program": parsed.dsl, "metadata": metadata})
                else:
                    failures.append({"program_digest": digest, "reason": key})

        verified.sort(key=lambda item: float(item.get("metadata", {}).get("confidence", 0.0)), reverse=True)
        if len(verified) > self._settings.refinement_candidates:
            verified = verified[: self._settings.refinement_candidates]
        return {
            "candidates": verified,
            "failures": failures,
            "failure_reasons": failure_reasons,
        }

    def _parse_generation(self, generation: LLMGenerationResult) -> Tuple[Optional[ParsedGeneration], str]:
        text = generation.completion.strip()
        if not text:
            return None, "empty_completion"
        snippet = self._extract_json_block(text)
        if not snippet:
            return None, "json_missing"
        try:
            payload = json.loads(snippet)
        except json.JSONDecodeError:
            return None, "json_decode_error"
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            return None, "json_not_object"
        dsl = payload.get("dsl") or payload.get("program")
        if not isinstance(dsl, str) or not dsl.strip():
            return None, "missing_dsl"
        rationale = str(payload.get("rationale") or payload.get("reasoning") or "").strip()
        confidence_value = payload.get("confidence", payload.get("score"))
        model_conf = self._safe_float(confidence_value, default=0.5)
        predictions = payload.get("test_outputs") or payload.get("test_prediction") or []
        if isinstance(predictions, Mapping):
            predictions = [predictions]
        elif not isinstance(predictions, Sequence):
            predictions = []
        notes = payload.get("notes")
        return (
            ParsedGeneration(
                dsl=dsl.strip(),
                rationale=rationale,
                model_confidence=max(0.0, min(1.0, model_conf)),
                predictions=predictions,
                payload=payload,
                notes=str(notes) if notes is not None else None,
            ),
            "",
        )

    def _extract_json_block(self, text: str) -> Optional[str]:
        tick = "\u0060" * 3
        if tick in text:
            start = text.find(tick)
            end = text.find(tick, start + len(tick))
            if end > start >= 0:
                block = text[start + len(tick) : end]
                if block.strip().startswith("json"):
                    block = block[4:]
                return block.strip()
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return None
        return text[first : last + 1]

    def _prepare_program(self, source: str) -> Tuple[Optional[Any], List[str], Optional[str]]:
        try:
            program = parse_program(source)
        except DSLParseError as exc:
            return None, [], f"parse_error:{exc}"[:128]
        assert self._interpreter is not None
        issues = validate_program(program, self._interpreter.registry)
        if issues:
            return program, issues, "validation_failed"
        return program, issues, None

    def _evaluate_program(
        self,
        program: Any,
        train_examples: Sequence[Mapping[str, Any]],
        eval_examples: Sequence[Mapping[str, Any]],
        task_id: str,
    ) -> CandidateVerification:
        assert self._interpreter is not None
        train_outputs: List[Dict[str, Any]] = []
        eval_outputs: List[Dict[str, Any]] = []
        matches = 0
        total_expected = 0
        failure_reason: Optional[str] = None

        for index, example in enumerate(train_examples):
            expected = example.get("output")
            start = time.perf_counter()
            try:
                trace = self._interpreter.run(
                    program,
                    example.get("input"),
                    metadata={"task_id": task_id, "lane": self.module_name, "example_index": index},
                )
            except InterpreterFailure as exc:
                failure_reason = f"interpreter_error:{getattr(exc, 'code', 'unknown')}"
                return CandidateVerification(
                    passed=False,
                    train_outputs=train_outputs,
                    eval_outputs=eval_outputs,
                    train_accuracy=0.0,
                    total_train_examples=total_expected,
                    failure_reason=failure_reason,
                )
            duration_ms = (time.perf_counter() - start) * 1000.0
            output_grid = trace.final_grid
            record = {
                "index": index,
                "grid": output_grid.to_list(),
                "duration_ms": duration_ms,
            }
            if expected is not None:
                total_expected += 1
                expected_grid = normalise_grid(expected)
                if grids_equal(output_grid, expected_grid):
                    matches += 1
                    record["matches_expected"] = True
                else:
                    record["matches_expected"] = False
            train_outputs.append(record)

        for index, example in enumerate(eval_examples):
            start = time.perf_counter()
            try:
                trace = self._interpreter.run(
                    program,
                    example.get("input"),
                    metadata={"task_id": task_id, "lane": self.module_name, "example_index": index, "role": "eval"},
                )
                eval_outputs.append(
                    {
                        "index": index,
                        "grid": trace.final_grid.to_list(),
                        "duration_ms": (time.perf_counter() - start) * 1000.0,
                    }
                )
            except InterpreterFailure as exc:  # pragma: no cover - defensive
                eval_outputs.append(
                    {
                        "index": index,
                        "error": f"interpreter_error:{getattr(exc, 'code', 'unknown')}",
                    }
                )

        train_accuracy = matches / total_expected if total_expected else 0.0
        passed = matches == total_expected
        return CandidateVerification(
            passed=passed,
            train_outputs=train_outputs,
            eval_outputs=eval_outputs,
            train_accuracy=train_accuracy,
            total_train_examples=total_expected,
            failure_reason=failure_reason,
        )

    def _build_metadata(
        self,
        *,
        generation: LLMGenerationResult,
        parsed: ParsedGeneration,
        lint_issues: Sequence[str],
        verification: CandidateVerification,
        program_digest: str,
    ) -> Dict[str, Any]:
        confidence = self._blend_confidence(parsed.model_confidence, verification.train_accuracy)
        prompt_hash = hashlib.sha1(
            json.dumps(generation.request.messages, sort_keys=True).encode("utf-8")
        ).hexdigest()
        metadata = {
            "prompt_version": self._settings.prompt_version,
            "prompt_variant": generation.request.variant,
            "prompt_metadata": generation.request.metadata,
            "prompt_hash": prompt_hash,
            "engine": self._engine_name,
            "sampling": {
                "temperature": generation.request.temperature,
                "top_p": generation.request.top_p,
                "max_new_tokens": generation.request.max_new_tokens,
            },
            "token_usage": {
                "prompt": generation.prompt_tokens,
                "completion": generation.completion_tokens,
                "total": generation.prompt_tokens + generation.completion_tokens,
            },
            "generation_finish_reason": generation.finish_reason,
            "generation_runtime_s": generation.runtime_s,
            "truncated_prompt": generation.truncated_prompt,
            "confidence": confidence,
            "model_confidence": parsed.model_confidence,
            "train_accuracy": verification.train_accuracy,
            "train_example_count": verification.total_train_examples,
            "verification_ready": verification.passed,
            "dsl_issues": list(lint_issues),
            "program_digest": program_digest,
            "rationale": parsed.rationale,
            "notes": parsed.notes,
            "predicted_eval_outputs": parsed.predictions,
            "llm_payload": parsed.payload,
        }
        metadata.setdefault("train_outputs", verification.train_outputs)
        metadata.setdefault("eval_outputs", verification.eval_outputs)
        return metadata

    def _blend_confidence(self, model_conf: float, train_accuracy: float) -> float:
        return round(max(0.0, min(1.0, 0.35 * model_conf + 0.65 * train_accuracy)), 4)

    def _issue_virtual_smt_token(self, task_id: str, sample_index: int) -> Optional[str]:
        if not self._smt.enabled:
            return None
        self._smt_counter += 1
        payload = f"{task_id}:{sample_index}:{self._smt_counter}:{time.time_ns()}:{self._smt.secret}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{self._smt.prefix}{digest[:24]}"

    @staticmethod
    def _safe_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
