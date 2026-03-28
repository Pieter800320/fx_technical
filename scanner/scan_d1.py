"""
scanner/scan_d1.py
D1 scan — bias layer. Scores all pairs, computes improved currency strength.
Fetches both D1 and H4 OHLCV for multi-timeframe CSM calculation.
"""

import json
import os
import sys
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair
from scanner.csm import compute_currency_strength, MAJOR_PAIRS

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT  = os.path.join(DATA_DIR, "d1_scores.json")
CSM_OUTPUT = os.path.join(DATA_DIR, "csm.json")


def main():
    print(f"\n=== D1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    # Fetch D1 for scoring all pairs
    print("\n  Fetching D1 data...")
    d1_ohlcv = fetch_all_pairs(PAIRS, "D1")

    # Fetch H4 for major pairs only (CSM multi-TF weighting)
    # Pause to respect 8 requests/minute rate limit after D1 fetches
    import time
    print("\n  Rate limit pause before H4 fetch (62s)...")
    time.sleep(62)
    print("  Fetching H4 data for currency strength...")
    h4_ohlcv = fetch_all_pairs(MAJOR_PAIRS, "H4")

    d1_results = {}
    now = datetime.datetime.utcnow()

    # Score all pairs on D1
    for pair in PAIRS:
        df = d1_ohlcv.get(pair)
        if df is None:
            print(f"  {pair_display(pair)}: no data")
            continue

        result = score_pair(df, timeframe="D1")
        if result is None:
            print(f"  {pair_display(pair)}: insufficient bars")
            continue

        display     = pair_display(pair)
        filter_note = "" if result["filter_ok"] else f" ⚠️ {', '.join(result['filter_reasons'])}"
        print(f"  {display}: {result['score']:+d} → {result['label']}{filter_note}")

        d1_results[pair] = {
            "score":     result["score"],
            "label":     result["label"],
            "direction": result["direction"],
            "raw":       result["raw"],
            "signals":   result["signals"],
            "filter_ok": result["filter_ok"],
            "updated":   now.isoformat(),
        }

    # Compute improved currency strength
    print("\n  Computing currency strength (ATR-adjusted, D1×0.7 + H4×0.3)...")
    csm_result = compute_currency_strength(d1_ohlcv, h4_ohlcv)

    print("  Rankings:")
    for ccy, val in csm_result["rankings"].items():
        conf = csm_result["confidence"].get(ccy, 0)
        print(f"    {ccy}: {val:.1f}  (confidence: {conf:.0%})")

    # Save
    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_results, f, indent=2)

    with open(CSM_OUTPUT, "w") as f:
        json.dump({
            "rankings":   csm_result["rankings"],
            "confidence": csm_result["confidence"],
            "breakdown":  csm_result.get("breakdown", {}),
            "updated":    now.isoformat(),
        }, f, indent=2)

    print(f"\n  Saved: {D1_OUTPUT}")
    print(f"  Saved: {CSM_OUTPUT}")
    print("=== D1 Scan complete ===\n")


if __name__ == "__main__":
    main()
