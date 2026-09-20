# Campfire

Desktop pixel-fire animation, rendered with [raylib](https://www.raylib.com/)
(one implementation for Windows/macOS/Linux). Ported from
[tinyfire](https://github.com/wdkwdkwdk/tinyfire).

## Run

```
uv run campfire.py          # standalone demo, random intensity drift
uv run audio_source.py      # audio-reactive: fire follows system audio playback
```

Both scripts declare their own dependencies (`raylib`, plus `soundcard`+`numpy`
for the audio version) via PEP 723 inline metadata, installed automatically by
`uv run`.

### Why raylib, not tkinter

This used to be a tkinter app. On macOS, Tk 9's aqua backend turned out to
have a confirmed, non-deterministic bug in its per-pixel window transparency
(`-transparent`/`systemTransparent`) — identical code produced a transparent
window on one run and an opaque black one on the next, across every drawing
approach tried (`PhotoImage` alpha, `Canvas` items, plain widget backgrounds).
Tk 8.6 doesn't have the bug, but there's no way to get it on a current,
non-EOL Python on macOS. raylib's `FLAG_WINDOW_TRANSPARENT` sidesteps Tk
entirely and works reliably, as one implementation across all three
platforms instead of a Tk path plus a macOS-specific native fallback. As a
bonus it also measured 2-3x lower CPU use than the old Tk renderer on the
same machine (Tk's `PhotoImage.put()` re-parses a big pixel string every
frame; raylib batches a few hundred GPU rectangle draws instead).

### Audio source & macOS

The audio version reacts to whatever is currently playing on the system
(loopback capture, not the microphone): bass/mid/treble energy drives the
flame's color mix, overall loudness drives intensity/tier, and bass
transients trigger sparks + brief Blaze flares.

**macOS has no native audio loopback device** (unlike Windows' WASAPI
loopback) — `soundcard` doesn't fail because of a bug, it's a real CoreAudio
limitation shared by every PortAudio-based library. The practical fix is a
free virtual audio driver:

```
brew install blackhole-2ch
```

Then set up a Multi-Output Device so system audio keeps playing through your
speakers *and* gets routed into BlackHole at the same time (a raw BlackHole
output would be silent to you):

1. Open **Audio MIDI Setup.app** (Spotlight → "Audio MIDI Setup", or
   `/System/Applications/Utilities/`)
2. Click **+** at the bottom-left → **Create Multi-Output Device**
3. Check both your speakers (e.g. "MacBook Air Speakers") and **BlackHole 2ch**
   in the new device's list
4. Set that Multi-Output Device as your system output (right-click it →
   **Use This Device For Sound Output**, or System Settings → Sound → Output)

『中文』macOS 没有系统级的音频回放捕获（loopback），这是 CoreAudio 本身的限制，不是
`soundcard` 库的 bug。解决办法是装一个免费的虚拟声卡 `brew install blackhole-2ch`，
然后在 **Audio MIDI Setup.app**（聚焦搜索"音频 MIDI 设置"）里：点左下角 **+** →
**创建多输出设备（Create Multi-Output Device）**，勾选你的扬声器 + **BlackHole 2ch**
两项，再把这个"多输出设备"设为系统的输出设备（右键点它 → **将此设备用于声音输出**，
或者 系统设置 → 声音 → 输出）。这样系统音频会同时正常播放、也会被同步录入 BlackHole。
做完这一步之后，`audio_source.py` 会自动找到 BlackHole。

`audio_source.py` then finds BlackHole automatically.
(The newer, narrower-permission CoreAudio Process Tap API was evaluated and
rejected: it needs an Objective-C class, a hand-built aggregate device, a C
audio callback, and a TCC permission that likely requires a signed `.app`
bundle to register — no working Python implementation of it exists anywhere.)

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

- `campfire.py` — raylib renderer + `CampfireApp`. Knows nothing about concrete sources.
- `source_base.py` — the `BaseSource`/`SourceSnapshot` protocol shared by all sources.
- `audio_source.py` — the audio-reactive source; a standalone, independently runnable script.

A source is just a `BaseSource` subclass that emits `SourceSnapshot`s (phase,
intensity, tier, spark_burst, color_weights). Each source wires itself into
`CampfireApp` from its own entry point — `campfire.py` never imports one.
