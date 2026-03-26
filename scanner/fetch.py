"""
scanner/fetch.py
Twelvedata OHLCV fetcher with free-tier rate limiting.
"""

import os
import time
import requests
import pandas as pd
from config.pairs import td_symbol

API_KEY  = os.environ.get("TWELVEDATA_API_KEY", "")
BASE_URL = "https://api.twelvedata.com/time_series"

TF_MAP = {
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}

BARS_NEEDED = {
    "H1":  250,
    "H4":  250,
    "D1":  250,
}

BATCH_SIZE  = 8
BATCH_SLEEP = 62


def fetch_pair(pair, timeframe):
    symbol = td_symbol(pair)
    params = {
        "symbol":     symbol,
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
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        print(f"  [TD] Exception fetching {pair}: {e}")
        return None


def fetch_all_pairs(pairs, timeframe):
    results = {}
    for i, pair in enumerate(pairs):
        print(f"  Fetching {pair} {timeframe} ({i+1}/{len(pairs)})")
        results[pair] = fetch_pair(pair, timeframe)
        if (i + 1) % BATCH_SIZE == 0 and (i + 1) < len(pairs):
            print(f"  Rate limit pause ({BATCH_SLEEP}s)...")
            time.sleep(BATCH_SLEEP)
        else:
            time.sleep(0.5)
    return results
