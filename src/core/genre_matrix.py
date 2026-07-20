"""
genre_matrix.py -- Commercial Genre Matrix: stylistic routing for mathematical variety.

Purpose:
    Raw mathematical variety (Euclidean patterns, voice-leading, polyrhythms) must
    be ROUTED through commercial genre conventions to produce commercially viable
    tracks.  Without genre constraints, the system outputs statistically correct
    but stylistically incoherent music.

    This module defines the per-genre "envelope" of allowable musical decisions and
    provides static application helpers that translates those envelopes into concrete
    MIDI manipulations inside the generator classes.

    Every generator calls GenreMatrix.get_profile(genre) in __init__ and stores the
    result as self._gp.  All application methods are pure static functions so
    generators can call GenreMatrix.method(args) without instantiation.

Protocols:

    TRAP PROTOCOL  (trap, phonk)
        02_Percussion: 32nd-note hi-hat subdivision layer with velocity-drop runs
                       (each step: vel *= vel_drop_curve, creating the bounce)
                       Optional triplet roll for phonk's aggressive chatter
        01_Kick / 03_Bass: 808 sub-bass note-on times snapped to exact kick step
                           positions -- no humanizer jitter on the attack so the
                           kick and 808 share the same tick (locked sub-kick)

    HIP-HOP PROTOCOL  (hiphop)
        Global Swing: MPC-style swing_pct = 0.67 (full triplet feel) on tracks
                      1, 2, 3 (kick, percussion, bass) -- off-beat 16ths pushed
                      late for laid-back human groove
        05_Chords / 06_Pad: jazz-style extended voicings (7ths, 9ths) via
                            extended_chord_intervals(); chord notes rolled
                            (arpeggiated) with roll_ms delay between voices for
                            a human keyboard attack feel

    HOUSE PROTOCOL  (house)
        01_Kick: strict four-on-the-floor at max velocity -- every beat, no
                 exceptions, no syncopation
        03_Bass: strong off-beat 16th bias (plays between the kicks for the
                 classic house pump-and-drive feel)
        Build + Drop: 1-beat silence gap immediately before DROP

    EDM PROTOCOL  (edm)
        01_Kick: four-on-the-floor at maximum velocity (127)
        03_Bass: very strong off-beat 16th bias (0.78)
        06_Pad / 09_Texture (BUILD): exponential velocity ramp culminating in
                                     absolute silence (drop gap) 1 beat before
                                     the DROP section -- the defining "drop moment"

    NOTE ON PITCH BEND:
        The user specification references pitch-bend data ramping during BUILD.
        Pitch-bend is delegated to the EDM cipher layer (PolyrhythmicFilterSweep
        and StochasticBuildUp in orchestrator.py) which already handles CC11 /
        filter-sweep automations.  The genre_matrix handles VELOCITY ramp only.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple

Note = Tuple[float, float, int, int]


# ---------------------------------------------------------------------------
# GenreProfile dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenreProfile:
    """
    Immutable parameter bundle describing one genre's stylistic constraints.

    All generator classes store one instance as self._gp.
    Fields are grouped by the protocol that consumes them.
    """

    # -- Trap Protocol --------------------------------------------------
    trap_hihat_32nd_weight:  float   # probability of inserting 32nd hi-hat runs
    trap_hihat_triplet_roll: bool    # enable 4-step triplet rolls (phonk bounce)
    trap_808_kick_lock:      bool    # snap 808 note-on to exact kick step positions
    trap_vel_drop_curve:     float   # per-step velocity multiplier in hi-hat runs

    # -- Hip-Hop / Global Swing -----------------------------------------
    swing_pct:               float   # MPC swing (0.50=straight, 0.67=full triplet)
    hiphop_extended_chords:  bool    # use 7th/9th intervals in chords + pad
    hiphop_chord_roll_ms:    float   # ms between rolled chord voices (0 = off)

    # -- House / EDM Kick -----------------------------------------------
    four_on_floor:           bool    # override kick with strict 4/4 every beat
    four_on_floor_vel:       int     # base velocity for 4otf kick hits

    # -- House / EDM Bass -----------------------------------------------
    bass_offbeat_bias:       float   # fraction of off-beat 16th steps that fire

    # -- Build + Drop (EDM / House) -------------------------------------
    build_ramp_exponential:  bool    # exponential velocity ramp during BUILD
    build_drop_gap_beats:    float   # beats of absolute silence before DROP


# ---------------------------------------------------------------------------
# Per-genre profile definitions
# ---------------------------------------------------------------------------

GENRE_PROFILES: Dict[str, GenreProfile] = {
    'trap': GenreProfile(
        trap_hihat_32nd_weight  = 0.72,   # heavy 32nd density -- the signature bounce
        trap_hihat_triplet_roll = True,   # rolling velocity-drop runs
        trap_808_kick_lock      = True,   # 808 fires on exact kick tick
        trap_vel_drop_curve     = 0.82,   # vel × 0.82 per step (fast fade)
        swing_pct               = 0.56,   # mild swing -- trap sits just off-grid
        hiphop_extended_chords  = False,
        hiphop_chord_roll_ms    = 0.0,
        four_on_floor           = False,
        four_on_floor_vel       = 127,
        bass_offbeat_bias       = 0.20,
        build_ramp_exponential  = False,
        build_drop_gap_beats    = 0.5,
    ),
    'phonk': GenreProfile(
        trap_hihat_32nd_weight  = 0.80,   # denser than trap -- the chatter
        trap_hihat_triplet_roll = True,
        trap_808_kick_lock      = True,
        trap_vel_drop_curve     = 0.78,   # faster fade = more aggressive bounce
        swing_pct               = 0.60,
        hiphop_extended_chords  = False,
        hiphop_chord_roll_ms    = 0.0,
        four_on_floor           = False,
        four_on_floor_vel       = 127,
        bass_offbeat_bias       = 0.25,
        build_ramp_exponential  = False,
        build_drop_gap_beats    = 0.5,
    ),
    'hiphop': GenreProfile(
        trap_hihat_32nd_weight  = 0.18,   # occasional 32nds for flair
        trap_hihat_triplet_roll = False,
        trap_808_kick_lock      = False,
        trap_vel_drop_curve     = 1.0,
        swing_pct               = 0.67,   # full MPC triplet swing (2/3)
        hiphop_extended_chords  = True,   # 7ths and 9ths throughout
        hiphop_chord_roll_ms    = 22.0,   # ~22ms roll = human piano touch
        four_on_floor           = False,
        four_on_floor_vel       = 110,
        bass_offbeat_bias       = 0.18,
        build_ramp_exponential  = False,
        build_drop_gap_beats    = 0.0,
    ),
    'house': GenreProfile(
        trap_hihat_32nd_weight  = 0.0,
        trap_hihat_triplet_roll = False,
        trap_808_kick_lock      = False,
        trap_vel_drop_curve     = 1.0,
        swing_pct               = 0.50,   # house is straight -- no swing
        hiphop_extended_chords  = False,
        hiphop_chord_roll_ms    = 0.0,
        four_on_floor           = True,   # the house law -- kick on every beat
        four_on_floor_vel       = 120,
        bass_offbeat_bias       = 0.72,   # bass pumps hard between the kicks
        build_ramp_exponential  = False,
        build_drop_gap_beats    = 1.0,    # 1-beat silence before drop
    ),
    'edm': GenreProfile(
        trap_hihat_32nd_weight  = 0.0,
        trap_hihat_triplet_roll = False,
        trap_808_kick_lock      = False,
        trap_vel_drop_curve     = 1.0,
        swing_pct               = 0.52,
        hiphop_extended_chords  = False,
        hiphop_chord_roll_ms    = 0.0,
        four_on_floor           = True,   # maximum-velocity 4otf -- no exceptions
        four_on_floor_vel       = 127,
        bass_offbeat_bias       = 0.78,   # very strong pump
        build_ramp_exponential  = True,   # exponential ramp into the drop
        build_drop_gap_beats    = 1.0,    # 1-beat void = the drop moment
    ),
    'techno': GenreProfile(
        trap_hihat_32nd_weight  = 0.0,
        trap_hihat_triplet_roll = False,
        trap_808_kick_lock      = False,
        trap_vel_drop_curve     = 1.0,
        swing_pct               = 0.50,
        hiphop_extended_chords  = False,
        hiphop_chord_roll_ms    = 0.0,
        four_on_floor           = True,
        four_on_floor_vel       = 127,
        bass_offbeat_bias       = 0.65,
        build_ramp_exponential  = True,
        build_drop_gap_beats    = 0.5,
    ),
    'dnb': GenreProfile(
        trap_hihat_32nd_weight  = 0.15,
        trap_hihat_triplet_roll = False,
        trap_808_kick_lock      = False,
        trap_vel_drop_curve     = 0.90,
        swing_pct               = 0.54,
        hiphop_extended_chords  = False,
        hiphop_chord_roll_ms    = 0.0,
        four_on_floor           = False,
        four_on_floor_vel       = 110,
        bass_offbeat_bias       = 0.50,
        build_ramp_exponential  = True,
        build_drop_gap_beats    = 0.5,
    ),
    'pop': GenreProfile(
        trap_hihat_32nd_weight  = 0.08,
        trap_hihat_triplet_roll = False,
        trap_808_kick_lock      = False,
        trap_vel_drop_curve     = 1.0,
        swing_pct               = 0.52,
        hiphop_extended_chords  = False,
        hiphop_chord_roll_ms    = 0.0,
        four_on_floor           = False,
        four_on_floor_vel       = 110,
        bass_offbeat_bias       = 0.28,
        build_ramp_exponential  = False,
        build_drop_gap_beats    = 0.0,
    ),
    'cinematic': GenreProfile(
        trap_hihat_32nd_weight  = 0.0,
        trap_hihat_triplet_roll = False,
        trap_808_kick_lock      = False,
        trap_vel_drop_curve     = 1.0,
        swing_pct               = 0.50,
        hiphop_extended_chords  = True,   # rich orchestral/jazz voicings
        hiphop_chord_roll_ms    = 35.0,   # wide roll = orchestral string stagger
        four_on_floor           = False,
        four_on_floor_vel       = 100,
        bass_offbeat_bias       = 0.10,
        build_ramp_exponential  = True,   # cinematic builds ramp to climax
        build_drop_gap_beats    = 0.0,
    ),
}


# ---------------------------------------------------------------------------
# GenreMatrix -- static application helpers
# ---------------------------------------------------------------------------

class GenreMatrix:
    """
    Static helpers that apply GenreProfile parameters inside generator classes.

    Usage in generators:
        from src.core.genre_matrix import GenreMatrix, GenreProfile

        class MyGenerator(TrackGenerator):
            def __init__(self, context, rng):
                super().__init__(context, rng)
                self._gp: GenreProfile = GenreMatrix.get_profile(context.genre)
    """

    @staticmethod
    def get_profile(genre: str) -> GenreProfile:
        """Return the GenreProfile for genre.  Falls back to 'pop' for unknown genres."""
        return GENRE_PROFILES.get(genre, GENRE_PROFILES['pop'])

    # ------------------------------------------------------------------
    # Trap Protocol
    # ------------------------------------------------------------------

    @staticmethod
    def trap_hihat_velocity_run(
        base_vel:   int,
        n_steps:    int,
        drop_curve: float,
    ) -> List[int]:
        """
        Generate a velocity-drop sequence for a trap hi-hat bounce run.

        Each step multiplies the previous velocity by drop_curve, creating
        the rapid fade-out characteristic of the trap bounce.

        Parameters
        ----------
        base_vel   : starting velocity (the loudest, accented hit)
        n_steps    : number of 32nd-note steps in the run
        drop_curve : per-step multiplier (e.g., 0.82 → fast fade)

        Returns
        -------
        List[int] of velocities, length n_steps, strictly descending.
        """
        vels: List[int] = []
        v = float(base_vel)
        for _ in range(n_steps):
            vels.append(max(1, int(v)))
            v *= drop_curve
        return vels

    @staticmethod
    def get_kick_beats(genre: str, bar_start_beat: float) -> List[float]:
        """
        Return kick beat positions for one bar of the given genre.

        Used by BassGenerator (808 kick-lock) to derive the exact kick timings
        without requiring cross-generator state sharing.  Reads the SAME
        GENRE_DRUM_PATTERNS reference the KickGenerator uses so they are
        mathematically aligned before humanizer jitter is applied.

        Only the first pattern variant is used for deterministic lock calculation.
        """
        from src.composition.genre_constants import GENRE_DRUM_PATTERNS
        patterns = GENRE_DRUM_PATTERNS.get(genre, GENRE_DRUM_PATTERNS.get('pop', [{}]))
        if not patterns:
            return [bar_start_beat]
        kick_steps = patterns[0].get('kick', [])
        return [bar_start_beat + step * 0.25 for step, _ in kick_steps]

    @staticmethod
    def nearest_kick_beat(note_time: float, kick_beats: List[float]) -> float:
        """
        Snap a note time to the nearest kick beat (within 0.5 beats).

        Returns original time if no kick beat is within half a beat.
        """
        if not kick_beats:
            return note_time
        nearest = min(kick_beats, key=lambda kb: abs(kb - note_time))
        if abs(nearest - note_time) <= 0.50:
            return nearest
        return note_time

    # ------------------------------------------------------------------
    # Hip-Hop Protocol
    # ------------------------------------------------------------------

    @staticmethod
    def extended_chord_intervals(quality: str) -> List[int]:
        """
        Return 7th / 9th extended chord intervals for jazz-style voicings.

        Replaces the standard CHORD_INTERVALS triads when hiphop_extended_chords
        is True.  Quality string matches the output of parse_chord_string().

        Interval map (semitones relative to root):
            major / maj / M  →  maj7   [0, 4, 7, 11]
            minor / min / m  →  min7   [0, 3, 7, 10]
            dom / 7          →  dom9   [0, 4, 7, 10, 14]
            dim              →  min7b5 [0, 3, 6, 10]
            aug              →  augM7  [0, 4, 8, 11]
            sus2             →  sus2-7 [0, 2, 7, 10]
            sus4             →  sus4-7 [0, 5, 7, 10]
        """
        _EXT: Dict[str, List[int]] = {
            'maj':    [0, 4, 7, 11],
            'major':  [0, 4, 7, 11],
            'M':      [0, 4, 7, 11],
            'min':    [0, 3, 7, 10],
            'minor':  [0, 3, 7, 10],
            'm':      [0, 3, 7, 10],
            'dom':    [0, 4, 7, 10, 14],
            '7':      [0, 4, 7, 10, 14],
            'dim':    [0, 3, 6, 10],
            'aug':    [0, 4, 8, 11],
            'sus2':   [0, 2, 7, 10],
            'sus4':   [0, 5, 7, 10],
            'maj7':   [0, 4, 7, 11],
            'min7':   [0, 3, 7, 10],
            'dom7':   [0, 4, 7, 10],
            'dim7':   [0, 3, 6, 9],
        }
        return _EXT.get(quality, [0, 4, 7, 11])   # default: maj7

    @staticmethod
    def apply_chord_roll(
        notes:    List[Note],
        roll_ms:  float,
        bpm:      float,
    ) -> List[Note]:
        """
        Arpeggiate chord notes by staggering their onset times.

        Notes sharing the same onset (same chord block) are sorted by ascending
        pitch, then each voice after the first is delayed by roll_ms ms.  This
        mimics a human pianist rolling the chord from lowest to highest note.

        Parameters
        ----------
        notes   : list of Note tuples (time, dur, pitch, vel)
        roll_ms : delay in milliseconds between each successive voice
        bpm     : beats per minute (for ms → beats conversion)

        Returns
        -------
        New sorted note list with staggered onsets.  Gate of each rolled voice
        is shortened by half its delay to preserve the rhythmic feel.
        """
        if roll_ms <= 0.0 or not notes:
            return notes

        roll_beats    = (roll_ms / 1000.0) * (bpm / 60.0)
        cluster_win   = (7.0 / 1000.0) * (bpm / 60.0)   # 7ms clustering window

        sorted_notes  = sorted(notes, key=lambda n: (n[0], n[2]))
        rolled: List[Note] = []

        i = 0
        while i < len(sorted_notes):
            t0      = sorted_notes[i][0]
            cluster: List[Note] = []
            while i < len(sorted_notes) and abs(sorted_notes[i][0] - t0) <= cluster_win:
                cluster.append(sorted_notes[i])
                i += 1

            cluster.sort(key=lambda n: n[2])   # ascending pitch

            for voice_idx, (t, dur, pitch, vel) in enumerate(cluster):
                delay   = voice_idx * roll_beats
                new_dur = max(0.05, dur - delay * 0.5)   # compensate gate
                rolled.append((t + delay, new_dur, pitch, vel))

        rolled.sort(key=lambda n: n[0])
        return rolled

    # ------------------------------------------------------------------
    # Build + Drop Protocol (EDM / House)
    # ------------------------------------------------------------------

    @staticmethod
    def apply_build_ramp(
        notes:            List[Note],
        build_start_beat: float,
        build_end_beat:   float,
        exponential:      bool = True,
    ) -> List[Note]:
        """
        Ramp note velocities upward across a BUILD section.

        Exponential curve (square-root):  vel_out = vel + (127-vel) · √progress
        Linear curve:                     vel_out = vel + (127-vel) · progress

        where progress ∈ [0, 1] = fraction through the build section.

        The exponential curve starts slowly (tension) and accelerates toward
        the drop, matching the perceptual intensity curve of real EDM builds.

        Parameters
        ----------
        notes            : notes to ramp (should be filtered to BUILD section only)
        build_start_beat : absolute beat where the BUILD begins
        build_end_beat   : absolute beat where the BUILD ends (= DROP start)
        exponential      : True → exponential curve, False → linear

        Returns
        -------
        New list of Note tuples with ramped velocities.
        """
        span = build_end_beat - build_start_beat
        if span <= 0.0:
            return notes

        ramped: List[Note] = []
        for (t, dur, pitch, vel) in notes:
            progress = max(0.0, min(1.0, (t - build_start_beat) / span))
            if exponential:
                shaped = int(vel + (127 - vel) * (progress ** 0.5))
            else:
                shaped = int(vel + (127 - vel) * progress)
            ramped.append((t, dur, pitch, max(1, min(127, shaped))))

        return ramped

    @staticmethod
    def apply_drop_gap(
        notes:           List[Note],
        drop_start_beat: float,
        gap_beats:       float,
    ) -> List[Note]:
        """
        Enforce absolute silence in the window immediately before a DROP.

        The drop gap is the defining moment of EDM and House production.  One beat
        of silence before the drop creates maximum tension and release -- it is the
        "breath before the punch."

        Notes whose onset falls in [drop_start - gap_beats, drop_start) are removed.
        Notes that START before the gap but whose TAIL extends into it are truncated.

        Parameters
        ----------
        notes           : the full track note list
        drop_start_beat : absolute beat where the DROP/CHORUS begins
        gap_beats       : width of the silence window in beats

        Returns
        -------
        Filtered and tail-clipped note list, sorted by time.
        """
        if gap_beats <= 0.0:
            return notes

        gap_start = drop_start_beat - gap_beats
        result: List[Note] = []

        for (t, dur, pitch, vel) in notes:
            if gap_start <= t < drop_start_beat:
                # Note onset is inside the gap -- remove entirely
                continue
            if t < gap_start and t + dur > gap_start:
                # Note started before gap but tail overlaps -- clip tail
                new_dur = max(0.02, gap_start - t)
                result.append((t, new_dur, pitch, vel))
            else:
                result.append((t, dur, pitch, vel))

        result.sort(key=lambda n: n[0])
        return result

    @staticmethod
    def find_drop_start_beats(
        structure: list,
        bar_beats: float = 4.0,
    ) -> List[float]:
        """
        Return absolute beat positions of DROP / CHORUS sections that are
        immediately preceded by a BUILD or PRE-CHORUS section.

        Only "earned" drops (following a build) get the silence gap.  A chorus
        that follows a verse directly is not treated as a drop-gap target.
        """
        drop_starts: List[float] = []
        beat = 0.0
        _DROP_TYPES    = frozenset({'drop', 'chorus', 'climax'})
        _BUILD_TYPES   = frozenset({'build', 'pre_chorus'})

        for i, (section_type, section_bars) in enumerate(structure):
            if section_type in _DROP_TYPES:
                if i > 0 and structure[i - 1][0] in _BUILD_TYPES:
                    drop_starts.append(beat)
            beat += section_bars * bar_beats

        return drop_starts

    @staticmethod
    def find_build_ranges(
        structure: list,
        bar_beats: float = 4.0,
    ) -> List[Tuple[float, float]]:
        """
        Return (start_beat, end_beat) pairs for every BUILD section.

        Used by pad.py and texture.py to scope the build ramp pass.
        """
        ranges: List[Tuple[float, float]] = []
        beat = 0.0
        for section_type, section_bars in structure:
            span = section_bars * bar_beats
            if section_type == 'build':
                ranges.append((beat, beat + span))
            beat += span
        return ranges
