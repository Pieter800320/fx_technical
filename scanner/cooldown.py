"""
scanner/cooldown.py
Cooldown guard — prevents re-firing the same pair/direction within N hours.

State is stored in state/cooldown.json and committed back to the repo
by the GitHub Actions workflow after each alert run.
"""

import json
import os
import datetime

COOLDOWN_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "cooldown.json")
COOLDOWN_HOURS = 4


def _load() -> dict:
    try:
        with open(COOLDOWN_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(state: dict):
    os.makedirs(os.path.dirname(COOLDOWN_PATH), exist_ok=True)
    with open(COOLDOWN_PATH, "w") as f:
        json.dump(state, f, indent=2)


def is_on_cooldown(pair: str, direction: str) -> bool:
    """True if this pair+direction fired within the last COOLDOWN_HOURS."""
    state = _load()
    key = f"{pair}_{direction}"
    last_str = state.get(key)
    if not last_str:
        return False
    last_dt = datetime.datetime.fromisoformat(last_str)
    elapsed = (datetime.datetime.utcnow() - last_dt).total_seconds() / 3600
    return elapsed < COOLDOWN_HOURS


def record_alert(pair: str, direction: str):
    """Mark this pair+direction as alerted now."""
    state = _load()
    key = f"{pair}_{direction}"
    state[key] = datetime.datetime.utcnow().isoformat()
    _save(state)
