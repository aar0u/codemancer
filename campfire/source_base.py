"""
source_base.py — Unified source interface for Campfire.
Decouples input data (audio, CPU, tokens, etc.) from rendering.
"""

from dataclasses import dataclass
from typing import Optional

# ── standard phases and tiers ──────────────────────────────────────────────────

PHASE_FLAME = "flame"
PHASE_EMBER = "ember"
PHASE_OUT   = "out"

TIER_HUSH    = 0
TIER_GLOW    = 1
TIER_CRACKLE = 2
TIER_ROAR    = 3
TIER_BLAZE   = 4

TIER_LABELS = {
    TIER_HUSH:    "1: 微火 (Hush)",
    TIER_GLOW:    "2: 余火 (Glow)",
    TIER_CRACKLE: "3: 篝火 (Crackle)",
    TIER_ROAR:    "4: 烈火 (Roar)",
    TIER_BLAZE:   "5: 爆燃 (Blaze)",
}


@dataclass
class SourceSnapshot:
    """
    Standard snapshot emitted by any input source.
    CampfireApp reads this every tick to update its state.
    """
    phase: Optional[str] = None          # "flame", "ember", "out"
    intensity: Optional[float] = None    # 0.0 ~ 1.0 (controls flame height/heat)
    tier: Optional[int] = None           # 0 (Hush) .. 4 (Blaze)
    spark_burst: Optional[float] = None  # 0.0 ~ 1.0 (triggers extra spark burst)
    color_weights: Optional[list[float]] = None  # dynamic weights for multi-color bands
    status_text: Optional[str] = None    # optional label for window title or tooltip


class BaseSource:
    """Abstract interface for all campfire input sources."""

    @property
    def name(self) -> str:
        """Display name of the input source."""
        return "Source"

    def start(self) -> None:
        """Start listening / collecting data."""
        pass

    def stop(self) -> None:
        """Stop listening and release resources."""
        pass

    def poll(self) -> Optional[SourceSnapshot]:
        """Called every frame by CampfireApp to get the latest state."""
        return None

    def populate_menu(self, parent_menu, app=None) -> None:
        """
        Optional hook: attach source-specific menu items or submenus to parent_menu.
        Allows input sources to provide their own UI/controls dynamically.
        """
        pass

