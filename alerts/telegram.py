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
