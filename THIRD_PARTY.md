# Herkunft und externe Komponenten

## MangaStudio-Code

Copyright © 2026 Thomas Schamberger. Die projektseitig bereitgestellten
Softwarebestandteile stehen unter der MIT-Lizenz in [LICENSE](LICENSE),
soweit keine gesonderten Hinweise gelten.

Die Dateien `mangastudio/vendor/extraction.py`, `uploads.py` und `comfy.py`
wurden am 25. Oktober 2026 als lokale Snapshots aus dem Vorgängerprojekt
**AutomatedBookPromotion** (`src/bookpromo`) übernommen. Sie übernehmen den
DOCX-Import, die Upload-Prüfung und die ComfyUI-Kommunikation. Der Vorgänger
wird zur Laufzeit nicht benötigt. Verbliebene BookPromo-Bezeichnungen im
Client sind historische interne Namen.

## Python-Abhängigkeiten

MangaStudio verwendet unter anderem FastAPI, Uvicorn, HTTPX, python-multipart,
Pydantic, defusedxml, Pillow, ReportLab, pypdf und pypdfium2 (mit PDFium); pytest wird für Tests verwendet.
Direkte Abhängigkeiten stehen in `requirements.txt`, die festgeschriebenen
Versionen einschließlich transitiver Abhängigkeiten in `requirements-lock.txt`.

Diese Pakete behalten ihre jeweiligen Copyright-, Lizenz- und Notice-Texte.
Die MIT-Lizenz von MangaStudio ersetzt deren Lizenzen nicht. Maßgeblich sind
die mit der jeweiligen Paketversion ausgelieferten Hinweise. Bei Weitergabe
einer gebündelten Installation müssen auch diese berücksichtigt werden.

## ComfyUI und Modelle

ComfyUI, zusätzliche Nodes, Modellgewichte, Textencoder und VAEs werden separat
installiert und nicht mit diesem Repository ausgeliefert. Ihre jeweiligen
Lizenzbedingungen gelten unabhängig von der MangaStudio-Lizenz. Das betrifft
insbesondere die gewählte Modellversion und deren kommerzielle Nutzbarkeit.
Die Erwähnung eines Modellnamens ist keine zusätzliche Nutzungserlaubnis.

## Schriften

Es werden keine Schriftdateien im Repository mitgeliefert. Der PDF-Satz verwendet
nach Verfügbarkeit Arial aus Windows, DejaVu Sans aus dem System oder einen
ReportLab-Standardfont. Für Systemschriften und gegebenenfalls in PDFs eingebettete
Schriften gelten die jeweiligen Schriftlizenzen.

## Bücher und Bilder

Importierte Texte, Charakterbeschreibungen, Referenzbilder und Exporte sind
Nutzerdaten. Die Lizenz des Programms erteilt daran keine Rechte und macht
keine Zusage zu Schutzfähigkeit oder Nutzungsrechten erzeugter Bilder.
Private Inhalte und Modellgewichte gehören nicht zum Quellcode-Repository.
