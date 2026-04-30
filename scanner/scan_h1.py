"""scanner/scan_h1.py — H1 scan + level alert checker"""
import json, os, sys, datetime
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, is_pair_active, get_active_sessions
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair, is_extended
from alerts.telegram import send_level_alert

DATA_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
H1_OUTPUT    = os.path.join(DATA_DIR, "h1_scores.json")
H4_SCORES    = os.path.join(DATA_DIR, "h4_scores.json")
D1_SCORES    = os.path.join(DATA_DIR, "d1_scores.json")
REGIME_FILE  = os.path.join(DATA_DIR, "regime.json")
LEVEL_ALERTS = os.path.join(DATA_DIR, "level_alerts.json")

def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def check_level_alerts(ohlcv_latest: dict):
    """Read level_alerts.json, fire Telegram for any triggered levels."""
    try:
        with open(LEVEL_ALERTS) as f:
            alerts = json.load(f)
    except FileNotFoundError:
        return  # No alert file yet — frontend hasn't saved any
    except Exception as e:
        print(f"  [Alerts] Read error: {e}"); return

    changed = False
    for a in alerts:
        if not a.get("active"):
            continue
        pair = a.get("pair")
        price = a.get("price")
        direction = a.get("direction")  # "above" or "below"
        if not pair or not price or not direction:
            continue
        df = ohlcv_latest.get(pair)
        if df is None or len(df) < 1:
            continue
        try:
            current = float(df.iloc[-1]["close"])
        except Exception:
            continue
        hit = (direction == "above" and current >= price) or \
              (direction == "below" and current <= price)
        if hit:
            print(f"  [Alerts] ★ {pair} {direction.upper()} {price} HIT at {current:.5f}")
            send_level_alert(pair=pair, direction=direction,
                             alert_price=price, current_price=current)
            a["active"] = False
            a["triggered_at"] = datetime.datetime.utcnow().isoformat()
            changed = True

    if changed:
        try:
            with open(LEVEL_ALERTS, "w") as f:
                json.dump(alerts, f, indent=2)
        except Exception as e:
            print(f"  [Alerts] Write error: {e}")


def main():
    print(f"\n=== H1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    now = datetime.datetime.utcnow()
    day, hour = now.weekday(), now.hour
    market_closed = day == 5 or (day == 6 and hour < 22) or (day == 4 and hour >= 22)
    if market_closed:
        print("  Market closed (weekend) — scoring/alerts run, OHLCV frozen.")

    ohlcv  = fetch_all_pairs(PAIRS, "H1")
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
        display   = pair_display(pair)
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
        print(f"  {display}: {result['score']:+d} → {label}")

    # ── Level alert check ─────────────────────────────────────────────────────
    check_level_alerts(ohlcv)

    # ── Embed last 100 OHLCV bars per pair inside h1_scores.json ─────────────
    if market_closed:
        h1_ohlcv = load_json(H1_OUTPUT).get("_ohlcv", {})
        print(f"  OHLCV: frozen — {len(h1_ohlcv)} pairs retained from last market close")
    else:
        h1_ohlcv = {}
        try:
            for pair in PAIRS:
                df = ohlcv.get(pair)
                if df is None or len(df) < 2:
                    continue
                bars = df.tail(100).copy()
                bars_list = []
                for ts, row in bars.iterrows():
                    try:
                        import calendar, datetime as _dt
                        dt_raw = row.get("datetime") if hasattr(row, "get") else str(ts)
                        dt_obj = _dt.datetime.fromisoformat(str(dt_raw))
                        t = calendar.timegm(dt_obj.timetuple())
                        bars_list.append({
                            "time":  t,
                            "open":  round(float(row["open"]),  6),
                            "high":  round(float(row["high"]),  6),
                            "low":   round(float(row["low"]),   6),
                            "close": round(float(row["close"]), 6),
                        })
                    except Exception as bar_err:
                        print(f"    [OHLCV] bar error {pair}: {bar_err}")
                        continue
                if bars_list:
                    h1_ohlcv[pair] = bars_list
            print(f"  OHLCV: {len(h1_ohlcv)} pairs saved")
        except Exception as e:
            print(f"  [OHLCV] ERROR: {e}")

    h1_output = {**h1_results, "_ohlcv": h1_ohlcv}
    with open(H1_OUTPUT, "w") as f:
        json.dump(h1_output, f, indent=2)
    print(f"\n  Saved: {H1_OUTPUT}")
    print("=== H1 Scan complete ===\n")

if __name__ == "__main__":
    main()
