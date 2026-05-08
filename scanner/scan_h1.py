"""scanner/scan_h1.py — H1 scan + level alerts + trade TP/SL alerts"""
import json, os, sys, datetime, calendar as _calendar
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, is_pair_active, get_active_sessions
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair, is_extended
from alerts.telegram import send_level_alert, send_trade_alert

DATA_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
H1_OUTPUT    = os.path.join(DATA_DIR, "h1_scores.json")
H4_SCORES    = os.path.join(DATA_DIR, "h4_scores.json")
D1_SCORES    = os.path.join(DATA_DIR, "d1_scores.json")
REGIME_FILE  = os.path.join(DATA_DIR, "regime.json")
LEVEL_ALERTS = os.path.join(DATA_DIR, "level_alerts.json")
TRADES_FILE  = os.path.join(DATA_DIR, "trades.json")


def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def load_list(path):
    try:
        with open(path) as f: return json.load(f)
    except: return []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _current_price(ohlcv_df):
    """Safely extract latest close from a fetched DataFrame."""
    if ohlcv_df is None or len(ohlcv_df) == 0:
        return None
    row = ohlcv_df.iloc[-1]
    # Twelvedata returns 'close' column — handle both string and float
    try:
        return float(row["close"])
    except Exception:
        return None


# ── Level alert checker ────────────────────────────────────────────────────────
def check_level_alerts(ohlcv: dict):
    """Check price-level alerts against latest H1 close. Fire + deactivate on hit."""
    alerts = load_list(LEVEL_ALERTS)
    if not alerts:
        return

    changed = False
    for a in alerts:
        if not a.get("active"):
            continue
        pair      = a.get("pair")
        price     = a.get("price")
        direction = a.get("direction")   # "above" | "below"
        if not pair or price is None or not direction:
            continue

        current = _current_price(ohlcv.get(pair))
        if current is None:
            continue

        hit = (direction == "above" and current >= price) or \
              (direction == "below" and current <= price)

        if hit:
            print(f"  [Level] ★ {pair} {direction.upper()} {price} HIT at {current}")
            send_level_alert(
                pair=pair, direction=direction,
                alert_price=float(price), current_price=current,
            )
            a["active"]       = False
            a["triggered_at"] = datetime.datetime.utcnow().isoformat()
            changed = True

    if changed:
        save_json(LEVEL_ALERTS, alerts)
        print(f"  [Level] Updated level_alerts.json")


# ── Trade TP/SL checker ────────────────────────────────────────────────────────
def check_trades(ohlcv: dict):
    """
    Check open/pending trades against latest H1 OHLCV bars.
    - Pending: filled when price touches entry
    - Open: TP or SL hit on high/low of bar (not just close — avoids missed wicks)
    Fires Telegram and updates trade status in trades.json.
    """
    trades = load_list(TRADES_FILE)
    if not trades:
        return

    changed = False
    now_iso = datetime.datetime.utcnow().isoformat()

    for t in trades:
        status = t.get("status")
        if status == "closed":
            continue

        pair      = t.get("pair")
        direction = t.get("direction")   # "BUY" | "SELL"
        entry     = t.get("entry")
        sl        = t.get("sl")
        tp        = t.get("tp")
        if not pair or not direction or entry is None:
            continue

        entry = float(entry)
        sl    = float(sl)    if sl is not None else None
        tp    = float(tp)    if tp is not None else None

        df = ohlcv.get(pair)
        if df is None or len(df) == 0:
            continue

        # Use the latest bar's high/low/close for wick-accurate detection
        bar     = df.iloc[-1]
        bar_h   = float(bar["high"])
        bar_l   = float(bar["low"])
        bar_c   = float(bar["close"])

        dec  = 3 if "JPY" in pair else 5
        rr   = None
        if sl and tp:
            risk = abs(entry - sl)
            rwd  = abs(tp - entry)
            rr   = round(rwd / risk, 2) if risk > 0 else None

        # ── Pending → filled ──────────────────────────────────────────────────
        if status == "pending":
            filled = (direction == "BUY"  and bar_h >= entry) or \
                     (direction == "SELL" and bar_l <= entry)
            if filled:
                t["status"] = "open"
                t["opened"] = now_iso
                changed = True
                print(f"  [Trade] ⚡ {pair} {direction} FILLED at {entry:.{dec}f}")
                send_trade_alert(
                    pair=pair, event="filled", direction=direction,
                    price=entry, entry=entry, sl=sl, tp=tp, rr=rr,
                )
                # Fall through to check TP/SL on same bar

        # ── Open → TP or SL ───────────────────────────────────────────────────
        if t.get("status") == "open":
            tp_hit = tp is not None and (
                (direction == "BUY"  and bar_h >= tp) or
                (direction == "SELL" and bar_l <= tp)
            )
            sl_hit = sl is not None and (
                (direction == "BUY"  and bar_l <= sl) or
                (direction == "SELL" and bar_h >= sl)
            )

            # If both on same bar (gap), TP takes priority
            if tp_hit:
                t["status"]      = "closed"
                t["result"]      = "win"
                t["close_price"] = tp
                t["closed"]      = now_iso
                changed = True
                print(f"  [Trade] ✅ {pair} {direction} TP HIT at {tp:.{dec}f}")
                send_trade_alert(
                    pair=pair, event="tp_hit", direction=direction,
                    price=tp, entry=entry, sl=sl, tp=tp, rr=rr,
                )
            elif sl_hit:
                t["status"]      = "closed"
                t["result"]      = "loss"
                t["close_price"] = sl
                t["closed"]      = now_iso
                changed = True
                print(f"  [Trade] ❌ {pair} {direction} SL HIT at {sl:.{dec}f}")
                send_trade_alert(
                    pair=pair, event="sl_hit", direction=direction,
                    price=sl, entry=entry, sl=sl, tp=tp, rr=rr,
                )

    if changed:
        save_json(TRADES_FILE, trades)
        print(f"  [Trade] Updated trades.json")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== H1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    now = datetime.datetime.utcnow()
    day, hour = now.weekday(), now.hour
    market_closed = day == 5 or (day == 6 and hour < 22) or (day == 4 and hour >= 22)
    if market_closed:
        print("  Market closed (weekend) — scoring/alerts run, OHLCV frozen.")

    ohlcv   = fetch_all_pairs(PAIRS, "H1")
    h4_data = load_json(H4_SCORES)
    d1_data = load_json(D1_SCORES)
    h1_results = {}

    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None:
            print(f"  {pair_display(pair)}: no data"); continue
        result = score_pair(df, timeframe="H1")
        if result is None:
            print(f"  {pair_display(pair)}: insufficient bars"); continue

        label     = result["label"]
        direction = result["direction"]
        ext_data  = is_extended(df, direction)

        h1_results[pair] = {
            "score":     result["score"],
            "label":     label,
            "direction": direction,
            "raw":       result["raw"],
            "signals":   result["signals"],
            "filter_ok": result["filter_ok"],
            "extended":  ext_data,
            "updated":   now.isoformat(),
        }
        print(f"  {pair_display(pair)}: {result['score']:+d} → {label}")

    # ── Level alerts ──────────────────────────────────────────────────────────
    check_level_alerts(ohlcv)

    # ── Trade TP/SL alerts ────────────────────────────────────────────────────
    if not market_closed:
        check_trades(ohlcv)
    else:
        print("  [Trade] Skipped — market closed")

    # ── Embed OHLCV ───────────────────────────────────────────────────────────
    if market_closed:
        h1_ohlcv = load_json(H1_OUTPUT).get("_ohlcv", {})
        print(f"  OHLCV: frozen — {len(h1_ohlcv)} pairs retained")
    else:
        h1_ohlcv = {}
        for pair in PAIRS:
            df = ohlcv.get(pair)
            if df is None or len(df) < 2:
                continue
            bars_list = []
            for ts, row in df.tail(100).iterrows():
                try:
                    dt_obj = datetime.datetime.fromisoformat(
                        str(row.get("datetime", ts) if hasattr(row, "get") else ts)
                    )
                    t = _calendar.timegm(dt_obj.timetuple())
                    bars_list.append({
                        "time":  t,
                        "open":  round(float(row["open"]),  6),
                        "high":  round(float(row["high"]),  6),
                        "low":   round(float(row["low"]),   6),
                        "close": round(float(row["close"]), 6),
                    })
                except Exception as e:
                    print(f"    [OHLCV] bar error {pair}: {e}")
            if bars_list:
                h1_ohlcv[pair] = bars_list
        print(f"  OHLCV: {len(h1_ohlcv)} pairs saved")

    save_json(H1_OUTPUT, {**h1_results, "_ohlcv": h1_ohlcv})
    print(f"\n  Saved: {H1_OUTPUT}")
    print("=== H1 Scan complete ===\n")


if __name__ == "__main__":
    main()
