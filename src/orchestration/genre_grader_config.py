"""
genre_grader_config.py — Per-genre grader parameter presets.

Each GraderGenreConfig encodes the music-theory tolerances and penalty weights
appropriate for one genre.  The grader extracts `genre` from the track's
generation_params and calls get_grader_config() to obtain the correct preset.

Penalty budget for context:
    Scale Adherence     up to 40 pts  (weight varies per genre)
    Rhythmic Variance      20 pts  (CV target range varies)
    Chord Density          20 pts  (disabled for EDM; polyphony cap for Pop)
    Motif Repetition       25 pts  (bigram min-rep varies: 0.03 trap, 0.10 others)
    Melodic Range           5 pts  (guard, unchanged)
    God Mode bonus        +15 pts
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class GraderGenreConfig:
    # ── Penalty 1 — Scale Adherence ───────────────────────────────────────────
    scale_penalty_max: float = 35.0
    # Pop=40 (strict), House=30 (modal chromaticism OK), EDM/Trap/Hip-Hop=35

    # ── Penalty 2 — Rhythmic Variance ─────────────────────────────────────────
    rv_target_lo:  float = 0.01   # CV below this = metronomic / no groove
    rv_target_hi:  float = 2.00   # CV above this = chaotic
    rv_min_onsets: int   = 8      # skip check when melody is too sparse

    # ── Penalty 3 — Chord Density ─────────────────────────────────────────────
    low_pitch_threshold:   int  = 43    # MIDI pitch below which a note is "sub-bass"
    chord_density_disabled: bool = False  # True for EDM (supersaws require polyphony)
    max_chord_polyphony:   int  = 0     # 0 = no limit; Pop=4 (triad + 1 extension)

    # ── Penalty 4 — Motif Repetition ──────────────────────────────────────────
    motif_min_repetition: float = 0.03
    # Trap/HipHop = 0.03 (Markov chains explore; even 1 bigram repeat suffices)
    # Pop/House/EDM = 0.10 (verse-chorus / 4-bar loops must repeat bigrams)

    # ── God Mode Check 3 — Humanization Delta ─────────────────────────────────
    humanization_delta_target_ms:   float = 4.5
    humanization_delta_tolerance_ms: float = 1.5
    # Pop/EDM = 1.5 ms (quantized grid); House = 3.0 ms (swung groove)


# ── Per-genre presets ─────────────────────────────────────────────────────────

_CONFIGS: Dict[str, GraderGenreConfig] = {

    # Trap — sparse Phrygian/minor melodies, Markov-chain progressions, low voicings
    'trap': GraderGenreConfig(
        scale_penalty_max               = 35.0,
        rv_target_lo                    = 0.01,
        rv_target_hi                    = 2.00,
        rv_min_onsets                   = 8,
        low_pitch_threshold             = 43,
        motif_min_repetition            = 0.03,
        humanization_delta_target_ms    = 4.5,
        humanization_delta_tolerance_ms = 1.5,
    ),

    # Hip-Hop — similar to trap; slightly looser velocity, swung 16th feel
    'hiphop': GraderGenreConfig(
        scale_penalty_max               = 35.0,
        rv_target_lo                    = 0.01,
        rv_target_hi                    = 2.00,
        rv_min_onsets                   = 8,
        low_pitch_threshold             = 43,
        motif_min_repetition            = 0.03,
        humanization_delta_target_ms    = 4.5,
        humanization_delta_tolerance_ms = 1.5,
    ),

    # Pop — strict diatonic scale, vocal-friendly sparse chords, tight quantization
    'pop': GraderGenreConfig(
        scale_penalty_max               = 40.0,   # heavy: no dissonant non-chord tones
        rv_target_lo                    = 0.08,   # syncopated but quantized
        rv_target_hi                    = 1.50,
        rv_min_onsets                   = 8,
        low_pitch_threshold             = 43,
        max_chord_polyphony             = 4,      # triads + one extension max
        motif_min_repetition            = 0.10,   # verse-chorus must repeat bigrams
        humanization_delta_target_ms    = 1.5,    # heavily quantized
        humanization_delta_tolerance_ms = 1.0,
    ),

    # House — Dorian/Mixolydian chromaticism OK, swung 16th groove
    'house': GraderGenreConfig(
        scale_penalty_max               = 30.0,   # lighter: modal passing tones OK
        rv_target_lo                    = 0.05,
        rv_target_hi                    = 2.00,   # wide: swing raises CV naturally
        rv_min_onsets                   = 8,
        low_pitch_threshold             = 43,
        motif_min_repetition            = 0.10,   # 4-bar loops must repeat
        humanization_delta_target_ms    = 3.0,    # swung 16th-note push-pull
        humanization_delta_tolerance_ms = 1.5,
    ),

    # EDM — chord density disabled (supersaws), rigid 4-on-the-floor, 8-bar riser
    'edm': GraderGenreConfig(
        scale_penalty_max               = 35.0,
        rv_target_lo                    = 0.05,
        rv_target_hi                    = 2.00,
        rv_min_onsets                   = 8,
        low_pitch_threshold             = 43,
        chord_density_disabled          = True,   # supersaws need polyphony
        motif_min_repetition            = 0.10,   # riser/drop loops repeat
        humanization_delta_target_ms    = 1.5,    # rigid grid
        humanization_delta_tolerance_ms = 1.0,
    ),
}

# ── Alias table — normalise genre variants to canonical keys ──────────────────

_ALIASES: Dict[str, str] = {
    'phonk':     'trap',
    'jpop':      'pop',
    'dnb':       'edm',
    'techno':    'edm',
    'cinematic': 'pop',
    'ambient':   'house',
    'lofi':      'hiphop',
}

_DEFAULT = GraderGenreConfig()   # global fallback (uses dataclass defaults)


def get_grader_config(genre: str) -> GraderGenreConfig:
    """Return the GraderGenreConfig for *genre* with alias resolution and fallback."""
    key = genre.lower().strip()
    key = _ALIASES.get(key, key)
    return _CONFIGS.get(key, _DEFAULT)
