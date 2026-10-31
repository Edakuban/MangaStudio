@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto fail
echo Einrichtung abgeschlossen. Jetzt start.bat starten.
pause
exit /b 0
:fail
echo Einrichtung fehlgeschlagen. Python ab Version 3.11 muss installiert sein.
pause
exit /b 1
