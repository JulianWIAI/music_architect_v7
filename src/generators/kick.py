"""
kick.py -- 01_Kick generator: genre-specific rhythmic anchors on the drum bus.

Music Theory Context:
    The kick drum is the foundation of the groove.  Its placement relative to
    the bass guitar (or 808 sub) defines the "lock" -- the perceptual unity
    of the low end.  This generator produces kick patterns that are:
        - Section-aware (intro sparse → drop full four-on-floor)
        - Genre-aware (trap half-time vs. EDM 4/4 vs. hip-hop boom-bap)
        - Probabilistic with seeded RNG so each track is unique but reproducible
        - Velocity-shaped per section energy

    GM Drum Mapping:
        KICK = 36  (Bass Drum 1 / Acoustic Bass Drum)
        MIDI channel 9 (0-indexed) = GM percussion channel

    Output: List of (time_beats, duration, 36, velocity) notes.
    Note: duration for drums is always short (0.25 beats = one 16th note).
"""

from __future__ import annotations
from typing import List, Tuple

from src.generators.base import TrackGenerator
from src.core.context_manager import SharedContext
from src.core.genre_matrix import GenreMatrix, GenreProfile
from src.composition.genre_constants import (
    GENRE_DRUM_PATTERNS, GENRE_SWING, KICK, CRASH, TOM_LOW,
)
import random

Note = Tuple[float, float, int, int]

# Sections where the kick plays at full density
_FULL_ENERGY_SECTIONS = frozenset({'chorus', 'drop', 'climax'})
# Sections where the kick stays completely silent
_SILENT_SECTIONS      = frozenset({'break', 'intro'})


class KickGenerator(TrackGenerator):
    """
    Generates the 01_Kick drum track.

    Strategy per section type:
        intro       → silent (let build-up layers carry energy)
        build       → escalating density, 25% → 75% of full pattern
        drop/chorus → full four-on-floor or genre pattern at max velocity
        verse       → normal genre pattern, moderate velocity
        break       → silent
        outro       → decaying, single downbeat only
    """

    track_name = '01_Kick'
    channel    = 9   # GM percussion

    def __init__(self, context, rng):
        super().__init__(context, rng)
        # [GENRE MATRIX] Load stylistic constraints for this genre
        self._gp: GenreProfile = GenreMatrix.get_profile(context.genre)

    def generate(self) -> List[Note]:
        notes: List[Note] = []

        # Pick one base drum pattern for the full song (same variant every bar)
        # so the kick pattern feels consistent while melody/chords vary
        g_pats  = GENRE_DRUM_PATTERNS.get(self.ctx.genre,
                                           GENRE_DRUM_PATTERNS.get('pop'))
        g_pat   = self.rng.choice(g_pats)
        kick_steps: List[Tuple[float, int]] = g_pat.get('kick', [])

        # [GENRE MATRIX] Genre swing -- profile overrides GENRE_SWING for heavy genres
        swing_pct = self._gp.swing_pct
        swing_off = (swing_pct - 0.5) * 0.5   # beat offset for odd steps

        bar_offset = 0
        for sec_idx, (section_type, section_bars) in enumerate(self.ctx.structure):
            energy = self.section_energy(section_type)

            for bar in range(section_bars):
                bo           = (bar_offset + bar) * 4.0
                build_pct    = (bar + 1) / section_bars if section_type == 'build' else 1.0

                if section_type in _SILENT_SECTIONS:
                    # Absolute silence -- no kick
                    pass

                elif section_type == 'outro':
                    # Single downbeat kick, decaying velocity
                    fade = 1.0 - (bar / max(1, section_bars))
                    if fade > 0.3 and bar % 2 == 0:
                        notes.append((
                            self.jitter_time(bo, max_ms=5.0),
                            0.25,
                            KICK,
                            self.velocity(100, fade, jitter=8),
                        ))

                elif section_type == 'build':
                    # Escalate from sparse to dense across the build section
                    density = 0.25 + 0.75 * build_pct
                    for step, base_vel in kick_steps:
                        if self.rng.random() < density:
                            t_raw = bo + step * 0.25
                            if int(step) % 2 == 1:
                                t_raw += swing_off
                            notes.append((
                                self.jitter_time(t_raw, max_ms=6.0),
                                0.25,
                                KICK,
                                self.velocity(base_vel, energy * build_pct, jitter=10),
                            ))

                else:
                    if self._gp.four_on_floor:
                        # [GENRE MATRIX] House / EDM: strict maximum-velocity four-on-the-floor
                        # Every beat fires at four_on_floor_vel -- no syncopation, no misses
                        for beat_idx in range(4):
                            notes.append((
                                bo + float(beat_idx),
                                0.25,
                                KICK,
                                self._gp.four_on_floor_vel,
                            ))
                    else:
                        # Normal genre pattern -- gate each step through energy and mutation
                        for step, base_vel in kick_steps:
                            if energy > 0.3 and self.rng.random() > self.ctx.mutation_factor * 0.15:
                                is_downbeat = (step == 0)
                                if is_downbeat:
                                    vel = self.rng.randint(110, 127) if section_type in _FULL_ENERGY_SECTIONS else self.rng.randint(100, 118)
                                else:
                                    vel = self.velocity(base_vel, energy, jitter=10)
                                t_raw = bo + step * 0.25
                                if int(step) % 2 == 1:
                                    t_raw += swing_off
                                notes.append((
                                    self.jitter_time(t_raw, max_ms=4.0),
                                    0.25,
                                    KICK,
                                    vel,
                                ))

                # Section-opening crash+kick for drop/chorus (adds energy on bar 1)
                is_first_bar_of_section = (bar == 0)
                if is_first_bar_of_section and section_type in _FULL_ENERGY_SECTIONS:
                    if self.rng.random() < 0.35:
                        notes.append((bo, 0.5, CRASH, self.velocity(110, energy, jitter=5)))
                        notes.append((bo, 0.5, TOM_LOW, self.velocity(95, energy, jitter=8)))

            bar_offset += section_bars

        notes.sort(key=lambda n: n[0])
        return notes
