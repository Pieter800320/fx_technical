# scanner/fetch.py
#
# Change from audit:
#   - H4 outputsize reduced from 5000 → 300.
#     score_pair() needs 210 bars minimum. Structure detection uses ~30 bars.
#     300 provides a safe margin without fetching 3.5 years of unused data.
#     Meaningfully faster scan times on GitHub Actions.

import os
import time
import requests
import pandas as pd
from config.pairs import td_symbol

API_KEY  = os.environ.get("TWELVEDATA_API_KEY", "")
BASE_URL = "https://api.twelvedata.com/time_series"

TF_MAP = {"H1": "1h", "H4": "4h", "D1": "1day"}

BARS_NEEDED = {
    "H1": 250,   # 250 hourly bars (~10 days)
    "H4": 300,   # 300 × 4h bars (~50 days) — reduced from 5000 (was 833 days, wasteful)
    "D1": 500,   # 500 daily bars (~2 years, needed for EMA200 + embed_d1_ohlcv 200-bar chart)
}

BATCH_SIZE  = 7
BATCH_SLEEP = 62


def fetch_pair(pair, timeframe):
    params = {
        "symbol":     td_symbol(pair),
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
