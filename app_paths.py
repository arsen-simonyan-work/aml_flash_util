import os
import sys
from pathlib import Path

APP_DATA_DIR_NAME = "AmlogicFlashTool"
LINUX_DATA_DIR_NAME = "amlogic-flash-tool"


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def get_resource_path(*parts: str) -> Path:
    roots: list[Path] = []

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))

    roots.append(get_app_root())
    roots.append(Path(__file__).resolve().parent)

    for root in roots:
        candidate = root.joinpath(*parts)
        if candidate.exists():
            return candidate

    return roots[0].joinpath(*parts)


def get_user_data_root() -> Path:
    if os.name == "nt":
        base_dir = Path(
            os.environ.get(
                "LOCALAPPDATA",
                Path.home() / "AppData" / "Local",
            )
        )
        return base_dir / APP_DATA_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DATA_DIR_NAME

    base_dir = Path(
        os.environ.get(
            "XDG_DATA_HOME",
            Path.home() / ".local" / "share",
        )
    )
    return base_dir / LINUX_DATA_DIR_NAME
