"""
src/dsp/parameter_smoother.py
──────────────────────────────
Per-block parameter smoother for zipper-noise-free DSP control.

When a parameter (filter cutoff, reverb size, drive level, …) changes
instantaneously between audio blocks it produces an audible "zipper" artifact
because the DSP sees a step discontinuity.  ``ParameterSmoother`` resolves
this by maintaining a *current* value that chases a *target* value using a
linear ramp over ``smoothing_ms`` milliseconds.

Callers set a new target via ``set_target()`` and retrieve a per-sample ramp
for the next block via ``get_block()``.  After ``smoothing_ms`` worth of
samples the current value equals the target and subsequent ``get_block()``
calls return a flat buffer.

Integration with ``AperiodicLFOEngine``:
    ``apply_lfo_block()`` accepts the dict returned by
    ``AperiodicLFOEngine.next_block()`` and feeds each target through the
    smoother, converting normalised LFO values to real parameter values using
    the registered min/max range.  This lets the LFO engine operate in a
    clean normalised domain while the smoother handles both scaling and
    zipper-noise prevention.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


class ParameterSmoother:
    """
    Maintains current/target values for named parameters and produces
    linearly interpolated per-block ramps.

    Parameters
    ----------
    smoothing_ms : float
        Time over which a parameter change is fully applied.  Default 5 ms is
        fast enough to avoid zipper noise while being imperceptible as lag.
    sample_rate : int
        Audio sample rate in Hz (default 48 000).
    """

    def __init__(
        self, smoothing_ms: float = 5.0, sample_rate: int = 48_000
    ) -> None:
        self._smoothing_ms = smoothing_ms
        self._sample_rate = sample_rate

        # Number of samples required to complete one parameter transition.
        self._smooth_samples: int = max(
            1, int(smoothing_ms * sample_rate / 1000.0)
        )

        # Per-parameter state.
        self._current:  Dict[str, float] = {}
        self._target:   Dict[str, float] = {}
        # How many samples remain in the current ramp (0 = at target).
        self._ramp_left: Dict[str, int] = {}
        # Per-parameter optional [min, max] range for LFO scaling.
        self._ranges: Dict[str, Tuple[float, float]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, initial_value: float = 0.0) -> None:
        """
        Register a new named parameter.

        If *name* is already registered the call is ignored so callers may
        safely re-register without resetting the current state.
        """
        if name in self._current:
            return
        self._current[name]   = initial_value
        self._target[name]    = initial_value
        self._ramp_left[name] = 0

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def set_target(self, name: str, target: float) -> None:
        """
        Set a new target value for *name*.

        The smoother begins ramping from the current value toward *target*
        over the next ``smoothing_ms`` worth of samples.  The ramp duration
        resets every time ``set_target`` is called, which correctly handles
        rapid successive changes (the ramp always starts from the *current*
        instantaneous value).
        """
        if name not in self._current:
            self.register(name, target)
            return
        self._target[name]    = target
        self._ramp_left[name] = self._smooth_samples

    # ------------------------------------------------------------------
    # Block retrieval
    # ------------------------------------------------------------------

    def get_block(self, name: str, block_size: int) -> List[float]:
        """
        Return a ``block_size``-length list of per-sample interpolated values.

        Samples monotonically approach the target.  Once the ramp completes the
        buffer is filled with the (constant) target value.
        """
        if name not in self._current:
            return [0.0] * block_size

        output: List[float] = []
        current = self._current[name]
        target  = self._target[name]
        left    = self._ramp_left[name]

        for _ in range(block_size):
            if left <= 0:
                # Ramp complete — output flat at target.
                output.append(target)
            else:
                # Linear step toward target.
                step = (target - current) / left
                current += step
                left    -= 1
                output.append(current)

        # Persist updated state.
        self._current[name]   = current
        self._ramp_left[name] = left

        return output

    def get_current(self, name: str) -> float:
        """
        Return the current (instantaneous, not target) value of *name*.

        Returns 0.0 if the parameter has not been registered.
        """
        return self._current.get(name, 0.0)

    # ------------------------------------------------------------------
    # LFO integration
    # ------------------------------------------------------------------

    def apply_lfo_block(self, lfo_block: Dict[str, List[float]]) -> None:
        """
        Feed ``AperiodicLFOEngine.next_block()`` output into the smoother.

        For each target in *lfo_block*:
        1. Reads the last sample in the block as the new target value.
        2. Scales it from [0.0, 1.0] to the registered min/max range
           (or leaves it unscaled if no range is registered).
        3. Calls ``set_target()`` so the smoother ramps smoothly to that value.

        Only the final sample of each block is used as the target because the
        LFO engine already provides smooth block-level interpolation — feeding
        every sample would cause the smoother to continuously restart its ramp,
        which would effectively just pass the LFO through unchanged.
        """
        for target_name, samples in lfo_block.items():
            if not samples:
                continue
            normalised = samples[-1]   # last sample of the LFO block
            # Scale to registered range if available.
            if target_name in self._ranges:
                lo, hi = self._ranges[target_name]
                scaled = lo + normalised * (hi - lo)
            else:
                scaled = normalised
            # Auto-register on first LFO contact.
            self.register(target_name, scaled)
            self.set_target(target_name, scaled)

    def set_range(
        self, name: str, min_val: float, max_val: float
    ) -> None:
        """
        Register the physical min/max range for *name*.

        This is used by ``apply_lfo_block()`` to scale normalised LFO values
        ``[0.0, 1.0]`` into the parameter's real range.
        """
        self._ranges[name] = (min_val, max_val)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def all_parameters(self) -> Dict[str, float]:
        """
        Return a snapshot ``{name: current_value}`` of all parameters.

        This is what the C++ bridge (or any consumer) reads at the start
        of each audio block to update DSP state.
        """
        return dict(self._current)
