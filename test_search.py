#!/usr/bin/env python3
"""Quick test script to verify the Sub Search fix works."""

import logging
import sys
from subsearch.auto_sub_analyzer import find_unmoderated_subreddits

# Enable debug logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("test_search")

def test_home_search():
    """Test searching for 'home' which was previously returning 0 results."""
    logger.info("Testing search for 'home' keyword...")

    try:
        results = find_unmoderated_subreddits(
            limit=50,
            name_keyword="home",
            unmoderated_only=False,  # Get all subreddits, not just unmoderated
            exclude_nsfw=False,
            min_subscribers=0,
            rate_limit_delay=0.0,  # Fast test
            include_all=True,
        )

        found_subs = results.get("results", [])
        evaluated_subs = results.get("evaluated", [])
        checked = results.get("checked", 0)

        logger.info(f"Search completed!")
        logger.info(f"  Checked: {checked} subreddits")
        logger.info(f"  Evaluated: {len(evaluated_subs)} subreddits")
        logger.info(f"  Results: {len(found_subs)} subreddits")

        if found_subs:
            logger.info("\nFirst 10 results:")
            for i, sub in enumerate(found_subs[:10], 1):
                logger.info(f"  {i}. {sub.get('display_name_prefixed', 'N/A')} - {sub.get('subscribers', 0):,} subs - {sub.get('title', 'N/A')}")
            return True
        else:
            logger.error("ERROR: Search returned 0 results! This should not happen for 'home'")
            return False

    except Exception as e:
        logger.error(f"Search failed with error: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_home_search()
    sys.exit(0 if success else 1)
