"""
src/midi/genre_profiles.py
──────────────────────────
Genre profile dataclass and library for the hybrid beat/sound generator.

Each ``GenreProfile`` captures every musical and signal-processing parameter
that defines a genre archetype: timing feel, harmony, dynamics, saturation,
reverb, LFO behaviour, and more.  The ``GenreProfileLibrary`` provides
look-up by genre+BPM, archetype ID, and utility conversion helpers.

Usage::

    lib = GenreProfileLibrary()
    profile = lib.get("trap", 138.0)
    pre_delay_ms = lib.compute_pre_delay_ms(profile, 138.0)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class GenreProfile:
    """
    Full parameter set describing a single genre archetype.

    Fields are grouped by concern:
      - Identity      : genre, archetype_id, label, BPM range, meter
      - Timing        : swing, jitter, velocity range and curve
      - Harmony       : voice leading, modes, modal interchange, chord extensions
      - Arrangement   : section_bars, fill density/types, transition type
      - Signal chain  : saturation, reverb, stereo width
      - Modulation    : LFO targets, rate range, waveform
    """
    # ── Identity ─────────────────────────────────────────────────────────────
    genre: str
    archetype_id: str           # e.g. "midtempo", "dance_pop"
    label: str
    bpm_min: int
    bpm_max: int
    bpm_default: int
    meter: str                  # "4/4", "4/4_halftime", "3/4", "6/8"
    meter_alternates: List[str]

    # ── Timing / Feel ─────────────────────────────────────────────────────────
    swing_pct_min: float
    swing_pct_max: float
    jitter_ms_max: float
    velocity_min: int
    velocity_max: int
    velocity_curve: str         # name looked up in MicroTimingEngine

    # ── Harmony ──────────────────────────────────────────────────────────────
    voice_leading_strictness: str   # "classical", "strict", "moderate", "loose", "none"
    allowed_parallels: List[str]
    primary_modes: List[str]
    modal_interchange: bool
    modal_interchange_chords: List[str]
    mediants: bool
    chord_extension_level: str
    max_voice_jump_semitones: int

    # ── Arrangement ──────────────────────────────────────────────────────────
    section_bars: Dict[str, int]
    fill_density: str           # "none","very_sparse","sparse","moderate","dense","dense_in_build"
    fill_types: List[str]
    transition_type: str
    subtraction_enabled: bool

    # ── Signal Chain ──────────────────────────────────────────────────────────
    saturation_type: str        # "none","tape_soft","tube_tanh","hard_clip", …
    drive_pct_min: float
    drive_pct_max: float
    reverb_size: str
    reverb_decay_s_min: float
    reverb_decay_s_max: float
    pre_delay_note_fraction: float  # 0.25=quarter, 0.125=eighth, 0.0625=sixteenth
    stereo_width: str

    # ── Modulation ────────────────────────────────────────────────────────────
    lfo_targets: List[str]
    lfo_rate_bars_min: float
    lfo_rate_bars_max: float
    lfo_waveform: str           # "sine","sample_hold","random_ramp","square","none"


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

class GenreProfileLibrary:
    """
    Repository of all 22 genre archetype profiles.

    Lookup order in ``get(genre, bpm)``:
      1. Find all archetypes for the genre.
      2. Among those whose [bpm_min, bpm_max] contains ``bpm``, return the one
         whose bpm_default is closest to ``bpm``.
      3. If none contains the BPM, fall back to the archetype with the
         nearest bpm_default overall (useful for extreme BPMs).
    """

    def __init__(self) -> None:
        # Build the flat list then index it.
        self._profiles: List[GenreProfile] = _build_all_profiles()
        # genre -> list of profiles
        self._by_genre: Dict[str, List[GenreProfile]] = {}
        for p in self._profiles:
            self._by_genre.setdefault(p.genre, []).append(p)

    # ------------------------------------------------------------------
    # Public look-up API
    # ------------------------------------------------------------------

    def get(self, genre: str, bpm: float) -> GenreProfile:
        """
        Return the best-matching archetype for *genre* at *bpm*.

        Falls back to nearest bpm_default if no archetype's range contains
        the requested BPM.
        """
        candidates = self._by_genre.get(genre)
        if not candidates:
            # Unknown genre — fall back to pop/midtempo as a safe default.
            candidates = self._by_genre.get("pop", self._profiles[:1])

        # Prefer profiles whose range contains the BPM.
        in_range = [p for p in candidates if p.bpm_min <= bpm <= p.bpm_max]
        pool = in_range if in_range else candidates

        # Among the pool, pick the one closest to the given BPM.
        return min(pool, key=lambda p: abs(p.bpm_default - bpm))

    def get_by_archetype(self, genre: str, archetype_id: str) -> GenreProfile:
        """Return a specific archetype by genre + archetype_id string."""
        for p in self._by_genre.get(genre, []):
            if p.archetype_id == archetype_id:
                return p
        raise KeyError(f"Archetype '{archetype_id}' not found for genre '{genre}'.")

    def list_genres(self) -> List[str]:
        """Return a sorted list of all available genre keys."""
        return sorted(self._by_genre.keys())

    def list_archetypes(self, genre: str) -> List[str]:
        """Return archetype_id strings for all profiles of *genre*."""
        return [p.archetype_id for p in self._by_genre.get(genre, [])]

    # ------------------------------------------------------------------
    # Helper computations
    # ------------------------------------------------------------------

    def compute_pre_delay_ms(self, profile: GenreProfile, bpm: float) -> float:
        """
        Convert the profile's pre_delay_note_fraction to milliseconds.

        Formula: (60_000 ms / bpm) * note_fraction
        E.g. 1/16 note at 138 BPM = (60000/138) * 0.0625 ≈ 27.2 ms.
        """
        beat_ms = 60_000.0 / max(bpm, 1.0)
        return beat_ms * profile.pre_delay_note_fraction

    def compute_lfo_rate_hz(
        self, profile: GenreProfile, rate_bars: float, bpm: float
    ) -> float:
        """
        Convert a bar-count LFO period to a frequency in Hz.

        Formula: 1.0 / (rate_bars × beats_per_bar × beat_duration_s)
        Assumes 4 beats per bar (all profiles use 4/4 or 4/4_halftime
        for this calculation, with 6/8 treated as a bar of 6 quavers ≈ 2 beats
        but kept at 4 for simplicity).
        """
        if rate_bars <= 0.0 or bpm <= 0.0:
            return 0.0
        beat_s = 60.0 / bpm
        bar_s = rate_bars * 4.0 * beat_s
        return 1.0 / bar_s

    def compute_swing_extra_ms(self, profile: GenreProfile, bpm: float) -> float:
        """
        Compute the additional delay applied to the off-beat 16th note at
        *swing_pct_max* swing.

        At 50 % swing the off-beat lands exactly on the 16th note grid
        (no extra delay).  At 66.67 % it lands on the triplet subdivision.

        Formula:
            16th_note_ms = (60_000 / bpm) / 4
            swing_extra  = 16th_note_ms × 2 × (swing_pct_max/100 − 0.5)
        """
        sixteenth_ms = (60_000.0 / max(bpm, 1.0)) / 4.0
        extra_fraction = profile.swing_pct_max / 100.0 - 0.5
        return sixteenth_ms * 2.0 * extra_fraction


# ---------------------------------------------------------------------------
# Internal profile construction
# ---------------------------------------------------------------------------

def _p(  # noqa: PLR0913 — one factory call per archetype is intentional
    genre: str,
    archetype_id: str,
    label: str,
    bpm_min: int,
    bpm_max: int,
    bpm_default: int,
    meter: str,
    meter_alternates: List[str],
    swing_pct_min: float,
    swing_pct_max: float,
    jitter_ms_max: float,
    velocity_min: int,
    velocity_max: int,
    velocity_curve: str,
    voice_leading_strictness: str,
    allowed_parallels: List[str],
    primary_modes: List[str],
    modal_interchange: bool,
    modal_interchange_chords: List[str],
    mediants: bool,
    chord_extension_level: str,
    max_voice_jump_semitones: int,
    section_bars: Dict[str, int],
    fill_density: str,
    fill_types: List[str],
    transition_type: str,
    subtraction_enabled: bool,
    saturation_type: str,
    drive_pct_min: float,
    drive_pct_max: float,
    reverb_size: str,
    reverb_decay_s_min: float,
    reverb_decay_s_max: float,
    pre_delay_note_fraction: float,
    stereo_width: str,
    lfo_targets: List[str],
    lfo_rate_bars_min: float,
    lfo_rate_bars_max: float,
    lfo_waveform: str,
) -> GenreProfile:
    """Thin wrapper so the profile list stays readable."""
    return GenreProfile(
        genre=genre,
        archetype_id=archetype_id,
        label=label,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        bpm_default=bpm_default,
        meter=meter,
        meter_alternates=meter_alternates,
        swing_pct_min=swing_pct_min,
        swing_pct_max=swing_pct_max,
        jitter_ms_max=jitter_ms_max,
        velocity_min=velocity_min,
        velocity_max=velocity_max,
        velocity_curve=velocity_curve,
        voice_leading_strictness=voice_leading_strictness,
        allowed_parallels=allowed_parallels,
        primary_modes=primary_modes,
        modal_interchange=modal_interchange,
        modal_interchange_chords=modal_interchange_chords,
        mediants=mediants,
        chord_extension_level=chord_extension_level,
        max_voice_jump_semitones=max_voice_jump_semitones,
        section_bars=section_bars,
        fill_density=fill_density,
        fill_types=fill_types,
        transition_type=transition_type,
        subtraction_enabled=subtraction_enabled,
        saturation_type=saturation_type,
        drive_pct_min=drive_pct_min,
        drive_pct_max=drive_pct_max,
        reverb_size=reverb_size,
        reverb_decay_s_min=reverb_decay_s_min,
        reverb_decay_s_max=reverb_decay_s_max,
        pre_delay_note_fraction=pre_delay_note_fraction,
        stereo_width=stereo_width,
        lfo_targets=lfo_targets,
        lfo_rate_bars_min=lfo_rate_bars_min,
        lfo_rate_bars_max=lfo_rate_bars_max,
        lfo_waveform=lfo_waveform,
    )


def _build_all_profiles() -> List[GenreProfile]:
    """
    Construct the full list of 22 archetype profiles.

    Note fractions: 0.25 = quarter note, 0.125 = eighth, 0.0625 = sixteenth,
    0.03125 = thirty-second.
    """
    return [
        # ── POP ──────────────────────────────────────────────────────────────
        _p("pop", "midtempo", "Pop – Midtempo",
           80, 110, 96, "4/4", [],
           51.0, 55.0, 14.0, 58, 110, "downbeat_backbeat_accent",
           "moderate", [],
           ["major", "mixolydian"], True, ["bVII", "iv", "bVI"],
           False, "7ths", 4,
           {"intro": 8, "verse": 8, "pre_chorus": 4, "chorus": 8,
            "bridge": 8, "outro": 4},
           "moderate", ["drum_fill_2bar", "hat_variation"],
           "drum_fill_into_chorus", True,
           "tape_soft", 2.0, 5.0,
           "medium", 1.8, 2.8, 0.0625, "moderate",
           ["pad_filter_cutoff", "chorus_width"], 8.0, 24.0, "sine"),

        _p("pop", "dance_pop", "Pop – Dance Pop",
           116, 132, 124, "4/4", [],
           50.0, 51.5, 7.0, 72, 122, "compressed_high_energy",
           "moderate", [],
           ["major", "lydian"], False, [],
           False, "sus_and_add", 5,
           {"intro": 8, "verse": 8, "pre_chorus": 4, "chorus": 16,
            "drop": 8, "outro": 8},
           "moderate", ["snare_roll", "tacet_1beat"],
           "snare_roll_then_silence_into_drop", True,
           "tape_soft", 1.5, 4.0,
           "small", 0.8, 1.5, 0.03125, "wide",
           ["synth_pitch_drift", "filter_cutoff_buildup"], 16.0, 32.0, "random_ramp"),

        _p("pop", "ballad", "Pop – Ballad",
           60, 80, 72, "4/4", [],
           50.0, 52.0, 22.0, 35, 105, "swell_dynamic",
           "strict", [],
           ["major", "natural_minor"], True, ["bVI", "bVII", "iv"],
           False, "extended", 3,
           {"intro": 4, "verse": 16, "pre_chorus": 4, "chorus": 8,
            "bridge": 8, "outro": 8},
           "sparse", ["hat_variation", "piano_run"],
           "velocity_swell_into_chorus", False,
           "none", 0.0, 1.5,
           "large", 2.5, 4.0, 0.125, "moderate",
           ["reverb_size", "pad_filter_cutoff"], 16.0, 48.0, "sine"),

        # ── HIP-HOP ──────────────────────────────────────────────────────────
        _p("hiphop", "boom_bap", "Hip-Hop – Boom Bap",
           84, 100, 92, "4/4", [],
           56.0, 66.0, 20.0, 48, 102, "mpc_dilla_groove",
           "loose", [],
           ["natural_minor", "dorian", "phrygian"],
           True, ["bVII", "IV_from_minor", "tritone_sub"],
           False, "jazz_extended", 7,
           {"intro": 4, "verse": 16, "hook": 8, "break": 8, "outro": 4},
           "sparse", ["hat_variation", "breakdown", "vinyl_skip"],
           "hat_pattern_change", True,
           "vinyl_tape", 6.0, 14.0,
           "medium", 1.5, 2.5, 0.0625, "narrow",
           ["vinyl_flutter_pitch", "pad_filter_cutoff"], 4.0, 16.0, "sample_hold"),

        _p("hiphop", "lofi_chill", "Hip-Hop – Lo-Fi Chill",
           68, 86, 76, "4/4", [],
           58.0, 70.0, 26.0, 38, 88, "dilla_loose",
           "loose", [],
           ["dorian", "lydian", "natural_minor"],
           True, ["III_major", "bVI_maj7", "tritone_sub"],
           False, "jazz_extended", 9,
           {"loop_a": 8, "loop_b": 8, "transition": 4},
           "very_sparse", ["hat_variation", "vinyl_skip", "drum_fill_1bar"],
           "organic_hat_shift", False,
           "vinyl_tape", 10.0, 20.0,
           "medium", 2.0, 3.5, 0.0625, "narrow_to_moderate",
           ["vinyl_flutter_pitch", "filter_lowpass_cutoff", "reverb_size"],
           6.0, 24.0, "sample_hold"),

        # ── TRAP ─────────────────────────────────────────────────────────────
        _p("trap", "standard_halftime", "Trap – Standard Halftime",
           128, 148, 138, "4/4_halftime", [],
           50.0, 54.0, 12.0, 60, 127, "trap_hat_stagger",
           "loose", [],
           ["phrygian", "phrygian_dominant", "natural_minor"],
           False, [], False, "triads", 12,
           {"intro_808_only": 4, "verse": 16, "hook": 8, "outro": 4},
           "sparse", ["hat_triplet_roll", "808_slide", "snare_buildup"],
           "hat_acceleration_into_hook", True,
           "asymmetric_soft", 8.0, 18.0,
           "small", 0.6, 1.2, 0.03125, "mono_bass_wide_hats",
           ["hat_filter_cutoff", "808_portamento_depth"], 2.0, 8.0, "sample_hold"),

        _p("trap", "fast_dark", "Trap – Fast Dark",
           150, 180, 162, "4/4", [],
           50.0, 51.5, 7.0, 82, 127, "aggressive_flat",
           "none", [],
           ["phrygian", "locrian", "chromatic"],
           False, [], False, "chromatic_clusters", 24,
           {"intro": 4, "verse": 8, "hook": 4, "break": 4},
           "moderate", ["snare_roll", "tacet_1beat", "stutter"],
           "abrupt_section_cut", False,
           "hard_clip", 15.0, 35.0,
           "small", 0.4, 0.9, 0.03125, "mono_dominant",
           ["distortion_drive", "reverb_gating"], 1.0, 4.0, "sample_hold"),

        # ── CINEMATIC ────────────────────────────────────────────────────────
        _p("cinematic", "slow_orchestral", "Cinematic – Slow Orchestral",
           40, 72, 56, "4/4", ["3/4", "6/8"],
           50.0, 50.0, 38.0, 18, 122, "orchestral_swell",
           "classical", [],
           ["aeolian", "dorian", "lydian", "phrygian"],
           True, ["chromatic_mediant", "neapolitan", "augmented_6th"],
           True, "extended", 2,
           {"intro": 16, "theme_a": 32, "development": 24,
            "climax": 16, "resolution": 16, "outro": 8},
           "none", ["orchestral_riser", "tacet_grand_pause"],
           "string_crescendo_into_tutti", True,
           "none", 0.0, 1.5,
           "hall", 4.0, 8.0, 0.125, "very_wide",
           ["string_vibrato_depth", "reverb_pre_delay", "pad_filter_cutoff"],
           8.0, 48.0, "sine"),

        _p("cinematic", "epic_action", "Cinematic – Epic Action",
           120, 160, 140, "4/4", ["5/4", "7/8"],
           50.0, 50.0, 14.0, 68, 127, "downbeat_accent_aggressive",
           "strict", [],
           ["natural_minor", "phrygian", "diminished"],
           True, ["tritone_sub", "augmented_chord", "pedal_point"],
           True, "power_and_extended", 3,
           {"intro": 8, "theme": 16, "buildup": 16,
            "climax": 8, "stinger": 4, "resolution": 8},
           "dense",
           ["orchestral_riser", "drum_fill_2bar",
            "timpani_roll", "tacet_grand_pause"],
           "tutti_impact_followed_by_silence", True,
           "tape_soft", 3.0, 8.0,
           "large", 2.5, 5.0, 0.0625, "very_wide",
           ["reverb_size", "brass_filter_cutoff", "string_tremolo_rate"],
           4.0, 16.0, "random_ramp"),

        # ── CLASSICAL ────────────────────────────────────────────────────────
        _p("classical", "adagio", "Classical – Adagio",
           40, 76, 60, "4/4", ["3/4", "6/8", "9/8"],
           50.0, 50.0, 48.0, 12, 115, "orchestral_swell",
           "classical", [],
           ["major", "natural_minor", "dorian"],
           True,
           ["neapolitan_6th", "augmented_6th_german",
            "augmented_6th_french", "borrowed_iv"],
           False, "triads_and_7ths", 2,
           {"exposition": 24, "development": 16,
            "recapitulation": 24, "coda": 8},
           "none", ["ornament_trill", "ornament_mordent"],
           "dominant_pedal_into_recapitulation", False,
           "none", 0.0, 0.0,
           "concert_hall", 3.0, 6.0, 0.125, "wide_natural",
           [], 0.0, 0.0, "none"),

        _p("classical", "allegro", "Classical – Allegro",
           120, 200, 152, "4/4", ["3/4", "2/2"],
           50.0, 50.0, 14.0, 48, 118, "forte_accent_downbeats",
           "classical", [],
           ["major", "natural_minor"],
           False, [], False, "triads_and_diminished7", 2,
           {"exposition": 16, "development": 24,
            "recapitulation": 16, "coda": 8},
           "none", ["ornament_trill", "ornament_turn"],
           "diminished7_modulation", False,
           "none", 0.0, 0.0,
           "concert_hall", 2.0, 4.0, 0.0625, "wide_natural",
           [], 0.0, 0.0, "none"),

        # ── TECHNO ───────────────────────────────────────────────────────────
        _p("techno", "melodic_peak_time", "Techno – Melodic Peak Time",
           128, 138, 132, "4/4", [],
           50.0, 52.5, 7.0, 85, 127, "compressed_kick_accent",
           "moderate", [],
           ["aeolian", "dorian", "phrygian"],
           False, [], False, "7ths", 5,
           {"intro": 16, "main_groove": 32, "breakdown": 16,
            "buildup": 16, "drop": 32, "outro": 16},
           "very_sparse",
           ["hat_variation", "filter_sweep", "sub_bass_drop"],
           "subtraction_then_filter_sweep", True,
           "tube_tanh", 2.0, 6.0,
           "medium", 1.5, 2.5, 0.0625, "moderate_wide",
           ["main_synth_filter_cutoff", "reverb_size", "pad_chorus_depth"],
           4.0, 16.0, "sample_hold"),

        _p("techno", "hard_industrial", "Techno – Hard Industrial",
           140, 158, 148, "4/4", [],
           50.0, 50.0, 4.0, 100, 127, "wall_of_sound",
           "none", [],
           ["phrygian_dominant", "atonal", "chromatic_clusters"],
           False, [], False, "noise_and_clusters", 24,
           {"intro": 16, "main": 32, "break": 8,
            "main_return": 32, "outro": 8},
           "sparse",
           ["abrupt_silence", "stutter", "noise_burst"],
           "abrupt_cut_then_reentry", True,
           "hard_clip", 20.0, 45.0,
           "small_metallic", 0.3, 0.8, 0.03125, "mono_dominant",
           ["distortion_drive", "noise_gate_threshold", "pitch_drift"],
           1.0, 4.0, "sample_hold"),

        # ── J-POP ─────────────────────────────────────────────────────────────
        _p("jpop", "idol_dance_pop", "J-Pop – Idol Dance Pop",
           118, 136, 126, "4/4", [],
           50.5, 53.0, 9.0, 65, 116, "j_pop_bright",
           "strict", [],
           ["major", "lydian", "mixolydian"],
           True, ["IV_minor", "bVI", "bVII"],
           False, "extended", 3,
           {"intro": 8, "verse": 8, "pre_chorus": 4, "chorus_sabi": 8,
            "verse_2": 8, "bridge": 8, "final_chorus": 16, "outro": 4},
           "moderate",
           ["snare_roll", "synth_arp_fill", "drum_fill_1bar"],
           "snare_fill_into_sabi", False,
           "tape_soft", 1.5, 4.0,
           "small", 0.9, 1.6, 0.03125, "wide",
           ["synth_chorus_width", "pad_filter_cutoff"], 8.0, 32.0, "sine"),

        _p("jpop", "anime_rock", "J-Pop – Anime Rock",
           145, 185, 165, "4/4", [],
           50.0, 51.0, 8.0, 78, 127, "rock_accent",
           "moderate", [],
           ["major", "natural_minor", "mixolydian"],
           True, ["bVII", "bVI", "iv"],
           False, "triads_and_power", 7,
           {"intro": 4, "verse": 8, "pre_chorus": 4, "chorus": 8,
            "breakdown": 4, "guitar_solo": 8, "final_chorus": 8, "outro": 4},
           "dense",
           ["drum_fill_2bar", "snare_roll", "stutter", "synth_arp_fill"],
           "double_bass_fill_into_chorus", False,
           "hard_clip", 8.0, 18.0,
           "small", 0.6, 1.2, 0.03125, "wide",
           ["guitar_tremolo", "lead_pitch_drift"], 0.5, 2.0, "sine"),

        # ── PHONK ────────────────────────────────────────────────────────────
        _p("phonk", "classic_drift", "Phonk – Classic Drift",
           128, 148, 138, "4/4_halftime", [],
           55.0, 66.0, 18.0, 50, 108, "mpc_dilla_groove",
           "none", [],
           ["phrygian_dominant", "natural_minor", "chromatic"],
           False, [], False, "triads_chromatic", 24,
           {"loop_main": 8, "loop_variation": 8, "flip": 4},
           "sparse",
           ["hat_triplet_roll", "808_slide", "vinyl_skip"],
           "sample_flip_cut", False,
           "vinyl_tape", 8.0, 18.0,
           "small", 0.5, 1.2, 0.03125, "narrow",
           ["tape_flutter_pitch", "reverb_size", "cowbell_filter"],
           4.0, 16.0, "sample_hold"),

        _p("phonk", "brazilian_rave", "Phonk – Brazilian Rave",
           150, 175, 160, "4/4", [],
           50.0, 52.0, 6.0, 88, 127, "aggressive_flat",
           "none", [],
           ["phrygian", "natural_minor"],
           False, [], False, "1_2_chord_loop", 24,
           {"intro": 4, "main_drop": 8, "break": 4, "drop_return": 8},
           "moderate",
           ["snare_roll", "tacet_1beat", "808_slide"],
           "silence_into_drop", False,
           "hard_clip", 18.0, 40.0,
           "small", 0.3, 0.7, 0.03125, "moderate",
           ["distortion_drive", "reverb_gating", "filter_cutoff"],
           1.0, 4.0, "sample_hold"),

        # ── EDM ──────────────────────────────────────────────────────────────
        _p("edm", "festival_bigroom", "EDM – Festival Big Room",
           124, 132, 128, "4/4", [],
           50.0, 51.0, 5.0, 90, 127, "compressed_wall",
           "moderate", [],
           ["major", "mixolydian", "dorian"],
           False, [], False, "sus_and_add", 5,
           {"intro": 8, "verse": 8, "pre_build": 8, "build": 16,
            "drop": 16, "break": 8, "build_2": 8, "drop_2": 16, "outro": 8},
           "dense_in_build",
           ["snare_roll_16bar", "pitch_riser", "filter_sweep", "tacet_1beat"],
           "16bar_build_snare_plus_riser_then_silence_into_drop", True,
           "tape_soft", 2.0, 6.0,
           "small", 0.8, 1.5, 0.03125, "very_wide",
           ["filter_cutoff_build_sweep", "supersaw_detune", "sidechain_depth"],
           8.0, 16.0, "random_ramp"),

        _p("edm", "future_bass", "EDM – Future Bass",
           140, 160, 150, "4/4", [],
           50.0, 53.0, 9.0, 68, 120, "downbeat_backbeat_accent",
           "strict", [],
           ["major", "lydian"],
           True, ["iv_minor", "bVI", "bVII"],
           False, "extended", 3,
           {"intro": 4, "verse": 8, "pre_chorus": 4, "chorus_chop_drop": 8,
            "post_chorus": 4, "build": 8, "final_drop": 8, "outro": 4},
           "moderate",
           ["pitch_riser", "snare_roll", "tacet_1beat", "chord_chop_entry"],
           "riser_then_chop_chord_entry", False,
           "tape_soft", 3.0, 7.0,
           "medium", 1.5, 2.5, 0.0625, "very_wide",
           ["chord_chop_lfo_rate", "lead_chorus_width", "filter_cutoff"],
           0.125, 0.5, "square"),

        _p("edm", "dubstep", "EDM – Dubstep",
           138, 145, 140, "4/4_halftime", [],
           52.0, 56.0, 9.0, 80, 127, "halftime_kick_snare",
           "loose", [],
           ["aeolian", "phrygian"],
           True, ["tritone_sub", "bII"],
           False, "7ths", 7,
           {"intro": 8, "build": 8, "drop_wub": 16, "break": 8,
            "build_2": 8, "drop_2": 16, "outro": 4},
           "moderate",
           ["pitch_riser", "noise_burst", "tacet_1beat", "snare_roll"],
           "noise_air_into_wub_drop", True,
           "asymmetric_soft", 15.0, 35.0,
           "small", 0.5, 1.0, 0.03125, "wide",
           ["wobble_bass_filter_cutoff"], 0.125, 0.5, "sine"),

        # ── HOUSE ─────────────────────────────────────────────────────────────
        _p("house", "deep_chill", "House – Deep Chill",
           116, 126, 120, "4/4", [],
           52.0, 58.0, 14.0, 62, 106, "house_groove",
           "moderate", [],
           ["dorian", "natural_minor", "major"],
           True, ["bVII", "IV_from_minor", "tritone_sub_dominant"],
           False, "jazz_extended", 4,
           {"intro": 16, "main_groove": 32, "breakdown": 16,
            "groove_return": 32, "outro": 16},
           "very_sparse",
           ["hat_variation", "sub_bass_drop", "filter_sweep"],
           "element_removal_over_8bars", True,
           "tube_tanh", 3.0, 7.0,
           "medium", 2.0, 3.5, 0.0625, "moderate",
           ["pad_filter_cutoff", "reverb_size", "chord_resonance"],
           8.0, 32.0, "sine"),

        _p("house", "tech_house", "House – Tech House",
           124, 136, 130, "4/4", [],
           50.5, 54.0, 9.0, 80, 122, "driving_flat_kick",
           "loose", [],
           ["dorian", "aeolian"],
           False, [], False, "triads_and_sus2", 7,
           {"intro": 16, "groove": 32, "breakdown": 8,
            "filter_build": 8, "groove_return": 32, "outro": 16},
           "sparse",
           ["filter_sweep", "hat_variation", "sub_bass_drop", "clap_stutter"],
           "bass_removal_then_filter_sweep_reentry", True,
           "tube_tanh", 4.0, 10.0,
           "small", 0.5, 1.0, 0.03125, "moderate_wide",
           ["bass_filter_cutoff", "kick_drive", "clap_reverb_size"],
           2.0, 8.0, "sample_hold"),
    ]
