"""
scanner/levels.py
Support and Resistance level detection.

Replicates the Pine Script 1212(-1) momentum shift logic:
  - SMA(12) momentum = SMA[shift1] - SMA[shift2]
  - CrossUp  (momentum flips positive) → support level at close[midShift]
  - CrossDown (momentum flips negative) → resistance level at close[midShift]

Clustering:
  - Levels within 0.3 × ATR of each other are merged
  - Representative = level closest to current price in each cluster

Output: 3 support levels below price, 3 resistance levels above price.
Each level includes pip distance from current price.
"""

import numpy as np
import pandas as pd


# ── Parameters (matching Pine Script defaults) ────────────────────────────────
SMA_LEN      = 12
SHIFT1       = 3
SHIFT2       = 4
MID_SHIFT    = round((SHIFT1 + SHIFT2) / 2)   # = 3
LEVELS_EACH  = 3
CLUSTER_ATR  = 0.3


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]


def _pip_size(price: float) -> float:
    """Approximate pip size based on price magnitude."""
    if price > 500:    return 1.0      # XAUUSD — 1 pip = $1
    if price > 100:    return 0.01     # JPY pairs
    return 0.0001                       # Standard forex


def _pips(distance: float, price: float) -> float:
    return round(distance / _pip_size(price), 1)


def _cluster_levels(levels: list[float], threshold: float, current_price: float) -> list[float]:
    """
    Merge levels within `threshold` of each other.
    Representative = level closest to current_price in each cluster.
    """
    if not levels:
        return []

    sorted_levels = sorted(levels)
    clusters = []
    current_cluster = [sorted_levels[0]]

    for i in range(1, len(sorted_levels)):
        if sorted_levels[i] - sorted_levels[i - 1] <= threshold:
            current_cluster.append(sorted_levels[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [sorted_levels[i]]
    clusters.append(current_cluster)

    # Pick level closest to current price as cluster representative
    result = []
    for cluster in clusters:
        representative = min(cluster, key=lambda x: abs(x - current_price))
        result.append(representative)

    return result


# ── Main function ─────────────────────────────────────────────────────────────

def find_levels(df: pd.DataFrame) -> dict:
    """
    df: OHLCV DataFrame with columns open, high, low, close.
    Returns {
        "support":    [{"price": 1.0821, "pips": 34}, ...],  # below price, nearest first
        "resistance": [{"price": 1.0876, "pips": 21}, ...],  # above price, nearest first
        "current_price": 1.0855,
    }
    """
    close = df["close"].astype(float)
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)

    current_price = close.iloc[-1]
    atr_val       = _atr(high, low, close)
    threshold     = CLUSTER_ATR * atr_val

    sma     = _sma(close, SMA_LEN)
    momentum = sma.shift(SHIFT1) - sma.shift(SHIFT2)

    # Detect crossovers
    sup_raw = []
    res_raw = []

    for i in range(1, len(momentum)):
        if pd.isna(momentum.iloc[i]) or pd.isna(momentum.iloc[i - 1]):
            continue

        # CrossUp → support
        if momentum.iloc[i] > 0 and momentum.iloc[i - 1] <= 0:
            idx = i - MID_SHIFT
            if idx >= 0:
                sup_raw.append(close.iloc[idx])

        # CrossDown → resistance
        if momentum.iloc[i] < 0 and momentum.iloc[i - 1] >= 0:
            idx = i - MID_SHIFT
            if idx >= 0:
                res_raw.append(close.iloc[idx])

    # Filter: support below price, resistance above price
    sup_below = [p for p in sup_raw if p < current_price]
    res_above = [p for p in res_raw if p > current_price]

    # Cluster
    sup_clustered = _cluster_levels(sup_below, threshold, current_price)
    res_clustered = _cluster_levels(res_above, threshold, current_price)

    # Sort: support descending (nearest first), resistance ascending (nearest first)
    sup_clustered.sort(reverse=True)
    res_clustered.sort()

    # Take top N
    sup_final = sup_clustered[:LEVELS_EACH]
    res_final = res_clustered[:LEVELS_EACH]

    # Format with pip distance
    pip = _pip_size(current_price)

    support = [
        {
            "price": round(p, 5),
            "pips":  round((current_price - p) / pip, 1),
        }
        for p in sup_final
    ]

    resistance = [
        {
            "price": round(p, 5),
            "pips":  round((p - current_price) / pip, 1),
        }
        for p in res_final
    ]

    return {
        "support":       support,
        "resistance":    resistance,
        "current_price": round(current_price, 5),
    }
