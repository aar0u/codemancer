#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["sherpa-onnx", "sounddevice", "numpy", "evdev"]
# ///
"""SenseVoice dictation — run ad-hoc in a terminal. See README.md for the why.

Push-to-talk via evdev (bypasses the DE's global-shortcut system, which
on KDE only fires on key-down) drives start()/stop() below. Pass --toggle
to also open a Unix socket for `toggle.py` (manual testing / an optional
extra DE shortcut) — off by default so no socket file is left behind.
"""
import argparse
import os
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd
from evdev import InputDevice, ecodes, list_devices

MODEL_ROOT = Path(os.environ.get("SENSEVOICE_MODEL_DIR", str(Path.home() / ".local/share/sensevoice")))
MODEL_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL_NAME}.tar.bz2"
MODEL_DIR = MODEL_ROOT / MODEL_NAME
SAMPLE_RATE = 16000
SILENCE_RMS_THRESHOLD = 0.01  # below this, treat the recording as silence (mic bump, accidental press)
MIN_SPEECH_DURATION = 0.15  # seconds; shorter is almost certainly a key-click, not real speech
SOCK_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dictate.sock"
# Must outlast the target app's clipboard read, or the restore clobbers the paste.
CLIPBOARD_RESTORE_DELAY = float(os.environ.get("DICTATE_CLIPBOARD_RESTORE_DELAY", "0.6"))

KEYBOARD_KEY = os.environ.get("DICTATE_KEYBOARD_KEY", "KEY_RIGHTCTRL")
MOUSE_BUTTON = os.environ.get("DICTATE_MOUSE_BUTTON", "BTN_EXTRA")
KEYBOARD_DEVICE = os.environ.get("DICTATE_KEYBOARD_DEVICE")
MOUSE_DEVICE = os.environ.get("DICTATE_MOUSE_DEVICE")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def notify(msg: str) -> None:
    subprocess.run(["notify-send", "-t", "2000", "Dictate", msg], check=False)


def _timed_run(label: str, *args, **kwargs) -> subprocess.CompletedProcess:
    start = time.monotonic()
    result = subprocess.run(*args, **kwargs)
    log(f"[timing] {label} took {time.monotonic() - start:.3f}s (exit {result.returncode})")
    return result


def _wl_copy(data: bytes, *, primary: bool, mime: str | None = None) -> subprocess.CompletedProcess:
    args = ["wl-copy"]
    if primary:
        args.append("--primary")
    if mime:
        args += ["--type", mime]
    # wl-copy stays running in the background to serve the selection; piping
    # its stdout/stderr makes subprocess.run() hang waiting for a pipe EOF
    # that only comes when that background process exits. -> /dev/null.
    return _timed_run(
        " ".join(args), args, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )


def _wl_paste(*, primary: bool, mime: str | None = None) -> bytes | None:
    args = ["wl-paste"]
    if primary:
        args.append("--primary")
    if mime:
        args += ["--type", mime]
    args.append("-n")
    result = _timed_run(" ".join(args), args, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def _backup_selection(*, primary: bool) -> tuple[bytes, str] | None:
    """Snapshot a selection as whatever MIME type it actually holds (not
    just text/plain), so restoring afterward doesn't clobber e.g. a copied
    image with an empty string."""
    args = ["wl-paste", "--list-types"]
    if primary:
        args.insert(1, "--primary")
    result = subprocess.run(args, capture_output=True, check=False)
    types = [t.strip() for t in result.stdout.decode(errors="replace").splitlines() if t.strip()]
    if not types:
        return None
    mime = types[0]
    data = _wl_paste(primary=primary, mime=mime)
    return (data, mime) if data is not None else None


def type_text(text: str) -> None:
    """Paste via clipboard + Shift+Insert (not Ctrl+V — see README).

    Sets both CLIPBOARD and PRIMARY selection: some terminals (WezTerm)
    bind Shift+Insert to PRIMARY (the mouse-selection buffer) rather than
    CLIPBOARD, a separate buffer wl-copy doesn't touch by default.
    """
    old_clip = _backup_selection(primary=False)
    old_primary = _backup_selection(primary=True)

    copy = _wl_copy(text.encode(), primary=False)
    _wl_copy(text.encode(), primary=True)
    if copy.returncode != 0:
        log(f"[wl-copy] exited {copy.returncode}")
        return
    time.sleep(0.05)

    # KEY_LEFTSHIFT=42, KEY_INSERT=110 (Linux evdev keycodes)
    paste = _timed_run(
        "ydotool key (Shift+Insert)",
        ["ydotool", "key", "42:1", "110:1", "110:0", "42:0"],
        capture_output=True,
        check=False,
    )
    if paste.returncode != 0:
        log(f"[ydotool key] exited {paste.returncode}: {paste.stderr.decode(errors='replace').strip()}")
    else:
        log("[type] pasted via ydotool (Shift+Insert)")

    if old_clip is not None or old_primary is not None:
        time.sleep(CLIPBOARD_RESTORE_DELAY)
        if old_clip is not None:
            _wl_copy(old_clip[0], primary=False, mime=old_clip[1])
        if old_primary is not None:
            _wl_copy(old_primary[0], primary=True, mime=old_primary[1])


def ensure_model() -> None:
    if (MODEL_DIR / "model.int8.onnx").exists():
        return
    log(f"[model] not found at {MODEL_DIR}, downloading (~230MB)...")
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    archive = MODEL_ROOT / f"{MODEL_NAME}.tar.bz2"
    urllib.request.urlretrieve(MODEL_URL, archive)
    with tarfile.open(archive) as tar:
        tar.extractall(MODEL_ROOT, filter="data")
    archive.unlink()
    log(f"[model] extracted to {MODEL_DIR}")


def build_recognizer() -> sherpa_onnx.OfflineRecognizer:
    ensure_model()
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(MODEL_DIR / "model.int8.onnx"),
        tokens=str(MODEL_DIR / "tokens.txt"),
        num_threads=4,
        use_itn=True,
        language="auto",
    )


def transcribe(recognizer: sherpa_onnx.OfflineRecognizer, samples: np.ndarray) -> str:
    """Decode the whole recording in one shot — no VAD segmentation (tried, dropped; see README)."""
    stream = recognizer.create_stream()
    stream.accept_waveform(SAMPLE_RATE, samples)
    recognizer.decode_stream(stream)
    return stream.result.text.strip()


class Dictation:
    def __init__(self) -> None:
        self.recognizer = build_recognizer()
        self.frames: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.lock = threading.Lock()
        self.finish_lock = threading.Lock()  # serializes _finish() across overlapping sessions
        self.active_source: str | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        self.frames.append(indata.copy())

    def start(self, source: str = "socket") -> None:
        with self.lock:
            if self.stream is not None:
                return
            self.frames = []
            self.active_source = source
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self.stream.start()
            notify("录音中…")

    def stop(self, source: str = "socket") -> None:
        # Only the source that started a recording may stop it — otherwise
        # e.g. brushing the keyboard hotkey while holding the mouse one
        # would cut the mouse-triggered recording short.
        with self.lock:
            if self.stream is None or self.active_source != source:
                return
            self.stream.stop()
            self.stream.close()
            self.stream = None
            self.active_source = None
            frames = self.frames
            self.frames = []

        # notify("转写中…")
        # Runs off the caller's thread (a DeviceWatcher) so it can get back
        # to read_loop() immediately instead of blocking on ASR/paste.
        threading.Thread(target=self._finish, args=(frames,), daemon=True).start()

    def _finish(self, frames: list[np.ndarray]) -> None:
        # Serializes overlapping sessions so two clipboard/paste operations
        # never interleave; only ever held by background _finish threads,
        # never by a DeviceWatcher, so hotkeys keep responding immediately.
        with self.finish_lock:
            if not frames:
                notify("没识别到内容")
                return

            samples = np.concatenate(frames)[:, 0]
            duration = len(samples) / SAMPLE_RATE
            peak = float(np.abs(samples).max()) if len(samples) else 0.0
            rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
            log(f"[audio] captured {duration:.2f}s ({len(samples)} samples) peak={peak:.4f} rms={rms:.4f}")

            # Exact zero means PortAudio's device table went stale (real
            # silence still has a noise floor) — reinit for the next start().
            if peak == 0.0:
                log("[audio] pure silence (all-zero) — reinitializing PortAudio device table")
                sd._terminate()
                sd._initialize()
                notify("麦克风好像失效了，已重置，请重试一次")
                return

            if duration < MIN_SPEECH_DURATION or rms < SILENCE_RMS_THRESHOLD:
                log("[audio] too short or below silence threshold, skipping decode")
                notify("没识别到内容")
                return

            text = transcribe(self.recognizer, samples)
            log(f"[asr] text={text!r}")

            if not text:
                notify("没识别到内容")
                return

            type_text(text)
            notify(text[:40])

    def toggle(self) -> None:
        if self.stream is None:
            self.start()
        else:
            self.stop(self.active_source)


def _is_virtual_device(name: str) -> bool:
    lowered = name.lower()
    return "ydotool" in lowered or "virtual" in lowered


class DeviceWatcher(threading.Thread):
    """Watches one evdev device node for press/release events."""

    def __init__(self, dictation: Dictation, path: str, code: int, code_name: str) -> None:
        super().__init__(daemon=True)
        self.dictation = dictation
        self.path = path
        self.code = code
        self.code_name = code_name

    def run(self) -> None:
        try:
            device = InputDevice(self.path)
        except OSError:
            return

        log(f"[hotkey] watching {self.code_name!r} on {device.path} ({device.name!r})")
        try:
            for event in device.read_loop():
                if event.type != ecodes.EV_KEY or event.code != self.code:
                    continue
                if event.value == 1:
                    self.dictation.start(self.code_name)
                elif event.value == 0:
                    self.dictation.stop(self.code_name)
        except OSError as e:
            self.dictation.stop(self.code_name)
            log(f"[hotkey] {device.path} ({device.name!r}) disconnected: {e}")
        finally:
            device.close()


class HotkeyManager(threading.Thread):
    """Dynamically monitors all physical input devices and spawns watchers
    for any device advertising the registered hotkey codes (Plan B: pool all devices)."""

    def __init__(self, dictation: Dictation, bindings: list[tuple[str, str | None]]) -> None:
        super().__init__(daemon=True)
        self.dictation = dictation
        self.bindings = []
        for code_name, explicit_path in bindings:
            code = getattr(ecodes, code_name, None)
            if code is None:
                log(f"[hotkey] unknown event code {code_name!r}")
                continue
            self.bindings.append((code_name, code, explicit_path))
        self.active_watchers: dict[tuple[str, int], DeviceWatcher] = {}

    def run(self) -> None:
        while True:
            # Clean up watchers whose threads have exited (e.g. device unplugged)
            self.active_watchers = {
                k: w for k, w in self.active_watchers.items() if w.is_alive()
            }

            for code_name, code, explicit_path in self.bindings:
                if explicit_path:
                    # User specified an exact device path
                    key = (explicit_path, code)
                    if key not in self.active_watchers:
                        watcher = DeviceWatcher(self.dictation, explicit_path, code, code_name)
                        watcher.start()
                        self.active_watchers[key] = watcher
                    continue

                # Scan all physical devices advertising this code
                for path in list_devices():
                    key = (path, code)
                    if key in self.active_watchers:
                        continue
                    try:
                        dev = InputDevice(path)
                    except OSError:
                        continue
                    if _is_virtual_device(dev.name):
                        dev.close()
                        continue
                    if code in dev.capabilities().get(ecodes.EV_KEY, []):
                        watcher = DeviceWatcher(self.dictation, path, code, code_name)
                        watcher.start()
                        self.active_watchers[key] = watcher
                    dev.close()

            time.sleep(3)


def start_hotkey_manager(dictation: Dictation) -> None:
    manager = HotkeyManager(
        dictation,
        [
            (KEYBOARD_KEY, KEYBOARD_DEVICE),
            (MOUSE_BUTTON, MOUSE_DEVICE),
        ],
    )
    manager.start()


def _run_toggle_server(dictation: Dictation) -> None:
    """Only bound when --toggle is passed — otherwise no socket file is left
    behind for the common case where evdev hotkeys are the only trigger."""
    SOCK_PATH.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCK_PATH))
    server.listen(1)
    log(f"[toggle] listening on {SOCK_PATH}")
    try:
        while True:
            conn, _ = server.accept()
            with conn:
                conn.recv(16)
            dictation.toggle()
    finally:
        SOCK_PATH.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--toggle",
        action="store_true",
        help="also listen on a Unix socket for toggle.py (default: evdev hotkeys only, no socket file)",
    )
    args = parser.parse_args()

    try:
        log(f"[audio] default input device: {sd.query_devices(kind='input')}")
    except Exception as e:  # PortAudio raises its own exception types
        log(f"[audio] failed to query default input device: {e}")

    dictation = Dictation()
    start_hotkey_manager(dictation)

    log("ready" + (f", toggle socket at {SOCK_PATH}" if args.toggle else " (evdev hotkeys only)"))
    log(
        "env: WAYLAND_DISPLAY={!r} XDG_RUNTIME_DIR={!r} XDG_SESSION_TYPE={!r}".format(
            os.environ.get("WAYLAND_DISPLAY"),
            os.environ.get("XDG_RUNTIME_DIR"),
            os.environ.get("XDG_SESSION_TYPE"),
        )
    )

    if args.toggle:
        _run_toggle_server(dictation)
    else:
        threading.Event().wait()  # evdev hotkeys already run in background threads; just block


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
