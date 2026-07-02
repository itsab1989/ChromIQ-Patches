"""Map device values to a displayable sRGB-ish triple for the TIFF raster.

ChromIQ profiles **RGB** printers, so RGB / CMY (stored as RGB) render exactly.
Gray and CMYK are converted for a faithful *visual* chart; their measured
device values in the ``.ti2`` are always exact regardless of this preview.
True CMYK/DeviceN raster output (a CMYK TIFF) is a later addition.
"""
from __future__ import annotations


def to_display_rgb(device: tuple[float, ...], color_rep: str) -> tuple[int, int, int]:
    """Device values (0–100) → 8-bit (R, G, B) for rendering."""
    rep = color_rep.upper()

    def clamp(v: float) -> int:
        return max(0, min(255, round(v)))

    if rep in ("RGB", "IRGB") and len(device) == 3:
        # Stored RGB is the printable RGB (CMY targets are stored as RGB too).
        return tuple(clamp(c / 100.0 * 255.0) for c in device)  # type: ignore[return-value]

    if rep == "W" and len(device) == 1:
        v = clamp(device[0] / 100.0 * 255.0)
        return (v, v, v)

    if rep.startswith("CMYK") and len(device) >= 4:
        c, m, y, k = (d / 100.0 for d in device[:4])
        r = 255.0 * (1.0 - c) * (1.0 - k)
        g = 255.0 * (1.0 - m) * (1.0 - k)
        b = 255.0 * (1.0 - y) * (1.0 - k)
        return (clamp(r), clamp(g), clamp(b))

    if rep in ("CMY",) and len(device) == 3:
        c, m, y = (d / 100.0 for d in device)
        return (clamp(255.0 * (1.0 - c)), clamp(255.0 * (1.0 - m)), clamp(255.0 * (1.0 - y)))

    # Fallback: first channel as grey.
    v = clamp((device[0] if device else 0.0) / 100.0 * 255.0)
    return (v, v, v)


def luminance(rgb: tuple[int, int, int]) -> float:
    """Rec.709 relative luminance (0–255)."""
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
