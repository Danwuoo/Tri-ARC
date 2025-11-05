from __future__ import annotations

import datetime as dt
import hashlib
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

import yaml

from arc.scheduler.cache import FeatureCache, NamespaceCache, configure_feature_cache
from arc.scheduler.features import TaskFeatures
from arc.scheduler.ingest import IngestedTask, SchedulerIngestor
from arc.scheduler.resources import ResourceTracker

LOGGER = logging.getLogger("arc.scheduler.core")

MODULES = ("symbolic", "ttt", "llm")


@dataclass(frozen=True)
class ModuleBudget:
    module: str
    priority: float
    weight: float
    soft_limit_s: float
    hard_limit_s: float
    expected_runtime_s: float
    start_delay_s: float
    donation_eligible: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": self.module,
            "priority": self.priority,
            "weight": self.weight,
            "soft_limit_s": self.soft_limit_s,
            "hard_limit_s": self.hard_limit_s,
            "expected_runtime_s": self.expected_runtime_s,
            "start_delay_s": self.start_delay_s,
            "donation_eligible": self.donation_eligible,
        }


@dataclass(frozen=True)
class ScheduledTask:
    task_id: str
    features: TaskFeatures
    allocations: Dict[str, ModuleBudget]
    matched_rules: List[str]
    donation_window_s: float
    global_budget_risk: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "features": self.features.to_dict(),
            "allocations": {name: budget.to_dict() for name, budget in self.allocations.items()},
            "matched_rules": list(self.matched_rules),
            "donation_window_s": self.donation_window_s,
            "global_budget_risk": self.global_budget_risk,
            "metadata": dict(self.metadata),
        }


@dataclass
class ModuleFeedback:
    successes: int = 0
    attempts: int = 0
    total_runtime_s: float = 0.0
    total_budget_s: float = 0.0

    def record(self, *, success: bool, runtime_s: float, budget_s: float) -> None:
        self.attempts += 1
        if success:
            self.successes += 1
        self.total_runtime_s += max(0.0, runtime_s)
        self.total_budget_s += max(0.0, budget_s)

    @property
    def success_rate(self) -> float:
        return float(self.successes / self.attempts) if self.attempts else 0.5

    @property
    def mean_runtime_s(self) -> float:
        return float(self.total_runtime_s / self.attempts) if self.attempts else 0.0

    @property
    def mean_budget_utilisation(self) -> float:
        if self.total_budget_s == 0.0:
            return 0.0
        return float(self.total_runtime_s / self.total_budget_s)


@dataclass(frozen=True)
class SchedulerPolicyRule:
    name: str
    conditions: Mapping[str, str]
    weights: Mapping[str, float]
    description: str = ""

    def matches(self, feature_dict: Mapping[str, Any]) -> bool:
        for path, condition in self.conditions.items():
            value = _resolve_feature_value(feature_dict, path)
            if value is None:
                return False
            if not _evaluate_condition(value, condition):
                return False
        return True


class SchedulerPolicy:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        default_weights = payload.get("default_weights", {})
        self.default_weights: Dict[str, float] = {
            module: float(default_weights.get(module, 1.0)) for module in MODULES
        }

        raw_rules = payload.get("rules", [])
        rules: List[SchedulerPolicyRule] = []
        for entry in raw_rules:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("name", "unnamed"))
            conditions = entry.get("conditions", {}) or {}
            weights = entry.get("weights", {}) or {}
            description = str(entry.get("description", ""))
            rules.append(
                SchedulerPolicyRule(
                    name=name,
                    conditions={str(k): str(v) for k, v in conditions.items()},
                    weights={str(k): float(v) for k, v in weights.items()},
                    description=description,
                )
            )
        self.rules = tuple(rules)

    def evaluate(self, features: TaskFeatures) -> Tuple[Dict[str, float], List[str]]:
        weights = dict(self.default_weights)
        matched: List[str] = []
        feature_dict = features.to_dict()

        for rule in self.rules:
            if rule.matches(feature_dict):
                matched.append(rule.name)
                for module, value in rule.weights.items():
                    weights[module] = weights.get(module, 1.0) * float(value)

        return weights, matched


class SchedulerCore:
    """Central scheduler applying policy rules, budgets, and feedback loops."""

    SNAPSHOT_INTERVAL = 20

    def __init__(
        self,
        config: MutableMapping[str, Any],
        *,
        feature_cache: FeatureCache | None = None,
        policy_path: Optional[Path] = None,
        logger: Optional[logging.Logger] = None,
        metrics_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        resource_tracker: Optional[ResourceTracker] = None,
    ) -> None:
        self.config = config
        self.logger = logger or LOGGER
        self._version_token = self._compute_version_token()
        self.feature_cache = feature_cache or configure_feature_cache(config, version=self._version_token)
        self.metrics_sink = metrics_sink
        self.ingestor = SchedulerIngestor(
            config,
            feature_cache=self.feature_cache,
            logger=self.logger.getChild("ingest"),
            metrics_sink=self.metrics_sink,
        )

        self.policy = self._load_policy(policy_path)
        self.feedback: Dict[str, ModuleFeedback] = {module: ModuleFeedback() for module in MODULES}
        self.projected_runtime_s: float = 0.0
        self.actual_runtime_s: float = 0.0
        self._scheduled_tasks: int = 0
        self._snapshot_dir = self._resolve_snapshot_dir()
        self._backlog_alert_threshold = float(
            config.get("scheduler", {}).get("backlog_alert_threshold", 50)
        )
        scheduler_cfg = self.config.get("scheduler", {})
        descriptor_cfg = scheduler_cfg.get("descriptor_cache", {}) or {}
        warm_cache_cfg = scheduler_cfg.get("warm_start_cache", {}) or {}
        self.descriptor_cache = NamespaceCache(
            "scheduler_descriptors",
            int(descriptor_cfg.get("max_items", 256)),
            version=self._version_token,
        )
        self.warm_start_cache = NamespaceCache(
            "scheduler_warm_starts",
            int(warm_cache_cfg.get("max_items", 128)),
            version=self._version_token,
        )

        resource_pool_cfg = scheduler_cfg.get("resource_pool", {}) or {}
        gpu_capacity = float(resource_pool_cfg.get("gpu_capacity", 1.0))
        cpu_capacity = float(resource_pool_cfg.get("cpu_worker_capacity", 16))
        device_map = {}
        global_cfg = self.config.get("global", {})
        if isinstance(global_cfg, Mapping):
            device_map = dict(global_cfg.get("device_map", {}) or {})
        self.resource_tracker = resource_tracker or ResourceTracker(
            device_map,
            gpu_capacity=gpu_capacity,
            cpu_worker_capacity=cpu_capacity,
        )
        self._risk_threshold = float(scheduler_cfg.get("halt_threshold", 0.95))

    def schedule(
        self,
        tasks: Iterable[Mapping[str, Any]],
        *,
        force_refresh: bool = False,
    ) -> List[ScheduledTask]:
        ingested = self.ingestor.ingest(tasks, force_refresh=force_refresh)
        scheduled: List[ScheduledTask] = []
        for task in ingested:
            current_risk = self._global_budget_risk()
            if current_risk >= self._risk_threshold:
                self.logger.error(
                    "Global budget risk %.2f exceeds threshold %.2f; halting new allocations.",
                    current_risk,
                    self._risk_threshold,
                )
                self._emit_metrics(
                    "scheduler_halt",
                    {
                        "risk": current_risk,
                        "threshold": self._risk_threshold,
                        "scheduled_tasks": self._scheduled_tasks,
                    },
                )
                break
            scheduled_task = self._schedule_task(task)
            self._register_resources(scheduled_task)
            self._emit_schedule_metrics(scheduled_task)
            scheduled.append(scheduled_task)
            self._scheduled_tasks += 1
            if self._scheduled_tasks % self.SNAPSHOT_INTERVAL == 0:
                self._persist_snapshot()
        return scheduled

    def record_feedback(
        self,
        task_id: str,
        module: str,
        *,
        success: bool,
        runtime_s: float,
        budget_s: float,
    ) -> None:
        if module not in self.feedback:
            self.feedback[module] = ModuleFeedback()
        self.feedback[module].record(success=success, runtime_s=runtime_s, budget_s=budget_s)
        self.actual_runtime_s += max(0.0, runtime_s)
        self.logger.debug(
            "Recorded feedback for task_id=%s module=%s success=%s runtime=%.2fs",
            task_id,
            module,
            success,
            runtime_s,
        )
        state = self.feedback[module]
        self._emit_metrics(
            "scheduler_feedback",
            {
                "task_id": task_id,
                "module": module,
                "success": success,
                "runtime_s": runtime_s,
                "budget_s": budget_s,
                "success_rate": state.success_rate,
                "mean_runtime_s": state.mean_runtime_s,
                "mean_budget_utilisation": state.mean_budget_utilisation,
            },
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _schedule_task(self, task: IngestedTask) -> ScheduledTask:
        self._cache_descriptors(task)
        weights, matched_rules = self.policy.evaluate(task.features)
        weights = self._apply_feedback(weights)

        allocations = self._build_allocations(weights)
        projected = sum(entry.soft_limit_s for entry in allocations.values())
        self.projected_runtime_s += projected

        global_risk = self._global_budget_risk()
        donation_window = float(self.config.get("scheduler", {}).get("donation_window_s", 15))

        self.logger.info(
            "Scheduled task_id=%s projected=%.1fs risk=%.2f matched_rules=%s",
            task.task_id,
            projected,
            global_risk,
            matched_rules,
        )

        return ScheduledTask(
            task_id=task.task_id,
            features=task.features,
            allocations=allocations,
            matched_rules=matched_rules,
            donation_window_s=donation_window,
            global_budget_risk=global_risk,
            metadata=task.metadata,
        )

    def _cache_descriptors(self, task: IngestedTask) -> None:
        self.descriptor_cache.set("grid", task.task_id, asdict(task.features.grid))
        self.descriptor_cache.set("palette", task.task_id, asdict(task.features.palette))
        self.descriptor_cache.set("symmetry", task.task_id, asdict(task.features.symmetry))
        self.descriptor_cache.set("objects", task.task_id, asdict(task.features.objects))

    def register_warm_start(self, module: str, task_id: str, payload: Any) -> None:
        self.warm_start_cache.set(module, task_id, payload)

    def _register_resources(self, scheduled_task: ScheduledTask) -> None:
        for module, budget in scheduled_task.allocations.items():
            record = self.resource_tracker.create_record(
                scheduled_task.task_id,
                module,
                expected_runtime_s=budget.expected_runtime_s,
                start_delay_s=budget.start_delay_s,
            )
            self.resource_tracker.register(scheduled_task.task_id, module, record)

    def _emit_schedule_metrics(self, scheduled_task: ScheduledTask) -> None:
        payload = {
            "task_id": scheduled_task.task_id,
            "matched_rules": list(scheduled_task.matched_rules),
            "global_budget_risk": scheduled_task.global_budget_risk,
            "donation_window_s": scheduled_task.donation_window_s,
            "risk_alert": scheduled_task.global_budget_risk >= self._risk_threshold,
            "allocations": {
                module: {
                    "priority": budget.priority,
                    "soft_limit_s": budget.soft_limit_s,
                    "hard_limit_s": budget.hard_limit_s,
                    "expected_runtime_s": budget.expected_runtime_s,
                    "start_delay_s": budget.start_delay_s,
                }
                for module, budget in scheduled_task.allocations.items()
            },
            "cache": {
                "feature": self.feature_cache.stats(),
                "descriptor": self.descriptor_cache.stats(),
                "warm_start": self.warm_start_cache.stats(),
            },
            "resources": self.resource_tracker.snapshot(),
        }
        self._evaluate_scheduler_guardrails(payload["cache"])
        self._emit_metrics("scheduler_allocate", payload)

    def _evaluate_scheduler_guardrails(self, cache_stats: Dict[str, Any]) -> None:
        guardrails = self.config.get("guardrails", {}).get("scheduler", {})
        if not guardrails:
            return
        alerts: list[Dict[str, Any]] = []

        feature_stats = cache_stats.get("feature", {}) if isinstance(cache_stats, dict) else {}
        feature_hit = feature_stats.get("hit_rate") if isinstance(feature_stats, dict) else None
        threshold = guardrails.get("feature_cache_min_hit_rate")
        if threshold is not None and feature_hit is not None and feature_hit < float(threshold):
            alerts.append({
                "type": "feature_cache_hit_rate",
                "limit": float(threshold),
                "observed": feature_hit,
            })

        descriptor_stats = cache_stats.get("descriptor", {}) if isinstance(cache_stats, dict) else {}
        descriptor_overall = descriptor_stats.get("overall", {}) if isinstance(descriptor_stats, dict) else {}
        descriptor_hit = descriptor_overall.get("hit_rate") if isinstance(descriptor_overall, dict) else None
        descriptor_threshold = guardrails.get("descriptor_cache_min_hit_rate")
        if descriptor_threshold is not None and descriptor_hit is not None and descriptor_hit < float(descriptor_threshold):
            alerts.append({
                "type": "descriptor_cache_hit_rate",
                "limit": float(descriptor_threshold),
                "observed": descriptor_hit,
            })

        if alerts:
            self._emit_metrics("scheduler_guardrail", {"alerts": alerts})

    def _emit_metrics(self, event: str, payload: Dict[str, Any]) -> None:
        if not self.metrics_sink:
            return
        record = {
            "event": event,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        record.update(payload)
        try:
            self.metrics_sink(record)
        except Exception as exc:  # pragma: no cover - metrics failures should not interrupt scheduling
            self.logger.debug("Metrics sink failed for event %s: %s", event, exc)

    def _build_allocations(self, weights: Mapping[str, float]) -> Dict[str, ModuleBudget]:
        module_configs = self.config.get("modules", {})
        scheduler_cfg = self.config.get("scheduler", {})
        default_soft = float(scheduler_cfg.get("default_soft_timeout_s", 90))
        default_hard = float(scheduler_cfg.get("default_hard_timeout_s", 150))

        allocations: Dict[str, ModuleBudget] = {}
        sum_weights = sum(max(0.01, float(weights.get(module, 1.0))) for module in MODULES)
        sum_weights = sum_weights or 0.01
        sorted_modules = sorted(MODULES, key=lambda mod: float(weights.get(mod, 1.0)), reverse=True)

        for index, module in enumerate(sorted_modules):
            module_cfg = module_configs.get(module, {})
            soft_limit = float(module_cfg.get("soft_timeout_s", default_soft))
            hard_limit = float(module_cfg.get("hard_timeout_s", default_hard))
            weight = float(weights.get(module, 1.0))

            priority = max(0.0, weight) / sum_weights

            soft = max(5.0, soft_limit * weight)
            hard = max(soft + 5.0, hard_limit * max(1.0, weight))

            start_delay = 0.0 if index == 0 else 5.0
            if index > 1:
                start_delay = 10.0

            allocations[module] = ModuleBudget(
                module=module,
                priority=priority,
                weight=weight,
                soft_limit_s=soft,
                hard_limit_s=hard,
                expected_runtime_s=soft,
                start_delay_s=start_delay,
                donation_eligible=True,
            )

        return allocations

    def _apply_feedback(self, weights: Mapping[str, float]) -> Dict[str, float]:
        adjusted = dict(weights)
        for module in MODULES:
            multiplier = self._feedback_multiplier(module)
            adjusted[module] = adjusted.get(module, 1.0) * multiplier
        return adjusted

    def _feedback_multiplier(self, module: str) -> float:
        state = self.feedback.get(module)
        if state is None or state.attempts < 3:
            return 1.0

        success_rate = state.success_rate
        utilisation = state.mean_budget_utilisation

        multiplier = 1.0
        if success_rate >= 0.7:
            multiplier += 0.1
        elif success_rate <= 0.35:
            multiplier -= 0.15

        if utilisation <= 0.5:
            multiplier -= 0.1
        elif utilisation >= 0.9:
            multiplier += 0.05

        return max(0.5, min(1.5, multiplier))

    def _global_budget_risk(self) -> float:
        max_hours = float(self.config.get("global", {}).get("max_wall_clock_hours", 12))
        total_budget_seconds = max_hours * 3600.0
        envelope = max(self.projected_runtime_s, self.actual_runtime_s)
        return min(1.0, envelope / total_budget_seconds) if total_budget_seconds else 0.0

    def _persist_snapshot(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        filename = f"scheduler_budget_{now.strftime('%Y%m%dT%H%M%SZ')}.md"
        path = self._snapshot_dir / filename
        header = [
            f"# Scheduler Budget Snapshot ({now.isoformat()})",
            "",
            f"- Projected runtime seconds: {self.projected_runtime_s:.2f}",
            f"- Actual runtime seconds: {self.actual_runtime_s:.2f}",
            "",
            "| Module | Success Rate | Mean Runtime (s) | Budget Utilisation |",
            "|--------|--------------|------------------|--------------------|",
        ]
        rows = []
        for module in MODULES:
            feedback = self.feedback.get(module) or ModuleFeedback()
            rows.append(
                f"| {module} | {feedback.success_rate:.2f} | {feedback.mean_runtime_s:.2f} | {feedback.mean_budget_utilisation:.2f} |"
            )
        resource_summary = self.resource_tracker.device_summary()
        resource_lines: List[str] = []
        if resource_summary:
            resource_lines.extend(
                [
                    "",
                    "| Device | Allocations | Total Expected Runtime (s) | Avg Expected Runtime (s) |",
                    "|--------|-------------|----------------------------|--------------------------|",
                ]
            )
            for device, metrics in resource_summary.items():
                resource_lines.append(
                    f"| {device} | {metrics['allocations']:.0f} | {metrics['total_expected_runtime_s']:.2f} | {metrics['avg_expected_runtime_s']:.2f} |"
                )

        feature_stats = self.feature_cache.stats()
        descriptor_stats = self.descriptor_cache.stats()
        warm_stats = self.warm_start_cache.stats()
        cache_section = [
            "",
            "## Cache Statistics",
            f"- Feature cache hit rate: {feature_stats.get('hit_rate', 0.0):.2f} ({feature_stats.get('hits', 0)} hits / {feature_stats.get('misses', 0)} misses)",
            f"- Descriptor cache hit rate: {descriptor_stats['overall'].get('hit_rate', 0.0):.2f}",
            f"- Warm start cache hit rate: {warm_stats['overall'].get('hit_rate', 0.0):.2f}",
        ]

        content = "\n".join(header + rows + resource_lines + cache_section) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.logger.info("Persisted scheduler snapshot to %s", path)

    def _load_policy(self, policy_path: Optional[Path]) -> SchedulerPolicy:
        scheduler_cfg = self.config.get("scheduler", {})
        path_value = policy_path or scheduler_cfg.get("feature_lookup", "configs/scheduler/features.yaml")
        policy_file = Path(path_value)
        if not policy_file.is_absolute():
            policy_file = Path.cwd() / policy_file
        if not policy_file.exists():
            raise FileNotFoundError(f"Scheduler policy file not found: {policy_file}")
        with policy_file.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        if not isinstance(payload, Mapping):
            raise ValueError("Scheduler policy file must define a mapping.")
        return SchedulerPolicy(payload)

    def _resolve_snapshot_dir(self) -> Path:
        scheduler_cfg = self.config.get("scheduler", {})
        diagnostics = scheduler_cfg.get("diagnostics", {}) or {}
        snapshot_dir = diagnostics.get("snapshot_dir", "reports")
        path = Path(snapshot_dir)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _compute_version_token(self) -> str:
        scheduler_cfg = self.config.get("scheduler", {})
        diagnostics = scheduler_cfg.get("diagnostics", {}) or {}
        salt = str(diagnostics.get("fingerprint_salt", "scheduler_v1"))
        fingerprint_components = [salt]

        for section, key in (("symbolic", "library_path"), ("ttt", "model_path"), ("llm", "model_path")):
            section_cfg = self.config.get(section, {})
            if not isinstance(section_cfg, Mapping):
                continue
            raw_path = section_cfg.get(key)
            if not raw_path:
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            if candidate.exists():
                stat = candidate.stat()
                fingerprint_components.append(f"{candidate.name}:{int(stat.st_mtime)}:{stat.st_size}")

        digest = hashlib.sha1("|".join(fingerprint_components).encode("utf-8")).hexdigest()
        return digest[:12]


# ---------------------------------------------------------------------- #
# Helper utilities
# ---------------------------------------------------------------------- #
def _resolve_feature_value(features: Mapping[str, Any], path: str) -> Optional[Any]:
    cursor: Any = features
    for token in path.split("."):
        if isinstance(cursor, Mapping) and token in cursor:
            cursor = cursor[token]
        else:
            return None
    return cursor


def _evaluate_condition(value: Any, condition: str) -> bool:
    condition = condition.strip()
    try:
        numeric = float(value)
    except Exception:
        numeric = None

    if condition.startswith(">="):
        target = float(condition[2:])
        return numeric is not None and numeric >= target
    if condition.startswith("<="):
        target = float(condition[2:])
        return numeric is not None and numeric <= target
    if condition.startswith(">"):
        target = float(condition[1:])
        return numeric is not None and numeric > target
    if condition.startswith("<"):
        target = float(condition[1:])
        return numeric is not None and numeric < target
    if condition.startswith("=="):
        target = float(condition[2:])
        return numeric is not None and numeric == target
    if condition.startswith("!="):
        target = float(condition[2:])
        return numeric is not None and numeric != target

    # Fallback equality for stringified condition.
    try:
        target = float(condition)
        if numeric is not None:
            return numeric == target
    except Exception:
        pass
    return str(value) == condition

