"""
scanner/levels.py
Support and Resistance levels via swing high/low detection.

A swing high: bar where high[i] > high of N bars on each side
A swing low:  bar where low[i]  < low  of N bars on each side

Levels above current price = resistance
Levels below current price = support

Clustering: levels within 0.3 × ATR merged, representative = closest to current price.
Output: 3 resistance (nearest first), 3 support (nearest first).
"""

import pandas as pd
import numpy as np

SWING_LOOKBACK = 5     # bars each side to confirm a swing
LEVELS_EACH    = 3
CLUSTER_ATR    = 0.3


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def _pip_size(price: float) -> float:
    if price > 500:  return 1.0      # Gold
    if price > 100:  return 0.01     # JPY pairs
    return 0.0001                    # Standard forex


def _cluster(levels: list, threshold: float, current_price: float) -> list:
    """Merge levels within threshold. Representative = closest to current price."""
    if not levels:
        return []
    sorted_lvls = sorted(levels)
    clusters    = []
    group       = [sorted_lvls[0]]

    for i in range(1, len(sorted_lvls)):
        if sorted_lvls[i] - sorted_lvls[i - 1] <= threshold:
            group.append(sorted_lvls[i])
        else:
            clusters.append(group)
            group = [sorted_lvls[i]]
    clusters.append(group)

    return [min(g, key=lambda x: abs(x - current_price)) for g in clusters]


def find_levels(df: pd.DataFrame) -> dict:
    """
    df: OHLCV DataFrame, columns: open, high, low, close.
    Returns {
        "support":       [{"price": 1.0821, "pips": 34}, ...],
        "resistance":    [{"price": 1.0876, "pips": 21}, ...],
        "current_price": 1.0855,
    }
    """
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)

    current_price = float(close.iloc[-1])
    atr_val       = _atr(high, low, close)
    threshold     = CLUSTER_ATR * atr_val
    pip           = _pip_size(current_price)

    n  = SWING_LOOKBACK
    h  = high.values
    l  = low.values

    swing_highs = []
    swing_lows  = []

    # Detect swings — exclude last N bars (not confirmed yet)
    for i in range(n, len(h) - n):
        left_h  = h[i - n : i]
        right_h = h[i + 1 : i + n + 1]
        if h[i] > max(left_h) and h[i] > max(right_h):
            swing_highs.append(float(h[i]))

        left_l  = l[i - n : i]
        right_l = l[i + 1 : i + n + 1]
        if l[i] < min(left_l) and l[i] < min(right_l):
            swing_lows.append(float(l[i]))

    # Split by position relative to current price
    res_raw = [p for p in swing_highs if p > current_price]
    sup_raw = [p for p in swing_lows  if p < current_price]

    # Cluster
    res_clustered = _cluster(res_raw, threshold, current_price)
    sup_clustered = _cluster(sup_raw, threshold, current_price)

    # Sort: resistance ascending (nearest first), support descending (nearest first)
    res_clustered.sort()
    sup_clustered.sort(reverse=True)

    # Take top N
    res_final = res_clustered[:LEVELS_EACH]
    sup_final = sup_clustered[:LEVELS_EACH]

    resistance = [
        {"price": round(p, 5), "pips": round((p - current_price) / pip, 1)}
        for p in res_final
    ]
    support = [
        {"price": round(p, 5), "pips": round((current_price - p) / pip, 1)}
        for p in sup_final
    ]

    return {
        "support":       support,
        "resistance":    resistance,
        "current_price": round(current_price, 5),
    }
