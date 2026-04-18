"""scanner/embed_d1_ohlcv.py — Fetch D1 OHLCV and embed into d1_scores.json.
Run AFTER scan_d1.py. INITIAL_WAIT lets the per-minute credit window reset
between the two processes. Per-fetch pacing is handled by _rate_limit_wait().
"""
import json, os, sys, time, calendar, datetime as _dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS
from scanner.fetch import _rate_limit_wait, BATCH_SIZE, BATCH_SLEEP

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT = os.path.join(DATA_DIR, "d1_scores.json")

INITIAL_WAIT = 70   # seconds to let rate limit reset after scan_d1.py

def fetch_ohlcv_for_pair(pair: str, outputsize: int = 200) -> list:
    """Fetch D1 OHLCV directly via Twelvedata REST (avoids scanner abstraction issues)."""
    import requests
    api_key = os.environ.get("TWELVEDATA_API_KEY", "")
    if not api_key:
        print(f"  [{pair}] No API key"); return []
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": pair, "interval": "1day",
        "outputsize": outputsize, "apikey": api_key,
        "format": "JSON", "timezone": "UTC",
    }
    try:
        _rate_limit_wait()
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        if data.get("status") == "error":
            print(f"  [{pair}] API error: {data.get('message')}")
            return []
        values = data.get("values", [])
        bars = []
        for v in reversed(values):  # oldest first
            try:
                dt = _dt.datetime.fromisoformat(v["datetime"])
                t  = calendar.timegm(dt.timetuple())
                bars.append({
                    "time":  t,
                    "open":  round(float(v["open"]),  6),
                    "high":  round(float(v["high"]),  6),
                    "low":   round(float(v["low"]),   6),
                    "close": round(float(v["close"]), 6),
                })
            except Exception as e:
                continue
        return bars
    except Exception as e:
        print(f"  [{pair}] Fetch error: {e}")
        return []

def main():
    print(f"\n=== Embed D1 OHLCV — {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")

    print(f"  Waiting {INITIAL_WAIT}s for rate limit to reset after scan_d1.py...")
    time.sleep(INITIAL_WAIT)

    try:
        with open(D1_OUTPUT) as f:
            d1_data = json.load(f)
    except Exception as e:
        print(f"  ERROR reading {D1_OUTPUT}: {e}"); return

    d1_ohlcv = {}
    for i, pair in enumerate(PAIRS):
        bars = fetch_ohlcv_for_pair(pair, outputsize=200)
        if bars:
            d1_ohlcv[pair] = bars
            print(f"  {pair}: {len(bars)} bars")
        else:
            print(f"  {pair}: no data")
        if (i + 1) % BATCH_SIZE == 0 and (i + 1) < len(PAIRS):
            print(f"  Rate limit pause ({BATCH_SLEEP}s)...")
            time.sleep(BATCH_SLEEP)

    print(f"  OHLCV: {len(d1_ohlcv)}/{len(PAIRS)} pairs")
    d1_data["_ohlcv"] = d1_ohlcv
    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_data, f, indent=2)
    print(f"  Saved → {D1_OUTPUT}")
    print("=== D1 OHLCV embed complete ===\n")

if __name__ == "__main__":
    main()
