#!/bin/bash
# Zatrzymuje program eduGO Analiza na Macu (zwykle niepotrzebne – program sam zwalnia pamięć po 15 minutach bezczynności).
cd "$(dirname "$0")" || exit 1
if pkill -f "$(pwd)/.venv/bin/python"; then
  echo "Program eduGO Analiza został zatrzymany."
else
  echo "Program eduGO Analiza nie był uruchomiony."
fi
sleep 2
