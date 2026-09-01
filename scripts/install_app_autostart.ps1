$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Services = @(
    @{ Name = 'CCB Regional - Aplicacao'; Runner = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run_app_server.ps1')).Path; Description = 'Mantem a aplicacao Django local disponivel e reinicia apos falhas.' },
    @{ Name = 'CCB Regional - Espelho SAM'; Runner = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'run_sam_worker.ps1')).Path; Description = 'Mantem a sincronizacao automatica do SAM ativa e reinicia apos falhas.' }
)

function Install-ScheduledServices {
    foreach ($Service in $Services) {
        $Action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$($Service.Runner)`"" -WorkingDirectory $ProjectRoot
        $Trigger = New-ScheduledTaskTrigger -AtLogOn
        $Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $Service.Name -Action $Action -Trigger $Trigger -Settings $Settings -Description $Service.Description -Force -ErrorAction Stop | Out-Null
        Start-ScheduledTask -TaskName $Service.Name -ErrorAction Stop
        Write-Host "Tarefa '$($Service.Name)' instalada e iniciada."
    }
}

function Install-StartupShortcuts {
    $StartupDirectory = [Environment]::GetFolderPath('Startup')
    $Shell = New-Object -ComObject WScript.Shell
    foreach ($Service in $Services) {
        $ShortcutPath = Join-Path $StartupDirectory ($Service.Name + '.lnk')
        $Shortcut = $Shell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = 'powershell.exe'
        $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$($Service.Runner)`""
        $Shortcut.WorkingDirectory = $ProjectRoot
        $Shortcut.Description = $Service.Description
        $Shortcut.WindowStyle = 7
        $Shortcut.Save()
        Start-Process -FilePath 'powershell.exe' -ArgumentList $Shortcut.Arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden
        Write-Host "Inicializacao '$($Service.Name)' instalada e iniciada sem privilegios administrativos."
    }
}

try {
    Install-ScheduledServices
    Write-Host 'Aplicacao e sincronizacao SAM configuradas no Agendador do Windows.'
} catch {
    Write-Warning "Agendador indisponivel ($($_.Exception.Message)). Usando a pasta Inicializar do usuario."
    Install-StartupShortcuts
    Write-Host 'Aplicacao e sincronizacao SAM configuradas na pasta Inicializar do usuario.'
}
