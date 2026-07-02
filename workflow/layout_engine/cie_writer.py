"""Emit an ArgyllCMS ``.cie`` reference from a *measured* ``.ti3``.

The companion to :mod:`workflow.layout_engine.cht_writer`: where the ``.cht``
says *where* each patch sits, the ``.cie`` says *what colour it truly is*. Their
key is the patch **loc** (``A01`` …) — the ``.cht`` box loc, the ``.ti3``
``SAMPLE_LOC`` and the ``.cie`` ``SAMPLE_ID`` are one and the same, because they
all come from the engine's single :func:`permutation.location_label`. ``scanin``
matches on it to turn a flatbed scan of the printed chart into a ``scan.ti3``
(scanner RGB ↔ measured reference), which ``colprof`` then builds into a scanner
input profile (#97).

The reference values are the **measured** XYZ from the run's ``.ti3`` — the real
colours the spectrophotometer read off the printed sheet — so the scanner
profile maps to the actual chart, exactly, with no RGB reconstruction. (This is
why an *aim*-value ``.cie`` was never meaningful and was dropped in beta.59: the
scanner must be characterised against what the paper really did, not the target.)

Format is IT8.7/2 CGATS, matching Argyll's own reference files::

    IT8.7/2
    ORIGINATOR "ChromIQ"
    DESCRIPTOR "<chart>"
    CREATED "<date>"

    NUMBER_OF_FIELDS 4
    BEGIN_DATA_FORMAT
    SAMPLE_ID XYZ_X XYZ_Y XYZ_Z
    END_DATA_FORMAT

    NUMBER_OF_SETS <n>
    BEGIN_DATA
    A01 <X> <Y> <Z>
    …
    END_DATA
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from workflow.ti3_analysis import Ti3Data, parse_ti3


def cie_rows_from_ti3(data: Ti3Data) -> list[tuple[str, float, float, float]]:
    """``(loc, X, Y, Z)`` reference rows from a measured ``.ti3``, keyed by
    ``SAMPLE_LOC`` (the id the ``.cht`` boxes use). XYZ is the measured D50
    0–100 value straight from the file, in the file's own patch order."""
    return [(loc, float(x), float(y), float(z))
            for loc, (x, y, z) in zip(data.sample_locs, data.xyz)]


def build_cie_text(rows: list[tuple[str, float, float, float]],
                   descriptor: str = "ChromIQ chart") -> str:
    """Render the IT8.7/2 ``.cie`` text for *rows* (``(loc, X, Y, Z)``)."""
    out: list[str] = [
        "IT8.7/2",
        'ORIGINATOR "ChromIQ"',
        f'DESCRIPTOR "{descriptor}"',
        f'CREATED "{date.today().isoformat()}"',
        "",
        "NUMBER_OF_FIELDS 4",
        "BEGIN_DATA_FORMAT",
        "SAMPLE_ID XYZ_X XYZ_Y XYZ_Z",
        "END_DATA_FORMAT",
        "",
        f"NUMBER_OF_SETS {len(rows)}",
        "BEGIN_DATA",
    ]
    out += [f"{loc} {x:.6f} {y:.6f} {z:.6f}" for loc, x, y, z in rows]
    out.append("END_DATA")
    out.append("")
    return "\n".join(out)


def write_cie(path: str | Path, data_or_ti3: Ti3Data | str | Path,
              descriptor: str = "ChromIQ chart") -> Path:
    """Write ``<…>.cie`` from a :class:`~workflow.ti3_analysis.Ti3Data` (or a
    ``.ti3`` path). Returns the written path."""
    data = (data_or_ti3 if isinstance(data_or_ti3, Ti3Data)
            else parse_ti3(data_or_ti3))
    p = Path(path)
    p.write_text(build_cie_text(cie_rows_from_ti3(data), descriptor),
                 encoding="utf-8")
    return p
