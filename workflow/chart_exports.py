"""Extra deliverable files written alongside every generated chart.

A chart build leaves the load-bearing files (``.ti1`` / ``.ti2`` / ``.tif`` /
``.cht``) in the run folder.  This module adds the *hand-off* sidecars that let
the same chart be used outside ChromIQ's own measure tab:

* ``<stem>-colours.txt`` — a plain hex list of the device RGB values, the same
  format the New-chart "paste colour values" mode reads (RGB charts only).
* ``<stem>-i1profiler.txt`` / ``.pxf`` — the i1Profiler patch set (via
  :mod:`workflow.i1profiler_export`).

Everything here is best-effort and pure-Python; callers log what was written.
"""
from __future__ import annotations

from pathlib import Path


def _parse_cgats(path: Path) -> tuple[list[str], list[list[str]]]:
    """Return (field names, data rows) from a CGATS ``.ti1``/``.ti2`` file."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    fields: list[str] = []
    rows: list[list[str]] = []
    in_fmt = in_data = False
    for line in text.splitlines():
        s = line.strip()
        if s == "BEGIN_DATA_FORMAT":
            in_fmt = True; continue
        if s == "END_DATA_FORMAT":
            in_fmt = False; continue
        if s == "BEGIN_DATA":
            in_data = True; continue
        if s == "END_DATA":
            in_data = False; continue
        if in_fmt:
            fields += s.split()
        elif in_data and s:
            rows.append(s.split())
    return fields, rows


def write_colours_txt(ti1_path: str | Path, txt_path: str | Path) -> Path | None:
    """Write a ``<stem>-colours.txt`` hex list from an RGB chart's device values.

    Returns the path, or ``None`` when the chart isn't RGB (nothing written).
    """
    ti1_path, txt_path = Path(ti1_path), Path(txt_path)
    fields, rows = _parse_cgats(ti1_path)
    idx = {f: i for i, f in enumerate(fields)}
    if not all(c in idx for c in ("RGB_R", "RGB_G", "RGB_B")):
        return None
    out = []
    for r in rows:
        try:
            rgb = [float(r[idx[c]]) for c in ("RGB_R", "RGB_G", "RGB_B")]
        except (ValueError, IndexError):
            continue
        out.append("#" + "".join(f"{max(0, min(255, round(v / 100 * 255))):02x}"
                                 for v in rgb))
    txt_path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return txt_path


def write_sidecars(ti1_path: str | Path, out_dir: str | Path,
                   base_name: str) -> list[Path]:
    """Write the colour list and i1Profiler pair into *out_dir*.

    Best-effort: a failure of one file logs and skips it, never raising. Returns
    the list of files actually written. The ``.cht`` is produced by the chart
    build itself (engine ``emit_cht`` / printtarg), not here.
    """
    import logging
    log = logging.getLogger(__name__)
    ti1_path, out_dir = Path(ti1_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if not ti1_path.is_file():
        return written

    try:
        p = write_colours_txt(ti1_path, out_dir / f"{base_name}-colours.txt")
        if p is not None:
            written.append(p)
    except OSError:
        log.warning("colour-list export failed", exc_info=True)
    try:
        from workflow.i1profiler_export import export_from_ti1
        txt, pxf = export_from_ti1(ti1_path, out_dir,
                                   base_name=f"{base_name}-i1profiler",
                                   descriptor=base_name)
        written += [q for q in (txt, pxf) if q is not None]
    except Exception:  # noqa: BLE001 — never block on the i1Profiler export
        log.warning("i1Profiler export failed", exc_info=True)
    return written
