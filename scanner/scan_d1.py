"""
scanner/scan_d1.py
D1 scan — bias layer. Scores all pairs. No alerts fired here.
Also computes currency strength (forex pairs only).
"""

import json
import os
import sys
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair
from scanner.csm import compute_currency_strength

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT  = os.path.join(DATA_DIR, "d1_scores.json")
CSM_OUTPUT = os.path.join(DATA_DIR, "csm.json")

FOREX_PAIRS = [p for p in PAIRS if p != "XAU/USD"]


def main():
    print(f"\n=== D1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    ohlcv = fetch_all_pairs(PAIRS, "D1")

    d1_results = {}
    now = datetime.datetime.utcnow()

    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None:
            print(f"  {pair_display(pair)}: no data")
            continue

        result = score_pair(df, timeframe="D1")
        if result is None:
            print(f"  {pair_display(pair)}: insufficient bars")
            continue

        display = pair_display(pair)
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

    # Currency strength — forex only
    print("\n  Computing currency strength...")
    forex_ohlcv = {p: ohlcv[p] for p in FOREX_PAIRS if p in ohlcv}
    csm = compute_currency_strength(forex_ohlcv)
    for currency, value in csm.items():
        print(f"    {currency}: {value}")

    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_results, f, indent=2)

    with open(CSM_OUTPUT, "w") as f:
        json.dump({"rankings": csm, "updated": now.isoformat()}, f, indent=2)

    print(f"\n  Saved: {D1_OUTPUT}")
    print(f"  Saved: {CSM_OUTPUT}")
    print("=== D1 Scan complete ===\n")


if __name__ == "__main__":
    main()
