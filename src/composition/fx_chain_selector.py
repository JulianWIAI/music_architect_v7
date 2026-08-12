"""
src.composition.fx_chain_selector
-----------------------------------
Three-layer FX chain variant system.

Scientific foundation
---------------------
FX chain variants are grounded in three independent psychoacoustic axes:

  BRIGHT  — elevated air shelf (+2-4 dB @ 8-12 kHz per Fletcher-Munson
             equal-loudness model), shorter reverb pre-delay (transient
             clarity), higher reverb HPF (brighter room tail).

  NEUTRAL — the genre JSON is the reference; no overlay applied.

  DARK    — tape saturation drive +2-5 dB (2nd/3rd harmonic density =
             perceived warmth, Huber & Runstein "Modern Recording" §12),
             longer reverb decay (Haas-effect threshold exceeded →
             perceived depth), lower reverb HPF (darker room).

Instrument-aware adjustments (layer 3) are triggered by the GM program
number assigned to each track.  The adjustments are justified by:

  • Harmonic density:  Sawtooth/square leads already contain all harmonics
    → adding reverb/saturation causes inter-harmonic distortion products
    (BDRA P4 density principle).

  • Envelope matching: Pads (BDRA A=3, attack >100ms) need longer reverb
    to fill the slow onset; fast brass (A=0-1) needs shorter pre-delay.

  • Timbre complementarity: Electric piano overtones above 8 kHz are
    removed by tape HF roll-off → tube saturation is the historically
    correct choice (EMT 140 plate + Fender tube amp = classic Rhodes sound).

  • Formant protection: Choir voices have F1-F2 formants in 200-2500 Hz;
    ping-pong delay comb-filters this range → swap to mono single-tap.

Public API
----------
FxChainSelector.load()
    Load fx_variants.json once; cache the result.

FxChainSelector.select_variant_id(genre, seed) → str
    Deterministic variant selection: 'bright', 'neutral', or 'dark'.
    Rotates based on seed so different compositions get different flavors.

FxChainSelector.get_variant(genre, variant_id) → dict
    Returns the full variant record (id, label, description, chain_overlay).

FxChainSelector.get_instrument_adjustment(genre, track, gm_program) → list
    Returns chain_delta entries for the instrument class occupying *track*.
    Returns [] when no matching class is found.

FxChainSelector.merge_deltas(*deltas) → dict
    Merge multiple chain_delta dicts with later entries overriding earlier
    for the same track+slot.  Priority: instrument > variant > palette.
"""

from __future__ import annotations

import json
import pathlib
from typing import Dict, List, Optional

# ── Data file path ────────────────────────────────────────────────────────────

_DATA_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "data" / "production_guide" / "json" / "fx_variants.json"
)

# ── Cached data ───────────────────────────────────────────────────────────────

_DATA: Optional[dict] = None


def _load() -> dict:
    """Load fx_variants.json once and cache it in module scope."""
    global _DATA
    if _DATA is None:
        _DATA = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return _DATA


# ── Variant rotation order ────────────────────────────────────────────────────
# Using seed % 3 gives an even distribution: 0=bright, 1=neutral, 2=dark.
# The order is intentional: neutral is most common (index 1 = ~33 % of seeds)
# but each variant occurs with equal frequency over a large seed set.
_VARIANT_ORDER = ["bright", "neutral", "dark"]


class FxChainSelector:
    """
    Stateless utility class for the three-layer FX chain variant system.

    All methods are class methods — no instantiation needed.
    """

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    @classmethod
    def load(cls) -> dict:
        """Return the loaded fx_variants.json data (cached after first call)."""
        return _load()

    @classmethod
    def get_all_variants(cls, genre: str) -> List[dict]:
        """
        Return all three variant records for *genre*.

        Each record has keys: id, label, description, chain_overlay.
        Returns empty list when the genre is not in the data file.
        """
        data = _load()
        return data.get("variants", {}).get(genre, [])

    @classmethod
    def get_variant(cls, genre: str, variant_id: str) -> dict:
        """
        Return the variant record for *genre* + *variant_id*.

        Falls back to the neutral record (empty overlay) if the combination
        is not found, so callers never need to guard against missing data.
        """
        for v in cls.get_all_variants(genre):
            if v["id"] == variant_id:
                return v
        # Neutral fallback — safe no-op
        return {"id": "neutral", "label": "NEUTRAL",
                "description": "Genre reference", "chain_overlay": {}}

    # ------------------------------------------------------------------
    # Deterministic variant selection
    # ------------------------------------------------------------------

    @classmethod
    def select_variant_id(cls, genre: str, seed: int) -> str:
        """
        Pick a variant id deterministically from the composition seed.

        Same seed → same variant every time, ensuring the advisor preview
        matches the generated song.  Different seeds → different flavor.

        The modulo is over 3 (bright / neutral / dark), so the distribution
        is perfectly even across any range of consecutive seeds.
        """
        return _VARIANT_ORDER[seed % len(_VARIANT_ORDER)]

    # ------------------------------------------------------------------
    # Instrument-aware adjustment lookup
    # ------------------------------------------------------------------

    @classmethod
    def get_instrument_adjustment(
        cls,
        track: str,
        gm_program: int,
    ) -> List[dict]:
        """
        Return instrument-class chain_delta entries for *track* and *gm_program*.

        Iterates instrument_classes in fx_variants.json to find a class
        whose gm_range covers *gm_program*, then returns that class's
        per-track delta for *track*.

        Returns an empty list when:
          • no instrument class covers *gm_program*
          • the matching class has no adjustment for *track*
        """
        data = _load()
        for cls_def in data.get("instrument_classes", []):
            lo, hi = cls_def["gm_range"]
            if lo <= gm_program <= hi:
                # Found the matching instrument class
                return cls_def.get("tracks", {}).get(track, [])
        return []

    @classmethod
    def classify_instrument(cls, gm_program: int) -> Optional[dict]:
        """
        Return the instrument class record for *gm_program*, or None.

        Useful for displaying which class is active in the UI.
        """
        data = _load()
        for cls_def in data.get("instrument_classes", []):
            lo, hi = cls_def["gm_range"]
            if lo <= gm_program <= hi:
                return cls_def
        return None

    # ------------------------------------------------------------------
    # Delta merging
    # ------------------------------------------------------------------

    @classmethod
    def merge_deltas(cls, *deltas: dict) -> dict:
        """
        Merge multiple chain_delta dicts into one.

        Format of each delta: {track_name: [{slot, action, …}, …]}

        For the same track+slot, **later** deltas override earlier ones.
        This implements the priority stack:
            palette delta (lowest) → variant delta → instrument delta (highest)

        Returns a new dict in the same format.
        """
        merged: Dict[str, Dict[int, dict]] = {}

        for delta in deltas:
            for track, entries in delta.items():
                if track not in merged:
                    merged[track] = {}
                for entry in entries:
                    slot = entry.get("slot", 0)
                    # Later delta wins — instrument adjustments override variants
                    merged[track][slot] = entry

        # Convert slot-keyed inner dicts back to ordered lists
        return {
            track: sorted(slots.values(), key=lambda e: e.get("slot", 0))
            for track, slots in merged.items()
        }

    # ------------------------------------------------------------------
    # Convenience: build full merged delta for a composition
    # ------------------------------------------------------------------

    @classmethod
    def build_merged_delta(
        cls,
        genre: str,
        variant_id: str,
        palette_delta: dict,
        track_instruments: Dict[str, int],
    ) -> dict:
        """
        Build the complete merged chain_delta for the advisor to display.

        Parameters
        ----------
        genre : str
            The current genre (e.g. 'pop').
        variant_id : str
            'bright', 'neutral', or 'dark'.
        palette_delta : dict
            The chain_delta from the currently selected instrument palette.
            May be empty ({}).
        track_instruments : dict
            Maps track name → GM program number for each active track.
            e.g. {'melody': 81, 'pads': 88, 'bass': 38, …}

        Returns
        -------
        dict  — merged chain_delta combining palette + variant + instrument
                adjustments.  Same format as chain_delta in instrument_palettes.json.
        """
        # Layer 2: variant overlay
        variant_delta = cls.get_variant(genre, variant_id).get("chain_overlay", {})

        # Layer 3: per-track instrument adjustments
        inst_delta: dict = {}
        for track, gm_program in track_instruments.items():
            if gm_program is None:
                continue
            adj = cls.get_instrument_adjustment(track, gm_program)
            if adj:
                inst_delta[track] = adj

        # Merge in priority order: palette (base) → variant → instrument (top)
        return cls.merge_deltas(palette_delta, variant_delta, inst_delta)
