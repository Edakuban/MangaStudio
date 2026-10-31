# Sicherheit und private Daten

## Vorgesehener Betrieb

MangaStudio ist für einen einzelnen Benutzer auf einem lokalen Rechner gedacht.
Der App-Server bindet an `127.0.0.1`. Die Anwendung hat keine Benutzeranmeldung
und ist nicht für eine direkte Veröffentlichung im Internet ausgelegt.
Auch ComfyUI sollte nur im vorgesehenen lokalen Umfeld erreichbar sein.

Buchtexte, Prompts und Referenzbilder werden für die Verarbeitung an die
konfigurierte lokale ComfyUI-Instanz übermittelt. Installierte Nodes und deren
mögliche zusätzliche Netzwerkzugriffe liegen außerhalb der App-Steuerung.

## Private Dateien

Nicht veröffentlichen: `data/`, individuelle Datenordner, Datenbanken samt
WAL/SHM-Dateien, Backups, `.env`-Dateien, Zugangsdaten, Manuskripte, Referenzbilder,
Logs und Modellgewichte. Vor Screenshots und Fehlerberichten private Inhalte
entfernen. `.gitignore` entfernt keine bereits getrackten Dateien aus Git.

## Schwachstellen melden

Bitte keine ausnutzbaren Schwachstellen oder privaten Daten in öffentlichen
Issues veröffentlichen. Wenn im GitHub-Repository die private Funktion
**Report a vulnerability** verfügbar ist, diese verwenden. Andernfalls zunächst
nur um einen privaten Meldeweg bitten, ohne technische Exploitdetails zu posten.
Eine feste Reaktionszeit wird derzeit nicht zugesagt.
