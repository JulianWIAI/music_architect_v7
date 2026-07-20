"""
pad.py -- 06_Pad generator: long tied notes, voice leading, and Note-Tie Mechanic.

Music Theory Context:
    The pad layer creates the harmonic "bed" -- a continuous sustaining texture
    that fills the frequency space between the bass and melody.  Unlike chords
    (which fire repeatedly), the pad holds notes across multiple bars, creating
    a sense of harmonic weight and continuity.

    [GOD MODE] Algorithmic Voice Leading:
        The pad is even more sensitive to voice-leading quality than chords,
        because the long held notes make any abrupt jump immediately audible.
        VoiceLeadingEngine.lead() ensures every pad chord change is as smooth
        as possible.  Because the pad uses fewer voices (root + 5th + octave),
        the voice-leading constraint is strict: each voice moves only 1-3
        semitones between pad voicings wherever possible.

    [GOD MODE] Macro-Velocity Envelope:
        MacroVelocityEnvelope with phase φ = π/2 (90° behind melody) makes the
        pad swell when the melody is at its halfway point -- creating a lagged
        harmonic support structure that feels like a sea rising under the melody.

    Note-Tie Mechanic:
        Consecutive same-pitch notes are merged into single held blocks by
        note_tie_engine.tie_notes(), removing re-trigger attack transients.

    Section-Aware Gate Scaling:
        BUILD   → staccato short notes (0.3 – 0.6 beats)
        DROP    → very long legato (4.0 – 16.0 beats)
        VERSE   → medium (2.0 – 4.0 beats)
        INTRO   → long (8.0 – 16.0 beats) for atmosphere

    Harmonic Supersymmetry:
        melody_density > 0.6 → pad_gate_mult *= 2.0

    MIDI Channel: 3
    GM Program: 95 (Pad 8 Sweep) or 89 (Pad 3 Poly Synth) based on genre
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from src.generators.base import TrackGenerator
from src.composition.genre_constants import (
    CHORD_INTERVALS, NOTE_TO_MIDI, parse_chord_string,
)
from src.utils.note_tie_engine import tie_notes
from src.utils.math_tools import melody_density, harmonic_supersymmetry_gate_mult

# [GOD MODE] New imports
from src.utils.voice_leading import VoiceLeadingEngine
from src.utils.macro_envelope import make_envelope, MacroVelocityEnvelope

# [GENRE MATRIX]
from src.core.genre_matrix import GenreMatrix, GenreProfile

Note = Tuple[float, float, int, int]

# Gate ranges per section type (in beats)
_GATE_RANGES = {
    'intro':      (8.0,  16.0),
    'verse':      (2.0,   4.0),
    'pre_chorus': (1.5,   3.0),
    'build':      (0.3,   0.6),   # staccato build
    'drop':       (4.0,  16.0),   # very long legato
    'chorus':     (4.0,  12.0),
    'climax':     (4.0,  12.0),
    'hook':       (2.0,   6.0),
    'bridge':     (2.0,   6.0),
    'break':      (8.0,  16.0),
    'outro':      (8.0,  16.0),
}
_DEFAULT_GATE = (2.0, 4.0)

# Pad uses wide-spread shell voicing (root, 5th, octave) for transparency
_PAD_VOICE_INTERVALS = [0, 7, 12]          # 3-voice shell
_PAD_VOICE_FULL      = [0, 7, 12, 19]      # 4-voice for high-energy sections


class PadGenerator(TrackGenerator):
    """
    Generates the 06_Pad track with long tied sustain notes and smooth voice
    leading between each chord change.
    """

    track_name = '06_Pad'
    channel    = 3

    def __init__(self, context, rng, melody_notes: Optional[List[Note]] = None):
        super().__init__(context, rng)
        self._melody_notes = melody_notes or []

        # [GENRE MATRIX] Stylistic constraints for this genre
        self._gp: GenreProfile = GenreMatrix.get_profile(context.genre)

        # [GOD MODE] Voice leading engine with tighter range for pad bass position
        # Pad sits below chords: root in C1-B2 range (MIDI 24-47)
        self._voice_engine = VoiceLeadingEngine(voice_range=(24, 84))

        # [GOD MODE] Macro envelope -- phase φ = π/2 (peaks when melody halfway done)
        self._envelope: MacroVelocityEnvelope = make_envelope(
            track_name = '06_Pad',
            total_bars = context.total_bars,
            seed       = context.seed_value,
        )

        # State: track the previous pad voicing for voice-leading continuity
        self._prev_voicing: Optional[List[int]] = None

    def generate(self) -> List[Note]:
        raw_notes: List[Note] = []
        chord_prog = self.ctx.chord_prog

        def chord_at_bar(bar_idx: int) -> str:
            if not chord_prog:
                return 'C'
            return chord_prog[bar_idx % len(chord_prog)]

        bar_offset = 0
        beat_total = 0.0

        for section_type, section_bars in self.ctx.structure:
            energy = self.section_energy(section_type)

            # Harmonic Supersymmetry: long melody → hold pad even longer
            m_density = melody_density(
                self._melody_notes, beat_total, section_bars
            ) if self._melody_notes else 0.0
            pad_gate_mult, _ = harmonic_supersymmetry_gate_mult(m_density)

            for bar in range(section_bars):
                abs_bar   = bar_offset + bar
                bo        = abs_bar * 4.0
                chord_str = chord_at_bar(abs_bar)

                # Section-aware gate with Harmonic Supersymmetry scaling
                gate_min, gate_max = _GATE_RANGES.get(section_type, _DEFAULT_GATE)
                gate_min *= pad_gate_mult
                gate_max *= pad_gate_mult
                gate = self.rng.uniform(gate_min, gate_max)

                # [GOD MODE] Build smoothly voice-led pad voicing
                pad_notes = self._build_voice_led_pad(chord_str, section_type)

                # [GOD MODE] Apply macro envelope to base velocity
                base_vel = self.velocity(72, energy, jitter=6)
                vel      = self._envelope.apply(base_vel, bo)

                for midi_note in pad_notes:
                    raw_notes.append((
                        self.jitter_time(bo, max_ms=12.0),   # pads have wider timing jitter
                        gate,
                        midi_note,
                        vel,
                    ))

            bar_offset += section_bars
            beat_total += section_bars * 4.0

        # Apply the Note-Tie Mechanic: merge consecutive same-pitch notes
        # This eliminates re-trigger attacks and creates true sustained pads
        tied = tie_notes(raw_notes)
        tied.sort(key=lambda n: n[0])

        # [GENRE MATRIX] EDM/House: build ramp + drop gap post-processing
        # Applies exponential velocity ramp across BUILD sections and enforces
        # absolute silence for build_drop_gap_beats before each DROP.
        if self._gp.build_ramp_exponential or self._gp.build_drop_gap_beats > 0.0:
            tied = self._apply_genre_matrix_passes(tied)

        return tied

    # ------------------------------------------------------------------

    def _build_voice_led_pad(
        self,
        chord_str:    str,
        section_type: str,
    ) -> List[int]:
        """
        [GOD MODE] Build a pad voicing that smoothly leads from the previous
        pad chord using VoiceLeadingEngine.

        Pad voicing philosophy:
            - Root sits LOW (octave 1-2, MIDI 24-47) for harmonic weight
            - 5th fills the lower-mid range
            - Octave (and optional 19th = octave+5th) complete the spread
            - Total span ≤ 2 octaves for a coherent pad sound

        The voice leading here is particularly important because the pad notes
        are HELD for 4-16 beats.  A poorly-led pad voicing creates an audible
        "bump" on every chord change, breaking the sustained texture.
        """
        root_name, quality = parse_chord_string(chord_str)
        root_pc   = NOTE_TO_MIDI.get(root_name, 0)

        # [GENRE MATRIX] Hip-hop / cinematic: extend shell voicing with a 7th
        # Root (C1) + 5th + b7/maj7 + octave creates jazz harmonic weight
        if self._gp.hiphop_extended_chords:
            intervals = [0, 7, 10, 12]   # root, 5th, minor 7th, octave (shell + b7)
        elif section_type in ('drop', 'chorus', 'climax'):
            intervals = _PAD_VOICE_FULL   # 4-voice wide spread for maximum body
        else:
            intervals = _PAD_VOICE_INTERVALS   # 3-voice shell

        # Root in octave 1 (MIDI C1=24) for wide spread
        root_midi = 24 + root_pc
        # Wrap into [24, 47] range (C1-B2)
        while root_midi > 47:
            root_midi -= 12
        while root_midi < 24:
            root_midi += 12

        # [GOD MODE] First chord: use direct interval placement as seed
        if self._prev_voicing is None:
            voicing = sorted(
                max(24, min(84, root_midi + i)) for i in intervals
            )
            self._prev_voicing = voicing
            return voicing

        # [GOD MODE] Subsequent chords: smooth voice-leading transition
        # Each voice finds the nearest target note, parallel fifths are penalized
        voicing = self._voice_engine.lead(
            prev_voicing   = self._prev_voicing,
            next_intervals = intervals,
            next_root_midi = root_midi,
            n_voices       = len(self._prev_voicing),
        )

        self._prev_voicing = voicing
        return voicing

    # ------------------------------------------------------------------

    def _apply_genre_matrix_passes(self, notes: List[Note]) -> List[Note]:
        """
        [GENRE MATRIX] Post-processing for EDM / House genres:

        1. Build Ramp: notes inside BUILD sections have their velocity ramped
           exponentially from their current value toward 127 as the build
           progresses toward the drop.  This creates the classic "rise" feeling.

        2. Drop Gap: notes whose onset falls in the gap_beats window before a
           DROP / CHORUS section are removed (absolute silence).  This creates
           the "drop moment" -- maximum tension immediately before release.
        """
        bar_beats = self.ctx.bar_beats

        # -- Build ramp ---------------------------------------------------
        if self._gp.build_ramp_exponential:
            build_ranges = GenreMatrix.find_build_ranges(self.ctx.structure, bar_beats)
            if build_ranges:
                result: List[Note] = []
                for note in notes:
                    ramped = False
                    for (b_start, b_end) in build_ranges:
                        if b_start <= note[0] < b_end:
                            note = GenreMatrix.apply_build_ramp(
                                [note], b_start, b_end, exponential=True
                            )[0]
                            ramped = True
                            break
                    result.append(note)
                notes = result

        # -- Drop gap -----------------------------------------------------
        if self._gp.build_drop_gap_beats > 0.0:
            drop_starts = GenreMatrix.find_drop_start_beats(
                self.ctx.structure, bar_beats
            )
            for drop_start in drop_starts:
                notes = GenreMatrix.apply_drop_gap(
                    notes, drop_start, self._gp.build_drop_gap_beats
                )

        return notes
