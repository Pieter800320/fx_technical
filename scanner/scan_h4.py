"""
scanner/scan_h4.py
H4 scan — fires when D1 + H4 agree in direction.
D1 acts as the bias gate. H4 is the confirmation trigger.
Shared cooldown key with H1 (same pair+direction = one alert per 4 hours).
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

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
H4_OUTPUT = os.path.join(DATA_DIR, "h4_scores.json")
H1_SCORES = os.path.join(DATA_DIR, "h1_scores.json")
D1_SCORES = os.path.join(DATA_DIR, "d1_scores.json")


def load_scores(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    print(f"\n=== H4 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    ohlcv    = fetch_all_pairs(PAIRS, "H4")
    h1_data  = load_scores(H1_SCORES)
    d1_data  = load_scores(D1_SCORES)

    h4_results = {}
    now             = datetime.datetime.utcnow()
    active_sessions = get_active_sessions(now)

    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None:
            print(f"  {pair_display(pair)}: no data")
            continue

        result = score_pair(df, timeframe="H4")
        if result is None:
            print(f"  {pair_display(pair)}: insufficient bars")
            continue

        label     = result["label"]
        direction = result["direction"]
        display   = pair_display(pair)

        h4_results[pair] = {
            "score":     result["score"],
            "label":     label,
            "direction": direction,
            "raw":       result["raw"],
            "signals":   result["signals"],
            "filter_ok": result["filter_ok"],
            "updated":   now.isoformat(),
        }

        print(f"  {display}: {result['score']:+d} → {label}")

        if direction == "neutral":
            continue

        # ── D1 gate: D1 must agree ────────────────────────────────────────────
        d1_dir   = d1_data.get(pair, {}).get("direction", "neutral")
        d1_label = d1_data.get(pair, {}).get("label", "N/A")
        if d1_dir != direction:
            print(f"    ↳ Suppressed: D1 is {d1_dir} — bias does not confirm H4 {direction}")
            continue

        # ── ADX/ATR filter ────────────────────────────────────────────────────
        if not result["filter_ok"]:
            for r in result["filter_reasons"]:
                print(f"    ↳ Suppressed: {r}")
            continue

        # ── Session guard ─────────────────────────────────────────────────────
        if not is_pair_active(pair, now):
            print(f"    ↳ Suppressed: {display} not active in current session")
            continue

        # ── Shared cooldown (same key as H1) ──────────────────────────────────
        if is_on_cooldown(pair, direction):
            print(f"    ↳ Suppressed: on cooldown")
            continue

        # ── Fire ──────────────────────────────────────────────────────────────
        h1_label = h1_data.get(pair, {}).get("label", "N/A")
        adx_val  = result["raw"].get("adx")
        atr_ok   = result["filter_ok"]

        print(f"    ↳ H4 ALERT: {direction.upper()} (D1+H4 aligned) — fetching news context...")
        ctx = get_alert_context(pair)

        msg = build_message(
            pair=pair,
            direction=direction,
            h1_label=h1_label,
            h4_label=label,
            d1_label=d1_label,
            session_names=active_sessions,
            adx_val=adx_val,
            atr_ok=atr_ok,
            headline=ctx["headline"],
            events=ctx["events"],
        )
        send_telegram(msg)
        record_alert(pair, direction)
        log_alert(pair, direction, h1_label, label, d1_label, ctx["headline"])

    with open(H4_OUTPUT, "w") as f:
        json.dump(h4_results, f, indent=2)
    print(f"\n  Saved: {H4_OUTPUT}")
    print("=== H4 Scan complete ===\n")


if __name__ == "__main__":
    main()
