"""
syncopated_anticipation.py — Billboard "Syncopated Anticipation" intro archetype.

The chord strikes on the "and of 4" (beat_pos + 3.5), leaving the bar's
downbeat completely empty.  In music theory this is called a "rhythmic
anticipation" — the chord sounds before the bar it belongs to, which
creates a continuous forward pull in the groove.

Commercial reference
--------------------
Drake ("God's Plan" intro chords), Future ("Mask Off" atmosphere),
Travis Scott chord stabs, Fisher / Chris Lake / Skrillex house sets —
all lead with the "and-of-4" hit to build tension into the next bar.

Per-bar event structure
------------------------
  beat_pos + 0.0  → silent (downbeat intentionally empty)
  beat_pos + 3.5  → full chord stab, 85–100 % velocity, short gate

Chord polyphony cap: 4 notes maximum.
Gate: 0.25–0.45 beats (staccato punch, not sustained).

The hit's humanisation is intentionally tight (0.008 * h_amt) so the
anticipation lands precisely — sloppiness undermines the groove function.
"""

from __future__ import annotations

import random
from typing import Callable, List, Tuple


class SyncopatedAnticipation:
    """Chord hit on beat 3.5 ('and of 4') only; downbeat left empty."""

    # ── Maximum chord notes to include (keeps the stab punchy, not muddy) ────
    _MAX_CHORD_NOTES: int = 4

    # ── Velocity and gate constants ───────────────────────────────────────────
    _VEL_RATIO_LO: float = 0.85   # anticipation is prominent — high floor
    _VEL_RATIO_HI: float = 1.00
    _VEL_MIN:      int   = 55
    _GATE_LO:      float = 0.25   # short punch
    _GATE_HI:      float = 0.45

    # ── Fixed timing offset (the "and of 4" in 4/4 time) ─────────────────────
    _ANTICIPATION_OFFSET: float = 3.5

    # ── Humanisation sigma — kept tight to preserve groove precision ──────────
    _HUM_SIGMA_SCALE: float = 0.008

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
        Return one chord stab event at beat_pos + 3.5.

        Parameters
        ----------
        bar           : Current bar index in section (0-based). Unused but
                        retained for consistent archetype API.
        section_bars  : Total intro section bars. Unused — pattern is constant.
        chord_notes   : MIDI pitches from the composition engine (voice-led).
        beat_pos      : Absolute beat position of this bar's downbeat.
        bar_vel       : Base velocity for this bar.
        h_amt         : Humanisation amount scalar (0.0 – 1.0).
        humanize_fn   : Callable(position, sigma) → jittered beat position.
        gate_fn       : Callable(duration) → humanised gate length.
        key_root_midi : Unused; included for archetype API consistency.
        key_scale     : Unused; included for archetype API consistency.
        """

        events: List[Tuple[float, float, int, int]] = []

        # ── Select chord tones (cap at 4 for punch) ──────────────────────────
        stab_notes: List[int] = chord_notes[: cls._MAX_CHORD_NOTES]
        if not stab_notes:
            return events

        # ── One stab event per chord tone ─────────────────────────────────────
        hit_vel: int = max(
            cls._VEL_MIN,
            int(bar_vel * random.uniform(cls._VEL_RATIO_LO, cls._VEL_RATIO_HI)),
        )
        hit_gate: float = gate_fn(random.uniform(cls._GATE_LO, cls._GATE_HI))
        hit_time: float = humanize_fn(
            beat_pos + cls._ANTICIPATION_OFFSET,
            cls._HUM_SIGMA_SCALE * h_amt,
        )

        for note in stab_notes:
            events.append((hit_time, hit_gate, note, hit_vel))

        return events
