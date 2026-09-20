#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["raylib"]
# ///
"""
Campfire — pixel fire animation.
Visual style ported from tinyfire (https://github.com/wdkwdkwdk/tinyfire)

Features:
  • Single raylib-based renderer for Windows/macOS/Linux — see README.md for
    why this isn't tkinter (Tk 9's per-pixel window transparency is broken,
    non-deterministically, under macOS aqua)
  • Clean crisp pixel art (no heavy CPU Gaussian blur or halo artifacts)
  • Mac-style Multi-Color Column Bands: horizontal smooth-blended multi-hue flames
  • White-hot tip convergence so multi-color flames burn cohesively
  • Location-aware spark tinting
  • Stationary wood log base + graceful flame sway
  • Interactive zoom, right-click menu, keyboard shortcuts, mouse drag

Controls:
  • 鼠标右键 (Right Click) : 弹出菜单 (多彩混色 / 尺寸 / 火势 / 退出)
  • 鼠标滚轮 (Mouse Wheel) : 任意放大 / 缩小
  • 快捷键 + / -           : 逐级放大 / 缩小
  • 快捷键 S / M / L       : 小 (Small) / 中 (Medium) / 大 (Large)
  • 快捷键 C               : 轮换火焰色彩 (冰与火 / 赛博霓虹 / 彩虹 / 经典橙 等)
  • 快捷键 0               : 恢复经典橙色
  • 快捷键 1 ~ 5           : 切换火势强度 (Hush → Glow → Crackle → Roar → Blaze)
  • 快捷键 F / E / O       : 燃火 (Flame) / 余烬 (Ember) / 熄灭 (Out)
  • 快捷键 R               : 减弱动态效果 (Reduce Motion，静止/降频)
  • 快捷键 T               : 切换窗口置顶 (Always on Top，默认开启)
  • 鼠标左键拖拽           : 移动窗口
  • ESC / Q                : 退出
"""

import ctypes, math, os, random, re, sys, time
from pyray import *

# ── scene constants ───────────────────────────────────────────────────────────

FIRE_W, FIRE_H = 28, 36         # heat-field grid
LOG_W,  LOG_H  = 28, 12         # log sprite grid
PAD_X          = 4              # horizontal padding for flame sway
LOG_X_IN_COMB  = PAD_X          # log stays static at x=PAD_X
LOG_Y_IN_COMB  = 31             # log stays static at y=31
COMB_W, COMB_H = FIRE_W + PAD_X * 2, 43  # 36 × 43 combined buffer

DEFAULT_SCALE = 6               # 6 screen pixels per pixel art unit

DISPLAY_MS = 33                  # ~30 fps
SIM_FPS    = 12                  # heat-field steps/sec

# Menu labels are bilingual; raylib's default font is ASCII-only. Leads with a
# stock plain .ttf/.otf per OS since raylib/stb_truetype can't reliably parse
# .ttc collections (every mainstream CJK font ships as one); those are kept as
# a bonus in case they work elsewhere. No load falling back to default font is
# still handled (tofu boxes for CJK, ASCII renders fine) — see _load_font.
_CJK_FONT_CANDIDATES = {
    "darwin": [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # stock, plain .ttf, confirmed to work
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
    ],
    "win32": [
        "C:/Windows/Fonts/simhei.ttf",  # stock, plain .ttf
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ],
    "linux": [
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # plain .ttf
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ],
}

# ── native macOS window dragging ────────────────────────────────────────────
# raylib can't drag its own window, and polling get_mouse_delta() once per
# frame lags visibly (async round-trip through GLFW to the window server/DWM)
# and, on Windows, races: at our 30fps cap the real WM_LBUTTONUP can land
# before the next poll even fires the drag, so a fast click-release exits
# the OS move-loop instantly with no movement. Both platforms instead hook
# the raw event directly, no per-frame polling:
#   macOS:   toggle NSWindow.isMovableByWindowBackground; the OS drags on
#            any background click while it's enabled.
#   Windows: subclass the GLFW window's WndProc and react to WM_LBUTTONDOWN
#            synchronously with WM_NCLBUTTONDOWN/HTCAPTION, handing the drag
#            to Windows' own modal move-loop (blocks our render loop until
#            release — flame freezes while dragged, traded for exact tracking).
# Linux has no native hook wired up yet and keeps the laggy per-frame fallback.
if sys.platform == "darwin":
    _objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    _objc.objc_msgSend.restype = ctypes.c_void_p
    _objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _objc.sel_registerName.restype = ctypes.c_void_p
    _objc.sel_registerName.argtypes = [ctypes.c_char_p]
    _SEL_SET_MOVABLE = _objc.sel_registerName(b"setMovableByWindowBackground:")
    _send_bool = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(
        ctypes.cast(_objc.objc_msgSend, ctypes.c_void_p).value
    )

    def _set_movable_by_background(enabled: bool) -> None:
        nswindow = int(ffi.cast("uintptr_t", get_window_handle()))
        _send_bool(nswindow, _SEL_SET_MOVABLE, enabled)
elif sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _WM_LBUTTONDOWN = 0x0201
    _WM_NCLBUTTONDOWN = 0x00A1
    _HTCAPTION = 2
    _GWLP_WNDPROC = -4
    # argtypes needed: ctypes otherwise truncates the 64-bit HWND, so calls
    # silently target a garbage handle instead of raising.
    _user32.ReleaseCapture.restype = ctypes.c_bool
    _user32.SendMessageW.restype = ctypes.c_ssize_t
    _user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    _user32.CallWindowProcW.restype = ctypes.c_ssize_t
    _user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
    ]
    _user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    _user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]

    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

    _drag_movable = True     # gated by _set_movable_by_background (off while a menu is open)
    _orig_wndproc = None     # None also means "subclass not installed yet"
    _wndproc_closure = None  # kept alive so the ctypes trampoline isn't GC'd

    def _drag_wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == _WM_LBUTTONDOWN and _drag_movable:
            _user32.ReleaseCapture()
            _user32.SendMessageW(hwnd, _WM_NCLBUTTONDOWN, _HTCAPTION, 0)
            return 0
        return _user32.CallWindowProcW(_orig_wndproc, hwnd, msg, wparam, lparam)

    def _set_movable_by_background(enabled: bool) -> None:
        global _drag_movable, _orig_wndproc, _wndproc_closure
        _drag_movable = enabled
        if _orig_wndproc is None:
            hwnd = int(ffi.cast("uintptr_t", get_window_handle()))
            _wndproc_closure = _WNDPROC(_drag_wndproc)
            _orig_wndproc = _user32.SetWindowLongPtrW(
                hwnd, _GWLP_WNDPROC, ctypes.cast(_wndproc_closure, ctypes.c_void_p)
            )
else:
    def _set_movable_by_background(enabled: bool) -> None:
        pass

# ── color palettes & Mac multi-color ramp generator ───────────────────────────

def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))

_COLOR_CACHE: dict[str, Color] = {}

def _hex_to_color(h: str) -> Color:
    # Drawn ~150-1000x/frame from a small fixed set of hex strings — caching
    # skips re-parsing hex that dominated frame time.
    c = _COLOR_CACHE.get(h)
    if c is None:
        c = Color(int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255)
        _COLOR_CACHE[h] = c
    return c

def _build_classic_rgb() -> list[tuple[int, int, int]]:
    """Original DOOM fire RGB ramps (PixelPalette.fire)."""
    rgba: list[tuple[int, int, int]] = [(0, 0, 0)]
    for i in range(1, 5):   rgba.append((_clamp(80+i*20),  _clamp(8+i*2),   0))
    for i in range(6):      rgba.append((_clamp(180+i*10), _clamp(20+i*8),  0))
    for i in range(7):      rgba.append((255, _clamp(70+i*14),  _clamp(i*4)))
    for i in range(7):      rgba.append((255, _clamp(170+i*8),  _clamp(20+i*12)))
    for i in range(6):      rgba.append((255, _clamp(230+i*4),  _clamp(140+i*18)))
    while len(rgba) < 33:   rgba.append((255, 252, 230))
    return rgba

CLASSIC_RGB = _build_classic_rgb()

def _lerp3(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    u = max(0.0, min(1.0, t))
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)

def build_single_ramp(ar: float, ag: float, ab: float) -> list[tuple[int, int, int]]:
    """Ported from FlamePaletteBuilder.ramp(accent:) (SourceFlameColors.swift)."""
    ramp: list[tuple[int, int, int]] = [(0, 0, 0)]
    for h in range(1, 33):
        u = h / 32.0
        if u < 0.32:
            k = u / 0.32
            deep = (ar * 0.22, ag * 0.14, ab * 0.10)
            mid = (ar * 0.55, ag * 0.38, ab * 0.28)
            r, g, b = _lerp3(deep, mid, k)
        elif u < 0.58:
            k = (u - 0.32) / 0.26
            mid = (ar * 0.55, ag * 0.38, ab * 0.28)
            full = (ar, ag, ab)
            r, g, b = _lerp3(mid, full, k)
        elif u < 0.82:
            k = (u - 0.58) / 0.24
            hot = (
                min(1.0, ar * 0.35 + 0.65),
                min(1.0, ag * 0.25 + 0.72),
                min(1.0, ab * 0.12 + 0.28),
            )
            r, g, b = _lerp3((ar, ag, ab), hot, k)
        else:
            k = (u - 0.82) / 0.18
            tip = (1.0, 0.96, 0.82)
            white = (1.0, 0.99, 0.94)
            r, g, b = _lerp3(tip, white, k)
        ramp.append((_clamp(r * 255), _clamp(g * 255), _clamp(b * 255)))
    return ramp

def compute_column_weights(width: int, raw_weights: list[float], feather: float = 0.14) -> list[list[float]]:
    """
    Mac tinyfire SourceFlameColors.swift columnWeights() implementation.
    Divides horizontal columns into smooth overlapping bands with Smoothstep feathering.
    """
    n = len(raw_weights)
    if n <= 1:
        return [[1.0] for _ in range(width)]

    total = sum(raw_weights)
    if total <= 1e-4 or width <= 0:
        norm = [1.0 / n] * n
    else:
        norm = [w / total for w in raw_weights]

    edges = [0.0]
    cum = 0.0
    for w in norm:
        cum += w
        edges.append(cum)

    out: list[list[float]] = []
    for x in range(width):
        u = (x + 0.5) / width
        row = [0.0] * n
        for i in range(n):
            if norm[i] <= 0.001:
                continue
            start = edges[i]
            end = edges[i + 1]
            center = (start + end) * 0.5
            half = max(0.06, (end - start) * 0.5 + feather * 0.5)
            d = abs(u - center)
            t = max(0.0, 1.0 - d / half)
            row[i] = t * t * (3.0 - 2.0 * t)  # Smoothstep
        s = sum(row)
        if s > 0:
            row = [v / s for v in row]
        out.append(row)
    return out

def build_multi_color_table(
    width: int,
    colors: list[tuple[float, float, float] | None],
    raw_weights: list[float] | None = None,
) -> list[list[str | None]]:
    """
    Builds a 2D lookup table: [heat: 0..32][col_x: 0..width-1] -> hex color string.
    Implements Mac tinyfire's horizontal multi-color blending and white-hot tip convergence.
    """
    # Single classic palette optimization
    if len(colors) == 1 and colors[0] is None:
        classic_hex = [None if h == 0 else f"#{CLASSIC_RGB[h][0]:02x}{CLASSIC_RGB[h][1]:02x}{CLASSIC_RGB[h][2]:02x}"
                       for h in range(33)]
        return [[classic_hex[h] for _ in range(width)] for h in range(33)]

    ramps: list[list[tuple[int, int, int]]] = []
    for c in colors:
        if c is None:
            ramps.append(CLASSIC_RGB)
        else:
            ramps.append(build_single_ramp(c[0], c[1], c[2]))

    if raw_weights is not None and len(raw_weights) >= len(colors):
        eff_weights = raw_weights[:len(colors)]
    else:
        eff_weights = [1.0] * len(colors)

    weights = compute_column_weights(width, eff_weights)
    table: list[list[str | None]] = []

    for h in range(33):
        if h == 0:
            table.append([None] * width)
            continue
        row: list[str | None] = []
        for x in range(width):
            ws = weights[x]
            r, g, b = 0.0, 0.0, 0.0
            for i, ramp in enumerate(ramps):
                w = ws[i]
                if w > 0.001:
                    cr, cg, cb = ramp[h]
                    r += cr * w
                    g += cg * w
                    b += cb * w

            # Mac tinyfire tip convergence:
            # Tip converges to shared white-hot so multi-hue flames still read as one fire
            if h >= 26:
                k = (h - 26) / 6.0
                tip_r, tip_g, tip_b = CLASSIC_RGB[h]
                r = r * (1.0 - k) + tip_r * k
                g = g * (1.0 - k) + tip_g * k
                b = b * (1.0 - k) + tip_b * k

            row.append(f"#{_clamp(r):02x}{_clamp(g):02x}{_clamp(b):02x}")
        table.append(row)
    return table


# ── preset color themes (Mac multi-color blends + classic accents) ────────────

RGBColor = tuple[float, float, float]

PRESET_THEMES: list[tuple[str, list[RGBColor | None]]] = [
    # ── Mac-style Multi-Color Blends (Official tinyfire palettes) ──
    ("🔥 冰与火之歌 (Fire & Ice)",    [(0.20, 0.78, 0.78), (0.91, 0.47, 0.18)]),  # Amp Teal + Claude Orange
    ("🔮 赛博霓虹 (Cyber Neon)",      [(0.95, 0.35, 0.65), (0.72, 0.42, 0.95), (0.32, 0.56, 0.92)]), # Pink + Grok Violet + Cursor Blue
    ("🌈 全光谱彩虹 (Rainbow)",        [(0.91, 0.22, 0.18), (0.95, 0.62, 0.22), (0.28, 0.72, 0.42), (0.20, 0.78, 0.78), (0.72, 0.42, 0.95)]),
    ("🌲 极光森林 (Aurora Forest)",   [(0.28, 0.72, 0.42), (0.20, 0.78, 0.78)]),  # Codex Green + Amp Teal
    ("🌅 暮光余晖 (Twilight Amber)",  [(0.72, 0.42, 0.95), (0.95, 0.62, 0.22)]),  # Grok Violet + Pi Amber
    ("👻 幽灵鬼火 (Ghost Flame)",     [(0.72, 0.42, 0.95), (0.28, 0.72, 0.42)]),  # Grok Violet + Codex Green

    # ── Classic & Pure Flame Colors ──
    ("🔸 经典橙 (Classic Orange)",  [None]),
    ("🟧 暖橘红 (Warm Orange)",    [(0.91, 0.47, 0.18)]),
    ("🟦 晴空蓝 (Sky Blue)",        [(0.32, 0.56, 0.92)]),
    ("🟩 翠竹绿 (Forest Green)",    [(0.28, 0.72, 0.42)]),
    ("🟪 紫罗兰 (Violet)",          [(0.72, 0.42, 0.95)]),
    ("🟨 琥珀金 (Amber Gold)",      [(0.95, 0.62, 0.22)]),
    ("🩵 水鸭青 (Teal)",            [(0.20, 0.78, 0.78)]),
]

# ── sprite palette colours ────────────────

_ASH       = "#4e4a46"
_COAL      = "#1c1814"
_EMBER     = "#dc3008"
_LOG_DARK  = "#3e220e"
_LOG_MID   = "#6e441c"
_LOG_LIGHT = "#94622c"
_LOG_END   = "#ba9458"

def build_log_grid() -> list[list[str | None]]:
    """CampfireSprites.Log() — 28×12 pixel art of crossed logs + ash substrate."""
    g: list[list[str | None]] = [[None] * LOG_W for _ in range(LOG_H)]

    def stamp(row: int, x0: int, x1: int, col: str) -> None:
        for x in range(x0, x1 + 1):
            g[row][x] = col

    # Ash & coal substrate
    stamp(8,  4, 23, _ASH)
    stamp(9,  3, 24, _COAL)
    stamp(10, 5, 22, _ASH)
    stamp(11, 7, 20, _COAL)

    # Ember glints
    g[8][9]  = _EMBER
    g[8][14] = _EMBER
    g[8][19] = _EMBER

    # Rear log
    stamp(6, 2, 25, _LOG_DARK)
    stamp(7, 2, 25, _LOG_MID)
    g[6][2]  = _LOG_END;   g[7][2]  = _LOG_END
    g[6][25] = _LOG_END;   g[7][25] = _LOG_LIGHT

    # Front log (flat top where fire sits)
    stamp(4, 3, 24, _LOG_LIGHT)
    stamp(5, 3, 24, _LOG_MID)
    g[4][3]  = _LOG_END;   g[5][3]  = _LOG_END
    g[4][24] = _LOG_END;   g[5][24] = _LOG_LIGHT

    return g

LOG_GRID = build_log_grid()

# ── fire engine ──────────────────────────────────

from source_base import (
    PHASE_FLAME, PHASE_EMBER, PHASE_OUT,
    TIER_HUSH, TIER_GLOW, TIER_CRACKLE, TIER_ROAR, TIER_BLAZE,
    TIER_LABELS,
    BaseSource, SourceSnapshot,
)


class RandomSource(BaseSource):
    """Built-in default source: gentle randomized intensity drift, used whenever
    no external source (audio, CPU, ...) is attached."""

    @property
    def name(self) -> str:
        return "Random"

    def __init__(self) -> None:
        self._elapsed = 0.0
        self._last_t = time.perf_counter()
        self._intensity = 0.5
        self._target_int = 0.6
        self._next_retgt = 0.0

    def poll(self) -> SourceSnapshot:
        now = time.perf_counter()
        self._elapsed += min(now - self._last_t, 0.1)
        self._last_t = now
        t = self._elapsed

        if t >= self._next_retgt:
            self._target_int = random.uniform(0.3, 1.0)
            self._next_retgt = t + random.uniform(3.0, 8.0)
        self._intensity += (self._target_int - self._intensity) * 0.03

        return SourceSnapshot(intensity=self._intensity)

_COOL_RANGE = {
    TIER_HUSH:    (2, 4),
    TIER_GLOW:    (1, 3),
    TIER_CRACKLE: (1, 3),
    TIER_ROAR:    (1, 2),
    TIER_BLAZE:   (0, 2),
}
_FLAME_HALF     = {TIER_HUSH: 2, TIER_GLOW: 3, TIER_CRACKLE: 5, TIER_ROAR: 7,  TIER_BLAZE: 10}
_FLAME_PEAK     = {TIER_HUSH: 18, TIER_GLOW: 22, TIER_CRACKLE: 26, TIER_ROAR: 30, TIER_BLAZE: 32}
_MAX_ROWS       = {TIER_HUSH: 8, TIER_GLOW: 14, TIER_CRACKLE: 22, TIER_ROAR: 30, TIER_BLAZE: FIRE_H}

_SPARK_COUNT    = {TIER_HUSH: 0, TIER_GLOW: 1, TIER_CRACKLE: 3, TIER_ROAR: 6,  TIER_BLAZE: 10}
_RISE_MAX_UNITS = {TIER_HUSH: 10, TIER_GLOW: 14, TIER_CRACKLE: 20, TIER_ROAR: 26, TIER_BLAZE: 32}
_TIER_SEED      = {TIER_HUSH: 0.0, TIER_GLOW: 1.3, TIER_CRACKLE: 2.8, TIER_ROAR: 4.5, TIER_BLAZE: 6.1}


class FireEngine:
    MAX_HEAT = 32

    def __init__(self) -> None:
        self._heat = bytearray(FIRE_W * FIRE_H)
        self.intensity: float = 0.5
        self.tier: int = TIER_CRACKLE
        self.phase: str = PHASE_FLAME
        self.ember_heat: float = 0.6
        self.current_colors: list[RGBColor | None] = [None]
        self.weights: list[float] | None = None
        self.color_table: list[list[str | None]] = build_multi_color_table(FIRE_W, [None])

    def set_colors(self, colors: list[RGBColor | None]) -> None:
        self.current_colors = colors
        self.color_table = build_multi_color_table(FIRE_W, colors, raw_weights=self.weights)

    def set_weights(self, weights: list[float] | None) -> None:
        if weights == self.weights:
            return
        # If single-color flame, column weights do not affect rendered colors
        if len(self.current_colors) <= 1:
            self.weights = weights
            return
        # Deadband: skip rebuilding 924 hex strings if weights fluctuation is imperceptible
        if (
            self.weights is not None
            and weights is not None
            and len(self.weights) == len(weights)
            and max(abs(a - b) for a, b in zip(self.weights, weights)) < 0.015
        ):
            return
        self.weights = weights
        self.color_table = build_multi_color_table(FIRE_W, self.current_colors, raw_weights=weights)

    def step(self) -> None:
        w, h, heat = FIRE_W, FIRE_H, self._heat
        ri = random.randint
        c_lo, c_hi = _COOL_RANGE[self.tier]

        # Upward propagation with wind offset
        for y in range(h - 1):
            row, below = y * w, (y + 1) * w
            for x in range(w):
                src = heat[below + x]
                dst_x = max(0, min(w - 1, x + ri(0, 2) - 1))
                heat[row + dst_x] = max(0, src - ri(c_lo, c_hi))

        # Bottom source row
        bot = (h - 1) * w
        for x in range(w):
            heat[bot + x] = 0

        if self.phase == PHASE_FLAME:
            self._seed_flame(bot)
        elif self.phase == PHASE_EMBER:
            self._seed_embers(bot)

        # Height cap per tier & phase
        self._apply_height_cap()

    def _seed_flame(self, bot: int) -> None:
        w, h, heat = FIRE_W, FIRE_H, self._heat
        cx   = w // 2
        half = _FLAME_HALF[self.tier]
        peak = min(self.MAX_HEAT, int(_FLAME_PEAK[self.tier] * (0.55 + self.intensity * 0.55)))
        ri   = random.randint

        for dx in range(-half, half + 1):
            x = cx + dx
            if not (0 <= x < w):
                continue
            edge = (abs(dx) == half)
            v = peak - abs(dx) * 2 - (4 if edge else 0) + ri(0, 4) - 2
            if self.tier in (TIER_ROAR, TIER_BLAZE) and random.randint(0, 8) == 0:
                v = min(self.MAX_HEAT, v + 6)
            heat[bot + x] = max(0, min(self.MAX_HEAT, v))

        if h >= 2 and half > 1:
            row = (h - 2) * w
            for dx in range(-(half - 1), half):
                x = cx + dx
                if not (0 <= x < w):
                    continue
                boost = peak // 2 - abs(dx)
                heat[row + x] = max(heat[row + x], max(0, boost))

    def _seed_embers(self, bot: int) -> None:
        """Ported from Mac PixelFireEngine.seedEmbers()"""
        w, heat = FIRE_W, self._heat
        cx = w // 2
        n = 3 + int(self.ember_heat * 4)
        for i in range(n):
            x = cx - n // 2 + i
            if 0 <= x < w:
                pulse = int(10 + self.ember_heat * 12) + random.randint(-3, 3)
                if random.randint(0, 2) == 0:
                    heat[bot + x] = max(0, min(self.MAX_HEAT, pulse))

    def _apply_height_cap(self) -> None:
        if self.phase == PHASE_OUT:
            max_rows = 0
        elif self.phase == PHASE_EMBER:
            max_rows = 4
        else:
            max_rows = _MAX_ROWS.get(self.tier, FIRE_H)

        cut = FIRE_H - max_rows
        if cut <= 0:
            return
        w, heat = FIRE_W, self._heat
        for y in range(cut):
            dist = cut - y
            row  = y * w
            for x in range(w):
                if dist > 2:
                    heat[row + x] = 0
                else:
                    heat[row + x] = heat[row + x] // (4 - dist)

    def hex_at(self, x: int, y: int) -> str | None:
        h = min(self._heat[y * FIRE_W + x], self.MAX_HEAT)
        if h == 0:
            return None
        return self.color_table[h][x]

# ── context menu (flat: no cascading submenus, see the Menu docstring below
# for why) ───────────────────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\uFE0F\u200D]+"
)

def _strip_emoji(s: str) -> str:
    """raylib has no color-emoji glyph support, so menu labels are ASCII/CJK-only."""
    return _EMOJI_RE.sub("", s).strip()


class MenuItem:
    __slots__ = ("label", "command", "separator")

    def __init__(self, label: str | None = None, command=None, separator: bool = False) -> None:
        self.label = _strip_emoji(label) if label else label
        self.command = command
        self.separator = separator


class Menu:
    """Flat menu builder matching the tk.Menu subset this file used
    (add_command/add_cascade/add_separator), so BaseSource.populate_menu hooks
    still work. add_cascade flattens its items under a plain header line
    instead of a real submenu — raylib only draws inside its own window, so a
    hover-to-expand cascade would need a resize per nesting level."""

    def __init__(self) -> None:
        self.items: list[MenuItem] = []

    def add_command(self, label: str, command) -> None:
        self.items.append(MenuItem(label, command))

    def add_separator(self) -> None:
        self.items.append(MenuItem(separator=True))

    def add_cascade(self, label: str, menu: "Menu") -> None:
        self.items.append(MenuItem(f"── {_strip_emoji(label)} ──"))
        self.items.extend(menu.items)


# ── main application ──────────────────────────────────────────────────────────

class CampfireApp:

    _JITTER_AMP_GRID = {
        TIER_HUSH:    0.0,
        TIER_GLOW:    0.6,
        TIER_CRACKLE: 1.1,
        TIER_ROAR:    1.6,
        TIER_BLAZE:   2.1,
    }

    _MENU_ROW_H      = 22
    _MENU_SEP_H      = 9
    _MENU_PAD        = 10
    _MENU_FONT_SIZE  = 13

    def __init__(self, source=None) -> None:
        self.source = source if source is not None else RandomSource()

        self.scale = DEFAULT_SCALE
        self._topmost = True
        self._reduce_motion = False
        self._first_layout = True
        self._theme_idx = 0
        self._spark_burst = 0.0
        self._quit = False

        self.engine = FireEngine()
        self._tier        = TIER_CRACKLE
        self._intensity   = 0.5
        self._elapsed     = 0.0
        self._last_sim    = -999.0
        self._last_jitter = 0
        self._last_t      = time.perf_counter()
        self._last_status_text = None

        self._menu = self._build_context_menu()
        self._menu_open = False
        self._menu_items: list[MenuItem] = []
        self._menu_local_pos = (0, 0)
        self._menu_size = (0, 0)
        self._pre_menu_window = None  # (x, y, w, h) to restore when the menu closes
        self._draw_dx = 0             # flame draw offset while the window is
        self._draw_dy = 0             # temporarily enlarged to fit an open menu

        self._dragging = False
        self._drag_x = self._drag_y = 0.0
        self._resize_settle = 0  # frames to skip drawing after the menu's window
                                  # resize/reposition, see _open_menu/_close_menu
        self._font = None
        self._win_w = COMB_W * self.scale + 60
        self._win_h = COMB_H * self.scale + 80

        self.set_color_index(0)  # initial theme (0: Fire & Ice)

    # ── entry / main loop ────────────────────────────────────────────────────

    def run(self) -> None:
        self.source.start()
        set_config_flags(
            ConfigFlags.FLAG_WINDOW_TRANSPARENT
            | ConfigFlags.FLAG_WINDOW_UNDECORATED
            | ConfigFlags.FLAG_WINDOW_TOPMOST
            | ConfigFlags.FLAG_WINDOW_HIGHDPI  # else renders at 1x and gets
                                                # upscaled by the OS on Retina,
                                                # blurring everything
        )
        init_window(self._win_w, self._win_h, "🔥 CampFire")
        # raylib's default exit key (ESC) arms window_should_close() on its
        # own, so ESC-to-close-menu (_handle_menu_input) would also quit the
        # app next frame. Quit only via our own _quit flag instead.
        set_exit_key(KeyboardKey.KEY_NULL)
        set_target_fps(round(1000 / DISPLAY_MS))
        self._load_font()
        self._recalc_geometry()
        _set_movable_by_background(True)

        try:
            while not window_should_close() and not self._quit:
                self._frame()
        finally:
            self.source.stop()
            close_window()

    def _load_font(self) -> None:
        text = "".join(item.label for item in self._menu.items if item.label)
        codepoints = sorted(set(ord(c) for c in text) | set(range(32, 127)))
        arr = ffi.new("int[]", codepoints)
        ptr = ffi.cast("int *", arr)

        # Bake at the physical pixel size (HIGHDPI draw calls stay in logical
        # units, but a glyph atlas baked at logical size gets stretched across
        # dpi_scale x more physical pixels and blurs); draw/measure calls
        # below keep using the logical _MENU_FONT_SIZE.
        dpi = get_window_scale_dpi()
        font_px = round(self._MENU_FONT_SIZE * dpi.x)

        default_font = get_font_default()
        self._font = default_font
        for path in _CJK_FONT_CANDIDATES.get(sys.platform, []):
            if not os.path.exists(path):
                continue
            font = load_font_ex(path, font_px, ptr, len(codepoints))
            # A failed load (e.g. an unparseable .ttc) silently returns
            # GetFontDefault() rather than erroring — glyphCount can't detect
            # that (224 default ASCII glyphs is usually >= a menu's actual
            # count), so compare texture identity instead.
            if font.texture.id != default_font.texture.id:
                self._font = font
                break

    # ── size & geometry ───────────────────────────────────────────────────────

    def set_scale(self, new_scale: int) -> None:
        clamped = max(2, min(12, new_scale))
        if clamped == self.scale:
            return
        self.scale = clamped
        self._recalc_geometry()

    def _recalc_geometry(self) -> None:
        sc = self.scale
        self._camp_w_px = COMB_W * sc
        self._camp_h_px = COMB_H * sc

        win_w = self._camp_w_px + int(60 * (sc / 6.0))
        win_h = self._camp_h_px + int(80 * (sc / 6.0))

        if self._first_layout:
            self._first_layout = False
            screen_w = get_monitor_width(get_current_monitor())
            screen_h = get_monitor_height(get_current_monitor())
            x = max(0, screen_w - win_w - 36)
            y = max(0, screen_h - win_h - 48)
            self._win_w, self._win_h = win_w, win_h
            set_window_size(win_w, win_h)
            set_window_position(x, y)
        else:
            # Anchor to bottom-center so logs remain planted on the desktop when scaling
            pos = get_window_position()
            cur_x, cur_y = int(pos.x), int(pos.y)
            old_w, old_h = self._win_w, self._win_h
            new_x = cur_x - (win_w - old_w) // 2
            new_y = cur_y - (win_h - old_h)
            self._win_w, self._win_h = win_w, win_h
            set_window_size(win_w, win_h)
            set_window_position(new_x, new_y)

        self._camp_x0 = (win_w - self._camp_w_px) // 2
        self._camp_y0 = win_h - self._camp_h_px - max(8, int(16 * (sc / 6.0)))

        self._spark_ox = self._camp_x0 + (LOG_X_IN_COMB + LOG_W // 2) * sc
        self._spark_oy = self._camp_y0 + (LOG_Y_IN_COMB + 4) * sc

    # ── color control ─────────────────────────────────────────────────────────

    def set_color_index(self, idx: int) -> None:
        self._theme_idx = idx % len(PRESET_THEMES)
        name, colors = PRESET_THEMES[self._theme_idx]
        self.engine.set_colors(colors)

    def cycle_color(self) -> None:
        self.set_color_index(self._theme_idx + 1)

    # ── context menu ──────────────────────────────────────────────────────────

    def _build_context_menu(self) -> Menu:
        m = Menu()

        for i in range(6):
            cname, _ = PRESET_THEMES[i]
            m.add_command(cname, (lambda idx=i: self.set_color_index(idx)))
        m.add_separator()
        for i in range(6, len(PRESET_THEMES)):
            cname, _ = PRESET_THEMES[i]
            m.add_command(cname, (lambda idx=i: self.set_color_index(idx)))
        m.add_separator()

        m.add_command("小 / Small (4x)",  lambda: self.set_scale(4))
        m.add_command("中 / Medium (6x)", lambda: self.set_scale(6))
        m.add_command("大 / Large (8x)",  lambda: self.set_scale(8))
        m.add_command("特大 / XL (10x)",  lambda: self.set_scale(10))
        m.add_separator()

        m.add_command("燃火模式 (Flame - F)", lambda: self.set_phase(PHASE_FLAME))
        m.add_command("余烬暗火 (Ember - E)", lambda: self.set_phase(PHASE_EMBER))
        m.add_command("熄灭冷柴 (Extinguish - O)", lambda: self.set_phase(PHASE_OUT))
        m.add_separator()

        for t in (TIER_HUSH, TIER_GLOW, TIER_CRACKLE, TIER_ROAR, TIER_BLAZE):
            m.add_command(TIER_LABELS[t], (lambda val=t: self._set_tier(val)))
        m.add_separator()

        # Source-provided menu extensions (open interface for any input source)
        if hasattr(self.source, "populate_menu"):
            self.source.populate_menu(m, app=self)

        m.add_separator()
        m.add_command("减弱动态效果 (Reduce Motion - R)", self.toggle_reduce_motion)
        m.add_command("切换置顶 (Toggle Topmost - T)", self.toggle_topmost)
        m.add_command("退出 (Quit - ESC)", self.quit)
        return m

    def set_source(self, source=None) -> None:
        """Dynamically attach or detach an input source (duck-typed or BaseSource).
        Detaching (source=None) falls back to the built-in RandomSource, so
        self.source is always a valid, pollable source."""
        self.source.stop()
        self.source = source if source is not None else RandomSource()
        self.source.start()
        if source is None:
            set_window_title("🔥 CampFire")
            self._last_status_text = None
            self.engine.set_weights(None)
        self._menu = self._build_context_menu()

    def set_phase(self, phase: str) -> None:
        self.engine.phase = phase
        if phase == PHASE_OUT:
            self.engine._heat = bytearray(FIRE_W * FIRE_H)

    def toggle_reduce_motion(self) -> None:
        self._reduce_motion = not self._reduce_motion

    def toggle_topmost(self) -> None:
        self._topmost = not self._topmost
        if self._topmost:
            set_window_state(ConfigFlags.FLAG_WINDOW_TOPMOST)
        else:
            clear_window_state(ConfigFlags.FLAG_WINDOW_TOPMOST)

    def quit(self) -> None:
        self._quit = True

    def _set_tier(self, tier: int) -> None:
        self._tier = tier
        self.engine.tier = tier
        if self.engine.phase != PHASE_FLAME:
            self.set_phase(PHASE_FLAME)

    def _measure_menu(self, items: list[MenuItem]) -> tuple[int, int]:
        w = 0
        h = self._MENU_PAD * 2
        for it in items:
            if it.separator:
                h += self._MENU_SEP_H
            else:
                tw = measure_text_ex(self._font, it.label, self._MENU_FONT_SIZE, 1).x
                w = max(w, tw)
                h += self._MENU_ROW_H
        return int(w) + self._MENU_PAD * 2, h

    def _open_menu(self, mx: int, my: int) -> None:
        items = self._menu.items
        panel_w, panel_h = self._measure_menu(items)

        win_pos = get_window_position()
        win_x, win_y = int(win_pos.x), int(win_pos.y)
        screen_mx, screen_my = win_x + mx, win_y + my

        mon = get_current_monitor()
        mon_w, mon_h = get_monitor_width(mon), get_monitor_height(mon)
        panel_x = max(0, min(screen_mx, mon_w - panel_w))
        panel_y = max(0, min(screen_my, mon_h - panel_h))

        union_x0 = min(win_x, panel_x)
        union_y0 = min(win_y, panel_y)
        union_x1 = max(win_x + self._win_w, panel_x + panel_w)
        union_y1 = max(win_y + self._win_h, panel_y + panel_h)

        self._pre_menu_window = (win_x, win_y, self._win_w, self._win_h)
        self._draw_dx = win_x - union_x0
        self._draw_dy = win_y - union_y0
        self._menu_local_pos = (panel_x - union_x0, panel_y - union_y0)
        self._menu_size = (panel_w, panel_h)
        self._menu_items = items

        set_window_size(union_x1 - union_x0, union_y1 - union_y0)
        set_window_position(union_x0, union_y0)
        self._menu_open = True
        self._resize_settle = 2  # see _frame: async resize flashes stale content otherwise
        _set_movable_by_background(False)  # a drag while picking an item shouldn't move the window

    def _close_menu(self) -> None:
        if self._pre_menu_window is not None:
            x, y, w, h = self._pre_menu_window
            set_window_size(w, h)
            set_window_position(x, y)
            self._pre_menu_window = None
        self._draw_dx = 0
        self._draw_dy = 0
        self._menu_open = False
        self._resize_settle = 2
        _set_movable_by_background(True)

    def _draw_menu(self) -> None:
        px, py = self._menu_local_pos
        pw, ph = self._menu_size
        draw_rectangle(px, py, pw, ph, Color(28, 24, 20, 235))
        draw_rectangle_lines(px, py, pw, ph, Color(90, 80, 70, 255))

        mouse = get_mouse_position()
        y = py + self._MENU_PAD
        for it in self._menu_items:
            if it.separator:
                draw_line(px + 8, y + self._MENU_SEP_H // 2, px + pw - 8, y + self._MENU_SEP_H // 2,
                          Color(80, 70, 60, 255))
                y += self._MENU_SEP_H
                continue
            hovered = it.command is not None and check_collision_point_rec(mouse, (px, y, pw, self._MENU_ROW_H))
            if hovered:
                draw_rectangle(px + 2, y, pw - 4, self._MENU_ROW_H, Color(90, 60, 30, 200))
            color = WHITE if it.command is not None else Color(200, 160, 90, 255)
            draw_text_ex(self._font, it.label, (px + self._MENU_PAD, y + 3), self._MENU_FONT_SIZE, 1, color)
            y += self._MENU_ROW_H

    def _handle_menu_input(self) -> None:
        if is_key_pressed(KeyboardKey.KEY_ESCAPE):
            self._close_menu()
            return
        if not is_mouse_button_pressed(MouseButton.MOUSE_BUTTON_LEFT):
            return

        mouse = get_mouse_position()
        px, py = self._menu_local_pos
        pw, ph = self._menu_size
        if not check_collision_point_rec(mouse, (px, py, pw, ph)):
            self._close_menu()
            return

        y = py + self._MENU_PAD
        for it in self._menu_items:
            if it.separator:
                y += self._MENU_SEP_H
                continue
            if it.command is not None and check_collision_point_rec(mouse, (px, y, pw, self._MENU_ROW_H)):
                cmd = it.command
                self._close_menu()
                cmd()
                return
            y += self._MENU_ROW_H
        self._close_menu()

    # ── input (menu closed) ──────────────────────────────────────────────────

    def _handle_input(self) -> None:
        if is_key_pressed(KeyboardKey.KEY_ESCAPE) or is_key_pressed(KeyboardKey.KEY_Q):
            self.quit()
            return
        if is_key_pressed(KeyboardKey.KEY_T):
            self.toggle_topmost()
        if is_key_pressed(KeyboardKey.KEY_R):
            self.toggle_reduce_motion()
        if is_key_pressed(KeyboardKey.KEY_F):
            self.set_phase(PHASE_FLAME)
        if is_key_pressed(KeyboardKey.KEY_E):
            self.set_phase(PHASE_EMBER)
        if is_key_pressed(KeyboardKey.KEY_O):
            self.set_phase(PHASE_OUT)
        for key, tier in ((KeyboardKey.KEY_ONE, TIER_HUSH), (KeyboardKey.KEY_TWO, TIER_GLOW),
                           (KeyboardKey.KEY_THREE, TIER_CRACKLE), (KeyboardKey.KEY_FOUR, TIER_ROAR),
                           (KeyboardKey.KEY_FIVE, TIER_BLAZE)):
            if is_key_pressed(key):
                self._set_tier(tier)

        if is_key_pressed(KeyboardKey.KEY_EQUAL):
            self.set_scale(self.scale + 1)
        if is_key_pressed(KeyboardKey.KEY_MINUS):
            self.set_scale(self.scale - 1)
        if is_key_pressed(KeyboardKey.KEY_S):
            self.set_scale(4)
        if is_key_pressed(KeyboardKey.KEY_M):
            self.set_scale(6)
        if is_key_pressed(KeyboardKey.KEY_L):
            self.set_scale(8)

        if is_key_pressed(KeyboardKey.KEY_C):
            self.cycle_color()
        if is_key_pressed(KeyboardKey.KEY_ZERO):
            self.set_color_index(6)  # 6 is Classic Orange

        wheel = get_mouse_wheel_move()
        if wheel > 0:
            self.set_scale(self.scale + 1)
        elif wheel < 0:
            self.set_scale(self.scale - 1)

        if is_mouse_button_pressed(MouseButton.MOUSE_BUTTON_RIGHT):
            mouse = get_mouse_position()
            self._dragging = False
            self._open_menu(int(mouse.x), int(mouse.y))
            return

        # macOS drags natively via _set_movable_by_background — nothing more to do.
        if sys.platform == "darwin":
            return

        # Windows: the subclassed WndProc reacts to WM_LBUTTONDOWN directly
        # (see _set_movable_by_background / _drag_wndproc) — nothing more to do here.
        if sys.platform == "win32":
            return

        # Linux: no native hook wired up yet (e.g. X11 _NET_WM_MOVERESIZE),
        # so this per-frame delta fallback has the same lag macOS/Windows had.
        if is_mouse_button_pressed(MouseButton.MOUSE_BUTTON_LEFT):
            self._dragging = True
            wpos = get_window_position()
            self._drag_x, self._drag_y = wpos.x, wpos.y  # float accumulator, see below
        if is_mouse_button_released(MouseButton.MOUSE_BUTTON_LEFT):
            self._dragging = False
        if self._dragging and is_mouse_button_down(MouseButton.MOUSE_BUTTON_LEFT):
            # Accumulate in float, round only when setting the position —
            # truncating every frame silently drops sub-pixel movement,
            # making the window lag/stutter behind the cursor.
            d = get_mouse_delta()
            if d.x or d.y:
                self._drag_x += d.x
                self._drag_y += d.y
                set_window_position(round(self._drag_x), round(self._drag_y))

    # ── per-frame update + draw ──────────────────────────────────────────────

    def _frame(self) -> None:
        now = time.perf_counter()
        dt  = min(now - self._last_t, 0.1)
        self._last_t = now
        self._elapsed += dt
        t = self._elapsed

        # Source polling (RandomSource by default, or an attached AudioSource/CPUSource/...)
        snap = self.source.poll()
        if snap is not None:
            if snap.phase is not None:
                self.engine.phase = snap.phase
            if snap.intensity is not None:
                self._intensity = snap.intensity
                self.engine.intensity = snap.intensity
            if snap.tier is not None:
                self._tier = snap.tier
                self.engine.tier = snap.tier
            if snap.spark_burst is not None:
                self._spark_burst = snap.spark_burst
            if snap.color_weights is not None:
                self.engine.set_weights(snap.color_weights)
            if snap.status_text is not None and snap.status_text != self._last_status_text:
                self._last_status_text = snap.status_text
                set_window_title(f"🔥 {snap.status_text}")

        ig = self._intensity

        if self._menu_open:
            self._handle_menu_input()
        else:
            self._handle_input()

        # Reduce motion: 6 fps simulation step, otherwise 12 fps
        step_fps = 6 if self._reduce_motion else SIM_FPS
        sim_due = (t - self._last_sim >= 1.0 / step_fps)

        # Flame sway (grid units): 0 when motion reduced or phase is not flame
        amp = 0.0 if (self._reduce_motion or self.engine.phase != PHASE_FLAME) else self._JITTER_AMP_GRID.get(self._tier, 1.0)
        jitter_grid = int(round(math.sin(t * 2.2) * amp))

        if sim_due:
            self._last_sim = t
            self.engine.step()
        self._last_jitter = jitter_grid

        begin_drawing()
        clear_background(BLANK)
        if self._resize_settle > 0:
            # macOS applies window resize/move asynchronously — a blank frame
            # here beats a flash of content misaligned against the old geometry.
            self._resize_settle -= 1
        else:
            self._draw_scene(jitter_grid)
            self._render_sparks(t, ig)
            if self._menu_open:
                self._draw_menu()
        end_drawing()

    def _draw_scene(self, jitter_grid: int) -> None:
        grid: list[list[str | None]] = [[None] * COMB_W for _ in range(COMB_H)]

        # 1. Log sprite (STATIONARY at LOG_X_IN_COMB, LOG_Y_IN_COMB)
        for ly in range(LOG_H):
            row = LOG_Y_IN_COMB + ly
            log_row = LOG_GRID[ly]
            for lx in range(LOG_W):
                col = log_row[lx]
                if col is not None:
                    grid[row][LOG_X_IN_COMB + lx] = col

        # 2. Flame (shifted horizontally by jitter_grid)
        for fy in range(FIRE_H):
            for fx in range(FIRE_W):
                fcol = self.engine.hex_at(fx, fy)
                if fcol is not None:
                    gx = LOG_X_IN_COMB + fx + jitter_grid
                    if 0 <= gx < COMB_W:
                        grid[fy][gx] = fcol

        # 3. Draw each row as horizontal runs of same-colored cells instead of
        # one rectangle per cell — typically ~1-2 dozen runs/row rather than
        # COMB_W.
        sc = self.scale
        x0, y0 = self._camp_x0 + self._draw_dx, self._camp_y0 + self._draw_dy
        for row_idx, row in enumerate(grid):
            run_color = row[0]
            run_start = 0
            for x in range(1, COMB_W + 1):
                cell = row[x] if x < COMB_W else object()  # sentinel forces a flush past the last cell
                if cell != run_color:
                    if run_color is not None:
                        draw_rectangle(
                            x0 + run_start * sc, y0 + row_idx * sc,
                            (x - run_start) * sc, sc,
                            _hex_to_color(run_color),
                        )
                    run_color = cell
                    run_start = x

    def _render_sparks(self, t: float, ig: float) -> None:
        if self.engine.phase == PHASE_OUT:
            return
        elif self.engine.phase == PHASE_EMBER:
            active = 1 if self.engine.ember_heat > 0.55 else 0
        else:
            base_count = _SPARK_COUNT[self._tier]
            burst_extra = int(self._spark_burst * 4)
            active = max(0, base_count // 2) if self._reduce_motion else min(12, base_count + burst_extra + int(ig * 2))

        if active <= 0 or (self.engine.phase == PHASE_FLAME and ig < 0.15):
            return

        sc       = self.scale
        speed    = 12.0 + ig * 14.0
        rise_max = _RISE_MAX_UNITS[self._tier] * sc
        tseed    = _TIER_SEED[self._tier]
        spark_w  = max(1, sc)
        spark_h  = max(2, sc * 2)
        ox       = self._spark_ox + self._draw_dx
        oy       = self._spark_oy + self._draw_dy

        for i in range(active):
            seed   = i * 1.7 + tseed
            tt     = t * speed * 0.07 + seed
            rise   = (tt * 9) % max(1.0, rise_max)
            sway   = round(math.sin(tt * 2.1 + seed) * sc * 0.5)
            spread = (i - active / 2) * sc

            sx = int(round(ox + sway + spread))
            sy = int(round(oy - rise))
            life = 1.0 - rise / max(1.0, rise_max)
            if life < 0.05:
                continue

            # Location-aware spark tint: sample color table from the column the spark originates from
            fire_x0 = self._camp_x0 + self._draw_dx + LOG_X_IN_COMB * sc  # screen x of fire column fx=0
            col_x = max(0, min(FIRE_W - 1, int(round((sx - fire_x0) / sc))))
            if life > 0.55:
                spark_col = self.engine.color_table[30][col_x] or "#fff8b0"
            elif life > 0.25:
                spark_col = self.engine.color_table[20][col_x] or "#ffb428"
            else:
                spark_col = self.engine.color_table[10][col_x] or "#dc3008"

            # Mac tinyfire: clean 1x2 pixel sprite particle (no trail)
            draw_rectangle(
                sx - spark_w // 2, sy - spark_h // 2,
                spark_w, spark_h,
                _hex_to_color(spark_col),
            )


# ── entry ─────────────────────────────────────────────────────────────────────

def main() -> None:
    CampfireApp().run()


if __name__ == "__main__":
    main()
