"""
src/midi/micro_timing_engine.py
────────────────────────────────
Position-dependent velocity and timing offset generator.

``MicroTimingEngine`` reads a ``GenreProfile`` and, for each of the 16 steps
in a bar, returns:

* A **velocity multiplier** drawn from a named curve (e.g. ``"mpc_dilla_groove"``).
* A **timing offset in milliseconds** that combines swing (even/odd 16th-note
  displacement) with random humanisation jitter bounded by the profile's
  ``jitter_ms_max``.

The two 16-element lists produced by ``get_bar_params()`` plug directly into
the ``v_grid`` / ``t_grid`` fields of ``TrackGrooveSettings`` and therefore
into the existing ``GrooveProcessor`` pipeline without any change to that code.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.midi.genre_profiles import GenreProfile


# ---------------------------------------------------------------------------
# Velocity curve definitions
# Each curve is a 16-element list of multipliers (float).
# Index 0 = first 16th note of the bar; index 15 = last.
# ---------------------------------------------------------------------------

def _flat() -> List[float]:
    """All steps identical — no accent pattern."""
    return [1.0] * 16


def _downbeat_backbeat_accent() -> List[float]:
    """
    Standard rock/pop accent: strong on 1 (step 0) and 3 (step 8),
    backbeat accent on 2 (step 4) and 4 (step 12), everything else slightly
    reduced.
    """
    base = [0.95] * 16
    for s in (0, 8):
        base[s] = 1.15   # downbeats
    for s in (4, 12):
        base[s] = 1.08   # backbeats
    return base


def _compressed_high_energy() -> List[float]:
    """Narrow dynamic range — heavy bus compression feel."""
    base = [1.02] * 16
    for s in (0, 4, 8, 12):
        base[s] = 1.10
    return base


def _mpc_dilla_groove() -> List[float]:
    """
    MPC / J Dilla groove: irregular, humanised feel with ghost notes.
    Kick and snare accented; many off-beat 16ths pushed down.
    """
    curve = [
        1.15,  # 0  kick (beat 1)
        0.78,  # 1  ghost 16th
        0.85,  # 2  upbeat
        0.60,  # 3  weak 16th
        1.05,  # 4  snare (beat 2)
        0.78,  # 5  ghost
        0.70,  # 6  upbeat
        0.55,  # 7  very weak
        1.15,  # 8  kick (beat 3)
        0.78,  # 9  ghost
        0.85,  # 10 upbeat
        0.60,  # 11 weak
        1.05,  # 12 snare (beat 4)
        0.78,  # 13 ghost
        0.70,  # 14 upbeat
        0.55,  # 15 very weak
    ]
    return curve


def _dilla_loose() -> List[float]:
    """
    Lo-fi Dilla variant: more extreme low-end steps, extreme variation.
    """
    curve = [
        1.15,  # 0  kick
        0.70,  # 1
        0.82,  # 2
        0.45,  # 3  very low ghost
        1.05,  # 4  snare
        0.65,  # 5
        0.75,  # 6
        0.45,  # 7  very low ghost
        1.12,  # 8  kick
        0.68,  # 9
        0.80,  # 10
        0.50,  # 11
        1.02,  # 12 snare
        0.65,  # 13
        0.72,  # 14
        0.45,  # 15
    ]
    return curve


def _trap_hat_stagger() -> List[float]:
    """
    Trap hat stagger: hard kick/snare accents, irregular hat velocities.
    Hats alternate between very quiet (0.40) and semi-loud (0.90) in the
    characteristic trap roll feel.
    """
    curve = [
        1.20,  # 0  kick
        0.65,  # 1  hat
        0.40,  # 2  hat quiet
        0.90,  # 3  hat accent
        1.15,  # 4  snare
        0.55,  # 5  hat
        0.75,  # 6  hat
        0.40,  # 7  hat quiet
        1.20,  # 8  kick
        0.90,  # 9  hat accent
        0.40,  # 10 hat quiet
        0.75,  # 11 hat
        1.15,  # 12 snare
        0.55,  # 13 hat
        1.00,  # 14 hat louder
        0.40,  # 15 hat quiet
    ]
    return curve


def _aggressive_flat() -> List[float]:
    """
    Aggressive flat: all steps pushed close to maximum, tiny variation
    mimicking heavy compression / limiting on a fast/dark track.
    """
    # Slight alternating variation so it doesn't sound literally mechanical.
    return [1.08 if i % 2 == 0 else 1.05 for i in range(16)]


def _orchestral_swell() -> List[float]:
    """
    Smooth crescendo from 0.75 at step 0 to 1.25 at step 15.
    Mimics a within-bar orchestral swell.
    """
    return [0.75 + (0.50 * i / 15.0) for i in range(16)]


def _downbeat_accent_aggressive() -> List[float]:
    """Strong downbeat accent, secondary beat accents, reduced off-beats."""
    base = [0.90] * 16
    base[0] = 1.25   # beat 1 — strongest
    for s in (4, 8, 12):
        base[s] = 1.10
    return base


def _compressed_kick_accent() -> List[float]:
    """Four-on-the-floor accent; kick on every beat, everything else flat."""
    base = [0.95] * 16
    for s in (0, 4, 8, 12):
        base[s] = 1.20
    return base


def _wall_of_sound() -> List[float]:
    """Maximum sustained compression — every step at 1.10."""
    return [1.10] * 16


def _j_pop_bright() -> List[float]:
    """
    J-pop bright accent: downbeats and backbeats bright, off-beats at 1.05
    giving a light, bouncy feel.
    """
    base = [1.05] * 16
    for s in (0, 8):
        base[s] = 1.18
    for s in (4, 12):
        base[s] = 1.12
    return base


def _rock_accent() -> List[float]:
    """
    Rock: hard kick and snare accents; 16th-note subdivisions significantly
    reduced to let the main beats cut through.
    """
    base = [0.75] * 16
    for s in (0, 8):
        base[s] = 1.20
    for s in (4, 12):
        base[s] = 1.18
    return base


def _forte_accent_downbeats() -> List[float]:
    """Classical forte: strong quarter-note downbeats, reduced off-beats."""
    base = [0.85] * 16
    for s in (0, 4, 8, 12):
        base[s] = 1.20
    return base


def _house_groove() -> List[float]:
    """
    House four-on-the-floor groove: kick on every beat strongly accented,
    upbeats (off-16th of beat) moderate, remaining 16ths quiet.
    """
    base = [0.70] * 16
    for s in (0, 4, 8, 12):
        base[s] = 1.15   # kick
    for s in (2, 6, 10, 14):
        base[s] = 0.90   # upbeat clap/snare region
    return base


def _driving_flat_kick() -> List[float]:
    """Tech-house: driving flat kick, everything else slightly suppressed."""
    base = [0.92] * 16
    for s in (0, 4, 8, 12):
        base[s] = 1.18
    return base


def _swell_dynamic() -> List[float]:
    """
    Ballad phrase swell: rises from 0.70 to 1.10 across the first half bar,
    holds then gently falls back across the second half.
    """
    first_half  = [0.70 + 0.40 * (i / 7.0) for i in range(8)]  # 0.70 → 1.10
    second_half = [1.10 - 0.20 * (i / 7.0) for i in range(8)]  # 1.10 → 0.90
    return first_half + second_half


def _halftime_kick_snare() -> List[float]:
    """Dubstep / half-time: massive step 0 (kick) and step 8 (snare), rest quiet."""
    base = [0.85] * 16
    base[0] = 1.25
    base[8] = 1.20
    return base


def _compressed_wall() -> List[float]:
    """EDM wall of sound: everything at 1.08."""
    return [1.08] * 16


# Map curve name → generator function (called once per profile instantiation).
_CURVE_REGISTRY: Dict[str, object] = {
    "flat":                       _flat,
    "downbeat_backbeat_accent":   _downbeat_backbeat_accent,
    "compressed_high_energy":     _compressed_high_energy,
    "mpc_dilla_groove":           _mpc_dilla_groove,
    "dilla_loose":                _dilla_loose,
    "trap_hat_stagger":           _trap_hat_stagger,
    "aggressive_flat":            _aggressive_flat,
    "orchestral_swell":           _orchestral_swell,
    "downbeat_accent_aggressive": _downbeat_accent_aggressive,
    "compressed_kick_accent":     _compressed_kick_accent,
    "wall_of_sound":              _wall_of_sound,
    "j_pop_bright":               _j_pop_bright,
    "rock_accent":                _rock_accent,
    "forte_accent_downbeats":     _forte_accent_downbeats,
    "house_groove":               _house_groove,
    "driving_flat_kick":          _driving_flat_kick,
    "swell_dynamic":              _swell_dynamic,
    "halftime_kick_snare":        _halftime_kick_snare,
    "compressed_wall":            _compressed_wall,
}


class MicroTimingEngine:
    """
    Per-step velocity multiplier and timing offset generator.

    Takes a ``GenreProfile`` and derives a 16-step velocity curve plus
    position-dependent timing offsets that include:

    * **Swing** — odd-indexed 16th notes (1, 3, 5, …) are delayed by a
      fraction that maps ``swing_pct_max`` to real milliseconds.
    * **Jitter** — each step gets a small random perturbation bounded by
      ``profile.jitter_ms_max``.

    The RNG is seeded once at construction; the same seed produces the same
    jitter pattern across renders (reproducibility).
    """

    def __init__(self, profile: "GenreProfile", seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)
        self._profile = profile
        # Build the base velocity curve from the profile's named curve.
        self._base_vel_curve: List[float] = self._resolve_curve(profile)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_step_params(
        self, step_index: int, section: str = "verse"
    ) -> Tuple[float, float]:
        """
        Return ``(velocity_multiplier, timing_offset_ms)`` for a single step.

        Parameters
        ----------
        step_index : int
            Step within the bar, 0-based (0–15).
        section : str
            Section name (reserved for future section-dependent variation;
            currently not used to alter the curve but present for API stability).

        Returns
        -------
        (float, float)
            velocity_multiplier — scale factor to apply to raw MIDI velocity.
            timing_offset_ms   — milliseconds to add/subtract from the step's
                                 nominal grid position.
        """
        step_index = max(0, min(15, step_index))
        vel_mult = self._base_vel_curve[step_index]

        # Swing: odd steps (1, 3, 5, …) are pushed late.
        timing = self._swing_offset_ms(step_index)

        # Jitter: small random deviation bounded by jitter_ms_max.
        jitter_range = self._profile.jitter_ms_max
        if jitter_range > 0.0:
            timing += self._rng.uniform(-jitter_range, jitter_range)

        return vel_mult, timing

    def get_bar_params(
        self, section: str = "verse"
    ) -> Tuple[List[float], List[float]]:
        """
        Return two 16-element lists: ``(velocity_multipliers, timing_offsets_ms)``.

        These map directly to the ``v_grid`` / ``t_grid`` fields of
        ``TrackGrooveSettings`` consumed by ``GrooveProcessor``.
        """
        vel_list: List[float] = []
        time_list: List[float] = []
        for step in range(16):
            v, t = self.get_step_params(step, section=section)
            vel_list.append(v)
            time_list.append(t)
        return vel_list, time_list

    def update_profile(self, profile: "GenreProfile") -> None:
        """
        Replace the active profile without re-seeding the RNG.

        Useful when the song transitions to a new section with a different feel.
        The RNG state is preserved so subsequent jitter values are continuous.
        """
        self._profile = profile
        self._base_vel_curve = self._resolve_curve(profile)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_curve(self, profile: "GenreProfile") -> List[float]:
        """
        Build the 16-element velocity-multiplier list for the profile's curve name.

        Falls back to the flat curve for unrecognised names.
        """
        factory = _CURVE_REGISTRY.get(profile.velocity_curve, _flat)
        return factory()  # type: ignore[operator]

    def _swing_offset_ms(self, step_index: int) -> float:
        """
        Compute the timing offset in milliseconds due to swing for *step_index*.

        Only odd-numbered steps are displaced (the "e" and "ah" of each beat).
        The displacement is:

            16th_ms = (60_000 / bpm) / 4
            extra   = 16th_ms × 2 × (swing_pct_max/100 − 0.5)

        At 50 % swing there is zero extra displacement (straight 16ths).
        At 66.67 % the off-beat lands exactly on the triplet subdivision.

        BPM is approximated from the profile's bpm_default so the engine
        works without a live BPM argument (callers that know the BPM can
        create a fresh engine or call update_profile; the offset will be
        close enough for feel-based generation).
        """
        if step_index % 2 == 0:
            # Even steps sit exactly on the 16th-note grid.
            return 0.0

        bpm = float(self._profile.bpm_default)
        sixteenth_ms = (60_000.0 / bpm) / 4.0
        swing_fraction = self._profile.swing_pct_max / 100.0 - 0.5
        return sixteenth_ms * 2.0 * swing_fraction
