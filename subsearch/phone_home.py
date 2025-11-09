import logging
import os
import threading
from typing import Dict, List

import requests


def _truthy(value: str) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


PHONE_HOME_ENABLED = _truthy(os.getenv("PHONE_HOME", "false"))
PHONE_HOME_ENDPOINT = os.getenv("PHONE_HOME_ENDPOINT", "https://allthesubs.ericrosenberg.com/api/ingest").strip()
PHONE_HOME_TOKEN = os.getenv("PHONE_HOME_TOKEN", "").strip()
PHONE_HOME_TIMEOUT = float(os.getenv("PHONE_HOME_TIMEOUT", "10") or 10)
PHONE_HOME_BATCH_MAX = int(os.getenv("PHONE_HOME_BATCH_MAX", "500") or 500)
PHONE_HOME_SOURCE = os.getenv("SITE_URL", "").strip() or os.getenv("PHONE_HOME_SOURCE", "self-hosted").strip() or "self-hosted"

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
    except Exception as exc:
        logger.warning("Phone-home sync failed: %s", exc)
