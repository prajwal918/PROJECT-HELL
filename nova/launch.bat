@echo off
echo ====================================
echo   FINAL TRADING PROJECT LAUNCHER
echo ====================================
echo.
echo This launcher will guide you through starting all required systems
echo.
pause

echo.
echo [STEP 1/5] Check if Python is installed...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found! Please install Python 3.9+
    pause
    exit /b 1
)
echo Python found: 
python --version

echo.
echo [STEP 2/5] Check if Rust is installed...
rustc --version >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: Rust not found! NEXUS backend cannot start
    echo You can still run NOVA/AEGIS if NEXUS is already running
)
if %errorlevel% equ 0 (
    echo Rust found:
    rustc --version
)

echo.
echo [STEP 3/5] Install Python dependencies...
echo Installing NOVA dependencies...
cd nova_logic
pip install -r requirements.txt
cd ..
echo Installing AEGIS dependencies...
cd aegis_logic
pip install -r requirements.txt
cd ..

echo.
echo [STEP 4/5] Check configuration files...
if not exist "nova_logic\.env" (
    echo WARNING: nova_logic\.env not found!
    echo Copy nova_logic\.env.example to nova_logic\.env and fill in API keys
)
if not exist "aegis_logic\.env" (
    echo WARNING: aegis_logic\.env not found!
    echo Copy aegis_logic\.env.example to aegis_logic\.env and fill in API keys
)

echo.
echo [STEP 5/5] Select system to launch:
echo.
echo 1. NOVA (Phase 1) - 1-minute news binary (manual execution)
echo 2. AEGIS (Phase 2) - 15-minute absorption trap (automated Deriv)
echo 3. NEXUS Rust Backend (if not already running)
echo 4. Exit
echo.
set /p choice="Enter choice (1-4): "

if "%choice%"=="1" (
    echo.
    echo Launching NOVA...
    cd nova_logic
    call start_nova.bat
) else if "%choice%"=="2" (
    echo.
    echo Launching AEGIS...
    cd aegis_logic
    call start_aegis.bat
) else if "%choice%"=="3" (
    echo.
    echo Launching NEXUS Rust Backend...
    echo Note: This requires Rust to be installed
    echo Location: C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nexus\rust-backend
    pause
) else if "%choice%"=="4" (
    echo Exiting...
    exit /b 0
) else (
    echo Invalid choice. Exiting...
    pause
    exit /b 1
)

pause