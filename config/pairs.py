"""config/pairs.py"""
import datetime

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY",
]

CURRENCIES = ["EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD"]

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
    for session in get_active_sessions(dt):
        if pair in SESSION_PAIRS.get(session, []):
            return True
    return False

def pair_display(pair):
    return pair.replace("/", "")

def td_symbol(pair):
    return pair
