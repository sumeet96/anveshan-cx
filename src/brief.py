"""
src/brief.py
============
Narrates the pre-computed stats.json into a short founder brief. The model adds NO
numbers: a Python number-guard checks that every figure in the brief also appears in
the stats object (within a small tolerance) and flags any that does not.

`generate_brief()` is exposed so an external trigger (n8n/Make webhook) can call it.

Run:  python -m src.brief
"""
from __future__ import annotations

import argparse
import json
import re

from . import config, llm
from .promptlib import load_prompt


def _stats_numbers(stats) -> set:
    nums = set()

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            nums.add(round(float(v), 2))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            for m in re.findall(r"-?\d+\.?\d*", v):
                try:
                    nums.add(round(float(m), 2))
                except ValueError:
                    pass

    walk(stats)
    return nums


def check_numbers(brief, stats, tol=0.05):
    """Return numbers used in the brief that are NOT present in the stats."""
    allowed = _stats_numbers(stats)
    text = " ".join([brief.get("headline", "")]
                    + list(brief.get("what_changed", []))
                    + list(brief.get("what_to_watch", [])))
    bad = []
    for m in re.findall(r"-?\d+\.?\d*", text):
        try:
            val = round(float(m), 2)
        except ValueError:
            continue
        if not any(abs(val - a) <= tol for a in allowed):
            bad.append(m)
    return bad


def render_md(brief, stats, bad):
    L = [
        f"# Founder Brief — {stats.get('product_scope', '')}",
        "",
        (f"> **PROTOTYPE.** Every figure below is computed by pandas from a dated snapshot "
         f"of public Amazon reviews collected on {stats.get('snapshot_date')}. Not live data. "
         f"The model only narrates; it computes no numbers."),
        "",
        f"**{brief.get('headline', '')}**",
        "",
        "## What changed",
        *[f"- {s}" for s in brief.get("what_changed", [])],
        "",
        "## What to watch",
        *[f"- {s}" for s in brief.get("what_to_watch", [])],
        "",
        (f"_Comparison: {stats.get('previous_month')} → {stats.get('current_month')} "
         f"(last complete month; partial {stats.get('excludes_partial_month')} excluded from deltas). "
         f"{stats.get('total_reviews')} reviews over {stats.get('date_range')}._"),
    ]
    if bad:
        L += ["", f"> ⚠️ number-guard flagged unverifiable figures {bad} — see parse_failures.log"]
    return "\n".join(L) + "\n"


def generate_brief(model=None):
    """Generate the brief from stats.json; returns (brief_dict, flagged_numbers)."""
    model = model or config.OPENAI_BRIEF_MODEL
    stats = json.loads(config.STATS_JSON.read_text(encoding="utf-8"))
    system, user_t = load_prompt(config.PROMPTS_DIR / "brief_prompt.txt")
    user = (user_t
            .replace("{date_range}", str(stats.get("date_range", "")))
            .replace("{product_scope}", str(stats.get("product_scope", "")))
            .replace("{stats_json}", json.dumps(stats, ensure_ascii=False, indent=2)))
    brief = llm.loads_object(llm.chat(system, user, model=model, temperature=0))

    bad = check_numbers(brief, stats)
    if bad:
        config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
        with open(config.PARSE_FAILURES_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"[brief] numbers not found in stats (possible fabrication): {bad}\n")

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    config.BRIEF_MD.write_text(render_md(brief, stats, bad), encoding="utf-8")
    config.BRIEF_JSON.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    return brief, bad


def main(argv=None):
    from dotenv import load_dotenv
    load_dotenv(config.BASE_DIR / ".env")
    argparse.ArgumentParser(description="Narrate stats.json -> brief.md").parse_args(argv)
    brief, bad = generate_brief()
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    if bad:
        print(f"\n⚠️ number-guard flagged: {bad}")
    print(f"\nwrote {config.BRIEF_MD}")


if __name__ == "__main__":
    main()
