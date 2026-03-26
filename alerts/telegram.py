"""
alerts/telegram.py
Build and send Telegram alert messages.

Message format:
  🟢 BUY EURUSD

  Technical Summary
  H1: Strong Buy  |  H4: Buy  |  D1: Buy

  Session: London, New York

  📰 Latest Analysis:
  "EUR resilient despite weak PMI as ECB holds firm" — DailyFX

  ⚠️ Upcoming High-Impact Events (UTC):
  EUR — CPI Flash  10:00
  USD — NFP        13:30

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
    pair: str,
    direction: str,
    h1_label: str,
    h4_label: str,
    d1_label: str,
    session_names: list[str],
    headline: tuple | None = None,
    events: list[dict] = None,
) -> str:
    emoji   = DIRECTION_EMOJI[direction]
    action  = DIRECTION_WORD[direction]
    display = pair.replace("/", "")
    session = ", ".join(session_names) if session_names else "Off-session"
    events  = events or []

    lines = [
        f"{emoji} <b>{action} {display}</b>",
        "",
        "<b>Technical Summary</b>",
        f"H1: {h1_label}  |  H4: {h4_label}  |  D1: {d1_label}",
        "",
        f"<b>Session:</b> {session}",
    ]

    if headline:
        source, title = headline
        lines += [
            "",
            "📰 <b>Latest Analysis:</b>",
            f'<i>"{title}"</i> — {source}',
        ]
    else:
        lines += ["", "📰 <i>No recent analysis found.</i>"]

    if events:
        lines += ["", "⚠️ <b>Upcoming High-Impact Events (UTC):</b>"]
        for ev in events:
            lines.append(f"{ev['currency']} — {ev['event']}  {ev['time_utc']}")
    else:
        lines += ["", "✅ <i>No high-impact events in next 12h.</i>"]

    lines += ["", f'📊 <a href="{DASHBOARD_URL}">Dashboard</a>']

    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [TG] Missing bot token or chat ID — skipping send.")
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
        print(f"  [TG] Failed to send: {e}")
        return False
