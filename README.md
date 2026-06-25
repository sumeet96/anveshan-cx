# Anveshan Review & CX Intelligence (prototype)

> ⚠️ **PROTOTYPE.** Built in ~24 hours as a job-application artifact for Anveshan's
> Founder's Office (AI & Automation) role. It runs on a **dated, manually-collected
> snapshot** of public Amazon reviews (collected **2026-06-24**). It does **not**
> scrape live marketplaces and makes **no** product purity / quality / health
> claims — it analyses customer-complaint *signals* only.

## What it does
Ingests public marketplace reviews for Anveshan's ghee SKUs, tags each review by
theme + sentiment with an LLM, computes complaint trends and spike alerts with
pandas, and auto-generates a short "what changed + what to watch" founder brief.

Three pillars:
1. **Automate** — one command (or a scheduled GitHub Action) runs
   `ingest → enrich → analyze → brief → deliver`.
2. **Illuminate** — a Streamlit dashboard led by an alert feed, with negative-rate
   by SKU, normalized complaint-theme share, and rolling-window views.
3. **Anticipate** — month-over-month spike detection on negative themes, delivered
   to Slack.

## The data (provenance)
- Source: public **Amazon.in** reviews for **Anveshan A2 Cow Ghee**, across **5 size
  variants** — 0.15L `B0D7VJ8R8W` · 0.5L `B07TMKSC3S` · 1L `B08KJG9VLJ` ·
  2.5L `B0FW5H42TN` · 5L `B0DY813WTD`.
- Collected **manually** on **2026-06-24** into
  `data/raw/amazon_reviews_snapshot_2026-06-24.txt` — a dated snapshot, **not live**.
- 300 raw review blocks → **297 clean rows** (1 dropped by the faithfulness guard,
  2 image/video-only with empty bodies). Date range **2021-07-21 → 2026-06-22**.
- To refresh, collect a new dated snapshot and re-run — the snapshot is never
  presented as real-time.

## Architecture
```
data/raw/<snapshot>.txt
   │  ingest.py    LLM extracts structured fields; Python guard requires each body
   ▼               to be a VERBATIM substring of its source block (else flag + drop)
data/processed/reviews.csv
   │  enrich.py    LLM assigns theme(s) + sentiment from a fixed taxonomy; the
   ▼               evidence phrase must be a verbatim substring (else null + flag)
data/processed/reviews_enriched.csv
   │  analyze.py   pandas computes ALL trends / metrics / alerts — no LLM here
   ▼
stats.json · trends.csv · alerts.json
   │  brief.py     LLM narrates stats.json; a number-guard flags any figure in the
   ▼               brief that is not present in the stats
data/processed/brief.md ──▶ deliver.py ──▶ Slack incoming webhook (or dry-run to log)
   │  app.py       Streamlit dashboard — reads processed artifacts only
   ▼
(dashboard: KPIs · alert feed (centerpiece) · brief · negative-rate by SKU ·
 normalized theme-share · 30-day rolling negatives · per-SKU & date filters)
```
The three prompts live in `prompts/*.txt` as `[SYSTEM]` / `[USER]` blocks
(`parse_prompt.txt`, `enrich_prompt.txt`, `brief_prompt.txt`) and are loaded by
`src/promptlib.py`. Model: OpenAI `gpt-4o-mini` (override via `.env`).

## Honesty & guardrails (non-negotiable)
- **No live scraping.** `ingest` only reads the local raw text you pass it.
- **The LLM never invents data.** Extraction bodies *and* enrichment evidence must be
  **verbatim substrings** of the source or they are flagged and not kept
  (`data/processed/parse_failures.log`).
- **pandas owns every number.** `analyze.py` computes all metrics; `brief.py`'s
  number-guard flags any figure in the brief that is not in `stats.json`.
- **No product claims.** The brief reports complaint *counts and movements* (e.g.
  "N reviews raised authenticity concerns"), never statements about the product's
  purity / quality / health / safety (FSSAI & brand-trust sensitivity).
- **Partial periods are never compared to full ones.** The month-over-month
  comparison and alerts use the last *complete* calendar month; the partial snapshot
  month is shown in the trend chart but excluded from deltas.

## Run it
```bash
pip install -r requirements.txt
cp .env.example .env            # then add your OPENAI_API_KEY
# put your three prompts in prompts/parse_prompt.txt, enrich_prompt.txt, brief_prompt.txt
python -m src.pipeline          # ingest -> enrich -> analyze -> brief
python -m streamlit run app.py  # dashboard  (streamlit.exe may not be on PATH; use `python -m`)
```
The `data/processed/` artifacts are committed, so the dashboard renders **without an
API key**. Re-runs reuse the enrich cache (`python -m src.enrich --no-cache` to force).

Cheap / stage-by-stage checks:
```bash
python -m src.ingest --blocks-only   # split & count review blocks (no key)
python -m src.ingest  --limit 12     # extract the first 12 reviews
python -m src.enrich  --limit 15     # classify the first 15
python -m src.analyze                # pandas only, no key
```

## Going live (the swap)
The pipeline's only coupling to the snapshot is the **`reviews.csv` schema**.
Everything downstream (`enrich` / `analyze` / `brief` / `app`) consumes that schema
and is source-agnostic. To go live, add a connector that pulls reviews from an
approved marketplace API / data source and emits the same `reviews.csv` columns (or
feeds review blocks to `ingest.parse_reviews`), then schedule it. No downstream code
changes. This build intentionally ships only the snapshot source.

## Automation: scheduled brief delivery
`.github/workflows/brief.yml` closes the loop — trigger → run pipeline → deliver:
- **Triggers:** weekly `schedule` (heartbeat), `workflow_dispatch` (manual run), and
  `push` to `data/raw/**` (a new dated snapshot → full re-extract).
- **Delivery:** `python -m src.deliver` (`src/deliver.py`) posts the brief to a
  **Slack** incoming webhook; with no webhook it prints to the run log (dry-run).
  Email is a one-function swap.
- **Secrets** (repo → Settings → Secrets and variables → Actions): `OPENAI_API_KEY`
  (regenerate the brief; without it the job does a stats-only refresh) and
  `SLACK_WEBHOOK_URL` (post to Slack; without it, dry-run). The deployed dashboard
  needs neither.
- The job commits refreshed `data/processed/` back, so the deployed dashboard stays
  in sync.

Honest scope: under the no-scrape rule, the *schedule* re-narrates a fixed snapshot;
the **push-on-new-snapshot** trigger is the meaningful refresh until the ingest source
is swapped to a live connector (the seam is `ingest.parse_reviews`).

## This snapshot at a glance
- 297 reviews · overall avg rating **2.76** · sentiment **204 neg / 67 pos / 26 neu**.
- Top complaint themes: taste_quality (199), authenticity_traceability (83),
  price_value (71), packaging_leakage (60).
- Alerts (last complete month vs trailing 3-mo baseline): **taste_quality** 13 vs
  7.67, **packaging_leakage** 6 vs 2.67.

## Repo layout
```
data/raw/            dated snapshot (input)
data/processed/      reviews.csv, reviews_enriched.csv, enrich_cache.json,
                     stats.json, trends.csv, alerts.json, brief.md, parse_failures.log
prompts/             parse_prompt.txt, enrich_prompt.txt, brief_prompt.txt  ([SYSTEM]/[USER])
src/                 config, promptlib, llm, ingest, enrich, analyze, brief, deliver, pipeline
app.py               Streamlit dashboard
.github/workflows/   brief.yml (scheduled pipeline run + Slack delivery)
```

## Limitations
- Prototype on a single dated snapshot; monthly samples are small (tens of reviews),
  so treat month-over-month deltas as directional, not statistical.
- The evidence guard is strict (exact substring), so it nulls some near-verbatim
  phrases — these are logged, and the row's theme/sentiment are still kept.
- Alerts use monthly buckets; weekly was too sparse on this snapshot to be meaningful.
- Sentiment is judged from the review text, so it can differ from the star rating.
