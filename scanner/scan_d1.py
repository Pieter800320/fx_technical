"""scanner/scan_d1.py — D1 scan, CSM, regime"""
import json, os, sys, datetime, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair
from scanner.csm import compute_currency_strength, MAJOR_PAIRS, STRENGTH_PAIRS, CSM_EXTRA_PAIRS
from scanner.regime import classify_regime

DATA_DIR      = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT     = os.path.join(DATA_DIR, "d1_scores.json")
CSM_OUTPUT    = os.path.join(DATA_DIR, "csm.json")
REGIME_OUTPUT = os.path.join(DATA_DIR, "regime.json")

# Tradeable pairs only (excludes XAU/USD if present)
FOREX_PAIRS = [p for p in PAIRS if p != "XAU/USD"]

# All pairs needed for D1 CSM — tradeable pairs + CSM-only extras
D1_FETCH_PAIRS = FOREX_PAIRS + [p for p in CSM_EXTRA_PAIRS if p not in FOREX_PAIRS]


def load_prev_regime():
    try:
        with open(REGIME_OUTPUT) as f:
            data = json.load(f)
            return data.get("data_source") == "H4"
    except:
        return False


def main():
    print(f"\n=== D1 Scan — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    print("\n  Fetching D1 data...")
    # D1_FETCH_PAIRS includes CSM_EXTRA_PAIRS (EUR/GBP, EUR/CHF) so the
    # CSM calculation gets a full 12-pair strength data set.
    d1_ohlcv = fetch_all_pairs(D1_FETCH_PAIRS, "D1")

    print(f"\n  Rate limit pause before H4 fetch (62s)...")
    time.sleep(62)

    print("  Fetching H4 data for currency strength...")
    # MAJOR_PAIRS already includes EUR/GBP and EUR/CHF
    h4_ohlcv = fetch_all_pairs(MAJOR_PAIRS, "H4")

    d1_results = {}
    now = datetime.datetime.utcnow()

    # Score only the tradeable FOREX_PAIRS — CSM extras are not scored
    for pair in FOREX_PAIRS:
        df = d1_ohlcv.get(pair)
        if df is None:
            print(f"  {pair_display(pair)}: no data"); continue
        result = score_pair(df, timeframe="D1")
        if result is None:
            print(f"  {pair_display(pair)}: insufficient bars"); continue

        display     = pair_display(pair)
        filter_note = "" if result["filter_ok"] else f" ⚠️ {', '.join(result['filter_reasons'])}"
        print(f"  {display}: {result['score']:+d} → {result['label']}{filter_note}")

        d1_results[pair] = {
            "score":      result["score"],
            "label":      result["label"],
            "direction":  result["direction"],
            "raw":        result["raw"],
            "signals":    result["signals"],
            "filter_ok":  result["filter_ok"],
            "conflict":   result.get("conflict", False),
            "structure":  result.get("structure", {}),
            "adx_weight": result.get("adx_weight", 1.0),
            "updated":    now.isoformat(),
        }

    # Currency strength — pass full d1_ohlcv (includes CSM extras)
    print("\n  Computing currency strength...")
    csm_result = compute_currency_strength(d1_ohlcv, h4_ohlcv)
    for ccy, val in csm_result["rankings"].items():
        print(f"    {ccy}: {val:.1f}")

    # Regime
    print("\n  Computing market regime...")
    prev_h4 = load_prev_regime()
    regime_result = classify_regime(
        {"rankings": csm_result["rankings"]},
        d1_results,
        prev_h4_regime=prev_h4,
    )
    print(f"  Regime: {regime_result['regime']} ({regime_result['confidence']}) "
          f"[{regime_result['data_source']}] VOL_RATIO={regime_result['vol_ratio']}")

    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_results, f, indent=2)
    with open(CSM_OUTPUT, "w") as f:
        json.dump({
            "rankings":   csm_result["rankings"],
            "confidence": csm_result["confidence"],
            "breakdown":  csm_result.get("breakdown", {}),
            "updated":    now.isoformat(),
        }, f, indent=2)
    with open(REGIME_OUTPUT, "w") as f:
        json.dump({
            "regime":      regime_result["regime"],
            "confidence":  regime_result["confidence"],
            "data_source": regime_result["data_source"],
            "vol_ratio":   regime_result["vol_ratio"],
            "signals":     regime_result["signals"],
            "updated":     now.isoformat(),
        }, f, indent=2)

    print(f"\n  Saved: {D1_OUTPUT}")
    print(f"  Saved: {CSM_OUTPUT}")
    print(f"  Saved: {REGIME_OUTPUT}")
    print("=== D1 Scan complete ===\n")


if __name__ == "__main__":
    main()
