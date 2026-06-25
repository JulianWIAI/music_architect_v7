"""
Phase C1 — Rhythmic Decoupling.

Extracts raw pitches from an ingested note list and re-maps them onto a
modern, probabilistically generated rhythm grid tailored to the target genre.
Original timing is completely discarded; only pitch (and approximate velocity
scaled to energy) is preserved.
"""

from __future__ import annotations

import random
from typing import List, Tuple

# (beat_pos: float, duration_beats: float, pitch: int, velocity: int)
NoteList = List[Tuple[float, float, int, int]]

# Genres and their rhythm grid parameters
_TRAP_PHONK = frozenset({"trap", "phonk"})
_TECHNO_EDM  = frozenset({"techno", "house", "edm"})


def _genre_grid(target_genre: str, tpqn: int):
    """Return (swing_beats, durations_beats, weights) for target_genre."""
    g = target_genre.lower()
    if g in _TRAP_PHONK:
        swing_ms = 15
        dur_ticks = [tpqn // 4, tpqn // 2, tpqn // 8]
        weights   = [0.2, 0.4, 0.4]
    elif g in _TECHNO_EDM:
        swing_ms = 0
        dur_ticks = [tpqn, tpqn // 2, tpqn // 4]
        weights   = [0.1, 0.6, 0.3]
    else:  # pop, hiphop, jpop, cinematic, classical, default
        swing_ms = 5
        dur_ticks = [tpqn, tpqn // 2]
        weights   = [0.5, 0.5]

    # Convert tick durations to beats (1 beat = tpqn ticks)
    dur_beats = [t / tpqn for t in dur_ticks]
    # Convert swing_ms to beats: tick_offset = swing_ms/1000 * tpqn*2 → beats = offset/tpqn
    swing_beats = (swing_ms / 1000.0) * 2.0  # equivalent: swing_ms*2/1000
    return swing_beats, dur_beats, weights


class RhythmicDecoupler:
    """
    Strips timing from seed notes and applies a genre-specific probabilistic
    rhythm grid to the extracted pitches.
    """

    _REST_PROBABILITY = 0.15  # probability of inserting a rest instead of a note

    def apply(
        self,
        seed_notes: NoteList,
        target_genre: str,
        tpqn: int = 480,
        total_beats: float = 64.0,
    ) -> NoteList:
        """
        Parameters
        ----------
        seed_notes    : source notes — only pitches (and velocities) are kept.
        target_genre  : determines the rhythm grid and swing amount.
        tpqn          : ticks-per-quarter-note (used for duration scaling only).
        total_beats   : how many beats of output to generate.

        Returns
        -------
        A new NoteList with genre-appropriate timing.
        """
        if not seed_notes:
            return []

        pitches    = [n[2] for n in seed_notes]
        velocities = [n[3] for n in seed_notes]

        swing_beats, dur_options, weights = _genre_grid(target_genre, tpqn)

        result: NoteList = []
        current_beat = 0.0
        pitch_idx    = 0
        step_count   = 0  # counts placed *notes* (not rests) for off-beat detection

        while current_beat < total_beats and pitch_idx < len(pitches):
            selected_dur = random.choices(dur_options, weights=weights, k=1)[0]

            # Rest insertion
            if random.random() < self._REST_PROBABILITY:
                current_beat += selected_dur * 2  # rest lasts twice the selected duration
                step_count += 1
                continue

            # Micro-timing swing on odd steps (off-beats)
            onset = current_beat
            if swing_beats > 0 and (step_count % 2 == 1):
                onset += swing_beats

            # Clamp so note doesn't exceed total_beats
            if onset >= total_beats:
                break

            pitch    = pitches[pitch_idx % len(pitches)]
            velocity = velocities[pitch_idx % len(velocities)]

            # Clip duration so it doesn't spill past total_beats
            duration = min(selected_dur, total_beats - onset)

            result.append((round(onset, 4), round(duration, 4), pitch, velocity))

            pitch_idx    += 1
            step_count   += 1
            current_beat += selected_dur

        return result
