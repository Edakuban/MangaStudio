# MangaStudio

**Vom Roman zum Manga – eine lokale Werkstatt mit ComfyUI.**

MangaStudio (in der Oberfläche auch **KOMA**) importiert dein Buch, plant daraus
Szenen und Panels, erzeugt Charakter- und Szenenbilder und setzt alles als PDF.
Du prüfst und bearbeitest die KI-Vorschläge, bevor du sie übernimmst.

Die Oberfläche ist deutschsprachig. Die App läuft im Browser auf deinem Rechner;
Text-, Vision- und Bildmodelle laufen über ein separat installiertes lokales ComfyUI.
Ein Cloud-Konto ist für den vorgesehenen Betrieb nicht erforderlich.

> **Entwicklungsstand:** nutzbarer Prototyp mit laufender Weiterentwicklung.
> Kein automatischer Ersatz für Lektorat, Illustration oder Druckvorstufe.

## Funktionen

- **Buchimport:** DOCX, TXT und Markdown mit Kapitelaufteilung und Quellabsätzen.
- **Charakterverwaltung:** Beschreibungen, Aliase, Referenzbilder und kapitelweises
  KI-Erkennen neuer Figuren. Bilder direkt hochladen, vorhandene Render in Manga
  umwandeln oder neue Charakterbilder aus Beschreibungen erzeugen.
- **Storyboard:** Szenen, Kameraeinstellungen, Körperhaltungen, Dialoge und Erzählkästen
  planen und bearbeiten; Panels ergänzen oder löschen.
- **Dramaturgie:** KI-Vorschläge mit Fundstellen und Vorher/Nachher-Vergleich einzeln
  übernehmen oder verwerfen.
- **Koma-Wari:** KI-Seitenplanung, asymmetrische und diagonale Vorlagen, große Panels,
  Seitenumbrüche sowie Links-nach-rechts- und Rechts-nach-links-Leserichtung.
- **Bilder:** ausgewählte Charakterreferenzen einbinden, einzelne Panels oder alle
  fehlenden/veralteten Bilder erzeugen; eigene Panelbilder hochladen.
- **Sprechblasen:** Sprache, Gedanke, Flüstern und Schreien; Position, Größe,
  Schriftgröße und Zipfel im Seiteneditor bearbeiten.
- **PDF:** B5 (176 × 250 mm), Farbe oder Schwarzweiß, separat gesetzte Schrift und
  native Panelauflösung passend zur Druckfläche mit mindestens 300 dpi.
- **Lokale Speicherung:** SQLite, gespeicherte Fortschritte und Wiederaufnahme
  unterbrochener Aufträge. Gelöschte Bücher und Charaktere sind wiederherstellbar.

## Voraussetzungen

- **Python 3.11 oder neuer.** Die Startskripte sind für Windows ausgelegt;
  die manuelle Einrichtung ist unten beschrieben.
- **ComfyUI separat installiert und gestartet**, standardmäßig unter
  `http://127.0.0.1:8188`.
- Passende Modelle und Nodes für Text, Vision und Flux.2 Klein 4B (siehe
  [Modelle & Einrichtung](docs/SETUP.md)). Modelle werden nicht mitgeliefert.
- Eine für die gewählten Modelle und Bildgrößen geeignete GPU. Der Speicherbedarf
  hängt von Modell, Quantisierung, Referenzen und Auflösung ab; eine allgemeine
  Mindest-VRAM-Zusage gibt es derzeit nicht.

## Schnellstart unter Windows

1. Repository herunterladen oder klonen und in den Projektordner wechseln.
2. `setup.bat` starten. Das Skript erstellt `.venv` und installiert
   `requirements-lock.txt`.
3. ComfyUI starten und Modelle/Nodes einrichten.
4. `start.bat` starten und **[MangaStudio öffnen](http://127.0.0.1:8042/)**.
5. Unter **Verbindung & Modelle** die Verbindung und Modelldateien prüfen.

Für den ersten Download der Abhängigkeiten und Modelle wird Internet benötigt.
Node.js ist nur für die JavaScript-Tests erforderlich, nicht für den App-Betrieb.

### Manuelle Einrichtung

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m mangastudio --no-browser
```

Unter Linux/macOS entsprechend `.venv/bin/python` verwenden. Diese Plattformen
sind bisher nicht vollständig getestet. Ein anderer App-Port ist über
`--port 8043` wählbar. Der Server bindet an `127.0.0.1`.

## Empfohlener Ablauf

1. **Buch importieren** und die Kapitelaufteilung unter **Buchtext** prüfen.
2. **Charaktere und Bildsprache festlegen.** Die KI kann Figuren aus einem Kapitel
   erkennen und eine gemeinsame Bildsprache aus dem Buch vorschlagen. Entwürfe prüfen,
   speichern und gewünschte Charakterbilder ausdrücklich als Referenz übernehmen.
3. **Storyboard mit KI planen**, danach Szenen, Dialoge und Figuren-Zuordnungen prüfen.
4. **Storyboard dramaturgisch prüfen** und passende Vorschläge übernehmen.
5. **Seitenablauf mit KI planen**, Vorschlag prüfen und übernehmen. Alternativ lassen
   sich die Szenenlayouts verwenden und über **KI-Layout vorschlagen** verfeinern.
6. **Fehlende Bilder erzeugen.** Körperhaltungen und Bildprompts bei Bedarf korrigieren
   und betroffene Panels erneut erzeugen.
7. **Ausschnitte und Sprechblasen prüfen**, anschließend PDF exportieren.

Die Seitenplanung sollte vor der endgültigen Bilderzeugung stehen: Eine größere
Panel-Druckfläche benötigt mehr Pixel und kann eine Neuerzeugung erforderlich machen.
Ein **Layout-Entwurf** erlaubt fehlende oder noch unzureichende Bilder; der fertige
Export prüft unter anderem Aktualität, Auflösung und Sprechblasenprobleme.

## Daten und Sicherungen

Standardmäßig liegen Datenbank, importierte Bücher, Charakterbilder, Panelbilder
und Exporte unter `data/`. Dieser Ordner gehört nicht ins öffentliche Repository.
Für einen anderen Speicherort vor dem Start `MANGA_DATA_DIR` setzen:

```powershell
$env:MANGA_DATA_DIR = 'D:\MangaStudio-Daten'
.\.venv\Scripts\python.exe -m mangastudio
```

Für eine einfache vollständige Sicherung die App nach Ende laufender Aufträge
beenden und den gesamten Datenordner kopieren. Nur die SQLite-Datei zu kopieren
sichert keine Bilder und kann bei laufender App unvollständig sein.

## Grenzen

KI-Ausgaben können Handlung, Anatomie, Figurenidentität oder Posen falsch wiedergeben.
Referenzbilder verbessern die Wiedererkennbarkeit, garantieren sie aber nicht.
Charakterbilder aus Beschreibungen werden vor weißem Hintergrund angefordert;
echte Transparenz wird dabei nicht automatisch erzeugt.

Die Seitenlayouts basieren auf Vorlagen und sind kein freier Polygoneditor.
Sprechblasen erkennen Gesichter nicht automatisch. Der PDF-Export bietet derzeit
kein PDF/X, CMYK, zusätzliche Beschnittflächen oder professionelle Ausschießung.
300 dpi beschreibt die Rasterauflösung, nicht die vollständige Druckfertigkeit.
Eine randlose B5-Fläche wird mit 2080 × 2960 Pixeln angefordert.

Standard ist **Flux.2 Klein 4B Distilled (Apache 2.0)**. Die ebenfalls technisch
unterstützte 9B-Variante hat eine gesonderte nichtkommerzielle Modelllizenz; siehe
[Modelllizenzen](docs/SETUP.md#modelllizenzen).
Die Bildanbindung ist auf **Flux.2 Klein Distilled** zugeschnitten. Andere
Modellarchitekturen sind kein direkter Austausch im Modellfeld.

## Entwicklung und Hilfe

- [Modelle, Nodes und Fehlerbehebung](docs/SETUP.md)
- [Entwicklungsumgebung und Beiträge](CONTRIBUTING.md)
- [Sicherheit und private Daten](SECURITY.md)
- [Übernommene Bausteine und externe Abhängigkeiten](THIRD_PARTY.md)

Fehlerberichte bitte mit App-Version, reproduzierbaren Schritten und bereinigter
Fehlermeldung erstellen. Keine vollständigen Manuskripte, privaten Bilder oder
unbereinigten Datenbanken anhängen.

## Lizenz und Copyright

Copyright © 2026 **Thomas Schamberger**. Der App-Code steht unter der
[MIT-Lizenz](LICENSE), die auch kommerzielle Nutzung erlaubt.

Bücher, Charaktere, hochgeladene Bilder und erzeugte Inhalte werden durch diese
Softwarelizenz nicht mitlizenziert. Externe Bibliotheken, ComfyUI und Modelle haben
jeweils eigene Lizenzbedingungen; siehe [THIRD_PARTY.md](THIRD_PARTY.md).
