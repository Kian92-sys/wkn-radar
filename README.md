# Reddit WKN-Radar

Durchsucht mehrere deutsche und internationale Finanz-Subreddits danach, wie
oft bestimmte Aktien (per WKN, Ticker oder Firmenname) erwähnt werden, und
zeigt die Top 10 der Woche in einem Dashboard: **`docs/index.html`**
(wird von GitHub Pages als Webseite ausgeliefert, sobald einmalig eingerichtet – siehe unten).

**Läuft nicht automatisch** – du startest jeden Lauf selbst mit einem Klick
(siehe "Aktualisieren" unten). Auf einen Aktiennamen im Dashboard klicken
öffnet ein Pop-up mit Links zu den jeweiligen Reddit-Beiträgen.

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

Repo → Tab *Actions* → *"WKN-Radar aktualisieren"* → *Run workflow*.
Ein Lauf dauert ein paar Minuten; danach ist das Dashboard unter deinem
Pages-Link aktuell. Es passiert sonst nichts von selbst – kein Zeitplan,
kein Hintergrundjob.

## Wie es funktioniert (grob)

1. `scripts/collect.py` fragt für jeden konfigurierten Subreddit über den
   Datendienst Apify neue Beiträge und Kommentare ab.
2. Jeder Text wird nach bekannten WKNs, Tickern und Firmennamen durchsucht
   (Liste in `data/wkn_mapping.csv`), inklusive Link zum jeweiligen Beitrag.
3. Treffer werden in `data/mentions.jsonl` gesammelt (nichts geht verloren,
   auch nicht bei künftigen Läufen).
4. `scripts/aggregate.py` fasst das pro Kalenderwoche zusammen
   (`data/weekly_data.json`), inklusive der Beitrags-Links pro Aktie.
5. `scripts/render_dashboard.py` baut daraus `docs/index.html`.
6. Ein GitHub-Actions-Workflow (`.github/workflows/update.yml`) führt diese
   drei Schritte aus, wenn du ihn manuell startest, und lädt das Ergebnis
   wieder ins Repo hoch.

## Dinge, die du ohne Programmierkenntnisse anpassen kannst

- **Welche Subreddits durchsucht werden:** `config.json`, Liste `subreddits`.
- **Wie viele Beiträge/Kommentare pro Lauf geladen werden** (beeinflusst die
  Apify-Kosten): `config.json`, `max_results_per_subreddit` /
  `max_comments_per_post`.
- **Welche Aktien erkannt werden:** `data/wkn_mapping.csv` – einfach eine neue
  Zeile mit WKN, Ticker, Firmenname, Alias-Namen (getrennt mit `|`) und
  Segment (`bluechip` / `smallcap` / `pennystock`) hinzufügen.

Wenn du bei einer dieser Dateien unsicher bist, schick mir einfach, was du
ändern möchtest – ich mach's dann für dich.

## Kosten

Apify vergibt neuen Konten ca. 5 US-Dollar Gratis-Guthaben pro Monat. Die
Standardeinstellungen hier (10 Subreddits, 30 Beiträge + bis zu 15 Kommentare
pro Beitrag und Lauf) sind bewusst sparsam gewählt, um möglichst innerhalb
dieses Rahmens zu bleiben. Solltest du es doch überschreiten, siehst du das
transparent in deinem Apify-Konto unter "Usage". Da du selbst startest statt
eines täglichen Automatiklaufs, hast du die Kosten ohnehin direkt im Griff.
