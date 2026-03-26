# FX Technical Dashboard

A fully automated forex technical analysis system built on GitHub Actions, with Telegram alerts, a live GitHub Pages dashboard, and real-time news context.

## Philosophy

**D1 = Bias. H4 = Confirmation. H1 = Execution.**

Alerts only fire when all relevant timeframes agree. The system tells you *which pairs are in play and in which direction* — you find the entry on your chart.

## How It Works

Three scheduled scans run automatically:

| Job | Schedule | Role |
|---|---|---|
| D1 Scan | Daily 00:10 UTC | Sets the bias. Scores all pairs. No alerts. |
| H4 Scan | Every 4 hours | Fires if D1 + H4 agree in direction. |
| H1 Scan | Every hour | Fires if D1 + H4 + H1 all agree in direction. |

H1 and H4 share a single 4-hour cooldown per pair — if either fires, both are blocked.

## Instruments

**Forex (9 pairs):**
EURUSD · GBPUSD · USDJPY · USDCHF · AUDUSD · USDCAD · NZDUSD · EURJPY · GBPJPY

**Commodities:**
XAUUSD (Gold)

## Scoring Engine

6 independent signals per timeframe, each voting +1 (bull) / -1 (bear):

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

- **ADX < 20** — no trend present, not worth trading
- **ATR contracted** — current ATR < 70% of 14-bar average, low participation

## Telegram Alert Format

```
🟢 BUY AUDUSD

D1: Buy  |  H4: Strong Buy  |  H1: Buy

ADX: 26.3  |  ATR: Normal
Session: New York

📰 "AUD holds gains as risk appetite recovers" — DailyFX
✅ No high-impact events in next 12h.

📊 Dashboard → https://...
```

## Dashboard

Live GitHub Pages dashboard showing:
- **Session badges** — which sessions are currently active
- **Currency Strength (D1)** — 8 currencies ranked strongest to weakest
- **Technical Scores** — all 10 instruments × H1/H4/D1 with pill + score
- **AI Prompt** — copy-ready prompt for each recent alert to paste into any AI

## Setup

### 1. Create a GitHub repo

Name it `fx_technical` (or anything — update `DASHBOARD_URL` accordingly).

### 2. Upload all files

Use GitHub Desktop to push the full project including the `.github/workflows/` folder.

### 3. Add Repository Secrets

**Settings → Secrets and variables → Actions → New repository secret:**

| Secret | Value |
|---|---|
| `TWELVEDATA_API_KEY` | Twelvedata free tier API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `DASHBOARD_URL` | `https://YOUR_USERNAME.github.io/fx_technical/` |

### 4. Enable GitHub Actions write permissions

**Settings → Actions → General → Workflow permissions → Read and write permissions ✓**

### 5. Enable GitHub Pages

**Settings → Pages → Source → GitHub Actions**

### 6. Make repo public

GitHub Pages requires a public repo on the free plan.
**Settings → Danger Zone → Change visibility → Make public**

### 7. Seed the data with manual runs

Trigger in this order:
1. **Actions → D1 Scan + Deploy Dashboard → Run workflow**
2. **Actions → H4 Scan → Run workflow**
3. **Actions → H1 Scan → Run workflow**

From this point the cron schedule takes over automatically.

## File Structure

```
├── config/
│   └── pairs.py              # Instruments, sessions, display names
├── scanner/
│   ├── fetch.py              # Twelvedata OHLCV fetcher (rate-limited)
│   ├── score.py              # 6-signal scoring engine + ADX/ATR filters
│   ├── csm.py                # D1 currency strength calculation
│   ├── cooldown.py           # 4-hour alert cooldown guard
│   ├── scan_h1.py            # H1 scan runner
│   ├── scan_h4.py            # H4 scan runner
│   └── scan_d1.py            # D1 scan runner
├── alerts/
│   ├── news.py               # RSS headlines + ForexFactory calendar
│   ├── telegram.py           # Message builder + Telegram sender
│   └── log.py                # alerts.json writer (dashboard AI prompts)
├── dashboard/
│   └── index.html            # GitHub Pages dashboard
├── data/                     # Auto-committed JSON outputs
│   ├── h1_scores.json
│   ├── h4_scores.json
│   ├── d1_scores.json
│   ├── csm.json
│   └── alerts.json
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
| Twelvedata API | Free (800 req/day limit — ~330 used) |
| GitHub Actions | Free |
| GitHub Pages | Free |
| RSS + ForexFactory | Free |
| Anthropic API | Not required |

**Total running cost: $0/month**
