@echo off
rem eduGO Analiza - instalacja (Windows 10/11). Kliknij dwukrotnie. Potrzebny internet, ok. 2 GB miejsca, 5-15 minut.
if not exist "%~dp0install\install_windows.ps1" (
    echo.
    echo  Najpierw rozpakuj plik ZIP:
    echo  kliknij go PRAWYM przyciskiem myszy - "Wyodrebnij wszystkie..." - "Wyodrebnij",
    echo  a potem w rozpakowanym folderze kliknij dwukrotnie "Zainstaluj_Windows".
    echo.
    pause
    exit /b 1
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install_windows.ps1"
echo.
pause
