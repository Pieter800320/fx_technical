"""
config/pairs.py
Central configuration: pairs, currencies, session guards.
"""

import datetime

# ── Forex Pairs ───────────────────────────────────────────────────────────────
PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY"
]

# ── Extra Instruments (commodities + indices) ─────────────────────────────────
EXTRA_INSTRUMENTS = [
    "XAU/USD",   # Gold
    "SPX",       # S&P 500
    "NAS100",    # Nasdaq 100
]

# Twelvedata symbol overrides (where slash format differs)
TD_SYMBOL_MAP = {
    "XAU/USD": "XAU/USD",
    "SPX":     "SPX",
    "NAS100":  "NDX",      # Twelvedata uses NDX for Nasdaq 100
}

INSTRUMENT_DISPLAY = {
    "XAU/USD": "GOLD",
    "SPX":     "SPX",
    "NAS100":  "NAS100",
}

# Market hours UTC for non-forex instruments
INSTRUMENT_SESSIONS = {
    "XAU/USD": (8, 21),    # London open to NY close
    "SPX":     (13, 21),   # NYSE hours (approximate)
    "NAS100":  (13, 21),   # NYSE/Nasdaq hours
}

CURRENCIES = ["EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD"]

# ── Forex Session windows (UTC) ───────────────────────────────────────────────
SESSIONS = {
    "Sydney":   (21, 6),
    "Tokyo":    (0,  9),
    "London":   (7,  16),
    "New York": (12, 21),
}

SESSION_PAIRS = {
    "Sydney":   ["AUD/USD", "NZD/USD", "USD/JPY"],
    "Tokyo":    ["USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/USD", "NZD/USD"],
    "London":   ["EUR/USD", "GBP/USD", "USD/CHF", "EUR/JPY", "GBP/JPY", "USD/CAD"],
    "New York": ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "AUD/USD", "NZD/USD"],
}


def get_active_sessions(dt=None):
    if dt is None:
        dt = datetime.datetime.utcnow()
    hour = dt.hour
    active = []
    for name, (start, end) in SESSIONS.items():
        if start > end:
            if hour >= start or hour < end:
                active.append(name)
        else:
            if start <= hour < end:
                active.append(name)
    return active


def is_pair_active(pair, dt=None):
    if dt is None:
        dt = datetime.datetime.utcnow()
    # Non-forex instruments use fixed hours
    if pair in INSTRUMENT_SESSIONS:
        start, end = INSTRUMENT_SESSIONS[pair]
        hour = dt.hour
        return start <= hour < end
    # Forex — session guard
    for session in get_active_sessions(dt):
        if pair in SESSION_PAIRS.get(session, []):
            return True
    return False


def pair_display(pair):
    return INSTRUMENT_DISPLAY.get(pair, pair.replace("/", ""))


def td_symbol(pair):
    return TD_SYMBOL_MAP.get(pair, pair)
