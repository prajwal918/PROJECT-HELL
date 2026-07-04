@echo off
echo Starting NOVA Phase 1...
echo.
echo Prerequisites:
echo 1. NEXUS Rust backend must be running on ws://localhost:9001
echo 2. OVERSEER must be running to feed L3 data to NEXUS
echo 3. .env file must be configured with API keys
echo.
pause

cd /d "%~dp0"

if not exist ".env" (
    echo ERROR: .env file not found!
    echo Copy .env.example to .env and fill in your values
    pause
    exit /b 1
)

python main.py

pause