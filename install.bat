@echo off
echo =========================================
echo   Surebet System - Installation Script
echo =========================================

echo.
echo [1/4] Creating Python virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

echo.
echo [2/4] Installing Python dependencies...
pip install -r requirements.txt

echo.
echo [3/4] Installing Node.js frontend dependencies...
cd frontend
npm install
echo Building frontend...
npm run build
cd ..

echo.
echo [4/4] Setting up environment...
if not exist .env (
    copy .env.example .env
    echo Created .env file from template. Edit it to configure email alerts.
)

echo.
echo =========================================
echo   Installation complete!
echo.
echo   To start: python run.py
echo   Dashboard: http://localhost:8000
echo =========================================
pause
