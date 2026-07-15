from pathlib import Path
import math
import os

from constants import BARCODE_FONT_PATH_PRIMARY, BARCODE_FONT_PATH_FALLBACK

# Pixel geometry tuned to match barcode.tec-it.com/en/UPCA output exactly.
# Derived by pixel-analysing 91 reference images (all 707×313 px at 300 DPI).
_IMG_W        = 707       # total image width
_IMG_H        = 313       # total image height
_QZ_PX        = 56        # quiet-zone width (each side)
_BAR_H_DATA   = 240       # regular data bars: y=0..239
_BAR_H_GUARD  = 273       # guard bars (start/middle/end): y=0..272
_MH_PX        = 594 / 95  # module width ≈6.2526 px  (barcode spans px 56–650)
_TEXT_Y       = 275       # vertical centre of digit characters (anchor "mm")
_FONT_PX      = 64        # Arial Regular pixel size - produces cap-height ≈48 px
_CAP_H_PX     = 48        # measured cap height of digits at _FONT_PX

# Module indices (0-based in the 95-module pattern) that are static guard bars.
_GUARD_MODULES = frozenset({0, 2, 46, 48, 92, 94})

# Points-per-pixel at the 300-DPI reference resolution (1 pt = 1/72 in).
_PX_TO_PT = 72 / 300


def validate_upc(raw: str) -> str:
    """
    Return a clean 12-digit UPC-A string.
    Accepts 11 digits (check digit auto-calculated) or 12 digits (check digit validated).
    Raises ValueError with a descriptive message on any problem.
    """
    code = raw.strip().replace("-", "").replace(" ", "")
    if not code:
        raise ValueError("empty")
    if not code.isdigit():
        raise ValueError(f"non-numeric characters in {code!r}")
    if len(code) == 11:
        code = code + _check_digit(code)
    elif len(code) == 12:
        expected = _check_digit(code[:11])
        if code[11] != expected:
            raise ValueError(
                f"invalid check digit in {code!r} (expected {expected}, got {code[11]})"
            )
    else:
        raise ValueError(f"expected 11 or 12 digits, got {len(code)} in {code!r}")
    return code


def _check_digit(eleven: str) -> str:
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(eleven))
    return str((10 - (total % 10)) % 10)


def _guard_mods_for(pattern: str) -> frozenset:
    return (
        _GUARD_MODULES
        | {i for i in range(3, 10)  if pattern[i] == "1"}   # first digit area
        | {i for i in range(85, 92) if pattern[i] == "1"}   # last digit area
    )


def generate_barcode_image(upc: str, output_path: Path, dpi: int = 300,
                           quality: int = 95, fmt: str = "EPS",
                           bar_height_pct: int = 100) -> None:
    """
    Render a UPC-A barcode.
    fmt="EPS"  → true vector EPS (resolution-independent; dpi ignored).
    fmt="JPEG" / "PNG" → raster image scaled to the requested DPI.
    bar_height_pct scales bar and image height independently of DPI.
    """
    if fmt == "EPS":
        _generate_eps(upc, output_path, bar_height_pct)
    else:
        _generate_raster(upc, output_path, dpi, quality, fmt, bar_height_pct)


# ── raster renderer ───────────────────────────────────────────────────────────

def _build_raster_image(upc: str, dpi: int, bar_height_pct: int):
    import barcode as bc
    from PIL import Image, ImageDraw, ImageFont

    dpi_s = dpi / 300
    h_s   = bar_height_pct / 100

    img_w       = round(_IMG_W       * dpi_s)
    img_h       = round(_IMG_H       * dpi_s * h_s)
    qz          = _QZ_PX             * dpi_s
    mh          = _MH_PX             * dpi_s
    bar_h_data  = round(_BAR_H_DATA  * dpi_s * h_s)
    bar_h_guard = round(_BAR_H_GUARD * dpi_s * h_s)
    text_y      = round(_TEXT_Y      * dpi_s * h_s)
    font_px     = round(_FONT_PX     * dpi_s * h_s)
    left_x      = round(11           * dpi_s)
    right_x     = round(706          * dpi_s)

    pattern = bc.get("upca", upc[:11]).build()[0]
    guard_mods = _guard_mods_for(pattern)

    img  = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img)

    for i, bit in enumerate(pattern):
        if bit == "1":
            x0 = math.ceil(qz + i * mh)
            x1 = math.ceil(qz + (i + 1) * mh) - 1
            bar_h = bar_h_guard if i in guard_mods else bar_h_data
            draw.rectangle([x0, 0, x1, bar_h - 1], fill="black")

    font_path = (
        BARCODE_FONT_PATH_PRIMARY
        if os.path.isfile(BARCODE_FONT_PATH_PRIMARY)
        else BARCODE_FONT_PATH_FALLBACK
    )
    font = ImageFont.truetype(font_path, font_px)

    draw.text((left_x,        text_y), upc[0],    font=font, fill="black", anchor="lm")
    draw.text((qz + 28 * mh,  text_y), upc[1:6],  font=font, fill="black", anchor="mm")
    draw.text((qz + 67 * mh,  text_y), upc[6:11], font=font, fill="black", anchor="mm")
    draw.text((right_x,       text_y), upc[11],   font=font, fill="black", anchor="rm")

    return img


def _generate_raster(upc: str, output_path: Path, dpi: int, quality: int,
                     fmt: str, bar_height_pct: int) -> None:
    img = _build_raster_image(upc, dpi, bar_height_pct)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict = {"dpi": (dpi, dpi)}
    if fmt == "JPEG":
        save_kwargs["quality"] = quality
    img.save(str(output_path), fmt, **save_kwargs)


def render_barcode_preview(upc: str, dpi: int = 300, bar_height_pct: int = 100):
    """Return a PIL Image for the live preview panel (no file I/O)."""
    return _build_raster_image(upc, dpi, bar_height_pct)


# ── vector EPS renderer ───────────────────────────────────────────────────────

def _generate_eps(upc: str, output_path: Path, bar_height_pct: int) -> None:
    """
    Write a fully vector EPS file. Bars are PostScript rectfill rectangles;
    digits are rendered in Helvetica (standard PS font, metrically equivalent
    to Arial). Resolution-independent - scales to any print size.
    """
    import barcode as bc

    h_s = bar_height_pct / 100
    P   = _PX_TO_PT  # pixel → point conversion at 300 DPI reference

    # Physical dimensions in points
    img_w_pt       = _IMG_W       * P
    img_h_pt       = _IMG_H       * P * h_s
    qz_pt          = _QZ_PX       * P
    mh_pt          = _MH_PX       * P
    bar_h_data_pt  = _BAR_H_DATA  * P * h_s
    bar_h_guard_pt = _BAR_H_GUARD * P * h_s
    font_pt        = _FONT_PX     * P * h_s

    # Digit baseline in PS coords (y from bottom of image).
    # With "mm" anchor: digits are centred at _TEXT_Y from top.
    # Cap height ≈ _CAP_H_PX, so baseline ≈ text_centre + cap_height/2 from top.
    baseline_from_top_pt = (_TEXT_Y + _CAP_H_PX / 2) * P * h_s
    baseline_pt = img_h_pt - baseline_from_top_pt

    # Horizontal text anchors (x only; widths scale with DPI, not bar height)
    left_x_pt  = 11  * P
    right_x_pt = 706 * P
    mfr_x_pt   = (_QZ_PX + 28 * _MH_PX) * P
    prod_x_pt  = (_QZ_PX + 67 * _MH_PX) * P

    pattern    = bc.get("upca", upc[:11]).build()[0]
    guard_mods = _guard_mods_for(pattern)

    bb_w = math.ceil(img_w_pt)
    bb_h = math.ceil(img_h_pt)

    lines: list[str] = [
        "%!PS-Adobe-3.0 EPSF-3.0",
        f"%%BoundingBox: 0 0 {bb_w} {bb_h}",
        f"%%HiResBoundingBox: 0.000 0.000 {img_w_pt:.3f} {img_h_pt:.3f}",
        "%%DocumentFonts: Helvetica",
        "%%EndComments",
        "",
        "% White background",
        "1 setgray",
        f"0 0 {img_w_pt:.3f} {img_h_pt:.3f} rectfill",
        "",
        "% Bars",
        "0 setgray",
    ]

    for i, bit in enumerate(pattern):
        if bit == "1":
            # Use the same ceil formula as the raster renderer for x positions
            x0_px = math.ceil(_QZ_PX + i * _MH_PX)
            x1_px = math.ceil(_QZ_PX + (i + 1) * _MH_PX) - 1
            bar_h_pt = bar_h_guard_pt if i in guard_mods else bar_h_data_pt
            x_pt = x0_px * P
            w_pt = (x1_px - x0_px + 1) * P
            # PS origin is bottom-left; bars start at the top of the image
            y_pt = img_h_pt - bar_h_pt
            lines.append(f"{x_pt:.3f} {y_pt:.3f} {w_pt:.3f} {bar_h_pt:.3f} rectfill")

    # PostScript stringwidth lets us centre/right-align without pre-computing widths
    lines += [
        "",
        "% Digit text",
        f"/Helvetica findfont {font_pt:.3f} scalefont setfont",
        "",
        "% Number system digit - left-aligned",
        f"{left_x_pt:.3f} {baseline_pt:.3f} moveto ({upc[0]}) show",
        "",
        "% Manufacturer code - centre-aligned",
        f"({upc[1:6]}) stringwidth pop 2 div neg {mfr_x_pt:.3f} add"
        f" {baseline_pt:.3f} moveto ({upc[1:6]}) show",
        "",
        "% Product code - centre-aligned",
        f"({upc[6:11]}) stringwidth pop 2 div neg {prod_x_pt:.3f} add"
        f" {baseline_pt:.3f} moveto ({upc[6:11]}) show",
        "",
        "% Check digit - right-aligned",
        f"({upc[11]}) stringwidth pop neg {right_x_pt:.3f} add"
        f" {baseline_pt:.3f} moveto ({upc[11]}) show",
        "",
        "%%EOF",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(output_path), "w", encoding="ascii") as f:
        f.write("\n".join(lines))


# ── spreadsheet helpers ───────────────────────────────────────────────────────

def read_spreadsheet_columns(path: Path) -> list[str]:
    """Return column names from an Excel or CSV file."""
    import pandas as pd
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, nrows=0)
    else:
        df = pd.read_excel(path, nrows=0)
    return list(df.columns)


def read_upcs_from_spreadsheet(path: Path, upc_col: str) -> list[str]:
    """Return UPC strings from the given column. Handles float-notation cells."""
    import pandas as pd
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=object)
    else:
        df = pd.read_excel(path, dtype=object)

    results: list[str] = []
    for _, row in df.iterrows():
        raw_upc = row.get(upc_col)
        if raw_upc is None or str(raw_upc).strip() in ("", "nan", "NaN", "None"):
            continue
        results.append(_cell_to_str(raw_upc))
    return results


def _cell_to_str(val) -> str:
    s = str(val).strip()
    if "." in s:
        try:
            f = float(s)
            if f == int(f):
                return str(int(f))
        except (ValueError, OverflowError):
            pass
    return s
