"""
WAVRenderer — top-level audio rendering orchestrator.

Tries FluidSynth first for high-quality output; falls back transparently to the
built-in additive synthesiser when FluidSynth is unavailable.

After synthesis, a DspSession is applied to the full PCM buffer when a genre
profile can be resolved from the composition's config dict.  This routes the
audio through the genre's saturation character (tape_soft, tube_tanh, etc.) and
LFO-driven drive automation so the preview output reflects the same timbral
signature as the final export.
"""

from __future__ import annotations

import numpy as np

from src.rendering.builtin_synthesizer import BuiltinSynthesizer
from src.rendering.fluidsynth_renderer import FluidSynthRenderer
from src.rendering.wav_writer import write_wav
from src.audio.sidechain_processor import apply_sidechain
from src.sampling.sample_engine import SampleEngine
from src.sampling.sample_loader import load_audio_file

# Block size for DspSession processing — matches the LFO engine's internal
# granularity and the C++ SaturationProcessor's smoothing window.
_DSP_BLOCK_SIZE: int = 512


def _apply_fx_chain(
    samples: np.ndarray,
    composition: dict,
    sample_rate: int,
    instrument_params: dict = None,
) -> np.ndarray:
    """
    Run the PCM buffer through the full effects chain: TransientShaper →
    ThreeBandEQ → SchroederReverb → TempoDelay.

    Accepts mono (N,) or stereo (N, 2) arrays.  Stereo input is processed
    with separate FxChain instances for L and R so each stateful processor
    (reverb, delay) maintains independent internal state per channel.

    Returns the input unchanged on any error so the render always produces
    valid audio even if the FX chain import fails.
    """
    try:
        from src.audio.effects.fx_chain import FxChain
        from src.midi.genre_profiles import GenreProfileLibrary

        cfg   = composition.get('config', {})
        genre = cfg.get('genre', '')
        bpm   = float(cfg.get('bpm', 120.0))

        if not genre:
            return samples

        profile = GenreProfileLibrary().get(genre, bpm)

        arr = np.asarray(samples, dtype=np.float32)

        if arr.ndim == 2:
            # Stereo: independent chain instances so each channel's reverb tail
            # and delay feedback are computed separately — preserves stereo image.
            chain_L = FxChain(sample_rate=sample_rate, bpm=bpm, genre=genre, profile=profile)
            chain_R = FxChain(sample_rate=sample_rate, bpm=bpm, genre=genre, profile=profile)
            out = np.stack([chain_L.process(arr[:, 0]),
                            chain_R.process(arr[:, 1])], axis=1)
        else:
            chain = FxChain(sample_rate=sample_rate, bpm=bpm, genre=genre, profile=profile)
            out   = chain.process(arr)

        # Re-normalise after the FX chain to prevent clipping.
        peak = float(np.max(np.abs(out)))
        if peak > 0.85:
            out *= 0.85 / peak

        return out

    except Exception:
        return samples   # graceful fallback — raw synthesis audio is still valid


def _apply_dsp_session(
    samples: np.ndarray,
    composition: dict,
    sample_rate: int,
) -> np.ndarray:
    """
    Run the PCM buffer through a DspSession built from the composition's genre.

    Accepts mono (N,) or stereo (N, 2) arrays.  Stereo input is processed with
    separate DspSession instances for L and R so the LFO-driven saturation
    automation runs independently per channel.

    Returns the input unchanged on any error so the render always produces
    valid audio.
    """
    try:
        from src.audio.dsp_bridge import DspSession
        from src.midi.genre_profiles import GenreProfileLibrary

        cfg   = composition.get('config', {})
        genre = cfg.get('genre')
        bpm   = float(cfg.get('bpm', 120.0))

        if not genre:
            return samples

        profile = GenreProfileLibrary().get(genre, bpm)

        # Skip the DSP pass entirely when drive is effectively zero — avoids
        # a processing round-trip for genres with purely decorative profiles.
        if profile.drive_pct_max < 1.0 and profile.saturation_type == 'none':
            return samples

        arr = np.asarray(samples, dtype=np.float32)

        def _process_channel(ch: np.ndarray) -> np.ndarray:
            session = DspSession(
                profile      = profile,
                bpm          = bpm,
                sample_rate  = sample_rate,
                seed         = None,
                smoothing_ms = 5.0,
            )
            chunks = []
            for start in range(0, len(ch), _DSP_BLOCK_SIZE):
                chunks.append(session.process_block(ch[start:start + _DSP_BLOCK_SIZE]))
            return np.concatenate(chunks) if chunks else ch

        if arr.ndim == 2:
            return np.stack([_process_channel(arr[:, 0]),
                             _process_channel(arr[:, 1])], axis=1)

        return _process_channel(arr)

    except Exception:
        return samples   # graceful fallback — raw synthesis audio is still valid


class WAVRenderer:
    """
    Unified renderer that delegates to FluidSynth or the built-in synthesiser.

    Usage::

        renderer = WAVRenderer()
        renderer.render_composition_to_wav(composition, 'output.wav')
    """

    def __init__(self, soundfont_path: str = None, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.fluidsynth = FluidSynthRenderer(soundfont_path)
        self.builtin = BuiltinSynthesizer(sample_rate)
        self.use_fluidsynth = self.fluidsynth.is_available()

    def render_midi_to_wav(
        self, midi_path: str, wav_path: str, progress_callback=None
    ) -> str:
        """
        Render a MIDI file to WAV.

        When FluidSynth is available it is used directly. Otherwise the method
        returns an empty string because the built-in synthesiser requires a
        composition dict rather than a parsed MIDI file.
        """
        if self.use_fluidsynth:
            print('Rendering with FluidSynth...')
            success = self.fluidsynth.render(midi_path, wav_path, self.sample_rate)
            if success:
                print(f'WAV exported: {wav_path}')
                return wav_path
            print('FluidSynth failed, built-in synth requires a composition dict.')
        return ''

    def render_composition_to_wav(
        self,
        composition: dict,
        wav_path: str,
        progress_callback=None,
        sample_assignments: dict = None,
        instrument_params: dict = None,
    ) -> str:
        """
        Render a composition dict directly to WAV using the built-in synthesiser.

        After synthesis the audio passes through a DspSession (saturation +
        LFO-driven drive) derived from the genre profile embedded in the
        composition config.  FluidSynth compositions are rendered directly
        from the MIDI file and do not go through this DSP pass (FluidSynth
        applies its own reverb/chorus internally).

        Parameters
        ----------
        composition       : Composition dict from CompositionEngine.
        wav_path          : Output file path.
        progress_callback : Optional callable(processed, total) for UI progress.
        sample_assignments: Optional {builder_key: file_path} mapping.  When
                            provided, tracks with an assigned audio file use
                            SamplePlayer instead of the built-in synthesiser
                            (samples take priority over GM instrument selection).
        """
        # Pre-load samples synchronously before entering the render loop.
        # SampleEngine.load_from_assignments() prints load errors but never raises.
        sample_engine = None
        if sample_assignments:
            sample_engine = SampleEngine(self.sample_rate)
            sample_engine.load_from_assignments(sample_assignments)
            # Discard engine when nothing was actually loaded (avoids per-event lookup overhead)
            if not any(sample_engine.is_loaded(t) for t in (
                '01_Kick', '02_Percussion',
                '03_Bass', '04_Melody', '05_Chords', '06_Pad',
                '07_Arp', '08_Stabs', '09_Texture', '10_FX',
            )):
                sample_engine = None

        print('Synthesising audio...')
        samples = self.builtin.render_composition(
            composition, progress_callback,
            sample_engine=sample_engine,
            instrument_params=instrument_params,
        )

        # Apply genre-specific saturation and LFO automation.
        samples = _apply_dsp_session(samples, composition, self.sample_rate)

        # Apply kick-triggered sidechain gain reduction.
        samples = apply_sidechain(samples, composition, self.sample_rate)

        # Apply the full effects chain: transient shaping, EQ, reverb, delay.
        samples = _apply_fx_chain(samples, composition, self.sample_rate, instrument_params)

        arr      = np.asarray(samples, dtype=np.float32)
        write_wav(wav_path, arr, self.sample_rate)
        duration = arr.shape[0] / self.sample_rate
        print(f'WAV exported: {wav_path} ({duration:.1f}s)')
        return wav_path
