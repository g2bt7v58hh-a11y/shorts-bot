@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
set /p TOPIC="What should the Short be about? "
python make_short.py "%TOPIC%"
start "" output
pause
