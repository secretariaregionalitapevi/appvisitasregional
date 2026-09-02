$ErrorActionPreference = 'Stop'
$SupervisorMutex = [Threading.Mutex]::new($false, 'Local\CCBRegionalAppServerSupervisor')
if (-not $SupervisorMutex.WaitOne(0)) { exit 0 }
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PythonExe = (Get-Command python -ErrorAction Stop).Source
$LogDirectory = Join-Path $ProjectRoot 'relatorios\app-server'
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogPath = Join-Path $LogDirectory ("server-{0}-{1}.log" -f (Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'), $PID)

Set-Location -LiteralPath $ProjectRoot
$ErrorActionPreference = 'Continue'
while ($true) {
    "[$(Get-Date -Format o)] Iniciando servidor local em 127.0.0.1:8000." | Tee-Object -FilePath $LogPath -Append
    & $PythonExe manage.py runserver 127.0.0.1:8000 2>&1 | Tee-Object -FilePath $LogPath -Append
    $ServerExitCode = $LASTEXITCODE
    "[$(Get-Date -Format o)] Servidor encerrado com codigo $ServerExitCode; reiniciando em 10 segundos." |
        Tee-Object -FilePath $LogPath -Append
    Start-Sleep -Seconds 10
}
