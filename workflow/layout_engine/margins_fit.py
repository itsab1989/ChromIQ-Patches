"""Raise a layout's page margins so the realised patch area meets the user's
per-side margin *minimums* (the thresholds defined in Preferences → Margin
Thresholds).

The thresholds were, until now, a post-hoc *inspection* — the Measured-from-
Preview panel warned you only after a chart existed. The layout engine never
read them, so it could happily place patches inside a minimum (e.g. an i1Pro
top run-up of 27.8 mm under a 38 mm rule). This module closes that gap by
treating each threshold as a minimum margin and clamping the effective margins
up to it *before* anything is rendered, so both the patch-count estimate and the
actual chart honour the rule (one source of truth — they share
``geom_from_build_kwargs``). The engine stays settings-agnostic: thresholds
arrive as a plain ``{"L","R","T","B": mm}`` dict supplied by the UI (#93).

The realised top inset includes the strip-label band and the left inset includes
the clip border, and the block is centred in the vertical slack — so a margin
bump does not map 1:1 to the inset it moves. Rather than invert that algebra we
iterate: measure the realised insets, bump each deficient side by its shortfall,
recompute, repeat until every side meets its minimum (or the page can't hold
them).
"""
from __future__ import annotations

from . import geometry, instruments, papers

# build_kwargs "margins" tuple order, matching instruments.build().
_T, _R, _B, _L = 0, 1, 2, 3
_TOL = 0.05            # mm: treat sub-0.05 mm shortfalls as met
_MAX_ITERS = 40


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def clamp_margins_to_thresholds(
    kw: dict, thresholds: dict | None
) -> tuple[dict, list[str]]:
    """Return ``(build_kwargs, notes)`` with margins raised to meet *thresholds*.

    *thresholds* is the entry for this chart's instrument/paper/orientation
    combo (``{"L","R","T","B": mm, ...}``) or ``None``. A no-op (original kw,
    no notes) when there are no usable thresholds. *notes* describe each side
    that was raised, for the log / info box.
    """
    if not thresholds:
        return kw, []
    thr = {k: _num(thresholds.get(k)) for k in ("L", "R", "T", "B")}
    thr = {k: v for k, v in thr.items() if v is not None and v > 0}
    if not thr:
        return kw, []
    try:
        w_mm, h_mm = papers.dimensions_mm(kw.get("paper", "A4"))
    except Exception:
        return kw, []

    # Seed from the per-side margins tuple (recipe path) or, when absent (the
    # basic build-kwargs path), from the uniform `border`. `border` itself is
    # left untouched — it drives the instrument leader / clip-holder base — so we
    # only ever override the page-edge margins.
    seed = kw.get("margins")
    if not seed:
        b = float(kw.get("border", 6.0))
        seed = (b, b, b, b)
    base = list(seed)
    orig = tuple(base)
    margins = list(base)
    # side label -> (margins index, paper extent that bounds the bump)
    sides = {"T": (_T, h_mm), "R": (_R, w_mm), "B": (_B, h_mm), "L": (_L, w_mm)}

    for _ in range(_MAX_ITERS):
        test = {**kw, "margins": tuple(margins)}
        try:
            geom = instruments.geom_from_build_kwargs(test)
            cap = geometry.patches_per_sheet(geom, w_mm, h_mm)
            layout = geometry.compute(geom, w_mm, h_mm, cap)
            L, R, T, B = geometry.realized_margins_mm(geom, w_mm, h_mm, layout)
        except geometry.LayoutError:
            break                       # page already over-constrained; stop here
        realised = {"L": L, "R": R, "T": T, "B": B}
        worst = 0.0
        for k, want in thr.items():
            deficit = want - realised[k]
            if deficit > _TOL:
                idx, extent = sides[k]
                # Don't let a bump consume the whole sheet (keeps it solvable).
                margins[idx] = min(margins[idx] + deficit, extent * 0.45)
                worst = max(worst, deficit)
        if worst <= _TOL:
            break

    # Round the bumped margins to 0.1 mm for a clean recipe (round UP so a bump
    # can never fall back below the threshold it just satisfied).
    import math
    for k, (idx, _extent) in sides.items():
        if k in thr and margins[idx] > orig[idx] + _TOL:
            margins[idx] = math.ceil(margins[idx] * 10.0) / 10.0

    notes: list[str] = []
    labels = {"T": "Top", "R": "Right", "B": "Bottom", "L": "Left"}
    for k, (idx, _extent) in sides.items():
        if k in thr and margins[idx] > orig[idx] + _TOL:
            notes.append(
                f"{labels[k]} margin raised {orig[idx]:g}→{margins[idx]:g} mm "
                f"to meet your {thr[k]:g} mm minimum")
    return {**kw, "margins": tuple(margins)}, notes
