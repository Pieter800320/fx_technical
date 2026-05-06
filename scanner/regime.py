# scanner/regime.py — Proxy regime classifier
#
# Architecture (post-redesign):
#   compute_w1_regime()   — W1 macro regime from cross-asset data (daily update)
#   classify_regime()     — H4 structural regime from price action
#   compute_final_regime()— combines W1 + H4 structural + macro overlay + AI sentiment
#
# Final regime weights: W1 25% / H4 structural 30% / Macro overlay 30% / AI sentiment 15%
# W1 acts as a slow anchor — changes rarely, persists through noise.
# Regime persistence: requires 2 consecutive confirms to flip W1 classification.

import numpy as np


def compute_w1_regime(macro):
    """
    W1 (weekly) macro regime from cross-asset data already in news_brief.json.
    Inputs: SPX, VIX, US10Y, DXY, Gold, Copper — all available from macro scan.
    Returns a score 0-10 and regime label.

    Composite:
      0.30 × Equity trend     (SPX — rising = risk-on)
      0.25 × Volatility regime (VIX — low/falling = risk-on, high/rising = risk-off)
      0.20 × Rates direction  (US10Y — rising too fast = risk-off for FX risk pairs)
      0.15 × FX risk proxy    (Gold — rising = risk-off)
      0.10 × USD direction    (DXY — falling = risk-on for risk pairs)

    Each component scored -1 / 0 / +1, then mapped to 0-10.
    """
    if not macro:
        return {"score": 5.0, "regime": "Mixed", "confidence": "Low",
                "components": {}, "note": "No macro data"}

    def component(key, pos_thr, neg_thr, invert=False):
        d = macro.get(key)
        if not d:
            return 0, None
        chg = d.get("change_pct", 0)
        if invert:
            score = -1 if chg > pos_thr else 1 if chg < neg_thr else 0
        else:
            score = 1 if chg > pos_thr else -1 if chg < neg_thr else 0
        return score, round(chg, 2)

    spx_s,   spx_chg  = component("spx",    0.3,  -0.3,  invert=False)  # rising SPX = risk-on
    vix_s,   vix_chg  = component("vix",    5.0,  -5.0,  invert=True)   # rising VIX = risk-off
    us10y_s, us10y_chg= component("us10y",  3.0,  -3.0,  invert=True)   # sharply rising yields = risk-off
    gold_s,  gold_chg = component("gold",   0.8,  -0.8,  invert=True)   # rising gold = risk-off
    dxy_s,   dxy_chg  = component("dxy",    0.4,  -0.4,  invert=True)   # falling DXY = risk-on

    weights = {"spx": 0.30, "vix": 0.25, "us10y": 0.20, "gold": 0.15, "dxy": 0.10}
    scores  = {"spx": spx_s, "vix": vix_s, "us10y": us10y_s, "gold": gold_s, "dxy": dxy_s}
    changes = {"spx": spx_chg, "vix": vix_chg, "us10y": us10y_chg, "gold": gold_chg, "dxy": dxy_chg}

    # Weighted composite: ranges from -1 to +1
    raw = sum(weights[k] * scores[k] for k in weights)

    # Map to 0-10: -1 → 0, 0 → 5, +1 → 10
    score = round((raw + 1) / 2 * 10, 2)
    score = max(0, min(10, score))

    if score >= 7.5:   regime, conf = "Risk-On",  "High"
    elif score >= 6.0: regime, conf = "Risk-On",  "Medium"
    elif score >= 5.0: regime, conf = "Risk-On",  "Low"
    elif score >= 4.0: regime, conf = "Mixed",    "Low"
    elif score >= 3.0: regime, conf = "Risk-Off", "Low"
    elif score >= 2.0: regime, conf = "Risk-Off", "Medium"
    else:              regime, conf = "Risk-Off", "High"

    comps = {k: {"score": scores[k], "change_pct": changes[k]} for k in weights}

    return {
        "score":      score,
        "regime":     regime,
        "confidence": conf,
        "components": comps,
    }


def apply_w1_persistence(new_w1, stored_w1):
    """
    Regime persistence — require 2 consecutive confirms before W1 flips.
    Prevents noise-driven flips from macro data day-to-day moves.

    stored_w1 must contain:
        regime       — current confirmed regime
        pending      — proposed next regime (if different)
        pending_count — how many consecutive scans pending has been seen
    """
    if not stored_w1:
        return {**new_w1, "pending": None, "pending_count": 0, "confirmed": True}

    current_regime = stored_w1.get("regime", "Mixed")
    pending        = stored_w1.get("pending")
    pending_count  = stored_w1.get("pending_count", 0)
    new_regime     = new_w1["regime"]

    if new_regime == current_regime:
        # Same regime — reset any pending flip
        return {**new_w1, "regime": current_regime,
                "pending": None, "pending_count": 0, "confirmed": True}

    if new_regime == pending:
        pending_count += 1
    else:
        pending        = new_regime
        pending_count  = 1

    if pending_count >= 2:
        # Confirmed flip
        return {**new_w1, "regime": new_regime,
                "pending": None, "pending_count": 0, "confirmed": True}
    else:
        # Hold current regime, note pending
        return {**new_w1, "regime": current_regime,
                "score": stored_w1.get("score", new_w1["score"]),
                "pending": pending, "pending_count": pending_count, "confirmed": False}


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


def compute_final_regime(h4_regime, macro_bias, ai_sentiment, w1_regime=None):
    """
    Combines four independent sources into a final regime reading.

    W1 macro       25% — cross-asset weekly anchor (slow, persistent)
    H4 structural  30% — price-action based, 4h update
    Macro overlay  30% — instrument-based (VIX/DXY/US2Y/Gold/SPX/Copper), 4x daily
    AI sentiment   15% — news-based, 4x daily

    Each source normalized to 0-10 scale before weighting.
    Output: final_regime dict with regime/confidence/score/components
    """
    components = {}

    # ── W1 macro anchor (0-10)
    if w1_regime and w1_regime.get("score") is not None:
        w1_score = max(0, min(10, float(w1_regime["score"])))
        components["w1"] = {
            "score":      w1_score,
            "label":      w1_regime.get("regime", "Mixed"),
            "confidence": w1_regime.get("confidence", "Low"),
            "confirmed":  w1_regime.get("confirmed", True),
            "pending":    w1_regime.get("pending"),
        }
    else:
        w1_score = 5.0
        components["w1"] = {"score": 5.0, "label": "Pending", "confidence": "Low"}

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

    # ── Macro overlay (0-10)
    if macro_bias and macro_bias.get("max", 0) > 0:
        raw = macro_bias["score"]
        max_v = macro_bias["max"]
        macro_score = round((raw / max_v + 1) / 2 * 10, 1)
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

    # ── AI sentiment (1-10)
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

    # ── Weighted average: W1×0.25 + H4×0.30 + Macro×0.30 + AI×0.15
    final_score = round(
        w1_score   * 0.25 +
        h4_score   * 0.30 +
        macro_score* 0.30 +
        ai_score   * 0.15,
        2
    )
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

    # ── Disagreement penalty — spread ≥ 4 forces Mixed
    scores = [w1_score, h4_score, macro_score, ai_score]
    spread = max(scores) - min(scores)
    if spread >= 4 and confidence != "Low":
        confidence = "Low"
        regime = "Mixed"

    # ── W1 tide penalty — if W1 strongly opposes final direction, scale down confidence
    w1_label = components["w1"]["label"]
    if w1_label == "Risk-Off" and regime == "Risk-On" and w1_score <= 3:
        confidence = "Low"
    elif w1_label == "Risk-On" and regime == "Risk-Off" and w1_score >= 7:
        confidence = "Low"

    # ── Direction (H4 structural as momentum indicator)
    h4_rank    = {"Risk-On": 3, "Mixed": 2, "Ranging": 2, "Risk-Off": 1}.get(h4_reg, 2)
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
