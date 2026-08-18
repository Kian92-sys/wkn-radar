#!/usr/bin/env python3
"""
Baut docs/index.html (das Dashboard, das GitHub Pages ausliefert) aus
data/weekly_data.json. Wird vom manuell gestarteten GitHub-Actions-Workflow
nach collect.py und aggregate.py aufgerufen.

Nichts hier muss von Hand angepasst werden -- reine Vorlagen-Befuellung.
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, "scripts", "dashboard_template.html")
DATA_PATH = os.path.join(BASE_DIR, "data", "weekly_data.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "docs")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "index.html")


def main():
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "generated_at": "-",
            "subreddits": [],
            "week_order": [],
            "week_labels": {},
            "weeks": {},
        }

    has_data = bool(data.get("week_order"))
    status_badge = (
        "ZULETZT AKTUALISIERT &middot; manuell gestartet"
        if has_data
        else "WARTE AUF ERSTEN LAUF"
    )
    footer_note = (
        "Generiert aus manuell gesammelten Reddit-Erwaehnungen (Datenquelle: "
        "Apify Reddit Scraper). Ein neuer Lauf wird ueber den GitHub-Actions-"
        "Tab gestartet ('WKN-Radar aktualisieren' -> 'Run workflow'), nicht "
        "automatisch. Erwaehnungen werden ueber WKN, Ticker oder Firmennamen "
        "erkannt (Mapping-Liste in data/wkn_mapping.csv, jederzeit erweiterbar). "
        "Auf einen Aktiennamen klicken zeigt die verlinkten Reddit-Beitraege."
        if has_data
        else "Noch keine Daten -- starte den ersten Lauf ueber Repo -> Tab "
        "'Actions' -> 'WKN-Radar aktualisieren' -> 'Run workflow'. Diese Seite "
        "aktualisiert sich danach automatisch."
    )

    html = template
    html = html.replace("__STATUS_BADGE__", status_badge)
    html = html.replace("__SUB_COUNT__", str(len(data.get("subreddits", []))))
    html = html.replace("__FOOTER_NOTE__", footer_note)
    html = html.replace("__SUBREDDITS_JSON__", json.dumps(data.get("subreddits", [])))
    html = html.replace("__WEEK_DATA_JSON__", json.dumps(data.get("weeks", {})))
    html = html.replace("__WEEK_ORDER_JSON__", json.dumps(data.get("week_order", [])))
    html = html.replace("__WEEK_LABELS_JSON__", json.dumps(data.get("week_labels", {})))
    html = html.replace("__GENERATED_AT_JSON__", json.dumps(data.get("generated_at", "-")))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard geschrieben: {OUTPUT_PATH} (hat Daten: {has_data})")


if __name__ == "__main__":
    main()
