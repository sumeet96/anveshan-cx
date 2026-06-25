# Project: Anveshan Review & CX Intelligence (prototype)

## What this is
A ~24-hour prototype built as a job-application artifact for Anveshan's
Founder's Office (AI & Automation) role. It ingests public marketplace
reviews for Anveshan's top SKUs, tags each review by theme and sentiment,
visualises complaint trends over time, flags spikes, and auto-generates a
short "what changed + what to watch" founder brief.

## The three things it must demonstrate
1. Automate: a pipeline (ingest -> LLM tag/sentiment -> trend/alert -> brief).
2. Illuminate: a dashboard a founder could open and trust.
3. Anticipate: spike detection on negative themes (e.g., leakage, delivery,
   taste, authenticity) with an alerts panel.

## Honesty and scope rules (non-negotiable)
- This is a PROTOTYPE. The README and dashboard must say so plainly.
- Data is a DATED SNAPSHOT of public reviews collected manually on a fixed
  date. Never present snapshot data as live or real-time. The ingestion
  layer must be pluggable (swap snapshot -> live source later).
- Do NOT scrape live marketplace sites in this build. Read from data/raw/.
- The LLM never invents reviews, ratings, or numbers. It only tags and
  summarises rows that exist in the data.
- The tool analyses customer complaints; it must NOT generate any product
  health, purity, or quality claims (brand-trust and FSSAI sensitivity).
- Keep secrets out of git: API keys in .env, provide .env.example only.

## Suggested stack (confirm in planning)
- Python 3.11+, pandas for processing.
- LLM tagging/sentiment + brief: OpenAI API (key via .env). Themes as a
  fixed taxonomy: taste/quality, packaging/leakage, delivery/logistics,
  price/value, authenticity/traceability, customer service, other.
- Dashboard: Streamlit (fast, Python-native, hostable on Streamlit
  Community Cloud for a shareable public link). Static HTML export or
  Power BI are acceptable alternates.
- Alerts: week-over-week deltas per theme with a threshold flag.

## Repo layout (target)
- data/raw/ , data/processed/
- src/ingest.py, src/enrich.py, src/analyze.py, src/brief.py
- app.py (dashboard), README.md, plans/PLAN.md, .env.example

## Definition of done
- One command runs the pipeline end-to-end on the snapshot.
- Dashboard shows: rating trend, theme breakdown, sentiment-over-time,
  alerts panel, and the auto-generated founder brief.
- README explains the prototype framing, data provenance, and how the
  live-ingestion swap would work.