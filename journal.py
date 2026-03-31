import json
from datetime import datetime, timezone
from pathlib import Path

from config import JOURNAL_ENABLED, JOURNAL_FILE


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def append_journal_entry(event_type, payload=None, path=JOURNAL_FILE, enabled=JOURNAL_ENABLED):
    if not enabled:
        return False

    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": utc_timestamp(),
        "event": event_type,
        "payload": payload or {},
    }

    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")

    return True
