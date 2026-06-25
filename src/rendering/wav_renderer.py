"""
WAVRenderer — top-level audio rendering orchestrator.

Tries FluidSynth first for high-quality output; falls back transparently to the
built-in additive synthesiser when FluidSynth is unavailable.
"""

from src.rendering.builtin_synthesizer import BuiltinSynthesizer
from src.rendering.fluidsynth_renderer import FluidSynthRenderer
from src.rendering.wav_writer import write_wav


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

        *composition* must be a dict in the format produced by CompositionEngine.
        """
        print('Synthesising audio...')
        samples = self.builtin.render_composition(composition, progress_callback)
        write_wav(wav_path, samples, self.sample_rate)
        duration = len(samples) / self.sample_rate
        print(f'WAV exported: {wav_path} ({duration:.1f}s)')
        return wav_path
