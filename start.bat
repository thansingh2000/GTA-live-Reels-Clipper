@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10+ from https://www.python.org/downloads/
    echo and tick "Add Python to PATH" during installation, then run start.bat again.
    pause
    exit /b 1
)
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing / updating dependencies...
pip install -q -r requirements.txt
pip install -q -U "yt-dlp[default]"
start "" http://127.0.0.1:5000
python app.py
pause
