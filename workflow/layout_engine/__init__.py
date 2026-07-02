"""ChromIQ custom chart-layout engine (issue #93).

A from-scratch generator that turns a targen ``.ti1`` into a printable chart
(TIFF) plus a matching ``.ti2`` for chartread, as an alternative to driving
ArgyllCMS ``printtarg``.  Gated behind the ``use_chromiq_layout_engine``
setting (default off); the printtarg path remains the fallback.

This package is **Qt-free and unit-testable** (mirrors ``workflow/ti2_relayout``).
Phase 1 (this commit) lands the keystone, headless core:

* :mod:`instruments` — per-instrument geometry constants reverse-engineered
  from ``printtarg.c`` (verified against a live printtarg option matrix).
* :mod:`geometry`    — the steps-per-pass / passes / pages / padding packing
  math, a faithful port of printtarg's ``setup_pat`` layout computation.
* :mod:`permutation` — reproducible seeded patch-location shuffle + the
  strip/patch index-label generator (``A…Z, AA…AZ`` etc.).
* :mod:`ti2_writer` — emit a valid CGATS ``.ti2``.

See ``docs`` / issue #93 for the full design and the remaining phases
(raster, presets, settings tab, clip-border editor, ``.cht``, calibration).
"""
from __future__ import annotations
