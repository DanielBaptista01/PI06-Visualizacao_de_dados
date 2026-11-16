@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=python"
if exist ".venv-2\Scripts\python.exe" set "PYTHON=.venv-2\Scripts\python.exe"
if not exist ".venv-2\Scripts\python.exe" if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
echo PI06 v2.4 - Construindo a apresentacao offline completa...
"%PYTHON%" "PI06_site_html_v24\preparar_site_offline.py"
if errorlevel 1 (
 echo Erro: confira CSVs, referencias, GeoJSON e manifesto SHA256.
 pause
 exit /b 1
)
start "" "%CD%\apresentacao_PI06_capital_v24.html"
endlocal
