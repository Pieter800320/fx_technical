# scanner/conviction.py — Currency Conviction Score
#
# Combines 6 inputs into a per-currency conviction score (-100 to +100).
# Score answers: "Is the structural and positioning environment supporting
# a directional move, or is it crowded/exhausted?"
#
# Inputs:
#   1. COT net speculator position — 52w percentile, bifurcated scoring
#   2. COT open interest momentum  — direction of new money flow
#   3. COT disaggregated           — asset manager vs leveraged fund alignment
#   4. CSM extreme                 — mean-reversion / exhaustion signal
#   5. Extension composite         — cross-pair extension aggregation
#   6. RSI breadth                 — directional confirmation breadth
#
# Each input scores as a small integer. Sum is normalised to -100/+100.
# EWMA smoothing (alpha=0.6) prevents weekly flicker.

import math

from config.pairs import PAIRS, CURRENCIES

# ── Input 1: COT Net Speculator Position ─────────────────────────────────────

def _score_cot_position(noncomm_pct: float | None, prev_score: int = 0) -> int:
    """
    Bifurcated scoring with ±3pt hysteresis zone at each threshold.
    
    At extremes (>80 or <20): contrarian signal (crowded positioning).
    At moderate levels (60-80 or 20-40): trend-following (specs are right).
    At centre (40-60): neutral.
    
    Hysteresis prevents flip-flopping near threshold boundaries.
    """
    if noncomm_pct is None:
        return 0

    p = noncomm_pct
    # Apply hysteresis: only change score if clearly past threshold (±3 buffer)
    # Use previous score to determine which side of boundary we're on
    if p > 83:   return -2  # deeply crowded long → contrarian bear
    if p > 77:   return -2 if prev_score <= -1 else -1  # hysteresis zone 77-83
    if p > 57:   return +1  # moderate long → follow specs (bull)
    if p > 43:   return 0   # neutral zone
    if p > 23:   return -1  # moderate short → follow specs (bear)
    if p > 17:   return +2 if prev_score >= 1 else +1   # hysteresis zone 17-23
    return +2               # deeply crowded short → contrarian bull


# ── Input 2: COT Open Interest Momentum ──────────────────────────────────────

def _score_cot_oi(oi_current: float | None, oi_4w_ago: float | None,
                   currency_dir: int) -> int:
    """
    Compare 4-week OI change to currency's D1 directional bias.
    Normalised by rolling average to handle thin contracts.
    
    currency_dir: +1 = bullish D1, -1 = bearish D1, 0 = neutral
    
    Rising OI in direction of trend = new participation = +1 (healthy)
    Falling OI against trend = short covering / long liquidation = -1 (weak)
    """
    if oi_current is None or oi_4w_ago is None or oi_4w_ago == 0 or currency_dir == 0:
        return 0

    change_pct = (oi_current - oi_4w_ago) / oi_4w_ago
    if abs(change_pct) < 0.03:  # < 3% change = effectively flat
        return 0

    oi_rising = change_pct > 0
    if oi_rising:
        # New money entering regardless of direction = healthy trend
        return +1
    else:
        # Positions being closed = liquidation driven, not fresh directional flow
        return -1


# ── Input 3: COT Disaggregated — Asset Mgr vs Leveraged Fund ─────────────────

def _score_cot_disagg(am_pct: float | None, lf_pct: float | None) -> int:
    """
    Asset managers (structural, sticky) vs Leveraged funds (tactical, fast).
    
    Both long  → strong bull (+2): structural AND tactical confirm
    Both short → strong bear (-2): structural AND tactical confirm
    AM long, LF short → 0: structural bull but tactically fading
    AM short, LF long → -1: tactical chase against structural flow
                              (riskier setup — weak hands chasing)
    
    Uses 55/45 threshold with ±5pt hysteresis to determine "long" vs "short".
    """
    if am_pct is None or lf_pct is None:
        return 0

    # 55/45 thresholds with some hysteresis baked in
    am_long  = am_pct > 55
    am_short = am_pct < 45
    lf_long  = lf_pct > 55
    lf_short = lf_pct < 45

    if am_long  and lf_long:  return +2  # full alignment, bull
    if am_short and lf_short: return -2  # full alignment, bear
    if am_long  and lf_short: return  0  # structural bull, tactical fade
    if am_short and lf_long:  return -1  # tactical chases against structure
    return 0  # mixed / neutral zone


# ── Input 4: CSM Extreme ─────────────────────────────────────────────────────

def _score_csm_extreme(csm_value: float | None) -> int:
    """
    Mean-reversion / exhaustion signal from CSM 0-100 ranking.
    
    Extreme readings signal crowded positions via price action.
    High CSM = currency has been broadly bought → upside limited.
    Low CSM  = currency has been broadly sold → downside limited.
    
    This is a CONTRARIAN input (scores against the CSM direction).
    """
    if csm_value is None:
        return 0

    if csm_value > 88:  return -2  # deeply overbought
    if csm_value > 72:  return -1
    if csm_value < 12:  return +2  # deeply oversold
    if csm_value < 28:  return +1
    return 0  # 28-72 neutral zone


# ── Input 5: Extension Composite ─────────────────────────────────────────────

def _score_extension(pair_data: dict, currency: str, d1_direction: int) -> int:
    """
    Aggregate is_extended() across all pairs involving this currency.
    Only counts extensions in the direction of the currency's D1 bias.
    
    Returns asymmetric score: 0 extension = mildly positive (+1),
    broad extension = strongly negative (-2).
    Asymmetric because extension is always a caution flag,
    absence is only mildly reassuring.
    
    pair_data: dict of pair → D1 score data (from d1_scores)
    d1_direction: +1 bull, -1 bear, 0 neutral
    """
    if d1_direction == 0:
        return 0

    relevant_pairs = [p for p in PAIRS if currency in p.split("/")]
    if not relevant_pairs:
        return 0

    extended_count = 0
    total = 0
    for pair in relevant_pairs:
        pdata = pair_data.get(pair, {})
        if not pdata:
            continue
        total += 1
        ext = pdata.get("extended", {})
        if not isinstance(ext, dict):
            continue
        if not ext.get("extended", False):
            continue
        # Check extension direction matches currency direction in this pair
        base, quote = pair.split("/")
        pair_dir = pdata.get("direction", "neutral")
        if pair_dir == "neutral":
            continue
        pair_dir_int = 1 if pair_dir == "bull" else -1
        # Currency direction in this pair:
        # if currency is base and pair is bull → currency is bull (matches d1_direction +1)
        # if currency is quote and pair is bull → currency is bear (matches d1_direction -1)
        if currency == base:
            currency_pair_dir = pair_dir_int
        else:
            currency_pair_dir = -pair_dir_int

        if currency_pair_dir == d1_direction:
            extended_count += 1

    if total == 0:
        return 0

    ratio = extended_count / total
    if ratio == 0:      return +1  # no extension, clean runway
    if ratio < 0.34:    return  0
    if ratio < 0.67:    return -1  # majority extended
    return -2                       # broadly extended


# ── Input 6: RSI Breadth ─────────────────────────────────────────────────────

def _score_rsi_breadth(d1_scores: dict, h4_scores: dict, currency: str,
                        d1_direction: int) -> int:
    """
    Count pairs where RSI vote confirms currency's D1 directional bias.
    Uses H4 signals for RSI vote (more responsive than D1 RSI).
    
    Broad RSI confirmation = sustainable momentum (+2)
    Narrow confirmation = one pair driving the reading, less reliable (-1)
    """
    if d1_direction == 0:
        return 0

    relevant_pairs = [p for p in PAIRS if currency in p.split("/")]
    if not relevant_pairs:
        return 0

    confirming = 0
    total = 0
    for pair in relevant_pairs:
        # Prefer H4 RSI signal, fall back to D1
        pdata = h4_scores.get(pair) or d1_scores.get(pair, {})
        if not pdata:
            continue
        total += 1
        rsi_vote = pdata.get("signals", {}).get("RSI", 0)
        if rsi_vote == 0:
            continue
        # RSI vote is +1 (bullish) or -1 (bearish)
        # Adjust for whether currency is base or quote
        base, _ = pair.split("/")
        if currency != base:
            rsi_vote = -rsi_vote  # invert for quote currency
        if rsi_vote == d1_direction:
            confirming += 1

    if total == 0:
        return 0

    breadth = confirming / total
    if breadth > 0.75: return +2
    if breadth > 0.50: return +1
    if breadth > 0.25: return  0
    return -1  # narrow confirmation


# ── Currency D1 direction helper ──────────────────────────────────────────────

def _currency_d1_direction(d1_scores: dict, currency: str) -> int:
    """
    Derive net D1 directional bias for a currency from all its pair scores.
    Returns +1 (net bull), -1 (net bear), 0 (neutral).
    """
    relevant = [p for p in PAIRS if currency in p.split("/")]
    votes = []
    for pair in relevant:
        pdata = d1_scores.get(pair, {})
        direction = pdata.get("direction", "neutral")
        score = pdata.get("score", 0)
        if direction == "neutral" or abs(score) < 2:
            continue
        base, _ = pair.split("/")
        dir_int = 1 if direction == "bull" else -1
        if currency != base:
            dir_int = -dir_int
        votes.append(dir_int)

    if not votes:
        return 0
    net = sum(votes)
    if net > 0:  return +1
    if net < 0:  return -1
    return 0


# ── EWMA smoother ─────────────────────────────────────────────────────────────

def _ewma(new_val: float, prev_val: float | None, alpha: float = 0.6) -> float:
    """
    3-week EWMA with alpha=0.6.
    Higher alpha = more weight on current reading (less smoothing).
    0.6 means current week counts for 60%, previous smoothed for 40%.
    """
    if prev_val is None:
        return new_val
    return round(alpha * new_val + (1 - alpha) * prev_val, 1)


# ── Total range normalisation ─────────────────────────────────────────────────
# Theoretical max: +1 + +1 + +2 + +2 + +1 + +2 = +9
# Theoretical min: -2 + -1 + -2 + -2 + -2 + -1 = -10
# We normalise to -100/+100 using symmetric ±10 denominator for simplicity.
SCORE_MAX = 10.0


# ── Master conviction computation ─────────────────────────────────────────────

def compute_conviction(cot_data: dict, d1_scores: dict, h4_scores: dict,
                        csm_rankings: dict, prev_conviction: dict | None = None) -> dict:
    """
    Compute per-currency conviction scores and pair-level scores.

    Parameters
    ----------
    cot_data       : output of cot.fetch_cot_data()
    d1_scores      : current d1_scores dict (from d1_scores.json)
    h4_scores      : current h4_scores dict (from h4_scores.json)
    csm_rankings   : CSM 0-100 rankings dict
    prev_conviction: previous conviction.json (for EWMA smoothing)

    Returns
    -------
    dict with 'currencies' and 'pairs' sub-dicts, ready to save.
    """
    cot_currencies = cot_data.get("currencies", {})
    prev_currencies = (prev_conviction or {}).get("currencies", {})
    cot_stale = cot_data.get("cot_stale", True)

    currency_scores = {}
    currency_raw = {}  # for pair computation before EWMA

    for ccy in CURRENCIES:
        cot_ccy = cot_currencies.get(ccy, {})
        available = cot_ccy.get("available", False)

        # Get previous scores for hysteresis and EWMA
        prev_ccy = prev_currencies.get(ccy, {})
        prev_comp = prev_ccy.get("components", {})
        prev_conv = prev_ccy.get("conviction")

        # Currency directional bias from D1
        d1_dir = _currency_d1_direction(d1_scores, ccy)

        # ── Score each input ──────────────────────────────────────────────────
        if available and not cot_stale:
            s_pos   = _score_cot_position(
                cot_ccy.get("noncomm_pct"),
                prev_comp.get("cot_position", 0)
            )
            s_oi    = _score_cot_oi(
                cot_ccy.get("oi_current"),
                cot_ccy.get("oi_4w_ago"),
                d1_dir
            )
            s_disagg = _score_cot_disagg(
                cot_ccy.get("am_pct"),
                cot_ccy.get("lf_pct")
            )
        else:
            # COT unavailable or stale — zero COT components, keep technical
            s_pos = s_oi = s_disagg = 0

        s_csm  = _score_csm_extreme(csm_rankings.get(ccy))
        s_ext  = _score_extension(d1_scores, ccy, d1_dir)
        s_rsi  = _score_rsi_breadth(d1_scores, h4_scores, ccy, d1_dir)

        raw = s_pos + s_oi + s_disagg + s_csm + s_ext + s_rsi
        normalised = round(raw / SCORE_MAX * 100)

        # EWMA smoothing
        smoothed = _ewma(normalised, prev_conv, alpha=0.6)
        smoothed_int = int(round(smoothed))

        currency_raw[ccy] = normalised  # pre-EWMA for pair calc
        currency_scores[ccy] = {
            "conviction": smoothed_int,
            "direction":  d1_dir,
            "components": {
                "cot_position": s_pos,
                "cot_oi":       s_oi,
                "cot_disagg":   s_disagg,
                "csm_extreme":  s_csm,
                "extension":    s_ext,
                "rsi_breadth":  s_rsi,
            },
            "raw": raw,
            "cot_available": available and not cot_stale,
        }

    # ── Pair-level conviction: (base_raw - quote_raw) / 2 ────────────────────
    pair_scores = {}
    for pair in PAIRS:
        base, quote = pair.split("/")
        b_raw = currency_raw.get(base, 0)
        q_raw = currency_raw.get(quote, 0)
        pair_conv = int(round((b_raw - q_raw) / 2))
        pair_scores[pair] = max(-100, min(100, pair_conv))

    return {
        "currencies": currency_scores,
        "pairs":      pair_scores,
        "cot_date":   cot_data.get("cot_date", "unknown"),
        "cot_stale":  cot_stale,
    }
