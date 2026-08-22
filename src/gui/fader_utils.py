"""
src/gui/fader_utils.py
──────────────────────
Shared fader taper maths used by every volume/gain slider in the GUI.

All sliders use a piecewise-linear dB curve (the standard DAW fader law):
  - Unity (0 dB) sits at 80 % of slider travel.
  - The lower 80 % spans −60 dB to 0 dB (practical mixing range).
  - The upper 20 % spans 0 dB to +6 dB (boost headroom).
  - Position 0 is treated as −∞ (gain = 0, silence).

The internal slider range is 0–1000 integer steps (``_GAIN_STEPS``).

Public API
----------
_pos_to_db(pos)     Convert normalised position [0, 1] → dB.
_db_to_pos(db)      Convert dB → normalised position [0, 1].
gain_db_to_volume(db)
                    Convert dB to a linear volume multiplier [0, 1]
                    clamped for composition-engine velocity scaling.
_GAIN_STEPS         int — internal integer scale used by all sliders.
_GAIN_MIN_DB        float — practical floor (displayed as −∞).
_GAIN_MAX_DB        float — maximum boost.
_GAIN_INF_FLOOR     float — anything ≤ this is treated as −∞.
_GAIN_UNITY_POS     float — normalised position at 0 dB.
"""

from __future__ import annotations

import math

# ── Fader constants ───────────────────────────────────────────────────────────

_GAIN_UNITY_POS = 0.80    # normalised fader position at 0 dB (unity gain)
_GAIN_MAX_DB    = 6.0     # maximum boost in dB (fader fully up)
_GAIN_MIN_DB    = -60.0   # practical floor — displayed to the user as −∞
_GAIN_INF_FLOOR = -59.9   # anything ≤ this is treated as −∞ (linear gain 0.0)
_GAIN_STEPS     = 1000    # slider integer range: 0 – 1000


def _pos_to_db(pos: float) -> float:
    """
    Map a normalised fader position [0, 1] to dB.

    Piecewise linear in dB space:
      pos = 0.00 → −60 dB  (displayed as −∞)
      pos = 0.80 →   0 dB  (unity gain)
      pos = 1.00 →  +6 dB
    """
    pos = max(0.0, min(1.0, pos))
    if pos <= 0.001:
        return _GAIN_MIN_DB
    if pos <= _GAIN_UNITY_POS:
        # Linear stretch: −60 → 0 dB over the bottom 80 % of travel
        return _GAIN_MIN_DB + (pos / _GAIN_UNITY_POS) * (-_GAIN_MIN_DB)
    # Linear stretch: 0 → +6 dB over the top 20 % of travel
    return (pos - _GAIN_UNITY_POS) / (1.0 - _GAIN_UNITY_POS) * _GAIN_MAX_DB


def _db_to_pos(db: float) -> float:
    """
    Map a dB value to a normalised fader position [0, 1].

    Inverse of _pos_to_db; clamps to [0, 1].
    """
    if db <= _GAIN_MIN_DB:
        return 0.0
    if db <= 0.0:
        return (db - _GAIN_MIN_DB) / (-_GAIN_MIN_DB) * _GAIN_UNITY_POS
    return _GAIN_UNITY_POS + (db / _GAIN_MAX_DB) * (1.0 - _GAIN_UNITY_POS)


def gain_db_to_volume(db: float) -> float:
    """
    Convert a dB value to a linear volume multiplier for the composition engine.

    The composition engine uses a 0–1 volume factor that scales MIDI velocities.
    Positive dB is clamped to 1.0 (no velocity boost beyond 100 %) because
    velocities are already capped at 127 by the note generator.

    Returns 0.0 for −∞ (silence), 1.0 for 0 dB and above.
    """
    if db <= _GAIN_INF_FLOOR:
        return 0.0
    linear = 10.0 ** (db / 20.0)
    return max(0.0, min(1.0, linear))
