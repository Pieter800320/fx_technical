"""scanner/embed_d1_ohlcv.py
Fetches D1 OHLCV bars and embeds them into data/d1_scores.json as _ohlcv.
Run AFTER scan_d1.py. Sleeps 70s first to respect Twelvedata rate limits.
"""
import json, os, sys, time, calendar, datetime as _dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT = os.path.join(DATA_DIR, "d1_scores.json")

# Twelvedata free tier: 8 credits/min, each pair = 1 credit
BATCH_SIZE   = 8
RATE_DELAY   = 65   # seconds between batches
INITIAL_WAIT = 70   # seconds to let rate limit reset after scan_d1.py

def fetch_ohlcv_for_pair(pair: str, outputsize: int = 200) -> list:
    """Fetch D1 OHLCV directly via Twelvedata REST (avoids scanner abstraction issues)."""
    import requests
    api_key = os.environ.get("TWELVEDATA_API_KEY", "")
    if not api_key:
        print(f"  [{pair}] No API key"); return []
    symbol = pair  # e.g. EUR/USD
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol, "interval": "1day",
        "outputsize": outputsize, "apikey": api_key,
        "format": "JSON", "timezone": "UTC",
    }
    try:
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
        # Rate limit: pause between batches
        if i > 0 and i % BATCH_SIZE == 0:
            print(f"  Batch complete — waiting {RATE_DELAY}s...")
            time.sleep(RATE_DELAY)

        bars = fetch_ohlcv_for_pair(pair, outputsize=200)
        if bars:
            d1_ohlcv[pair] = bars
            print(f"  {pair}: {len(bars)} bars")
        else:
            print(f"  {pair}: no data")

    print(f"  OHLCV: {len(d1_ohlcv)}/{len(PAIRS)} pairs")
    d1_data["_ohlcv"] = d1_ohlcv
    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_data, f, indent=2)
    print(f"  Saved → {D1_OUTPUT}")
    print("=== D1 OHLCV embed complete ===\n")

if __name__ == "__main__":
    main()
