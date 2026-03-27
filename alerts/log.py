"""
alerts/log.py
Append alert records to data/alerts.json so the dashboard
can display the latest AI opinion per pair.

Keeps the last 50 alerts to avoid unbounded growth.
"""

import json
import os
import datetime

ALERTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "alerts.json")
MAX_ALERTS = 50


def log_alert(
    pair: str,
    direction: str,
    h1_label: str,
    h4_label: str,
    d1_label: str,
    blurb: str,
    levels: dict = None,
):
    """Append a new alert record to alerts.json."""
    try:
        with open(ALERTS_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"alerts": []}

    record = {
        "pair":      pair,
        "direction": direction,
        "h1_label":  h1_label,
        "h4_label":  h4_label,
        "d1_label":  d1_label,
        "blurb":     blurb,
        "levels":    levels or {},
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }

    data["alerts"].append(record)

    # Trim to last MAX_ALERTS
    data["alerts"] = data["alerts"][-MAX_ALERTS:]

    os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
    with open(ALERTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
