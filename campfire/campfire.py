#!/usr/bin/env python3
"""
Campfire — pixel fire animation.
Visual style ported from tinyfire (https://github.com/wdkwdkwdk/tinyfire)

Features:
  • Zero external dependencies (Python stdlib tkinter only)
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

import math, random, time, tkinter as tk

# ── scene constants ───────────────────────────────────────────────────────────

FIRE_W, FIRE_H = 28, 36         # heat-field grid
LOG_W,  LOG_H  = 28, 12         # log sprite grid
PAD_X          = 4              # horizontal padding for flame sway
LOG_X_IN_COMB  = PAD_X          # log stays static at x=PAD_X
LOG_Y_IN_COMB  = 31             # log stays static at y=31
COMB_W, COMB_H = FIRE_W + PAD_X * 2, 43  # 36 × 43 combined buffer

DEFAULT_SCALE = 6               # 6 screen pixels per pixel art unit

BG = "#080503"                  # transparent color key (wm_attributes -transparentcolor)

DISPLAY_MS = 33                  # ~30 fps
SIM_FPS    = 12                  # heat-field steps/sec

# ── color palettes & Mac multi-color ramp generator ───────────────────────────

def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))

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

# ── main application ──────────────────────────────────────────────────────────

class CampfireApp:

    _JITTER_AMP_GRID = {
        TIER_HUSH:    0.0,
        TIER_GLOW:    0.6,
        TIER_CRACKLE: 1.1,
        TIER_ROAR:    1.6,
        TIER_BLAZE:   2.1,
    }

    def __init__(self, root: tk.Tk, source=None) -> None:
        self.root = root
        self.source = source if source is not None else RandomSource()
        self.source.start()

        root.title("🔥 CampFire")
        root.resizable(False, False)
        root.configure(bg=BG)
        root.overrideredirect(True)                  # no OS window border
        root.wm_attributes("-transparentcolor", BG) # BG pixels become transparent
        root.wm_attributes("-topmost", True)         # Always on top by default

        self.scale = DEFAULT_SCALE
        self._topmost = True
        self._reduce_motion = False
        self._first_layout = True
        self._theme_idx = 0
        self._spark_burst = 0.0

        self._cv = tk.Canvas(root, bg=BG, highlightthickness=0)
        self._cv.pack()

        # Key bindings
        root.bind("<Escape>", lambda _: root.quit())
        root.bind("q",        lambda _: root.quit())
        root.bind("t",        lambda _: self.toggle_topmost())
        root.bind("r",        lambda _: self.toggle_reduce_motion())
        root.bind("f",        lambda _: self.set_phase(PHASE_FLAME))
        root.bind("e",        lambda _: self.set_phase(PHASE_EMBER))
        root.bind("o",        lambda _: self.set_phase(PHASE_OUT))
        for key, tier in [("1", TIER_HUSH), ("2", TIER_GLOW), ("3", TIER_CRACKLE),
                           ("4", TIER_ROAR), ("5", TIER_BLAZE)]:
            root.bind(key, lambda _, t=tier: self._set_tier(t))

        # Size hotkeys
        root.bind("+",       lambda _: self.set_scale(self.scale + 1))
        root.bind("=",       lambda _: self.set_scale(self.scale + 1))
        root.bind("-",       lambda _: self.set_scale(self.scale - 1))
        root.bind("_",       lambda _: self.set_scale(self.scale - 1))
        root.bind("s",       lambda _: self.set_scale(4))   # Small
        root.bind("m",       lambda _: self.set_scale(6))   # Medium
        root.bind("l",       lambda _: self.set_scale(8))   # Large

        # Color hotkeys
        root.bind("c",       lambda _: self.cycle_color())
        root.bind("0",       lambda _: self.set_color_index(6))  # 6 is Classic Orange

        # Mouse Wheel zoom
        root.bind("<MouseWheel>", self._on_mouse_wheel)

        # Drag window
        self._drag_ox = self._drag_oy = 0
        self._cv.bind("<ButtonPress-1>", self._drag_start)
        self._cv.bind("<B1-Motion>",     self._drag_move)

        # Context Menu (Right Click)
        self._build_context_menu()
        self._cv.bind("<ButtonPress-3>", self._show_context_menu)

        # Canvas items
        self._camp_base_img: tk.PhotoImage | None = None  # unscaled COMB_W x COMB_H source
        self._camp_img_disp: tk.PhotoImage | None = None  # zoom()-scaled image actually shown
        self._camp_id: int = 0
        self._spark_ids: list[int] = []

        # Engine & timing
        self.engine = FireEngine()
        self._tier        = TIER_CRACKLE
        self._intensity   = 0.5
        self._elapsed     = 0.0
        self._last_sim    = -999.0
        self._last_jitter = 0
        self._last_t      = time.perf_counter()

        # Apply initial theme (0: Fire & Ice)
        self.set_color_index(0)

        # Setup size geometry & initial frame
        self._recalc_geometry()

        root.after(DISPLAY_MS, self._tick)

    # ── size & geometry ───────────────────────────────────────────────────────

    def set_scale(self, new_scale: int) -> None:
        clamped = max(2, min(12, new_scale))
        if clamped == self.scale:
            return
        self.scale = clamped
        self._recalc_geometry()

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        if event.delta > 0:
            self.set_scale(self.scale + 1)
        elif event.delta < 0:
            self.set_scale(self.scale - 1)

    def _recalc_geometry(self) -> None:
        sc = self.scale
        self._camp_w_px = COMB_W * sc
        self._camp_h_px = COMB_H * sc

        win_w = self._camp_w_px + int(60 * (sc / 6.0))
        win_h = self._camp_h_px + int(80 * (sc / 6.0))

        if self._first_layout:
            self._first_layout = False
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            x = max(0, screen_w - win_w - 36)
            y = max(0, screen_h - win_h - 48)
            self._win_w = win_w
            self._win_h = win_h
            self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        else:
            # Anchor to bottom-center so logs remain planted on the desktop when scaling
            cur_x = self.root.winfo_x()
            cur_y = self.root.winfo_y()
            old_w = getattr(self, "_win_w", win_w)
            old_h = getattr(self, "_win_h", win_h)
            new_x = cur_x - (win_w - old_w) // 2
            new_y = cur_y - (win_h - old_h)
            self._win_w = win_w
            self._win_h = win_h
            self.root.geometry(f"{win_w}x{win_h}+{new_x}+{new_y}")

        self._cv.config(width=win_w, height=win_h)

        self._camp_x0 = (win_w - self._camp_w_px) // 2
        self._camp_y0 = win_h - self._camp_h_px - max(8, int(16 * (sc / 6.0)))

        self._spark_ox = self._camp_x0 + (LOG_X_IN_COMB + LOG_W // 2) * sc
        self._spark_oy = self._camp_y0 + (LOG_Y_IN_COMB + 4) * sc

        # Unscaled COMB_W x COMB_H source image — PhotoImage.zoom() (C-level pixel
        # replication) does the sc-times upscale instead of a Python nested loop,
        # so redraw cost no longer grows with sc^2.
        self._camp_base_img = tk.PhotoImage(width=COMB_W, height=COMB_H)
        if self._camp_id:
            self._cv.delete(self._camp_id)
        self._camp_id = self._cv.create_image(
            self._camp_x0, self._camp_y0, anchor=tk.NW, image=self._camp_base_img
        )

        self._composite_and_blit(self._last_jitter)

    # ── color control ─────────────────────────────────────────────────────────

    def set_color_index(self, idx: int) -> None:
        self._theme_idx = idx % len(PRESET_THEMES)
        name, colors = PRESET_THEMES[self._theme_idx]
        self.engine.set_colors(colors)
        self._composite_and_blit(self._last_jitter)

    def cycle_color(self) -> None:
        self.set_color_index(self._theme_idx + 1)

    # ── context menu ──────────────────────────────────────────────────────────

    def _build_context_menu(self) -> None:
        m = tk.Menu(self.root, tearoff=0)

        # Multi-color submenu
        multi_menu = tk.Menu(m, tearoff=0)
        for i in range(6):
            cname, _ = PRESET_THEMES[i]
            multi_menu.add_command(label=cname, command=lambda idx=i: self.set_color_index(idx))
        m.add_cascade(label="🌈 多彩混色 (Multi-Color)", menu=multi_menu)

        # Single-color submenu
        single_menu = tk.Menu(m, tearoff=0)
        for i in range(6, len(PRESET_THEMES)):
            cname, _ = PRESET_THEMES[i]
            single_menu.add_command(label=cname, command=lambda idx=i: self.set_color_index(idx))
        m.add_cascade(label="🎨 经典单色 (Single-Color)", menu=single_menu)

        # Size submenu
        s_menu = tk.Menu(m, tearoff=0)
        s_menu.add_command(label="小 / Small (4x)",  command=lambda: self.set_scale(4))
        s_menu.add_command(label="中 / Medium (6x)", command=lambda: self.set_scale(6))
        s_menu.add_command(label="大 / Large (8x)",  command=lambda: self.set_scale(8))
        s_menu.add_command(label="特大 / XL (10x)",   command=lambda: self.set_scale(10))
        m.add_cascade(label="📏 尺寸 (Size)", menu=s_menu)

        # Phase submenu
        p_menu = tk.Menu(m, tearoff=0)
        p_menu.add_command(label="🔥 燃火模式 (Flame - F)", command=lambda: self.set_phase(PHASE_FLAME))
        p_menu.add_command(label="🪵 余烬暗火 (Ember - E)", command=lambda: self.set_phase(PHASE_EMBER))
        p_menu.add_command(label="💨 熄灭冷柴 (Extinguish - O)", command=lambda: self.set_phase(PHASE_OUT))
        m.add_cascade(label="🪵 状态阶段 (Phase)", menu=p_menu)

        # Tier submenu
        t_menu = tk.Menu(m, tearoff=0)
        for t in (TIER_HUSH, TIER_GLOW, TIER_CRACKLE, TIER_ROAR, TIER_BLAZE):
            t_menu.add_command(label=TIER_LABELS[t], command=lambda val=t: self._set_tier(val))
        m.add_cascade(label="🔥 火势 (Tier)", menu=t_menu)

        # Source-provided menu extensions (open interface for any input source)
        if hasattr(self.source, "populate_menu"):
            self.source.populate_menu(m, app=self)

        m.add_separator()
        m.add_command(label="🔕 减弱动态效果 (Reduce Motion - R)", command=self.toggle_reduce_motion)
        m.add_command(label="📌 切换置顶 (Toggle Topmost - T)", command=self.toggle_topmost)
        m.add_command(label="❌ 退出 (Quit - ESC)", command=self.root.quit)
        self._menu = m

    def set_source(self, source=None) -> None:
        """Dynamically attach or detach an input source (duck-typed or BaseSource).
        Detaching (source=None) falls back to the built-in RandomSource, so
        self.source is always a valid, pollable source."""
        self.source.stop()
        self.source = source if source is not None else RandomSource()
        self.source.start()
        if source is None:
            self.root.title("🔥 CampFire")
            self._last_status_text = None
            self.engine.set_weights(None)
            self._composite_and_blit(self._last_jitter)
        self._build_context_menu()

    def set_phase(self, phase: str) -> None:
        self.engine.phase = phase
        if phase == PHASE_OUT:
            self.engine._heat = bytearray(FIRE_W * FIRE_H)
        self._composite_and_blit(self._last_jitter)

    def toggle_reduce_motion(self) -> None:
        self._reduce_motion = not self._reduce_motion

    def toggle_topmost(self) -> None:
        self._topmost = not self._topmost
        self.root.wm_attributes("-topmost", self._topmost)

    def _show_context_menu(self, event: tk.Event) -> None:
        self._menu.post(event.x_root, event.y_root)

    # ── interactions ──────────────────────────────────────────────────────────

    def _set_tier(self, tier: int) -> None:
        self._tier = tier
        self.engine.tier = tier
        if self.engine.phase != PHASE_FLAME:
            self.set_phase(PHASE_FLAME)

    def _drag_start(self, e: tk.Event) -> None:
        self._drag_ox = e.x_root - self.root.winfo_x()
        self._drag_oy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e: tk.Event) -> None:
        self.root.geometry(f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}")

    def _composite_and_blit(self, jitter_grid: int = 0) -> None:
        grid: list[list[str]] = [[BG] * COMB_W for _ in range(COMB_H)]

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

        # 3. Blit the unscaled grid, then let PhotoImage.zoom() (Tk's C-level pixel
        # replication) do the sc-times upscale — avoids an O(sc^2) Python loop.
        if self._camp_base_img is None:
            return
        rows = ["{" + " ".join(row) + "}" for row in grid]
        self._camp_base_img.put(" ".join(rows))

        sc = self.scale
        self._camp_img_disp = self._camp_base_img.zoom(sc, sc) if sc > 1 else self._camp_base_img
        self._cv.itemconfig(self._camp_id, image=self._camp_img_disp)

    def _tick(self) -> None:
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
            if snap.status_text is not None and snap.status_text != getattr(self, "_last_status_text", None):
                self._last_status_text = snap.status_text
                self.root.title(f"🔥 {snap.status_text}")

        ig = self._intensity

        # Reduce motion: 6 fps simulation step, otherwise 12 fps
        step_fps = 6 if self._reduce_motion else SIM_FPS
        sim_due = (t - self._last_sim >= 1.0 / step_fps)

        # Flame sway (grid units): 0 when motion reduced or phase is not flame
        amp = 0.0 if (self._reduce_motion or self.engine.phase != PHASE_FLAME) else self._JITTER_AMP_GRID.get(self._tier, 1.0)
        jitter_grid = int(round(math.sin(t * 2.2) * amp))

        # Heat-field physics is gated to sim_fps (matches upstream's stepFPS); the
        # redraw itself runs every display tick so sway stays smooth — cheap now
        # that scaling is offloaded to PhotoImage.zoom() instead of a Python loop.
        if sim_due:
            self._last_sim = t
            self.engine.step()
        self._last_jitter = jitter_grid
        self._composite_and_blit(jitter_grid)

        # Sparks
        for sid in self._spark_ids:
            self._cv.delete(sid)
        self._spark_ids.clear()
        self._render_sparks(t, ig)

        self.root.after(DISPLAY_MS, self._tick)

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
        ox       = self._spark_ox
        oy       = self._spark_oy

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
            fire_x0 = self._camp_x0 + LOG_X_IN_COMB * sc  # screen x of fire column fx=0
            col_x = max(0, min(FIRE_W - 1, int(round((sx - fire_x0) / sc))))
            if life > 0.55:
                spark_col = self.engine.color_table[30][col_x] or "#fff8b0"
            elif life > 0.25:
                spark_col = self.engine.color_table[20][col_x] or "#ffb428"
            else:
                spark_col = self.engine.color_table[10][col_x] or "#dc3008"

            # Mac tinyfire: clean 1x2 pixel sprite particle (no trail)
            sid = self._cv.create_rectangle(
                sx - spark_w // 2, sy - spark_h // 2,
                sx + spark_w // 2, sy + spark_h // 2,
                fill=spark_col, outline="",
            )
            self._spark_ids.append(sid)


# ── entry ─────────────────────────────────────────────────────────────────────

def main() -> None:
    root = tk.Tk()
    app = CampfireApp(root)

    def on_close():
        app.source.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
