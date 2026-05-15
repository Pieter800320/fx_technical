"""alerts/telegram.py — All Telegram notifications for Forex1212."""
import os, requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL      = os.environ.get("DASHBOARD_URL", "https://Pieter800320.github.io/fx_technical/")


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [TG] Missing credentials — skipped.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     message,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        resp.raise_for_status()
        print("  [TG] Sent.")
        return True
    except Exception as e:
        print(f"  [TG] Failed: {e}")
        return False


def build_message(*args, **kwargs) -> str:
    """Stub — kept for backward-compat. Returns empty string."""
    return ""


def send_level_alert(pair: str, direction: str, alert_price: float,
                     current_price: float) -> bool:
    """Price crossed a manually-set level."""
    display = pair.replace("/", "")
    arrow   = "↑" if direction == "above" else "↓"
    emoji   = "🟢" if direction == "above" else "🔴"
    dec     = 3 if "JPY" in pair else 5
    msg = "\n".join([
        f"{emoji} <b>Level Alert — {display}</b>",
        "",
        f"Price crossed <b>{arrow} {alert_price:.{dec}f}</b>",
        f"Current: <b>{current_price:.{dec}f}</b>",
        "",
        f'📊 <a href="{DASHBOARD_URL}">Dashboard</a>',
    ])
    return send_telegram(msg)


def send_sma_alert(pair: str, direction: str, d1_label: str, h4_label: str,
                   h1_label: str, edge: int = None, setup: int = None,
                   adx: float = None) -> bool:
    """Triple-TF SMA12 momentum alignment alert."""
    display  = pair.replace("/", "")
    emoji    = "🟢" if direction == "UP" else "🔴"
    arrow    = "▲" if direction == "UP" else "▼"

    lines = [
        f"{emoji} <b>SMA Alignment — {display}</b>",
        f"All 3 TFs pointing <b>{arrow} {direction}</b>",
        "",
        f"D1: {d1_label}  ·  H4: {h4_label}  ·  H1: {h1_label}",
    ]
    extras = []
    if setup is not None:
        extras.append(f"Setup {setup}%")
    if edge is not None:
        extras.append(f"Edge {edge}/10")
    if adx is not None:
        extras.append(f"ADX {adx:.1f}")
    if extras:
        lines.append("  ".join(extras))
    lines += ["", f'📊 <a href="{DASHBOARD_URL}">Dashboard</a>']
    return send_telegram("\n".join(lines))


def send_trade_alert(pair: str, event: str, direction: str,
                     price: float, entry: float,
                     sl: float = None, tp: float = None,
                     rr: float = None) -> bool:
    """
    Trade lifecycle alert.
    event: 'filled' | 'tp_hit' | 'sl_hit'
    """
    display = pair.replace("/", "")
    dec     = 3 if "JPY" in pair else 5
    dir_arrow = "▲ BUY" if direction == "BUY" else "▼ SELL"

    if event == "filled":
        emoji = "⚡"
        title = f"Order Filled — {display}"
        detail = f"Filled at <b>{price:.{dec}f}</b>"
    elif event == "tp_hit":
        emoji = "✅"
        title = f"Take Profit Hit — {display}"
        detail = f"TP reached at <b>{price:.{dec}f}</b>"
    elif event == "sl_hit":
        emoji = "❌"
        title = f"Stop Loss Hit — {display}"
        detail = f"SL triggered at <b>{price:.{dec}f}</b>"
    else:
        return False

    lines = [
        f"{emoji} <b>{title}</b>",
        "",
        f"Direction: <b>{dir_arrow}</b>",
        f"Entry: <b>{entry:.{dec}f}</b>",
        detail,
    ]
    if sl is not None:
        lines.append(f"SL: {sl:.{dec}f}")
    if tp is not None:
        lines.append(f"TP: {tp:.{dec}f}")
    if rr is not None:
        lines.append(f"R:R: {rr:.2f}R")
    lines += ["", f'📊 <a href="{DASHBOARD_URL}">Dashboard</a>']

    return send_telegram("\n".join(lines))



def _fmt(val, suffix="", none="—"):
    return f"{val}{suffix}" if val is not None else none

def _mom_str(mom, delta):
    if mom is None:
        return "—"
    s = str(mom)
    if delta is not None:
        s += f" {'↓' if delta < 0 else '↑' if delta > 0 else '→'}{abs(delta)}"
    return s

def _csm_warn(label, val):
    if val is None:
        return ""
    if val > 65:
        return f"⚠️ {label} elevated ({val:.0f})"
    if val < 35:
        return f"⚠️ {label} weak ({val:.0f})"
    return ""


def send_bb_band_alert(ev: dict) -> bool:
    """Message 1 — H4 wick touches upper or lower Bollinger Band."""
    band    = ev["band"]
    display = ev["display"]
    dec     = ev["dec"]
    q       = ev["quality"]

    arrow  = "🔼" if band == "upper" else "🔽"
    side   = "UPPER" if band == "upper" else "LOWER"
    emoji  = q["rating_emoji"]

    cw_base  = _csm_warn(ev["csm_labels"][0], ev["csm_base"])
    cw_quote = _csm_warn(ev["csm_labels"][1], ev["csm_quote"])
    csm_line = "  ".join(filter(None, [cw_base, cw_quote]))

    adx_str = f"{ev['adx_val']:.1f} {ev['adx_dir']}" if ev["adx_val"] is not None else "—"

    lines = [
        f"{arrow} <b>{display} — {side} BB TOUCH</b>",
        f"H4 close: <b>{ev['close']:.{dec}f}</b>   BB: {ev['upper']:.{dec}f} / {ev['lower']:.{dec}f}",
        "",
        f"Rating: {emoji} <b>{q['rating']}</b>  [{q['score']}/10  T2:{q['tier2']} T3:{q['tier3']}]",
        "",
        f"H4 MOM  {_mom_str(ev['h4_mom'], ev['h4_delta'])}    D1 MOM  {_mom_str(ev['d1_mom'], ev['d1_delta'])}",
        f"H1 MOM  {_mom_str(ev['h1_mom'], ev['h1_delta'])}    W1 MOM  {_fmt(ev['w1_mom'])}",
        f"Setup   {_fmt(ev['setup_pct'], '%')}     Edge    {_fmt(ev['edge'], '/10')}",
        f"ADX     {adx_str}     Regime  {ev['regime']} ({ev['reg_conf']})",
        f"Ext: {'✅' if ev['extended'] else '—'}   Conflict: {'✅' if ev['conflict'] else '—'}",
    ]
    if csm_line:
        lines.append(csm_line)
    lines += ["", f'📊 <a href="{DASHBOARD_URL}">{display} H4</a>']

    return send_telegram("\n".join(lines))


def send_bb_midline_alert(ev: dict) -> bool:
    """Message 2 — H4 wick touches BB 20-SMA midline after a band touch."""
    band    = ev["band"]
    display = ev["display"]
    dec     = ev["dec"]

    origin = "upper" if band == "upper" else "lower"

    h4_unwound = ev["h4_mom"] is not None and 45 <= ev["h4_mom"] <= 55
    d1_unwound = ev["d1_mom"] is not None and 45 <= ev["d1_mom"] <= 55
    if h4_unwound and d1_unwound:
        verdict = "Momentum fully unwound. Trade complete."
    elif h4_unwound:
        verdict = "H4 neutral. D1 still running — watch for continuation."
    else:
        verdict = "Momentum still turning. Potential continuation through midline."

    lines = [
        f"⚪ <b>{display} — MIDLINE ({ev['mid']:.{dec}f})</b>",
        f"From {origin} BB touch · +{ev['elapsed']}",
        "",
        f"H4 MOM  {_mom_str(ev['h4_mom'], ev['h4_delta'])}    D1 MOM  {_mom_str(ev['d1_mom'], ev['d1_delta'])}",
        f"Setup   {_fmt(ev['setup_pct'], '%')}",
        "",
        verdict,
        "",
        f'📊 <a href="{DASHBOARD_URL}">{display} H4</a>',
    ]
    return send_telegram("\n".join(lines))

def send_time_alert(pair: str, label: str = "", alert_time: int = 0,
                    tf: str = "") -> bool:
    """Vertical time line alert — fires when UTC time passes the marker."""
    display = pair.replace("/", "") if pair else "—"
    import datetime as _dt
    try:
        t = _dt.datetime.utcfromtimestamp(alert_time)
        time_str = t.strftime("%H:%M UTC")
        date_str = t.strftime("%d %b")
    except Exception:
        time_str = "—"
        date_str = ""

    lines = [
        f"🕐 <b>Time Alert — {display}</b>",
        "",
        f"Time reached: <b>{time_str}</b>",
    ]
    if date_str:
        lines.append(f"Date: {date_str}")
    if label:
        lines.append(f"Note: <b>{label}</b>")
    if tf:
        lines.append(f"TF: {tf}")
    lines += ["", f'📊 <a href="{DASHBOARD_URL}">Dashboard</a>']
    return send_telegram("\n".join(lines))
