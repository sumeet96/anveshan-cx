"""
src/enrich.py
=============
LLM theme + sentiment classification (classify-only; never invents facts).

Sends batches of {review_id, rating, title, body} to the model using the
[SYSTEM]/[USER] prompt in prompts/enrich_prompt.txt, then verifies in Python that:
  * every returned review_id matches an input review_id (unknown ids dropped & flagged);
  * every theme is in the allowed taxonomy (invalid labels dropped & flagged);
  * sentiment is one of the allowed values (else set to neutral & flagged);
  * each evidence phrase is a VERBATIM substring of its review body (else nulled & flagged).
Results are cached by review_id so re-runs cost nothing.

Run:
  python -m src.enrich --limit 15     # cheap test on the first 15 reviews
  python -m src.enrich                 # full run -> data/processed/reviews_enriched.csv
"""
from __future__ import annotations

import argparse
import json
import re

import pandas as pd

from . import config, llm
from .promptlib import load_prompt

ALLOWED_THEMES = set(config.THEMES)
ALLOWED_SENTIMENT = set(config.SENTIMENTS)


def _norm(s: str) -> str:
    # whitespace-normalised + lower-cased, so the evidence substring check ignores case
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _flag(msg: str) -> None:
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(config.PARSE_FAILURES_LOG, "a", encoding="utf-8") as fh:
        fh.write("[enrich] " + msg.rstrip() + "\n")


def _classify_batch(batch, system, user_template, model):
    user = user_template.replace("{reviews_json}", json.dumps(batch, ensure_ascii=False))
    return llm.loads_array(llm.chat(system, user, model=model, temperature=0))


def enrich(df, model=None, batch_size=15, use_cache=True):
    """Return df + columns: themes (JSON list), sentiment, evidence."""
    model = model or config.OPENAI_ENRICH_MODEL
    system, user_template = load_prompt(config.PROMPTS_DIR / "enrich_prompt.txt")

    results = {}
    if use_cache and config.ENRICH_CACHE.exists():
        results = json.loads(config.ENRICH_CACHE.read_text(encoding="utf-8"))

    bodies = {str(rid): body for rid, body in zip(df["review_id"], df["body"])}
    todo = [r for r in df.to_dict("records") if str(r["review_id"]) not in results]

    for start in range(0, len(todo), batch_size):
        chunk = todo[start:start + batch_size]
        batch = [{
            "review_id": str(r["review_id"]),
            "rating": int(r["rating"]) if pd.notna(r.get("rating")) else None,
            "title": r["title"] if pd.notna(r.get("title")) else None,
            "body": r["body"],
        } for r in chunk]
        input_ids = {b["review_id"] for b in batch}

        try:
            objs = _classify_batch(batch, system, user_template, model)
        except Exception as exc:  # noqa: BLE001 — log and continue
            _flag(f"batch starting {start} failed: {exc}")
            continue

        returned = set()
        for obj in objs:
            rid = str(obj.get("review_id"))
            returned.add(rid)
            if rid not in input_ids:
                _flag(f"unknown review_id {rid!r} returned; dropped")
                continue
            raw_themes = obj.get("themes") or []
            themes = [t for t in raw_themes if t in ALLOWED_THEMES]
            if len(themes) != len(raw_themes):
                _flag(f"{rid}: dropped invalid themes {[t for t in raw_themes if t not in ALLOWED_THEMES]}")
            if not themes:
                themes = ["other"]
            sentiment = obj.get("sentiment")
            if sentiment not in ALLOWED_SENTIMENT:
                _flag(f"{rid}: invalid sentiment {sentiment!r} -> neutral")
                sentiment = "neutral"
            evidence = obj.get("evidence")
            if evidence and _norm(evidence) not in _norm(bodies.get(rid, "")):
                _flag(f"{rid}: evidence not a verbatim substring; nulled ({str(evidence)[:60]!r})")
                evidence = None
            results[rid] = {"themes": themes, "sentiment": sentiment, "evidence": evidence}

        for rid in input_ids - returned:
            _flag(f"{rid}: no classification returned")

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    config.ENRICH_CACHE.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")

    out = df.copy()
    out["themes"] = out["review_id"].map(
        lambda x: json.dumps(results.get(str(x), {}).get("themes", []), ensure_ascii=False))
    out["sentiment"] = out["review_id"].map(lambda x: results.get(str(x), {}).get("sentiment"))
    out["evidence"] = out["review_id"].map(lambda x: results.get(str(x), {}).get("evidence"))
    return out


def main(argv=None):
    from dotenv import load_dotenv
    load_dotenv(config.BASE_DIR / ".env")
    ap = argparse.ArgumentParser(description="Classify reviews -> reviews_enriched.csv")
    ap.add_argument("--limit", type=int, default=None, help="only classify the first N reviews")
    ap.add_argument("--no-cache", action="store_true", help="ignore the enrich cache")
    args = ap.parse_args(argv)

    df = pd.read_csv(config.REVIEWS_CSV)
    if args.limit:
        df = df.head(args.limit)
    out = enrich(df, use_cache=not args.no_cache)
    out.to_csv(config.REVIEWS_ENRICHED_CSV, index=False, encoding="utf-8")
    print(f"wrote {len(out)} rows -> {config.REVIEWS_ENRICHED_CSV}")
    print("\nsentiment:\n" + out["sentiment"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
