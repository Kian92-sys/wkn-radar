#!/usr/bin/env python3
"""
Aggregiert data/mentions.jsonl zu wöchentlichen Top-Listen pro WKN und
schreibt data/weekly_data.json -- das render_dashboard.py dann in
docs/index.html einbaut.

Gruppiert nach ISO-Kalenderwoche (Montag-Start, wie in Deutschland ueblich).
"""
import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MAPPING_PATH = os.path.join(BASE_DIR, "data", "wkn_mapping.csv")
MENTIONS_PATH = os.path.join(BASE_DIR, "data", "mentions.jsonl")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "weekly_data.json")

MAX_POSTS_PER_STOCK = 30  # caps dashboard JSON size / popup list length

GERMAN_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mär", 4: "Apr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Dez",
}


def iso_week_key(d: date):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(week_key):
    year, week = week_key.split("-W")
    monday = date.fromisocalendar(int(year), int(week), 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def format_label(week_key):
    monday, sunday = week_bounds(week_key)
    _, week = week_key.split("-W")
    if monday.month == sunday.month:
        span = f"{monday.day}.–{sunday.day}. {GERMAN_MONTHS[sunday.month]} {sunday.year}"
    else:
        span = f"{monday.day}. {GERMAN_MONTHS[monday.month]}–{sunday.day}. {GERMAN_MONTHS[sunday.month]} {sunday.year}"
    return f"KW {int(week)} · {span}"


def load_wkn_info():
    info = {}
    with open(MAPPING_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            wkn = (row.get("wkn") or "").strip()
            if not wkn or wkn in info:
                continue
            info[wkn] = {
                "wkn": wkn,
                "ticker": (row.get("ticker") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "segment": (row.get("segment") or "bluechip").strip(),
            }
    return info


def main():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    retention_weeks = cfg.get("weekly_data_retention_weeks", 10)
    wkn_info = load_wkn_info()

    # counts[week][wkn][subreddit] = n ; daily[week][wkn][date_str] = n
    # posts[week][wkn] = list of {url, subreddit, date, snippet} for the link-popup
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    daily = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    posts = defaultdict(lambda: defaultdict(list))

    if os.path.exists(MENTIONS_PATH):
        with open(MENTIONS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    d = datetime.strptime(m["date"], "%Y-%m-%d").date()
                except (KeyError, ValueError):
                    continue
                wk = iso_week_key(d)
                counts[wk][m["wkn"]][m["subreddit"]] += 1
                daily[wk][m["wkn"]][m["date"]] += 1
                if m.get("url"):
                    posts[wk][m["wkn"]].append({
                        "url": m["url"],
                        "subreddit": m["subreddit"],
                        "date": m["date"],
                        "snippet": m.get("snippet") or "",
                    })

    week_order = sorted(counts.keys(), reverse=True)[:retention_weeks]
    week_labels = {wk: format_label(wk) for wk in week_order}

    weeks_out = {}
    for wk in week_order:
        monday, _ = week_bounds(wk)
        day_seq = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        stocks = []
        for wkn, by_sub in counts[wk].items():
            info = wkn_info.get(wkn, {"wkn": wkn, "ticker": "", "name": wkn, "segment": "bluechip"})
            spark = [daily[wk][wkn].get(day, 0) for day in day_seq]
            wkn_posts = sorted(posts[wk].get(wkn, []), key=lambda p: p["date"], reverse=True)[:MAX_POSTS_PER_STOCK]
            stocks.append({
                "ticker": info["ticker"] or wkn,
                "name": info["name"] or wkn,
                "wkn": wkn,
                "segment": info["segment"],
                "spark": spark,
                "bySubreddit": dict(by_sub),
                "posts": wkn_posts,
            })
        weeks_out[wk] = stocks

    output = {
        "generated_at": datetime.now().strftime("%d.%m.%Y, %H:%M UTC"),
        "subreddits": cfg["subreddits"],
        "week_order": week_order,
        "week_labels": week_labels,
        "weeks": weeks_out,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_stocks = sum(len(v) for v in weeks_out.values())
    print(f"Wochen aggregiert: {len(week_order)} | Aktien-Eintraege gesamt: {total_stocks}")


if __name__ == "__main__":
    main()
