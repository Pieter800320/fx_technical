# config/pairs.py
import datetime

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY",
    "AUD/JPY", "NZD/JPY", "CAD/JPY",
]

CURRENCIES = ["EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD"]

# Fetched in D1 scan for regime classification — not traded pairs
# XAU/USD: gold direction is a key risk-off/risk-on signal
REGIME_EXTRA_PAIRS = ["XAU/USD"]

SESSIONS = {
    "Sydney":   (21, 6),
    "Tokyo":    (23, 8),   # corrected: 23:00–08:00 UTC = 01:00–10:00 CEST
    "London":   (7,  16),
    "New York": (13, 22),  # corrected: 13:00–22:00 UTC = 15:00–00:00 CEST
}

SESSION_PAIRS = {
    "Sydney":   ["AUD/USD", "NZD/USD", "USD/JPY", "AUD/JPY", "NZD/JPY"],
    "Tokyo":    ["USD/JPY", "EUR/JPY", "GBP/JPY", "AUD/USD", "NZD/USD",
                 "AUD/JPY", "NZD/JPY", "CAD/JPY"],
    "London":   ["EUR/USD", "GBP/USD", "USD/CHF", "EUR/JPY", "GBP/JPY",
                 "USD/CAD", "CAD/JPY"],
    "New York": ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CAD", "AUD/USD",
                 "NZD/USD", "CAD/JPY"],
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
    for session in get_active_sessions(dt):
        if pair in SESSION_PAIRS.get(session, []):
            return True
    return False


def pair_display(pair):
    return pair.replace("/", "")


def td_symbol(pair):
    return pair
