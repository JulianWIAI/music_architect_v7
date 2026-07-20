"""
intro_archetype_registry.py — Central registry mapping genre -> intro archetypes.

Two tiers of archetypes are registered here:

  Tier 1 — Legacy genre-specific archetypes (dispatched by genre module):
    pop   → pop_archetypes.py   (piano_staccato, pluck_arpeggio, atmospheric_pad)
    house → house_archetypes.py (lpf_bass_groove, percussive_build, chord_stab)
    edm   → edm_archetypes.py   (filter_sweep, mono_pluck, impact_drone)

  Tier 2 — Billboard archetypes (dispatched by archetype name, cross-genre):
    pedal_point             → billboard/pedal_point.py             (Pop, EDM, Trap, Hip-Hop)
    syncopated_anticipation → billboard/syncopated_anticipation.py (all genres)
    four_chord_loop         → billboard/four_chord_loop.py         (Pop only)
    inverted_filter_sweep   → billboard/inverted_filter_sweep.py   (EDM, House)

Genres not listed in GENRE_ARCHETYPES (phonk, cinematic aliases, …) return
None from get_archetypes() and None from generate_events(), signalling
composition_engine.py to use its built-in staccato/atmospheric/arpeggio logic.

Dispatch order in generate_events()
-------------------------------------
1. If archetype name is a Billboard archetype → route to BillboardIntroMatrix.
2. Otherwise find the genre's legacy module and call module.generate(archetype, ...).
3. If neither matches → return None (built-in fallback).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from src.composition import pop_archetypes
from src.composition import house_archetypes
from src.composition import edm_archetypes

# Billboard archetypes imported lazily inside generate_events() to avoid a
# circular import if composition_engine ever imports this module at module level.
# The BillboardIntroMatrix import is deferred to the first generate_events() call.
_billboard_matrix = None


def _get_billboard():
    """Lazy-import BillboardIntroMatrix (avoids circular import at load time)."""
    global _billboard_matrix
    if _billboard_matrix is None:
        from src.generators.intro import BillboardIntroMatrix
        _billboard_matrix = BillboardIntroMatrix
    return _billboard_matrix


# ── Genre -> ordered archetype name tuples ────────────────────────────────────
# Tier 1 legacy names come first; Billboard names follow.
# The engine draws randomly from the full pool on each 80% variety trigger.

GENRE_ARCHETYPES: Dict[str, Tuple[str, ...]] = {
    'pop':    (
        'piano_staccato',
        'pluck_arpeggio',
        'atmospheric_pad',
        'pedal_point',             # Billboard Tier 2
        'four_chord_loop',         # Billboard Tier 2
        'syncopated_anticipation', # Billboard Tier 2
    ),
    'house':  (
        'lpf_bass_groove',
        'percussive_build',
        'chord_stab',
        'syncopated_anticipation', # Billboard Tier 2
        'inverted_filter_sweep',   # Billboard Tier 2
    ),
    'edm':    (
        'filter_sweep',
        'mono_pluck',
        'impact_drone',
        'pedal_point',             # Billboard Tier 2
        'inverted_filter_sweep',   # Billboard Tier 2
        'syncopated_anticipation', # Billboard Tier 2
    ),
    # Trap and Hip-Hop previously used built-in fallback for all intro bars.
    # Billboard archetypes are now available to them via Tier 2 dispatch.
    'trap':   (
        'syncopated_anticipation', # natural groove for trap
        'pedal_point',             # low tonic anchor over hi-hats
    ),
    'hiphop': (
        'syncopated_anticipation',
        'pedal_point',
    ),
}

# ── Alias normalisation ───────────────────────────────────────────────────────
_ALIASES: Dict[str, str] = {
    'jpop':      'pop',
    'cinematic': 'pop',
    'techno':    'edm',
    'dnb':       'edm',
    'ambient':   'house',
    'hip-hop':   'hiphop',
    'hip_hop':   'hiphop',
}

# ── Tier 1: legacy genre module dispatch ──────────────────────────────────────
_LEGACY_DISPATCH: Dict[str, Callable] = {
    'pop':   pop_archetypes.generate,
    'house': house_archetypes.generate,
    'edm':   edm_archetypes.generate,
}

# ── Tier 2: Billboard archetype name set ──────────────────────────────────────
# These names bypass the per-genre module and go to BillboardIntroMatrix.
_BILLBOARD_NAMES: frozenset = frozenset({
    'pedal_point',
    'syncopated_anticipation',
    'four_chord_loop',
    'inverted_filter_sweep',
})


def _resolve(genre: str) -> str:
    """Normalise genre string to canonical key (lower-cased, aliased)."""
    key = genre.lower().strip()
    return _ALIASES.get(key, key)


def get_archetypes(genre: str) -> Optional[Tuple[str, ...]]:
    """
    Return the archetype name tuple for *genre*, or None if the genre uses
    composition_engine built-in archetypes (staccato / atmospheric / arpeggio).
    """
    return GENRE_ARCHETYPES.get(_resolve(genre))


def generate_events(
    genre:        str,
    archetype:    str,
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
) -> Optional[List[Tuple[float, float, int, int]]]:
    """
    Dispatch to the correct archetype generator and return event tuples.

    Dispatch priority
    -----------------
    1. Billboard Tier 2: if *archetype* is a Billboard name → BillboardIntroMatrix.
    2. Legacy Tier 1:    if resolved *genre* has a legacy module → module.generate().
    3. No match:         return None → engine uses built-in fallback.

    Parameters
    ----------
    genre         : Genre string from CompositionConfig (e.g. 'trap', 'pop').
    archetype     : Archetype name string selected by the engine.
    bar           : Current bar index in the intro section (0-based).
    section_bars  : Total bars in this intro section.
    chord_notes   : MIDI pitches from the engine's voice-leading.
    beat_pos      : Absolute beat position of this bar's downbeat.
    bar_vel       : Base velocity for this bar.
    h_amt         : Humanisation amount scalar (0.0 – 1.0).
    humanize_fn   : Callable(position, sigma) → jittered beat position.
    gate_fn       : Callable(duration) → humanised gate length.
    key_root_midi : MIDI tonic at octave 4. Required by Billboard archetypes.
    key_scale     : 'major' or 'minor'. Required by FourChordLoop.

    Returns
    -------
    List of (time_beats, dur_beats, midi_note, velocity) tuples, or None if
    the genre/archetype combination has no registered handler.
    """

    # ── Tier 2: Billboard dispatch (archetype-name based, cross-genre) ─────────
    if archetype in _BILLBOARD_NAMES:
        matrix = _get_billboard()
        return matrix.generate(
            archetype     = archetype,
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

    # ── Tier 1: Legacy per-genre dispatch ──────────────────────────────────────
    resolved = _resolve(genre)
    fn = _LEGACY_DISPATCH.get(resolved)
    if fn is None:
        # Genre has no legacy module (trap/hiphop without Billboard names → built-in).
        return None

    return fn(
        archetype    = archetype,
        bar          = bar,
        section_bars = section_bars,
        chord_notes  = chord_notes,
        beat_pos     = beat_pos,
        bar_vel      = bar_vel,
        h_amt        = h_amt,
        humanize_fn  = humanize_fn,
        gate_fn      = gate_fn,
    )
