"""Built-in chart presets — standalone shim of ChromIQ's ``ui.tabs.tab_chart``.

chromiq-patches does not ship ChromIQ's full Create Chart tab; the layout
editor only imports two functions from it (``builtin_recipe_choices`` and
``comparable_presets``). This module carries exactly those two functions plus
the built-in-preset registry they read — extracted verbatim from ChromIQ's
``ui/tabs/tab_chart.py`` (the registry block). When syncing from ChromIQ
(tools/sync_from_chromiq.py) diff this file against upstream's registry and
carry over any new built-in presets.

``comparable_presets`` is the one deliberate rewrite: upstream it consults the
``TabChart`` widget class; here the built-in .ti1 asset lookup is a module
function and user presets come from the same on-disk preset store ChromIQ uses
(~ChromIQ presets dir), so presets saved in either app appear in both.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core.i18n import tr
from core.preset_store import (
    load_presets as _load_tab_presets,
    sidecar_path as _preset_sidecar_path,
)
from core.resource_path import resource_path

# assets/charts/<creator>/<colorspace>/<instrument>/<paper>/<target>/.
TC918_PRESET_KEY = "__chromiq_tc918_builtin__"
TC918_PRESET_LABEL = "★  i1Pro TC9.18 by Pharmacist  ·  built-in"
TC918_TI1_ASSET = "assets/charts/pharmacist/rgb/i1pro/a4/tc918/tc918.ti1"
TC918_TARGET_NAME = "tc918"

# Prebuilt-files built-in presets: a complete, pre-generated target (ti1 + ti2 +
# TIFFs) bundled in assets/. Selecting one prompts for a name, copies the bundled
# files into a fresh ~/ChromIQ/<name> folder (renamed to <name>…) and loads them.
# targen AND printtarg are skipped entirely — the param panels are greyed out
# while such a preset is active, because none of those options apply.
# The four "by Pharmacist" targets below are the full built-in line-up
# (two i1Pro, two ColorMunki) — every one a prebuilt-files preset.
# Labels follow the same convention as Knut's presets — instrument · paper +
# patch count + page count, then the set name + "by Pharmacist". (Patch width and
# orientation, which Knut's names carry, aren't stored for these pre-rendered
# charts, so they're omitted here.) The *_KEY is the stable identity — labels can
# change freely, keys must not.
TC924_PRESET_KEY = "__chromiq_tc924_builtin__"
TC924_PRESET_LABEL = "★  i1Pro · A4-924p-2pages TC9.24 by Pharmacist  ·  built-in"
ABW1110_PRESET_KEY = "__chromiq_abw1110_builtin__"
ABW1110_PRESET_LABEL = "★  i1Pro · A4-1110p-2pages ABW-optimized by Pharmacist  ·  built-in"
# TC9.18 extended-greys 1160-patch target, in A4 and US-Letter layouts. Same
# patch set, two page sizes — the paper is carried in the label so the pair is
# distinguishable in the dropdown and the overlay.
TC918EG_A4_PRESET_KEY = "__chromiq_tc918eg_a4_builtin__"
TC918EG_A4_PRESET_LABEL = "★  i1Pro · A4-1160p-2pages TC9.18 extended greys by Pharmacist  ·  built-in"
TC918EG_LETTER_PRESET_KEY = "__chromiq_tc918eg_letter_builtin__"
TC918EG_LETTER_PRESET_LABEL = "★  i1Pro · Letter-1160p-2pages TC9.18 extended greys by Pharmacist  ·  built-in"
TC300_PRESET_KEY = "__chromiq_tc300_builtin__"
TC300_PRESET_LABEL = "★  ColorMunki · A4-300p-1page TC3.00 by Pharmacist  ·  built-in"
ABW702_PRESET_KEY = "__chromiq_abw702_builtin__"
ABW702_PRESET_LABEL = "★  ColorMunki · A4-702p-2pages ABW-optimized by Pharmacist  ·  built-in"
# TC9.24 target laid out for the ColorMunki on A3 (single page, 924 patches).
TC924_CM_A3_PRESET_KEY = "__chromiq_tc924_cm_a3_builtin__"
TC924_CM_A3_PRESET_LABEL = "★  ColorMunki · A3-924p-1page TC9.24 by Pharmacist  ·  built-in"
# TC9.18 extended greys laid out for the ColorMunki on A3+ (single page, 1160 patches).
TC918EG_CM_A3_PRESET_KEY = "__chromiq_tc918eg_cm_a3_builtin__"
TC918EG_CM_A3_PRESET_LABEL = "★  ColorMunki · A3+-1160p-1page TC9.18 extended greys by Pharmacist  ·  built-in"
# Extended 1944-patch RGB target (shuffled patch set), in A4 and US-Letter
# layouts. Same patch set, two page sizes — paper carried in the label so the
# pair is distinguishable in the dropdown and the overlay.
EXT1944_A4_PRESET_KEY = "__chromiq_ext1944_a4_builtin__"
EXT1944_A4_PRESET_LABEL = "★  i1Pro · A4-1944p-3pages extended target by Pharmacist  ·  built-in"
EXT1944_LETTER_PRESET_KEY = "__chromiq_ext1944_letter_builtin__"
EXT1944_LETTER_PRESET_LABEL = "★  i1Pro · Letter-1944p-3pages extended target by Pharmacist  ·  built-in"

# key -> (asset stem under assets/charts, default target name). Charts are filed
# by creator/colorspace/instrument/paper/target; the stem locates <stem>.ti1,
# <stem>.ti2 and the <stem>_NN.tif page TIFFs inside that leaf folder.
# The default target name follows the sortable convention (#68):
# <instrument>-<paper>-<patches>p-<pages>pages-<set name>. Orientation isn't
# stored for these pre-rendered charts, so it's omitted (the colour-set name is
# the "additional text" tail). It's only the prompt's suggested default — the
# user can edit it freely.
PREBUILT_PRESETS = {
    TC924_PRESET_KEY:          ("assets/charts/pharmacist/rgb/i1pro/a4/tc924/tc924",            "i1Pro-A4-924p-2pages-TC9.24 by Pharmacist"),
    ABW1110_PRESET_KEY:        ("assets/charts/pharmacist/rgb/i1pro/a4/abw1110/abw1110",        "i1Pro-A4-1110p-2pages-ABW-optimized by Pharmacist"),
    TC918EG_A4_PRESET_KEY:     ("assets/charts/pharmacist/rgb/i1pro/a4/tc918eg/tc918eg",        "i1Pro-A4-1160p-2pages-TC9.18 extended greys by Pharmacist"),
    TC918EG_LETTER_PRESET_KEY: ("assets/charts/pharmacist/rgb/i1pro/letter/tc918eg/tc918eg",    "i1Pro-Letter-1160p-2pages-TC9.18 extended greys by Pharmacist"),
    TC300_PRESET_KEY:          ("assets/charts/pharmacist/rgb/colormunki/a4/tc300/tc300",       "ColorMunki-A4-300p-1page-TC3.00 by Pharmacist"),
    ABW702_PRESET_KEY:         ("assets/charts/pharmacist/rgb/colormunki/a4/abw702/abw702",     "ColorMunki-A4-702p-2pages-ABW-optimized by Pharmacist"),
    TC924_CM_A3_PRESET_KEY:    ("assets/charts/pharmacist/rgb/colormunki/a3/tc924/tc924",       "ColorMunki-A3-924p-1page-TC9.24 by Pharmacist"),
    TC918EG_CM_A3_PRESET_KEY:  ("assets/charts/pharmacist/rgb/colormunki/a3plus/tc918eg/tc918eg", "ColorMunki-A3+-1160p-1page-TC9.18 extended greys by Pharmacist"),
    EXT1944_A4_PRESET_KEY:     ("assets/charts/pharmacist/rgb/i1pro/a4/extended1944/extended1944",     "i1Pro-A4-1944p-3pages-extended target by Pharmacist"),
    EXT1944_LETTER_PRESET_KEY: ("assets/charts/pharmacist/rgb/i1pro/letter/extended1944/extended1944", "i1Pro-Letter-1944p-3pages-extended target by Pharmacist"),
}

# --- Knut's TC9.18 + Spyderprint-greys presets -----------------------------
# A family of built-in presets that all share ONE bundled 1168-patch .ti1
# (TC9.18 colour set + Spyderprint neutral ramp) and differ only in their
# printtarg layout — instrument, page size, patch scale, margin, spacer scale
# and random seed. Unlike the prebuilt-files presets, nothing is pre-rendered:
# picking one seeds the Manual printtarg panel and runs printtarg on the bundled
# .ti1 (the same ti1→printtarg path the "attach a .ti1" user presets use, via
# _preset_ti1_path), so the panels stay editable and only one small .ti1 ships.
KNUT_TI1_ASSET = "assets/charts/knut/rgb/tc918-spyderprint-1168p/1168p.ti1"
KNUT_PATCHES, KNUT_WHITE, KNUT_BLACK = 1168, 9, 8   # from the .ti1 header
KNUT_DPI = 200                                        # -T200 (16-bit) on every one
KNUT_SUFFIX = " TC9.18+Spyderprint Grays"             # common name tail
_KNUT_I1, _KNUT_CM = "i1", "CM"

# Knut's "Full layout setup" family (#63): multi-colour-set charts, each with
# its OWN bundled .ti1 (unlike the shared-.ti1 TC9.18 presets) AND a complete
# Create-Chart recipe (the colour-set generators + layout), so loading one
# repopulates the whole Create Chart tab — they're meant as a basis for new
# charts. Driven by his exported Create Chart presets; 8-bit, default randomise
# (printtarg -r off, no fixed -R seed).
KNUT_FLS_SUFFIX = " · Full layout setup"
_KNUT_FLS_DIR = "assets/charts/knut/rgb/fulllayout"


# Pulls a "-w<number>mm" patch-width token (e.g. "-w11.5mm") out of a name.
_WIDTH_TOKEN_RE = re.compile(r"-w\d+(?:\.\d+)?mm")


def _sortable_builtin_name(instr_label: str, full_name: str, suffix: str) -> str:
    """Normalise a built-in preset's name to the sortable convention (#68):

        <instrument>-<paper>-<patches>p-<pages>pages-<orientation>-<extras>

    The instrument leads (so sorting groups by device), and the two non-sorting
    bits — the layout's ``-w<number>mm`` patch width and the colour-set name
    (e.g. "TC9.18+Spyderprint Grays") — move to the tail as "additional text",
    exactly where the user's own free text would sit. Earlier the width sat in
    the middle and the instrument was missing, which broke folder sorting and
    re-ordered inconsistently.
    """
    base = full_name
    set_name = ""
    if suffix and base.endswith(suffix):
        base = base[: -len(suffix)]
        set_name = suffix.strip(" ·")          # " · Full layout setup" → "Full layout setup"
    width = ""
    m = _WIDTH_TOKEN_RE.search(base)
    if m:
        width = m.group(0)[1:]                  # "-w11.5mm" → "w11.5mm"
        base = base[: m.start()] + base[m.end():]   # leaves "…-<orientation>"
    name = f"{instr_label}-{base}"
    tail = "-".join(t for t in (width, set_name) if t)
    return f"{name}-{tail}" if tail else name


@dataclass(frozen=True)
class _Ti1Preset:
    """One TC9.18+Spyderprint preset: a printtarg layout over the shared .ti1."""
    slug: str            # stable identity component (never change once shipped)
    name: str            # Knut's full chart name (display + default target name)
    instrument: str      # printtarg -i ("i1" | "CM")
    paper: str           # printtarg -p (named size or "WxH" in mm)
    patch_scale: float   # printtarg -a
    margin: int          # printtarg -m / -M
    pages: int           # informational (the page count in the name)
    double_density: bool = False        # printtarg -h (ColorMunki)
    triple_density: bool = False        # ChromIQ triple density (i1Pro layout + CM tag)
    spacer_scale: float | None = None   # printtarg -A (None → leave at default)
    seed: int | None = None             # printtarg -R (None → default randomise)
    # Full-layout-setup family (#63) extensions. The defaults reproduce the shared-.ti1
    # TC9.18+Spyderprint presets byte-for-byte, so only the new family sets them:
    ti1_asset: str = KNUT_TI1_ASSET     # bundled .ti1 (shared one by default)
    patches: int = KNUT_PATCHES         # descriptive targen -f (panel display only)
    white: int = KNUT_WHITE             # descriptive targen -e
    black: int = KNUT_BLACK             # descriptive targen -B
    no_strip_limit: bool = True         # printtarg -P
    suppress_left_clip: bool = False    # printtarg -L
    no_randomise: bool = False          # printtarg -r (False = randomise, the default)
    tiff_16bit: bool = True             # 16-bit TIFF (→ -T)
    suffix: str = KNUT_SUFFIX           # family name tail (stripped for target name)

    @property
    def key(self) -> str:
        return f"__chromiq_knut_{self.slug}__"

    @property
    def combo_label(self) -> str:
        instr = "i1Pro" if self.instrument == _KNUT_I1 else "ColorMunki"
        return f"★  {instr} · {self.name}  ·  built-in"

    @property
    def overlay_label(self) -> str:
        return self.name  # the overlay already groups by instrument

    @property
    def default_target_name(self) -> str:
        instr = "i1Pro" if self.instrument == _KNUT_I1 else "ColorMunki"
        return _sortable_builtin_name(instr, self.name, self.suffix)


# Named printtarg page sizes in mm (only those the presets use); custom sizes are
# given as "WxH" and parsed directly. Used to order the presets by paper size.
_PAPER_MM = {
    "A4": (210.0, 297.0), "A4R": (297.0, 210.0),
    "Letter": (215.9, 279.4), "LetterR": (279.4, 215.9),
    "A3": (297.0, 420.0), "A2": (420.0, 594.0),
    # "11x17" is an inch designation (Tabloid), not millimetres — its real size
    # is 279.4 × 431.8 mm. Listed here so _paper_area_mm2 resolves it by name
    # before the "WxH" fallback would misread "11x17" as 187 mm².
    "11x17": (279.4, 431.8),
}


def _paper_area_mm2(paper: str) -> float:
    """Sheet area in mm² for a printtarg -p value (named size or 'WxH')."""
    # Named sizes win over the "WxH" split so inch-designated codes like
    # "11x17" (which contain an 'x' but are not millimetres) resolve correctly.
    dims = _PAPER_MM.get(paper)
    if dims:
        return dims[0] * dims[1]
    if "x" in paper:
        try:
            w, h = paper.split("x", 1)
            return float(w) * float(h)
        except ValueError:
            return 0.0
    return 0.0

def _paper_sort_key(paper: str) -> float:
    """Ordering key for "smallest sheet first".

    Area-based, except US Letter is nudged to sort *just after* A4. The two are
    within ~3% (Letter is marginally smaller), but the conventional order — and
    the one the Pharmacist presets already use — lists A4 first, so we match it
    rather than letting Letter jump ahead on raw area."""
    if paper in ("Letter", "LetterR"):
        return _paper_area_mm2("A4") + 1.0
    return _paper_area_mm2(paper)


# Knut's commands, transcribed (the trailing common suffix is added above):
#   i1Pro:      printtarg -v -P -ii1  -T200 -p<paper> -M8 -R<seed> -a<scale> -A0.6
#   ColorMunki: printtarg -v -P -iCM -h -T200 -p<paper> -a<scale> -M6
# ChromIQ emits -m<m> -M<m> together (functionally == Knut's lone -M, since
# printtarg's -m/-M write the same margin) and keeps the left clip border (no -L).
KNUT_PRESETS: list[_Ti1Preset] = [
    # (The 17 "TC9.18+Spyderprint Grays" shared-.ti1 presets were removed in #89 —
    # only the Full layout setup and "by Pharmacist" built-ins remain.)

    # Full-layout-setup family (#63) — Knut's exported Create Chart charts, each
    # with its own bundled .ti1 (per-preset patch set + layout) AND a sidecar
    # recipe.json (the colour-set + layout recipe) so the preset can seed a New
    # chart. Several ColorMunki ones are triple density (i1Pro layout + ColorMunki
    # tag); the i1Pro ones keep the left clip + strip limit (-L/-P). All 8-bit.
    # Rows + assets generated from his JSON exports (see scripts).
    # ColorMunki Full-layout-setup family — reworked by Knut (#89). The multi-
    # page charts are double density; the dense single-page charts stay triple
    # density (the export's printtarg block diverges from its editor_recipe for
    # those — the recipe's td/scale is authoritative). Patch width is in each name.
    _Ti1Preset("fls_colormunki_a3_1196p_2pages_portrait", "A3-1196p-2pages-Portrait-w12.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "A3", 0.88, 6, 2,
               double_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a3_1196p_2pages_portrait/chart.ti1", patches=1196, white=9, black=8, no_strip_limit=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a3_1224p_2pages_landscape", "A3-1224p-2pages-Landscape-w12.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "420x297", 0.85, 6, 2,
               double_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a3_1224p_2pages_landscape/chart.ti1", patches=1224, white=9, black=8, no_strip_limit=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a3_1575p_3pages_portrait", "A3-1575p-3pages-Portrait-w13.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "A3", 0.94, 6, 3,
               double_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a3_1575p_3pages_portrait/chart.ti1", patches=1575, white=9, black=8, no_strip_limit=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a3_2016p_4pages_portrait", "A3-2016p-4pages-Portrait-w13.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "A3", 0.96, 6, 4,
               double_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a3_2016p_4pages_portrait/chart.ti1", patches=2016, white=9, black=8, no_strip_limit=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a3_2016p_4pages_portrait_nature_focus", "A3-2016p-4pages-Portrait-w13.0mm-Nature Focus" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "A3", 0.96, 6, 4,
               double_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a3_2016p_4pages_portrait_nature_focus/chart.ti1", patches=2016, white=9, black=8, no_strip_limit=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a3plus_1190p_1page_portrait", "A3Plus-1190p-1page-Portrait-w9.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "329x483", 1.14, 6, 1,
               triple_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a3plus_1190p_1page_portrait/chart.ti1", patches=1190, white=9, black=8, no_strip_limit=True, suppress_left_clip=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a3plus_1196p_1page_landscape", "A3Plus-1196p-1page-Landscape-w9.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "483x329", 1.12, 6, 1,
               triple_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a3plus_1196p_1page_landscape/chart.ti1", patches=1196, white=9, black=8, no_strip_limit=True, suppress_left_clip=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a4_480p_2pages_portrait", "A4-480p-2pages-Portrait-w13.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "A4", 0.93, 6, 2,
               double_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a4_480p_2pages_portrait/chart.ti1", patches=480, white=9, black=8, no_strip_limit=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a4_484p_1page_portrait", "A4-484p-1page-Portrait-w8.5mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "A4", 1.08, 6, 1,
               triple_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a4_484p_1page_portrait/chart.ti1", patches=484, white=9, black=8, no_strip_limit=True, suppress_left_clip=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_colormunki_a4_495p_1page_landscape", "A4-495p-1page-Landscape-w8.0mm" + KNUT_FLS_SUFFIX,
               _KNUT_CM, "A4R", 1.06, 6, 1,
               triple_density=True, ti1_asset=f"{_KNUT_FLS_DIR}/fls_colormunki_a4_495p_1page_landscape/chart.ti1", patches=495, white=9, black=8, no_strip_limit=True, suppress_left_clip=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    # i1Pro A4 portrait family — reworked by Knut (#88) to keep the i1Pro clip
    # border (no -L) and honour the strip-length limit (no -P), with patch
    # widths baked into the names. The 960p landscape preset was retired.
    _Ti1Preset("fls_i1pro_a4_1200p_3pages_portrait", "A4-1200p-3pages-Portrait-w8.5mm" + KNUT_FLS_SUFFIX,
               _KNUT_I1, "A4", 1.05, 10, 3,
               ti1_asset=f"{_KNUT_FLS_DIR}/fls_i1pro_a4_1200p_3pages_portrait/chart.ti1", patches=1200, white=9, black=8, no_strip_limit=False, suppress_left_clip=False, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_i1pro_a4_484p_1page_portrait", "A4-484p-1page-Portrait-w7.5mm" + KNUT_FLS_SUFFIX,
               _KNUT_I1, "A4", 0.96, 10, 1,
               ti1_asset=f"{_KNUT_FLS_DIR}/fls_i1pro_a4_484p_1page_portrait/chart.ti1", patches=484, white=9, black=8, no_strip_limit=False, suppress_left_clip=False, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_i1pro_a4_495p_1page_landscape", "A4-495p-1page-Landscape" + KNUT_FLS_SUFFIX,
               _KNUT_I1, "A4R", 1.03, 10, 1,
               ti1_asset=f"{_KNUT_FLS_DIR}/fls_i1pro_a4_495p_1page_landscape/chart.ti1", patches=495, no_strip_limit=True, suppress_left_clip=True, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_i1pro_a4_924p_2pages_portrait", "A4-924p-2pages-Portrait-w7.5mm" + KNUT_FLS_SUFFIX,
               _KNUT_I1, "A4", 0.98, 10, 2,
               ti1_asset=f"{_KNUT_FLS_DIR}/fls_i1pro_a4_924p_2pages_portrait/chart.ti1", patches=924, white=9, black=8, no_strip_limit=False, suppress_left_clip=False, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
    _Ti1Preset("fls_i1pro_a4_924p_2pages_portrait_nature_focus", "A4-924p-2pages-Portrait-w7.5mm-Nature Focus" + KNUT_FLS_SUFFIX,
               _KNUT_I1, "A4", 0.98, 10, 2,
               ti1_asset=f"{_KNUT_FLS_DIR}/fls_i1pro_a4_924p_2pages_portrait_nature_focus/chart.ti1", patches=924, white=9, black=8, no_strip_limit=False, suppress_left_clip=False, tiff_16bit=False, suffix=KNUT_FLS_SUFFIX),
]
KNUT_PRESETS_BY_KEY: dict[str, _Ti1Preset] = {p.key: p for p in KNUT_PRESETS}
KNUT_PRESET_KEYS = frozenset(KNUT_PRESETS_BY_KEY)


# --- built-in preset recipes (Set B: a preset's New-chart / Add design) -------
# Built-in presets can carry a creation recipe — the same colour-set + layout
# settings a user preset stores in its own .json — so loading the preset seeds
# the New-chart window, exactly like a locally-saved preset (Knut). A preset's
# recipe is looked up two ways, in order: a per-preset ``recipe.json`` sitting
# beside its bundled ``chart.ti1`` (the general convention — any built-in, any
# folder, can carry one; the Full-layout-setup family uses these), then an
# optional shared ``recipes.json`` keyed by the preset's display name (a legacy
# fallback; no shipped family relies on it any more).
def _recipe_display_key(p: "_Ti1Preset") -> str:
    """The name a preset's recipe is filed under in a shared recipes.json —
    instrument label + the preset's name without its family suffix."""
    instr = "i1Pro" if p.instrument == _KNUT_I1 else "ColorMunki"
    return f"{instr} {p.name.replace(p.suffix, '').strip()}"


def _load_shared_wg_recipes() -> dict:
    try:
        path = resource_path(f"{_KNUT_FLS_DIR}/recipes.json")
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except Exception:  # noqa: BLE001 — never block preset loading
        pass
    return {}


def builtin_preset_recipe(preset_key: str) -> dict | None:
    """The creation recipe a built-in preset carries, or None. Tries a
    per-preset ``recipe.json`` next to its ``chart.ti1`` first, then the shared
    wide-gamut store keyed by display name."""
    p = KNUT_PRESETS_BY_KEY.get(preset_key)
    if p is None:
        return None
    if p.ti1_asset:
        try:
            side = resource_path(p.ti1_asset).parent / "recipe.json"
            if side.is_file():
                rec = json.loads(side.read_text(encoding="utf-8"))
                if isinstance(rec, dict) and rec:
                    return rec
        except Exception:  # noqa: BLE001
            pass
    rec = _load_shared_wg_recipes().get(_recipe_display_key(p))
    return rec if isinstance(rec, dict) and rec else None


def builtin_recipe_choices() -> dict[str, dict]:
    """``{display_name: recipe}`` for every built-in preset that carries a
    recipe — registry-driven, so it's not tied to one hardcoded file and any
    future built-in with a recipe shows up automatically (Knut)."""
    out: dict[str, dict] = {}
    for p in KNUT_PRESETS:
        rec = builtin_preset_recipe(p.key)
        if rec:
            out[_recipe_display_key(p)] = rec
    return out


# Built-in presets can be parked here (shown greyed-out, non-selectable) pending
# a fix from their author; none are parked at the moment.
DISABLED_BUILTIN_PRESET_KEYS = frozenset()

# Every built-in (non-deletable) preset key — all four are prebuilt-files. Used
# to protect them from the delete button and to keep disk presets from shadowing
# them.
BUILTIN_PRESET_KEYS = frozenset(PREBUILT_PRESETS) | KNUT_PRESET_KEYS
BUILTIN_PRESET_LABELS = frozenset({
    TC924_PRESET_LABEL, ABW1110_PRESET_LABEL,
    TC918EG_A4_PRESET_LABEL, TC918EG_LETTER_PRESET_LABEL,
    TC300_PRESET_LABEL, ABW702_PRESET_LABEL,
    TC924_CM_A3_PRESET_LABEL, TC918EG_CM_A3_PRESET_LABEL,
    EXT1944_A4_PRESET_LABEL, EXT1944_LETTER_PRESET_LABEL,
}) | {p.combo_label for p in KNUT_PRESETS}

# Built-in presets grouped by the instrument they target — the single source of
# truth shared by the Manual presets dropdown (_populate_preset_combo) and the
# "Built-in presets" overlay (BuiltinPresetPopup). Each group is
# (instrument, [(combo_label, overlay_label, key), …]). The combo label is the
# full "★ … · built-in" string; the overlay groups by instrument so it shows the
# shorter label with the instrument prefix dropped.
# Order here is the single source of truth for BOTH the dropdown and the overlay
# (neither re-sorts) — ColorMunki first, then i1Pro.
# Knut's presets merged into their instrument group, below the Pharmacist ones,
# ordered by paper size (smallest sheet first). sorted() is stable, so presets on
# the same paper keep their registry order (e.g. 2-page before 3-page).
_KNUT_GROUP_ENTRIES = {
    grp: [(p.combo_label, p.overlay_label, p.key)
          for p in sorted((q for q in KNUT_PRESETS if q.instrument == instr),
                          key=lambda q: _paper_sort_key(q.paper))]
    for grp, instr in (("ColorMunki", _KNUT_CM), ("i1Pro", _KNUT_I1))
}
BUILTIN_PRESET_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("ColorMunki", [
        (TC300_PRESET_LABEL,   "A4-300p-1page TC3.00 by Pharmacist",          TC300_PRESET_KEY),
        (ABW702_PRESET_LABEL,  "A4-702p-2pages ABW-optimized by Pharmacist",   ABW702_PRESET_KEY),
        (TC924_CM_A3_PRESET_LABEL, "A3-924p-1page TC9.24 by Pharmacist",       TC924_CM_A3_PRESET_KEY),
        (TC918EG_CM_A3_PRESET_LABEL, "A3+-1160p-1page TC9.18 extended greys by Pharmacist", TC918EG_CM_A3_PRESET_KEY),
        *_KNUT_GROUP_ENTRIES["ColorMunki"],
    ]),
    ("i1Pro", [
        # A4 first (ascending patch count), then US-Letter — keep paper grouped.
        (TC924_PRESET_LABEL,   "A4-924p-2pages TC9.24 by Pharmacist",          TC924_PRESET_KEY),
        (ABW1110_PRESET_LABEL, "A4-1110p-2pages ABW-optimized by Pharmacist",  ABW1110_PRESET_KEY),
        (TC918EG_A4_PRESET_LABEL,     "A4-1160p-2pages TC9.18 extended greys by Pharmacist",     TC918EG_A4_PRESET_KEY),
        (EXT1944_A4_PRESET_LABEL,     "A4-1944p-3pages extended target by Pharmacist",     EXT1944_A4_PRESET_KEY),
        (TC918EG_LETTER_PRESET_LABEL, "Letter-1160p-2pages TC9.18 extended greys by Pharmacist", TC918EG_LETTER_PRESET_KEY),
        (EXT1944_LETTER_PRESET_LABEL, "Letter-1944p-3pages extended target by Pharmacist", EXT1944_LETTER_PRESET_KEY),
        *_KNUT_GROUP_ENTRIES["i1Pro"],
    ]),
]


def _builtin_ti1_asset(key: str) -> str | None:
    """Asset path of a built-in preset's bundled .ti1, or None. Mirrors
    ChromIQ's ``TabChart._builtin_ti1_asset`` (minus the targen-based
    ColorMunki built-ins, which chromiq-patches doesn't ship)."""
    if key == TC918_PRESET_KEY:
        return TC918_TI1_ASSET
    if key in KNUT_PRESETS_BY_KEY:
        return KNUT_PRESETS_BY_KEY[key].ti1_asset
    if key in PREBUILT_PRESETS:
        return PREBUILT_PRESETS[key][0] + ".ti1"
    return None


def comparable_presets(settings) -> list[tuple[str, list[tuple[str, "Path"]]]]:
    """Presets whose patch set exists on disk, grouped for the "Compare with"
    dropdown: ``[(group, [(label, .ti1 path), …]), …]`` — built-in presets by
    instrument plus a "Custom presets" group for user presets that bundled a
    .ti1. Re-read on each call. Same contract as ChromIQ's version."""
    groups: list[tuple[str, list[tuple[str, Path]]]] = []
    for instr, entries in BUILTIN_PRESET_GROUPS:
        items: list[tuple[str, Path]] = []
        for _combo, overlay_label, key in entries:
            asset = _builtin_ti1_asset(key)
            if asset:
                p = resource_path(asset)
                if p.is_file():
                    items.append((overlay_label, p))
        if items:
            groups.append((instr, items))
    custom: list[tuple[str, Path]] = []
    for name, data in _load_tab_presets("create_chart", settings).items():
        if isinstance(data, dict) and data.get("attached_ti1"):
            sc = _preset_sidecar_path("create_chart", str(name), ".ti1")
            if sc.is_file():
                custom.append((str(name), sc))
    if custom:
        groups.append((tr("Custom presets"), custom))
    return groups
