from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_NAME = "tj-nearby-activity.log"


def activity_log_path(state_dir: Path) -> Path:
    log_dir = state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / LOG_NAME


def setup_activity_logger(state_dir: Path) -> logging.Logger:
    """Create one small rotating activity log for the desktop app.

    The log intentionally records lifecycle, GPS/API phases, result counts, and
    errors. It never writes API tokens or raw authentication payloads.
    """
    path = activity_log_path(state_dir)
    logger = logging.getLogger("tj_nearby.activity")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    resolved = str(path.resolve())
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "") == resolved:
            return logger

    handler = RotatingFileHandler(
        path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def tail_activity_log(state_dir: Path, *, max_lines: int = 500) -> str:
    path = activity_log_path(state_dir)
    if not path.exists():
        return "(activity log belum tersedia)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"(activity log tidak dapat dibaca: {exc})"
    return "\n".join(lines[-max(1, max_lines):])
