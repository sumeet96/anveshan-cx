# Build Plan — Anveshan Review & CX Intelligence (as built)

A ~24h prototype: ingest public Amazon ghee reviews → LLM theme/sentiment → pandas
trends/alerts → auto founder brief → Streamlit dashboard. Non-negotiables: prototype
framing, dated snapshot (no live scrape), LLM only tags/summarises existing rows
(never invents), no product purity/quality/health claims, secrets in `.env`.

## Key decisions
- **Snapshot:** 300 raw blocks → 297 clean rows; one product line (Anveshan A2 Cow
  Ghee) across 5 size variants; 2021-07 → 2026-06.
- **Prompts as files:** `prompts/{parse,enrich,brief}_prompt.txt` with `[SYSTEM]`/
  `[USER]` blocks, loaded by `src/promptlib.py`. User authors the prompts.
- **Engine:** OpenAI `gpt-4o-mini` (configurable). Processed artifacts committed so the
  dashboard runs key-free; enrich is cached.
- **Trends monthly; comparison + alerts use the last COMPLETE month** (partial snapshot
  month excluded from deltas). Alerts = monthly negative-theme spike vs trailing
  3-month baseline (weekly was too sparse).
- **Stats are scoped** (`overall` / `current_month_stats` / `previous_month_stats`) so
  the brief can't conflate snapshot-wide totals with one month's counts.

## Phases (all complete)
0. **Scaffold** — `config.py` (snapshot date, SKU map, taxonomy), `requirements.txt`,
   `.gitignore` (ignores `.env`), `.env.example`.
1. **ingest.py** — `parse_reviews(raw_text, product_name, asin, collected_on)`: split
   blocks (anchor on the rating line) → LLM extract (batches of 12, temp 0) → strip
   fences + `json.loads` → Python post-process (review_id, ISO date, **faithfulness
   guard**: body must be a verbatim substring; size parsed deterministically from the
   `Size:` line → derive asin via SKU_MAP) → `reviews.csv`. Verified: 297 rows, correct
   sizes/dates/verified/helpful_votes, verbatim multilingual bodies.
2. **enrich.py** — LLM theme(s)+sentiment+evidence per the fixed taxonomy; Python
   verifies theme ∈ taxonomy, sentiment valid, `review_id` matches input, and evidence
   is a verbatim substring (else null) → `reviews_enriched.csv` (+ cache). Verified.
3. **analyze.py** — pandas only: `stats.json` (scoped blocks + top_rising_negative_theme
   + alerts), `trends.csv`, `alerts.json`. Verified (2 real alerts: taste_quality,
   packaging_leakage).
4. **brief.py** — narrates `stats.json` → `brief.md`; **number-guard** flags any figure
   not in the stats. `generate_brief()` exposed for an n8n/Make hook. Verified.
5. **pipeline.py** — `python -m src.pipeline` runs all four; reuses the enrich cache.
6. **app.py** — Streamlit: provenance banner, KPIs, alerts panel, founder brief, and a
   filtered Explore section (rating/volume/sentiment trends, themes, per-SKU, samples).
   Reads processed artifacts only. Data ops verified on the real artifacts.
7. **README.md** — prototype framing, provenance, honesty guards, run steps, the
   live-ingestion swap, and the n8n/Make hook.

## Verify end-to-end
`pip install -r requirements.txt` → add key to `.env` → put prompts in `prompts/` →
`python -m src.pipeline` → `python -m streamlit run app.py`. No marketplace network
calls; every brief figure traces to `stats.json`; all surfaces show the 2026-06-24
snapshot framing.
