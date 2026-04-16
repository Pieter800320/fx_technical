"""alerts/telegram.py — Level alert notifications only.
build_message is kept as a no-op stub so existing scan imports don't break.
"""
import os, requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL      = os.environ.get("DASHBOARD_URL", "https://Pieter800320.github.io/fx_technical/")


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [TG] Missing credentials.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        resp.raise_for_status()
        print("  [TG] Sent.")
        return True
    except Exception as e:
        print(f"  [TG] Failed: {e}")
        return False


def build_message(*args, **kwargs) -> str:
    """Stub — signal Telegram messages removed. Returns empty string."""
    return ""


def send_level_alert(pair: str, direction: str, alert_price: float, current_price: float) -> bool:
    display = pair.replace("/", "")
    arrow   = "↑" if direction == "above" else "↓"
    emoji   = "🟢" if direction == "above" else "🔴"
    dec     = 2 if "JPY" in pair else 5
    lines = [
        f"{emoji} <b>Level Alert — {display}</b>",
        "",
        f"Price crossed <b>{arrow} {alert_price:.{dec}f}</b>",
        f"Current: <b>{current_price:.{dec}f}</b>",
        "",
        f'📊 <a href="{DASHBOARD_URL}">Dashboard</a>',
    ]
    return send_telegram("\n".join(lines))
