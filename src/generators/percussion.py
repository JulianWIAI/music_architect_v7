"""
percussion.py -- 02_Percussion generator: Euclidean E(k,n) distribution.

Music Theory Context:
    Euclidean rhythms distribute k onsets across n steps as evenly as possible.
    This mathematical distribution is the basis of many world-music and dance
    rhythms (clave, son, bossa nova, shiko, etc.) and produces an organic,
    non-robotic feel compared to on-grid step programming.

    This generator handles ALL secondary percussion:
        Snare, Rimshot, Clap, Hi-Hat (closed/open/pedal), Crash, Ride,
        Toms (low/mid/high), Ghost notes.

    Pattern assignment per genre:
        trap/phonk  → sparse snare, machine-gun hi-hats with triplet rolls
        edm/house   → 4/4 snare on 2&4, upbeat hi-hats
        hiphop      → boom-bap snare with velocity swing
        cinematic   → tom-heavy, no hi-hat, tribal Euclidean patterns
        dnb         → amen-break style fast snare rolls

    [GOD MODE] Prime-Number Euclidean Interference (Syncopation Layer):
        The hi-hat section is augmented with a PrimeEuclideanPolyrhythm using
        preset 'driving': E(4,7) superimposed on E(3,5).  Combined period = 35
        steps (8.75 beats), which crosses a standard 4-beat bar boundary and
        ensures the syncopation pattern evolves continuously without repeating
        within a typical 4 or 8 bar loop.

        Rotation advances 4 steps per bar so each bar shifts the cross-rhythm
        phase, producing the "infinite micro-variation" quality of great polyrhythmic
        music.  The generated notes are soft ghost hi-hat hits (vel ~ 52) that sit
        BELOW the primary grid hi-hats, adding rhythmic depth without cluttering
        the pattern.

        Velocity weights from the polyrhythm engine:
            Both patterns coincide → vel_weight = 1.20  (rare accent point)
            Only primary (E(4,7)) → vel_weight = 1.00
            Only secondary (E(3,5)) → vel_weight = 0.65 (ghost syncopation)

    GM Drum Note Map (channel 9):
        37=Rimshot  38=Snare  39=Clap  42=Hihat-Closed  44=Hihat-Pedal
        45=Tom-Low  46=Hihat-Open  47=Tom-Mid  49=Crash  50=Tom-High  51=Ride
"""

from __future__ import annotations
from typing import List, Tuple

from src.generators.base import TrackGenerator
from src.composition.genre_constants import (
    GENRE_DRUM_PATTERNS, GENRE_SWING,
    SNARE, RIMSHOT, CLAP, HIHAT_CLOSED, HIHAT_OPEN, HIHAT_PEDAL,
    CRASH, RIDE, TOM_LOW, TOM_MID, TOM_HIGH,
)
from src.utils.math_tools import euclidean_rhythm
from src.core.genre_matrix import GenreMatrix, GenreProfile

# [GOD MODE] Prime-Euclidean polyrhythm for hi-hat syncopation
from src.utils.polyrhythm_engine import PrimeEuclideanPolyrhythm

Note = Tuple[float, float, int, int]

_FULL_ENERGY = frozenset({'chorus', 'drop', 'climax'})
_SILENT      = frozenset({'break'})


class PercussionGenerator(TrackGenerator):
    """
    Generates the 02_Percussion drum track (all non-kick percussion elements).

    [GOD MODE] A PrimeEuclideanPolyrhythm ('driving' preset: E(4,7) × E(3,5))
    augments the hi-hat grid with ghost syncopation hits.  The 35-step combined
    period crosses bar boundaries, ensuring the secondary rhythm never repeats
    within a standard 4 or 8 bar loop.
    """

    track_name = '02_Percussion'
    channel    = 9   # GM percussion -- same channel as kick

    def __init__(self, context, rng):
        super().__init__(context, rng)
        # [GENRE MATRIX] Load stylistic constraints for this genre
        self._gp: GenreProfile = GenreMatrix.get_profile(context.genre)
        # [GOD MODE] 'driving' preset: E(4,7) × E(3,5) -- dense, forward-motion
        # Combined period = 35 steps (8.75 beats) -- crosses bar boundaries
        self._hihat_poly = PrimeEuclideanPolyrhythm(preset='driving')

    def generate(self) -> List[Note]:
        notes: List[Note] = []

        g_pats     = GENRE_DRUM_PATTERNS.get(self.ctx.genre,
                                              GENRE_DRUM_PATTERNS.get('pop'))
        g_pat      = self.rng.choice(g_pats)
        snare_steps = g_pat.get('snare', [])
        hihat_steps = g_pat.get('hihat', [])

        # [GENRE MATRIX] MPC swing overrides GENRE_SWING for heavy genres (hip-hop = 0.67)
        swing_pct  = self._gp.swing_pct
        swing_off  = (swing_pct - 0.5) * 0.5

        bar_offset = 0
        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            for bar in range(section_bars):
                bo = (bar_offset + bar) * 4.0

                if section_type in _SILENT:
                    # Sparse break -- occasional open hi-hat or ride accent only
                    if self.rng.random() < 0.3:
                        notes.append((bo + 2.0, 0.1, HIHAT_OPEN, 40))
                    continue

                if section_type == 'intro':
                    # Intro builds: only hi-hat pedal pattern
                    if energy > 0.25:
                        notes.append((self.jitter_time(bo, 4.0), 0.1,
                                      HIHAT_PEDAL, self.velocity(55, energy, 6)))
                    continue

                if section_type == 'outro':
                    fade = 1.0 - (bar / max(1, section_bars))
                    if fade > 0.2:
                        notes.append((self.jitter_time(bo + 4.0, 5.0), 0.25,
                                      SNARE, self.velocity(80, fade, 10)))
                    continue

                # --- Snare pattern -------------------------------------------
                for step, base_vel in snare_steps:
                    vel   = self.velocity(base_vel, energy, jitter=8)
                    t_raw = bo + step * 0.25
                    if int(step) % 2 == 1:
                        t_raw += swing_off
                    notes.append((
                        self.jitter_time(t_raw, max_ms=5.0),
                        0.25, SNARE, vel,
                    ))

                # --- Ghost snare (25% chance per bar, off main beats) ---------
                if self.rng.random() < 0.25:
                    occupied = {int(s) for s, _ in snare_steps}
                    candidates = [s for s in range(16)
                                  if s not in occupied and s not in (0, 4, 8, 12)]
                    if candidates:
                        gs = self.rng.choice(candidates)
                        t_raw = bo + gs * 0.25
                        if gs % 2 == 1:
                            t_raw += swing_off
                        notes.append((self.jitter_time(t_raw, 3.0),
                                      0.08, SNARE, self.rng.randint(25, 42)))

                # --- Trap/Phonk 32nd-note snare roll at bar end --------------
                if self.ctx.genre in ('trap', 'phonk') and bar % 4 == 3:
                    if self.rng.random() < 0.30:
                        for sub in (14, 15):
                            notes.append((
                                self.jitter_time(bo + sub * 0.25, 2.0),
                                0.06, SNARE, self.rng.randint(55, 72),
                            ))

                # --- Hi-hat pattern ------------------------------------------
                for step, base_vel in hihat_steps:
                    if energy > 0.2 and self.rng.random() > self.ctx.mutation_factor * 0.20:
                        t_raw = bo + step * 0.25
                        # Odd 16th steps receive swing offset
                        step_int = int(step * 4) if step != int(step) else int(step)
                        if step_int % 2 == 1:
                            t_raw += swing_off
                        vel = self.velocity(base_vel, energy, jitter=6)
                        notes.append((
                            self.jitter_time(t_raw, max_ms=3.0),
                            0.08, HIHAT_CLOSED, vel,
                        ))

                # [GOD MODE] Prime-Euclidean hi-hat syncopation layer -----------
                # Generates evolving ghost hi-hat hits between the main grid beats.
                # Rotation advances 4 steps per bar -- each bar shifts the cross-rhythm
                # phase so the 35-step pattern never locks to the 4/4 bar grid.
                bar_idx   = int(bo / 4.0)
                rotation  = (bar_idx * 4) % self._hihat_poly.period_steps
                for poly_beat, vel_weight in self._hihat_poly.generate_offsets(
                        bo, 4.0, rotation):
                    # Keep the syncopation layer soft (base 52) to sit under the grid
                    poly_vel = max(1, min(127,
                        int(self.velocity(52, energy, jitter=6) * vel_weight)
                    ))
                    notes.append((
                        self.jitter_time(poly_beat, max_ms=3.0),
                        0.07, HIHAT_CLOSED, poly_vel,
                    ))

                # [GENRE MATRIX] Trap 32nd-note hi-hat bounce layer ---------------
                # Fires a rapid velocity-drop run at a syncopated position within
                # the bar.  The run starts loud and decays by trap_vel_drop_curve
                # per step, creating the characteristic trap hi-hat bounce.
                # Probability gate = trap_hihat_32nd_weight (0 for non-trap genres).
                if (self._gp.trap_hihat_32nd_weight > 0.0
                        and self.rng.random() < self._gp.trap_hihat_32nd_weight):
                    n_steps     = 4 if self._gp.trap_hihat_triplet_roll else 3
                    run_start   = self.rng.choice([1.5, 2.5, 3.0, 1.0, 2.0])
                    run_vels    = GenreMatrix.trap_hihat_velocity_run(
                        base_vel   = self.velocity(90, energy, jitter=6),
                        n_steps    = n_steps,
                        drop_curve = self._gp.trap_vel_drop_curve,
                    )
                    for step_i, step_vel in enumerate(run_vels):
                        t_run = bo + run_start + step_i * 0.125   # 32nd-note grid
                        if t_run < bo + 4.0:                       # stay in bar
                            notes.append((
                                self.jitter_time(t_run, max_ms=1.5),  # tight jitter
                                0.06, HIHAT_CLOSED, step_vel,
                            ))

                # --- Hi-hat open accent on upbeat in drop/chorus -------------
                if section_type in _FULL_ENERGY and self.rng.random() < 0.18:
                    notes.append((
                        self.jitter_time(bo + 2.0, 4.0),   # "and" of beat 1
                        0.15, HIHAT_OPEN,
                        self.velocity(75, energy, 8),
                    ))

                # --- Euclidean percussion fill (cinematic, tribal genres) ----
                if self.ctx.genre in ('cinematic', 'trap') and bar % 4 == 3:
                    self._add_euclidean_fill(notes, bo, energy)

                # --- Clap layer (EDM/house genre) ----------------------------
                if self.ctx.genre in ('edm', 'house') and section_type in _FULL_ENERGY:
                    # Clap on 2 and 4 (beats 1.0 and 3.0 in 4/4 zero-indexed)
                    for clap_beat in (1.0, 3.0):
                        notes.append((
                            self.jitter_time(bo + clap_beat * 1.0, 5.0),
                            0.12, CLAP,
                            self.velocity(95, energy, 8),
                        ))

            bar_offset += section_bars

        notes.sort(key=lambda n: n[0])
        return notes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_euclidean_fill(self, notes: List[Note],
                             bar_start: float, energy: float) -> None:
        """
        Generate a short Euclidean tom fill at the end of a 4-bar phrase.

        Uses E(5, 16) rotated by a random offset for variety.  Assigns
        notes alternately to TOM_HIGH and TOM_MID for stereo movement.
        """
        # E(5,16) -- 5 tom hits across 16 16th-note steps
        pattern = euclidean_rhythm(5, 16)
        rotation = self.rng.randint(0, 8)
        pattern  = pattern[rotation:] + pattern[:rotation]

        toms = [TOM_HIGH, TOM_MID, TOM_LOW]
        tom_idx = 0
        for step, active in enumerate(pattern):
            if active:
                t = self.jitter_time(bar_start + step * 0.25, 4.0)
                notes.append((t, 0.20,
                               toms[tom_idx % len(toms)],
                               self.velocity(85, energy, 10)))
                tom_idx += 1
