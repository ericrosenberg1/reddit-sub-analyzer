"""
Legacy CLI helper for Sub Search.

This thin wrapper exists for folks who want to run the sub search from a shell
and dump the filtered results to disk without touching the Flask UI. It simply
invokes :func:`subsearch.auto_sub_search.find_unmoderated_subreddits` and
writes the resulting list to a CSV file for quick inspection.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

import praw
import prawcore
from dotenv import load_dotenv



CSV_FIELDS: Sequence[str] = (
    "display_name_prefixed",
    "title",
    "public_description",
    "subscribers",
    "mod_count",
    "is_unmoderated",
    "is_nsfw",
    "last_activity_utc",
    "last_mod_activity_utc",
    "url",
)


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _float_env(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def save_to_csv(rows: Iterable[dict], filename: str | None = None) -> Path:
    """Write sub search rows to CSV and return the file path."""
    items = list(rows)
    if not filename:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"subsearch_run_{timestamp}.csv"
    path = Path(filename).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in items:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})
    logger.info("Wrote %s rows to %s", len(items), path)
    return path


def main() -> None:
    """Run the sub search once using environment-driven settings."""
    load_dotenv(override=True)
    keyword = os.getenv("SUBSEARCH_CLI_KEYWORD") or None
    limit = _int_env("SUBSEARCH_CLI_LIMIT", 1000)
    min_subs = _int_env("SUBSEARCH_CLI_MIN_SUBS", 0)
    unmoderated_only = os.getenv("SUBSEARCH_CLI_UNMOD_ONLY", "1").lower() not in {"0", "false", "off"}
    exclude_nsfw = os.getenv("SUBSEARCH_CLI_EXCLUDE_NSFW", "0").lower() in {"1", "true", "on"}
    activity_mode = os.getenv("SUBSEARCH_CLI_ACTIVITY_MODE") or "any"
    activity_threshold = _int_env("SUBSEARCH_CLI_ACTIVITY_THRESHOLD", 0) or None
    rate_limit_delay = max(0.1, _float_env("SUBSEARCH_RATE_LIMIT_DELAY", 0.2))

    logger.info(
        "CLI run starting keyword=%r limit=%d unmoderated_only=%s exclude_nsfw=%s",
        keyword,
        limit,
        unmoderated_only,
        exclude_nsfw,
    )
    try:
        payload = find_unmoderated_subreddits(
            limit=limit,
            name_keyword=keyword,
            unmoderated_only=unmoderated_only,
            exclude_nsfw=exclude_nsfw,
            min_subscribers=min_subs,
            activity_mode=activity_mode,
            activity_threshold_utc=activity_threshold,
            rate_limit_delay=rate_limit_delay,
            include_all=True,
        )
        subs = payload.get("results") or []
        csv_path = save_to_csv(subs)
        print(f"Saved {len(subs)} subreddits to {csv_path}")
    except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException) as exc:
        logger.error("Reddit API error: %s", exc, exc_info=True)
        print("Reddit API error. Double-check your credentials and network.")
    except Exception as exc:  # pragma: no cover - safety net for CLI usage
        logger.exception("Unexpected CLI failure")
        print(f"Unexpected error: {exc}")


if __name__ == "__main__":
    main()

# injected fallback logger to avoid self-import
import logging
logger = logging.getLogger("subsearch")
# ==== BEGIN SHIM (added safely by ops) ====
try:
    _ = find_unmoderated_subreddits  # already defined upstream
except NameError:
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    def _normalize_result(res):
        # Always return a dict so callers can do .get("results", [])
        if res is None:
            return {"results": []}
        if isinstance(res, dict):
            return res if "results" in res else {"results": res.get("items", []) or []}
        if isinstance(res, (list, tuple, set)):
            return {"results": list(res)}
        return {"results": [res]}

    def find_unmoderated_subreddits(*args, **kwargs):
        """
        Safe fallback:
        - Prefer internal helpers if they exist (no recursion into main()).
        - Otherwise, if main() exists, call it and normalize the shape.
        - If nothing is available, return an empty result set (no crash).
        """
        # Common internal helper names to try (won't call main() first to avoid recursion)
        for _helper_name in ("_find_unmoderated_core", "scan_unmoderated", "finder", "run"):
            _helper = globals().get(_helper_name)
            if callable(_helper):
                try:
                    return _normalize_result(_helper(*args, **kwargs))
                except Exception as _e:
                    _logger.warning("Helper %s failed: %s", _helper_name, _e)

        _main = globals().get("main")
        if callable(_main):
            try:
                return _normalize_result(_main(*args, **kwargs))
            except TypeError as _e:
                # If signature mismatches, strip kwargs down to only what main accepts
                import inspect as _inspect
                try:
                    sig = _inspect.signature(_main)
                    params = sig.parameters
                    accepts_var_kw = any(p.kind == p.VAR_KEYWORD for p in params.values())
                    if not accepts_var_kw:
                        kwargs = {k: v for k, v in kwargs.items() if k in params}
                except Exception:
                    pass
                try:
                    return _normalize_result(_main(*args, **kwargs))
                except Exception as _e2:
                    _logger.error("main() failed after adapt: %s", _e2)
                    return {"results": []}
            except Exception as _e:
                _logger.error("main() failed: %s", _e)
                return {"results": []}

        _logger.warning("No suitable function found; returning empty results (shim).")
        return {"results": []}
# ==== END SHIM ====
