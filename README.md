# Forex1212

An automated forex technical analysis system built on free infrastructure. Telegram alerts fire when D1, H4, and H1 all agree. The dashboard gives you a complete market picture at a glance.

**Live:** https://Pieter800320.github.io/fx_technical/

---

## Philosophy

**D1 = Bias. H4 = Confirmation. H1 = Execution.**

No alert fires unless all relevant timeframes agree. Hard filters eliminate ranging and low-participation markets entirely. The dashboard is the market brief — everything essential visible without scrolling.

---

## Dashboard

Four tabs:

**Dashboard** — the daily brief. Three modules at a glance:
- Sessions with live countdown (London closes 1h 20m)
- Regime with signal breakdown (tap to expand)
- Market Brief — tap to generate auto-brief, Copy Prompt sends it to Claude.ai with web search for live VIX/DXY/SPX context

Below that: Currency Strength bars with per-pair breakdown, and a Shortlist showing the top 1-2 correlation-filtered trade candidates.

**Correlation** — 9×9 pairwise correlation matrix of H4 returns over 50 bars. Red = high positive (same bet), blue = high negative (natural hedge), grey = uncorrelated (genuine diversification). Inline warning when active signals are correlated.

**Signals** — Technical Scores table (H1/H4/D1 per pair, tap any pill for 6-signal breakdown + ADX/ATR) and latest alert cards with clickable BUY/SELL pills showing full Telegram-equivalent context.

**Journal** — Trade log with snapshot of market conditions at entry time, R-multiple calculation, Win/Loss/Early-Close outcome buttons, edit modal for post-trade notes, delete with restore, CSV export, and performance stats (win rate, avg R, expectancy).

---

## How It Works

Three scheduled scans run automatically via GitHub Actions:

| Job | Schedule (UTC) | Role |
|---|---|---|
| D1 Scan | Daily 00:10 | Sets bias. Scores all pairs. Computes currency strength and regime. |
| H4 Scan | Every 4h at :25 | Fires if D1 + H4 agree. Computes correlation matrix. |
| H1 Scan | Every hour at :02 | Fires if D1 + H4 + H1 all agree. |

H1 and H4 share a 4-hour cooldown per pair. No alerts fire on weekends (Friday 22:00 – Sunday 22:00 UTC).

---

## Instruments

**Forex (9 pairs):** EURUSD · GBPUSD · USDJPY · USDCHF · AUDUSD · USDCAD · NZDUSD · EURJPY · GBPJPY

---

## Scoring Engine

6 independent signals per timeframe — each votes +1 (bull) or -1 (bear):

| Signal | Logic |
|---|---|
| EMA200 | Price above = bull |
| EMA50 | Price above = bull |
| RSI vs 50 | RSI > 50 = bull |
| MACD | MACD line above signal = bull |
| DMI+/DMI- | DMI+ > DMI- = bull |
| Structure | HH+HL = bull, LH+LL = bear (H4/D1 only) |

**Score → Label:** ±5–6 = Strong Buy/Sell · ±3–4 = Buy/Sell · -2 to +2 = Neutral

**Hard filters** suppress alerts regardless of score:
- ADX < 20 — no trend present
- ATR < 70% of 14-bar average — low participation

**Extension detection** flags overextended signals:
- Price > 2.0× ATR from EMA200
- RSI > 75 (bull) or < 25 (bear)
- 8+ consecutive bars beyond EMA50

---

## Currency Strength Model

ATR-adjusted, multi-timeframe weighted model.

For each pair: compute % return over 14 bars on D1 and H4, divide by ATR(14) to normalise for volatility, weight D1 × 0.7 + H4 × 0.3. Base currency adds the score, quote subtracts. Normalise all 8 currencies to 0–100.

Tap any currency bar on the dashboard to see the per-pair breakdown — the score shown is the ATR-adjusted contribution of each pair. Positive = supporting the currency's strength. Negative = contesting it.

---

## Market Regime

Proxy detector using existing data — no additional API calls.

Five signals vote for Risk-On or Risk-Off:

| Signal | Source | Weight |
|---|---|---|
| Safe-haven divergence: (JPY+CHF)/2 - (AUD+NZD+CAD)/3 | CSM | ×2 |
| USD proxy: USD pair directions averaged | D1 scores | ×2 |
| Risk basket: AUDUSD + NZDUSD + GBPJPY + EURJPY avg | D1 scores | ×1 |
| Gold direction | XAUUSD D1 score | ×1 |
| Volatility confidence modifier | Avg ADX | scales votes |

**Override rule:** when average ADX > 30 (elevated volatility), regime confidence is halved and H4 data is used instead of D1. Reverts when ADX drops below 22 (hysteresis).

**Output:** Risk-Off / Risk-On / Ranging / Mixed + confidence (High / Medium / Low) + data source (D1 / H4)

Tap the regime chip on the dashboard to see all six underlying signal values.

---

## Correlation Matrix

Pairwise Pearson correlation of 50-bar H4 returns across all 9 pairs. Updated every 4 hours.

Reading it: +100 means two pairs move identically — picking both is doubling up on one bet. -100 is a natural hedge. 0 is genuinely uncorrelated — both can be traded independently.

The dashboard Shortlist uses correlation filtering automatically: signals are ranked by score, then correlated duplicates are removed. The Shortlist shows the 1-2 best independent opportunities and lists what was dropped and why.

---

## Shortlist Logic

1. Collect all pairs with a directional signal (score ≥ 3 or ≤ -3)
2. Sort by absolute score descending, ADX as tiebreaker
3. Walk the ranked list — add each pair unless it correlates > 70% with an already-selected pair in the same direction
4. Show top picks + what was dropped

---

## Alert Format

```
🔴 SELL AUDUSD

D1: Sell  |  H4: Strong Sell  |  H1: Sell

ADX: 26.3  |  ATR: Normal
Session: New York
Regime: Risk-Off (Medium)
⚠️ Extended: Price 2.4x ATR from EMA200

📰 "AUD slides as risk aversion grips markets" — DailyFX
No high-impact events in next 12h.

Dashboard →
```

---

## AI Workflow

**Per-signal:** Tap Copy Prompt on any Signals card. Paste into Claude.ai (with web search enabled). The prompt includes pair, direction, all TF scores, ADX, ATR, extension flag, regime, correlated pairs, and news headline. Claude searches for live VIX, DXY, and pair-specific macro context and returns a 40-word verdict.

**Market Brief:** Tap Market Brief on the Dashboard tab to see the auto-generated brief, or Copy Prompt to validate it with live data in Claude.ai. The prompt includes currency strength rankings, all directional scores, regime signal values, the pre-filtered shortlist with correlation reasoning, and asks for a regime classification, key driver, 9-pair bias table, and one caution in under 100 words.

---

## Setup

### 1. Create a GitHub repo and upload all files

### 2. Add Repository Secrets

Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|---|---|
| `TWELVEDATA_API_KEY` | Twelvedata free tier API key |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `DASHBOARD_URL` | `https://YOUR_USERNAME.github.io/fx_technical/` |

### 3. Enable GitHub Actions write permissions

Settings → Actions → General → Workflow permissions → Read and write permissions ✓

### 4. Enable GitHub Pages

Settings → Pages → Source → GitHub Actions

### 5. Make repo public

Settings → Danger Zone → Change visibility → Make public

### 6. Seed data with manual runs (in this order)

1. Actions → D1 Scan + Deploy Dashboard → Run workflow
2. Actions → H4 Scan + Deploy Dashboard → Run workflow
3. Actions → H1 Scan → Run workflow

---

## File Structure

```
config/
  pairs.py                # Instruments, sessions, display names
scanner/
  fetch.py                # Twelvedata OHLCV fetcher
  score.py                # 6-signal engine + ADX/ATR filters + extension detection
  csm.py                  # ATR-adjusted currency strength model
  correlate.py            # Pairwise Pearson correlation matrix
  regime.py               # Proxy market regime detector
  levels.py               # Swing high/low S/R detection
  cooldown.py             # 4-hour alert cooldown guard
  scan_h1.py              # H1 scan runner
  scan_h4.py              # H4 scan runner (also computes correlation)
  scan_d1.py              # D1 scan runner (also computes CSM and regime)
alerts/
  news.py                 # RSS headlines + ForexFactory calendar
  telegram.py             # Message builder + Telegram sender
  log.py                  # alerts.json writer
dashboard/
  index.html              # GitHub Pages dashboard (Forex1212)
data/                     # Auto-committed JSON outputs
  h1_scores.json
  h4_scores.json
  d1_scores.json
  csm.json
  alerts.json
  regime.json
  correlation.json
state/
  cooldown.json           # Alert cooldown state
.github/workflows/
  scan_h1.yml
  scan_h4.yml
  scan_d1.yml
requirements.txt
```

---

## Cost

| Service | Cost |
|---|---|
| Twelvedata API | Free (800 req/day — ~400 used) |
| GitHub Actions | Free |
| GitHub Pages | Free |
| Telegram | Free |
| Anthropic API | Not required (optional for AI prompts in Claude.ai) |

**Total running cost: $0/month**
