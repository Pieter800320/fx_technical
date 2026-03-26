"""
scanner/score.py
Revised technical scoring engine — 6 independent signals + 2 hard filters.

SIGNALS (each +1 bull / -1 bear):
  1. Price vs EMA200   — long-term bias
  2. Price vs EMA50    — medium-term bias
  3. RSI vs 50 line    — momentum direction (not overbought/oversold)
  4. MACD line vs signal line — momentum confirmation
  5. DMI+ vs DMI-      — directional pressure
  6. Structure         — swing high/low behaviour (H4/D1 only, neutral on H1)

HARD FILTERS (suppress alert entirely, not scored):
  ADX < 20            — no trend, no trade
  ATR < 70% of avg    — contracted/low participation market

Score thresholds:
  +5 to +6  -> Strong Buy
  +3 to +4  -> Buy
  -2 to +2  -> Neutral
  -3 to -4  -> Sell
  -5 to -6  -> Strong Sell
"""

import pandas as pd
import numpy as np


def _ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _macd(close):
    macd_line = _ema(close, 12) - _ema(close, 26)
    signal_line = _ema(macd_line, 9)
    return macd_line, signal_line


def _atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _dmi(high, low, close, period=14):
    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm   = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=close.index)
    minus_dm  = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=close.index)
    atr_vals  = _atr(high, low, close, period)
    plus_di   = 100 * plus_dm.rolling(period).mean() / atr_vals
    minus_di  = 100 * minus_dm.rolling(period).mean() / atr_vals
    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    adx = dx.rolling(period).mean()
    return plus_di, minus_di, adx


def _swing_structure(close, lookback=20):
    if len(close) < lookback:
        return 0
    recent = close.iloc[-lookback:]
    mid = lookback // 2
    first  = recent.iloc[:mid]
    second = recent.iloc[mid:]
    if second.max() > first.max() and second.min() > first.min():
        return 1
    if second.max() < first.max() and second.min() < first.min():
        return -1
    return 0


def calculate_signals(df, include_structure=True):
    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    last  = close.iloc[-1]
    signals, raw = {}, {}

    # 1. EMA200 — long-term bias
    ema200 = _ema(close, 200).iloc[-1]
    signals["EMA200"] = 1 if last > ema200 else -1
    raw["ema200"] = round(ema200, 5)

    # 2. EMA50 — medium-term bias
    ema50 = _ema(close, 50).iloc[-1]
    signals["EMA50"] = 1 if last > ema50 else -1
    raw["ema50"] = round(ema50, 5)

    # 3. RSI vs 50 — momentum direction
    rsi_val = _rsi(close).iloc[-1]
    signals["RSI"] = 1 if rsi_val > 50 else -1
    raw["rsi"] = round(rsi_val, 1)

    # 4. MACD line vs signal line
    macd_line, signal_line = _macd(close)
    signals["MACD"] = 1 if macd_line.iloc[-1] > signal_line.iloc[-1] else -1
    raw["macd_line"]   = round(macd_line.iloc[-1], 6)
    raw["macd_signal"] = round(signal_line.iloc[-1], 6)

    # 5. DMI+ vs DMI-
    plus_di, minus_di, adx = _dmi(high, low, close)
    signals["DMI"] = 1 if plus_di.iloc[-1] > minus_di.iloc[-1] else -1
    raw["dmi_plus"]  = round(plus_di.iloc[-1], 1)
    raw["dmi_minus"] = round(minus_di.iloc[-1], 1)
    raw["adx"]       = round(adx.iloc[-1], 1)

    # 6. Structure — H4/D1 only
    struct = _swing_structure(close, lookback=20) if include_structure else 0
    signals["Structure"] = struct
    raw["structure"] = struct

    raw["close"] = round(last, 5)
    return signals, raw


def check_filters(df):
    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    reasons = []

    _, _, adx = _dmi(high, low, close)
    adx_val = adx.iloc[-1]
    if adx_val < 20:
        reasons.append(f"ADX {adx_val:.1f} < 20 (no trend)")

    atr = _atr(high, low, close)
    cur_atr = atr.iloc[-1]
    avg_atr = atr.iloc[-15:-1].mean()
    if avg_atr > 0 and cur_atr < 0.70 * avg_atr:
        reasons.append(f"ATR contracted ({cur_atr:.5f} vs avg {avg_atr:.5f})")

    return (len(reasons) == 0), reasons


LABEL_EMOJI = {
    "Strong Buy":  "✅",
    "Buy":         "🟢",
    "Neutral":     "⚪",
    "Sell":        "🔴",
    "Strong Sell": "❌",
}


def compute_score(signals):
    total = sum(signals.values())
    if total >= 5:   label = "Strong Buy"
    elif total >= 3: label = "Buy"
    elif total <= -5: label = "Strong Sell"
    elif total <= -3: label = "Sell"
    else:            label = "Neutral"
    return total, label


def score_direction(label):
    if label in ("Buy", "Strong Buy"):   return "bull"
    if label in ("Sell", "Strong Sell"): return "bear"
    return "neutral"


def score_pair(df, timeframe="H4"):
    if len(df) < 210:
        return None

    include_structure  = timeframe in ("H4", "D1")
    passes, reasons    = check_filters(df)
    signals, raw       = calculate_signals(df, include_structure)
    total, label       = compute_score(signals)

    return {
        "signals":        signals,
        "raw":            raw,
        "score":          total,
        "label":          label,
        "direction":      score_direction(label),
        "emoji":          LABEL_EMOJI[label],
        "filter_ok":      passes,
        "filter_reasons": reasons,
    }
