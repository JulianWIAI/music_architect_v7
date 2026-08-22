"""
tests/test_genre_archetypes.py
───────────────────────────────
Automated validation suite for all 22 genre archetypes.

Each archetype is exercised through the full new DSP stack:

  [1] Profile fields       — types, value ranges, recognised enum values
  [2] MicroTimingEngine    — 16-step V/T grids: finite, V > 0, |T| ≤ 150 ms
  [3] AperiodicLFOEngine   — 4 × 512-sample blocks: values in [0, 1], no NaN/Inf
  [4] ParameterSmoother    — apply_lfo_block → get_current: finite, in drive range
  [5] SaturationBridge DSP — 4 × 512 white-noise samples: no NaN/Inf,
                             peak < 2.0, RMS > 0

Exit code: 0 all pass  |  1 any failure.

Usage::
    python -m tests.test_genre_archetypes
    python tests/test_genre_archetypes.py
"""

from __future__ import annotations

import math
import sys
from typing import List, Tuple

import numpy as np

from src.midi.genre_profiles import GenreProfileLibrary, GenreProfile
from src.midi.micro_timing_engine import MicroTimingEngine
from src.dsp.lfo_engine import AperiodicLFOEngine
from src.dsp.parameter_smoother import ParameterSmoother
from src.audio.dsp_bridge import SaturationBridge


# ── Constants ─────────────────────────────────────────────────────────────────

BLOCK_SIZE  = 512   # samples per block
NUM_BLOCKS  = 4     # blocks to run per engine
SAMPLE_RATE = 48_000
SEED        = 42

# saturation_type strings recognised by SaturationProcessor (saturation.cpp).
# "tube_hard_blend" and anything else unknown silently falls back to NONE.
_KNOWN_SAT_TYPES: frozenset = frozenset({
    "none", "tape_soft", "tube_tanh", "hard_clip",
    "asymmetric_soft", "vinyl_tape", "waveshaper",
})

# lfo_waveform strings handled by AperiodicLFOEngine.
_KNOWN_WAVEFORMS: frozenset = frozenset({
    "sine", "sample_hold", "random_ramp", "square", "none",
})

# Synthetic test audio: white noise at −12 dBFS (~0.25 amplitude).
# Fixed seed so results are reproducible across runs.
_rng_audio = np.random.default_rng(seed=0)
_NOISE_BLOCK: np.ndarray = _rng_audio.uniform(
    -0.25, 0.25, BLOCK_SIZE
).astype(np.float32)


# ── Buffer health check ───────────────────────────────────────────────────────

def _check_audio(arr: np.ndarray, label: str) -> List[str]:
    """
    Return a list of error strings describing problems in *arr*.

    Checks: NaN, Inf, extreme peak (> 2.0), silence (RMS < 1e-9).
    The peak threshold is 2.0 rather than 1.0 because soft-clipping curves
    such as tape_soft may slightly exceed unity on transients before settling.
    """
    errors: List[str] = []
    if np.any(np.isnan(arr)):
        errors.append(f"{label}: NaN in output")
    if np.any(np.isinf(arr)):
        errors.append(f"{label}: Inf in output")
    peak = float(np.max(np.abs(arr)))
    rms  = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
    if peak > 2.0:
        errors.append(f"{label}: extreme peak {peak:.4f} > 2.0 (hard distortion)")
    if rms < 1e-9:
        errors.append(f"{label}: silent output RMS={rms:.2e}")
    return errors


# ── Per-archetype test ────────────────────────────────────────────────────────

def _test_archetype(profile: GenreProfile) -> Tuple[bool, List[str]]:
    """
    Run all 5 check groups for one archetype.

    Returns
    -------
    (passed, messages)
        passed   – True only when there are zero hard errors.
        messages – list of error strings and "[WARN]" prefixed advisories.
    """
    errors:   List[str] = []
    warnings: List[str] = []

    # ── [1] Profile field validation ──────────────────────────────────────────
    # BPM ordering
    if not (0 < profile.bpm_min <= profile.bpm_default <= profile.bpm_max):
        errors.append(
            f"BPM range invalid: min={profile.bpm_min} "
            f"default={profile.bpm_default} max={profile.bpm_max}"
        )

    # Drive range
    if not (0.0 <= profile.drive_pct_min <= profile.drive_pct_max <= 100.0):
        errors.append(
            f"drive range invalid: [{profile.drive_pct_min}, {profile.drive_pct_max}]"
        )

    # Reverb decay ordering
    if profile.reverb_decay_s_min > profile.reverb_decay_s_max:
        errors.append(
            f"reverb decay inverted: min={profile.reverb_decay_s_min} "
            f"> max={profile.reverb_decay_s_max}"
        )

    # LFO rate ordering (allow both zero = disabled)
    if (profile.lfo_rate_bars_min > 0 or profile.lfo_rate_bars_max > 0) and \
       profile.lfo_rate_bars_min > profile.lfo_rate_bars_max:
        errors.append(
            f"LFO rate inverted: min={profile.lfo_rate_bars_min} "
            f"> max={profile.lfo_rate_bars_max}"
        )

    # Enum checks — produce warnings so the test keeps running even if a
    # string was accidentally misspelled in the profile table.
    if profile.saturation_type not in _KNOWN_SAT_TYPES:
        warnings.append(
            f"saturation_type '{profile.saturation_type}' not in C++ enum "
            f"-> will be treated as NONE (unity gain)"
        )
    if profile.lfo_waveform not in _KNOWN_WAVEFORMS:
        warnings.append(
            f"lfo_waveform '{profile.lfo_waveform}' not recognised "
            f"-> AperiodicLFO will use linear-ramp fallback"
        )

    # ── [2] MicroTimingEngine ─────────────────────────────────────────────────
    try:
        mte      = MicroTimingEngine(profile, seed=SEED)
        v_grid, t_grid = mte.get_bar_params()

        if len(v_grid) != 16 or len(t_grid) != 16:
            errors.append(
                f"MicroTimingEngine: expected 16 steps, "
                f"got V={len(v_grid)} T={len(t_grid)}"
            )
        else:
            if any(math.isnan(v) or math.isinf(v) for v in v_grid):
                errors.append("MicroTimingEngine: NaN/Inf in V-grid")
            elif any(v <= 0 for v in v_grid):
                errors.append(
                    f"MicroTimingEngine: non-positive V value "
                    f"(min={min(v_grid):.4f})"
                )

            if any(math.isnan(t) or math.isinf(t) for t in t_grid):
                errors.append("MicroTimingEngine: NaN/Inf in T-grid")
            elif any(abs(t) > 150.0 for t in t_grid):
                worst = max(abs(t) for t in t_grid)
                errors.append(
                    f"MicroTimingEngine: T-grid offset {worst:.1f} ms exceeds ±150 ms"
                )

    except Exception as exc:
        errors.append(f"MicroTimingEngine raised {type(exc).__name__}: {exc}")

    # ── [3] AperiodicLFOEngine ────────────────────────────────────────────────
    lfo_out: dict = {}
    try:
        lfo = AperiodicLFOEngine(
            profile     = profile,
            bpm         = float(profile.bpm_default),
            sample_rate = SAMPLE_RATE,
            seed        = SEED,
        )
        for _ in range(NUM_BLOCKS):
            lfo_out = lfo.next_block(BLOCK_SIZE)

        # Validate the last block's values (empty dict is fine when no targets).
        for target, values in lfo_out.items():
            if not values:
                errors.append(f"AperiodicLFO[{target}]: empty block returned")
                continue
            if any(math.isnan(v) or math.isinf(v) for v in values):
                errors.append(f"AperiodicLFO[{target}]: NaN/Inf in output")
            elif any(v < -0.001 or v > 1.001 for v in values):
                out_of_range = [v for v in values if v < -0.001 or v > 1.001]
                errors.append(
                    f"AperiodicLFO[{target}]: {len(out_of_range)} sample(s) "
                    f"outside [0,1] — first={out_of_range[0]:.4f}"
                )

    except Exception as exc:
        errors.append(f"AperiodicLFOEngine raised {type(exc).__name__}: {exc}")

    # ── [4] ParameterSmoother ─────────────────────────────────────────────────
    try:
        smoother = ParameterSmoother(smoothing_ms=5.0, sample_rate=SAMPLE_RATE)
        init_drive = (profile.drive_pct_min + profile.drive_pct_max) / 2.0
        smoother.register("drive", initial_value=init_drive)
        smoother.set_range("drive", profile.drive_pct_min, profile.drive_pct_max)

        if lfo_out:
            smoother.apply_lfo_block(lfo_out)
        else:
            # No LFO targets — manually push a target change to exercise the ramp.
            smoother.set_target("drive", profile.drive_pct_max)

        val = smoother.get_current("drive")
        if math.isnan(val) or math.isinf(val):
            errors.append(f"ParameterSmoother: non-finite drive value {val}")
        elif not (profile.drive_pct_min - 0.1 <= val <= profile.drive_pct_max + 0.1):
            errors.append(
                f"ParameterSmoother: drive {val:.3f} outside "
                f"[{profile.drive_pct_min}, {profile.drive_pct_max}]"
            )

    except Exception as exc:
        errors.append(f"ParameterSmoother raised {type(exc).__name__}: {exc}")

    # ── [5] SaturationBridge DSP ──────────────────────────────────────────────
    try:
        init_drive = (profile.drive_pct_min + profile.drive_pct_max) / 2.0
        bridge = SaturationBridge(
            saturation_type   = profile.saturation_type,
            drive_pct_initial = init_drive,
            sample_rate       = SAMPLE_RATE,
            smoothing_ms      = 5.0,
        )
        out = _NOISE_BLOCK.copy()
        for _ in range(NUM_BLOCKS):
            out = bridge.process(_NOISE_BLOCK)
        errors.extend(_check_audio(out, "SaturationBridge"))

    except Exception as exc:
        errors.append(f"SaturationBridge raised {type(exc).__name__}: {exc}")

    passed   = len(errors) == 0
    messages = errors + [f"[WARN] {w}" for w in warnings]
    return passed, messages


# ── Runner ────────────────────────────────────────────────────────────────────

def run_suite() -> bool:
    """
    Run the full suite and print a report.

    Returns True when all archetypes pass.
    """
    lib       = GenreProfileLibrary()
    profiles  = lib._profiles          # full flat list, all 22 archetypes
    n_total   = len(profiles)
    n_pass    = 0
    n_fail    = 0
    failures: List[str] = []

    width = 55
    print()
    print("  Genre Archetype DSP Test Suite")
    print(f"  {'-' * width}")
    print(f"  {'Archetype':<38} {'V/T':>4}  {'LFO':>4}  {'DSP':>4}  Status")
    print(f"  {'-' * width}")

    for profile in profiles:
        tag = f"{profile.genre}/{profile.archetype_id}"
        passed, messages = _test_archetype(profile)

        # Collect sub-check indicators for the table column.
        # Each sub-check is shown as ✓ or ✗ based on whether its key phrase
        # appears in the error list — keeps the table columns meaningful.
        def _col(keywords: List[str]) -> str:
            hit = any(
                any(kw in m for kw in keywords)
                for m in messages
                if not m.startswith("[WARN]")
            )
            return " X " if hit else " ok"

        col_grid = _col(["MicroTimingEngine"])
        col_lfo  = _col(["AperiodicLFO", "AperiodicLFO"])
        col_dsp  = _col(["SaturationBridge", "ParameterSmoother"])
        status   = "PASS" if passed else "FAIL"

        print(
            f"  {tag:<38} {col_grid:>4} {col_lfo:>4} {col_dsp:>4}  {status}"
        )

        # Print errors and warnings indented under the archetype row.
        for msg in messages:
            prefix = "    [WARN]  " if msg.startswith("[WARN]") else "    [ERROR] "
            print(f"{prefix}{msg.lstrip('[WARN] ').lstrip('[ERROR] ')}")

        if passed:
            n_pass += 1
        else:
            n_fail += 1
            failures.append(tag)

    print(f"  {'-' * width}")
    print()

    # Summary
    if n_fail == 0:
        print(f"  RESULT: {n_pass}/{n_total} passed   -- all archetypes clean")
    else:
        print(f"  RESULT: {n_pass}/{n_total} passed   {n_fail} FAILED:")
        for tag in failures:
            print(f"    • {tag}")

    print()
    return n_fail == 0


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ok = run_suite()
    sys.exit(0 if ok else 1)
