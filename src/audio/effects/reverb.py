"""Schroeder-style reverb using a seeded random impulse response convolved via numpy FFT."""

import math
import numpy as np


class SchroederReverb:
    """
    Algorithmic reverb built from a noise-based impulse response (IR).

    The IR is generated once at construction time with a fixed random seed (42)
    so that output is fully deterministic across runs and platforms.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz (e.g. 44100 or 48000).
    room_size : float
        Room size coefficient in [0, 1].  Controls diffusion window length.
    decay_s : float
        RT60 decay time in seconds (time for the IR to fall -60 dB).
    pre_delay_ms : float
        Pre-delay in milliseconds prepended before the IR onset.
    wet : float
        Wet mix level in [0, 1].
    dry : float
        Dry mix level in [0, 1].
    """

    def __init__(
        self,
        sample_rate: int,
        room_size: float = 0.45,
        decay_s: float = 1.5,
        pre_delay_ms: float = 10.0,
        wet: float = 0.25,
        dry: float = 1.0,
    ) -> None:
        self._sample_rate = int(sample_rate)
        self._room_size = float(room_size)
        self._decay_s = float(decay_s)
        self._pre_delay_ms = float(pre_delay_ms)
        self._wet = float(wet)
        self._dry = float(dry)

        self._ir = self._build_ir()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_ir(self) -> np.ndarray:
        """
        Build the impulse response used for convolution reverb.

        Steps:
          1. Generate Gaussian noise with a fixed seed for reproducibility.
          2. Apply an exponential decay envelope (RT60).
          3. Diffuse with a Hanning window convolution.
          4. Prepend pre-delay silence.
          5. Normalise leaving headroom.

        Returns
        -------
        np.ndarray
            float32 impulse response array.
        """
        sr = self._sample_rate
        rng = np.random.default_rng(42)  # fixed seed for determinism

        n = int(self._decay_s * sr)
        if n < 1:
            n = 1

        # Step 1: noise
        ir = rng.standard_normal(n).astype(np.float64)

        # Step 2: RT60 exponential decay — reaches -60 dB at t = decay_s
        t = np.arange(n, dtype=np.float64) / sr
        ir *= np.exp(-t * 6.908 / self._decay_s)

        # Step 3: diffusion via Hanning window convolution
        win_len = max(1, int(self._room_size * 80))
        if win_len > 1:
            window = np.hanning(win_len)
            window /= window.sum()  # keep gain neutral
            ir = np.convolve(ir, window, mode="same")

        # Step 4: pre-delay silence
        pre_delay_samples = int(self._pre_delay_ms / 1000.0 * sr)
        if pre_delay_samples > 0:
            ir = np.concatenate([np.zeros(pre_delay_samples, dtype=np.float64), ir])

        # Step 5: normalise with headroom
        peak = np.max(np.abs(ir))
        if peak > 0.0:
            ir /= peak * 5.0

        return ir.astype(np.float32)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        Apply reverb to an audio buffer.

        The convolution is performed in the frequency domain using numpy's
        real-FFT routines (overlap-add is not used; the full buffer is
        convolved at once, which is suitable for offline/block processing).

        Parameters
        ----------
        audio : np.ndarray
            Input audio as float32 (mono).

        Returns
        -------
        np.ndarray
            Wet/dry mixed output as float32, same length as input.
        """
        audio = np.asarray(audio, dtype=np.float32)
        n_audio = len(audio)
        n_ir = len(self._ir)

        if n_audio == 0 or n_ir == 0:
            return audio.copy()

        # Next power of two large enough for linear (non-circular) convolution
        linear_len = n_audio + n_ir - 1
        fft_size = 1
        while fft_size < linear_len:
            fft_size <<= 1

        # Frequency-domain convolution
        audio_f = np.fft.rfft(audio, n=fft_size)
        ir_f = np.fft.rfft(self._ir, n=fft_size)
        wet_full = np.fft.irfft(audio_f * ir_f, n=fft_size)

        # Trim to input length (drop the tail that extends beyond the input)
        wet_result = wet_full[:n_audio].astype(np.float32)

        return audio * self._dry + wet_result * self._wet
