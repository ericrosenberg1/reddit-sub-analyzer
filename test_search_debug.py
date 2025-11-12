#!/usr/bin/env python3
"""Debug test script to see what's happening with broadened_search."""

import logging
import os
import praw
import prawcore
from dotenv import load_dotenv
from subsearch.broadened_search import broadened_subreddit_search

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("test_search_debug")

load_dotenv()

# Check env vars
logger.info(f"REDDIT_CLIENT_ID: {os.getenv('REDDIT_CLIENT_ID', 'NOT SET')[:20]}...")
logger.info(f"REDDIT_CLIENT_SECRET: {os.getenv('REDDIT_CLIENT_SECRET', 'NOT SET')[:20]}...")
logger.info(f"REDDIT_USERNAME: {os.getenv('REDDIT_USERNAME', 'NOT SET')}")

# Try to create Reddit instance
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "your_client_id_here")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "your_client_secret_here")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "SubSearch/1.0")

logger.info("Creating Reddit instance...")
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT,
    check_for_async=False,
)
reddit.read_only = True

logger.info("Testing basic Reddit API access...")
try:
    # Test basic access
    for sub in reddit.subreddits.popular(limit=3):
        logger.info(f"  Popular sub: {sub.display_name}")
    logger.info("Basic access works!")
except Exception as e:
    logger.error(f"Basic access failed: {e}", exc_info=True)

logger.info("\nTesting broadened_subreddit_search for 'home'...")
count = 0
try:
    for sub in broadened_subreddit_search(
        reddit=reddit,
        query="home",
        limit=20,
        delay=0.0,
        include_over_18=True,
        breadth=3,
        popular_sip=100,
    ):
        count += 1
        logger.info(f"  {count}. {sub.display_name} - {getattr(sub, 'subscribers', 0):,} subs")
        if count >= 10:
            break
    logger.info(f"Total results from generator: {count}")
except Exception as e:
    logger.error(f"Broadened search failed: {e}", exc_info=True)
