from __future__ import annotations

import importlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Set

from .context import ModuleContext
from .module_base import ModuleError, SolverModule

LOGGER = logging.getLogger("arc.core.registry")


class ModuleRegistryError(RuntimeError):
    """Raised when a module cannot be constructed or initialised."""


@dataclass
class ModuleSpec:
    name: str
    class_path: str
    enabled: bool = True
    device: Optional[str] = None
    mock_class: Optional[str] = None
    use_mock: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, name: str, raw: Mapping[str, Any]) -> ModuleSpec:
        if "class" not in raw:
            raise ModuleRegistryError(f"Module '{name}' is missing required 'class' entry.")
        if not isinstance(raw["class"], str):
            raise ModuleRegistryError(f"Module '{name}' class entry must be a string import path.")
        if "device" in raw and raw["device"] is not None and not isinstance(raw["device"], str):
            raise ModuleRegistryError(f"Module '{name}' device entry must be a string when provided.")
        mock_class = raw.get("mock_class")
        if mock_class is not None and not isinstance(mock_class, str):
            raise ModuleRegistryError(f"Module '{name}' mock_class must be a string import path.")
        extras = {key: value for key, value in raw.items() if key not in {"class", "enabled", "device", "mock_class"}}
        raw_enabled = raw.get("enabled", True)
        enabled = raw_enabled if isinstance(raw_enabled, bool) else bool(raw_enabled)
        return cls(
            name=name,
            class_path=raw["class"],
            enabled=enabled,
            device=raw.get("device"),
            mock_class=mock_class,
            extras=extras,
        )


class ModuleRegistry:
    """Instantiates and manages solver modules from configuration."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        run_id: Optional[str] = None,
        shared_cache: Optional[MutableMapping[str, Any]] = None,
        metrics_sink: Optional[Any] = None,
        logger: Optional[logging.Logger] = None,
        force_enable: Optional[Iterable[str]] = None,
        force_disable: Optional[Iterable[str]] = None,
        use_mocks: Optional[Iterable[str]] = None,
    ) -> None:
        self.config = config
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        self.shared_cache: MutableMapping[str, Any] = shared_cache or {}
        self.metrics_sink = metrics_sink
        self.logger = logger or LOGGER
        self.force_enable: Set[str] = set(force_enable or [])
        self.force_disable: Set[str] = set(force_disable or [])
        self.use_mocks: Set[str] = set(use_mocks or [])

        raw_specs = config.get("modules", {})
        if not isinstance(raw_specs, Mapping):
            raise ModuleRegistryError("Top-level 'modules' config must be a mapping.")
        self._specs: Dict[str, ModuleSpec] = {}
        for name, payload in raw_specs.items():
            if not isinstance(payload, Mapping):
                raise ModuleRegistryError(f"Module '{name}' config must be a mapping.")
            hydrated_payload = dict(payload)
            hydrated_payload["enabled"] = self._resolve_interpolated_value(payload.get("enabled", True))
            hydrated_payload["device"] = self._resolve_interpolated_value(payload.get("device"))
            hydrated_payload["mock_class"] = self._resolve_interpolated_value(payload.get("mock_class"))
            spec = ModuleSpec.from_config(name, hydrated_payload)
            if name in self.force_enable:
                spec.enabled = True
            if name in self.force_disable:
                spec.enabled = False
            if name in self.use_mocks:
                spec.use_mock = True
            self._specs[name] = spec

        self._modules: Dict[str, SolverModule] = {}
        self._disabled: Dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def bootstrap(self) -> None:
        for name, spec in self._specs.items():
            if not spec.enabled:
                self._disabled[name] = "disabled_via_config"
                continue
            try:
                module = self._initialise_module(spec)
            except ModuleRegistryError as exc:
                self.logger.error("Failed to bootstrap module '%s': %s", name, exc)
                self._disabled[name] = str(exc)
            except ModuleError as exc:
                self.logger.error("Module '%s' raised error during initialise: %s", name, exc)
                self._disabled[name] = str(exc)
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.exception("Unexpected failure initialising module '%s'", name)
                self._disabled[name] = repr(exc)
            else:
                self._modules[name] = module

    def shutdown(self) -> None:
        for module in self._modules.values():
            try:
                module.shutdown()
            except Exception as exc:  # pragma: no cover - best effort
                self.logger.warning("Module '%s' raised during shutdown: %s", module.module_name, exc)

    def get(self, name: str) -> SolverModule:
        return self._modules[name]

    def active_modules(self) -> Dict[str, SolverModule]:
        return dict(self._modules)

    def disabled_modules(self) -> Dict[str, str]:
        return dict(self._disabled)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _initialise_module(self, spec: ModuleSpec) -> SolverModule:
        module_cls = self._resolve_class(spec.mock_class if spec.use_mock and spec.mock_class else spec.class_path)
        module: SolverModule = module_cls(config=self.config)  # type: ignore[call-arg]
        if not isinstance(module, SolverModule):
            raise ModuleRegistryError(
                f"Module '{spec.name}' does not inherit from SolverModule; received {module.__class__.__name__}."
            )

        module_logger = self.logger.getChild(spec.name)
        device = spec.device or self._resolve_device_default(spec.name)
        global_guardrails = dict(self.config.get("guardrails", {}) or {})
        module_guardrails: Dict[str, Any] = {}
        modules_cfg = self.config.get("modules", {})
        if isinstance(modules_cfg, Mapping):
            module_specific = modules_cfg.get(spec.name, {})
            if isinstance(module_specific, Mapping):
                module_guardrails = dict(module_specific.get("guardrails", {}) or {})
        if module_guardrails:
            global_guardrails.update(module_guardrails)

        extras = dict(spec.extras)
        if global_guardrails:
            extras.setdefault("guardrails", global_guardrails)
        extras["device"] = device
        context = ModuleContext(
            module_name=spec.name,
            config=self.config,
            shared_cache=self.shared_cache,
            run_id=self.run_id,
            logger=module_logger,
            metrics_sink=self.metrics_sink,
            extras=extras,
        )
        self._verify_device_contract(module, spec, device)
        module.initialize(context)
        return module

    def _resolve_device_default(self, module_name: str) -> Optional[str]:
        device_map = self.config.get("global", {}).get("device_map", {})
        if isinstance(device_map, Mapping):
            value = device_map.get(module_name)
            if isinstance(value, str):
                return value
        return None

    def _verify_device_contract(self, module: SolverModule, spec: ModuleSpec, device: Optional[str]) -> None:
        if module.capabilities.requires_gpu and (device is None or str(device).lower().startswith("cpu")):
            self.logger.warning(
                "Module '%s' requires a GPU but device '%s' configured. Expect degraded performance.",
                spec.name,
                device,
            )

    def _resolve_class(self, path: str) -> type:
        try:
            module_path, attr = path.rsplit(".", 1)
        except ValueError as exc:
            raise ModuleRegistryError(f"Invalid class path '{path}': {exc}") from exc
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise ModuleRegistryError(f"Could not import module '{module_path}': {exc}") from exc
        try:
            target = getattr(module, attr)
        except AttributeError as exc:
            raise ModuleRegistryError(f"Module '{module_path}' does not define attribute '{attr}'.") from exc
        if not isinstance(target, type):
            raise ModuleRegistryError(f"Resolved object '{path}' is not a class.")
        return target

    def _resolve_interpolated_value(self, value: Any) -> Any:
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            reference = value[2:-1]
            resolved = self._resolve_reference(reference)
            return resolved if resolved is not None else value
        return value

    def _resolve_reference(self, reference: str) -> Any:
        cursor: Any = self.config
        for token in reference.split("."):
            if isinstance(cursor, Mapping) and token in cursor:
                cursor = cursor[token]
            else:
                return None
        return cursor
