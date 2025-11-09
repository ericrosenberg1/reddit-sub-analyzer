import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from .cache import search_cache, summary_cache
from .phone_home import queue_phone_home

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - psycopg2 is optional until postgres is requested
    psycopg2 = None
    RealDictCursor = None


def _truthy(value: Optional[str], default: str = "false") -> bool:
    if value is None:
        value = default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


DB_TYPE = os.getenv("DB_TYPE", "sqlite").strip().lower() or "sqlite"
IS_POSTGRES = DB_TYPE == "postgres"

BASE_DIR = os.getenv("SUBSEARCH_BASE_DIR") or os.path.abspath(os.getcwd())
DATA_DIR = os.getenv("SUBSEARCH_DATA_DIR") or os.path.join(BASE_DIR, "data")
DB_PATH = os.getenv("SUBSEARCH_DB_PATH") or os.path.join(DATA_DIR, "subsearch.db")

DB_POSTGRES_HOST = os.getenv("DB_POSTGRES_HOST", "").strip()
DB_POSTGRES_PORT = os.getenv("DB_POSTGRES_PORT", "5432").strip()
DB_POSTGRES_DB = os.getenv("DB_POSTGRES_DB", "").strip()
DB_POSTGRES_USER = os.getenv("DB_POSTGRES_USER", "").strip()
DB_POSTGRES_PASSWORD = os.getenv("DB_POSTGRES_PASSWORD", "").strip()
DB_POSTGRES_SSLMODE = os.getenv("DB_POSTGRES_SSLMODE", "prefer").strip()

CONFIG_WARNINGS: List[str] = []

NAMED_PARAM_PATTERN = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")

PHONE_HOME_ENABLED = _truthy(os.getenv("PHONE_HOME", "false"))
if PHONE_HOME_ENABLED and not os.getenv("PHONE_HOME_TOKEN"):
    CONFIG_WARNINGS.append(
        "PHONE_HOME is enabled without PHONE_HOME_TOKEN; upstream sync will be anonymous."
    )


def _validate_database_settings() -> None:
    if DB_TYPE not in {"sqlite", "postgres"}:
        raise RuntimeError(
            f"DB_TYPE must be either 'sqlite' or 'postgres', not '{DB_TYPE}'."
        )
    if IS_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError(
                "psycopg2-binary is required for Postgres support but is not installed."
            )
        missing = [
            name
            for name, value in [
                ("DB_POSTGRES_HOST", DB_POSTGRES_HOST),
                ("DB_POSTGRES_DB", DB_POSTGRES_DB),
                ("DB_POSTGRES_USER", DB_POSTGRES_USER),
                ("DB_POSTGRES_PASSWORD", DB_POSTGRES_PASSWORD),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing Postgres configuration values: " + ", ".join(missing)
            )


_validate_database_settings()


class PostgresConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn
        self.total_changes = 0

    def _cursor(self):
        return self._conn.cursor(cursor_factory=RealDictCursor)

    def execute(self, sql: str, params: Optional[Dict] = None):
        prepared_sql = _prepare_sql(sql)
        cur = self._cursor()
        cur.execute(prepared_sql, params or {})
        self._update_total_changes(cur)
        return cur

    def executemany(self, sql: str, seq_of_params: Sequence[Dict]):
        prepared_sql = _prepare_sql(sql)
        cur = self._cursor()
        cur.executemany(prepared_sql, seq_of_params)
        self._update_total_changes(cur)
        return cur

    def _update_total_changes(self, cursor):
        try:
            if cursor.rowcount and cursor.rowcount > 0:
                self.total_changes += cursor.rowcount
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


def _prepare_sql(sql: str) -> str:
    if not IS_POSTGRES or not sql:
        return sql
    return NAMED_PARAM_PATTERN.sub(lambda match: f"%({match.group(1)})s", sql)


def _connect_sqlite() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        timeout=30,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _connect_postgres() -> PostgresConnectionWrapper:
    conn = psycopg2.connect(
        host=DB_POSTGRES_HOST,
        port=DB_POSTGRES_PORT,
        user=DB_POSTGRES_USER,
        password=DB_POSTGRES_PASSWORD,
        dbname=DB_POSTGRES_DB,
        cursor_factory=RealDictCursor,
        sslmode=DB_POSTGRES_SSLMODE,
    )
    conn.autocommit = False
    return PostgresConnectionWrapper(conn)


def _connect():
    if IS_POSTGRES:
        return _connect_postgres()
    return _connect_sqlite()


@contextmanager
def db_conn():
    conn = _connect()
    try:
        yield conn
        if hasattr(conn, "commit"):
            conn.commit()
    except Exception:
        if hasattr(conn, "rollback"):
            conn.rollback()
        raise
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _clean_text(value: Optional[str], *, limit: int = 255) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return text[:limit]


def get_config_warnings() -> List[str]:
    return list(CONFIG_WARNINGS)


def init_db() -> None:
    if IS_POSTGRES:
        _init_postgres()
    else:
        _init_sqlite()


def _init_sqlite():
    statements = [
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
        """,
        """
        CREATE TABLE IF NOT EXISTS subreddits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name_prefixed TEXT,
            title TEXT,
            public_description TEXT,
            url TEXT,
            subscribers INTEGER,
            is_unmoderated INTEGER NOT NULL DEFAULT 0,
            is_nsfw INTEGER NOT NULL DEFAULT 0,
            last_activity_utc INTEGER,
            last_mod_activity_utc INTEGER,
            mod_count INTEGER,
            last_seen_run_id INTEGER,
            last_keyword TEXT,
            source TEXT,
            first_seen_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(last_seen_run_id) REFERENCES query_runs(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS volunteer_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            reddit_username TEXT,
            location TEXT,
            system_details TEXT,
            availability TEXT,
            bandwidth_notes TEXT,
            notes TEXT,
            health_status TEXT NOT NULL DEFAULT 'pending',
            last_check_in_at TEXT,
            broken_since TEXT,
            manage_token TEXT UNIQUE NOT NULL,
            manage_token_sent_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_subreddits_subscribers ON subreddits(subscribers DESC)",
        "CREATE INDEX IF NOT EXISTS idx_subreddits_updated_at ON subreddits(updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_subreddits_unmod ON subreddits(is_unmoderated, subscribers DESC)",
        "CREATE INDEX IF NOT EXISTS idx_nodes_health ON volunteer_nodes(health_status, updated_at DESC)",
    ]
    with db_conn() as conn:
        for stmt in statements:
            conn.execute(stmt)
        conn.execute("PRAGMA journal_mode = WAL;")


def _init_postgres():
    statements = [
        """
        CREATE TABLE IF NOT EXISTS query_runs (
            id SERIAL PRIMARY KEY,
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
        """,
        """
        CREATE TABLE IF NOT EXISTS subreddits (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            display_name_prefixed TEXT,
            title TEXT,
            public_description TEXT,
            url TEXT,
            subscribers INTEGER,
            is_unmoderated INTEGER NOT NULL DEFAULT 0,
            is_nsfw INTEGER NOT NULL DEFAULT 0,
            last_activity_utc BIGINT,
            last_mod_activity_utc BIGINT,
            mod_count INTEGER,
            last_seen_run_id INTEGER REFERENCES query_runs(id) ON DELETE SET NULL,
            last_keyword TEXT,
            source TEXT,
            first_seen_at TEXT,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS volunteer_nodes (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            reddit_username TEXT,
            location TEXT,
            system_details TEXT,
            availability TEXT,
            bandwidth_notes TEXT,
            notes TEXT,
            health_status TEXT NOT NULL DEFAULT 'pending',
            last_check_in_at TEXT,
            broken_since TEXT,
            manage_token TEXT UNIQUE NOT NULL,
            manage_token_sent_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_subreddits_subscribers ON subreddits(subscribers)",
        "CREATE INDEX IF NOT EXISTS idx_subreddits_updated_at ON subreddits(updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_subreddits_unmod ON subreddits(is_unmoderated, subscribers)",
        "CREATE INDEX IF NOT EXISTS idx_nodes_health ON volunteer_nodes(health_status, updated_at)",
    ]
    with db_conn() as conn:
        for stmt in statements:
            conn.execute(stmt)


def record_run_start(job_id: str, params: Dict, source: str = "manual") -> None:
    data = {
        "job_id": job_id,
        "source": (source or "manual")[:64],
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
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO query_runs
            (job_id, source, started_at, keyword, limit_value, unmoderated_only,
             exclude_nsfw, min_subscribers, activity_mode, activity_threshold_utc, file_name)
            VALUES
            (:job_id, :source, :started_at, :keyword, :limit_value, :unmoderated_only,
             :exclude_nsfw, :min_subscribers, :activity_mode, :activity_threshold_utc, :file_name)
            ON CONFLICT(job_id) DO UPDATE SET
                source = EXCLUDED.source,
                started_at = EXCLUDED.started_at,
                keyword = EXCLUDED.keyword,
                limit_value = EXCLUDED.limit_value,
                unmoderated_only = EXCLUDED.unmoderated_only,
                exclude_nsfw = EXCLUDED.exclude_nsfw,
                min_subscribers = EXCLUDED.min_subscribers,
                activity_mode = EXCLUDED.activity_mode,
                activity_threshold_utc = EXCLUDED.activity_threshold_utc,
                file_name = EXCLUDED.file_name
            """,
            data,
        )
    summary_cache.invalidate()


def record_run_complete(job_id: str, result_count: int, error: Optional[str] = None) -> None:
    completed_at = _now_iso()
    duration_ms: Optional[int] = None
    with db_conn() as conn:
        row = conn.execute(
            "SELECT started_at FROM query_runs WHERE job_id = :job_id",
            {"job_id": job_id},
        ).fetchone()
        if row and row.get("started_at"):
            try:
                started = datetime.fromisoformat(row["started_at"])
                duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        conn.execute(
            """
            UPDATE query_runs
            SET completed_at = :completed_at,
                result_count = :result_count,
                error = :error,
                duration_ms = :duration_ms
            WHERE job_id = :job_id
            """,
            {
                "completed_at": completed_at,
                "result_count": result_count,
                "error": error,
                "duration_ms": duration_ms,
                "job_id": job_id,
            },
        )
    summary_cache.invalidate()


def _get_run_id(conn, job_id: str) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM query_runs WHERE job_id = :job_id", {"job_id": job_id}
    ).fetchone()
    if not row:
        return None
    return row["id"]


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
    public_payload: List[Dict] = []
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
            last_mod_activity = sub.get("last_mod_activity_utc")
            try:
                last_mod_activity_val = int(last_mod_activity) if last_mod_activity is not None else None
            except (TypeError, ValueError):
                last_mod_activity_val = None
            row = {
                "name": name,
                "display_name_prefixed": sub.get("display_name_prefixed") or f"r/{name}",
                "title": sub.get("title") or name,
                "public_description": sub.get("public_description") or "",
                "url": sub.get("url"),
                "subscribers": int(sub.get("subscribers") or 0),
                "is_unmoderated": 1 if sub.get("is_unmoderated") else 0,
                "is_nsfw": 1 if sub.get("is_nsfw") else 0,
                "last_activity_utc": last_activity_val,
                "last_mod_activity_utc": last_mod_activity_val,
                "mod_count": mod_count_val,
                "run_id": run_id,
                "last_keyword": (sub.get("keyword") or keyword or "")[:128],
                "source": (sub.get("source") or source or "manual")[:64],
                "now": now,
            }
            payload.append(row)
            public_payload.append(
                {
                    "name": row["name"],
                    "display_name_prefixed": row["display_name_prefixed"],
                    "title": row["title"],
                    "subscribers": row["subscribers"],
                    "is_unmoderated": bool(row["is_unmoderated"]),
                    "is_nsfw": bool(row["is_nsfw"]),
                    "last_activity_utc": row["last_activity_utc"],
                    "last_mod_activity_utc": row["last_mod_activity_utc"],
                    "mod_count": row["mod_count"],
                    "last_keyword": row["last_keyword"],
                    "source": row["source"],
                    "updated_at": row["now"],
                }
            )
        if not payload:
            return 0
        conn.executemany(
            """
            INSERT INTO subreddits
            (name, display_name_prefixed, title, public_description, url,
             subscribers, is_unmoderated, is_nsfw, last_activity_utc,
             last_mod_activity_utc, mod_count, last_seen_run_id, last_keyword,
             source, first_seen_at, updated_at)
            VALUES
            (:name, :display_name_prefixed, :title, :public_description, :url,
             :subscribers, :is_unmoderated, :is_nsfw, :last_activity_utc,
             :last_mod_activity_utc, :mod_count, :run_id, :last_keyword,
             :source, :now, :now)
            ON CONFLICT(name) DO UPDATE SET
                display_name_prefixed = COALESCE(
                    NULLIF(EXCLUDED.display_name_prefixed, ''),
                    subreddits.display_name_prefixed
                ),
                title = CASE
                    WHEN EXCLUDED.title IS NOT NULL AND EXCLUDED.title != '' THEN EXCLUDED.title
                    ELSE subreddits.title
                END,
                public_description = CASE
                    WHEN EXCLUDED.public_description IS NOT NULL THEN EXCLUDED.public_description
                    ELSE subreddits.public_description
                END,
                url = EXCLUDED.url,
                subscribers = CASE
                    WHEN EXCLUDED.subscribers IS NOT NULL THEN EXCLUDED.subscribers
                    ELSE subreddits.subscribers
                END,
                is_unmoderated = CASE
                    WHEN EXCLUDED.is_unmoderated > subreddits.is_unmoderated THEN EXCLUDED.is_unmoderated
                    ELSE subreddits.is_unmoderated
                END,
                is_nsfw = EXCLUDED.is_nsfw,
                last_activity_utc = COALESCE(EXCLUDED.last_activity_utc, subreddits.last_activity_utc),
                last_mod_activity_utc = COALESCE(EXCLUDED.last_mod_activity_utc, subreddits.last_mod_activity_utc),
                mod_count = COALESCE(EXCLUDED.mod_count, subreddits.mod_count),
                last_seen_run_id = EXCLUDED.last_seen_run_id,
                last_keyword = CASE
                    WHEN EXCLUDED.last_keyword != '' THEN EXCLUDED.last_keyword
                    ELSE subreddits.last_keyword
                END,
                source = EXCLUDED.source,
                updated_at = EXCLUDED.updated_at
            """,
            payload,
        )
        saved = getattr(conn, "total_changes", len(payload))
    summary_cache.invalidate()
    search_cache.invalidate()
    if saved:
        queue_phone_home(public_payload)
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
            LIMIT :limit
            """,
            {"limit": limit},
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
    name_sort = "LOWER(name)" if IS_POSTGRES else "name COLLATE NOCASE"
    title_sort = "LOWER(title)" if IS_POSTGRES else "title COLLATE NOCASE"
    sort_map = {
        "name": name_sort,
        "title": title_sort,
        "subscribers": "subscribers",
        "updated_at": "updated_at",
        "first_seen_at": "first_seen_at",
        "mod_count": "COALESCE(mod_count, 0)",
        "mod_activity": "last_mod_activity_utc",
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
    params: Dict = {}
    if q:
        comparator = "ILIKE" if IS_POSTGRES else "LIKE"
        conditions.append(f"name {comparator} :name_like")
        params["name_like"] = f"%{q}%"
    if is_unmoderated is not None:
        conditions.append("is_unmoderated = :is_unmoderated")
        params["is_unmoderated"] = 1 if is_unmoderated else 0
    if nsfw is not None:
        conditions.append("is_nsfw = :is_nsfw")
        params["is_nsfw"] = 1 if nsfw else 0
    if min_subs is not None:
        conditions.append("subscribers >= :min_subs")
        params["min_subs"] = min_subs
    if max_subs is not None:
        conditions.append("subscribers <= :max_subs")
        params["max_subs"] = max_subs

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = max(page - 1, 0) * page_size
    count_params = dict(params)
    params_with_paging = dict(params)
    params_with_paging.update({"limit": page_size, "offset": offset})

    with db_conn() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM subreddits {where_clause}",
            count_params,
        ).fetchone()
        total = total_row["c"] if total_row else 0
        rows = conn.execute(
            f"""
            SELECT name, display_name_prefixed, title, public_description,
                   url, subscribers, is_unmoderated, is_nsfw,
                   last_activity_utc, last_mod_activity_utc,
                   mod_count, source, first_seen_at, updated_at
            FROM subreddits
            {where_clause}
            ORDER BY {sort_column} {order_dir}
            LIMIT :limit OFFSET :offset
            """,
            params_with_paging,
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
    if IS_POSTGRES:
        return f"postgresql://{DB_POSTGRES_USER}@{DB_POSTGRES_HOST}:{DB_POSTGRES_PORT}/{DB_POSTGRES_DB}"
    return DB_PATH


def create_volunteer_node(
    *,
    email: str,
    reddit_username: str,
    location: Optional[str] = None,
    system_details: Optional[str] = None,
    availability: Optional[str] = None,
    bandwidth_notes: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    token = secrets.token_urlsafe(32)
    now = _now_iso()
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO volunteer_nodes (
                email, reddit_username, location, system_details,
                availability, bandwidth_notes, notes, health_status,
                last_check_in_at, manage_token, created_at, updated_at
            ) VALUES (
                :email, :reddit_username, :location, :system_details,
                :availability, :bandwidth_notes, :notes, 'pending',
                :last_check_in_at, :token, :created_at, :updated_at
            )
            """,
            {
                "email": _clean_text(email, limit=256),
                "reddit_username": _clean_text(reddit_username, limit=256),
                "location": _clean_text(location, limit=256),
                "system_details": _clean_text(system_details, limit=512),
                "availability": _clean_text(availability, limit=256),
                "bandwidth_notes": _clean_text(bandwidth_notes, limit=256),
                "notes": _clean_text(notes, limit=1000),
                "last_check_in_at": now,
                "token": token,
                "created_at": now,
                "updated_at": now,
            },
        )
    return token


def list_public_nodes(limit: int = 12) -> List[Dict]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT reddit_username, location, system_details, availability,
                   bandwidth_notes, notes, health_status, last_check_in_at, updated_at
            FROM volunteer_nodes
            WHERE is_deleted = 0
              AND (health_status IS NULL OR health_status != 'broken')
            ORDER BY updated_at DESC
            LIMIT :limit
            """,
            {"limit": limit},
        ).fetchall()
    return [dict(row) for row in rows]


def get_node_stats() -> Dict:
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN health_status = 'active' AND is_deleted = 0 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN health_status = 'pending' AND is_deleted = 0 THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN health_status = 'broken' AND is_deleted = 0 THEN 1 ELSE 0 END) AS broken
            FROM volunteer_nodes
            WHERE is_deleted = 0
            """
        ).fetchone()
    if not row:
        return {"total": 0, "active": 0, "pending": 0, "broken": 0}
    return {
        "total": row["total"] or 0,
        "active": row["active"] or 0,
        "pending": row["pending"] or 0,
        "broken": row["broken"] or 0,
    }


def get_node_by_token(token: str) -> Optional[Dict]:
    if not token:
        return None
    with db_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM volunteer_nodes
            WHERE manage_token = :token
              AND is_deleted = 0
            """,
            {"token": token},
        ).fetchone()
    return dict(row) if row else None


def update_volunteer_node(
    token: str,
    *,
    email: Optional[str] = None,
    reddit_username: Optional[str] = None,
    location: Optional[str] = None,
    system_details: Optional[str] = None,
    availability: Optional[str] = None,
    bandwidth_notes: Optional[str] = None,
    notes: Optional[str] = None,
    health_status: Optional[str] = None,
    broken_since: Optional[str] = None,
) -> bool:
    if not token:
        return False
    fields: List[str] = []
    params: Dict = {"token": token}
    mapping = {
        "email": email,
        "reddit_username": reddit_username,
        "location": location,
        "system_details": system_details,
        "availability": availability,
        "bandwidth_notes": bandwidth_notes,
        "notes": notes,
    }
    for column, value in mapping.items():
        if value is not None:
            limit = 1000 if column == "notes" else 512 if column == "system_details" else 256
            params[column] = _clean_text(value, limit=limit)
            fields.append(f"{column} = :{column}")
    now = _now_iso()
    params["updated_at"] = now
    params["last_check_in_at"] = now
    fields.append("updated_at = :updated_at")
    fields.append("last_check_in_at = :last_check_in_at")
    if health_status:
        params["health_status"] = health_status
        fields.append("health_status = :health_status")
    if broken_since is not None:
        params["broken_since"] = broken_since or None
        fields.append("broken_since = :broken_since")
    if not fields:
        return False
    with db_conn() as conn:
        cur = conn.execute(
            f"""
            UPDATE volunteer_nodes
            SET {', '.join(fields)}
            WHERE manage_token = :token AND is_deleted = 0
            """,
            params,
        )
        return cur.rowcount > 0 if hasattr(cur, "rowcount") else True


def delete_volunteer_node(token: str) -> bool:
    if not token:
        return False
    now = _now_iso()
    with db_conn() as conn:
        cur = conn.execute(
            """
            UPDATE volunteer_nodes
            SET is_deleted = 1,
                deleted_at = :deleted_at,
                updated_at = :updated_at
            WHERE manage_token = :token AND is_deleted = 0
            """,
            {"deleted_at": now, "updated_at": now, "token": token},
        )
        return cur.rowcount > 0 if hasattr(cur, "rowcount") else True


def mark_manage_link_sent(token: str) -> None:
    if not token:
        return
    now = _now_iso()
    with db_conn() as conn:
        conn.execute(
            """
            UPDATE volunteer_nodes
            SET manage_token_sent_at = :sent_at
            WHERE manage_token = :token AND is_deleted = 0
            """,
            {"sent_at": now, "token": token},
        )


def prune_broken_nodes(max_age_days: int = 7) -> int:
    max_age_days = max(1, int(max_age_days or 7))
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    cutoff_iso = cutoff.isoformat()
    with db_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM volunteer_nodes
            WHERE is_deleted = 0
              AND health_status = 'broken'
              AND COALESCE(broken_since, last_check_in_at, updated_at, created_at) <= :cutoff
            """,
            {"cutoff": cutoff_iso},
        )
        if hasattr(cur, "rowcount") and cur.rowcount is not None:
            return cur.rowcount
    return 0
