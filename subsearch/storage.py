import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from .cache import search_cache, summary_cache
BASE_DIR = os.getenv("SUBSEARCH_BASE_DIR") or os.path.abspath(os.getcwd())
DATA_DIR = os.getenv("SUBSEARCH_DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.getenv("SUBSEARCH_DB_PATH") or os.path.join(DATA_DIR, "subsearch.db")


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_conn():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with db_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS query_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                keyword TEXT,
                limit_value INTEGER,
                unmoderated_only INTEGER NOT NULL DEFAULT 1,
                exclude_nsfw INTEGER NOT NULL DEFAULT 0,
                min_subscribers INTEGER NOT NULL DEFAULT 0,
                activity_mode TEXT,
                activity_threshold_utc INTEGER,
                file_name TEXT,
                result_count INTEGER DEFAULT 0,
                duration_ms INTEGER,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subreddits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                url TEXT,
                subscribers INTEGER,
                is_unmoderated INTEGER NOT NULL DEFAULT 0,
                is_nsfw INTEGER NOT NULL DEFAULT 0,
                last_activity_utc INTEGER,
                mod_count INTEGER,
                last_seen_run_id INTEGER,
                last_keyword TEXT,
                source TEXT,
                first_seen_at TEXT,
                updated_at TEXT,
                FOREIGN KEY(last_seen_run_id) REFERENCES query_runs(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subreddits_subscribers ON subreddits(subscribers DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subreddits_updated_at ON subreddits(updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_subreddits_unmod ON subreddits(is_unmoderated, subscribers DESC)"
        )
        conn.commit()


def record_run_start(job_id: str, params: Dict, source: str = "manual") -> None:
    data = {
        "job_id": job_id,
        "source": source[:64],
        "started_at": _now_iso(),
        "keyword": (params.get("keyword") or "")[:128] if params else None,
        "limit_value": params.get("limit"),
        "unmoderated_only": 1 if params.get("unmoderated_only") else 0,
        "exclude_nsfw": 1 if params.get("exclude_nsfw") else 0,
        "min_subscribers": params.get("min_subs") or params.get("min_subscribers") or 0,
        "activity_mode": params.get("activity_mode"),
        "activity_threshold_utc": params.get("activity_threshold_utc"),
        "file_name": params.get("file_name"),
    }
    with db_conn() as conn, conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO query_runs
            (job_id, source, started_at, keyword, limit_value, unmoderated_only,
             exclude_nsfw, min_subscribers, activity_mode, activity_threshold_utc, file_name)
            VALUES
            (:job_id, :source, :started_at, :keyword, :limit_value, :unmoderated_only,
             :exclude_nsfw, :min_subscribers, :activity_mode, :activity_threshold_utc, :file_name)
            """,
            data,
        )
    summary_cache.invalidate()


def record_run_complete(job_id: str, result_count: int, error: Optional[str] = None) -> None:
    completed_at = _now_iso()
    duration_ms: Optional[int] = None
    with db_conn() as conn:
        row = conn.execute(
            "SELECT started_at FROM query_runs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row and row["started_at"]:
            try:
                started = datetime.fromisoformat(row["started_at"])
                duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        with conn:
            conn.execute(
                """
                UPDATE query_runs
                SET completed_at = ?, result_count = ?, error = ?, duration_ms = ?
                WHERE job_id = ?
                """,
                (completed_at, result_count, error, duration_ms, job_id),
            )
    summary_cache.invalidate()


def _get_run_id(conn: sqlite3.Connection, job_id: str) -> Optional[int]:
    row = conn.execute("SELECT id FROM query_runs WHERE job_id = ?", (job_id,)).fetchone()
    return row["id"] if row else None


def persist_subreddits(
    job_id: str,
    subreddits: Iterable[Dict],
    keyword: Optional[str] = None,
    source: Optional[str] = None,
) -> int:
    items = list(subreddits)
    if not items:
        return 0
    now = _now_iso()
    saved = 0
    with db_conn() as conn:
        run_id = _get_run_id(conn, job_id)
        if not run_id:
            return 0
        payload: List[Dict] = []
        for sub in items:
            name = (sub.get("name") or "").strip()
            if not name:
                continue
            mod_count = sub.get("mod_count")
            try:
                mod_count_val = int(mod_count) if mod_count is not None else None
            except (TypeError, ValueError):
                mod_count_val = None
            last_activity = sub.get("last_activity_utc")
            try:
                last_activity_val = int(last_activity) if last_activity is not None else None
            except (TypeError, ValueError):
                last_activity_val = None
            payload.append(
                {
                    "name": name,
                    "url": sub.get("url"),
                    "subscribers": int(sub.get("subscribers") or 0),
                    "is_unmoderated": 1 if sub.get("is_unmoderated") else 0,
                    "is_nsfw": 1 if sub.get("is_nsfw") else 0,
                    "last_activity_utc": last_activity_val,
                    "mod_count": mod_count_val,
                    "run_id": run_id,
                    "last_keyword": (sub.get("keyword") or keyword or "")[:128],
                    "source": (sub.get("source") or source or "manual")[:64],
                    "now": now,
                }
            )
        if not payload:
            return 0
        with conn:
            conn.executemany(
                """
                INSERT INTO subreddits
                (name, url, subscribers, is_unmoderated, is_nsfw, last_activity_utc,
                 mod_count, last_seen_run_id, last_keyword, source, first_seen_at, updated_at)
                VALUES
                (:name, :url, :subscribers, :is_unmoderated, :is_nsfw, :last_activity_utc,
                 :mod_count, :run_id, :last_keyword, :source, :now, :now)
                ON CONFLICT(name) DO UPDATE SET
                    url = excluded.url,
                    subscribers = CASE
                        WHEN excluded.subscribers IS NOT NULL THEN excluded.subscribers
                        ELSE subreddits.subscribers
                    END,
                    is_unmoderated = CASE
                        WHEN excluded.is_unmoderated > subreddits.is_unmoderated THEN excluded.is_unmoderated
                        ELSE subreddits.is_unmoderated
                    END,
                    is_nsfw = excluded.is_nsfw,
                    last_activity_utc = COALESCE(excluded.last_activity_utc, subreddits.last_activity_utc),
                    mod_count = COALESCE(excluded.mod_count, subreddits.mod_count),
                    last_seen_run_id = excluded.last_seen_run_id,
                    last_keyword = CASE
                        WHEN excluded.last_keyword != '' THEN excluded.last_keyword
                        ELSE subreddits.last_keyword
                    END,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
            saved = conn.total_changes
    summary_cache.invalidate()
    search_cache.invalidate()
    return saved


def get_summary_stats() -> Dict:
    cached = summary_cache.get("summary")
    if cached is not None:
        return cached
    with db_conn() as conn:
        subs = conn.execute(
            "SELECT COUNT(*) AS total, MAX(updated_at) AS last_update FROM subreddits"
        ).fetchone()
        runs = conn.execute(
            "SELECT COUNT(*) AS total_runs, MAX(started_at) AS last_run FROM query_runs"
        ).fetchone()
        result = {
            "total_subreddits": subs["total"] if subs else 0,
            "last_indexed": subs["last_update"] if subs else None,
            "total_runs": runs["total_runs"] if runs else 0,
            "last_run_started": runs["last_run"] if runs else None,
        }
    summary_cache.set("summary", result)
    return result


def fetch_recent_runs(limit: int = 5) -> List[Dict]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT job_id, source, started_at, completed_at, keyword,
                   result_count, error, limit_value
            FROM query_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def search_subreddits(
    *,
    q: Optional[str] = None,
    is_unmoderated: Optional[bool] = None,
    nsfw: Optional[bool] = None,
    min_subs: Optional[int] = None,
    max_subs: Optional[int] = None,
    sort: str = "subscribers",
    order: str = "desc",
    page: int = 1,
    page_size: int = 50,
) -> Dict:
    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    sort_map = {
        "name": "name COLLATE NOCASE",
        "subscribers": "subscribers",
        "updated_at": "updated_at",
        "first_seen_at": "first_seen_at",
    }
    sort_column = sort_map.get(sort, "subscribers")
    order_dir = "ASC" if order.lower() == "asc" else "DESC"
    cache_key = (
        "search",
        q or "",
        is_unmoderated,
        nsfw,
        min_subs,
        max_subs,
        sort_column,
        order_dir,
        page,
        page_size,
    )
    cached = search_cache.get(cache_key)
    if cached is not None:
        return cached

    conditions: List[str] = []
    params: List = []
    if q:
        conditions.append("name LIKE ?")
        params.append(f"%{q}%")
    if is_unmoderated is not None:
        conditions.append("is_unmoderated = ?")
        params.append(1 if is_unmoderated else 0)
    if nsfw is not None:
        conditions.append("is_nsfw = ?")
        params.append(1 if nsfw else 0)
    if min_subs is not None:
        conditions.append("subscribers >= ?")
        params.append(min_subs)
    if max_subs is not None:
        conditions.append("subscribers <= ?")
        params.append(max_subs)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = max(page - 1, 0) * page_size

    with db_conn() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM subreddits {where_clause}", params
        ).fetchone()
        total = total_row["c"] if total_row else 0
        rows = conn.execute(
            f"""
            SELECT name, url, subscribers, is_unmoderated, is_nsfw,
                   last_activity_utc, last_keyword, source, first_seen_at, updated_at
            FROM subreddits
            {where_clause}
            ORDER BY {sort_column} {order_dir}
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
    result = {
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": [dict(row) for row in rows],
    }
    search_cache.set(cache_key, result)
    return result


def get_database_path() -> str:
    return DB_PATH
