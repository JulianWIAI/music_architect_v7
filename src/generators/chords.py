"""
chords.py -- 05_Chords generator: inversions, voice leading, and section-aware gate scaling.

Music Theory Context:
    Chords are the harmonic scaffolding.  Their voicing (which octave each note
    sits in), inversion (which chord tone is in the bass), and gate length
    (how long notes are held) determine whether the track sounds like a stab, a
    shimmer, or a sustained pad-like layer.

    [GOD MODE] Algorithmic Voice Leading:
        Instead of generating random inversions, every chord transition is run
        through VoiceLeadingEngine.lead(), which calculates the mathematically
        shortest path for each individual voice between consecutive chords.
        This eliminates large jumps and enforces the no-parallel-fifths rule
        from Renaissance counterpoint -- making the chords sound like a real
        keyboard player, not a step sequencer.

    [GOD MODE] Macro-Velocity Envelope:
        MacroVelocityEnvelope applies a 16-bar sine-wave LFO to the base velocity
        of every chord event.  The phrase "breathes" -- swelling at bar 4, fading
        at bar 12, swelling again at bar 20 -- mimicking a real ensemble.

    Section-Aware Gate Scaling:
        gate = f(section_type)
            BUILD   → staccato 0.3 – 0.6 beats
            DROP    → legato   2.0 – 8.0 beats
            CHORUS  → legato   2.0 – 6.0 beats
            VERSE   → medium   1.0 – 2.0 beats
            INTRO   → long     4.0 – 8.0 beats

    Vocal Mask Open Voicing:
        When vocal_mask=True: drop the 3rd, use root + 5th + octave shell.

    Harmonic Supersymmetry:
        If melody_density > 0.6: chord_density *= 0.5

    MIDI Channel: 2
    GM Program:   89 (Pad 3 Poly Synth) for EDM/house, 4 (Electric Piano 1) for others
"""

from __future__ import annotations
import random
from typing import List, Optional, Tuple

from src.generators.base import TrackGenerator
from src.composition.genre_constants import (
    CHORD_INTERVALS, NOTE_TO_MIDI, parse_chord_string, get_chord_midi_notes,
)
from src.utils.vocal_mask_math import open_chord_voicing, VOCAL_SECTIONS
from src.utils.math_tools import melody_density, harmonic_supersymmetry_gate_mult

# [GOD MODE] New imports
from src.utils.voice_leading import VoiceLeadingEngine
from src.utils.macro_envelope import make_envelope, MacroVelocityEnvelope

# [GENRE MATRIX]
from src.core.genre_matrix import GenreMatrix, GenreProfile

Note = Tuple[float, float, int, int]

# Section-aware gate scaling table
_GATE_RANGES = {
    'intro':      (4.0,  8.0),
    'verse':      (1.0,  2.0),
    'pre_chorus': (0.8,  1.5),
    'build':      (0.3,  0.6),   # staccato -- driving tension
    'drop':       (2.0,  8.0),   # legato -- wide harmonic release
    'chorus':     (2.0,  6.0),   # legato
    'climax':     (2.0,  6.0),
    'hook':       (1.5,  3.0),
    'bridge':     (1.5,  3.0),
    'break':      (4.0,  8.0),   # sparse, held
    'outro':      (4.0,  8.0),
}
_DEFAULT_GATE = (1.0, 2.0)


class ChordsGenerator(TrackGenerator):
    """
    Generates the 05_Chords track.

    [GOD MODE] Each chord event is voice-led from the previous chord using
    VoiceLeadingEngine -- minimizing voice displacement and avoiding parallel
    fifths.  A 16-bar macro LFO shapes the overall velocity arc of the phrase.
    """

    track_name = '05_Chords'
    channel    = 2

    def __init__(self, context, rng, melody_notes: Optional[List[Note]] = None):
        super().__init__(context, rng)
        self._melody_notes = melody_notes or []

        # [GENRE MATRIX] Stylistic constraints for this genre
        self._gp: GenreProfile = GenreMatrix.get_profile(context.genre)

        # [GOD MODE] Voice leading engine -- shared across all chord transitions
        self._voice_engine = VoiceLeadingEngine(voice_range=(36, 96))

        # [GOD MODE] Macro envelope -- phase offset π/4 (45° behind melody)
        self._envelope: MacroVelocityEnvelope = make_envelope(
            track_name = '05_Chords',
            total_bars = context.total_bars,
            seed       = context.seed_value,
        )

        # Track the previous chord voicing for smooth voice-leading continuity
        # Initialised to None; first chord is placed as root position
        self._prev_voicing: Optional[List[int]] = None

    def generate(self) -> List[Note]:
        notes: List[Note] = []
        chord_prog = self.ctx.chord_prog

        def chord_at_bar(bar_idx: int) -> str:
            if not chord_prog:
                return 'C'
            return chord_prog[bar_idx % len(chord_prog)]

        bar_offset        = 0
        beat_offset_total = 0.0

        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            # Harmonic Supersymmetry: scale chord density inversely to melody density
            section_start_beat = beat_offset_total
            m_density = melody_density(
                self._melody_notes, section_start_beat, section_bars
            ) if self._melody_notes else 0.0
            _, chord_density_factor = harmonic_supersymmetry_gate_mult(m_density)

            for bar in range(section_bars):
                abs_bar   = bar_offset + bar
                bo        = abs_bar * 4.0
                chord_str = chord_at_bar(abs_bar)

                events_per_bar = self._events_per_bar(section_type, energy)

                for event_idx in range(events_per_bar):
                    # Harmonic Supersymmetry: randomly suppress when melody is dense
                    if self.rng.random() > chord_density_factor:
                        continue

                    beat_within_bar = event_idx * (4.0 / events_per_bar)
                    event_beat      = bo + beat_within_bar

                    # Section-aware gate (staccato in build, legato in drop)
                    gate_min, gate_max = _GATE_RANGES.get(section_type, _DEFAULT_GATE)
                    gate = self.rng.uniform(gate_min, gate_max)

                    # [GOD MODE] Build voice-led voicing from previous chord
                    chord_notes = self._build_voice_led_voicing(
                        chord_str, section_type, event_beat
                    )

                    # [GENRE MATRIX] Hip-hop: cap velocity for legato feel (no staccato stabs)
                    # [GOD MODE] Apply macro envelope to base velocity
                    raw_base = self.velocity(88, energy, jitter=6)
                    base_vel = min(raw_base, 76) if self._gp.hiphop_extended_chords else raw_base
                    vel      = self._envelope.apply(base_vel, event_beat)

                    for midi_note in chord_notes:
                        notes.append((
                            self.jitter_time(event_beat, max_ms=7.0),
                            gate,
                            midi_note,
                            vel,
                        ))

            bar_offset        += section_bars
            beat_offset_total += section_bars * 4.0

        notes.sort(key=lambda n: n[0])

        # [GENRE MATRIX] Hip-hop chord roll: arpeggiate voices for human touch
        # Voices are spaced hiphop_chord_roll_ms ms apart (low → high pitch order)
        if self._gp.hiphop_chord_roll_ms > 0.0:
            notes = GenreMatrix.apply_chord_roll(
                notes, self._gp.hiphop_chord_roll_ms, self.ctx.bpm
            )

        return notes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _events_per_bar(self, section_type: str, energy: float) -> int:
        """How many chord events fire per bar of 4 beats."""
        if section_type in ('intro', 'break', 'outro'):
            return 1    # one long chord per bar -- atmosphere
        if section_type == 'build':
            return 4    # staccato quarter-note chords drive the build
        if section_type in ('drop', 'chorus', 'climax'):
            return 2    # two half-note events -- full and spacious
        return 2        # default: 2 per bar for verses

    def _build_voice_led_voicing(
        self,
        chord_str:    str,
        section_type: str,
        beat:         float,
    ) -> List[int]:
        """
        [GOD MODE] Build a chord voicing that smoothly leads from the previous
        chord using the VoiceLeadingEngine.

        First call: place root position (no previous chord to lead from).
        Subsequent calls: VoiceLeadingEngine.lead() minimizes total semitone
        displacement across all voices while enforcing:
            - No parallel fifths
            - No voice crossing
            - Large leaps penalized
        """
        root_name, quality = parse_chord_string(chord_str)
        root_pc   = NOTE_TO_MIDI.get(root_name, 0)

        # [GENRE MATRIX] Hip-hop / cinematic: use 7th/9th extended voicings
        if self._gp.hiphop_extended_chords:
            intervals = GenreMatrix.extended_chord_intervals(quality)
        else:
            intervals = CHORD_INTERVALS.get(quality, [0, 4, 7])

        # Determine target octave from section energy
        # High-energy sections (drop/chorus): sit higher for brightness
        octave    = 4 if self.section_energy(section_type) >= 0.8 else 3
        root_midi = 12 * (octave + 1) + root_pc   # C4=60, C3=48

        # Apply vocal mask open voicing (overrides voice leading in vocal sections)
        if self.ctx.vocal_mask and section_type in VOCAL_SECTIONS:
            voicing = open_chord_voicing(root_midi, intervals, section_type, active=True)
            self._prev_voicing = sorted(voicing)
            return voicing

        # [GOD MODE] First chord: use root position as seed for the voice-leading chain
        if self._prev_voicing is None:
            voicing = sorted(
                max(36, min(96, root_midi + i)) for i in intervals
            )
            self._prev_voicing = voicing
            return voicing

        # [GOD MODE] Subsequent chords: compute smooth voice-leading transition
        # VoiceLeadingEngine generates all possible inversions/voicings of the new
        # chord and picks the one with minimum total voice displacement
        voicing = self._voice_engine.lead(
            prev_voicing   = self._prev_voicing,
            next_intervals = intervals,
            next_root_midi = root_midi,
            n_voices       = len(self._prev_voicing),
        )

        # Update state for the next transition
        self._prev_voicing = voicing
        return voicing
