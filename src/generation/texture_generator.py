"""
Texture Generator — Phase C2 / Track 09_Texture.

Produces a counter-melody by mathematically inverting the pitch intervals
of the 04_Melody track within the active scale, with 30 % velocity
reduction and 1.5× duration stretch.
"""

from __future__ import annotations

import random
from typing import List, Tuple

NoteList = List[Tuple[float, float, int, int]]

_VELOCITY_REDUCTION = 0.70   # multiply melody velocity by this
_DURATION_STRETCH   = 1.50   # multiply melody duration by this


def _expand_scale(scale_notes: List[int], lo: int = 36, hi: int = 96) -> List[int]:
    """Expand a single-octave scale across the MIDI range [lo, hi]."""
    if not scale_notes:
        return list(range(lo, hi))
    base = [n % 12 for n in scale_notes]
    expanded = []
    for midi in range(lo, hi + 1):
        if midi % 12 in base:
            expanded.append(midi)
    return expanded


def _nearest_scale_note(target: int, expanded: List[int]) -> int:
    if not expanded:
        return target
    return min(expanded, key=lambda n: abs(n - target))


class TextureGenerator:
    """Generates 09_Texture: interval-inverted counter-melody of 04_Melody."""

    def generate(
        self,
        melody_notes: NoteList,
        scale_notes: List[int],
        anchor_pitch: int = 60,
    ) -> NoteList:
        """
        Parameters
        ----------
        melody_notes  : the 04_Melody track notes.
        scale_notes   : MIDI note list for the active scale (one octave).
        anchor_pitch  : starting pitch for the texture voice; inversions are
                        computed relative to this note.

        Returns
        -------
        NoteList with inverted intervals, reduced velocity, stretched duration.
        """
        if not melody_notes:
            return []

        expanded = _expand_scale(scale_notes)
        if not expanded:
            return []

        result: NoteList = []
        prev_melody_pitch   = melody_notes[0][2]
        prev_texture_pitch  = _nearest_scale_note(anchor_pitch, expanded)

        for (onset, duration, pitch, velocity) in melody_notes:
            interval = pitch - prev_melody_pitch          # how much melody moved
            target   = prev_texture_pitch - interval      # invert: move opposite

            # Clamp to comfortable range before scale quantisation
            target = max(36, min(84, target))
            texture_pitch = _nearest_scale_note(target, expanded)

            texture_vel = max(1, min(127, int(velocity * _VELOCITY_REDUCTION)))
            texture_dur = round(min(duration * _DURATION_STRETCH, 4.0), 4)

            result.append((onset, texture_dur, texture_pitch, texture_vel))

            prev_melody_pitch  = pitch
            prev_texture_pitch = texture_pitch

        return result
