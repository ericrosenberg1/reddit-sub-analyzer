from typing import Iterable, List, Dict
import time, re

def _local_match(q: str, s: str) -> bool:
    q = (q or "").strip().lower()
    return q in (s or "").lower()

def _tokenize(q: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", q or "") if t]

def broadened_subreddit_search(
    reddit,
    query: str,
    limit: int = 500,
    delay: float = 0.3,
    include_over_18: bool = True,
    breadth: int = 3,
    popular_sip: int = 300,
) -> Iterable[Dict]:
    seen = set()
    q_tokens = _tokenize(query)

    def dedupe_push(sr):
        key = getattr(sr, "display_name", None) or getattr(sr, "id", None)
        if not key or key in seen:
            return False
        seen.add(key)
        return True

    try:
        for sr in reddit.subreddits.search(query, limit=limit):
            if dedupe_push(sr):
                yield sr
                time.sleep(delay)
    except Exception:
        pass

    if breadth < 2:
        return

    try:
        for sr in reddit.subreddits.search_by_name(query, exact=False):
            if dedupe_push(sr):
                yield sr
                time.sleep(delay)
    except Exception:
        pass

    if breadth < 3:
        return

    for tok in q_tokens:
        try:
            for sr in reddit.subreddits.search(tok, limit=max(100, limit // 3)):
                if dedupe_push(sr):
                    yield sr
                    time.sleep(delay)
        except Exception:
            continue

    def _maybe(sr):
        try:
            name = getattr(sr, "display_name", "") or ""
            title = getattr(sr, "title", "") or ""
            desc = getattr(sr, "public_description", "") or ""
            blob = f"{name} {title} {desc}"
        except Exception:
            return False
        if _local_match(query, blob):
            return True
        for tok in q_tokens:
            if _local_match(tok, blob):
                return True
        return False

    def _sip(gen, n):
        c = 0
        for sr in gen:
            if c >= n:
                break
            if dedupe_push(sr) and _maybe(sr):
                yield sr
                c += 1

    try:
        for sr in _sip(reddit.subreddits.popular(limit=popular_sip), popular_sip):
            yield sr
            time.sleep(delay)
    except Exception:
        pass

    try:
        for sr in _sip(reddit.subreddits.new(limit=popular_sip), popular_sip // 2):
            yield sr
            time.sleep(delay)
    except Exception:
        pass
