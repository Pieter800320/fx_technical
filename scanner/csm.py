"""
scanner/csm.py
Improved currency strength model.

Method:
  For each pair, compute ATR-adjusted return on D1 and H4.
  Weighted combination: D1 × 0.7 + H4 × 0.3
  Aggregate per currency (base adds, quote subtracts).
  Normalize all 8 currencies to 0-100.
  Also compute confidence: % of pairs agreeing on direction per currency.

ATR adjustment:
  adj_return = % return over LOOKBACK bars / ATR(14)
  This normalises for volatility — a currency that moved 3 ATRs
  is genuinely stronger than one that moved 1 ATR.
"""

import numpy as np
import pandas as pd
from config.pairs import CURRENCIES

LOOKBACK  = 14   # bars for return calculation
ATR_PERIOD = 14

# Only the 7 major pairs — covers all 8 currencies with minimal redundancy
MAJOR_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF",
    "AUD/USD", "USD/CAD", "NZD/USD",
]

D1_WEIGHT = 0.7
H4_WEIGHT = 0.3


def _atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
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


def _adj_return(df: pd.DataFrame) -> float | None:
    """ATR-adjusted % return over LOOKBACK bars."""
    if df is None or len(df) < LOOKBACK + ATR_PERIOD + 1:
        return None
    close = df["close"].astype(float)
    ret   = (close.iloc[-1] - close.iloc[-(LOOKBACK + 1)]) / close.iloc[-(LOOKBACK + 1)] * 100
    atr   = _atr(df)
    if atr == 0:
        return None
    return ret / atr


def compute_currency_strength(d1_ohlcv: dict, h4_ohlcv: dict = None) -> dict:
    """
    d1_ohlcv: { "EUR/USD": pd.DataFrame, ... }
    h4_ohlcv: { "EUR/USD": pd.DataFrame, ... } — optional, for multi-TF weighting

    Returns: {
        "rankings": { "USD": 100.0, "EUR": 86.9, ... },  # sorted desc, 0-100
        "confidence": { "USD": 0.86, "EUR": 0.71, ... }, # 0-1 agreement score
    }
    """
    raw_scores  = {c: [] for c in CURRENCIES}
    confidence  = {c: [] for c in CURRENCIES}  # list of +1/-1 per pair

    for pair in MAJOR_PAIRS:
        base, quote = pair.split("/")

        d1_df = d1_ohlcv.get(pair)
        h4_df = h4_ohlcv.get(pair) if h4_ohlcv else None

        d1_ret = _adj_return(d1_df)
        h4_ret = _adj_return(h4_df)

        if d1_ret is None:
            continue

        # Weighted combined return
        if h4_ret is not None:
            combined = D1_WEIGHT * d1_ret + H4_WEIGHT * h4_ret
        else:
            combined = d1_ret

        # Base currency: positive return = strong base
        # Quote currency: positive return = weak quote (need to invert)
        if base in raw_scores:
            raw_scores[base].append(combined)
            confidence[base].append(1 if combined > 0 else -1)
        if quote in raw_scores:
            raw_scores[quote].append(-combined)
            confidence[quote].append(1 if combined < 0 else -1)

    # Average raw score per currency
    averages = {}
    for c in CURRENCIES:
        vals = raw_scores[c]
        averages[c] = float(np.mean(vals)) if vals else 0.0

    # Normalize to 0-100
    values = list(averages.values())
    min_v, max_v = min(values), max(values)
    spread = max_v - min_v if max_v != min_v else 1.0

    normalized = {
        c: round((v - min_v) / spread * 100, 1)
        for c, v in averages.items()
    }

    # Confidence: % of pairs agreeing on direction (0.0-1.0)
    conf_scores = {}
    for c in CURRENCIES:
        votes = confidence[c]
        if not votes:
            conf_scores[c] = 0.0
        else:
            # Agreement = how many votes match the majority direction
            majority = 1 if sum(votes) >= 0 else -1
            agreeing = sum(1 for v in votes if v == majority)
            conf_scores[c] = round(agreeing / len(votes), 2)

    # Sort strongest to weakest
    ranked = dict(sorted(normalized.items(), key=lambda x: x[1], reverse=True))

    # Per-currency pair breakdown for dashboard drill-down
    breakdown = {c: [] for c in CURRENCIES}
    for pair in MAJOR_PAIRS:
        base, quote = pair.split("/")
        d1_df = d1_ohlcv.get(pair)
        h4_df = h4_ohlcv.get(pair) if h4_ohlcv else None
        d1_ret = _adj_return(d1_df)
        h4_ret = _adj_return(h4_df)
        if d1_ret is None:
            continue
        combined = D1_WEIGHT * d1_ret + H4_WEIGHT * h4_ret if h4_ret is not None else d1_ret
        display  = pair.replace("/", "")
        if base in breakdown:
            breakdown[base].append({
                "pair": display,
                "score": round(float(combined), 3),
                "bull":  bool(combined > 0),
            })
        if quote in breakdown:
            breakdown[quote].append({
                "pair": display,
                "score": round(float(-combined), 3),
                "bull":  bool(combined < 0),
            })

    return {
        "rankings":   ranked,
        "confidence": {c: conf_scores[c] for c in ranked},
        "breakdown":  breakdown,
    }
