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
import random as _rand
import time as _time
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Try to import the C++ extension ──────────────────────────────────────────
# synth_core.so / synth_core.pyd must exist in the project root (build with
# `python setup.py build_ext --inplace` from the project root).

try:
    import synth_core as _cpp           # C++ SynthCore exposed via pybind11
    # The module may exist as an empty namespace package without the C++
    # class SynthCore actually being compiled.  Check explicitly so the
    # Python fallback is triggered correctly instead of failing later.
    if not hasattr(_cpp, "SynthCore"):
        raise ImportError("synth_core.SynthCore is not compiled")
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
    generate_perc_from_params,
)

# MIDI note → percussion role key used to look up instrument_params
_DRUM_NOTE_ROLE: dict = {
    36: 'kick',
    37: 'snare', 38: 'snare', 39: 'snare', 40: 'snare',
    42: 'hihat', 44: 'hihat', 46: 'hihat',
    49: 'cymbal', 51: 'cymbal', 57: 'cymbal',
    45: 'kick', 47: 'kick', 50: 'kick',  # toms — treated as kick variants
}

# Composition track name → instrument_params lookup key
_TRACK_TO_ROLE: dict = {
    '01_Kick':       'kick',
    '02_Percussion': 'snare',
    '03_Bass':       'melodic',
    '04_Melody':     'melodic',
    '05_Chords':     'melodic',
    '06_Pad':        'melodic',
    '07_Arp':        'melodic',
    '08_Stabs':      'melodic',
    '09_Texture':    'melodic',
    '10_FX':         'melodic',
}


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
        instrument_params: dict = None,
    ) -> np.ndarray:
        """
        Render a full composition dict to a stereo PCM float buffer.

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
        np.ndarray: stereo PCM buffer of shape (N, 2), normalised to ≈ ±0.85 peak.
        """
        # Use the C++ fast path only when no custom timbre params are active.
        # When instrument_params contains at least one entry the Python path is
        # used so PercussionParams / MelodicParams take effect.  The C++ path
        # has no equivalent param-driven synthesis, so we fall back rather than
        # silently ignoring the user's preset selections.
        use_cpp = _CPP_AVAILABLE and not bool(instrument_params)
        if use_cpp:
            return self._render_cpp(composition, progress_callback, sample_engine)
        return self._render_python(composition, progress_callback, sample_engine,
                                   instrument_params)

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
        melodic_params=None,
    ) -> Tuple[int, List[float]]:
        """
        Synthesise one melodic note.  Python fallback path only.

        When *melodic_params* is a MelodicParams instance the synthesiser uses
        its harmonic_richness, brightness, ADSR, noise_amount, and drive fields
        instead of the built-in INSTRUMENT_TIMBRES table.
        """
        freq      = self.midi_to_freq(midi_note)
        start_idx = int(start_time * self.sample_rate)
        vel_scale = velocity / 127.0

        if melodic_params is not None:
            # Build harmonic series from richness (count) and brightness (weighting)
            n_harmonics = max(1, int(1 + melodic_params.harmonic_richness * 7))
            harmonics = []
            for h in range(n_harmonics):
                # brightness=0 → descending 1/(h+1); brightness=1 → flat 1.0
                desc  = 1.0 / (h + 1)
                flat  = 1.0 / (1.0 + h * 0.2)
                harmonics.append(
                    desc * (1.0 - melodic_params.brightness) + flat * melodic_params.brightness
                )

            adsr_params = (
                melodic_params.attack_ms  / 1000.0,
                melodic_params.decay_ms   / 1000.0,
                melodic_params.sustain_level,
                melodic_params.release_ms / 1000.0,
            )
            # Brighter timbres use saw; darker timbres use sine
            osc_type     = 'saw' if melodic_params.brightness > 0.65 else 'sine'
            noise_amount = melodic_params.noise_amount
            drive        = melodic_params.drive
        else:
            timbre       = INSTRUMENT_TIMBRES.get(program, DEFAULT_TIMBRE)
            harmonics    = timbre['harmonics']
            adsr_params  = timbre['adsr']
            osc_type     = timbre['type']
            noise_amount = 0.0
            drive        = 0.0

        envelope     = ADSREnvelope(*adsr_params)
        total_dur    = duration + adsr_params[3]
        n_samples    = int(total_dur * self.sample_rate)
        harmonic_sum = sum(harmonics) or 1.0

        samples = []
        for i in range(n_samples):
            # Yield the GIL every 4096 samples (~93 ms at 44100 Hz) so the
            # Tkinter main thread stays responsive during long note synthesis.
            if i & 0xFFF == 0 and i > 0:
                _time.sleep(0)

            t   = i / self.sample_rate
            amp = envelope.get_amplitude(t, duration) * vel_scale
            s   = sum(
                self.oscillator(freq * (h + 1), t, osc_type) * h_amp
                for h, h_amp in enumerate(harmonics)
                if freq * (h + 1) <= self.sample_rate / 2
            )
            s = s / harmonic_sum * amp * 0.4

            # Optional noise breath layer
            if noise_amount > 0.0:
                noise = (_rand.random() * 2.0 - 1.0) * amp * 0.4
                s = s * (1.0 - noise_amount) + noise * noise_amount

            # Optional soft tanh saturation
            if drive > 0.0:
                drive_factor = 1.0 + drive * 3.0
                denom = math.tanh(drive_factor)
                if denom > 1e-6:
                    s = math.tanh(s * drive_factor) / denom

            samples.append(s)

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

    def _synth_drum(
        self,
        midi_note: int,
        start_time: float,
        velocity: float,
        instrument_params: dict,
    ) -> Tuple[int, List[float]]:
        """
        Param-aware drum synthesis — Python fallback path only.

        Looks up the MIDI note's role ('kick', 'snare', 'hihat') and fetches
        the corresponding PercussionParams from *instrument_params*.  When
        params are present the rich param-driven synthesiser is used; otherwise
        falls back to the legacy cached-sample drum synthesiser.

        Cymbal notes (49, 51, 57) have no param entry and always use the legacy
        path because the Timbre panel does not expose a cymbal role.
        """
        role   = _DRUM_NOTE_ROLE.get(midi_note)
        params = instrument_params.get(role) if role else None

        vel_scale = velocity / 127.0
        start_idx = int(start_time * self.sample_rate)

        if params is not None:
            raw = generate_perc_from_params(params, self.sample_rate)
            return start_idx, [s * vel_scale for s in raw]

        # Legacy path: cached waveform tables for all unparameterised notes
        return self.synthesize_drum(midi_note, start_time, velocity)

    # =========================================================================
    # Private — C++ render path
    # =========================================================================

    def _render_cpp(
        self,
        composition: dict,
        progress_callback=None,
        sample_engine=None,
    ) -> np.ndarray:
        """
        Render using the C++ SynthCore for per-sample synthesis.

        Returns a stereo np.ndarray of shape (N, 2).  Each track is
        accumulated into a per-track mono buffer, optionally widened with
        ChorusWidener (pad / texture / lead), then constant-power panned
        into the stereo master buffers before being mixed in.
        """
        from src.audio.stereo_panner import TRACK_PAN, CHORUS_TRACKS, COMP_TRACK_TO_GROOVE_KEY
        from src.audio.chorus_widener import ChorusWidener

        bpm           = composition['config']['bpm']
        beat_dur      = 60.0 / bpm
        total_secs    = composition['total_bars'] * 4 * beat_dur + 5
        total_samples = int(total_secs * self.sample_rate)

        buffer_L = np.zeros(total_samples, dtype=np.float32)
        buffer_R = np.zeros(total_samples, dtype=np.float32)

        tracks       = composition.get('tracks', {})
        track_info   = composition.get('track_info', {})
        total_events = sum(len(e) for e in tracks.values())
        processed    = 0

        widener = ChorusWidener(sample_rate=self.sample_rate)

        for track_name, events in tracks.items():
            info     = track_info.get(track_name, {})
            program  = info.get('program', 0)
            is_drum  = info.get('channel', 0) == 9
            gain     = float(info.get('gain', 1.0))

            groove_key = COMP_TRACK_TO_GROOVE_KEY.get(track_name, '')
            pan        = TRACK_PAN.get(groove_key, 0.0)
            use_chorus = groove_key in CHORUS_TRACKS

            use_sample = (
                sample_engine is not None
                and sample_engine.is_loaded(track_name)
            )

            # Collect all events for this track into a mono buffer
            track_mono = np.zeros(total_samples, dtype=np.float32)

            for event in events:
                if len(event) < 4:
                    continue
                time_beats, duration_beats, pitch, velocity = event[:4]
                time_sec = time_beats * beat_dur
                dur_sec  = duration_beats * beat_dur

                if use_sample:
                    try:
                        start_idx, samples = sample_engine.synthesize(
                            track_name, int(pitch), time_sec, dur_sec, velocity)
                    except Exception:
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

                n       = len(samples)
                b_start = max(0, start_idx)
                s_start = max(0, -start_idx)
                b_end   = min(start_idx + n, total_samples)
                actual  = b_end - b_start
                if actual > 0:
                    track_mono[b_start:b_end] += (
                        np.asarray(samples[s_start:s_start + actual], dtype=np.float32) * gain
                    )

                processed += 1
                if progress_callback and processed % 200 == 0:
                    progress_callback(processed, total_events)

            # Widen designated tracks before panning
            if use_chorus:
                track_L, track_R = widener.process(track_mono)
            else:
                track_L = track_R = track_mono

            # Constant-power pan into the stereo master buffers
            angle  = (pan + 1.0) * math.pi / 4.0
            gain_L = math.cos(angle)
            gain_R = math.sin(angle)
            buffer_L += track_L * gain_L
            buffer_R += track_R * gain_R

        # Normalise both channels together to preserve the stereo image
        peak = float(max(np.max(np.abs(buffer_L)), np.max(np.abs(buffer_R))))
        if peak > 0.85:
            scale     = 0.85 / peak
            buffer_L *= scale
            buffer_R *= scale

        return np.stack([buffer_L, buffer_R], axis=1)

    # =========================================================================
    # Private — pure-Python render path (fallback)
    # =========================================================================

    def _render_python(
        self,
        composition: dict,
        progress_callback=None,
        sample_engine=None,
        instrument_params: dict = None,
    ) -> np.ndarray:
        """
        Pure-Python render path — used when C++ extension is not compiled.

        Mirrors the stereo structure of _render_cpp: each track is accumulated
        into a per-track mono buffer, optionally widened with ChorusWidener
        (pad / texture / lead), then constant-power panned into the stereo
        master buffers.  Returns a stereo np.ndarray of shape (N, 2).

        When instrument_params is provided, percussion and melodic tracks use
        PercussionParams / MelodicParams to override the default synthesis
        character (timbre, noise amount, pitch sweep, drive, etc.).
        """
        from src.audio.stereo_panner import TRACK_PAN, CHORUS_TRACKS, COMP_TRACK_TO_GROOVE_KEY
        from src.audio.chorus_widener import ChorusWidener

        bpm           = composition['config']['bpm']
        beat_dur      = 60.0 / bpm
        total_secs    = composition['total_bars'] * 4 * beat_dur + 5
        total_samples = int(total_secs * self.sample_rate)

        buffer_L = np.zeros(total_samples, dtype=np.float32)
        buffer_R = np.zeros(total_samples, dtype=np.float32)

        tracks       = composition.get('tracks', {})
        track_info   = composition.get('track_info', {})
        total_events = sum(len(e) for e in tracks.values())
        processed    = 0
        ip           = instrument_params or {}

        widener = ChorusWidener(sample_rate=self.sample_rate)

        for track_name, events in tracks.items():
            info    = track_info.get(track_name, {})
            program = info.get('program', 0)
            is_drum = info.get('channel', 0) == 9
            gain    = float(info.get('gain', 1.0))

            groove_key = COMP_TRACK_TO_GROOVE_KEY.get(track_name, '')
            pan        = TRACK_PAN.get(groove_key, 0.0)
            use_chorus = groove_key in CHORUS_TRACKS

            # Resolve per-track instrument params (None = use built-in defaults)
            track_role    = _TRACK_TO_ROLE.get(track_name)
            track_iparams = ip.get(track_role) if track_role else None

            use_sample = (
                sample_engine is not None
                and sample_engine.is_loaded(track_name)
            )

            # Collect all note events for this track into a mono buffer
            track_mono = np.zeros(total_samples, dtype=np.float32)

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
                        note_samples = arr.tolist()
                    except Exception:
                        if is_drum:
                            start_idx, note_samples = self._synth_drum(
                                int(pitch), time_sec, velocity, ip)
                        else:
                            start_idx, note_samples = self.synthesize_note(
                                pitch, time_sec, dur_sec, velocity, program,
                                melodic_params=track_iparams)
                elif is_drum:
                    start_idx, note_samples = self._synth_drum(
                        int(pitch), time_sec, velocity, ip)
                else:
                    start_idx, note_samples = self.synthesize_note(
                        pitch, time_sec, dur_sec, velocity, program,
                        melodic_params=track_iparams)

                n       = len(note_samples)
                b_start = max(0, start_idx)
                s_start = max(0, -start_idx)
                b_end   = min(start_idx + n, total_samples)
                actual  = b_end - b_start
                if actual > 0:
                    track_mono[b_start:b_end] += (
                        np.asarray(note_samples[s_start:s_start + actual], dtype=np.float32) * gain
                    )

                processed += 1
                if processed % 50 == 0:
                    _time.sleep(0)   # yield GIL — keeps Tk main thread responsive
                if progress_callback and processed % 200 == 0:
                    progress_callback(processed, total_events)

            # Widen designated tracks before panning
            if use_chorus:
                track_L, track_R = widener.process(track_mono)
            else:
                track_L = track_R = track_mono

            # Constant-power pan into the stereo master buffers
            angle  = (pan + 1.0) * math.pi / 4.0
            gain_L = math.cos(angle)
            gain_R = math.sin(angle)
            buffer_L += track_L * gain_L
            buffer_R += track_R * gain_R

        # Normalise both channels together to preserve the stereo image
        peak = float(max(np.max(np.abs(buffer_L)), np.max(np.abs(buffer_R))))
        if peak > 0.85:
            scale     = 0.85 / peak
            buffer_L *= scale
            buffer_R *= scale

        return np.stack([buffer_L, buffer_R], axis=1)
