"""
Broadened subreddit search using multiple Reddit API strategies.

This module provides a generator that combines several search methods
to find subreddits matching a query, with deduplication.

Rate limiting is handled by PRAW automatically (100 req/min for OAuth).
We remove manual delays to maximize throughput while staying within limits.

Optimized for maximum discovery:
- Primary search finds most relevant matches
- Name search catches partial name matches
- Token search finds related communities
- Pattern search finds common naming conventions
- Related subreddits via sidebar/wiki links
"""

import logging
import re
from typing import Iterable, List, Set

import prawcore

logger = logging.getLogger(__name__)


def _tokenize(query: str) -> List[str]:
    """Split query into alphanumeric tokens."""
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", query or "") if t]


def _safe_iterate(gen, logger_msg: str = "API iteration", max_items: int = 0):
    """Safely iterate over a PRAW generator, handling rate limits and errors."""
    count = 0
    try:
        for item in gen:
            yield item
            count += 1
            if max_items > 0 and count >= max_items:
                break
    except prawcore.exceptions.RequestException as e:
        logger.warning("Reddit API request failed in %s: %s", logger_msg, e)
    except prawcore.exceptions.ResponseException as e:
        if hasattr(e, 'response') and e.response is not None:
            status = getattr(e.response, 'status_code', 'unknown')
            if status == 429:
                logger.info("Rate limited in %s, PRAW will handle retry", logger_msg)
            else:
                logger.warning("API error (%s) in %s: %s", status, logger_msg, e)
        else:
            logger.warning("Reddit API response error in %s: %s", logger_msg, e)
    except (StopIteration, GeneratorExit):
        pass
    except Exception as e:  # noqa: BLE001
        logger.debug("Unexpected error in %s: %s", logger_msg, e, exc_info=True)


def broadened_subreddit_search(
    reddit,
    query: str,
    limit: int = 500,
    breadth: int = 5,
    **kwargs,  # Accept deprecated args for compatibility
) -> Iterable:
    """
    Search for subreddits using multiple strategies with deduplication.

    Optimized for maximum discovery while respecting Reddit's rate limits.
    PRAW handles rate limiting automatically (100 req/min for OAuth).

    Strategies:
    1. Primary search - most relevant keyword matches
    2. Name search - partial subreddit name matches
    3. Token search - each word searched separately
    4. Pattern search - common prefix/suffix patterns
    5. Related search - synonyms and related terms
    6. Expanded pattern search - more naming conventions

    Args:
        reddit: PRAW Reddit instance
        query: Search query string
        limit: Maximum results from primary search
        breadth: Search depth (1-6, higher = more thorough)

    Yields:
        Subreddit objects matching the query
    """
    seen: Set[str] = set()
    q_tokens = _tokenize(query)
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
    for sr in _safe_iterate(
        reddit.subreddits.search(query, limit=limit), "primary search"
    ):
        if dedupe_push(sr):
            yield sr
            yielded_count += 1

    logger.debug("After primary search: %d unique subreddits", yielded_count)

    if breadth < 2:
        return

    # Strategy 2: Search by name (partial matching) - very effective
    logger.debug("Strategy 2: Name search for '%s'", query)
    for sr in _safe_iterate(
        reddit.subreddits.search_by_name(query, exact=False), "name search"
    ):
        if dedupe_push(sr):
            yield sr
            yielded_count += 1

    # Also try with underscores/no spaces for compound queries
    if ' ' in query or '_' in query:
        alt = query.replace(' ', '_') if ' ' in query else query.replace('_', ' ')
        for sr in _safe_iterate(
            reddit.subreddits.search_by_name(alt, exact=False), "alt name search"
        ):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    if breadth < 3:
        return

    # Strategy 3: Search by individual tokens (catches partial matches)
    logger.debug("Strategy 3: Token search for %s", q_tokens)
    for tok in q_tokens:
        if len(tok) < 3:
            continue  # Skip very short tokens
        tok_limit = max(300, limit // 2)
        for sr in _safe_iterate(
            reddit.subreddits.search(tok, limit=tok_limit), f"token '{tok}'"
        ):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    if breadth < 4:
        return

    # Strategy 4: Search with common suffixes/prefixes
    logger.debug("Strategy 4: Pattern search for '%s'", query)
    patterns_basic = [
        f"{query}s",
        f"{query}ing",
        f"the{query}",
        f"{query}hub",
        f"r{query}",
        f"{query}memes",
        f"ask{query}",
    ]
    for pattern in patterns_basic:
        for sr in _safe_iterate(
            reddit.subreddits.search_by_name(pattern, exact=False),
            f"pattern '{pattern}'"
        ):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    if breadth < 5:
        return

    # Strategy 5: Related term searches (expand discovery)
    logger.debug("Strategy 5: Related term searches for '%s'", query)
    # Search for plural/singular variations and related suffixes
    related_searches = [
        f"{query} community",
        f"{query} discussion",
        f"{query} news",
        f"true{query}",
        f"real{query}",
        f"{query}porn",  # Common suffix for enthusiast subs (e.g., earthporn)
        f"{query}enthusiasts",
    ]
    for related in related_searches:
        for sr in _safe_iterate(
            reddit.subreddits.search(related, limit=100), f"related '{related}'"
        ):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    if breadth < 6:
        return

    # Strategy 6: More aggressive pattern matching
    logger.debug("Strategy 6: Extended pattern search for '%s'", query)
    patterns_extended = [
        f"{query}advice",
        f"{query}101",
        f"{query}tips",
        f"{query}help",
        f"best{query}",
        f"{query}circle",
        f"casual{query}",
        f"{query}irl",
    ]
    for pattern in patterns_extended:
        for sr in _safe_iterate(
            reddit.subreddits.search_by_name(pattern, exact=False),
            f"ext pattern '{pattern}'"
        ):
            if dedupe_push(sr):
                yield sr
                yielded_count += 1

    # Also search each token with patterns
    for tok in q_tokens:
        if len(tok) < 4:
            continue
        for suffix in ["s", "ing", "hub", "memes"]:
            pattern = f"{tok}{suffix}"
            for sr in _safe_iterate(
                reddit.subreddits.search_by_name(pattern, exact=False),
                f"token pattern '{pattern}'",
                max_items=50
            ):
                if dedupe_push(sr):
                    yield sr
                    yielded_count += 1

    logger.info(
        "Broadened search complete: %d unique subreddits for query '%s'",
        yielded_count, query
    )
