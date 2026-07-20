"""
voice_leading.py -- Algorithmic Voice Leading Engine for 05_Chords and 06_Pad.

Classical Music Theory Context:
    Voice leading is the craft of moving between chords such that each individual
    pitch (voice) travels the SHORTEST possible distance to its counterpart in the
    next chord.  Smooth voice leading is what separates amateur MIDI from
    professional-quality harmonic writing.

    The Three Laws of Voice Leading (implemented here):
    -------------------------------------------------------
    LAW 1 -- MINIMAL MOTION
        Each voice should move to the nearest available note in the next chord.
        We minimize total displacement:

            cost = sum( |new_voice[i] - prev_voice[i]| )  for i in voices

    LAW 2 -- NO PARALLEL FIFTHS (Parallel Perfect Fifth Rule)
        Two voices must not BOTH move by a perfect fifth in the SAME direction.
        This was codified in Renaissance counterpoint and remains valid in all
        Western harmonic traditions.

        Detection:
            For voices A and B:
                parallel = (
                    (prev_B - prev_A) % 12 == 7    # fifth in old chord
                    AND (new_B - new_A) % 12 == 7  # fifth in new chord
                    AND (new_A - prev_A) != 0       # voice A actually moved
                    AND sign(new_A - prev_A) == sign(new_B - prev_B)  # same direction
                )

    LAW 3 -- NO VOICE CROSSING
        The relative ordering of voices must be maintained.
        If voice A was above voice B in chord 1, it must remain above in chord 2.
        Crossing creates auditory confusion (the ear loses track of voice identities).

Algorithm:
    1. Take prev_voicing: sorted list of MIDI notes (ascending = bass to soprano).
    2. Generate all candidate voicings of the next chord:
           - Root position and all inversions across the target octave range
           - Each candidate matches the number of voices in prev_voicing
    3. For each candidate:
           a. Compute displacement cost (LAW 1)
           b. Add large penalty for any parallel fifth pair (LAW 2)
           c. Add crossing penalty if voices re-order (LAW 3)
    4. Return the minimum-cost candidate voicing.

Performance:
    For 3-voice chords: 3 inversions × 3 voices = O(9) per chord transition.
    For 4-voice chords: 4 inversions × 4 voices = O(16) per chord transition.
    Negligible overhead per MIDI generation call.
"""

from __future__ import annotations
import itertools
from typing import List, Optional, Tuple

# Penalty added to cost for each parallel fifth pair detected.
# Must be large enough to outweigh savings from minimal motion.
PARALLEL_FIFTH_PENALTY = 48   # semitones -- equivalent to jumping 4 octaves

# Penalty for each voice crossing
CROSSING_PENALTY = 24   # semitones

# Penalty for leaps larger than a major 6th (9 semitones)
LEAP_PENALTY = 4        # per semitone above 9 (tapers large jumps)

# Perfect fifth interval class in semitones
PERFECT_FIFTH = 7


class VoiceLeadingEngine:
    """
    Computes the optimal MIDI voicing for a new chord given the previous voicing,
    minimizing voice movement while obeying classical counterpoint rules.

    Usage:
        engine = VoiceLeadingEngine()
        prev   = [48, 52, 55]          # C3-E3-G3 (C major root position)
        next   = [45, 48, 52]          # A2-C3-E3 candidate (Am first inversion)
        result = engine.lead(prev, next_chord_intervals=[0, 3, 7], root_midi=57)
        # result: optimal voice-led Am voicing
    """

    def __init__(self, voice_range: Tuple[int, int] = (36, 96)):
        """
        Parameters
        ----------
        voice_range : (min_midi, max_midi) hard limits for any generated note.
                      Default C2 (36) to C7 (96).
        """
        self.voice_min = voice_range[0]
        self.voice_max = voice_range[1]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def lead(
        self,
        prev_voicing:      List[int],
        next_intervals:    List[int],
        next_root_midi:    int,
        n_voices:          Optional[int] = None,
    ) -> List[int]:
        """
        Return the optimal voice-leading of next_intervals from prev_voicing.

        Parameters
        ----------
        prev_voicing     : Previous chord as sorted MIDI notes (bass → soprano).
        next_intervals   : Semitone intervals above next_root_midi (e.g. [0,4,7]).
        next_root_midi   : MIDI note of the chord root for the next chord.
        n_voices         : Number of voices to output. Defaults to len(prev_voicing).

        Returns
        -------
        Sorted list of MIDI notes (ascending) for the optimally voice-led chord.
        """
        if not prev_voicing or not next_intervals:
            # Nothing to lead from/to -- return root position
            return self._root_position(next_root_midi, next_intervals, n_voices or 3)

        n = n_voices or len(prev_voicing)

        # Generate candidate voicings centered on the previous voicing
        candidates = self._generate_candidates(next_root_midi, next_intervals, n,
                                               prev_voicing=prev_voicing)

        if not candidates:
            return self._root_position(next_root_midi, next_intervals, n)

        # Score each candidate and pick the minimum-cost one
        best_voicing = min(candidates, key=lambda c: self._cost(prev_voicing, c))
        return best_voicing

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------

    def _generate_candidates(
        self,
        root_midi:    int,
        intervals:    List[int],
        n_voices:     int,
        prev_voicing: Optional[List[int]] = None,
    ) -> List[List[int]]:
        """
        Generate valid chord voicings centred on the previous voicing.

        Performance fix:
            The naive approach -- itertools.combinations over the full voice range --
            produces C(pool, n_voices) candidates.  For extended chords (dom9 = 5
            pitch classes) with n_voices=5 across a 60-semitone range the pool can
            reach 25+ notes, giving C(25,5) = 53,130 candidates × 64 events/song =
            3.4 million cost calculations per composition.  That causes the hang.

            Fix: when prev_voicing is known, restrict the pool to a ±18-semitone
            window centred on the previous voicing's midpoint.  If the pool is still
            larger than _POOL_CAP (16) after windowing, keep only the 16 notes
            nearest to the midpoint.

            Worst case after fix: C(16, 5) = 4,368 -- instant.
            Musical quality is preserved: voice leading only needs candidates that
            are CLOSE to the previous voicing, not notes 3 octaves away.
        """
        _POOL_CAP = 16   # hard upper limit on pool size (C(16,5)=4368 -- safe)

        pitch_class_set = {(root_midi + i) % 12 for i in intervals}

        # Determine search window centred on previous voicing
        if prev_voicing:
            center     = sum(prev_voicing) // len(prev_voicing)
            search_min = max(self.voice_min, center - 18)
            search_max = min(self.voice_max, center + 18)
        else:
            center     = root_midi + 12
            search_min = self.voice_min
            search_max = self.voice_max

        pool = [m for m in range(search_min, search_max + 1)
                if m % 12 in pitch_class_set]

        # Expand to full range if the window was too narrow
        if len(pool) < n_voices:
            pool = [m for m in range(self.voice_min, self.voice_max + 1)
                    if m % 12 in pitch_class_set]

        # Cap pool size: keep notes nearest to center (prevents combinatorial blow-up)
        if len(pool) > _POOL_CAP:
            pool = sorted(pool, key=lambda x: abs(x - center))[:_POOL_CAP]
            pool.sort()

        if len(pool) < n_voices:
            return []

        # Generate combinations within span / spread constraints
        candidates = []
        for combo in itertools.combinations(pool, n_voices):
            voicing = list(combo)
            if voicing[-1] - voicing[0] > 24:   # reject span > 2 octaves
                continue
            if n_voices > 2 and voicing[-1] - voicing[0] < 4:   # reject too clustered
                continue
            candidates.append(voicing)

        return candidates

    def _root_position(self, root_midi: int,
                        intervals: List[int], n_voices: int) -> List[int]:
        """Fallback: build root-position voicing with n_voices notes."""
        notes = [root_midi + i for i in intervals]
        # Trim or pad to n_voices
        while len(notes) < n_voices:
            notes.append(notes[-1] + 12)   # double in higher octave
        notes = notes[:n_voices]
        return sorted(max(self.voice_min, min(self.voice_max, n)) for n in notes)

    # ------------------------------------------------------------------
    # Cost function
    # ------------------------------------------------------------------

    def _cost(self, prev: List[int], candidate: List[int]) -> float:
        """
        Compute the total voice-leading cost from prev to candidate.

        Cost = displacement + parallel_fifth_penalty + crossing_penalty + leap_penalty
        """
        n = min(len(prev), len(candidate))
        prev_c = prev[:n]
        cand_c = candidate[:n]

        # LAW 1 -- Displacement cost
        displacement = sum(abs(cand_c[i] - prev_c[i]) for i in range(n))

        # LAW 2 -- Parallel fifth penalty
        p5_penalty = 0
        for i in range(n):
            for j in range(i + 1, n):
                if self._is_parallel_fifth(prev_c[i], prev_c[j], cand_c[i], cand_c[j]):
                    p5_penalty += PARALLEL_FIFTH_PENALTY

        # LAW 3 -- Voice crossing penalty
        crossing_penalty = 0
        for i in range(n - 1):
            if cand_c[i] > cand_c[i + 1]:
                crossing_penalty += CROSSING_PENALTY

        # Leap penalty -- large jumps (> major 6th = 9 semitones) are penalized
        leap_penalty = 0
        for i in range(n):
            jump = abs(cand_c[i] - prev_c[i])
            if jump > 9:
                leap_penalty += (jump - 9) * LEAP_PENALTY

        return displacement + p5_penalty + crossing_penalty + leap_penalty

    @staticmethod
    def _is_parallel_fifth(
        prev_lo: int, prev_hi: int,
        new_lo:  int, new_hi:  int,
    ) -> bool:
        """
        Return True if the interval between two voices is a perfect fifth in
        BOTH the previous chord AND the next chord, with both voices moving
        in the same direction (parallel, not oblique or contrary).

        Parameters
        ----------
        prev_lo, prev_hi : lower and higher voice in the PREVIOUS chord
        new_lo,  new_hi  : lower and higher voice in the NEXT chord
        """
        prev_interval = (prev_hi - prev_lo) % 12
        new_interval  = (new_hi  - new_lo)  % 12

        if prev_interval != PERFECT_FIFTH or new_interval != PERFECT_FIFTH:
            return False   # not both fifths

        # Check for oblique motion (one voice stays stationary) -- allowed
        if prev_lo == new_lo or prev_hi == new_hi:
            return False

        # Both moved in the same direction?
        lo_dir = new_lo - prev_lo
        hi_dir = new_hi - prev_hi
        return (lo_dir > 0 and hi_dir > 0) or (lo_dir < 0 and hi_dir < 0)


# ---------------------------------------------------------------------------
# Standalone helper: score a single transition
# ---------------------------------------------------------------------------

def voice_leading_distance(voicing_a: List[int], voicing_b: List[int]) -> int:
    """
    Return the total semitone displacement between two equally-sized voicings.

    Used by pad.py and chords.py to quickly check if a candidate voicing
    is smoother than the previous best without building a full engine instance.
    """
    n = min(len(voicing_a), len(voicing_b))
    return sum(abs(voicing_b[i] - voicing_a[i]) for i in range(n))
