"""scanner/bb.py — Bollinger Band touch detection + reversal quality scoring.

Called from scan_h4.py on every H4 close.
Produces:
  - Band touch alerts  (Message 1) when H4 wick touches upper/lower BB
  - Midline alerts     (Message 2) when H4 wick touches 20-SMA after a band touch

State persisted in data/bb_state.json:
  { "EURUSD": { "band": "upper"|"lower", "touch_time": <iso>, "touch_price": <float>,
                "midline_sent": false } }
"""

import json, math, os, datetime
import numpy as np

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
STATE_FILE = os.path.join(DATA_DIR, "bb_state.json")

BB_PERIOD = 20
BB_STD    = 2.0


# ── Bollinger Band computation ────────────────────────────────────────────────

def compute_bb(closes: list, period: int = BB_PERIOD, std_mult: float = BB_STD):
    """Return (upper, mid, lower) for the last bar. None if insufficient data."""
    if len(closes) < period:
        return None, None, None
    arr   = np.array(closes[-period:], dtype=float)
    mid   = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1))
    return mid + std_mult * sigma, mid, mid - std_mult * sigma


# ── 1212 Momentum (port of dashboard JS) ─────────────────────────────────────

def _atr14(df) -> float:
    """Simple ATR14 from DataFrame with high/low/close columns."""
    highs  = df["high"].astype(float).values
    lows   = df["low"].astype(float).values
    closes = df["close"].astype(float).values
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i]  - closes[i - 1]))
        trs.append(tr)
    if len(trs) < 14:
        return 0.0
    return float(np.mean(trs[-14:]))


def _mom1212_raw(closes: list) -> float:
    """Raw 1212 momentum value (pre-sigmoid). Requires ≥ 24 closes."""
    if len(closes) < 24:
        return 0.0
    sma_now  = sum(closes[-12:])  / 12
    sma_past = sum(closes[-24:-12]) / 12
    # ATR approximation from closes only (no high/low in this path)
    diffs = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    atr   = float(np.mean(diffs[-14:])) if len(diffs) >= 14 else 0.0
    if atr == 0:
        return 0.0
    return (sma_now - sma_past) / (12 * atr)


def _norm1212(m: float) -> int:
    """Sigmoid normaliser → 0-100 (50 = neutral)."""
    e = math.exp(5.6 * m)
    return round(50 + 50 * (e - 1) / (e + 1))


def compute_mom1212(df, lb: int = 30):
    """
    Return (current_score, prev_score, delta) as ints (0-100).
    lb: lookback offset in bars for the 'previous' reading.
    """
    closes = df["close"].astype(float).tolist()
    if len(closes) < 24 + lb:
        return None, None, None
    cur  = _norm1212(_mom1212_raw(closes))
    prev = _norm1212(_mom1212_raw(closes[:-lb])) if lb > 0 else None
    delta = (cur - prev) if prev is not None else None
    return cur, prev, delta


# ── ADX direction (rising or falling) ────────────────────────────────────────

def adx_direction(df) -> str:
    """↑ if ADX rose over last 3 bars, ↓ if fell, → if flat."""
    from scanner.score import _dmi
    _, _, adx_s = _dmi(df["high"].astype(float),
                        df["low"].astype(float),
                        df["close"].astype(float))
    adx = adx_s.dropna().values
    if len(adx) < 3:
        return "→"
    if adx[-1] > adx[-3] + 0.5:
        return "↑"
    if adx[-1] < adx[-3] - 0.5:
        return "↓"
    return "→"


# ── Reversal quality score ────────────────────────────────────────────────────

def _tier1_pass(d1_mom, w1_mom, csm_base, csm_quote, regime, regime_conf) -> int:
    """Return number of Tier-1 conditions met (out of 6)."""
    score = 0
    if regime in ("Mixed", "Ranging"):
        score += 1
    if regime_conf != "High":
        score += 1
    if d1_mom is not None and 38 <= d1_mom <= 62:
        score += 1
    if w1_mom is not None and 35 <= w1_mom <= 65:
        score += 1
    if csm_base is not None and 40 <= csm_base <= 60:
        score += 1
    if csm_quote is not None and 40 <= csm_quote <= 60:
        score += 1
    return score


def compute_quality(h4_mom, h4_delta, d1_mom, d1_delta, w1_mom,
                    setup_pct, adx_val, adx_dir,
                    edge, extended, conflict,
                    csm_base, csm_quote,
                    regime, regime_conf, h1_mom, h1_delta) -> dict:
    """
    Compute composite reversal quality score and rating.
    Returns dict: { score, tier1, tier2, tier3, rating, rating_emoji, warnings }
    """
    warnings = []

    # Tier 1 — context
    tier1 = _tier1_pass(d1_mom, w1_mom, csm_base, csm_quote, regime, regime_conf)
    if tier1 < 4:
        warnings.append(f"Context weak ({tier1}/6 Tier-1)")

    # Tier 2 — trigger quality (0-5)
    t2 = 0
    if h4_mom is not None:
        d = abs(h4_mom - 50)
        if d <= 8:    t2 += 3   # 42-58: sweet spot
        elif d <= 15: t2 += 2   # 35-65: acceptable
        elif d <= 22: t2 += 1   # 28-72: caution
    if h4_delta is not None and h4_delta < 0:
        t2 += 1   # decelerating toward 50
    if adx_val is not None and adx_val < 25 and adx_dir in ("↓", "→"):
        t2 += 1

    # Tier 3 — conviction (0-5)
    t3 = 0
    if h1_mom is not None and h1_delta is not None and h1_delta < 0:
        t3 += 1   # H1 already turning
    if d1_mom is not None and d1_delta is not None and d1_delta < 0:
        t3 += 1   # D1 also decelerating
    if edge is not None and edge >= 7:
        t3 += 1
    if extended:
        t3 += 1
    if conflict:
        t3 += 1

    total = t2 + t3

    if total >= 8:
        rating, emoji = "AA", "🔴"
    elif total >= 5:
        rating, emoji = "BB", "🟡"
    else:
        rating, emoji = "CC", "⚪"

    if tier1 < 4:
        rating = "CC"
        emoji  = "⚪"

    return {
        "score":        total,
        "tier1":        tier1,
        "tier2":        t2,
        "tier3":        t3,
        "rating":       rating,
        "rating_emoji": emoji,
        "warnings":     warnings,
    }


# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Main detection function ───────────────────────────────────────────────────

def detect_bb_events(pair: str, df, h4_result: dict,
                     d1_data: dict, h1_data: dict,
                     csm: dict, regime: dict, news: dict,
                     now: datetime.datetime) -> list:
    """
    Check for BB wick touches and midline touches for one pair.
    Returns list of event dicts:
      { "type": "band"|"midline", "pair": ..., "band": "upper"|"lower",
        ... all fields needed for Telegram message }
    """
    if df is None or len(df) < BB_PERIOD + 14:
        return []

    closes = df["close"].astype(float).tolist()
    highs  = df["high"].astype(float).tolist()
    lows   = df["low"].astype(float).tolist()

    upper, mid, lower = compute_bb(closes)
    if upper is None:
        return []

    last_high  = highs[-1]
    last_low   = lows[-1]
    last_close = closes[-1]
    dec        = 3 if "JPY" in pair else 5
    display    = pair.replace("/", "")

    # ── Determine band touch ──────────────────────────────────────────────────
    upper_touch = last_high >= upper
    lower_touch = last_low  <= lower
    mid_touch   = last_low  <= mid <= last_high   # wick spans the midline

    # ── Load scoring inputs ───────────────────────────────────────────────────
    h4_raw     = h4_result.get("raw", {})
    adx_val    = h4_raw.get("adx")
    setup_raw  = h4_result.get("score", 0)       # raw signed score
    setup_pct  = h4_result.get("reset_score")    # mean-reversion oscillator (0-100)
    extended   = h4_result.get("extended", {}).get("extended", False)
    conflict   = h4_result.get("conflict", False)

    adx_dir    = adx_direction(df)

    # H4 MOM
    h4_mom, h4_mom_prev, h4_delta = compute_mom1212(df, lb=30)

    # D1 MOM
    d1_ohlcv = d1_data.get("_ohlcv", {}).get(pair)
    d1_mom = d1_delta = None
    if d1_ohlcv and len(d1_ohlcv) >= 30:
        import pandas as pd
        d1_df = pd.DataFrame(d1_ohlcv)
        d1_mom, _, d1_delta = compute_mom1212(d1_df, lb=5)

    # W1 MOM (aggregate from D1 bars)
    w1_mom = None
    if d1_ohlcv and len(d1_ohlcv) >= 28:
        # Build weekly closes: every 5th D1 bar
        w1_closes = [b["close"] for b in d1_ohlcv[::5]]
        if len(w1_closes) >= 24:
            w1_mom = _norm1212(_mom1212_raw(w1_closes))

    # H1 MOM
    h1_ohlcv = h1_data.get("_ohlcv", {}).get(pair)
    h1_mom = h1_delta = None
    if h1_ohlcv and len(h1_ohlcv) >= 154:
        import pandas as pd
        h1_df = pd.DataFrame(h1_ohlcv)
        h1_mom, _, h1_delta = compute_mom1212(h1_df, lb=120)

    # CSM — H4 rankings preferred
    rankings   = csm.get("h4_rankings") or csm.get("rankings", {})
    currencies = pair.split("/")
    csm_base   = rankings.get(currencies[0]) if len(currencies) == 2 else None
    csm_quote  = rankings.get(currencies[1]) if len(currencies) == 2 else None

    # Regime
    fr          = regime.get("final_regime", {})
    reg_label   = fr.get("regime", "Mixed")
    reg_conf    = fr.get("confidence", "Low")
    reg_score   = fr.get("score")

    # Edge
    edge_key    = display
    edge_val    = news.get("edge_scores", {}).get(edge_key)

    # Quality score
    quality = compute_quality(
        h4_mom=h4_mom, h4_delta=h4_delta,
        d1_mom=d1_mom, d1_delta=d1_delta,
        w1_mom=w1_mom,
        setup_pct=setup_pct, adx_val=adx_val, adx_dir=adx_dir,
        edge=edge_val, extended=extended, conflict=conflict,
        csm_base=csm_base, csm_quote=csm_quote,
        regime=reg_label, regime_conf=reg_conf,
        h1_mom=h1_mom, h1_delta=h1_delta,
    )

    # Shared payload used by both message builders
    payload = {
        "pair":        pair,
        "display":     display,
        "dec":         dec,
        "upper":       round(upper, dec),
        "mid":         round(mid, dec),
        "lower":       round(lower, dec),
        "close":       round(last_close, dec),
        "h4_mom":      h4_mom,
        "h4_delta":    h4_delta,
        "d1_mom":      d1_mom,
        "d1_delta":    d1_delta,
        "w1_mom":      w1_mom,
        "h1_mom":      h1_mom,
        "h1_delta":    h1_delta,
        "setup_pct":   setup_pct,
        "adx_val":     adx_val,
        "adx_dir":     adx_dir,
        "edge":        edge_val,
        "extended":    extended,
        "conflict":    conflict,
        "csm_base":    csm_base,
        "csm_quote":   csm_quote,
        "csm_labels":  currencies if len(currencies) == 2 else ["?", "?"],
        "regime":      reg_label,
        "reg_conf":    reg_conf,
        "quality":     quality,
        "now":         now.strftime("%Y-%m-%d %H:%M"),
    }

    state  = load_state()
    key    = display
    events = []

    # ── Band touch ───────────────────────────────────────────────────────────
    if upper_touch or lower_touch:
        band = "upper" if upper_touch else "lower"
        touch_price = round(last_high if upper_touch else last_low, dec)
        # Only fire if not already tracking this band for this pair
        existing = state.get(key, {})
        if existing.get("band") != band:
            state[key] = {
                "band":          band,
                "touch_time":    now.isoformat(),
                "touch_price":   touch_price,
                "midline_sent":  False,
            }
            events.append({**payload,
                           "type":        "band",
                           "band":        band,
                           "touch_price": touch_price})

    # ── Midline touch (only if we have a pending band touch) ─────────────────
    elif mid_touch and key in state and not state[key].get("midline_sent", True):
        entry      = state[key]
        touch_time = datetime.datetime.fromisoformat(entry["touch_time"])
        elapsed    = now - touch_time
        hours, rem = divmod(int(elapsed.total_seconds()), 3600)
        mins       = rem // 60
        elapsed_str = f"{hours}h {mins:02d}m" if hours else f"{mins}m"

        events.append({**payload,
                       "type":         "midline",
                       "band":         entry["band"],
                       "touch_price":  entry["touch_price"],
                       "elapsed":      elapsed_str})

        state[key]["midline_sent"] = True

    # ── Clear state if price is well inside the bands again ──────────────────
    elif key in state:
        # Reset when close is comfortably inside (>25% of band width from either band)
        band_width = upper - lower
        margin     = band_width * 0.25
        if lower + margin < last_close < upper - margin:
            # If midline already sent (trade complete) → clear
            if state[key].get("midline_sent"):
                del state[key]

    save_state(state)
    return events
