"""
src/deliver.py
==============
Deliver the founder brief to where the founder already is (Slack incoming webhook).

This closes the automation loop: a scheduled GitHub Action runs the pipeline, then
calls this to push the brief out. If no SLACK_WEBHOOK_URL is configured it prints the
message (dry-run) so the run log still shows the delivery. Email is an easy swap —
point the formatted message at an SMTP / transactional-email send instead.

Run:
  python -m src.deliver            # posts to Slack if SLACK_WEBHOOK_URL is set
  python -m src.deliver --dry-run  # always just prints the message
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

from . import config


def _load():
    brief = json.loads(config.BRIEF_JSON.read_text(encoding="utf-8")) if config.BRIEF_JSON.exists() else {}
    stats = json.loads(config.STATS_JSON.read_text(encoding="utf-8")) if config.STATS_JSON.exists() else {}
    return brief, stats


def format_message(brief, stats) -> str:
    """Slack-mrkdwn message built from the structured brief + stats (no new numbers)."""
    parts = [f"*Anveshan CX Brief* — snapshot {stats.get('snapshot_date', '?')}  _(PROTOTYPE, not live)_"]
    if brief.get("headline"):
        parts.append(brief["headline"])
    if brief.get("what_changed"):
        parts.append("*What changed*\n" + "\n".join(f"• {x}" for x in brief["what_changed"]))
    if brief.get("what_to_watch"):
        parts.append("*What to watch*\n" + "\n".join(f"• {x}" for x in brief["what_to_watch"]))
    if stats.get("alerts"):
        parts.append("*Alerts*\n" + "\n".join(
            f"• {a['theme']}: {a['current']} vs {a['baseline']}/mo baseline (Δ{a['delta']})"
            for a in stats["alerts"]))
    parts.append(
        f"_window {stats.get('previous_month')}→{stats.get('current_month')} · "
        f"{stats.get('total_reviews')} reviews · figures by pandas, model only narrates_")
    return "\n\n".join(parts)


def deliver(webhook_url=None, dry_run=False) -> bool:
    brief, stats = _load()
    message = format_message(brief, stats)
    webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if dry_run or not webhook_url:
        print("[deliver] no SLACK_WEBHOOK_URL set (dry run) — message below:\n")
        print(message)
        return False
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": message}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"[deliver] posted to Slack (HTTP {resp.status})")
    return True


def main(argv=None):
    import sys
    try:  # ensure non-ASCII (Δ, emoji) prints on a Windows cp1252 console
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    from dotenv import load_dotenv
    load_dotenv(config.BASE_DIR / ".env")
    ap = argparse.ArgumentParser(description="Deliver the founder brief to Slack")
    ap.add_argument("--dry-run", action="store_true", help="print the message instead of posting")
    args = ap.parse_args(argv)
    deliver(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
