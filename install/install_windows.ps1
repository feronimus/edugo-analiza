# eduGO Analiza - instalacja na Windows (jednorazowo, potrzebny internet, ok. 2 GB miejsca).
# Wszystko trafia do folderu programu (Python, biblioteki, modele). Odinstalowanie = usunięcie folderu i skrótu.
# Można uruchomić ponownie w każdej chwili - naprawia niedokończoną instalację.
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"
$App = Split-Path -Parent $PSScriptRoot
Set-Location $App
$UvVersion = "0.6.14"
$Bin = Join-Path $App "runtime\bin"
$Uv = Join-Path $Bin "uv.exe"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $App "runtime\python"
$env:UV_CACHE_DIR = Join-Path $App "runtime\cache"
$env:UV_NO_CONFIG = "1"

function Step($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }
function Retry($block) { for ($i = 1; $i -le 3; $i++) { try { & $block; return } catch { if ($i -eq 3) { throw }; Write-Host "  ponawiam ($i)..."; Start-Sleep 5 } } }

try {
    # Paths with Polish letters can break some model libraries -> keep models in an ASCII-only folder in that case.
    if ($App -match '[^\x00-\x7F]') {
        $Data = Join-Path $env:PUBLIC "eduGO_data"
        Step "Ścieżka folderu programu zawiera polskie znaki – modele zostaną zapisane w $Data"
        New-Item -ItemType Directory -Force $Data | Out-Null
        $settings = @{ data_dir = $Data } | ConvertTo-Json
        [IO.File]::WriteAllText((Join-Path $App "settings.json"), $settings)
    }

    Step "1/4 Narzędzie instalacyjne (uv $UvVersion)"
    if (-not (Test-Path $Uv)) {
        New-Item -ItemType Directory -Force $Bin | Out-Null
        $zip = Join-Path $env:TEMP "edugo_uv.zip"
        Retry { Invoke-WebRequest "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip -UseBasicParsing }
        Expand-Archive $zip -DestinationPath $Bin -Force
        Remove-Item $zip -Force
    }

    Step "2/4 Python 3.13 i biblioteki (kilka minut)"
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Retry { & $Uv venv .venv --python 3.13 --python-preference only-managed; if ($LASTEXITCODE) { throw "uv venv" } }
    }
    Retry { & $Uv pip install --python .venv\Scripts\python.exe -r requirements.txt; if ($LASTEXITCODE) { throw "uv pip" } }

    Step "3/4 Modele (ok. 700 MB, jednorazowo)"
    Retry { & .venv\Scripts\python.exe install\setup_models.py; if ($LASTEXITCODE) { throw "models" } }

    Step "4/4 Skrót na pulpicie"
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "eduGO Analiza.lnk"))
    $lnk.TargetPath = Join-Path $App ".venv\Scripts\pythonw.exe"
    $lnk.Arguments = "`"$(Join-Path $App 'server.py')`" --open"
    $lnk.WorkingDirectory = $App
    $lnk.IconLocation = Join-Path $App "static\favicon.ico"
    $lnk.Description = "eduGO - analiza lekcji"
    $lnk.Save()

    Write-Host ""
    Write-Host "GOTOWE. Uruchamiaj program ikoną 'eduGO Analiza' na pulpicie." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Instalacja nie powiodła się: $_" -ForegroundColor Red
    Write-Host "Sprawdź połączenie z internetem i uruchom instalację jeszcze raz (zostanie wznowiona od miejsca przerwania)."
    exit 1
}
