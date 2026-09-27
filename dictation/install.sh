#!/usr/bin/env bash
# One-time setup: SenseVoice-Small (sherpa-onnx) local dictation for CachyOS + KDE Plasma.
# Run manually on the CachyOS host (not in a container): bash install.sh
#
# No systemd service — this is ad-hoc: run `./dictate.py` yourself whenever
# you want dictation live, Ctrl+C to stop it.
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

cat <<EOF

Done.

Run it whenever you want dictation live (ad-hoc, no service):

  $DICT_DIR/dictate.py

First run resolves/downloads its uv dependencies (sherpa-onnx, sounddevice,
numpy, evdev) AND the SenseVoice-Small int8 model (~230MB, to
\${SENSEVOICE_MODEL_DIR:-~/.local/share/sensevoice}) — give it a minute
before testing. Ctrl+C to stop it.

Push-to-talk, no shortcut binding needed:
  - Keyboard: hold Scroll Lock, speak, release.
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
