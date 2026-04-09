"""scanner/score.py"""
import pandas as pd
import numpy as np


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
    return macd_line, signal_line

def _atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if not np.isnan(val) else 1.0

def _dmi(high, low, close, period=14):
    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm   = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=close.index)
    minus_dm  = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=close.index)
    atr_vals  = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1).rolling(period).mean()
    plus_di   = 100 * plus_dm.rolling(period).mean() / atr_vals
    minus_di  = 100 * minus_dm.rolling(period).mean() / atr_vals
    dx  = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    adx = dx.rolling(period).mean()
    return plus_di, minus_di, adx

def _swing_structure(close, lookback=20):
    if len(close) < lookback:
        return 0
    recent = close.iloc[-lookback:]
    mid    = lookback // 2
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

    ema200 = _ema(close, 200).iloc[-1]
    signals["EMA200"] = 1 if last > ema200 else -1
    raw["ema200"] = round(float(ema200), 5)

    ema50 = _ema(close, 50).iloc[-1]
    signals["EMA50"] = 1 if last > ema50 else -1
    raw["ema50"] = round(float(ema50), 5)

    rsi_val = _rsi(close).iloc[-1]
    signals["RSI"] = 1 if rsi_val > 50 else -1
    raw["rsi"] = round(float(rsi_val), 1)

    macd_line, signal_line = _macd(close)
    signals["MACD"] = 1 if macd_line.iloc[-1] > signal_line.iloc[-1] else -1
    raw["macd_line"]   = round(float(macd_line.iloc[-1]), 6)
    raw["macd_signal"] = round(float(signal_line.iloc[-1]), 6)

    plus_di, minus_di, adx = _dmi(high, low, close)
    signals["DMI"] = 1 if plus_di.iloc[-1] > minus_di.iloc[-1] else -1
    raw["dmi_plus"]  = round(float(plus_di.iloc[-1]), 1)
    raw["dmi_minus"] = round(float(minus_di.iloc[-1]), 1)
    raw["adx"]       = round(float(adx.iloc[-1]), 1)

    struct = _swing_structure(close, lookback=20) if include_structure else 0
    signals["Structure"] = struct
    raw["structure"] = struct
    raw["close"] = round(float(last), 5)

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
    atr_series = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1).rolling(14).mean()
    cur_atr = atr_series.iloc[-1]
    avg_atr = atr_series.iloc[-15:-1].mean()
    if avg_atr > 0 and cur_atr < 0.70 * avg_atr:
        reasons.append(f"ATR contracted ({cur_atr:.5f} vs avg {avg_atr:.5f})")
    return (len(reasons) == 0), reasons


LABEL_EMOJI = {
    "Strong Buy":  "✅", "Buy": "🟢", "Neutral": "⚪",
    "Sell": "🔴", "Strong Sell": "❌",
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
    include_structure = timeframe in ("H4", "D1")
    passes, reasons   = check_filters(df)
    signals, raw      = calculate_signals(df, include_structure)
    total, label      = compute_score(signals)
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


def is_extended(df, direction):
    """Returns {"extended": bool, "reasons": [...], "atr_dist": float}"""
    if direction == "neutral":
        return {"extended": False, "reasons": [], "atr_dist": 0.0}

    close  = df["close"].astype(float)
    high   = df["high"].astype(float)
    low    = df["low"].astype(float)
    last   = float(close.iloc[-1])
    ema200 = float(_ema(close, 200).iloc[-1])
    rsi    = float(_rsi(close).iloc[-1])
    atr    = _atr(high, low, close)
    reasons = []

    atr_dist = abs(last - ema200) / atr if atr > 0 else 0.0
    if atr_dist > 2.0:
        reasons.append(f"Price {atr_dist:.1f}× ATR from EMA200")

    if direction == "bull" and rsi > 75:
        reasons.append(f"RSI overbought ({rsi:.0f})")
    elif direction == "bear" and rsi < 25:
        reasons.append(f"RSI oversold ({rsi:.0f})")

    ema50_series = _ema(close, 50)
    if direction == "bull":
        consecutive = sum(1 for i in range(1, 11) if len(close) > i and close.iloc[-i] > ema50_series.iloc[-i])
    else:
        consecutive = sum(1 for i in range(1, 11) if len(close) > i and close.iloc[-i] < ema50_series.iloc[-i])

    if consecutive >= 8:
        reasons.append(f"{consecutive} consecutive bars beyond EMA50")

    return {
        "extended": len(reasons) > 0,
        "reasons":  reasons,
        "atr_dist": round(atr_dist, 2),
    }
