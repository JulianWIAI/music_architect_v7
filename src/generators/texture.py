"""
texture.py -- 09_Texture generator: counter-melodies and atmospheric layers.

Music Theory Context:
    Texture tracks create the "upper harmonic sheen" -- high-register counter-
    melodies, tremolo or trembling figures, and atmospheric fills that sit above
    the main melody without competing with it.

    Counter-melody rules:
        1. Counter-melody targets notes the MAIN melody doesn't land on
           (complementary rhythm: where melody rests, texture fills)
        2. Stays in the upper register: MIDI 72-96 (C5-C7)
        3. Uses faster notes than the melody (16th-note fragments vs. quarter notes)
        4. Velocity is always SOFTER than melody:
               Vout = Vbase - 20 + Δv  (Vbase = 65, Δv ~ ±10)

    Velocity curve for texture:
        Vout = Vbase ± Δv
        Vbase is reduced to 65 (softer than all primary stems) to sit behind melody.

    Atmospheric variants (by genre):
        edm/house  → bright sawtooth runs in upper octave
        cinematic  → sustained high string tremolos (use long notes + velocity swell)
        trap/phonk → pitched hi-hat-like riffs (16th note staccato)
        hiphop     → jazzy chromatic approach tones

    [GOD MODE] Macro-Velocity Envelope:
        MacroVelocityEnvelope with phase φ = -π/4 (slightly ahead of melody) creates
        a counter-motion swell -- the texture peaks just BEFORE the melody peak, then
        fades as the melody takes the foreground.  This creates harmonic space at the
        exact moment the melody reaches its emotional climax, rather than piling on top.

    [GOD MODE] Prime-Number Euclidean Interference:
        Instead of a uniform 16th-note scan, texture fills are triggered by a
        PrimeEuclideanPolyrhythm with preset 'groove': E(3,7) superimposed on E(2,5).
        Combined period = 35 steps (8.75 beats at 16th-note resolution).
        Because 35 is not divisible by 4 (bar length = 16 steps), the pattern
        crosses bar boundaries -- it never sounds the same within a standard 4 or
        8 bar loop, producing the "evolving, hypnotic" texture quality.

        Rotation advances by 4 steps per bar so successive bars are phase-shifted,
        preventing the cross-bar repetition from becoming audible as a sub-loop.

        Velocity weighting from the polyrhythm engine:
            Both patterns coincide → vel_weight = 1.20  (accent point)
            Only primary (E(3,7)) → vel_weight = 1.00
            Only secondary (E(2,5)) → vel_weight = 0.65 (soft fill)

    MIDI Channel: 6
    GM Program:   80 (Lead 1 Square) or 85 (Lead 6 Voice) -- ethereal highs
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from src.generators.base import TrackGenerator
from src.utils.vocal_mask_math import apply_vocal_mask_to_track

# [GOD MODE] Macro envelope import
from src.utils.macro_envelope import make_envelope, MacroVelocityEnvelope

# [GOD MODE] Polyrhythm engine import
from src.utils.polyrhythm_engine import PrimeEuclideanPolyrhythm

# [GENRE MATRIX]
from src.core.genre_matrix import GenreMatrix, GenreProfile

Note = Tuple[float, float, int, int]

# Sections where texture plays
_TEXTURE_ACTIVE  = frozenset({'verse', 'pre_chorus', 'build', 'drop',
                               'chorus', 'hook', 'climax', 'bridge'})
# Sections where texture is completely silent
_TEXTURE_SILENT  = frozenset({'intro', 'break', 'outro'})

# Texture lives in the upper register (C5-C7)
_TEX_MIN = 72   # C5
_TEX_MAX = 96   # C7

# Softness: texture velocity base is 65 (below melody's ~90)
_BASE_VEL = 65


class TextureGenerator(TrackGenerator):
    """
    Generates the 09_Texture counter-melody and atmospheric layer track.

    [GOD MODE] A MacroVelocityEnvelope (φ = -π/4) shapes the overall dynamic arc
    so the texture peaks slightly before the melody, creating negative space at the
    melody's emotional high point.  A PrimeEuclideanPolyrhythm ('groove' preset)
    replaces the uniform 16th-note grid with a 35-step evolving interference pattern
    that never repeats the same phase within a standard 4 or 8 bar loop.
    """

    track_name = '09_Texture'
    channel    = 6

    def __init__(self, context, rng, melody_notes: Optional[List[Note]] = None):
        super().__init__(context, rng)
        # Receive melody notes to generate complementary rhythm
        self._melody_notes = melody_notes or []

        # [GENRE MATRIX] Stylistic constraints for this genre
        self._gp: GenreProfile = GenreMatrix.get_profile(context.genre)

        # [GOD MODE] Macro envelope -- phase φ = -π/4 (peaks slightly before melody)
        # Texture counter-motion: fades when melody peaks, giving the melody space
        self._envelope: MacroVelocityEnvelope = make_envelope(
            track_name = '09_Texture',
            total_bars = context.total_bars,
            seed       = context.seed_value,
        )

        # [GOD MODE] Prime-Euclidean polyrhythm for evolving hi-register fills
        # 'groove' preset: E(3,7) × E(2,5) -- combined period 35 steps (8.75 beats)
        # 35-step period crosses a 4-beat bar, so it never sounds the same twice
        self._polyrhythm = PrimeEuclideanPolyrhythm(preset='groove')

    def generate(self) -> List[Note]:
        notes: List[Note] = []
        chord_prog = self.ctx.chord_prog

        def chord_at_bar(bar_idx: int) -> str:
            if not chord_prog:
                return 'C'
            return chord_prog[bar_idx % len(chord_prog)]

        # Build a set of melody beat positions for complementary fill detection
        melody_beats = {n[0] for n in self._melody_notes}

        bar_offset = 0
        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            if section_type in _TEXTURE_SILENT:
                bar_offset += section_bars
                continue

            if section_type not in _TEXTURE_ACTIVE:
                bar_offset += section_bars
                continue

            for bar in range(section_bars):
                abs_bar   = bar_offset + bar
                bo        = abs_bar * 4.0
                chord_str = chord_at_bar(abs_bar)

                bar_notes = self._generate_texture_bar(
                    start_beat   = bo,
                    chord_str    = chord_str,
                    section_type = section_type,
                    energy       = energy,
                    melody_beats = melody_beats,
                )
                notes.extend(bar_notes)

            bar_offset += section_bars

        # Apply vocal mask: texture must also stay out of vocal zone
        if self.ctx.vocal_mask:
            notes = apply_vocal_mask_to_track(
                notes, self.track_name, 'verse', active=True
            )

        notes.sort(key=lambda n: n[0])

        # [GENRE MATRIX] EDM / House: build ramp + drop gap post-processing
        if self._gp.build_ramp_exponential or self._gp.build_drop_gap_beats > 0.0:
            notes = self._apply_genre_matrix_passes(notes)

        return notes

    # ------------------------------------------------------------------

    def _apply_genre_matrix_passes(self, notes: List[Note]) -> List[Note]:
        """
        [GENRE MATRIX] Identical build-ramp and drop-gap logic applied to texture.
        See pad.py for the full rationale.
        """
        bar_beats = self.ctx.bar_beats

        if self._gp.build_ramp_exponential:
            build_ranges = GenreMatrix.find_build_ranges(self.ctx.structure, bar_beats)
            if build_ranges:
                result: List[Note] = []
                for note in notes:
                    for (b_start, b_end) in build_ranges:
                        if b_start <= note[0] < b_end:
                            note = GenreMatrix.apply_build_ramp(
                                [note], b_start, b_end, exponential=True
                            )[0]
                            break
                    result.append(note)
                notes = result

        if self._gp.build_drop_gap_beats > 0.0:
            drop_starts = GenreMatrix.find_drop_start_beats(
                self.ctx.structure, bar_beats
            )
            for drop_start in drop_starts:
                notes = GenreMatrix.apply_drop_gap(
                    notes, drop_start, self._gp.build_drop_gap_beats
                )

        return notes

    # ------------------------------------------------------------------

    def _generate_texture_bar(
        self,
        start_beat:   float,
        chord_str:    str,
        section_type: str,
        energy:       float,
        melody_beats: set,
    ) -> List[Note]:
        """
        Generate texture notes for one bar.

        [GOD MODE] Strategy: use PrimeEuclideanPolyrhythm offsets instead of
        a uniform 16th-note scan.  The E(3,7) × E(2,5) interference pattern
        (period = 35 steps) crosses bar boundaries so the rhythm evolves
        continuously.  Rotation advances by 4 steps per bar to maintain phase
        continuity across bars.

        Velocity is shaped by the MacroVelocityEnvelope, then scaled by the
        polyrhythm velocity weight (accent points are louder).
        """
        bar_notes: List[Note] = []

        # Get upper-register scale notes
        scale_upper = [n for n in self.ctx.scale_midi if _TEX_MIN <= n <= _TEX_MAX]
        if not scale_upper:
            scale_upper = [72, 74, 76, 79, 81]   # fallback: C major pentatonic oct 5

        fill_probability = self._fill_probability(section_type, energy)

        # [GOD MODE] Phase rotation: advance by 4 steps per bar so successive bars
        # are phase-shifted -- prevents the 35-step pattern from sounding repetitive
        bar_idx  = int(start_beat / 4.0)
        rotation = (bar_idx * 4) % self._polyrhythm.period_steps

        # [GOD MODE] Get active steps from the prime-interference pattern
        offsets = self._polyrhythm.generate_offsets(
            start_beat  = start_beat,
            total_beats = 4.0,
            rotation    = rotation,
        )

        for beat, vel_weight in offsets:
            # Complementary rhythm: skip when melody is present (unless high-energy)
            melody_nearby = any(abs(beat - mb) < 0.05 for mb in melody_beats)
            if melody_nearby and section_type not in ('drop', 'chorus', 'climax'):
                continue

            if self.rng.random() >= fill_probability:
                continue

            # Pick note from upper register scale
            note = self.rng.choice(scale_upper)
            gate = self.rng.uniform(0.10, 0.22)   # staccato for texture crispness

            # [GOD MODE] Macro envelope modulates base velocity, then polyrhythm
            # velocity weight accents the interference coincidence points
            raw_vel  = int(_BASE_VEL * vel_weight) + self.rng.randint(-10, 10)
            vel      = self._envelope.apply(max(1, min(127, raw_vel)), beat)

            bar_notes.append((
                self.jitter_time(beat, max_ms=4.0),
                gate,
                note,
                vel,
            ))

        # Genre variant: cinematic uses long tremolo instead of staccato runs
        if self.ctx.genre == 'cinematic' and section_type in ('build', 'climax'):
            bar_notes = self._cinematic_tremolo(start_beat, scale_upper, energy)

        return bar_notes

    def _fill_probability(self, section_type: str, energy: float) -> float:
        """Density of texture fills per polyrhythm active step."""
        if section_type in ('drop', 'chorus', 'climax'):
            return min(0.65, energy * 0.70)
        elif section_type in ('build', 'pre_chorus'):
            return min(0.40, energy * 0.45)
        elif section_type in ('verse', 'hook'):
            return min(0.25, energy * 0.30)
        else:
            return 0.15

    def _cinematic_tremolo(self, start_beat: float,
                            scale_upper: list, energy: float) -> List[Note]:
        """
        Cinematic variant: two long notes with velocity swell (simulates tremolo strings).
        """
        if not scale_upper:
            return []
        note1 = scale_upper[len(scale_upper) // 2]
        note2 = scale_upper[min(len(scale_upper) - 1, len(scale_upper) // 2 + 2)]

        # [GOD MODE] Apply envelope to the tremolo velocity swell
        base_v = self.velocity(_BASE_VEL + 10, energy, jitter=8)
        vel1   = self._envelope.apply(base_v, start_beat)
        vel2   = self._envelope.apply(max(1, base_v - 8), start_beat + 2.0)

        return [
            (start_beat,       2.0, note1, vel1),
            (start_beat + 2.0, 2.0, note2, vel2),
        ]
