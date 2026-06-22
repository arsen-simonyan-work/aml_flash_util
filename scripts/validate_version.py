#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from version import read_version

NUMERIC_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")


def normalize_tag(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def main() -> int:
    version = read_version()

    if not NUMERIC_VERSION_RE.fullmatch(version):
        print(
            "VERSION must be numeric and use 3 or 4 dot-separated parts, "
            f"got: {version}",
            file=sys.stderr,
        )
        return 1

    tag = os.getenv("GITHUB_REF_NAME")
    if tag:
        normalized_tag = normalize_tag(tag)
        if normalized_tag != version:
            print(
                f"Tag {tag} does not match VERSION {version}",
                file=sys.stderr,
            )
            return 1

    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
