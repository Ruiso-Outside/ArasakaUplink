#!/usr/bin/env bash
# ARASAKA UPLINK // desinstalador (os arquivos recebidos continuam em Downloads/Uplink)
set -uo pipefail
APP_ID=arasaka-uplink
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/$APP_ID"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
rm -f "$HOME/.local/bin/$APP_ID" "$APPS/$APP_ID.desktop" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/$APP_ID.svg" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/icons/Arasaka/scalable/apps/$APP_ID.svg"
rm -rf "$DATA/app" "$DATA/venv"
update-desktop-database -q "$APPS" 2>/dev/null
echo "■ Arasaka Uplink removido. Os arquivos recebidos continuam na pasta Downloads/Uplink."
