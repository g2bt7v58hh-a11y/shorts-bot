@echo off
cd /d "%~dp0"
echo === Shorts Bot setup (Windows) ===
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python is not installed. Opening the download page...
  echo Install it, and TICK "Add python.exe to PATH" on the first screen.
  echo Then double-click this file again.
  start https://www.python.org/downloads/
  pause
  exit /b
)
if not exist venv py -3 -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Setup complete!  Next: open the ".env" file with Notepad and paste your keys.
notepad .env
pause
