"""scanner/scan_d1.py — D1 scan, CSM, regime, conviction refresh
Changes from audit:
  - XAU/USD now fetched and scored via REGIME_EXTRA_PAIRS.
  - vol_ratio removed from REGIME_OUTPUT.
  - D1_FETCH_PAIRS updated to include REGIME_EXTRA_PAIRS.
  - New pairs in CSM_EXTRA_PAIRS picked up automatically.
  - Daily conviction refresh: recomputes technical components using latest
    D1/CSM data. COT components carry forward from last Saturday's scan.
"""
import json, os, sys, datetime, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.pairs import PAIRS, pair_display, REGIME_EXTRA_PAIRS
from scanner.fetch import fetch_all_pairs
from scanner.score import score_pair
from scanner.csm import compute_currency_strength, MAJOR_PAIRS, STRENGTH_PAIRS, CSM_EXTRA_PAIRS
from scanner.regime import classify_regime
from scanner.conviction import compute_conviction

DATA_DIR      = os.path.join(os.path.dirname(__file__), "..", "data")
D1_OUTPUT     = os.path.join(DATA_DIR, "d1_scores.json")
CSM_OUTPUT    = os.path.join(DATA_DIR, "csm.json")
REGIME_OUTPUT = os.path.join(DATA_DIR, "regime.json")
CONVICTION_OUT= os.path.join(DATA_DIR, "conviction.json")
COT_FILE      = os.path.join(DATA_DIR, "cot.json")

# Tradeable forex pairs only (excludes XAU/USD)
FOREX_PAIRS = [p for p in PAIRS if p != "XAU/USD"]

# All pairs fetched in D1 scan:
#   - Tradeable forex pairs (scored + used for regime)
#   - CSM extra pairs (EUR/GBP, EUR/CHF, GBP/CHF, AUD/NZD, AUD/CAD, GBP/AUD)
#   - Regime extra pairs (XAU/USD — gold direction for risk-off/risk-on)
D1_FETCH_PAIRS = (
    FOREX_PAIRS
    + [p for p in CSM_EXTRA_PAIRS    if p not in FOREX_PAIRS]
    + [p for p in REGIME_EXTRA_PAIRS if p not in FOREX_PAIRS and p not in CSM_EXTRA_PAIRS]
)


def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}

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
    now = datetime.datetime.utcnow()

    print(f"\n  Fetching D1 data ({len(D1_FETCH_PAIRS)} pairs)...")
    d1_ohlcv = fetch_all_pairs(D1_FETCH_PAIRS, "D1")

    print(f"\n  Rate limit pause before H4 fetch (62s)...")
    time.sleep(62)

    print("  Fetching H4 data for currency strength...")
    # MAJOR_PAIRS includes original 12 + new cross pairs for CSM
    h4_ohlcv = fetch_all_pairs(MAJOR_PAIRS, "H4")

    d1_results = {}

    # ── Score tradeable forex pairs ───────────────────────────────────────────
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

    # ── Score XAU/USD for regime classifier ───────────────────────────────────
    # Gold direction feeds regime.py: bull = risk-off signal, bear = risk-on signal.
    # Stored in d1_results under "XAU/USD" so classify_regime() can read it.
    gold_df = d1_ohlcv.get("XAU/USD")
    if gold_df is not None:
        gold_result = score_pair(gold_df, timeframe="D1")
        if gold_result:
            d1_results["XAU/USD"] = {
                "score":     gold_result["score"],
                "label":     gold_result["label"],
                "direction": gold_result["direction"],
                "raw":       gold_result["raw"],
                "signals":   gold_result["signals"],
                "filter_ok": gold_result["filter_ok"],
                "conflict":  gold_result.get("conflict", False),
                "structure": gold_result.get("structure", {}),
                "updated":   now.isoformat(),
            }
            print(f"  XAU/USD: {gold_result['score']:+d} → {gold_result['label']} "
                  f"({gold_result['direction']}) — used for regime only")
        else:
            print("  XAU/USD: insufficient bars for scoring")
    else:
        print("  XAU/USD: no data — gold signal inactive this cycle")

    # ── Currency strength ─────────────────────────────────────────────────────
    print("\n  Computing currency strength...")
    csm_result = compute_currency_strength(d1_ohlcv, h4_ohlcv)
    for ccy, val in csm_result["rankings"].items():
        print(f"    {ccy}: {val:.1f}")

    # ── Regime ────────────────────────────────────────────────────────────────
    print("\n  Computing market regime...")
    prev_h4 = load_prev_regime()
    regime_result = classify_regime(
        {"rankings": csm_result["rankings"]},
        d1_results,
        prev_h4_regime=prev_h4,
    )
    gold_dir = d1_results.get("XAU/USD", {}).get("direction", "neutral")
    print(f"  Regime: {regime_result['regime']} ({regime_result['confidence']}) "
          f"[{regime_result['data_source']}] Gold: {gold_dir}")

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(D1_OUTPUT, "w") as f:
        json.dump(d1_results, f, indent=2)

    with open(CSM_OUTPUT, "w") as f:
        json.dump({
            "rankings":   csm_result["rankings"],
            "confidence": csm_result["confidence"],
            "breakdown":  csm_result.get("breakdown", {}),
            "updated":    now.isoformat(),
        }, f, indent=2)

    # vol_ratio removed from output (regime.py no longer computes it)
    with open(REGIME_OUTPUT, "w") as f:
        json.dump({
            "regime":      regime_result["regime"],
            "confidence":  regime_result["confidence"],
            "data_source": regime_result["data_source"],
            "signals":     regime_result["signals"],
            "updated":     now.isoformat(),
        }, f, indent=2)

    print(f"\n  Saved: {D1_OUTPUT}")
    print(f"  Saved: {CSM_OUTPUT}")
    print(f"  Saved: {REGIME_OUTPUT}")

    # ── Daily conviction refresh ───────────────────────────────────────────────
    # Recomputes CSM extreme, extension, RSI breadth components using today's data.
    # COT components (cot_position, cot_oi, cot_disagg) carry forward from last
    # Saturday's scan_cot.py run — they're in cot.json.
    print("\n  Refreshing conviction scores (technical components)...")
    try:
        cot_data  = load_json(COT_FILE)
        h4_data   = load_json(os.path.join(DATA_DIR, "h4_scores.json"))
        prev_conv = load_json(CONVICTION_OUT)

        if not cot_data:
            # No COT data yet — first run before Saturday scan
            # Create minimal stub so conviction still shows technical components
            cot_data = {"cot_date": "pending", "cot_stale": True, "currencies": {}}

        conviction = compute_conviction(
            cot_data        = cot_data,
            d1_scores       = d1_results,
            h4_scores       = h4_data,
            csm_rankings    = csm_result["rankings"],
            prev_conviction = prev_conv,
        )
        with open(CONVICTION_OUT, "w") as f:
            json.dump({**conviction, "updated": now.isoformat()}, f, indent=2)
        print(f"  Saved: {CONVICTION_OUT}")

        # Print conviction summary
        for ccy, cdata in conviction["currencies"].items():
            print(f"    {ccy}: {cdata['conviction']:+d}  "
                  f"(csm={cdata['components']['csm_extreme']:+d} "
                  f"ext={cdata['components']['extension']:+d} "
                  f"rsi={cdata['components']['rsi_breadth']:+d})")
    except Exception as e:
        print(f"  [Conviction] ERROR: {e}")

    print("=== D1 Scan complete ===\n")


if __name__ == "__main__":
    main()
