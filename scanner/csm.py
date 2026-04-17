# scanner/csm.py — Currency Strength Model
#
# Changes from audit:
#   - Added AUD/NZD, AUD/CAD, GBP/AUD to STRENGTH_PAIRS and CSM_EXTRA_PAIRS.
#     AUD/CAD/NZD previously had only 2 observations each — poor signal quality.
#     Now AUD: 5 obs, CAD: 3 obs, NZD: 3 obs, GBP: 5 obs.
#   - XAU/USD is fetched via REGIME_EXTRA_PAIRS (pairs.py) for regime.py use only.
#     It is intentionally excluded from CSM rankings (gold is not a currency).

import numpy as np
import pandas as pd
from config.pairs import CURRENCIES

LOOKBACK   = 14
ATR_PERIOD = 14
D1_WEIGHT  = 0.7
H4_WEIGHT  = 0.3

# All pairs used for display in dashboard breakdown
MAJOR_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY",
    "AUD/JPY", "NZD/JPY", "CAD/JPY",
    "EUR/GBP", "EUR/CHF", "GBP/CHF",
    "AUD/NZD", "AUD/CAD", "GBP/AUD",
]

# Extra pairs fetched in D1 scan for CSM calculation only (not traded)
CSM_EXTRA_PAIRS = [
    "EUR/GBP", "EUR/CHF", "GBP/CHF",
    "AUD/NZD",   # AUD: 3rd independent obs; NZD: 3rd independent obs
    "AUD/CAD",   # AUD: 4th obs; CAD: 3rd independent obs
    "GBP/AUD",   # GBP: 5th obs; AUD: 5th obs
]

# Drives CSM score calculation
# Coverage per currency:
#   EUR : EUR/USD, EUR/JPY, EUR/GBP, EUR/CHF                              (4)
#   GBP : GBP/USD, GBP/JPY, EUR/GBP, GBP/CHF, GBP/AUD                   (5)
#   USD : EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD  (7)
#   JPY : USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, NZD/JPY, CAD/JPY          (6)
#   CHF : USD/CHF, EUR/CHF, GBP/CHF                                       (3)
#   AUD : AUD/USD, AUD/JPY, AUD/NZD, AUD/CAD, GBP/AUD                   (5) ← was 2
#   CAD : USD/CAD, CAD/JPY, AUD/CAD                                       (3) ← was 2
#   NZD : NZD/USD, NZD/JPY, AUD/NZD                                       (3) ← was 2
STRENGTH_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD",
    "AUD/JPY", "NZD/JPY", "CAD/JPY",
    "EUR/GBP", "EUR/CHF", "GBP/CHF",
    "AUD/NZD", "AUD/CAD", "GBP/AUD",
]


def _atr(df, period=ATR_PERIOD):
    high  = df["high"].astype(float)
    low   = df["low"].astype(float)
    close = df["close"].astype(float)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if not np.isnan(val) else 1.0


def _adj_return(df):
    if df is None or len(df) < LOOKBACK + ATR_PERIOD + 1:
        return None
    close = df["close"].astype(float)
    ret   = (close.iloc[-1] - close.iloc[-(LOOKBACK + 1)]) / close.iloc[-(LOOKBACK + 1)] * 100
    atr   = _atr(df)
    if atr == 0:
        return None
    return ret / atr


def compute_currency_strength(d1_ohlcv, h4_ohlcv=None):
    raw_scores = {c: [] for c in CURRENCIES}
    confidence = {c: [] for c in CURRENCIES}

    for pair in STRENGTH_PAIRS:
        base, quote = pair.split("/")
        d1_ret = _adj_return(d1_ohlcv.get(pair))
        h4_ret = _adj_return(h4_ohlcv.get(pair)) if h4_ohlcv else None
        if d1_ret is None:
            continue
        combined = D1_WEIGHT * d1_ret + H4_WEIGHT * h4_ret if h4_ret is not None else d1_ret
        if base in raw_scores:
            raw_scores[base].append(combined)
            confidence[base].append(1 if combined > 0 else -1)
        if quote in raw_scores:
            raw_scores[quote].append(-combined)
            confidence[quote].append(1 if combined < 0 else -1)

    averages = {c: float(np.mean(v)) if v else 0.0 for c, v in raw_scores.items()}
    values   = list(averages.values())
    min_v, max_v = min(values), max(values)
    spread   = max_v - min_v if max_v != min_v else 1.0
    normalized = {c: round((v - min_v) / spread * 100, 1) for c, v in averages.items()}

    conf_scores = {}
    for c in CURRENCIES:
        votes = confidence[c]
        if not votes:
            conf_scores[c] = 0.0
        else:
            majority = 1 if sum(votes) >= 0 else -1
            agreeing = sum(1 for v in votes if v == majority)
            conf_scores[c] = round(agreeing / len(votes), 2)

    ranked = dict(sorted(normalized.items(), key=lambda x: x[1], reverse=True))

    breakdown = {c: [] for c in CURRENCIES}
    for pair in MAJOR_PAIRS:
        base, quote = pair.split("/")
        d1_ret = _adj_return(d1_ohlcv.get(pair))
        h4_ret = _adj_return(h4_ohlcv.get(pair)) if h4_ohlcv else None
        if d1_ret is None:
            continue
        combined = D1_WEIGHT * d1_ret + H4_WEIGHT * h4_ret if h4_ret is not None else d1_ret
        display  = pair.replace("/", "")
        if base in breakdown:
            breakdown[base].append({"pair": display, "score": round(float(combined), 3), "bull": bool(combined > 0)})
        if quote in breakdown:
            breakdown[quote].append({"pair": display, "score": round(float(-combined), 3), "bull": bool(combined < 0)})

    return {"rankings": ranked, "confidence": conf_scores, "breakdown": breakdown}
