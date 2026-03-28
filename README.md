# Forex1212

A fully automated forex technical analysis system. Telegram alerts fire only when D1, H4 and H1 all agree — the system tells you *which pairs are in play and in which direction*. You find the entry on your chart.

## Philosophy

**D1 = Bias. H4 = Confirmation. H1 = Execution.**

No alert fires unless all relevant timeframes agree. Filters eliminate ranging and low-participation markets entirely.

## Live Dashboard

**https://Pieter800320.github.io/fx_technical/**

Features:
- Session badges (active market hours)
- Currency Strength meter with per-pair breakdown (tap any currency)
- Market Brief button — compiles everything into one AI prompt
- Technical Scores table — tap any pill to see the 6-signal breakdown + ADX/ATR
- Signals & Headlines — latest alert per pair with RSS headline and copy-to-AI prompt

## How It Works

Three scheduled scans run automatically via GitHub Actions:

| Job | Schedule | Role |
|---|---|---|
| D1 Scan | Daily 00:10 UTC | Sets the bias. Scores all pairs. No alerts. Computes currency strength. |
| H4 Scan | Every 4 hours | Fires if D1 + H4 agree in direction. |
| H1 Scan | Every hour | Fires if D1 + H4 + H1 all agree in direction. |

H1 and H4 share a single 4-hour cooldown per pair. No alerts fire on weekends (Friday 22:00 – Sunday 22:00 UTC).

## Instruments

**Forex (9 pairs):**
EURUSD · GBPUSD · USDJPY · USDCHF · AUDUSD · USDCAD · NZDUSD · EURJPY · GBPJPY

**Commodities:**
XAUUSD (Gold)

## Scoring Engine

6 independent signals per timeframe — each votes +1 (bull) / -1 (bear):

| Signal | Measures | Logic |
|---|---|---|
| EMA200 | Long-term bias | Price above = bull |
| EMA50 | Medium-term bias | Price above = bull |
| RSI vs 50 | Momentum direction | RSI > 50 = bull |
| MACD line vs signal | Momentum confirmation | MACD line above signal = bull |
| DMI+ vs DMI- | Directional pressure | DMI+ > DMI- = bull |
| Structure | Swing behaviour (H4/D1 only) | HH+HL = bull, LH+LL = bear |

**Score → Label:**

| Score | Label |
|---|---|
| +5 / +6 | Strong Buy |
| +3 / +4 | Buy |
| -2 to +2 | Neutral |
| -3 / -4 | Sell |
| -5 / -6 | Strong Sell |

## Hard Filters

Two filters suppress alerts regardless of score:

| Filter | Logic |
|---|---|
| ADX < 20 | No trend present — market is ranging |
| ATR contracted | Current ATR < 70% of 14-bar average — low participation |

## Alert Logic

An alert fires only when ALL of the following are true:

1. Score reaches Buy/Strong Buy or Sell/Strong Sell
2. D1 agrees with direction (bias gate)
3. H4 agrees with direction (confirmation gate) — H1 alerts only
4. ADX and ATR filters pass
5. Pair is in its relevant trading session
6. 4-hour cooldown has cleared
7. Market is open (not weekend)

## Telegram Alert Format

```
🟢 BUY EURUSD

D1: Buy  |  H4: Strong Buy  |  H1: Buy

ADX: 26.3  |  ATR: Normal
Session: London, New York

📰 "EUR supported by hawkish ECB tone" — DailyFX
✅ No high-impact events in next 12h.

📊 Dashboard → https://...
```

## Currency Strength Model

ATR-adjusted, multi-timeframe weighted model using 7 major pairs.

**Method:**
- For each pair: compute % return over 14 bars on D1 and H4
- Divide by ATR(14) to normalise for volatility
- Weight: D1 × 0.7 + H4 × 0.3
- Base currency adds the score; quote currency subtracts it
- Normalize all 8 currencies to 0–100

**Reading the pair breakdown dropdown:**
- The number shown is the ATR-adjusted contribution of that pair to the currency's score
- Positive = the pair is supporting the currency's strength ranking
- Negative = the pair is contesting it
- Larger absolute values = stronger driver

**Crosses included in breakdown:**
- EUR: EURUSD + EURJPY
- GBP: GBPUSD + GBPJPY
- JPY: USDJPY + EURJPY + GBPJPY

## News Context

Each alert includes:
- Latest relevant RSS headline (DailyFX, MarketPulse, FXStreet)
- Upcoming high-impact ForexFactory events for the pair's currencies (next 12h)

## AI Integration

**Per-alert prompt:** Tap "Copy AI Prompt" on any card in the Signals & Headlines section. Pastes a structured prompt into your clipboard ready for any AI — includes pair, direction, TF scores, news headline, and asks for entry/SL/TP guidance.

**Market Brief:** Tap "Market Brief / Copy AI Prompt" above the signal table. Compiles currency strength rankings + all directional scores + upcoming events into one prompt asking for a 100-word global macro narrative.

## Setup

### 1. Create a GitHub repo and upload all files via GitHub Desktop

### 2. Add Repository Secrets

**Settings → Secrets and variables → Actions → New repository secret:**

| Secret | Value |
|--------|-------|
| `TWELVEDATA_API_KEY` | Twelvedata free tier API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `DASHBOARD_URL` | `https://YOUR_USERNAME.github.io/fx_technical/` |

### 3. Enable GitHub Actions write permissions
**Settings → Actions → General → Workflow permissions → Read and write permissions ✓**

### 4. Enable GitHub Pages
**Settings → Pages → Source → GitHub Actions**

### 5. Make repo public
**Settings → Danger Zone → Change visibility → Make public**

### 6. Seed the data with manual runs (in this order)
1. Actions → D1 Scan + Deploy Dashboard → Run workflow
2. Actions → H4 Scan → Run workflow
3. Actions → H1 Scan → Run workflow

## File Structure

```
├── config/
│   └── pairs.py              # Instruments, sessions, display names
├── scanner/
│   ├── fetch.py              # Twelvedata OHLCV fetcher
│   ├── score.py              # 6-signal scoring engine + ADX/ATR filters
│   ├── csm.py                # ATR-adjusted currency strength model
│   ├── levels.py             # Swing high/low S/R level detection
│   ├── cooldown.py           # 4-hour alert cooldown guard
│   ├── scan_h1.py            # H1 scan runner
│   ├── scan_h4.py            # H4 scan runner
│   └── scan_d1.py            # D1 scan runner
├── alerts/
│   ├── news.py               # RSS headlines + ForexFactory calendar
│   ├── telegram.py           # Message builder + Telegram sender
│   └── log.py                # alerts.json writer (Signals & Headlines)
├── dashboard/
│   └── index.html            # GitHub Pages dashboard (Forex1212)
├── data/                     # Auto-committed JSON outputs
├── state/
│   └── cooldown.json         # Alert cooldown state
├── .github/workflows/
│   ├── scan_h1.yml
│   ├── scan_h4.yml
│   └── scan_d1.yml
└── requirements.txt
```

## Cost

| Service | Cost |
|---|---|
| Twelvedata API | Free (800 req/day limit — ~400 used) |
| GitHub Actions | Free |
| GitHub Pages | Free |
| RSS + ForexFactory | Free |
| Anthropic API | Not required |

**Total running cost: $0/month**
