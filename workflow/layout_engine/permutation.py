"""Reproducible patch-location shuffle + strip/patch index labels.

printtarg keeps its patch *data* in canonical order and only permutes which
sheet *location* each patch lands on, reproducibly from a single seed
(``RANDOM_START``).  ChromIQ owns both the raster and the ``.ti2``, so it needs
its own reproducible permutation rather than Argyll's exact LFSR — Python's
``random.Random`` (Mersenne Twister) is deterministic across platforms and
versions, so the same seed always yields the same layout.

Index labels follow Argyll's odometer: ``A…Z, AA…AZ, BA…BZ`` for alphabetic
patterns (the spreadsheet-column scheme the user described), decimal counting
for numeric patterns.  ``SAMPLE_LOC`` = strip label + patch label, with
``INDEX_ORDER = STRIP_THEN_PATCH``.
"""
from __future__ import annotations

import random

DEFAULT_STRIP_PATTERN = "A-Z, A-Z"
DEFAULT_PATCH_PATTERN = "0-9,@-9,@-9;1-999"


def alpha_label(n: int) -> str:
    """1-based spreadsheet-column label: 1→A, 26→Z, 27→AA, 52→AZ, 53→BA …"""
    if n < 1:
        raise ValueError("alpha_label is 1-based")
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def _is_alpha_pattern(pattern: str) -> bool:
    p = pattern.upper()
    return "A-Z" in p


def make_labeller(pattern: str):
    """Return a 1-based ``int -> str`` labeller for an Argyll index *pattern*.

    Phase-1 scope: alphabetic patterns (containing ``A-Z``) use
    :func:`alpha_label`; everything else counts in decimal.  This covers every
    pattern ChromIQ offers (Argyll default, numeric, ``A-Z``); the full Argyll
    pattern grammar can be added later behind the same interface.
    """
    if _is_alpha_pattern(pattern):
        return alpha_label
    return lambda n: str(n)


def location_label(slot: int, steps_in_pass: int,
                   strip_pattern: str = DEFAULT_STRIP_PATTERN,
                   patch_pattern: str = DEFAULT_PATCH_PATTERN) -> str:
    """Label for grid *slot* (0-based, STRIP_THEN_PATCH order).

    Strip = ``slot // steps_in_pass``, position in pass = ``slot % steps_in_pass``.
    """
    if steps_in_pass < 1:
        raise ValueError("steps_in_pass must be >= 1")
    strip_idx, patch_idx = divmod(slot, steps_in_pass)
    strip = make_labeller(strip_pattern)(strip_idx + 1)
    patch = make_labeller(patch_pattern)(patch_idx + 1)
    return f"{strip}{patch}"


def pick_seed(rng: random.Random | None = None) -> int:
    """A fresh full-range seed to show the user after randomising."""
    r = rng or random
    return r.randint(0, 2_147_483_647)


def location_permutation(n: int, seed: int, randomize: bool = True) -> list[int]:
    """Map canonical patch index → sheet slot.

    With *randomize* False this is the identity (A1, A2, A3 … like printtarg
    ``-r``).  With it True the slots are shuffled reproducibly from *seed*.
    """
    slots = list(range(n))
    if randomize:
        random.Random(seed).shuffle(slots)
    return slots


def preview(total: int, steps_in_pass: int,
            strip_pattern: str = DEFAULT_STRIP_PATTERN,
            patch_pattern: str = DEFAULT_PATCH_PATTERN,
            count: int = 12) -> tuple[list[str], str]:
    """First *count* location labels and the last one — for the UI live preview.

    These are the canonical (unshuffled) slot labels, i.e. exactly what gets
    printed and what chartread announces.
    """
    labels = [
        location_label(k, steps_in_pass, strip_pattern, patch_pattern)
        for k in range(total)
    ]
    return labels[:count], (labels[-1] if labels else "")
