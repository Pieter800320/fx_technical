"""
config/pairs.py
Central configuration: pairs, currencies, session guards.
"""

import datetime

# ── Pairs ────────────────────────────────────────────────────────────────────
PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY"
]

CURRENCIES = ["EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD"]

# ── Session windows (UTC hours, inclusive start / exclusive end) ──────────────
SESSIONS = {
    "Sydney":   (21, 6),   # wraps midnight
    "Tokyo":    (0,  9),
    "London":   (7,  16),
    "New York": (12, 21),
}

# Pairs most relevant per session
SESSION_PAIRS = {
    "Sydney":   ["AUD/USD", "NZD/USD", "USD/JPY"],
    "Tokyo":    ["USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/USD", "NZD/USD"],
    "London":   ["EUR/USD", "GBP/USD", "USD/CHF", "EUR/JPY", "GBP/JPY", "USD/CAD"],
    "New York": ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "AUD/USD", "NZD/USD"],
}


def get_active_sessions(dt: datetime.datetime = None) -> list[str]:
    """Return list of active session names for a given UTC datetime."""
    if dt is None:
        dt = datetime.datetime.utcnow()
    hour = dt.hour
    active = []
    for name, (start, end) in SESSIONS.items():
        if start > end:  # wraps midnight (Sydney)
            if hour >= start or hour < end:
                active.append(name)
        else:
            if start <= hour < end:
                active.append(name)
    return active


def is_pair_active(pair: str, dt: datetime.datetime = None) -> bool:
    """True if the pair trades in at least one currently active session."""
    for session in get_active_sessions(dt):
        if pair in SESSION_PAIRS.get(session, []):
            return True
    return False


def pair_display(pair: str) -> str:
    """EUR/USD → EURUSD"""
    return pair.replace("/", "")


def pair_td(pair: str) -> str:
    """EUR/USD → EUR/USD (Twelvedata already uses slash format)"""
    return pair
