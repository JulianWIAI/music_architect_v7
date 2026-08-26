"""
src/rendering/instrument_params.py
────────────────────────────────────
Per-instrument synthesis parameter system.

Exposes named presets for each instrument role so the built-in synthesiser
can produce a wide variety of timbres without needing external samples.

PercussionParams controls the synthesis of drum sounds:
  pitch_start_hz  -- oscillator frequency at t=0 (start of sweep)
  pitch_end_hz    -- oscillator frequency after the sweep completes
  sweep_ms        -- duration of the pitch sweep in milliseconds
  noise_amount    -- 0.0 = pure pitched tone, 1.0 = pure noise
  decay_ms        -- total decay envelope length in milliseconds
  body_freq_hz    -- secondary resonant frequency (metallic / body colour), 0 = off
  drive           -- soft saturation amount 0.0-1.0

MelodicParams controls melodic track synthesis:
  harmonic_richness  -- 0.0 = few harmonics, 1.0 = all harmonics
  brightness         -- weight toward higher harmonics (0=dark, 1=bright)
  attack_ms          -- ADSR attack in milliseconds
  decay_ms           -- ADSR decay in milliseconds
  sustain_level      -- ADSR sustain 0.0-1.0
  release_ms         -- ADSR release in milliseconds
  noise_amount       -- breath/noise mix 0.0-1.0
  drive              -- soft saturation 0.0-1.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Union


# ── Percussion dataclass ───────────────────────────────────────────────────────

@dataclass
class PercussionParams:
    """
    Synthesis parameters for a single percussion sound.

    The synthesiser drives a pitch-swept oscillator mixed with white noise,
    then runs the result through an exponential decay envelope and an optional
    soft saturation stage.

    Validation (enforced in __post_init__):
      - noise_amount clamped to [0.0, 1.0]
      - drive clamped to [0.0, 1.0]
      - decay_ms must be > 0
      - sweep_ms must be > 0
    """

    # Oscillator pitch sweep
    pitch_start_hz: float   # Oscillator frequency at t=0 (Hz)
    pitch_end_hz:   float   # Oscillator frequency at end of sweep (Hz)
    sweep_ms:       float   # Duration of the pitch sweep (ms); must be > 0

    # Texture
    noise_amount:   float   # 0.0 = pure tone, 1.0 = pure noise

    # Envelope
    decay_ms:       float   # Total decay length (ms); must be > 0

    # Resonant body colouration
    body_freq_hz:   float = 0.0   # Secondary resonant frequency (Hz); 0 = off

    # Saturation
    drive:          float = 0.0   # Soft saturation amount; clamped to [0.0, 1.0]

    def __post_init__(self) -> None:
        # Clamp bounded parameters
        self.noise_amount = max(0.0, min(1.0, self.noise_amount))
        self.drive        = max(0.0, min(1.0, self.drive))

        # Require strictly positive time constants
        if self.decay_ms <= 0:
            raise ValueError(
                f"PercussionParams.decay_ms must be > 0, got {self.decay_ms}"
            )
        if self.sweep_ms <= 0:
            raise ValueError(
                f"PercussionParams.sweep_ms must be > 0, got {self.sweep_ms}"
            )


# ── Melodic dataclass ──────────────────────────────────────────────────────────

@dataclass
class MelodicParams:
    """
    Synthesis parameters for a single melodic (pitched) instrument.

    The synthesiser builds an additive stack of harmonics whose amplitudes
    are shaped by harmonic_richness and brightness, then applies a standard
    ADSR envelope.  An optional noise layer adds breath or air, and soft
    saturation adds warmth or aggression.

    Validation (enforced in __post_init__):
      - noise_amount clamped to [0.0, 1.0]
      - drive clamped to [0.0, 1.0]
      - sustain_level clamped to [0.0, 1.0]
      - harmonic_richness clamped to [0.0, 1.0]
      - brightness clamped to [0.0, 1.0]
      - decay_ms must be > 0
    """

    # Harmonic content
    harmonic_richness: float   # 0.0 = sparse harmonics, 1.0 = full harmonic series
    brightness:        float   # 0.0 = weight toward fundamentals, 1.0 = weight toward highs

    # ADSR envelope (all times in ms)
    attack_ms:    float   # Attack time (ms)
    decay_ms:     float   # Decay time (ms); must be > 0
    sustain_level: float  # Sustain amplitude level [0.0, 1.0]
    release_ms:   float   # Release time (ms)

    # Texture and saturation
    noise_amount: float = 0.0   # Breath/noise mix [0.0, 1.0]
    drive:        float = 0.0   # Soft saturation [0.0, 1.0]

    def __post_init__(self) -> None:
        # Clamp bounded parameters
        self.noise_amount      = max(0.0, min(1.0, self.noise_amount))
        self.drive             = max(0.0, min(1.0, self.drive))
        self.sustain_level     = max(0.0, min(1.0, self.sustain_level))
        self.harmonic_richness = max(0.0, min(1.0, self.harmonic_richness))
        self.brightness        = max(0.0, min(1.0, self.brightness))

        # Require strictly positive decay
        if self.decay_ms <= 0:
            raise ValueError(
                f"MelodicParams.decay_ms must be > 0, got {self.decay_ms}"
            )


# ── Kick presets ──────────────────────────────────────────────────────────────
# Pitch sweep from a high transient start down to a low sub fundamental.
# noise_amount is kept very low so the pitched character dominates.

KICK_PRESETS: Dict[str, PercussionParams] = {
    'Punchy': PercussionParams(
        pitch_start_hz=180, pitch_end_hz=45,  sweep_ms=40,
        noise_amount=0.05,  decay_ms=280, body_freq_hz=0,    drive=0.10,
    ),
    'Space': PercussionParams(
        pitch_start_hz=120, pitch_end_hz=35,  sweep_ms=90,
        noise_amount=0.02,  decay_ms=600, body_freq_hz=0,    drive=0.05,
    ),
    'Sub 808': PercussionParams(
        pitch_start_hz=55,  pitch_end_hz=38,  sweep_ms=120,
        noise_amount=0.00,  decay_ms=900, body_freq_hz=0,    drive=0.00,
    ),
    'Acoustic': PercussionParams(
        pitch_start_hz=90,  pitch_end_hz=58,  sweep_ms=18,
        noise_amount=0.20,  decay_ms=150, body_freq_hz=0,    drive=0.15,
    ),
    'Industrial': PercussionParams(
        pitch_start_hz=220, pitch_end_hz=50,  sweep_ms=25,
        noise_amount=0.35,  decay_ms=200, body_freq_hz=0,    drive=0.50,
    ),
    'Car Crash': PercussionParams(
        pitch_start_hz=500, pitch_end_hz=40,  sweep_ms=15,
        noise_amount=0.75,  decay_ms=180, body_freq_hz=0,    drive=0.70,
    ),
    'Factory': PercussionParams(
        pitch_start_hz=1200, pitch_end_hz=900, sweep_ms=30,
        noise_amount=0.60,   decay_ms=200, body_freq_hz=1100, drive=0.60,
    ),
}

# ── Snare presets ─────────────────────────────────────────────────────────────
# Balanced mix of a pitched body tone and broadband noise.
# body_freq_hz adds a metallic ringing partial where present.

SNARE_PRESETS: Dict[str, PercussionParams] = {
    'Standard': PercussionParams(
        pitch_start_hz=200, pitch_end_hz=140, sweep_ms=20,
        noise_amount=0.60,  decay_ms=150, body_freq_hz=0,    drive=0.10,
    ),
    'Clap': PercussionParams(
        pitch_start_hz=280, pitch_end_hz=200, sweep_ms=5,
        noise_amount=0.85,  decay_ms=80,  body_freq_hz=0,    drive=0.20,
    ),
    'Deep': PercussionParams(
        pitch_start_hz=140, pitch_end_hz=100, sweep_ms=25,
        noise_amount=0.50,  decay_ms=250, body_freq_hz=0,    drive=0.10,
    ),
    'Trap Snap': PercussionParams(
        pitch_start_hz=220, pitch_end_hz=160, sweep_ms=10,
        noise_amount=0.75,  decay_ms=120, body_freq_hz=400,  drive=0.30,
    ),
    'Industrial': PercussionParams(
        pitch_start_hz=350, pitch_end_hz=220, sweep_ms=15,
        noise_amount=0.85,  decay_ms=120, body_freq_hz=600,  drive=0.70,
    ),
}

# ── Hi-hat presets ────────────────────────────────────────────────────────────
# Noise-dominant: pitch fields are largely symbolic (the synthesiser can use
# them to tune a band-pass filter centre) but noise_amount >= 0.90 throughout.

HIHAT_PRESETS: Dict[str, PercussionParams] = {
    'Crisp': PercussionParams(
        pitch_start_hz=8000, pitch_end_hz=6000, sweep_ms=5,
        noise_amount=0.95,   decay_ms=60,  body_freq_hz=0,   drive=0.00,
    ),
    'Open Washy': PercussionParams(
        pitch_start_hz=7000, pitch_end_hz=5000, sweep_ms=10,
        noise_amount=0.95,   decay_ms=300, body_freq_hz=0,   drive=0.00,
    ),
    'Tight': PercussionParams(
        pitch_start_hz=9000, pitch_end_hz=7000, sweep_ms=3,
        noise_amount=0.95,   decay_ms=30,  body_freq_hz=0,   drive=0.00,
    ),
    'Vintage': PercussionParams(
        pitch_start_hz=6000, pitch_end_hz=4500, sweep_ms=8,
        noise_amount=0.90,   decay_ms=80,  body_freq_hz=200, drive=0.30,
    ),
}

# ── Melodic presets ───────────────────────────────────────────────────────────
# Cover the full range from warm pads to aggressive leads and organic textures.

MELODIC_PRESETS: Dict[str, MelodicParams] = {
    'Warm': MelodicParams(
        harmonic_richness=0.6, brightness=0.2,
        attack_ms=15,  decay_ms=200, sustain_level=0.70, release_ms=300,
        noise_amount=0.00, drive=0.05,
    ),
    'Bright': MelodicParams(
        harmonic_richness=0.9, brightness=0.8,
        attack_ms=5,   decay_ms=100, sustain_level=0.80, release_ms=200,
        noise_amount=0.00, drive=0.10,
    ),
    'Pluck': MelodicParams(
        harmonic_richness=0.7, brightness=0.6,
        attack_ms=2,   decay_ms=80,  sustain_level=0.30, release_ms=100,
        noise_amount=0.00, drive=0.10,
    ),
    'Pad': MelodicParams(
        harmonic_richness=0.5, brightness=0.3,
        attack_ms=400, decay_ms=200, sustain_level=0.80, release_ms=600,
        noise_amount=0.00, drive=0.00,
    ),
    'Aggressive': MelodicParams(
        harmonic_richness=1.0, brightness=0.9,
        attack_ms=3,   decay_ms=50,  sustain_level=0.90, release_ms=150,
        noise_amount=0.05, drive=0.50,
    ),
    'Vintage': MelodicParams(
        harmonic_richness=0.6, brightness=0.3,
        attack_ms=20,  decay_ms=150, sustain_level=0.60, release_ms=200,
        noise_amount=0.08, drive=0.20,
    ),
    'Organic': MelodicParams(
        harmonic_richness=0.5, brightness=0.5,
        attack_ms=30,  decay_ms=180, sustain_level=0.65, release_ms=350,
        noise_amount=0.06, drive=0.05,
    ),
}

# ── Internal registry ─────────────────────────────────────────────────────────
# Maps role names to their preset dictionaries for unified lookup.

_REGISTRY: Dict[str, Dict[str, Union[PercussionParams, MelodicParams]]] = {
    'kick':    KICK_PRESETS,
    'snare':   SNARE_PRESETS,
    'hihat':   HIHAT_PRESETS,
    'melodic': MELODIC_PRESETS,
}


# ── Public API ─────────────────────────────────────────────────────────────────

def list_presets(role: str) -> List[str]:
    """
    Return a sorted list of preset names available for *role*.

    Parameters
    ----------
    role:
        One of 'kick', 'snare', 'hihat', 'melodic'.

    Returns
    -------
    list[str]
        Sorted preset names, or an empty list if *role* is not recognised.

    Examples
    --------
    >>> list_presets('kick')
    ['Acoustic', 'Car Crash', 'Factory', 'Industrial', 'Punchy', 'Space', 'Sub 808']
    """
    bucket = _REGISTRY.get(role, {})
    return sorted(bucket.keys())


def get_preset(
    role: str,
    name: str,
) -> Optional[Union[PercussionParams, MelodicParams]]:
    """
    Retrieve a single named preset for *role*.

    Parameters
    ----------
    role:
        One of 'kick', 'snare', 'hihat', 'melodic'.
    name:
        Preset name (case-sensitive, e.g. 'Punchy', 'Warm').

    Returns
    -------
    PercussionParams | MelodicParams | None
        The matching preset object, or None if either *role* or *name* is
        not found in the registry.

    Examples
    --------
    >>> p = get_preset('kick', 'Punchy')
    >>> p.pitch_start_hz
    180
    """
    bucket = _REGISTRY.get(role)
    if bucket is None:
        return None
    return bucket.get(name)
