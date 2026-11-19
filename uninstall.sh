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
if [ -e /usr/libexec/arasaka-uplink-auth ] || [ -e /usr/share/polkit-1/actions/studio.arasaka.uplink.policy ]; then
  sudo -n rm -f /usr/libexec/arasaka-uplink-auth /usr/share/polkit-1/actions/studio.arasaka.uplink.policy 2>/dev/null || \
    echo "Para tirar a acao de senha do sistema: sudo rm /usr/libexec/arasaka-uplink-auth /usr/share/polkit-1/actions/studio.arasaka.uplink.policy"
fi
update-desktop-database -q "$APPS" 2>/dev/null
echo "■ Arasaka Uplink removido. Os arquivos recebidos continuam na pasta Downloads/Uplink."
