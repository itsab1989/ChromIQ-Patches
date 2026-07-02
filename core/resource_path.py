"""PyInstaller-compatible resource path resolver."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent


def resource_path(relative: str) -> Path:
    """Return absolute path to a bundled resource.

    In a frozen PyInstaller bundle sys._MEIPASS points to the temp extraction
    directory.  During development the project root is used instead.
    """
    base = Path(getattr(sys, "_MEIPASS", _PROJECT_ROOT))
    return base / relative


def argyll_binary(name: str) -> str:
    """Return the platform-correct binary name (appends .exe on Windows)."""
    return name + ".exe" if sys.platform == "win32" else name
