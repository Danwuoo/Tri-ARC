from __future__ import annotations

import gzip
import json
import logging
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict


def configure_logging(
    log_dir: Path,
    runtime_log_name: str,
    level: str = "INFO",
    *,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    compress_rotated: bool = False,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / runtime_log_name

    handler = RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backup_count)
    if compress_rotated:
        handler.namer = lambda name: f"{name}.gz"

        def _rotator(source: str, dest: str) -> None:
            with open(source, "rb") as src, gzip.open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            Path(source).unlink(missing_ok=True)

        handler.rotator = _rotator

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    return log_path


def append_metric(metrics_file: Path, payload: Dict[str, Any]) -> None:
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    with metrics_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
