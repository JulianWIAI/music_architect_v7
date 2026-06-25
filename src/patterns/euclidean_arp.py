"""
Euclidean (Bjorklund) arpeggio generator — Phase C2 / Track 07_Arp.

Distributes N hits as evenly as possible across K steps per bar using the
Bjorklund algorithm, then maps chord tones onto the active slots.
"""

from __future__ import annotations

import random
from typing import List, Tuple

NoteList = List[Tuple[float, float, int, int]]


def _bjorklund(n: int, k: int) -> List[int]:
    """
    Return a binary sequence of length k with n ones distributed as
    evenly as possible (Bjorklund / Euclidean rhythm algorithm).
    """
    if k == 0 or n == 0:
        return [0] * k
    if n >= k:
        return [1] * k

    pattern: List[List[int]] = [[1] if i < n else [0] for i in range(k)]

    while True:
        ones   = [p for p in pattern if p[-1] == 1]
        zeros  = [p for p in pattern if p[-1] == 0]
        if len(zeros) <= 1 or len(ones) == 0:
            break
        count  = min(len(ones), len(zeros))
        merged = [ones[i] + zeros[i] for i in range(count)]
        rest   = ones[count:] + zeros[count:]
        pattern = merged + rest

    return [bit for sub in pattern for bit in sub]


class EuclideanArpGenerator:
    """
    Generates a 07_Arp track by running the Bjorklund algorithm over
    the notes of each active chord and cycling through their tones.
    """

    # steps per bar (16 = 16th-note grid)
    _STEPS = 16
    # default hits per bar by genre character
    _HITS_BY_GENRE = {
        "trap": 5, "phonk": 5,
        "techno": 8, "house": 8, "edm": 8,
        "pop": 6, "jpop": 6,
        "hiphop": 5,
        "cinematic": 4, "classical": 4,
    }

    def generate(
        self,
        chord_progression: List[str],
        structure: List[Tuple[str, int]],
        chord_notes_fn,          # callable(root, quality, octave) → List[int]
        parse_chord_fn,          # callable(chord_str) → (root, quality)
        volume: float = 0.5,
        genre: str = "pop",
    ) -> NoteList:
        """
        Parameters
        ----------
        chord_progression : one chord string per bar.
        structure         : list of (section_name, num_bars).
        chord_notes_fn    : get_chord_midi_notes from genre_constants.
        parse_chord_fn    : parse_chord_string from genre_constants.
        volume            : velocity scale [0..1].
        genre             : used to pick default hit density.

        Returns
        -------
        NoteList  [(beat_pos, duration, pitch, velocity), ...]
        """
        base_vel = int(70 * volume)
        step_dur = 4.0 / self._STEPS        # beats per 16th note
        n_hits   = self._HITS_BY_GENRE.get(genre.lower(), 6)
        pattern  = _bjorklund(n_hits, self._STEPS)

        result: NoteList = []
        bar_idx   = 0
        chord_idx = 0

        for section_type, section_bars in structure:
            # Suppress arp in silent sections
            if section_type in ("intro", "break", "outro"):
                bar_idx   += section_bars
                chord_idx += section_bars
                continue

            for _ in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                root, quality = parse_chord_fn(chord_progression[chord_idx])
                c_notes = chord_notes_fn(root, quality, 5)
                if not c_notes:
                    c_notes = [60, 64, 67]

                # Rotate the Euclidean pattern by a random offset each bar
                offset = random.randint(0, self._STEPS - 1)
                rotated = pattern[offset:] + pattern[:offset]

                bar_time = bar_idx * 4.0
                tone_idx = 0

                for step, hit in enumerate(rotated):
                    if hit:
                        pitch    = c_notes[tone_idx % len(c_notes)]
                        onset    = bar_time + step * step_dur
                        velocity = min(127, base_vel + random.randint(-8, 8))
                        result.append((round(onset, 4), round(step_dur * 0.8, 4), pitch, velocity))
                        tone_idx += 1

                bar_idx   += 1
                chord_idx += 1

        return result
