"""Centralised logging setup for ChromIQ."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime

from core.platform_paths import log_dir


def _log_path():
    base = log_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / "chromiq.log"


def _write_session_banner(path) -> None:
    try:
        from core.version import APP_VERSION
    except Exception:
        APP_VERSION = "unknown"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    py = sys.version.split()[0]
    banner = (
        "\n"
        "================================================================================\n"
        f"=== ChromIQ session started — {ts}  v{APP_VERSION}  ({sys.platform}, py {py})\n"
        "================================================================================\n"
    )
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(banner)
    except Exception:
        pass


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    path = _log_path()
    _write_session_banner(path)

    fh = logging.handlers.RotatingFileHandler(
        path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
