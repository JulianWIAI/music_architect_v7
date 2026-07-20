"""
fx.py -- 10_FX generator: sparse 1-bar phrase-boundary impacts and vocal mask guard.

Music Theory Context:
    FX events are non-melodic, transitional MIDI events placed at phrase and
    section boundaries.  They include:

    1. IMPACT HITS -- a single high-velocity note at section transitions.
       The pitch is irrelevant (will be routed to an FX sample/impulse); what
       matters is the timing: exactly on the downbeat of the new section.

    2. RISER CUES  -- sustained notes with rising pitch bend (pre-build to drop).
       Implemented as long whole-note events that trigger a riser sample.

    3. REVERSE CYMBAL (white noise) -- placed 1-2 beats BEFORE the drop.
       MIDI note 97 (if routed to a reverse crash sample slot).

    4. DOWNBEAT ACCENT -- short note at beat 0 of every 4-bar phrase boundary,
       reinforcing the macro-structure for the listener.

    Sparse design: at most 1-2 events per section boundary, NOT per bar.
    Placing an FX event every bar destroys the impact hierarchy.

    Vocal Mask Guard:
        10_FX events are NOT subject to vocal mask transposition because they
        route to non-pitched FX sample layers.  The notes are dummy triggers
        (pitch value is irrelevant).  However, the generator avoids placing
        notes in the vocal zone to prevent accidental pitched MIDI output
        if the FX channel is accidentally routed to a pitched instrument.

    MIDI Channel: 7
    GM Program:   Any percussion/SFX program (e.g., 112 = Tinkle Bell,
                  119 = Synth Drum, 120 = Reverse Cymbal) -- DAW-specific routing
"""

from __future__ import annotations
from typing import List, Tuple

from src.generators.base import TrackGenerator
from src.utils.phrase_boundaries import compute_phrase_boundaries

Note = Tuple[float, float, int, int]

# FX "trigger" pitches -- sit below vocal zone so no accidental pitch clash
_IMPACT_NOTE       = 48   # C3 -- impact trigger
_RISER_NOTE        = 50   # D3 -- riser trigger
_REVERSE_CYM_NOTE  = 51   # Eb3 -- reverse cymbal trigger
_DOWNBEAT_ACC_NOTE = 52   # E3 -- downbeat accent

# Sections that get an impact hit at their start
_IMPACT_SECTIONS = frozenset({'drop', 'chorus', 'climax', 'build'})
# Section transitions that warrant a riser (bar BEFORE drop/chorus)
_RISER_PRE_SECTIONS = frozenset({'drop', 'chorus', 'climax'})


class FXGenerator(TrackGenerator):
    """
    Generates the 10_FX sparse impact and riser event track.

    FX events fire ONLY at:
        - Major section boundaries (section start downbeat)
        - 4-bar phrase boundaries
        - 1-2 beats before a high-impact section (reverse cymbal / riser cue)

    No per-bar events. Placement is deterministic from seed_value.
    """

    track_name = '10_FX'
    channel    = 7

    def generate(self) -> List[Note]:
        notes: List[Note] = []

        # Compute all phrase boundaries for the full song structure
        boundaries = compute_phrase_boundaries(self.ctx.structure, phrase_bars=4)

        bar_offset = 0
        for sec_idx, (section_type, section_bars) in enumerate(self.ctx.structure):
            sec_start_beat = bar_offset * 4.0

            # --- Impact hit at section start --------------------------------
            if section_type in _IMPACT_SECTIONS:
                vel = self.velocity(110, self.section_energy(section_type), jitter=8)
                notes.append((sec_start_beat, 0.25, _IMPACT_NOTE, vel))

            # --- Reverse cymbal / riser 1-2 beats before the drop ----------
            if (section_type in _RISER_PRE_SECTIONS
                    and sec_idx > 0
                    and self.ctx.structure[sec_idx - 1][0] == 'build'):
                # Place reverse cymbal 1 beat before the section start
                rev_beat = max(0.0, sec_start_beat - 1.0)
                notes.append((rev_beat, 1.0, _REVERSE_CYM_NOTE,
                               self.velocity(90, 1.0, jitter=6)))
                # Riser: whole-note starting at build section start (-4 bars)
                riser_beat = max(0.0, sec_start_beat - 4.0)
                notes.append((riser_beat, 4.0, _RISER_NOTE,
                               self.velocity(80, 0.8, jitter=5)))

            bar_offset += section_bars

        # --- Downbeat accents at 4-bar phrase boundaries -------------------
        for boundary in boundaries:
            if not boundary.is_section:
                # 4-bar phrase mark (not a major section change) -- light accent
                if self.rng.random() < 0.40:
                    vel = self.velocity(70, self.section_energy(boundary.section_type), 8)
                    notes.append((boundary.beat, 0.12, _DOWNBEAT_ACC_NOTE, vel))

        notes.sort(key=lambda n: n[0])
        return notes
