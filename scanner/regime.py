# scanner/regime.py — Proxy regime classifier
#
# Changes from audit:
#   - XAU/USD gold signal now works: scan_d1.py fetches and scores XAU/USD
#     via REGIME_EXTRA_PAIRS, so d1_scores["XAU/USD"] is populated.
#   - vol_ratio / conf_multiplier removed. It was using ADX as a volatility
#     proxy (ADX measures directional strength, not volatility — wrong metric).
#     The ranging detection via trend_ratio + dispersion already handles low-
#     volatility environments correctly without a multiplier.
#   - Risk basket expanded to include AUD/JPY and NZD/JPY (most regime-
#     sensitive pairs in G10). Already present in original — retained.
#   - Confidence thresholds unchanged.

import numpy as np


def _pair_score_to_dir(score):
    if score >= 3:   return  1
    if score <= -3: return -1
    return 0


def classify_regime(csm, d1_scores, prev_h4_regime=False):
    rankings = csm.get("rankings", {})
    if not rankings:
        return {
            "regime": "Unknown", "confidence": "Low",
            "data_source": "D1",
            "signals": {},
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
        return _pair_score_to_dir(d1_scores.get(pair, {}).get("score", 0))

    usd_long  = np.mean([dir_score("USD/JPY"), dir_score("USD/CHF"), dir_score("USD/CAD")])
    usd_short = np.mean([dir_score("EUR/USD"), dir_score("GBP/USD"),
                         dir_score("AUD/USD"), dir_score("NZD/USD")])
    usd_proxy = usd_long - usd_short

    if usd_proxy > 1.0:    usd_off, usd_on = 2, 0
    elif usd_proxy > 0.5:  usd_off, usd_on = 1, 0
    elif usd_proxy < -1.0: usd_off, usd_on = 0, 2
    elif usd_proxy < -0.5: usd_off, usd_on = 0, 1
    else:                  usd_off, usd_on = 0, 0

    # Risk basket: AUD/JPY and NZD/JPY lead on risk. AUD/USD, NZD/USD, GBP/JPY, EUR/JPY support.
    risk_basket = np.mean([
        dir_score("AUD/USD"), dir_score("NZD/USD"),
        dir_score("GBP/JPY"), dir_score("EUR/JPY"),
        dir_score("AUD/JPY"), dir_score("NZD/JPY"),
    ])
    if risk_basket > 0.3:    risk_on, risk_off = 1, 0
    elif risk_basket < -0.3: risk_on, risk_off = 0, 1
    else:                    risk_on, risk_off = 0, 0

    # Gold: XAU/USD — now properly fetched via REGIME_EXTRA_PAIRS in scan_d1.py
    # Gold rising = risk-off. Gold falling = risk-on.
    gold_dir = d1_scores.get("XAU/USD", {}).get("direction", "neutral")
    gold_off  = 1 if gold_dir == "bull"  else 0  # gold up = risk-off
    gold_on   = 1 if gold_dir == "bear"  else 0  # gold down = risk-on

    # Trend participation and CSM dispersion
    trend_count = sum(
        1 for v in d1_scores.values()
        if isinstance(v, dict) and v.get("filter_ok", True)
        and v.get("raw", {}).get("adx", 0) > 20
    )
    total_pairs = len([v for v in d1_scores.values() if isinstance(v, dict)])
    trend_ratio = trend_count / total_pairs if total_pairs > 0 else 0
    dispersion  = max(rankings.values()) - min(rankings.values())

    # Ranging override: low trend participation + compressed CSM = no regime signal
    if trend_ratio < 0.4 and dispersion < 25:
        return {
            "regime":      "Ranging",
            "confidence":  "Medium",
            "data_source": "D1",
            "signals": {
                "sh_divergence": round(sh_div, 1),
                "usd_proxy":     round(usd_proxy, 2),
                "risk_basket":   round(risk_basket, 2),
                "gold_direction": gold_dir,
                "trend_ratio":   round(trend_ratio, 2),
                "dispersion":    round(dispersion, 1),
            },
        }

    # Final vote tally — weights: SH div ×2, USD proxy ×2, risk basket ×1, gold ×1
    risk_off_score = sh_off * 2 + usd_off * 2 + risk_off * 1 + gold_off * 1
    risk_on_score  = sh_on  * 2 + usd_on  * 2 + risk_on  * 1 + gold_on  * 1

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
        "data_source": "D1",
        "signals": {
            "sh_divergence":  round(sh_div, 1),
            "usd_proxy":      round(usd_proxy, 2),
            "risk_basket":    round(risk_basket, 2),
            "gold_direction": gold_dir,
            "trend_ratio":    round(trend_ratio, 2),
            "dispersion":     round(dispersion, 1),
            "risk_off_votes": round(risk_off_score, 2),
            "risk_on_votes":  round(risk_on_score, 2),
        },
    }
