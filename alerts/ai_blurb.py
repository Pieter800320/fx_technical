"""
alerts/ai_blurb.py
Generates a concise expert AI opinion on a trading opportunity.

Uses the Anthropic API with web_search tool enabled so the model
can pull current fundamental and technical context.

Fires only when a Telegram alert is triggered (not every scan).
"""

import os
import json
import requests

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are a professional forex analyst providing concise trade opinions.
You will be given a currency pair, the current technical score summary, and the timeframe.
Use web search to find the latest relevant news, central bank commentary, macro data,
and technical context for this pair.

Respond with a single paragraph of 2-4 sentences maximum. Be direct, factual, and current.
Focus on: key macro driver right now, any recent news, and whether technicals support the direction.
Do NOT use bullet points. Do NOT repeat the technical score. Write like a professional analyst's brief note.
"""


def generate_blurb(pair: str, direction: str, h1_label: str, h4_label: str, d1_label: str) -> str:
    """
    Generate an AI opinion blurb for a triggered alert.

    pair: "EUR/USD"
    direction: "bull" | "bear"
    h1_label, h4_label, d1_label: score labels e.g. "Strong Buy"

    Returns: opinion string, or fallback message on error.
    """
    if not ANTHROPIC_API_KEY:
        return "AI opinion unavailable (no API key configured)."

    direction_str = "bullish (BUY)" if direction == "bull" else "bearish (SELL)"

    user_prompt = (
        f"Pair: {pair}\n"
        f"Signal direction: {direction_str}\n"
        f"Technical scores — H1: {h1_label} | H4: {h4_label} | D1: {d1_label}\n\n"
        f"Search for the latest news and fundamental context for {pair}. "
        f"Give me a brief 2-4 sentence expert opinion on whether this {direction_str} "
        f"setup is supported by current fundamentals and market conditions."
    )

    payload = {
        "model": "claude-opus-4-5",
        "max_tokens": 300,
        "system": SYSTEM_PROMPT,
        "tools": [
            {
                "type": "web_search_20250305",
                "name": "web_search"
            }
        ],
        "messages": [
            {"role": "user", "content": user_prompt}
        ]
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "web-search-2025-03-05"
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        data = resp.json()

        # Extract text blocks from response
        text_parts = [
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        blurb = " ".join(text_parts).strip()
        return blurb if blurb else "No AI opinion generated."

    except Exception as e:
        print(f"  [AI] Error generating blurb for {pair}: {e}")
        return "AI opinion temporarily unavailable."
