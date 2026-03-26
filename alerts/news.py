"""
alerts/news.py
Free fundamental context for Telegram alerts.

Two data sources:
  1. RSS feeds (FXStreet, DailyFX, MarketPulse) — latest analysis headline
  2. ForexFactory economic calendar — upcoming high-impact events today

No API keys required. No cost.
"""

import re
import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

# ── RSS Sources ───────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("DailyFX",     "https://www.dailyfx.com/feeds/all"),
    ("MarketPulse", "https://www.marketpulse.com/feed/"),
    ("FXStreet",    "https://www.fxstreet.com/rss/news"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (FX-Dashboard-Bot/1.0)"
}


def _fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS feed. Returns list of {title, summary}."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = []
        for item in root.iter("item"):
            title   = item.findtext("title") or ""
            summary = item.findtext("description") or item.findtext("summary") or ""
            # Strip HTML tags from summary
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            # Truncate summary to ~120 chars
            if len(summary) > 120:
                summary = summary[:117] + "..."
            items.append({"title": title.strip(), "summary": summary})
        return items
    except Exception:
        return []


def _currencies_in_pair(pair: str) -> list[str]:
    """'EUR/USD' → ['EUR', 'USD']"""
    return pair.split("/")


def get_rss_headline(pair: str) -> tuple[str, str] | None:
    """
    Search RSS feeds for the most relevant recent headline for this pair.
    Returns (source_name, headline) or None if nothing found.
    """
    currencies = _currencies_in_pair(pair)
    pair_str   = pair.replace("/", "")  # EURUSD

    for source, url in RSS_FEEDS:
        items = _fetch_rss(url)
        for item in items:
            title_upper = item["title"].upper()
            # Match if pair name or both currencies appear in the title
            if pair_str in title_upper or all(c in title_upper for c in currencies):
                return source, item["title"]

    # Fallback: find any headline mentioning either currency
    for source, url in RSS_FEEDS:
        items = _fetch_rss(url)
        for item in items:
            title_upper = item["title"].upper()
            if any(c in title_upper for c in currencies):
                return source, item["title"]

    return None


# ── ForexFactory Calendar ─────────────────────────────────────────────────────

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def get_upcoming_events(pair: str, hours_ahead: int = 12) -> list[dict]:
    """
    Fetch ForexFactory calendar and return high-impact events
    for this pair's currencies within the next `hours_ahead` hours.

    Returns list of {currency, event, time_utc, impact}
    """
    currencies = _currencies_in_pair(pair)
    now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(hours=hours_ahead)

    try:
        req = urllib.request.Request(FF_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            events = json.loads(resp.read())
    except Exception:
        return []

    upcoming = []
    for ev in events:
        # Only high impact
        if ev.get("impact", "").lower() != "high":
            continue

        currency = ev.get("country", "").upper()
        if currency not in currencies:
            continue

        # Parse datetime — FF format: "01-15-2026T10:30:00-0500"
        dt_str = ev.get("date", "")
        try:
            # Normalize offset format for fromisoformat
            dt_str_clean = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", dt_str)
            dt = datetime.datetime.fromisoformat(dt_str_clean)
            # Convert to UTC
            offset = dt.utcoffset()
            dt_utc = (dt - offset).replace(tzinfo=None) if offset else dt.replace(tzinfo=None)
        except Exception:
            continue

        if now <= dt_utc <= cutoff:
            upcoming.append({
                "currency":  currency,
                "event":     ev.get("title", "Unknown event"),
                "time_utc":  dt_utc.strftime("%H:%M"),
                "impact":    "High",
            })

    # Sort by time
    upcoming.sort(key=lambda x: x["time_utc"])
    return upcoming


# ── Combined context builder ──────────────────────────────────────────────────

def get_alert_context(pair: str) -> dict:
    """
    Returns:
      {
        "headline":  ("DailyFX", "EUR surges as ECB signals...") or None,
        "events":    [{"currency":"EUR","event":"CPI","time_utc":"10:00"}, ...],
      }
    """
    headline = get_rss_headline(pair)
    events   = get_upcoming_events(pair)
    return {"headline": headline, "events": events}
