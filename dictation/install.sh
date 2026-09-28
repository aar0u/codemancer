#!/usr/bin/env bash
# One-time setup: SenseVoice-Small (sherpa-onnx) local dictation for CachyOS + KDE Plasma.
# Run manually on the CachyOS host (not in a container): bash install.sh
set -euo pipefail

DICT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing system packages (pacman)"
sudo pacman -S --needed --noconfirm \
  pipewire pipewire-pulse pipewire-alsa \
  ydotool wl-clipboard \
  portaudio

echo "==> Enabling ydotoold (kernel-level /dev/uinput text injection; works regardless"
echo "    of which Wayland protocols the compositor implements)"
sudo systemctl enable --now ydotool.service 2>/dev/null || {
  echo "    ydotool.service not found, enabling user unit instead"
  systemctl --user enable --now ydotool 2>/dev/null || true
}
# ydotool talks to /dev/uinput; make sure the current user can reach it without sudo each time.
if ! groups "$USER" | grep -qw input; then
  echo "==> Adding $USER to the 'input' group (log out/in required once)"
  sudo usermod -aG input "$USER"
fi

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
chmod +x "$DICT_DIR/dictate.py" "$DICT_DIR/toggle.py" "$DICT_DIR/sniff_key.py"
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
numpy, evdev) AND the SenseVoice-Small int8 model (~230MB, to
\${SENSEVOICE_MODEL_DIR:-~/.local/share/sensevoice}) — give it a minute
before testing. Ctrl+C to stop it.

Push-to-talk, no shortcut binding needed:
  - Keyboard: hold Right Ctrl, speak, release.
  - Mouse: hold the side button, speak, release.
Watch its terminal output for lines starting with '[hotkey] watching' to
confirm both devices were found. If a device wasn't found (wrong name
match), set DICTATE_KEYBOARD_DEVICE / DICTATE_MOUSE_DEVICE env vars before
running it — see README.md.

Want a manual toggle trigger too (e.g. a one-off DE shortcut)? Start with
'--toggle' instead so it opens a socket for './toggle.py':

  $DICT_DIR/dictate.py --toggle

If you were just added to the 'input' group, log out and back in once
before the first use, otherwise ydotool/evdev will fail with a permission
error.
EOF
