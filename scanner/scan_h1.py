"""scanner/scan_h1.py — H1 scan, D1+H4+H1 gate"""
import json, os, sys, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, is_pair_active, get_active_sessions
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair, is_extended
from scanner.levels import find_levels
from scanner.cooldown import is_on_cooldown, record_alert
from alerts.news import get_alert_context
from alerts.telegram import build_message, send_telegram
from alerts.log import log_alert

DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
H1_OUTPUT   = os.path.join(DATA_DIR, "h1_scores.json")
H4_SCORES   = os.path.join(DATA_DIR, "h4_scores.json")
D1_SCORES   = os.path.join(DATA_DIR, "d1_scores.json")
REGIME_FILE = os.path.join(DATA_DIR, "regime.json")

def load_scores(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def main():
    print(f"\n=== H1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    now = datetime.datetime.utcnow()

    # Weekend guard
    day, hour = now.weekday(), now.hour
    if day == 5 or (day == 6 and hour < 22) or (day == 4 and hour >= 22):
        print("  Market closed (weekend) — exiting.")
        return

    ohlcv           = fetch_all_pairs(PAIRS, "H1")
    h4_data         = load_scores(H4_SCORES)
    d1_data         = load_scores(D1_SCORES)
    regime          = load_scores(REGIME_FILE)
    active_sessions = get_active_sessions(now)
    h1_results      = {}

    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None:
            print(f"  {pair_display(pair)}: no data"); continue
        result = score_pair(df, timeframe="H1")
        if result is None:
            print(f"  {pair_display(pair)}: insufficient bars"); continue

        label     = result["label"]
        direction = result["direction"]
        display   = pair_display(pair)
        ext_data  = is_extended(df, direction)
        levels    = find_levels(df)

        h1_results[pair] = {
            "score":     result["score"], "label": label, "direction": direction,
            "raw":       result["raw"], "signals": result["signals"],
            "filter_ok": result["filter_ok"], "extended": ext_data,
            "updated":   now.isoformat(),
        }
        print(f"  {display}: {result['score']:+d} → {label}")

        if direction == "neutral": continue
        h4_dir   = h4_data.get(pair, {}).get("direction", "neutral")
        h4_label = h4_data.get(pair, {}).get("label", "N/A")
        if h4_dir != direction:
            print(f"    ↳ Suppressed: H4 is {h4_dir}"); continue
        d1_dir   = d1_data.get(pair, {}).get("direction", "neutral")
        d1_label = d1_data.get(pair, {}).get("label", "N/A")
        if d1_dir != direction:
            print(f"    ↳ Suppressed: D1 is {d1_dir}"); continue
        if not result["filter_ok"]:
            [print(f"    ↳ Suppressed: {r}") for r in result["filter_reasons"]]; continue
        if not is_pair_active(pair, now):
            print(f"    ↳ Suppressed: {display} not active"); continue
        if is_on_cooldown(pair, direction):
            print(f"    ↳ Suppressed: on cooldown"); continue

        print(f"    ↳ ALERT: {direction.upper()} — fetching news context...")
        ctx = get_alert_context(pair)
        adx_val = result["raw"].get("adx")
        msg = build_message(
            pair=pair, direction=direction, h1_label=label,
            h4_label=h4_label, d1_label=d1_label,
            session_names=active_sessions, adx_val=adx_val,
            atr_ok=result["filter_ok"], headline=ctx["headline"],
            events=ctx["events"], extended=ext_data, regime=regime,
        )
        send_telegram(msg)
        record_alert(pair, direction)
        log_alert(pair, direction, label, h4_label, d1_label,
                  ctx["headline"], levels=levels, extended=ext_data,
                  regime=regime, adx_val=adx_val, atr_ok=result["filter_ok"])

    with open(H1_OUTPUT, "w") as f:
        json.dump(h1_results, f, indent=2)
    print(f"\n  Saved: {H1_OUTPUT}")
    print("=== H1 Scan complete ===\n")

if __name__ == "__main__":
    main()
