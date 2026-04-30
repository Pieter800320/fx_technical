"""
scan_alerts.py — Forex1212 Daily Signal Summary
Fires once per day per pair maximum.
Gate: Setup >= 70% AND Edge >= 7 AND D1 confirms H4 AND ADX >= 20 AND ATR ok

Called from H4 workflow. Sends a single summary message, not individual alerts.
Uses alert_cooldown.json to enforce once-daily limit per pair.
"""

import json, os, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE     = Path(__file__).parent.parent / "data"
H1_FILE  = BASE / "h1_scores.json"
H4_FILE  = BASE / "h4_scores.json"
D1_FILE  = BASE / "d1_scores.json"
CSM_FILE = BASE / "csm.json"
REG_FILE = BASE / "regime.json"
NB_FILE  = BASE / "news_brief.json"
CD_FILE  = BASE / "alert_cooldown.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL  = "https://pieter800320.github.io/fx_technical"

SETUP_MIN  = 70
EDGE_MIN   = 7
ADX_MIN    = 20
COOLDOWN_H = 20

PAIRS = [
    "EUR/USD","GBP/USD","USD/JPY","USD/CHF",
    "AUD/USD","USD/CAD","NZD/USD","EUR/JPY",
    "GBP/JPY","AUD/JPY","NZD/JPY","CAD/JPY",
]
SIGNAL_LABELS = {"Strong Buy","Strong Sell","Buy","Sell"}
STRONG_LABELS = {"Strong Buy","Strong Sell"}

def lj(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

def sj(path, data):
    with open(path,"w") as f: json.dump(data, f, indent=2)

def compute_setup(pair, h1, h4, d1, csm_rankings, regime_str):
    """Compute Setup% for a pair. Must match frontend computeQAI() exactly.
    Conviction removed; weights redistributed across 9 components.
    """
    h1d=h1.get(pair,{}); h4d=h4.get(pair,{}); d1d=d1.get(pair,{})
    base,quote=pair.split("/")
    d1_dir=d1d.get("direction","neutral")
    is_bull=d1_dir=="bull"; is_bear=d1_dir=="bear"
    d1_label=d1d.get("label","")
    d1_score=3 if d1_dir=="neutral" else (10 if "Strong" in d1_label else 7 if ("Buy" in d1_label or "Sell" in d1_label) else 4)
    h4_dir=h4d.get("direction","neutral"); h4_label=h4d.get("label","")
    if h4_dir==d1_dir and d1_dir!="neutral": h4_score=10 if "Strong" in h4_label else 7
    elif h4_dir=="neutral": h4_score=4
    else: h4_score=0
    h1_dir=h1d.get("direction","neutral")
    h1_score=10 if h1_dir==d1_dir and d1_dir!="neutral" else 6 if h1_dir=="neutral" else 1
    reset_raw=h4d.get("reset_score")
    reset_score=5 if reset_raw is None else (10 if reset_raw<=20 else 7 if reset_raw<=35 else 5 if reset_raw<=50 else 2)
    adx_v=(h4d.get("raw") or {}).get("adx")
    adx_score=5 if adx_v is None else (10 if adx_v>=25 else 7 if adx_v>=20 else 4 if adx_v>=15 else 1)
    atr_pct=d1d.get("atr_percentile")
    atr_score=5 if atr_pct is None else (10 if 20<=atr_pct<=70 else 7 if atr_pct<20 else 3)
    csm_base=csm_rankings.get(base,50); csm_quote=csm_rankings.get(quote,50)
    csm_div=(csm_base-csm_quote) if is_bull else (csm_quote-csm_base) if is_bear else abs(csm_base-csm_quote)
    csm_score=10 if csm_div>=30 else 7 if csm_div>=15 else 5 if csm_div>=5 else 3 if csm_div>=-5 else 1
    reg_score=5
    if regime_str=="Risk-On": reg_score=9 if is_bull else 5
    elif regime_str=="Risk-Off": reg_score=9 if is_bear else 5
    elif regime_str=="Ranging": reg_score=4
    # Weights match frontend computeQAI() exactly (conviction removed, total=1.00)
    weights={"d1":.23,"h4":.17,"h1":.09,"reset":.11,"adx":.05,"atr":.03,"csm":.18,"regime":.09,"rate":.05}
    scores={"d1":d1_score,"h4":h4_score,"h1":h1_score,"reset":reset_score,"adx":adx_score,"atr":atr_score,"csm":csm_score,"regime":reg_score,"rate":5}
    raw=round(sum(scores[k]*weights[k] for k in weights)*10)
    riskBases={"AUD","NZD","CAD"}; safeHavens={"CHF","JPY"}
    is_risk=base in riskBases or (quote in riskBases and base not in safeHavens)
    is_safe=base in safeHavens or quote in safeHavens
    capped=raw
    if regime_str=="Risk-Off" and is_bull: capped=min(raw,45) if is_risk else min(raw,75) if is_safe else min(raw,55)
    elif regime_str=="Risk-On" and is_bear: capped=min(raw,45) if is_safe else min(raw,75) if is_risk else min(raw,55)
    return min(capped,100)

def load_cooldown():
    try:
        with open(CD_FILE) as f: return json.load(f)
    except: return {}

def is_cooled(cd, pair):
    rec=cd.get(pair)
    if not rec: return True
    last=datetime.fromisoformat(rec["last_fire"])
    return (datetime.now(timezone.utc)-last)>=timedelta(hours=COOLDOWN_H)

def record_fire(cd, pair):
    cd[pair]={"last_fire":datetime.now(timezone.utc).isoformat()}

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print("  [Telegram] No credentials — skipped"); return
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r=requests.post(url,json={"chat_id":TELEGRAM_CHAT,"text":text,"parse_mode":"Markdown","disable_web_page_preview":True},timeout=10)
    if r.ok: print("  [Telegram] Sent OK")
    else: print(f"  [Telegram] Failed: {r.status_code}")

def main(trigger_tf="H4"):
    print(f"=== Alert Scanner — {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC (trigger: {trigger_tf}) ===")
    h1=lj(H1_FILE); h4=lj(H4_FILE); d1=lj(D1_FILE)
    csm=lj(CSM_FILE); reg=lj(REG_FILE); nb=lj(NB_FILE)
    csm_rankings=csm.get("rankings",{})
    regime_str=reg.get("regime","Mixed")
    edge_scores=nb.get("edge_scores",{})
    cd=load_cooldown()
    signals=[]

    for pair in PAIRS:
        h4d=h4.get(pair,{}); d1d=d1.get(pair,{})
        h4_label=h4d.get("label","")
        d1_dir=d1d.get("direction","neutral")
        h4_dir=h4d.get("direction","neutral")
        if h4_label not in SIGNAL_LABELS: continue
        if d1_dir=="neutral" or d1_dir!=h4_dir: continue
        adx=(h4d.get("raw") or {}).get("adx",0) or 0
        if adx<ADX_MIN: continue
        if not h4d.get("filter_ok",True): continue
        if h4d.get("conflict",False): continue
        setup=compute_setup(pair,h1,h4,d1,csm_rankings,regime_str)
        if setup<SETUP_MIN: continue
        edge=edge_scores.get(pair.replace("/",""))
        if edge is None or edge<EDGE_MIN: continue
        if not is_cooled(cd,pair):
            print(f"  {pair}: suppressed — cooldown active"); continue
        direction="BUY" if h4_dir=="bull" else "SELL"
        is_strong=h4_label in STRONG_LABELS
        signals.append({"pair":pair,"direction":direction,"setup":setup,"edge":edge,"strong":is_strong,"adx":adx})
        record_fire(cd,pair)

    sj(CD_FILE,cd)

    if not signals:
        print("  No qualifying signals — 0 alerts sent"); return

    signals.sort(key=lambda x:(not x["strong"],-x["setup"]))

    lines=["📊 *Forex1212 — Signal Summary*"]
    for s in signals:
        arr="▲" if s["direction"]=="BUY" else "▼"
        tier="🟢" if s["strong"] else "🟡"
        lines.append(f"{tier} {arr} *{s['pair'].replace('//','')}* {s['direction']} · Setup {s['setup']}% · Edge {s['edge']}/10")
    lines.append(f"\n[Dashboard]({DASHBOARD_URL})")

    msg="\n".join(lines)
    print(f"  {len(signals)} signal(s):")
    for s in signals: print(f"    {s['pair']} {s['direction']} Setup={s['setup']}% Edge={s['edge']}/10")
    send_telegram(msg)
    print(f"=== Alert Scanner complete — {len(signals)} alert(s) sent ===")

if __name__=="__main__":
    import sys
    tf=sys.argv[1] if len(sys.argv)>1 else "H4"
    main(tf)
