#!/usr/bin/env python3
"""
Sammel-Schritt (manuell gestartet ueber den GitHub-Actions "Run workflow"-
Knopf): fragt fuer jeden konfigurierten Subreddit ueber Apify (Reddit
Scraper Actor) neue Posts + Kommentare ab, erkennt WKN/Ticker/
Firmennamen-Erwaehnungen per wkn_matcher und haengt neue Treffer
(inkl. Link zum jeweiligen Reddit-Beitrag) an data/mentions.jsonl an.

Benoetigt Umgebungsvariable APIFY_TOKEN (wird vom GitHub-Actions-Workflow
aus dem Repo-Secret gesetzt).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from wkn_matcher import WknIndex, load_mapping, match_text

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MAPPING_PATH = os.path.join(BASE_DIR, "data", "wkn_mapping.csv")
MENTIONS_PATH = os.path.join(BASE_DIR, "data", "mentions.jsonl")
SEEN_IDS_PATH = os.path.join(BASE_DIR, "data", "seen_ids.json")

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
APIFY_SYNC_URL_TMPL = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_seen_ids():
    if not os.path.exists(SEEN_IDS_PATH):
        return {}
    with open(SEEN_IDS_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_seen_ids(seen, retention_days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    pruned = {k: v for k, v in seen.items() if v >= cutoff}
    os.makedirs(os.path.dirname(SEEN_IDS_PATH), exist_ok=True)
    with open(SEEN_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(pruned, f)


def fetch_subreddit_items(actor, subreddit, sort, max_results, include_comments, max_comments):
    url = APIFY_SYNC_URL_TMPL.format(actor=actor.replace("/", "~"))
    payload = {
        "mode": "subreddit_posts",
        "subreddits": [subreddit],
        "sort": sort,
        "maxResults": max_results,
        "includeComments": include_comments,
        "maxCommentsPerPost": max_comments,
    }
    params = {"token": APIFY_TOKEN, "timeout": 180}
    resp = requests.post(url, params=params, json=payload, timeout=200)
    resp.raise_for_status()
    return resp.json()


def extract_id(item):
    for key in ("id", "postId", "commentId", "name", "fullname"):
        if item.get(key):
            return str(item[key])
    return None


def extract_text(item):
    parts = []
    for key in ("title", "selftext", "body", "text", "content"):
        v = item.get(key)
        if v:
            parts.append(str(v))
    return "\n".join(parts)


def extract_subreddit(item, fallback):
    for key in ("subreddit", "community", "subredditName"):
        v = item.get(key)
        if v:
            return str(v).lstrip("r/")
    return fallback


def extract_url(item):
    for key in ("permalink", "url", "postUrl", "link", "commentUrl"):
        v = item.get(key)
        if not v:
            continue
        v = str(v)
        if v.startswith("http"):
            return v
        if v.startswith("/"):
            return "https://www.reddit.com" + v
    return None


def extract_snippet(item, max_len=140):
    title = str(item.get("title") or "").strip()
    body = str(item.get("selftext") or item.get("body") or item.get("text") or "").strip()
    snippet = title if title else body
    snippet = " ".join(snippet.split())  # collapse whitespace/newlines
    if len(snippet) > max_len:
        snippet = snippet[:max_len].rstrip() + "…"
    return snippet


def extract_date(item):
    for key in ("createdAt", "created_utc", "created", "timestamp", "date"):
        v = item.get(key)
        if not v:
            continue
        try:
            if isinstance(v, (int, float)):
                return datetime.fromtimestamp(float(v), tz=timezone.utc).strftime("%Y-%m-%d")
            # try ISO string
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    if not APIFY_TOKEN:
        print("FEHLER: Umgebungsvariable APIFY_TOKEN ist nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    rows = load_mapping(MAPPING_PATH)
    index = WknIndex(rows)
    seen = load_seen_ids()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_mentions = []
    total_items = 0

    for sub in cfg["subreddits"]:
        try:
            items = fetch_subreddit_items(
                cfg["apify_actor"],
                sub,
                cfg.get("sort", "new"),
                cfg.get("max_results_per_subreddit", 30),
                cfg.get("include_comments", True),
                cfg.get("max_comments_per_post", 15),
            )
        except requests.RequestException as e:
            print(f"WARNUNG: Abruf fuer r/{sub} fehlgeschlagen: {e}", file=sys.stderr)
            continue

        total_items += len(items)
        for item in items:
            item_id = extract_id(item)
            if not item_id or item_id in seen:
                continue
            seen[item_id] = today

            text = extract_text(item)
            wkns = match_text(text, index)
            if not wkns:
                continue

            item_subreddit = extract_subreddit(item, sub)
            item_date = extract_date(item)
            item_url = extract_url(item)
            item_snippet = extract_snippet(item)
            for wkn in wkns:
                new_mentions.append({
                    "id": item_id,
                    "wkn": wkn,
                    "subreddit": item_subreddit,
                    "date": item_date,
                    "url": item_url,
                    "snippet": item_snippet,
                })

        time.sleep(1)  # be gentle between subreddit calls

    if new_mentions:
        os.makedirs(os.path.dirname(MENTIONS_PATH), exist_ok=True)
        with open(MENTIONS_PATH, "a", encoding="utf-8") as f:
            for m in new_mentions:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

    save_seen_ids(seen, cfg.get("seen_id_retention_days", 60))

    print(f"Verarbeitete Items: {total_items} | Neue Erwaehnungen: {len(new_mentions)}")


if __name__ == "__main__":
    main()
