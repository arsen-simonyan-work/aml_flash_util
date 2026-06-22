#!/usr/bin/env python3
import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON_ROOT = ROOT / "assets" / "icons"
SOURCE_ICON = ICON_ROOT / "app-icon-source.png"
RUNTIME_ICON = ICON_ROOT / "app-icon.png"
WINDOWS_ICON = ICON_ROOT / "app-icon.ico"
MACOS_ICON = ICON_ROOT / "app-icon.icns"
LINUX_ICON_ROOT = ICON_ROOT / "hicolor"
LINUX_SIZES = [16, 24, 32, 48, 64, 128, 256, 512]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_SIZES = [
    (16, 16, 1),
    (16, 16, 2),
    (32, 32, 1),
    (32, 32, 2),
    (128, 128, 1),
    (128, 128, 2),
    (256, 256, 1),
    (256, 256, 2),
    (512, 512, 1),
    (512, 512, 2),
]
PACKAGE_NAME = "amlogic-flash-tool"
GENERATE_WINDOWS_ICON = False
GENERATE_MACOS_ICON = False
GENERATE_LINUX_ICONS = True


def make_square_image(size: int) -> Image.Image:
    with Image.open(SOURCE_ICON) as source:
        resized = source.convert("RGBA")
        resized.thumbnail((size, size), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        offset_x = (size - resized.width) // 2
        offset_y = (size - resized.height) // 2
        canvas.paste(resized, (offset_x, offset_y), resized)
        return canvas


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-icns",
        action="store_true",
        help="Fail if app-icon.icns cannot be produced or found.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not SOURCE_ICON.exists():
        raise FileNotFoundError(f"Missing source icon: {SOURCE_ICON}")

    ICON_ROOT.mkdir(parents=True, exist_ok=True)

    runtime = make_square_image(512)
    runtime.save(RUNTIME_ICON)
    if GENERATE_WINDOWS_ICON:
        runtime.save(WINDOWS_ICON, sizes=[(size, size) for size in ICO_SIZES])

    if GENERATE_MACOS_ICON:
        icns_image = make_square_image(1024)
        icns_image.save(MACOS_ICON, sizes=ICNS_SIZES)
    elif args.require_icns:
        raise RuntimeError("app-icon.icns generation is disabled for this scaffold.")

    if GENERATE_LINUX_ICONS:
        for size in LINUX_SIZES:
            output_path = LINUX_ICON_ROOT / f"{size}x{size}" / "apps" / f"{PACKAGE_NAME}.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            make_square_image(size).save(output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
