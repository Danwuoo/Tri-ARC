from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


def _normalize_level(level: Optional[str]) -> int:
    if not level:
        return logging.INFO
    if isinstance(level, str):
        candidate = getattr(logging, level.upper(), None)
        if isinstance(candidate, int):
            return candidate
    return logging.INFO


def setup_logging(level: Optional[str], logfile: Path, *, include_console: bool = True) -> logging.Logger:
    """
    Configure the shared Tri-ARC logger.

    Parameters
    ----------
    level:
        Logging level name (e.g. "INFO"). Falls back to INFO when unspecified or invalid.
    logfile:
        Path to the log file to append to. Parent directories are created automatically.
    include_console:
        When True the logger also emits to stderr for interactive feedback.
    """
    logfile.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("tri_arc")
    logger.setLevel(_normalize_level(level))
    logger.propagate = False

    # Replace existing handlers to prevent duplicate log lines during repeated invocations.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(logfile, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if include_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.debug("Logger initialised (level=%s, logfile=%s)", logging.getLevelName(logger.level), logfile)
    return logger

