#!/usr/bin/env bash
# One-time setup: SenseVoice-Small (sherpa-onnx) local dictation for CachyOS + Hyprland.
# Run manually on the CachyOS host (not in a container): bash install.sh
set -euo pipefail

DICT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing system packages (pacman)"
sudo pacman -S --needed --noconfirm \
  pipewire pipewire-pulse pipewire-alsa \
  wtype wl-clipboard \
  portaudio

if command -v fcitx5 &>/dev/null && [ -d "$DICT_DIR/fcitx5-commit" ]; then
  echo "==> Building and installing fcitx5-commit addon (native D-Bus text injection)"
  sudo pacman -S --needed --noconfirm cmake extra-cmake-modules base-devel
  cmake -B "$DICT_DIR/fcitx5-commit/build" -S "$DICT_DIR/fcitx5-commit" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr
  cmake --build "$DICT_DIR/fcitx5-commit/build" -j"$(nproc)"
  sudo cmake --install "$DICT_DIR/fcitx5-commit/build"
  fcitx5 -r -d 2>/dev/null || true
fi

echo "==> Setting up systemd user service (dictate.service)"
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/dictate"
if [ ! -f "$HOME/.config/dictate/env" ]; then
  cat > "$HOME/.config/dictate/env" << 'EOF'
# Dictation Configuration
# Uncomment to enable cloud ASR via standard OpenAI-compatible API (e.g. Groq, SiliconFlow, OpenAI)
# DICTATE_API_KEY=gsk_xxxxxxxxxxxx
# DICTATE_API_BASE=https://api.groq.com/openai/v1
# DICTATE_API_MODEL=whisper-large-v3-turbo
EOF
  chmod 600 "$HOME/.config/dictate/env"
fi
chmod +x "$DICT_DIR/dictate.py" "$DICT_DIR/toggle.py"
ln -sf "$DICT_DIR/dictate.service" "$HOME/.config/systemd/user/dictate.service"
systemctl --user daemon-reload
systemctl --user enable --now dictate.service

cat <<EOF

Done.

Daemon is managed via systemd user service:
  - Check status : systemctl --user status dictate
  - View live logs: journalctl --user -u dictate -f
  - Restart      : systemctl --user restart dictate

First run resolves/downloads its uv dependencies (sherpa-onnx, sounddevice,
numpy) AND the SenseVoice-Small int8 model (~230MB, to
\${SENSEVOICE_MODEL_DIR:-~/.local/share/sensevoice}) — give it a minute
before testing.

Push-to-talk needs Hyprland binds that call toggle.py (no input-group
access involved); see README.md for the hypr/hyprland.lua snippet.
EOF
