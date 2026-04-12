# Forex1212

An automated multi-timeframe forex technical analysis system built entirely on free infrastructure. Telegram alerts fire only when D1, H4, and H1 all agree. The dashboard gives a complete, real-time market picture across five tabs.

**Live dashboard:** https://Pieter800320.github.io/fx_technical/

---

## Philosophy

**D1 = Bias. H4 = Confirmation. H1 = Execution.**

No alert fires unless all three timeframes agree. Structure must confirm momentum — if they contradict, the signal is suppressed entirely. Hard filters eliminate ranging and low-participation markets. The system is designed to fire fewer, higher-quality signals rather than alert constantly.

Every coloured pill on the dashboard is interactive. Tap any pill to reveal more information.

---

## Dashboard — Five Tabs

### Dashboard tab

Six modules, stacked vertically:

**Sessions** — shows only the currently active session with its closing countdown. Tap to expand all four sessions with open/close countdowns. When the market is closed, a red "Market Closed · opens in Xh Ym" pill replaces the session chips automatically.

**Market Brief / Live** — two equal blue pills side by side.
- *Market Brief* — opens an inline drawer with an auto-generated narrative covering regime, USD direction, safe-haven divergence, CSM dispersion, strongest/weakest currencies, active signals, extension warnings, and ADX quality. A *Copy Prompt* button inside sends the full context to Claude.ai for a 100-word macro validation with live VIX/DXY/SPX data.
- *Live* — opens an inline drawer showing all 12 tradeable pairs with their current price (from the latest H1 scan), pip change vs yesterday's close, and percentage change. Updated every hour. Green = positive, red = negative, with + and − signs.

**Shortlist** — always visible. Shows the top 1–2 independent trade candidates ranked by score, ADX as tiebreaker, with correlation filtering applied. Pairs correlated above 70% in the same direction are removed — only the stronger one is shown. Lists what was dropped and why. When no signals meet the threshold, shows a "No signals right now" message.

**Regime** — coloured pill (green = Risk-On, red = Risk-Off, grey = Ranging, amber = Mixed) with confidence level. Tap the pill to expand a drawer showing the 10 underlying signal values: safe-haven divergence, USD proxy, risk basket, gold direction, trend ratio, dispersion, Risk-Off/On vote totals, data source, and vol ratio.

**Currency Strength** — 8 currency bars (EUR, GBP, USD, JPY, CHF, AUD, CAD, NZD) ranked 0–100 by ATR-adjusted multi-timeframe strength. Bars have rounded tips. Tap any currency bar to see the per-pair contribution breakdown showing which pairs are supporting or contesting that currency's strength.

**Shortlist** is always present at the top of the Currency Strength section for quick reference.

---

### Correlation tab

Three modules:

**Pair selector** — centred pill buttons for all 12 tradeable pairs. Tap any pair to select it.

**Lollipop chart** — shows the selected pair's correlation with all other 11 pairs. Bars extend right (positive/red = same-direction bet) or left (negative/blue = natural hedge) from a centre zero line. Values shown as ±number. 50-bar H4 returns, updated every 4 hours.

Reading it: +70 or above = doubling up on the same bet. −70 or below = natural hedge. Near zero = genuinely independent.

---

### Signals tab

Two modules:

**Technical Scores** — compact table showing all 12 pairs across H1, H4, D1. Pills use abbreviations: **SB** Strong Buy · **B** Buy · **N** Neutral · **S** Sell · **SS** Strong Sell · **CF** Conflict. Score is shown inside the pill (e.g. "SB +6"). Tap any pill to expand a dropdown showing:
- Six signal votes (EMA200, EMA50, RSI, MACD, DMI, Structure) with Bull/Bear/Neutral arrows
- ADX value with graduated weight applied
- ATR status (Normal / Contracted)
- Structure event (BOS or CHOCH) with direction, strength %, and multiplier — H4/D1 only
- Conflict flag when structure contradicts momentum
- Extension warning when price is stretched

**Latest Signals** — alert cards from the last 24 hours on a dark background. Each card shows pair name and a coloured **BUY** or **SELL** pill. Tap the pill to expand a Telegram-format info panel showing the direction, all three timeframe labels, ADX/ATR, structure event, conflict warning if present, and regime. Below the pill info is the RSS headline that fired with the alert, and a Copy Prompt button for Claude.ai analysis.

---

### Journal tab

New trade entry form with grey module background and dark input fields. Fields:
- Pair (all 12 tradeable pairs)
- Direction (BUY / SELL)
- AI Rec (Edge / Flaw)
- Entry, Stop Loss, Take Profit prices
- Notes (setup rationale)

A market snapshot auto-populates below the fields showing D1/H4 labels, CSM base/quote values, ADX, ATR status, extension flag, and regime at the time of entry. Buttons: *Add to Journal* and *Export CSV*.

---

### Log tab

**Trade Log** — scrollable table of all journal entries with date, pair, direction, entry/SL/TP, R-multiple, D1/H4 labels, regime, extension flag, AI rec, and outcome buttons (Win / Loss / Early Close). Deleted trades go to a *Recently Deleted* section with a Restore button.

**Performance** — five dark stat cards: Total Trades, Win Rate, Avg R, Expectancy, Open trades. Green when positive, red when negative. Empty state is white (not incorrectly green).

Export to CSV covers all 20 fields including CSM base/quote values and post-trade notes.

---

## How It Works

Three GitHub Actions jobs run automatically:

| Job | Schedule (UTC) | Role |
|---|---|---|
| D1 Scan | Daily 00:10 | Sets bias. Scores all 12 pairs. Computes currency strength (15 pairs) and regime. |
| H4 Scan | Every 4h at :25 | Fires alert if D1 + H4 agree. Computes 12×12 correlation matrix. |
| H1 Scan | Every hour at :02 | Fires alert if D1 + H4 + H1 all agree. |

H1 and H4 share a 4-hour cooldown per pair. No alerts fire on weekends (Friday 22:00 – Sunday 22:00 UTC).

---

## Instruments

**12 tradeable pairs:** EURUSD · GBPUSD · USDJPY · USDCHF · AUDUSD · USDCAD · NZDUSD · EURJPY · GBPJPY · AUDJPY · NZDJPY · CADJPY

**CSM-only pairs (not traded, used for strength calculation only):** EURGBP · EURCHF · GBPCHF

---

## Scoring Engine

Three independent signal components — continuous scores, not binary votes:

| Component | Logic | Max contribution |
|---|---|---|
| EMA200 | Price above = +1.5, below = −1.5 | ±1.5 |
| Momentum group | EMA50 + DMI + MACD histogram majority. All agree = ±2.0, two of three = ±1.0 | ±2.0 |
| RSI graduated | ≥70=+2.0 / ≥60=+1.0 / ≥50=+0.5 / ≥40=−0.5 / ≥30=−1.0 / <30=−2.0 | ±2.0 |

**Raw maximum: ±5.5**

**ADX graduated weight** — not a binary gate:

| ADX | Weight applied |
|---|---|
| < 15 | ×0.0 — score zeroed |
| 15–20 | ×0.5 — halved |
| 20–25 | ×0.75 — developing |
| ≥ 25 | ×1.0 — full |

**ATR hard filter** — if current ATR < 70% of its 14-bar average, the pair is suppressed entirely. Low participation is genuinely binary.

---

## Structure Engine

Structure is a score multiplier, not a voting signal. This is the key architectural distinction from most retail systems.

**Detection (H4 and D1 only):** Swing highs/lows are identified using a lookback window — 5 bars on H4, 10 bars on D1 (wider for more robust institutional pivots).

| Event | Meaning | Score multiplier |
|---|---|---|
| BOS — Break of Structure | Price breaks the last swing in the trend direction. Confirms continuation. | ×1.00 – ×1.30 |
| CHOCH — Change of Character | Price breaks against the prior trend sequence. Warns of potential reversal. | ×0.40 – ×1.00 |
| None detected | No clear structural event. | ×1.00 |

Multiplier magnitude scales with **strength** — how far price cleared the level relative to ATR (0–100%).

**Conflict detection:** If the structural sequence direction contradicts the momentum group majority (EMA50 + DMI + MACD), the multiplier is forced to ×0.00. Score is zeroed. Label becomes **CF (Conflict)**. No alert fires. The system treats structure-momentum disagreement as a non-tradeable state.

**Final score maximum: ±7.15** (after BOS ×1.30 at full ADX weight)

**Regime-aware label thresholds:**

| Regime | Strong Buy/Sell threshold | Buy/Sell threshold |
|---|---|---|
| Risk-On / Risk-Off | ±4.5 | ±3.0 |
| Ranging / Mixed | ±5.5 | ±4.0 |

---

## Currency Strength Model

ATR-adjusted, multi-timeframe weighted model across 15 observation pairs.

**Weighting:** D1 × 0.7 + H4 × 0.3. For each pair: compute % return over 14 bars, divide by ATR(14) to normalise for volatility.

**Strength pairs (drive the 0–100 score):**

| Category | Pairs |
|---|---|
| USD base | EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD |
| JPY crosses | AUDJPY, NZDJPY, CADJPY |
| Cross-validation | EURGBP, EURCHF, GBPCHF |

**Coverage per currency:**

| Currency | Observation count | Pairs |
|---|---|---|
| USD | 7 | All USD base pairs |
| JPY | 6 | USDJPY, EURJPY, GBPJPY, AUDJPY, NZDJPY, CADJPY |
| EUR | 4 | EURUSD, EURJPY, EURGBP, EURCHF |
| GBP | 4 | GBPUSD, GBPJPY, EURGBP, GBPCHF |
| AUD / NZD / CAD / CHF | 2–3 each | Respective pairs |

EURGBP, EURCHF, and GBPCHF contribute to strength scores but are not scanned for signals or shown in the correlation matrix.

---

## Market Regime

Proxy detector using existing data — zero additional API calls.

Five signals vote for Risk-On or Risk-Off:

| Signal | Source | Weight |
|---|---|---|
| Safe-haven divergence: (JPY+CHF)/2 − (AUD+NZD+CAD)/3 | CSM rankings | ×2 |
| USD proxy: USD-long avg − USD-short avg | D1 pair scores | ×2 |
| Risk basket: avg of AUDUSD, NZDUSD, GBPJPY, EURJPY, AUDJPY, NZDJPY | D1 pair scores | ×1 |
| Gold direction | XAUUSD D1 score | ×1 |
| Volatility modifier | Average ADX | Scales all votes |

**Override rule:** when average ADX > 30, confidence is halved and H4 data replaces D1. Reverts below ADX 22 (hysteresis). Output includes regime label, confidence (High/Medium/Low), data source (D1/H4), vol ratio, and all 10 signal values.

**Ranging detection:** if trend ratio < 40% and CSM dispersion < 25, regime is classified as Ranging regardless of directional votes.

---

## Correlation

Pairwise Pearson correlation of 50-bar H4 returns across all 12 tradeable pairs. Updated every 4 hours on the H4 scan. Displayed as an interactive lollipop chart — tap any pair button to see its correlation with all other 11 pairs.

---

## Shortlist Logic

1. Collect all pairs with score ≥ 3 or ≤ −3 (directional signal)
2. Sort by absolute score descending, ADX as tiebreaker
3. Walk the ranked list — add each pair unless it correlates > 70% with an already-selected pair in the same direction
4. Display top picks and list what was dropped with the correlation value

---

## Alert Format (Telegram)

```
🟢 BUY AUDUSD

D1: Strong Buy  |  H4: Strong Buy  |  H1: Buy

ADX: 44.4  |  ATR: Normal
Structure: BOS (bull, strength 74%, ×1.28)
Session: Sydney
Regime: Risk-On (Medium)

📰 "AUD surges on risk recovery" — DailyFX
✅ No high-impact events in next 12h.

📊 Dashboard →
```

When a **Conflict** is present:
```
⚠️ Conflict: Structure contradicts momentum — treat with caution
```

---

## AI Workflow

**Per-signal prompt** — tap *Copy Prompt* on any signal card. Paste into Claude.ai with web search enabled. Prompt includes pair, direction, all three timeframe labels, ADX, ATR, extension flag, structure event, conflict flag, and regime. Claude returns a 40-word verdict: Regime / Edge or Flaw / Verdict.

**Market Brief prompt** — tap *Copy Prompt* inside the Market Brief drawer. Prompt includes full CSM rankings, all non-neutral pair scores, regime signal values, conflict pairs, ranked shortlist with correlation reasoning. Claude searches current VIX, DXY, SPX, WTI, Copper, BTC, US10Y and returns a structured 100-word output: regime classification, key driver, 9-pair bias table, one caution, shortlist confirmation or adjustment.

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

### 6. Seed data (run in this order)

1. Actions → D1 Scan + Deploy Dashboard → Run workflow
2. Actions → H4 Scan + Deploy Dashboard → Run workflow
3. Actions → H1 Scan → Run workflow

H1 and H4 will exit immediately if run during weekend hours (Friday 22:00 – Sunday 22:00 UTC). Run D1 any time — it always executes.

---

## File Structure

```
config/
  pairs.py                # 12 tradeable pairs + CSM extras, sessions, session-pair mapping

scanner/
  fetch.py                # Twelvedata OHLCV fetcher with batching and rate-limit handling
  score.py                # 3-component scoring engine + ADX graduated weight + structure multiplier
  structure.py            # BOS/CHOCH event detection with configurable swing pivot lookback
  csm.py                  # ATR-adjusted currency strength (15 strength pairs, 3 CSM-only)
  correlate.py            # 12×12 Pearson correlation matrix from H4 returns
  regime.py               # 6-signal proxy regime detector with hysteresis and H4 override
  levels.py               # Swing high/low support/resistance detection
  cooldown.py             # 4-hour per-pair alert cooldown guard
  scan_h1.py              # H1 scan runner — D1+H4+H1 confluence gate
  scan_h4.py              # H4 scan runner — D1+H4 gate, runs correlation matrix
  scan_d1.py              # D1 scan runner — fetches CSM extras, computes strength and regime

alerts/
  news.py                 # RSS headlines (DailyFX, MarketPulse, FXStreet) + ForexFactory calendar
  telegram.py             # Message builder + Telegram sender (structure/conflict fields included)
  log.py                  # alerts.json writer (structure, conflict, regime fields)

dashboard/
  index.html              # Single-file dashboard — all five tabs, all JS inline

data/                     # Auto-committed JSON outputs
  h1_scores.json          # H1 scores with label, direction, signals, raw values, filter_ok
  h4_scores.json          # H4 scores + conflict, structure, adx_weight fields
  d1_scores.json          # D1 scores + conflict, structure, adx_weight fields
  csm.json                # Currency strength rankings + confidence + per-pair breakdown
  alerts.json             # Alert log (last 100) with structure, conflict, regime fields
  regime.json             # Regime label, confidence, data source, vol ratio, signal values
  correlation.json        # 12×12 Pearson matrix + pair labels + timestamp

state/
  cooldown.json           # Per-pair cooldown state

.github/workflows/
  scan_h1.yml
  scan_h4.yml
  scan_d1.yml

requirements.txt          # pandas, numpy, requests (all standard, no TA libraries)
```

---

## API Budget

| Resource | Usage |
|---|---|
| Twelvedata daily limit | 800 requests/day |
| Current usage (12 pairs + CSM extras) | ~430 requests/day |
| Headroom | ~46% |

The D1 scan fetches 15 pairs (12 tradeable + 3 CSM extras) on D1, then 14 pairs on H4 for CSM. The H4 scan fetches 12 pairs. The H1 scan fetches 12 pairs. All fetching uses automatic 8-symbol batching with 61-second delays and retry logic for 429 errors.

---

## Cost

| Service | Cost |
|---|---|
| Twelvedata API | Free |
| GitHub Actions | Free |
| GitHub Pages | Free |
| Telegram | Free |
| Anthropic API | Not required (AI prompts paste into Claude.ai) |

**Total running cost: $0/month**
