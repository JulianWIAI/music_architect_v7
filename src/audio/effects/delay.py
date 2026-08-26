"""Tempo-synced multi-tap delay effect."""

import numpy as np


class TempoDelay:
    """
    Tempo-synced multi-tap delay with up to four feedback taps.

    The delay time is derived from the BPM and a rhythmic subdivision so that
    echoes land precisely on musical grid positions.  Each successive tap is
    attenuated by feedback^k, creating a natural echo fade.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz.
    bpm : float
        Tempo in beats per minute.
    subdivision : str
        Rhythmic subdivision key from SUBDIVISIONS.  Defaults to 'dotted_1/8'.
    feedback : float
        Echo level multiplier per tap.  Clamped to [0, 0.85] to prevent
        runaway feedback.
    wet : float
        Mix level of the delay signal added to the dry output.
    """

    # Map subdivision names to beat multipliers
    SUBDIVISIONS: dict = {
        "1/4": 1.0,
        "1/8": 0.5,
        "dotted_1/4": 1.5,
        "dotted_1/8": 0.75,
        "1/16": 0.25,
        "triplet_1/8": 1.0 / 3.0,
        "triplet_1/4": 2.0 / 3.0,
    }

    def __init__(
        self,
        sample_rate: int,
        bpm: float,
        subdivision: str = "dotted_1/8",
        feedback: float = 0.35,
        wet: float = 0.2,
    ) -> None:
        self._sample_rate = int(sample_rate)
        self._bpm = float(bpm)
        self._wet = float(wet)

        # Clamp feedback to a safe maximum to avoid divergence
        self._feedback = min(float(feedback), 0.85)

        # Seconds per beat
        beat_s = 60.0 / self._bpm

        # Look up subdivision factor (fall back to 1/8 note if key unknown)
        factor = self.SUBDIVISIONS.get(subdivision, self.SUBDIVISIONS["1/8"])

        # Base delay in samples for tap k=1
        self._delay_samples = int(beat_s * factor * self._sample_rate)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        Apply multi-tap delay to an audio buffer.

        Four taps are generated at integer multiples of the base delay time.
        Tap k has gain = feedback^k.  Taps whose delay would exceed the
        buffer length are silently skipped.

        Parameters
        ----------
        audio : np.ndarray
            Input audio as float32 (mono).

        Returns
        -------
        np.ndarray
            Dry signal plus wet delay signal as float32.
        """
        audio = np.asarray(audio, dtype=np.float32)
        n = len(audio)

        if n == 0 or self._delay_samples <= 0:
            return audio.copy()

        wet_signal = np.zeros(n, dtype=np.float32)

        # Build four taps: k = 1, 2, 3, 4
        for k in range(1, 5):
            tap_delay = self._delay_samples * k
            if tap_delay >= n:
                # This tap and all subsequent ones would exceed the buffer
                break
            gain = self._feedback ** k
            # The delayed signal starts at sample tap_delay in the original;
            # we place it at position 0 in the output (shift left by tap_delay)
            wet_signal[: n - tap_delay] += audio[tap_delay:] * gain

        return audio + wet_signal * self._wet
