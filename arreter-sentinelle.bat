@echo off
setlocal
cd /d "%~dp0"
rem Arrete la Tri-Sentinelle en cours d'execution.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' OR Name = 'pythonw.exe'\" | Where-Object { $_.CommandLine -like '*surveille-mail-message-comptage.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('Sentinelle arretee (PID ' + $_.ProcessId + ')') }"
exit /b 0
