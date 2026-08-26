"""
Instrument timbre definitions and percussion sample synthesisers.

INSTRUMENT_TIMBRES maps GM program numbers to additive-synthesis parameters.
The drum functions generate short audio buffers for each percussion type using
simple synthesis techniques (pitch sweep for kick, noise for snare/hihat).
"""

import math
import random as _random
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.rendering.instrument_params import PercussionParams


INSTRUMENT_TIMBRES = {
    # Acoustic / Electric Piano
    0:  {'harmonics': [1.0, 0.5, 0.25, 0.12, 0.06], 'adsr': (0.005, 0.3, 0.3, 0.4),  'type': 'sine'},
    4:  {'harmonics': [1.0, 0.6, 0.3, 0.15],         'adsr': (0.005, 0.2, 0.4, 0.3),  'type': 'sine'},
    # Bass
    33: {'harmonics': [1.0, 0.7, 0.3],               'adsr': (0.01,  0.1, 0.8, 0.1),  'type': 'sine'},
    38: {'harmonics': [1.0, 0.8, 0.5, 0.3],          'adsr': (0.005, 0.05, 0.9, 0.05),'type': 'saw'},
    87: {'harmonics': [1.0, 0.9, 0.6, 0.4],          'adsr': (0.002, 0.05, 0.85, 0.05),'type': 'saw'},
    # Strings
    40: {'harmonics': [1.0, 0.4, 0.2, 0.1],          'adsr': (0.15,  0.1, 0.8, 0.3),  'type': 'sine'},
    42: {'harmonics': [1.0, 0.5, 0.25],               'adsr': (0.1,   0.1, 0.85, 0.3), 'type': 'sine'},
    43: {'harmonics': [1.0, 0.6, 0.3],                'adsr': (0.08,  0.1, 0.8, 0.2),  'type': 'sine'},
    46: {'harmonics': [1.0, 0.3, 0.15],               'adsr': (0.02,  0.1, 0.7, 0.3),  'type': 'sine'},
    48: {'harmonics': [1.0, 0.4, 0.2, 0.1],          'adsr': (0.2,   0.15, 0.75, 0.4),'type': 'sine'},
    # Lead synths
    80: {'harmonics': [1.0, 0.5, 0.3, 0.2, 0.1],    'adsr': (0.01,  0.05, 0.8, 0.1),  'type': 'saw'},
    81: {'harmonics': [1.0, 0.7, 0.5, 0.3],          'adsr': (0.01,  0.05, 0.85, 0.1), 'type': 'square'},
    # Orchestra
    68: {'harmonics': [1.0, 0.3, 0.1],               'adsr': (0.05,  0.1, 0.7, 0.2),  'type': 'sine'},
    # Pads
    88: {'harmonics': [1.0, 0.3, 0.15, 0.08],        'adsr': (0.4,   0.2, 0.7, 0.5),  'type': 'sine'},
    89: {'harmonics': [1.0, 0.4, 0.2, 0.1],          'adsr': (0.3,   0.2, 0.65, 0.6), 'type': 'sine'},
    92: {'harmonics': [1.0, 0.2, 0.1],               'adsr': (0.5,   0.3, 0.6, 0.8),  'type': 'sine'},
    95: {'harmonics': [1.0, 0.5, 0.3, 0.2],          'adsr': (0.3,   0.15, 0.7, 0.5), 'type': 'saw'},
    # Vibraphone / Bells
    11: {'harmonics': [1.0, 0.6, 0.4, 0.2, 0.1],    'adsr': (0.005, 0.3, 0.2, 0.5),  'type': 'sine'},
}

DEFAULT_TIMBRE = {'harmonics': [1.0, 0.3, 0.1], 'adsr': (0.01, 0.1, 0.7, 0.2), 'type': 'sine'}


# ─── PERCUSSION SYNTHESIS ─────────────────────────────────────────────────────

def generate_kick_sample(sample_rate: int = 44100, duration: float = 0.3) -> List[float]:
    """Synthesise a kick drum using a pitched sine with exponential decay and frequency sweep."""
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        freq = 40 + 110 * math.exp(-t * 30)
        amp = math.exp(-t * 8)
        s = math.sin(2 * math.pi * freq * t) * amp
        if t < 0.005:
            s += (0.005 - t) / 0.005 * 0.5
        samples.append(s * 0.8)
    return samples


def generate_snare_sample(sample_rate: int = 44100, duration: float = 0.2) -> List[float]:
    """Synthesise a snare drum mixing a decaying tone with bandpass noise."""
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        tone = math.sin(2 * math.pi * 180 * t) * math.exp(-t * 20)
        noise = (_random.random() * 2 - 1) * math.exp(-t * 12)
        samples.append((tone * 0.4 + noise * 0.6) * 0.7)
    return samples


def generate_hihat_sample(
    sample_rate: int = 44100, duration: float = 0.08, is_open: bool = False
) -> List[float]:
    """Synthesise a hi-hat as high-passed noise with fast (closed) or slow (open) decay."""
    dur = 0.3 if is_open else duration
    n = int(sample_rate * dur)
    decay = 5 if is_open else 25
    samples = []
    for i in range(n):
        t = i / sample_rate
        noise = (_random.random() * 2 - 1) * math.exp(-t * decay)
        hp = noise * (0.8 + 0.2 * math.sin(2 * math.pi * 8000 * t))
        samples.append(hp * 0.4)
    return samples


def generate_crash_sample(sample_rate: int = 44100, duration: float = 1.0) -> List[float]:
    """Synthesise a crash cymbal as slow-decaying noise with a high partial."""
    n = int(sample_rate * duration)
    samples = []
    for i in range(n):
        t = i / sample_rate
        noise = (_random.random() * 2 - 1) * math.exp(-t * 3)
        tone = math.sin(2 * math.pi * 3000 * t) * math.exp(-t * 5) * 0.2
        samples.append((noise * 0.7 + tone) * 0.35)
    return samples


# ─── PARAM-DRIVEN PERCUSSION SYNTHESIS ───────────────────────────────────────
# These functions accept a PercussionParams object and produce a rich variety
# of sounds from the same underlying algorithm.  Import is deferred to avoid
# a circular dependency — instrument_params imports nothing from this module.


def generate_perc_from_params(params: 'PercussionParams', sample_rate: int = 44100) -> List[float]:
    """
    Synthesise a percussion hit from a PercussionParams preset.

    Algorithm:
      1. Pitch-swept sine oscillator (start → end over sweep_ms).
      2. White noise layer weighted by params.noise_amount.
      3. Optional secondary resonant body tone (body_freq_hz > 0).
      4. Exponential decay envelope over params.decay_ms.
      5. Transient click at t=0 to sharpen the attack.
      6. Soft tanh saturation scaled by params.drive.

    Music theory note: params.pitch_end_hz should be tuned to the root or
    perfect-fifth of the song key so the kick sits harmonically in the mix.
    The 'Car Crash' and 'Factory' presets use noise_amount > 0.5 and are
    intentionally atonal — high-pass them above 150 Hz to avoid masking bass.
    """
    n         = int(params.decay_ms / 1000.0 * sample_rate)
    sweep_n   = int(params.sweep_ms  / 1000.0 * sample_rate)
    samples   = []
    phase     = 0.0
    phase_b   = 0.0   # secondary body oscillator phase

    for i in range(n):
        t = i / sample_rate

        # Exponential pitch sweep from start to end frequency
        frac = 1.0 - math.exp(-5.0 * i / max(1, sweep_n))
        freq = params.pitch_start_hz + (params.pitch_end_hz - params.pitch_start_hz) * frac

        # Amplitude envelope: rt60-style exponential decay
        amp = math.exp(-t * 6.908 / (params.decay_ms / 1000.0))

        # Oscillator (incrementally to preserve phase coherence across freq changes)
        phase += 2.0 * math.pi * freq / sample_rate
        tone = math.sin(phase)

        # White noise
        noise = _random.random() * 2.0 - 1.0

        # Mix tone and noise according to noise_amount
        s = tone * (1.0 - params.noise_amount) + noise * params.noise_amount

        # Optional secondary resonant body (metallic colouration)
        if params.body_freq_hz > 0:
            phase_b += 2.0 * math.pi * params.body_freq_hz / sample_rate
            body_amp = math.exp(-t * 15.0)
            s += math.sin(phase_b) * body_amp * 0.3

        # Apply amplitude envelope
        s *= amp

        # Short transient click at t=0 sharpens the attack (mimics physical impact)
        if t < 0.003:
            s += (0.003 - t) / 0.003 * 0.25

        # Soft tanh saturation — adds harmonics and warmth
        if params.drive > 0.0:
            drive_factor = 1.0 + params.drive * 3.0
            denom = math.tanh(drive_factor)
            if denom > 1e-6:
                s = math.tanh(s * drive_factor) / denom

        samples.append(s * 0.8)

    return samples
