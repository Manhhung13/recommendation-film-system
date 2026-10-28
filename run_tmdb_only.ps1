param([ValidateSet("Test30", "Full")][string]$Mode = "Test30")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$Python = ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Missing .venv. Run .\run_windows.ps1 first." }
if ($Mode -eq "Full") {
    & $Python acquire_all_data.py --workdir .\dataset_linkage_work --full
} else {
    & $Python acquire_all_data.py --workdir .\dataset_linkage_work --tmdb-limit 30
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python verify_raw_data.py --workdir .\dataset_linkage_work
exit $LASTEXITCODE
