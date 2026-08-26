"""
src/audio/stereo_panner.py
───────────────────────────
Constant-power stereo panner and per-track pan / chorus tables.

Default pan positions follow music-production conventions:
  - Sub-frequency content (kick, bass) stays at centre for mono compatibility
    on club systems where low-end summing to mono is standard.
  - Melodic lead sits slightly left — the convention for the primary voice.
  - Chords push slightly right to balance the image against the lead.
  - Arp and FX push further right as rhythmic / textural counterpoints.
  - Pad and texture are centred but widened by ChorusWidener.

Usage::

    from src.audio.stereo_panner import StereoPanner, TRACK_PAN, CHORUS_TRACKS

    L, R = StereoPanner.pan(mono_samples, pan=TRACK_PAN['lead'])
"""
from __future__ import annotations

import math

import numpy as np


# ---------------------------------------------------------------------------
# Per-track pan positions
# Range: -1.0 (hard left) | 0.0 (centre) | +1.0 (hard right)
# ---------------------------------------------------------------------------

TRACK_PAN: dict[str, float] = {
    'drums':      0.00,   # kick: dead centre — sub-bass must stay mono
    'percussion': -0.10,  # snare/clap: slightly left (natural drum image)
    'bass':        0.00,  # bass: centre — low-frequency mono for club systems
    'lead':       -0.15,  # melody: slightly left (primary voice convention)
    'chords':      0.20,  # chords: slightly right (balances against lead)
    'pad':         0.00,  # pad: centre — ChorusWidener provides the width
    'arp':         0.25,  # arp: right of centre (rhythmic counterpoint)
    'stabs':      -0.20,  # stabs: slightly left (call to the arp's response)
    'texture':     0.00,  # texture: centre — ChorusWidener provides the width
    'fx':          0.30,  # fx: right (ear-candy, non-structural)
}

# Tracks that receive chorus widening before panning.
# Widening is applied to the full track buffer so the stereo image is
# coherent across the whole render, not fragmented per note.
CHORUS_TRACKS: frozenset[str] = frozenset({'pad', 'texture', 'lead'})

# Composition MIDI track name → groove key.
# Mirrors _COMP_TRACK_TO_GROOVE_KEY in app.py / mixer_panel.py but lives
# here so stereo_panner can be used by the rendering layer without importing
# from the GUI layer.
COMP_TRACK_TO_GROOVE_KEY: dict[str, str] = {
    '01_Kick':       'drums',
    '02_Percussion': 'percussion',
    '03_Bass':       'bass',
    '04_Melody':     'lead',
    '05_Chords':     'chords',
    '06_Pad':        'pad',
    '07_Arp':        'arp',
    '08_Stabs':      'stabs',
    '09_Texture':    'texture',
    '10_FX':         'fx',
}


class StereoPanner:
    """
    Applies constant-power panning to a mono numpy array.

    Constant-power panning preserves perceived loudness across the stereo
    field by using a quarter-circle gain law:

        L_gain = cos(θ),   R_gain = sin(θ)   where θ ∈ [0, π/2]

    At centre (pan=0.0, θ=π/4) both channels are at 1/√2 ≈ −3 dB so a
    stereo mix summed to mono produces 0 dB — full mono compatibility.
    """

    @staticmethod
    def pan(
        samples: np.ndarray,
        pan: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Pan a mono array to a left/right pair.

        Parameters
        ----------
        samples : np.ndarray, shape (N,)
            Mono input, any float dtype.
        pan : float
            Position in [-1.0, +1.0].  -1 = hard left, 0 = centre, +1 = hard right.

        Returns
        -------
        (L, R) : each np.ndarray shape (N,), float32.
        """
        pan_c  = float(max(-1.0, min(1.0, pan)))
        angle  = (pan_c + 1.0) * math.pi / 4.0   # [-1,+1] → [0, π/2]
        gain_L = math.cos(angle)
        gain_R = math.sin(angle)
        arr    = np.asarray(samples, dtype=np.float32)
        return arr * gain_L, arr * gain_R
