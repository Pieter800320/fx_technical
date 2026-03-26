"""
scanner/scan_h1.py
H1 scan: score all pairs, apply H4 override conflict logic, fire alerts.

H4 override rule:
  - If H1 is directional (Buy/Sell) AND H4 is opposite direction → suppress alert.
  - If H1 is directional AND H4 agrees OR is neutral → fire.
  - H4 scores are read from data/h4_scores.json (written by scan_h4.py).

Session guard: only alert if the pair is active in the current session.
Cooldown guard: suppress if same pair+direction alerted within 4 hours.
"""

import json
import os
import sys
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, is_pair_active, get_active_sessions
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair
from scanner.cooldown import is_on_cooldown, record_alert
from alerts.news import get_alert_context
from alerts.telegram import build_message, send_telegram
from alerts.log import log_alert

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
H1_OUTPUT  = os.path.join(DATA_DIR, "h1_scores.json")
H4_SCORES  = os.path.join(DATA_DIR, "h4_scores.json")
D1_SCORES  = os.path.join(DATA_DIR, "d1_scores.json")


def load_scores(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    print(f"\n=== H1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── Fetch H1 OHLCV ──────────────────────────────────────────────────────
    ohlcv = fetch_all_pairs(PAIRS, "H1")

    # ── Load H4 and D1 scores for context ───────────────────────────────────
    h4_data = load_scores(H4_SCORES)
    d1_data = load_scores(D1_SCORES)

    # ── Score each pair ──────────────────────────────────────────────────────
    h1_results = {}
    now = datetime.datetime.utcnow()
    active_sessions = get_active_sessions(now)

    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None:
            print(f"  {pair}: no data")
            continue

        result = score_pair(df, timeframe="H1")
        if result is None:
            print(f"  {pair}: insufficient bars")
            continue

        h1_results[pair] = {
            "score":     result["score"],
            "label":     result["label"],
            "direction": result["direction"],
            "raw":       result["raw"],
            "signals":   result["signals"],
            "updated":   now.isoformat(),
        }

        label     = result["label"]
        direction = result["direction"]
        display   = pair_display(pair)

        print(f"  {display}: {result['score']:+d} → {label}")

        # ── Alert logic ──────────────────────────────────────────────────────
        # Filter guard — ADX/ATR filters
        if not result["filter_ok"]:
            for r in result["filter_reasons"]:
                print(f"    ↳ Suppressed: {r}")
            continue

        if direction == "neutral":
            continue

        # Session guard
        if not is_pair_active(pair, now):
            print(f"    ↳ Suppressed: {pair} not active in current session")
            continue

        # H4 override: if H4 is opposite direction → suppress
        h4_dir = h4_data.get(pair, {}).get("direction", "neutral")
        if h4_dir != "neutral" and h4_dir != direction:
            print(f"    ↳ Suppressed: H4 is {h4_dir} (overrides H1 {direction})")
            continue

        # Cooldown guard
        if is_on_cooldown(pair, direction):
            print(f"    ↳ Suppressed: on cooldown")
            continue

        # ── Fire alert ───────────────────────────────────────────────────────
        h4_label = h4_data.get(pair, {}).get("label", "N/A")
        d1_label = d1_data.get(pair, {}).get("label", "N/A")

        print(f"    ↳ ALERT: {direction.upper()} — fetching news context...")
        ctx = get_alert_context(pair)

        msg = build_message(
            pair=pair,
            direction=direction,
            h1_label=label,
            h4_label=h4_label,
            d1_label=d1_label,
            session_names=active_sessions,
            headline=ctx["headline"],
            events=ctx["events"],
        )
        send_telegram(msg)
        record_alert(pair, direction)
        log_alert(pair, direction, label, h4_label, d1_label, ctx["headline"])

    # ── Save H1 scores to JSON (for dashboard) ───────────────────────────────
    with open(H1_OUTPUT, "w") as f:
        json.dump(h1_results, f, indent=2)
    print(f"\n  Saved: {H1_OUTPUT}")
    print("=== H1 Scan complete ===\n")


if __name__ == "__main__":
    main()
