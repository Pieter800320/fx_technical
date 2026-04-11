import numpy as np
import pandas_ta as ta

from scanner.structure import detect_structure


# ── Regime-aware label thresholds ────────────────────────────────────────────
# Ranging / mixed markets require higher conviction before a label fires.
# Raw score range: EMA200 (±1.5) + Momentum (±2.0) + RSI (±2.0) = ±5.5
# After BOS multiplier max (×1.30): ±7.15
# Thresholds are set against the post-multiplier score.
THRESHOLDS = {
    'risk_on':  {'strong': 4.5, 'signal': 3.0},
    'risk_off': {'strong': 4.5, 'signal': 3.0},
    'ranging':  {'strong': 5.5, 'signal': 4.0},
    'mixed':    {'strong': 5.5, 'signal': 4.0},
    'unknown':  {'strong': 4.5, 'signal': 3.0},
}


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────

def _adx_weight(adx):
    """
    ADX as a graduated confidence weight, not a binary gate.
    ATR remains the binary filter (low participation = no signal).
    """
    if adx is None or np.isnan(adx): return 0.0
    if adx < 15:  return 0.0   # no trend — suppress entirely
    if adx < 20:  return 0.5   # weak — halve the score
    if adx < 25:  return 0.75  # developing
    return 1.0                  # confirmed trend — full score


def _ema200_score(close, ema200):
    """
    Trend anchor.  ±1.5 — upweighted vs old ±1 because EMA200
    is the primary institutional level, not just another vote.
    """
    return 1.5 if close > ema200 else -1.5


def _momentum_score(ema50_v, dmi_v, macd_v):
    """
    One vote from the three collinear momentum signals (EMA50, DMI, MACD).
    Majority direction wins.  Magnitude = 2.0 if all agree, 1.0 if 2/3.
    This replaces the old triple-count of the same underlying condition.

    Returns (score, direction_int, breakdown_dict)
    """
    votes = [ema50_v, dmi_v, macd_v]
    total = sum(votes)
    direction = 1 if total > 0 else (-1 if total < 0 else 0)

    if direction == 0:
        return 0.0, 0, {'ema50': ema50_v, 'dmi': dmi_v, 'macd': macd_v}

    magnitude = 2.0 if abs(total) == 3 else 1.0
    return float(direction * magnitude), direction, {
        'ema50': ema50_v, 'dmi': dmi_v, 'macd': macd_v
    }


def _rsi_score(rsi):
    """
    Graduated RSI — measures exhaustion / confirmation quality,
    not just which side of 50 it sits on.
    """
    if rsi >= 70:  return  2.0   # strong bull confirmation
    if rsi >= 60:  return  1.0
    if rsi >= 50:  return  0.5
    if rsi >= 40:  return -0.5
    if rsi >= 30:  return -1.0
    return -2.0                   # strong bear confirmation


def _macd_histogram_vote(hist_series):
    """
    MACD histogram momentum (acceleration) is more predictive than
    simple crossover direction.  Returns a directional vote int.
    """
    h = hist_series.values
    if len(h) < 3:
        return 0
    if h[-1] > h[-2] > h[-3]:  return  1   # accelerating bullish
    if h[-1] < h[-2] < h[-3]:  return -1   # accelerating bearish
    if h[-1] > h[-2]:          return  1   # decelerating but still rising
    if h[-1] < h[-2]:          return -1   # decelerating but still falling
    return 0


def _extension_flags(close, ema200, ema50_vals, rsi, atr, close_series):
    """
    Unchanged from prior system — detects overextended conditions.
    """
    flags = []
    ext = abs(close - ema200) / max(float(atr), 1e-8)
    if ext > 2.0:
        flags.append(f'Price {ext:.1f}x ATR from EMA200')
    if rsi > 75:
        flags.append('RSI overbought (>75)')
    elif rsi < 25:
        flags.append('RSI oversold (<25)')

    # Consecutive closes beyond EMA50
    closes = close_series.values
    ema50v = ema50_vals.values
    consec = 0
    for c, e in zip(reversed(closes), reversed(ema50v)):
        if not np.isnan(e):
            if (close > ema200 and c > e) or (close < ema200 and c < e):
                consec += 1
            else:
                break
    if consec >= 8:
        flags.append(f'{consec} consecutive bars beyond EMA50')
    return flags


# ────────────────────────────────────────────────────────────────────────────
# Main scoring function
# ────────────────────────────────────────────────────────────────────────────

def score_signals(df, timeframe='H4', regime='unknown', swing_n=5):
    """
    Score a single pair on one timeframe.

    Scoring architecture
    ────────────────────
    1. Trend       EMA200          ±1.5   (primary anchor, upweighted)
    2. Momentum    EMA50/DMI/MACD  ±2.0   (1 grouped vote — no collinearity)
    3. Condition   RSI graduated   ±2.0   (exhaustion / confirmation quality)
       ─────────────────────────────────
       Raw max                     ±5.5

    4. ADX weight  0.0 – 1.0      (graduated, not binary gate)
       Weighted max                ±5.5

    5. Structure multiplier        0.40 – 1.30  (H4/D1 only)
       BOS aligned  → ×1.30 max   Final max ±7.15
       CHOCH        → ×0.40 min
       Conflict     → ×0.00       (alert killed)

    6. Regime-aware thresholds     Ranging/mixed require higher conviction.

    ATR remains a hard binary filter (low participation = no data worth scoring).

    Parameters
    ----------
    df        : OHLCV DataFrame with sufficient history
    timeframe : 'H1' | 'H4' | 'D1'
    regime    : string from regime.py output
    swing_n   : pivot lookback for structure detection

    Returns
    -------
    dict — fully backward-compatible with existing JSON schema + new fields
    """

    close = float(df['close'].iloc[-1])

    # ── Compute all indicators once ──────────────────────────────────────────
    ema200_s = ta.ema(df['close'], length=200)
    ema50_s  = ta.ema(df['close'], length=50)
    rsi_s    = ta.rsi(df['close'], length=14)
    atr_s    = ta.atr(df['high'], df['low'], df['close'], length=14)
    adx_df   = ta.adx(df['high'], df['low'], df['close'], length=14)
    macd_df  = ta.macd(df['close'])

    ema200   = float(ema200_s.iloc[-1])
    ema50    = float(ema50_s.iloc[-1])
    rsi      = float(rsi_s.iloc[-1])
    atr      = float(atr_s.iloc[-1])
    atr_avg  = float(atr_s.rolling(14).mean().iloc[-1])
    adx      = float(adx_df['ADX_14'].iloc[-1])
    dmi_plus = float(adx_df['DMP_14'].iloc[-1])
    dmi_minus= float(adx_df['DMN_14'].iloc[-1])

    # ── ATR hard filter (binary — low participation is genuinely binary) ─────
    atr_ratio = round(atr / max(atr_avg, 1e-8), 2)
    if atr < 0.7 * atr_avg:
        return {
            'score':      0,
            'raw_score':  0,
            'label':      'Filtered',
            'filter':     'ATR',
            'adx':        round(adx, 1),
            'adx_weight': _adx_weight(adx),
            'atr_ratio':  atr_ratio,
            'structure':  {
                'direction': 'neutral', 'event': 'none',
                'strength': 0.0, 'multiplier': 1.0
            },
            'conflict':   False,
            'extension':  [],
            'signals':    {},
        }

    # ── Individual signal votes ───────────────────────────────────────────────
    ema200_score = _ema200_score(close, ema200)

    ema50_vote  = 1 if close > ema50 else -1
    dmi_vote    = 1 if dmi_plus > dmi_minus else -1
    macd_vote   = _macd_histogram_vote(macd_df['MACDh_12_26_9'])

    momentum_score, momentum_dir, m_detail = _momentum_score(
        ema50_vote, dmi_vote, macd_vote
    )

    rsi_score = _rsi_score(rsi)

    # ── Raw score ─────────────────────────────────────────────────────────────
    raw_score = ema200_score + momentum_score + rsi_score

    # ── ADX graduated weight ──────────────────────────────────────────────────
    adx_weight = _adx_weight(adx)
    raw_score  = round(raw_score * adx_weight, 2)

    # ── Structure (H4 / D1 only) ──────────────────────────────────────────────
    structure = {
        'direction': 'neutral', 'event': 'none',
        'strength': 0.0, 'multiplier': 1.0
    }
    conflict = False

    if timeframe in ['H4', 'D1']:
        structure = detect_structure(df, atr, swing_n=swing_n)

        # Conflict: structure direction contradicts momentum group majority
        if structure['direction'] != 'neutral' and momentum_dir != 0:
            struct_int = 1 if structure['direction'] == 'bull' else -1
            if struct_int != momentum_dir:
                conflict = True
                structure = dict(structure)       # don't mutate cached ref
                structure['multiplier'] = 0.0    # zero the score — no alert

    # ── Apply structure multiplier ────────────────────────────────────────────
    final_score = round(raw_score * structure['multiplier'], 2)

    # ── Regime-aware label assignment ─────────────────────────────────────────
    regime_key = str(regime).lower().split()[0] if regime else 'unknown'
    thresh     = THRESHOLDS.get(regime_key, THRESHOLDS['unknown'])

    if conflict:
        label = 'Conflict'
    else:
        abs_s = abs(final_score)
        sign  = 1 if final_score > 0 else -1
        if abs_s >= thresh['strong']:
            label = 'Strong Buy' if sign > 0 else 'Strong Sell'
        elif abs_s >= thresh['signal']:
            label = 'Buy' if sign > 0 else 'Sell'
        else:
            label = 'Neutral'

    # ── Extension flags ───────────────────────────────────────────────────────
    extension = _extension_flags(close, ema200, ema50_s, rsi, atr, df['close'])

    return {
        # Core output — backward compatible
        'score':      final_score,
        'raw_score':  round(raw_score, 2),   # pre-multiplier, for debugging
        'label':      label,
        'adx':        round(adx, 1),
        'adx_weight': adx_weight,
        'atr_ratio':  atr_ratio,
        'extension':  extension,

        # New fields
        'conflict':   conflict,
        'structure':  structure,

        # Signal breakdown (dashboard / Telegram drill-down)
        'signals': {
            'ema200':     round(ema200_score, 2),
            'momentum':   round(momentum_score, 2),
            'rsi':        round(rsi_score, 2),
            'm_detail':   m_detail,    # per-indicator votes within momentum group
        },
    }


# Backward-compatible alias — scan_d1/h4/h1 import this name
score_pair = score_signals
