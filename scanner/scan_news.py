"""
scan_news.py — Forex1212 News Brief + Market Narrative
Sources : FXStreet, ForexLive, Nasdaq FX (RSS — last 4 h)
Macro   : Stooq.com (VIX, US10Y, WTI, Gold, S&P500, BTC, Copper)
Tech    : h4_scores.json, d1_scores.json, csm.json, regime.json
Output  : data/news_brief.json

JSON fields
  status        "ok" | "unavailable"
  macro         {vix, us10y, wti, gold, spx, btc, copper}  ← new
  narrative     150-word integrated FX prose                ← new
  themes        [{theme, currencies, direction, confidence}]
  usd_bias      "bullish"|"bearish"|"neutral"
  risk_sentiment "risk-on"|"risk-off"|"neutral"
  key_observation one-sentence insight
  watch         one watch point
  updated       ISO timestamp
  headline_count int
"""

import json, os, re, urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    import anthropic
except ImportError:
    anthropic = None

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent

RSS_FEEDS = [
    ("FXStreet",  "https://www.fxstreet.com/rss/news"),
    ("ForexLive", "https://www.forexlive.com/feed/news"),
    ("Nasdaq FX", "https://www.nasdaq.com/feed/rssoutbound?category=Currencies"),
]

# (json_key, stooq_symbol, display_label, invert_color)
# invert_color=True means rising value is BAD for risk (e.g. VIX)
STOOQ_INSTRUMENTS = [
    ("vix",    "^vix",   "VIX",     True),
    ("us10y",  "^tnx",   "US 10Y",  False),
    ("wti",    "cl.f",   "WTI Oil", False),
    ("gold",   "xauusd", "Gold",    False),
    ("spx",    "^spx",   "S&P 500", False),
    ("btc",    "btcusd", "Bitcoin", False),
    ("copper", "hg.f",   "Copper",  False),
]

PAIRS = [
    "EUR/USD","GBP/USD","USD/JPY","USD/CHF",
    "AUD/USD","USD/CAD","NZD/USD","EUR/JPY","GBP/JPY","XAU/USD",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Forex1212/1.0)"}

# ── Stooq ─────────────────────────────────────────────────────────────────────
def fetch_stooq(symbol):
    """Return {value, change, change_pct} for last daily bar, or None."""
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        lines = [
            l.strip() for l in raw.strip().split("\n")
            if l.strip() and not l.lower().startswith("date")
        ]
        if len(lines) < 2:
            return None
        def close(line):
            parts = line.split(",")
            return float(parts[4]) if len(parts) >= 5 else None
        prev = close(lines[-2])
        curr = close(lines[-1])
        if prev is None or curr is None or prev == 0:
            return None
        change     = round(curr - prev, 6)
        change_pct = round((change / prev) * 100, 2)
        return {"value": curr, "change": change, "change_pct": change_pct}
    except Exception as e:
        print(f"    [Stooq] {symbol}: {e}")
        return None

def fetch_all_macro():
    print("  Fetching macro data from Stooq...")
    macro = {}
    for key, symbol, label, invert in STOOQ_INSTRUMENTS:
        d = fetch_stooq(symbol)
        if d:
            d["label"]  = label
            d["invert"] = invert
            macro[key]  = d
            arr = "↑" if d["change"] > 0 else "↓" if d["change"] < 0 else "→"
            print(f"    [{label}] {d['value']:.4g} {arr}{abs(d['change_pct']):.2f}%")
        else:
            print(f"    [{label}] unavailable")
    return macro

# ── RSS ───────────────────────────────────────────────────────────────────────
def fetch_rss(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            root = ET.parse(resp).getroot()
        items = []
        now    = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=4)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            try:
                pub = parsedate_to_datetime(item.findtext("pubDate") or "")
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                if pub < cutoff:
                    continue
                time_str = pub.strftime("%H:%M")
            except Exception:
                time_str = "??"
            items.append({"title": title, "time": time_str})
        return items
    except Exception as e:
        print(f"    RSS error: {e}")
        return []

def deduplicate(items):
    seen, out = set(), []
    for item in items:
        key = re.sub(r"[^a-z0-9]", "", item["title"].lower())[:60]
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out

# ── Technical snapshot ────────────────────────────────────────────────────────
def load_tech():
    def lj(name):
        try:
            with open(BASE_DIR / "data" / name) as f:
                return json.load(f)
        except Exception:
            return {}
    return lj("h4_scores.json"), lj("d1_scores.json"), lj("csm.json"), lj("regime.json")

def build_tech_text(h4, d1, csm, regime):
    lines = []
    reg  = regime.get("regime", "Unknown")
    conf = regime.get("confidence", "")
    s    = regime.get("signals", {})
    lines.append(f"Regime: {reg} {conf} | USD proxy: {s.get('usd_proxy','?')} | SH div: {s.get('sh_divergence','?')}")

    ranks = csm.get("rankings") or {}
    sorted_r = sorted(ranks.items(), key=lambda x: x[1], reverse=True)
    if sorted_r:
        top = " ".join(f"{c}({v:.0f})" for c, v in sorted_r[:3])
        bot = " ".join(f"{c}({v:.0f})" for c, v in sorted_r[-3:])
        lines.append(f"Strongest: {top} | Weakest: {bot}")

    sigs = []
    for pair in PAIRS:
        h4d = h4.get(pair, {}); d1d = d1.get(pair, {})
        if not h4d:
            continue
        h4l = h4d.get("label", "Neutral")
        d1l = d1d.get("label", "Neutral")
        sc  = h4d.get("score", 0)
        if "Neutral" in h4l and "Neutral" in d1l:
            continue
        sigs.append(f"{pair.replace('/','')}: D1={d1l} H4={h4l}({sc:+d})")
    if sigs:
        lines.append("Signals: " + " | ".join(sigs))
    else:
        lines.append("Signals: none above threshold")
    return "\n".join(lines)

# ── Claude calls ──────────────────────────────────────────────────────────────
def _strip_json(raw):
    start = raw.find("{"); end = raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found: {raw[:120]}")
    return raw[start:end + 1]

def call_themes(headlines_text, n):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = (
        f"You are an institutional FX macro analyst. "
        f"Analyse these {n} FX headlines from the last 4 hours.\n\n"
        f"Headlines:\n{headlines_text}\n\n"
        f"Respond ONLY with valid JSON, no markdown:\n"
        f'{{"themes":[{{"theme":"...","currencies":["USD"],"direction":"bullish|bearish|neutral","confidence":"high|medium|low"}}],'
        f'"usd_bias":"bullish|bearish|neutral",'
        f'"risk_sentiment":"risk-on|risk-off|neutral",'
        f'"key_observation":"...",'
        f'"watch":"...",'
        f'"updated":"{datetime.now(timezone.utc).isoformat()}",'
        f'"headline_count":{n}}}'
    )
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text
    print(f"  [Claude themes] preview: {raw[:100]}")
    return json.loads(_strip_json(raw))

def call_narrative(macro, themes_data, tech_text):
    """Generate 150-word integrated FX narrative."""
    # Macro text
    macro_lines = []
    for key, _, label, invert in STOOQ_INSTRUMENTS:
        d = macro.get(key)
        if not d:
            continue
        chg = d["change_pct"]
        arr = "▲" if chg > 0 else "▼" if chg < 0 else "→"
        macro_lines.append(f"{label}: {d['value']:.4g} ({arr}{abs(chg):.2f}%)")
    macro_text = "\n".join(macro_lines) or "No macro data"

    # Themes text
    themes = themes_data.get("themes", [])
    t_lines = [f"- {t['theme']} [{t['direction'].upper()}]" for t in themes]
    themes_text = (
        f"USD bias: {themes_data.get('usd_bias','?')} | "
        f"Risk: {themes_data.get('risk_sentiment','?')}\n"
        + "\n".join(t_lines)
    )

    prompt = (
        "You are a senior FX strategist writing a pre-session market brief. "
        "Write a 150-word narrative integrating ALL THREE data sources below.\n\n"
        f"MACRO READINGS:\n{macro_text}\n\n"
        f"NEWS THEMES:\n{themes_text}\n\n"
        f"TECHNICAL PICTURE:\n{tech_text}\n\n"
        "Rules:\n"
        "- Reference specific instruments and FX pairs by name\n"
        "- Highlight where macro + news + technical converge\n"
        "- Explicitly flag any contradictions between the three sources\n"
        "- End with one actionable watch point for today's session\n"
        "- Flowing prose only — no bullet points, no section headers\n"
        "- Target 140-160 words\n\n"
        "Write the narrative directly, no preamble:"
    )
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    narrative = resp.content[0].text.strip()
    wc = len(narrative.split())
    print(f"  [Claude narrative] {wc} words")
    return narrative

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"=== News Brief — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC ===")

    # 1. Macro
    macro = fetch_all_macro()

    # 2. Headlines
    all_items = []
    for name, url in RSS_FEEDS:
        items = fetch_rss(url)
        print(f"  [{name}] {len(items)} items in window")
        all_items.extend(items)
    all_items = deduplicate(all_items)[:40]
    print(f"  Total headlines after dedup: {len(all_items)}")

    # 3. Technical data
    h4, d1, csm, regime = load_tech()
    tech_text = build_tech_text(h4, d1, csm, regime)

    # 4. Default stub
    result = {
        "status":   "unavailable",
        "updated":  datetime.now(timezone.utc).isoformat(),
        "macro":    macro,
        "narrative": "",
    }

    can_call = (
        all_items
        and anthropic is not None
        and "ANTHROPIC_API_KEY" in os.environ
    )

    if can_call:
        headlines_text = "\n".join(
            f"[{i['time']}] {i['title']}" for i in all_items
        )
        # Themes call
        try:
            themes_data = call_themes(headlines_text, len(all_items))
            print(f"  [Claude themes] {len(themes_data.get('themes',[]))} themes, "
                  f"usd_bias={themes_data.get('usd_bias')}")
            result.update(themes_data)
            result["status"] = "ok"
            result["macro"]  = macro   # restore after update()
        except Exception as e:
            print(f"  Claude themes error: {e}")

        # Narrative call (only if themes succeeded)
        if result["status"] == "ok":
            try:
                result["narrative"] = call_narrative(macro, result, tech_text)
            except Exception as e:
                print(f"  Claude narrative error: {e}")
    else:
        print("  Skipping Claude calls (no headlines or no API key)")

    # 5. Write
    out = BASE_DIR / "data" / "news_brief.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Saved: {out}")
    print("=== News Brief complete ===")

if __name__ == "__main__":
    main()
