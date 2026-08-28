$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PythonExe = (Get-Command python -ErrorAction Stop).Source
$ScraperDir = $env:SAM_SCRAPER_DIR
if (-not $ScraperDir -or -not (Test-Path -LiteralPath (Join-Path $ScraperDir 'web_scraper.py'))) {
    $ProjectParent = Split-Path $ProjectRoot -Parent
    $Candidates = @(
        Get-ChildItem -LiteralPath $ProjectParent -Directory -Filter 'PROJETO_SAM*' -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'web_scraper.py') }
    )
    if ($Candidates.Count -ne 1) {
        throw "Não foi possível localizar de forma única a pasta do scraper SAM em $ProjectParent."
    }
    $ScraperDir = $Candidates[0].FullName
}
$env:SAM_SCRAPER_DIR = $ScraperDir
$LogDirectory = Join-Path $ProjectRoot 'relatorios\sam-sync'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$DateStamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$LogPath = Join-Path $LogDirectory "worker-$DateStamp-$PID.log"

Set-Location -LiteralPath $ProjectRoot
$ErrorActionPreference = 'Continue'
& $PythonExe manage.py run_sam_sync_worker 2>&1 | Tee-Object -FilePath $LogPath -Append
exit $LASTEXITCODE
