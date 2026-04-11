# Forex1212

An automated forex technical analysis system built on free infrastructure. Telegram alerts fire when D1, H4, and H1 all agree. The dashboard gives you a complete market picture at a glance.

**Live:** https://Pieter800320.github.io/fx_technical/

---

## Philosophy

**D1 = Bias. H4 = Confirmation. H1 = Execution.**

No alert fires unless all relevant timeframes agree. Hard filters eliminate ranging and low-participation markets entirely. Structure must confirm momentum — if they disagree, the signal is suppressed. The dashboard is the market brief — everything essential visible without scrolling.

---

## Dashboard

Four tabs:

**Dashboard** — the daily brief. Three modules at a glance:
- Sessions with live countdown (London closes 1h 20m)
- Regime with signal breakdown (tap to expand)
- Market Brief — tap to generate auto-brief, Copy Prompt sends it to Claude.ai with web search for live VIX/DXY/SPX context

Below that: Currency Strength bars with per-pair breakdown (tap any currency), and a Shortlist showing the top 1–2 correlation-filtered trade candidates.

**Correlation** — Lollipop chart. Tap any pair button to see its correlation with all other pairs. Red = high positive (same bet), blue = high negative (natural hedge), grey = uncorrelated. Pair buttons at top, 50-bar H4 returns.

**Signals** — Technical Scores table (H1/H4/D1 per pair, abbreviated pills SB/B/N/S/SS/CF with score inside, tap any pill for full breakdown including ADX, ATR, structure event, conflict flag). Latest alert cards with clickable BUY/SELL labels showing full Telegram-equivalent context.

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

**Forex (12 pairs):** EURUSD · GBPUSD · USDJPY · USDCHF · AUDUSD · USDCAD · NZDUSD · EURJPY · GBPJPY · AUDJPY · NZDJPY · CADJPY

---

## Scoring Engine

Three independent signal components — each contributes a continuous score, not a binary vote:

| Component | Logic | Weight |
|---|---|---|
| EMA200 | Price above = +1.5, below = -1.5 | ±1.5 |
| Momentum group | EMA50 + DMI + MACD histogram majority vote. All three agree = ±2.0, two of three = ±1.0 | ±2.0 |
| RSI graduated | ≥70=+2.0, ≥60=+1.0, ≥50=+0.5, ≥40=-0.5, ≥30=-1.0, <30=-2.0 | ±2.0 |

**Raw maximum: ±5.5**

**ADX graduated weight** scales the raw score before the structure multiplier is applied. This replaces the old binary gate — markets with weak trends produce proportionally weaker scores rather than a hard cut-off:

| ADX | Weight |
|---|---|
| < 15 | ×0.0 — score zeroed |
| 15–20 | ×0.5 — halved |
| 20–25 | ×0.75 — developing trend |
| ≥ 25 | ×1.0 — full score |

**ATR hard filter** — if current ATR < 70% of its 14-bar average, the pair is suppressed entirely. Low participation is genuinely binary.

---

## Structure Engine

Structure is not a voting signal — it is a score multiplier. This is the architectural difference from most retail systems.

**Structure detection (H4 and D1 only):**

Swing highs/lows are identified using a lookback window (5 bars on H4, 10 bars on D1 for more robust institutional pivots). Two events are detected:

| Event | Meaning | Multiplier |
|---|---|---|
| BOS — Break of Structure | Price breaks the last swing high/low in the trend direction. Confirms continuation. | ×1.00 – ×1.30 |
| CHOCH — Change of Character | Price breaks against the prior trend sequence. Warning of potential reversal. | ×0.40 – ×1.00 |
| None | No structural event detected. | ×1.00 |

Multiplier magnitude scales with **strength** — how far price cleared the structural level relative to ATR (0–100%).

**Conflict detection:**

If the structural sequence direction contradicts the momentum group majority (EMA50 + DMI + MACD), the multiplier is forced to ×0.00. The score is zeroed, the label becomes **Conflict (CF)**, and no alert fires. The system treats structure-momentum disagreement as a non-tradeable state.

**Final score maximum: ±7.15** (after BOS ×1.30 at full ADX weight)

**Score → Label** (regime-aware thresholds):

| Regime | Strong Buy/Sell | Buy/Sell |
|---|---|---|
| Risk-On / Risk-Off | ±4.5 | ±3.0 |
| Ranging / Mixed | ±5.5 | ±4.0 |

---

## Currency Strength Model

ATR-adjusted, multi-timeframe weighted model with 12 observation pairs.

**Strength pairs:**

| Category | Pairs |
|---|---|
| USD base | EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD |
| JPY crosses | AUDJPY, NZDJPY, CADJPY |
| EUR/GBP/CHF cross-validation | EURGBP, EURCHF |

**Coverage per currency:**

| Currency | Observations |
|---|---|
| USD | 7 |
| JPY | 6 |
| EUR | 4 (EURUSD, EURJPY, EURGBP, EURCHF) |
| GBP | 3 (GBPUSD, GBPJPY, EURGBP) |
| AUD / NZD / CAD / CHF | 2 each |

EURGBP and EURCHF are CSM-only — they contribute to EUR/GBP/CHF strength scores but are not scanned for signals or shown in correlation.

For each pair: compute % return over 14 bars on D1 and H4, divide by ATR(14) to normalise for volatility, weight D1 × 0.7 + H4 × 0.3. Base currency adds the score, quote subtracts. Normalise all 8 currencies to 0–100.

Tap any currency bar on the dashboard to see the per-pair breakdown.

---

## Market Regime

Proxy detector using existing data — no additional API calls.

Five signals vote for Risk-On or Risk-Off:

| Signal | Source | Weight |
|---|---|---|
| Safe-haven divergence: (JPY+CHF)/2 − (AUD+NZD+CAD)/3 | CSM rankings | ×2 |
| USD proxy: USD-long pairs avg − USD-short pairs avg | D1 scores | ×2 |
| Risk basket: AUDUSD + NZDUSD + GBPJPY + EURJPY + AUDJPY + NZDJPY avg | D1 scores | ×1 |
| Gold direction | XAUUSD D1 score | ×1 |
| Volatility confidence modifier | Avg ADX | scales votes |

**Override rule:** when average ADX > 30, regime confidence is halved and H4 data is used instead of D1. Reverts when ADX drops below 1.1× threshold (hysteresis).

**Output:** Risk-Off / Risk-On / Ranging / Mixed + confidence (High / Medium / Low) + data source (D1 / H4)

---

## Correlation Matrix

Pairwise Pearson correlation of 50-bar H4 returns across all 12 pairs. Updated every 4 hours.

Displayed as a lollipop chart: tap any pair to see its correlation with all other 11 pairs. Bars extend right (positive) or left (negative) from a centre zero line. Red = same direction bet (≥70), blue = natural hedge (≤-70), grey = uncorrelated.

---

## Shortlist Logic

1. Collect all pairs with a directional signal (score ≥ 3 or ≤ -3)
2. Sort by absolute score descending, ADX as tiebreaker
3. Walk the ranked list — add each pair unless it correlates > 70% with an already-selected pair in the same direction
4. Show top picks + what was dropped

---

## Alert Format

```
🟢 BUY AUDUSD

D1: Strong Buy  |  H4: Strong Buy  |  H1: Buy

ADX: 44.4  |  ATR: Normal
Structure: BOS (bull, strength 0.74, ×1.28)
Session: Sydney
Regime: Risk-On (Medium)

📰 "AUD surges on risk appetite recovery" — DailyFX
✅ No high-impact events in next 12h.

📊 Dashboard →
```

When a **Conflict** is active, the alert includes:
```
⚠️ Conflict: Structure contradicts momentum — treat with caution
```

---

## Dropdown Breakdown

Tap any pill in the Signals tab to see the full analysis:

**Always shown:**
- Six signal votes (EMA200, EMA50, RSI, MACD, DMI, Structure) — ▲ Bull / ▼ Bear / → Neutral
- ADX value with graduated weight applied (green ≥20, amber 15–20, red <15)
- ATR status (Normal / Contracted)

**Shown when detected (H4 / D1 only):**
- Structure event: BOS or CHOCH, direction, strength %, and multiplier applied
- Conflict flag: fires when structure direction ≠ momentum majority

**Shown when extended (any timeframe):**
- Extension warning: price >2× ATR from EMA200, RSI >75/<25, or 8+ bars beyond EMA50

---

## AI Workflow

**Per-signal:** Tap Copy Prompt on any Signals card. Paste into Claude.ai (web search enabled). Returns a 40-word verdict: Regime / Edge or Flaw / Verdict.

**Market Brief:** Tap Market Brief on the Dashboard tab, or Copy Prompt to validate with live data in Claude.ai. The prompt includes currency strength rankings, regime signal values, all directional scores, conflict pairs, the pre-filtered shortlist with correlation reasoning, and requests: regime classification, key driver, 9-pair bias table, one caution, shortlist confirmation — in under 100 words.

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
  pairs.py                # 12 instruments, sessions, display names
scanner/
  fetch.py                # Twelvedata OHLCV fetcher
  score.py                # 3-component scoring engine + ADX weight + structure multiplier
  structure.py            # BOS/CHOCH event detection with swing pivot lookback
  csm.py                  # ATR-adjusted currency strength model (12 strength pairs)
  correlate.py            # Pairwise Pearson correlation matrix
  regime.py               # Proxy market regime detector (6-signal risk basket)
  levels.py               # Swing high/low S/R detection
  cooldown.py             # 4-hour alert cooldown guard
  scan_h1.py              # H1 scan runner
  scan_h4.py              # H4 scan runner (also computes correlation)
  scan_d1.py              # D1 scan runner (also computes CSM and regime)
alerts/
  news.py                 # RSS headlines + ForexFactory calendar
  telegram.py             # Message builder + Telegram sender (includes structure/conflict)
  log.py                  # alerts.json writer (includes structure/conflict fields)
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
| Twelvedata API | Free (~416 req/day of 800 limit) |
| GitHub Actions | Free |
| GitHub Pages | Free |
| Telegram | Free |
| Anthropic API | Not required (optional for AI prompts in Claude.ai) |

**Total running cost: $0/month**
