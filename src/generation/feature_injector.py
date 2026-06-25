"""
FeatureInjector: post-composition transforms derived from commercial music research.

Transforms operate on the dict returned by CompositionEngine.compose() and
modify it in-place, returning the same dict for call-chaining.

Public API
----------
    fi = FeatureInjector()
    boundary = find_chorus_boundary(track_data)
    if boundary is not None:
        fi.inject_snare_buildup(track_data, boundary)
    fi.format_intro_block(track_data, intro_length_beats)
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from src.composition.genre_constants import SNARE

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Tracks treated as "melodic / high-frequency" — silenced during the intro
_MELODIC_TRACKS = frozenset({"chords", "lead", "pad", "arp"})

# MIDI channel for the Voice_Record_Trigger marker (0-indexed = channel 16)
_MARKER_CHANNEL = 15

# Snare build-up: 2 bars before a Chorus boundary (1 bar = 4 beats)
_BUILDUP_BARS = 2
_BUILDUP_BEATS = float(_BUILDUP_BARS * 4)  # 8.0 beats

# Subdivision phases: (beat_offset_start, beat_offset_end, step_in_beats)
# Each phase halves the step → doubles the note density (logarithmic doubling).
#   1/4  note = 1.000 beat
#   1/8  note = 0.500 beat
#   1/16 note = 0.250 beat
#   1/32 note = 0.125 beat
_BUILDUP_PHASES: List[Tuple[float, float, float]] = [
    (0.0, 2.0, 1.000),
    (2.0, 4.0, 0.500),
    (4.0, 6.0, 0.250),
    (6.0, 8.0, 0.125),
]

_VEL_MIN = 50
_VEL_MAX = 127

# ---------------------------------------------------------------------------
# Module-level convenience helper
# ---------------------------------------------------------------------------

def find_chorus_boundary(track_data: dict) -> Optional[float]:
    """
    Return the beat position of the first chorus-type section in
    *track_data*, or None if no such section exists.

    Recognised section types: 'chorus', 'drop', 'climax'.
    """
    cumulative_bars = 0
    for section_type, section_bars in track_data.get("structure", []):
        if section_type in ("chorus", "drop", "climax"):
            return float(cumulative_bars * 4)
        cumulative_bars += section_bars
    return None


# ---------------------------------------------------------------------------
# FeatureInjector
# ---------------------------------------------------------------------------

class FeatureInjector:
    """
    Stateless transformer: each method receives and returns the composition
    dict produced by CompositionEngine.compose().
    """

    # ------------------------------------------------------------------
    # Snare build-up
    # ------------------------------------------------------------------

    def inject_snare_buildup(
        self, track_data: dict, boundary_tick: float
    ) -> dict:
        """
        Insert a logarithmic snare crescendo roll in the 2 bars before
        *boundary_tick* (typically the downbeat of a Chorus section).

        Algorithm
        ---------
        The 2-bar window is split into four equal phases, each using a
        subdivision twice as fine as the previous (1/4 → 1/8 → 1/16 → 1/32).
        This geometric subdivision doubling is the logarithmic ramp described
        in the requirements.

        Velocity at each hit is computed via::

            vel = V_MIN + (V_MAX - V_MIN) * log2(1 + t/T)

        where *t* is the offset within the window and *T* is the total window
        length.  log2(1 + t/T) is concave-down — velocity grows quickly early
        and asymptotes toward the peak, producing the characteristic commercial
        "wall of sound" entry into the chorus.

        Existing snare hits inside the window are removed before injection to
        prevent velocity doubling.

        Args:
            track_data:    composition dict from CompositionEngine.compose()
            boundary_tick: beat position (float) of the section boundary

        Returns:
            The modified track_data dict (modified in-place).
        """
        if "drums" not in track_data.get("tracks", {}):
            return track_data

        start_tick = max(0.0, boundary_tick - _BUILDUP_BEATS)
        T = boundary_tick - start_tick  # actual available window (≤ 8 beats)

        drums: list = track_data["tracks"]["drums"]

        # Strip existing snare hits that overlap the window
        drums = [
            e for e in drums
            if not (e[2] == SNARE and start_tick <= e[0] < boundary_tick)
        ]

        # Generate roll
        new_hits: list = []
        for phase_start, phase_end, step in _BUILDUP_PHASES:
            # Scale phase boundaries to the actual window
            scaled_start = phase_start * (T / _BUILDUP_BEATS)
            scaled_end   = phase_end   * (T / _BUILDUP_BEATS)
            scaled_step  = step        * (T / _BUILDUP_BEATS)

            t = scaled_start
            while t < scaled_end - scaled_step * 0.01:
                s = t / T if T > 0 else 0.0
                vel = int(_VEL_MIN + (_VEL_MAX - _VEL_MIN) * math.log2(1.0 + s))
                vel = max(_VEL_MIN, min(_VEL_MAX, vel))
                note_dur = scaled_step * 0.9
                new_hits.append((start_tick + t, note_dur, SNARE, vel))
                t += scaled_step

        drums.extend(new_hits)
        track_data["tracks"]["drums"] = drums
        return track_data

    # ------------------------------------------------------------------
    # Intro formatting
    # ------------------------------------------------------------------

    def format_intro_block(
        self, track_data: dict, length_ticks: float
    ) -> dict:
        """
        Reshape the intro to a sparse sub/bass-only arrangement.

        - Melodic/high-frequency tracks (chords, lead, pad, arp) have all
          events before *length_ticks* removed.  Events at or after
          *length_ticks* are kept so the rest of the song is unaffected.
        - Drums and bass are left completely untouched.
        - A single-note placeholder is placed on MIDI Channel 16 at beat 0
          (pitch C-1, velocity 1) as a "Voice_Record_Trigger" DAW cue.

        Args:
            track_data:   composition dict from CompositionEngine.compose()
            length_ticks: intro length in beats (float)

        Returns:
            The modified track_data dict (modified in-place).
        """
        tracks   = track_data["tracks"]
        t_info   = track_data["track_info"]

        for name in _MELODIC_TRACKS:
            if name in tracks:
                tracks[name] = [e for e in tracks[name] if e[0] >= length_ticks]

        self._insert_voice_trigger(tracks, t_info)
        return track_data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _insert_voice_trigger(tracks: dict, track_info: dict) -> None:
        """
        Add a single C-1 (pitch=0) note at beat 0 on MIDI Channel 16.

        This is an inaudible cue note used by DAWs and live rigs to
        trigger an external voice / sample recorder at the session start.
        Pitch 0 / velocity 1 keeps it outside any audible instrument
        range while remaining a valid MIDI note-on event.
        """
        _KEY = "marker_voice_trigger"
        if _KEY not in tracks:
            tracks[_KEY] = []
            track_info[_KEY] = {"channel": _MARKER_CHANNEL, "program": 0}
        # Idempotent: only insert once
        if not any(e[0] == 0.0 and e[2] == 0 for e in tracks[_KEY]):
            tracks[_KEY].insert(0, (0.0, 1.0, 0, 1))
