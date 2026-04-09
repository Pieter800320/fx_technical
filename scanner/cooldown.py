"""scanner/cooldown.py"""
import json, os, datetime

COOLDOWN_PATH  = os.path.join(os.path.dirname(__file__), "..", "state", "cooldown.json")
COOLDOWN_HOURS = 4

def _load():
    try:
        with open(COOLDOWN_PATH) as f: return json.load(f)
    except: return {}

def _save(state):
    os.makedirs(os.path.dirname(COOLDOWN_PATH), exist_ok=True)
    with open(COOLDOWN_PATH, "w") as f: json.dump(state, f, indent=2)

def is_on_cooldown(pair, direction):
    state = _load()
    key   = f"{pair}_{direction}"
    last_str = state.get(key)
    if not last_str: return False
    elapsed = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(last_str)).total_seconds() / 3600
    return elapsed < COOLDOWN_HOURS

def record_alert(pair, direction):
    state = _load()
    state[f"{pair}_{direction}"] = datetime.datetime.utcnow().isoformat()
    _save(state)
