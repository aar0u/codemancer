#!/usr/bin/env bash
# Undo install.sh's unambiguous, ours-only changes (the downloaded model
# and a leftover socket file, if any). Does NOT touch system packages, which
# are shared with other software, so this only prints the command for those
# and leaves the decision to you.
set -euo pipefail

MODEL_DIR="${SENSEVOICE_MODEL_DIR:-$HOME/.local/share/sensevoice}"
SOCK_PATH="${XDG_RUNTIME_DIR:-/tmp}/dictate.sock"

if [[ -d "$MODEL_DIR" ]]; then
  echo "==> Removing $MODEL_DIR"
  rm -rf "$MODEL_DIR"
else
  echo "==> $MODEL_DIR not present, nothing to remove."
fi

if [[ -S "$SOCK_PATH" ]]; then
  echo "==> Removing leftover socket $SOCK_PATH"
  rm -f "$SOCK_PATH"
fi

SERVICE_FILE="$HOME/.config/systemd/user/dictate.service"
if [[ -f "$SERVICE_FILE" ]]; then
  echo "==> Disabling and removing dictate.service"
  systemctl --user disable --now dictate.service 2>/dev/null || true
  rm -f "$SERVICE_FILE"
  systemctl --user daemon-reload
fi

if [[ -f "/usr/lib/fcitx5/libcommit.so" ]]; then
  echo "==> Removing fcitx5-commit addon (/usr/lib/fcitx5/libcommit.so)"
  sudo rm -f /usr/lib/fcitx5/libcommit.so /usr/share/fcitx5/addon/commit.conf
  fcitx5 -r -d 2>/dev/null || true
fi

cat <<EOF

Done. Left alone (shared with other software — remove yourself if you're sure):

  sudo pacman -Rns wtype wl-clipboard portaudio     # pipewire/pipewire-pulse/pipewire-alsa
                                                     # not listed: core system audio, don't touch
EOF
