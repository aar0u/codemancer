#!/usr/bin/env bash
set -euo pipefail

# Keep both OCR stacks available so changing OCR_ENGINE needs no rebuild-script edit.
uv run \
  --with pyinstaller \
  --with pyqt6==6.9.1 \
  --with pynput==1.8.2 \
  --with rapidocr==3.9.2 \
  --with onnxruntime==1.23.2 \
  --with paddleocr==3.7.0 \
  --with paddlepaddle==3.3.1 \
  pyinstaller \
  --onedir \
  --noconfirm \
  --windowed \
  --icon icons8-screenshot-100.ico \
  --add-data 'icons8-screenshot-100.png:.' \
  --contents-directory . \
  --workpath Z:/build/temp \
  --distpath Z:/build \
  shotnpin.py
