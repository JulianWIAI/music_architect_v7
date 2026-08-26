"""Three-band parametric EQ using Audio EQ Cookbook biquad filter formulas."""

import math
import numpy as np


class ThreeBandEQ:
    """
    Three-band equaliser: low shelf, peaking mid, high shelf.

    All filter coefficients are computed using the Audio EQ Cookbook
    formulas (Robert Bristow-Johnson).  Filtering is performed sample-by-
    sample in Direct Form II Transposed for numerical stability.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz.
    low_gain_db : float
        Low-shelf gain in dB (positive = boost, negative = cut).
    mid_gain_db : float
        Peaking band gain in dB.
    high_gain_db : float
        High-shelf gain in dB.
    low_freq_hz : float
        Low-shelf corner frequency in Hz.
    mid_freq_hz : float
        Peaking band centre frequency in Hz.
    high_freq_hz : float
        High-shelf corner frequency in Hz.
    mid_q : float
        Q factor for the peaking mid band (bandwidth control).
    """

    def __init__(
        self,
        sample_rate: int,
        low_gain_db: float = 0.0,
        mid_gain_db: float = 0.0,
        high_gain_db: float = 0.0,
        low_freq_hz: float = 80.0,
        mid_freq_hz: float = 1000.0,
        high_freq_hz: float = 8000.0,
        mid_q: float = 1.5,
    ) -> None:
        self._sr = int(sample_rate)
        self._low_gain_db = float(low_gain_db)
        self._mid_gain_db = float(mid_gain_db)
        self._high_gain_db = float(high_gain_db)
        self._low_freq_hz = float(low_freq_hz)
        self._mid_freq_hz = float(mid_freq_hz)
        self._high_freq_hz = float(high_freq_hz)
        self._mid_q = float(mid_q)

        # Pre-compute coefficients at construction time
        self._b_low, self._a_low = self._biquad_coeffs_low_shelf(
            self._low_freq_hz, self._low_gain_db
        )
        self._b_mid, self._a_mid = self._biquad_coeffs_peak(
            self._mid_freq_hz, self._mid_gain_db, self._mid_q
        )
        self._b_high, self._a_high = self._biquad_coeffs_high_shelf(
            self._high_freq_hz, self._high_gain_db
        )

    # ------------------------------------------------------------------
    # Coefficient builders (Audio EQ Cookbook)
    # ------------------------------------------------------------------

    def _biquad_coeffs_low_shelf(
        self, freq_hz: float, gain_db: float, S: float = 1.0
    ):
        """
        Compute biquad coefficients for a low-shelf filter.

        Parameters
        ----------
        freq_hz : float
            Shelf corner frequency in Hz.
        gain_db : float
            Shelf gain in dB.
        S : float
            Shelf slope (1.0 = maximum steepness without overshoot).

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            Normalised (b, a) coefficient arrays of length 3.
        """
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * freq_hz / self._sr
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        alpha_S = sin_w0 / 2.0 * math.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)
        sqrt_A = math.sqrt(A)

        b0 = A * ((A + 1) - (A - 1) * cos_w0 + 2 * sqrt_A * alpha_S)
        b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
        b2 = A * ((A + 1) - (A - 1) * cos_w0 - 2 * sqrt_A * alpha_S)
        a0 = (A + 1) + (A - 1) * cos_w0 + 2 * sqrt_A * alpha_S
        a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
        a2 = (A + 1) + (A - 1) * cos_w0 - 2 * sqrt_A * alpha_S

        b = np.array([b0, b1, b2], dtype=np.float64) / a0
        a = np.array([a0, a1, a2], dtype=np.float64) / a0
        return b, a

    def _biquad_coeffs_peak(self, freq_hz: float, gain_db: float, Q: float):
        """
        Compute biquad coefficients for a peaking EQ filter.

        Parameters
        ----------
        freq_hz : float
            Centre frequency in Hz.
        gain_db : float
            Peak/dip gain in dB.
        Q : float
            Quality factor (higher Q = narrower band).

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            Normalised (b, a) coefficient arrays of length 3.
        """
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * freq_hz / self._sr
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        alpha = sin_w0 / (2.0 * Q)

        b0 = 1.0 + alpha * A
        b1 = -2.0 * cos_w0
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha / A

        b = np.array([b0, b1, b2], dtype=np.float64) / a0
        a = np.array([a0, a1, a2], dtype=np.float64) / a0
        return b, a

    def _biquad_coeffs_high_shelf(
        self, freq_hz: float, gain_db: float, S: float = 1.0
    ):
        """
        Compute biquad coefficients for a high-shelf filter.

        Parameters
        ----------
        freq_hz : float
            Shelf corner frequency in Hz.
        gain_db : float
            Shelf gain in dB.
        S : float
            Shelf slope (1.0 = maximum steepness without overshoot).

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            Normalised (b, a) coefficient arrays of length 3.
        """
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * freq_hz / self._sr
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        alpha_S = sin_w0 / 2.0 * math.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)
        sqrt_A = math.sqrt(A)

        b0 = A * ((A + 1) + (A - 1) * cos_w0 + 2 * sqrt_A * alpha_S)
        b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
        b2 = A * ((A + 1) + (A - 1) * cos_w0 - 2 * sqrt_A * alpha_S)
        a0 = (A + 1) - (A - 1) * cos_w0 + 2 * sqrt_A * alpha_S
        a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
        a2 = (A + 1) - (A - 1) * cos_w0 - 2 * sqrt_A * alpha_S

        b = np.array([b0, b1, b2], dtype=np.float64) / a0
        a = np.array([a0, a1, a2], dtype=np.float64) / a0
        return b, a

    # ------------------------------------------------------------------
    # Filter application
    # ------------------------------------------------------------------

    def _apply_biquad(
        self, b: np.ndarray, a: np.ndarray, x: np.ndarray
    ) -> np.ndarray:
        """
        Apply a biquad filter in Direct Form II Transposed.

        The filter is implemented sample-by-sample to avoid scipy dependency.
        State is local to each call (filter resets between process() calls for
        each band — sufficient for block processing).

        Parameters
        ----------
        b : np.ndarray
            Numerator coefficients [b0, b1, b2] (normalised, a[0]=1).
        a : np.ndarray
            Denominator coefficients [a0, a1, a2] (normalised, a[0]=1).
        x : np.ndarray
            Input signal (float64 recommended).

        Returns
        -------
        np.ndarray
            Filtered output array, same dtype and length as x.
        """
        b0, b1, b2 = b[0], b[1], b[2]
        # a[0] is 1 after normalisation; use a[1], a[2]
        a1, a2 = a[1], a[2]

        y = np.empty_like(x)
        w1 = 0.0  # delay state 1
        w2 = 0.0  # delay state 2

        for i in range(len(x)):
            xn = x[i]
            yn = b0 * xn + w1
            w1 = b1 * xn - a1 * yn + w2
            w2 = b2 * xn - a2 * yn
            y[i] = yn

        return y

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        Apply three-band EQ to an audio buffer.

        Bands whose gain is exactly 0 dB are skipped (pass-through) to avoid
        unnecessary computation.  Processing order: low shelf -> peak -> high
        shelf.

        Parameters
        ----------
        audio : np.ndarray
            Input audio as float32 (mono).

        Returns
        -------
        np.ndarray
            Equalised output as float32.
        """
        audio = np.asarray(audio, dtype=np.float32)
        x = audio.astype(np.float64)

        # Low shelf
        if self._low_gain_db != 0.0:
            x = self._apply_biquad(self._b_low, self._a_low, x)

        # Peaking mid
        if self._mid_gain_db != 0.0:
            x = self._apply_biquad(self._b_mid, self._a_mid, x)

        # High shelf
        if self._high_gain_db != 0.0:
            x = self._apply_biquad(self._b_high, self._a_high, x)

        return x.astype(np.float32)
