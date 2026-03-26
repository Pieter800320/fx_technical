"""
scanner/fetch.py
Twelvedata OHLCV fetcher with free-tier rate limiting.

Free tier limits:
  - 8 requests/minute
  - 800 requests/day

Strategy: fetch pairs in batches of 8, sleep 60s between batches.
"""

import os
import time
import requests
import pandas as pd

API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
BASE_URL = "https://api.twelvedata.com/time_series"

TF_MAP = {
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}

BARS_NEEDED = {
    "H1":  250,   # SMA200 warmup + buffer
    "H4":  250,
    "D1":  250,
}

BATCH_SIZE = 8
BATCH_SLEEP = 62  # seconds between batches (safe margin over 60s)


def fetch_pair(pair: str, timeframe: str) -> pd.DataFrame | None:
    """
    Fetch OHLCV for a single pair.
    pair: "EUR/USD"
    timeframe: "H1" | "H4" | "D1"
    Returns DataFrame with columns [datetime, open, high, low, close, volume]
    or None on error.
    """
    params = {
        "symbol":     pair,
        "interval":   TF_MAP[timeframe],
        "outputsize": BARS_NEEDED[timeframe],
        "apikey":     API_KEY,
        "format":     "JSON",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "error":
            print(f"  [TD] Error for {pair}: {data.get('message')}")
            return None

        values = data.get("values", [])
        if not values:
            return None

        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    except Exception as e:
        print(f"  [TD] Exception fetching {pair}: {e}")
        return None


def fetch_all_pairs(pairs: list[str], timeframe: str) -> dict:
    """
    Fetch all pairs with rate limiting.
    Returns { "EUR/USD": DataFrame, ... }
    """
    results = {}
    for i, pair in enumerate(pairs):
        print(f"  Fetching {pair} {timeframe} ({i+1}/{len(pairs)})")
        df = fetch_pair(pair, timeframe)
        results[pair] = df
        # Rate limit: sleep after every BATCH_SIZE requests
        if (i + 1) % BATCH_SIZE == 0 and (i + 1) < len(pairs):
            print(f"  Rate limit pause ({BATCH_SLEEP}s)...")
            time.sleep(BATCH_SLEEP)
        else:
            time.sleep(0.5)  # small gap between individual calls
    return results
