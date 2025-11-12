import sqlite3, time
def _conn(db_path='data/subsearch.db'):
    return sqlite3.connect(db_path)
def ensure_columns():
    con = _conn(); cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS subreddits (display_name TEXT PRIMARY KEY, title TEXT, subscribers INTEGER, nsfw INTEGER, created_utc REAL, included_in_report INTEGER DEFAULT 0, last_seen_at REAL)")
    con.commit(); con.close()
def upsert_subreddit(row: dict, included=False, db_path='data/subsearch.db'):
    ensure_columns()
    con = _conn(db_path); cur = con.cursor()
    cur.execute("""INSERT INTO subreddits(display_name,title,subscribers,nsfw,created_utc,included_in_report,last_seen_at)
                 VALUES (?,?,?,?,?,?,?)
                 ON CONFLICT(display_name) DO UPDATE SET
                   title=excluded.title,
                   subscribers=excluded.subscribers,
                   nsfw=excluded.nsfw,
                   created_utc=excluded.created_utc,
                   included_in_report=MAX(subreddits.included_in_report, excluded.included_in_report),
                   last_seen_at=excluded.last_seen_at
    """,(
      row.get('display_name'),
      row.get('title'),
      row.get('subscribers') or 0,
      1 if row.get('over18') or row.get('nsfw') else 0,
      row.get('created_utc') or 0.0,
      1 if included else 0,
      time.time()
    ))
    con.commit(); con.close()
