"""
scanner/correlate.py
Computes pairwise Pearson correlation across all pairs using H4 returns.
Uses last LOOKBACK bars. Output is a symmetric 9×9 matrix.
"""

import numpy as np
import pandas as pd
from config.pairs import PAIRS

LOOKBACK = 50   # bars — ~8 days on H4, enough for recent correlation


def _returns(df: pd.DataFrame) -> np.ndarray | None:
    if df is None or len(df) < LOOKBACK + 1:
        return None
    close = df["close"].astype(float).iloc[-(LOOKBACK + 1):]
    return close.pct_change().dropna().values


def compute_correlation(h4_ohlcv: dict) -> dict:
    """
    h4_ohlcv: { "EUR/USD": pd.DataFrame, ... }

    Returns {
        "pairs":  ["EURUSD", ...],          # 9 labels
        "matrix": [[1.0, 0.85, ...], ...],  # 9×9 float, rounded to 2dp
    }
    """
    labels = [p.replace("/", "") for p in PAIRS]
    rets   = [_returns(h4_ohlcv.get(p)) for p in PAIRS]

    n = len(PAIRS)
    matrix = [[None] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 1.0
                continue
            ri, rj = rets[i], rets[j]
            if ri is None or rj is None:
                matrix[i][j] = None
                continue
            min_len = min(len(ri), len(rj))
            if min_len < 10:
                matrix[i][j] = None
                continue
            corr = float(np.corrcoef(ri[-min_len:], rj[-min_len:])[0, 1])
            matrix[i][j] = round(corr, 2)

    return {"pairs": labels, "matrix": matrix}
