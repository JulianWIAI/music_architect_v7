"""
═══════════════════════════════════════════════════════════════════════
  WAV RENDERER — MIDI to WAV Synthesizer
  Converts MIDI files to WAV audio using software synthesis.
  
  Supports two backends:
  1. FluidSynth (high quality, requires fluidsynth + soundfont)
  2. Built-in sine/wave synthesizer (always available, lighter quality)
  
  The built-in synth generates unique timbres per GM program using
  additive synthesis with harmonics, ADSR envelopes, and effects.
═══════════════════════════════════════════════════════════════════════
"""

import struct
import math
import wave
import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Optional

try:
    from midiutil import MIDIFile
    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════
#  WAV WRITER
# ═══════════════════════════════════════════════════════════════════════

def write_wav(filepath: str, samples: List[float], sample_rate: int = 44100):
    """Write mono float samples to WAV file."""
    filepath = str(filepath)
    n_samples = len(samples)
    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            packed = struct.pack('<h', int(clamped * 32767))
            wav.writeframes(packed)


def write_wav_stereo(filepath: str, left: List[float], right: List[float],
                     sample_rate: int = 44100):
    """Write stereo float samples to WAV file."""
    filepath = str(filepath)
    n = min(len(left), len(right))
    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(n):
            l = max(-1.0, min(1.0, left[i]))
            r = max(-1.0, min(1.0, right[i]))
            packed = struct.pack('<hh', int(l * 32767), int(r * 32767))
            wav.writeframes(packed)


# ═══════════════════════════════════════════════════════════════════════
#  ADSR ENVELOPE
# ═══════════════════════════════════════════════════════════════════════

class ADSREnvelope:
    """Attack-Decay-Sustain-Release envelope generator."""

    def __init__(self, attack=0.01, decay=0.1, sustain=0.7, release=0.15):
        self.attack = attack
        self.decay = decay
        self.sustain = sustain
        self.release = release

    def get_amplitude(self, t: float, duration: float) -> float:
        """Get envelope amplitude at time t for a note of given duration."""
        if t < 0:
            return 0.0
        if t < self.attack:
            return t / self.attack
        t2 = t - self.attack
        if t2 < self.decay:
            return 1.0 - (1.0 - self.sustain) * (t2 / self.decay)
        if t < duration:
            return self.sustain
        t3 = t - duration
        if t3 < self.release:
            return self.sustain * (1.0 - t3 / self.release)
        return 0.0


# ═══════════════════════════════════════════════════════════════════════
#  INSTRUMENT DEFINITIONS (Additive Synthesis Timbres)
# ═══════════════════════════════════════════════════════════════════════

INSTRUMENT_TIMBRES = {
    # Piano-like
    0: {'harmonics': [1.0, 0.5, 0.25, 0.12, 0.06], 'adsr': (0.005, 0.3, 0.3, 0.4), 'type': 'sine'},
    4: {'harmonics': [1.0, 0.6, 0.3, 0.15], 'adsr': (0.005, 0.2, 0.4, 0.3), 'type': 'sine'},  # E.Piano
    # Bass
    33: {'harmonics': [1.0, 0.7, 0.3], 'adsr': (0.01, 0.1, 0.8, 0.1), 'type': 'sine'},  # Finger bass
    38: {'harmonics': [1.0, 0.8, 0.5, 0.3], 'adsr': (0.005, 0.05, 0.9, 0.05), 'type': 'saw'},  # Synth bass
    87: {'harmonics': [1.0, 0.9, 0.6, 0.4], 'adsr': (0.002, 0.05, 0.85, 0.05), 'type': 'saw'},  # Lead bass
    # Strings
    40: {'harmonics': [1.0, 0.4, 0.2, 0.1], 'adsr': (0.15, 0.1, 0.8, 0.3), 'type': 'sine'},  # Violin
    42: {'harmonics': [1.0, 0.5, 0.25], 'adsr': (0.1, 0.1, 0.85, 0.3), 'type': 'sine'},  # Cello
    43: {'harmonics': [1.0, 0.6, 0.3], 'adsr': (0.08, 0.1, 0.8, 0.2), 'type': 'sine'},  # Contrabass
    46: {'harmonics': [1.0, 0.3, 0.15], 'adsr': (0.02, 0.1, 0.7, 0.3), 'type': 'sine'},  # Harp
    48: {'harmonics': [1.0, 0.4, 0.2, 0.1], 'adsr': (0.2, 0.15, 0.75, 0.4), 'type': 'sine'},  # Strings
    # Lead synth
    80: {'harmonics': [1.0, 0.5, 0.3, 0.2, 0.1], 'adsr': (0.01, 0.05, 0.8, 0.1), 'type': 'saw'},
    81: {'harmonics': [1.0, 0.7, 0.5, 0.3], 'adsr': (0.01, 0.05, 0.85, 0.1), 'type': 'square'},
    # Orchestra
    68: {'harmonics': [1.0, 0.3, 0.1], 'adsr': (0.05, 0.1, 0.7, 0.2), 'type': 'sine'},  # Oboe
    # Pads
    88: {'harmonics': [1.0, 0.3, 0.15, 0.08], 'adsr': (0.4, 0.2, 0.7, 0.5), 'type': 'sine'},
    89: {'harmonics': [1.0, 0.4, 0.2, 0.1], 'adsr': (0.3, 0.2, 0.65, 0.6), 'type': 'sine'},
    92: {'harmonics': [1.0, 0.2, 0.1], 'adsr': (0.5, 0.3, 0.6, 0.8), 'type': 'sine'},  # Space pad
    95: {'harmonics': [1.0, 0.5, 0.3, 0.2], 'adsr': (0.3, 0.15, 0.7, 0.5), 'type': 'saw'},  # Sweep
    # Vibraphone / bells
    11: {'harmonics': [1.0, 0.6, 0.4, 0.2, 0.1], 'adsr': (0.005, 0.3, 0.2, 0.5), 'type': 'sine'},
}

# Default timbre for unknown instruments
DEFAULT_TIMBRE = {'harmonics': [1.0, 0.3, 0.1], 'adsr': (0.01, 0.1, 0.7, 0.2), 'type': 'sine'}


# ═══════════════════════════════════════════════════════════════════════
#  DRUM SAMPLES (Simple noise-based synthesis)
# ═══════════════════════════════════════════════════════════════════════

def generate_kick_sample(sample_rate: int = 44100, duration: float = 0.3) -> List[float]:
    """Synthesize a kick drum sound."""
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        # Pitch drop from 150Hz to 40Hz
        freq = 40 + 110 * math.exp(-t * 30)
        amp = math.exp(-t * 8)
        s = math.sin(2 * math.pi * freq * t) * amp
        # Add click
        if t < 0.005:
            s += (0.005 - t) / 0.005 * 0.5
        samples.append(s * 0.8)
    return samples


def generate_snare_sample(sample_rate: int = 44100, duration: float = 0.2) -> List[float]:
    """Synthesize a snare drum sound."""
    import random as rnd
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        # Tone component
        tone = math.sin(2 * math.pi * 180 * t) * math.exp(-t * 20)
        # Noise component
        noise = (rnd.random() * 2 - 1) * math.exp(-t * 12)
        samples.append((tone * 0.4 + noise * 0.6) * 0.7)
    return samples


def generate_hihat_sample(sample_rate: int = 44100, duration: float = 0.08,
                          is_open: bool = False) -> List[float]:
    """Synthesize a hi-hat sound."""
    import random as rnd
    dur = 0.3 if is_open else duration
    n = int(sample_rate * dur)
    decay = 5 if is_open else 25
    samples = []
    for i in range(n):
        t = i / sample_rate
        noise = (rnd.random() * 2 - 1) * math.exp(-t * decay)
        # High-pass filter approximation
        hp = noise * (0.8 + 0.2 * math.sin(2 * math.pi * 8000 * t))
        samples.append(hp * 0.4)
    return samples


def generate_crash_sample(sample_rate: int = 44100, duration: float = 1.0) -> List[float]:
    """Synthesize a crash cymbal."""
    import random as rnd
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        noise = (rnd.random() * 2 - 1) * math.exp(-t * 3)
        tone = math.sin(2 * math.pi * 3000 * t) * math.exp(-t * 5) * 0.2
        samples.append((noise * 0.7 + tone) * 0.35)
    return samples


# ═══════════════════════════════════════════════════════════════════════
#  BUILT-IN SOFTWARE SYNTHESIZER
# ═══════════════════════════════════════════════════════════════════════

class BuiltinSynthesizer:
    """
    Software synthesizer using additive synthesis.
    Converts MIDI-like events to audio samples.
    """

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.drum_cache = {}

    def midi_to_freq(self, midi_note: int) -> float:
        """Convert MIDI note to frequency."""
        return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))

    def oscillator(self, freq: float, t: float, osc_type: str = 'sine') -> float:
        """Generate oscillator sample."""
        phase = 2 * math.pi * freq * t
        if osc_type == 'sine':
            return math.sin(phase)
        elif osc_type == 'saw':
            return 2.0 * (freq * t % 1.0) - 1.0
        elif osc_type == 'square':
            return 1.0 if math.sin(phase) > 0 else -1.0
        elif osc_type == 'triangle':
            return 2.0 * abs(2.0 * (freq * t % 1.0) - 1.0) - 1.0
        return math.sin(phase)

    def synthesize_note(self, midi_note: int, start_time: float, duration: float,
                        velocity: float, program: int = 0) -> Tuple[int, List[float]]:
        """
        Synthesize a single note.
        Returns: (start_sample_index, samples)
        """
        freq = self.midi_to_freq(midi_note)
        timbre = INSTRUMENT_TIMBRES.get(program, DEFAULT_TIMBRE)
        harmonics = timbre['harmonics']
        adsr_params = timbre['adsr']
        osc_type = timbre['type']

        envelope = ADSREnvelope(*adsr_params)
        total_dur = duration + adsr_params[3]  # Add release time
        n_samples = int(total_dur * self.sample_rate)
        start_idx = int(start_time * self.sample_rate)

        vel_scale = velocity / 127.0
        samples = []

        for i in range(n_samples):
            t = i / self.sample_rate
            amp = envelope.get_amplitude(t, duration) * vel_scale

            # Additive synthesis with harmonics
            sample = 0.0
            for h_idx, h_amp in enumerate(harmonics):
                harmonic_freq = freq * (h_idx + 1)
                if harmonic_freq > self.sample_rate / 2:
                    break
                sample += self.oscillator(harmonic_freq, t, osc_type) * h_amp

            # Normalize by number of harmonics
            sample /= sum(harmonics)
            samples.append(sample * amp * 0.4)

        return start_idx, samples

    def synthesize_drum(self, midi_note: int, start_time: float,
                        velocity: float) -> Tuple[int, List[float]]:
        """Synthesize a drum hit."""
        vel_scale = velocity / 127.0
        start_idx = int(start_time * self.sample_rate)

        # Generate or cache drum samples
        if midi_note not in self.drum_cache:
            if midi_note == 36:  # Kick
                self.drum_cache[midi_note] = generate_kick_sample(self.sample_rate)
            elif midi_note in (38, 37, 39, 40):  # Snare/clap
                self.drum_cache[midi_note] = generate_snare_sample(self.sample_rate)
            elif midi_note in (42, 44):  # Closed hat
                self.drum_cache[midi_note] = generate_hihat_sample(self.sample_rate, is_open=False)
            elif midi_note == 46:  # Open hat
                self.drum_cache[midi_note] = generate_hihat_sample(self.sample_rate, is_open=True)
            elif midi_note == 49:  # Crash
                self.drum_cache[midi_note] = generate_crash_sample(self.sample_rate)
            elif midi_note == 51:  # Ride
                self.drum_cache[midi_note] = generate_hihat_sample(self.sample_rate, 0.15, True)
            elif midi_note in (45, 47, 50):  # Toms
                self.drum_cache[midi_note] = generate_kick_sample(self.sample_rate, 0.15)
            else:
                self.drum_cache[midi_note] = generate_snare_sample(self.sample_rate, 0.1)

        raw = self.drum_cache[midi_note]
        scaled = [s * vel_scale for s in raw]
        return start_idx, scaled

    def render_composition(self, composition: dict,
                           progress_callback=None) -> List[float]:
        """
        Render a full composition to audio samples.
        composition: output from CompositionEngine.compose()
        """
        bpm = composition['config']['bpm']
        beat_duration = 60.0 / bpm
        total_beats = composition['total_bars'] * 4
        total_seconds = total_beats * beat_duration + 5  # Extra for release tails
        total_samples = int(total_seconds * self.sample_rate)

        # Master buffer
        buffer = [0.0] * total_samples

        tracks = composition.get('tracks', {})
        track_info = composition.get('track_info', {})
        total_events = sum(len(events) for events in tracks.values())
        processed = 0

        for track_name, events in tracks.items():
            info = track_info.get(track_name, {})
            channel = info.get('channel', 0)
            program = info.get('program', 0)
            is_drum = (channel == 9)

            for event in events:
                if len(event) < 4:
                    continue

                time_beats, duration_beats, pitch, velocity = event[:4]
                time_sec = time_beats * beat_duration
                duration_sec = duration_beats * beat_duration

                if is_drum:
                    start_idx, samples = self.synthesize_drum(pitch, time_sec, velocity)
                else:
                    start_idx, samples = self.synthesize_note(
                        pitch, time_sec, duration_sec, velocity, program
                    )

                # Mix into buffer
                for i, s in enumerate(samples):
                    idx = start_idx + i
                    if 0 <= idx < total_samples:
                        buffer[idx] += s

                processed += 1
                if progress_callback and processed % 200 == 0:
                    progress_callback(processed, total_events)

        # Normalize to prevent clipping
        peak = max(abs(s) for s in buffer) if buffer else 1.0
        if peak > 0:
            scale = 0.85 / peak
            buffer = [s * scale for s in buffer]

        return buffer


# ═══════════════════════════════════════════════════════════════════════
#  FLUIDSYNTH RENDERER (High Quality)
# ═══════════════════════════════════════════════════════════════════════

class FluidSynthRenderer:
    """
    Render MIDI to WAV using FluidSynth command-line tool.
    Requires: fluidsynth installed + a .sf2 soundfont file.
    """

    def __init__(self, soundfont_path: str = None):
        self.soundfont = soundfont_path
        self._find_soundfont()

    def _find_soundfont(self):
        """Try to locate a soundfont if none specified."""
        if self.soundfont and os.path.exists(self.soundfont):
            return

        # Common locations
        search_paths = [
            r"C:\soundfonts\FluidR3_GM.sf2",
            r"C:\soundfonts\GeneralUser_GS.sf2",
            "/usr/share/sounds/sf2/FluidR3_GM.sf2",
            "/usr/share/soundfonts/FluidR3_GM.sf2",
            os.path.expanduser("~/soundfonts/FluidR3_GM.sf2"),
        ]
        for p in search_paths:
            if os.path.exists(p):
                self.soundfont = p
                return

    def is_available(self) -> bool:
        """Check if FluidSynth is available."""
        try:
            result = subprocess.run(['fluidsynth', '--version'],
                                    capture_output=True, timeout=5)
            return result.returncode == 0 and self.soundfont is not None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def render(self, midi_path: str, wav_path: str, sample_rate: int = 44100) -> bool:
        """Render MIDI to WAV using FluidSynth."""
        if not self.is_available():
            return False

        try:
            cmd = [
                'fluidsynth', '-ni',
                self.soundfont,
                midi_path,
                '-F', wav_path,
                '-r', str(sample_rate),
                '-g', '0.8',  # Gain
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            return result.returncode == 0 and os.path.exists(wav_path)
        except Exception as e:
            print(f"FluidSynth error: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════
#  MAIN RENDERER CLASS
# ═══════════════════════════════════════════════════════════════════════

class WAVRenderer:
    """
    Main renderer class. Tries FluidSynth first, falls back to built-in synth.
    """

    def __init__(self, soundfont_path: str = None, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.fluidsynth = FluidSynthRenderer(soundfont_path)
        self.builtin = BuiltinSynthesizer(sample_rate)
        self.use_fluidsynth = self.fluidsynth.is_available()

    def render_midi_to_wav(self, midi_path: str, wav_path: str,
                           progress_callback=None) -> str:
        """Render a MIDI file to WAV."""
        if self.use_fluidsynth:
            print("◢ RENDERING WITH FLUIDSYNTH ◣")
            success = self.fluidsynth.render(midi_path, wav_path, self.sample_rate)
            if success:
                print(f"✓ WAV exported: {wav_path}")
                return wav_path
            print("  FluidSynth failed, falling back to built-in synth...")

        print("◢ RENDERING WITH BUILT-IN SYNTH ◣")
        # This requires a composition dict, not just a MIDI file
        # For MIDI file rendering, we'd need to parse the MIDI
        # For now, return empty - the GUI will use render_composition instead
        return ""

    def render_composition_to_wav(self, composition: dict, wav_path: str,
                                  progress_callback=None) -> str:
        """Render a composition dict directly to WAV (bypasses MIDI parsing)."""
        print("◢ SYNTHESIZING AUDIO ◣")
        samples = self.builtin.render_composition(composition, progress_callback)

        write_wav(wav_path, samples, self.sample_rate)
        duration = len(samples) / self.sample_rate
        print(f"✓ WAV exported: {wav_path} ({duration:.1f}s)")
        return wav_path


# ═══════════════════════════════════════════════════════════════════════
#  CLI USAGE
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("WAV Renderer — Test")
    renderer = WAVRenderer()
    print(f"FluidSynth available: {renderer.use_fluidsynth}")
    print("Use render_composition_to_wav() with a composition dict from the engine.")
