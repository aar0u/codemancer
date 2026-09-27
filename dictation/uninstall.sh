#!/usr/bin/env bash
# Undo install.sh's unambiguous, ours-only changes (the downloaded model
# and a leftover socket file, if any). Does NOT touch system packages or
# your 'input' group membership — those are shared with other software,
# so this only prints the commands for those and leaves the decision to you.
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

cat <<EOF

Done. Left alone (shared with other software — remove yourself if you're sure):

  sudo pacman -Rns ydotool wl-clipboard portaudio   # pipewire/pipewire-pulse/pipewire-alsa
                                                     # not listed: core system audio, don't touch

  sudo gpasswd -d "\$USER" input                      # only if nothing else you use needs
                                                     # /dev/input access (e.g. input-remapper)

  sudo systemctl disable --now ydotool.service       # or: systemctl --user disable --now ydotool
                                                     # only if nothing else uses ydotoold
EOF
