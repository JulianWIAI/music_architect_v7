"""
intro.py — BillboardIntroMatrix master dispatcher.

Routes archetype name strings to their corresponding Billboard archetype
class generate() methods.  Acts as the single public interface between
intro_archetype_registry.py and the four billboard sub-modules.

Registered archetypes
----------------------
  pedal_point             → PedalPoint.generate()
  syncopated_anticipation → SyncopatedAnticipation.generate()
  four_chord_loop         → FourChordLoop.generate()
  inverted_filter_sweep   → InvertedFilterSweep.generate()

Usage
------
  from src.generators.intro import BillboardIntroMatrix

  events = BillboardIntroMatrix.generate(
      archetype     = 'pedal_point',
      bar           = 2,
      section_bars  = 8,
      chord_notes   = [60, 64, 67],
      beat_pos      = 8.0,
      bar_vel       = 90,
      h_amt         = 0.6,
      humanize_fn   = humanize,
      gate_fn       = GateLengthHumanizer.apply,
      key_root_midi = 60,
      key_scale     = 'major',
  )
  # events → List[Tuple[float, float, int, int]]
  # each tuple: (time_beats, dur_beats, midi_note, velocity)

  Returns [] when archetype is not a registered Billboard name (safe fallback).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple, Type

from src.composition.billboard.pedal_point             import PedalPoint
from src.composition.billboard.syncopated_anticipation import SyncopatedAnticipation
from src.composition.billboard.four_chord_loop         import FourChordLoop
from src.composition.billboard.inverted_filter_sweep   import InvertedFilterSweep


# ── Archetype name → class dispatch table ─────────────────────────────────────
# Each class exposes a generate() classmethod with a uniform signature.
_REGISTRY: Dict[str, Type] = {
    'pedal_point':             PedalPoint,
    'syncopated_anticipation': SyncopatedAnticipation,
    'four_chord_loop':         FourChordLoop,
    'inverted_filter_sweep':   InvertedFilterSweep,
}


class BillboardIntroMatrix:
    """
    Static dispatcher for the four commercially-proven Billboard intro archetypes.

    All generate() calls are class-level (no instance needed).  This keeps the
    registry stateless and safe for concurrent MIDI generation workers.
    """

    # Public set of registered archetype names — used by the registry to decide
    # whether to route an archetype here vs. the legacy per-genre modules.
    ARCHETYPE_NAMES: frozenset = frozenset(_REGISTRY.keys())

    @classmethod
    def generate(
        cls,
        archetype:     str,
        bar:           int,
        section_bars:  int,
        chord_notes:   List[int],
        beat_pos:      float,
        bar_vel:       int,
        h_amt:         float,
        humanize_fn:   Callable[[float, float], float],
        gate_fn:       Callable[[float], float],
        key_root_midi: int = 60,
        key_scale:     str = 'major',
    ) -> List[Tuple[float, float, int, int]]:
        """
        Dispatch to the named Billboard archetype and return event tuples.

        Parameters
        ----------
        archetype     : One of the registered Billboard archetype name strings.
        bar           : Current bar index within the intro section (0-based).
        section_bars  : Total bars in this intro section.
        chord_notes   : MIDI pitches from the composition engine's voice-leading.
        beat_pos      : Absolute beat position of this bar's downbeat.
        bar_vel       : Base velocity for this bar (already scaled by engine).
        h_amt         : Humanisation amount scalar (0.0 – 1.0).
        humanize_fn   : Callable(position, sigma) → jittered beat position.
        gate_fn       : Callable(duration) → humanised gate length.
        key_root_midi : MIDI tonic at octave 4 (e.g. 60 = C4).
                        Required by PedalPoint and FourChordLoop.
        key_scale     : 'major' or 'minor' — required by FourChordLoop.

        Returns
        -------
        List of (time_beats, dur_beats, midi_note, velocity) tuples, or []
        if the archetype name is not registered (safe no-op fallback).
        """

        archetype_cls = _REGISTRY.get(archetype)
        if archetype_cls is None:
            # Unknown archetype — return empty list so the engine's fallback runs.
            return []

        return archetype_cls.generate(
            bar           = bar,
            section_bars  = section_bars,
            chord_notes   = chord_notes,
            beat_pos      = beat_pos,
            bar_vel       = bar_vel,
            h_amt         = h_amt,
            humanize_fn   = humanize_fn,
            gate_fn       = gate_fn,
            key_root_midi = key_root_midi,
            key_scale     = key_scale,
        )

    @classmethod
    def is_billboard(cls, archetype: str) -> bool:
        """Return True iff *archetype* is a registered Billboard archetype name."""
        return archetype in cls.ARCHETYPE_NAMES
