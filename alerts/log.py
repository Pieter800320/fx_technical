import json, os, datetime

ALERTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "alerts.json")
MAX_ALERTS  = 100


def log_alert(pair, direction, h1_label, h4_label, d1_label,
              blurb, levels=None, extended=None, regime=None,
              adx_val=None, atr_ok=True, conflict=False, structure=None):
    try:
        with open(ALERTS_PATH) as f:
            data = json.load(f)
    except:
        data = {"alerts": []}

    record = {
        "pair":              pair,
        "direction":         direction,
        "h1_label":          h1_label,
        "h4_label":          h4_label,
        "d1_label":          d1_label,
        "blurb":             blurb,
        "levels":            levels or {},
        "extended":          extended or {},
        "regime":            regime.get("regime", "Unknown") if regime else "Unknown",
        "regime_confidence": regime.get("confidence", "") if regime else "",
        "adx":               round(adx_val, 1) if adx_val else None,
        "atr_ok":            atr_ok,
        "conflict":          conflict,
        "structure":         structure or {},
        "timestamp":         datetime.datetime.utcnow().isoformat(),
    }

    data["alerts"].append(record)
    data["alerts"] = data["alerts"][-MAX_ALERTS:]
    os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)

    with open(ALERTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
