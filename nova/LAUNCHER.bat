@echo off
echo ====================================
echo   FINAL TRADING PROJECT
echo   SYSTEM STATUS & LAUNCHER
echo ====================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found
    echo Please install Python 3.9+
    pause
    exit /b 1
)

python --version
echo.

echo Select mode:
echo.
echo [1] Check System Status
echo [2] Run NOVA Test Mode (Mock Data)
echo [3] Run AEGIS Test Mode (Mock Data)
echo [4] Verify NOVA Setup
echo [5] Verify AEGIS Setup
echo [6] View Project Status
echo [7] View Deployment Checklist
echo [8] Launch NOVA (Live)
echo [9] Launch AEGIS (Live)
echo [0] Exit
echo.
set /p choice="Enter choice (0-9): "

if "%choice%"=="1" (
    echo.
    echo ====================================
    echo   SYSTEM STATUS
    echo ====================================
    echo.
    echo [1/3] Checking Python...
    python --version
    echo.
    echo [2/3] Checking Dependencies...
    python -c "import asyncio, websockets, requests, numpy, pytz; print('All OK')"
    echo.
    echo [3/3] Checking OVERSEER Feed...
    powershell -Command "Test-NetConnection -ComputerName 127.0.0.1 -Port 12347 -InformationLevel Quiet" >nul 2>&1
    if %errorlevel% equ 0 (
        echo OVERSEER UDP: AVAILABLE
    ) else (
        echo OVERSEER UDP: NOT AVAILABLE
    )
    echo.
    echo NEXUS Backend: CHECK MANUALLY
    echo   - Should be running on ws://localhost:9001
    echo   - Check: netstat -an ^| findstr 9001
    echo.
    pause
) else if "%choice%"=="2" (
    echo.
    echo ====================================
    echo   NOVA TEST MODE
    echo ====================================
    echo.
    echo Running NOVA with mock data...
    echo No API keys or live data required.
    echo.
    cd nova_logic
    python test_mode.py
    cd ..
    pause
) else if "%choice%"=="3" (
    echo.
    echo ====================================
    echo   AEGIS TEST MODE
    echo ====================================
    echo.
    echo Running AEGIS with mock data...
    echo No API keys or live data required.
    echo.
    cd aegis_logic
    python test_mode.py
    cd ..
    pause
) else if "%choice%"=="4" (
    echo.
    echo ====================================
    echo   NOVA SETUP VERIFICATION
    echo ====================================
    echo.
    cd nova_logic
    python verify_setup.py
    cd ..
    pause
) else if "%choice%"=="5" (
    echo.
    echo ====================================
    echo   AEGIS SETUP VERIFICATION
    echo ====================================
    echo.
    cd aegis_logic
    python verify_setup.py
    cd ..
    pause
) else if "%choice%"=="6" (
    echo.
    echo Opening PROJECT_STATUS.md...
    start PROJECT_STATUS.md
) else if "%choice%"=="7" (
    echo.
    echo Opening DEPLOYMENT_CHECKLIST.md...
    start DEPLOYMENT_CHECKLIST.md
) else if "%choice%"=="8" (
    echo.
    echo ====================================
    echo   LAUNCH NOVA (LIVE)
    echo ====================================
    echo.
    echo WARNING: This will start NOVA with live data.
    echo Make sure:
    echo   - NEXUS backend is running on ws://localhost:9001
    echo   - .env file is configured with API keys
    echo   - OVERSEER is feeding data to NEXUS
    echo.
    set /p confirm="Continue? (Y/N): "
    if /i "%confirm%"=="Y" (
        cd nova_logic
        python main.py
        cd ..
    )
) else if "%choice%"=="9" (
    echo.
    echo ====================================
    echo   LAUNCH AEGIS (LIVE)
    echo ====================================
    echo.
    echo WARNING: This will start AEGIS with live data.
    echo Make sure:
    echo   - NEXUS backend is running on ws://localhost:9001
    echo   - .env file is configured with Deriv API token
    echo   - OVERSEER is feeding data to NEXUS
    echo   - You have sufficient Deriv account balance
    echo.
    set /p confirm="Continue? (Y/N): "
    if /i "%confirm%"=="Y" (
        cd aegis_logic
        python main.py
        cd ..
    )
) else if "%choice%"=="0" (
    echo Exiting...
    exit /b 0
) else (
    echo Invalid choice.
    pause
)

goto :eof