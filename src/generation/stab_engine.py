"""
Stab Engine — Phase C2 / Track 08_Stabs.

Places high-velocity stab chords exclusively on the downbeats of
high-tension structural transitions (verse→drop, verse→chorus,
pre_chorus→chorus, build→drop).  All other bars are silent.
"""

from __future__ import annotations

import random
from typing import List, Tuple

NoteList = List[Tuple[float, float, int, int]]

# Source sections that can *precede* a high-tension transition
_TENSION_SOURCES = frozenset({"verse", "pre_chorus", "build"})
# Target sections that mark the high-tension arrival
_TENSION_TARGETS = frozenset({"chorus", "drop", "climax"})


class StabEngine:
    """Generates 08_Stabs: punctuation notes at structural tension peaks."""

    _BASE_VELOCITY = 115
    _STAB_DURATION = 0.2   # beats — short, percussive stab

    def generate(
        self,
        chord_progression: List[str],
        structure: List[Tuple[str, int]],
        chord_notes_fn,    # get_chord_midi_notes(root, quality, octave)
        parse_chord_fn,    # parse_chord_string(chord_str) → (root, quality)
        volume: float = 0.8,
    ) -> NoteList:
        """
        Returns stab notes only on the downbeats of transition bars.

        Parameters
        ----------
        chord_progression : one chord string per bar.
        structure         : list of (section_name, num_bars).
        chord_notes_fn    : from genre_constants.
        parse_chord_fn    : from genre_constants.
        volume            : velocity scale [0..1].
        """
        base_vel = int(self._BASE_VELOCITY * volume)
        result: NoteList = []

        # Walk structure, track which bars are transition downbeats
        bar_idx  = 0
        chord_idx = 0
        prev_section = ""

        for sec_idx, (section_type, section_bars) in enumerate(structure):
            is_transition_target = (
                section_type in _TENSION_TARGETS
                and prev_section in _TENSION_SOURCES
            )

            for local_bar in range(section_bars):
                # Only on the very first bar of a tension-target section
                is_stab_bar = is_transition_target and local_bar == 0

                if is_stab_bar and chord_progression:
                    root, quality = parse_chord_fn(chord_progression[chord_idx % len(chord_progression)])
                    # Upper-octave voicing for cut-through brightness
                    c_notes = chord_notes_fn(root, quality, 5)
                    if not c_notes:
                        c_notes = [72, 76, 79]

                    bar_time = bar_idx * 4.0
                    vel      = min(127, base_vel + random.randint(-5, 5))

                    for pitch in c_notes:
                        result.append((bar_time, self._STAB_DURATION, pitch, vel))

                bar_idx   += 1
                chord_idx += 1

            prev_section = section_type

        return result
