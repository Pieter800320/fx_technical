"""scanner/scan_h4.py — H4 scan, D1+H4 gate
Changes from audit:
  - Removed build_message / send_telegram calls. Telegram is now level-alerts
    only. The old calls were sending empty strings (stub returns "") on every
    qualifying signal — producing blank Telegram messages.
  - Removed find_levels() call. Levels are computed but not used by the
    dashboard and add unnecessary processing per pair per scan.
  - Fixed pct_change calculation: now uses D1 OHLCV bar[-2] (yesterday's
    confirmed close) instead of raw.close from D1 scores (which is the D1
    bar captured at 00:10 UTC — potentially today's opening bar, not yesterday).
  - log_alert retained: feeds alerts.json which powers dashboard headlines.
"""
import json, os, sys, datetime
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, is_pair_active, get_active_sessions
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair, is_extended
from scanner.correlate import compute_correlation
from scanner.cooldown import is_on_cooldown, record_alert
from alerts.news import get_alert_context
from alerts.log import log_alert

def compute_reset_score(ohlcv_closes, period=20, direction='neutral'):
    """
    Mean reversion oscillator. Returns integer 0-100.
    Directionally aware: low score = price reset toward equilibrium (good entry).
    direction='bull'    : oversold/below-mean = low score (reset, good for longs)
    direction='bear'    : overbought/above-mean = low score (reset, good for shorts)
    direction='neutral' : abs() of all components (original behaviour)
    """
    if len(ohlcv_closes) < period + 14:
        return None
    closes = np.array(ohlcv_closes, dtype=float)

    def zscore(arr, n):
        mean = np.mean(arr[-n:])
        std  = np.std(arr[-n:])
        return 0.0 if std == 0 else (arr[-1] - mean) / std

    deltas   = np.diff(closes)
    gains    = np.where(deltas > 0, deltas, 0)
    losses   = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-14:])
    avg_loss = np.mean(losses[-14:])
    rs       = avg_gain / avg_loss if avg_loss != 0 else 100
    rsi      = 100 - (100 / (1 + rs))
    pos_proxy = np.tanh((rsi - 50.0) / 10.0)

    sma20   = np.mean(closes[-period:])
    stretch = np.tanh((closes[-1] - sma20) / sma20) if sma20 != 0 else 0.0

    vol_z = np.tanh(zscore(np.array([np.std(closes[i - period:i])
                                     for i in range(period, len(closes) + 1)]), period))

    roc5  = (closes[-1] - closes[-6])  / closes[-6]  if closes[-6]  != 0 else 0
    roc10 = (closes[-1] - closes[-11]) / closes[-11] if closes[-11] != 0 else 0
    momentum = np.tanh(roc5 * 0.6 + roc10 * 0.4)

    mom_series = np.array([np.tanh(
        ((closes[i] - closes[i - 5])  / closes[i - 5]  if closes[i - 5]  != 0 else 0) * 0.6 +
        ((closes[i] - closes[i - 10]) / closes[i - 10] if closes[i - 10] != 0 else 0) * 0.4
    ) for i in range(10, len(closes))])
    momentum_slow = np.mean(mom_series[-period:]) if len(mom_series) >= period else momentum

    if direction == 'bullish':
        pos_component     = (pos_proxy + 1) / 2
        stretch_component = (stretch + 1) / 2
    elif direction == 'bearish':
        pos_component     = (-pos_proxy + 1) / 2
        stretch_component = (-stretch + 1) / 2
    else:
        pos_component     = abs(pos_proxy)
        stretch_component = abs(stretch)

    mean_rev = (0.40 * pos_component +
                0.30 * stretch_component +
                0.20 * (abs(momentum - momentum_slow) / 2) +
                0.10 * abs(vol_z))
    return int(round(100 * mean_rev))


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


def _get_d1_confirmed_close(pair: str, d1_data: dict) -> float | None:
    """
    Return yesterday's confirmed D1 close price.
    Prefers D1 OHLCV bar[-2] (penultimate bar = confirmed yesterday close).
    Falls back to raw.close from D1 scores if OHLCV not available.
    """
    d1_ohlcv = d1_data.get("_ohlcv", {}).get(pair)
    if d1_ohlcv and len(d1_ohlcv) >= 2:
        return float(d1_ohlcv[-2]["close"])
    # Fallback
    raw_close = d1_data.get(pair, {}).get("raw", {}).get("close")
    return float(raw_close) if raw_close else None


def main():
    print(f"\n=== H4 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    now = datetime.datetime.utcnow()
    day, hour = now.weekday(), now.hour
    market_closed = day == 5 or (day == 6 and hour < 22) or (day == 4 and hour >= 22)
    if market_closed:
        print("  Market closed (weekend) — scoring/alerts run, OHLCV frozen.")

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

        d1_direction = d1_data.get(pair, {}).get("direction", "neutral")
        reset_score = compute_reset_score(df["close"].tolist(), direction=d1_direction)

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
            "adx_weight":  result.get("adx_weight", 1.0),
            "reset_score": reset_score,
            "updated":     now.isoformat(),
        }
        print(f"  {display}: {result['score']:+d} → {label}")

        # ── Alert gate ────────────────────────────────────────────────────────
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

        # Corrected pct_change: use confirmed D1 close (bar[-2]), not raw.close
        h4_close   = result["raw"].get("close")
        d1_conf_close = _get_d1_confirmed_close(pair, d1_data)
        pct_change = None
        if h4_close and d1_conf_close:
            try:
                pct_change = round((float(h4_close) - d1_conf_close) / d1_conf_close * 100, 2)
            except Exception:
                pass

        print(f"    ↳ H4 ALERT: {direction.upper()} — fetching news context...")
        ctx = get_alert_context(pair)

        # Log to alerts.json (feeds dashboard headlines and signal cards)
        log_alert(
            pair=pair, direction=direction,
            h1_label=h1_label, h4_label=label, d1_label=d1_label,
            blurb=ctx["headline"],
            extended=ext_data, regime=regime,
            adx_val=adx_val, atr_ok=result["filter_ok"],
            conflict=result.get("conflict", False),
            structure=result.get("structure", {}),
        )
        record_alert(pair, direction)
        print(f"    ↳ Logged to alerts.json")

    # ── Correlation matrix ────────────────────────────────────────────────────
    print("\n  Computing correlation matrix...")
    corr_result = compute_correlation(ohlcv)
    with open(CORR_OUTPUT, "w") as f:
        json.dump({
            "pairs":    corr_result["pairs"],
            "matrix":   corr_result["matrix"],
            "lookback": 50,
            "updated":  now.isoformat(),
        }, f, indent=2)
    print(f"  Correlation matrix: {len(corr_result['pairs'])} pairs")

    # ── Embed last 100 OHLCV bars per pair ───────────────────────────────────
    if market_closed:
        h4_ohlcv = load_scores(H4_OUTPUT).get("_ohlcv", {})
        print(f"  OHLCV: frozen — {len(h4_ohlcv)} pairs retained from last market close")
    else:
        h4_ohlcv = {}
        try:
            for pair in PAIRS:
                df = ohlcv.get(pair)
                if df is None or len(df) < 2:
                    continue
                bars_list = []
                for ts, row in df.tail(100).iterrows():
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
                    h4_ohlcv[pair] = bars_list
            print(f"  OHLCV: {len(h4_ohlcv)} pairs saved")
        except Exception as e:
            print(f"  [OHLCV] ERROR: {e}")

    h4_output = {**h4_results, "_ohlcv": h4_ohlcv}
    with open(H4_OUTPUT, "w") as f:
        json.dump(h4_output, f, indent=2)
    print(f"\n  Saved: {H4_OUTPUT}")
    print(f"  Saved: {CORR_OUTPUT}")
    print("=== H4 Scan complete ===\n")


if __name__ == "__main__":
    main()
