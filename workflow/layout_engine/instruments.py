"""Per-instrument chart geometry, reverse-engineered from ArgyllCMS ``printtarg.c``.

Every constant here was read from ``target/printtarg.c`` (v3.5.0) and then
**verified** against a live ``printtarg`` option matrix: for a 60-patch RGB
``.ti1`` on A4 these reproduce printtarg's reported ``STEPS_IN_PASS`` /
``PASSES_IN_STRIPS2`` / padded patch count exactly (i1 21×3→63, p3 9×7,
ColorMunki 15×4→60, DTP41 25×3→75, DTP51 19×4→76, SpectroScan 39×2,
SpectroScan hex 45×2, A4-landscape 16×4).

A :class:`Geom` carries every value :func:`workflow.layout_engine.geometry`
needs.  Values that depend on patch scale (``-a``), spacer scale (``-A``),
high-density / hex (``-h``), spacers on/off (``-n``), the page margin (``-m``)
or the left clip border (``-L``) are resolved in :func:`build`.

All lengths are millimetres.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

MAXPPROW = 500          # printtarg.c: absolute max patches per pass/row
MAXROWLEN = 5000.0      # printtarg.c MAXROWLEN — large enough to never bind for sheet sizes

# Instrument flag (printtarg -i value) -> CGATS TARGET_INSTRUMENT string.
TARGET_INSTRUMENT_NAME: dict[str, str] = {
    "i1": "GretagMacbeth i1 Pro",
    "p3": "GretagMacbeth i1 Pro",      # printtarg stamps the 3+ the same way
    "CM": "X-Rite ColorMunki",
    "41": "X-Rite DTP41",
    "51": "X-Rite DTP51",
    "SS": "GretagMacbeth SpectroScan",
}

# Instruments ChromIQ never lays out itself (delegated to i1Profiler).
DELEGATED = {"isis"}


def _inch(mm: float) -> float:
    return mm * 25.4


@dataclass(frozen=True)
class Geom:
    """Resolved geometry for one (instrument, scale, spacer, margin) combo."""
    key: str
    plen: float          # patch length along a pass (mm)
    pspa: float          # inter-patch spacer (mm); 0 if spacers off
    tspa: float          # trailer clear space after last patch (mm)
    pwid: float          # patch width (mm)
    rrsp: float          # row-centre to row-centre spacing (mm)
    lspa: float          # leader space before first patch (mm)
    lcar: float          # leading clear area (mm)
    txhisl: float        # strip/column label text height (mm)
    pglth: float         # page-label text height (mm)
    border: float        # base page margin (-m), mm — drives leader/clip-holder
    lbord: float         # extra left clip border (mm); 0 if suppressed (-L) / N/A
    hxeh: float          # hex/stagger extra height (mm)
    hxew: float          # hex extra width (mm)
    clwi: float          # cut-line width (mm)
    rlwi: float          # row-label width (mm)
    mxpprow: int         # max patches per pass
    mxrowl: float        # max pass length (mm)
    rpstrip: int         # rows per whole strip
    nextrap: int         # extra max/min/SID patches per pass (not test patches)
    dorspace: bool       # gutter between rows by rrsp (vs touching)
    dopglabel: bool      # reserve a per-page label column
    padlrow: bool        # pad the final pass up to full length
    target_name: str     # CGATS TARGET_INSTRUMENT
    has_clip_border: bool # whether this instrument supports a left clip border

    # Instrument-specific extra .ti2 keywords (e.g. DTP41 lengths, SS hex flag).
    extra_keywords: tuple[tuple[str, str], ...] = ()

    # Independent page-edge margins (ChromIQ extension); default to `border`
    # via build(); the 6.0 fallback only applies to bare _build_base() Geoms.
    margin_t: float = 6.0
    margin_r: float = 6.0
    margin_b: float = 6.0
    margin_l: float = 6.0
    strip_indicator_gap: float = 0.0   # gap (mm) between strip label and strip
    offset_x: float = 0.0              # whole-chart offset (mm)
    offset_y: float = 0.0
    # Rendered-furniture reservations (mm), filled in from the recipe + fonts by
    # raster.apply_furniture_reserves() so capacity reflects what's actually
    # drawn. label_band_mm < 0 ⇒ "not computed" → fall back to the instrument
    # label height (txhisl); 0 ⇒ no label at all (indicators off → reclaim the
    # band). bottom_reserve_mm 0 ⇒ no bottom furniture. A bare build() Geom keeps
    # the sentinel so it behaves exactly as before. (#93)
    label_band_mm: float = -1.0   # actual strip-label + underline band height
    bottom_reserve_mm: float = 0.0   # actual bottom sheet-text + stamp height
    # Bracket each strip with a leading + trailing spacer (printtarg parity).
    # When OFF the two end gaps are reclaimed for patches (denser than printtarg).
    edge_spacers: bool = False
    # Where the patch block sits within the usable area (#93). One of
    # "{top,center,bottom}-{left,center,right}" (the middle is plain "center").
    # Default "center-left" reproduces the prior behaviour (vertically centred in
    # the free span, left-anchored). Render-only — capacity is unchanged.
    patch_area_align: str = "center-left"
    # Which page edge the clip border / notes band sits on, "left" or "right"
    # (#93, Knut). The reserved width (lbord) is the same either side, so this
    # only moves the band + shifts the patch block to the other edge — capacity
    # is unchanged.
    clip_side: str = "left"
    # ColorMunki "offset every second strip" (printtarg's rig stagger): shift each
    # odd strip down the page by this much (mm) so the columns interleave like a
    # brick wall (#93, Knut). 0 = no stagger. Render + patch_rects honour it; the
    # hxeh reservation makes room so capacity reflects it.
    row_stagger_mm: float = 0.0
    # Minimum distance (mm) from the PAPER EDGE to the start of text on that side
    # (Knut #93): strip labels (top) and the clip/notes band (clip side) sit this
    # far in from the edge. Independent of the margins; if a margin is too small
    # for the text it overflows toward this line and a violation is flagged.
    text_edge_top_mm: float = 4.0
    text_edge_clip_mm: float = 4.0
    # "Margins are the law" mode (Knut): the patch area is exactly the margin box
    # (no hidden leader/trailer; strip labels live inside the top margin, anchored
    # at the text-edge from the page edge). This is now driven by the LAYOUT MODE
    # — it is ON for area-first ("Prioritise chart area, then fit patches to it")
    # and OFF for patch-first (the historical printtarg-style engine). It is NOT
    # tied to "Use instrument margins" anymore (that toggle only pre-fills the
    # margin boxes once). Set in geom_from_build_kwargs from layout_mode.
    margins_are_law: bool = False
    # Physical strip-length limit of the instrument's ruler/jig (mm); 0 = none
    # (ColorMunki/SpectroScan have no ruler). In area-first the strip is NOT capped
    # to this (the margin box is law — fill it), but a strip longer than the ruler
    # is flagged as a violation so the user knows it won't fit their jig (Knut #93).
    ruler_mm: float = 0.0


def supported() -> list[str]:
    return ["i1", "p3", "CM", "41", "51", "SS"]


def build(
    key: str,
    *,
    pscale: float = 1.0,
    sscale: float = 1.0,
    hflag: bool = False,
    density: int = 1,
    spacer_on: bool = True,
    border: float = 6.0,
    margins: tuple[float, float, float, float] | None = None,
    patch_w: float | None = None,
    patch_h: float | None = None,
    spacer_width: float | None = None,
    inter_patch: float | None = None,
    strip_gap: float | None = None,
    max_strip: float | None = None,
    strip_indicator_gap: float | None = None,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    nolpcbord: bool = False,
    nolimit: bool = False,
    clip_border_width: float = 26.0,
    clip_band: float = 0.0,
    edge_spacers: bool = False,
    patch_area_align: str = "center-left",
    clip_side: str = "left",
    cm_stagger: bool = False,
    text_edge_top: float = 4.0,
    text_edge_clip: float = 4.0,
    margins_are_law: bool = False,
) -> Geom:
    """Resolve :class:`Geom`, applying ChromIQ extensions over the base geometry.

    *margins* = independent ``(top, right, bottom, left)`` page margins in mm
    (default: all = *border*).  *patch_w* / *patch_h* override the patch size in
    mm.  *spacer_width* overrides the inter-patch spacer thickness; *inter_patch*
    adds extra gap between patches; *max_strip* caps the pass length (mm);
    *strip_indicator_gap* is the gap (mm) between the strip label and its strip.
    ``border`` still drives the instrument leader and clip-holder base.
    """
    geom = _build_base(
        key, pscale=pscale, sscale=sscale, hflag=hflag, density=density,
        spacer_on=spacer_on, border=border, nolpcbord=nolpcbord, nolimit=nolimit,
        clip_border_width=clip_border_width, clip_band=clip_band)
    mt, mr, mb, ml = margins if margins else (geom.border,) * 4
    plen, pwid, rrsp = geom.plen, geom.pwid, geom.rrsp
    if patch_h:
        plen = float(patch_h)
    if patch_w:
        ratio = (geom.rrsp / geom.pwid) if geom.pwid else 1.0
        pwid = float(patch_w)
        rrsp = pwid * ratio
    if strip_gap:                       # extra gutter between strips (adds to pitch)
        rrsp += float(strip_gap)
    pspa = geom.pspa
    if spacer_width is not None and geom.pspa > 0:   # only when spacers are on
        pspa = float(spacer_width)
    if inter_patch:
        pspa += float(inter_patch)
    mxrowl = float(max_strip) if max_strip else geom.mxrowl
    sig = geom.strip_indicator_gap if strip_indicator_gap is None \
        else float(strip_indicator_gap)
    # ColorMunki "offset every second strip": shift odd strips down by half a
    # patch (printtarg's rig stagger = 0.5·(plen + ½·spacer)) and reserve hxeh =
    # ¼·plen so the overhang stays on the page. Decoupled from density (#93, Knut).
    hxeh = geom.hxeh
    row_stagger = 0.0
    if key == "CM" and cm_stagger:
        row_stagger = 0.5 * (plen + 0.5 * pspa)
        hxeh = 0.25 * plen
    # Clip / notes band lives INSIDE the clip-side margin (Knut beta-13): raise
    # that margin to at least the clip-border width so the band fits and the patch
    # area starts at the (possibly bumped) margin — no additive double-count. This
    # keeps printtarg parity for the default clip (border + lbord == clip width)
    # while a larger user margin still pushes the patches further in.
    if geom.lbord > 0:
        clip_w = geom.lbord + geom.border
        if (clip_side or "left") == "right":
            mr = max(mr, clip_w)
        else:
            ml = max(ml, clip_w)
    return replace(geom, margin_t=mt, margin_r=mr, margin_b=mb, margin_l=ml,
                   plen=plen, pwid=pwid, rrsp=rrsp, pspa=pspa, mxrowl=mxrowl,
                   hxeh=hxeh, row_stagger_mm=row_stagger,
                   strip_indicator_gap=sig, offset_x=offset_x, offset_y=offset_y,
                   edge_spacers=edge_spacers,
                   patch_area_align=patch_area_align or "center-left",
                   clip_side=clip_side or "left",
                   text_edge_top_mm=float(text_edge_top or 4.0),
                   text_edge_clip_mm=float(text_edge_clip or 4.0),
                   margins_are_law=bool(margins_are_law))


# Keys of a recipe ``build_kwargs()`` dict that affect the laid-out geometry —
# i.e. every option that can change how many patches fit a page (capacity) or
# where they sit (placement). Keep in lockstep with build()'s keyword args: a
# missing key silently makes capacity ESTIMATES disagree with the actual render
# (clip_border_width once did exactly that — #93). This is the single source of
# truth shared by every capacity calculation.
GEOM_BUILD_KEYS = (
    "hflag", "density", "spacer_on", "pscale", "sscale", "border", "margins",
    "patch_w", "patch_h", "spacer_width", "inter_patch", "strip_gap", "max_strip",
    "strip_indicator_gap", "offset_x", "offset_y", "nolpcbord", "nolimit",
    "clip_border_width", "clip_band", "edge_spacers", "patch_area_align",
    "clip_side", "cm_stagger", "text_edge_top", "text_edge_clip",
)


def geom_from_build_kwargs(kw: dict, thresholds: dict | None = None) -> Geom:
    """Build a :class:`Geom` from a recipe ``build_kwargs()`` dict using every
    geometry-affecting key, so capacity estimates can never silently drift from
    the actual render (#93). Rendered-furniture reservations (label band, bottom
    sheet text / stamp) are applied too — the same step the renderer uses.

    When *thresholds* (a ``{"L","R","T","B": mm}`` minimum-margin dict) is given,
    the page margins are first raised so the realised patch area meets those
    minimums — so both the capacity estimate and the render honour the user's
    margin thresholds from this one chokepoint (#93)."""
    # CM/SS have no native clip border, but can still carry a notes/clip band
    # when clip content is on — reserve that band so capacity reflects it (#93).
    if (kw.get("instrument") in ("CM", "SS")
            and kw.get("clip_content_mode", "off") not in ("off", None)
            and not kw.get("clip_band")):
        kw = {**kw, "clip_band": float(kw.get("clip_border_width") or 26.0)}
    if thresholds:
        from . import margins_fit   # lazy: imports this module
        kw, _notes = margins_fit.clamp_margins_to_thresholds(kw, thresholds)
    # Area-first layout: derive patch_w/patch_h from the target grid, unless the
    # caller already set explicit sizes. Lazy import (it builds geoms via us).
    if kw.get("layout_mode") == "area_first" and not (kw.get("patch_w")
                                                      or kw.get("patch_h")):
        from . import area_fit
        _sz = area_fit.derive_area_patch_size(kw)
        if _sz is not None:
            kw = {**kw, "patch_w": _sz[0], "patch_h": _sz[1]}
    # "Margins are the law" is now decided by the LAYOUT MODE, not by the
    # "Use instrument margins" toggle (Knut): area-first treats the margin box as
    # the exact patch area; patch-first keeps the printtarg-style furniture.
    law = (kw.get("layout_mode") == "area_first")
    geom = build(kw["instrument"], margins_are_law=law,
                 **{k: v for k, v in kw.items() if k in GEOM_BUILD_KEYS})
    from . import raster   # lazy: raster imports this module
    return raster.apply_furniture_reserves(geom, kw)


def _build_base(
    key: str,
    *,
    pscale: float = 1.0,
    sscale: float = 1.0,
    hflag: bool = False,
    density: int = 1,
    spacer_on: bool = True,
    border: float = 6.0,
    nolpcbord: bool = False,
    nolimit: bool = False,
    clip_border_width: float = 26.0,
    clip_band: float = 0.0,
) -> Geom:
    """Resolve :class:`Geom` for *key* with the given options.

    *pscale* = printtarg ``-a`` (patch+spacer scale), *sscale* = ``-A`` (spacer
    scale), *hflag* = ``-h`` (SpectroScan hex), *spacer_on* False = ``-n``,
    *border* = ``-m`` margin, *nolpcbord* True = ``-L``, *nolimit* True = ``-P``.

    *density* (ColorMunki only) is the row-density level: 1 = normal hand-held,
    2 = high (the rig — printtarg ``-h``, exact), 3 = extra-high (a ChromIQ
    extension beyond printtarg's single level; tighter rows pending hardware
    validation, guarded by the 6 mm reliability floor).
    """
    if key == "CM" and hflag and density < 2:
        density = 2   # back-compat: hflag meant "rig" (double density)
    if key in DELEGATED:
        raise ValueError(f"instrument {key!r} is delegated to i1Profiler, not laid out here")
    if key not in TARGET_INSTRUMENT_NAME:
        raise ValueError(f"unknown instrument {key!r}")

    name = TARGET_INSTRUMENT_NAME[key]

    def spacer(base: float) -> float:
        return pscale * sscale * base if spacer_on else 0.0

    # ---- i1Pro family (5 mm and 8 mm apertures) -------------------------
    if key in ("i1", "p3"):
        clip_w = clip_border_width if clip_border_width else 26.0
        lbord = max(0.0, clip_w - border) if not nolpcbord else 0.0
        if key == "i1":                       # 5 mm aperture
            lcar, plen_b, pspa_b, tspa = 10.0, 10.0, 1.0, 10.0
            pwid_b = rrsp_b = 8.0
        else:                                 # p3 = i1Pro 3+ / 8 mm aperture
            lcar, plen_b, pspa_b, tspa = 20.0, 20.0, 2.0, 20.0
            pwid_b = rrsp_b = 16.0
        txhisl = 7.0
        mxrowl = MAXROWLEN if nolimit else (260.0 - lcar - tspa)
        return Geom(
            key=key, plen=pscale * plen_b, pspa=spacer(pspa_b), tspa=tspa,
            pwid=pscale * pwid_b, rrsp=pscale * rrsp_b,
            lspa=border + txhisl + lcar, lcar=lcar, txhisl=txhisl, pglth=5.0,
            border=border, lbord=lbord, hxeh=0.0, hxew=0.0, clwi=0.0, rlwi=0.0,
            mxpprow=MAXPPROW, mxrowl=mxrowl, rpstrip=999, nextrap=0,
            dorspace=False, dopglabel=False,   # page-label column reclaimed (#93)
            padlrow=True, target_name=name,
            has_clip_border=True, ruler_mm=(260.0 - lcar - tspa),
        )

    # Optional notes band for instruments without a native clip border (CM/SS):
    # reserve the same total zone from the edge as the i1Pro clip (#93, Knut).
    _band = max(0.0, clip_band - border) if clip_band > 0 else 0.0

    # ---- X-Rite ColorMunki ---------------------------------------------
    if key == "CM":
        # Extra-high density = a DENSE ColorMunki strip layout with small, still-
        # readable patches. printtarg could only fake this by laying out an i1Pro
        # chart and relabelling the .ti2 — it can't make ColorMunki patches this
        # small. Our engine can, so we define it natively as a ColorMunki geometry
        # (no i1 borrow, #93, Knut): ~10.4 mm patches in 13 mm steps — the same
        # readable size the old i1-trick produced, but ours. It's a fixed maximum-
        # density mode, so the patch size is INDEPENDENT of the patch scale (the
        # "auto" size is the same in Guided and Manual → both fill to the same
        # count); set an explicit patch_w/patch_h to override.
        if density >= 3:
            plen = 13.0
            pwid = rrsp = 10.4
            # ColorMunki has no i1-style ruler, so a strip is never length-capped
            # (matches the other CM densities) — the user pointed out a cap is
            # never needed here, so the page height is the only limit.
            txhisl, lcar, tspa = 7.0, 10.0, 10.0
            return Geom(
                key=key, plen=plen, pspa=(1.3 if spacer_on else 0.0), tspa=tspa,
                pwid=pwid, rrsp=rrsp,
                lspa=border + txhisl + lcar, lcar=lcar, txhisl=txhisl, pglth=5.0,
                border=border, lbord=_band, hxeh=0.0, hxew=0.0, clwi=0.0, rlwi=0.0,
                mxpprow=MAXPPROW, mxrowl=MAXROWLEN, rpstrip=999, nextrap=0,
                dorspace=False, dopglabel=False,   # page-label column reclaimed
                padlrow=True, target_name=name, has_clip_border=_band > 0,
            )
        plen = pscale * 14.0
        if density >= 2:                      # high density (rig) — tighter rows
            # Level 2 = printtarg's exact rig spacing (13.7 mm).
            pwid = rrsp = pscale * 13.7
        else:                                 # normal hand-held
            pwid = rrsp = pscale * 28.0
        # The strip stagger (and its hxeh reservation) is now a separate option
        # (cm_stagger), applied in build() — not tied to density (#93, Knut).
        hxeh = 0.0
        txhisl, lcar = 7.0, 20.0
        return Geom(
            key=key, plen=plen, pspa=spacer(1.0), tspa=25.0, pwid=pwid, rrsp=rrsp,
            lspa=border + 7.0 + 20.0, lcar=lcar, txhisl=txhisl, pglth=5.0,
            border=border, lbord=_band, hxeh=hxeh, hxew=0.0, clwi=0.0, rlwi=0.0,
            mxpprow=MAXPPROW, mxrowl=MAXROWLEN, rpstrip=999, nextrap=0,
            dorspace=False, dopglabel=False,   # page-label column reclaimed (#93)
            padlrow=True, target_name=name,
            has_clip_border=_band > 0,
        )

    # ---- GretagMacbeth SpectroScan (flatbed) ---------------------------
    if key == "SS":
        if hflag:                             # hexagon patches
            plen = pscale * math.sqrt(0.75) * 7.0
            hxeh = (1.0 / 6.0) * plen
            hxew = pscale * 0.25 * 7.0
        else:
            plen = pscale * 7.0
            hxeh = hxew = 0.0
        extra = (("HEXAGON_PATCHES", "True"),) if hflag else ()
        return Geom(
            key=key, plen=plen, pspa=0.0, tspa=0.0, pwid=pscale * 7.0, rrsp=pscale * 7.0,
            lspa=border + 7.0, lcar=0.0, txhisl=5.0, pglth=5.0,
            border=border, lbord=_band, hxeh=hxeh, hxew=hxew, clwi=0.0, rlwi=7.5,
            mxpprow=MAXPPROW, mxrowl=MAXROWLEN, rpstrip=999, nextrap=0,
            dorspace=False, dopglabel=False,   # page-label column reclaimed (#93)
            padlrow=False, target_name=name,
            has_clip_border=_band > 0, extra_keywords=extra,
        )

    # ---- X-Rite DTP41 ---------------------------------------------------
    if key == "41":
        plen = pscale * _inch(0.29)
        pspa = spacer(_inch(0.08))
        tspa = 2.0 * (plen + pspa)
        mxrowl = MAXROWLEN if nolimit else _inch(55.0)
        extra = (
            ("PATCH_LENGTH", f"{plen:.6f}"),
            ("GAP_LENGTH", f"{pspa:.6f}"),
            ("TRAILER_LENGTH", f"{tspa:.6f}"),
        )
        return Geom(
            key=key, plen=plen, pspa=pspa, tspa=tspa,
            pwid=_inch(0.5), rrsp=_inch(0.5),
            lspa=_inch(1.5), lcar=_inch(0.5), txhisl=5.0, pglth=5.0,
            border=border, lbord=0.0, hxeh=0.0, hxew=0.0, clwi=0.3, rlwi=0.0,
            mxpprow=100, mxrowl=mxrowl, rpstrip=8, nextrap=0,
            dorspace=False, dopglabel=False,   # page-label column reclaimed (#93)
            padlrow=True, target_name=name,
            has_clip_border=False, extra_keywords=extra, ruler_mm=_inch(55.0),
        )

    # ---- X-Rite DTP51 ---------------------------------------------------
    if key == "51":
        plen = pscale * _inch(0.4)
        pspa = spacer(_inch(0.07))
        mxrowl = MAXROWLEN if nolimit else _inch(40.0)
        return Geom(
            key=key, plen=plen, pspa=pspa, tspa=0.0,
            pwid=_inch(0.4), rrsp=_inch(0.5),
            lspa=_inch(1.2), lcar=_inch(0.25), txhisl=5.0, pglth=5.0,
            border=border, lbord=0.0, hxeh=0.0, hxew=0.0, clwi=0.3, rlwi=0.0,
            mxpprow=72, mxrowl=mxrowl, rpstrip=6, nextrap=2,   # max+min header/trailer
            dorspace=True, dopglabel=False, padlrow=True, target_name=name,
            has_clip_border=False, ruler_mm=_inch(40.0),
        )

    raise ValueError(f"unhandled instrument {key!r}")
