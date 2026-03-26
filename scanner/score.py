"""
scanner/score.py
Technical indicator suite → numeric score → label.

8 signals scored +1 (bullish) / -1 (bearish) / 0 (neutral):
  SMA20, SMA50, SMA200, RSI(14), MACD histogram,
  Stochastic %K(14), CCI(20), Bollinger Band midline

Score → Label:
  +6 to +8  → Strong Buy
  +3 to +5  → Buy
  -2 to +2  → Neutral
  -3 to -5  → Sell
  -6 to -8  → Strong Sell
"""

import pandas as pd
import numpy as np


# ── Indicator calculations ───────────────────────────────────────────────────

def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _macd_histogram(close: pd.Series) -> pd.Series:
    macd = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd, 9)
    return macd - signal


def _stoch_k(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    low_min = low.rolling(period).min()
    high_max = high.rolling(period).max()
    return 100 * (close - low_min) / (high_max - low_min)


def _cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    return (tp - tp.rolling(period).mean()) / (0.015 * tp.rolling(period).std())


def _bb_midline(close: pd.Series, period: int = 20) -> pd.Series:
    return close.rolling(period).mean()


# ── Signal scoring ───────────────────────────────────────────────────────────

def calculate_signals(df: pd.DataFrame) -> dict:
    """
    df must have columns: open, high, low, close (lowercase).
    Returns dict of signal_name → int (+1 / -1 / 0).
    Also returns raw indicator values for dashboard display.
    """
    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)

    last = close.iloc[-1]
    signals = {}
    raw = {}

    # SMA20
    sma20_val = _sma(close, 20).iloc[-1]
    signals["SMA20"]  = 1 if last > sma20_val else -1
    raw["sma20"] = round(sma20_val, 5)

    # SMA50
    sma50_val = _sma(close, 50).iloc[-1]
    signals["SMA50"]  = 1 if last > sma50_val else -1
    raw["sma50"] = round(sma50_val, 5)

    # SMA200
    sma200_val = _sma(close, 200).iloc[-1]
    signals["SMA200"] = 1 if last > sma200_val else -1
    raw["sma200"] = round(sma200_val, 5)

    # RSI
    rsi_val = _rsi(close).iloc[-1]
    raw["rsi"] = round(rsi_val, 1)
    if rsi_val < 30:
        signals["RSI"] = 1
    elif rsi_val > 70:
        signals["RSI"] = -1
    else:
        signals["RSI"] = 0

    # MACD
    hist_val = _macd_histogram(close).iloc[-1]
    signals["MACD"] = 1 if hist_val > 0 else -1
    raw["macd_hist"] = round(hist_val, 6)

    # Stochastic %K
    k_val = _stoch_k(high, low, close).iloc[-1]
    raw["stoch_k"] = round(k_val, 1)
    if k_val < 20:
        signals["Stoch"] = 1
    elif k_val > 80:
        signals["Stoch"] = -1
    else:
        signals["Stoch"] = 0

    # CCI
    cci_val = _cci(high, low, close).iloc[-1]
    raw["cci"] = round(cci_val, 1)
    if cci_val < -100:
        signals["CCI"] = 1
    elif cci_val > 100:
        signals["CCI"] = -1
    else:
        signals["CCI"] = 0

    # Bollinger Band midline
    bb_mid_val = _bb_midline(close).iloc[-1]
    signals["BB"] = 1 if last > bb_mid_val else -1
    raw["bb_mid"] = round(bb_mid_val, 5)

    raw["close"] = round(last, 5)

    return signals, raw


# ── Score + label ────────────────────────────────────────────────────────────

SCORE_THRESHOLDS = [
    (6,  8,  "Strong Buy"),
    (3,  5,  "Buy"),
    (-2, 2,  "Neutral"),
    (-5, -3, "Sell"),
    (-8, -6, "Strong Sell"),
]

LABEL_EMOJI = {
    "Strong Buy":  "✅",
    "Buy":         "🟢",
    "Neutral":     "⚪",
    "Sell":        "🔴",
    "Strong Sell": "❌",
}


def compute_score(signals: dict) -> tuple[int, str]:
    """Returns (total_score, label)."""
    total = sum(signals.values())
    if total >= 6:
        label = "Strong Buy"
    elif total >= 3:
        label = "Buy"
    elif total <= -6:
        label = "Strong Sell"
    elif total <= -3:
        label = "Sell"
    else:
        label = "Neutral"
    return total, label


def score_direction(label: str) -> str:
    """'bull' | 'bear' | 'neutral'"""
    if label in ("Buy", "Strong Buy"):
        return "bull"
    if label in ("Sell", "Strong Sell"):
        return "bear"
    return "neutral"


def score_pair(df: pd.DataFrame) -> dict:
    """Full pipeline: df → signals → score → label → direction."""
    if len(df) < 210:
        return None  # not enough bars for SMA200 warmup
    signals, raw = calculate_signals(df)
    total, label = compute_score(signals)
    return {
        "signals":   signals,
        "raw":       raw,
        "score":     total,
        "label":     label,
        "direction": score_direction(label),
        "emoji":     LABEL_EMOJI[label],
    }
