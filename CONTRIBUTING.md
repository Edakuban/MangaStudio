# Entwicklung und Beiträge

MangaStudio ist eine lokale Python-Web-App mit einer Oberfläche aus Vanilla
JavaScript und CSS. Für den Start ist kein Frontend-Build erforderlich.

## Projektstruktur

- `mangastudio/`: Web-API, Datenmodelle, SQLite-Speicher, Planung und PDF-Satz.
- `mangastudio/static/`: Browseroberfläche.
- `mangastudio/vendor/`: übernommene Bausteine; siehe `THIRD_PARTY.md`.
- `tests/`: Python- und JavaScript-Tests.
- `tools/`: gezielt auszuführende Demo-, Diagnose- und lokale KI-Testskripte.
- `docs/`: Einrichtung und Anwenderhinweise.
- `data/`, `tmp/`, `.venv/`: lokale Dateien, nicht Teil des Repositorys.

## Einrichtung und Tests

Installation wie in der [README](README.md). Tests mit einem separaten Datenordner
starten, damit die Standarddatenbank beim Import der Web-App nicht berührt wird:

```powershell
$env:MANGA_DATA_DIR = Join-Path $PWD 'tmp/test-data'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/pytest-local
node --test tests/character_ui.test.cjs
```

Die regulären Tests arbeiten mit Testdaten und benötigen keine laufende Bild-KI.
`tools/live_*.py` sind separat auszuführende Integrationstests: Sie benötigen
lokales ComfyUI und verbrauchen GPU-Zeit. Vor Ausführung den jeweiligen Quelltext
und die Ausgabe-/Datenpfade prüfen. Reparatur- oder Wiederherstellungswerkzeuge
nicht auf produktiven Daten ausprobieren.

## Änderungen

Bei Fehlern bitte ein möglichst kleines synthetisches Beispiel und relevante
Versions-/Fehlerangaben liefern. Tests sollten Verhalten absichern, insbesondere
Buchreihenfolge, Quellbezüge, Datenbewahrung, Wiederaufnahme und PDF-Geometrie.
KI-Vorschläge müssen prüfbar bleiben; eine Analyse soll keine Nutzerinhalte
unbemerkt überschreiben.

Keine Bücher, privaten Charakterbilder, SQLite-Dateien, Modellgewichte, Tokens
oder lokalen Backups committen. Für Beispiele selbst erstellte synthetische
Inhalte verwenden. Die `.gitignore` deckt die Standardpfade ab; ein selbst
gewählter Datenordner im Repository muss zusätzlich ausgeschlossen werden.

Mit einem Beitrag bestätigst du, dass du ihn unter der [MIT-Lizenz](LICENSE)
dieses Projekts bereitstellen darfst. Neue Abhängigkeiten und fremde Assets
müssen mit Herkunft und Lizenzhinweisen dokumentiert werden.
