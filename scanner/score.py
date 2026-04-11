import numpy as np


def detect_structure(df, atr, swing_n=5):
    """
    Event-based market structure detector.

    Finds genuine swing highs/lows using a lookback window, then classifies
    the last structural event as BOS (trend continuation) or CHOCH (potential
    reversal).  Returns a multiplier that score.py applies to the raw signal
    score post-ADX weighting.

    Parameters
    ----------
    df      : OHLCV DataFrame (must have 'high', 'low', 'close' columns)
    atr     : current ATR value (float) — used for strength normalisation
    swing_n : pivot lookback on each side (default 5 bars)

    Returns
    -------
    dict with keys:
        direction   : 'bull' | 'bear' | 'neutral'
        event       : 'BOS'  | 'CHOCH' | 'none'
        strength    : 0.0 – 1.0  (impulse size relative to ATR)
        multiplier  : applied to raw score by score.py
                      BOS   → 1.0 + 0.3 * strength  (max 1.30)
                      CHOCH → 1.0 - 0.4 * strength  (min 0.40)
                      none  → 1.00
    """
    high  = df['high'].values
    low   = df['low'].values
    close = df['close'].values

    _neutral = {
        'direction':  'neutral',
        'event':      'none',
        'strength':   0.0,
        'multiplier': 1.0,
    }

    if len(high) < swing_n * 2 + 1:
        return _neutral

    # ── Pivot detection ──────────────────────────────────────────────────────
    swH, swL = [], []
    for i in range(swing_n, len(high) - swing_n):
        window_h = high[i - swing_n : i + swing_n + 1]
        window_l = low[i  - swing_n : i + swing_n + 1]
        if high[i] == np.max(window_h):
            swH.append((i, high[i]))
        if low[i] == np.min(window_l):
            swL.append((i, low[i]))

    if len(swH) < 2 or len(swL) < 2:
        return _neutral

    # ── Trend from last two confirmed swings ─────────────────────────────────
    higher_highs = swH[-1][1] > swH[-2][1]
    higher_lows  = swL[-1][1] > swL[-2][1]
    lower_highs  = swH[-1][1] < swH[-2][1]
    lower_lows   = swL[-1][1] < swL[-2][1]

    if higher_highs and higher_lows:
        trend = 'bull'
    elif lower_highs and lower_lows:
        trend = 'bear'
    else:
        return _neutral  # mixed swing sequence — no clean structure

    last_c = close[-1]
    event  = 'none'

    # ── Event classification ─────────────────────────────────────────────────
    if trend == 'bear':
        if last_c < swL[-1][1]:    event = 'BOS'    # lower low confirmed
        elif last_c > swH[-1][1]:  event = 'CHOCH'  # broke above last swing high
    else:  # bull
        if last_c > swH[-1][1]:   event = 'BOS'    # higher high confirmed
        elif last_c < swL[-1][1]: event = 'CHOCH'  # broke below last swing low

    # ── Strength: how far price cleared the level relative to ATR ────────────
    ref = swL[-1][1] if trend == 'bull' else swH[-1][1]
    atr_safe = max(float(atr), 1e-8)
    strength = round(min(abs(last_c - ref) / atr_safe / 2.0, 1.0), 2)

    # ── Multiplier ───────────────────────────────────────────────────────────
    if event == 'BOS':
        multiplier = round(1.0 + 0.3 * strength, 3)   # 1.00 – 1.30
    elif event == 'CHOCH':
        multiplier = round(max(1.0 - 0.4 * strength, 0.4), 3)  # 0.40 – 1.00
    else:
        multiplier = 1.0

    return {
        'direction':  trend,
        'event':      event,
        'strength':   strength,
        'multiplier': multiplier,
    }
