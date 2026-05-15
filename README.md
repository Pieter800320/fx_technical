# Forex1212

A fully automated G10 forex scanner, regime classifier, and mobile trading dashboard — built on a zero-cost stack using GitHub Actions, GitHub Pages, Twelvedata free tier, the Anthropic API, and Telegram.

No server. No cloud bill. No subscription. Everything runs on GitHub's free compute.

---

## What it does

The system continuously scans 12 G10 currency pairs across four timeframes (W1, D1, H4, H1), classifies the current market regime, generates an AI-assisted news brief, and delivers a progressive mobile dashboard with chart drawing tools, a trade journal, and Telegram alerts.

**12 pairs tracked**
EUR/USD · GBP/USD · USD/JPY · USD/CHF · AUD/USD · USD/CAD · NZD/USD · EUR/JPY · GBP/JPY · AUD/JPY · NZD/JPY · CAD/JPY

---

## Architecture overview

```
GitHub Actions (free tier)
  ├── scan_d1.py        Weekdays 00:10 UTC
  ├── scan_h4.py        Every 4h at :25 UTC  ← deploys dashboard
  ├── scan_h1.py        Every 1h at :02 UTC
  ├── scan_alerts.py    Every 1h at :05 UTC
  ├── scan_news.py      06:00 / 11:00 / 15:00 / 21:00 UTC
  ├── scan_rates.py     Daily 06:30 UTC
  ├── scan_cot.py       Saturdays 14:00 UTC
  └── scan_calendar.py  Daily 06:00 UTC
         │
         ▼
  data/*.json  ──►  dashboard/  ──►  GitHub Pages
                                      (live mobile app)
```

All scan outputs are JSON files committed to the repo. GitHub Pages serves the dashboard directly from the `dashboard/` folder — no build step, no bundler.

---

## Dashboard features

### Home screen — Drum
- Infinite-scroll vertical drum showing all 12 pairs ranked by `Setup × Edge`
- Pairs with open trades marked with a glow indicator
- Per-pair data panel: D1/H4/H1 signal labels, Setup %, Edge score, 1212 MOM (W1/D1/H4/H1 with deltas), session badges, regime label, trade position bar

### Chart screen
- LightweightCharts price chart (H1 / H4 / D1) with live current-bar update via Twelvedata WebSocket
- Sub-chart: 1212 Momentum oscillator showing current TF line (blue), next higher TF line (red), and CMP composite (dotted)
- Sub-chart: MACD and RSI overlays
- EMA 200, EMA 50, Bollinger Bands, two configurable SMAs
- **Level tools** — draw horizontal price alerts, set Above/Below trigger, long-press to delete
- **Analysis button** — copies a full structured prompt (MOM, CSM, regime, session, news themes) for paste into any AI assistant
- **BB button** — copies a Bollinger Band reversal/continuation prompt with 9 scored factors for AI evaluation
- Candle countdown timer

### Signal strip
- Six-signal breakdown per pair per timeframe (EMA200, EMA50, RSI, MACD, ADX/DMI, Market Structure)
- Setup score, Edge score with breakdown tooltip (News / Regime / Session / ATR)
- 1212 MOM indicators per TF

### CSM sheet
- Currency Strength Model — D1 and H4 rankings for all 8 currencies
- Per-pair CSM breakdown showing which currency is driving the move

### Regime sheet
- Final regime (Risk-On / Risk-Off / Mixed / Ranging) with confidence
- Built from four weighted layers: W1 macro anchor, H4 structural, macro overlay, AI sentiment score
- Conviction bars per currency from COT + institutional positioning

### News brief
- AI-generated market narrative (Sonnet): DRIVER / MOMENTUM / WATCH
- News themes extracted from FXStreet, ForexLive, Nasdaq RSS (last 4h)
- Cross-asset macro panel: VIX, DXY, US10Y, US2Y, WTI, Gold, Silver, S&P500, BTC, Copper
- Copy Prompt button — sends full market brief to clipboard for AI analysis

### Trade journal
- Enter trades with full technical snapshot at open (MOM, CSM, regime, session, day, setup/edge scores)
- TP/SL monitoring via H1 scan (wick-accurate fill and close detection)
- Trade lifecycle Telegram alerts: filled / TP hit / SL hit
- Log tab: open trades, closed trades, pattern analysis by session/regime/day, performance stats (win rate, avg R, expectancy)
- CSV export with full trade schema

### Rates tab
- Live interest rate differentials for all 8 currencies
- Manual entry with GitHub sync

### Correlation sheet
- 50-bar H4 correlation matrix for all 12 pairs

---

## Scoring systems

### Setup score (0–100%)
Six-signal technical alignment score computed per pair per timeframe in `score.py`:

| Signal | Weight |
|--------|--------|
| EMA 200 (trend gate) | High |
| EMA 50 (momentum bias) | Medium |
| RSI midline position | Medium |
| MACD histogram direction | Medium |
| DMI+/- crossover | Medium |
| Market structure (BOS/CHoCH) | Medium |

Adjusted by: ADX weight, conflict penalty (H4 structure vs momentum), reset score (mean-reversion proximity).

### Edge score (1–10)
Multi-component environmental quality score computed in `scan_news.py`:

| Component | Max | Method |
|-----------|-----|--------|
| News sentiment (24h directional catalyst) | 5 | Claude Haiku |
| Regime fit (market environment vs trade direction) | 3 | Python rule-based |
| Session relevance (primary liquidity window) | 2 | Python time-check |
| ATR contraction bonus (diminishing energy) | 1 | Python — ATR split |

Raw max = 11, displayed as min(10, raw). Breakdown visible as tooltip on the Edge pill.

### 1212 Momentum oscillator (0–100)
ATR-normalised momentum oscillator computed from a 12-period SMA displacement:
- 50 = neutral
- Above 50 = bullish pressure
- Below 50 = bearish pressure
- Delta = change vs prior bar (direction of momentum shift)

Computed for W1, D1, H4, H1. CMP (Composite Momentum Pulse) = weighted blend: W1×0.1 + D1×0.4 + H4×0.3 + H1×0.2.

### Drum ranking
`rank = Setup% × edgeMult`

where `edgeMult` = 0.50 (Edge 1–4) / 0.75 (Edge 5–6) / 1.00 (Edge 7–8) / 1.15 (Edge 9–10).

---

## Regime system

Four-layer weighted composite:

| Layer | Weight | Source | Updates |
|-------|--------|---------|---------|
| W1 macro anchor | 25% | SPX, VIX, Gold, DXY 4-week returns | Daily via `scan_news.py` |
| H4 structural | 30% | CSM divergence + H4 signal alignment | Every 4h via `scan_h4.py` |
| Macro overlay | 30% | VIX, DXY, US2Y, Gold, SPX, Copper intraday | Every 4h via `scan_news.py` |
| AI sentiment | 15% | Claude Haiku news/macro risk appetite score | 4× daily via `scan_news.py` |

W1 requires two consecutive identical readings before confirming a regime flip (persistence filter).

Outputs: `Risk-On` / `Risk-Off` / `Mixed` / `Ranging` with confidence (High/Medium/Low) and direction (Strengthening/Stable/Deteriorating).

---

## Telegram alerts

Six alert types:

| Alert | Trigger | Source |
|-------|---------|--------|
| Signal summary | Setup ≥ 70% AND Edge ≥ 7 AND D1 confirms H4 AND ADX ≥ 20, not on 20h cooldown | `scan_alerts.py` |
| Level alert | Price crosses a horizontal level drawn in the dashboard | `scan_h1.py` |
| BB band touch | H4 wick touches upper/lower Bollinger Band | `scan_h4.py` via `bb.py` |
| BB midline return | H4 returns to 20-SMA after a band touch | `scan_h4.py` via `bb.py` |
| Trade filled | Pending order triggered (wick-accurate) | `scan_h1.py` |
| Trade closed | TP or SL hit (TP wins on same-bar gap) | `scan_h1.py` |

---

## Scan schedule

| Workflow | Schedule (UTC) | Deploys dashboard |
|----------|---------------|-------------------|
| `scan_d1.py` | Weekdays 00:10 | No |
| `scan_h4.py` | Every 4h at :25 | **Yes** |
| `scan_h1.py` | Every 1h at :02 | No |
| `scan_alerts.py` | Every 1h at :05 | No |
| `scan_news.py` | 06:00 / 11:00 / 15:00 / 21:00 | Yes (regime only) |
| `scan_rates.py` | Daily 06:30 | No |
| `scan_cot.py` | Saturdays 14:00 | No |
| `scan_calendar.py` | Daily 06:00 | No |

---

## Setup

### 1. Fork the repository

Fork to your own GitHub account. GitHub Pages and GitHub Actions both require the repo to be yours.

### 2. Enable GitHub Pages

Go to **Settings → Pages → Source** and select `Deploy from a branch`, branch `main`, folder `/dashboard`.

### 3. Configure repository secrets

Go to **Settings → Secrets and variables → Actions** and add the following:

| Secret | Required by | Where to get it |
|--------|-------------|-----------------|
| `TWELVEDATA_API_KEY` | H1, H4 scans | [twelvedata.com](https://twelvedata.com) — free tier |
| `TELEGRAM_BOT_TOKEN` | H1, H4, alert scans | Create a bot via [@BotFather](https://t.me/BotFather) on Telegram |
| `TELEGRAM_CHAT_ID` | H1, H4, alert scans | Your personal chat ID — send `/start` to [@userinfobot](https://t.me/userinfobot) |
| `ANTHROPIC_API_KEY` | News scan | [console.anthropic.com](https://console.anthropic.com) |
| `DASHBOARD_URL` | H1, H4 scans (alert links) | Your GitHub Pages URL, e.g. `https://yourusername.github.io/fx_technical` |

`GITHUB_TOKEN` is provided automatically by GitHub Actions — you do not need to create it.

### 4. Enable GitHub Actions

Go to **Actions** and enable workflows if prompted. Run `scan_d1.py` and `scan_h4.py` manually first via **Run workflow** to populate the initial data files before the schedule kicks in.

### 5. Dashboard PAT (for alert sync)

The dashboard syncs level alerts and trades to GitHub via the Contents API. To enable this, go to the Rates tab in the dashboard, enter a GitHub Personal Access Token (classic, with `repo` scope), and press Save. The token is stored in your browser's localStorage under `fx1212_gh_pat`.

### 6. Twelvedata WebSocket (live prices in chart)

The chart fetches the current live bar via Twelvedata when the chart is open. In the dashboard **Settings**, enter your Twelvedata API key. It is stored locally under `fx1212_td_key`.

---

## Data flow

```
Twelvedata API
  └── fetch.py ──► score.py ──► scan_h4.py ──► h4_scores.json
                            └── scan_d1.py ──► d1_scores.json
                            └── scan_h1.py ──► h1_scores.json

  ├── csm.py     ──► csm.json         (Currency Strength Model)
  ├── bb.py      ──► Telegram          (BB band/midline alerts)
  ├── regime.py  ──► regime.json       (structural regime)
  ├── structure.py ──► BOS/CHoCH data  (embedded in scores)
  ├── conviction.py ──► conviction.json (COT-based scores)
  └── correlate.py ──► correlation.json

Yahoo Finance API
  └── scan_news.py ──► macro data ──► news_brief.json
                   └── regime.json (macro overlay + W1 anchor)

FXStreet / ForexLive / Nasdaq RSS
  └── scan_news.py ──► Claude (Haiku: themes + edge scores)
                   └── Claude (Sonnet: narrative)
                   └── news_brief.json

CFTC COT data
  └── scan_cot.py ──► cot.json ──► conviction.json

All JSON ──► dashboard/ ──► GitHub Pages ──► Mobile browser
```

---

## Repository structure

```
fx_technical/
├── .github/workflows/     GitHub Actions scan schedules
├── alerts/
│   ├── telegram.py        Telegram message formatters (all 6 alert types)
│   ├── log.py             Alert logging to alerts.json
│   └── news.py            FXStreet news context fetcher for H4 alerts
├── config/
│   └── pairs.py           Pair list, session windows, session-pair mapping
├── scanner/
│   ├── fetch.py           Twelvedata OHLCV fetcher (H1/H4/D1)
│   ├── score.py           Six-signal scoring engine (all timeframes)
│   ├── csm.py             Currency Strength Model
│   ├── regime.py          Regime classifier (H4 structural + W1 + final)
│   ├── bb.py              Bollinger Band touch detection + state machine
│   ├── structure.py       BOS / CHoCH market structure detector
│   ├── conviction.py      COT-based currency conviction scores
│   ├── correlate.py       H4 correlation matrix
│   ├── levels.py          Support/resistance level detection
│   ├── cooldown.py        Alert cooldown manager
│   ├── cot.py             CFTC COT data fetcher
│   ├── scan_d1.py         Daily scan: D1 scores, regime, COT CSM
│   ├── scan_h4.py         H4 scan: scores, CSM, BB alerts, correlation
│   ├── scan_h1.py         H1 scan: scores, level alerts, trade monitoring
│   ├── scan_alerts.py     Alert gate: Setup/Edge/D1/ADX filters → Telegram
│   ├── scan_news.py       News brief: themes, narrative, Edge scores
│   ├── scan_rates.py      Interest rate data
│   ├── scan_cot.py        COT weekly data
│   └── scan_calendar.py   Economic calendar
├── data/                  Live JSON data (source of truth)
├── dashboard/             GitHub Pages root
│   ├── index.html         Single-file mobile dashboard (~180KB)
│   └── *.json             Copied from data/ by workflows
├── state/
│   └── cooldown.json      Alert cooldown state (24h per pair/direction)
└── requirements.txt       pandas · numpy · requests
```

---

## Dependencies

**Python (scanner):** `pandas==2.1.4` · `numpy==1.26.2` · `requests==2.31.0` · `anthropic` (installed at runtime by `scan_news.py` workflow)

**JavaScript (dashboard):** [LightweightCharts](https://github.com/tradingview/lightweight-charts) v4 (CDN) · Vanilla JS · No build toolchain

**External APIs (all free tier):**
- Twelvedata — OHLCV data (H1/H4/D1), WebSocket live prices
- Yahoo Finance v8 — Cross-asset macro data (VIX, DXY, SPX, Gold, etc.)
- FXStreet, ForexLive, Nasdaq — RSS news feeds
- CFTC — Weekly COT reports (public)
- Anthropic — Claude Haiku (Edge scoring + themes) and Claude Sonnet (narrative)

---

## Methodology

Signal scoring follows the **Pain-Free Performance** top-down framework (Dr. John Rusin adapted for FX):

1. D1 sets the directional bias — H4 must confirm before any signal fires
2. H1 provides precision entry context and monitors open trades
3. Regime filters environmental fit — Risk-On pairs flagged in Risk-Off conditions
4. ADX ≥ 20 required for signal alerts (no alerts in flat/ranging conditions)
5. 20-hour cooldown per pair/direction prevents alert clustering

The 1212 Momentum oscillator is a proprietary ATR-normalised SMA displacement indicator. It answers "is momentum building or exhausting?" on each timeframe independently, and the CMP composite answers "what is the multi-timeframe consensus?"

---

## Cost

| Service | Cost |
|---------|------|
| GitHub Actions | Free (2,000 min/month on free tier — well within limits) |
| GitHub Pages | Free |
| Twelvedata | Free tier (800 API calls/day — sufficient for 12 pairs) |
| Yahoo Finance | Free (unofficial v8 API) |
| RSS feeds | Free |
| CFTC COT data | Free (public) |
| Anthropic API | ~$0.01–0.05/day depending on scan frequency |

Total infrastructure cost: **~$0.30–1.50/month** (Anthropic API only).

---

## License

Private repository. Not licensed for redistribution.
