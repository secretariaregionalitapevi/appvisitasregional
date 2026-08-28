$ErrorActionPreference = 'Stop'
$Runner = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run_sam_worker.ps1')).Path
$RunnerCommand = "& '" + $Runner.Replace("'", "''") + "'"
$EncodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($RunnerCommand))
$StartupDirectory = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDirectory 'CCB Regional - Espelho SAM.lnk'

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = 'powershell.exe'
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $EncodedCommand"
$Shortcut.WorkingDirectory = (Split-Path $Runner -Parent)
$Shortcut.Description = 'Sincronização automática do SAM com o painel GEM'
$Shortcut.WindowStyle = 7
$Shortcut.Save()

Start-Process -FilePath 'powershell.exe' `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -EncodedCommand $EncodedCommand" `
    -WindowStyle Hidden

Write-Host "Inicialização automática instalada em: $ShortcutPath"
