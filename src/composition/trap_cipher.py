"""
trap_cipher.py — Five genre-defining production ciphers for Trap and Hip-Hop.

Each cipher is a stateless class with a class-method entry point so it can
be called from composition_engine.py with zero instance management overhead.

  HiHatRatchetEngine       maybe_roll(bar_idx, beat_pos, bpm) -> List[Note]
  EightOhEightGlider       apply(notes, bpm) -> List[Note]
  EightOhEightOctaveLeap   maybe_hit(root_midi, bar_beat_pos, bpm) -> Optional[Note]
  SilenceMatrix            compute_zones(total_bars, seed) -> Dict[int, float]
                           apply(notes, drop_zones, bar_beats=4.0) -> List[Note]
  AuxPercussionLayer       generate(beat_pos, occupied_steps, bpm) -> List[Note]

Note alias: Tuple[float, float, int, int] = (time_beats, duration_beats, midi_note, velocity)
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Set, Tuple

from src.composition.genre_constants import (
    HIHAT_CLOSED, HIHAT_OPEN, RIMSHOT, CLAP,
)

# ─────────────────────────────────────────────────────────────────────────────
#  1 · HI-HAT RATCHET ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class HiHatRatchetEngine:
    """
    Probabilistic hi-hat ratchet roll injected at the end of 2-bar and
    4-bar phrase boundaries.

    When triggered, the last 0.5–1.5 beats of the bar are replaced with a
    dense roll of 32nd notes, 64th notes, or 8th-note triplets.  Every note
    in the roll receives a linearly-ramped velocity — either swelling up
    (60 → 110) or sweeping down (110 → 60) — creating the modern bounce
    heard on commercial trap productions.

    Trigger probability: 17.5% (midpoint of 15–20%) at every 2-bar boundary,
    independent of the 4-bar boundary check.
    """

    PROB       = 0.175    # 17.5% — midpoint of required 15-20%
    VEL_LO    = 60
    VEL_HI    = 110

    # (label, step_size_in_beats)
    _ROLL_TYPES: Tuple[Tuple[str, float], ...] = (
        ('32nd',    0.125),          # 8 notes per beat
        ('64th',    0.0625),         # 16 notes per beat
        ('triplet', 1.0 / 3.0),     # 3 notes per beat (8th-note triplet)
    )
    _ROLL_DURATIONS = (0.5, 1.0, 1.5)   # beats the roll occupies

    @classmethod
    def maybe_roll(cls, bar_idx: int, bar_beat_pos: float,
                   bpm: float) -> List[Tuple[float, float, int, int]]:
        """
        Return ratchet notes for this bar, or an empty list.

        Triggers at the end of every 2-bar boundary (bar_idx % 2 == 1)
        and every 4-bar boundary (bar_idx % 4 == 3).
        The 4-bar boundary has an independent 2nd roll chance, so densely
        spaced 4-bar endings can receive double-wide ratchets.

        Args:
            bar_idx      : absolute bar number (0-based) across the track
            bar_beat_pos : beat position of this bar's downbeat
            bpm          : tempo — used for micro-jitter in beat-seconds
        """
        at_2bar = (bar_idx % 2 == 1)
        at_4bar = (bar_idx % 4 == 3)

        if not (at_2bar or at_4bar):
            return []
        if random.random() >= cls.PROB:
            return []

        _, step      = random.choice(cls._ROLL_TYPES)
        roll_beats   = random.choice(cls._ROLL_DURATIONS)
        roll_start   = bar_beat_pos + (4.0 - roll_beats)
        total_notes  = max(2, min(32, int(roll_beats / step)))

        swell_up     = random.random() < 0.5
        notes: List[Tuple[float, float, int, int]] = []

        for i in range(total_notes):
            pct = i / max(1, total_notes - 1)
            vel = (int(cls.VEL_LO + (cls.VEL_HI - cls.VEL_LO) * pct)
                   if swell_up
                   else int(cls.VEL_HI - (cls.VEL_HI - cls.VEL_LO) * pct))
            vel = max(20, min(127, vel))

            # Crown the swell with an open hat; sweeps close on a closed hat
            hat = (HIHAT_OPEN
                   if swell_up and i == total_notes - 1
                   else HIHAT_CLOSED)

            t      = roll_start + i * step
            jitter = random.uniform(-0.002, 0.002)
            notes.append((t + jitter, step * 0.85, hat, vel))

        return notes


# ─────────────────────────────────────────────────────────────────────────────
#  2 · 808 GLIDE TRIGGER (BASS LEGATO)
# ─────────────────────────────────────────────────────────────────────────────

class EightOhEightGlider:
    """
    Extends the duration of an 808 note so it overlaps the following note
    by 30–50 ms, triggering the portamento "slide" in downstream DAW samplers.

    This replicates the Legato mode used by producers in Kontakt 808 packs,
    Native Instruments Massive, and hardware Roland TR samplers: if a new
    note triggers while the previous note is still sounding, the sampler
    glides pitch instead of re-triggering the envelope.

    Trigger probability: 12.5% (midpoint of 10–15%) per consecutive
    pitch-change pair.  Same-pitch repetitions are intentionally excluded.
    """

    PROB          = 0.125    # 12.5%
    OVERLAP_MS_LO = 30.0     # milliseconds
    OVERLAP_MS_HI = 50.0     # milliseconds

    @classmethod
    def apply(cls, notes: List[Tuple[float, float, int, int]],
              bpm: float) -> List[Tuple[float, float, int, int]]:
        """
        Post-process a bass note list, extending durations for legato glides.

        Args:
            notes : (time, duration, pitch, velocity) list
            bpm   : track tempo in BPM
        Returns sorted list with some durations extended.
        """
        if len(notes) < 2:
            return notes

        ms_per_beat = 60_000.0 / max(bpm, 1.0)
        result      = [list(n) for n in sorted(notes, key=lambda x: x[0])]

        for i in range(len(result) - 1):
            curr_pitch = result[i][2]
            next_pitch = result[i + 1][2]

            if curr_pitch == next_pitch:
                continue                   # same pitch — no glide needed
            if random.random() >= cls.PROB:
                continue

            overlap_ms    = random.uniform(cls.OVERLAP_MS_LO, cls.OVERLAP_MS_HI)
            overlap_beats = overlap_ms / ms_per_beat
            next_start    = result[i + 1][0]

            # Extend so the note ends `overlap_beats` after the next note starts
            result[i][1] = (next_start - result[i][0]) + overlap_beats

        return [tuple(n) for n in result]


# ─────────────────────────────────────────────────────────────────────────────
#  3 · 808 OCTAVE LEAP
# ─────────────────────────────────────────────────────────────────────────────

class EightOhEightOctaveLeap:
    """
    Inserts a single +12-semitone stab on the 'and of beat 4' (steps 13-15)
    with 10% probability per bar.

    The stab is short (0.08–0.14 beats) and pitched an octave above the
    bar's sub-bass root.  This creates the dramatic high-register punctuation
    heard in modern Southside, Metro Boomin, and Wheezy productions before
    the bar resets to sub-bass weight on the next downbeat.
    """

    PROB        = 0.10
    WEAK_STEPS  = (13, 14, 15)   # 16th-note steps covering beat 4 "and" region

    @classmethod
    def maybe_hit(cls, root_midi: int, bar_beat_pos: float,
                  bpm: float) -> Optional[Tuple[float, float, int, int]]:
        """
        Args:
            root_midi    : current bar's root MIDI pitch (sub-bass register)
            bar_beat_pos : beat position of this bar's downbeat
            bpm          : tempo for micro-timing jitter
        Returns one note tuple or None.
        """
        if random.random() >= cls.PROB:
            return None

        step     = random.choice(cls.WEAK_STEPS)
        hit_pos  = bar_beat_pos + step * 0.25

        leaped   = root_midi + 12
        # Keep the leap within a practical 808 range (max MIDI C5 = 72)
        while leaped > 72:
            leaped -= 12

        duration = random.uniform(0.08, 0.14)
        velocity = random.randint(88, 108)
        jitter   = random.uniform(-0.004, 0.004)

        return (hit_pos + jitter, duration, leaped, velocity)


# ─────────────────────────────────────────────────────────────────────────────
#  4 · SILENCE MATRIX (BEAT DROPS)
# ─────────────────────────────────────────────────────────────────────────────

class SilenceMatrix:
    """
    Introduces structural beat-drop silences at the end of 8-bar phrases.

    25% of all 8-bar phrase boundaries have the last 1 or 2 beats completely
    muted in the drum and bass tracks.  Melodic tracks are left untouched,
    creating the tension-and-release pattern essential to commercial releases.

    Implementation notes
    --------------------
    Drop zones are computed DETERMINISTICALLY from a seed value (derived from
    config.seed_value or config.genre) so that the drum generator and the bass
    generator independently arrive at **the same drop windows** without needing
    to share runtime state.  Both generators call:

        zones = SilenceMatrix.compute_zones(total_bars, seed=_seed)
        notes = SilenceMatrix.apply(notes, zones)
    """

    DROP_PROB   = 0.25
    MUTE_OPTS   = (1.0, 2.0)   # beats to mute from bar end

    @classmethod
    def compute_zones(cls, total_bars: int,
                      seed: Optional[int] = None) -> Dict[int, float]:
        """
        Return {bar_idx: mute_beats} for 8-bar phrase-ending bars selected
        for a drop.

        Using a seeded RNG guarantees that two calls with the same arguments
        return identical results — essential for drum/bass synchronisation.
        """
        rng    = random.Random(seed)
        zones: Dict[int, float] = {}
        for bar in range(total_bars):
            if (bar + 1) % 8 == 0 and rng.random() < cls.DROP_PROB:
                zones[bar] = rng.choice(cls.MUTE_OPTS)
        return zones

    @classmethod
    def apply(cls, notes: List[Tuple[float, float, int, int]],
              drop_zones: Dict[int, float],
              bar_beats: float = 4.0) -> List[Tuple[float, float, int, int]]:
        """
        Remove notes that fall inside a drop zone's mute window.

        Args:
            notes      : track note list
            drop_zones : {bar_idx: mute_beats} from compute_zones()
            bar_beats  : beats per bar (default 4.0 for 4/4)
        """
        if not drop_zones:
            return notes

        result: List[Tuple[float, float, int, int]] = []
        for note in notes:
            t = note[0]
            bar_idx     = int(t / bar_beats)
            beat_in_bar = t - bar_idx * bar_beats
            if bar_idx in drop_zones:
                mute_b = drop_zones[bar_idx]
                if beat_in_bar >= (bar_beats - mute_b):
                    continue    # silence
            result.append(note)
        return result


# ─────────────────────────────────────────────────────────────────────────────
#  5 · AUXILIARY PERCUSSION LAYER (EAR CANDY)
# ─────────────────────────────────────────────────────────────────────────────

class AuxPercussionLayer:
    """
    Generates sparse, syncopated auxiliary percussion hits that fill the
    rhythmic space between the main kick and snare grid.

    Hit types: rimshots (MIDI 37), open hi-hats (MIDI 46), claps (MIDI 39).
    Placement: 16th-note off-beats and 8th-note triplet sub-positions,
               specifically avoiding the quarter-note grid and occupied kick/snare steps.
    Velocity:  60–80 (background texture, never competing with primary elements).

    12% probability per available step slot keeps the layer sparse enough to
    be felt rather than heard consciously — characteristic of the subliminal
    groove weight in top-tier trap productions.
    """

    HIT_PROB  = 0.12
    VEL_LO    = 60
    VEL_HI    = 80

    _HIT_NOTES: Tuple[int, ...] = (RIMSHOT, HIHAT_OPEN, CLAP)  # 37, 46, 39

    # Main quarter-note grid lines — always excluded from aux hits
    _GRID_EXCL: frozenset = frozenset({0, 4, 8, 12})

    @classmethod
    def generate(cls, bar_beat_pos: float,
                 occupied_steps: Set[int],
                 bpm: float) -> List[Tuple[float, float, int, int]]:
        """
        Generate aux percussion hits for one bar.

        Args:
            bar_beat_pos   : beat position of the bar's downbeat
            occupied_steps : step indices (0-15) used by kick and snare
            bpm            : tempo — used for micro-jitter scaling
        """
        notes: List[Tuple[float, float, int, int]] = []
        excluded = occupied_steps | cls._GRID_EXCL

        # Pool A — off-beat 16th steps clear of kick, snare, and grid
        candidates: List[float] = [
            s * 0.25
            for s in range(16)
            if s not in excluded
        ]

        # Pool B — 8th-note triplet sub-positions (highly irregular)
        for beat in range(4):
            for frac in (1.0 / 3.0, 2.0 / 3.0):
                pos          = beat + frac
                step_approx  = int(round(pos * 4))
                if step_approx not in excluded:
                    candidates.append(pos)

        for pos in candidates:
            if random.random() < cls.HIT_PROB:
                note_midi = random.choice(cls._HIT_NOTES)
                vel       = random.randint(cls.VEL_LO, cls.VEL_HI)
                jitter    = random.uniform(-0.007, 0.007)
                notes.append((bar_beat_pos + pos + jitter, 0.07, note_midi, vel))

        return notes
