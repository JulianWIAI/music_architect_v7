"""
four_chord_loop.py — Billboard "Four-Chord Pop Loop" intro archetype.

Forces the intro to cycle through the universally proven I-V-vi-IV chord
sequence (major keys) or i-bVI-bIII-bVII (minor keys) as sustained pads,
built entirely from key_root_midi.  The engine's voice-led chord is ignored
so the progression always delivers the canonical loop regardless of what the
Markov chain selected.

Commercial reference
--------------------
"Let It Be" (Beatles), "No Woman No Cry" (Marley), "Someone Like You" (Adele),
"Don't Stop Believin'" (Journey), virtually every Max Martin / Rami Yacoub
production — the I-V-vi-IV loop has appeared in well over 1,000 charting songs.

Chord construction
-------------------
All triads are stacked in close position from key_root_midi.

Major (key_scale = 'major') — I-V-vi-IV:
  I   : root + [0, 4, 7]
  V   : root + [7, 11, 14]
  vi  : root + [9, 12, 16]
  IV  : root + [5, 9, 12]

Minor (key_scale = 'minor') — i-bVI-bIII-bVII:
  i   : root + [0, 3, 7]
  bVI : root + [8, 12, 15]
  bIII: root + [3, 7, 10]
  bVII: root + [10, 14, 17]

Chord cycling: bar % 4 selects the chord index so the 4-bar loop repeats
perfectly and always re-aligns at bar 0 regardless of section length.

Output: all triad notes as sustained pads (gate ≥ 3.8 beats) at 60–75 %
of bar_vel.  Full velocity is avoided so the pads sit under any melody/pedal.
"""

from __future__ import annotations

import random
from typing import Callable, List, Tuple


# ── Chord semitone offsets from root ─────────────────────────────────────────

# Major key: I - V - vi - IV
_MAJOR_LOOP: List[List[int]] = [
    [0, 4, 7],    # I   — tonic triad
    [7, 11, 14],  # V   — dominant triad (upper register)
    [9, 12, 16],  # vi  — relative minor (octave-adjusted)
    [5, 9, 12],   # IV  — subdominant triad
]

# Minor key: i - bVI - bIII - bVII  (natural minor four-chord)
_MINOR_LOOP: List[List[int]] = [
    [0, 3, 7],    # i    — tonic minor triad
    [8, 12, 15],  # bVI  — major triad on flat sixth
    [3, 7, 10],   # bIII — major triad on flat third
    [10, 14, 17], # bVII — major triad on flat seventh
]


class FourChordLoop:
    """Sustained I-V-vi-IV (or minor equivalent) pad loop built from key root."""

    # ── Velocity ratios (pads sit behind lead/pedal elements) ─────────────────
    _VEL_RATIO_LO: float = 0.60
    _VEL_RATIO_HI: float = 0.75
    _VEL_MIN:      int   = 36

    # ── Gate lengths (full sustain across the bar) ────────────────────────────
    _GATE_BASE: float = 3.80
    _GATE_RAND: float = 0.35   # added randomly for slight variation

    # ── Humanisation — pads can drift slightly (laid-back feel) ───────────────
    _HUM_SIGMA_SCALE: float = 0.022

    @classmethod
    def generate(
        cls,
        bar:          int,
        section_bars: int,
        chord_notes:  List[int],
        beat_pos:     float,
        bar_vel:      int,
        h_amt:        float,
        humanize_fn:  Callable[[float, float], float],
        gate_fn:      Callable[[float], float],
        key_root_midi: int = 60,
        key_scale:     str = 'major',
    ) -> List[Tuple[float, float, int, int]]:
        """
        Return sustained pad events for one bar of the Four-Chord Pop Loop.

        Parameters
        ----------
        bar           : Current bar index in the intro section (0-based).
                        bar % 4 determines which loop chord plays.
        section_bars  : Total intro section bars. Unused — loop is cyclic.
        chord_notes   : Voice-led chord from engine. Intentionally overridden
                        by the key-based loop — not used for notes.
        beat_pos      : Absolute beat position of this bar's downbeat.
        bar_vel       : Base velocity for this bar.
        h_amt         : Humanisation amount scalar (0.0 – 1.0).
        humanize_fn   : Callable(position, sigma) → jittered beat position.
        gate_fn       : Callable(duration) → humanised gate length.
        key_root_midi : MIDI tonic note at octave 4 (e.g. 60 for C4).
        key_scale     : 'major' or 'minor' — selects the chord offsets table.
        """

        # ── Select chord table based on scale ─────────────────────────────────
        loop: List[List[int]] = (
            _MINOR_LOOP if 'minor' in key_scale.lower() else _MAJOR_LOOP
        )

        # ── Pick chord by bar position in the 4-bar cycle ─────────────────────
        chord_offsets: List[int] = loop[bar % 4]
        loop_notes: List[int] = [key_root_midi + offset for offset in chord_offsets]

        # ── Build sustained pad events ─────────────────────────────────────────
        pad_vel:  int   = max(cls._VEL_MIN, int(bar_vel * random.uniform(cls._VEL_RATIO_LO, cls._VEL_RATIO_HI)))
        pad_gate: float = gate_fn(cls._GATE_BASE + random.uniform(0.0, cls._GATE_RAND))
        pad_time: float = humanize_fn(beat_pos, cls._HUM_SIGMA_SCALE * h_amt)

        events: List[Tuple[float, float, int, int]] = []
        for note in loop_notes:
            events.append((pad_time, pad_gate, note, pad_vel))

        return events
