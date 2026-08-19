"""
src/midi/markov_harmony.py
──────────────────────────
Markov-chain chord-progression engine with voice-leading output.

The engine maintains an internal state machine over chord *degrees* within a
given mode/scale.  At each call to ``next_chord()`` it:

1. Consults the genre-specific transition matrix to stochastically select
   the next chord degree.
2. Resolves that degree to a set of scale intervals (chord quality is chosen
   from the mode's diatonic stack).
3. Delegates voice-leading to the existing ``VoiceLeadingEngine``, which
   guarantees minimal motion and no parallel fifths.
4. Optionally substitutes a modal-interchange chord from the genre profile
   (probability 0.15 when ``allow_interchange=True``).

Chord-degree conventions used throughout:
  - Degrees are Roman-numeral strings: "I", "ii", "iii", "IV", "V", "vi", "vii°",
    and flat-side variants: "bII", "bIII", "bVI", "bVII".
  - The ``_SEMITONE_OFFSETS`` table maps each label to its semitone above the root.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from src.utils.voice_leading import VoiceLeadingEngine
from src.composition.genre_constants import SCALE_INTERVALS, CHORD_INTERVALS

# Guard against circular-import situations for type hints only.
if TYPE_CHECKING:
    pass  # nothing circular here presently


# ---------------------------------------------------------------------------
# Semitone offset table for chord-degree labels
# ---------------------------------------------------------------------------

_SEMITONE_OFFSETS: Dict[str, int] = {
    "I":    0,  "i":   0,
    "bII":  1,
    "II":   2,  "ii":  2,
    "bIII": 3,  "iii": 4,
    "III":  4,
    "IV":   5,  "iv":  5,
    "#IV":  6,  "bV":  6,
    "V":    7,  "v":   7,
    "bVI":  8,  "vi":  9,
    "VI":   9,
    "bVII": 10, "vii": 11,
    "VII":  11,
}

# ---------------------------------------------------------------------------
# Diatonic quality tables
# Quality of the triad built on each scale degree (0-indexed) for common modes.
# Keys correspond to SCALE_INTERVALS keys; values are 7-element lists of
# CHORD_INTERVALS keys.
# ---------------------------------------------------------------------------

_DIATONIC_QUALITY: Dict[str, List[str]] = {
    "major":         ["major", "minor", "minor", "major", "major", "minor", "dim"],
    "natural_minor": ["minor", "dim",   "major", "minor", "minor", "major", "major"],
    "minor":         ["minor", "dim",   "major", "minor", "minor", "major", "major"],
    "dorian":        ["minor", "minor", "major", "major", "minor", "dim",   "major"],
    "phrygian":      ["minor", "major", "major", "minor", "dim",   "major", "minor"],
    "lydian":        ["major", "major", "minor", "dim",   "major", "minor", "minor"],
    "mixolydian":    ["major", "minor", "dim",   "major", "minor", "minor", "major"],
    "aeolian":       ["minor", "dim",   "major", "minor", "minor", "major", "major"],
    "locrian":       ["dim",   "major", "minor", "minor", "major", "major", "minor"],
    "phrygian_dominant": ["major", "major", "major", "minor", "dim", "major", "minor"],
    "harmonic_minor":    ["minor", "dim",   "major", "minor", "major", "major", "dim"],
    "diminished":        ["dim",   "dim",   "dim",   "dim",   "dim",  "dim",   "dim"],
    "chromatic":         ["major", "minor", "major", "minor", "major","minor", "dim"],
}

# ---------------------------------------------------------------------------
# Genre chord-degree Markov transition matrices
# Format: {from_degree: {to_degree: probability}}
# Probabilities in each row sum to 1.0.
# ---------------------------------------------------------------------------

_MARKOV_MATRICES: Dict[str, Dict[str, Dict[str, float]]] = {

    # ── Major-Pop (I IV V vi progressions, circle tendencies) ──────────────
    "major_pop": {
        "I":   {"IV": 0.35, "V": 0.30, "vi": 0.20, "ii": 0.15},
        "IV":  {"V": 0.45,  "I": 0.30, "ii": 0.15, "vi": 0.10},
        "V":   {"I": 0.55,  "vi": 0.25, "IV": 0.15, "ii": 0.05},
        "vi":  {"IV": 0.40, "II": 0.25, "V": 0.20,  "I": 0.15},
        "ii":  {"V": 0.55,  "IV": 0.25, "vi": 0.15, "I": 0.05},
        "iii": {"vi": 0.50, "IV": 0.30, "I": 0.20},
        "vii": {"I": 0.70,  "V": 0.20,  "iii": 0.10},
    },

    # ── Minor Hip-Hop (modal, flat-VII movements, tritone colour) ────────────
    "minor_hiphop": {
        "i":   {"bVII": 0.30, "iv": 0.25, "bVI": 0.25, "V": 0.20},
        "bVII":{"i": 0.40,   "bVI": 0.35, "iv": 0.25},
        "iv":  {"i": 0.35,   "bVII": 0.30, "V": 0.25,  "bVI": 0.10},
        "bVI": {"bVII": 0.45, "i": 0.30,  "iv": 0.25},
        "V":   {"i": 0.60,   "bVI": 0.25, "bVII": 0.15},
        "ii°": {"V": 0.70,   "i": 0.30},
    },

    # ── Phrygian Trap (dark modal, bII dominates, cluster feel) ──────────────
    "phrygian_trap": {
        "i":   {"bII": 0.45, "bVII": 0.30, "bVI": 0.25},
        "bII": {"i": 0.60,   "bVII": 0.40},
        "bVII":{"i": 0.50,   "bII": 0.30,  "bVI": 0.20},
        "bVI": {"bVII": 0.50,"i": 0.30,    "bII": 0.20},
        "V":   {"i": 0.80,   "bVII": 0.20},
    },

    # ── Dorian House (minor with raised 6th brightness, cyclic feel) ─────────
    "dorian_house": {
        "i":   {"IV": 0.35, "bVII": 0.30, "ii": 0.20, "V": 0.15},
        "IV":  {"i": 0.40,  "ii": 0.30,   "bVII": 0.30},
        "bVII":{"i": 0.45,  "IV": 0.35,   "ii": 0.20},
        "ii":  {"V": 0.45,  "i": 0.30,    "IV": 0.25},
        "V":   {"i": 0.65,  "IV": 0.25,   "bVII": 0.10},
        "vi":  {"ii": 0.50, "V": 0.30,    "IV": 0.20},
    },

    # ── Minor Techno (aeolian modal, hypnotic cyclic repetition) ─────────────
    "minor_techno": {
        "i":   {"bVI": 0.35, "bVII": 0.35, "iv": 0.20, "V": 0.10},
        "bVI": {"bVII": 0.50,"i": 0.30,    "iv": 0.20},
        "bVII":{"i": 0.50,   "bVI": 0.30,  "iv": 0.20},
        "iv":  {"i": 0.40,   "bVII": 0.35, "bVI": 0.25},
        "V":   {"i": 0.75,   "bVI": 0.25},
    },

    # ── Major J-Pop (bright, lots of VI, extended cadences) ──────────────────
    "major_jpop": {
        "I":   {"V": 0.30,  "vi": 0.30,  "IV": 0.25, "ii": 0.15},
        "V":   {"I": 0.45,  "vi": 0.30,  "iii": 0.15, "IV": 0.10},
        "vi":  {"ii": 0.35, "IV": 0.30,  "V": 0.25,   "I": 0.10},
        "IV":  {"V": 0.40,  "I": 0.30,   "ii": 0.20,  "vi": 0.10},
        "ii":  {"V": 0.55,  "IV": 0.25,  "vi": 0.20},
        "iii": {"vi": 0.55, "IV": 0.30,  "V": 0.15},
        "bVII":{"IV": 0.50, "I": 0.30,   "V": 0.20},
    },

    # ── Minor Cinematic (dramatic motion, augmented chords, chromaticism) ────
    "minor_cinematic": {
        "i":   {"bVI": 0.30, "iv": 0.25, "V": 0.25,  "bVII": 0.20},
        "bVI": {"bVII": 0.40,"V": 0.30,  "i": 0.30},
        "iv":  {"V": 0.40,   "i": 0.30,  "bVI": 0.30},
        "V":   {"i": 0.55,   "bVI": 0.25,"iv": 0.20},
        "bVII":{"bVI": 0.40, "i": 0.35,  "iv": 0.25},
        "ii°": {"V": 0.65,   "i": 0.35},
        "bII": {"i": 0.50,   "V": 0.30,  "iv": 0.20},
    },

    # ── Phrygian Phonk (dark, sparse, flat-II/flat-VII dominance) ────────────
    "phrygian_phonk": {
        "i":   {"bII": 0.40, "bVII": 0.35, "bVI": 0.25},
        "bII": {"i": 0.55,   "bVII": 0.30, "bVI": 0.15},
        "bVII":{"i": 0.50,   "bII": 0.30,  "bVI": 0.20},
        "bVI": {"i": 0.45,   "bII": 0.35,  "bVII": 0.20},
    },
}

# Map each genre string to its default matrix key.
_GENRE_TO_MATRIX: Dict[str, str] = {
    "pop":        "major_pop",
    "hiphop":     "minor_hiphop",
    "trap":       "phrygian_trap",
    "techno":     "minor_techno",
    "cinematic":  "minor_cinematic",
    "classical":  "major_pop",     # classical reuses major voice-leading matrix
    "jpop":       "major_jpop",
    "phonk":      "phrygian_phonk",
    "edm":        "major_pop",
    "house":      "dorian_house",
}

# Starting degree per matrix key (tonic).
_START_DEGREE: Dict[str, str] = {
    "major_pop":       "I",
    "minor_hiphop":    "i",
    "phrygian_trap":   "i",
    "dorian_house":    "i",
    "minor_techno":    "i",
    "major_jpop":      "I",
    "minor_cinematic": "i",
    "phrygian_phonk":  "i",
}


class MarkovHarmonyEngine:
    """
    Stateful Markov-chain chord generator with voice-led MIDI output.

    The engine tracks the *current degree* (e.g. ``"I"``, ``"bVII"``), resolves
    it to MIDI notes, and uses ``VoiceLeadingEngine`` to produce smooth chord
    transitions across successive calls to ``next_chord()``.

    Parameters
    ----------
    genre : str
        One of the 10 genre keys (pop, hiphop, trap, techno, cinematic,
        classical, jpop, phonk, edm, house).
    mode : str
        Scale mode key matching ``SCALE_INTERVALS`` (e.g. "dorian").
    root_midi : int
        MIDI note of the tonal centre.  Middle C = 60.
    n_voices : int
        Number of simultaneous voices (3 or 4).
    seed : int | None
        Random seed for reproducibility.
    """

    def __init__(
        self,
        genre: str,
        mode: str,
        root_midi: int,
        n_voices: int = 4,
        seed: Optional[int] = None,
    ) -> None:
        self._genre = genre
        self._mode = mode if mode in SCALE_INTERVALS else "major"
        self._root_midi = root_midi
        self._n_voices = n_voices

        # Select Markov matrix.
        matrix_key = _GENRE_TO_MATRIX.get(genre, "major_pop")
        self._matrix: Dict[str, Dict[str, float]] = _MARKOV_MATRICES[matrix_key]
        self._start_degree: str = _START_DEGREE.get(matrix_key, "I")
        self._current_degree: str = self._start_degree

        # Voice-leading engine (reused across calls).
        self._vl = VoiceLeadingEngine(voice_range=(36, 96))

        # Seed the internal RNG.
        self._rng = random.Random(seed)

        # Build the initial (tonic) voicing.
        self._current_voicing: List[int] = self._build_voicing(
            self._current_degree
        )

        # Cache modal interchange chords from profile if injected later.
        self._interchange_chords: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def next_chord(
        self, allow_interchange: bool = False
    ) -> Tuple[List[int], str]:
        """
        Advance the Markov chain and return the next voiced chord.

        Parameters
        ----------
        allow_interchange : bool
            When True, there is a 15 % chance of substituting a borrowed
            modal-interchange chord instead of the Markov-chosen degree.

        Returns
        -------
        (voicing, chord_label)
            ``voicing`` is a sorted list of MIDI notes (bass → soprano).
            ``chord_label`` is the Roman-numeral degree string.
        """
        # Step the Markov chain.
        next_degree = self._transition(self._current_degree)

        # Optional modal interchange substitution.
        if allow_interchange and self._interchange_chords:
            if self._rng.random() < 0.15:
                # Pick a random borrowed chord label from the list.
                next_degree = self._rng.choice(self._interchange_chords)

        # Build the voiced chord using voice-leading rules.
        intervals = self._degree_to_intervals(next_degree)
        root = self._degree_root_midi(next_degree)

        new_voicing = self._vl.lead(
            prev_voicing=self._current_voicing,
            next_intervals=intervals,
            next_root_midi=root,
            n_voices=self._n_voices,
        )

        # Advance internal state.
        self._current_degree = next_degree
        self._current_voicing = new_voicing

        return list(new_voicing), next_degree

    def reset(self) -> None:
        """Reset to the tonic voicing and starting degree."""
        self._current_degree = self._start_degree
        self._current_voicing = self._build_voicing(self._current_degree)

    def set_root(self, root_midi: int) -> None:
        """
        Modulate to a new root note.

        The current *degree* is preserved so the harmonic context carries over;
        only the absolute MIDI pitch of the root shifts.
        """
        self._root_midi = root_midi
        # Rebuild voicing at new root while keeping the same degree.
        self._current_voicing = self._build_voicing(self._current_degree)

    def set_interchange_chords(self, chords: List[str]) -> None:
        """Inject modal-interchange chord labels (from a GenreProfile)."""
        self._interchange_chords = list(chords)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(self, from_degree: str) -> str:
        """
        Sample the next chord degree from the Markov transition row.

        Falls back to the tonic degree when *from_degree* is not in the matrix
        (can happen with borrowed chords that are not matrix keys).
        """
        row = self._matrix.get(from_degree)
        if not row:
            # Fallback: from any unrecognised state, go back to the tonic.
            return self._start_degree

        # Weighted random choice from the probability dict.
        keys = list(row.keys())
        weights = [row[k] for k in keys]
        return self._rng.choices(keys, weights=weights, k=1)[0]

    def _degree_root_midi(self, degree: str) -> int:
        """
        Compute the MIDI note of the chord root for *degree* above self._root_midi.

        Uses _SEMITONE_OFFSETS, defaulting to 0 (tonic) for unrecognised labels.
        """
        offset = _SEMITONE_OFFSETS.get(degree, 0)
        return self._root_midi + offset

    def _degree_to_intervals(self, degree: str) -> List[int]:
        """
        Resolve a Roman-numeral degree to chord intervals (semitones above root).

        Strategy:
        1. Look up the scale for the current mode.
        2. Determine which diatonic scale step the degree corresponds to.
        3. Look up the diatonic chord quality for that step.
        4. Use CHORD_INTERVALS to get the interval list.

        For chromatic / borrowed degrees not in the diatonic table, fall back
        to a plain minor or major triad based on whether the degree is upper- or
        lower-case.
        """
        scale = SCALE_INTERVALS.get(self._mode, SCALE_INTERVALS["major"])
        quality_table = _DIATONIC_QUALITY.get(self._mode, _DIATONIC_QUALITY["major"])

        # Map degree to diatonic scale step index (0-based).
        step_map: Dict[str, int] = {
            "I": 0, "i": 0, "bII": 0, "II": 1, "ii": 1,
            "bIII": 2, "iii": 2, "III": 2, "IV": 3, "iv": 3,
            "bV": 4, "#IV": 4, "V": 4, "v": 4,
            "bVI": 5, "vi": 5, "VI": 5, "bVII": 6, "vii": 6, "VII": 6,
        }
        step_idx = step_map.get(degree)

        if step_idx is not None and step_idx < len(quality_table):
            quality = quality_table[step_idx]
            return list(CHORD_INTERVALS.get(quality, CHORD_INTERVALS["major"]))

        # Borrowed/chromatic degree: choose major for uppercase, minor for lower.
        if degree and degree[0].isupper():
            return list(CHORD_INTERVALS["major"])
        return list(CHORD_INTERVALS["minor"])

    def _build_voicing(self, degree: str) -> List[int]:
        """Build the initial root-position voicing for *degree*."""
        intervals = self._degree_to_intervals(degree)
        root = self._degree_root_midi(degree)
        return self._vl._root_position(root, intervals, self._n_voices)
