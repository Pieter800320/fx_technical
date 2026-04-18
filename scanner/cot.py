# scanner/cot.py — CFTC COT downloader and parser
#
# Downloads Legacy Futures-Only and Disaggregated Futures-Only reports.
# Extracts 52+ weeks of net speculator positioning for G10 currencies.
# Returns structured data for conviction.py to score.
#
# CFTC publishes every Friday ~15:30 EST. scan_cot.py runs Saturday 14:00 UTC.

import io
import csv
import zipfile
import datetime
import urllib.request
import urllib.error
import ssl

# ── Market name keywords for each currency ───────────────────────────────────
# CFTC uses full descriptive names. Match by keyword to be format-change robust.
CURRENCY_KEYWORDS = {
    "EUR": ["EURO FX", "EURO"],
    "GBP": ["BRITISH POUND", "POUND STERLING"],
    "JPY": ["JAPANESE YEN"],
    "CHF": ["SWISS FRANC"],
    "AUD": ["AUSTRALIAN DOLLAR"],
    "CAD": ["CANADIAN DOLLAR"],
    "NZD": ["NZ DOLLAR", "NEW ZEALAND DOLLAR"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FXDashboard/1.0; +https://github.com)",
    "Accept": "*/*",
}


# ── Download helpers ──────────────────────────────────────────────────────────

def _fetch_zip(url: str) -> bytes | None:
    """Download a ZIP file from CFTC. Returns bytes or None on failure."""
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return r.read()
    except Exception as e:
        print(f"  [COT] Failed to fetch {url}: {e}")
        return None


def _zip_to_rows(data: bytes) -> list[dict]:
    """
    Extract first CSV/TXT file from a ZIP and return list of row dicts.
    CFTC _txt_ ZIP files contain a single comma-delimited .txt file.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        # Find the data file — CFTC txt ZIPs contain a single .txt file
        matches = [n for n in names if n.lower().endswith((".txt", ".csv"))]
        if not matches:
            print(f"  [COT] No .txt/.csv found in ZIP. Contents: {names}")
            return []
        csv_name = matches[0]
        with z.open(csv_name) as f:
            # CFTC files are comma-delimited despite .txt extension
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"))
            rows = list(reader)
            # Strip whitespace from all keys (CFTC headers sometimes have spaces)
            cleaned = []
            for row in rows:
                cleaned.append({k.strip(): v.strip() if isinstance(v, str) else v
                                 for k, v in row.items()})
            return cleaned
    except zipfile.BadZipFile:
        print(f"  [COT] Invalid ZIP (server may have returned HTML/403 page)")
        return []
    except Exception as e:
        print(f"  [COT] ZIP parse error: {type(e).__name__}: {e}")
        return []


def _fetch_cot_rows(report: str, year: int) -> list[dict]:
    """
    Fetch COT rows for a given report type and year.
    Uses _txt_ ZIP files which contain comma-delimited text (not Excel binary).
    _xls_ ZIP files contain Excel .xls format which cannot be read as CSV.
    Tries current year then previous year for a full 52-week window.
    """
    tag = "fut_fin_txt" if report == "legacy" else "fut_disagg_txt"
    urls = [
        f"https://www.cftc.gov/files/dea/history/{tag}_{year}.zip",
        f"https://www.cftc.gov/files/dea/history/{tag}_{year - 1}.zip",
    ]
    rows = []
    for url in urls:
        data = _fetch_zip(url)
        if not data:
            continue
        year_label = url.split("_")[-1].split(".")[0]
        batch = _zip_to_rows(data)
        if batch:
            rows.extend(batch)
            print(f"  [COT] {report} {year_label}: {len(batch)} rows")
        else:
            print(f"  [COT] {report} {year_label}: parsed 0 rows (check ZIP contents)")
    return rows


# ── Currency matching ─────────────────────────────────────────────────────────

def _match_currency(market_name: str) -> str | None:
    name_upper = market_name.upper()
    for ccy, keywords in CURRENCY_KEYWORDS.items():
        if any(kw in name_upper for kw in keywords):
            return ccy
    return None


def _parse_date(date_str: str) -> datetime.date | None:
    """Parse CFTC date formats: YYMMDD or YYYY-MM-DD."""
    s = date_str.strip()
    for fmt in ("%y%m%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Main parsing functions ────────────────────────────────────────────────────

def _get(row: dict, *keys: str) -> str:
    """Get a value from a row, tolerating whitespace in key names."""
    for key in keys:
        if key in row:
            return row[key]
        # Try stripped version
        for k, v in row.items():
            if k.strip() == key:
                return v
    return "0"


def parse_legacy(rows: list[dict]) -> dict[str, list[dict]]:
    """
    Parse Legacy COT rows.
    Returns: {currency: [{date, net_noncomm, open_interest}, ...]}
    sorted oldest-first, last 60 weeks.
    """
    by_currency: dict[str, list] = {c: [] for c in CURRENCY_KEYWORDS}

    for row in rows:
        market = row.get("Market_and_Exchange_Names", "").strip()
        ccy = _match_currency(market)
        if not ccy:
            continue
        date = _parse_date(row.get("As_of_Date_in_Form_YYMMDD", ""))
        if not date:
            continue
        try:
            longs  = int(_get(row, "NonComm_Positions_Long_All").replace(",", ""))
            shorts = int(_get(row, "NonComm_Positions_Short_All").replace(",", ""))
            oi     = int(_get(row, "Open_Interest_All").replace(",", ""))
        except (ValueError, TypeError):
            continue
        by_currency[ccy].append({
            "date": date,
            "net_noncomm": longs - shorts,
            "open_interest": oi,
        })

    # Deduplicate by date, sort, keep last 60 weeks
    result = {}
    for ccy, records in by_currency.items():
        seen = {}
        for r in records:
            seen[r["date"]] = r
        sorted_recs = sorted(seen.values(), key=lambda x: x["date"])
        result[ccy] = sorted_recs[-60:]

    return result


def parse_disaggregated(rows: list[dict]) -> dict[str, list[dict]]:
    """
    Parse Disaggregated COT rows.
    Returns: {currency: [{date, net_asset_mgr, net_leveraged}, ...]}
    """
    by_currency: dict[str, list] = {c: [] for c in CURRENCY_KEYWORDS}

    for row in rows:
        market = row.get("Market_and_Exchange_Names", "").strip()
        ccy = _match_currency(market)
        if not ccy:
            continue
        date = _parse_date(row.get("As_of_Date_in_Form_YYMMDD", ""))
        if not date:
            continue
        try:
            am_long  = int(_get(row, "Asset_Mgr_Positions_Long_All").replace(",", ""))
            am_short = int(_get(row, "Asset_Mgr_Positions_Short_All").replace(",", ""))
            lf_long  = int(_get(row, "Lev_Money_Positions_Long_All").replace(",", ""))
            lf_short = int(_get(row, "Lev_Money_Positions_Short_All").replace(",", ""))
        except (ValueError, TypeError):
            continue
        by_currency[ccy].append({
            "date": date,
            "net_asset_mgr":  am_long - am_short,
            "net_leveraged":  lf_long - lf_short,
        })

    result = {}
    for ccy, records in by_currency.items():
        seen = {}
        for r in records:
            seen[r["date"]] = r
        sorted_recs = sorted(seen.values(), key=lambda x: x["date"])
        result[ccy] = sorted_recs[-60:]

    return result


# ── Percentile with hysteresis ────────────────────────────────────────────────

def _percentile_52w(series: list[float], current: float, lookback: int = 52) -> float:
    """
    52-week percentile rank of current value within the series.
    Uses last `lookback` values (excluding current).
    Returns 0.0-100.0.
    """
    window = series[-lookback:] if len(series) >= lookback else series
    if not window:
        return 50.0
    below = sum(1 for v in window if v < current)
    equal = sum(1 for v in window if v == current)
    return round((below + 0.5 * equal) / len(window) * 100, 1)


# ── Master fetch function ─────────────────────────────────────────────────────

def fetch_cot_data(year: int | None = None) -> dict:
    """
    Download and parse both Legacy and Disaggregated COT reports.
    Returns structured dict ready for conviction.py.
    """
    if year is None:
        year = datetime.datetime.utcnow().year

    print(f"  [COT] Fetching Legacy report...")
    leg_rows  = _fetch_cot_rows("legacy", year)
    # Diagnostic: show first 3 market names and all column headers
    if leg_rows:
        print(f"  [COT] Legacy columns sample: {list(leg_rows[0].keys())[:6]}")
        markets = list(dict.fromkeys(r.get("Market_and_Exchange_Names","") for r in leg_rows[:50]))
        print(f"  [COT] First market names: {markets[:8]}")
    print(f"  [COT] Fetching Disaggregated report...")
    dis_rows  = _fetch_cot_rows("disagg", year)
    if dis_rows:
        print(f"  [COT] Disagg columns sample: {list(dis_rows[0].keys())[:6]}")

    legacy = parse_legacy(leg_rows)
    disagg = parse_disaggregated(dis_rows)

    # Find latest date across all currencies
    latest_date = None
    for ccy, records in legacy.items():
        if records:
            d = records[-1]["date"]
            if latest_date is None or d > latest_date:
                latest_date = d

    # Compute percentiles and OI momentum for each currency
    output = {
        "cot_date":  str(latest_date) if latest_date else "unknown",
        "cot_stale": False,
        "currencies": {},
    }

    for ccy in CURRENCY_KEYWORDS:
        leg_recs  = legacy.get(ccy, [])
        dis_recs  = disagg.get(ccy, [])

        if not leg_recs:
            output["currencies"][ccy] = {
                "available": False,
                "net_noncomm": None, "noncomm_pct": None,
                "oi_current": None,  "oi_4w_ago": None,
                "net_asset_mgr": None, "am_pct": None,
                "net_leveraged": None, "lf_pct": None,
            }
            continue

        # Legacy: net non-commercial
        net_series = [r["net_noncomm"] for r in leg_recs]
        oi_series  = [r["open_interest"] for r in leg_recs]
        net_current = net_series[-1]
        oi_current  = oi_series[-1]
        oi_4w_ago   = oi_series[-5] if len(oi_series) >= 5 else oi_series[0]
        noncomm_pct = _percentile_52w(net_series[:-1], net_current)  # exclude current from window

        # Disaggregated
        am_pct = lf_pct = None
        net_am = net_lf = None
        if dis_recs:
            am_series = [r["net_asset_mgr"] for r in dis_recs]
            lf_series = [r["net_leveraged"]  for r in dis_recs]
            net_am = am_series[-1]
            net_lf = lf_series[-1]
            am_pct = _percentile_52w(am_series[:-1], net_am)
            lf_pct = _percentile_52w(lf_series[:-1], net_lf)

        output["currencies"][ccy] = {
            "available":    True,
            "net_noncomm":  net_current,
            "noncomm_pct":  noncomm_pct,
            "oi_current":   oi_current,
            "oi_4w_ago":    oi_4w_ago,
            "net_asset_mgr": net_am,
            "am_pct":        am_pct,
            "net_leveraged": net_lf,
            "lf_pct":        lf_pct,
        }

    # Stale check: if latest COT date is > 9 days old
    if latest_date:
        days_old = (datetime.datetime.utcnow().date() - latest_date).days
        output["cot_stale"] = days_old > 9

    return output
