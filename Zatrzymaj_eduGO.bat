@echo off
rem Zatrzymuje program eduGO Analiza (normalnie niepotrzebne - program sam zwalnia pamiec po 15 min bezczynnosci).
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "$d = '%~dp0'; Get-CimInstance Win32_Process -Filter \"Name like 'python%%.exe'\" | Where-Object { $_.CommandLine -like ('*' + $d + 'server.py*') } | ForEach-Object { & \"$env:SystemRoot\System32\taskkill.exe\" /T /F /PID $_.ProcessId 2>$null | Out-Null }"
echo Program eduGO Analiza zostal zatrzymany.
"%SystemRoot%\System32\ping.exe" -n 3 127.0.0.1 >nul
