#!/usr/bin/env python3
"""
Sammel-Schritt (manuell gestartet ueber den GitHub-Actions "Run workflow"-
Knopf): fragt fuer jeden ausgewaehlten Subreddit ueber Apify (Reddit Scraper
Actor) Posts + Kommentare ab, erkennt WKN/Ticker/Firmennamen-Erwaehnungen per
wkn_matcher und haengt neue Treffer (inkl. Link zum jeweiligen Reddit-Beitrag)
an data/mentions.jsonl an.

Drei Abfrage-Arten pro Subreddit (alle drei zusammen ergeben die Wochen-
Abdeckung, siehe README):
  1. sort=top + timeFilter=config["top_time_filter"] (Standard: "week")
     -- die meistdiskutierten Posts der letzten 7 Tage, nicht nur ein
     Schnappschuss vom Moment des Laufs.
  2. sort=new -- die aktuell frischesten Posts, die evtl. noch keine
     Upvotes gesammelt haben.
  3. mode=search mit den in config["tip_request"]["queries"] hinterlegten
     Formulierungen (z.B. "welche aktie", "tenbagger") -- findet gezielt
     Tipp-Anfrage-Threads, auch wenn dort noch kein bekannter Ticker faellt.

Zusaetzlich zur bekannten WKN-Erkennung wird bei jedem Text auch nach
$CASHTAGS gesucht, die NICHT in data/wkn_mapping.csv stehen -- das sind
Kandidaten fuer noch nicht getrackte (oft kleinere) Aktien und landen in
data/unknown_tickers.jsonl als Vorschlagsliste.

Welche Subreddits ueberhaupt abgefragt werden, laesst sich pro Lauf ueber
Umgebungsvariablen SUBREDDIT_<NAME> einschraenken (vom GitHub-Actions-
Workflow aus den Checkboxen im "Run workflow"-Dialog gesetzt). Ohne diese
Variablen (z.B. bei einem lokalen Testlauf) werden alle Subreddits aus
config.json verwendet.

Benoetigt Umgebungsvariable APIFY_TOKEN (wird vom GitHub-Actions-Workflow
aus dem Repo-Secret gesetzt).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from wkn_matcher import WknIndex, load_mapping, match_text, find_unknown_cashtags

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MAPPING_PATH = os.path.join(BASE_DIR, "data", "wkn_mapping.csv")
MENTIONS_PATH = os.path.join(BASE_DIR, "data", "mentions.jsonl")
SEEN_IDS_PATH = os.path.join(BASE_DIR, "data", "seen_ids.json")
UNKNOWN_TICKERS_PATH = os.path.join(BASE_DIR, "data", "unknown_tickers.jsonl")
TIP_THREADS_PATH = os.path.join(BASE_DIR, "data", "tip_threads.jsonl")

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


def subreddit_env_key(name):
    """Maps a subreddit name to the env var GitHub Actions sets for its
    checkbox, e.g. 'wallstreetbetsGER' -> 'SUBREDDIT_WALLSTREETBETSGER'."""
    slug = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
    return f"SUBREDDIT_{slug}"


def resolve_selected_subreddits(all_subreddits):
    """Applies the per-run subreddit selection. A subreddit is skipped only
    if its env var is explicitly set to a falsy value -- unset (e.g. a local
    run without the workflow's checkboxes) means "include", so behaviour
    without any env vars matches the old always-run-everything default."""
    selected = []
    skipped = []
    for sub in all_subreddits:
        raw = os.environ.get(subreddit_env_key(sub))
        if raw is not None and raw.strip().lower() in ("false", "0", "no"):
            skipped.append(sub)
            continue
        selected.append(sub)
    if skipped:
        print(f"Abgewaehlt (Checkbox aus): {', '.join(skipped)}")
    return selected


def call_apify(payload):
    actor = payload.pop("_actor")
    url = APIFY_SYNC_URL_TMPL.format(actor=actor.replace("/", "~"))
    params = {"token": APIFY_TOKEN, "timeout": 180}
    resp = requests.post(url, params=params, json=payload, timeout=200)
    resp.raise_for_status()
    return resp.json()


def fetch_subreddit_items(actor, subreddit, sort, max_results, include_comments,
                           max_comments, time_filter=None):
    payload = {
        "_actor": actor,
        "mode": "subreddit_posts",
        "subreddits": [subreddit],
        "sort": sort,
        "maxResults": max_results,
        "includeComments": include_comments,
        "maxCommentsPerPost": max_comments,
    }
    if sort == "top" and time_filter:
        payload["timeFilter"] = time_filter
    return call_apify(payload)


def fetch_tip_request_items(actor, subreddit, queries, max_results, include_comments,
                             max_comments):
    payload = {
        "_actor": actor,
        "mode": "search",
        "searchQueriesList": queries,
        "searchSubreddit": subreddit,
        "maxResults": max_results,
        "includeComments": include_comments,
        "maxCommentsPerPost": max_comments,
    }
    return call_apify(payload)


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


def is_post_item(item):
    """True for the post itself (used to decide what counts as a 'Tipp-
    Anfrage'-Thread rather than one of its comments) -- posts carry a title,
    comments normally do not."""
    return bool(str(item.get("title") or "").strip())


def process_item(item, sub, source, seen, today, index, new_mentions, new_unknowns):
    """Shared per-item handling for every fetch mode: dedup by id, run both
    the known-WKN matcher and the unknown-cashtag discovery, and append any
    hits to the given accumulator lists. Returns the item's text (so callers
    doing extra bookkeeping, e.g. tip-thread detection, don't re-extract it)."""
    item_id = extract_id(item)
    if not item_id or item_id in seen:
        return None
    seen[item_id] = today

    text = extract_text(item)
    item_subreddit = extract_subreddit(item, sub)
    item_date = extract_date(item)
    item_url = extract_url(item)
    item_snippet = extract_snippet(item)

    wkns = match_text(text, index)
    for wkn in wkns:
        new_mentions.append({
            "id": item_id,
            "wkn": wkn,
            "subreddit": item_subreddit,
            "date": item_date,
            "url": item_url,
            "snippet": item_snippet,
            "source": source,
        })

    for ticker in find_unknown_cashtags(text, index):
        new_unknowns.append({
            "id": item_id,
            "ticker": ticker,
            "subreddit": item_subreddit,
            "date": item_date,
            "url": item_url,
            "snippet": item_snippet,
            "source": source,
        })

    return text


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
    new_unknowns = []
    new_tip_threads = []
    stats = []  # per-subreddit diagnostic counters, printed at the end

    tip_cfg = cfg.get("tip_request", {})
    tip_enabled = tip_cfg.get("enabled", True) and bool(tip_cfg.get("queries"))

    selected_subreddits = resolve_selected_subreddits(cfg["subreddits"])
    if not selected_subreddits:
        print("FEHLER: Keine Subreddits ausgewaehlt (alle Checkboxen aus?).", file=sys.stderr)
        sys.exit(1)

    for sub in selected_subreddits:
        counts = {"sub": sub, "top": 0, "new": 0, "tip_search": 0,
                   "mentions": 0, "unknown": 0, "tip_threads": 0}

        # 1) sort=top + timeFilter (Wochen-Abdeckung statt Momentaufnahme)
        try:
            top_items = fetch_subreddit_items(
                cfg["apify_actor"], sub, "top",
                cfg.get("max_results_per_subreddit", 30),
                cfg.get("include_comments", True),
                cfg.get("max_comments_per_post", 15),
                time_filter=cfg.get("top_time_filter", "week"),
            )
        except requests.RequestException as e:
            print(f"WARNUNG: 'top'-Abruf fuer r/{sub} fehlgeschlagen: {e}", file=sys.stderr)
            top_items = []
        counts["top"] = len(top_items)

        # 2) sort=new (aktuellste Posts, ggf. noch ohne Upvotes)
        try:
            new_items = fetch_subreddit_items(
                cfg["apify_actor"], sub, "new",
                cfg.get("max_results_per_subreddit", 30),
                cfg.get("include_comments", True),
                cfg.get("max_comments_per_post", 15),
            )
        except requests.RequestException as e:
            print(f"WARNUNG: 'new'-Abruf fuer r/{sub} fehlgeschlagen: {e}", file=sys.stderr)
            new_items = []
        counts["new"] = len(new_items)

        before = len(new_mentions)
        before_unknown = len(new_unknowns)
        for item in top_items:
            process_item(item, sub, "top", seen, today, index, new_mentions, new_unknowns)
        for item in new_items:
            process_item(item, sub, "new", seen, today, index, new_mentions, new_unknowns)

        # 3) Tipp-Anfrage-Suche (mode=search): findet gezielt Threads wie
        # "welche Aktie ist das neue X" / "which stock is a tenbagger"
        if tip_enabled:
            try:
                tip_items = fetch_tip_request_items(
                    cfg["apify_actor"], sub, tip_cfg["queries"],
                    cfg.get("max_results_per_subreddit", 30),
                    True,
                    tip_cfg.get("max_comments_per_post", cfg.get("max_comments_per_post", 15)),
                )
            except requests.RequestException as e:
                print(f"WARNUNG: Tipp-Anfrage-Suche fuer r/{sub} fehlgeschlagen: {e}", file=sys.stderr)
                tip_items = []
            counts["tip_search"] = len(tip_items)

            for item in tip_items:
                item_id_before = extract_id(item)
                already_seen_before = item_id_before in seen if item_id_before else True
                text = process_item(item, sub, "tip_search", seen, today, index,
                                     new_mentions, new_unknowns)
                # Nur echte Posts (nicht Kommentare) und nur beim ersten Mal
                # gesehen landen in der Tipp-Threads-Liste fuers Dashboard.
                if text is not None and not already_seen_before and is_post_item(item):
                    new_tip_threads.append({
                        "id": item_id_before,
                        "subreddit": extract_subreddit(item, sub),
                        "date": extract_date(item),
                        "url": extract_url(item),
                        "snippet": extract_snippet(item, max_len=200),
                    })
                    counts["tip_threads"] += 1

        counts["mentions"] = len(new_mentions) - before
        counts["unknown"] = len(new_unknowns) - before_unknown
        stats.append(counts)
        time.sleep(1)  # be gentle between subreddit calls

    if new_mentions:
        os.makedirs(os.path.dirname(MENTIONS_PATH), exist_ok=True)
        with open(MENTIONS_PATH, "a", encoding="utf-8") as f:
            for m in new_mentions:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

    if new_unknowns:
        os.makedirs(os.path.dirname(UNKNOWN_TICKERS_PATH), exist_ok=True)
        with open(UNKNOWN_TICKERS_PATH, "a", encoding="utf-8") as f:
            for u in new_unknowns:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")

    if new_tip_threads:
        os.makedirs(os.path.dirname(TIP_THREADS_PATH), exist_ok=True)
        with open(TIP_THREADS_PATH, "a", encoding="utf-8") as f:
            for t in new_tip_threads:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

    save_seen_ids(seen, cfg.get("seen_id_retention_days", 60))

    total_items = sum(c["top"] + c["new"] + c["tip_search"] for c in stats)
    print("Pro Subreddit: top / new / tipp-suche Items -> Erwaehnungen | unbek. Ticker | Tipp-Threads")
    for c in stats:
        print(f"  r/{c['sub']}: {c['top']}/{c['new']}/{c['tip_search']} "
              f"-> {c['mentions']} | {c['unknown']} | {c['tip_threads']}")
    print(f"Verarbeitete Items gesamt: {total_items} | Neue Erwaehnungen: {len(new_mentions)} "
          f"| Neue unbekannte Ticker: {len(new_unknowns)} | Neue Tipp-Threads: {len(new_tip_threads)}")


if __name__ == "__main__":
    main()
