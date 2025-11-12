import logging
import threading
from typing import Dict, List

import requests

from .config import (
    PHONE_HOME_ENABLED,
    PHONE_HOME_ENDPOINT,
    PHONE_HOME_TOKEN,
    PHONE_HOME_TIMEOUT,
    PHONE_HOME_BATCH_MAX,
    PHONE_HOME_SOURCE,
)

logger = logging.getLogger("phone_home")


def is_enabled() -> bool:
    return PHONE_HOME_ENABLED and bool(PHONE_HOME_ENDPOINT)


def queue_phone_home(records: List[Dict]):
    if not is_enabled():
        return
    if not records:
        return
    trimmed = records[:PHONE_HOME_BATCH_MAX]
    thread = threading.Thread(target=_send_payload, args=(trimmed,), daemon=True)
    thread.start()


def _send_payload(records: List[Dict]):
    """Send discovered subreddits to upstream endpoint (non-blocking, best-effort)."""
    if not records:
        return

    payload = {
        "source": PHONE_HOME_SOURCE,
        "count": len(records),
        "subs": records,
    }
    headers = {"Content-Type": "application/json"}
    if PHONE_HOME_TOKEN:
        headers["Authorization"] = f"Bearer {PHONE_HOME_TOKEN}"
    try:
        resp = requests.post(
            PHONE_HOME_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=PHONE_HOME_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info("Phone-home sync delivered %d subreddits to %s", len(records), PHONE_HOME_ENDPOINT)
    except requests.exceptions.Timeout:
        logger.warning("Phone-home sync timed out after %ds", PHONE_HOME_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        logger.warning("Phone-home sync failed: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected error in phone-home sync: %s", exc)
