"""scanner/scan_cot.py — Weekly COT runner
Runs every Saturday 14:00 UTC (after CFTC Friday ~15:30 EST release).
Downloads Legacy + Disaggregated COT, computes conviction scores,
merges with current technical data, writes data/cot.json + data/conviction.json.
"""
import json, os, sys, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scanner.cot import fetch_cot_data
from scanner.conviction import compute_conviction

DATA_DIR        = os.path.join(os.path.dirname(__file__), "..", "data")
COT_OUTPUT      = os.path.join(DATA_DIR, "cot.json")
CONVICTION_OUT  = os.path.join(DATA_DIR, "conviction.json")
D1_SCORES       = os.path.join(DATA_DIR, "d1_scores.json")
H4_SCORES       = os.path.join(DATA_DIR, "h4_scores.json")
CSM_FILE        = os.path.join(DATA_DIR, "csm.json")


def load_json(path):
    try:
        with open(path) as f: return json.load(f)
    except: return {}


def main():
    now = datetime.datetime.utcnow()
    print(f"\n=== COT Scan — {now.strftime('%Y-%m-%d %H:%M')} UTC ===")
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── Download and parse CFTC data ─────────────────────────────────────────
    print("\n  Fetching CFTC COT data...")
    cot_data = fetch_cot_data(year=now.year)

    print(f"\n  COT date: {cot_data['cot_date']} | Stale: {cot_data['cot_stale']}")
    for ccy, d in cot_data["currencies"].items():
        if d.get("available"):
            def _fmt(v): return f"{v:.0f}" if v is not None else "N/A"
            print(f"    {ccy}: net={d['net_noncomm']:+,d}  pct={_fmt(d['noncomm_pct'])}  "
                  f"am={_fmt(d['am_pct'])}  lf={_fmt(d['lf_pct'])}")
        else:
            print(f"    {ccy}: no data")

    # ── Save raw COT data ─────────────────────────────────────────────────────
    cot_out = {**cot_data, "updated": now.isoformat()}
    with open(COT_OUTPUT, "w") as f:
        json.dump(cot_out, f, indent=2)
    print(f"\n  Saved: {COT_OUTPUT}")

    # ── Load current technical data ───────────────────────────────────────────
    d1_scores    = load_json(D1_SCORES)
    h4_scores    = load_json(H4_SCORES)
    csm          = load_json(CSM_FILE)
    prev_conv    = load_json(CONVICTION_OUT)
    csm_rankings = csm.get("rankings", {})

    if not d1_scores:
        print("  WARNING: No D1 scores found — technical components will be zero")
    if not csm_rankings:
        print("  WARNING: No CSM rankings found — CSM extreme component will be zero")
    else:
        print(f"  CSM rankings loaded ({len(csm_rankings)} currencies):")
        for ccy, val in sorted(csm_rankings.items(), key=lambda x: x[1], reverse=True):
            print(f"    {ccy}: {val}")

    # ── Compute conviction scores ─────────────────────────────────────────────
    print("\n  Computing conviction scores...")
    result = compute_conviction(
        cot_data     = cot_data,
        d1_scores    = d1_scores,
        h4_scores    = h4_scores,
        csm_rankings = csm_rankings,
        prev_conviction = prev_conv,
    )

    # Print summary
    for ccy, data in result["currencies"].items():
        comp = data["components"]
        print(f"    {ccy}: conviction={data['conviction']:+d}  "
              f"[pos={comp['cot_position']:+d} oi={comp['cot_oi']:+d} "
              f"dis={comp['cot_disagg']:+d} csm={comp['csm_extreme']:+d} "
              f"ext={comp['extension']:+d} rsi={comp['rsi_breadth']:+d}]")

    # ── Save conviction ───────────────────────────────────────────────────────
    conv_out = {**result, "updated": now.isoformat()}
    with open(CONVICTION_OUT, "w") as f:
        json.dump(conv_out, f, indent=2)
    print(f"\n  Saved: {CONVICTION_OUT}")
    print("=== COT Scan complete ===\n")


if __name__ == "__main__":
    main()
