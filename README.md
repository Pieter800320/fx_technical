# Forex1212

A fully automated FX analysis dashboard built on a free infrastructure stack. Multi-timeframe technical scoring, AI-powered narrative and edge scoring, currency strength modelling, Telegram alerts, and a mobile-first trading journal — all running on GitHub Actions, GitHub Pages, and the Anthropic API.

**Live:** [pieter800320.github.io/fx_technical](https://pieter800320.github.io/fx_technical)

---

## Architecture

```
GitHub Actions (5 scheduled workflows)
    │
    ├── scan_h1.py      → H1 technical scores
    ├── scan_h4.py      → H4 scores + CSM + correlation + regime
    ├── scan_d1.py      → D1 scores
    ├── scan_news.py    → macro data + Claude AI pipeline
    └── scan_alerts.py  → Telegram alert dispatcher (called by H4)
         │
         ▼
    data/*.json  →  dashboard/*.json  →  GitHub Pages
                                              │
                                              ▼
                                    dashboard/index.html
                                    (single-file PWA)
```

### Scan Schedule

| Workflow | Schedule (UTC) | Outputs |
|---|---|---|
| `scan_h1.yml` | Hourly | `h1_scores.json` |
| `scan_h4.yml` | Every 4h at :25 | `h4_scores.json`, `csm.json`, `correlation.json`, `regime.json` (h4 key) |
| `scan_d1.yml` | Daily 00:00 | `d1_scores.json`, `regime.json` (D1 signals) |
| `scan_news.yml` | 05/09/13/17 UTC | `news_brief.json`, `regime.json` (macro + AI + final_regime) |
| `scan_alerts.yml` | Called by H4 | Telegram messages |

---

## Pairs Covered

| # | Pair | # | Pair |
|---|---|---|---|
| 1 | EUR/USD | 7 | NZD/USD |
| 2 | GBP/USD | 8 | EUR/JPY |
| 3 | USD/JPY | 9 | GBP/JPY |
| 4 | USD/CHF | 10 | AUD/JPY |
| 5 | AUD/USD | 11 | NZD/JPY |
| 6 | USD/CAD | 12 | CAD/JPY |

---

## Setup Score (computeQAI)

The Setup score (0–100%) is the primary ranking signal. It combines 7 orthogonal components. ADX is a hard gate, not a component.

| Component | Weight | Description |
|---|---|---|
| TF Alignment | 28% | D1 + H4 + H1 unified direction |
| Entry Position | 18% | Reset score × 0.6 + ATR percentile × 0.4 |
| CSM Divergence | 16% | H4 base vs quote currency strength gap |
| Regime Fit | 13% | Macro context alignment (risk/growth/haven) |
| Edge (AI) | 12% | Claude cross-source coherence score 1–10 |
| Session Fit | 8% | Active trading session matches pair's optimal window |
| Rate Differential | 5% | Interest rate tailwind in trade direction |

**Hard gates and caps:**
- ADX < 20 → score capped at 45% (no trend, no alert)
- Counter-regime trades (e.g. bullish risk pair in Risk-Off) → score capped at 40–70% depending on pair type

**Regime currency classification:**
- Risk pairs: AUD, NZD, CAD
- Growth pairs: EUR, GBP
- Safe havens: CHF, JPY

---

## Regime System

Three sources combine into one `final_regime`:

```
H4 Structural (40%) + Macro Overlay (40%) + AI Sentiment (20%) = final_regime
```

| Source | Computed by | Method |
|---|---|---|
| H4 Structural | `scan_h4.py` → `regime.py:classify_regime()` | H4 CSM rankings, safe-haven divergence, USD proxy, risk basket |
| Macro Overlay | `scan_news.py:compute_macro_bias()` | VIX/DXY/US2Y/Gold/SPX/Copper each scored +1/0/-1 |
| AI Sentiment | `scan_news.py:call_regime_sentiment()` | Claude Haiku scores news-only risk appetite 1–10 |

If component spread ≥ 4 → `Mixed/Low` regardless of average.

---

## AI Pipeline (scan_news.py)

Four sequential Claude API calls per run:

| Call | Model | Output |
|---|---|---|
| `call_themes()` | Haiku | Structured theme extraction from RSS headlines |
| `call_narrative()` | Sonnet | 5-section FX narrative (Drivers/Price/Regime/Contradictions/Implications) |
| `call_edge_scores()` | Haiku | Edge coherence scores 1–10 for all 12 pairs |
| `call_regime_sentiment()` | Haiku | News-only risk appetite score 1–10 |

**Macro data sources (Yahoo Finance v8 API):**
VIX, DXY, US10Y, US2Y, WTI, Gold, Silver, SPX, BTC, Copper

**News sources (RSS):**
FXStreet, ForexLive, Nasdaq FX

---

## Currency Strength Model (CSM)

Two CSM rankings are maintained:

| Type | Key in csm.json | Source | Used for |
|---|---|---|---|
| D1 Composite | `rankings` | D1 × 0.7 + H4 × 0.3, ATR-adjusted returns | CSM sheet display, historical bias |
| H4 Only | `h4_rankings` | H4 bars only, 5-bar lookback (20h) | Setup score CSM component |

The H4 rankings are preferred in `computeQAI` when available, giving the setup score a current-session bias rather than a daily-close bias.

---

## Session Scoring

Session fit contributes 8% to the Setup score. Optimal sessions per pair:

| Session | Abbr | UTC Window | Best Pairs |
|---|---|---|---|
| Sydney | SY | 22:00–07:00 | AUD/USD, NZD/USD, AUD/JPY, NZD/JPY |
| Tokyo | TK | 23:00–08:00 | USD/JPY, EUR/JPY, GBP/JPY, AUD/JPY, NZD/JPY, CAD/JPY |
| London | LN | 07:00–16:00 | EUR/USD, GBP/USD, USD/CHF, EUR/JPY, GBP/JPY |
| New York | NY | 12:00–21:00 | USD/JPY, USD/CHF, USD/CAD, AUD/USD, NZD/USD, CAD/JPY |
| LN/NY Overlap | LN/NY | 12:00–16:00 | Highest liquidity — all USD majors |

Session match → score 10. No match → score 2. Market closed or no active session → score 3 (neutral).

---

## Telegram Alert Filters

Alerts fire via `scan_alerts.py`, called at the end of each H4 workflow. All conditions must pass:

| Filter | Threshold |
|---|---|
| Setup score | ≥ 70% |
| Edge score | ≥ 7 |
| D1 confirms H4 | D1 direction must match H4 |
| ADX | ≥ 20 |
| ATR | Must be within normal range |
| Conflict signals | None |
| Cooldown | 20h per pair (persisted in `alert_cooldown.json`) |

---

## Data Files

All files live in `data/` (raw) and `dashboard/` (served via Pages).

| File | Written by | Contents |
|---|---|---|
| `h1_scores.json` | scan_h1.py | H1 technical scores per pair |
| `h4_scores.json` | scan_h4.py | H4 scores, ADX, reset score, direction |
| `d1_scores.json` | scan_d1.py | D1 scores, ATR percentile, direction |
| `csm.json` | scan_h4.py | D1 CSM rankings + H4 rankings + breakdown |
| `regime.json` | scan_h4/d1/news | D1 signals, H4 structural, macro_bias, ai_sentiment, final_regime |
| `correlation.json` | scan_h4.py | 12×12 rolling correlation matrix |
| `news_brief.json` | scan_news.py | Narrative, themes, edge_scores, macro values |
| `rates.json` | Manual (frontend) | Central bank policy rates per currency |
| `alert_cooldown.json` | scan_alerts.py | Last alert timestamp per pair |
| `level_alerts.json` | Frontend | User-set price level alerts |
| `conviction.json` | Manual / future | COT-based conviction scores (CSM sheet) |

---

## Frontend (dashboard/index.html)

Single-file PWA. No build step. All data fetched via GitHub raw API with cache-busting.

### Navigation Tabs

| Tab | Contents |
|---|---|
| Home | Drum, signal strips, indicators, quick actions, currency strength |
| Log | Trade journal, statistics, pattern analysis, open trades |
| Corr | Rolling correlation chart per base pair |
| Rates | Policy rate entry, differentials popup |

### Drum

Ranks all 12 pairs by: `Setup% × 0.6 + Edge × 4`

Each row displays: **Pair name · Setup% · Edge · Session abbr**

Session abbreviation is bright when the current session matches the pair's optimal window, dim otherwise. Trade RR bars appear below the text when a trade is active on that pair.

### Signal Strips

**Regime strip** (4 cells): Final regime + confidence + direction | Macro score | AI sentiment | Combined score

**Indicator strip** (4 cells): H4 Regime | D1 % score | Setup% | Edge score

### Sheets (bottom drawers)

All detail views open as bottom sheets from the home screen: Regime breakdown, Pair Summary (QAI), News Brief, Sessions, Live Prices, Charts (fullscreen landscape), Enter Trade, Closed Trades (Log tab), Rates Data (Rates tab).

---

## Stack & Cost

| Component | Service | Cost |
|---|---|---|
| Data scanning | GitHub Actions | Free (2,000 min/month) |
| Dashboard hosting | GitHub Pages | Free |
| OHLCV data | Twelvedata free tier | Free (800 credits/day) |
| Macro data | Yahoo Finance v8 API | Free |
| AI narrative + scoring | Anthropic API | ~$0.10–0.20/day (Haiku + Sonnet) |
| Alerts | Telegram Bot API | Free |

---

## Environment Variables (GitHub Secrets)

| Secret | Used by |
|---|---|
| `TWELVEDATA_API_KEY` | scan_h1, scan_h4, scan_d1 |
| `ANTHROPIC_API_KEY` | scan_news |
| `TELEGRAM_BOT_TOKEN` | scan_alerts |
| `TELEGRAM_CHAT_ID` | scan_alerts |
| `DASHBOARD_URL` | scan_alerts (alert message link) |

---

## Local Development

```bash
git clone https://github.com/Pieter800320/fx_technical.git
cd fx_technical
pip install -r requirements.txt

# Run individual scanners
python scanner/scan_h4.py
python scanner/scan_news.py
python scanner/scan_alerts.py H4

# Serve the dashboard locally
cd dashboard
python -m http.server 8000
# Open http://localhost:8000
```

---

## Key Design Decisions

**Why single-file HTML?** Zero build tooling, zero dependencies, deployable anywhere. The entire frontend is one file that can be opened directly from disk.

**Why GitHub raw API instead of Pages URLs?** Pages has a CDN cache with up to 10-minute TTL. The raw API (`api.github.com/repos/.../contents/...`) serves current committed content immediately, which matters for a live trading dashboard.

**Why H4 CSM over D1 CSM in scoring?** D1 CSM reflects the daily close — it lags intraday shifts by hours. H4 CSM captures the current 20-hour momentum window, which is more relevant to the timeframe you're actually trading.

**Why separate `final_regime` from the D1 structural regime?** The D1 structural regime is a pure price-action signal. `final_regime` incorporates macro data and AI sentiment, making it more forward-looking. They're intentionally kept separate so divergence between them is visible — a useful caution signal.
