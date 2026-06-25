"""
OmniLayerGenerator — Phase C2 orchestrator.

Produces tracks 07_Arp, 08_Stabs, 09_Texture, and 10_FX by delegating
to the four dedicated generators and returning a unified dict.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.patterns.euclidean_arp     import EuclideanArpGenerator
from src.generation.stab_engine     import StabEngine
from src.generation.texture_generator import TextureGenerator
from src.generation.fx_generator    import FXGenerator

NoteList = List[Tuple[float, float, int, int]]


class OmniLayerGenerator:
    """
    Orchestrates the four extra Omni tracks (07–10).

    All generator instances are reused across calls (stateless generators).
    """

    def __init__(self) -> None:
        self._arp     = EuclideanArpGenerator()
        self._stabs   = StabEngine()
        self._texture = TextureGenerator()
        self._fx      = FXGenerator()

    def generate(
        self,
        melody_notes:      NoteList,
        chord_progression: List[str],
        structure:         List[Tuple[str, int]],
        scale_notes:       List[int],
        genre:             str,
        chord_notes_fn,    # get_chord_midi_notes(root, quality, octave)
        parse_chord_fn,    # parse_chord_string(chord_str) → (root, quality)
        anchor_pitch:      int   = 60,
        arp_volume:        float = 0.5,
        stab_volume:       float = 0.8,
        texture_volume_ignored: float = 0.7,   # texture uses velocity-relative reduction
        fx_volume:         float = 0.9,
    ) -> Dict[str, NoteList]:
        """
        Returns
        -------
        {
            '07_Arp':     [...],
            '08_Stabs':   [...],
            '09_Texture': [...],
            '10_FX':      [...],
        }
        """
        arp = self._arp.generate(
            chord_progression = chord_progression,
            structure         = structure,
            chord_notes_fn    = chord_notes_fn,
            parse_chord_fn    = parse_chord_fn,
            volume            = arp_volume,
            genre             = genre,
        )

        stabs = self._stabs.generate(
            chord_progression = chord_progression,
            structure         = structure,
            chord_notes_fn    = chord_notes_fn,
            parse_chord_fn    = parse_chord_fn,
            volume            = stab_volume,
        )

        texture = self._texture.generate(
            melody_notes  = melody_notes,
            scale_notes   = scale_notes,
            anchor_pitch  = anchor_pitch,
        )

        fx = self._fx.generate(
            structure = structure,
            volume    = fx_volume,
        )

        return {
            "07_Arp":     arp,
            "08_Stabs":   stabs,
            "09_Texture": texture,
            "10_FX":      fx,
        }
