"""scanner/embed_d1_ohlcv.py
Fetches D1 OHLCV bars and embeds them into data/d1_scores.json as a _ohlcv key.
Run this AFTER scan_d1.py in your GitHub Actions workflow.

Add to your d1.yml (or equivalent) after the scan_d1 step:
    - name: Embed D1 OHLCV
      run: python scanner/embed_d1_ohlcv.py
"""
import json, os, sys, calendar, datetime as _dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS
from scanner.fetch import fetch_all_pairs

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT  = os.path.join(DATA_DIR, "d1_scores.json")

def main():
    print(f"\n=== Embed D1 OHLCV — {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")

    # Load existing d1_scores.json
    try:
        with open(D1_OUTPUT) as f:
            d1_data = json.load(f)
    except Exception as e:
        print(f"  ERROR reading {D1_OUTPUT}: {e}")
        return

    # Fetch D1 OHLCV
    ohlcv = fetch_all_pairs(PAIRS, "D1")

    d1_ohlcv = {}
    for pair in PAIRS:
        df = ohlcv.get(pair)
        if df is None or len(df) < 2:
            print(f"  {pair}: no data")
            continue
        bars = df.tail(200).copy()
        bars_list = []
        for ts, row in bars.iterrows():
            try:
                dt_raw = row.get("datetime") if hasattr(row, "get") else str(ts)
                dt_obj = _dt.datetime.fromisoformat(str(dt_raw))
                t = calendar.timegm(dt_obj.timetuple())
                bars_list.append({
                    "time":  t,
                    "open":  round(float(row["open"]),  6),
                    "high":  round(float(row["high"]),  6),
                    "low":   round(float(row["low"]),   6),
                    "close": round(float(row["close"]), 6),
                })
            except Exception as bar_err:
                print(f"  [OHLCV] bar error {pair}: {bar_err}")
                continue
        if bars_list:
            d1_ohlcv[pair] = bars_list

    print(f"  OHLCV: {len(d1_ohlcv)} pairs fetched")

    # Embed and save
    d1_data["_ohlcv"] = d1_ohlcv
    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_data, f, indent=2)
    print(f"  Saved: {D1_OUTPUT}")
    print("=== D1 OHLCV embed complete ===\n")

if __name__ == "__main__":
    main()
