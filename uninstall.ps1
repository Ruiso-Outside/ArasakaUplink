# ARASAKA UPLINK // desinstalador Windows
# powershell -ExecutionPolicy Bypass -File uninstall.ps1
$App  = 'arasaka-uplink'
$Data = Join-Path $env:LOCALAPPDATA $App
$Bin  = Join-Path $Data 'bin'
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$Data*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
foreach ($l in @((Join-Path ([Environment]::GetFolderPath('Programs')) 'Arasaka Uplink.lnk'),
                 (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Arasaka Uplink.lnk'))) {
    if (Test-Path $l) { Remove-Item -Force $l }
}

$up = [Environment]::GetEnvironmentVariable('Path', 'User')
[Environment]::SetEnvironmentVariable('Path', (($up -split ';' | Where-Object { $_ -and $_ -ne $Bin }) -join ';'), 'User')
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Data
Write-Host " ■ ARASAKA UPLINK REMOVIDO (os seus dados foram mantidos)" -ForegroundColor Red
