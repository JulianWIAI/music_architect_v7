"""
melody.py -- 04_Melody generator: mixed probability matrix with tied notes.

Music Theory Context:
    Melody is the most memorable element of a composition.  A professional melody
    feels "singable" -- it has a clear phrase structure, uses mostly stepwise motion
    (adjacent scale degrees) with occasional leaps, and its rhythm varies between
    quarter notes, 8th notes, and dotted figures.

    Probability matrix for rhythmic values (varies by genre and complexity):
        1/4 note   (1.0 beats) -- melodic breath, gives space
        1/8 note   (0.5 beats) -- forward motion, typical pop/EDM hook
        dotted 1/8 (0.75 beats)-- rhythmic tension (common in trap/hiphop)
        tied       (extends previous duration) -- legato phrases

    Melodic motion probabilities (adjacent vs. skip vs. leap):
        step       (1-2 semitones) -- 55% probability
        skip       (3-4 semitones) -- 30% probability
        leap       (5+ semitones)  -- 15% probability (used sparingly)

    Range:
        Verse/build   → MIDI 60-79 (C4-G5)
        Drop/chorus   → MIDI 65-84 (F4-C6) -- higher register for energy
        Vocal mask ON → stays below 59 or above 84 (avoids singer's range)

    [GOD MODE] Macro-Velocity Envelope:
        MacroVelocityEnvelope with phase φ = 0.0 (melody LEADS the phrase --
        it peaks first, pulling the other stems behind it).  The melody swells
        to its loudest at bar 4, creating the emotional peak of the phrase,
        then decrescendos through bars 8-12 before the next phrase re-energizes.

    MIDI Channel: 1 (ch index)
    GM Program:   80 (Lead 1 Square) or genre-specific from GENRE_INSTRUMENTS
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from src.generators.base import TrackGenerator
from src.composition.genre_constants import (
    GENRE_INSTRUMENTS, GENRE_SWING, parse_chord_string, NOTE_TO_MIDI,
    get_chord_midi_notes,
)
from src.utils.vocal_mask_math import apply_vocal_mask_to_track

# [GOD MODE] Macro envelope import
from src.utils.macro_envelope import make_envelope, MacroVelocityEnvelope

Note = Tuple[float, float, int, int]

# MIDI octave ranges for melody by energy level
_MELODY_LOW_RANGE  = (60, 79)    # C4-G5 (verse, build)
_MELODY_HIGH_RANGE = (65, 84)    # F4-C6 (drop, chorus)

# Sections where melody is active vs. resting
_ACTIVE_SECTIONS  = frozenset({'verse', 'chorus', 'drop', 'hook', 'pre_chorus',
                                'climax', 'bridge', 'build'})
_SILENT_SECTIONS  = frozenset({'intro', 'break', 'outro'})


class MelodyGenerator(TrackGenerator):
    """
    Generates the 04_Melody (lead melody) track.

    [GOD MODE] A MacroVelocityEnvelope with phase φ=0 causes the melody to
    lead the phrase arc -- swelling at bar 4, pulling the pad and chords behind it.
    """

    track_name = '04_Melody'
    channel    = 1

    def __init__(self, context, rng):
        super().__init__(context, rng)
        # [GOD MODE] Melody leads the phrase arc (phase = 0.0)
        self._envelope: MacroVelocityEnvelope = make_envelope(
            track_name = '04_Melody',
            total_bars = context.total_bars,
            seed       = context.seed_value,
        )

    def generate(self) -> List[Note]:
        notes: List[Note] = []
        chord_prog = self.ctx.chord_prog

        def chord_at_bar(bar_idx: int) -> str:
            if not chord_prog:
                return 'C'
            return chord_prog[bar_idx % len(chord_prog)]

        bar_offset  = 0
        last_pitch  = 69   # A4 -- starting note for contour tracking

        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            if section_type in _SILENT_SECTIONS:
                bar_offset += section_bars
                continue

            if section_type not in _ACTIVE_SECTIONS:
                bar_offset += section_bars
                continue

            # Choose note range based on section energy
            note_min, note_max = (
                _MELODY_HIGH_RANGE if energy >= 0.9 else _MELODY_LOW_RANGE
            )

            for bar in range(section_bars):
                abs_bar = bar_offset + bar
                bo      = abs_bar * 4.0
                chord_str = chord_at_bar(abs_bar)

                # Generate a 4-beat phrase using the prob matrix
                bar_notes = self._generate_phrase(
                    start_beat  = bo,
                    chord_str   = chord_str,
                    section_type= section_type,
                    energy      = energy,
                    last_pitch  = last_pitch,
                    note_min    = note_min,
                    note_max    = note_max,
                )
                if bar_notes:
                    last_pitch = bar_notes[-1][2]   # track contour
                notes.extend(bar_notes)

            bar_offset += section_bars

        # Apply vocal mask -- transposes notes out of vocal zone
        if self.ctx.vocal_mask:
            notes = apply_vocal_mask_to_track(
                notes, self.track_name, 'verse', active=True
            )

        notes.sort(key=lambda n: n[0])
        return notes

    # ------------------------------------------------------------------
    # Phrase generation
    # ------------------------------------------------------------------

    def _generate_phrase(
        self,
        start_beat:   float,
        chord_str:    str,
        section_type: str,
        energy:       float,
        last_pitch:   int,
        note_min:     int,
        note_max:     int,
    ) -> List[Note]:
        """
        Generate a single-bar (4-beat) melodic phrase.

        Uses a probability-weighted rhythm matrix and voice-leading rules.
        Occasional rests (silence) create breathing room.
        """
        phrase: List[Note] = []
        cursor = start_beat
        bar_end = start_beat + 4.0

        # 30% chance of rest bar (important for verse breathing)
        if section_type in ('verse', 'bridge') and self.rng.random() < 0.30:
            return []

        # Get chord tones for "safe" notes (less dissonance)
        root_name, quality = parse_chord_string(chord_str)
        chord_tones = [
            36 + (NOTE_TO_MIDI.get(root_name, 0) + i) % 12 + oct * 12
            for oct in range(3, 6)
            for i in [0, 4, 7]
            if note_min <= 36 + (NOTE_TO_MIDI.get(root_name, 0) + i) % 12 + oct * 12 <= note_max
        ]

        current_pitch = last_pitch

        while cursor < bar_end - 0.01:
            # --- Choose rhythmic duration ---
            remaining = bar_end - cursor
            dur = self._choose_duration(remaining, section_type, energy)

            # --- Occasional rest (20% chance per note event) ---
            if self.rng.random() < 0.18:
                cursor += dur
                continue

            # --- Choose next pitch via melodic motion ---
            new_pitch = self._next_pitch(
                current_pitch, chord_tones, note_min, note_max, section_type
            )

            # Clamp gate to not exceed bar boundary
            gate = min(dur * self.rng.uniform(0.6, 0.95), bar_end - cursor - 0.01)
            gate = max(0.1, gate)

            # [GOD MODE] Apply macro envelope -- melody leads the phrase arc (φ=0)
            base_vel = self.velocity(90, energy, jitter=12)
            vel      = self._envelope.apply(base_vel, cursor)

            phrase.append((
                self.jitter_time(cursor, max_ms=8.0),
                gate,
                new_pitch,
                vel,
            ))

            current_pitch = new_pitch
            cursor += dur

        return phrase

    def _choose_duration(self, remaining: float,
                          section_type: str, energy: float) -> float:
        """
        Weighted choice of note duration based on section type and remaining space.
        """
        if remaining <= 0.5:
            return remaining

        # Weights: [quarter=1.0, 8th=0.5, dotted-8th=0.75, half=2.0]
        if energy >= 0.9:
            # High energy: fast 8th notes
            options = [(0.5, 0.50), (0.25, 0.25), (0.75, 0.15), (1.0, 0.10)]
        elif section_type in ('verse', 'bridge', 'hook'):
            # Relaxed: mix of quarters and 8ths
            options = [(1.0, 0.35), (0.5, 0.35), (0.75, 0.20), (2.0, 0.10)]
        else:
            options = [(0.5, 0.40), (1.0, 0.30), (0.25, 0.20), (0.75, 0.10)]

        # Filter to durations that fit in remaining space
        valid = [(d, w) for d, w in options if d <= remaining]
        if not valid:
            return remaining

        total_w = sum(w for _, w in valid)
        r = self.rng.random() * total_w
        acc = 0.0
        for dur, w in valid:
            acc += w
            if r <= acc:
                return dur
        return valid[-1][0]

    def _next_pitch(
        self,
        current: int,
        chord_tones: list,
        note_min: int,
        note_max: int,
        section_type: str,
    ) -> int:
        """
        Choose next melody pitch using voice-leading probabilities.

        Motion types:
            step  (55%) -- move 1-2 semitones in a scale-directed direction
            skip  (30%) -- move 3-4 semitones
            leap  (15%) -- move 5-7 semitones (always to a chord tone)
        """
        scale_midi = [n for n in self.ctx.scale_midi if note_min <= n <= note_max]
        if not scale_midi:
            return current

        r = self.rng.random()

        if r < 0.55:
            # Stepwise motion: pick adjacent scale note
            candidates = [n for n in scale_midi if 1 <= abs(n - current) <= 2]
        elif r < 0.85:
            # Skip: 3-4 semitones
            candidates = [n for n in scale_midi if 3 <= abs(n - current) <= 4]
        else:
            # Leap: 5-7 semitones to chord tone for safety
            candidates = [n for n in chord_tones if 5 <= abs(n - current) <= 7]
            if not candidates:
                candidates = [n for n in scale_midi if 5 <= abs(n - current) <= 7]

        if not candidates:
            # Fallback: any scale note within the range
            candidates = scale_midi

        # Prefer notes that don't stray too far from previous (within 10 semitones)
        nearby = [n for n in candidates if abs(n - current) <= 10]
        pool   = nearby if nearby else candidates

        return self.rng.choice(pool)
