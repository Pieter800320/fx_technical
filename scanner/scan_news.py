"""
scan_news.py — Forex1212 News Brief + Market Narrative
Sources : FXStreet, ForexLive, Nasdaq FX (RSS — last 4 h)
Macro   : Stooq.com (VIX, US10Y, WTI, Gold, S&P500, BTC, Copper)
Tech    : h4_scores.json, d1_scores.json, csm.json, regime.json
Output  : data/news_brief.json

JSON fields
  status        "ok" | "unavailable"
  macro         {vix, us10y, wti, gold, spx, btc, copper}
  narrative     structured FX prose (5 sections, plain text)
  themes        [{theme, currencies, direction, confidence}]
  usd_bias      "bullish"|"bearish"|"neutral"
  risk_sentiment "risk-on"|"risk-off"|"neutral"
  key_observation one-sentence insight
  watch         one watch point
  updated       ISO timestamp
  headline_count int
  edge_scores   {EURUSD:7, ...}
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
    "AUD/USD","USD/CAD","NZD/USD","EUR/JPY","GBP/JPY",
    "AUD/JPY","NZD/JPY","CAD/JPY",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Forex1212/1.0)"}

# ── Stooq ─────────────────────────────────────────────────────────────────────
def fetch_stooq(symbol):
    """Fetch last close + daily change via Yahoo Finance.

    NOTE: Stooq was abandoned — it blocks GitHub Actions runner IPs and
    returns empty responses from cloud providers. Yahoo Finance v8 API
    works reliably without an API key from GitHub Actions.

    Symbol mapping: internal Stooq-style keys → Yahoo Finance tickers.
    """
    yf_map = {
        "^vix":   "^VIX",
        "^tnx":   "^TNX",
        "cl.f":   "CL=F",
        "xauusd": "GC=F",
        "^spx":   "^GSPC",
        "btcusd": "BTC-USD",
        "hg.f":   "HG=F",
    }
    yf_symbol = yf_map.get(symbol.lower(), symbol)
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{yf_symbol}?interval=1d&range=5d"
    )
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        result = data["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]

        if len(closes) < 1:
            return None

        curr = closes[-1]

        if len(closes) >= 2:
            prev = closes[-2]
            if prev and prev != 0:
                change     = round(curr - prev, 6)
                change_pct = round((change / prev) * 100, 2)
            else:
                change = 0.0
                change_pct = 0.0
        else:
            change = 0.0
            change_pct = 0.0

        return {"value": curr, "change": change, "change_pct": change_pct}

    except Exception as e:
        print(f"    [Yahoo] {symbol} ({yf_symbol}): {e}")
        return None


def fmt_val(v):
    """Format macro value cleanly — no scientific notation for large numbers."""
    if v >= 10_000:
        return f"{v:,.0f}"   # BTC 94321 -> "94,321" / SPX 5512 -> "5,512"
    if v >= 100:
        return f"{v:.1f}"    # Gold 3300.1 -> "3300.1" / WTI 65.4 -> "65.4"
    return f"{v:.4g}"        # VIX 18.4 -> "18.4" / TNX 4.21 -> "4.21"


def fetch_all_macro():
    print("  Fetching macro data from Yahoo Finance...")
    macro = {}
    for key, symbol, label, invert in STOOQ_INSTRUMENTS:
        d = fetch_stooq(symbol)
        if d:
            d["label"]  = label
            d["invert"] = invert
            macro[key]  = d
            arr = "up" if d["change"] > 0 else "down" if d["change"] < 0 else "flat"
            print(f"    [{label}] {fmt_val(d['value'])} {arr} {abs(d['change_pct']):.2f}%")
        else:
            print(f"    [{label}] unavailable")
    print(f"  Macro: {len(macro)}/{len(STOOQ_INSTRUMENTS)} instruments fetched")
    return macro


# ── RSS ───────────────────────────────────────────────────────────────────────
def fetch_rss(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            root = ET.parse(resp).getroot()
        items  = []
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
    return lj("h4_scores.json"), lj("d1_scores.json"), lj("csm.json"), lj("regime.json"), lj("correlation.json")


def build_tech_text(h4, d1, csm, regime):
    lines   = []
    reg     = regime.get("regime", "Unknown")
    conf    = regime.get("confidence", "")
    s       = regime.get("signals", {})
    h4_reg  = regime.get("h4", {})
    h4_reg_name = h4_reg.get("regime", "") if h4_reg else ""

    # FIX: removed special character — plain "DIVERGENCE" instead of "⚡ DIVERGENCE"
    if h4_reg_name and h4_reg_name != reg:
        lines.append(
            f"Regime: D1={reg} {conf} | H4={h4_reg_name} {h4_reg.get('confidence', '')} "
            f"DIVERGENCE - H4 is leading, D1 transition in progress"
        )
    else:
        lines.append(
            f"Regime: {reg} {conf} (D1+H4 aligned)"
            f" | USD proxy: {s.get('usd_proxy', '?')}"
            f" | SH div: {s.get('sh_divergence', '?')}"
        )

    ranks    = csm.get("rankings") or {}
    sorted_r = sorted(ranks.items(), key=lambda x: x[1], reverse=True)
    if sorted_r:
        top = " ".join(f"{c}({v:.0f})" for c, v in sorted_r[:3])
        bot = " ".join(f"{c}({v:.0f})" for c, v in sorted_r[-3:])
        lines.append(f"Strongest: {top} | Weakest: {bot}")

    sigs = []
    for pair in PAIRS:
        h4d = h4.get(pair, {})
        d1d = d1.get(pair, {})
        if not h4d:
            continue
        h4l = h4d.get("label", "Neutral")
        d1l = d1d.get("label", "Neutral")
        sc  = h4d.get("score", 0)
        if "Neutral" in h4l and "Neutral" in d1l:
            continue
        sigs.append(f"{pair.replace('/', '')}: D1={d1l} H4={h4l}({sc:+d})")
    lines.append("Signals: " + (" | ".join(sigs) if sigs else "none above threshold"))
    return "\n".join(lines)


# ── Claude calls ──────────────────────────────────────────────────────────────
def _strip_json(raw):
    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found: {raw[:120]}")
    return raw[start:end + 1]


def call_themes(headlines_text, n):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    now_iso = datetime.now(timezone.utc).isoformat()
    prompt = (
        f"You are an institutional FX macro analyst. "
        f"Analyse these {n} FX headlines from the last 4 hours.\n\n"
        f"Headlines:\n{headlines_text}\n\n"
        f"Respond ONLY with valid JSON. No markdown. No special characters. Plain text values only.\n"
        f'{{"themes":[{{"theme":"...","currencies":["USD"],"direction":"bullish|bearish|neutral","confidence":"high|medium|low"}}],'
        f'"usd_bias":"bullish|bearish|neutral",'
        f'"risk_sentiment":"risk-on|risk-off|neutral",'
        f'"key_observation":"...",'
        f'"watch":"...",'
        f'"updated":"{now_iso}",'
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


def build_corr_text(corr):
    if not corr or not corr.get("pairs") or not corr.get("matrix"):
        return "No correlation data available."
    pairs  = corr["pairs"]
    matrix = corr["matrix"]
    lines  = []
    for i, p in enumerate(pairs):
        row    = matrix[i]
        ranked = sorted(
            [(pairs[j], row[j]) for j in range(len(pairs)) if j != i and row[j] is not None],
            key=lambda x: abs(x[1]), reverse=True
        )[:3]
        corrs = ", ".join(f"{q}({v:+.2f})" for q, v in ranked)
        lines.append(f"{p}: {corrs}")
    return "\n".join(lines)


def call_narrative(macro, themes_data, tech_text, corr_text):
    """Generate structured five-section FX narrative. Plain text only — no markdown."""

    macro_lines = []
    for key, _, label, invert in STOOQ_INSTRUMENTS:
        d = macro.get(key)
        if not d:
            continue
        chg = d["change_pct"]
        arr = "up" if chg > 0 else "down" if chg < 0 else "flat"
        macro_lines.append(f"{label}: {fmt_val(d['value'])} ({arr} {abs(chg):.2f}%)")
    macro_text = "\n".join(macro_lines) or "No macro data"

    themes   = themes_data.get("themes", [])
    t_lines  = [
        f"- {t['theme']} [{t['direction'].upper()}] ({t.get('confidence', '?')})"
        for t in themes[:6]
    ]
    themes_text = (
        f"USD bias: {themes_data.get('usd_bias', '?')} | "
        f"Risk sentiment: {themes_data.get('risk_sentiment', '?')}\n"
        + "\n".join(t_lines)
    )

    # FIX: explicit no-markdown instruction in both system and user prompts
    system = (
        "You are a professional macro FX trader. "
        "Your task is to synthesize multi-source market data into a clear, internally consistent narrative. "
        "You must resolve contradictions by prioritizing correlation and price behavior over narrative. "
        "Do not summarize inputs. Infer the dominant drivers and produce a coherent, decisive interpretation. "
        "CRITICAL: Write in plain text only. "
        "Do not use any markdown formatting whatsoever: no asterisks, no hash symbols, "
        "no dashes used as decorators, no bold, no italic, no underscores for emphasis. "
        "Use plain sentences and the exact section headers shown below, nothing else."
    )

    user = f"""DATA:

1) CORRELATIONS (H4, 50-bar):
{corr_text}

2) TECHNICALS (regime, CSM strength, signals, ADX):
{tech_text}

3) CROSS-ASSET MACRO:
{macro_text}

4) NEWS / FUNDAMENTALS:
{themes_text}

TASK: Produce a structured FX market narrative in EXACTLY this format. Plain text only.

DOMINANT DRIVERS
Rank the top 3 drivers by strength. One line each. Format: 1. Driver name because reason it is dominant

PRICE CONFIRMS
What correlation data and price action confirms or rejects the narrative. 2-3 sentences. Be specific about which pairs are leading or lagging.

REGIME
One line: Risk-On or Risk-Off or Mixed, confirmed or conflicted. Reference VIX, Gold, and S&P500 specifically.

CONTRADICTIONS
Identify max 2 genuine conflicts between sources. If none, write: None identified. Format: 1. Pair or theme: conflict explained in one line

TRADE IMPLICATIONS
Best: Pair up or down - reason in max 15 words - Conviction X/10
Secondary: Pair up or down - reason in max 15 words - Conviction X/10
Avoid: Pair - reason in max 10 words
Watch: One trigger that confirms or invalidates the primary trade

RULES:
- Correlation overrides fundamentals if they conflict
- Conviction score: 10 means all four sources aligned, 1 means all sources conflicted
- No generic statements such as markets are uncertain
- No hedging language. Be decisive.
- NO markdown formatting of any kind. No asterisks, no hash symbols, no bold, no bullet dashes."""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    narrative = resp.content[0].text.strip()
    wc = len(narrative.split())
    print(f"  [Claude narrative] {wc} words")
    return narrative


def call_edge_scores(macro, themes_data, tech_text, corr_text):
    """Score all 12 pairs 1-10 on cross-source coherence (Edge score)."""
    macro_lines = []
    for key, _, label, invert in STOOQ_INSTRUMENTS:
        d = macro.get(key)
        if not d:
            continue
        chg = d["change_pct"]
        arr = "up" if chg > 0 else "down" if chg < 0 else "flat"
        macro_lines.append(f"{label}: {fmt_val(d['value'])} ({arr} {abs(chg):.2f}%)")
    macro_text = "\n".join(macro_lines) or "No macro data"

    themes      = themes_data.get("themes", [])
    themes_text = (
        f"USD bias: {themes_data.get('usd_bias', '?')} | "
        f"Risk: {themes_data.get('risk_sentiment', '?')}\n"
        + "\n".join(f"- {t['theme']} [{t['direction'].upper()}]" for t in themes[:6])
    )

    prompt = (
        "You are a professional FX analyst. Score each currency pair 1-10 on EDGE - "
        "how coherently all four data sources (correlation, technicals, macro, news) "
        "agree on a tradeable direction for that pair right now.\n\n"
        "Scoring guide:\n"
        "10 = All four sources fully aligned, clear direction, no contradictions\n"
        "7-9 = Three sources agree, one mild conflict\n"
        "4-6 = Mixed signals, sources partially agree\n"
        "1-3 = Contradictory sources, no clear edge\n\n"
        f"DATA:\nCORRELATIONS: {corr_text[:800]}\n"
        f"TECHNICALS: {tech_text}\n"
        f"MACRO: {macro_text}\n"
        f"NEWS: {themes_text}\n\n"
        "Score ALL 12 pairs. Respond ONLY with valid JSON, no markdown, no explanation:\n"
        '{"EURUSD":7,"GBPUSD":5,"USDJPY":9,"USDCHF":6,"AUDUSD":4,"USDCAD":5,'
        '"NZDUSD":8,"EURJPY":6,"GBPJPY":5,"AUDJPY":4,"NZDJPY":7,"CADJPY":5}\n\n'
        "Replace the example numbers with your actual scores. Return only the JSON object."
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw    = resp.content[0].text.strip()
    scores = json.loads(_strip_json(raw))
    for pair in PAIRS:
        key = pair.replace("/", "")
        if key not in scores:
            scores[key] = 5
        else:
            scores[key] = max(1, min(10, int(scores[key])))
    print(f"  [Claude edge] scores: {scores}")
    return scores


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"=== News Brief - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC ===")

    # 1. Macro — always fetch first; written to JSON even if Claude fails
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
    h4, d1, csm, regime, corr = load_tech()
    tech_text = build_tech_text(h4, d1, csm, regime)
    corr_text = build_corr_text(corr)

    # 4. Default stub — macro always present even if Claude is unavailable
    result = {
        "status":      "unavailable",
        "updated":     datetime.now(timezone.utc).isoformat(),
        "macro":       macro,
        "narrative":   "",
        "edge_scores": {},
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
            print(
                f"  [Claude themes] {len(themes_data.get('themes', []))} themes, "
                f"usd_bias={themes_data.get('usd_bias')}"
            )
            result.update(themes_data)
            result["status"]      = "ok"
            result["macro"]       = macro   # restore after update() overwrites it
            result["edge_scores"] = {}      # restore after update()
        except Exception as e:
            print(f"  Claude themes error: {e}")

        if result["status"] == "ok":
            try:
                result["narrative"] = call_narrative(macro, result, tech_text, corr_text)
            except Exception as e:
                print(f"  Claude narrative error: {e}")
            try:
                result["edge_scores"] = call_edge_scores(macro, result, tech_text, corr_text)
            except Exception as e:
                print(f"  Claude edge error: {e}")
    else:
        print("  Skipping Claude calls (no headlines or no API key)")

    # 5. Write — macro always included regardless of Claude success
    out = BASE_DIR / "data" / "news_brief.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Saved: {out} | macro keys: {list(result.get('macro', {}).keys())}")
    print("=== News Brief complete ===")


if __name__ == "__main__":
    main()
