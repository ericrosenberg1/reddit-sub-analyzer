import logging
import os
import time
from datetime import datetime
from typing import Callable, Dict, Optional, Set

import praw
import prawcore
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Reddit API Configuration
# You'll need to create a Reddit app at: https://www.reddit.com/prefs/apps
# Click "create another app..." and select "script"
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "your_client_id_here")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "your_client_secret_here")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME", "your_username_here")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD", "your_password_here")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "unmoderated_subreddit_finder/1.0")
REDDIT_TIMEOUT = int(os.getenv("REDDIT_TIMEOUT", "10") or 10)

logger = logging.getLogger("sub_search")


def _int_from_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


# Limits to keep moderator lookups in check while still surfacing activity.
# Sample size controls how many moderators per subreddit we inspect (sorted by
# newest assignment). Fetch limit bounds total Redditor lookups per run.
MOD_ACTIVITY_SAMPLE_SIZE = max(0, _int_from_env("SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE", 5))
MOD_ACTIVITY_FETCH_LIMIT = max(0, _int_from_env("SUBSEARCH_MOD_ACTIVITY_FETCH_LIMIT", 8000))

def _current_reddit_config():
    """Resolve current Reddit configuration from environment (runtime).

    Falls back to module defaults if env is unset so environment changes take
    effect without restarting the process.
    """
    # Reload .env if present (non-fatal if missing)
    try:
        load_dotenv(override=True)
    except Exception:
        pass
    return {
        'client_id': os.getenv("REDDIT_CLIENT_ID") or REDDIT_CLIENT_ID,
        'client_secret': os.getenv("REDDIT_CLIENT_SECRET") or REDDIT_CLIENT_SECRET,
        'username': os.getenv("REDDIT_USERNAME") or REDDIT_USERNAME,
        'password': os.getenv("REDDIT_PASSWORD") or REDDIT_PASSWORD,
        'user_agent': os.getenv("REDDIT_USER_AGENT") or REDDIT_USER_AGENT,
        'timeout': int(os.getenv("REDDIT_TIMEOUT") or REDDIT_TIMEOUT or 10),
    }


def find_unmoderated_subreddits(
    limit=100,
    name_keyword=None,
    unmoderated_only=True,
    exclude_nsfw=False,
    min_subscribers=0,
    activity_mode="any",  # 'any' | 'active_after' | 'inactive_before'
    activity_threshold_utc=None,
    progress_callback=None,
    stop_callback=None,
    rate_limit_delay: float = 0.0,
    include_all: bool = False,
    exclude_names: Optional[Set[str]] = None,
    result_callback: Optional[Callable[[Dict], None]] = None,
):
    """
    Connect to Reddit API and find subreddits with no moderators.

    Args:
        limit: Number of subreddits to check (default 100)
        name_keyword: Optional keyword to search in subreddit names

    Returns:
        List of dictionaries containing subreddit info
    """
    cfg = _current_reddit_config()
    logger.debug("Connecting to Reddit API with user_agent=%s", cfg['user_agent'])

    # Initialize Reddit instance
    # Build Reddit instance. Prefer authenticated script mode when username/password present, else read-only.
    requestor_kwargs = {"timeout": max(3, min(int(cfg.get('timeout') or 10), 120))}
    reddit_kwargs = {
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'user_agent': cfg['user_agent'],
        'requestor_kwargs': requestor_kwargs,
        'check_for_async': False,
    }
    if cfg.get('username') and cfg.get('password') and cfg['username'] != 'your_username_here' and cfg['password'] != 'your_password_here':
        reddit_kwargs.update({'username': cfg['username'], 'password': cfg['password']})
        auth_mode = 'script'
    else:
        auth_mode = 'read-only'
    reddit = praw.Reddit(**reddit_kwargs)
    if auth_mode == 'read-only':
        try:
            reddit.read_only = True
        except Exception:
            pass

    mod_activity_cache: Dict[str, Optional[int]] = {}
    mod_activity_fetches = 0
    normalized_excludes = {name.strip().lower() for name in (exclude_names or set()) if name and name.strip()}

    def _fetch_mod_activity(mod_name: str) -> Optional[int]:
        """Return most recent known activity UTC for the given moderator."""
        nonlocal mod_activity_fetches
        if not mod_name:
            return None
        if MOD_ACTIVITY_SAMPLE_SIZE <= 0:
            return None
        key = mod_name.lower()
        if key in mod_activity_cache:
            return mod_activity_cache[key]
        if MOD_ACTIVITY_FETCH_LIMIT and mod_activity_fetches >= MOD_ACTIVITY_FETCH_LIMIT:
            mod_activity_cache[key] = None
            return None
        mod_activity_fetches += 1
        last_ts: Optional[int] = None
        try:
            redditor = reddit.redditor(mod_name)
            for item in redditor.new(limit=1):
                ts = getattr(item, 'created_utc', None)
                if ts is None:
                    continue
                try:
                    last_ts = int(ts)
                except (TypeError, ValueError):
                    last_ts = None
                if last_ts is not None:
                    break
        except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException):
            last_ts = None
        except Exception:
            last_ts = None
        mod_activity_cache[key] = last_ts
        return last_ts

    filtered_subs = []
    evaluated_subs = []
    checked = 0

    if name_keyword:
        logger.info("Searching subreddits by name containing %r (limit=%d)...", name_keyword, limit)
    else:
        logger.info("Searching recent subreddits (limit=%d)...", limit)

    # Search through subreddits
    # Note: Finding truly unmoderated subs is rare, so we check various sources
    subreddit_iter = None
    if name_keyword:
        # Use Reddit's search to find subreddits matching the keyword in their name
        # PRAW's search returns subreddits whose names/titles match the query
        try:
            subreddit_iter = reddit.subreddits.search(query=name_keyword, limit=limit)
        except (prawcore.exceptions.Forbidden, praw.exceptions.PRAWException) as e:
            logger.warning("Search endpoint error: %s. Falling back to recent subreddits.", e)
            subreddit_iter = reddit.subreddits.new(limit=limit)
    else:
        subreddit_iter = reddit.subreddits.new(limit=limit)

    for subreddit in subreddit_iter:
        # Allow cooperative cancellation
        if stop_callback:
            try:
                if stop_callback():
                    logger.info("Stop requested; ending early. Checked=%d, found=%d", checked, len(filtered_subs))
                    break
            except Exception:
                pass
        checked += 1
        if progress_callback:
            try:
                progress_callback(checked=checked, found=len(filtered_subs))
            except Exception:
                pass
        latest_post_utc = None

        try:
            # If a keyword is provided, restrict to subs whose NAME contains it
            if name_keyword:
                try:
                    if name_keyword.lower() not in subreddit.display_name.lower():
                        continue
                except AttributeError:
                    # If subreddit has no display_name, skip
                    continue

            # Exclude NSFW subreddits if requested
            if exclude_nsfw:
                try:
                    if getattr(subreddit, 'over18', False):
                        continue
                except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                    continue

            # Optional activity filter: inspect most recent post date
            if activity_mode in ("active_after", "inactive_before") and activity_threshold_utc:
                try:
                    for post in subreddit.new(limit=1):
                        latest_post_utc = getattr(post, 'created_utc', None)
                        break
                    if latest_post_utc is None:
                        continue
                    if activity_mode == "active_after" and latest_post_utc < activity_threshold_utc:
                        continue
                    if activity_mode == "inactive_before" and latest_post_utc >= activity_threshold_utc:
                        continue
                except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                    continue

            subscribers = None
            try:
                subscribers = subreddit.subscribers
            except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                subscribers = None
            subs_count = subscribers if isinstance(subscribers, int) else (subscribers or 0)
            if subs_count < (min_subscribers or 0):
                continue

            try:
                moderators = list(subreddit.moderator())
                real_mods = [
                    mod for mod in moderators
                    if getattr(mod, 'name', '').lower() not in ('automoderator', '')
                ]
                mod_count = len(real_mods)
            except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                real_mods = []
                mod_count = None

            last_mod_activity_utc = None
            if real_mods and MOD_ACTIVITY_SAMPLE_SIZE > 0:
                def _mod_sort_key(mod_obj):
                    raw = getattr(mod_obj, 'date', None)
                    if isinstance(raw, datetime):
                        return int(raw.timestamp())
                    try:
                        return int(raw or 0)
                    except (TypeError, ValueError):
                        return 0

                sorted_mods = sorted(real_mods, key=_mod_sort_key, reverse=True)
                for mod in sorted_mods[:MOD_ACTIVITY_SAMPLE_SIZE]:
                    mod_name = getattr(mod, 'name', None)
                    if not mod_name or mod_name.lower() == 'automoderator':
                        continue
                    ts = _fetch_mod_activity(mod_name)
                    if ts is None:
                        continue
                    if last_mod_activity_utc is None or ts > last_mod_activity_utc:
                        last_mod_activity_utc = ts

            display_name = getattr(subreddit, 'display_name', 'unknown')
            display_name_prefixed = getattr(subreddit, 'display_name_prefixed', f"r/{display_name}")
            title = getattr(subreddit, 'title', display_name)
            public_description = getattr(subreddit, 'public_description', '') or ''
            sub_info = {
                'name': display_name,
                'display_name_prefixed': display_name_prefixed,
                'title': title,
                'public_description': public_description,
                'subscribers': subs_count,
                'url': f"https://reddit.com{getattr(subreddit, 'url', '/') }",
                'is_unmoderated': bool(mod_count == 0) if mod_count is not None else False,
                'is_nsfw': bool(getattr(subreddit, 'over18', False)),
                'mod_count': mod_count,
                'last_activity_utc': latest_post_utc,
                'last_mod_activity_utc': last_mod_activity_utc,
            }
            name_key = (display_name or "").strip().lower()
            if normalized_excludes and name_key in normalized_excludes:
                continue
            evaluated_subs.append(sub_info)
            if not unmoderated_only or sub_info['is_unmoderated']:
                filtered_subs.append(sub_info)
                if unmoderated_only:
                    logger.info("Found unmoderated: %s (%s subscribers)", sub_info['display_name_prefixed'], sub_info['subscribers'])
            if result_callback:
                try:
                    result_callback(dict(sub_info))
                except Exception:
                    logger.debug("Result callback failed for %s", sub_info.get("name"), exc_info=True)

        except Exception:
            # Any unexpected error per-subreddit should not abort the run
            pass
        if checked % 20 == 0:
            logger.debug("Progress: checked=%d found=%d", checked, len(filtered_subs))
        if rate_limit_delay and rate_limit_delay > 0:
            time.sleep(rate_limit_delay)

    logger.info("Total checked: %d", checked)
    if unmoderated_only:
        logger.info("Found %d unmoderated subreddits", len(filtered_subs))
    else:
        logger.info("Collected %d subreddits", len(filtered_subs))

    if include_all:
        return {
            "results": filtered_subs,
            "evaluated": evaluated_subs,
            "checked": checked,
        }
    return filtered_subs
