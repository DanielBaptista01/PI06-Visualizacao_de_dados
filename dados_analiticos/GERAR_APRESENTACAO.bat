@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=python"
if exist ".venv-2\Scripts\python.exe" set "PYTHON=.venv-2\Scripts\python.exe"
if not exist ".venv-2\Scripts\python.exe" if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
echo.
echo PI06 v2.3 - Gerando o HTML completo com as 343 zonas reais...
echo.
"%PYTHON%" "PI06_site_html_v23\preparar_site_offline.py"
if errorlevel 1 (
  echo.
  echo Confira os CSVs, GeoJSONs e o manifesto de integridade.
  pause
  exit /b 1
)
echo.
echo Abrindo apresentacao_PI06_capital_v23.html...
start "" "%CD%\apresentacao_PI06_capital_v23.html"
pause
