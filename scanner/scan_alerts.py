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


def get_rate_diff_bps(pair, rates):
    """Extract rate differential in bps from rates.json for a pair."""
    if not rates:
        return 0
    base, quote = pair.split("/")
    # rates.json can be {USD:{rate:5.5,bank:Fed}, ...} or {rates:[{currency,rate,bank}]}
    rate_map = {}
    if isinstance(rates, dict) and "rates" in rates:
        for r in rates["rates"]:
            if r.get("currency"):
                rate_map[r["currency"]] = r.get("rate", 0)
    else:
        for ccy, v in rates.items():
            if isinstance(v, dict) and "rate" in v:
                rate_map[ccy] = v["rate"]
    b_rate = rate_map.get(base, 0)
    q_rate = rate_map.get(quote, 0)
    return round((b_rate - q_rate) * 100)  # bps


def compute_setup(pair, h1, h4, d1, csm_rankings, edge_scores, regime_str, rates=None):
    """
    6-component orthogonal Setup score. Mirrors computeQAI() in Index.html exactly.
    ADX is a hard gate (< 20 → cap 45), not a scoring component.
    """
    h1d=h1.get(pair,{}); h4d=h4.get(pair,{}); d1d=d1.get(pair,{})
    base,quote=pair.split("/")
    d1_dir=d1d.get("direction","neutral")
    h4_dir=h4d.get("direction","neutral")
    h1_dir=h1d.get("direction","neutral")
    is_bull=d1_dir=="bull"; is_bear=d1_dir=="bear"

    # 1. TF ALIGNMENT (30%)
    if d1_dir=="neutral":
        align_score=2
    else:
        h4m=h4_dir==d1_dir; h4n=h4_dir=="neutral"
        h1m=h1_dir==d1_dir; h1n=h1_dir=="neutral"
        d1s="Strong" in d1d.get("label","")
        h4s="Strong" in h4d.get("label","")
        if h4m and h1m:        align_score=10 if (d1s or h4s) else 9
        elif h4m and h1n:      align_score=7
        elif h4m and not h1m and not h1n: align_score=5
        elif h4n and h1m:      align_score=5
        elif h4n and h1n:      align_score=3
        else:                  align_score=1

    # 2. ENTRY POSITION (20%) — reset×0.6 + ATR×0.4
    reset_raw=h4d.get("reset_score")
    reset_comp=5 if reset_raw is None else (2 if reset_raw<=20 else 4 if reset_raw<=35 else 7 if reset_raw<=50 else 10)
    atr_pct=d1d.get("atr_percentile")
    atr_comp=5 if atr_pct is None else (10 if 20<=atr_pct<=70 else 7 if atr_pct<20 else 3)
    entry_score=round(reset_comp*0.6+atr_comp*0.4)

    # 3. CSM DIVERGENCE (18%)
    csm_base=csm_rankings.get(base,50); csm_quote=csm_rankings.get(quote,50)
    csm_div=(csm_base-csm_quote) if is_bull else (csm_quote-csm_base) if is_bear else abs(csm_base-csm_quote)
    csm_score=10 if csm_div>=30 else 7 if csm_div>=15 else 5 if csm_div>=5 else 3 if csm_div>=-5 else 1

    # 4. REGIME FIT (15%)
    risk_bases={"AUD","NZD","CAD"}; safe_havens={"CHF","JPY"}
    is_risk=base in risk_bases or (quote in risk_bases and base not in safe_havens)
    is_safe=base in safe_havens or quote in safe_havens
    if regime_str=="Risk-On":
        reg_score=10 if (is_bull and is_risk) else 8 if is_bull else 2 if (is_bear and is_safe) else 4 if is_bear else 5
    elif regime_str=="Risk-Off":
        reg_score=10 if (is_bear and is_safe) else 8 if is_bear else 2 if (is_bull and is_risk) else 4 if is_bull else 5
    elif regime_str=="Ranging":
        reg_score=4
    else:
        reg_score=5

    # 5. RATE DIFFERENTIAL
    rate_score=5  # computed below from rates.json

    # 6. EDGE — AI cross-source coherence
    edge_key=pair.replace("/","")
    edge_raw=edge_scores.get(edge_key)
    edge_score=edge_raw if edge_raw is not None else 5

    # 7. SESSION FIT — is current UTC session optimal for this pair?
    PAIR_SESS={
        "EUR/USD":["LN","NY"],"GBP/USD":["LN","NY"],"USD/JPY":["TK","NY"],
        "USD/CHF":["LN","NY"],"AUD/USD":["SY","TK","NY"],"USD/CAD":["NY"],
        "NZD/USD":["SY","TK","NY"],"EUR/JPY":["LN","TK"],"GBP/JPY":["LN","TK"],
        "AUD/JPY":["SY","TK"],"NZD/JPY":["SY","TK"],"CAD/JPY":["TK","NY"],
    }
    SESS_UTC={"SY":(22,7),"TK":(23,8),"LN":(7,16),"NY":(12,21)}
    import datetime as _dt
    _h=_dt.datetime.utcnow().hour
    _day=_dt.datetime.utcnow().weekday()
    _mkt_closed=(_day==5 or (_day==6 and _h<22) or (_day==4 and _h>=22))
    if _mkt_closed:
        sess_score=3
    else:
        active_sess=[s for s,(st,en) in SESS_UTC.items() if (st>en and (_h>=st or _h<en)) or (st<=en and st<=_h<en)]
        pair_sess=PAIR_SESS.get(pair,[])
        sess_score=10 if any(s in pair_sess for s in active_sess) else 2 if active_sess else 3

    # Real rate differential
    if rates:
        diff_bps = get_rate_diff_bps(pair, rates)
        diff_in_dir = diff_bps if is_bull else -diff_bps if is_bear else abs(diff_bps)
        rate_score = 10 if diff_in_dir>=200 else 7 if diff_in_dir>=50 else 5 if diff_in_dir>=-50 else 3 if diff_in_dir>=-200 else 1

    # Weighted sum — 7 components
    weights={"align":.28,"entry":.18,"csm":.16,"regime":.13,"rate":.05,"edge":.12,"session":.08}
    scores={"align":align_score,"entry":entry_score,"csm":csm_score,"regime":reg_score,"rate":rate_score,"edge":edge_score,"session":sess_score}
    raw=round(sum(scores[k]*weights[k] for k in weights)*10)

    # ADX hard gate
    adx_v=(h4d.get("raw") or {}).get("adx")
    capped=raw
    if adx_v is not None and adx_v<20:
        capped=min(capped,45)

    # Regime cap
    if regime_str=="Risk-Off" and is_bull:
        lim=40 if is_risk else 70 if is_safe else 50
        capped=min(capped,lim)
    elif regime_str=="Risk-On" and is_bear:
        lim=40 if is_safe else 70 if is_risk else 50
        capped=min(capped,lim)

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
    rates=lj(BASE / "rates.json")
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
        setup=compute_setup(pair,h1,h4,d1,csm_rankings,edge_scores,regime_str,rates)
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
