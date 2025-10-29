"""
Reddit Unmoderated Subreddit Finder
Downloads a list of subreddits with no moderators to a CSV file.
"""

import csv
import os
from datetime import datetime

import praw
import prawcore
import logging
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

logger = logging.getLogger("analyzer")

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
):
    """
    Connect to Reddit API and find subreddits with no moderators.

    Args:
        limit: Number of subreddits to check (default 100)
        name_keyword: Optional keyword to search in subreddit names

    Returns:
        List of dictionaries containing subreddit info
    """
    logger.debug("Connecting to Reddit API with user_agent=%s", REDDIT_USER_AGENT)

    # Initialize Reddit instance
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD,
        user_agent=REDDIT_USER_AGENT
    )

    unmoderated_subs = []
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
                    logger.info("Stop requested; ending early. Checked=%d, found=%d", checked, len(unmoderated_subs))
                    break
            except Exception:
                pass
        checked += 1
        if progress_callback:
            try:
                progress_callback(checked=checked, found=len(unmoderated_subs))
            except Exception:
                pass

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
                    latest = None
                    for post in subreddit.new(limit=1):
                        latest = getattr(post, 'created_utc', None)
                        break
                    if latest is None:
                        continue
                    if activity_mode == "active_after" and latest < activity_threshold_utc:
                        continue
                    if activity_mode == "inactive_before" and latest >= activity_threshold_utc:
                        continue
                except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                    continue

            if unmoderated_only:
                # Get moderator list
                try:
                    moderators = list(subreddit.moderator())
                except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                    # Skip private/quarantined/inaccessible
                    continue

                # Check if there are no moderators (excluding AutoModerator)
                real_mods = [mod for mod in moderators if getattr(mod, 'name', '').lower() != 'automoderator']

                if len(real_mods) == 0:
                    # Safely get subscribers (may 403 on some subs)
                    subscribers = None
                    try:
                        subscribers = subreddit.subscribers
                    except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                        subscribers = None

                    subs_count = subscribers if isinstance(subscribers, int) else (subscribers or 0)
                    if subs_count < (min_subscribers or 0):
                        continue
                    sub_info = {
                        'name': getattr(subreddit, 'display_name', 'unknown'),
                        'subscribers': subs_count,
                        'url': f"https://reddit.com{getattr(subreddit, 'url', '/') }"
                    }
                    unmoderated_subs.append(sub_info)
                    logger.info("Found: r/%s (%s subscribers)", sub_info['name'], sub_info['subscribers'])
            else:
                # Include all subs that match, without moderator check
                subscribers = None
                try:
                    subscribers = subreddit.subscribers
                except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                    subscribers = None
                subs_count = subscribers if isinstance(subscribers, int) else (subscribers or 0)
                if subs_count < (min_subscribers or 0):
                    continue
                sub_info = {
                    'name': getattr(subreddit, 'display_name', 'unknown'),
                    'subscribers': subs_count,
                    'url': f"https://reddit.com{getattr(subreddit, 'url', '/') }"
                }
                unmoderated_subs.append(sub_info)

        except Exception:
            # Any unexpected error per-subreddit should not abort the run
            continue

        if checked % 20 == 0:
            logger.debug("Progress: checked=%d found=%d", checked, len(unmoderated_subs))

    logger.info("Total checked: %d", checked)
    if unmoderated_only:
        logger.info("Found %d unmoderated subreddits", len(unmoderated_subs))
    else:
        logger.info("Collected %d subreddits", len(unmoderated_subs))

    return unmoderated_subs


def save_to_csv(subreddits, filename=None):
    """
    Save subreddit data to CSV file.

    Args:
        subreddits: List of subreddit dictionaries
        filename: Output filename (optional)
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"unmoderated_subreddits_{timestamp}.csv"

    # Ensure output directory exists if user provided a path
    out_dir = os.path.dirname(os.path.abspath(filename)) or "."
    os.makedirs(out_dir, exist_ok=True)

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        if subreddits:
            writer = csv.DictWriter(f, fieldnames=['name', 'subscribers', 'url'])
            writer.writeheader()
            writer.writerows(subreddits)
            logger.info("Data saved to: %s", filename)
        else:
            logger.info("No subreddit data to save.")


def main():
    """Main execution function."""
    print("=" * 60)
    print("Reddit Unmoderated Subreddit Finder")
    print("=" * 60)
    print()

    # Check if credentials are set
    if REDDIT_CLIENT_ID == "your_client_id_here" or REDDIT_USERNAME == "your_username_here":
        print("ERROR: Please set your Reddit API credentials!")
        print("\nTo get credentials:")
        print("1. Go to https://www.reddit.com/prefs/apps")
        print("2. Click 'create another app...' at the bottom")
        print("3. Select 'script' as the app type")
        print("4. Fill in the name and redirect URI (use http://localhost:8080)")
        print("5. Copy the client ID (under the app name)")
        print("6. Copy the client secret")
        print("7. Update your .env file with:")
        print("   - REDDIT_CLIENT_ID")
        print("   - REDDIT_CLIENT_SECRET")
        print("   - REDDIT_USERNAME (your Reddit username)")
        print("   - REDDIT_PASSWORD (your Reddit password)")
        return

    try:
        # Find unmoderated subreddits
        # You can increase the limit to check more subreddits
        subreddits = find_unmoderated_subreddits(limit=100)

        # Save to CSV
        save_to_csv(subreddits)

        print("\nDone!")

    except praw.exceptions.PRAWException as e:
        print(f"\nReddit API Error: {e}")
        print("\nMake sure:")
        print("- You have installed PRAW: pip install praw")
        print("- Your Reddit API credentials are correct")
        print("- You have internet connection")
    except Exception as e:
        print(f"\nUnexpected Error: {e}")


if __name__ == "__main__":
    main()
