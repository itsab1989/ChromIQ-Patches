"""Auto-detect the ArgyllCMS binary directory."""
from __future__ import annotations

from pathlib import Path
from shutil import which

from core.logger import get_logger
from core.platform_paths import argyll_candidate_dirs
from core.resource_path import argyll_binary

log = get_logger(__name__)

_REQUIRED = ("targen", "printtarg", "chartread", "colprof")
_OPTIONAL = ("profcheck", "printcal", "applycal", "iccgamut", "viewgam")


def all_tools_present(bin_dir: Path) -> bool:
    return all((bin_dir / argyll_binary(t)).exists() for t in _REQUIRED)


def find_argyll_bin_path() -> Path | None:
    """Return the first directory that contains all required ArgyllCMS tools, or None."""

    # 1. Check the system PATH first
    for tool in _REQUIRED:
        found = which(argyll_binary(tool))
        if found:
            candidate = Path(found).parent
            if all_tools_present(candidate):
                log.info("ArgyllCMS found in PATH at %s", candidate)
                return candidate

    # 2. Fall back to platform-specific well-known locations
    for candidate in argyll_candidate_dirs():
        if all_tools_present(candidate):
            log.info("ArgyllCMS auto-detected at %s", candidate)
            return candidate

    log.warning("ArgyllCMS binaries not found in any known location")
    return None
