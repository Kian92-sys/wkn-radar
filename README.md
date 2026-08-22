# Reddit WKN-Radar

Durchsucht mehrere deutsche und internationale Finanz-Subreddits danach, wie
oft bestimmte Aktien (per WKN, Ticker oder Firmenname) erwähnt werden, und
zeigt die Top 10 der Woche in einem Dashboard: **`docs/index.html`**
(wird von GitHub Pages als Webseite ausgeliefert, sobald einmalig eingerichtet – siehe unten).

Zusätzlich zur Top 10 gibt es zwei weitere Bereiche im Dashboard:

- **Unbekannte Aktien · Vorschläge** – `$CASHTAGS`, die im Text auftauchen,
  aber noch nicht in der Mapping-Liste stehen. So findest du auch kleinere,
  noch nicht getrackte Aktien, statt nur die vorab bekannten Blue Chips zu
  sehen.
- **Tipp-Anfragen** – Threads wie "welche Aktie wird die nächste Nebius"
  oder "which stock is a tenbagger", gezielt gesucht, auch wenn dort noch
  gar kein bekannter Ticker fällt.

**Läuft nicht automatisch** – du startest jeden Lauf selbst mit einem Klick
(siehe "Aktualisieren" unten). Dabei kannst du auswählen, welche Subreddits
für diesen Lauf durchsucht werden sollen. Auf einen Aktiennamen bzw. Ticker
im Dashboard klicken öffnet ein Pop-up mit Links zu den jeweiligen
Reddit-Beiträgen.

Du musst nichts von dem hier lesen oder verstehen, um das Dashboard zu nutzen –
dieses README ist nur für den Fall, dass du später mal etwas ändern möchtest
(z.B. welche Subreddits durchsucht werden) oder wissen willst, wie es funktioniert.

## Einmalige Einrichtung (nur diese zwei Schritte)

1. **Apify-Token als Secret hinterlegen**
   Repo → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*
   Name: `APIFY_TOKEN`, Wert: dein Apify-API-Token. Speichern.

2. **GitHub Pages aktivieren**
   Repo → *Settings* → *Pages* → bei *Source* **"Deploy from a branch"** wählen,
   Branch **`main`**, Ordner **`/docs`** → *Save*.
   Danach zeigt GitHub dir oben eine Adresse wie
   `https://<dein-username>.github.io/wkn-radar/` – das ist dein Dashboard-Link.

## Aktualisieren (jedes Mal manuell)

Repo → Tab *Actions* → *"WKN-Radar aktualisieren"* → *Run workflow*. Im
sich öffnenden Formular siehst du eine Checkbox pro Subreddit (alle
standardmäßig an) – hak einzelne ab, wenn du sie für diesen Lauf
überspringen willst, z.B. um Apify-Kosten zu sparen. Ein Lauf dauert ein
paar Minuten; danach ist das Dashboard unter deinem Pages-Link aktuell. Es
passiert sonst nichts von selbst – kein Zeitplan, kein Hintergrundjob.

## Wie es funktioniert (grob)

1. `scripts/collect.py` fragt für jeden ausgewählten Subreddit über den
   Datendienst Apify Beiträge und Kommentare ab – und zwar auf drei Arten:
   die meistdiskutierten Posts der letzten 7 Tage (`sort=top`,
   `timeFilter=week`), die aktuell neuesten Posts (`sort=new`), sowie eine
   gezielte Suche nach Tipp-Anfrage-Formulierungen (`mode=search`, Liste in
   `config.json` unter `tip_request.queries`). Das sorgt dafür, dass eine
   ganze Woche abgedeckt wird statt nur eines Schnappschusses vom
   Zeitpunkt des Laufs.
2. Jeder Text wird nach bekannten WKNs, Tickern und Firmennamen durchsucht
   (Liste in `data/wkn_mapping.csv`), inklusive Link zum jeweiligen Beitrag.
   Zusätzlich wird nach `$CASHTAGS` gesucht, die noch nicht in der Liste
   stehen – das sind Kandidaten für die "Unbekannte Aktien"-Vorschlagsliste.
3. Treffer werden in `data/mentions.jsonl` (bekannte Aktien),
   `data/unknown_tickers.jsonl` (unbekannte Cashtags) und
   `data/tip_threads.jsonl` (Tipp-Anfrage-Threads) gesammelt – nichts geht
   verloren, auch nicht bei künftigen Läufen.
4. `scripts/aggregate.py` fasst alle drei Dateien pro Kalenderwoche
   zusammen (`data/weekly_data.json`), inklusive der Beitrags-Links.
5. `scripts/render_dashboard.py` baut daraus `docs/index.html`.
6. Ein GitHub-Actions-Workflow (`.github/workflows/update.yml`) führt diese
   Schritte aus, wenn du ihn manuell startest, und lädt das Ergebnis wieder
   ins Repo hoch.

## Dinge, die du ohne Programmierkenntnisse anpassen kannst

- **Welche Subreddits durchsucht werden:** entweder dauerhaft in
  `config.json` (Liste `subreddits`), oder nur für einen einzelnen Lauf
  über die Checkboxen im "Run workflow"-Dialog.
- **Wie viele Beiträge/Kommentare pro Lauf geladen werden** (beeinflusst die
  Apify-Kosten): `config.json`, `max_results_per_subreddit` /
  `max_comments_per_post`.
- **Wie weit die "Top"-Abfrage zurückschaut:** `config.json`,
  `top_time_filter` (z.B. `"day"`, `"week"`, `"month"`).
- **Welche Aktien erkannt werden:** `data/wkn_mapping.csv` – einfach eine neue
  Zeile mit WKN, Ticker, Firmenname, Alias-Namen (getrennt mit `|`) und
  Segment (`bluechip` / `smallcap` / `pennystock`) hinzufügen.
- **Wonach bei den Tipp-Anfragen gesucht wird:** `config.json`,
  `tip_request.queries` – eigene Formulierungen ergänzen oder entfernen.
  Mit `tip_request.enabled: false` lässt sich die Suche ganz abschalten.

Wenn du bei einer dieser Dateien unsicher bist, schick mir einfach, was du
ändern möchtest – ich mach's dann für dich.

## Kosten

Apify vergibt neuen Konten ca. 5 US-Dollar Gratis-Guthaben pro Monat. Da pro
Lauf jetzt drei Abfragen pro Subreddit stattfinden (top, new, Tipp-Suche)
statt nur einer, ist der Verbrauch pro Lauf höher als vorher – über die
Checkboxen im "Run workflow"-Dialog kannst du das für einzelne Läufe wieder
eingrenzen. Solltest du dein Guthaben überschreiten, siehst du das
transparent in deinem Apify-Konto unter "Usage". Da du selbst startest statt
eines täglichen Automatiklaufs, hast du die Kosten ohnehin direkt im Griff.
