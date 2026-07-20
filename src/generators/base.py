"""
base.py -- Abstract TrackGenerator interface for all 10 stem generators.

Architecture:
    Every stem generator inherits from TrackGenerator and implements exactly
    one method: generate().  The Orchestrator calls generate() on each of the
    10 generators in parallel (or in series) and assembles the returned note
    lists into the final composition dict.

    All generators receive the same SharedContext object -- the immutable musical
    contract established by the ContextManager.  They also receive a seeded
    random.Random instance so that output is reproducible from the seed_value.

Stem Index / Track Name Map:
    Index  Track Name      MIDI Channel  Description
    0      01_Kick         ch 9          Drum (kick)
    1      02_Percussion   ch 9          Drum (snare, hihat, etc.)
    2      03_Bass         ch 0          Bass synth / 808
    3      04_Melody       ch 1          Lead melody
    4      05_Chords       ch 2          Chord stabs or pads
    5      06_Pad          ch 3          Long sustain pad
    6      07_Arp          ch 4          Arpeggiator
    7      08_Stabs        ch 5          Short syncopated stabs
    8      09_Texture      ch 6          Counter-melody / atmo
    9      10_FX           ch 7          Impacts, risers, effects

    Note: Both 01_Kick and 02_Percussion write to MIDI channel 9 (GM drum channel).
    They are separate Python lists that get merged into a single MIDI track at export.

Output Format:
    Each generate() call returns List[Note] where:
        Note = (time_beats: float, duration_beats: float, midi_note: int, velocity: int)

    Drum notes use GM drum note numbers (KICK=36, SNARE=38, etc.).
    Pitched notes use standard MIDI note numbers (C4=60).
"""

from __future__ import annotations
import random
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from src.core.context_manager import SharedContext

Note = Tuple[float, float, int, int]


class TrackGenerator(ABC):
    """
    Abstract base class for all 10 stem generators.

    Subclasses MUST implement generate().
    Subclasses MAY override track_name and channel properties.

    Parameters
    ----------
    context : SharedContext built by ContextManager
    rng     : seeded random.Random (track-specific, offset from master seed)
    """

    # Subclasses override these two class attributes
    track_name: str = 'unnamed'
    channel:    int = 0

    def __init__(self, context: SharedContext, rng: random.Random):
        self.ctx = context
        self.rng = rng

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def generate(self) -> List[Note]:
        """
        Generate all notes for this stem and return them as a sorted list.

        Implementations should:
            1. Iterate over self.ctx.structure for section-awareness
            2. Use self.rng for all random decisions (reproducibility)
            3. Apply humanization where specified
            4. Apply vocal mask if self.ctx.vocal_mask is True
            5. Return sorted by time (ascending)
        """
        ...

    # ------------------------------------------------------------------
    # Shared helpers available to all subclasses
    # ------------------------------------------------------------------

    def section_energy(self, section_type: str) -> float:
        """
        Map section type to an energy coefficient [0.0, 1.0].

        Energy controls overall density and velocity in generated patterns.
        Higher energy = denser patterns, louder hits.

            intro      → 0.3   (sparse, building)
            verse      → 0.6   (moderate, groove-focused)
            pre_chorus → 0.75  (building)
            build      → 0.8   (intensifying)
            chorus     → 1.0   (full energy)
            drop       → 1.0   (maximum impact)
            climax     → 1.0
            hook       → 0.9
            bridge     → 0.65
            break      → 0.3   (stripped down)
            outro      → 0.3   (fading)
        """
        MAP = {
            'intro':      0.30,
            'verse':      0.60,
            'pre_chorus': 0.75,
            'build':      0.80,
            'chorus':     1.00,
            'drop':       1.00,
            'climax':     1.00,
            'hook':       0.90,
            'bridge':     0.65,
            'break':      0.30,
            'outro':      0.30,
        }
        return MAP.get(section_type, 0.60)

    def velocity(self, base: int, energy: float, jitter: int = 8) -> int:
        """
        Compute a humanized MIDI velocity from a base value and energy factor.

        Vout = clamp(base * energy + Δv, 1, 127)
        where Δv ~ Uniform(-jitter, +jitter)
        """
        v = int(base * energy) + self.rng.randint(-jitter, jitter)
        return max(1, min(127, v))

    def scale_note(self, degree: int, octave: int = 4) -> int:
        """
        Return the MIDI note for a scale degree (0=root) in the given octave.

        Uses the key+scale from SharedContext.
        """
        scale_midi = self.ctx.scale_midi
        if not scale_midi:
            return 60   # fallback: C4
        # Map degree to index in the scale_midi list, spanning the requested octave
        notes_per_oct = len(self.ctx.scale_notes) if self.ctx.scale_notes else 7
        # Find notes in the target octave range (octave 4 = C4-B4, MIDI 60-71)
        octave_base = 12 * (octave + 1)   # MIDI C4=60 = C(octave=4) = 12*(4+1)=60 ✓
        candidates = [n for n in scale_midi
                      if octave_base <= n < octave_base + 12]
        if not candidates:
            candidates = scale_midi  # fallback: use any available note
        idx = degree % len(candidates)
        return candidates[idx]

    def pick_scale_note(self, min_midi: int = 48,
                        max_midi: int = 84) -> int:
        """
        Pick a random note from the scale within the given MIDI range.
        """
        pool = [n for n in self.ctx.scale_midi if min_midi <= n <= max_midi]
        if not pool:
            return 60
        return self.rng.choice(pool)

    def jitter_time(self, t: float, max_ms: float = 10.0) -> float:
        """
        Apply micro-timing jitter: shift beat position by ±max_ms milliseconds.

        Converts ms to beats using current BPM.  Clamps result to >= 0.
        """
        beats_per_sec = self.ctx.bpm / 60.0
        delta = self.rng.uniform(-max_ms, max_ms) / 1000.0 * beats_per_sec
        return max(0.0, t + delta)
