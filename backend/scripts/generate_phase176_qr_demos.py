#!/usr/bin/env python3
"""Generate Phase 176 QR demo styles: safe, branded, and aggressive.

Outputs are written to: backend/outputs/phase-176-qr/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

PAYLOAD_URL = "https://sentinel-demo.example/visit/ABC123"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs" / "phase-176-qr"
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
LOGO_PATH = ASSETS_DIR / "sentinel-logo.png"
BACKGROUND_PATH = ASSETS_DIR / "sentinel-qr-background.png"
DEFAULT_REFERENCE_CONCEPT_PATH = Path(
    "/home/bederf/.cursor/projects/opt-bms-intelligence/assets/"
    "c__Users_beder_AppData_Roaming_Cursor_User_workspaceStorage_"
    "c14aa2f4fb44caf40e683a5db02f8baf_images_"
    "image-166b1077-ce7c-4d02-87de-1a46081ed291.png"
)

BRAND_DARK = "#0f5f2f"
WHITE = "#ffffff"


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def resolve_reference_concept() -> Path | None:
    env_path = os.getenv("PHASE176_QR_REFERENCE_IMAGE", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate
    if DEFAULT_REFERENCE_CONCEPT_PATH.exists():
        return DEFAULT_REFERENCE_CONCEPT_PATH
    return None


def extract_logo_from_reference(reference_path: Path) -> Path:
    """Create a center-cropped logo from the provided QR concept image."""
    reference_img = Image.open(reference_path).convert("RGBA")
    w, h = reference_img.size
    crop_size = min(w, h) // 3
    left = (w - crop_size) // 2
    top = (h - crop_size) // 2
    center_crop = reference_img.crop((left, top, left + crop_size, top + crop_size))
    center_crop = center_crop.resize((320, 320), Image.Resampling.LANCZOS)

    mask = Image.new("L", (320, 320), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((8, 8, 312, 312), fill=255)

    logo = Image.new("RGBA", (320, 320), (255, 255, 255, 0))
    logo.paste(center_crop, (0, 0), mask)
    logo.save(LOGO_PATH)
    return LOGO_PATH


def ensure_logo() -> Path:
    if LOGO_PATH.exists():
        return LOGO_PATH

    reference = resolve_reference_concept()
    if reference is not None:
        return extract_logo_from_reference(reference)

    img = Image.new("RGBA", (320, 320), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((16, 16, 304, 304), fill=(15, 95, 47, 255), outline=(0, 0, 0, 255), width=4)
    font = ImageFont.load_default()
    draw.text((145, 150), "S", fill=(255, 255, 255, 255), font=font)
    img.save(LOGO_PATH)
    return LOGO_PATH


def ensure_background() -> Path:
    if BACKGROUND_PATH.exists():
        return BACKGROUND_PATH

    reference = resolve_reference_concept()
    if reference is not None:
        Image.open(reference).convert("RGB").save(BACKGROUND_PATH)
        return BACKGROUND_PATH

    img = Image.new("RGB", (1400, 900), color=(248, 250, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1400, 120), fill=(15, 95, 47))
    draw.rectangle((0, 780, 1400, 900), fill=(18, 40, 28))
    draw.text((40, 38), "Sentinel Visitor Access", fill=(255, 255, 255))
    draw.text((40, 820), "Concept background for aggressive QR demo", fill=(230, 235, 230))
    img.save(BACKGROUND_PATH)
    return BACKGROUND_PATH


def generate_safe_qr() -> dict[str, Path]:
    qr = segno.make(PAYLOAD_URL, error="h")
    png_path = OUTPUT_DIR / "safe_qr.png"
    svg_path = OUTPUT_DIR / "safe_qr.svg"
    qr.save(png_path, scale=12, dark=BRAND_DARK, light=WHITE)
    qr.save(svg_path, scale=12, dark=BRAND_DARK, light=WHITE)
    return {"png": png_path, "svg": svg_path}


def generate_branded_qr() -> dict[str, Path]:
    qr = segno.make(PAYLOAD_URL, error="h")
    png_path = OUTPUT_DIR / "branded_qr.png"
    svg_path = OUTPUT_DIR / "branded_qr.svg"

    qr.save(
        png_path,
        scale=12,
        dark=BRAND_DARK,
        light=WHITE,
        finder_dark=BRAND_DARK,
        finder_light=WHITE,
    )
    qr.save(svg_path, scale=12, dark=BRAND_DARK, light=WHITE)

    logo_path = ensure_logo()
    qr_img = Image.open(png_path).convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")
    target_size = max(80, qr_img.width // 4)
    logo = logo.resize((target_size, target_size), Image.Resampling.LANCZOS)

    badge = Image.new("RGBA", (target_size + 20, target_size + 20), (255, 255, 255, 0))
    bdraw = ImageDraw.Draw(badge)
    bdraw.ellipse((0, 0, badge.width - 1, badge.height - 1), fill=(255, 255, 255, 245), outline=(15, 95, 47, 255), width=4)
    badge.paste(logo, (10, 10), logo)

    x = (qr_img.width - badge.width) // 2
    y = (qr_img.height - badge.height) // 2
    qr_img.paste(badge, (x, y), badge)
    qr_img.save(png_path)
    return {"png": png_path, "svg": svg_path}


def generate_aggressive_qr() -> dict[str, Path]:
    qr = segno.make(PAYLOAD_URL, error="h")
    png_path = OUTPUT_DIR / "aggressive_qr.png"
    background = ensure_background()
    qr.to_artistic(
        background=str(background),
        target=str(png_path),
        scale=8,
    )
    return {"png": png_path}


def make_contact_sheet(paths: list[Path]) -> Path:
    images = [Image.open(p).convert("RGB") for p in paths]
    thumb_size = 420
    card_w = 520
    card_h = 560
    sheet = Image.new("RGB", (card_w * len(images), card_h), color=(245, 247, 246))
    labels = ["SAFE", "BRANDED", "AGGRESSIVE"]
    draw = ImageDraw.Draw(sheet)

    for idx, image in enumerate(images):
        image.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
        x = idx * card_w + (card_w - image.width) // 2
        y = 90
        sheet.paste(image, (x, y))
        draw.text((idx * card_w + 32, 32), labels[idx], fill=(15, 40, 30))

    out = OUTPUT_DIR / "contact_sheet.png"
    sheet.save(out)
    return out


def write_readme() -> Path:
    readme = OUTPUT_DIR / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Phase 176 QR Demos",
                "",
                "Generated variants:",
                "- `safe_qr.png` / `safe_qr.svg`: production-leaning, high reliability (error correction H), minimal branding.",
                "- `branded_qr.png` / `branded_qr.svg`: balanced visual branding with center badge/logo.",
                "- `aggressive_qr.png`: artistic concept style for pitch decks and mockups.",
                "- `contact_sheet.png`: side-by-side visual comparison.",
                "",
                "## Scan Reliability Guidance",
                "- **safe**: production candidate.",
                "- **branded**: pilot/demo candidate with field testing.",
                "- **aggressive**: concept/pitch visual unless thoroughly field-tested.",
            ]
        ),
        encoding="utf-8",
    )
    return readme


def verify_outputs(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"Output missing or empty: {path}")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            with Image.open(path) as img:
                print(f"- {path.name}: {img.format} {img.width}x{img.height}, {path.stat().st_size} bytes")
        else:
            print(f"- {path.name}: {path.stat().st_size} bytes")


def main() -> int:
    ensure_dirs()
    safe = generate_safe_qr()
    branded = generate_branded_qr()
    aggressive = generate_aggressive_qr()
    contact_sheet = make_contact_sheet([safe["png"], branded["png"], aggressive["png"]])
    readme = write_readme()

    print("Phase 176 QR demos generated:")
    output_files = [
        safe["png"],
        safe["svg"],
        branded["png"],
        branded["svg"],
        aggressive["png"],
        contact_sheet,
        readme,
    ]
    verify_outputs(output_files)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModuleNotFoundError as exc:
        print(
            "Missing dependency. Install with:\n"
            "  pip install segno qrcode-artistic pillow",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
