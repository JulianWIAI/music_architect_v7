"""
FX Generator — Phase C2 / Track 10_FX.

Places C3 impact trigger notes (MIDI 48) using a weighted randomiser
that favours section-transition downbeats and avoids 4-bar repetition.
"""

from __future__ import annotations

import random
from typing import List, Set, Tuple

NoteList = List[Tuple[float, float, int, int]]

# MIDI note used as the impact trigger marker
_IMPACT_PITCH = 48   # C3

# Section types that are strong candidate positions for FX hits
_HIGH_TENSION_SECTIONS = frozenset({
    "build", "chorus", "drop", "climax", "tension",
    "verse", "development",
})

# Weight applied to the very first bar of a high-tension section
_TRANSITION_WEIGHT = 0.85
# Base weight for all other bars in active sections
_BASE_WEIGHT       = 0.18
# Weight for quiet/background sections
_QUIET_WEIGHT      = 0.04

_FX_VELOCITY = 110
_FX_DURATION = 0.1   # beats — very short trigger pulse


class FXGenerator:
    """Generates 10_FX: sparsely placed impact trigger notes."""

    def generate(
        self,
        structure: List[Tuple[str, int]],
        volume: float = 0.9,
    ) -> NoteList:
        """
        Parameters
        ----------
        structure : list of (section_name, num_bars).
        volume    : velocity scale [0..1].

        Returns
        -------
        NoteList of C3 impact trigger notes.
        """
        base_vel = int(_FX_VELOCITY * volume)
        result:   NoteList = []
        # Track which (bar mod 4) positions have recently had an FX note
        # to avoid 4-bar repetition
        recent_mod4: Set[int] = set()

        bar_idx      = 0
        prev_section = ""

        for section_type, section_bars in structure:
            for local_bar in range(section_bars):
                global_bar = bar_idx
                mod4       = global_bar % 4

                is_transition = (
                    local_bar == 0
                    and section_type in _HIGH_TENSION_SECTIONS
                    and prev_section != section_type
                )

                # Determine placement probability
                if is_transition:
                    prob = _TRANSITION_WEIGHT
                elif section_type in _HIGH_TENSION_SECTIONS:
                    prob = _BASE_WEIGHT
                else:
                    prob = _QUIET_WEIGHT

                # Suppress if this mod-4 position was used recently
                if mod4 in recent_mod4:
                    prob *= 0.20   # strongly reduce, but don't fully block transitions

                if random.random() < prob:
                    bar_time = global_bar * 4.0
                    vel      = min(127, base_vel + random.randint(-8, 8))
                    result.append((bar_time, _FX_DURATION, _IMPACT_PITCH, vel))
                    recent_mod4.add(mod4)
                    # Allow re-use after 4 different positions have cycled
                    if len(recent_mod4) >= 4:
                        recent_mod4.clear()

                bar_idx += 1
            prev_section = section_type

        return result
