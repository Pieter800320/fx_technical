"""scanner/scan_rates.py — Publish central bank policy rates from rates_manual.json."""
import json, os, sys, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alerts.telegram import send_telegram

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
RATES_OUT  = os.path.join(DATA_DIR, "rates.json")
RATES_SRC  = os.path.join(DATA_DIR, "rates_manual.json")
STATE_FILE = os.path.join(DATA_DIR, "alert_state.json")


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
    s.setdefault("rates", {})
    return s

def save_state(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _implication(ccy: str, old: float, new: float, prev_move: str | None) -> str:
    move = "cut" if new < old else "hike"
    if move == "cut":
        if prev_move == "hike":
            return f"{ccy} cycle turning, watch longs"
        return f"{ccy} weakens, carry unwinds"
    else:
        if prev_move == "cut":
            return f"{ccy} tightening begins, trend fuel"
        return f"{ccy} strengthens, carry builds"


def main():
    print(f"\n=== Rates Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.datetime.utcnow()

    manual         = load_json(RATES_SRC)
    existing       = load_json(RATES_OUT)
    prev_rates_list = existing.get("rates", [])
    prev_rates     = {e["currency"]: e for e in prev_rates_list}
    state          = load_state()
    new_rates      = []

    for ccy, src in manual.items():
        if not isinstance(src, dict): continue
        rate = float(src["rate"])
        entry = {
            "currency": ccy,
            "rate":     rate,
            "bank":     src["bank"],
            "updated":  now.isoformat(),
        }
        new_rates.append(entry)
        print(f"  {src['bank']:4s} ({ccy}): {rate}%")

        # ── Change detection + Telegram alert ────────────────────────────────
        prev = prev_rates.get(ccy)
        if prev is None:
            continue
        old_rate = float(prev["rate"])
        if rate == old_rate:
            continue

        move      = "cut" if rate < old_rate else "hike"
        prev_move = state["rates"].get(ccy, {}).get("last_move")
        impl      = _implication(ccy, old_rate, rate, prev_move)
        msg = (
            f"🏦 <b>{src['bank']}</b> {old_rate:.2f}% → {rate:.2f}%"
            f" · {impl}"
        )
        print(f"  [RATE CHANGE] {msg}")
        if send_telegram(msg):
            state["rates"][ccy] = {"last_move": move}

    output = {"rates": new_rates, "_prev": prev_rates_list, "updated": now.isoformat()}
    with open(RATES_OUT, "w") as f:
        json.dump(output, f, indent=2)

    save_state(state)
    print(f"\n  Saved: {RATES_OUT}")
    print("=== Rates Scan complete ===\n")


if __name__ == "__main__":
    main()
