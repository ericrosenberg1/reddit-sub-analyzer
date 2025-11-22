#!/usr/bin/env python3
"""Ensure the build number and history track each deployment."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os

from subsearch.build_info import DEFAULT_BUILD_FILE, bump_build_number


def main() -> None:
    """Bump the build number and append the entry to the history log."""
    version = bump_build_number()
    history_path = Path(os.getenv("SUBSEARCH_VERSION_HISTORY_PATH") or DEFAULT_BUILD_FILE.parent / "VERSION_HISTORY.txt")
    history_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().isoformat()
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {version}\n")
    print(version)


if __name__ == "__main__":
    main()
