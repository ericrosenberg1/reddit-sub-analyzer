"""
Broadened subreddit search using multiple Reddit API strategies.

This module provides a generator that combines several search methods
to find subreddits matching a query, with deduplication.

Rate limiting is handled by PRAW automatically (100 req/min for OAuth).
We remove manual delays to maximize throughput while staying within limits.
"""

import logging
import re
import time
from typing import Iterable, List, Set

import prawcore

logger = logging.getLogger(__name__)

# Batch size for yielding results (reduces callback overhead)
YIELD_BATCH_SIZE = 10


def _local_match(query: str, text: str) -> bool:
    """Check if query appears in text (case-insensitive)."""
    query = (query or "").strip().lower()
    return query in (text or "").lower()


def _tokenize(query: str) -> List[str]:
    """Split query into alphanumeric tokens."""
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", query or "") if t]


def _safe_iterate(gen, logger_msg: str = "API iteration"):
    """Safely iterate over a PRAW generator, handling rate limits and errors."""
    try:
        for item in gen:
            yield item
    except prawcore.exceptions.RequestException as e:
        logger.warning("Reddit API request failed in %s: %s", logger_msg, e)
    except prawcore.exceptions.ResponseException as e:
        if hasattr(e, 'response') and e.response is not None:
            status = getattr(e.response, 'status_code', 'unknown')
            if status == 429:
                logger.info("Rate limited in %s, PRAW will handle retry", logger_msg)
            else:
                logger.warning("Reddit API response error (%s) in %s: %s", status, logger_msg, e)
        else:
            logger.warning("Reddit API response error in %s: %s", logger_msg, e)
    except Exception as e:
        logger.debug("Unexpected error in %s: %s", logger_msg, e, exc_info=True)


def broadened_subreddit_search(
    reddit,
    query: str,
    limit: int = 500,
    delay: float = 0.0,  # Deprecated - PRAW handles rate limiting
    include_over_18: bool = True,
    breadth: int = 3,
    popular_sip: int = 500,
) -> Iterable:
    """
    Search for subreddits using multiple strategies with deduplication.

    Optimized for maximum throughput while respecting Reddit's rate limits.
    PRAW handles rate limiting automatically (100 req/min for OAuth).

    Args:
        reddit: PRAW Reddit instance
        query: Search query string
        limit: Maximum results from primary search
        delay: Deprecated, ignored (PRAW handles rate limiting)
        include_over_18: Include NSFW subreddits
        breadth: Search depth (1-5, higher = more thorough)
        popular_sip: Max subreddits to sample from popular/new/default

    Yields:
        Subreddit objects matching the query
    """
    seen: Set[str] = set()
    q_tokens = _tokenize(query)
    q_lower = query.lower().strip() if query else ""
    yielded_count = 0

    def dedupe_push(sr) -> bool:
        """Add subreddit to seen set if not already present."""
        key = getattr(sr, "display_name", None) or getattr(sr, "id", None)
        if not key:
            return False
        key_lower = key.lower()
        if key_lower in seen:
            return False
        seen.add(key_lower)
        return True

    # Strategy 1: Primary subreddit search (most relevant)
    logger.debug("Strategy 1: Primary search for '%s' (limit=%d)", query, limit)
    for sr in _safe_iterate(reddit.subreddits.search(query, limit=limit), "primary search"):
        if dedupe_push(sr):
            yield sr
            yielded_count += 1

    logger.debug("After primary search: %d unique subreddits", yielded_count)

    if breadth < 2:
        return

    # Strategy 2: Search by name (partial matching) - very effective for discovery
    logger.debug("Strategy 2: Name search for '%s'", query)
    for sr in _safe_iterate(reddit.subreddits.search_by_name(query, exact=False), "name search"):
        if dedupe_push(sr):
            yield sr
            yielded_count += 1

    # Also try with underscores/no spaces for compound queries
    if ' ' in query or '_' in query:
        alt_query = query.replace(' ', '_') if ' ' in query else query.replace('_', ' ')
        for sr in _safe_iterate(reddit.subreddits.search_by_name(alt_query, exact=False), "alt name search"):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    if breadth < 3:
        return

    # Strategy 3: Search by individual tokens (catches partial matches)
    logger.debug("Strategy 3: Token search for %s", q_tokens)
    for tok in q_tokens:
        if len(tok) < 2:
            continue  # Skip single-char tokens
        tok_limit = max(200, limit // 2)
        for sr in _safe_iterate(reddit.subreddits.search(tok, limit=tok_limit), f"token search '{tok}'"):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    # Strategy 4: Search with common suffixes/prefixes
    common_patterns = [
        f"{query}s", f"{query}ing", f"the{query}", f"{query}hub",
        f"r{query}", f"{query}memes", f"ask{query}",
    ]
    for pattern in common_patterns:
        for sr in _safe_iterate(reddit.subreddits.search_by_name(pattern, exact=False), f"pattern search '{pattern}'"):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    if breadth < 4:
        return

    def _maybe(sr) -> bool:
        """Check if subreddit might match query via local text matching."""
        try:
            name = getattr(sr, "display_name", "") or ""
            title = getattr(sr, "title", "") or ""
            desc = getattr(sr, "public_description", "") or ""
            blob = f"{name} {title} {desc}".lower()
        except AttributeError:
            return False
        if q_lower and q_lower in blob:
            return True
        return any(tok.lower() in blob for tok in q_tokens if len(tok) >= 2)

    def _sip(gen, n: int, source: str):
        """Sample up to n matching subreddits from generator."""
        count = 0
        for sr in _safe_iterate(gen, source):
            if count >= n:
                break
            if dedupe_push(sr) and _maybe(sr):
                yield sr
                count += 1

    # Strategy 5: Sample from popular subreddits (high-quality matches)
    logger.debug("Strategy 5: Popular subreddit sampling (limit=%d)", popular_sip)
    for sr in _sip(reddit.subreddits.popular(limit=popular_sip), popular_sip // 2, "popular"):
        yield sr
        yielded_count += 1

    if breadth < 5:
        return

    # Strategy 6: Sample from new subreddits (catches emerging communities)
    logger.debug("Strategy 6: New subreddit sampling (limit=%d)", popular_sip)
    for sr in _sip(reddit.subreddits.new(limit=popular_sip), popular_sip // 3, "new"):
        yield sr
        yielded_count += 1

    # Strategy 7: Default subreddits (high-visibility communities)
    logger.debug("Strategy 7: Default subreddit sampling")
    try:
        for sr in _sip(reddit.subreddits.default(limit=100), 50, "default"):
            yield sr
            yielded_count += 1
    except Exception:
        pass  # Some Reddit instances may not support this

    logger.info("Broadened search complete: %d unique subreddits for query '%s'", yielded_count, query)
