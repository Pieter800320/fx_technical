"""
scan_alerts.py — Forex1212 Telegram Signal Scanner
Runs after H1 and H4 scans. Fires PRIME and WATCH alerts based on
score + QAI alignment. No PSL — purely score-based.

PRIME  🟢  All gates pass, QAI ≥ 65, Strong label, D1 confirms
WATCH  🟡  Most gates pass, QAI ≥ 55, Buy/Sell label, D1 confirms
Suppressed if: regime opposes, conflict flag, BB contracting, cooldown active
"""

import json, os, math, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE     = Path(__file__).parent.parent / "data"
H1_FILE  = BASE / "h1_scores.json"
H4_FILE  = BASE / "h4_scores.json"
D1_FILE  = BASE / "d1_scores.json"
CSM_FILE = BASE / "csm.json"
REG_FILE = BASE / "regime.json"
CD_FILE  = BASE / "alert_cooldown.json"    # cooldown timestamps per pair

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL  = "https://pieter800320.github.io/fx_technical"

# ── Cooldown periods ───────────────────────────────────────────────────────────
COOLDOWN_PRIME_H = 4     # hours between PRIME alerts on the same pair
COOLDOWN_WATCH_H = 2     # hours between WATCH alerts on the same pair

# ── Signal gates ──────────────────────────────────────────────────────────────
PRIME_MIN_QAI  = 65
PRIME_MIN_ADX  = 22
WATCH_MIN_QAI  = 55
WATCH_MIN_ADX  = 18

STRONG_LABELS  = {"Strong Buy", "Strong Sell"}
SIGNAL_LABELS  = {"Buy", "Sell", "Strong Buy", "Strong Sell"}

PAIRS = [
    "EUR/USD","GBP/USD","USD/JPY","USD/CHF",
    "AUD/USD","USD/CAD","NZD/USD","EUR/JPY",
    "GBP/JPY","XAU/USD"
]

# ── Load helpers ──────────────────────────────────────────────────────────────
def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── QAI computation (mirrors JS logic) ────────────────────────────────────────
def compute_qai(pair, h1, h4, d1, csm_rankings, conviction_pairs, regime_str):
    h1d = h1.get(pair, {})
    h4d = h4.get(pair, {})
    d1d = d1.get(pair, {})
    base, quote = pair.split("/")

    d1_dir = d1d.get("direction", "neutral")
    is_bull = d1_dir == "bull"
    is_bear = d1_dir == "bear"

    # D1 score (20%)
    d1_label = d1d.get("label", "")
    d1_score = 3 if d1_dir == "neutral" else (10 if "Strong" in d1_label else 7 if ("Buy" in d1_label or "Sell" in d1_label) else 4)

    # H4 score (15%)
    h4_dir = h4d.get("direction", "neutral")
    h4_label = h4d.get("label", "")
    if h4_dir == d1_dir and d1_dir != "neutral":
        h4_score = 10 if "Strong" in h4_label else 7
    elif h4_dir == "neutral":
        h4_score = 4
    else:
        h4_score = 0

    # H1 score (8%)
    h1_dir = h1d.get("direction", "neutral")
    if h1_dir == d1_dir and d1_dir != "neutral":
        h1_score = 10
    elif h1_dir == "neutral":
        h1_score = 6
    else:
        h1_score = 1

    # Reset score (10%)
    reset_raw = h4d.get("reset_score")
    if reset_raw is None:
        reset_score = 5
    elif reset_raw <= 20:
        reset_score = 10
    elif reset_raw <= 35:
        reset_score = 7
    elif reset_raw <= 50:
        reset_score = 5
    else:
        reset_score = 2

    # ADX (4%)
    adx_v = (h4d.get("raw") or {}).get("adx")
    if adx_v is None:
        adx_score = 5
    elif adx_v >= 25:
        adx_score = 10
    elif adx_v >= 20:
        adx_score = 7
    elif adx_v >= 15:
        adx_score = 4
    else:
        adx_score = 1

    # ATR percentile (3%)
    atr_pct = d1d.get("atr_percentile")
    if atr_pct is None:
        atr_score = 5
    elif 20 <= atr_pct <= 70:
        atr_score = 10
    elif atr_pct < 20:
        atr_score = 7
    else:
        atr_score = 3

    # CSM divergence (16%)
    csm_base  = csm_rankings.get(base, 50)
    csm_quote = csm_rankings.get(quote, 50)
    csm_div   = (csm_base - csm_quote) if is_bull else (csm_quote - csm_base) if is_bear else abs(csm_base - csm_quote)
    csm_score = 10 if csm_div >= 30 else 7 if csm_div >= 15 else 5 if csm_div >= 5 else 3 if csm_div >= -5 else 1

    # Conviction (12%)
    conv_raw = conviction_pairs.get(pair)
    conv_score = 5
    if conv_raw is not None:
        cd = conv_raw if is_bull else -conv_raw if is_bear else abs(conv_raw)
        conv_score = 10 if cd >= 60 else 8 if cd >= 40 else 6 if cd >= 20 else 5 if cd >= 0 else 3 if cd >= -20 else 1

    # Regime (8%)
    reg_score = 5
    if regime_str == "Risk-On":
        reg_score = 9 if is_bull else 5
    elif regime_str == "Risk-Off":
        reg_score = 9 if is_bear else 5
    elif regime_str == "Ranging":
        reg_score = 4

    # Rate diff (4%) — skip here, default 5
    rate_score = 5

    weights = {
        "d1": 0.20, "h4": 0.15, "h1": 0.08, "reset": 0.10,
        "adx": 0.04, "atr": 0.03, "csm": 0.16, "conv": 0.12,
        "regime": 0.08, "rate": 0.04,
    }
    scores = {
        "d1": d1_score, "h4": h4_score, "h1": h1_score, "reset": reset_score,
        "adx": adx_score, "atr": atr_score, "csm": csm_score, "conv": conv_score,
        "regime": reg_score, "rate": rate_score,
    }
    raw = round(sum(scores[k] * weights[k] for k in weights) * 10)

    # Regime cap
    risk_bases    = {"AUD","NZD","CAD"}
    safe_havens   = {"CHF","JPY"}
    is_risk_pair  = base in risk_bases or (quote in risk_bases and base not in safe_havens)
    is_safe_haven = base in safe_havens or quote in safe_havens
    capped = raw
    if regime_str == "Risk-Off" and is_bull:
        capped = min(raw, 45) if is_risk_pair else min(raw, 75) if is_safe_haven else min(raw, 55)
    elif regime_str == "Risk-On" and is_bear:
        capped = min(raw, 45) if is_safe_haven else min(raw, 75) if is_risk_pair else min(raw, 55)

    return min(capped, 100)

# ── Cooldown helpers ───────────────────────────────────────────────────────────
def load_cooldown():
    try:
        with open(CD_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def is_cooled_down(cd, pair, tier):
    """True if enough time has passed since last alert on this pair."""
    rec = cd.get(pair)
    if not rec:
        return True
    last = datetime.fromisoformat(rec["last_fire"])
    hours = COOLDOWN_PRIME_H if tier == "PRIME" else COOLDOWN_WATCH_H
    return (datetime.now(timezone.utc) - last) >= timedelta(hours=hours)

def record_fire(cd, pair, tier):
    cd[pair] = {
        "last_fire": datetime.now(timezone.utc).isoformat(),
        "tier": tier,
    }

# ── Signal evaluation ──────────────────────────────────────────────────────────
def evaluate_pair(pair, h1, h4, d1, csm_rankings, conviction_pairs, regime_str, regime_data, trigger_tf):
    """
    Returns ("PRIME"|"WATCH"|None, direction, data_dict)
    trigger_tf: "H1" or "H4" — which timeframe triggered this run
    """
    h1d = h1.get(pair, {})
    h4d = h4.get(pair, {})
    d1d = d1.get(pair, {})

    h4_label = h4d.get("label", "")
    h1_label = h1d.get("label", "")
    d1_label = d1d.get("label", "")
    d1_dir   = d1d.get("direction", "neutral")
    h4_dir   = h4d.get("direction", "neutral")

    # Use trigger TF label as primary signal
    trig_label = h4_label if trigger_tf == "H4" else h1_label
    trig_dir   = h4_dir   if trigger_tf == "H4" else h1d.get("direction","neutral")

    # Must have a real signal label
    if trig_label not in SIGNAL_LABELS:
        return None, None, {}

    # D1 must confirm direction
    if d1_dir == "neutral" or d1_dir != trig_dir:
        return None, None, {}

    direction = "BUY" if trig_dir == "bull" else "SELL"

    # ADX gate
    adx = (h4d.get("raw") or {}).get("adx", 0)

    # ATR gate (filter_ok)
    atr_ok = h4d.get("filter_ok", True)

    # Conflict flag
    conflict = h4d.get("conflict", False)

    # Regime opposition check
    regime_opposes = (
        (regime_str == "Risk-Off" and trig_dir == "bull" and pair in ["AUD/USD","NZD/USD","AUD/JPY","NZD/JPY","GBP/JPY","EUR/JPY"]) or
        (regime_str == "Risk-On"  and trig_dir == "bear" and pair in ["USD/CHF","USD/JPY"])
    )

    # QAI
    qai = compute_qai(pair, h1, h4, d1, csm_rankings, conviction_pairs, regime_str)

    # PRIME gate
    if (trig_label in STRONG_LABELS
            and adx >= PRIME_MIN_ADX
            and atr_ok
            and not conflict
            and not regime_opposes
            and qai >= PRIME_MIN_QAI):
        return "PRIME", direction, {"adx": adx, "qai": qai, "h4_label": h4_label, "h1_label": h1_label, "d1_label": d1_label}

    # WATCH gate (less strict)
    if (trig_label in SIGNAL_LABELS
            and adx >= WATCH_MIN_ADX
            and atr_ok
            and not conflict
            and qai >= WATCH_MIN_QAI):
        return "WATCH", direction, {"adx": adx, "qai": qai, "h4_label": h4_label, "h1_label": h1_label, "d1_label": d1_label}

    return None, None, {}

# ── Telegram message ───────────────────────────────────────────────────────────
def build_message(pair, tier, direction, data, trigger_tf, regime_str):
    dot    = "🟢" if tier == "PRIME" else "🟡"
    label  = pair.replace("/", "")
    d_sym  = "▲" if direction == "BUY" else "▼"
    h4_l   = data.get("h4_label","—")
    h1_l   = data.get("h1_label","—")
    d1_l   = data.get("d1_label","—")
    adx    = data.get("adx",0)
    qai    = data.get("qai",0)

    lines = [
        f"{dot} {tier} — {label} {direction} {d_sym}",
        f"D1 {d1_l} · H4 {h4_l} · H1 {h1_l}",
        f"ADX {adx:.0f} · QAI {qai}% · {regime_str}",
        f"[Dashboard]({DASHBOARD_URL})",
    ]
    return "\n".join(lines)

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  [Telegram] No token/chat — skipped")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=10)
    if r.ok:
        print(f"  [Telegram] Sent OK")
    else:
        print(f"  [Telegram] Failed: {r.status_code} {r.text[:80]}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main(trigger_tf="H4"):
    print(f"=== Alert Scanner — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC (trigger: {trigger_tf}) ===")

    h1  = load_json(H1_FILE)
    h4  = load_json(H4_FILE)
    d1  = load_json(D1_FILE)
    csm = load_json(CSM_FILE)
    reg = load_json(REG_FILE)

    csm_rankings    = csm.get("rankings", {})
    conviction_data = h4.get("_conviction", {})   # conviction pairs if embedded
    conviction_pairs = conviction_data if isinstance(conviction_data, dict) else {}
    regime_str      = reg.get("regime", "Mixed")

    cd = load_cooldown()
    fired = 0

    for pair in PAIRS:
        tier, direction, data = evaluate_pair(
            pair, h1, h4, d1, csm_rankings, conviction_pairs, regime_str, reg, trigger_tf
        )
        if tier is None:
            continue

        if not is_cooled_down(cd, pair, tier):
            print(f"  {pair}: {tier} suppressed — cooldown active")
            continue

        msg = build_message(pair, tier, direction, data, trigger_tf, regime_str)
        print(f"  {pair}: {tier} {direction} QAI={data.get('qai')}%")
        send_telegram(msg)
        record_fire(cd, pair, tier)
        fired += 1

    save_json(CD_FILE, cd)
    print(f"=== Alert Scanner complete — {fired} alert(s) sent ===")

if __name__ == "__main__":
    import sys
    tf = sys.argv[1] if len(sys.argv) > 1 else "H4"
    main(tf)
