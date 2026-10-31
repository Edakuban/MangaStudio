# Modelle und Einrichtung

## Lokale Verbindung

MangaStudio und ComfyUI sind zwei getrennte Prozesse. Die App verwendet
standardmäßig `http://127.0.0.1:8042`, ComfyUI `http://127.0.0.1:8188`.
Unter **Verbindung & Modelle** prüft MangaStudio Modelldateien und benötigte
Nodes, ohne dabei eine Generierung zu starten. Unterstützt wird lokales HTTP-ComfyUI.

MangaStudio installiert weder ComfyUI noch Nodes oder Modelle automatisch.
Es übermittelt selbst erzeugte API-Graphen; ein manuell zu importierender
ComfyUI-Workflow ist für den App-Betrieb nicht erforderlich.

## Aktuell voreingestellte Modelle

| Aufgabe | Dateiname in der Voreinstellung |
| --- | --- |
| Textplanung | `qwen3.5_4b_bf16.safetensors` |
| Analyse hochgeladener Charakterrender | `qwen3vl_4b_fp8_scaled.safetensors` |
| Bilder | `flux-2-klein-4b-fp8.safetensors` |
| Bild-Textencoder | `qwen_3_4b.safetensors` |
| VAE | `full_encoder_small_decoder.safetensors` |

Die Namen beziehen sich auf die lokal erprobte Konfiguration, nicht auf
mitgelieferte Downloads. Maßgeblich sind die tatsächlichen Dateien und
kompatiblen Loader deiner ComfyUI-Installation.

Die Graphen benötigen insbesondere `TextGenerate`, `PreviewAny`, `UNETLoader`,
`CLIPLoader`, `ReferenceLatent`, `Flux2Scheduler` und `EmptyFlux2LatentImage`
sowie die üblichen Sampling-, VAE- und Bild-Nodes. Nicht jede ComfyUI-Installation
stellt alle benötigten Nodes bereit. Fehlende Nodes vor der ersten Planung ergänzen.

Der Bildgraph verwendet **Flux.2 Klein Distilled**, vier Schritte und CFG 1.
Die Voreinstellung ist die 4B-Variante mit passendem Qwen-4B-Textencoder.
Auch 9B wird technisch unterstützt, benötigt jedoch einen Qwen-8B-Textencoder
und für kommerziellen lokalen Modelleinsatz eine gesonderte BFL-Lizenz.
Flux.1, SDXL und Klein Base benötigen andere Graphen und sind kein direkter Modellersatz.

## Modellauswahl in der App

Unter **Verbindung & Modelle → Bildmodell wählen** stehen Klein 4B und Klein 9B
mit Lizenzhinweis zur Auswahl. Die Auswahl setzt auch den passenden Textencoder.
Die Änderung wird erst mit **Speichern** aktiv. Modelldateien können weiterhin
manuell eingetragen werden. Ein Wechsel löscht keine vorhandenen Bilder, markiert
sie aber als veraltet. Lizenzhinweise beziehen sich auf die benannte Modellfamilie;
bei eigenen Varianten müssen deren Herkunft und zusätzliche Bedingungen geprüft werden.

## Charakterreferenzen

Für Panels werden die ausgewählten Charakterbeschreibungen und bis zu vier
Referenzbilder eingebunden. Verwende möglichst ein einzelnes Motiv je Referenz.
Hintergrund, Gegenstände und Posen aus Referenzen können ins Szenenbild einfließen.
Dauerhafte Eigenschaften gehören ins Profil; die konkrete Haltung gehört unter
**Körperhaltung & Aktion** ins jeweilige Panel.

Neue KI-Charakterbilder bleiben zunächst Entwürfe. Erst die ausdrückliche
Übernahme aktiviert sie als Referenz. Das bewahrt die bisherige Referenz während
der Prüfung. Ein Referenzbild ersetzt keine eindeutige Szenenbeschreibung.

## Aufträge und Wiederaufnahme

Aufträge laufen nacheinander und speichern ihren Fortschritt lokal. Bekannte
ComfyUI-Prompt-IDs werden zur Wiederaufnahme weiter beobachtet. Fehlerhafte
Textantworten werden begrenzt zur Korrektur zurückgegeben. Ein fehlgeschlagener
Auftrag lässt sich über **Fortsetzen** erneut versuchen.

Während eines aktiven Auftrags sind Änderungen am betroffenen Buch gesperrt.
Nach Änderungen an Stil, Prompt, Charakterprofil, Referenz oder Modell können
Panelbilder als veraltet gelten. Größere Panel-Druckflächen können ebenfalls
neue Bilder erfordern. Alte Bilddateien bleiben lokal erhalten.

## Häufige Probleme

| Problem | Prüfen / Vorgehen |
| --- | --- |
| ComfyUI nicht erreichbar | ComfyUI starten, lokale Adresse und Port prüfen. |
| Node oder Modell fehlt | Verbindungsprüfung lesen, kompatible Nodes/Dateien installieren und Felder aktualisieren. |
| Figur/Pose stimmt nicht | Profil, Referenz, Figuren-Zuordnung und Panelprompt prüfen; konkrete Aktion beschreiben. |
| KI-Antwort ungültig | Auftragsmeldung lesen, über Fortsetzen erneut versuchen; bei Wiederholung bereinigten Fehler melden. |
| Export meldet zu kleine Bilder | Seitenlayout festlegen und fehlende/veraltete Bilder neu erzeugen. |
| Text passt nicht in die Blase | Text kürzen, Blase verschieben oder vergrößern; im Seiteneditor prüfen. |
| Oberfläche zeigt alte Elemente | Browser mit Strg+F5 neu laden; bei Backend-Änderungen App neu starten. |
| Port 8042 schon belegt | Laufende App verwenden/beenden oder `--port 8043` wählen. |

## Druck und Farbe

PDFs verwenden B5 (176 × 250 mm). Bilder werden passend zu ihrer Panelgröße
mit mindestens 300 dpi angefordert, auf ein Pixelraster von 16 aufgerundet.
Ein randloses B5-Panel benötigt 2080 × 2960 Pixel. Höhere Auflösungen benötigen
mehr GPU-Speicher und können länger dauern.

Die Schwarzweißoption verändert Vorschau und Export; die ursprünglichen
Bilddateien bleiben erhalten. Der fertige Export prüft die tatsächlichen
Pixelmaße. Ein Layout-Entwurf kann unzureichende Bilder enthalten und ist keine
Qualitätsfreigabe. PDF/X, CMYK, Beschnittzugabe und Ausschießung sind nicht implementiert.

## Modelllizenzen

Die Voreinstellung verwendet [FLUX.2 Klein 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B)
unter Apache 2.0, einschließlich kommerzieller Nutzung. Qwen3.5 4B, Qwen3-VL 4B,
Qwen3 4B und der FLUX.2 Small Decoder sind ebenfalls als Apache 2.0 veröffentlicht.
Maßgeblich bleiben die Lizenzhinweise der tatsächlich installierten Dateien.

FLUX.2 Klein **9B** steht hingegen unter der FLUX Non-Commercial License.
BFL verlangt für kommerziellen lokalen Modelleinsatz eine zusätzliche Lizenz:
[BFL-Lizenzübersicht](https://help.bfl.ai/articles/9272590838-self-serve-dev-license-overview-pricing).
Die MIT-Lizenz von MangaStudio ersetzt diese Modellbedingungen nicht.
Ein Modellwechsel verändert keine Rechte an bereits erzeugten Bildern.
