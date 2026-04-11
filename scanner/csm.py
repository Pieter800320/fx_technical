import numpy as np
import pandas as pd
from config.pairs import CURRENCIES

LOOKBACK   = 14
ATR_PERIOD = 14
D1_WEIGHT  = 0.7
H4_WEIGHT  = 0.3

# MAJOR_PAIRS — used for H4 fetch in scan_d1 and breakdown display
MAJOR_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY",
    "AUD/JPY", "NZD/JPY", "CAD/JPY",
    "EUR/GBP", "EUR/CHF",
]

# CSM_EXTRA_PAIRS — not traded/scanned, CSM calculation only
# scan_d1.py adds these to the D1 fetch so compute_currency_strength
# gets a complete data set.
CSM_EXTRA_PAIRS = ["EUR/GBP", "EUR/CHF"]

# STRENGTH_PAIRS — drives the CSM score calculation
# Coverage per currency after additions:
#   EUR : EUR/USD, EUR/JPY, EUR/GBP, EUR/CHF  (4 observations)
#   GBP : GBP/USD, GBP/JPY, EUR/GBP           (3 observations)
#   USD : EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD (7)
#   JPY : USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, NZD/JPY, CAD/JPY          (6)
#   CHF : USD/CHF, EUR/CHF                     (2 observations)
#   AUD : AUD/USD, AUD/JPY                     (2 observations)
#   CAD : USD/CAD, CAD/JPY                     (2 observations)
#   NZD : NZD/USD, NZD/JPY                     (2 observations)
STRENGTH_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD",
    "AUD/JPY", "NZD/JPY", "CAD/JPY",
    "EUR/GBP", "EUR/CHF",
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

    # Breakdown uses MAJOR_PAIRS for per-pair drill-down in dashboard
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
