#!/usr/bin/env python3
"""
Erkennung von Aktien-Erwaehnungen (WKN) in Reddit-Text.

Erkennt drei Signal-Arten pro Text:
  1. Direkte WKN-Codes (z.B. "703000", "A2QA4J")
  2. Ticker-Symbole (z.B. "RHM", "TSLA") -- mit Schutz gegen häufige
     Woerter, die zufaellig wie ein Ticker aussehen (siehe AMBIGUOUS_TICKERS)
  3. Firmennamen / Aliase (z.B. "Rheinmetall", "Mercedes")

Alle drei Signale werden auf dieselbe WKN gemapped. Ein Text zaehlt pro WKN
nur einmal, egal ueber wie viele Signale er erkannt wurde.
"""
import csv
import re

# Ticker, die auch gaengige deutsche/englische Woerter oder sehr kurz sind --
# dort zaehlt nur ein Treffer, wenn explizit als "$TICKER" geschrieben wurde,
# um Falscherkennungen zu vermeiden (z.B. "BEI" = deutsches Wort "bei").
AMBIGUOUS_TICKERS = {
    "C", "GE", "KO", "CON", "AIR", "BEI", "ALL", "SIX", "ARE", "CAN", "FOR",
    "HAS", "HAD", "WAS", "NOW", "NEW", "ONE", "TWO", "WHO", "WHY", "HOW",
    "OUT", "GET", "PUT", "BUY", "BIG", "SAP", "DIS", "IT",
}

WKN_PATTERN = re.compile(r"\b[A-Z0-9]{6}\b")
DOLLAR_TICKER_PATTERN = re.compile(r"\$([A-Z]{1,6})\b")


def load_mapping(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


class WknIndex:
    def __init__(self, rows):
        self.by_wkn = {}          # wkn -> record
        self.wkn_set = set()
        self.ticker_to_wkn = {}   # ticker -> wkn
        self.name_patterns = []   # list of (compiled_regex, wkn)

        for row in rows:
            wkn = (row.get("wkn") or "").strip()
            ticker = (row.get("ticker") or "").strip()
            name = (row.get("name") or "").strip()
            aliases = (row.get("aliases") or "").strip()
            segment = (row.get("segment") or "bluechip").strip()
            if not wkn:
                continue

            if wkn not in self.by_wkn:
                self.by_wkn[wkn] = {
                    "wkn": wkn,
                    "ticker": ticker,
                    "name": name,
                    "segment": segment,
                }
            self.wkn_set.add(wkn)

            if ticker:
                self.ticker_to_wkn[ticker] = wkn

            phrases = [name] + [a for a in aliases.split("|") if a]
            for phrase in phrases:
                phrase = phrase.strip()
                if len(phrase) < 3:
                    continue  # too short / noisy to safely match as a name
                pattern = re.compile(
                    r"(?<![A-Za-zÄÖÜäöüß])" + re.escape(phrase) + r"(?![A-Za-zÄÖÜäöüß])",
                    re.IGNORECASE,
                )
                self.name_patterns.append((pattern, wkn))

    def record(self, wkn):
        return self.by_wkn.get(wkn)


def match_text(text, index: WknIndex):
    """Returns a set of WKNs mentioned in the given text."""
    if not text:
        return set()

    found = set()

    # 1) direct WKN codes
    for token in WKN_PATTERN.findall(text):
        if token in index.wkn_set:
            found.add(token)

    # 2) $TICKER (always unambiguous, any ticker)
    for token in DOLLAR_TICKER_PATTERN.findall(text):
        wkn = index.ticker_to_wkn.get(token)
        if wkn:
            found.add(wkn)

    # 3) bare ticker (skip ambiguous ones unless already caught via $TICKER)
    bare_tokens = set(re.findall(r"\b[A-Z]{1,6}\b", text))
    for token in bare_tokens:
        if token in AMBIGUOUS_TICKERS:
            continue
        wkn = index.ticker_to_wkn.get(token)
        if wkn:
            found.add(wkn)

    # 4) company name / alias phrases
    for pattern, wkn in index.name_patterns:
        if wkn in found:
            continue
        if pattern.search(text):
            found.add(wkn)

    return found


# Tickers that are also plain English/German words, common abbreviations, or
# too generic to be a useful "unknown stock" signal on their own -- without
# this, cashtag discovery would drown in noise ($IT, $ALL, $NOW, $DD, ...).
# Deliberately small and separate from AMBIGUOUS_TICKERS: that list only
# guards *bare* mentions of *known, mapped* tickers, whereas this one only
# suppresses the discovery/suggestion list -- a real, unmapped $TICKER is
# already a fairly strong signal by itself, so we only filter out the
# obvious noise words here.
GENERIC_CASHTAG_NOISE = {
    "IT", "ALL", "ONE", "TWO", "NOW", "NEW", "NEXT", "GO", "OK", "USD", "EUR",
    "CEO", "CFO", "IPO", "ATH", "DD", "YOLO", "FOMO", "TLDR",
}


def find_unknown_cashtags(text, index: WknIndex):
    """Returns the set of raw $TICKER symbols mentioned in text that are NOT
    covered by wkn_mapping.csv. This is the discovery signal for stocks we
    don't track yet -- surfaced separately as a suggestion list rather than
    folded into the tracked Top 10, since (deliberately) we know nothing
    else about them yet: no WKN, no name, no segment."""
    if not text:
        return set()

    found = set()
    for token in DOLLAR_TICKER_PATTERN.findall(text):
        if token in GENERIC_CASHTAG_NOISE:
            continue
        if token in index.ticker_to_wkn:
            continue  # already a known, tracked stock
        found.add(token)
    return found
