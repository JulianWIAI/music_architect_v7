"""
telemetry_grader_midi.py — Mathematical MIDI fitness scoring engine.

Evaluates tracks purely from music-theory mathematics: scale adherence, rhythmic
variance, chord density, and motif repetition. No audio (.wav) analysis.

CLI
---
python -m src.orchestration.telemetry_grader_midi --batch-dir ./batch_output

Output
------
batch_output/<genre>/math_fitness_report.json  per genre
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from src.orchestration.genre_grader_config import GraderGenreConfig, get_grader_config
    _GENRE_CONFIG_AVAILABLE = True
except ImportError:
    _GENRE_CONFIG_AVAILABLE = False
    GraderGenreConfig = None   # type: ignore

try:
    import mido
    _MIDO_OK = True
except ImportError:
    _MIDO_OK = False


# ── Music-theory constants ────────────────────────────────────────────────────

_NOTE_TO_PC: Dict[str, int] = {
    'C': 0,  'C#': 1,  'Db': 1,  'D': 2,  'D#': 3,  'Eb': 3,
    'E': 4,  'F': 5,  'F#': 6,  'Gb': 6,  'G': 7,
    'G#': 8, 'Ab': 8,  'A': 9,  'A#': 10, 'Bb': 10, 'B': 11,
}

_SCALE_INTERVALS: Dict[str, List[int]] = {
    'major':            [0, 2, 4, 5, 7, 9, 11],
    'ionian':           [0, 2, 4, 5, 7, 9, 11],
    'minor':            [0, 2, 3, 5, 7, 8, 10],
    'aeolian':          [0, 2, 3, 5, 7, 8, 10],
    'natural_minor':    [0, 2, 3, 5, 7, 8, 10],
    'dorian':           [0, 2, 3, 5, 7, 9, 10],
    'phrygian':         [0, 1, 3, 5, 7, 8, 10],
    'lydian':           [0, 2, 4, 6, 7, 9, 11],
    'mixolydian':       [0, 2, 4, 5, 7, 9, 10],
    'locrian':          [0, 1, 3, 5, 6, 8, 10],
    'harmonic_minor':   [0, 2, 3, 5, 7, 8, 11],
    'melodic_minor':    [0, 2, 3, 5, 7, 9, 11],
    'pentatonic_major': [0, 2, 4, 7, 9],
    'pentatonic_minor': [0, 3, 5, 7, 10],
    'blues':            [0, 3, 5, 6, 7, 10],
    'japanese':         [0, 1, 5, 7, 8],
    'chromatic':        list(range(12)),
}

_DRUM_CHANNEL = 9
_FX_CHANNEL   = 7   # 10_FX track in our engine


# ── MIDI loading ──────────────────────────────────────────────────────────────

class _Track:
    """Lightweight container for a parsed MIDI track."""
    __slots__ = ('name', 'channel', 'notes')

    def __init__(self, name: str, channel: Optional[int],
                 notes: List[Tuple[int, int, int]]):
        self.name    = name       # from track_name message
        self.channel = channel    # first channel seen (None if no notes)
        self.notes   = notes      # list of (abs_tick, pitch, velocity)

    @property
    def is_drum(self) -> bool:
        return self.channel == _DRUM_CHANNEL

    @property
    def is_fx(self) -> bool:
        return self.channel == _FX_CHANNEL or '10_fx' in self.name.lower()

    @property
    def is_pitched(self) -> bool:
        return bool(self.notes) and not self.is_drum and not self.is_fx


def _parse_midi(midi_path: Path) -> Tuple[int, List[_Track]]:
    """
    Return (ticks_per_beat, list_of_Track).
    Each Track contains sorted (abs_tick, pitch, velocity) note-on events.
    """
    midi = mido.MidiFile(str(midi_path))
    tpb  = midi.ticks_per_beat
    parsed: List[_Track] = []

    for mido_track in midi.tracks:
        name = next(
            (msg.name for msg in mido_track if msg.type == 'track_name'),
            'unknown',
        )
        notes: List[Tuple[int, int, int]] = []
        channel: Optional[int] = None
        abs_tick = 0

        for msg in mido_track:
            abs_tick += msg.time
            if hasattr(msg, 'channel'):
                if channel is None:
                    channel = msg.channel
            if msg.type == 'note_on' and msg.velocity > 0:
                notes.append((abs_tick, msg.note, msg.velocity))

        if notes:
            notes.sort()
            parsed.append(_Track(name, channel, notes))

    return tpb, parsed


# ── Scale helpers ─────────────────────────────────────────────────────────────

def _pitch_class_set(root: str, scale: str) -> frozenset:
    root_pc   = _NOTE_TO_PC.get(root, 0)
    intervals = _SCALE_INTERVALS.get(scale.lower(), _SCALE_INTERVALS['major'])
    return frozenset((root_pc + i) % 12 for i in intervals)


# ── Penalty 1 — Scale Adherence (max 35 pts) ─────────────────────────────────

def _scale_penalty(
    tracks:    List[_Track],
    scale_pcs: frozenset,
    cfg=None,
) -> Tuple[float, dict]:
    """
    Fraction of pitched notes outside target scale × max_weight.
    max_weight varies by genre: Pop=40 (strict), House=30 (modal OK), others=35.
    """
    max_weight = cfg.scale_penalty_max if cfg else 35.0
    in_scale = out_scale = 0
    per_track: dict = {}

    for t in tracks:
        if not t.is_pitched:
            continue
        t_in = t_out = 0
        for _, pitch, _ in t.notes:
            if pitch % 12 in scale_pcs:
                t_in  += 1
            else:
                t_out += 1
        in_scale  += t_in
        out_scale += t_out
        total_t = t_in + t_out
        per_track[t.name] = {
            "in_scale":      t_in,
            "out_of_scale":  t_out,
            "error_rate":    round(t_out / max(total_t, 1), 4),
        }

    total   = in_scale + out_scale
    rate    = out_scale / max(total, 1)
    penalty = round(rate * max_weight, 4)
    return penalty, {
        "total_pitched_notes": total,
        "out_of_scale_notes":  out_scale,
        "out_of_scale_rate":   round(rate, 4),
        "max_penalty_weight":  max_weight,
        "penalty":             penalty,
        "per_track":           per_track,
    }


# ── Penalty 2 — Rhythmic Variance (max 20 pts) ───────────────────────────────

_RV_TARGET_LO    = 0.05   # below = metronomic (uniform 8th-note grid with no variation)
_RV_TARGET_HI    = 2.00   # above = chaotic (trap mixes 16th/8th/qtr/half → CV 0.5–1.8 is normal)
_RV_MIN_ONSETS   = 8      # below this note count, skip variance check (too sparse to assess)

def _rhythmic_variance_penalty(tracks: List[_Track], cfg=None) -> Tuple[float, dict]:
    """
    Coefficient of variation (CV = σ/μ) of inter-onset intervals on the
    melody track. Target human-like groove: CV in [0.15, 0.45].
    """
    # Prefer melody track (name contains "melody"), then "lead", then "arp".
    # Explicitly exclude bass/808/pad/drum tracks to avoid measuring the wrong
    # thing when track names are unavailable in older MIDI files.
    _EXCLUDE = ('bass', '808', 'pad', 'kick', 'snare', 'hihat', 'hat', 'drum')
    melody = next(
        (t for t in tracks if 'melody' in t.name.lower() and t.is_pitched), None
    )
    if melody is None:
        melody = next(
            (t for t in tracks
             if t.is_pitched and not any(x in t.name.lower() for x in _EXCLUDE)),
            None,
        )

    lo      = cfg.rv_target_lo  if cfg else _RV_TARGET_LO
    hi      = cfg.rv_target_hi  if cfg else _RV_TARGET_HI
    min_onsets = cfg.rv_min_onsets if cfg else _RV_MIN_ONSETS

    if melody is None or len(melody.notes) < min_onsets:
        return 0.0, {"cv": None, "penalty": 0.0, "note": "insufficient_data_or_too_sparse"}

    onsets = sorted(t for t, _, _ in melody.notes)
    iois   = [onsets[i+1] - onsets[i] for i in range(len(onsets) - 1)
              if onsets[i+1] > onsets[i]]

    if not iois:
        return 0.0, {"cv": None, "penalty": 0.0}

    mean_ioi = statistics.mean(iois)
    if mean_ioi == 0:
        return 0.0, {"cv": None, "penalty": 0.0}

    cv = statistics.pstdev(iois) / mean_ioi

    if cv < lo:
        penalty = (((lo - cv) / lo)) * 20.0
    elif cv > hi:
        # Upper slope spans one full target-width above hi (e.g. hi=2.0 → full at cv=4.0).
        # Using max(hi,1.0) prevents denominator collapse when hi > 1.0.
        _upper_scale = max(hi, 1.0)
        penalty = (((cv - hi) / _upper_scale)) * 20.0
    else:
        penalty = 0.0

    penalty = round(min(penalty, 20.0), 4)
    return penalty, {
        "track_used":   melody.name,
        "onset_count":  len(onsets),
        "mean_ioi":     round(mean_ioi, 2),
        "cv":           round(cv, 4),
        "target_range": [lo, hi],
        "penalty":      penalty,
    }


# ── Penalty 3 — Chord Density (max 20 pts) ───────────────────────────────────

_LOW_PITCH_THRESHOLD = 43   # G2 — below this = true sub-bass; C3 was too high for trap
# Trap chord voicings sit in G#2-B2 (MIDI 44-47); only penalise notes below G2
_CLUSTER_WINDOW      = 20   # ticks — notes within this window = simultaneous chord
_CLUSTER_MIN_NOTES   = 4    # minimum notes to count as a dense cluster
_MUDDY_LOW_MIN       = 3    # ≥ this many low notes in a cluster = muddy

def _chord_density_penalty(tracks: List[_Track], cfg=None) -> Tuple[float, dict]:
    """
    Penalise dense note clusters (>=4 notes) where >=3 notes are below the
    sub-bass threshold.  Genre-aware behaviour:
      EDM  — disabled entirely (supersaws require full polyphony).
      Pop  — also enforces a max-polyphony check (triads/tetrads only).
      All  — requires an identifiable chord track; returns 0 when not found.
    """
    low_threshold = cfg.low_pitch_threshold if cfg else _LOW_PITCH_THRESHOLD
    max_polyphony = cfg.max_chord_polyphony  if cfg else 0

    # EDM: chord density check is meaningless for supersaw layering
    if cfg and cfg.chord_density_disabled:
        return 0.0, {"track_used": "disabled_for_genre", "muddy_clusters": 0,
                     "penalty": 0.0, "note": "chord_density_disabled_edm_supersaw"}

    chords_track = next(
        (t for t in tracks if 'chord' in t.name.lower() and t.is_pitched), None
    )
    if chords_track is None:
        return 0.0, {"track_used": "none_found", "muddy_clusters": 0,
                     "penalty": 0.0,
                     "note": "chord_track_not_identified_by_name"}

    events: List[Tuple[int, int]] = []
    for tick, pitch, _ in chords_track.notes:
        events.append((tick, pitch))
    events.sort()

    muddy_clusters = 0
    dense_clusters = 0   # polyphony violation counter (Pop)
    i = 0
    while i < len(events):
        ref_tick = events[i][0]
        j = i
        cluster: List[int] = []
        while j < len(events) and events[j][0] - ref_tick <= _CLUSTER_WINDOW:
            cluster.append(events[j][1])
            j += 1
        if len(cluster) >= _CLUSTER_MIN_NOTES:
            low_count = sum(1 for p in cluster if p < low_threshold)
            if low_count >= _MUDDY_LOW_MIN:
                muddy_clusters += 1
            # Pop sparsity: penalise chords with more notes than max_polyphony
            if max_polyphony > 0 and len(set(p % 128 for p in cluster)) > max_polyphony:
                dense_clusters += 1
        i = j if j > i else i + 1

    muddy_penalty = round(min(muddy_clusters * 3.0, 20.0), 4)
    dense_penalty = round(min(dense_clusters * 2.5, 20.0), 4) if max_polyphony else 0.0
    total_penalty = round(min(muddy_penalty + dense_penalty, 20.0), 4)

    return total_penalty, {
        "track_used":      chords_track.name,
        "muddy_clusters":  muddy_clusters,
        "dense_clusters":  dense_clusters,
        "low_threshold":   low_threshold,
        "max_polyphony":   max_polyphony if max_polyphony else "unlimited",
        "penalty":         total_penalty,
    }


# ── Penalty 4 — Motif Repetition (max 25 pts) ────────────────────────────────

_MOTIF_TARGET_MIN = 0.03   # repetition score below this = chaotic, no motif
# Calibrated from 0.25 → 0.10 → 0.03: Markov-chain trap/hip-hop progressions
# explore 32 unique bars; nearly all 4-grams are distinct (repetition≈0).
# 0.03 only penalises truly zero-structure sequences, not creative variation.

def _motif_repetition_penalty(chords: List[str], ngram: int = 2, cfg=None) -> Tuple[float, dict]:
    """
    4-gram uniqueness analysis on the chord progression.
    repetition_score = 1 − (unique_4grams / total_4grams).
    Penalty = linear from 0 (score ≥ 0.25) to 25 (score = 0).
    """
    if len(chords) < ngram * 2:
        return 0.0, {"repetition_score": None, "penalty": 0.0, "note": "insufficient_data"}

    grams       = [tuple(chords[i:i+ngram]) for i in range(len(chords) - ngram + 1)]
    unique_ratio = len(set(grams)) / len(grams)
    repetition   = 1.0 - unique_ratio

    min_rep = cfg.motif_min_repetition if cfg else _MOTIF_TARGET_MIN

    if repetition < min_rep:
        penalty = (((min_rep - repetition) / min_rep)) * 25.0
    else:
        penalty = 0.0

    penalty = round(min(penalty, 25.0), 4)
    return penalty, {
        "ngram_size":       ngram,
        "total_ngrams":     len(grams),
        "unique_ngrams":    len(set(grams)),
        "repetition_score": round(repetition, 4),
        "target_min":       min_rep,
        "penalty":          penalty,
    }


# ── Penalty 5 — Melodic Range (max 5 pts) ────────────────────────────────────

_RANGE_MIN = 7    # semitones — narrower = too flat
_RANGE_MAX = 48   # semitones — wider = too erratic (4 octaves)

def _melodic_range_penalty(tracks: List[_Track]) -> Tuple[float, dict]:
    """Small guard: melody span should fall within 7–48 semitones."""
    melody = next(
        (t for t in tracks if 'melody' in t.name.lower() and t.is_pitched), None
    )
    if melody is None or not melody.notes:
        return 0.0, {"range_semitones": None, "penalty": 0.0}

    pitches = [p for _, p, _ in melody.notes]
    span    = max(pitches) - min(pitches)
    penalty = 5.0 if (span < _RANGE_MIN or span > _RANGE_MAX) else 0.0
    return round(penalty, 4), {
        "range_semitones": span,
        "min_pitch":       min(pitches),
        "max_pitch":       max(pitches),
        "penalty":         round(penalty, 4),
    }


# ── God Mode checks (bonus points, max +15) ──────────────────────────────────

_GM_VEL_DEPTH_MIN  = 15.0   # benchmark: macro_dynamics.velocity_lfo_depth_min
_GM_VEL_DEPTH_MAX  = 25.0   # benchmark: macro_dynamics.velocity_lfo_depth_max
_GM_WINDOW_BARS    = 32     # sliding-window size in bars
_GM_DELTA_TARGET   = 4.5    # ms: benchmark humanization.timing_delta_ms_avg
_GM_DELTA_TOLERANCE = 1.5   # acceptable ±ms around target


_CH_MELODY  = 1   # 04_Melody
_CH_CHORDS  = 2   # 05_Chords
_CH_PAD     = 3   # 06_Pad
_CH_TEXTURE = 6   # 09_Texture


def _gm_macro_dynamics(
    tracks: List[_Track], tpb: int, bpm: float,
) -> Tuple[float, dict]:
    """
    Check 1 — Macro-Dynamics: over a 32-bar sliding window on the chords/pad
    track, the range (max_vel – min_vel) should fall in [15.0, 25.0].
    Bonus: +5 if passing, 0 otherwise.
    """
    target = (
        next((t for t in tracks if 'chord' in t.name.lower() and t.is_pitched), None)
        or next((t for t in tracks if 'pad'   in t.name.lower() and t.is_pitched), None)
        or next((t for t in tracks if t.channel == _CH_CHORDS   and t.is_pitched), None)
        or next((t for t in tracks if t.channel == _CH_PAD      and t.is_pitched), None)
    )
    if target is None or not target.notes:
        return 0.0, {"status": "no_chords_or_pad_track", "bonus": 0.0}

    bar_ticks = tpb * 4
    seg_bars  = 4                           # average velocity over 4-bar segments
    seg_ticks = bar_ticks * seg_bars
    max_tick  = max(tick for tick, _, _ in target.notes) + 1

    # Compute mean velocity per 4-bar segment (smoothes out per-note spikes)
    seg_means: List[float] = []
    pos = 0
    while pos + seg_ticks <= max_tick:
        vels = [v for (tick, _, v) in target.notes if pos <= tick < pos + seg_ticks]
        if len(vels) >= 4:
            seg_means.append(sum(vels) / len(vels))
        pos += seg_ticks

    win_segs = _GM_WINDOW_BARS // seg_bars  # 32 / 4 = 8 segments per window
    if len(seg_means) < win_segs:
        return 0.0, {"status": "insufficient_data", "bonus": 0.0}

    # Sliding window: LFO depth = swing of the segment means within each 32-bar window
    depths: List[float] = []
    for i in range(len(seg_means) - win_segs + 1):
        w = seg_means[i: i + win_segs]
        depths.append(max(w) - min(w))

    avg_depth = sum(depths) / len(depths)
    passing   = _GM_VEL_DEPTH_MIN <= avg_depth <= _GM_VEL_DEPTH_MAX
    bonus     = 5.0 if passing else 0.0
    return bonus, {
        "avg_velocity_lfo_depth": round(avg_depth, 3),
        "target_range":           [_GM_VEL_DEPTH_MIN, _GM_VEL_DEPTH_MAX],
        "segments_analyzed":      len(seg_means),
        "windows_analyzed":       len(depths),
        "passing":                passing,
        "bonus":                  bonus,
    }


def _gm_polyrhythmic_integrity(tracks: List[_Track], tpb: int) -> Tuple[float, dict]:
    """
    Check 2 — Polyrhythmic Integrity: the 09_Texture track rotates 4 steps/bar
    in a 35-step prime-Euclidean pattern, so bars 1 and 9 must be mathematically
    distinct.
    Bonus: +5 if distinct, 0 if identical.
    """
    texture = (
        next((t for t in tracks if 'texture' in t.name.lower() and t.is_pitched), None)
        or next((t for t in tracks if t.channel == _CH_TEXTURE  and t.is_pitched), None)
    )
    if texture is None or not texture.notes:
        return 0.0, {"status": "no_texture_track", "bonus": 0.0}

    bar_ticks = tpb * 4
    first_bar = min(tick for tick, _, _ in texture.notes) // bar_ticks
    cmp_bar   = first_bar + 8   # bar 1 vs bar 9 (0-indexed gap = 8)

    def _bar_pattern(bar_idx: int) -> frozenset:
        lo = bar_idx * bar_ticks
        hi = lo + bar_ticks
        return frozenset(
            (tick - lo) for tick, _, _ in texture.notes if lo <= tick < hi
        )

    pat_a = _bar_pattern(first_bar)
    pat_b = _bar_pattern(cmp_bar)

    if not pat_a or not pat_b:
        return 0.0, {"status": "insufficient_bars", "bonus": 0.0}

    distinct = pat_a != pat_b
    bonus    = 5.0 if distinct else 0.0
    return bonus, {
        "bars_compared":     [int(first_bar + 1), int(cmp_bar + 1)],
        "bar_a_note_count":  len(pat_a),
        "bar_b_note_count":  len(pat_b),
        "patterns_distinct": distinct,
        "bonus":             bonus,
    }


def _gm_humanization_delta(
    tracks: List[_Track], tpb: int, bpm: float, cfg=None,
) -> Tuple[float, dict]:
    """
    Check 3 — Humanization Delta: average deviation of melody note-on times
    from the perfect 16th-note grid should be near the genre target (±tolerance).
    Target varies: Pop/EDM = 1.5 ms (quantized), House = 3.0 ms (swung), Trap = 4.5 ms.
    Bonus: +5 if within tolerance, 0 otherwise.
    """
    delta_target    = cfg.humanization_delta_target_ms    if cfg else _GM_DELTA_TARGET
    delta_tolerance = cfg.humanization_delta_tolerance_ms if cfg else _GM_DELTA_TOLERANCE
    melody = (
        next((t for t in tracks if 'melody' in t.name.lower() and t.is_pitched), None)
        or next((t for t in tracks if t.channel == _CH_MELODY   and t.is_pitched), None)
    )

    if melody is None or len(melody.notes) < 4:
        return 0.0, {"status": "insufficient_data", "bonus": 0.0}

    grid_ticks   = tpb / 4.0                      # 16th-note grid step
    ticks_per_ms = (bpm * tpb) / 60_000.0         # ticks → ms

    deltas_ms = []
    for tick, _, _ in melody.notes:
        nearest   = round(tick / grid_ticks) * grid_ticks
        delta_ms  = abs(tick - nearest) / ticks_per_ms if ticks_per_ms > 0 else 0.0
        deltas_ms.append(delta_ms)

    avg_delta = sum(deltas_ms) / len(deltas_ms)
    passing   = abs(avg_delta - delta_target) <= delta_tolerance
    bonus     = 5.0 if passing else 0.0
    return bonus, {
        "avg_delta_ms":   round(avg_delta, 3),
        "target_ms":      delta_target,
        "tolerance_ms":   delta_tolerance,
        "notes_measured": len(deltas_ms),
        "passing":        passing,
        "bonus":          bonus,
    }


# ── Master fitness function ───────────────────────────────────────────────────

def calculate_midi_fitness(
    metadata:  dict,
    midi_path: Optional[Path] = None,
) -> Tuple[float, dict]:
    """
    Score one track on pure math-music-theory. Returns (score, breakdown).

    Penalty budget (base = 100):
        Scale Adherence      35 pts  (heavy)
        Rhythmic Variance    20 pts  (medium)
        Chord Density        20 pts  (medium)
        Motif Repetition     25 pts  (high)
        Melodic Range         5 pts  (guard)

    God Mode bonus (max +15):
        Macro-Dynamics        +5 pts  (velocity LFO depth in [15, 25])
        Polyrhythmic Integrity+5 pts  (bar 1 ≠ bar 9 on texture track)
        Humanization Delta    +5 pts  (avg timing offset ≈ 4.5 ms)
    """
    params = metadata.get("generation_params", {})
    chords = metadata.get("chord_progression", [])

    root  = params.get("root",  "C")
    scale = params.get("scale", "major")
    bpm   = float(params.get("bpm", 120.0))
    genre = params.get("genre", metadata.get("genre", "")).lower()
    scale_pcs = _pitch_class_set(root, scale)

    # Load genre-specific grader config (falls back to global defaults if unavailable)
    cfg = get_grader_config(genre) if _GENRE_CONFIG_AVAILABLE and genre else None

    # Load MIDI — preserve tpb for God Mode timing checks
    tracks: List[_Track] = []
    tpb: int = 480
    if midi_path and midi_path.exists() and _MIDO_OK:
        try:
            tpb, tracks = _parse_midi(midi_path)
        except Exception as exc:
            tracks = []
            print(f"    [WARN] MIDI parse error {midi_path.name}: {exc}")

    total_penalty = 0.0
    breakdown: dict = {}

    p1, d1 = _scale_penalty(tracks, scale_pcs, cfg)
    breakdown["scale_adherence"]   = d1;  total_penalty += p1

    p2, d2 = _rhythmic_variance_penalty(tracks, cfg)
    breakdown["rhythmic_variance"] = d2;  total_penalty += p2

    p3, d3 = _chord_density_penalty(tracks, cfg)
    breakdown["chord_density"]     = d3;  total_penalty += p3

    p4, d4 = _motif_repetition_penalty(chords, ngram=2, cfg=cfg)
    breakdown["motif_repetition"]  = d4;  total_penalty += p4

    p5, d5 = _melodic_range_penalty(tracks)
    breakdown["melodic_range"]     = d5;  total_penalty += p5

    # God Mode validation — three checks on the mathematical guarantees
    gm1_bonus, gm1 = _gm_macro_dynamics(tracks, tpb, bpm)
    gm2_bonus, gm2 = _gm_polyrhythmic_integrity(tracks, tpb)
    gm3_bonus, gm3 = _gm_humanization_delta(tracks, tpb, bpm, cfg)
    god_mode_bonus  = gm1_bonus + gm2_bonus + gm3_bonus
    breakdown["god_mode"] = {
        "macro_dynamics":         gm1,
        "polyrhythmic_integrity": gm2,
        "humanization_delta":     gm3,
        "total_bonus":            god_mode_bonus,
    }

    base_score = round(max(0.0, 100.0 - total_penalty), 4)
    return round(base_score + god_mode_bonus, 4), breakdown


# ── Per-genre sweep ───────────────────────────────────────────────────────────

def _process_genre(genre_dir: Path) -> dict:
    results = []

    for track_dir in sorted(p for p in genre_dir.iterdir() if p.is_dir()):
        meta_path = track_dir / "generation_metadata.json"
        if not meta_path.exists():
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        rel_midi  = meta.get("outputs", {}).get("midi_path")
        midi_path = (genre_dir / rel_midi) if rel_midi else None

        score, breakdown = calculate_midi_fitness(meta, midi_path)
        results.append({
            "track_name": track_dir.name,
            "score":      score,
            "breakdown":  breakdown,
            "metadata":   meta,
        })

    results.sort(key=lambda r: r["score"], reverse=True)

    leaderboard = [
        {
            "rank":              i + 1,
            "track_name":        r["track_name"],
            "score":             r["score"],
            "generation_params": r["metadata"].get("generation_params", {}),
            "penalties": {
                "scale_adherence":  r["breakdown"].get("scale_adherence",   {}).get("penalty", 0),
                "rhythmic_variance":r["breakdown"].get("rhythmic_variance",  {}).get("penalty", 0),
                "chord_density":    r["breakdown"].get("chord_density",      {}).get("penalty", 0),
                "motif_repetition": r["breakdown"].get("motif_repetition",   {}).get("penalty", 0),
                "melodic_range":    r["breakdown"].get("melodic_range",      {}).get("penalty", 0),
            },
        }
        for i, r in enumerate(results)
    ]

    golden_matrices = [
        {
            "rank":              i + 1,
            "track_name":        r["track_name"],
            "score":             r["score"],
            "generation_params": r["metadata"].get("generation_params", {}),
            "seed_info":         r["metadata"].get("seed_info", {}),
            "structure":         r["metadata"].get("structure", []),
            "chord_progression": r["metadata"].get("chord_progression", [])[:16],
            "breakdown":         r["breakdown"],
        }
        for i, r in enumerate(results[:5])
    ]

    return {
        "genre":           genre_dir.name,
        "tracks_scored":   len(results),
        "leaderboard":     leaderboard,
        "golden_matrices": golden_matrices,
    }


# ── Root sweep ────────────────────────────────────────────────────────────────

def run_grader(batch_dir: str) -> None:
    batch_path = Path(batch_dir)
    if not batch_path.exists():
        print(f"[ERROR] batch_dir not found: {batch_path}")
        return

    genre_dirs = sorted(p for p in batch_path.iterdir() if p.is_dir())
    if not genre_dirs:
        print(f"[ERROR] No subfolders found in '{batch_dir}'")
        return

    if not _MIDO_OK:
        print("[WARN] mido not installed — MIDI analysis disabled; install with: pip install mido")

    total_tracks = sum(
        sum(1 for p in g.iterdir() if p.is_dir() and (p / "generation_metadata.json").exists())
        for g in genre_dirs
    )

    print(f"MIDI Fitness Grader  |  {len(genre_dirs)} genres  |  ~{total_tracks} tracks")
    print("=" * 65)

    for genre_dir in genre_dirs:
        report = _process_genre(genre_dir)
        n      = report["tracks_scored"]
        genre  = report["genre"].upper()
        top5   = report["leaderboard"][:5]

        print(f"\n  [{genre}]  {n} tracks scored")
        print(f"  {'Rank':<5} {'Track':<14} {'Score':>7}  "
              f"{'ScaleErr':>9}  {'CV':>6}  {'Muddy':>6}  {'Motif':>7}  {'GodMode':>7}")
        print(f"  {'-'*68}")
        for e in top5:
            pen = e["penalties"]
            bd  = report["golden_matrices"][e["rank"] - 1]["breakdown"] \
                  if e["rank"] <= 5 else {}
            cv_val   = bd.get("rhythmic_variance", {}).get("cv", "-")
            err_rate = bd.get("scale_adherence",   {}).get("out_of_scale_rate", "-")
            gm_bonus = bd.get("god_mode", {}).get("total_bonus", 0.0)
            print(
                f"  #{e['rank']:<4} {e['track_name']:<14} {e['score']:>7.2f}"
                f"  {str(err_rate):>9}  {str(cv_val):>6}"
                f"  {pen['chord_density']:>6.1f}  {pen['motif_repetition']:>7.1f}"
                f"  +{gm_bonus:>5.1f}"
            )

        report_path = genre_dir / "math_fitness_report.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"\n  -> {report_path}")

    print("\n" + "=" * 65)
    print("Grading complete.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="telemetry_grader_midi",
        description="Music Architect — mathematical MIDI fitness grader",
    )
    parser.add_argument(
        "--batch-dir", default="./batch_output", dest="batch_dir",
        help="Root directory containing genre subfolders (default: ./batch_output)",
    )
    args = parser.parse_args()
    run_grader(args.batch_dir)


if __name__ == "__main__":
    main()
