# Campfire

Desktop pixel-fire animation (tkinter, no required dependencies). Ported from
[tinyfire](https://github.com/wdkwdkwdk/tinyfire).

## Run

```
python campfire.py          # standalone demo, random intensity drift
uv run audio_source.py      # audio-reactive: fire follows system audio playback
```

The audio version needs `soundcard` + `numpy` (installed automatically by `uv run`,
or `uv run --with soundcard --with numpy audio_source.py`). It reacts to whatever
is currently playing on the system (loopback capture, not the microphone):
bass/mid/treble energy drives the flame's color mix, overall loudness drives
intensity/tier, and bass transients trigger sparks + brief Blaze flares.

## Controls

- Right-click: menu (colors / size / phase / tier / quit)
- Mouse wheel or `+`/`-`: zoom
- `S`/`M`/`L`: size presets
- `C`: cycle color theme, `0`: reset to classic orange
- `1`-`5`: fire tier (Hush → Blaze)
- `F`/`E`/`O`: flame / ember / out
- `R`: reduce motion, `T`: toggle always-on-top
- Left-drag: move window, `Esc`/`Q`: quit

## Files

- `campfire.py` — renderer + `CampfireApp`. Knows nothing about concrete sources.
- `source_base.py` — the `BaseSource`/`SourceSnapshot` protocol shared by all sources.
- `audio_source.py` — the audio-reactive source; a standalone, independently runnable script.

A source is just a `BaseSource` subclass that emits `SourceSnapshot`s (phase,
intensity, tier, spark_burst, color_weights). Each source wires itself into
`CampfireApp` from its own entry point — `campfire.py` never imports one.
