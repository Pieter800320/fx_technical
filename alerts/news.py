# alerts/news.py
#
# Changes from audit:
#   - Module-level RSS cache with 5-minute TTL.
#     Multiple pairs sharing a currency (e.g. EUR/USD + EUR/JPY) previously
#     triggered duplicate fetches of all three RSS feeds. Now each feed is
#     fetched at most once per scan run.
#   - ForexFactory calendar date parsing now logs failures instead of
#     silently swallowing them. Protects against FF format changes.

import re
import time
import datetime
import urllib.request
import xml.etree.ElementTree as ET
import json

RSS_FEEDS = [
    ("DailyFX",     "https://www.dailyfx.com/feeds/all"),
    ("MarketPulse", "https://www.marketpulse.com/feed/"),
    ("FXStreet",    "https://www.fxstreet.com/rss/news"),
]
HEADERS       = {"User-Agent": "Mozilla/5.0 (FX-Dashboard-Bot/1.0)"}
FF_URL        = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
RSS_CACHE_TTL = 300  # seconds — one fetch per feed per scan run

# Module-level cache: {url: (items, timestamp)}
_rss_cache: dict = {}


def _fetch_rss(url: str) -> list:
    """Fetch and parse an RSS feed, returning a list of {title, summary} dicts.
    Results are cached for RSS_CACHE_TTL seconds to avoid duplicate fetches
    when multiple pairs share a currency."""
    now = time.time()
    cached = _rss_cache.get(url)
    if cached and (now - cached[1]) < RSS_CACHE_TTL:
        return cached[0]

    items = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        for item in root.iter("item"):
            title   = (item.findtext("title") or "").strip()
            summary = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
            if len(summary) > 120:
                summary = summary[:117] + "..."
            items.append({"title": title, "summary": summary})
    except Exception as e:
        print(f"  [News] RSS fetch failed ({url}): {e}")

    _rss_cache[url] = (items, now)
    return items


def get_rss_headline(pair: str):
    """Return (source, headline) for the pair, or None if not found."""
    currencies = pair.split("/")
    pair_str   = pair.replace("/", "")

    # Pass 1: exact pair match in headline
    for source, url in RSS_FEEDS:
        for item in _fetch_rss(url):
            t = item["title"].upper()
            if pair_str in t or all(c in t for c in currencies):
                return source, item["title"]

    # Pass 2: either currency mentioned
    for source, url in RSS_FEEDS:
        for item in _fetch_rss(url):
            if any(c in item["title"].upper() for c in currencies):
                return source, item["title"]

    return None


def get_upcoming_events(pair: str, hours_ahead: int = 12) -> list:
    """Return high-impact ForexFactory events for the pair's currencies."""
    currencies = pair.split("/")
    now        = datetime.datetime.utcnow()
    cutoff     = now + datetime.timedelta(hours=hours_ahead)
    upcoming   = []

    try:
        req = urllib.request.Request(FF_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read())
    except Exception as e:
        print(f"  [News] ForexFactory fetch failed: {e}")
        return []

    for ev in events:
        if ev.get("impact", "").lower() != "high":
            continue
        currency = ev.get("country", "").upper()
        if currency not in currencies:
            continue

        dt_str = ev.get("date", "")
        try:
            # ForexFactory may omit colon in tz offset: +0200 → +02:00
            dt_str_clean = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", dt_str)
            dt = datetime.datetime.fromisoformat(dt_str_clean)
            offset = dt.utcoffset()
            dt_utc = (dt - offset).replace(tzinfo=None) if offset else dt.replace(tzinfo=None)
        except Exception as e:
            print(f"  [News] FF date parse error for '{dt_str}': {e}")
            continue

        if now <= dt_utc <= cutoff:
            upcoming.append({
                "currency": currency,
                "event":    ev.get("title", ""),
                "time_utc": dt_utc.strftime("%H:%M"),
                "impact":   "High",
            })

    upcoming.sort(key=lambda x: x["time_utc"])
    return upcoming


def get_alert_context(pair: str) -> dict:
    return {"headline": get_rss_headline(pair), "events": get_upcoming_events(pair)}
