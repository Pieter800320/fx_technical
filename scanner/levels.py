"""scanner/levels.py"""
import pandas as pd
import numpy as np

SWING_LOOKBACK = 5
LEVELS_EACH    = 3
CLUSTER_ATR    = 0.3

def _atr(high, low, close, period=14):
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def _pip_size(price):
    if price > 500:  return 1.0
    if price > 100:  return 0.01
    return 0.0001

def _cluster(levels, threshold, current_price):
    if not levels:
        return []
    sorted_lvls = sorted(levels)
    clusters = []
    group = [sorted_lvls[0]]
    for i in range(1, len(sorted_lvls)):
        if sorted_lvls[i] - sorted_lvls[i - 1] <= threshold:
            group.append(sorted_lvls[i])
        else:
            clusters.append(group)
            group = [sorted_lvls[i]]
    clusters.append(group)
    return [min(g, key=lambda x: abs(x - current_price)) for g in clusters]

def find_levels(df):
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)
    current_price = float(close.iloc[-1])
    atr_val   = _atr(high, low, close)
    threshold = CLUSTER_ATR * atr_val
    pip       = _pip_size(current_price)
    n = SWING_LOOKBACK
    h = high.values
    l = low.values
    swing_highs, swing_lows = [], []
    for i in range(n, len(h) - n):
        if h[i] > max(h[i-n:i]) and h[i] > max(h[i+1:i+n+1]):
            swing_highs.append(float(h[i]))
        if l[i] < min(l[i-n:i]) and l[i] < min(l[i+1:i+n+1]):
            swing_lows.append(float(l[i]))
    res_raw = [p for p in swing_highs if p > current_price]
    sup_raw = [p for p in swing_lows  if p < current_price]
    res_clustered = _cluster(res_raw, threshold, current_price)
    sup_clustered = _cluster(sup_raw, threshold, current_price)
    res_clustered.sort()
    sup_clustered.sort(reverse=True)
    res_final = res_clustered[:LEVELS_EACH]
    sup_final = sup_clustered[:LEVELS_EACH]
    return {
        "support":       [{"price": round(p, 5), "pips": round((current_price - p) / pip, 1)} for p in sup_final],
        "resistance":    [{"price": round(p, 5), "pips": round((p - current_price) / pip, 1)} for p in res_final],
        "current_price": round(current_price, 5),
    }
