from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "docs" / "CONFIG_DEFAULTS.yaml"


def _deep_update(target: MutableMapping[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), MutableMapping):
            _deep_update(target[key], value)  # type: ignore[index]
        else:
            target[key] = value  # type: ignore[index]


def _maybe_override_path(cfg: Dict[str, Any], key: str, env_var: str, default: Optional[Path] = None) -> None:
    override = os.environ.get(env_var)
    if override:
        cfg["global"][key] = override
    elif default is not None:
        cfg["global"][key] = str(default)


def _apply_environment_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = copy.deepcopy(config)
    cfg.setdefault("global", {})

    kaggle_root = Path("/kaggle/working/Tri-ARC")
    kaggle_temp = Path("/kaggle/temp")
    project_root = os.environ.get("TRI_ARC_ROOT")

    if kaggle_root.exists():
        _maybe_override_path(cfg, "data_root", env_var="TRI_ARC_DATA_ROOT", default=kaggle_root / "data/arcagi2")
        _maybe_override_path(cfg, "cache_root", env_var="TRI_ARC_CACHE_ROOT", default=kaggle_root / "cache")
        _maybe_override_path(cfg, "log_root", env_var="TRI_ARC_LOG_ROOT", default=kaggle_temp / "Tri-ARC/logs")
    else:
        base_root = Path(project_root) if project_root else PROJECT_ROOT
        _maybe_override_path(cfg, "data_root", env_var="TRI_ARC_DATA_ROOT", default=base_root / "data/arcagi2")
        _maybe_override_path(cfg, "cache_root", env_var="TRI_ARC_CACHE_ROOT", default=base_root / "cache")
        _maybe_override_path(cfg, "log_root", env_var="TRI_ARC_LOG_ROOT", default=base_root / "logs")

    return cfg


def load_config(
    path: Optional[Path] = None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config path {config_path} not found.")

    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle)

    if not isinstance(raw_config, dict):
        raise ValueError("Config file must define a mapping at the top level.")

    cfg = _apply_environment_overrides(raw_config)

    if overrides:
        _deep_update(cfg, overrides)

    return cfg
