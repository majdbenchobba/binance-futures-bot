import logging

import requests

from config import ALERT_BELL, ALERT_TIMEOUT_SECONDS, ALERT_WEBHOOK_URL, DRY_RUN, USE_TESTNET


def send_alert(message, level="warning", context=None, log_message=True):
    if log_message:
        log_method = getattr(logging, level, logging.warning)
        log_method(message)

    if ALERT_BELL:
        print("\a", end="")

    if not ALERT_WEBHOOK_URL:
        return False

    payload = {
        "source": "binance-futures-bot",
        "level": level,
        "message": message,
        "context": context or {},
        "dry_run": DRY_RUN,
        "testnet": USE_TESTNET,
    }

    try:
        response = requests.post(
            ALERT_WEBHOOK_URL,
            json=payload,
            timeout=ALERT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logging.error(f"Failed to send alert webhook: {exc}")
        return False
