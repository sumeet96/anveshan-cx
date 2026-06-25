"""
src/ingest.py
=============
LLM-assisted extraction of the dated Amazon review snapshot into a clean table.

Provenance / honesty (see CLAUDE.md):
  * Reads ONLY local raw text passed in (no live marketplace scraping).
  * The LLM extracts structured fields from review blocks and is instructed to copy
    text VERBATIM. A Python *faithfulness guard* then requires each returned `body`
    to be a whitespace-normalised substring of its source block; otherwise the row is
    flagged in data/processed/parse_failures.log and dropped, never kept silently.
  * Every row is stamped with `source` + `collected_on` (the snapshot date).

Run:
  python -m src.ingest --blocks-only     # split & count blocks (no API key needed)
  python -m src.ingest --limit 12        # cheap LLM test on the first 12 blocks
  python -m src.ingest                    # full run -> data/processed/reviews.csv
"""
from __future__ import annotations

import argparse
import re

from . import config, llm
from .promptlib import load_prompt

# --------------------------------------------------------------------------- #
# PARSE_PROMPT  (USER-SUPPLIED, lives in prompts/parse_prompt.txt)
# --------------------------------------------------------------------------- #
# The prompt is split into [SYSTEM] / [USER] blocks; the [USER] block must contain
# a {blocks} token which ingest fills with the numbered review blocks. ingest
# refuses to run while the file still holds the "<<PASTE" placeholder text.
PARSE_PROMPT_FILE = config.PROMPTS_DIR / "parse_prompt.txt"
_PLACEHOLDER = "<<PASTE"

# --------------------------------------------------------------------------- #
# Block splitting  (prompt-independent, stdlib only)
# --------------------------------------------------------------------------- #
_RATING_ANCHOR = re.compile(r"^\s*[1-5]\.0 out of 5 stars\b")
_SEPARATOR = re.compile(r"^\s*-{3,}\s*$")


def split_blocks(raw_text: str) -> list[str]:
    """Split raw snapshot text into one string per review block.

    1. If explicit '---' separator lines are present (added when pasting), split on them.
    2. Otherwise anchor on the 'X.0 out of 5 stars' rating line: each block begins at the
       nearest non-empty line *above* an anchor (the reviewer name) and runs up to just
       before the next block. This keeps multi-paragraph / blank-line bodies intact and
       skips the leading product 'Legend' (everything before the first anchor).
    """
    lines = raw_text.splitlines()

    # 1) explicit separators (require several, so a stray '---' in a body can't trigger)
    if sum(1 for ln in lines if _SEPARATOR.match(ln)) >= 5:
        blocks, current = [], []
        for ln in lines:
            if _SEPARATOR.match(ln):
                if current:
                    blocks.append("\n".join(current).strip())
                    current = []
            else:
                current.append(ln)
        if current:
            blocks.append("\n".join(current).strip())
        return [b for b in blocks if b]

    # 2) rating-anchor fallback
    anchor_idx = [i for i, ln in enumerate(lines) if _RATING_ANCHOR.match(ln)]
    if not anchor_idx:
        return []

    starts = []
    for a in anchor_idx:
        j = a - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        starts.append(j if j >= 0 else a)

    bounds = starts + [len(lines)]
    blocks = []
    for k in range(len(starts)):
        text = "\n".join(lines[bounds[k]:bounds[k + 1]]).strip()
        if text:
            blocks.append(text)
    return blocks


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _to_iso_date(raw):
    if not raw:
        return None
    from dateutil import parser as dateparser  # lazy import
    try:
        return dateparser.parse(str(raw), dayfirst=True).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _normalise_size(raw):
    if not raw:
        return None
    m = re.search(r"([0-9]*\.?[0-9]+)\s*L", str(raw), re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    return f"{int(val)}L" if val == int(val) else f"{val}L"


def _size_from_block(block):
    """Pull the size variant from a block's 'Size:' line (deterministic, no LLM)."""
    m = re.search(r"Size:\s*([0-9]*\.?[0-9]+\s*L)", block or "", re.IGNORECASE)
    return _normalise_size(m.group(1)) if m else None


# --------------------------------------------------------------------------- #
# LLM call + response parsing
# --------------------------------------------------------------------------- #
def _extract_batch(blocks, model, product_name, asin, collected_on):
    system, user_t = load_prompt(PARSE_PROMPT_FILE)
    if _PLACEHOLDER in system or _PLACEHOLDER in user_t:
        raise RuntimeError(
            "prompts/parse_prompt.txt still contains a placeholder — paste your parse "
            "prompt before running ingest."
        )
    joined = "\n\n---\n\n".join(blocks)
    user = (user_t
            .replace("{product_name}", product_name)
            .replace("{asin}", asin)
            .replace("{collected_on}", collected_on))
    for token in ("{raw_blocks}", "{blocks}"):  # support either block placeholder
        if token in user:
            user = user.replace(token, joined)
            break
    else:
        user = f"{user}\n\n{joined}"
    return llm.loads_array(llm.chat(system, user, model=model, temperature=0))


# --------------------------------------------------------------------------- #
# Main extraction
# --------------------------------------------------------------------------- #
OUTPUT_COLUMNS = [
    "review_id", "product_name", "asin", "size", "rating",
    "review_date", "review_date_raw", "title", "body",
    "verified_purchase", "helpful_votes", "source", "collected_on",
]


def parse_reviews(raw_text, product_name, asin, collected_on,
                  model=None, source=None, batch_size=12, limit=None):
    """Parse raw snapshot text into a DataFrame of clean review rows.

    `asin` / `product_name` are fallbacks; the actual values are derived per-row from
    the extracted `size` via config.SKU_MAP so a single call covers all size variants.
    """
    import pandas as pd  # lazy import

    model = model or config.OPENAI_INGEST_MODEL
    source = source or config.SOURCE_NAME
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    def log_failure(msg: str) -> None:
        with open(config.PARSE_FAILURES_LOG, "a", encoding="utf-8") as fh:
            fh.write(msg.rstrip() + "\n")

    blocks = split_blocks(raw_text)
    if limit:
        blocks = blocks[:limit]

    records, n = [], 0
    for start in range(0, len(blocks), batch_size):
        batch = blocks[start:start + batch_size]
        try:
            objs = _extract_batch(batch, model, product_name, asin, collected_on)
        except Exception as exc:  # noqa: BLE001 — log and continue, never crash the run
            log_failure(f"[batch {start}-{start + len(batch) - 1}] LLM/JSON failure: {exc}")
            continue

        if len(objs) != len(batch):
            log_failure(
                f"[batch {start}-{start + len(batch) - 1}] count mismatch: "
                f"{len(objs)} objs vs {len(batch)} blocks (aligning by index)"
            )

        for obj, block in zip(objs, batch):
            body = (obj.get("body") or "").strip()
            if not body:
                continue  # drop empty-body rows

            # Faithfulness guard: returned body must be a verbatim substring of its source.
            if _normalise_ws(body) not in _normalise_ws(block):
                log_failure(
                    "[faithfulness] body is not a verbatim substring of its source block; "
                    f"flagged for manual review.\n  BODY : {body[:200]!r}\n  BLOCK: {block[:200]!r}"
                )
                continue

            size = _size_from_block(block)
            sku = config.SKU_MAP.get(size)
            row_asin = sku["asin"] if sku else asin
            row_product = sku["product_name"] if sku else product_name

            try:
                rating = int(obj.get("rating")) if obj.get("rating") is not None else None
            except (TypeError, ValueError):
                rating = None
            try:
                helpful = int(obj.get("helpful_votes") or 0)
            except (TypeError, ValueError):
                helpful = 0

            date_raw = obj.get("review_date")
            records.append({
                "review_id": obj.get("review_id") or f"{row_asin}-{n}",
                "product_name": row_product,
                "asin": row_asin,
                "size": size,
                "rating": rating,
                "review_date": _to_iso_date(date_raw),
                "review_date_raw": date_raw,
                "title": (obj.get("title") or "").strip() or None,
                "body": body,
                "verified_purchase": bool(obj.get("verified_purchase")),
                "helpful_votes": helpful,
                "source": source,
                "collected_on": collected_on,
            })
            n += 1

    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_report(df) -> None:
    print(f"\nwrote {len(df)} rows -> {config.REVIEWS_CSV}")
    if df.empty:
        return
    print("\nrating histogram:\n" + df["rating"].value_counts(dropna=False).sort_index().to_string())
    print("\nsize distribution:\n" + df["size"].value_counts(dropna=False).to_string())
    dates = df["review_date"].dropna()
    if len(dates):
        print(f"\ndate range: {dates.min()} -> {dates.max()}")
    print(f"unparsed dates: {int(df['review_date'].isna().sum())}")
    if config.PARSE_FAILURES_LOG.exists():
        print(f"\nsee {config.PARSE_FAILURES_LOG} for any flagged rows")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Ingest the review snapshot -> data/processed/reviews.csv")
    ap.add_argument("--limit", type=int, default=None, help="only parse the first N blocks (cheap test)")
    ap.add_argument("--blocks-only", action="store_true", help="just split & count blocks; no LLM calls")
    args = ap.parse_args(argv)

    raw_text = config.RAW_SNAPSHOT.read_text(encoding="utf-8")

    if args.blocks_only:
        blocks = split_blocks(raw_text)
        print(f"blocks found: {len(blocks)}")
        if blocks:
            print("\n--- first block ---\n" + blocks[0][:400])
            print("\n--- last block ---\n" + blocks[-1][:400])
        return

    from dotenv import load_dotenv  # lazy import
    load_dotenv(config.BASE_DIR / ".env")

    df = parse_reviews(
        raw_text,
        product_name=config.PRODUCT_NAME,
        asin=config.DEFAULT_ASIN,
        collected_on=config.SNAPSHOT_DATE,
        limit=args.limit,
    )
    config.REVIEWS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.REVIEWS_CSV, index=False, encoding="utf-8")
    _print_report(df)


if __name__ == "__main__":
    main()
