"""Utility helpers for managing and exposing Sub Search build numbers."""

from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_BUILD_FILE = Path(
    os.getenv("SUBSEARCH_BUILD_FILE") or PACKAGE_ROOT / "BUILD_NUMBER"
)


def _parse_build(value: str) -> Optional[Tuple[int, int, int]]:
    parts = value.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        year = int(parts[0])
        month = int(parts[1])
        sequence = int(parts[2])
    except (TypeError, ValueError):
        return None
    if month < 1 or month > 12 or sequence < 0:
        return None
    return year, month, sequence


def _build_string(year: int, month: int, sequence: int) -> str:
    return f"{year}.{month:02d}.{sequence}"


def _read_build_file(path: Path = DEFAULT_BUILD_FILE) -> Optional[str]:
    try:
        data = path.read_text(encoding="utf-8").strip()
        return data or None
    except FileNotFoundError:
        return None


def bump_build_number(now: Optional[datetime] = None, path: Path = DEFAULT_BUILD_FILE) -> str:
    """Increment and persist the build number."""
    now = now or datetime.utcnow()
    current = _parse_build(_read_build_file(path) or "")
    if current and current[0] == now.year and current[1] == now.month:
        sequence = current[2] + 1
    else:
        sequence = 1
    build_str = _build_string(now.year, now.month, sequence)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_str + "\n", encoding="utf-8")
    _get_current_build_number.cache_clear()
    return build_str


@lru_cache()
def _get_current_build_number(path: Path = DEFAULT_BUILD_FILE) -> Optional[str]:
    raw = _read_build_file(path)
    if raw and _parse_build(raw):
        return raw
    return None


def get_current_build_number(default: str = "dev") -> str:
    """Return the current build number, falling back to `default` when unset."""
    return _get_current_build_number() or default


if __name__ == "__main__":
    print(bump_build_number())
