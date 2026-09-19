# /// script
# dependencies = ["soundcard", "numpy"]
# ///
"""
audio_source.py — Real-time system-audio visualization source for Campfire.

Captures whatever is currently playing on the system (WASAPI loopback via
`soundcard`, no microphone involved) and maps it onto SourceSnapshot:
  • RMS energy (asymmetric smoothing: rises fast, falls slow) -> intensity/tier.
  • Bass/mid/treble spectral split (FFT) -> color_weights (3-way column blend).
  • A bass-energy transient ("kick") -> spark_burst + a brief pin to TIER_BLAZE.
  • Sustained silence -> phase decays flame -> ember -> out.

This is an energy-threshold onset detector, not real beat/tempo tracking —
it reacts to loud transients, it does not follow a BPM grid.

Optional dependency: needs `soundcard` + `numpy`. If either is missing, or no
loopback-capable output device is found, constructing AudioSource raises —
callers (CampfireApp) should catch that and fall back to RandomSource.
"""

import threading
import time

from source_base import (
    BaseSource, SourceSnapshot,
    PHASE_FLAME, PHASE_EMBER, PHASE_OUT,
    TIER_HUSH, TIER_GLOW, TIER_CRACKLE, TIER_ROAR, TIER_BLAZE,
)

try:
    import numpy as np
    import soundcard as sc
    AUDIO_DEPS_AVAILABLE = True
except ImportError:
    AUDIO_DEPS_AVAILABLE = False

# Bass / Mid / Treble accent colors (0..1 RGB) — warm low end, golden mids, cool highs.
BASS_COLOR = (0.85, 0.28, 0.14)
MID_COLOR = (0.95, 0.72, 0.20)
TREBLE_COLOR = (0.30, 0.70, 0.95)


class AudioSource(BaseSource):
    """Reacts to system audio playback (loopback capture) rather than the microphone."""

    SAMPLE_RATE = 48000
    CHUNK = 1024            # ~21ms/chunk at 48kHz — frequent enough for snappy transients
    FFT_SIZE = 2048

    BASS_HI = 200.0          # Hz: < this = bass
    MID_HI = 2000.0          # Hz: this..MID_HI = mid, >= this = treble

    SILENCE_RMS = 0.004       # linear amplitude below which audio counts as "quiet"
    EMBER_AFTER_S = 2.0        # quiet this long -> ember
    OUT_AFTER_S = 8.0          # quiet this long -> out

    ONSET_RATIO = 1.7          # bass energy vs its own rolling average to count as a "hit"
    ONSET_FLOOR = 0.02          # absolute floor so near-silence can't "hit"
    ONSET_HOLD_S = 0.35         # how long a hit pins tier at BLAZE
    SPARK_DECAY = 0.08           # per-chunk spark_burst falloff after a hit

    preferred_colors = [BASS_COLOR, MID_COLOR, TREBLE_COLOR]

    @property
    def name(self) -> str:
        return "Audio"

    def __init__(self) -> None:
        if not AUDIO_DEPS_AVAILABLE:
            raise RuntimeError("AudioSource requires the 'soundcard' and 'numpy' packages")
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        self._latest = SourceSnapshot(status_text="Audio (starting...)")

        # Audio-thread-only state (no lock needed — never read from the main thread).
        self._smoothed_rms = 0.0
        self._bass_avg = 0.0
        self._spark_burst = 0.0
        self._last_onset_t = -999.0
        self._quiet_since: float | None = None
        self._t0 = time.perf_counter()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="AudioSource")
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def poll(self):
        with self._lock:
            return self._latest

    # ── audio thread ──────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            speaker = sc.default_speaker()
            mic = sc.get_microphone(speaker.name, include_loopback=True)
        except Exception as exc:
            self._publish(SourceSnapshot(status_text=f"Audio unavailable: {exc}"))
            return

        try:
            with mic.recorder(samplerate=self.SAMPLE_RATE, channels=1) as rec:
                while not self._stop_evt.is_set():
                    data = rec.record(numframes=self.CHUNK)
                    samples = data[:, 0] if data.ndim == 2 else data
                    self._process_chunk(samples)
        except Exception as exc:
            self._publish(SourceSnapshot(status_text=f"Audio error: {exc}"))

    def _publish(self, snap: SourceSnapshot) -> None:
        with self._lock:
            self._latest = snap

    def _process_chunk(self, samples) -> None:
        now = time.perf_counter() - self._t0

        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        # Asymmetric smoothing: rises fast (transients read), falls slow (no flicker).
        alpha = 0.6 if rms > self._smoothed_rms else 0.08
        self._smoothed_rms += (rms - self._smoothed_rms) * alpha

        # --- bass/mid/treble split via FFT ---
        window = np.hanning(len(samples))
        spec = np.abs(np.fft.rfft(samples * window, n=self.FFT_SIZE))
        freqs = np.fft.rfftfreq(self.FFT_SIZE, d=1.0 / self.SAMPLE_RATE)
        bass = float(spec[freqs < self.BASS_HI].sum())
        mid = float(spec[(freqs >= self.BASS_HI) & (freqs < self.MID_HI)].sum())
        treble = float(spec[freqs >= self.MID_HI].sum())
        total = bass + mid + treble
        weights = [bass / total, mid / total, treble / total] if total > 1e-6 else [1 / 3, 1 / 3, 1 / 3]

        # --- bass transient ("kick") detection ---
        bass_norm = bass / max(1, len(samples))
        is_onset = (
            bass_norm > self.ONSET_FLOOR
            and self._bass_avg > 1e-6
            and bass_norm > self._bass_avg * self.ONSET_RATIO
        )
        if is_onset:
            self._last_onset_t = now
        self._bass_avg += (bass_norm - self._bass_avg) * 0.05
        recent_onset = (now - self._last_onset_t) < self.ONSET_HOLD_S
        self._spark_burst = 1.0 if recent_onset else max(0.0, self._spark_burst - self.SPARK_DECAY)

        # --- phase: sustained silence decays flame -> ember -> out ---
        if self._smoothed_rms < self.SILENCE_RMS:
            if self._quiet_since is None:
                self._quiet_since = now
            quiet_for = now - self._quiet_since
        else:
            self._quiet_since = None
            quiet_for = 0.0

        if quiet_for >= self.OUT_AFTER_S:
            phase = PHASE_OUT
        elif quiet_for >= self.EMBER_AFTER_S:
            phase = PHASE_EMBER
        else:
            phase = PHASE_FLAME

        # --- intensity: compressed so normal listening stays low, loud passages climb ---
        intensity = min(1.0, self._smoothed_rms * 9.0) ** 0.6

        # --- tier: mostly gentle bands; a hit pins Blaze briefly ---
        # (1-4 barely differ visually by design — Blaze is the "it just dropped" signal.)
        if recent_onset:
            tier = TIER_BLAZE
        elif intensity < 0.20:
            tier = TIER_HUSH
        elif intensity < 0.45:
            tier = TIER_GLOW
        elif intensity < 0.75:
            tier = TIER_CRACKLE
        else:
            tier = TIER_ROAR

        self._publish(SourceSnapshot(
            phase=phase,
            intensity=intensity if phase == PHASE_FLAME else None,
            tier=tier,
            spark_burst=self._spark_burst,
            color_weights=weights,
            status_text="Audio Reactive",
        ))


# ── entry ─────────────────────────────────────────────────────────────────────
# Run this file directly (`uv run audio_source.py`) for the audio-reactive
# campfire. campfire.py itself never imports this module — a source is wired
# in at launch time, not chosen from a menu campfire.py would have to know about.

def main() -> None:
    if not AUDIO_DEPS_AVAILABLE:
        raise SystemExit(
            "AudioSource requires 'soundcard' and 'numpy'. Run with: "
            "uv run --with soundcard --with numpy audio_source.py"
        )

    import tkinter as tk
    import campfire

    root = tk.Tk()
    app = campfire.CampfireApp(root, source=AudioSource())
    app.engine.set_colors(AudioSource.preferred_colors)  # bass/mid/treble palette

    def on_close():
        app.source.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
