"""scanner/scan_news.py — AI-powered FX news brief, runs every 4 hours."""
import json, os, sys, datetime, time
import xml.etree.ElementTree as ET
import urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import anthropic

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT     = os.path.join(DATA_DIR, "news_brief.json")

RSS_FEEDS = [
    ("FXStreet",    "https://www.fxstreet.com/rss/news"),
    ("ForexLive",   "https://www.forexlive.com/feed/news"),
    ("Investing",   "https://www.investing.com/rss/news_285.rss"),
    ("Fed",         "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("ECB",         "https://www.ecb.europa.eu/rss/press.html"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

STUB = {"status": "unavailable", "themes": [], "usd_bias": "neutral",
        "risk_sentiment": "neutral", "key_observation": "", "watch": "",
        "headline_count": 0}


def _parse_date(date_str: str) -> datetime.datetime | None:
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=datetime.timezone.utc) if dt.tzinfo is None else dt.astimezone(datetime.timezone.utc)
        except ValueError:
            continue
    return None


def fetch_feed(name: str, url: str, cutoff: datetime.datetime) -> list[dict]:
    items = []
    try:
        req  = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
        root = ET.fromstring(body)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}

        # RSS 2.0
        for item in root.iter("item"):
            title_el = item.find("title")
            date_el  = item.find("pubDate")
            if title_el is None or date_el is None:
                continue
            dt = _parse_date(date_el.text or "")
            if dt is None or dt < cutoff:
                continue
            items.append({"title": (title_el.text or "").strip(), "source": name, "dt": dt})

        # Atom
        if not items:
            for entry in root.findall("atom:entry", ns) or root.iter("{http://www.w3.org/2005/Atom}entry"):
                title_el = entry.find("{http://www.w3.org/2005/Atom}title")
                date_el  = entry.find("{http://www.w3.org/2005/Atom}updated") or entry.find("{http://www.w3.org/2005/Atom}published")
                if title_el is None or date_el is None:
                    continue
                dt = _parse_date(date_el.text or "")
                if dt is None or dt < cutoff:
                    continue
                items.append({"title": (title_el.text or "").strip(), "source": name, "dt": dt})

        print(f"  [{name}] {len(items)} items in window")
    except Exception as e:
        print(f"  [{name}] fetch error: {e}")
    return items


def _word_set(title: str) -> set[str]:
    stop = {"the", "a", "an", "in", "on", "at", "to", "of", "and", "for", "is", "are", "as"}
    return {w.lower() for w in title.split() if len(w) > 2 and w.lower() not in stop}


def deduplicate(items: list[dict]) -> list[dict]:
    kept = []
    for item in items:
        ws = _word_set(item["title"])
        duplicate = False
        for k in kept:
            overlap = ws & _word_set(k["title"])
            if ws and len(overlap) / len(ws) > 0.60:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept


def build_prompt(items: list[dict], now: datetime.datetime) -> str:
    lines = []
    for it in items:
        age = int((now - it["dt"]).total_seconds() / 60)
        lines.append(f"[{it['source']} {age}m ago] {it['title']}")
    n = len(items)
    headlines = "\n".join(lines)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""You are an institutional FX macro analyst. Analyse these {n} FX news headlines from the last 4 hours and extract the key market themes.

Headlines:
{headlines}

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "themes": [
    {{"theme": "...", "currencies": ["USD","JPY"], "direction": "bullish|bearish|neutral", "confidence": "high|medium|low"}},
    ...max 4 themes...
  ],
  "usd_bias": "bullish|bearish|neutral",
  "risk_sentiment": "risk-on|risk-off|neutral",
  "key_observation": "One sentence - most important non-obvious insight",
  "watch": "One upcoming event or level worth watching",
  "updated": "{ts}",
  "headline_count": {n}
}}"""


def call_claude(prompt: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    print(f"  [Claude] Raw response preview: {raw[:200]}")
    return json.loads(raw.strip())


def main():
    print(f"\n=== News Brief — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)
    now    = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=4)

    all_items = []
    for name, url in RSS_FEEDS:
        all_items.extend(fetch_feed(name, url, cutoff))

    all_items.sort(key=lambda x: x["dt"], reverse=True)
    all_items = deduplicate(all_items)[:40]
    print(f"  Total headlines after dedup: {len(all_items)}")

    if not all_items:
        print("  No headlines — writing stub")
        stub = {**STUB, "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
        with open(OUTPUT, "w") as f:
            json.dump(stub, f, indent=2)
        print(f"  Saved: {OUTPUT}")
        return

    prompt = build_prompt(all_items, now)

    try:
        brief = call_claude(prompt)
        brief["status"] = "ok"
        print(f"  Claude: {len(brief.get('themes', []))} themes, usd_bias={brief.get('usd_bias')}")
    except Exception as e:
        print(f"  Claude error: {e}")
        brief = {**STUB, "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ")}

    with open(OUTPUT, "w") as f:
        json.dump(brief, f, indent=2)
    print(f"  Saved: {OUTPUT}")
    print("=== News Brief complete ===\n")


if __name__ == "__main__":
    main()
