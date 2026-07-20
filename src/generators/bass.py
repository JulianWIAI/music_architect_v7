"""
bass.py -- 03_Bass generator: locked to kick note-on triggers.

Music Theory Context:
    The bass is the harmonic foundation and rhythmic glue between the kick drum
    and the chord progression.  The classic technique is "locking the bass to
    the kick": the bass plays on every kick hit and stays silent where the kick
    is silent.  This creates the perceptual "punchiness" of professional mixes.

    Additional bass techniques implemented:
        Sub octave doubling  -- bass notes doubled one octave lower for sub weight
        Walking bass (verse) -- stepwise motion between chord roots on off-beats
        808 glide (trap)     -- pitch bend from one root to next (handled by 8OhEight)
        Root + 5th voicing   -- when energy is high, bass plays root on 1, 5th on 3

    MIDI range:
        Bass sits in MIDI 24-55 (C1-G3).  Below C1 is subsonic; above G3
        conflicts with the lower vocal zone.

    Instrument Program (GENRE_INSTRUMENTS mapping, channel 0):
        edm/house/trap/hiphop → 38 (Synth Bass 1)
        pop                   → 33 (Acoustic Bass)
        cinematic             → 43 (Contrabass)
"""

from __future__ import annotations
from typing import List, Tuple

from src.generators.base import TrackGenerator
from src.core.genre_matrix import GenreMatrix, GenreProfile
from src.composition.genre_constants import (
    GENRE_INSTRUMENTS, GENRE_SWING, get_chord_midi_notes, parse_chord_string,
    NOTE_TO_MIDI, MIDI_TO_NOTE,
)
from src.utils.vocal_mask_math import apply_vocal_mask_to_track

Note = Tuple[float, float, int, int]

# Bass MIDI range
_BASS_MIN = 28   # E1 -- lowest comfortable bass note
_BASS_MAX = 52   # E3 -- upper limit before conflicts with lower melody


class BassGenerator(TrackGenerator):
    """
    Generates the 03_Bass track.

    Core pattern: play root of the current chord on the beat, with optional
    walking bass lines and rhythmic subdivision based on genre and section energy.
    """

    track_name = '03_Bass'
    channel    = 0

    def __init__(self, context, rng):
        super().__init__(context, rng)
        # [GENRE MATRIX] Load stylistic constraints
        self._gp: GenreProfile = GenreMatrix.get_profile(context.genre)

    def generate(self) -> List[Note]:
        notes: List[Note] = []

        # [GENRE MATRIX] Genre swing -- profile value overrides GENRE_SWING
        swing_pct = self._gp.swing_pct
        swing_off = (swing_pct - 0.5) * 0.5

        # Index chord progression by bar
        chord_prog = self.ctx.chord_prog
        total_bars = self.ctx.total_bars
        # Map each bar to a chord string (cycle if progression is shorter than song)
        def chord_at_bar(bar_idx: int) -> str:
            if not chord_prog:
                return 'C'
            return chord_prog[bar_idx % len(chord_prog)]

        bar_offset = 0
        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            for bar in range(section_bars):
                abs_bar  = bar_offset + bar
                bo       = abs_bar * 4.0
                chord_str = chord_at_bar(abs_bar)

                # Determine bass root note
                root_name, quality = parse_chord_string(chord_str)
                root_pc   = NOTE_TO_MIDI.get(root_name, 0)
                # Place root in the bass octave (C2-B2 = MIDI 36-47)
                root_midi = 36 + root_pc   # C2 base
                # Wrap into [_BASS_MIN, _BASS_MAX]
                while root_midi > _BASS_MAX:
                    root_midi -= 12
                while root_midi < _BASS_MIN:
                    root_midi += 12

                # 5th of the chord
                fifth_midi = root_midi + 7

                if section_type in ('intro', 'break'):
                    # Minimal -- single downbeat bass note per 2 bars
                    if bar % 2 == 0 and energy > 0.25:
                        notes.append((
                            self.jitter_time(bo, 8.0),
                            1.5, root_midi,
                            self.velocity(75, energy, 8),
                        ))
                    continue

                if section_type == 'outro':
                    fade = 1.0 - (bar / max(1, section_bars))
                    if fade > 0.2:
                        notes.append((self.jitter_time(bo, 6.0), 1.8,
                                      root_midi, self.velocity(85, fade, 8)))
                    continue

                # ---- Normal section patterns --------------------------------

                if self.ctx.genre in ('trap', 'hiphop', 'phonk'):
                    if self._gp.trap_808_kick_lock:
                        # [GENRE MATRIX] Trap/Phonk kick-lock: 808 fires exactly on
                        # kick step positions -- no jitter so sub and kick share the tick.
                        # Gate extends to just before the next kick for a locked 808 tail.
                        kick_beats = GenreMatrix.get_kick_beats(self.ctx.genre, bo)
                        for ki, kick_b in enumerate(kick_beats):
                            next_b = kick_beats[ki + 1] if ki + 1 < len(kick_beats) else bo + 4.0
                            gate   = max(0.1, next_b - kick_b - 0.04)  # tiny gap = clean cut
                            pitch  = root_midi if ki % 2 == 0 else (
                                fifth_midi if fifth_midi <= _BASS_MAX else root_midi
                            )
                            vel    = self.velocity(112 if ki == 0 else 96, energy, jitter=4)
                            notes.append((kick_b, gate, pitch, vel))   # exact tick -- no jitter
                    else:
                        # 808-style with light jitter
                        notes.append((self.jitter_time(bo, 8.0), 1.8,
                                      root_midi, self.velocity(110, energy, 6)))
                        if energy > 0.6 and self.rng.random() < 0.65:
                            notes.append((self.jitter_time(bo + 2.0, 8.0), 1.8,
                                          fifth_midi if fifth_midi <= _BASS_MAX else root_midi,
                                          self.velocity(95, energy, 8)))

                elif self.ctx.genre in ('edm', 'house', 'techno'):
                    # Syncopated 8th-note bass line with kick lock
                    bass_steps = self._edm_bass_steps(section_type)
                    for step_frac, vel_base in bass_steps:
                        t_raw = bo + step_frac
                        # Alternate between root and 5th for movement
                        pitch = root_midi if self.rng.random() < 0.7 else fifth_midi
                        if pitch > _BASS_MAX:
                            pitch -= 12
                        notes.append((
                            self.jitter_time(t_raw, 7.0),
                            0.45,
                            pitch,
                            self.velocity(vel_base, energy, 7),
                        ))

                elif self.ctx.genre in ('dnb',):
                    # Fast 8th-note rolling bass
                    for beat in range(8):   # 8 8th notes per bar
                        if self.rng.random() < energy:
                            pitch = root_midi if beat % 2 == 0 else fifth_midi
                            if pitch > _BASS_MAX:
                                pitch -= 12
                            notes.append((
                                self.jitter_time(bo + beat * 0.5, 5.0),
                                0.4,
                                pitch,
                                self.velocity(100, energy, 8),
                            ))

                else:
                    # Walking bass / pop: root on 1, walkup note on 3
                    notes.append((
                        self.jitter_time(bo, 8.0),
                        1.8, root_midi,
                        self.velocity(100, energy, 8),
                    ))
                    if self.rng.random() < 0.55 and energy > 0.5:
                        walk_note = self._walk_note(root_midi, chord_str)
                        notes.append((
                            self.jitter_time(bo + 2.0, 8.0),
                            0.9, walk_note,
                            self.velocity(85, energy, 10),
                        ))

            bar_offset += section_bars

        # Apply vocal mask (bass sits below vocal zone -- density thinning only)
        if self.ctx.vocal_mask:
            notes = apply_vocal_mask_to_track(
                notes, self.track_name, 'verse', active=True
            )

        notes.sort(key=lambda n: n[0])
        return notes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _edm_bass_steps(self, section_type: str) -> List[Tuple[float, int]]:
        """
        Return (beat_offset_within_bar, base_velocity) pairs for EDM / House bass.

        [GENRE MATRIX] bass_offbeat_bias controls how many off-beat 16th steps
        (0.5, 1.5, 2.5, 3.5) fire in addition to the on-beat anchors.  A high
        value (e.g., 0.78 for EDM) produces the classic pump-and-drive feel where
        the bass plays BETWEEN the kicks.
        """
        bias = self._gp.bass_offbeat_bias

        # On-beat anchors always present
        on_beats: List[Tuple[float, int]] = [(0.0, 110), (2.0, 105)]

        # Off-beat 16ths: each fires probabilistically using bias as the threshold
        offbeat_candidates: List[Tuple[float, int]] = [
            (0.5, 88), (1.5, 82), (2.5, 85), (3.5, 80),
        ]

        if section_type in ('drop', 'chorus', 'climax'):
            # High energy: also fire beats 1 and 3
            on_beats = [(0.0, 112), (1.0, 92), (2.0, 110), (3.0, 90)]
            steps = list(on_beats)
            for off_b, off_v in offbeat_candidates:
                if self.rng.random() < bias:
                    steps.append((off_b, off_v))
            steps.sort(key=lambda x: x[0])
            return steps

        elif section_type == 'build':
            steps = [(0.0, 105), (2.0, 95)]
            for off_b, off_v in [(1.5, 78), (3.5, 72)]:
                if self.rng.random() < bias * 0.7:   # slightly less dense in build
                    steps.append((off_b, off_v))
            steps.sort(key=lambda x: x[0])
            return steps

        else:
            # Verse / hook: root anchor + bias-gated off-beats
            steps = [(0.0, 100)]
            for off_b, off_v in offbeat_candidates:
                if self.rng.random() < bias * 0.5:   # sparse in verse
                    steps.append((off_b, off_v))
            steps.sort(key=lambda x: x[0])
            return steps

    def _walk_note(self, root_midi: int, chord_str: str) -> int:
        """
        Return a walking bass note one scale step above the root.

        Uses the scale intervals from context to ensure the walk note is
        in-key.  Clamped to bass range.
        """
        scale_midi = self.ctx.scale_midi
        # Find notes above the root within the bass range
        candidates = [n for n in scale_midi if root_midi < n <= root_midi + 5]
        if candidates:
            return min(candidates)
        # Fallback: chromatic approach note
        return min(root_midi + 2, _BASS_MAX)
