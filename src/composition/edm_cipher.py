"""
edm_cipher.py — Five commercial EDM/House production ciphers.

Each cipher is a stateless class with a class-method entry point callable
from composition_engine.py with zero instance management overhead.

  SidechainMatrix          generate_cc(kick_times, total_bars)      -> List[CCEvent]
  StochasticBuildUp        generate(bar_offset, n_bars, bpm)        -> BuildUpDict
  PreDropVoid              apply(tracks, structure)                  -> tracks
  AntiDropFakeOut          apply(tracks, structure, seed)            -> tracks
  PolyrhythmicFilterSweep  generate_cc(total_bars)                   -> List[CCEvent]

CCEvent     = Tuple[float, int, int, int]   (time_beats, cc_number, cc_value, channel)
PitchEvent  = Tuple[float, int, int]        (time_beats, pitch_wheel_value, channel)
Note        = Tuple[float, float, int, int] (time_beats, dur_beats, midi_note, velocity)
BuildUpDict = {'kick': List[Note], 'perc': List[Note], 'pitch_events': List[PitchEvent]}

Pitch-bend values are standard MIDI range: -8192 to 8191.  A value of 8191
maps to whatever pitch-bend range the receiving synth is configured for
(typically ±2 st, but set to ±12 st or ±24 st for the intended +12/+24 rise).
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from src.composition.genre_constants import (
    SNARE, HIHAT_CLOSED, HIHAT_OPEN, CRASH,
)

CCEvent    = Tuple[float, int, int, int]    # (time, cc_num, cc_val, channel)
PitchEvent = Tuple[float, int, int]         # (time, pitch_wheel_val, channel)
Note       = Tuple[float, float, int, int]  # (time, duration, midi, velocity)

# Section types treated as "drop" for cipher purposes.
# House uses 'chorus' where EDM uses 'drop' — both receive the same treatment.
_DROP_LIKE: frozenset = frozenset({'drop', 'chorus'})


# ─────────────────────────────────────────────────────────────────────────────
#  1 · SIDECHAIN AUTOMATION MATRIX
# ─────────────────────────────────────────────────────────────────────────────

class SidechainMatrix:
    """
    Simulates 4-on-the-floor sidechain compression via CC11 (Expression)
    automation on the Bass, Chords, and Pad channels.

    On every quarter-note beat the CC value drops instantly to 30-40 (the
    'duck'), then ramps back to 127 over the following 8th note (0.5 beats)
    in RAMP_STEPS discrete steps.  Each step value is jittered by ±JITTER_PCT
    of its target value to replicate the non-linear attack of an analog VCA.

    The ramp uses a derived kick-position grid so the pump phase-locks to the
    actual kick timing rather than an abstract metronome.  Any beats not covered
    by a kick hit fall back to the quarter-note grid, guaranteeing 4-on-the-floor
    sidechain even in genres with sparse kick patterns.

    Target channels: Bass (ch 0), Chords (ch 2), Pad (ch 3).
    """

    CC_NUM      = 11       # Expression
    DROP_LO     = 30
    DROP_HI     = 40
    PEAK        = 127
    RAMP_STEPS  = 8        # subdivisions across the 0.5-beat ramp window
    RAMP_BEATS  = 0.5      # 8th-note pump recovery
    JITTER_PCT  = 0.02     # ±2% of target value

    _CHANNELS: Tuple[int, ...] = (0, 2, 3)   # bass, chords, pad

    @classmethod
    def generate_cc(
        cls,
        kick_times:  List[float],
        total_bars:  int,
        channels:    Tuple[int, ...] = _CHANNELS,
    ) -> List[CCEvent]:
        """
        Args:
            kick_times : absolute beat positions of kick hits
            total_bars : total song length in bars
            channels   : MIDI channels to apply sidechain to
        """
        total_beats = total_bars * 4.0
        step_size   = cls.RAMP_BEATS / cls.RAMP_STEPS

        # Snap kick positions to nearest quarter note, merge with full beat grid
        quarter_grid: set = set(float(b) for b in range(int(total_beats)))
        for t in kick_times:
            snapped = round(t)
            if 0.0 <= snapped < total_beats:
                quarter_grid.add(float(snapped))

        events: List[CCEvent] = []

        for ch in channels:
            for beat in sorted(quarter_grid):
                drop_val = random.randint(cls.DROP_LO, cls.DROP_HI)

                # Instant duck on the downbeat
                events.append((beat, cls.CC_NUM, drop_val, ch))

                # Smooth ramp back to 127
                for s in range(1, cls.RAMP_STEPS + 1):
                    t = beat + s * step_size
                    if t >= total_beats:
                        break
                    pct    = s / cls.RAMP_STEPS
                    target = drop_val + (cls.PEAK - drop_val) * pct
                    max_j  = max(1, int(target * cls.JITTER_PCT))
                    jitter = random.randint(-max_j, max_j)
                    val    = max(0, min(127, int(target) + jitter))
                    events.append((t, cls.CC_NUM, val, ch))

        return events


# ─────────────────────────────────────────────────────────────────────────────
#  2 · STOCHASTIC BUILD-UP ARCHITECTURE
# ─────────────────────────────────────────────────────────────────────────────

class StochasticBuildUp:
    """
    Generates the drum layer and pitch-bend riser for an EDM build-up section
    (typically 8 bars before a Drop).

    Snare density doubles every two bars:
      bars 0–1 : quarter note (1.0 beat step)
      bars 2–3 : 8th note    (0.5 beat step)
      bars 4–5 : 16th note   (0.25 beat step)
      bars 6–7 : 32nd note   (0.125 beat step)

    Fracture probability 15%: each scheduled snare hit independently rolls
    for a fracture — either a dropped beat (50%) or a triplet offset hit
    (50%) that lands at step × 1/3 after the scheduled position.  This breaks
    the mathematical rigidity and mimics a live drummer pushing the boundaries
    of the pattern.

    Pitch-bend riser: a linear sweep from pitch-bend value 0 to 8191 (full
    positive range) over the entire build-up section.  Applied to the melody /
    lead channel (ch 1).  The actual semitone range depends on the target
    synthesiser's pitch-bend range setting (set the synth to ±12 st for a
    +12-semitone rise, or ±24 st for a full two-octave sweep).

    A crash cymbal is injected on the first downbeat of the build-up bar to
    mark the entrance, and pitch bend is reset to 0 at the exact drop point.
    """

    FRACTURE_PROB  = 0.15

    # (from_bar_inclusive, to_bar_exclusive, step_beats)
    _RAMP_SCHEDULE: Tuple[Tuple[int, int, float], ...] = (
        (0, 2, 1.000),   # quarter note
        (2, 4, 0.500),   # 8th note
        (4, 6, 0.250),   # 16th note
        (6, 8, 0.125),   # 32nd note
    )

    _RISER_CHANNELS: Tuple[int, ...] = (1,)   # melody / lead

    @classmethod
    def _step_for_bar(cls, bar_in_build: int) -> float:
        for lo, hi, step in cls._RAMP_SCHEDULE:
            if lo <= bar_in_build < hi:
                return step
        return 0.125   # beyond 8 bars: stay at 32nd note density

    @classmethod
    def generate(
        cls,
        bar_offset: int,
        n_bars:     int,
        bpm:        float,
    ) -> Dict[str, list]:
        """
        Generate build-up content for one build section.

        Args:
            bar_offset : absolute bar index where this build starts (0-based)
            n_bars     : number of bars in the build section
            bpm        : tempo (not used for timing math; kept for caller parity)

        Returns dict with:
            'kick'        : List[Note]       — crash on downbeat
            'perc'        : List[Note]       — accelerating snare roll
            'pitch_events': List[PitchEvent] — linear pitch-bend sweep + reset
        """
        base_beat          = bar_offset * 4.0
        total_build_beats  = n_bars * 4.0

        kick_notes:   List[Note]       = []
        perc_notes:   List[Note]       = []
        pitch_events: List[PitchEvent] = []

        # ── Crash on build downbeat ───────────────────────────────────────────
        kick_notes.append((base_beat, 0.25, CRASH, 105))

        # ── Accelerating snare roll with fractures ────────────────────────────
        for bar_in_build in range(n_bars):
            step     = cls._step_for_bar(bar_in_build)
            bar_beat = base_beat + bar_in_build * 4.0
            bar_pct  = bar_in_build / max(1, n_bars - 1)   # 0.0 → 1.0 across build

            pos = 0.0
            while pos < 4.0 - 1e-6:
                pos_pct = pos / 4.0
                vel     = int(55 + 72 * (bar_pct * 0.65 + pos_pct * 0.35))
                vel     = max(40, min(127, vel + random.randint(-5, 5)))

                if random.random() < cls.FRACTURE_PROB:
                    if random.random() < 0.5:
                        # Fracture type A: drop this beat entirely
                        pos += step
                        continue
                    else:
                        # Fracture type B: triplet offset — hit 1/3 step late
                        hit_t = bar_beat + pos + step * (1.0 / 3.0)
                else:
                    hit_t = bar_beat + pos

                hit_t = min(hit_t, base_beat + total_build_beats - step * 0.5)
                perc_notes.append((hit_t, step * 0.80, SNARE, vel))

                # Add open hi-hat shimmer in the final 2 bars for air
                if bar_in_build >= n_bars - 2 and abs(pos % 0.5 - 0.25) < 1e-4:
                    hat_vel = max(30, vel - 25)
                    perc_notes.append((hit_t, 0.10, HIHAT_OPEN, hat_vel))

                pos += step

        # ── Linear pitch-bend riser (one event per beat) ─────────────────────
        n_steps = int(total_build_beats)
        for s in range(n_steps + 1):
            t      = base_beat + s * (total_build_beats / max(1, n_steps))
            pb_val = int(8191 * s / max(1, n_steps))
            for ch in cls._RISER_CHANNELS:
                pitch_events.append((t, pb_val, ch))

        # Reset pitch bend at the drop downbeat
        reset_t = base_beat + total_build_beats
        for ch in cls._RISER_CHANNELS:
            pitch_events.append((reset_t, 0, ch))

        return {
            'kick':         kick_notes,
            'perc':         perc_notes,
            'pitch_events': pitch_events,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  3 · PRE-DROP VOID  (TENSION TRIGGER)
# ─────────────────────────────────────────────────────────────────────────────

class PreDropVoid:
    """
    Enforces a mathematical silence in the 1–2 beats immediately before every
    Drop section's downbeat.

    All low-end energy (Kick, Bass) and all sustained harmonic weight (Chords,
    Pad) are muted in this window.  The percussion fill, Arp, Melody, and FX
    tracks are untouched, allowing a single high-frequency element or complete
    silence to hold the tension before the drop lands.

    Void length is chosen per drop from {1, 2} beats using a deterministic
    RNG seeded from the drop's bar index — so drum and bass generators produce
    the same window independently.
    """

    _MUTED_TRACKS: Tuple[str, ...] = ('01_Kick', '03_Bass', '05_Chords', '06_Pad')

    @classmethod
    def apply(
        cls,
        tracks:    Dict[str, List[Note]],
        structure: List[Tuple[str, int]],
        bar_beats: float = 4.0,
    ) -> Dict[str, List[Note]]:
        """
        Args:
            tracks    : assembled track dict from compose()
            structure : [(section_type, n_bars), ...]
            bar_beats : beats per bar (4.0 for 4/4)
        Returns the modified tracks dict.
        """
        drop_voids: List[Tuple[float, float]] = []   # (void_start, drop_beat)
        bar_idx = 0
        for s_type, s_bars in structure:
            if s_type in _DROP_LIKE:
                drop_beat  = bar_idx * bar_beats
                void_beats = random.Random(bar_idx).randint(1, 2)
                void_start = drop_beat - void_beats
                if void_start >= 0.0:
                    drop_voids.append((void_start, drop_beat))
            bar_idx += s_bars

        if not drop_voids:
            return tracks

        for name in cls._MUTED_TRACKS:
            if name not in tracks:
                continue
            tracks[name] = [
                n for n in tracks[name]
                if not any(vs <= n[0] < de for vs, de in drop_voids)
            ]

        return tracks


# ─────────────────────────────────────────────────────────────────────────────
#  4 · ANTI-DROP FAKE-OUT  (THE UNIQUENESS FACTOR)
# ─────────────────────────────────────────────────────────────────────────────

class AntiDropFakeOut:
    """
    With FAKE_OUT_PROB (20%) probability, resolves a full build-up into a
    minimalist drop — only Kick + Bass + sparse Percussion play for the first
    MINIMALIST_BARS (4) bars of the Drop, before the Pad, Chords, and Arp
    detonate on bar 5.

    The decision is seeded deterministically from config.seed_value so the
    same config always produces the same structural choice, which guarantees
    consistency if a track is regenerated with the same parameters.

    Tracks suppressed in the minimalist window: Chords (05), Pad (06), Arp (07).
    Drop sections shorter than MINIMALIST_BARS are skipped (fake-out impossible).
    """

    FAKE_OUT_PROB   = 0.20
    MINIMALIST_BARS = 4
    _SUPPRESSED: Tuple[str, ...] = ('05_Chords', '06_Pad', '07_Arp')

    @classmethod
    def apply(
        cls,
        tracks:    Dict[str, List[Note]],
        structure: List[Tuple[str, int]],
        seed:      Optional[int] = None,
        bar_beats: float = 4.0,
    ) -> Dict[str, List[Note]]:
        """
        Args:
            tracks    : assembled track dict
            structure : [(section_type, n_bars), ...]
            seed      : deterministic seed (pass config.seed_value)
            bar_beats : beats per bar
        Returns unmodified tracks if fake-out is not triggered.
        """
        rng = random.Random(seed)
        if rng.random() >= cls.FAKE_OUT_PROB:
            return tracks

        suppressed_ranges: List[Tuple[float, float]] = []
        bar_idx = 0
        for s_type, s_bars in structure:
            if s_type in _DROP_LIKE and s_bars > cls.MINIMALIST_BARS:
                start_beat = bar_idx * bar_beats
                end_beat   = start_beat + cls.MINIMALIST_BARS * bar_beats
                suppressed_ranges.append((start_beat, end_beat))
            bar_idx += s_bars

        if not suppressed_ranges:
            return tracks

        for name in cls._SUPPRESSED:
            if name not in tracks:
                continue
            tracks[name] = [
                n for n in tracks[name]
                if not any(s <= n[0] < e for s, e in suppressed_ranges)
            ]

        return tracks


# ─────────────────────────────────────────────────────────────────────────────
#  5 · POLYRHYTHMIC FILTER SWEEP
# ─────────────────────────────────────────────────────────────────────────────

class PolyrhythmicFilterSweep:
    """
    Injects CC74 (Filter Cutoff) automation into the Pad (ch 3) and Arp (ch 4)
    tracks, cycling on a 3-bar period over a standard 4-bar musical phrase.

    The 3-vs-4 phase offset ensures the filter tone is in a different position
    relative to the phrase on every bar — the pattern repeats only after a
    12-bar hyper-cycle (LCM of 3 and 4), so within any 8-bar or 16-bar loop
    the synth texture is continuously morphing and never sounds identical.

    Sweep shape: symmetric triangle wave.
        phase 0.0  → cutoff = CC_LO  (darkest, closed filter)
        phase 0.5  → cutoff = CC_HI  (brightest, fully open filter)
        phase 1.0  → cutoff = CC_LO  (back to dark)

    Each CC step receives ±JITTER of per-step randomization to replicate the
    non-linear response of analog filter circuitry.
    """

    CC_NUM     = 74      # Filter Cutoff
    CC_LO      = 20
    CC_HI      = 127
    CYCLE_BARS = 3       # odd-meter cycle length
    RESOLUTION = 0.25    # 16th-note automation density
    JITTER     = 2

    _CHANNELS: Tuple[int, ...] = (3, 4)   # pad, arp

    @classmethod
    def generate_cc(
        cls,
        total_bars: int,
        channels:   Tuple[int, ...] = _CHANNELS,
    ) -> List[CCEvent]:
        """
        Args:
            total_bars : total song length in bars
            channels   : MIDI channels to write CC74 to (default: pad + arp)
        """
        cycle_beats = cls.CYCLE_BARS * 4.0
        total_beats = total_bars * 4.0
        events: List[CCEvent] = []

        t = 0.0
        while t < total_beats - 1e-9:
            phase     = (t % cycle_beats) / cycle_beats          # 0 → 1
            triangle  = 1.0 - 2.0 * abs(phase - 0.5)            # 0 → 1 → 0
            cc_val    = int(cls.CC_LO + (cls.CC_HI - cls.CC_LO) * triangle)
            jitter    = random.randint(-cls.JITTER, cls.JITTER)
            cc_val    = max(0, min(127, cc_val + jitter))

            for ch in channels:
                events.append((t, cls.CC_NUM, cc_val, ch))

            t = round(t + cls.RESOLUTION, 6)   # avoid float drift

        return events
