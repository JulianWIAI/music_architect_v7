"""
stabs.py -- 08_Stabs generator: syncopated off-beat short impacts.

Music Theory Context:
    Stabs are short (16th-note length), rhythmically displaced chord hits that
    appear on the off-beat (the "and" positions between the main beats).  They
    add rhythmic tension and syncopation without cluttering the downbeat where
    kick and bass already lock together.

    Placement rules:
        Stabs NEVER hit on main beats (0, 1, 2, 3 in a 4-beat bar).
        Stabs target the "and" positions: 0.5, 1.5, 2.5, 3.5 beats
        and the 16th-note off-beats: 0.25, 0.75, 1.25, 1.75, etc.

    Genre variations:
        trap/hiphop → heavy accented stabs on beat 2.5, 3.5 (push feel)
        EDM/house   → gated synth stabs every 1 beat in drop sections
        pop/jpop    → light synth stabs doubling the chord hook rhythm
        cinematic   → sparse 1-2 stabs per 2 bars (like brass punches)

    Velocity curve:
        Vout = Vbase ± Δv  where Δv ~ Uniform(-12, 12)
        High-energy sections push Vbase up by energy * 30

    MIDI Channel: 5
    GM Program:   81 (Lead 2 Sawtooth) or 89 (Pad 3) based on genre
"""

from __future__ import annotations
from typing import List, Tuple

from src.generators.base import TrackGenerator
from src.composition.genre_constants import (
    CHORD_INTERVALS, NOTE_TO_MIDI, parse_chord_string,
)

Note = Tuple[float, float, int, int]

# Sections where stabs are active
_STAB_ACTIVE  = frozenset({'verse', 'pre_chorus', 'build', 'drop',
                             'chorus', 'hook', 'climax', 'bridge'})

# Off-beat target positions within a 4-beat bar (in beats from bar start)
_OFFBEAT_POSITIONS = [0.5, 1.5, 2.5, 3.5]             # main off-beats
_SIXTEENTH_OFFS    = [0.25, 0.75, 1.25, 1.75,          # 16th off-beats
                       2.25, 2.75, 3.25, 3.75]


class StabsGenerator(TrackGenerator):
    """
    Generates the 08_Stabs syncopated stab track.
    """

    track_name = '08_Stabs'
    channel    = 5

    def generate(self) -> List[Note]:
        notes: List[Note] = []
        chord_prog = self.ctx.chord_prog

        def chord_at_bar(bar_idx: int) -> str:
            if not chord_prog:
                return 'C'
            return chord_prog[bar_idx % len(chord_prog)]

        bar_offset = 0
        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            if section_type not in _STAB_ACTIVE:
                bar_offset += section_bars
                continue

            for bar in range(section_bars):
                abs_bar   = bar_offset + bar
                bo        = abs_bar * 4.0
                chord_str = chord_at_bar(abs_bar)

                bar_stabs = self._generate_stabs_bar(
                    start_beat   = bo,
                    chord_str    = chord_str,
                    section_type = section_type,
                    energy       = energy,
                )
                notes.extend(bar_stabs)

            bar_offset += section_bars

        notes.sort(key=lambda n: n[0])
        return notes

    # ------------------------------------------------------------------

    def _generate_stabs_bar(
        self,
        start_beat:   float,
        chord_str:    str,
        section_type: str,
        energy:       float,
    ) -> List[Note]:
        """
        Place stab events at off-beat positions within one bar.
        """
        # Choose the stab pitch set: root + 5th + octave (open voicing)
        root_name, quality = parse_chord_string(chord_str)
        root_pc    = NOTE_TO_MIDI.get(root_name, 0)
        intervals  = CHORD_INTERVALS.get(quality, [0, 4, 7])
        # Place stabs in octave 4 (MIDI 60-71)
        base_note  = 60 + root_pc
        stab_tones = [base_note + i for i in intervals[:3]]   # at most 3 voices
        stab_tones = [max(48, min(84, n)) for n in stab_tones]

        bar_stabs: List[Note] = []

        if self.ctx.genre in ('edm', 'house', 'techno'):
            # EDM: gated stab on every off-beat in drop; 50% in verse
            probability = 0.90 if section_type in ('drop', 'chorus') else 0.45
            for pos in _OFFBEAT_POSITIONS:
                if self.rng.random() < probability:
                    gate_dur = self.rng.uniform(0.12, 0.22)   # tight gated stab
                    vel      = self.velocity(95, energy, jitter=10)
                    t        = self.jitter_time(start_beat + pos, max_ms=5.0)
                    for tone in stab_tones:
                        bar_stabs.append((t, gate_dur, tone, vel))

        elif self.ctx.genre in ('trap', 'hiphop', 'phonk'):
            # Trap: syncopated stab on 2.5 and sometimes 3.5 (the "push" feel)
            # These positions create the characteristic "punch" before the downbeat
            trap_positions = [2.5]
            if self.rng.random() < 0.45:
                trap_positions.append(3.5)
            if self.rng.random() < 0.25 and section_type in ('drop', 'verse'):
                trap_positions.append(1.5)

            for pos in trap_positions:
                gate_dur = self.rng.uniform(0.15, 0.30)
                vel      = self.velocity(105, energy, jitter=12)
                t        = self.jitter_time(start_beat + pos, max_ms=7.0)
                for tone in stab_tones:
                    bar_stabs.append((t, gate_dur, tone, vel))

        elif self.ctx.genre == 'cinematic':
            # Cinematic: sparse brass-punch stabs, 1-2 per phrase (30% per bar)
            if self.rng.random() < 0.30 and section_type not in ('intro', 'break'):
                pos      = self.rng.choice(_OFFBEAT_POSITIONS)
                gate_dur = self.rng.uniform(0.4, 0.8)   # longer cinematic punches
                vel      = self.velocity(100, energy, jitter=8)
                t        = self.jitter_time(start_beat + pos, max_ms=6.0)
                for tone in stab_tones[:2]:   # only 2-voice cinematic stab
                    bar_stabs.append((t, gate_dur, tone, vel))

        else:
            # Generic: random off-beat stab selection at moderate density
            positions = self.rng.sample(
                _OFFBEAT_POSITIONS,
                k=int(len(_OFFBEAT_POSITIONS) * energy * 0.6 + 0.5)
            )
            for pos in positions:
                gate_dur = self.rng.uniform(0.15, 0.35)
                vel      = self.velocity(88, energy, jitter=10)
                t        = self.jitter_time(start_beat + pos, max_ms=6.0)
                for tone in stab_tones[:2]:
                    bar_stabs.append((t, gate_dur, tone, vel))

        return bar_stabs
