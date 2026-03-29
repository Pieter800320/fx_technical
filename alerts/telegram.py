"""
alerts/telegram.py
Build and send Telegram alert messages.

Format:
  🟢 BUY EURUSD

  D1: Strong Buy  |  H4: Buy  |  H1: Buy

  ADX: 28.4  |  ATR: Normal
  Session: London

  📰 "EUR supported by hawkish ECB tone" — DailyFX
  ⚠️ USD — NFP  13:30 UTC

  📊 Dashboard → https://...
"""

import os
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL      = os.environ.get("DASHBOARD_URL", "https://yourusername.github.io/fx_technical/")

DIRECTION_EMOJI = {"bull": "🟢", "bear": "🔴"}
DIRECTION_WORD  = {"bull": "BUY", "bear": "SELL"}


def build_message(
    pair,
    direction,
    h1_label,
    h4_label,
    d1_label,
    session_names,
    adx_val=None,
    atr_ok=True,
    headline=None,
    events=None,
    levels=None,
):
    emoji   = DIRECTION_EMOJI[direction]
    action  = DIRECTION_WORD[direction]
    display = pair.replace("/", "")
    session = ", ".join(session_names) if session_names else "Off-session"
    events  = events or []

    # ATR status
    atr_status = "Normal" if atr_ok else "Contracted"
    adx_str    = f"{adx_val:.1f}" if adx_val is not None else "N/A"

    lines = [
        f"{emoji} <b>{action} {display}</b>",
        "",
        f"D1: {d1_label}  |  H4: {h4_label}  |  H1: {h1_label}",
        "",
        f"ADX: {adx_str}  |  ATR: {atr_status}",
        f"Session: {session}",
    ]

    # RSS headline
    if headline:
        source, title = headline
        lines += ["", f'📰 <i>"{title}"</i> — {source}']
    else:
        lines += ["", "📰 <i>No recent analysis found.</i>"]

    # Calendar events
    if events:
        lines.append("")
        for ev in events:
            lines.append(f"⚠️ {ev['currency']} — {ev['event']}  {ev['time_utc']} UTC")
    else:
        lines += ["", "✅ <i>No high-impact events in next 12h.</i>"]

    lines += ["", f'📊 <a href="{DASHBOARD_URL}">Dashboard</a>']
    return "\n".join(lines)


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [TG] Missing credentials — skipping.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print("  [TG] Alert sent.")
        return True
    except Exception as e:
        print(f"  [TG] Failed: {e}")
        return False
