"""
src/analyze.py
==============
Pandas computes ALL trends, metrics and alerts here. There is NO LLM in this file.

It writes a fully pre-computed `stats.json` that brief.py simply narrates, so every
figure in the founder brief traces back to the data. Also writes trends.csv (for the
dashboard charts) and alerts.json.

stats.json contains: date_range, total_reviews, current/previous period labels,
avg_rating (+ prev + overall), sentiment_split (+ overall), theme_counts (+ prev +
overall), top_rising_negative_theme (with delta), and alerts (weekly negative-theme
spikes over threshold).

Run:  python -m src.analyze
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from . import config

NEGATIVE_THEMES = [t for t in config.THEMES if t != "other"]


def _load_enriched():
    df = pd.read_csv(config.REVIEWS_ENRICHED_CSV)
    df["themes_list"] = df["themes"].apply(
        lambda s: json.loads(s) if isinstance(s, str) and s.strip() else [])
    df["date"] = pd.to_datetime(df["review_date"], errors="coerce")
    return df


def _explode(frame):
    ex = frame.explode("themes_list").rename(columns={"themes_list": "theme"})
    return ex[ex["theme"].notna()]


def _avg_rating(frame):
    m = frame["rating"].mean()
    return round(float(m), 2) if pd.notna(m) else None


def _counts(series):
    return {str(k): int(v) for k, v in series.value_counts().items()}


def compute_alerts(dated, current_month):
    """Monthly negative-theme spikes: last complete month vs trailing baseline."""
    neg = _explode(dated[dated["sentiment"] == "negative"]).copy()
    if neg.empty or current_month is None:
        return []
    months = sorted(m for m in dated["month"].unique() if m < current_month)
    baseline_months = months[-config.ALERT_BASELINE_MONTHS:]
    if not baseline_months:
        return []
    alerts = []
    for theme in NEGATIVE_THEMES:
        by_month = neg[neg["theme"] == theme]["month"].value_counts().to_dict()
        current = int(by_month.get(current_month, 0))
        baseline = sum(by_month.get(m, 0) for m in baseline_months) / len(baseline_months)
        if current >= config.ALERT_MIN_VOLUME and (current - baseline) / max(baseline, 1) >= config.ALERT_THRESHOLD:
            alerts.append({
                "theme": theme, "month": current_month, "current": current,
                "baseline": round(baseline, 2), "delta": round(current - baseline, 2),
                "baseline_months": baseline_months,
            })
    return alerts


def compute_stats(df):
    dated = df.dropna(subset=["date"]).copy()
    dated["month"] = dated["date"].dt.to_period("M").astype(str)
    snapshot_month = config.SNAPSHOT_DATE[:7]
    months = sorted(dated["month"].unique())
    complete = [m for m in months if m < snapshot_month]  # drop the partial snapshot month
    current = complete[-1] if complete else (months[-1] if months else None)
    previous = complete[-2] if len(complete) >= 2 else None

    cur_df = dated[dated["month"] == current]
    prev_df = dated[dated["month"] == previous] if previous else dated.iloc[0:0]

    def theme_counts(frame):
        return _counts(_explode(frame)["theme"]) if len(frame) else {}

    def neg_theme_counts(frame):
        return _explode(frame[frame["sentiment"] == "negative"])["theme"].value_counts().to_dict()

    ncur, nprev = neg_theme_counts(cur_df), neg_theme_counts(prev_df)
    rising, best = None, 0
    for theme in NEGATIVE_THEMES:
        delta = int(ncur.get(theme, 0)) - int(nprev.get(theme, 0))
        if delta > best:
            best = delta
            rising = {"theme": theme, "delta": delta,
                      "current": int(ncur.get(theme, 0)), "previous": int(nprev.get(theme, 0))}

    dts = df["date"].dropna()
    date_range = f"{dts.min().date()} to {dts.max().date()}" if len(dts) else "n/a"

    def month_stats(frame, label):
        return {
            "month": label,
            "review_count": int(len(frame)),
            "avg_rating": _avg_rating(frame),
            "sentiment_counts": _counts(frame["sentiment"]),
            "theme_counts": theme_counts(frame),
        }

    # Clearly-scoped blocks so a narrator can't conflate snapshot-wide totals with a
    # single month's counts (e.g. "negative fell from 204 to 20").
    return {
        "snapshot_date": config.SNAPSHOT_DATE,
        "product_scope": f"{config.PRODUCT_NAME} ({len(config.SKU_MAP)} size variants)",
        "date_range": date_range,
        "total_reviews": int(len(df)),
        "current_month": current,
        "previous_month": previous,
        "excludes_partial_month": snapshot_month if snapshot_month in months else None,
        "overall": {
            "avg_rating": _avg_rating(df),
            "sentiment_counts": _counts(df["sentiment"]),
            "theme_counts": theme_counts(dated),
        },
        "current_month_stats": month_stats(cur_df, current),
        "previous_month_stats": month_stats(prev_df, previous),
        "top_rising_negative_theme": rising,
        "alerts": compute_alerts(dated, current),
    }


def build_trends(df):
    dated = df.dropna(subset=["date"]).copy()
    dated["period"] = dated["date"].dt.to_period("M").astype(str)
    rows = []
    for (period, theme), c in _explode(dated).groupby(["period", "theme"]).size().items():
        rows.append({"period": period, "series": f"theme:{theme}", "value": int(c)})
    for period, sub in dated.groupby("period"):
        rows.append({"period": period, "series": "rating_avg", "value": _avg_rating(sub)})
        rows.append({"period": period, "series": "volume", "value": int(len(sub))})
        for s, c in sub["sentiment"].value_counts().items():
            rows.append({"period": period, "series": f"sentiment:{s}", "value": int(c)})
    return pd.DataFrame(rows).sort_values(["period", "series"]).reset_index(drop=True)


def main(argv=None):
    argparse.ArgumentParser(description="Compute trends/alerts/stats (pandas only)").parse_args(argv)
    df = _load_enriched()
    stats = compute_stats(df)
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    config.STATS_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    config.ALERTS_JSON.write_text(json.dumps(stats["alerts"], ensure_ascii=False, indent=2), encoding="utf-8")
    build_trends(df).to_csv(config.TRENDS_CSV, index=False, encoding="utf-8")
    print(f"wrote {config.STATS_JSON}\n      {config.ALERTS_JSON}\n      {config.TRENDS_CSV}")
    print("\nstats preview:\n" + json.dumps(stats, ensure_ascii=False, indent=2)[:1800])


if __name__ == "__main__":
    main()
