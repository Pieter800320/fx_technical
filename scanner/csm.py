"""
scanner/csm.py
D1 currency strength calculation.

Method:
  For each currency, find all pairs it appears in.
  Compute the % return of each pair over the last N bars.
  If the currency is the BASE  → add the return.
  If the currency is the QUOTE → subtract the return.
  Average across all pairs the currency appears in.
  Normalize all 8 currencies to 0–100.
"""

import numpy as np
from config.pairs import PAIRS, CURRENCIES


LOOKBACK = 14  # bars for strength calculation


def compute_currency_strength(ohlcv_map: dict) -> dict:
    """
    ohlcv_map: { "EUR/USD": pd.DataFrame, ... }
                DataFrames must have a 'close' column.

    Returns: { "EUR": 72.3, "USD": 61.1, ... } — values 0–100, sorted desc.
    """
    raw_scores = {c: [] for c in CURRENCIES}

    for pair, df in ohlcv_map.items():
        if df is None or len(df) < LOOKBACK + 1:
            continue
        close = df["close"].astype(float)
        # % return over LOOKBACK bars
        ret = (close.iloc[-1] - close.iloc[-(LOOKBACK + 1)]) / close.iloc[-(LOOKBACK + 1)] * 100

        base, quote = pair.split("/")
        if base in raw_scores:
            raw_scores[base].append(ret)
        if quote in raw_scores:
            raw_scores[quote].append(-ret)

    # Average raw score per currency
    averages = {}
    for c in CURRENCIES:
        vals = raw_scores[c]
        averages[c] = float(np.mean(vals)) if vals else 0.0

    # Normalize to 0–100
    values = list(averages.values())
    min_v, max_v = min(values), max(values)
    spread = max_v - min_v if max_v != min_v else 1.0

    normalized = {
        c: round((v - min_v) / spread * 100, 1)
        for c, v in averages.items()
    }

    # Sort strongest → weakest
    return dict(sorted(normalized.items(), key=lambda x: x[1], reverse=True))
