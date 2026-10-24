$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
} else {
    $Python = "python"
}

Push-Location $ProjectRoot
try {
    if ($Python -eq "py") {
        & $Python -3.12 scripts\run_all.py
    } else {
        & $Python scripts\run_all.py
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
