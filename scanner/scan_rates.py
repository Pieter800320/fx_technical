"""scanner/scan_rates.py — Fetch central bank policy rates from FRED."""
import csv, io, json, os, sys, datetime, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alerts.telegram import send_telegram

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
RATES_OUT  = os.path.join(DATA_DIR, "rates.json")
STATE_FILE = os.path.join(DATA_DIR, "alert_state.json")
HEADERS    = {"User-Agent": "Mozilla/5.0 (FX-Dashboard-Bot/1.0)"}

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

RATE_SOURCES = {
    "USD": {"series": "FEDFUNDS",        "bank": "Fed"},
    "EUR": {"series": "ECBDFR",          "bank": "ECB"},
    "GBP": {"series": "BOERUKM",         "bank": "BOE"},
    "JPY": {"series": "IRSTCI01JPM156N", "bank": "BOJ"},
    "CHF": {"series": "IRSTCI01CHM156N", "bank": "SNB"},
    "AUD": {"series": "IRSTCI01AUM156N", "bank": "RBA"},
    "CAD": {"series": "IRSTCI01CAM156N", "bank": "BOC"},
    "NZD": {"series": "IRSTCI01NZM156N", "bank": "RBNZ"},
}


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


def _fetch_rate(series: str) -> float | None:
    url = FRED_BASE.format(series=series)
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode()
        last_val = None
        for row in csv.DictReader(io.StringIO(text)):
            v = row.get("VALUE", "").strip()
            if v and v != ".":
                last_val = round(float(v), 4)
        if last_val is None:
            print(f"  [FRED] {series}: no valid rows")
        return last_val
    except Exception as e:
        print(f"  [FRED] {series}: {e}")
        return None


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

    prev_rates = {e["currency"]: e for e in load_json(RATES_OUT).get("rates", [])}
    state      = load_state()
    new_rates  = []

    for ccy, src in RATE_SOURCES.items():
        rate = _fetch_rate(src["series"])
        if rate is None:
            print(f"  {ccy} ({src['bank']}): fetch failed — carrying forward")
            if ccy in prev_rates:
                new_rates.append(prev_rates[ccy])
            continue
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

    output = {"rates": new_rates, "updated": now.isoformat()}
    with open(RATES_OUT, "w") as f:
        json.dump(output, f, indent=2)

    save_state(state)
    print(f"\n  Saved: {RATES_OUT}")
    print("=== Rates Scan complete ===\n")


if __name__ == "__main__":
    main()
