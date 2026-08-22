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

# Block size for DspSession processing — matches the LFO engine's internal
# granularity and the C++ SaturationProcessor's smoothing window.
_DSP_BLOCK_SIZE: int = 512


def _apply_dsp_session(
    samples: list,
    composition: dict,
    sample_rate: int,
) -> list:
    """
    Run the PCM buffer through a DspSession built from the composition's genre.

    Returns the processed samples list.  On any error returns the input
    unchanged so the render always produces valid audio.
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

        session = DspSession(
            profile     = profile,
            bpm         = bpm,
            sample_rate = sample_rate,
            seed        = None,
            smoothing_ms = 5.0,
        )

        buf    = np.array(samples, dtype=np.float32)
        chunks = []
        for start in range(0, len(buf), _DSP_BLOCK_SIZE):
            chunk = buf[start:start + _DSP_BLOCK_SIZE]
            chunks.append(session.process_block(chunk))

        return np.concatenate(chunks).tolist() if chunks else samples

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
        self, composition: dict, wav_path: str, progress_callback=None
    ) -> str:
        """
        Render a composition dict directly to WAV using the built-in synthesiser.

        After synthesis the audio passes through a DspSession (saturation +
        LFO-driven drive) derived from the genre profile embedded in the
        composition config.  FluidSynth compositions are rendered directly
        from the MIDI file and do not go through this DSP pass (FluidSynth
        applies its own reverb/chorus internally).

        *composition* must be a dict in the format produced by CompositionEngine.
        """
        print('Synthesising audio...')
        samples = self.builtin.render_composition(composition, progress_callback)

        # Apply genre-specific saturation and LFO automation.
        samples = _apply_dsp_session(samples, composition, self.sample_rate)

        # Apply kick-triggered sidechain gain reduction.
        samples = apply_sidechain(samples, composition, self.sample_rate)

        write_wav(wav_path, samples, self.sample_rate)
        duration = len(samples) / self.sample_rate
        print(f'WAV exported: {wav_path} ({duration:.1f}s)')
        return wav_path
