param(
    [Parameter(Mandatory = $true)]
    [string]$User,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [string]$SystemName = "Rithmic Paper Trading",
    [string]$Url = "wss://rituz00100.rithmic.com:443",
    [string]$Symbols = "6EM6:CME,6BM6:CME,6JM6:CME,6AM6:CME,6CM6:CME,6NM6:CME"
)

$env:RITHMIC_USER = $User
$env:RITHMIC_PASSWORD = $Password
$env:RITHMIC_SYSTEM_NAME = $SystemName
$env:RITHMIC_URL = $Url
$env:RITHMIC_SYMBOLS = $Symbols
$env:OVERSEER_UDP_HOST = "127.0.0.1"
$env:OVERSEER_UDP_PORT = "65000"

python "$PSScriptRoot\rithmic_mbo_udp_bridge.py"
