"""scanner/scan_calendar.py — Write high-impact economic events for the next 7 days.
Writes to data/calendar.json.

Uses the faireconomy.media JSON mirror of the ForexFactory calendar
(same data, no iCal parsing, already used by alerts/news.py).
Fetches both thisweek and nextweek feeds to guarantee a 7-day window.
"""
import json, os, sys, re, datetime
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_DIR     = os.path.join(os.path.dirname(__file__), "..", "data")
CALENDAR_OUT = os.path.join(DATA_DIR, "calendar.json")
HEADERS      = {"User-Agent": "Mozilla/5.0 (FX-Dashboard-Bot/1.0)"}

FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]


def _fetch_feed(url: str) -> list:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [Calendar] Fetch failed ({url}): {e}")
        return []


def _to_utc(dt_str: str) -> datetime.datetime | None:
    try:
        clean = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", dt_str)
        dt    = datetime.datetime.fromisoformat(clean)
        off   = dt.utcoffset()
        return (dt - off).replace(tzinfo=None) if off else dt.replace(tzinfo=None)
    except Exception as e:
        print(f"  [Calendar] Date parse error for '{dt_str}': {e}")
        return None


def main():
    print(f"\n=== Calendar Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    now    = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(days=7)

    raw = []
    for url in FEEDS:
        raw.extend(_fetch_feed(url))

    events = []
    seen   = set()
    for ev in raw:
        if ev.get("impact", "").lower() != "high":
            continue
        dt_utc = _to_utc(ev.get("date", ""))
        if dt_utc is None or not (now <= dt_utc <= cutoff):
            continue
        currency = ev.get("country", "").upper()
        title    = ev.get("title", "").strip()
        key      = (currency, title, dt_utc.isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "currency": currency,
            "event":    title,
            "datetime": dt_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "impact":   "High",
        })

    events.sort(key=lambda x: x["datetime"])

    with open(CALENDAR_OUT, "w") as f:
        json.dump({"events": events, "updated": now.isoformat(),
                   "window": f"{now.strftime('%Y-%m-%d')} to {cutoff.strftime('%Y-%m-%d')}"},
                  f, indent=2)

    print(f"  {len(events)} high-impact events → {CALENDAR_OUT}")
    for ev in events:
        print(f"  {ev['datetime']}  {ev['currency']:4s}  {ev['event']}")
    print("=== Calendar Scan complete ===\n")


if __name__ == "__main__":
    main()
