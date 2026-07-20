"""
pedal_point.py — Billboard "Pedal Point Anchor" intro archetype.

A single sustained root or 5th pedal note repeats rhythmically over each bar
while the full chord voicing sustains underneath at a lower velocity.

Commercial reference: Max Martin ballads ("Teenage Dream"), The Weeknd
("Blinding Lights" verse intro), Drake quiet intro chords over a repeating bass.

Build logic across the intro section
-------------------------------------
build_frac = (bar + 1) / section_bars

  < 0.40  → pedal on beat 1 only (one quarter-note anchor per bar)
  0.40–0.75 → pedal on beats 1 and 2 (two quarter notes; energy doubles)
  ≥ 0.75  → pedal on beats 1, 1.5, 2, 3 (8th-note cluster; peak density)

Pedal note selection
---------------------
Even bars  → tonic  (key_root_midi, octave 4)
Odd  bars  → 5th    (key_root_midi + 7, octave 4)

The alternation prevents harmonic stasis while keeping the pedal grounded.
Chord tones (up to 4) play beneath the pedal at 58 % velocity for context.
"""

from __future__ import annotations

import random
from typing import Callable, List, Optional, Tuple


class PedalPoint:
    """Rhythmic tonic/5th pedal note over a sustained chord bed."""

    # ── Chord bed note cap (prevents muddy clusters) ──────────────────────────
    _MAX_CHORD_NOTES: int = 4

    # ── Velocity ratios (fraction of bar_vel) ─────────────────────────────────
    _PEDAL_VEL_RATIO:  float = 0.95   # pedal note is prominent
    _CHORD_VEL_RATIO:  float = 0.58   # chord bed sits behind the pedal
    _PEDAL_VEL_MIN:    int   = 50
    _CHORD_VEL_MIN:    int   = 32

    # ── Gate lengths (beats) ──────────────────────────────────────────────────
    _PEDAL_GATE_RANGE: Tuple[float, float] = (0.28, 0.44)  # short, punchy pedal
    _CHORD_GATE_MIN:   float = 3.80                         # sustain through bar

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
        Return note events for one bar of Pedal Point Anchor.

        Parameters
        ----------
        bar           : Current bar index within the intro section (0-based).
        section_bars  : Total bars in this intro section.
        chord_notes   : MIDI pitches from the composition engine's voice-leading.
        beat_pos      : Absolute beat position of this bar's downbeat.
        bar_vel       : Base velocity for this bar (already humanised by engine).
        h_amt         : Humanisation amount scalar (0.0 – 1.0).
        humanize_fn   : Callable(position, sigma) → jittered position.
        gate_fn       : Callable(duration) → humanised gate length.
        key_root_midi : MIDI note number of the key tonic at octave 4 (e.g. 60=C4).
        key_scale     : 'major' or 'minor' — unused here but kept for API parity.
        """

        events: List[Tuple[float, float, int, int]] = []

        # ── Select pedal note: tonic on even bars, 5th on odd bars ───────────
        # The 5th is always 7 semitones above the tonic.
        pedal_note: int = key_root_midi if (bar % 2 == 0) else key_root_midi + 7

        # ── Determine rhythmic density from section progress ──────────────────
        build_frac: float = (bar + 1) / max(1, section_bars)
        if build_frac < 0.40:
            # Sparse: single anchor hit on the downbeat
            pedal_offsets: List[float] = [0.0]
        elif build_frac < 0.75:
            # Medium: two quarter-note hits
            pedal_offsets = [0.0, 2.0]
        else:
            # Dense: 8th-note cluster (builds intensity before the drop)
            pedal_offsets = [0.0, 1.5, 2.0, 3.0]

        # ── 1. Pedal note hits ────────────────────────────────────────────────
        pedal_vel: int = max(cls._PEDAL_VEL_MIN, int(bar_vel * cls._PEDAL_VEL_RATIO))
        for off in pedal_offsets:
            events.append((
                humanize_fn(beat_pos + off, 0.012 * h_amt),   # tight jitter on pedal
                gate_fn(random.uniform(*cls._PEDAL_GATE_RANGE)),
                pedal_note,
                pedal_vel,
            ))

        # ── 2. Chord bed: sustained tones, lower velocity ─────────────────────
        # Cap polyphony so the pedal doesn't get buried in a dense cluster.
        bed_notes: List[int] = chord_notes[: cls._MAX_CHORD_NOTES]
        chord_vel: int = max(cls._CHORD_VEL_MIN, int(bar_vel * cls._CHORD_VEL_RATIO))
        chord_gate: float = gate_fn(cls._CHORD_GATE_MIN + random.uniform(0.0, 0.4))
        for note in bed_notes:
            events.append((
                humanize_fn(beat_pos, 0.018 * h_amt),
                chord_gate,
                note,
                chord_vel,
            ))

        return events
