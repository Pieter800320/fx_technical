# scanner/fetch.py
#
# Change from audit:
#   - H4 outputsize increased to 500 (~83 days) for reset_score momentum
#     series which benefits from a longer lookback window.

import os
import time
import requests
import pandas as pd
from config.pairs import td_symbol

API_KEY  = os.environ.get("TWELVEDATA_API_KEY", "")
BASE_URL = "https://api.twelvedata.com/time_series"

TF_MAP = {"H1": "1h", "H4": "4h", "D1": "1day"}

BARS_NEEDED = {
    "H1": 500,   # 500 hourly bars (~21 days)
    "H4": 400,   # 400 × 4h bars (~67 days)
    "D1": 300,   # 300 daily bars (~1.2 years, needed for EMA200 + embed_d1_ohlcv 200-bar chart)
}

BATCH_SIZE   = 7
BATCH_SLEEP  = 62
MIN_INTERVAL = 8.0  # seconds between fetches → ≤7.5 req/min ceiling

_last_fetch_time = 0.0


def _rate_limit_wait():
    global _last_fetch_time
    elapsed = time.time() - _last_fetch_time
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_fetch_time = time.time()


# ── Spike filter ─────────────────────────────────────────────────────────────
# Forex data feeds occasionally emit bad ticks at weekly opens or during
# connectivity gaps — a wick that is 5-100× the normal range.
# We clamp high/low to within MAX_SPIKE_PCT of the candle open.
# 3 % is safe for all forex pairs including JPY crosses:
# the largest legitimate single-hourly move on record is ~4 % (flash crashes),
# so 3 % catches all data errors without touching real price action.

MAX_SPIKE_PCT = 0.03  # 3 % max deviation of high/low from open


def _filter_spikes(df, pair=""):
    """Clamp candle high/low that deviate more than MAX_SPIKE_PCT from open."""
    if df.empty:
        return df
    spikes_fixed = 0
    for idx in df.index:
        o = df.at[idx, "open"]
        if not o or o != o:  # skip NaN
            continue
        threshold = o * MAX_SPIKE_PCT
        h = df.at[idx, "high"]
        l = df.at[idx, "low"]
        c = df.at[idx, "close"]
        fixed = False
        if abs(h - o) > threshold:
            df.at[idx, "high"] = max(o, c)  # clamp to realistic max
            fixed = True
        if abs(l - o) > threshold:
            df.at[idx, "low"] = min(o, c)   # clamp to realistic min
            fixed = True
        if fixed:
            spikes_fixed += 1
    if spikes_fixed:
        print(f"    [spike] {pair}: clamped {spikes_fixed} bad candle(s)")
    return df


def fetch_pair(pair, timeframe):
    params = {
        "symbol":     td_symbol(pair),
        "interval":   TF_MAP[timeframe],
        "outputsize": BARS_NEEDED[timeframe],
        "apikey":     API_KEY,
        "format":     "JSON",
    }
    try:
        _rate_limit_wait()
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "error":
            msg = data.get("message", "")
            if "run out of API credits for the current minute" in msg:
                print(f"  [TD] Per-minute limit hit for {pair}, waiting 62s and retrying...")
                time.sleep(62)
                _rate_limit_wait()
                resp = requests.get(BASE_URL, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "error":
                    print(f"  [TD] Error for {pair} after retry: {data.get('message')}")
                    return None
            else:
                print(f"  [TD] Error for {pair}: {msg}")
                return None
        values = data.get("values", [])
        if not values:
            return None
        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = _filter_spikes(df, pair)
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
    return results
