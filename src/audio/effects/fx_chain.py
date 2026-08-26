"""
FX chain that wires TransientShaper -> ThreeBandEQ -> SchroederReverb -> TempoDelay.

Genre EQ defaults and reverb parameters can be derived automatically from a
GenreProfile (src/midi/genre_profiles.py) or from built-in per-genre tables.
Any setting can be overridden via user_params.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .reverb import SchroederReverb
from .delay import TempoDelay
from .eq import ThreeBandEQ
from .transient_shaper import TransientShaper


# ---------------------------------------------------------------------------
# Per-genre EQ defaults: (low_gain_db, mid_gain_db, high_gain_db)
# ---------------------------------------------------------------------------
_EQ_DEFAULTS: dict[str, tuple[float, float, float]] = {
    "trap":       ( 3.0, -2.0,  1.0),
    "techno":     ( 2.0, -4.0,  3.0),
    "house":      ( 2.0,  0.0,  2.0),
    "phonk":      ( 5.0, -3.0, -1.0),
    "dnb":        ( 3.0, -3.0,  4.0),
    "hiphop":     ( 3.0, -1.0,  0.0),
    "edm":        ( 2.0, -1.0,  3.0),
    "pop":        ( 1.0,  1.0,  2.0),
    "jpop":       ( 0.0,  2.0,  3.0),
    "cinematic":  ( 1.0, -1.0,  2.0),
    "classical":  ( 0.0,  0.0,  1.0),
}

# Map GenreProfile.reverb_size strings to room_size float values
_REVERB_SIZE_MAP: dict[str, float] = {
    "small":  0.20,
    "medium": 0.45,
    "large":  0.70,
    "hall":   0.90,
}


class FxChain:
    """
    Configurable effects chain for the Music Architect V7 audio pipeline.

    Processing order (applied in sequence):
      1. TransientShaper — shapes attack and sustain dynamics.
      2. ThreeBandEQ     — genre-tuned tonal balance.
      3. SchroederReverb — room/space simulation.
      4. TempoDelay      — tempo-synced multi-tap echo.

    The chain can be configured from three sources (in increasing priority):
      a. Built-in per-genre defaults.
      b. A GenreProfile dataclass (extracts reverb, pre-delay, EQ values).
      c. user_params dict — can override any individual parameter.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz.
    bpm : float
        Tempo in beats per minute (used for delay sync and pre-delay calculation).
    genre : str
        Genre key for default look-up (e.g. 'trap', 'techno').  Case-insensitive.
    profile : GenreProfile or None
        Optional GenreProfile dataclass.  When provided, overrides the genre
        defaults with profile-specific reverb and timing values.
    user_params : dict or None
        Optional parameter overrides.  Recognised keys:

        ==================== ============================================
        Key                  Effect
        ==================== ============================================
        reverb_wet           Reverb wet level [0, 1]
        reverb_room_size     Room size [0, 1]
        reverb_decay_s       Reverb RT60 in seconds
        delay_subdivision    Delay subdivision string (see TempoDelay)
        delay_feedback       Delay feedback [0, 0.85]
        delay_wet            Delay wet level [0, 1]
        eq_low               Low-shelf gain in dB
        eq_mid               Peaking mid gain in dB
        eq_high              High-shelf gain in dB
        transient_attack_db  Attack boost in dB
        transient_sustain_db Sustain cut/boost in dB
        ==================== ============================================
    """

    def __init__(
        self,
        sample_rate: int,
        bpm: float,
        genre: str = "",
        profile=None,
        user_params: Optional[dict] = None,
    ) -> None:
        self._sample_rate = int(sample_rate)
        self._bpm = float(bpm)
        genre_key = genre.strip().lower()

        user = user_params or {}

        # ------------------------------------------------------------------
        # Step 1: resolve EQ gains from genre defaults
        # ------------------------------------------------------------------
        eq_low, eq_mid, eq_high = _EQ_DEFAULTS.get(genre_key, (0.0, 0.0, 0.0))

        # ------------------------------------------------------------------
        # Step 2: resolve reverb parameters
        # ------------------------------------------------------------------
        beat_ms = 60000.0 / self._bpm  # one beat in milliseconds

        if profile is not None:
            # Derive room size from the profile's verbal reverb_size label
            room_size = _REVERB_SIZE_MAP.get(
                str(profile.reverb_size).lower(), 0.4
            )
            # Use the midpoint of the profile's decay range as the target RT60
            decay_s = (
                float(profile.reverb_decay_s_min)
                + float(profile.reverb_decay_s_max)
            ) / 2.0
            # Convert note-fraction to milliseconds
            pre_delay_ms = float(profile.pre_delay_note_fraction) * beat_ms
        else:
            # Sensible defaults when no profile is provided
            room_size = 0.4
            decay_s = 1.2
            pre_delay_ms = 0.125 * beat_ms  # eighth-note pre-delay

        # Reverb wet defaults: moderate by default
        reverb_wet = 0.25
        reverb_dry = 1.0

        # ------------------------------------------------------------------
        # Step 3: delay defaults
        # ------------------------------------------------------------------
        delay_subdivision = "dotted_1/8"
        delay_feedback = 0.35
        delay_wet = 0.20

        # ------------------------------------------------------------------
        # Step 4: transient shaper defaults
        # ------------------------------------------------------------------
        transient_attack_db = 3.0
        transient_sustain_db = 0.0

        # ------------------------------------------------------------------
        # Step 5: apply user overrides
        # ------------------------------------------------------------------
        eq_low = float(user.get("eq_low", eq_low))
        eq_mid = float(user.get("eq_mid", eq_mid))
        eq_high = float(user.get("eq_high", eq_high))

        reverb_wet = float(user.get("reverb_wet", reverb_wet))
        room_size = float(user.get("reverb_room_size", room_size))
        decay_s = float(user.get("reverb_decay_s", decay_s))

        delay_subdivision = str(user.get("delay_subdivision", delay_subdivision))
        delay_feedback = float(user.get("delay_feedback", delay_feedback))
        delay_wet = float(user.get("delay_wet", delay_wet))

        transient_attack_db = float(
            user.get("transient_attack_db", transient_attack_db)
        )
        transient_sustain_db = float(
            user.get("transient_sustain_db", transient_sustain_db)
        )

        # ------------------------------------------------------------------
        # Step 6: construct all four processors
        # ------------------------------------------------------------------
        self._transient = TransientShaper(
            sample_rate=self._sample_rate,
            attack_boost_db=transient_attack_db,
            sustain_cut_db=transient_sustain_db,
        )

        self._eq = ThreeBandEQ(
            sample_rate=self._sample_rate,
            low_gain_db=eq_low,
            mid_gain_db=eq_mid,
            high_gain_db=eq_high,
        )

        self._reverb = SchroederReverb(
            sample_rate=self._sample_rate,
            room_size=room_size,
            decay_s=decay_s,
            pre_delay_ms=pre_delay_ms,
            wet=reverb_wet,
            dry=reverb_dry,
        )

        self._delay = TempoDelay(
            sample_rate=self._sample_rate,
            bpm=self._bpm,
            subdivision=delay_subdivision,
            feedback=delay_feedback,
            wet=delay_wet,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        Run audio through the full effects chain.

        Processing order: TransientShaper -> ThreeBandEQ -> SchroederReverb
        -> TempoDelay.

        Parameters
        ----------
        audio : np.ndarray
            Input audio.  Any numeric dtype is accepted; internally converted
            to float32 before processing.

        Returns
        -------
        np.ndarray
            Processed audio as float32.
        """
        # Ensure float32 input throughout the chain
        x = np.asarray(audio, dtype=np.float32)

        # 1. Shape transient attack and sustain dynamics
        x = self._transient.process(x)

        # 2. Apply genre-tuned tonal balance
        x = self._eq.process(x)

        # 3. Add space / room ambience
        x = self._reverb.process(x)

        # 4. Add tempo-synced echoes
        x = self._delay.process(x)

        return x.astype(np.float32)
