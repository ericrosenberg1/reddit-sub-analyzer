"""
Broadened subreddit search using multiple Reddit API strategies.

This module provides a generator that combines several search methods
to find subreddits matching a query, with deduplication and rate limiting.
"""

import logging
import re
import time
from typing import Dict, Iterable, List

import prawcore

logger = logging.getLogger(__name__)


def _local_match(query: str, text: str) -> bool:
    """Check if query appears in text (case-insensitive)."""
    query = (query or "").strip().lower()
    return query in (text or "").lower()


def _tokenize(query: str) -> List[str]:
    """Split query into alphanumeric tokens."""
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", query or "") if t]


def broadened_subreddit_search(
    reddit,
    query: str,
    limit: int = 500,
    delay: float = 0.3,
    include_over_18: bool = True,
    breadth: int = 3,
    popular_sip: int = 300,
) -> Iterable[Dict]:
    """
    Search for subreddits using multiple strategies with deduplication.

    Args:
        reddit: PRAW Reddit instance
        query: Search query string
        limit: Maximum results from primary search
        delay: Delay between API calls (rate limiting)
        include_over_18: Include NSFW subreddits
        breadth: Search depth (1-3, higher = more thorough)
        popular_sip: Max subreddits to sample from popular/new

    Yields:
        Subreddit objects matching the query
    """
    seen: set = set()
    q_tokens = _tokenize(query)

    def dedupe_push(sr) -> bool:
        """Add subreddit to seen set if not already present."""
        key = getattr(sr, "display_name", None) or getattr(sr, "id", None)
        if not key or key in seen:
            return False
        seen.add(key)
        return True

    # Strategy 1: Primary subreddit search
    try:
        for sr in reddit.subreddits.search(query, limit=limit):
            if dedupe_push(sr):
                yield sr
                time.sleep(delay)
    except prawcore.exceptions.RequestException as e:
        logger.warning("Reddit API request failed in primary search: %s", e)
    except prawcore.exceptions.ResponseException as e:
        logger.warning("Reddit API response error in primary search: %s", e)

    if breadth < 2:
        return

    # Strategy 2: Search by name (partial matching)
    try:
        for sr in reddit.subreddits.search_by_name(query, exact=False):
            if dedupe_push(sr):
                yield sr
                time.sleep(delay)
    except prawcore.exceptions.RequestException as e:
        logger.warning("Reddit API request failed in name search: %s", e)
    except prawcore.exceptions.ResponseException as e:
        logger.warning("Reddit API response error in name search: %s", e)

    if breadth < 3:
        return

    # Strategy 3: Search by individual tokens
    for tok in q_tokens:
        try:
            for sr in reddit.subreddits.search(tok, limit=max(100, limit // 3)):
                if dedupe_push(sr):
                    yield sr
                    time.sleep(delay)
        except prawcore.exceptions.RequestException as e:
            logger.debug("Token search failed for '%s': %s", tok, e)
            continue
        except prawcore.exceptions.ResponseException as e:
            logger.debug("Token search response error for '%s': %s", tok, e)
            continue

    def _maybe(sr) -> bool:
        """Check if subreddit might match query via local text matching."""
        try:
            name = getattr(sr, "display_name", "") or ""
            title = getattr(sr, "title", "") or ""
            desc = getattr(sr, "public_description", "") or ""
            blob = f"{name} {title} {desc}"
        except AttributeError:
            return False
        if _local_match(query, blob):
            return True
        return any(_local_match(tok, blob) for tok in q_tokens)

    def _sip(gen, n: int):
        """Sample up to n matching subreddits from generator."""
        count = 0
        for sr in gen:
            if count >= n:
                break
            if dedupe_push(sr) and _maybe(sr):
                yield sr
                count += 1

    # Strategy 4: Sample from popular subreddits
    try:
        for sr in _sip(reddit.subreddits.popular(limit=popular_sip), popular_sip):
            yield sr
            time.sleep(delay)
    except prawcore.exceptions.RequestException as e:
        logger.warning("Reddit API request failed in popular search: %s", e)
    except prawcore.exceptions.ResponseException as e:
        logger.warning("Reddit API response error in popular search: %s", e)

    # Strategy 5: Sample from new subreddits
    try:
        for sr in _sip(reddit.subreddits.new(limit=popular_sip), popular_sip // 2):
            yield sr
            time.sleep(delay)
    except prawcore.exceptions.RequestException as e:
        logger.warning("Reddit API request failed in new search: %s", e)
    except prawcore.exceptions.ResponseException as e:
        logger.warning("Reddit API response error in new search: %s", e)
