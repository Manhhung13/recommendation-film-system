param([ValidateSet("Test30", "Full")][string]$Mode = "Test30")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$VenvPython = ".venv\Scripts\python.exe"
$VenvWorks = (Test-Path -LiteralPath $VenvPython)
if ($VenvWorks) {
    & $VenvPython -c "import sys" 2>$null
    $VenvWorks = ($LASTEXITCODE -eq 0)
}
if (-not $VenvWorks) {
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv --clear .venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { python -m venv --clear .venv }
    else { throw "Python 3 was not found on PATH." }
}
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($Mode -eq "Full") {
    & ".venv\Scripts\python.exe" acquire_all_data.py --workdir .\dataset_linkage_work --full
} else {
    & ".venv\Scripts\python.exe" acquire_all_data.py --workdir .\dataset_linkage_work --tmdb-limit 30
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ".venv\Scripts\python.exe" verify_raw_data.py --workdir .\dataset_linkage_work
exit $LASTEXITCODE
