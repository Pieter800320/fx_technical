"""
scanner/score.py
Upgraded technical scoring engine.

ARCHITECTURE (replaces 6-vote binary system):

  1. Trend       EMA200                    +-1.5  (primary anchor, upweighted)
  2. Momentum    EMA50 / DMI / MACD hist   +-2.0  (one grouped vote, no collinearity)
  3. Condition   RSI graduated             +-2.0  (exhaustion / confirmation quality)
                                           -----
                 Raw max                   +-5.5

  4. ADX weight  0.0 - 1.0   graduated, not binary gate
  5. Structure   multiplier  0.40 - 1.30  (H4 / D1 only, via structure.py)
                 BOS aligned  -> up to x1.30
                 CHOCH        -> down to x0.40
                 Conflict     -> x0.00  (alert killed)

  6. Regime-aware label thresholds
     Ranging / mixed require higher conviction before a label fires.

ATR remains a hard binary filter.
"""

import pandas as pd
import numpy as np

from scanner.structure import detect_structure


# ── Regime-aware label thresholds ────────────────────────────────────────────
THRESHOLDS = {
    "risk_on":  {"strong": 4.5, "signal": 3.0},
    "risk_off": {"strong": 4.5, "signal": 3.0},
    "ranging":  {"strong": 5.5, "signal": 4.0},
    "mixed":    {"strong": 5.5, "signal": 4.0},
    "unknown":  {"strong": 4.5, "signal": 3.0},
}

LABEL_EMOJI = {
    "Strong Buy":  "✅",
    "Buy":         "🟢",
    "Neutral":     "⚪",
    "Sell":        "🔴",
    "Strong Sell": "❌",
    "Conflict":    "⚠️",
    "Filtered":    "⛔",
}


# ────────────────────────────────────────────────────────────────────────────
# Indicator helpers — pure pandas / numpy, no external TA library
# ────────────────────────────────────────────────────────────────────────────

def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))


def _macd(close):
    macd_line   = _ema(close, 12) - _ema(close, 26)
    signal_line = _ema(macd_line, 9)
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def _atr_series(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _dmi(high, low, close, period=14):
    up_move  = high.diff()
    dn_move  = -low.diff()
    plus_dm  = pd.Series(
        np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0),
        index=close.index)
    minus_dm = pd.Series(
        np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0),
        index=close.index)
    atr      = _atr_series(high, low, close, period)
    plus_di  = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx       = (100 * (plus_di - minus_di).abs() /
                (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    adx      = dx.rolling(period).mean()
    return plus_di, minus_di, adx


# ────────────────────────────────────────────────────────────────────────────
# Scoring helpers
# ────────────────────────────────────────────────────────────────────────────

def _adx_weight(adx_val):
    """Graduated ADX confidence weight — not a binary gate."""
    if adx_val is None or np.isnan(adx_val): return 0.0
    if adx_val < 15:  return 0.0
    if adx_val < 20:  return 0.5
    if adx_val < 25:  return 0.75
    return 1.0


def _ema200_score(last, ema200_val):
    """Primary trend anchor — +-1.5, upweighted vs old +-1."""
    return 1.5 if last > ema200_val else -1.5


def _momentum_group_score(ema50_vote, dmi_vote, macd_vote):
    """
    One grouped vote from three collinear momentum signals.
    Majority direction wins.
    Magnitude = 2.0 if all three agree, 1.0 if 2/3.
    Returns (score, direction_int, breakdown_dict).
    """
    votes     = [ema50_vote, dmi_vote, macd_vote]
    total     = sum(votes)
    direction = 1 if total > 0 else (-1 if total < 0 else 0)
    if direction == 0:
        return 0.0, 0, {"ema50": ema50_vote, "dmi": dmi_vote, "macd": macd_vote}
    magnitude = 2.0 if abs(total) == 3 else 1.0
    return float(direction * magnitude), direction, {
        "ema50": ema50_vote, "dmi": dmi_vote, "macd": macd_vote
    }


def _rsi_score(rsi_val):
    """Graduated RSI — measures exhaustion quality, not just side of 50."""
    if rsi_val >= 70:  return  2.0
    if rsi_val >= 60:  return  1.0
    if rsi_val >= 50:  return  0.5
    if rsi_val >= 40:  return -0.5
    if rsi_val >= 30:  return -1.0
    return -2.0


def _macd_histogram_vote(hist_series):
    """MACD histogram acceleration vote — more predictive than crossover."""
    h = hist_series.values
    if len(h) < 3:
        return 0
    if h[-1] > h[-2] > h[-3]:  return  1
    if h[-1] < h[-2] < h[-3]:  return -1
    if h[-1] > h[-2]:          return  1
    if h[-1] < h[-2]:          return -1
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Filter check
# ────────────────────────────────────────────────────────────────────────────

def check_filters(df):
    """ATR hard filter — low participation is genuinely binary."""
    close   = df["close"].astype(float)
    high    = df["high"].astype(float)
    low     = df["low"].astype(float)
    reasons = []
    atr     = _atr_series(high, low, close)
    cur_atr = atr.iloc[-1]
    avg_atr = atr.iloc[-15:-1].mean()
    if avg_atr > 0 and cur_atr < 0.70 * avg_atr:
        reasons.append(f"ATR contracted ({cur_atr:.5f} vs avg {avg_atr:.5f})")
    return (len(reasons) == 0), reasons


# ────────────────────────────────────────────────────────────────────────────
# Extension / exhaustion detection (unchanged from original)
# ────────────────────────────────────────────────────────────────────────────

def is_extended(df, direction):
    """Returns {"extended": bool, "reasons": [...], "atr_dist": float}"""
    if direction == "neutral":
        return {"extended": False, "reasons": [], "atr_dist": 0.0}
    close    = df["close"].astype(float)
    high     = df["high"].astype(float)
    low      = df["low"].astype(float)
    last     = float(close.iloc[-1])
    ema200   = float(_ema(close, 200).iloc[-1])
    rsi      = float(_rsi(close).iloc[-1])
    atr      = float(_atr_series(high, low, close).iloc[-1])
    reasons  = []
    atr_dist = abs(last - ema200) / atr if atr > 0 else 0.0
    if atr_dist > 2.0:
        reasons.append(f"Price {atr_dist:.1f}x ATR from EMA200")
    if direction == "bull" and rsi > 75:
        reasons.append(f"RSI overbought ({rsi:.0f})")
    elif direction == "bear" and rsi < 25:
        reasons.append(f"RSI oversold ({rsi:.0f})")
    ema50_s = _ema(close, 50)
    if direction == "bull":
        consec = sum(1 for i in range(1, 11)
                     if len(close) > i and close.iloc[-i] > ema50_s.iloc[-i])
    else:
        consec = sum(1 for i in range(1, 11)
                     if len(close) > i and close.iloc[-i] < ema50_s.iloc[-i])
    if consec >= 8:
        reasons.append(f"{consec} consecutive bars beyond EMA50")
    return {"extended": len(reasons) > 0, "reasons": reasons,
            "atr_dist": round(atr_dist, 2)}


# ────────────────────────────────────────────────────────────────────────────
# Direction helper
# ────────────────────────────────────────────────────────────────────────────

def score_direction(label):
    if label in ("Buy", "Strong Buy"):   return "bull"
    if label in ("Sell", "Strong Sell"): return "bear"
    return "neutral"


# ────────────────────────────────────────────────────────────────────────────
# Main scoring function
# ────────────────────────────────────────────────────────────────────────────

def score_pair(df, timeframe="H4", regime="unknown", swing_n=5):
    """
    Score a single pair on one timeframe.

    Parameters
    ----------
    df        : OHLCV DataFrame (210+ bars required)
    timeframe : 'H1' | 'H4' | 'D1'
    regime    : string from regime.py — adjusts label thresholds
    swing_n   : pivot lookback for structure detection (default 5)

    Returns
    -------
    dict — backward-compatible with existing JSON schema, plus new fields:
        structure, conflict, raw_score, adx_weight, m_detail
    """
    if len(df) < 210:
        return None

    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    last  = float(close.iloc[-1])

    # ── Compute all indicators once ──────────────────────────────────────────
    ema200_s                        = _ema(close, 200)
    ema50_s                         = _ema(close, 50)
    rsi_s                           = _rsi(close)
    macd_line, sig_line, macd_hist  = _macd(close)
    plus_di, minus_di, adx_s        = _dmi(high, low, close)
    atr_s                           = _atr_series(high, low, close)

    ema200_val = float(ema200_s.iloc[-1])
    ema50_val  = float(ema50_s.iloc[-1])
    rsi_val    = float(rsi_s.iloc[-1])
    adx_val    = float(adx_s.iloc[-1])
    atr_val    = float(atr_s.iloc[-1])
    atr_avg    = float(atr_s.iloc[-15:-1].mean())
    plus_di_v  = float(plus_di.iloc[-1])
    minus_di_v = float(minus_di.iloc[-1])

    # ── ATR hard filter ───────────────────────────────────────────────────────
    passes, filter_reasons = check_filters(df)
    if not passes:
        return {
            "score": 0, "raw_score": 0, "label": "Filtered",
            "filter_reasons": filter_reasons, "signals": {}, "raw": {},
            "passes": False, "adx": round(adx_val, 1),
            "adx_weight": _adx_weight(adx_val),
            "atr_ratio": round(atr_val / max(atr_avg, 1e-8), 2),
            "structure": {"direction": "neutral", "event": "none",
                          "strength": 0.0, "multiplier": 1.0},
            "conflict": False, "m_detail": {},
            "filter_ok": False,
        }

    # ── Signal scores ─────────────────────────────────────────────────────────
    ema200_sc  = _ema200_score(last, ema200_val)
    ema50_vote = 1 if last > ema50_val else -1
    dmi_vote   = 1 if plus_di_v > minus_di_v else -1
    macd_vote  = _macd_histogram_vote(macd_hist)

    momentum_sc, momentum_dir, m_detail = _momentum_group_score(
        ema50_vote, dmi_vote, macd_vote
    )
    rsi_sc = _rsi_score(rsi_val)

    raw_score  = ema200_sc + momentum_sc + rsi_sc

    # ── ADX graduated weight ──────────────────────────────────────────────────
    adx_weight = _adx_weight(adx_val)
    raw_score  = round(raw_score * adx_weight, 2)

    # ── Structure (H4 / D1 only) ──────────────────────────────────────────────
    structure = {"direction": "neutral", "event": "none",
                 "strength": 0.0, "multiplier": 1.0}
    conflict  = False

    if timeframe in ("H4", "D1"):
        structure = detect_structure(df, atr_val, swing_n=swing_n)
        if structure["direction"] != "neutral" and momentum_dir != 0:
            struct_int = 1 if structure["direction"] == "bull" else -1
            if struct_int != momentum_dir:
                conflict  = True
                structure = dict(structure)
                structure["multiplier"] = 0.0

    # ── Apply multiplier ──────────────────────────────────────────────────────
    final_score = round(raw_score * structure["multiplier"], 2)

    # ── Regime-aware label ────────────────────────────────────────────────────
    regime_key = str(regime).lower().split()[0] if regime else "unknown"
    thresh     = THRESHOLDS.get(regime_key, THRESHOLDS["unknown"])

    if conflict:
        label = "Conflict"
    else:
        abs_s = abs(final_score)
        sign  = 1 if final_score >= 0 else -1
        if abs_s >= thresh["strong"]:
            label = "Strong Buy" if sign > 0 else "Strong Sell"
        elif abs_s >= thresh["signal"]:
            label = "Buy" if sign > 0 else "Sell"
        else:
            label = "Neutral"

    # ── Raw values (backward-compatible) ─────────────────────────────────────
    raw = {
        "close":       round(last, 5),
        "ema200":      round(ema200_val, 5),
        "ema50":       round(ema50_val, 5),
        "rsi":         round(rsi_val, 1),
        "macd_line":   round(float(macd_line.iloc[-1]), 6),
        "macd_signal": round(float(sig_line.iloc[-1]), 6),
        "dmi_plus":    round(plus_di_v, 1),
        "dmi_minus":   round(minus_di_v, 1),
        "adx":         round(adx_val, 1),
    }

    # ── Signals dict (backward-compatible + detail for dashboard) ─────────────
    signals = {
        "EMA200":    int(np.sign(ema200_sc)),
        "Momentum":  int(np.sign(momentum_sc)),
        "RSI":       int(np.sign(rsi_sc)),
        "EMA50":     ema50_vote,
        "DMI":       dmi_vote,
        "MACD":      macd_vote,
        "Structure": 0 if timeframe == "H1" else (
            1 if structure["direction"] == "bull" else
            (-1 if structure["direction"] == "bear" else 0)
        ),
    }

    return {
        "score":          final_score,
        "raw_score":      raw_score,
        "label":          label,
        "signals":        signals,
        "raw":            raw,
        "passes":         True,
        "filter_reasons": [],
        "adx":            round(adx_val, 1),
        "adx_weight":     adx_weight,
        "atr_ratio":      round(atr_val / max(atr_avg, 1e-8), 2),
        "conflict":       conflict,
        "structure":      structure,
        "m_detail":       m_detail,
        "filter_ok":      True,
    }


# Backward-compatible alias
score_signals = score_pair
