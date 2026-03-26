# FX Technical Dashboard

Automated forex technical analysis system with GitHub Actions scheduling, Telegram alerts, AI-generated opinions, and a GitHub Pages dashboard.

## Architecture

```
scan_h1.py  → runs hourly    → h1_scores.json + alert if triggered
scan_h4.py  → runs 4-hourly  → h4_scores.json + alert if triggered
scan_d1.py  → runs daily     → d1_scores.json + csm.json
                             + deploys dashboard to GitHub Pages
```

**Alert trigger:** H1 or H4 score reaches Buy / Strong Buy / Sell / Strong Sell.  
**H4 override:** If H4 and H1 conflict in direction, H1 alert is suppressed.  
**Cooldown:** Same pair + direction won't re-fire within 4 hours.  
**Session guard:** Only alerts fire during the pair's relevant trading session.

## Pairs Covered

EURUSD · GBPUSD · USDJPY · USDCHF · AUDUSD · USDCAD · NZDUSD · EURJPY · GBPJPY

## Technical Indicators (8 signals per TF)

| Indicator | Bull | Bear |
|-----------|------|------|
| Price vs SMA20 | Above | Below |
| Price vs SMA50 | Above | Below |
| Price vs SMA200 | Above | Below |
| RSI(14) | < 30 | > 70 |
| MACD Histogram | Positive | Negative |
| Stochastic %K(14) | < 20 | > 80 |
| CCI(20) | < -100 | > 100 |
| Bollinger Band midline | Price above | Price below |

**Score → Label:** +6/+8 = Strong Buy · +3/+5 = Buy · -2/+2 = Neutral · -3/-5 = Sell · -6/-8 = Strong Sell

## Setup

### 1. Create a new GitHub repo

Name it `fx_technical` (or anything — update `DASHBOARD_URL` accordingly).

### 2. Add Repository Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|--------|-------|
| `TWELVEDATA_API_KEY` | Your Twelvedata free tier key |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/user ID |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `DASHBOARD_URL` | `https://YOUR_USERNAME.github.io/fx_technical/` |

### 3. Enable GitHub Pages

Go to **Settings → Pages → Source → GitHub Actions**

### 4. Enable GitHub Actions write permissions

Go to **Settings → Actions → General → Workflow permissions → Read and write permissions** ✓

### 5. Push the repo

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/fx_technical.git
git push -u origin main
```

### 6. Trigger a first run manually

Go to **Actions → D1 Scan + Deploy Dashboard → Run workflow**  
Then **H4 Scan → Run workflow**, then **H1 Scan → Run workflow**.

This seeds all JSON files and deploys the dashboard before the cron schedule kicks in.

## Telegram Alert Format

```
🟢 BUY EURUSD

Technical Summary
H1: Strong Buy  |  H4: Buy  |  D1: Buy

Session: London, New York

AI Opinion:
"EUR supported by hawkish ECB tone and softer US 
labour data. Technically clear above D1 SMA200 
with MACD and RSI momentum aligning. 
Watch 1.0950 resistance."

📊 Dashboard → https://...
```

## Cost Estimate

- **Twelvedata:** ~270 requests/day (well under 800/day free tier)
- **Anthropic API:** Only fires on alerts. ~$0.015/call with web search. 20 alerts/day ≈ $0.30/day
- **GitHub Actions:** Free tier easily sufficient

## File Structure

```
├── config/
│   └── pairs.py          # Pairs, sessions, currency list
├── scanner/
│   ├── fetch.py           # Twelvedata OHLCV fetcher
│   ├── score.py           # 8-indicator scoring engine
│   ├── csm.py             # D1 currency strength
│   ├── cooldown.py        # Alert cooldown guard
│   ├── scan_h1.py         # H1 scan runner
│   ├── scan_h4.py         # H4 scan runner
│   └── scan_d1.py         # D1 scan runner
├── alerts/
│   ├── ai_blurb.py        # Anthropic API + web search
│   ├── telegram.py        # Telegram message builder + sender
│   └── log.py             # alerts.json writer (dashboard blurbs)
├── dashboard/
│   └── index.html         # GitHub Pages dashboard
├── data/                  # JSON outputs (auto-committed by workflows)
├── state/
│   └── cooldown.json      # Cooldown state (auto-committed)
├── .github/workflows/
│   ├── scan_h1.yml
│   ├── scan_h4.yml
│   └── scan_d1.yml
└── requirements.txt
```
