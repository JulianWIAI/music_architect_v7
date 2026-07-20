"""
inverted_filter_sweep.py — Billboard "Inverted Filter Sweep" intro archetype.

The lowest note of each chord voicing is displaced up one octave (+12 semitones),
creating a first-inversion sonority with an open, airy low end.  Simultaneously,
velocity sweeps from 20 % up to 100 % of bar_vel across the intro section,
simulating a high-pass / bandpass filter gradually opening from the top down.

Commercial reference
--------------------
deadmau5 ("Ghosts n Stuff" intro synth stacks), Martin Garrix pre-drop pads,
Eric Prydz atmospheric chords ("Call on Me"), Eric Rymer-style progressive house —
inverted voicings with a slow velocity rise are a signature of progressive
electronic intros because they give a sense of "emergence" before the drop.

Inversion algorithm (per bar)
------------------------------
Given chord_notes = [n1, n2, n3, ...] sorted by pitch:
  lowest_note   = min(chord_notes)
  inverted_chord = [n for n in chord_notes if n != lowest_note first occurrence]
                   + [lowest_note + 12]

This lifts the bass tone into the mid register, thinning the low end
and brightening the overall voicing.

Velocity envelope
------------------
  build_frac  = (bar + 1) / section_bars
  sweep_vel   = max(28, int(bar_vel * (0.20 + 0.80 * build_frac)))

Gate: sustained, 3.6–4.0 beats.  Humanisation is minimal (0.010 * h_amt)
so the pad sounds programmatic — consistent with electronic production style.
"""

from __future__ import annotations

import random
from typing import Callable, List, Tuple


class InvertedFilterSweep:
    """First-inversion chord pads with 20→100% velocity sweep across intro."""

    # ── Velocity sweep envelope ───────────────────────────────────────────────
    _VEL_FLOOR_RATIO: float = 0.20   # start at 20% of bar_vel
    _VEL_CEIL_RATIO:  float = 1.00   # reach 100% by the final bar
    _VEL_MIN:         int   = 28     # hard floor so notes are always audible

    # ── Gate (sustained pad feel) ─────────────────────────────────────────────
    _GATE_LO: float = 3.60
    _GATE_HI: float = 4.00

    # ── Humanisation (minimal for electronic/programmatic feel) ───────────────
    _HUM_SIGMA_SCALE: float = 0.010

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
        Return inverted chord pad events for one bar.

        Parameters
        ----------
        bar           : Current bar index in the intro section (0-based).
        section_bars  : Total intro section bars (used for velocity envelope).
        chord_notes   : MIDI pitches from the composition engine.
        beat_pos      : Absolute beat position of this bar's downbeat.
        bar_vel       : Base velocity for this bar.
        h_amt         : Humanisation amount scalar (0.0 – 1.0).
        humanize_fn   : Callable(position, sigma) → jittered beat position.
        gate_fn       : Callable(duration) → humanised gate length.
        key_root_midi : Unused; included for archetype API consistency.
        key_scale     : Unused; included for archetype API consistency.
        """

        events: List[Tuple[float, float, int, int]] = []

        if not chord_notes:
            return events

        # ── Apply first inversion: lift the lowest note up one octave ─────────
        lowest_note: int = min(chord_notes)
        # Build inverted chord: remove the first occurrence of lowest_note
        # and push it to the top of the voicing (+12).
        remaining: List[int] = list(chord_notes)
        remaining.remove(lowest_note)          # removes first occurrence only
        inverted_chord: List[int] = remaining + [lowest_note + 12]

        # ── Velocity sweep: 20% → 100% of bar_vel across the section ──────────
        build_frac: float = (bar + 1) / max(1, section_bars)
        sweep_ratio: float = cls._VEL_FLOOR_RATIO + (cls._VEL_CEIL_RATIO - cls._VEL_FLOOR_RATIO) * build_frac
        sweep_vel: int = max(cls._VEL_MIN, int(bar_vel * sweep_ratio))

        # ── Sustained gate ─────────────────────────────────────────────────────
        pad_gate: float = gate_fn(random.uniform(cls._GATE_LO, cls._GATE_HI))

        # ── Minimal humanisation (programmatic electronic feel) ────────────────
        pad_time: float = humanize_fn(beat_pos, cls._HUM_SIGMA_SCALE * h_amt)

        for note in inverted_chord:
            events.append((pad_time, pad_gate, note, sweep_vel))

        return events
