"""alerts/news.py"""
import re, datetime, urllib.request, xml.etree.ElementTree as ET, json

RSS_FEEDS = [
    ("DailyFX",     "https://www.dailyfx.com/feeds/all"),
    ("MarketPulse", "https://www.marketpulse.com/feed/"),
    ("FXStreet",    "https://www.fxstreet.com/rss/news"),
]
HEADERS   = {"User-Agent": "Mozilla/5.0 (FX-Dashboard-Bot/1.0)"}
FF_URL    = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

def _fetch_rss(url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root  = ET.fromstring(raw)
        items = []
        for item in root.iter("item"):
            title   = (item.findtext("title") or "").strip()
            summary = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
            if len(summary) > 120: summary = summary[:117] + "..."
            items.append({"title": title, "summary": summary})
        return items
    except: return []

def get_rss_headline(pair):
    currencies = pair.split("/")
    pair_str   = pair.replace("/", "")
    for source, url in RSS_FEEDS:
        for item in _fetch_rss(url):
            t = item["title"].upper()
            if pair_str in t or all(c in t for c in currencies):
                return source, item["title"]
    for source, url in RSS_FEEDS:
        for item in _fetch_rss(url):
            if any(c in item["title"].upper() for c in currencies):
                return source, item["title"]
    return None

def get_upcoming_events(pair, hours_ahead=12):
    currencies = pair.split("/")
    now    = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(hours=hours_ahead)
    try:
        req = urllib.request.Request(FF_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read())
    except: return []
    upcoming = []
    for ev in events:
        if ev.get("impact", "").lower() != "high": continue
        currency = ev.get("country", "").upper()
        if currency not in currencies: continue
        dt_str = ev.get("date", "")
        try:
            dt_str_clean = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", dt_str)
            dt = datetime.datetime.fromisoformat(dt_str_clean)
            offset = dt.utcoffset()
            dt_utc = (dt - offset).replace(tzinfo=None) if offset else dt.replace(tzinfo=None)
        except: continue
        if now <= dt_utc <= cutoff:
            upcoming.append({"currency": currency, "event": ev.get("title", ""), "time_utc": dt_utc.strftime("%H:%M"), "impact": "High"})
    upcoming.sort(key=lambda x: x["time_utc"])
    return upcoming

def get_alert_context(pair):
    return {"headline": get_rss_headline(pair), "events": get_upcoming_events(pair)}
