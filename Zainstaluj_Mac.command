#!/bin/bash
# eduGO Analiza - instalacja na Macu (Apple M1-M4: macOS 14+, Intel: macOS 13+). Potrzebny internet, ok. 2 GB, 5-15 minut.
# Pierwszy raz: prawy klik na tym pliku -> Otwórz (macOS pyta o zgodę na pliki z internetu).
# Wszystko trafia do folderu programu. Można uruchomić ponownie - dokończy niedokończoną instalację.
set -u
cd "$(dirname "$0")" || exit 1
APP="$(pwd)"
UV_VERSION="0.6.14"
export UV_PYTHON_INSTALL_DIR="$APP/runtime/python" UV_CACHE_DIR="$APP/runtime/cache" UV_NO_CONFIG=1
fail() { echo; echo "Instalacja nie powiodła się: $1"; echo "Sprawdź połączenie z internetem i uruchom instalację jeszcze raz."; read -r -p "Naciśnij Enter, aby zamknąć."; exit 1; }
stop() { echo; echo "$1"; read -r -p "Naciśnij Enter, aby zamknąć."; exit 1; }
retry() { for i in 1 2 3; do "$@" && return 0; echo "  ponawiam ($i)..."; sleep 5; done; return 1; }

MACOS="$(sw_vers -productVersion)"; MAJOR="${MACOS%%.*}"
if [ "$(uname -m)" = arm64 ] && [ "$MAJOR" -lt 14 ]; then stop "Ten Mac ma macOS $MACOS – potrzebny jest macOS 14 (Sonoma) lub nowszy. Zaktualizuj system (Ustawienia systemowe → Ogólne → Uaktualnienia oprogramowania)."; fi
if [ "$(uname -m)" != arm64 ] && [ "$MAJOR" -lt 13 ]; then stop "Ten Mac ma macOS $MACOS – potrzebny jest macOS 13 (Ventura) lub nowszy. Zaktualizuj system (Ustawienia systemowe → Ogólne → Uaktualnienia oprogramowania)."; fi

if LC_ALL=C grep -q '[^ -~]' <<< "$APP"; then
  DATA="$HOME/eduGO_data"; mkdir -p "$DATA"
  printf '{"data_dir": "%s"}\n' "$DATA" > "$APP/settings.json"
  echo "Ścieżka folderu programu zawiera polskie znaki – modele zostaną zapisane w $DATA"
fi

echo "== 1/4 Narzędzie instalacyjne (uv $UV_VERSION)"
if [ ! -x runtime/bin/uv ]; then
  case "$(uname -m)" in arm64) T=aarch64-apple-darwin ;; *) T=x86_64-apple-darwin ;; esac
  mkdir -p runtime/bin
  retry bash -c "curl -fsSL https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$T.tar.gz | tar xz -C runtime/bin --strip-components 1" || fail "pobieranie uv"
fi

echo "== 2/4 Python 3.13 i biblioteki (kilka minut)"
[ -x .venv/bin/python ] || retry runtime/bin/uv venv .venv --python 3.13 --python-preference only-managed || fail "python"
retry runtime/bin/uv pip install --python .venv/bin/python -r requirements.txt || fail "biblioteki"

echo "== 3/4 Modele (ok. 700 MB, jednorazowo)"
retry .venv/bin/python install/setup_models.py || fail "modele"

echo "== 4/4 Ikona na biurku"
# Full paths, so that Zatrzymaj_eduGO.command finds exactly this copy's processes. The program writes its own log
# (data/server.log), so the terminal output can be thrown away.
osacompile -o "$HOME/Desktop/eduGO Analiza.app" -e "do shell script \"cd \" & quoted form of \"$APP\" & \" && nohup \" & quoted form of \"$APP/.venv/bin/python\" & \" \" & quoted form of \"$APP/server.py\" & \" --open > /dev/null 2>&1 &\"" \
  || fail "ikona"
echo
echo "GOTOWE. Uruchamiaj program ikoną „eduGO Analiza” na biurku."
read -r -p "Naciśnij Enter, aby zamknąć."
