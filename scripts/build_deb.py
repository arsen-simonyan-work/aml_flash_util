#!/usr/bin/env python3
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from version import APP_NAME, PACKAGE_NAME, read_version

ARCHITECTURE = "amd64"
INSTALL_DIR = Path("/opt") / PACKAGE_NAME
EXECUTABLE_NAME = "AmlogicFlashTool"
ICON_NAME = PACKAGE_NAME
STARTUP_WM_CLASS = "AmlogicFlashTool"
MAINTAINER = "Home"
DESCRIPTION = "Packaged desktop application."


def write_file(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def main() -> int:
    version = read_version()
    source_dir = ROOT / "dist" / EXECUTABLE_NAME
    icon_root = ROOT / "assets" / "icons" / "hicolor"
    if not source_dir.exists():
        raise FileNotFoundError(f"Missing build output: {source_dir}")
    if not icon_root.exists():
        raise FileNotFoundError(f"Missing Linux icon set: {icon_root}")

    package_root = ROOT / "build" / "deb-package"
    output_dir = ROOT / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)

    if package_root.exists():
        shutil.rmtree(package_root)

    app_dir = package_root / INSTALL_DIR.relative_to("/")
    shutil.copytree(source_dir, app_dir)

    executable_path = app_dir / EXECUTABLE_NAME
    executable_path.chmod(0o755)

    launcher = f'#!/bin/sh\nexec {INSTALL_DIR}/{EXECUTABLE_NAME} "$@"\n'
    write_file(package_root / "usr" / "bin" / PACKAGE_NAME, launcher, 0o755)

    desktop_file = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Exec=/usr/bin/{PACKAGE_NAME}
Icon={ICON_NAME}
StartupWMClass={STARTUP_WM_CLASS}
Terminal=false
Categories=Utility;
"""
    write_file(
        package_root / "usr" / "share" / "applications" / f"{PACKAGE_NAME}.desktop",
        desktop_file,
        0o644,
    )

    for icon_file in sorted(icon_root.glob("*/apps/*.png")):
        relative_icon_path = icon_file.relative_to(ROOT / "assets" / "icons")
        destination = package_root / "usr" / "share" / "icons" / relative_icon_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon_file, destination)

    control_file = f"""Package: {PACKAGE_NAME}
Version: {version}
Section: utils
Priority: optional
Architecture: {ARCHITECTURE}
Maintainer: {MAINTAINER}
Description: {DESCRIPTION}
"""
    write_file(package_root / "DEBIAN" / "control", control_file, 0o644)

    output_file = output_dir / f"AmlogicFlashTool-{version}-linux-{ARCHITECTURE}.deb"
    subprocess.run(
        ["dpkg-deb", "--build", "--root-owner-group", str(package_root), str(output_file)],
        check=True,
    )

    print(output_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
