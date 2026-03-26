"""
scanner/scan_d1.py
D1 scan: score all pairs + compute currency strength.
Runs once daily at midnight UTC. No alerts — D1 provides context for H1/H4.
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

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT = os.path.join(DATA_DIR, "d1_scores.json")
CSM_OUTPUT = os.path.join(DATA_DIR, "csm.json")


def main():
    print(f"\n=== D1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    ohlcv = fetch_all_pairs(PAIRS, "D1")

    d1_results = {}
    now = datetime.datetime.utcnow()

    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None:
            print(f"  {pair}: no data")
            continue

        result = score_pair(df)
        if result is None:
            print(f"  {pair}: insufficient bars")
            continue

        display = pair_display(pair)
        print(f"  {display}: {result['score']:+d} → {result['label']}")

        d1_results[pair] = {
            "score":     result["score"],
            "label":     result["label"],
            "direction": result["direction"],
            "raw":       result["raw"],
            "signals":   result["signals"],
            "updated":   now.isoformat(),
        }

    # ── Currency Strength ────────────────────────────────────────────────────
    print("\n  Computing currency strength...")
    csm = compute_currency_strength(ohlcv)
    for currency, value in csm.items():
        print(f"    {currency}: {value}")

    csm_output = {
        "rankings": csm,
        "updated": now.isoformat(),
    }

    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_results, f, indent=2)

    with open(CSM_OUTPUT, "w") as f:
        json.dump(csm_output, f, indent=2)

    print(f"\n  Saved: {D1_OUTPUT}")
    print(f"  Saved: {CSM_OUTPUT}")
    print("=== D1 Scan complete ===\n")


if __name__ == "__main__":
    main()
