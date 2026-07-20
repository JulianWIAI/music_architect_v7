"""
arp.py -- 07_Arp generator: strict staccato 16th/8th grid arpeggiator.

Music Theory Context:
    An arpeggio breaks a chord into individual notes played sequentially.
    The arpeggiator layer creates rhythmic interest and fills the harmonic
    space without the density of sustained chords.

    Arpeggiation patterns:
        UP        -- root → 3rd → 5th → oct (ascending sequence)
        DOWN      -- oct → 5th → 3rd → root (descending)
        UP-DOWN   -- root → 3rd → 5th → oct → 5th → 3rd (ping-pong)
        RANDOM    -- randomly ordered chord tones

    Grid subdivision:
        High energy (drop/chorus): 16th notes (0.25 beats per note)
        Normal energy:             8th notes (0.5 beats per note)
        Build:                     16th with density escalation

    Vocal Mask:
        When active, arp notes in the vocal zone (B3-B7, MIDI 59-107) are
        transposed down one octave.  If that puts them below C2 (36), the
        note is dropped.

    MIDI Channel: 4
    GM Program:   81 (Lead 2 Sawtooth) -- cutting, bright arp sound
"""

from __future__ import annotations
from typing import List, Tuple

from src.generators.base import TrackGenerator
from src.composition.genre_constants import (
    CHORD_INTERVALS, NOTE_TO_MIDI, parse_chord_string,
)
from src.utils.vocal_mask_math import apply_vocal_mask_to_track, VOCAL_SECTIONS

Note = Tuple[float, float, int, int]

# Sections where the arp plays
_ARP_ACTIVE = frozenset({'verse', 'pre_chorus', 'build', 'drop', 'chorus',
                          'hook', 'climax', 'bridge'})

# Arp patterns: list of chord-tone indices (0=root, 1=3rd, 2=5th, 3=oct)
_PATTERNS = {
    'up':       [0, 1, 2, 3],
    'down':     [3, 2, 1, 0],
    'up_down':  [0, 1, 2, 3, 2, 1],
    'random':   None,   # handled specially
}


class ArpGenerator(TrackGenerator):
    """
    Generates the 07_Arp (arpeggiator) track.
    """

    track_name = '07_Arp'
    channel    = 4

    def generate(self) -> List[Note]:
        notes: List[Note] = []
        chord_prog = self.ctx.chord_prog

        # Pick one arp pattern for the full song (consistent feel)
        pattern_name = self.rng.choice(list(_PATTERNS.keys()))

        def chord_at_bar(bar_idx: int) -> str:
            if not chord_prog:
                return 'C'
            return chord_prog[bar_idx % len(chord_prog)]

        bar_offset = 0
        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            if section_type not in _ARP_ACTIVE:
                bar_offset += section_bars
                continue

            for bar in range(section_bars):
                abs_bar   = bar_offset + bar
                bo        = abs_bar * 4.0
                chord_str = chord_at_bar(abs_bar)

                bar_notes = self._generate_arp_bar(
                    start_beat   = bo,
                    chord_str    = chord_str,
                    section_type = section_type,
                    energy       = energy,
                    pattern_name = pattern_name,
                )
                notes.extend(bar_notes)

            bar_offset += section_bars

        # Apply vocal mask: transpose arp notes out of vocal zone
        if self.ctx.vocal_mask:
            notes = apply_vocal_mask_to_track(
                notes, self.track_name, 'verse', active=True
            )

        notes.sort(key=lambda n: n[0])
        return notes

    # ------------------------------------------------------------------

    def _generate_arp_bar(
        self,
        start_beat:   float,
        chord_str:    str,
        section_type: str,
        energy:       float,
        pattern_name: str,
    ) -> List[Note]:
        """
        Generate one bar of arpeggiated chord tones.

        Returns staccato notes strictly on the 16th or 8th note grid.
        """
        # Build chord tones across 2 octaves (root oct 3 and oct 4)
        root_name, quality = parse_chord_string(chord_str)
        root_pc    = NOTE_TO_MIDI.get(root_name, 0)
        intervals  = CHORD_INTERVALS.get(quality, [0, 4, 7])

        # Two octaves: oct 3 (MIDI 48=C3) and oct 4 (MIDI 60=C4)
        tones = []
        for octave in [3, 4]:
            base = 12 * (octave + 1)
            for i in intervals:
                tones.append(base + root_pc + i)

        if not tones:
            return []

        # Select the pattern order
        if pattern_name == 'random':
            order = self.rng.sample(range(len(tones)), k=len(tones))
        else:
            pat = _PATTERNS.get(pattern_name, [0, 1, 2, 3])
            order = [i % len(tones) for i in pat]

        # Grid resolution: 16th in high energy, 8th otherwise
        step_dur = 0.25 if energy >= 0.8 else 0.5
        gate_dur = step_dur * self.rng.uniform(0.55, 0.80)   # staccato gate

        bar_notes: List[Note] = []
        cursor = start_beat
        bar_end = start_beat + 4.0
        pat_idx = 0

        while cursor < bar_end - 0.01:
            # Probabilistic density: high energy = more notes
            density_roll = energy + self.rng.uniform(-0.15, 0.15)
            if self.rng.random() < density_roll:
                tone_idx = order[pat_idx % len(order)]
                midi_note = tones[tone_idx]
                vel = self.velocity(85, energy, jitter=10)
                bar_notes.append((
                    self.jitter_time(cursor, max_ms=5.0),
                    gate_dur,
                    midi_note,
                    vel,
                ))
            pat_idx += 1
            cursor  += step_dur

        return bar_notes
