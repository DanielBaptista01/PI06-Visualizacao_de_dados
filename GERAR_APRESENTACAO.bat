@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=python"
if exist ".venv-2\Scripts\python.exe" set "PYTHON=.venv-2\Scripts\python.exe"
if not exist ".venv-2\Scripts\python.exe" if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
echo.
echo PI06 - Gerando a apresentacao offline a partir dos dados locais...
echo.
"%PYTHON%" "PI06_site_html_v22\preparar_site_offline.py"
if errorlevel 1 (
  echo.
  echo Houve um erro na preparacao. Confira o caminho dos CSVs e GeoJSONs.
  pause
  exit /b 1
)
echo.
echo Abrindo apresentacao_PI06_capital_v22.html no navegador...
start "" "%CD%\apresentacao_PI06_capital_v22.html"
echo.
pause
