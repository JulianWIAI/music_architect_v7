"""
BuiltinSynthesizer

Software synthesiser using additive synthesis with ADSR envelopes.
Converts MIDI-like event dicts into a flat PCM audio buffer (list of floats).
Requires no external dependencies beyond the standard library.
"""

import math
from typing import List, Tuple

from src.rendering.adsr_envelope import ADSREnvelope
from src.rendering.instrument_timbres import (
    INSTRUMENT_TIMBRES, DEFAULT_TIMBRE,
    generate_kick_sample, generate_snare_sample,
    generate_hihat_sample, generate_crash_sample,
)


class BuiltinSynthesizer:
    """
    Renders a composition dict to a list of mono float PCM samples.

    Uses additive synthesis (overlaid harmonics) for melodic instruments and
    synthesised noise/sweep samples for percussion. All samples are mixed into
    a single master buffer and peak-normalised before return.
    """

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.drum_cache: dict = {}

    # ─── LOW-LEVEL SYNTHESIS ──────────────────────────────────────────────────

    def midi_to_freq(self, midi_note: int) -> float:
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

    def oscillator(self, freq: float, t: float, osc_type: str = 'sine') -> float:
        phase = 2 * math.pi * freq * t
        if osc_type == 'sine':
            return math.sin(phase)
        if osc_type == 'saw':
            return 2.0 * (freq * t % 1.0) - 1.0
        if osc_type == 'square':
            return 1.0 if math.sin(phase) > 0 else -1.0
        if osc_type == 'triangle':
            return 2.0 * abs(2.0 * (freq * t % 1.0) - 1.0) - 1.0
        return math.sin(phase)

    def synthesize_note(
        self, midi_note: int, start_time: float, duration: float,
        velocity: float, program: int = 0
    ) -> Tuple[int, List[float]]:
        """Synthesise a single note; returns (start_sample_index, samples)."""
        freq = self.midi_to_freq(midi_note)
        timbre = INSTRUMENT_TIMBRES.get(program, DEFAULT_TIMBRE)
        harmonics = timbre['harmonics']
        adsr_params = timbre['adsr']
        osc_type = timbre['type']

        envelope = ADSREnvelope(*adsr_params)
        total_dur = duration + adsr_params[3]
        n_samples = int(total_dur * self.sample_rate)
        start_idx = int(start_time * self.sample_rate)
        vel_scale = velocity / 127.0
        harmonic_sum = sum(harmonics)

        samples = []
        for i in range(n_samples):
            t = i / self.sample_rate
            amp = envelope.get_amplitude(t, duration) * vel_scale
            sample = sum(
                self.oscillator(freq * (h + 1), t, osc_type) * h_amp
                for h, h_amp in enumerate(harmonics)
                if freq * (h + 1) <= self.sample_rate / 2
            )
            samples.append(sample / harmonic_sum * amp * 0.4)

        return start_idx, samples

    def synthesize_drum(
        self, midi_note: int, start_time: float, velocity: float
    ) -> Tuple[int, List[float]]:
        """Return (start_sample_index, velocity-scaled drum samples)."""
        vel_scale = velocity / 127.0
        start_idx = int(start_time * self.sample_rate)

        if midi_note not in self.drum_cache:
            if midi_note == 36:
                self.drum_cache[midi_note] = generate_kick_sample(self.sample_rate)
            elif midi_note in (38, 37, 39, 40):
                self.drum_cache[midi_note] = generate_snare_sample(self.sample_rate)
            elif midi_note in (42, 44):
                self.drum_cache[midi_note] = generate_hihat_sample(self.sample_rate, is_open=False)
            elif midi_note == 46:
                self.drum_cache[midi_note] = generate_hihat_sample(self.sample_rate, is_open=True)
            elif midi_note == 49:
                self.drum_cache[midi_note] = generate_crash_sample(self.sample_rate)
            elif midi_note == 51:
                self.drum_cache[midi_note] = generate_hihat_sample(self.sample_rate, 0.15, True)
            elif midi_note in (45, 47, 50):
                self.drum_cache[midi_note] = generate_kick_sample(self.sample_rate, 0.15)
            else:
                self.drum_cache[midi_note] = generate_snare_sample(self.sample_rate, 0.1)

        raw = self.drum_cache[midi_note]
        return start_idx, [s * vel_scale for s in raw]

    # ─── COMPOSITION RENDERING ────────────────────────────────────────────────

    def render_composition(self, composition: dict, progress_callback=None) -> List[float]:
        """
        Render a full composition dict to a mono PCM float buffer.

        The composition dict must have the structure produced by CompositionEngine:
            {
              'config': {'bpm': float},
              'total_bars': int,
              'tracks': {track_name: [(time_beats, dur_beats, pitch, velocity), ...]},
              'track_info': {track_name: {'channel': int, 'program': int}},
            }
        """
        bpm = composition['config']['bpm']
        beat_dur = 60.0 / bpm
        total_seconds = composition['total_bars'] * 4 * beat_dur + 5
        total_samples = int(total_seconds * self.sample_rate)
        buffer = [0.0] * total_samples

        tracks = composition.get('tracks', {})
        track_info = composition.get('track_info', {})
        total_events = sum(len(events) for events in tracks.values())
        processed = 0

        for track_name, events in tracks.items():
            info = track_info.get(track_name, {})
            program = info.get('program', 0)
            is_drum = info.get('channel', 0) == 9

            for event in events:
                if len(event) < 4:
                    continue
                time_beats, duration_beats, pitch, velocity = event[:4]
                time_sec = time_beats * beat_dur
                dur_sec = duration_beats * beat_dur

                if is_drum:
                    start_idx, samples = self.synthesize_drum(pitch, time_sec, velocity)
                else:
                    start_idx, samples = self.synthesize_note(
                        pitch, time_sec, dur_sec, velocity, program
                    )

                for i, s in enumerate(samples):
                    idx = start_idx + i
                    if 0 <= idx < total_samples:
                        buffer[idx] += s

                processed += 1
                if progress_callback and processed % 200 == 0:
                    progress_callback(processed, total_events)

        peak = max(abs(s) for s in buffer) if buffer else 1.0
        if peak > 0:
            scale = 0.85 / peak
            buffer = [s * scale for s in buffer]

        return buffer
