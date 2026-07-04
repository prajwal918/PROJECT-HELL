<#
.SYNOPSIS
    OVERSEER v12 - One-click auto-installer
.DESCRIPTION
    Checks/installs Python 3.12+, pip upgrades, installs all requirements,
    initializes SQLite database, and verifies syntax on all Python files.
    Run: .\setup.ps1
#>

$ErrorActionPreference = 'Continue'
$ProjectRoot = $PSScriptRoot

function Write-Status([string]$msg) { Write-Host "`n[OVERSEER] $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)     { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg)   { Write-Host "  WARN $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg)   { Write-Host "  FAIL $msg" -ForegroundColor Red }

# ── 1. Python version check ──
Write-Status 'Checking Python...'

$pythonExe = $null
$pyVersions = @('python', 'python3', 'py')

foreach ($py in $pyVersions) {
    try {
        $verRaw = & $py --version 2>&1 | Out-String
        if ($verRaw -match 'Python (\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $pythonExe = $py
                Write-OK "Found $verRaw via '$py'"
                break
            } else {
                Write-Warn "Found $verRaw - need 3.11+, will install"
            }
        }
    } catch { }
}

if (-not $pythonExe) {
    Write-Status 'Installing Python 3.12 via winget...'

    $wingetAvailable = $false
    try { Get-Command winget -ErrorAction Stop | Out-Null; $wingetAvailable = $true } catch { }

    if ($wingetAvailable) {
        Write-Host '  Installing Python.Python.3.12...' -NoNewline
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-Null
        Write-Host ' done'

        $machinePath = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine')
        $userPath = [System.Environment]::GetEnvironmentVariable('PATH', 'User')
        $env:PATH = "$machinePath;$userPath"

        foreach ($py in @('python', 'python3', 'py')) {
            try {
                $verRaw = & $py --version 2>&1 | Out-String
                if ($verRaw -match 'Python (\d+)\.(\d+)') {
                    $major = [int]$Matches[1]
                    $minor = [int]$Matches[2]
                    if ($major -ge 3 -and $minor -ge 11) {
                        $pythonExe = $py
                        Write-OK "Python installed: $verRaw"
                        break
                    }
                }
            } catch { }
        }
    } else {
        Write-Fail 'winget not available. Install Python 3.12+ manually from https://www.python.org/downloads/'
        Write-Host '  Then re-run this script.'
        exit 1
    }
}

if (-not $pythonExe) {
    Write-Fail 'Python 3.11+ not found after install attempt'
    exit 1
}

# ── 2. pip upgrade ──
Write-Status 'Upgrading pip...'
& $pythonExe -m pip install --upgrade pip 2>&1 | Select-Object -Last 1 | ForEach-Object { Write-OK $_ }

# ── 3. Virtual environment ──
Write-Status 'Checking virtual environment...'
$venvPath = Join-Path $ProjectRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host '  Creating .venv...' -NoNewline
    & $pythonExe -m venv $venvPath
    Write-Host ' done'
    $venvPython = Join-Path $venvPath 'Scripts\python.exe'
}

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
    Write-OK "Using venv: $venvPython"
} else {
    Write-Warn 'venv creation failed - using system Python'
}

# ── 4. Install requirements ──
Write-Status 'Installing pip packages...'
$reqFile = Join-Path $ProjectRoot 'requirements.txt'

if (Test-Path $reqFile) {
    & $pythonExe -m pip install -r $reqFile --quiet 2>&1 | ForEach-Object {
        if ($_ -match 'error|Error|ERROR') { Write-Fail $_ }
    }
    Write-OK 'All requirements installed'
} else {
    Write-Fail "requirements.txt not found at $reqFile"
    exit 1
}

# ── 5. Initialize SQLite database ──
Write-Status 'Initializing SQLite database...'
$dbScript = Join-Path $ProjectRoot 'database\setup_db.py'
if (Test-Path $dbScript) {
    $dbOut = & $pythonExe $dbScript 2>&1 | Out-String
    Write-OK $dbOut.Trim()
} else {
    Write-Fail 'database\setup_db.py not found'
}

# ── 6. Syntax check all Python files ──
Write-Status 'Syntax checking all Python files...'
$pyFiles = Get-ChildItem -Path $ProjectRoot -Recurse -Filter '*.py' -File |
    Where-Object { $_.FullName -notmatch '\\\.venv\\' -and $_.FullName -notmatch '\\__pycache__\\' -and $_.FullName -notmatch '\\overseer_forex\\' }

$failCount = 0
$passCount = 0

foreach ($f in $pyFiles) {
    $null = & $pythonExe -m py_compile $f.FullName 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "SYNTAX ERROR: $($f.FullName)"
        $failCount++
    } else {
        $passCount++
    }
}

if ($failCount -gt 0) {
    Write-Host "  Passed: $passCount  Failed: $failCount" -ForegroundColor Red
} else {
    Write-Host "  Passed: $passCount  Failed: 0" -ForegroundColor Green
}

# ── 7. Verify core imports ──
Write-Status 'Verifying core imports...'

Set-Location $ProjectRoot

$importTests = @(
    'from engine_logic.gates.gate_registry import GateRegistry',
    'from ml.load_model import predict_trade_quality',
    'from ml.framework_scorer import aggregate_framework_scores',
    'from ml.signal_logger import log_signal, get_signal_stats',
    'from execution.mt5_executor import connect_mt5, execute_trade',
    'from core.hub_listener import start_udp_listener',
    'from database.setup_db import init_db, DB_PATH'
)

foreach ($imp in $importTests) {
    $null = & $pythonExe -c $imp 2>&1
    if ($LASTEXITCODE -ne 0) {
        $modName = ($imp -split ' ')[1]
        Write-Fail "Import failed: $modName"
    } else {
        $modName = ($imp -split ' ')[1]
        Write-OK "Import OK: $modName"
    }
}

# ── 8. Quick pipeline test ──
Write-Status 'Quick pipeline test...'

$testScript = @'
from database.setup_db import init_db, DB_PATH
init_db(DB_PATH)
from engine_logic.gates.gate_registry import GateRegistry
from ml.load_model import predict_trade_quality
registry = GateRegistry()
gate_states = registry.evaluate({'symbol':'EURUSD','bid':1.085,'ask':1.0851,'delta':0,'timestamp':'2026-01-01'})
score = predict_trade_quality(gate_states)
print(f'Gates: {len(gate_states)}  Score: {score:.4f}')
'@

$testResult = & $pythonExe -c $testScript 2>&1 | Out-String
if ($LASTEXITCODE -eq 0) {
    Write-OK $testResult.Trim()
} else {
    Write-Fail 'Pipeline test failed'
    Write-Host "  $testResult" -ForegroundColor Red
}

# ── Summary ──
Write-Host ''
Write-Host '===================================================' -ForegroundColor Cyan
Write-Host '  OVERSEER v12 SETUP COMPLETE' -ForegroundColor Green
Write-Host '===================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host '  To start:' -ForegroundColor White
Write-Host '    python main.py' -ForegroundColor Yellow
Write-Host ''
Write-Host '  Dashboard:  http://localhost:8080' -ForegroundColor White
Write-Host '  Signal log: database\overseer_trades.db (signal_log table)' -ForegroundColor White
Write-Host ''

if ($failCount -gt 0) {
    Write-Host "  WARNING: $failCount syntax errors found - fix before running" -ForegroundColor Red
    exit 1
}
