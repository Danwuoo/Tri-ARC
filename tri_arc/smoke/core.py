from __future__ import annotations

import dataclasses
import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, List, Literal, MutableMapping, Optional, Sequence


SmokeStatus = Literal["pass", "warn", "fail"]
SmokeTest = Callable[["SmokeContext"], "SmokeResult"]


@dataclass(slots=True)
class SmokeContext:
    """Execution context shared by smoke tests."""

    root_dir: Path
    env: str
    reports_dir: Path
    log_dir: Path
    data_root: Path
    config_path: Path
    wheel_roots: Sequence[Path] = field(default_factory=tuple)
    extra: MutableMapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_root(
        cls,
        root_dir: Path,
        env: str,
        *,
        reports_dir: Optional[Path] = None,
        log_dir: Optional[Path] = None,
        data_root: Optional[Path] = None,
        config_path: Optional[Path] = None,
        wheel_roots: Optional[Sequence[Path]] = None,
        extra: Optional[MutableMapping[str, Any]] = None,
    ) -> "SmokeContext":
        root_dir = root_dir.resolve()
        if reports_dir is None:
            reports_dir = root_dir / "reports" / "smoke_logs"
        if log_dir is None:
            log_dir = root_dir / "logs"
        if data_root is None:
            data_root = root_dir / "data" / "arcagi2"
        if config_path is None:
            config_path = root_dir / "docs" / "CONFIG_DEFAULTS.yaml"
        computed_wheel_roots: List[Path] = []
        if wheel_roots:
            computed_wheel_roots.extend(Path(p).resolve() for p in wheel_roots)
        vendor_default = root_dir / "vendor" / "wheels"
        if vendor_default.exists():
            computed_wheel_roots.append(vendor_default)
        return cls(
            root_dir=root_dir,
            env=env,
            reports_dir=reports_dir.resolve(),
            log_dir=log_dir.resolve(),
            data_root=data_root.resolve(),
            config_path=config_path.resolve(),
            wheel_roots=tuple(dict.fromkeys(p.resolve() for p in computed_wheel_roots)),
            extra=dict(extra or {}),
        )


@dataclass(slots=True)
class SmokeResult:
    """Structured record for an individual smoke test."""

    name: str
    status: SmokeStatus
    duration_s: float
    details: MutableMapping[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        payload = dataclasses.asdict(self)
        payload["duration_s"] = round(self.duration_s, 4)
        return payload


class SmokeSuite:
    """Runner for a collection of smoke tests."""

    def __init__(self, tests: Iterable[SmokeTest]) -> None:
        self._tests: List[SmokeTest] = list(tests)
        if not self._tests:
            raise ValueError("SmokeSuite requires at least one test.")

    def run(self, context: SmokeContext, *, stop_on_fail: bool = False) -> List[SmokeResult]:
        results: List[SmokeResult] = []
        for test in self._tests:
            result = self._run_single(test, context)
            results.append(result)
            if stop_on_fail and result.status == "fail":
                break
        return results

    @staticmethod
    def _run_single(test: SmokeTest, context: SmokeContext) -> SmokeResult:
        start = time.perf_counter()
        name = getattr(test, "__name__", test.__class__.__name__)
        try:
            result = test(context)
            if not isinstance(result, SmokeResult):
                raise TypeError(f"Smoke test {name} returned unexpected type {type(result)!r}.")
            outcome = result
        except Exception as exc:  # pragma: no cover - defensive guard
            duration = time.perf_counter() - start
            outcome = SmokeResult(
                name=name,
                status="fail",
                duration_s=duration,
                details={},
                error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
            )
        else:
            outcome.duration_s = time.perf_counter() - start
        return outcome

    @staticmethod
    def summarise(results: Sequence[SmokeResult]) -> dict:
        counts = {"pass": 0, "warn": 0, "fail": 0}
        total_duration = 0.0
        for result in results:
            counts[result.status] += 1
            total_duration += result.duration_s
        if counts["fail"]:
            overall = "fail"
        elif counts["warn"]:
            overall = "warn"
        else:
            overall = "pass"
        return {
            "overall": overall,
            "counts": counts,
            "total_duration_s": round(total_duration, 4),
        }

    @staticmethod
    def to_json(
        context: SmokeContext, results: Sequence[SmokeResult], summary: dict, *, timestamp: Optional[str] = None
    ) -> str:
        payload = {
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "environment": context.env,
            "root_dir": str(context.root_dir),
            "data_root": str(context.data_root),
            "reports_dir": str(context.reports_dir),
            "config_path": str(context.config_path),
            "wheel_roots": [str(path) for path in context.wheel_roots],
            "summary": summary,
            "results": [result.to_dict() for result in results],
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    @staticmethod
    def to_markdown(
        context: SmokeContext, results: Sequence[SmokeResult], summary: dict, *, timestamp: Optional[str] = None
    ) -> str:
        ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        lines = [
            f"# Smoke Validation - {context.env.capitalize()} - {ts}",
            "",
            f"- Environment: `{context.env}`",
            f"- Root dir: `{context.root_dir}`",
            f"- Data root: `{context.data_root}`",
            f"- Config: `{context.config_path}`",
            f"- Wheel roots: {', '.join(f'`{path}`' for path in context.wheel_roots) or 'None'}",
            "",
            "## Summary",
            f"- Overall status: **{summary['overall'].upper()}**",
            f"- Total duration: {summary['total_duration_s']} s",
            f"- Passed: {summary['counts']['pass']}",
            f"- Warned: {summary['counts']['warn']}",
            f"- Failed: {summary['counts']['fail']}",
            "",
            "## Results",
        ]
        for result in results:
            lines.append(f"### {result.name}")
            lines.append(f"- Status: **{result.status.upper()}**")
            lines.append(f"- Duration: {round(result.duration_s, 4)} s")
            if result.details:
                lines.append("```json")
                lines.append(json.dumps(result.details, indent=2, sort_keys=True))
                lines.append("```")
            if result.error:
                lines.append("> Error:")
                lines.append(f"> {result.error}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
