# scanner/cot.py — CFTC COT downloader and parser
#
# Uses the CFTC Traders in Financial Futures (TFF) report: fut_fin_txt_YYYY.zip
# This is the correct file for currency futures (EUR, GBP, JPY, CHF, AUD, CAD, NZD).
#
# TFF categories (replaces legacy "Non-Commercial"):
#   Lev_Money  = Leveraged Funds (hedge funds, CTAs) — speculative positioning proxy
#   Asset_Mgr  = Asset Managers (pension funds, institutions) — structural positioning
#
# We use Lev_Money as the speculative signal (COT inputs 1 & 2) and
# Asset_Mgr vs Lev_Money divergence as the disaggregated signal (COT input 3).
# Both come from the same fut_fin_txt file.

import io
import csv
import zipfile
import datetime
import urllib.request
import ssl

CURRENCY_KEYWORDS = {
    "EUR": ["EURO FX", "EURO CURRENCY", "EURO"],
    "GBP": ["BRITISH POUND", "POUND STERLING"],
    "JPY": ["JAPANESE YEN"],
    "CHF": ["SWISS FRANC"],
    "AUD": ["AUSTRALIAN DOLLAR"],
    "CAD": ["CANADIAN DOLLAR"],
    "NZD": ["NZ DOLLAR", "NEW ZEALAND DOLLAR"],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FXDashboard/1.0)", "Accept": "*/*"}


def _fetch_zip(url):
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return r.read()
    except Exception as e:
        print(f"  [COT] Failed to fetch {url}: {e}")
        return None


def _zip_to_rows(data):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        matches = [n for n in z.namelist() if n.lower().endswith((".txt", ".csv"))]
        if not matches:
            print(f"  [COT] No .txt/.csv in ZIP. Contents: {z.namelist()}")
            return []
        with z.open(matches[0]) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="latin-1"))
            return [{k.strip(): (v.strip() if isinstance(v, str) else v)
                     for k, v in row.items()} for row in reader]
    except zipfile.BadZipFile:
        print(f"  [COT] Invalid ZIP file")
        return []
    except Exception as e:
        print(f"  [COT] ZIP parse error: {type(e).__name__}: {e}")
        return []


def _fetch_tff_rows(year):
    """Fetch TFF rows for current and previous year to get 60 weeks of history."""
    rows = []
    for y in (year, year - 1):
        url = f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{y}.zip"
        data = _fetch_zip(url)
        if not data:
            continue
        batch = _zip_to_rows(data)
        if batch:
            rows.extend(batch)
            print(f"  [COT] TFF {y}: {len(batch)} rows")
        else:
            print(f"  [COT] TFF {y}: 0 rows parsed")
    return rows


def _match_currency(market_name):
    name_upper = market_name.upper()
    for ccy, keywords in CURRENCY_KEYWORDS.items():
        if any(kw in name_upper for kw in keywords):
            return ccy
    return None


def _parse_date(s):
    s = s.strip()
    if not s:
        return None
    for fmt in ("%y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _get_date(row):
    for key in ("As_of_Date_In_Form_YYMMDD", "As_of_Date_in_Form_YYMMDD",
                "Report_Date_as_YYYY-MM-DD"):
        val = row.get(key, "").strip()
        if val:
            d = _parse_date(val)
            if d:
                return d
    return None


def _int(row, *keys):
    """Case-insensitive integer extraction from row."""
    for key in keys:
        val = row.get(key, "")
        if not val:
            key_lower = key.lower()
            for k, v in row.items():
                if k.lower() == key_lower:
                    val = v
                    break
        if val:
            try:
                return int(str(val).replace(",", "").strip())
            except (ValueError, TypeError):
                pass
    return 0


def _percentile_52w(series, current, lookback=52):
    window = series[-lookback:] if len(series) >= lookback else series
    if not window:
        return 50.0
    below = sum(1 for v in window if v < current)
    equal = sum(1 for v in window if v == current)
    return round((below + 0.5 * equal) / len(window) * 100, 1)


def _parse_tff(rows):
    """Parse TFF rows into per-currency records with leveraged and asset manager nets."""
    by_currency = {c: [] for c in CURRENCY_KEYWORDS}

    for row in rows:
        market = row.get("Market_and_Exchange_Names", "").strip()
        ccy = _match_currency(market)
        if not ccy:
            continue
        date = _get_date(row)
        if not date:
            continue

        lev_long  = _int(row, "Lev_Money_Positions_Long_All")
        lev_short = _int(row, "Lev_Money_Positions_Short_All")
        am_long   = _int(row, "Asset_Mgr_Positions_Long_All")
        am_short  = _int(row, "Asset_Mgr_Positions_Short_All")
        oi        = _int(row, "Open_Interest_All")

        by_currency[ccy].append({
            "date":          date,
            "net_lev":       lev_long - lev_short,
            "net_am":        am_long  - am_short,
            "open_interest": oi,
        })

    result = {}
    for ccy, records in by_currency.items():
        seen = {}
        for r in records:
            seen[r["date"]] = r
        sorted_recs = sorted(seen.values(), key=lambda x: x["date"])
        result[ccy] = sorted_recs[-60:]
    return result


def fetch_cot_data(year=None):
    """Download and parse CFTC TFF data. Returns dict ready for conviction.py."""
    if year is None:
        year = datetime.datetime.utcnow().year

    print(f"  [COT] Fetching TFF (Leveraged + Asset Manager)...")
    rows = _fetch_tff_rows(year)

    if not rows:
        print(f"  [COT] No data fetched")
        return {"cot_date": "unknown", "cot_stale": True,
                "currencies": {c: {"available": False} for c in CURRENCY_KEYWORDS}}

    # Diagnostic: show currency contracts found
    markets = list(dict.fromkeys(r.get("Market_and_Exchange_Names","") for r in rows[:200]))
    currency_markets = [m for m in markets if _match_currency(m)]
    print(f"  [COT] Currency contracts: {currency_markets}")

    parsed = _parse_tff(rows)

    latest_date = None
    for records in parsed.values():
        if records:
            d = records[-1]["date"]
            if latest_date is None or d > latest_date:
                latest_date = d

    output = {"cot_date": str(latest_date) if latest_date else "unknown",
               "cot_stale": False, "currencies": {}}

    for ccy in CURRENCY_KEYWORDS:
        records = parsed.get(ccy, [])
        if not records:
            output["currencies"][ccy] = {
                "available": False, "net_noncomm": None, "noncomm_pct": None,
                "oi_current": None, "oi_4w_ago": None,
                "net_asset_mgr": None, "am_pct": None,
                "net_leveraged": None, "lf_pct": None,
            }
            continue

        lev_series = [r["net_lev"] for r in records]
        am_series  = [r["net_am"]  for r in records]
        oi_series  = [r["open_interest"] for r in records]
        net_lev    = lev_series[-1]
        net_am     = am_series[-1]
        lev_pct    = _percentile_52w(lev_series[:-1], net_lev)
        am_pct     = _percentile_52w(am_series[:-1],  net_am)

        output["currencies"][ccy] = {
            "available":     True,
            "net_noncomm":   net_lev,
            "noncomm_pct":   lev_pct,
            "oi_current":    oi_series[-1],
            "oi_4w_ago":     oi_series[-5] if len(oi_series) >= 5 else oi_series[0],
            "net_asset_mgr": net_am,
            "am_pct":        am_pct,
            "net_leveraged": net_lev,
            "lf_pct":        lev_pct,
        }

    if latest_date:
        output["cot_stale"] = (datetime.datetime.utcnow().date() - latest_date).days > 9

    return output
