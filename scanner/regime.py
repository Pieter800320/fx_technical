# scanner/regime.py — Proxy regime classifier
#
# Architecture (post-redesign):
#   classify_regime()    — H4 structural regime from price action
#   compute_final_regime() — combines H4 structural + macro overlay + AI sentiment
#
# Final regime weights: H4 structural 40% / Macro overlay 40% / AI sentiment 20%
# This gives real-time sensitivity (macro/AI update 4x daily) while keeping
# price-action grounding (H4 structural updates every 4h).

import numpy as np


def _pair_score_to_dir(score):
    if score >= 3:  return  1
    if score <= -3: return -1
    return 0


def classify_regime(csm, h4_scores, prev_h4_regime=False):
    """
    H4 structural regime — reads H4 pair scores and H4 CSM rankings.
    Called by scan_h4.py every 4 hours.
    Returns regime dict with regime/confidence/signals.
    """
    # Use H4 CSM rankings if available, fall back to D1 rankings
    rankings = csm.get("h4_rankings") or csm.get("rankings", {})
    if not rankings:
        return {
            "regime": "Unknown", "confidence": "Low",
            "data_source": "H4", "signals": {},
        }

    jpy = rankings.get("JPY", 50)
    chf = rankings.get("CHF", 50)
    aud = rankings.get("AUD", 50)
    nzd = rankings.get("NZD", 50)
    cad = rankings.get("CAD", 50)

    # Safe-haven divergence: JPY+CHF vs AUD+NZD+CAD
    sh_div = (jpy + chf) / 2 - (aud + nzd + cad) / 3

    if sh_div > 20:    sh_off, sh_on = 2, 0
    elif sh_div > 10:  sh_off, sh_on = 1, 0
    elif sh_div < -20: sh_off, sh_on = 0, 2
    elif sh_div < -10: sh_off, sh_on = 0, 1
    else:              sh_off, sh_on = 0, 0

    def dir_score(pair):
        return _pair_score_to_dir(h4_scores.get(pair, {}).get("score", 0))

    usd_long  = np.mean([dir_score("USD/JPY"), dir_score("USD/CHF"), dir_score("USD/CAD")])
    usd_short = np.mean([dir_score("EUR/USD"), dir_score("GBP/USD"),
                         dir_score("AUD/USD"), dir_score("NZD/USD")])
    usd_proxy = usd_long - usd_short

    if usd_proxy > 1.0:    usd_off, usd_on = 2, 0
    elif usd_proxy > 0.5:  usd_off, usd_on = 1, 0
    elif usd_proxy < -1.0: usd_off, usd_on = 0, 2
    elif usd_proxy < -0.5: usd_off, usd_on = 0, 1
    else:                  usd_off, usd_on = 0, 0

    risk_basket = np.mean([
        dir_score("AUD/USD"), dir_score("NZD/USD"),
        dir_score("GBP/JPY"), dir_score("EUR/JPY"),
        dir_score("AUD/JPY"), dir_score("NZD/JPY"),
    ])
    if risk_basket > 0.3:    risk_on, risk_off = 1, 0
    elif risk_basket < -0.3: risk_on, risk_off = 0, 1
    else:                    risk_on, risk_off = 0, 0

    # Trend participation and CSM dispersion
    trend_count = sum(
        1 for v in h4_scores.values()
        if isinstance(v, dict) and v.get("filter_ok", True)
        and v.get("raw", {}).get("adx", 0) > 20
    )
    total_pairs = len([v for v in h4_scores.values() if isinstance(v, dict)])
    trend_ratio = trend_count / total_pairs if total_pairs > 0 else 0
    dispersion  = max(rankings.values()) - min(rankings.values()) if rankings else 0

    # Ranging override
    if trend_ratio < 0.4 and dispersion < 25:
        return {
            "regime":      "Ranging",
            "confidence":  "Medium",
            "data_source": "H4",
            "signals": {
                "sh_divergence": round(sh_div, 1),
                "usd_proxy":     round(usd_proxy, 2),
                "risk_basket":   round(risk_basket, 2),
                "trend_ratio":   round(trend_ratio, 2),
                "dispersion":    round(dispersion, 1),
            },
        }

    # Final vote tally
    risk_off_score = sh_off * 2 + usd_off * 2 + risk_off * 1
    risk_on_score  = sh_on  * 2 + usd_on  * 2 + risk_on  * 1

    if risk_off_score >= 3 and risk_off_score > risk_on_score:
        regime     = "Risk-Off"
        confidence = "High" if risk_off_score >= 5 else "Medium"
    elif risk_on_score >= 3 and risk_on_score > risk_off_score:
        regime     = "Risk-On"
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
        "data_source": "H4",
        "signals": {
            "sh_divergence":  round(sh_div, 1),
            "usd_proxy":      round(usd_proxy, 2),
            "risk_basket":    round(risk_basket, 2),
            "trend_ratio":    round(trend_ratio, 2),
            "dispersion":     round(dispersion, 1),
            "risk_off_votes": round(risk_off_score, 2),
            "risk_on_votes":  round(risk_on_score, 2),
        },
    }


def compute_final_regime(h4_regime, macro_bias, ai_sentiment):
    """
    Combines three independent sources into a final regime reading.

    H4 structural  40% — price-action based, 4h update
    Macro overlay  40% — instrument-based (VIX/DXY/US2Y/Gold/SPX/Copper), 4x daily
    AI sentiment   20% — news-based, 4x daily

    Each source normalized to 0-10 scale before weighting.
    Output: final_regime dict with regime/confidence/score/components
    """
    components = {}

    # ── H4 structural (0-10)
    h4_reg = h4_regime.get("regime", "Mixed") if h4_regime else "Mixed"
    h4_conf = h4_regime.get("confidence", "Low") if h4_regime else "Low"
    h4_map = {
        ("Risk-On",  "High"):   10,
        ("Risk-On",  "Medium"): 8,
        ("Risk-On",  "Low"):    6.5,
        ("Mixed",    "High"):   5,
        ("Mixed",    "Medium"): 5,
        ("Mixed",    "Low"):    5,
        ("Ranging",  "Medium"): 5,
        ("Risk-Off", "Low"):    3.5,
        ("Risk-Off", "Medium"): 2,
        ("Risk-Off", "High"):   0,
    }
    h4_score = h4_map.get((h4_reg, h4_conf), 5)
    components["h4"] = {"score": h4_score, "label": h4_reg, "confidence": h4_conf}

    # ── Macro overlay (0-10) — normalize +/-6 range
    if macro_bias and macro_bias.get("max", 0) > 0:
        raw = macro_bias["score"]
        max_v = macro_bias["max"]
        macro_score = round((raw / max_v + 1) / 2 * 10, 1)  # maps -max..+max → 0..10
        macro_score = max(0, min(10, macro_score))
        components["macro"] = {
            "score": macro_score,
            "raw": raw,
            "max": max_v,
            "interpretation": macro_bias.get("interpretation", ""),
        }
    else:
        macro_score = 5
        components["macro"] = {"score": 5, "raw": 0, "max": 0, "interpretation": "Pending"}

    # ── AI sentiment (1-10) — direct from Haiku call
    if ai_sentiment and ai_sentiment.get("score") is not None:
        ai_score = max(1, min(10, float(ai_sentiment["score"])))
        components["ai"] = {
            "score": ai_score,
            "label": ai_sentiment.get("label", ""),
            "rationale": ai_sentiment.get("rationale", ""),
        }
    else:
        ai_score = 5
        components["ai"] = {"score": 5, "label": "Pending", "rationale": ""}

    # ── Weighted average
    final_score = round(h4_score * 0.40 + macro_score * 0.40 + ai_score * 0.20, 2)
    components["final_score"] = final_score

    # ── Classify
    if final_score >= 8:
        regime, confidence = "Risk-On", "High"
    elif final_score >= 6.5:
        regime, confidence = "Risk-On", "Medium"
    elif final_score >= 5.5:
        regime, confidence = "Risk-On", "Low"
    elif final_score >= 4.5:
        regime, confidence = "Mixed", "Low"
    elif final_score >= 3.5:
        regime, confidence = "Risk-Off", "Low"
    elif final_score >= 2:
        regime, confidence = "Risk-Off", "Medium"
    else:
        regime, confidence = "Risk-Off", "High"

    # ── Disagreement penalty → Mixed
    scores = [h4_score, macro_score, ai_score]
    spread = max(scores) - min(scores)
    if spread >= 4 and confidence != "Low":
        confidence = "Low"
        regime = "Mixed"

    # ── Direction (H4 structural as momentum indicator)
    h4_rank = {"Risk-On": 3, "Mixed": 2, "Ranging": 2, "Risk-Off": 1}.get(h4_reg, 2)
    final_rank = {"Risk-On": 3, "Mixed": 2, "Risk-Off": 1}.get(regime, 2)
    if h4_rank > final_rank:    direction = "Strengthening"
    elif h4_rank < final_rank:  direction = "Deteriorating"
    else:                       direction = "Stable"

    return {
        "regime":     regime,
        "confidence": confidence,
        "score":      final_score,
        "direction":  direction,
        "components": components,
        "spread":     round(spread, 1),
    }
