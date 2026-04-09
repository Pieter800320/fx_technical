"""
scanner/regime.py
Improved market regime detector.

Signals:
  1A. Safe-haven divergence: (JPY+CHF)/2 - (AUD+NZD+CAD)/3
  1B. USD proxy: avg(USD pairs) - avg(EUR/GBP/AUD/NZD pairs) from D1 scores
  1C. Risk proxy basket: avg direction of AUDUSD+NZDUSD+GBPJPY+EURJPY
  1D. Gold direction (optional)
  1E. Volatility confidence modifier: ATR(14)/ATR(100) on D1

Override: if VOL_RATIO > 1.3, use H4 data instead of D1 (hysteresis: revert when < 1.1)
"""

import numpy as np


def _pair_score_to_dir(score):
    if score >= 3:   return 1
    if score <= -3:  return -1
    return 0


def _vol_ratio(d1_scores):
    """Approximate VOL_RATIO from ATR data in D1 scores."""
    atrs = []
    for v in d1_scores.values():
        if isinstance(v, dict) and v.get("raw", {}).get("adx"):
            atrs.append(v["raw"].get("adx", 0))
    if not atrs:
        return 1.0
    avg_adx = np.mean(atrs)
    # Proxy: high ADX = high volatility trend
    if avg_adx > 30:  return 1.4
    if avg_adx > 20:  return 1.0
    return 0.7


def classify_regime(csm, d1_scores, prev_h4_regime=False):
    """
    csm:             { "rankings": {...}, ... }
    d1_scores:       { "EUR/USD": {"score": -4, "direction": "bear", ...}, ... }
    prev_h4_regime:  bool — True if last regime used H4 override

    Returns {
        "regime":      str,
        "confidence":  str,
        "data_source": "D1" or "H4",
        "vol_ratio":   float,
        "signals":     dict,
    }
    """
    rankings = csm.get("rankings", {})
    if not rankings:
        return {"regime": "Unknown", "confidence": "Low",
                "data_source": "D1", "vol_ratio": 1.0, "signals": {}}

    # ── Volatility confidence modifier ───────────────────────────────────────
    vol_ratio = _vol_ratio(d1_scores)
    if vol_ratio > 1.3:
        data_source      = "H4"
        conf_multiplier  = 0.5
    elif vol_ratio < 0.8:
        data_source      = "D1"
        conf_multiplier  = 1.5
    else:
        data_source      = "D1"
        conf_multiplier  = 1.0

    # Hysteresis: keep H4 until VOL_RATIO < 1.1
    if prev_h4_regime and vol_ratio < 1.1:
        data_source = "D1"

    # ── 1A: Safe-haven divergence ─────────────────────────────────────────────
    jpy = rankings.get("JPY", 50)
    chf = rankings.get("CHF", 50)
    aud = rankings.get("AUD", 50)
    nzd = rankings.get("NZD", 50)
    cad = rankings.get("CAD", 50)
    usd = rankings.get("USD", 50)

    sh_div = (jpy + chf) / 2 - (aud + nzd + cad) / 3

    if sh_div > 20:   sh_off, sh_on = 2, 0
    elif sh_div > 10: sh_off, sh_on = 1, 0
    elif sh_div < -20: sh_off, sh_on = 0, 2
    elif sh_div < -10: sh_off, sh_on = 0, 1
    else:              sh_off, sh_on = 0, 0

    # ── 1B: USD proxy from pair scores ───────────────────────────────────────
    def dir_score(pair):
        return _pair_score_to_dir(d1_scores.get(pair, {}).get("score", 0))

    usd_long  = np.mean([dir_score("USD/JPY"), dir_score("USD/CHF"), dir_score("USD/CAD")])
    usd_short = np.mean([dir_score("EUR/USD"), dir_score("GBP/USD"),
                          dir_score("AUD/USD"), dir_score("NZD/USD")])
    # usd_short is negative when USD is strong (pairs are selling)
    usd_proxy = usd_long - usd_short  # positive = USD strong

    if usd_proxy > 1.0:    usd_off, usd_on = 2, 0
    elif usd_proxy > 0.5:  usd_off, usd_on = 1, 0
    elif usd_proxy < -1.0: usd_off, usd_on = 0, 2
    elif usd_proxy < -0.5: usd_off, usd_on = 0, 1
    else:                  usd_off, usd_on = 0, 0

    # ── 1C: Risk proxy basket ─────────────────────────────────────────────────
    risk_basket = np.mean([
        dir_score("AUD/USD"), dir_score("NZD/USD"),
        dir_score("GBP/JPY"), dir_score("EUR/JPY"),
    ])
    if risk_basket > 0.3:   risk_on, risk_off = 1, 0
    elif risk_basket < -0.3: risk_on, risk_off = 0, 1
    else:                    risk_on, risk_off = 0, 0

    # ── 1D: Gold ─────────────────────────────────────────────────────────────
    gold_dir = d1_scores.get("XAU/USD", {}).get("direction", "neutral")
    gold_off = 1 if gold_dir == "bear" else 0
    gold_on  = 1 if gold_dir == "bull" else 0

    # ── 1E: Trend / dispersion ────────────────────────────────────────────────
    trend_count = sum(
        1 for v in d1_scores.values()
        if isinstance(v, dict) and v.get("filter_ok", True)
        and v.get("raw", {}).get("adx", 0) > 20
    )
    total_pairs = len([v for v in d1_scores.values() if isinstance(v, dict)])
    trend_ratio = trend_count / total_pairs if total_pairs > 0 else 0
    dispersion  = max(rankings.values()) - min(rankings.values())

    # ── Ranging check ─────────────────────────────────────────────────────────
    if trend_ratio < 0.4 and dispersion < 25:
        return {
            "regime":      "Ranging",
            "confidence":  "Medium",
            "data_source": data_source,
            "vol_ratio":   round(vol_ratio, 2),
            "signals": {
                "sh_divergence": round(sh_div, 1),
                "usd_proxy":     round(usd_proxy, 2),
                "risk_basket":   round(risk_basket, 2),
                "trend_ratio":   round(trend_ratio, 2),
                "dispersion":    round(dispersion, 1),
                "vol_ratio":     round(vol_ratio, 2),
            }
        }

    # ── Weighted vote ─────────────────────────────────────────────────────────
    risk_off_raw = (sh_off * 2 + usd_off * 2 + risk_off * 1 + gold_off * 1)
    risk_on_raw  = (sh_on  * 2 + usd_on  * 2 + risk_on  * 1 + gold_on  * 1)

    risk_off_score = risk_off_raw * conf_multiplier
    risk_on_score  = risk_on_raw  * conf_multiplier

    # ── Final label ───────────────────────────────────────────────────────────
    if risk_off_score >= 3 and risk_off_score > risk_on_score:
        regime = "Risk-Off"
        confidence = "High" if risk_off_score >= 5 else "Medium"
    elif risk_on_score >= 3 and risk_on_score > risk_off_score:
        regime = "Risk-On"
        confidence = "High" if risk_on_score >= 5 else "Medium"
    elif abs(risk_off_score - risk_on_score) <= 1:
        regime     = "Mixed"
        confidence = "Low"
    else:
        regime     = "Risk-Off" if risk_off_score > risk_on_score else "Risk-On"
        confidence = "Low"

    return {
        "regime":      regime,
        "confidence":  confidence,
        "data_source": data_source,
        "vol_ratio":   round(vol_ratio, 2),
        "signals": {
            "sh_divergence":   round(sh_div, 1),
            "usd_proxy":       round(usd_proxy, 2),
            "risk_basket":     round(risk_basket, 2),
            "gold_direction":  gold_dir,
            "trend_ratio":     round(trend_ratio, 2),
            "dispersion":      round(dispersion, 1),
            "risk_off_votes":  round(risk_off_score, 2),
            "risk_on_votes":   round(risk_on_score, 2),
            "conf_multiplier": round(conf_multiplier, 2),
        }
    }
