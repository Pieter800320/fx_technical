"""scanner/scan_alerts.py — Telegram alerts: mean reversion reset only."""
import json, os, sys, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display
from alerts.telegram import send_telegram

DATA_DIR        = os.path.join(os.path.dirname(__file__), "..", "data")
STATE_FILE      = os.path.join(DATA_DIR, "alert_state.json")
D1_SCORES       = os.path.join(DATA_DIR, "d1_scores.json")
H4_SCORES       = os.path.join(DATA_DIR, "h4_scores.json")
CONVICTION_FILE = os.path.join(DATA_DIR, "conviction.json")


def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def load_state() -> dict:
    s = load_json(STATE_FILE)
    s.setdefault("reset", {})
    return s

def save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def _arrow(direction: str) -> str:
    return "▲" if direction == "bullish" else ("▼" if direction == "bearish" else "–")


def check_reset(state: dict, now: datetime.datetime):
    h4         = load_json(H4_SCORES)
    d1         = load_json(D1_SCORES)
    conviction = load_json(CONVICTION_FILE).get("pairs", {})
    for pair in PAIRS:
        reset = h4.get(pair, {}).get("reset_score")
        if reset is None:
            continue
        if reset > 35:
            state["reset"].pop(pair, None)
            continue
        if reset > 20:
            continue
        conv = conviction.get(pair)
        if conv is None or conv < 20:
            continue
        if pair in state["reset"]:
            continue
        d1_dir = d1.get(pair, {}).get("direction", "neutral")
        sign   = "+" if conv >= 0 else ""
        msg    = f"🎯 <b>{pair_display(pair)}</b> Reset {reset} · Conv {sign}{conv} · D1 {_arrow(d1_dir)}"
        print(f"  [RESET] {pair_display(pair)} reset={reset} conv={conv}")
        if send_telegram(msg):
            state["reset"][pair] = now.isoformat()


def main():
    print(f"\n=== Alert Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    now   = datetime.datetime.utcnow()
    state = load_state()

    print("  Checking mean reversion reset...")
    check_reset(state, now)

    save_state(state)
    print(f"\n  State: {STATE_FILE}")
    print("=== Alert Scan complete ===\n")


if __name__ == "__main__":
    main()
