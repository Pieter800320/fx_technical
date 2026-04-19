"""scanner/scan_alerts.py — Proactive Telegram alerts (events, alignment, compression)."""
import json, os, sys, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display
from alerts.telegram import send_telegram

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
STATE_FILE = os.path.join(DATA_DIR, "alert_state.json")
CALENDAR   = os.path.join(DATA_DIR, "calendar.json")
D1_SCORES  = os.path.join(DATA_DIR, "d1_scores.json")
H4_SCORES  = os.path.join(DATA_DIR, "h4_scores.json")

STRONG_LABELS = {"Strong Buy", "Buy", "Strong Sell", "Sell"}


def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def load_state() -> dict:
    s = load_json(STATE_FILE)
    s.setdefault("events", {})
    s.setdefault("alignment", {})
    s.setdefault("compression", {})
    s.setdefault("regime", "")
    return s

def save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def _arrow(direction: str) -> str:
    return "▲" if direction == "bullish" else ("▼" if direction == "bearish" else "–")


def check_events(state: dict, now: datetime.datetime):
    events = load_json(CALENDAR).get("events", [])
    horizon = now + datetime.timedelta(hours=4)
    for ev in events:
        try:
            dt = datetime.datetime.fromisoformat(ev["datetime"])
        except Exception:
            continue
        if not (now <= dt <= horizon):
            continue
        key = f"{ev['datetime']}_{ev['currency']}"
        if key in state["events"]:
            continue
        hours = (dt - now).total_seconds() / 3600
        msg = f"⚡ <b>{ev['event']}</b> in {hours:.1f}h — {ev['currency']}"
        print(f"  [EVENT] {ev['currency']} {ev['event']}")
        if send_telegram(msg):
            state["events"][key] = now.isoformat()


def check_alignment(state: dict, now: datetime.datetime):
    d1 = load_json(D1_SCORES)
    h4 = load_json(H4_SCORES)
    today = now.strftime("%Y-%m-%d")
    for pair in PAIRS:
        d1e = d1.get(pair, {})
        h4e = h4.get(pair, {})
        d1_dir, h4_dir     = d1e.get("direction", "neutral"), h4e.get("direction", "neutral")
        d1_label, h4_label = d1e.get("label", "Neutral"),    h4e.get("label", "Neutral")
        if d1_dir == "neutral" or h4_dir == "neutral" or d1_dir != h4_dir:
            continue
        if d1_label not in STRONG_LABELS or h4_label not in STRONG_LABELS:
            continue
        key = f"{pair}_{today}"
        if key in state["alignment"]:
            continue
        arr = _arrow(d1_dir)
        msg = f"📊 <b>{pair_display(pair)}</b>  D1 {arr}  H4 {arr}"
        print(f"  [ALIGN] {pair_display(pair)} {d1_dir}")
        if send_telegram(msg):
            state["alignment"][key] = now.isoformat()


def check_compression(state: dict, now: datetime.datetime):
    d1 = load_json(D1_SCORES)
    for pair in PAIRS:
        entry = d1.get(pair, {})
        pct   = entry.get("atr_percentile")
        if pct is None:
            continue
        if pct > 30:
            state["compression"].pop(pair, None)
            continue
        if pct <= 20 and pair not in state["compression"]:
            arr = _arrow(entry.get("direction", "neutral"))
            msg = f"🔲 <b>{pair_display(pair)}</b> compression (ATR {int(pct)}th pct)  D1 {arr}"
            print(f"  [COMP] {pair_display(pair)} ATR {int(pct)}th")
            if send_telegram(msg):
                state["compression"][pair] = now.isoformat()


def main():
    print(f"\n=== Alert Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    now   = datetime.datetime.utcnow()
    state = load_state()

    print("\n  Checking event warnings...")
    check_events(state, now)
    print("  Checking D1+H4 alignment...")
    check_alignment(state, now)
    print("  Checking ATR compression...")
    check_compression(state, now)

    save_state(state)
    print(f"\n  State: {STATE_FILE}")
    print("=== Alert Scan complete ===\n")


if __name__ == "__main__":
    main()
