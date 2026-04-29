$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$env:TAPADOSPRI_DB_ROOT = "C:\Users\Dell\Dropbox\TapadosPRI"
$env:TAPADOSPRI_DATA_DIR = Join-Path $env:TAPADOSPRI_DB_ROOT "data"
$env:TAPADOSPRI_OUTPUT_DIR = Join-Path $env:TAPADOSPRI_DB_ROOT "output"
$env:TAPADOSPRI_LITERATURE_DIR = Join-Path $env:TAPADOSPRI_DB_ROOT "literature"

$activatePath = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $activatePath) {
    . $activatePath
    Write-Host "TapadosPRI environment activated." -ForegroundColor Green
    Write-Host "DB root: $env:TAPADOSPRI_DB_ROOT"
} else {
    Write-Warning "Virtual environment not found at $activatePath"
}
