"""Reusable ChromIQ layout-engine options panel (issue #93).

The same control set is shown in **Settings → Chart Layout** (as the defaults
editor) and in the **Create Chart → Manual** module (as the per-chart mirror),
so the two can't drift.  The panel edits the layout-specific fields of a
:class:`~workflow.layout_engine.presets.LayoutRecipe`; the host supplies the
instrument / paper / mode (those live in the surrounding selectors).

It is Qt-only UI glue — no engine logic beyond reading/writing the recipe.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMenu,
    QToolButton, QVBoxLayout, QWidget,
)

from core.i18n import tr
from ui.tooltip_button import TooltipButton
from ui.widgets import (
    CollapsibleGroupBox,
    NoScrollComboBox,
    NoScrollDoubleSpinBox,
    NoScrollSpinBox,
)
from workflow.layout_engine.presets import LayoutRecipe

# Sheet-text placeholders, filled in at build time by chart.build_chart with
# human-readable values (e.g. {instrument} → "i1Pro3+", {paper} → "A4 landscape",
# {patchcount} → "576 patches", {seed} → "seed 1234", {dpi} → "300 dpi").
SHEET_TOKENS = (
    ("project", tr("Printer profile name")),
    ("page", tr("This page, e.g. “page 1/3”")),
    ("date", tr("Build date")),
    ("paper", tr("Paper size & orientation")),
    ("instrument", tr("Instrument name")),
    ("patchcount", tr("Patch count (with “patches”)")),
    ("pages", tr("Total number of pages")),
    ("seed", tr("Seed (with “seed”)")),
    ("dpi", tr("Resolution (with “dpi”)")),
)


class LayoutOptionsPanel(QWidget):
    """All layout-engine controls except instrument/paper/mode."""

    changed = pyqtSignal()

    # Labels mirror the printtarg -i combobox (data/parameters.yaml) so the engine
    # and printtarg show the same instrument names (Knut). Codes stay i1/p3/CM/SS.
    INSTRUMENTS = [("i1", "i1Pro / i1Pro 2 / i1Pro 3"),
                   ("p3", "i1Pro 3 Plus"),
                   ("CM", "ColorMunki / i1Studio / ColorChecker Studio"),
                   ("SS", "SpectroScan (flatbed)")]

    @staticmethod
    def mode_label_for(inst: str) -> str:
        """The selector's label — it isn't really a generic "Mode" (#93, Knut):
        for i1/p3 it's the clip border, for CM the density, for SS the shape."""
        if inst in ("i1", "p3"):
            return tr("Clip border:")
        if inst == "CM":
            return tr("Density:")
        if inst == "SS":
            return tr("Patch shape:")
        return tr("Mode:")

    @staticmethod
    def mode_tooltip_for(inst: str) -> tuple[str, str]:
        """(title, body) for the Mode selector's ⓘ, describing only the option
        that actually applies to *inst* — not every instrument's (#93, Knut)."""
        if inst in ("i1", "p3"):
            return (tr("Clip border"),
                    tr("Whether a CLIP BORDER is printed — the white strip the "
                       "measuring rail grips so it can pull the chart through. "
                       "Turning it off frees that space for more patches; only do "
                       "so if your rig doesn't need it. Choose which edge it sits "
                       "on, and what it carries (a notes box, text or a logo), in "
                       "the Clip-border content section."))
        if inst == "CM":
            return (tr("Reading density"),
                    tr("How densely the ColorMunki reads. “Hand-held” still reads "
                       "whole strips — just a few large, widely-spaced patches — "
                       "with no accessory needed. “High density (rig)” needs the "
                       "measuring-rig accessory and packs far more patches per "
                       "sheet. “Extra-high density” packs even more (a ChromIQ "
                       "extension) — only use it if your patches stay large enough "
                       "to read reliably (watch the warning).\n\n"
                       "Only available with “Prioritise patch size”: in "
                       "“Prioritise chart area” the patch size comes from the "
                       "columns/rows you set, so Density is hidden."))
        if inst == "SS":
            return (tr("Patch shape"),
                    tr("Rectangular or hexagonal patches. Hexagons tessellate "
                       "tighter, fitting a few more patches per sheet; "
                       "rectangular is the safe default."))
        return (tr("Layout mode"),
                tr("A per-instrument layout choice that keeps its own saved "
                   "preset."))

    @staticmethod
    def modes_for(inst: str) -> list[tuple[str, str]]:
        if inst in ("i1", "p3"):
            return [("clip", tr("On")),
                    ("noclip", tr("Off — more patches"))]
        if inst == "CM":
            return [("freehand", tr("Hand-held")), ("high", tr("High density (rig)")),
                    ("extrahigh", tr("Extra-high density"))]
        if inst == "SS":
            return [("flat", tr("Rectangular")), ("hex", tr("Hexagonal — denser"))]
        return [("default", tr("Default"))]

    def __init__(self, parent: QWidget | None = None, *,
                 with_calibration: bool = False, with_selectors: bool = False) -> None:
        super().__init__(parent)
        self._loading = False
        self._with_calibration = with_calibration
        self._with_selectors = with_selectors
        # Per-spacer manual colour overrides {str(flat_idx): "#hex"} — set by
        # clicking spacers in the editor preview; carried in the recipe (#93).
        self._spacer_overrides: dict = {}
        # The clip-side margin the user had before the clip band floored it, so it
        # can be restored when the band is turned off (Knut/Sebastian); None = not
        # currently floored. (key, value) e.g. ("l", 6.0).
        self._saved_clip_margin: "tuple[str, float] | None" = None
        self._border: float = 6.0      # base margin (-m); preserved, no control
        self._inst = "i1"           # last-known instrument / clip state, for
        self._clip = True           # clip-border-width row visibility
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        self.instr = self.paper = self.mode = self.pages = None
        if with_selectors:
            sel = QGridLayout()
            # Instrument and Mode each get a full-width row.
            self.instr = NoScrollComboBox(self)
            for k, lbl in self.INSTRUMENTS:
                self.instr.addItem(lbl, k)
            sel.addWidget(QLabel(tr("Instrument:"), self), 0, 0)
            sel.addWidget(self.instr, 0, 1, 1, 3)
            sel.addWidget(TooltipButton(
                tr("Instrument"),
                tr("The measuring device you'll read the printed chart with. It "
                   "sets the patch size, strip length and overall layout the chart "
                   "is built for, so pick the one you actually own — a chart laid "
                   "out for one instrument may not read correctly on another."),
                self), 0, 4)
            # Mode (= ColorMunki density / i1 clip mode / SpectroScan shape) and
            # the CM/SS Clip-border toggle are created here but ADDED TO THE LAYOUT
            # FRAME (below), grouped with the other layout choices for better order
            # (Knut #93). Labels/tips stay referenced for the conditional enabling.
            self.mode = NoScrollComboBox(self)
            self._mode_lbl = QLabel(tr("Mode:"), self)
            _mt, _mb = self.mode_tooltip_for("i1")
            self._mode_tip = TooltipButton(_mt, _mb, self)
            self._clip_enable_lbl = QLabel(tr("Clip border:"), self)
            self.clip_enable = NoScrollComboBox(self)
            self.clip_enable.addItem(tr("Off — more patches"), "off")
            self.clip_enable.addItem(tr("On"), "on")
            self.clip_enable.currentIndexChanged.connect(self._on_clip_enable_changed)
            self._clip_enable_tip = TooltipButton(
                tr("Clip border"),
                tr("Reserve a clip-border strip on this chart (the same option the "
                   "i1Pro has). On reserves a band you can fill with a notes box, "
                   "text or a logo in the Clip-border content section below; Off "
                   "uses the whole page for patches. Choose which edge it sits on "
                   "in that section."), self)
            # Paper + Pages share a row, directly under Instrument (Knut #93);
            # paper gets the stretch (wider).
            self.paper = NoScrollComboBox(self)
            sel.addWidget(QLabel(tr("Paper:"), self), 1, 0)
            sel.addWidget(self.paper, 1, 1)
            self._pages_lbl = QLabel(tr("Pages:"), self)
            sel.addWidget(self._pages_lbl, 1, 2)
            self.pages = NoScrollSpinBox(self)
            self.pages.setRange(1, 20)
            self.pages.setValue(1)
            self.pages.setMaximumWidth(70)
            self.pages.valueChanged.connect(self._emit)
            sel.addWidget(self.pages, 1, 3)
            sel.addWidget(TooltipButton(
                tr("Paper and pages"),
                tr("Paper is the sheet size you'll print on — the profile is only "
                   "valid for the paper you actually use. Pages is how many sheets "
                   "to spread the patches across: more pages = more patches total "
                   "(and more ink and paper)."), self), 1, 4)
            # Custom paper W×H (shown only when Paper = "Custom…").
            self._custom_paper_w = QWidget(self)
            _cpl = QHBoxLayout(self._custom_paper_w)
            _cpl.setContentsMargins(0, 0, 0, 0); _cpl.setSpacing(6)
            _cpl.addWidget(QLabel(tr("Custom size (mm):"), self))
            self.custom_w = NoScrollDoubleSpinBox(self)
            self.custom_h = NoScrollDoubleSpinBox(self)
            for _cs in (self.custom_w, self.custom_h):
                _cs.setRange(20, 2000); _cs.setDecimals(0); _cs.setMaximumWidth(80)
                _cs.valueChanged.connect(self._emit)
            self.custom_w.setValue(210); self.custom_h.setValue(297)
            _cpl.addWidget(self.custom_w); _cpl.addWidget(QLabel("×", self))
            _cpl.addWidget(self.custom_h); _cpl.addStretch()
            sel.addWidget(self._custom_paper_w, 2, 0, 1, 4)   # directly below Paper
            self._custom_paper_w.setVisible(False)
            sel.setColumnStretch(1, 1)        # paper / instrument / mode expand
            v.addLayout(sel)
            # Long paper labels shouldn't force the panel wide; the paper combo
            # gets a roomier minimum (it shares its row only with Pages) while
            # instrument/mode stay capped. The dropdown always shows full text.
            from PyQt6.QtWidgets import QComboBox
            self.paper.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self.paper.setMinimumContentsLength(11)   # elides long labels; full text in popup
            for _c in (self.instr, self.mode):
                _c.setSizeAdjustPolicy(
                    QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                _c.setMinimumContentsLength(10)
            self.instr.currentIndexChanged.connect(self._on_instr_changed)
            self.paper.currentIndexChanged.connect(self._on_paper_changed)
            self.mode.currentIndexChanged.connect(self._apply_mode_defaults)
            self.mode.currentIndexChanged.connect(self._sync_clip_content_for_mode)
            self.mode.currentIndexChanged.connect(self._emit)
            self.mode.currentIndexChanged.connect(self._update_clip_visibility)
            self._on_instr_changed()

        def mm(special_auto: bool = False, top: float = 300.0) -> NoScrollDoubleSpinBox:
            sb = NoScrollDoubleSpinBox(self)
            sb.setRange(0, top)
            sb.setDecimals(1)
            sb.setSingleStep(0.5)
            sb.setSuffix(" mm")
            sb.setMinimumWidth(96)          # room for "300,0 mm" + buttons
            if special_auto:
                sb.setSpecialValueText(tr("auto"))
            sb.valueChanged.connect(self._emit)
            return sb

        def scale() -> NoScrollDoubleSpinBox:
            sb = NoScrollDoubleSpinBox(self)
            sb.setRange(0.5, 3.0)
            sb.setDecimals(3)
            sb.setSingleStep(0.05)
            sb.setMinimumWidth(96)
            sb.valueChanged.connect(self._emit)
            return sb

        from PyQt6.QtCore import Qt as _Qt

        def add_row(grid, r, label, control, tip=None):
            """label | control (control fills the column → no clipping).
            Returns the placed widgets so a whole row can be shown/hidden."""
            lbl = QLabel(label, self)
            grid.addWidget(lbl, r, 0, _Qt.AlignmentFlag.AlignRight)
            grid.addWidget(control, r, 1)
            if tip is not None:
                grid.addWidget(tip, r, 2)
            grid.setColumnStretch(1, 1)
            return [w for w in (lbl, control, tip) if w is not None]

        def cell(*widgets):
            """A compact left-aligned row of small widgets in one grid cell."""
            box = QHBoxLayout(); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(6)
            for w in widgets:
                box.addWidget(w)
            box.addStretch()
            wrap = QWidget(self); wrap.setLayout(box)
            return wrap

        def cell_fill(grow, *fixed):
            """First widget fills the cell; trailing widgets keep their size."""
            box = QHBoxLayout(); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(6)
            box.addWidget(grow, 1)
            for w in fixed:
                box.addWidget(w)
            wrap = QWidget(self); wrap.setLayout(box)
            return wrap

        def mm_inch(spin):
            """A mm spinbox with a live, non-editable inch readout to its right —
            metric + imperial at a glance (#93, Knut). Sits in the control
            column's slack, so it doesn't widen the panel. Blank for a spinbox
            on its special ('auto'/'square') value."""
            inch = QLabel("", self)
            inch.setStyleSheet("color: #909090; font-size: 10px;")
            inch.setMinimumWidth(48)

            def _upd(*_a):
                v = spin.value()
                if spin.specialValueText() and v <= spin.minimum() + 1e-9:
                    inch.setText("")
                else:
                    # 3 decimals so a 0.1 mm change is visible in the inch readout
                    # (Knut beta.38).
                    inch.setText(f"{v / 25.4:.3f}″")
            spin.valueChanged.connect(_upd)
            _upd()
            box = QHBoxLayout(); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(6)
            box.addWidget(spin); box.addWidget(inch); box.addStretch()
            wrap = QWidget(self); wrap.setLayout(box)
            return wrap
        self._mm_inch = mm_inch

        # "Show strip indicators" (the per-chart on/off) lives in the Layout frame
        # right above Clip border (Knut #93); the indicator *styling* (font / size
        # / rotation / underline …) moved to Settings → Chart Layout. Created
        # unconditionally so from_recipe/to_recipe work even without selectors.
        self.show_indicators = QCheckBox(tr("Show strip indicators"), self)
        self.show_indicators.setChecked(True)
        self.show_indicators.toggled.connect(self._on_show_indicators)
        self.show_indicators.toggled.connect(self._emit)
        self._show_indicators_tip = TooltipButton(
            tr("Strip indicators"),
            tr("The small letter label printed above each strip (A, B, C…) so "
               "you always know which strip you're measuring and in what order. "
               "Turn off only if you have another way to keep the strips "
               "straight. Set the font, size and underline style in "
               "Settings → Chart Layout."), self)

        from PyQt6.QtWidgets import QLineEdit, QPushButton

        def small_mm(top: float = 60.0) -> NoScrollDoubleSpinBox:
            sb = NoScrollDoubleSpinBox(self)
            sb.setRange(0, top); sb.setDecimals(1); sb.setSingleStep(0.5)
            sb.setMinimumWidth(84)            # room for "300,0" / "auto" + buttons
            sb.setMaximumWidth(96)            # (suffix lives in the row label)
            sb.valueChanged.connect(self._emit)
            return sb

        # The layout groups are split into two collapsible sections (Knut): Basic
        # (Layout, Page geometry, Randomisation) open by default, and Expert
        # Options (Patches & spacers, Output, Sheet text, Clip-border content,
        # Printer calibration) collapsed. Each group below is routed into one of
        # these instead of straight onto the panel.
        self._basic_frame = CollapsibleGroupBox(tr("Basic"), self)
        self._expert_frame = CollapsibleGroupBox(
            tr("Expert Options"), self, collapsed=True)
        _basic_v = QVBoxLayout(self._basic_frame.body)
        _basic_v.setContentsMargins(6, 6, 6, 6)
        _expert_v = QVBoxLayout(self._expert_frame.body)
        _expert_v.setContentsMargins(6, 6, 6, 6)
        v.addWidget(self._basic_frame)
        v.addWidget(self._expert_frame)

        # ---- Layout strategy (patch-first vs area-first, #93 / Knut) ----
        lg = QGroupBox(tr("Layout"), self)
        lgg = QGridLayout(lg)
        self.layout_mode = NoScrollComboBox(self)
        self.layout_mode.addItem(
            tr("Prioritise chart area, then fit patches to it"), "area_first")
        self.layout_mode.addItem(
            tr("Prioritise patch size, then fit to page"), "patch_first")
        self.layout_mode.currentIndexChanged.connect(self._emit)
        self.layout_mode.currentIndexChanged.connect(self._sync_layout_mode)
        add_row(lgg, 0, tr("Create layout:"), self.layout_mode,
                tip=TooltipButton(
                    tr("Create layout"),
                    tr("Two ways to decide patch size vs. how many fit:\n\n"
                       "• Prioritise patch size — you set the patch size (or "
                       "scale) and ChromIQ fits as many patches as it can. Simple, "
                       "but the last strip may not reach the far margin.\n\n"
                       "• Prioritise chart area — you say how many strips "
                       "(columns) and/or patches per strip (rows) you want, and "
                       "ChromIQ SIZES the patches so the grid fills the usable area "
                       "(the space left inside your margins). The patch area always "
                       "lands exactly where you defined it; you trade patch size "
                       "for the grid you asked for. Watch that the patches don't "
                       "get too small for your instrument to read."), self))
        # Area-first fields (shown only in that mode).
        self._area_fields_w = QWidget(self)
        afg = QGridLayout(self._area_fields_w)
        afg.setContentsMargins(0, 0, 0, 0)
        self.area_cols = NoScrollSpinBox(self); self.area_cols.setRange(0, 200)
        self.area_cols.setSpecialValueText(tr("auto")); self.area_cols.setMaximumWidth(96)
        self.area_cols.valueChanged.connect(self._emit)
        self.area_cols.valueChanged.connect(self._sync_layout_mode)
        self.area_rows = NoScrollSpinBox(self); self.area_rows.setRange(0, 500)
        self.area_rows.setSpecialValueText(tr("auto")); self.area_rows.setMaximumWidth(96)
        self.area_rows.valueChanged.connect(self._emit)
        self.area_rows.valueChanged.connect(self._sync_layout_mode)
        # Patch shape as "minimum patch height, % of width" (Knut): 150 → height
        # 1.5× width. Stored in the recipe as a height:width fraction (value/100).
        # Default 100 % (square); no "square" special value — the arrows step it
        # up or down from 100 (Knut #93).
        self.area_ratio = NoScrollDoubleSpinBox(self)
        self.area_ratio.setRange(10.0, 1000.0); self.area_ratio.setDecimals(0)
        self.area_ratio.setSingleStep(10.0); self.area_ratio.setMaximumWidth(96)
        self.area_ratio.setSuffix(" %")
        self.area_ratio.setValue(100.0)
        self.area_ratio.valueChanged.connect(self._emit)
        self.area_min_patch = NoScrollDoubleSpinBox(self)
        self.area_min_patch.setRange(0.0, 100.0); self.area_min_patch.setDecimals(1)
        self.area_min_patch.setSingleStep(0.5); self.area_min_patch.setMaximumWidth(96)
        self.area_min_patch.setSpecialValueText(tr("auto"))
        self.area_min_patch.valueChanged.connect(self._emit)
        self.area_method = NoScrollComboBox(self)
        self.area_method.addItem(tr("By patch width"), "by_width")
        self.area_method.addItem(tr("By columns / rows"), "by_grid")
        self.area_method.currentIndexChanged.connect(self._emit)
        self.area_method.currentIndexChanged.connect(self._sync_layout_mode)
        add_row(afg, 0, tr("Calculation method:"), self.area_method,
                tip=TooltipButton(
                    tr("Calculation method"),
                    tr("How to work out the patch grid inside the area:\n\n"
                       "• By patch width — you set the smallest patch width (and a "
                       "height %); ChromIQ fits as many as possible at that size "
                       "and grows them to fill the area. You know the strip width "
                       "you want, without juggling column counts.\n\n"
                       "• By columns / rows — you set exactly how many strips and "
                       "patches-per-strip; ChromIQ sizes the patches to fit. Full "
                       "control of the grid, but you tune the counts to land on a "
                       "patch size you like.\n\n"
                       "Both fill the same patch area defined by the margins."),
                    self))
        self._area_row_minpatch = add_row(afg, 1, tr("Minimum patch width (mm):"),
                mm_inch(self.area_min_patch),
                tip=TooltipButton(
                    tr("Minimum patch width"),
                    tr("The smallest strip (patch) width your instrument can read "
                       "reliably. ChromIQ fits as many strips as possible at this "
                       "width, then grows them slightly so the grid fills the area "
                       "exactly. The patch height follows the height % below."),
                    self))
        self._area_row_ratio = add_row(afg, 2,
                tr("Minimum patch height (% of width):"), self.area_ratio,
                tip=TooltipButton(
                    tr("Minimum patch height"),
                    tr("The patch height as a percentage of its width. 100% keeps "
                       "height = width (square); 150% makes each patch half again "
                       "as tall as it is wide; below 100% makes them wider than "
                       "tall. It's a minimum — the engine grows the patches from "
                       "here to fill the chart area."), self))
        self._area_row_cols = add_row(afg, 3, tr("Strips (columns):"), self.area_cols,
                tip=TooltipButton(
                    tr("Strips (columns)"),
                    tr("How many strips (columns of patches) to fit across the "
                       "page. ChromIQ makes the patches exactly wide enough that "
                       "this many strips span the usable width, so the block "
                       "reaches the margins evenly.\n\n"
                       "Leave it on “auto” and ChromIQ picks a count that gives a "
                       "patch close to your instrument's natural patch size — the "
                       "size it was designed to read — then fills the width to "
                       "that count."), self))
        self._area_row_rows = add_row(afg, 4, tr("Patches per strip (rows):"),
                self.area_rows,
                tip=TooltipButton(
                    tr("Patches per strip (rows)"),
                    tr("How many patches to stack down each strip. ChromIQ makes "
                       "the patches exactly tall enough that this many fit the "
                       "usable height.\n\n"
                       "Leave it on “auto” and ChromIQ picks a count that gives a "
                       "patch close to your instrument's natural patch size — the "
                       "size it was designed to read — then fills the height to "
                       "that count."), self))
        lgg.addWidget(self._area_fields_w, 1, 0, 1, 3)
        # "Show strip indicators" is a layout option (not a selector), so it is
        # ALWAYS placed here — otherwise, when the panel has no built-in selectors
        # (e.g. the Settings → Chart Layout tab), the checkbox was created but
        # never added to a layout and floated at the panel's top-left, overlapping
        # the "Basic" frame header (Knut).
        lgg.addWidget(self.show_indicators, 2, 1)
        lgg.addWidget(self._show_indicators_tip, 2, 2)
        # Mode (density / clip mode / shape) and the CM/SS Clip-border toggle are
        # SELECTORS, so they only appear when the panel owns them (#93); in
        # Settings the same selectors are provided by the tab itself.
        if getattr(self, "mode", None) is not None:
            lgg.addWidget(self._mode_lbl, 3, 0)
            lgg.addWidget(self.mode, 3, 1)
            lgg.addWidget(self._mode_tip, 3, 2)
            lgg.addWidget(self._clip_enable_lbl, 4, 0)
            lgg.addWidget(self.clip_enable, 4, 1)
            lgg.addWidget(self._clip_enable_tip, 4, 2)
        # "Offset every second strip" is a ColorMunki layout option (printtarg's
        # rig stagger), so it belongs with the layout choices, not in Patches &
        # spacers (Knut). CM-only — visibility is set per-instrument. Always placed
        # (like Show strip indicators) so it shows in Settings too.
        self.cm_stagger_cb = QCheckBox(tr("Offset every second strip"), self)
        self.cm_stagger_cb.toggled.connect(self._emit)
        self._cm_stagger_tip = TooltipButton(
            tr("Offset every second strip"),
            tr("ColorMunki only: shifts every second strip down by half a patch so "
               "the columns interleave like a brick wall — matching ArgyllCMS "
               "printtarg's measuring-rig layout. Reserves a little space at the "
               "top and bottom for the offset, so the patch count drops slightly. "
               "Leave off for a plain aligned grid."), self)
        lgg.addWidget(self.cm_stagger_cb, 5, 1)
        lgg.addWidget(self._cm_stagger_tip, 5, 2)
        _basic_v.addWidget(lg)

        # ---- Patches & spacers (2-column: label | control) ----
        ps = QGroupBox(tr("Patches && spacers"), self)
        g = QGridLayout(ps)
        self.pscale = scale()
        self.sscale = scale()
        self.spacer_mode = NoScrollComboBox(self)
        for k, lbl in (("colored", tr("Coloured")), ("bw", tr("Black & white")),
                       ("none", tr("None"))):
            self.spacer_mode.addItem(lbl, k)
        self.spacer_mode.currentIndexChanged.connect(self._emit)
        self.spacer_mode.currentIndexChanged.connect(self._sync_spacer_swatches)
        self.spacer_width = mm(special_auto=True)
        self.patch_x = small_mm(); self.patch_x.setSpecialValueText(tr("auto"))
        self.patch_y = small_mm(); self.patch_y.setSpecialValueText(tr("auto"))
        self.inter_patch = mm()
        self.strip_gap = mm()
        self.sig = mm()
        self._patch_size_row = add_row(g, 0, tr("Patch size (mm):"),
                cell(self.patch_x, QLabel("×", self), self.patch_y),
                tip=TooltipButton(
                    tr("Patch size"),
                    tr("Width × height of each patch in millimetres. Leave at "
                       "“auto” (0) to use the instrument's recommended size "
                       "(scaled by Patch scale). A value below ~6 mm can make the "
                       "chart hard to read."), self))
        self._patch_scale_row = add_row(g, 1, tr("Patch scale:"), self.pscale,
                tip=TooltipButton(
                    tr("Patch scale"),
                    tr("Grows or shrinks every patch (and its spacer) together. "
                       "1.0 is the instrument's standard size. Below 1.0 fits more "
                       "patches per sheet but each is harder for the instrument to "
                       "read reliably — watch the warning if patches get too "
                       "small."), self))
        add_row(g, 2, tr("Spacers:"), self.spacer_mode,
                tip=TooltipButton(
                    tr("Spacers"),
                    tr("The thin separator drawn between patches in a strip so the "
                       "instrument can tell where one patch ends and the next "
                       "begins. “Coloured” picks a high-contrast colour per gap "
                       "(default, most reliable); “Black & white” uses plain "
                       "black/white; “None” removes them — only if your instrument "
                       "doesn't need gaps."), self))
        add_row(g, 3, tr("Spacer size:"), mm_inch(self.spacer_width),
                tip=TooltipButton(
                    tr("Spacer size"),
                    tr("How thick the separator between patches is, in mm (it runs "
                       "along the strip, between consecutive patches). Leave at "
                       "“auto” (0) for the instrument default; increase it only if "
                       "your scanner has trouble finding the patch edges."),
                    self))
        add_row(g, 4, tr("Spacer scale:"), self.sscale,
                tip=TooltipButton(
                    tr("Spacer scale"),
                    tr("Scales only the spacer thickness, leaving patch size "
                       "alone. 1.0 is standard; raise it for fatter gaps without "
                       "making the patches bigger."), self))
        add_row(g, 5, tr("Inter-patch gap:"), mm_inch(self.inter_patch),
                tip=TooltipButton(
                    tr("Inter-patch gap"),
                    tr("Makes the spacer between patches thicker, in mm — extra "
                       "blank separation along the strip. Usually 0; raise it only "
                       "if patches bleed into each other on your printer/paper."),
                    self))
        add_row(g, 6, tr("Strip-indicator gap:"), mm_inch(self.sig),
                tip=TooltipButton(
                    tr("Strip-indicator gap"),
                    tr("How far the strip's letter label sits below the top edge of "
                       "the page, in mm. At 0 the labels hug the minimum text-edge "
                       "distance at the very top; raising it slides them down, "
                       "toward the patches, to fine-tune where the labels print."),
                    self))
        add_row(g, 7, tr("Strip gap (between strips):"), mm_inch(self.strip_gap),
                tip=TooltipButton(
                    tr("Strip gap"),
                    tr("Extra blank space added sideways between neighbouring "
                       "strips (columns of patches), in mm. Usually 0, which packs "
                       "the strips as tightly as the instrument allows to fit the "
                       "most patches per sheet. Raise it if your scanner needs a "
                       "wider gutter between strips, or to spread a sparse chart "
                       "out — each millimetre here means fewer strips fit, so the "
                       "patch count drops."), self))
        # Custom spacer palette (colored mode): the engine draws each gap's
        # spacer from this set instead of the built-in accents.
        self.custom_spacer_cb = QCheckBox(tr("Custom spacer colours"), self)
        self.custom_spacer_cb.toggled.connect(self._on_custom_spacer_toggled)
        self._spacer_swatches = []
        _swrow = QHBoxLayout(); _swrow.setContentsMargins(0, 0, 0, 0); _swrow.setSpacing(4)
        # Five ChromIQ accents plus white + black, so the engine can pick a
        # high-contrast separator against very light or very dark patches too.
        for _hex in ("#ff4573", "#ffb42d", "#56d6a5", "#37bcd6", "#9f82ff",
                     "#ffffff", "#000000"):
            _b = QPushButton(self)
            # NOT objectName "compact_input": that QSS imposes an input min-width
            # which overrides setFixedSize, blowing the 5 swatches up to ~446px
            # and scrolling the panel (feedback_qt_button_sizing).
            _b.setFixedSize(26, 22)
            _b.setProperty("hexcol", _hex)
            self._style_swatch(_b)
            _b.clicked.connect(lambda _c=False, bb=_b: self._pick_spacer_colour(bb))
            self._spacer_swatches.append(_b)
            _swrow.addWidget(_b)
        _swrow.addStretch()
        _sww = QWidget(self); _sww.setLayout(_swrow)
        g.addWidget(self.custom_spacer_cb, 8, 1)
        g.addWidget(TooltipButton(
            tr("Custom spacer colours"),
            tr("By default the engine separates patches with spacers drawn from "
               "the five ChromIQ accent colours plus white and black, "
               "automatically picking the one with the most contrast at each gap "
               "so the instrument can always find the patch edges (white and "
               "black give it a strong choice against very dark or very light "
               "patches). Turn this on to choose your own set instead — click a "
               "swatch to change it. The engine still auto-picks the "
               "highest-contrast one from your set per gap, so keep them varied "
               "(and watch the low-contrast warning)."), self),
            8, 2)
        add_row(g, 9, tr("Spacer colours:"), _sww)
        self.edge_spacers_cb = QCheckBox(tr("Edge spacers (bracket each strip)"), self)
        self.edge_spacers_cb.toggled.connect(self._emit)
        g.addWidget(self.edge_spacers_cb, 10, 1)
        g.addWidget(TooltipButton(
            tr("Edge spacers"),
            tr("Adds a spacer before the first patch and after the last patch of "
               "every strip — the way ArgyllCMS printtarg does. It's optional: "
               "the instrument finds each strip from the white border the layout "
               "already leaves at both ends, so this isn't needed for reliable "
               "reading. It fits in space the layout already reserves, so it "
               "doesn't reduce the patch count. Turn it on if you prefer the "
               "printtarg look or want an extra separator at the strip ends."),
            self), 10, 2)
        _expert_v.addWidget(ps)

        # ---- Randomisation ----
        rg = QGroupBox(tr("Randomisation"), self)
        rgg = QGridLayout(rg)
        self.randomize_cb = QCheckBox(tr("Randomise patch order"), self)
        self.randomize_cb.setChecked(True)
        self.randomize_cb.toggled.connect(self._on_randomize_toggled)
        self.fixed_seed_cb = QCheckBox(tr("Use a fixed seed (reproducible)"), self)
        self.fixed_seed_cb.toggled.connect(self._on_fixed_seed_toggled)
        self.seed_spin = NoScrollSpinBox(self)
        self.seed_spin.setRange(0, 2_147_483_647)
        self.seed_spin.setMinimumWidth(70)        # don't force the row wide for 10 digits
        self.seed_spin.setMaximumWidth(150)
        self.seed_spin.setObjectName("compact_input")
        self.seed_spin.valueChanged.connect(self._emit)
        self.new_seed_btn = QPushButton(tr("New seed"), self)
        self.new_seed_btn.setObjectName("compact_input")
        # Height in the button's OWN stylesheet so the editor's controls QSS
        # (QPushButton { min-height: 26px }) can't inflate it; match the compact
        # browse buttons (#93).
        self.new_seed_btn.setStyleSheet(
            "QPushButton { min-height: 22px; max-height: 22px; "
            "padding-top: 0px; padding-bottom: 0px; }")
        self.new_seed_btn.clicked.connect(self._on_new_seed)
        rgg.addWidget(self.randomize_cb, 0, 1)
        rgg.addWidget(self.fixed_seed_cb, 1, 1)
        rgg.addWidget(QLabel(tr("Seed:"), self), 2, 0, _Qt.AlignmentFlag.AlignRight)
        rgg.addWidget(cell_fill(self.seed_spin, self.new_seed_btn), 2, 1)
        rgg.addWidget(TooltipButton(
            tr("Randomisation"),
            tr("Patches are shuffled across the sheet so a streak of similar "
               "colours can't bias a strip — leave this on. The seed is the "
               "number that drives the shuffle: with a fixed seed the exact same "
               "layout is reproduced every build (handy for re-printing an "
               "identical chart), otherwise a fresh seed is drawn each time. "
               "Press New seed to draw one now; it's saved with the chart so you "
               "can always recreate it."), self), 2, 2)
        _basic_v.addWidget(rg)
        self._on_randomize_toggled(True)

        # ---- Strip indicators (detail widgets) ----
        # The styling controls moved to Settings → Chart Layout (Knut #93); only
        # the "Show strip indicators" checkbox stays in the panel (in the Layout
        # frame, above Clip border). These widgets are still built so a loaded
        # preset's styling round-trips through from_recipe / to_recipe, but the
        # group is never shown — it's a hidden carrier (see si.setVisible(False)).
        si = QGroupBox(tr("Strip indicators"), self)
        sig2 = QGridLayout(si)
        self.indicator_font = NoScrollComboBox(self)
        self._populate_font_combo(self.indicator_font)
        self.indicator_font.currentIndexChanged.connect(self._emit)
        self.indicator_size = small_mm(top=20.0)
        self.indicator_size.setSpecialValueText(tr("auto"))
        self.ind_bold = QCheckBox(tr("Bold"), self)
        self.ind_bold.toggled.connect(self._emit)
        self.ind_italic = QCheckBox(tr("Italic"), self)
        self.ind_italic.toggled.connect(self._emit)
        self._add_font_rows(sig2, 1, tr("Font:"), self.indicator_font,
                            self.indicator_size, self.ind_bold, self.ind_italic,
                            tip=TooltipButton(
                                tr("Indicator font"),
                                tr("Typeface, size and style of the strip letter "
                                   "labels. Bundled fonts are listed first, then "
                                   "every font installed on your system. Size "
                                   "“auto” fits the label to the strip width; Bold "
                                   "/ Italic grey out for fonts that don't offer "
                                   "them."), self))
        self.underline_mode = NoScrollComboBox(self)
        for k, lbl in (("off", tr("Off")),
                       ("segments", tr("Coloured (5 segments)")),
                       ("cycle", tr("Coloured (per strip)")),
                       ("black", tr("Black"))):
            self.underline_mode.addItem(lbl, k)
        self.underline_mode.currentIndexChanged.connect(self._on_underline_changed)
        self.underline_thickness = small_mm(top=5.0)
        self.underline_gap = small_mm(top=20.0)
        add_row(sig2, 3, tr("Underline:"), self.underline_mode,
                tip=TooltipButton(
                    tr("Underline"),
                    tr("Draws a thin rule under each strip's letter label. "
                       "Coloured (5 segments) splits the rule into the five "
                       "ChromIQ accent colours side by side under every strip; "
                       "Coloured (per strip) instead cycles one accent colour "
                       "per strip so neighbours read apart; Black is a plain "
                       "rule. Use the thickness and distance to taste."),
                    self))
        add_row(sig2, 4, tr("Line thickness:"), self.underline_thickness,
                tip=TooltipButton(
                    tr("Underline thickness"),
                    tr("How thick the rule under the strip labels is drawn, in "
                       "millimetres. A thicker line is easier to spot at a glance; "
                       "a thinner one is more subtle. Only matters when the "
                       "Underline above is set to something other than Off."),
                    self))
        add_row(sig2, 5, tr("Line distance:"), self.underline_gap,
                tip=TooltipButton(
                    tr("Underline distance"),
                    tr("How far below the strip label the rule sits, in "
                       "millimetres. Increase it to give the label a little "
                       "breathing room above the line."), self))
        self.indicator_rotation = NoScrollComboBox(self)
        for _deg in (0, 90, 180, 270):
            self.indicator_rotation.addItem(f"{_deg}°", _deg)
        # Compact, but wide enough for "270°" + the dropdown arrow; the freed
        # space goes to the alignment checkboxes alongside it.
        self.indicator_rotation.setMinimumContentsLength(3)
        self.indicator_rotation.setMaximumWidth(88)
        self.indicator_rotation.currentIndexChanged.connect(self._on_rotation_changed)
        # Reading-axis alignment for side-rotated (90°/270°) multi-letter labels.
        # A mutually-exclusive checkbox set (Left / Centered / Right); only active
        # when the rotation lays the label on its side, greyed out otherwise.
        self.ind_align_left = QCheckBox(tr("Left"), self)
        self.ind_align_center = QCheckBox(tr("Centered"), self)
        self.ind_align_right = QCheckBox(tr("Right"), self)
        self._align_group = QButtonGroup(self)
        self._align_group.setExclusive(True)
        for _cb in (self.ind_align_left, self.ind_align_center, self.ind_align_right):
            self._align_group.addButton(_cb)
            _cb.toggled.connect(self._emit)
        self.ind_align_left.setChecked(True)
        add_row(sig2, 6, tr("Rotation:"),
                cell(self.indicator_rotation, self.ind_align_left,
                     self.ind_align_center, self.ind_align_right),
                tip=TooltipButton(
                    tr("Indicator rotation"),
                    tr("Turns the little letter printed above each strip so it "
                       "reads in the direction you want. 0° is normal, upright "
                       "text. 90° and 270° lay it on its side — useful when the "
                       "strips are very narrow (an upright letter would be wider "
                       "than the strip) or so the labels face you the way you "
                       "actually hold the sheet while measuring. 180° prints it "
                       "upside-down, for when you feed the page in from the other "
                       "end. If you're not sure, leave it at 0°.\n\n"
                       "Left / Centered / Right (only available at 90° / 270°) "
                       "set how a two-letter label lines up: Left keeps the first "
                       "letter on a fixed line nearest the patches so the label "
                       "grows away from them, Right anchors the last letter, and "
                       "Centered splits the difference."), self))
        self.strip_label_offset = NoScrollDoubleSpinBox(self)
        self.strip_label_offset.setRange(-50.0, 50.0)
        self.strip_label_offset.setDecimals(1)
        self.strip_label_offset.setSingleStep(0.5)
        self.strip_label_offset.setSuffix(" mm")
        self.strip_label_offset.setMinimumWidth(96)
        self.strip_label_offset.valueChanged.connect(self._emit)
        add_row(sig2, 7, tr("Label offset:"), self.strip_label_offset,
                tip=TooltipButton(
                    tr("Label offset"),
                    tr("Moves the strip letters up or down without moving the "
                       "patches. By default the labels sit flush just under the "
                       "top margin; a positive value lowers them toward the "
                       "patches, a negative value raises them into the margin. The "
                       "patch area doesn't change, so this doesn't affect how many "
                       "patches fit."), self))
        # Hidden carrier: the styling now lives in Settings → Chart Layout, but
        # these widgets still back from_recipe / to_recipe so presets round-trip.
        si.setVisible(False)
        self._on_rotation_changed()

        # ---- Page geometry ----
        pg = QGroupBox(tr("Page geometry"), self)
        gg = QGridLayout(pg)
        self.margins = {k: small_mm(top=60.0) for k in ("t", "r", "b", "l")}
        # One row per edge (Top/Right/Bottom/Left), each with a live inch readout
        # — Knut's "list all 4 margins, mm and inch" (#93).
        _mlabels = {"t": tr("Top"), "r": tr("Right"), "b": tr("Bottom"),
                    "l": tr("Left")}
        _mgrid = QGridLayout()
        _mgrid.setContentsMargins(0, 0, 0, 0)
        _mgrid.setVerticalSpacing(4); _mgrid.setHorizontalSpacing(6)
        # "Use instrument margins" — when ticked, the four margins come from
        # Preferences → Instrument Limits for this combo (read-only) (#93, Knut).
        # Shown only when a threshold lookup is wired (set_threshold_lookup).
        self.use_instr_margins = QCheckBox(tr("Use instrument margins"), self)
        self.use_instr_margins.setVisible(False)
        self.use_instr_margins.toggled.connect(self._sync_instr_margins)
        self.use_instr_margins.toggled.connect(self._emit)
        # Its own Page-geometry row so the ⓘ aligns with the panel's tooltip
        # column (gg col 2), not buried inside the margins sub-grid (Knut).
        self._use_instr_tip = TooltipButton(
            tr("Use instrument margins"),
            tr("Fill the four page margins from the per-instrument minimums set "
               "in Preferences → Instrument Limits for this instrument and "
               "paper, and lock them so the patch area always clears your "
               "reading jig. They refill automatically when you change "
               "instrument or paper. Untick to type your own margins."), self)
        self._use_instr_tip.setVisible(False)
        gg.addWidget(self.use_instr_margins, 0, 1)
        gg.addWidget(self._use_instr_tip, 0, 2)
        for _i, _k in enumerate(("t", "r", "b", "l")):
            _dl = QLabel(_mlabels[_k], self); _dl.setMinimumWidth(46)
            _mgrid.addWidget(_dl, _i, 0)
            _mgrid.addWidget(mm_inch(self.margins[_k]), _i, 1)
        _margins_w = QWidget(self); _margins_w.setLayout(_mgrid)
        self.dpi = NoScrollSpinBox(self); self.dpi.setRange(72, 1200)
        self.dpi.setSuffix(" dpi"); self.dpi.valueChanged.connect(self._emit)
        self.nolimit = QCheckBox(tr("Don't cap strip length"), self)
        self.nolimit.toggled.connect(self._emit)
        self.max_strip = mm(special_auto=True, top=2000.0)  # large paper / roll media
        self.offx = small_mm(top=300.0)
        self.offy = small_mm(top=300.0)
        self.strip_pat = QLineEdit(self); self.strip_pat.textChanged.connect(self._emit)
        self.patch_pat = QLineEdit(self); self.patch_pat.textChanged.connect(self._emit)
        # Patch-area alignment — where the block sits within the usable area.
        self.patch_align = NoScrollComboBox(self)
        for _key, _lbl in (
            ("top-left", tr("Top-left")), ("top-center", tr("Top-centre")),
            ("top-right", tr("Top-right")),
            ("center-left", tr("Centre-left")), ("center", tr("Centre")),
            ("center-right", tr("Centre-right")),
            ("bottom-left", tr("Bottom-left")), ("bottom-center", tr("Bottom-centre")),
            ("bottom-right", tr("Bottom-right")),
        ):
            self.patch_align.addItem(_lbl, _key)
        self.patch_align.currentIndexChanged.connect(self._emit)
        # Clip-border width (i1/p3, clip mode only) — reserved left zone for the
        # scanner's paper clip; printtarg hard-codes 26 mm, we make it adjustable.
        self.clip_width = small_mm(top=100.0)
        self.clip_width.setMinimum(10.0)
        self.clip_width.valueChanged.connect(self._sync_clip_margin_floor)
        self.clip_width_label = QLabel(tr("Clip border width:"), self)
        self.clip_width_tip = TooltipButton(
            tr("Clip border width"),
            tr("Width of the blank zone reserved down the left edge for the "
               "clip that holds the sheet against the scanner bed. Make it wider "
               "if your clip covers more of the page; the patches start to its "
               "right. Only applies to the i1Pro / i1Pro 3 in clip-border mode "
               "(printtarg fixes this at 26 mm)."), self)
        add_row(gg, 1, tr("Margins (mm):"), _margins_w,
                tip=TooltipButton(
                    tr("Margins"),
                    tr("Blank borders kept clear of patches on each edge — Top, "
                       "Right, Bottom, Left, in mm. Most printers can't print to "
                       "the very edge, so keep a few mm here; the smallest of the "
                       "four also sets the instrument's leader/clip base."), self))
        gg.addWidget(self.clip_width_label, 2, 0, _Qt.AlignmentFlag.AlignRight)
        self._clip_width_row = mm_inch(self.clip_width)   # spin + inch readout
        gg.addWidget(self._clip_width_row, 2, 1)
        gg.addWidget(self.clip_width_tip, 2, 2)
        add_row(gg, 3, tr("Resolution:"), self.dpi,
                tip=TooltipButton(
                    tr("Resolution"),
                    tr("Pixel density of the printed chart TIFF, in dots per inch. "
                       "300 dpi is a good default; higher makes a larger file with "
                       "no real benefit for solid colour patches."), self))
        self._max_strip_row = add_row(gg, 4, tr("Max strip length:"),
                mm_inch(self.max_strip),
                tip=TooltipButton(
                    tr("Max strip length"),
                    tr("Caps how long a single strip (column of patches) may get, "
                       "in mm. Leave at “auto” to use the instrument's limit (set "
                       "per instrument/paper in Settings → Instrument Limits). Some "
                       "scanners can't read a strip past a certain length; lower "
                       "this if long strips misread. Only used in “Prioritise patch "
                       "size” — area-first fills the page and warns if a strip is "
                       "longer than the instrument's ruler instead."), self))
        self._offset_row = add_row(gg, 5, tr("Chart offset (mm):"),
                cell(self.offx, QLabel("×", self), self.offy),
                tip=TooltipButton(
                    tr("Chart offset"),
                    tr("Shifts the whole patch block right (X) and down (Y) on the "
                       "sheet, in mm. Usually 0 — use it to nudge the layout away "
                       "from a printer's unprintable area or to line up with a "
                       "pre-printed sheet. Only used in “Prioritise patch size”; "
                       "area-first places the block by the margins."), self))
        add_row(gg, 6, tr("Strip pattern:"), self.strip_pat,
                tip=TooltipButton(
                    tr("Strip pattern"),
                    tr("How strips (columns) are labelled — the letter part of a "
                       "patch's location, e.g. A, B, C. Leave the default unless "
                       "you have a specific labelling scheme to match."), self))
        add_row(gg, 7, tr("Patch pattern:"), self.patch_pat,
                tip=TooltipButton(
                    tr("Patch pattern"),
                    tr("How patches within a strip are numbered — the number part "
                       "of a location, e.g. A1, A2, A3. Leave the default unless "
                       "matching a specific scheme."), self))
        self._patch_align_row = add_row(gg, 8, tr("Patch area alignment:"),
                self.patch_align,
                tip=TooltipButton(
                    tr("Patch area alignment"),
                    tr("Where the whole patch block sits within the page once the "
                       "margins are kept clear. The patches rarely fill the usable "
                       "area exactly, so this decides where the leftover white "
                       "space goes.\n\n"
                       "“Top-left” pins the block to the top-left corner (the "
                       "leftover sits at the right and bottom); “Centre” puts the "
                       "spare space evenly around it; “Bottom-right” pins it to the "
                       "opposite corner, and so on. It only moves the block — the "
                       "patch count and size don't change. Margins / thresholds "
                       "are still respected."), self))
        gg.addWidget(self.nolimit, 9, 1)
        self._nolimit_tip = TooltipButton(
            tr("Don't cap strip length"),
            tr("Removes the strip-length limit entirely (printtarg -P), letting a "
               "strip run the full usable height. Only enable if your instrument "
               "can read an unlimited-length strip; otherwise leave it off. Only "
               "used in “Prioritise patch size” — area-first already fills the "
               "page, so it's hidden there."),
            self)
        gg.addWidget(self._nolimit_tip, 9, 2)
        # Page geometry sits directly UNDER the Layout frame (Knut): the two are
        # the core layout block, so they read together, with patches/spacers and
        # the rest below. pg is built after several other groups, so insert it just
        # after Layout rather than appending at the end.
        _lg_idx = _basic_v.indexOf(lg)
        if _lg_idx >= 0:
            _basic_v.insertWidget(_lg_idx + 1, pg)
        else:
            _basic_v.addWidget(pg)
        self._update_clip_visibility()

        # ---- Output ----
        og = QGroupBox(tr("Output"), self)
        ogg = QGridLayout(og)
        self.bit_depth = NoScrollComboBox(self)
        self.bit_depth.addItem(tr("8-bit"), 8)
        self.bit_depth.addItem(tr("16-bit"), 16)
        self.bit_depth.currentIndexChanged.connect(self._emit)
        self.compression = NoScrollComboBox(self)
        for k, lbl in (("lzw", "LZW"), ("zlib", "Zlib"), ("none", tr("None"))):
            self.compression.addItem(lbl, k)
        self.compression.currentIndexChanged.connect(self._emit)
        add_row(ogg, 0, tr("Bit depth:"), self.bit_depth,
                tip=TooltipButton(
                    tr("Bit depth"),
                    tr("Colour precision of the chart TIFF. 8-bit is standard and "
                       "right for almost everyone. 16-bit doubles the file size "
                       "and only helps if your whole print path is genuinely "
                       "16-bit — otherwise it makes no visible difference."),
                    self))
        add_row(ogg, 1, tr("Compression:"), self.compression,
                tip=TooltipButton(
                    tr("Compression"),
                    tr("How the chart TIFF is compressed. LZW (default) and Zlib "
                       "are lossless and shrink the file; “None” writes it "
                       "uncompressed (largest, most compatible). All keep the "
                       "exact colours."), self))
        _expert_v.addWidget(og)

        # ---- Sheet text ----
        st = QGroupBox(tr("Sheet text"), self)
        stg = QGridLayout(st)
        self.chart_text = QLineEdit(self)
        self.chart_text.setPlaceholderText(tr("e.g. {project} — {date}"))
        self.chart_text.textChanged.connect(self._emit)
        self.insert_token_btn = self._make_insert_button(self.chart_text)
        self.text_preview = QLabel(self)
        self.text_preview.setWordWrap(True)
        self.text_preview.setStyleSheet("color: palette(mid);")
        self.chart_text_font = NoScrollComboBox(self)
        self._populate_font_combo(self.chart_text_font)
        self.chart_text_font.currentIndexChanged.connect(self._emit)
        self.chart_text_size = small_mm(top=20.0)
        self.chart_text_size.setSpecialValueText(tr("auto"))
        self.ct_bold = QCheckBox(tr("Bold"), self)
        self.ct_bold.toggled.connect(self._emit)
        self.ct_italic = QCheckBox(tr("Italic"), self)
        self.ct_italic.toggled.connect(self._emit)
        self.stamp_command = QCheckBox(tr("Stamp layout summary on the sheet"), self)
        self.stamp_command.toggled.connect(self._emit)
        add_row(stg, 0, tr("Custom text:"),
                cell_fill(self.chart_text, self.insert_token_btn),
                tip=TooltipButton(
                    tr("Sheet text"),
                    tr("Optional text printed in the bottom margin of every sheet. "
                       "Use Insert ▾ to drop in a placeholder — it's replaced with "
                       "a human-readable value when the chart is built: {project} "
                       "(profile name), {page} (“page 1/3”), {date}, {paper} (e.g. "
                       "“A4 landscape”), {instrument} (e.g. “i1Pro3+”), "
                       "{patchcount}, {pages}, {seed}, {dpi}. The Preview line "
                       "shows how it will read."), self))
        add_row(stg, 1, tr("Preview:"), self.text_preview)
        self._add_font_rows(stg, 2, tr("Font:"), self.chart_text_font,
                            self.chart_text_size, self.ct_bold, self.ct_italic,
                            tip=TooltipButton(
                                tr("Sheet-text font"),
                                tr("Typeface, size and style of the custom sheet "
                                   "text in the bottom margin. Size “auto” uses a "
                                   "sensible default; Bold / Italic grey out for "
                                   "fonts that don't offer them."), self))
        stg.addWidget(self.stamp_command, 4, 1)
        stg.addWidget(TooltipButton(
            tr("Stamp layout summary"),
            tr("Prints a one-line summary of how the chart was made (engine, "
               "instrument, paper, dpi, patch count, seed) in the bottom margin. "
               "Handy for re-creating an identical chart later from the printed "
               "sheet alone."), self), 4, 2)
        # Min distance from the paper edge to text, one per text-bearing side
        # (Knut #93): top = strip labels, bottom = sheet text, clip = notes/clip
        # band. Independent of the margins; text overflows toward this line (and a
        # violation is flagged) if its margin is too small.
        self.text_edge_top = small_mm(top=30.0); self.text_edge_top.setValue(4.0)
        self.text_edge = small_mm(top=30.0); self.text_edge.setValue(4.0)
        self.text_edge_clip = small_mm(top=30.0); self.text_edge_clip.setValue(4.0)
        _te = QHBoxLayout(); _te.setContentsMargins(0, 0, 0, 0); _te.setSpacing(4)
        for _lbl, _sp in ((tr("T"), self.text_edge_top), (tr("B"), self.text_edge),
                          (tr("Clip"), self.text_edge_clip)):
            _sp.setMaximumWidth(50)
            _te.addWidget(QLabel(_lbl, self)); _te.addWidget(_sp)
        _te.addStretch()
        _te_w = QWidget(self); _te_w.setLayout(_te)
        # Label on its own row, the three compact spins below it, so the wide
        # spin row doesn't force the whole panel wider. The spin row is indented to
        # the field column (1) so it lines up with the boxes above it (Knut #93).
        stg.addWidget(QLabel(tr("Text distance from edge (mm):"), self), 5, 0, 1, 2)
        stg.addWidget(_te_w, 6, 1, 1, 2)
        stg.addWidget(TooltipButton(
            tr("Text distance from edge"),
            tr("The minimum distance from the paper edge to the text on each side "
               "that can carry text: Top = strip labels, Bottom = sheet text, "
               "Clip = the clip-border / notes band. Increase a value if your "
               "printer clips text near that edge. These are independent of the "
               "page margins; if a margin is too small for its text, the text "
               "overflows toward this line and a margin warning is shown."), self),
            5, 2)
        _expert_v.addWidget(st)
        self._update_text_preview()

        # ---- Clip-border content (i1/p3 clip mode) ----
        self._clip_content_grp = QGroupBox(tr("Clip-border content"), self)
        ccg = QGridLayout(self._clip_content_grp)
        self.clip_content_mode = NoScrollComboBox(self)
        for k, lbl in (("off", tr("Off")), ("text", tr("Custom text")),
                       ("branding", tr("ChromIQ branding")),
                       ("notes", tr("Notes box")), ("image", tr("Imported image"))):
            self.clip_content_mode.addItem(lbl, k)
        self.clip_content_mode.currentIndexChanged.connect(self._on_clip_content_changed)
        self.clip_side = NoScrollComboBox(self)
        self.clip_side.addItem(tr("Left"), "left")
        self.clip_side.addItem(tr("Right"), "right")
        self.clip_side.currentIndexChanged.connect(self._sync_clip_margin_floor)
        self.clip_side.currentIndexChanged.connect(self._emit)
        self.clip_text = QLineEdit(self)
        self.clip_text.setPlaceholderText(tr("e.g. {project} — {date}"))
        self.clip_text.textChanged.connect(self._emit)
        self.clip_insert_btn = self._make_insert_button(self.clip_text)
        self.clip_text_font = NoScrollComboBox(self)
        self._populate_font_combo(self.clip_text_font)
        self.clip_text_font.currentIndexChanged.connect(self._emit)
        self.clip_image_path = QLineEdit(self)
        self.clip_image_path.setPlaceholderText(tr("no image selected"))
        self.clip_image_path.textChanged.connect(self._emit)
        self.clip_image_browse = self._compact_browse(tr("Browse for an image"))
        self.clip_image_browse.clicked.connect(self._browse_clip_image)
        from PyQt6.QtWidgets import QSizePolicy
        self.clip_dims_label = QLabel("", self)
        self.clip_dims_label.setStyleSheet("color: palette(mid);")
        self.clip_dims_label.setWordWrap(True)
        self.clip_preview = QLabel(self)
        self.clip_preview.setMinimumHeight(30)
        self.clip_preview.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        self.clip_preview.setStyleSheet("border: 1px solid palette(mid);")
        # Don't let the preview pixmap or dims text dictate the panel's min width
        # (it lives in a horizontal-scroll-free column).
        self.clip_preview.setSizePolicy(QSizePolicy.Policy.Ignored,
                                        QSizePolicy.Policy.Fixed)
        self.clip_dims_label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                           QSizePolicy.Policy.Preferred)
        self.clip_export_btn = QPushButton(tr("Export template (PNG + PDF)…"), self)
        self.clip_export_btn.setObjectName("compact_input")
        self.clip_export_btn.clicked.connect(self._export_clip_template)
        add_row(ccg, 0, tr("Content:"), self.clip_content_mode,
                tip=TooltipButton(
                    tr("Clip-border content"),
                    tr("Fills the blank strip down the left edge that the scanner "
                       "clip reserves. Custom text accepts the same "
                       "{project}/{date}/… tokens as the sheet text; Notes box "
                       "prints a ready-made record — chart facts filled in "
                       "automatically (patches, instrument, paper, page, profile "
                       "name, date) plus labelled lines to hand-write the "
                       "printer, ink set, paper and media settings; ChromIQ "
                       "branding stamps the wordmark; Imported image places a "
                       "logo. Export template gives you an exact-size PNG and PDF "
                       "to design a graphic in another tool."), self))
        add_row(ccg, 1, tr("Side:"), self.clip_side,
                tip=TooltipButton(
                    tr("Clip border side"),
                    tr("Which edge of the page the clip border / notes band sits "
                       "on — Left or Right. Choose whichever matches how you feed "
                       "the chart into your instrument's ruler. The patches fill "
                       "the rest of the page; the patch count is the same either "
                       "way."), self))
        add_row(ccg, 2, tr("Text:"), cell_fill(self.clip_text, self.clip_insert_btn))
        add_row(ccg, 3, tr("Font:"), self.clip_text_font)
        self._clip_image_row = add_row(
            ccg, 4, tr("Image:"),
            cell_fill(self.clip_image_path, self.clip_image_browse))
        # Image transform (rotate / scale / move) — applies to the imported image.
        self.clip_image_rotation = NoScrollSpinBox(self)
        self.clip_image_rotation.setRange(0, 359); self.clip_image_rotation.setSuffix("°")
        self.clip_image_scale = NoScrollDoubleSpinBox(self)
        # Very generous max (up to 50000%) so a small logo can be blown right up;
        # typing a value above the max would otherwise snap back (Knut). Step 10.
        self.clip_image_scale.setRange(1.0, 50000.0); self.clip_image_scale.setDecimals(0)
        self.clip_image_scale.setSingleStep(10.0)
        self.clip_image_scale.setSuffix(" %"); self.clip_image_scale.setValue(100.0)
        self.clip_image_offx = NoScrollDoubleSpinBox(self)
        self.clip_image_offy = NoScrollDoubleSpinBox(self)
        for _o in (self.clip_image_offx, self.clip_image_offy):
            _o.setRange(-300.0, 300.0); _o.setDecimals(1); _o.setSingleStep(0.5)
        def _xform_row(*pairs):
            row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(6)
            for _l, _w in pairs:
                _w.setMinimumWidth(88); _w.valueChanged.connect(self._emit)
                row.addWidget(QLabel(_l, self)); row.addWidget(_w)
            row.addStretch()
            wrap = QWidget(self); wrap.setLayout(row)
            return wrap
        # Two rows so each spin is wide enough for its content (rotate/scale on
        # one, move X/Y on the next).
        self._clip_image_xform_w = _xform_row((tr("Rotate"), self.clip_image_rotation),
                                              (tr("Scale"), self.clip_image_scale))
        self._clip_image_move_w = _xform_row((tr("X"), self.clip_image_offx),
                                             (tr("Y"), self.clip_image_offy))
        self._clip_image_fit_row = add_row(
                ccg, 5, tr("Image fit:"), self._clip_image_xform_w,
                tip=TooltipButton(
                    tr("Image fit"),
                    tr("Adjust the imported clip image: rotate (°), scale (% of the "
                       "fit-to-band size), and move it across (X) and along (Y) the "
                       "clip band, in mm."), self))
        self._clip_image_move_row = add_row(
                ccg, 6, tr("Image move (mm):"), self._clip_image_move_w)
        add_row(ccg, 7, tr("Clip area:"), self.clip_dims_label)
        add_row(ccg, 8, tr("Preview:"), self.clip_preview)
        ccg.addWidget(self.clip_export_btn, 9, 1)
        _expert_v.addWidget(self._clip_content_grp)

        # ---- Calibration (per-chart; engine -K/-I) ----
        self.cal_mode = self.cal_path_edit = None
        if with_calibration:
            from PyQt6.QtWidgets import QLineEdit, QPushButton
            cg = QGroupBox(tr("Printer calibration"), self)
            cgg = QGridLayout(cg)
            cgg.addWidget(QLabel(tr("Mode:"), self), 0, 0)
            self.cal_mode = NoScrollComboBox(self)
            for k, lbl in (("off", tr("None")),
                           ("apply", tr("Apply & embed (-K)")),
                           ("embed", tr("Embed only (-I)"))):
                self.cal_mode.addItem(lbl, k)
            self.cal_mode.currentIndexChanged.connect(self._emit)
            cgg.addWidget(self.cal_mode, 0, 1)
            self.cal_path_edit = QLineEdit(self)
            self.cal_path_edit.setPlaceholderText(tr("no .cal file selected"))
            self.cal_path_edit.textChanged.connect(self._emit)
            cgg.addWidget(self.cal_path_edit, 1, 0, 1, 3)
            browse = self._compact_browse(tr("Browse for a .cal file"))
            browse.clicked.connect(self._browse_cal)
            cgg.addWidget(browse, 1, 3)
            cgg.addWidget(TooltipButton(
                tr("Printer calibration"),
                tr("Attach an ArgyllCMS calibration (.cal) that linearises your "
                   "printer so the chart's tones come out evenly spaced. "
                   "“Apply & embed (-K)” bakes the calibration into the printed "
                   "patch values and also records it in the chart file — pick this "
                   "if you have a .cal and want it used. “Embed only (-I)” just "
                   "records it without changing the patches; use this when your "
                   "printer or RIP already linearises on its own. Leave it on "
                   "“None” if you don't use a calibration."), self), 0, 2)
            _expert_v.addWidget(cg)

        # Match the compact input styling used throughout the Manual module
        # (app QSS targets #compact_input for the slim look + white bg).
        from PyQt6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit
        for w in self.findChildren((QAbstractSpinBox, QComboBox, QLineEdit)):
            w.setObjectName("compact_input")

        self._sync_clip_content_enabled()
        self._sync_spacer_swatches()
        self._update_clip_visibility()
        self._sync_layout_mode()

    def _browse_cal(self) -> None:
        from pathlib import Path
        from ui.widgets import open_file_dialog
        cur = self.cal_path_edit.text().strip() if self.cal_path_edit else ""
        start = str(Path(cur).parent) if cur else ""
        path = open_file_dialog(
            self, tr("Select printer calibration"),
            name_filter=tr("ArgyllCMS calibration (*.cal)"),
            start_dir=start, extra_path=start)
        if path and self.cal_path_edit is not None:
            self.cal_path_edit.setText(path)

    def cal_settings(self) -> tuple[str | None, bool]:
        """Return ``(cal_path_or_None, apply_cal)`` for the engine."""
        if self.cal_mode is None:
            return None, False
        mode = self.cal_mode.currentData()
        path = (self.cal_path_edit.text().strip() or None) if self.cal_path_edit else None
        if mode == "off" or not path:
            return None, False
        return path, (mode == "apply")

    def set_cal(self, path: str, mode: str) -> None:
        if self.cal_mode is None:
            return
        i = self.cal_mode.findData(mode)
        self.cal_mode.setCurrentIndex(i if i >= 0 else 0)
        if self.cal_path_edit is not None:
            self.cal_path_edit.setText(path or "")

    # ------------------------------------------------------------------
    def _apply_mode_defaults(self, *_a) -> None:
        """Seed the Guided-matching defaults when the user picks a mode that has
        its own preset. ColorMunki Extra-high density mirrors Guided's triple
        density exactly: 5 mm margins on every side (clip already defaults off for
        CM). Skipped during load so a loaded recipe's own margins win (#93,
        Sebastian)."""
        if self._loading or self.mode is None or self.instr is None:
            return
        if (self.instr.currentData() == "CM"
                and self.mode.currentData() == "extrahigh"):
            self._loading = True
            for k in ("t", "r", "b", "l"):
                self.margins[k].setValue(5.0)
            self._border = 5.0                       # base margin, = Guided
            # Guided centres the patch block (the small extra gap below the strip
            # labels Sebastian liked); match it here.
            if hasattr(self, "patch_align"):
                j = self.patch_align.findData("center-left")
                if j >= 0:
                    self.patch_align.setCurrentIndex(j)
            self._loading = False
            self._emit()

    def _on_instr_changed(self, *_a) -> None:
        from workflow.layout_engine import papers
        if self.instr is None:
            return
        self._loading = True
        # New instrument = new clip context; forget any clip-floor restore point
        # so it can't clobber the new instrument's margins (e.g. a mode preset).
        self._saved_clip_margin = None
        inst = self.instr.currentData() or "i1"
        prev_paper = self.paper.currentData()
        self.paper.clear()
        for code, label, _dims in papers.list_papers(inst, for_engine=True):
            self.paper.addItem(label, code)
        self.paper.addItem(tr("Custom…"), "__custom__")
        i = self.paper.findData(prev_paper)
        if i < 0:
            # The engine paper list is ordered largest-first (A2 is index 0), which
            # is a surprising default — fall back to A4 when the previous paper
            # isn't available for the new instrument, not whatever sits at 0 (the
            # "keeps jumping back to A2" report, Sebastian).
            i = self.paper.findData("A4")
        self.paper.setCurrentIndex(i if i >= 0 else 0)
        prev_mode = self.mode.currentData()
        self.mode.clear()
        for k, lbl in self.modes_for(inst):
            self.mode.addItem(lbl, k)
        j = self.mode.findData(prev_mode)
        self.mode.setCurrentIndex(j if j >= 0 else 0)
        if getattr(self, "_mode_lbl", None) is not None:
            self._mode_lbl.setText(self.mode_label_for(inst))
        # Mode tooltip describes only the option this instrument actually has.
        if getattr(self, "_mode_tip", None) is not None:
            self._mode_tip.set_content(*self.mode_tooltip_for(inst))
        # The extra clip-border On/Off selector — and its tooltip — are for CM/SS
        # only (i1/p3 use their Mode selector for the clip border).
        if hasattr(self, "clip_enable"):
            is_band = inst in ("CM", "SS")
            self.clip_enable.setVisible(is_band)
            self._clip_enable_lbl.setVisible(is_band)
            self._clip_enable_tip.setVisible(is_band)
            self._sync_clip_enable_display()
        # "Offset every second strip" is a ColorMunki-only option.
        if hasattr(self, "cm_stagger_cb"):
            self.cm_stagger_cb.setVisible(inst == "CM")
            self._cm_stagger_tip.setVisible(inst == "CM")
        # Re-evaluate area-first field visibility / Density-disable for the new
        # instrument (Density is moot for CM in area-first).
        if hasattr(self, "layout_mode"):
            self._sync_layout_mode()
        self._loading = False
        self._on_paper_changed()

    def _update_clip_visibility(self, *_a) -> None:
        """Show the clip-content group when a clip / notes band is available: for
        i1/p3 in clip-border mode, and for CM/SS (which can carry an optional
        notes band, #93). The clip-width row shows whenever that band exists
        (i1/p3 clip mode, or CM/SS once notes content is turned on)."""
        if not hasattr(self, "clip_width"):
            return
        if self.instr is not None:
            inst = self.instr.currentData() or "i1"
            clip_mode = inst in ("i1", "p3") and (self.mode.currentData() == "clip")
        else:
            inst = self._inst
            clip_mode = self._clip and inst in ("i1", "p3")
        is_band_inst = inst in ("CM", "SS")
        content_on = (hasattr(self, "clip_content_mode")
                      and self.clip_content_mode.currentData() != "off")
        # For CM/SS the band (and its content group) appears only when the clip
        # border is turned on — i.e. content is set to something — matching the
        # i1Pro, whose group hides when its clip is off (#93).
        show_group = clip_mode or (is_band_inst and content_on)
        show_width = clip_mode or (is_band_inst and content_on)
        for w in (self.clip_width_label,
                  getattr(self, "_clip_width_row", self.clip_width),
                  self.clip_width_tip):
            w.setVisible(show_width)
        if hasattr(self, "_clip_content_grp"):
            self._clip_content_grp.setVisible(show_group)
            if show_group:
                self._refresh_clip_preview()
        # Floor the clip-side margin at the clip width whenever a band is active.
        self._sync_clip_margin_floor()

    # ---- Clip-border content -------------------------------------------
    def _sync_clip_content_enabled(self) -> None:
        mode = self.clip_content_mode.currentData()
        # The "notes" design is fixed (auto-filled from the chart) so it ignores
        # the free Text field, but still honours the Font choice for its body.
        custom_text = mode in ("text", "branding")
        font_modes = mode in ("text", "branding", "notes")
        self.clip_text.setEnabled(custom_text)
        self.clip_insert_btn.setEnabled(custom_text)
        self.clip_text_font.setEnabled(font_modes)
        # The image path / rotate / scale / move rows only make sense for an
        # imported image, so HIDE them entirely unless "Imported image" is the
        # content type (Knut), rather than just greying them out.
        show_image = (mode == "image")
        for row in (getattr(self, "_clip_image_row", None),
                    getattr(self, "_clip_image_fit_row", None),
                    getattr(self, "_clip_image_move_row", None)):
            for w in (row or []):
                w.setVisible(show_image)

    def _on_clip_content_changed(self, *_a) -> None:
        self._sync_clip_content_enabled()
        # On CM/SS the clip-width row appears only once notes content is on, so
        # re-evaluate visibility when the content mode changes (#93).
        self._sync_clip_enable_display()
        self._update_clip_visibility()
        self._emit()

    def _sync_clip_enable_display(self) -> None:
        """Keep the CM/SS clip-border On/Off selector in step with the content
        mode (On ⇔ content set, Off ⇔ content off), without re-triggering its
        own handler (#93)."""
        if not hasattr(self, "clip_enable"):
            return
        on = (hasattr(self, "clip_content_mode")
              and self.clip_content_mode.currentData() not in (None, "off"))
        i = self.clip_enable.findData("on" if on else "off")
        self.clip_enable.blockSignals(True)
        self.clip_enable.setCurrentIndex(i if i >= 0 else 0)
        self.clip_enable.blockSignals(False)

    def _on_clip_enable_changed(self, *_a) -> None:
        """The CM/SS clip-border On/Off selector drives the content on/off."""
        self.set_clip_enabled(self.clip_enable.currentData() == "on")

    def _sync_clip_content_for_mode(self, *_a) -> None:
        """i1 / i1Pro 3+ use the Mode combo as the clip-border On/Off switch.
        Turning the clip border ON should default its content to the notes box
        (not “none”), and clear it when OFF — mirroring the CM/SS clip-enable
        behaviour (Knut). Skipped during load so a recipe that deliberately had
        the clip border on with no content keeps it."""
        if self._loading or self.instr is None or self.mode is None:
            return
        if self.instr.currentData() in ("i1", "p3"):
            self.set_clip_enabled(self.mode.currentData() == "clip")

    def clip_enabled(self) -> bool:
        """Whether a clip / notes band is currently turned on (content set)."""
        return (hasattr(self, "clip_content_mode")
                and self.clip_content_mode.currentData() not in (None, "off"))

    def set_clip_enabled(self, on: bool) -> None:
        """Turn the clip / notes band on or off by driving the content mode: On
        seeds a notes band (if none yet), Off clears it (#93). Lets a host (the
        Settings window) expose the CM/SS clip toggle without its own selector."""
        cur = self.clip_content_mode.currentData()
        if on and cur in (None, "off"):
            j = self.clip_content_mode.findData("notes")
            if j >= 0:
                self.clip_content_mode.setCurrentIndex(j)   # fires content-changed
        elif not on and cur not in (None, "off"):
            j = self.clip_content_mode.findData("off")
            if j >= 0:
                self.clip_content_mode.setCurrentIndex(j)   # fires content-changed
        else:
            self._update_clip_visibility()
            self._emit()

    def set_threshold_lookup(self, fn) -> None:
        """Wire a callable ``fn(instrument, paper_code) -> {L,R,T,B}|None`` that
        returns the user's Instrument-Margins thresholds, enabling the "Use
        instrument margins" checkbox (#93). Without it the checkbox stays hidden."""
        self._threshold_lookup = fn
        if hasattr(self, "use_instr_margins"):
            self.use_instr_margins.setVisible(fn is not None)
            if hasattr(self, "_use_instr_tip"):
                self._use_instr_tip.setVisible(fn is not None)
            self._sync_instr_margins()

    def _current_instrument_paper(self) -> tuple[str, str]:
        if self.instr is not None and self.paper is not None:
            return (self.instr.currentData() or "i1",
                    self.paper.currentData() or "A4")
        return (self._inst, "A4")

    def _sync_instr_margins(self, *_a) -> None:
        """When "Use instrument margins" is on, fill the four margins from the
        threshold lookup for the current combo and lock them read-only; ticking it
        remembers the user's own margins and unticking restores them (#93, Knut)."""
        fn = getattr(self, "_threshold_lookup", None)
        on = (fn is not None and hasattr(self, "use_instr_margins")
              and self.use_instr_margins.isChecked())
        loading = getattr(self, "_loading", False)
        if loading:                      # a fresh recipe → no restore baseline
            self._saved_margins = None

        def _set(k, v):
            self.margins[k].blockSignals(True)
            self.margins[k].setValue(float(v))
            self.margins[k].blockSignals(False)

        if on:
            # Remember the user's typed margins the first time it's ticked, so
            # unticking can put them back.
            if not loading and getattr(self, "_saved_margins", None) is None:
                self._saved_margins = {k: self.margins[k].value()
                                       for k in ("t", "r", "b", "l")}
            inst, paper = self._current_instrument_paper()
            try:
                thr = fn(inst, paper)
            except Exception:
                thr = None
            if thr:
                for k, key in {"t": "T", "r": "R", "b": "B", "l": "L"}.items():
                    v = thr.get(key)
                    if v not in (None, ""):
                        _set(k, v)
        else:
            saved = getattr(self, "_saved_margins", None)
            if saved is not None:        # restore what was there before ticking
                for k in ("t", "r", "b", "l"):
                    _set(k, saved[k])
                self._saved_margins = None
        for k in ("t", "r", "b", "l"):
            self.margins[k].setEnabled(not on)

    def _clip_band_active(self) -> bool:
        """Whether a clip / notes band is currently on for the selected
        instrument (i1/p3 clip mode, or CM/SS with notes content)."""
        inst = (self.instr.currentData() if self.instr is not None
                else self._inst) or "i1"
        if inst in ("i1", "p3"):
            return (self.mode.currentData() == "clip") if self.mode is not None \
                else bool(self._clip)
        if inst in ("CM", "SS"):
            return (hasattr(self, "clip_content_mode")
                    and self.clip_content_mode.currentData() not in (None, "off"))
        return False

    def _sync_clip_margin_floor(self, *_a) -> None:
        """The clip / notes band lives inside the clip-side page margin, so while
        the band is ON floor that margin at the clip-border width and show it in
        the box — editable, so the user can push the patches further in (Knut
        beta-13). When the band is turned OFF, RESTORE the margin the user had
        before it was floored (otherwise it stays stuck at the clip width and the
        band looks permanently reserved — Knut/Sebastian). Skipped while "Use
        instrument margins" locks the margins."""
        if self._loading or not (hasattr(self, "clip_width")
                                 and hasattr(self, "clip_side")):
            return
        if (hasattr(self, "use_instr_margins") and self.use_instr_margins.isChecked()):
            return
        key = "r" if (self.clip_side.currentData() or "left") == "right" else "l"
        if not self._clip_band_active():
            # Band off → give back the margin we floored when it went on.
            saved = getattr(self, "_saved_clip_margin", None)
            if saved is not None:
                skey, sval = saved
                self._saved_clip_margin = None
                self.margins[skey].setValue(sval)     # fires its own _emit
            return
        clip_w = self.clip_width.value()
        if self.margins[key].value() < clip_w:
            # Remember the user's margin once, before the first floor, so it can be
            # restored when the band is turned off again.
            if getattr(self, "_saved_clip_margin", None) is None:
                self._saved_clip_margin = (key, self.margins[key].value())
            self.margins[key].setValue(clip_w)        # fires its own _emit

    def _sync_layout_mode(self, *_a) -> None:
        """Show only the fields each layout choice needs (#93 / Knut). Area-first
        derives the patch size, so HIDE the patch size/scale rows and the patch-
        area-alignment row (alignment is moot when the patches fill the area) —
        symmetric with hiding the area fields in patch-first. Margins and clip-
        border width stay (they define the area)."""
        if not hasattr(self, "layout_mode"):
            return
        area = (self.layout_mode.currentData() == "area_first")
        self._area_fields_w.setVisible(area)
        # Patch size/scale/alignment, the strip-length cap and the chart offset are
        # all "Prioritise patch size" concerns — area-first sizes patches to fill
        # the margin box, so hide them there (Knut #93).
        _patch_first_rows = [getattr(self, "_patch_size_row", []),
                             getattr(self, "_patch_scale_row", []),
                             getattr(self, "_patch_align_row", []),
                             getattr(self, "_max_strip_row", []),
                             getattr(self, "_offset_row", [])]
        for row in _patch_first_rows:
            for w in row:
                w.setVisible(not area)
        for w in (getattr(self, "nolimit", None), getattr(self, "_nolimit_tip", None)):
            if w is not None:
                w.setVisible(not area)
        # Within area-first, show only the rows the chosen Calculation method
        # needs: "by patch width" → min width + height%; "by columns/rows" →
        # strips + rows (Knut's two methods).
        by_width = (self.area_method.currentData() == "by_width")
        for w in self._area_row_minpatch + self._area_row_ratio:
            w.setVisible(area and by_width)
        for w in self._area_row_cols + self._area_row_rows:
            w.setVisible(area and not by_width)
        # ColorMunki "Density" doesn't define an area-first grid (the area fields
        # do), so HIDE the whole Density row there rather than greying it — same as
        # the Calculation-method rows hidden in patch-first (Knut). i1 clip and SS
        # shape still affect the area, so their Mode row stays.
        if self.mode is not None:
            inst = (self.instr.currentData() if self.instr is not None
                    else self._inst) or "i1"
            density_moot = (inst == "CM" and area)
            for w in (self.mode, getattr(self, "_mode_lbl", None),
                      getattr(self, "_mode_tip", None)):
                if w is not None:
                    w.setVisible(not density_moot)

    def _browse_clip_image(self) -> None:
        from pathlib import Path
        from ui.widgets import open_file_dialog
        cur = self.clip_image_path.text().strip()
        start = str(Path(cur).parent) if cur else ""
        path = open_file_dialog(
            self, tr("Select clip-strip image"),
            name_filter=tr("Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)"),
            start_dir=start, extra_path=start, preview=True)
        if path:
            self.clip_image_path.setText(path)

    def _clip_geom_and_height(self):
        """Build the current i1/p3 Geom + paper height for the clip preview."""
        from workflow.layout_engine import instruments, papers
        if self.instr is not None:
            inst, paper, mode = self.selection()
        else:
            inst, paper, mode = self._inst, "A4", ("clip" if self._clip else "noclip")
        if inst not in ("i1", "p3"):
            return None
        try:
            geom = instruments.build(
                inst, border=min(self.margins[k].value() for k in ("t", "r", "b", "l")),
                margins=tuple(self.margins[k].value() for k in ("t", "r", "b", "l")),
                clip_border_width=self.clip_width.value(),
                nolpcbord=(mode != "clip"))
            _w, h_mm = papers.dimensions_mm(paper)
        except Exception:
            return None
        return geom, h_mm

    @staticmethod
    def _pil_to_pixmap(img):
        from PyQt6.QtGui import QImage, QPixmap
        rgb = img.convert("RGB")
        data = rgb.tobytes("raw", "RGB")
        qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3,
                      QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    def _preview_clip_image(self, max_px: int):
        """A downscaled copy of the clip image for the live preview, cached by
        (path, mtime, size) so dragging the rotate/scale/move spins stays smooth
        on a big file — generation still uses the full-resolution original (#93)."""
        path = self.clip_image_path.text().strip()
        if not path:
            return None
        try:
            from pathlib import Path as _P
            mtime = _P(path).stat().st_mtime
        except OSError:
            return None
        key = (path, mtime, int(max_px))
        if getattr(self, "_clip_img_cache_key", None) == key:
            return self._clip_img_cache
        try:
            from PIL import Image as _Img
            im = _Img.open(path).convert("RGBA")
            if max(im.width, im.height) > max_px:        # shrink for the preview
                sc = max_px / max(im.width, im.height)
                im = im.resize((max(1, int(im.width * sc)),
                                max(1, int(im.height * sc))))
            self._clip_img_cache_key, self._clip_img_cache = key, im
            return im
        except Exception:  # noqa: BLE001 — bad/missing image → blank preview
            self._clip_img_cache_key, self._clip_img_cache = key, None
            return None

    def _refresh_clip_preview(self) -> None:
        if not hasattr(self, "clip_preview"):
            return
        from PyQt6.QtCore import Qt
        from workflow.layout_engine import geometry, raster
        gh = self._clip_geom_and_height()
        area = geometry.clip_area_mm(gh[0], gh[1]) if gh else None
        if area is None:
            self.clip_dims_label.setText(tr("—"))
            self.clip_preview.clear()
            return
        _x, _y, w_mm, h_mm = area
        dpi = int(self.dpi.value())
        wp, hp = round(w_mm * dpi / 25.4), round(h_mm * dpi / 25.4)
        self.clip_dims_label.setText(
            tr("{w:.0f} × {h:.0f} mm  ({wp} × {hp} px @ {dpi} dpi)").format(
                w=w_mm, h=h_mm, wp=wp, hp=hp, dpi=dpi))
        mode = self.clip_content_mode.currentData()
        if mode == "off":
            self.clip_preview.clear()
            return
        pdpi = 220                  # render crisp, then scale down for display
        pw = max(1, round(w_mm * pdpi / 25.4))
        ph = max(1, round(h_mm * pdpi / 25.4))
        img = raster.render_clip_strip(
            mode, width_px=pw, height_px=ph, dpi=pdpi,
            text=self._resolve_sample(self.clip_text.text()),
            font_family=self.clip_text_font.currentData() or "Inter",
            image_path=self.clip_image_path.text().strip(),
            image_obj=self._preview_clip_image(max(pw, ph)) if mode == "image" else None,
            image_rotation=self.clip_image_rotation.value(),
            image_scale=self.clip_image_scale.value(),
            image_offset_x_mm=self.clip_image_offx.value(),
            image_offset_y_mm=self.clip_image_offy.value())
        # Show it lying down (rotated 90°) so the long strip uses the panel's
        # horizontal space instead of a thin vertical ribbon.
        img = img.rotate(-90, expand=True)
        pix = self._pil_to_pixmap(img)
        # Render at the screen's device-pixel ratio so it stays crisp on Retina
        # (a logical-size pixmap would be upscaled ×2 and look blurry).
        dpr = self.clip_preview.devicePixelRatioF() or 1.0
        avail = self.clip_preview.width()
        avail = min(max(avail if avail > 60 else 300, 120), 360)
        scaled = pix.scaledToWidth(round(avail * dpr),
                                   Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        self.clip_preview.setPixmap(scaled)
        self.clip_preview.setFixedHeight(round(scaled.height() / dpr) + 2)

    def _export_clip_template(self) -> None:
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from workflow.layout_engine import geometry, raster
        gh = self._clip_geom_and_height()
        area = geometry.clip_area_mm(gh[0], gh[1]) if gh else None
        if area is None:
            return
        _x, _y, w_mm, h_mm = area
        dpi = int(self.dpi.value())
        base, _ = QFileDialog.getSaveFileName(
            self, tr("Export clip template"), "clip-template",
            tr("Template base name"))
        if not base:
            return
        paths = raster.export_clip_template(
            base, width_px=round(w_mm * dpi / 25.4), height_px=round(h_mm * dpi / 25.4),
            width_mm=w_mm, height_mm=h_mm, dpi=dpi)
        QMessageBox.information(
            self, tr("Clip template exported"),
            tr("Wrote:\n{files}").format(files="\n".join(str(p) for p in paths)))

    def _sync_seed_enabled(self) -> None:
        on = self.randomize_cb.isChecked()
        self.fixed_seed_cb.setEnabled(on)
        self.new_seed_btn.setEnabled(on)
        self.seed_spin.setEnabled(on and self.fixed_seed_cb.isChecked())

    def _on_randomize_toggled(self, *_a) -> None:
        self._sync_seed_enabled()
        self._emit()

    def _on_fixed_seed_toggled(self, *_a) -> None:
        self._sync_seed_enabled()
        self._emit()

    def _on_new_seed(self) -> None:
        from workflow.layout_engine.permutation import pick_seed
        self.fixed_seed_cb.setChecked(True)   # a drawn seed is a reproducible one
        self.seed_spin.setValue(pick_seed())

    def _make_insert_button(self, target):
        """A compact "Insert ▾" token menu that inserts into *target* line edit.

        Qt's own menu-indicator arrow is hidden so the single "▾" in the label
        is the only arrow (and stays aligned with the text).
        """
        btn = QToolButton(self)
        btn.setText(tr("Insert ▾"))
        btn.setObjectName("compact_input")
        btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(btn)
        for tok, desc in SHEET_TOKENS:
            act = menu.addAction(f"{{{tok}}} — {desc}")
            act.triggered.connect(
                lambda _c=False, t=tok, tgt=target: self._insert_token_into(tgt, t))
        btn.setMenu(menu)
        return btn

    @staticmethod
    def _style_swatch(btn) -> None:
        # min/max-width in the button's OWN stylesheet — the app QSS min-width
        # (for QPushButton / #compact_input) otherwise overrides setFixedSize and
        # blows the swatch row wide (feedback_qt_button_sizing).
        hexc = btn.property("hexcol") or "#ffffff"
        btn.setStyleSheet(
            f"QPushButton {{ background: {hexc}; border: 1px solid #888; "
            "border-radius: 3px; min-width: 22px; max-width: 26px; "
            "min-height: 18px; max-height: 22px; padding: 0; margin: 0; }")

    def _pick_spacer_colour(self, btn) -> None:
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog
        cur = QColor(btn.property("hexcol") or "#ffffff")
        # Non-native picker (hex field + RGB/HSV spinners), matching the editor's
        # patch / single-colour pickers — not the OS colour panel.
        col = QColorDialog.getColor(
            cur, self, tr("Spacer colour"),
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if col.isValid():
            btn.setProperty("hexcol", col.name())
            self._style_swatch(btn)
            self._emit()

    def set_spacer_override(self, flat: int, hexcol: "str | None") -> None:
        """Set (or clear, if *hexcol* is None) one spacer's manual colour and
        emit changed — used by the editor's click-to-recolour (#93)."""
        key = str(int(flat))
        if hexcol is None:
            self._spacer_overrides.pop(key, None)
        else:
            self._spacer_overrides[key] = hexcol
        self._emit()

    def _on_custom_spacer_toggled(self, *_a) -> None:
        self._sync_spacer_swatches()
        self._emit()

    def _sync_spacer_swatches(self, *_a) -> None:
        if not hasattr(self, "custom_spacer_cb"):
            return
        on = (self.custom_spacer_cb.isChecked()
              and (self.spacer_mode.currentData() or "colored") == "colored")
        for b in self._spacer_swatches:
            b.setEnabled(on)

    def _compact_browse(self, tooltip: str):
        """A magenta folder browse button sized like the targen -c browse
        (objectName browse_compact, 14px icon, 22px tall)."""
        from PyQt6.QtCore import QSize
        from ui.widgets import load_magenta_folder_icon, make_browse_button
        b = make_browse_button(self, tooltip)
        b.setIcon(load_magenta_folder_icon())
        b.setObjectName("browse_compact")
        b.style().unpolish(b)
        b.style().polish(b)
        b.setIconSize(QSize(14, 14))
        b.setFixedHeight(22)
        # Enforce the height in the button's OWN stylesheet too — when this panel
        # is embedded in the editor, the editor's controls QSS
        # (QPushButton { min-height: 26px }) cascades in and overrides
        # setFixedHeight; a per-widget rule has higher precedence (#93).
        b.setStyleSheet("QPushButton { min-height: 22px; max-height: 22px; "
                        "padding: 0px; margin: 0px; }")
        return b

    def _insert_token_into(self, target, token: str) -> None:
        """Drop ``{token}`` into *target* at the cursor."""
        target.insert("{%s}" % token)
        target.setFocus()

    def _resolve_sample(self, text: str) -> str:
        """Fill *text*'s placeholders with representative values for preview —
        mirroring the human-readable values chart.build_chart produces."""
        import time
        from data.patch_db import PAPER_LABELS
        inst, paper = "i1", "A4"
        if self.instr is not None:
            inst, paper, _ = self.selection()
        _instr_friendly = {"i1": "i1Pro", "p3": "i1Pro3+", "CM": "ColorMunki",
                           "SS": "SpectroScan", "41": "DTP41", "51": "DTP51"}
        _plabel = PAPER_LABELS.get(paper, paper)
        _pname = _plabel.split(" (")[0]
        _porient = (" landscape" if "Landscape" in _plabel
                    else " portrait" if "Portrait" in _plabel else "")
        _pages = self.get_pages()
        ctx = {
            "project": "MyChart", "page": f"page 1/{_pages}",
            "date": time.strftime("%Y-%m-%d"),
            "paper": f"{_pname}{_porient}",
            "instrument": _instr_friendly.get(inst, inst),
            "patchcount": "600 patches",
            "pages": str(_pages), "seed": "seed 12345",
            "dpi": f"{int(self.dpi.value())} dpi",
        }
        try:
            return text.format(**ctx)
        except (KeyError, IndexError, ValueError):
            return text       # unknown token — leave literal, as the builder does

    def _update_text_preview(self) -> None:
        if not hasattr(self, "text_preview"):
            return
        text = self.chart_text.text()
        self.text_preview.setText(self._resolve_sample(text) if text
                                  else tr("(no sheet text)"))

    def _add_font_rows(self, grid, r, label, combo, size, bold, italic,
                       tip=None) -> None:
        """Font on row *r*; Size + Bold + Italic on row *r+1*."""
        from PyQt6.QtCore import Qt
        grid.addWidget(QLabel(label, self), r, 0, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(combo, r, 1)
        if tip is not None:
            grid.addWidget(tip, r, 2)
        grid.addWidget(QLabel(tr("Size:"), self), r + 1, 0, Qt.AlignmentFlag.AlignRight)
        wrap = QWidget(self)
        box = QHBoxLayout(wrap); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(8)
        box.addWidget(size); box.addWidget(bold); box.addWidget(italic); box.addStretch()
        grid.addWidget(wrap, r + 1, 1)
        grid.setColumnStretch(1, 1)
        combo.currentIndexChanged.connect(
            lambda: self._update_style_enabled(combo, bold, italic))
        self._update_style_enabled(combo, bold, italic)

    def _update_style_enabled(self, combo, bold, italic) -> None:
        """Grey Bold/Italic (box + label) when the chosen font lacks the style.

        Uses the engine's own capability probe so the checkbox can't promise a
        style the renderer won't actually apply.
        """
        from workflow.layout_engine.raster import font_supports
        has_bold, has_italic = font_supports(combo.currentData() or "")
        bold.setEnabled(has_bold)
        italic.setEnabled(has_italic)
        if not has_bold:
            bold.setChecked(False)
        if not has_italic:
            italic.setChecked(False)

    @staticmethod
    def _populate_font_combo(combo) -> None:
        """Bundled fonts on top, then a separator, then all installed families."""
        for fam in ("JetBrains Mono", "Inter", "Instrument Serif"):
            combo.addItem(fam, fam)
        combo.insertSeparator(combo.count())
        try:
            from PyQt6.QtGui import QFontDatabase
            for fam in QFontDatabase.families():
                combo.addItem(fam, fam)
        except Exception:
            pass
        from PyQt6.QtWidgets import QComboBox
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)

    def _on_show_indicators(self, on: bool) -> None:
        self.indicator_font.setEnabled(on)
        self.indicator_size.setEnabled(on)
        if on:
            self._update_style_enabled(self.indicator_font,
                                       self.ind_bold, self.ind_italic)
        else:
            self.ind_bold.setEnabled(False)
            self.ind_italic.setEnabled(False)
        self._sync_underline_enabled()
        self._emit()

    def _sync_underline_enabled(self) -> None:
        on = self.show_indicators.isChecked()
        self.underline_mode.setEnabled(on)
        active = on and self.underline_mode.currentData() != "off"
        self.underline_thickness.setEnabled(active)
        self.underline_gap.setEnabled(active)

    def _on_underline_changed(self, *_a) -> None:
        self._sync_underline_enabled()
        self._emit()

    def _on_rotation_changed(self, *_a) -> None:
        """Reading-axis alignment only matters for the side rotations (90°/270°);
        grey out the Left/Centered/Right checkboxes (and their labels) otherwise."""
        rot = int(self.indicator_rotation.currentData() or 0)
        active = rot in (90, 270)
        for cb in (self.ind_align_left, self.ind_align_center, self.ind_align_right):
            cb.setEnabled(active)
        self._emit()

    def _on_paper_changed(self, *_a) -> None:
        if self.paper is not None:
            self._custom_paper_w.setVisible(self.paper.currentData() == "__custom__")
        # Re-pull instrument margins for the new instrument/paper combo (#93).
        if hasattr(self, "use_instr_margins") and self.use_instr_margins.isChecked():
            self._sync_instr_margins()
        self._emit()

    def selection(self) -> tuple[str, str, str]:
        """(instrument, paper, mode) from the selectors (when present)."""
        if self.instr is None:
            return "i1", "A4", "default"
        paper = self.paper.currentData() or "A4"
        if paper == "__custom__":
            paper = f"{int(self.custom_w.value())}x{int(self.custom_h.value())}"
        return (self.instr.currentData() or "i1", paper,
                self.mode.currentData() or "default")

    def get_pages(self) -> int:
        return int(self.pages.value()) if self.pages is not None else 1

    def set_pages(self, n: int) -> None:
        if self.pages is not None:
            self.pages.setValue(max(1, int(n)))

    def set_pages_enabled(self, enabled: bool) -> None:
        """Grey the Pages control (spin + label) — used when an exact patch count
        is set, so the page count is fixed (#93)."""
        if self.pages is not None:
            self.pages.setEnabled(enabled)
        if getattr(self, "_pages_lbl", None) is not None:
            self._pages_lbl.setEnabled(enabled)

    def get_recipe(self, base: LayoutRecipe | None = None) -> LayoutRecipe:
        """Build a complete recipe from the selectors (if any) + the controls."""
        from workflow.layout_engine.presets import default_recipe
        if self.instr is not None:
            inst, paper, mode = self.selection()
            r = default_recipe(inst, paper, mode=mode)
        else:
            r = base if base is not None else LayoutRecipe()
        return self.apply_to_recipe(r)

    def _emit(self, *_a) -> None:
        self._update_text_preview()
        self._refresh_clip_preview()
        if not self._loading:
            self.changed.emit()

    def set_recipe(self, r: LayoutRecipe) -> None:
        self._loading = True
        # The loaded recipe's margins are authoritative; forget any clip-floor
        # restore point from the previous chart so it can't clobber them.
        self._saved_clip_margin = None
        if self.instr is not None:
            ii = self.instr.findData(r.instrument)
            self.instr.setCurrentIndex(ii if ii >= 0 else 0)
            self._on_instr_changed()
            self._loading = True
            pi = self.paper.findData(r.paper)
            if pi >= 0:
                self.paper.setCurrentIndex(pi)
            else:
                from workflow.layout_engine import papers
                dims = papers.parse_custom(r.paper)
                ci = self.paper.findData("__custom__")
                if dims and ci >= 0:
                    self.paper.setCurrentIndex(ci)
                    self.custom_w.setValue(dims[0])
                    self.custom_h.setValue(dims[1])
            self._custom_paper_w.setVisible(self.paper.currentData() == "__custom__")
            mi = self.mode.findData(r.mode())
            if mi >= 0:
                self.mode.setCurrentIndex(mi)
        self.pscale.setValue(r.pscale)
        self.sscale.setValue(r.sscale)
        i = self.spacer_mode.findData(r.spacer_mode)
        self.spacer_mode.setCurrentIndex(i if i >= 0 else 0)
        self.spacer_width.setValue(r.spacer_width_mm)
        self.edge_spacers_cb.setChecked(bool(r.edge_spacers))
        self.cm_stagger_cb.setChecked(bool(getattr(r, "cm_stagger", False)))
        self._spacer_overrides = {str(k): v for k, v in (r.spacer_overrides or {}).items()}
        _pal = list(r.spacer_palette or [])
        self.custom_spacer_cb.setChecked(bool(_pal))
        for _i, _b in enumerate(self._spacer_swatches):
            if _i < len(_pal):
                _b.setProperty("hexcol", _pal[_i])
                self._style_swatch(_b)
        self._sync_spacer_swatches()
        _lm = self.layout_mode.findData(r.layout_mode or "patch_first")
        self.layout_mode.setCurrentIndex(_lm if _lm >= 0 else 0)
        _am = self.area_method.findData(r.area_method or "by_width")
        self.area_method.setCurrentIndex(_am if _am >= 0 else 0)
        self.area_cols.setValue(int(r.area_cols or 0))
        self.area_rows.setValue(int(r.area_rows or 0))
        # frac → %; an old 0.0 ("square") maps to 100 % (same height = width).
        self.area_ratio.setValue((float(r.area_ratio) or 1.0) * 100.0)
        self.area_min_patch.setValue(float(r.area_min_patch_mm or 0.0))
        self._sync_layout_mode()
        self.patch_x.setValue(r.patch_w_mm)
        self.patch_y.setValue(r.patch_h_mm)
        self.inter_patch.setValue(r.inter_patch_mm)
        self.strip_gap.setValue(r.strip_gap_mm)
        self.sig.setValue(r.strip_indicator_gap_mm)
        self.margins["t"].setValue(r.margin_top)
        self.margins["r"].setValue(r.margin_right)
        self.margins["b"].setValue(r.margin_bottom)
        self.margins["l"].setValue(r.margin_left)
        if hasattr(self, "use_instr_margins"):
            self.use_instr_margins.blockSignals(True)
            self.use_instr_margins.setChecked(bool(getattr(
                r, "use_instrument_margins", False)))
            self.use_instr_margins.blockSignals(False)
            self._sync_instr_margins()     # fill from thresholds when ticked
        self._border = r.border        # preserve base margin across the round-trip
        self.dpi.setValue(r.dpi)
        self.nolimit.setChecked(r.nolimit)
        self.max_strip.setValue(r.max_strip_mm)
        self.offx.setValue(r.offset_x_mm)
        self.offy.setValue(r.offset_y_mm)
        self.strip_pat.setText(r.strip_pattern)
        self.patch_pat.setText(r.patch_pattern)
        _ai = self.patch_align.findData(r.patch_area_align or "center-left")
        self.patch_align.setCurrentIndex(_ai if _ai >= 0 else
                                         self.patch_align.findData("center-left"))
        self.bit_depth.setCurrentIndex(1 if r.bit16 else 0)
        self.show_indicators.setChecked(r.show_strip_indicators)
        _fi = self.indicator_font.findData(r.indicator_font)
        self.indicator_font.setCurrentIndex(_fi if _fi >= 0 else 0)
        self.indicator_size.setValue(r.indicator_size_mm)
        self.ind_bold.setChecked(r.indicator_bold)
        self.ind_italic.setChecked(r.indicator_italic)
        _rot = self.indicator_rotation.findData(int(r.indicator_rotation))
        self.indicator_rotation.setCurrentIndex(_rot if _rot >= 0 else 0)
        _align = {"left": self.ind_align_left, "center": self.ind_align_center,
                  "right": self.ind_align_right}.get(r.indicator_align,
                                                     self.ind_align_left)
        _align.setChecked(True)
        self.strip_label_offset.setValue(r.strip_label_offset_mm)
        self._on_rotation_changed()      # grey out align unless 90°/270°
        _umkey = "segments" if r.underline_mode == "colored" else r.underline_mode
        _um = self.underline_mode.findData(_umkey)
        self.underline_mode.setCurrentIndex(_um if _um >= 0 else 0)
        self.underline_thickness.setValue(r.underline_thickness_mm)
        self.underline_gap.setValue(r.underline_gap_mm)
        self._sync_underline_enabled()
        self.chart_text.setText(r.chart_text)
        _ctf = self.chart_text_font.findData(r.chart_text_font)
        self.chart_text_font.setCurrentIndex(_ctf if _ctf >= 0 else 0)
        self.chart_text_size.setValue(r.chart_text_size_mm)
        self.text_edge.setValue(getattr(r, "text_edge_mm", 4.0) or 4.0)
        self.text_edge_top.setValue(getattr(r, "text_edge_top_mm", 4.0) or 4.0)
        self.text_edge_clip.setValue(getattr(r, "text_edge_clip_mm", 4.0) or 4.0)
        self.ct_bold.setChecked(r.chart_text_bold)
        self.ct_italic.setChecked(r.chart_text_italic)
        self.stamp_command.setChecked(r.stamp_command)
        ci = self.compression.findData(r.compression)
        self.compression.setCurrentIndex(ci if ci >= 0 else 0)
        self.clip_width.setValue(r.clip_border_width_mm or 26.0)
        _cc = self.clip_content_mode.findData(r.clip_content_mode)
        self.clip_content_mode.setCurrentIndex(_cc if _cc >= 0 else 0)
        _cs = self.clip_side.findData(getattr(r, "clip_side", "left") or "left")
        self.clip_side.setCurrentIndex(_cs if _cs >= 0 else 0)
        self.clip_text.setText(r.clip_text)
        _cf = self.clip_text_font.findData(r.clip_text_font)
        self.clip_text_font.setCurrentIndex(_cf if _cf >= 0 else 0)
        self.clip_image_path.setText(r.clip_image_path)
        self.clip_image_rotation.setValue(int(getattr(r, "clip_image_rotation", 0) or 0))
        self.clip_image_scale.setValue(float(getattr(r, "clip_image_scale", 100.0) or 100.0))
        self.clip_image_offx.setValue(float(getattr(r, "clip_image_offset_x_mm", 0.0) or 0.0))
        self.clip_image_offy.setValue(float(getattr(r, "clip_image_offset_y_mm", 0.0) or 0.0))
        self._sync_clip_content_enabled()
        self._sync_clip_enable_display()
        self.randomize_cb.setChecked(r.randomize)
        _fixed = r.seed is not None
        self.fixed_seed_cb.setChecked(_fixed)
        if _fixed:
            self.seed_spin.setValue(int(r.seed))
        self._sync_seed_enabled()
        self._inst, self._clip = r.instrument, r.clip_border
        self._update_clip_visibility()
        self._loading = False

    def apply_to_recipe(self, r: LayoutRecipe) -> LayoutRecipe:
        """Write the panel's values onto *r* (keeps r's instrument/paper/mode)."""
        r.pscale = self.pscale.value()
        r.sscale = self.sscale.value()
        r.spacer_mode = self.spacer_mode.currentData() or "colored"
        r.spacer_palette = ([b.property("hexcol") for b in self._spacer_swatches]
                            if self.custom_spacer_cb.isChecked() else [])
        r.spacer_overrides = dict(self._spacer_overrides)
        r.spacer_on = r.spacer_mode != "none"
        r.edge_spacers = self.edge_spacers_cb.isChecked()
        r.cm_stagger = self.cm_stagger_cb.isChecked()
        r.spacer_width_mm = self.spacer_width.value()
        r.layout_mode = self.layout_mode.currentData() or "patch_first"
        r.area_method = self.area_method.currentData() or "by_width"
        r.area_cols = int(self.area_cols.value())
        r.area_rows = int(self.area_rows.value())
        r.area_ratio = float(self.area_ratio.value()) / 100.0          # % → frac
        r.area_min_patch_mm = float(self.area_min_patch.value())
        r.patch_w_mm = self.patch_x.value()
        r.patch_h_mm = self.patch_y.value()
        r.inter_patch_mm = self.inter_patch.value()
        r.strip_gap_mm = self.strip_gap.value()
        r.strip_indicator_gap_mm = self.sig.value()
        r.margin_top = self.margins["t"].value()
        r.margin_right = self.margins["r"].value()
        r.margin_bottom = self.margins["b"].value()
        r.margin_left = self.margins["l"].value()
        if hasattr(self, "use_instr_margins"):
            r.use_instrument_margins = self.use_instr_margins.isChecked()
        # Preserve the chart's base margin (printtarg -m; drives the clip-holder
        # width lbord = clip_width − border). The panel has no separate control
        # for it, so re-deriving it from min(margins) silently changed it on a
        # round-trip (e.g. 10→6), shifting the layout right and dropping strips
        # in the editor. Keep the loaded value; new recipes default it to 6. (#93)
        r.border = self._border
        r.dpi = int(self.dpi.value())
        r.nolimit = self.nolimit.isChecked()
        r.max_strip_mm = self.max_strip.value()
        r.offset_x_mm = self.offx.value()
        r.offset_y_mm = self.offy.value()
        r.strip_pattern = self.strip_pat.text() or r.strip_pattern
        r.patch_pattern = self.patch_pat.text() or r.patch_pattern
        r.patch_area_align = self.patch_align.currentData() or "center-left"
        r.bit16 = (self.bit_depth.currentData() == 16)
        r.show_strip_indicators = self.show_indicators.isChecked()
        r.indicator_font = self.indicator_font.currentData() or "JetBrains Mono"
        r.indicator_size_mm = self.indicator_size.value()
        r.indicator_bold = self.ind_bold.isChecked()
        r.indicator_italic = self.ind_italic.isChecked()
        r.indicator_rotation = int(self.indicator_rotation.currentData() or 0)
        r.indicator_align = ("center" if self.ind_align_center.isChecked()
                             else "right" if self.ind_align_right.isChecked()
                             else "left")
        r.strip_label_offset_mm = self.strip_label_offset.value()
        r.underline_mode = self.underline_mode.currentData() or "off"
        r.underline_thickness_mm = self.underline_thickness.value()
        r.underline_gap_mm = self.underline_gap.value()
        r.chart_text = self.chart_text.text()
        r.chart_text_font = self.chart_text_font.currentData() or "Inter"
        r.chart_text_size_mm = self.chart_text_size.value()
        r.text_edge_mm = self.text_edge.value()
        r.text_edge_top_mm = self.text_edge_top.value()
        r.text_edge_clip_mm = self.text_edge_clip.value()
        r.chart_text_bold = self.ct_bold.isChecked()
        r.chart_text_italic = self.ct_italic.isChecked()
        r.stamp_command = self.stamp_command.isChecked()
        r.compression = self.compression.currentData() or "lzw"
        r.clip_border_width_mm = self.clip_width.value()
        r.clip_content_mode = self.clip_content_mode.currentData() or "off"
        r.clip_side = self.clip_side.currentData() or "left"
        r.clip_text = self.clip_text.text()
        r.clip_text_font = self.clip_text_font.currentData() or "Inter"
        r.clip_image_path = self.clip_image_path.text().strip()
        r.clip_image_rotation = self.clip_image_rotation.value()
        r.clip_image_scale = self.clip_image_scale.value()
        r.clip_image_offset_x_mm = self.clip_image_offx.value()
        r.clip_image_offset_y_mm = self.clip_image_offy.value()
        r.randomize = self.randomize_cb.isChecked()
        r.seed = (int(self.seed_spin.value())
                  if r.randomize and self.fixed_seed_cb.isChecked() else None)
        return r
