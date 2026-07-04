<#
.SYNOPSIS
OVERSEER v12 Watchdog - Keeps main.py running 24/7
.DESCRIPTION
Auto-starts main.py, monitors it, auto-restarts on crash,
logs output to file, sends Telegram notification on crash/restart.
Run: .\run_watchdog.ps1
Stop: Ctrl+C or close this window
#>

$ProjectRoot = $PSScriptRoot
$LogFile = Join-Path $ProjectRoot 'logs\overseer.log'
$CrashLog = Join-Path $ProjectRoot 'logs\crashes.log'
$LockFile = Join-Path $ProjectRoot 'logs\watchdog.lock'

$null = New-Item -ItemType Directory -Path (Join-Path $ProjectRoot 'logs') -Force -ErrorAction SilentlyContinue

if (Test-Path $LockFile) {
    $lockPid = Get-Content $LockFile -ErrorAction SilentlyContinue
    if ($lockPid -and (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
        Write-Host "Watchdog already running (PID $lockPid). Exiting." -ForegroundColor Red
        exit 1
    }
}
$PID | Set-Content $LockFile

function Write-Log([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] $msg"
    Write-Host $line -ForegroundColor Cyan
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Write-CrashLog([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] $msg"
    Add-Content -Path $CrashLog -Value $line -Encoding UTF8
}

function Send-Telegram([string]$msg) {
    try {
        $envFile = Join-Path $ProjectRoot '.env'
        $token = ''
        $chatId = ''
        if (Test-Path $envFile) {
            $token = (Get-Content $envFile | Where-Object { $_ -match '^TELEGRAM_BOT_TOKEN=(.+)' }) -replace '^TELEGRAM_BOT_TOKEN=', ''
            $chatId = (Get-Content $envFile | Where-Object { $_ -match '^TELEGRAM_CHAT_ID=(.+)' }) -replace '^TELEGRAM_CHAT_ID=', ''
        }
        if ($token -and $chatId -and $token -ne 'your_bot_token_here') {
            $encoded = [System.Uri]::EscapeDataString($msg)
            $url = "https://api.telegram.org/bot$token/sendMessage?chat_id=$chatId&text=$encoded&parse_mode=HTML"
            Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5 | Out-Null
        }
    } catch { }
}

$restartCount = 0
$backoffSeconds = 5
$maxBackoff = 300

Write-Log 'OVERSEER Watchdog started'
Send-Telegram '<b>OVERSEER Watchdog</b> started - monitoring main.py'

while ($true) {
    $startTime = Get-Date

    $existingMain = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'main.py' -and $_.Id -ne $proc.Id }
    if ($existingMain) {
        Write-Log "Killing stale main.py (PID $($existingMain.Id))"
        $existingMain | Stop-Process -Force
        Start-Sleep -Seconds 2
    }

    Write-Log "Starting main.py (attempt $($restartCount + 1))..."

    $proc = Start-Process -FilePath 'python' -ArgumentList 'main.py' -WorkingDirectory $ProjectRoot -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $ProjectRoot 'logs\stdout.log') -RedirectStandardError (Join-Path $ProjectRoot 'logs\stderr.log')

    Write-Log "PID: $($proc.Id)"

    $proc.WaitForExit()

    $exitCode = $proc.ExitCode
    $uptime = (Get-Date) - $startTime
    $uptimeStr = '{0:hh}:{0:mm}:{0:ss}' -f $uptime

    if ($exitCode -eq 0) {
        Write-Log "main.py exited cleanly after $uptimeStr - restarting to keep OVERSEER always on"
        Send-Telegram "<b>OVERSEER</b> exited cleanly after $uptimeStr - restarting"
        Start-Sleep -Seconds $backoffSeconds
        continue
    }

    $restartCount++

    Write-Log "CRASH detected! Exit code: $exitCode Uptime: $uptimeStr (restart #$restartCount)"
    Write-CrashLog "CRASH #$restartCount exit=$exitCode uptime=$uptimeStr"

    $stderrPath = Join-Path $ProjectRoot 'logs\stderr.log'
    $crashInfo = ''
    if (Test-Path $stderrPath) {
        $lastLines = Get-Content $stderrPath -Tail 5 -ErrorAction SilentlyContinue
        $crashInfo = ($lastLines -join ' | ').Substring(0, [Math]::Min(200, ($lastLines -join ' | ').Length))
    }

    Send-Telegram "<b>OVERSEER CRASH</b> #$restartCount exit=$exitCode uptime=$uptimeStr`n$crashInfo"

    $waitTime = [Math]::Min($backoffSeconds * [Math]::Pow(2, $restartCount - 1), $maxBackoff)
    Write-Log "Waiting $waitTime seconds before restart..."
    Start-Sleep -Seconds $waitTime
}

Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
Write-Log 'Watchdog stopped'
