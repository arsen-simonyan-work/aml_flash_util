import sys
from pathlib import Path

APP_NAME = "Amlogic Flash Tool"
PACKAGE_NAME = "amlogic-flash-tool"
BUNDLE_ID = "com.home.amlogicflashtool"
APP_WM_CLASS = "Amlogicflashtool"


def version_file_candidates() -> list[Path]:
    candidates: list[Path] = []

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "VERSION")

    module_dir = Path(__file__).resolve().parent
    candidates.append(module_dir / "VERSION")
    candidates.append(module_dir.parent / "VERSION")

    return candidates


def read_version() -> str:
    for version_file in version_file_candidates():
        if not version_file.exists():
            continue

        version = version_file.read_text(encoding="utf-8").strip()
        if not version:
            raise ValueError(f"VERSION file is empty: {version_file}")
        return version

    searched = ", ".join(str(path) for path in version_file_candidates())
    raise FileNotFoundError(f"VERSION file not found. Looked in: {searched}")


__version__ = read_version()
