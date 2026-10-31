@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Die Python-Umgebung fehlt. Bitte zuerst setup.bat starten.
  pause
  exit /b 1
)
echo KOMA MangaStudio: http://127.0.0.1:8042
echo Dieses Fenster offen lassen. Strg+C beendet die App.
".venv\Scripts\python.exe" -m mangastudio
pause
