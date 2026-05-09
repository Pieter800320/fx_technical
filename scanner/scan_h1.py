"""scanner/scan_h1.py — H1 scan + level alerts + trade TP/SL alerts"""
import json, os, sys, datetime, calendar as _calendar
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, is_pair_active, get_active_sessions
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair, is_extended
from alerts.telegram import send_level_alert, send_trade_alert, send_sma_alert

SMA_STATE    = os.path.join(DATA_DIR, "sma_alert_state.json")

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


# ── SMA12 momentum alignment ──────────────────────────────────────────────────
def _sma12_direction(ohlcv_df):
    """
    Compute SMA12 fast (current) and slow (1 bar ago).
    Returns 'UP' if fast > slow, 'DOWN' if fast < slow, None if insufficient data.
    """
    if ohlcv_df is None or len(ohlcv_df) < 14:
        return None, None, None
    closes = ohlcv_df["close"].astype(float).tolist()
    if len(closes) < 14:
        return None, None, None
    fast = sum(closes[-12:]) / 12           # SMA12 of last 12 bars
    slow = sum(closes[-13:-1]) / 12         # SMA12 shifted back 1 bar
    direction = "UP" if fast > slow else "DOWN" if fast < slow else None
    return direction, fast, slow


def check_sma_alignment(ohlcv: dict, h1_results: dict):
    """
    Fire a Telegram alert when:
    - H1 has a fresh SMA12 crossover on the current bar
    - D1 and H4 SMA12 momentum point the same direction
    - This direction hasn't been fired for this pair before (state tracking)
    """
    state = load_list(SMA_STATE) if os.path.exists(SMA_STATE) else []
    # Convert state list to dict for easy lookup: {pair: last_direction}
    state_map = {s["pair"]: s["direction"] for s in state} if isinstance(state, list) else state

    h4_scores = load_json(H4_SCORES)
    d1_scores = load_json(D1_SCORES)
    news_brief_path = os.path.join(DATA_DIR, "news_brief.json")
    news_brief = load_json(news_brief_path)
    edge_scores = news_brief.get("edge_scores", {}) if news_brief else {}

    changed = False

    for pair in PAIRS:
        # ── H1: detect fresh crossover ────────────────────────────────────────
        h1_df = ohlcv.get(pair)
        if h1_df is None or len(h1_df) < 15:
            continue

        # Current bar direction
        h1_dir, h1_fast, h1_slow = _sma12_direction(h1_df)
        if h1_dir is None:
            continue

        # Previous bar direction (drop last row)
        prev_dir, _, _ = _sma12_direction(h1_df.iloc[:-1])

        # Fresh crossover = direction changed on this bar
        if prev_dir is None or h1_dir == prev_dir:
            continue  # No crossover — skip

        # ── D1 and H4: just direction, no crossover needed ────────────────────
        h4_ohlcv_key = h4_scores.get("_ohlcv", {})
        d1_ohlcv_key = d1_scores.get("_ohlcv", {})

        # Build DataFrames from stored OHLCV bars
        def bars_to_df(bars):
            if not bars:
                return None
            import pandas as pd
            df = pd.DataFrame(bars)
            df["close"] = df["close"].astype(float)
            return df

        h4_df = bars_to_df(h4_ohlcv_key.get(pair))
        d1_df = bars_to_df(d1_ohlcv_key.get(pair))

        h4_dir, _, _ = _sma12_direction(h4_df)
        d1_dir, _, _ = _sma12_direction(d1_df)

        if h4_dir is None or d1_dir is None:
            continue

        # All three must agree
        if not (h1_dir == h4_dir == d1_dir):
            continue

        direction = h1_dir

        # ── State check: only fire if direction changed ───────────────────────
        last_fired = state_map.get(pair)
        if last_fired == direction:
            continue  # Already fired for this direction

        # ── Gather context for message ────────────────────────────────────────
        d1_label = d1_scores.get(pair, {}).get("label", "—")
        h4_label = h4_scores.get(pair, {}).get("label", "—")
        h1_label = h1_results.get(pair, {}).get("label", "—")
        edge     = edge_scores.get(pair.replace("/", ""))
        adx      = h4_scores.get(pair, {}).get("raw", {}).get("adx")

        print(f"  [SMA] ★ {pair} ALL TFs {direction} — firing alert")
        send_sma_alert(
            pair=pair, direction=direction,
            d1_label=d1_label, h4_label=h4_label, h1_label=h1_label,
            edge=edge, adx=float(adx) if adx else None,
        )

        # Update state
        state_map[pair] = direction
        changed = True

    if changed:
        new_state = [{"pair": p, "direction": d} for p, d in state_map.items()]
        save_json(SMA_STATE, new_state)
        print("  [SMA] Updated sma_alert_state.json")
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

    # ── SMA12 triple-TF alignment ─────────────────────────────────────────────
    if not market_closed:
        check_sma_alignment(ohlcv, h1_results)
    else:
        print("  [SMA] Skipped — market closed")

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
            for ts, row in df.tail(2000).iterrows():
                try:
                    dt_obj = datetime.datetime.fromisoformat(
                        str(row.get("datetime", ts) if hasattr(row, "get") else ts)
                    )
                    t = _calendar.timegm(dt_obj.timetuple())
                    bars_list.append({
                        "time":   t,
                        "open":   round(float(row["open"]),  6),
                        "high":   round(float(row["high"]),  6),
                        "low":    round(float(row["low"]),   6),
                        "close":  round(float(row["close"]), 6),
                        "volume": int(float(row.get("volume", 0) or 0)),
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
