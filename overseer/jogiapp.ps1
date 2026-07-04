$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $ProjectRoot 'jogiapp.py') --open
} else {
    python (Join-Path $ProjectRoot 'jogiapp.py') --open
}
