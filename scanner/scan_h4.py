"""scanner/scan_h4.py — H4 scan, D1+H4 gate"""
import json, os, sys, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, is_pair_active, get_active_sessions
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair, is_extended
from scanner.correlate import compute_correlation
from scanner.levels import find_levels
from scanner.cooldown import is_on_cooldown, record_alert
from alerts.news import get_alert_context
from alerts.telegram import build_message, send_telegram
from alerts.log import log_alert

DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
H4_OUTPUT   = os.path.join(DATA_DIR, "h4_scores.json")
CORR_OUTPUT = os.path.join(DATA_DIR, "correlation.json")
H1_SCORES   = os.path.join(DATA_DIR, "h1_scores.json")
D1_SCORES   = os.path.join(DATA_DIR, "d1_scores.json")
REGIME_FILE = os.path.join(DATA_DIR, "regime.json")

def load_scores(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def main():
    print(f"\n=== H4 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    now = datetime.datetime.utcnow()

    day, hour = now.weekday(), now.hour
    if day == 5 or (day == 6 and hour < 22) or (day == 4 and hour >= 22):
        print("  Market closed (weekend) — exiting.")
        return

    ohlcv           = fetch_all_pairs(PAIRS, "H4")
    h1_data         = load_scores(H1_SCORES)
    d1_data         = load_scores(D1_SCORES)
    regime          = load_scores(REGIME_FILE)
    active_sessions = get_active_sessions(now)
    h4_results      = {}

    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None:
            print(f"  {pair_display(pair)}: no data"); continue
        result = score_pair(df, timeframe="H4")
        if result is None:
            print(f"  {pair_display(pair)}: insufficient bars"); continue

        label     = result["label"]
        direction = result["direction"]
        display   = pair_display(pair)
        ext_data  = is_extended(df, direction)
        levels    = find_levels(df)

        h4_results[pair] = {
            "score":      result["score"],
            "label":      label,
            "direction":  direction,
            "raw":        result["raw"],
            "signals":    result["signals"],
            "filter_ok":  result["filter_ok"],
            "extended":   ext_data,
            "conflict":   result.get("conflict", False),
            "structure":  result.get("structure", {}),
            "adx_weight": result.get("adx_weight", 1.0),
            "updated":    now.isoformat(),
        }
        print(f"  {display}: {result['score']:+d} → {label}")

        if direction == "neutral": continue
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

        h1_label = h1_data.get(pair, {}).get("label", "N/A")
        adx_val  = result["raw"].get("adx")
        print(f"    ↳ H4 ALERT: {direction.upper()} — fetching news context...")
        ctx = get_alert_context(pair)
        msg = build_message(
            pair=pair, direction=direction, h1_label=h1_label,
            h4_label=label, d1_label=d1_label,
            session_names=active_sessions, adx_val=adx_val,
            atr_ok=result["filter_ok"], headline=ctx["headline"],
            events=ctx["events"], extended=ext_data, regime=regime,
            conflict=result.get("conflict", False),
            structure=result.get("structure"),
            adx_weight=result.get("adx_weight"),
        )
        send_telegram(msg)
        record_alert(pair, direction)
        log_alert(pair, direction, h1_label, label, d1_label,
                  ctx["headline"], levels=levels, extended=ext_data,
                  regime=regime, adx_val=adx_val, atr_ok=result["filter_ok"],
                  conflict=result.get("conflict", False),
                  structure=result.get("structure", {}))

    # Correlation matrix
    print("\n  Computing correlation matrix...")
    corr_result = compute_correlation(ohlcv)
    with open(CORR_OUTPUT, "w") as f:
        json.dump({"pairs": corr_result["pairs"], "matrix": corr_result["matrix"],
                   "lookback": 50, "updated": now.isoformat()}, f, indent=2)
    print(f"  Correlation matrix: {len(corr_result['pairs'])} pairs")

    with open(H4_OUTPUT, "w") as f:
        json.dump(h4_results, f, indent=2)
    print(f"\n  Saved: {H4_OUTPUT}")
    print(f"  Saved: {CORR_OUTPUT}")
    print("=== H4 Scan complete ===\n")

if __name__ == "__main__":
    main()
