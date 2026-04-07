"""
scanner/regime.py
Proxy market regime detector using existing CSM + score data.
No additional API calls required.

Regime classification:
  Risk-Off:  USD + JPY + CHF strong, AUD + NZD + CAD weak, Gold bearish
  Risk-On:   AUD + NZD + CAD strong, USD + JPY + CHF weak, Gold bullish
  Ranging:   Low dispersion, most pairs neutral, ADX generally low
  Mixed:     Contradictory signals — no clear regime

Signals used:
  1. Safe-haven score:  avg(JPY, CHF) - avg(AUD, NZD, CAD)  [from CSM]
  2. USD strength:      USD CSM rank position
  3. Gold direction:    D1 score for XAU/USD
  4. Trend count:       number of pairs with ADX > 20
  5. Dispersion:        spread between strongest and weakest currency
"""


def classify_regime(csm: dict, d1_scores: dict) -> dict:
    """
    csm:       { "rankings": {"USD": 100, "JPY": 80, ...}, ... }
    d1_scores: { "EUR/USD": {"score": -4, "direction": "bear", ...}, ... }

    Returns {
        "regime":     "Risk-Off" | "Risk-On" | "Ranging" | "Mixed",
        "confidence": "High" | "Medium" | "Low",
        "signals":    { ... detail ... },
    }
    """
    rankings = csm.get("rankings", {})
    if not rankings:
        return {"regime": "Unknown", "confidence": "Low", "signals": {}}

    # ── Signal 1: Safe-haven vs commodity currency divergence ────────────────
    safe_havens    = ["JPY", "CHF"]
    commodity_ccys = ["AUD", "NZD", "CAD"]

    sh_avg  = sum(rankings.get(c, 50) for c in safe_havens)  / len(safe_havens)
    com_avg = sum(rankings.get(c, 50) for c in commodity_ccys) / len(commodity_ccys)
    usd_val = rankings.get("USD", 50)

    sh_divergence = sh_avg - com_avg   # positive = risk-off, negative = risk-on

    # ── Signal 2: Gold direction ─────────────────────────────────────────────
    gold_data = d1_scores.get("XAU/USD", {})
    gold_dir  = gold_data.get("direction", "neutral")
    gold_score = gold_data.get("score", 0)

    # ── Signal 3: Trend participation (ADX > 20 count) ───────────────────────
    trending_count = sum(
        1 for v in d1_scores.values()
        if isinstance(v, dict) and v.get("filter_ok", True)
        and v.get("raw", {}).get("adx", 0) > 20
    )
    total_pairs = len([v for v in d1_scores.values() if isinstance(v, dict)])
    trend_ratio = trending_count / total_pairs if total_pairs > 0 else 0

    # ── Signal 4: CSM dispersion ─────────────────────────────────────────────
    vals = list(rankings.values())
    dispersion = max(vals) - min(vals) if vals else 0

    # ── Classify ─────────────────────────────────────────────────────────────
    risk_off_votes = 0
    risk_on_votes  = 0

    # Safe-haven divergence
    if sh_divergence > 20:   risk_off_votes += 2
    elif sh_divergence < -20: risk_on_votes  += 2
    elif sh_divergence > 10:  risk_off_votes += 1
    elif sh_divergence < -10: risk_on_votes  += 1

    # USD strength
    if usd_val > 70:   risk_off_votes += 1
    elif usd_val < 35: risk_on_votes  += 1

    # Gold (risk-off = Gold falls as USD safe haven; risk-on = Gold rises with risk assets)
    # In pure risk-off: Gold can go either way — we weight it lightly
    if gold_dir == "bear": risk_off_votes += 1
    elif gold_dir == "bull": risk_on_votes += 1

    # Dispersion — high dispersion = trending = clearer regime
    high_dispersion = dispersion > 50

    # ── Final label ──────────────────────────────────────────────────────────
    total_votes = risk_off_votes + risk_on_votes

    if trend_ratio < 0.4 and dispersion < 30:
        regime     = "Ranging"
        confidence = "Medium"
    elif risk_off_votes >= 3 and risk_off_votes > risk_on_votes:
        regime     = "Risk-Off"
        confidence = "High" if (high_dispersion and risk_off_votes >= 4) else "Medium"
    elif risk_on_votes >= 3 and risk_on_votes > risk_off_votes:
        regime     = "Risk-On"
        confidence = "High" if (high_dispersion and risk_on_votes >= 4) else "Medium"
    elif total_votes == 0 or abs(risk_off_votes - risk_on_votes) <= 1:
        regime     = "Mixed"
        confidence = "Low"
    else:
        regime     = "Risk-Off" if risk_off_votes > risk_on_votes else "Risk-On"
        confidence = "Low"

    return {
        "regime":     regime,
        "confidence": confidence,
        "signals": {
            "sh_divergence":   round(sh_divergence, 1),
            "usd_strength":    round(usd_val, 1),
            "gold_direction":  gold_dir,
            "trend_ratio":     round(trend_ratio, 2),
            "dispersion":      round(dispersion, 1),
            "risk_off_votes":  risk_off_votes,
            "risk_on_votes":   risk_on_votes,
        }
    }
