"""
billboard — Commercially-proven intro archetype implementations.

Each module provides a single archetype class with a generate() class method
that returns (time_beats, dur_beats, midi_note, vel) event tuples.

Archetypes
----------
pedal_point            : Rhythmic root/5th pedal over chord sustain.
syncopated_anticipation: Chord hit on beat 3.5 only; downbeat stays empty.
four_chord_loop        : Forces I-V-vi-IV (major) or i-bVI-bIII-bVII (minor) pad loop.
inverted_filter_sweep  : Lowest chord note displaced +12; velocity sweeps 20→100%.
"""

from src.composition.billboard.pedal_point             import PedalPoint
from src.composition.billboard.syncopated_anticipation import SyncopatedAnticipation
from src.composition.billboard.four_chord_loop         import FourChordLoop
from src.composition.billboard.inverted_filter_sweep   import InvertedFilterSweep

__all__ = [
    'PedalPoint',
    'SyncopatedAnticipation',
    'FourChordLoop',
    'InvertedFilterSweep',
]
