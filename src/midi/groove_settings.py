"""
src/midi/groove_settings.py
───────────────────────────
Data model for per-track groove and mixer settings.

Two tiers of control:

  Tier 1 — Deterministic (always applied, fully reproducible):
    transpose_st      semitone pitch shift, written into MIDI note pitches.
    vel_min / vel_max velocity range clamp; all notes are rescaled to fit.
    vel_curve         accent pattern applied across the bar.
    swing_pct         off-beat 16th-note delay (50 = straight, 66 = triplet).
    timing_nudge_ms   fixed ±50 ms offset applied to every note on the track.
    gain_db           written as MIDI CC7 (volume) at track start.
    pan               written as MIDI CC10 (pan) at track start.

  Tier 2 — Seeded humanisation (optional, reproducible when seed is locked):
    vel_humanize      ±velocity jitter added on top of Tier 1.
    timing_humanize_ms ±timing jitter (ms) added on top of Tier 1.
    seed              int seed for reproducibility; None = new random each render.

SongGrooveSettings is the top-level container passed to GrooveProcessor.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# Velocity curve identifiers exposed to the GUI.
VEL_CURVES = ['flat', 'accent_1', 'accent_1_3', 'crescendo', 'decrescendo']

# GUI track keys — must match the keys used in app.py's track_vars dict.
TRACK_KEYS = [
    'drums', 'bass', 'chords', 'lead', 'pad',
    'arp', 'stabs', 'texture', 'fx', 'percussion',
]


@dataclass
class TrackGrooveSettings:
    """
    Groove + mixer settings for a single track.

    All Tier-1 values encode the deterministic intention; Tier-2 values add
    a controlled randomness on top.  Default values produce no change to the
    MIDI — i.e. the identity transform.
    """

    # ── Tier 1 — Deterministic ────────────────────────────────────────────────
    transpose_st:     int   = 0      # semitone shift: -24 to +24
    vel_min:          int   = 1      # velocity floor: 1–127
    vel_max:          int   = 127    # velocity ceiling: 1–127
    vel_curve:        str   = 'flat' # see VEL_CURVES
    swing_pct:        float = 50.0   # 50.0=straight, 66.0=full triplet
    timing_nudge_ms:  float = 0.0    # fixed offset per note: -50 to +50 ms
    gain_db:          float = 0.0    # mix gain: -60 dB (−∞/silence) to +6 dB; 0 = unity
    pan:              int   = 0      # pan written as CC10: -64 (L) to +63 (R)

    # ── Tier 2 — Seeded humanisation ─────────────────────────────────────────
    vel_humanize:        int   = 0    # ±velocity jitter: 0–30
    timing_humanize_ms:  float = 0.0  # ±timing jitter in ms: 0–20
    seed:                Optional[int] = None  # None = random each render

    # ── Advanced mode — raw 16-step grid data ─────────────────────────────────
    # When use_advanced is True, GrooveProcessor uses these arrays instead of the
    # simplified Tier-1 fields (vel_curve, swing_pct, timing_nudge_ms, pan).
    # Transpose, Gain, vel_min/vel_max, and Tier-2 fields are always applied.
    use_advanced: bool                 = False
    v_grid: Optional[List[float]]      = None  # 16 velocity multipliers (0–2, neutral 1.0)
    t_grid: Optional[List[float]]      = None  # 16 timing offsets in ms (±50, neutral 0.0)
    p_grid: Optional[List[float]]      = None  # 16 pan positions (−63–+63, neutral 0)
    e_grid: Optional[List[float]]      = None  # 16 expression CC11 values (0–127, neutral 64)

    def is_identity(self) -> bool:
        """Return True when this setting produces no change to the MIDI."""
        if self.use_advanced:
            # In advanced mode, check whether all grids are at their neutral values.
            _v_ok = self.v_grid is None or all(abs(x - 1.0) < 0.001 for x in self.v_grid)
            _t_ok = self.t_grid is None or all(abs(x)       < 0.001 for x in self.t_grid)
            _p_ok = self.p_grid is None or all(abs(x)       < 0.001 for x in self.p_grid)
            _e_ok = self.e_grid is None or all(abs(x - 64)  < 0.001 for x in self.e_grid)
            return (
                _v_ok and _t_ok and _p_ok and _e_ok
                and self.transpose_st == 0
                and self.vel_min == 1
                and self.vel_max == 127
                and abs(self.gain_db) < 0.01
                and self.vel_humanize == 0
                and abs(self.timing_humanize_ms) < 0.01
            )
        return (
            self.transpose_st == 0
            and self.vel_min == 1
            and self.vel_max == 127
            and self.vel_curve == 'flat'
            and abs(self.swing_pct - 50.0) < 0.01
            and abs(self.timing_nudge_ms) < 0.01
            and abs(self.gain_db) < 0.01
            and self.pan == 0
            and self.vel_humanize == 0
            and abs(self.timing_humanize_ms) < 0.01
        )

    def effective_seed(self) -> int:
        """Return the seed to use; generates a new random int if seed is None."""
        return self.seed if self.seed is not None else random.randint(0, 2 ** 31 - 1)


@dataclass
class SongGrooveSettings:
    """
    Groove settings for all tracks in a song.

    ``tracks`` is keyed by the GUI track name ('lead', 'bass', etc.).
    Missing keys fall back to an identity TrackGrooveSettings.

    When ``apply_enabled`` is False the GrooveProcessor skips processing
    entirely and returns the original MIDI path unchanged.

    ``genre`` is optional — when set, GrooveProcessor uses MicroTimingEngine
    to derive genre-aware V/T grids for any track that has not been manually
    configured (i.e. ``use_advanced=False`` and ``v_grid is None``).
    """
    tracks:        Dict[str, TrackGrooveSettings] = field(default_factory=dict)
    apply_enabled: bool = True
    genre:         Optional[str] = None   # e.g. 'trap', 'house' — enables micro-timing

    def get(self, track_key: str) -> TrackGrooveSettings:
        """Return settings for *track_key*, falling back to identity defaults."""
        return self.tracks.get(track_key, TrackGrooveSettings())

    def has_any_effect(self) -> bool:
        """Return True if at least one track has a non-identity setting."""
        return self.apply_enabled and any(
            not s.is_identity() for s in self.tracks.values()
        )
