# Build and deploy the OVERSEER Quantower bridge strategy.
# Run from PowerShell as Administrator if copying to Program Files.

param(
    [string]$QuantowerPath = $env:QuantowerPath,
    [string]$Configuration = "Release",
    [string]$StrategyName = "OverseerBridge"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Split-Path -Parent $scriptDir

# Auto-detect Quantower path if not provided
if (-not $QuantowerPath) {
    $quantowerBase = "C:\Quantower\TradingPlatform"
    if (Test-Path $quantowerBase) {
        $versions = Get-ChildItem -Path $quantowerBase -Directory | Sort-Object Name -Descending
        if ($versions) {
            $latest = $versions[0].FullName
            $candidate = Join-Path $latest "bin"
            if (Test-Path (Join-Path $candidate "TradingPlatform.BusinessLayer.dll")) {
                $QuantowerPath = $candidate
            }
        }
    }
}

if (-not $QuantowerPath -or -not (Test-Path (Join-Path $QuantowerPath "TradingPlatform.BusinessLayer.dll"))) {
    Write-Error "Could not find TradingPlatform.BusinessLayer.dll. Please install Quantower or set `$env:QuantowerPath to the Quantower bin folder."
}

Write-Host "Using Quantower path: $QuantowerPath"

# Build
$csproj = Join-Path $scriptDir "$StrategyName.csproj"
if (-not (Test-Path $csproj)) {
    Write-Error "Project file not found: $csproj"
}

$env:QuantowerPath = $QuantowerPath
dotnet build "$csproj" -c $Configuration

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed."
}

# Deploy to Quantower strategies folder
$strategiesDir = Join-Path $env:USERPROFILE "Documents\Quantower\Strategies"
if (-not (Test-Path $strategiesDir)) {
    New-Item -ItemType Directory -Path $strategiesDir -Force | Out-Null
}

$dll = Join-Path $scriptDir "bin\$Configuration\net8.0-windows\$StrategyName.dll"
if (-not (Test-Path $dll)) {
    Write-Error "Built DLL not found: $dll"
}

Copy-Item -Path $dll -Destination $strategiesDir -Force
Write-Host "Deployed $dll to $strategiesDir"
Write-Host "Open Quantower Strategy Manager and start '$StrategyName'."
