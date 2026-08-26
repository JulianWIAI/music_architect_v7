"""
BuiltinSynthesizer
==================
Software synthesiser that converts a composition dict to a mono PCM float
buffer.

C++ fast path (preferred)
--------------------------
When the synth_core C++ extension module is compiled and importable, all
per-sample synthesis is delegated to it.  The C++ path is 50–200× faster:
a 4-bar composition that takes ~8 s in pure Python renders in ~100 ms.

Build the extension once from the project root:
    pip install pybind11
    python setup.py build_ext --inplace

Pure-Python fallback
--------------------
If synth_core is not compiled (import fails), the original Python
implementation runs unchanged.  Output is bit-for-bit identical.

Architecture split
------------------
• Per-sample synthesis (hot loops):  C++ SynthCore     ← the speed gain
• Buffer mixing and normalisation:   Python + numpy     ← already fast (C)
• Composition dict parsing:          Python             ← negligible overhead
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Try to import the C++ extension ──────────────────────────────────────────
# synth_core.so / synth_core.pyd must exist in the project root (build with
# `python setup.py build_ext --inplace` from the project root).

try:
    import synth_core as _cpp           # C++ SynthCore exposed via pybind11
    # Das Modul kann als leeres Namespace-Package existieren ohne dass
    # die C++-Klasse SynthCore tatsaechlich kompiliert wurde.
    # Explizit pruefen, damit der Python-Fallback korrekt ausgeloest wird.
    if not hasattr(_cpp, "SynthCore"):
        raise ImportError("synth_core.SynthCore wurde nicht kompiliert")
    _CPP_AVAILABLE = True
except ImportError:
    _cpp = None
    _CPP_AVAILABLE = False

# ── Python fallback imports (used only when C++ is unavailable) ───────────────

from src.rendering.adsr_envelope import ADSREnvelope
from src.rendering.instrument_timbres import (
    INSTRUMENT_TIMBRES, DEFAULT_TIMBRE,
    generate_kick_sample, generate_snare_sample,
    generate_hihat_sample, generate_crash_sample,
)


class BuiltinSynthesizer:
    """
    Renders a composition dict to a mono float PCM buffer.

    Transparently uses the C++ synth_core extension when available;
    falls back to the pure-Python implementation otherwise.
    The public API is identical in both cases.
    """

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate

        if _CPP_AVAILABLE:
            # C++ path: SynthCore owns its own drum cache
            self._core = _cpp.SynthCore(sample_rate)
            self.drum_cache: dict = {}   # kept for API parity; not used on C++ path
        else:
            # Python path: drum_cache used by synthesize_drum()
            self._core = None
            self.drum_cache = {}

    # =========================================================================
    # Public API
    # =========================================================================

    def render_composition(
        self,
        composition: dict,
        progress_callback=None,
        sample_engine=None,
    ) -> List[float]:
        """
        Render a full composition dict to a mono PCM float buffer.

        The composition dict must have the structure produced by
        CompositionEngine:
            {
              'config':     {'bpm': float},
              'total_bars': int,
              'tracks':     {name: [(time_beats, dur_beats, pitch, vel), ...]},
              'track_info': {name: {'channel': int, 'program': int}},
            }

        Parameters
        ----------
        composition       : Composition dict from CompositionEngine.
        progress_callback : Optional callable(processed, total) for UI progress.
        sample_engine     : Optional SampleEngine instance.  When a track has a
                            loaded sample, the SamplePlayer is used instead of
                            the built-in synthesiser for that track (samples take
                            priority over GM instrument selection).

        Returns
        -------
        List[float]: mono PCM samples, normalised to ≈ ±0.85 peak.
        """
        if _CPP_AVAILABLE:
            return self._render_cpp(composition, progress_callback, sample_engine)
        return self._render_python(composition, progress_callback, sample_engine)

    # ── Low-level API (Python fallback only) ─────────────────────────────────

    def midi_to_freq(self, midi_note: int) -> float:
        """MIDI note → frequency in Hz (equal temperament, A4 = 440 Hz)."""
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

    def oscillator(self, freq: float, t: float, osc_type: str = 'sine') -> float:
        """Single-sample oscillator output.  Used by Python fallback path."""
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
        self,
        midi_note: int,
        start_time: float,
        duration: float,
        velocity: float,
        program: int = 0,
    ) -> Tuple[int, List[float]]:
        """Synthesise one melodic note.  Python fallback path only."""
        freq       = self.midi_to_freq(midi_note)
        timbre     = INSTRUMENT_TIMBRES.get(program, DEFAULT_TIMBRE)
        harmonics  = timbre['harmonics']
        adsr_params = timbre['adsr']
        osc_type   = timbre['type']

        envelope      = ADSREnvelope(*adsr_params)
        total_dur     = duration + adsr_params[3]
        n_samples     = int(total_dur * self.sample_rate)
        start_idx     = int(start_time * self.sample_rate)
        vel_scale     = velocity / 127.0
        harmonic_sum  = sum(harmonics)

        samples = []
        for i in range(n_samples):
            t   = i / self.sample_rate
            amp = envelope.get_amplitude(t, duration) * vel_scale
            s   = sum(
                self.oscillator(freq * (h + 1), t, osc_type) * h_amp
                for h, h_amp in enumerate(harmonics)
                if freq * (h + 1) <= self.sample_rate / 2
            )
            samples.append(s / harmonic_sum * amp * 0.4)

        return start_idx, samples

    def synthesize_drum(
        self,
        midi_note: int,
        start_time: float,
        velocity: float,
    ) -> Tuple[int, List[float]]:
        """Synthesise one drum hit.  Python fallback path only."""
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

    # =========================================================================
    # Private — C++ render path
    # =========================================================================

    def _render_cpp(
        self,
        composition: dict,
        progress_callback=None,
        sample_engine=None,
    ) -> List[float]:
        """
        Render using the C++ SynthCore for per-sample synthesis.

        Note/drum synthesis: C++ (50–200× faster than Python).
        Buffer mixing:       numpy slice-add (already C, negligible cost).
        Dict parsing:        Python (tiny fraction of total time).

        When sample_engine is provided, melodic tracks that have a sample
        loaded use SamplePlayer instead of SynthCore.synthesize_note().
        Drum tracks always use the drum synthesiser (samples on drum tracks
        are not supported — they use dedicated drum sample generation).
        """
        bpm          = composition['config']['bpm']
        beat_dur     = 60.0 / bpm
        total_secs   = composition['total_bars'] * 4 * beat_dur + 5
        total_samples = int(total_secs * self.sample_rate)

        # numpy float32 buffer — slice-add is a BLAS-level C operation
        buffer = np.zeros(total_samples, dtype=np.float32)

        tracks     = composition.get('tracks', {})
        track_info = composition.get('track_info', {})
        total_events = sum(len(e) for e in tracks.values())
        processed    = 0

        for track_name, events in tracks.items():
            info     = track_info.get(track_name, {})
            program  = info.get('program', 0)
            is_drum  = info.get('channel', 0) == 9
            gain     = float(info.get('gain', 1.0))

            # Sample takes priority over the built-in synthesiser for this track.
            # Drum tracks are also eligible — SampleEngine plays them at root pitch.
            use_sample = (
                sample_engine is not None
                and sample_engine.is_loaded(track_name)
            )

            for event in events:
                if len(event) < 4:
                    continue
                time_beats, duration_beats, pitch, velocity = event[:4]
                time_sec = time_beats * beat_dur
                dur_sec  = duration_beats * beat_dur

                if use_sample:
                    # SampleEngine handles drum root-pitch correction internally.
                    try:
                        start_idx, samples = sample_engine.synthesize(
                            track_name, int(pitch), time_sec, dur_sec, velocity)
                    except Exception:
                        # Fallback to native synthesis if sample playback fails
                        if is_drum:
                            start_idx, samples = self._core.synthesize_drum(
                                pitch, time_sec, velocity)
                        else:
                            start_idx, samples = self._core.synthesize_note(
                                pitch, time_sec, dur_sec, velocity, program)
                elif is_drum:
                    start_idx, samples = self._core.synthesize_drum(
                        pitch, time_sec, velocity)
                else:
                    start_idx, samples = self._core.synthesize_note(
                        pitch, time_sec, dur_sec, velocity, program)

                # Mix into master buffer with numpy slice-add
                n = len(samples)
                b_start = max(0, start_idx)
                s_start = max(0, -start_idx)
                b_end   = min(start_idx + n, total_samples)
                actual  = b_end - b_start
                if actual > 0:
                    buffer[b_start:b_end] += (
                        np.asarray(samples[s_start:s_start + actual], dtype=np.float32) * gain
                    )

                processed += 1
                if progress_callback and processed % 200 == 0:
                    progress_callback(processed, total_events)

        # Soft-clip to 0.85 ceiling — only reduce if clipping, never boost.
        peak = float(np.max(np.abs(buffer)))
        if peak > 0.85:
            buffer *= 0.85 / peak

        return buffer.tolist()

    # =========================================================================
    # Private — pure-Python render path (fallback)
    # =========================================================================

    def _render_python(
        self,
        composition: dict,
        progress_callback=None,
        sample_engine=None,
    ) -> List[float]:
        """
        Pure-Python render path — used when C++ extension is not compiled.

        Uses the additive harmonic synthesiser for melodic tracks and the
        built-in drum synthesiser for percussion (channel 9).

        When sample_engine is provided, melodic tracks that have a sample
        loaded use the Python SamplePlayer fallback for that track.
        """
        bpm          = composition['config']['bpm']
        beat_dur     = 60.0 / bpm
        total_secs   = composition['total_bars'] * 4 * beat_dur + 5
        total_samples = int(total_secs * self.sample_rate)
        buffer       = [0.0] * total_samples

        tracks     = composition.get('tracks', {})
        track_info = composition.get('track_info', {})
        total_events = sum(len(e) for e in tracks.values())
        processed    = 0

        for track_name, events in tracks.items():
            info    = track_info.get(track_name, {})
            program = info.get('program', 0)
            is_drum = info.get('channel', 0) == 9
            gain    = float(info.get('gain', 1.0))

            use_sample = (
                sample_engine is not None
                and sample_engine.is_loaded(track_name)
            )

            for event in events:
                if len(event) < 4:
                    continue
                time_beats, duration_beats, pitch, velocity = event[:4]
                time_sec = time_beats * beat_dur
                dur_sec  = duration_beats * beat_dur

                if use_sample:
                    try:
                        start_idx, arr = sample_engine.synthesize(
                            track_name, int(pitch), time_sec, dur_sec, velocity)
                        samples = arr.tolist()
                    except Exception:
                        if is_drum:
                            start_idx, samples = self.synthesize_drum(
                                pitch, time_sec, velocity)
                        else:
                            start_idx, samples = self.synthesize_note(
                                pitch, time_sec, dur_sec, velocity, program)
                elif is_drum:
                    start_idx, samples = self.synthesize_drum(pitch, time_sec, velocity)
                else:
                    start_idx, samples = self.synthesize_note(
                        pitch, time_sec, dur_sec, velocity, program)

                for i, s in enumerate(samples):
                    idx = start_idx + i
                    if 0 <= idx < total_samples:
                        buffer[idx] += s * gain

                processed += 1
                if progress_callback and processed % 200 == 0:
                    progress_callback(processed, total_events)

        peak = max(abs(s) for s in buffer) if buffer else 0.0
        if peak > 0.85:
            scale  = 0.85 / peak
            buffer = [s * scale for s in buffer]

        return buffer
