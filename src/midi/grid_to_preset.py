"""
src/midi/grid_to_preset.py
───────────────────────────
Convert a raw 16-step grid back to the nearest simplified Tier-1 preset
values, and report whether the conversion is lossless.

Called by AdvancedGrooveView when the user switches from Advanced → Simplified
mode.  A warning is shown if the V or T grid cannot be expressed exactly as a
named vel_curve + uniform swing/nudge.

This module is also the single authoritative source for the velocity-curve
multiplier table so that groove_processor.py and advanced_groove_view.py both
reference the same data without duplication.

Public API::

    # Shared multiplier table used by groove_processor._apply_track
    from src.midi.grid_to_preset import VEL_CURVE_GRIDS

    # Lossless conversion
    curve, nudge, swing_extra_ms, lossless, warning = grids_to_simple(v, t)
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# ── Velocity-curve multiplier table ───────────────────────────────────────────
# 16 float multipliers, one per 16th-note step in a 4/4 bar.
# The multiplier is applied to the post-clamp velocity (step 6 in GrooveProcessor).
# THIS IS THE SINGLE SOURCE OF TRUTH — groove_processor.py imports this dict.
VEL_CURVE_GRIDS: Dict[str, List[float]] = {
    # All steps equal — no accent applied.
    'flat':        [1.00] * 16,

    # Beat 1 (step 0) boosted by +12 %; all other steps neutral.
    'accent_1':    [1.12, 1.0, 1.0, 1.0,  1.0, 1.0, 1.0, 1.0,
                    1.0,  1.0, 1.0, 1.0,  1.0, 1.0, 1.0, 1.0],

    # Beats 1 and 3 (steps 0, 8) boosted by +10 %; all other steps neutral.
    'accent_1_3':  [1.10, 1.0, 1.0, 1.0,  1.0, 1.0, 1.0, 1.0,
                    1.10, 1.0, 1.0, 1.0,  1.0, 1.0, 1.0, 1.0],

    # Linear ramp from 80 % at step 0 to 100 % at step 15.
    'crescendo':   [0.80 + 0.20 * i / 15 for i in range(16)],

    # Linear ramp from 100 % at step 0 down to 80 % at step 15.
    'decrescendo': [1.00 - 0.20 * i / 15 for i in range(16)],
}

# Float comparison tolerance used throughout this module.
_TOL: float = 0.02


# ── Velocity curve matching ───────────────────────────────────────────────────

def vel_curve_from_grid(v: List[float]) -> Tuple[str, bool]:
    """
    Find the named velocity curve whose reference grid most closely matches *v*.

    Parameters
    ----------
    v : 16-element list of float multipliers (0.0–2.0).

    Returns
    -------
    (curve_name, is_exact)
        curve_name — best-matching named curve (always returned even if not exact).
        is_exact   — True only when every step matches within _TOL.
    """
    if len(v) != 16:
        return ('flat', False)

    best_name  = 'flat'
    best_error = float('inf')

    for name, ref in VEL_CURVE_GRIDS.items():
        total_err = sum(abs(a - b) for a, b in zip(v, ref))
        if total_err < best_error:
            best_error = total_err
            best_name  = name

    ref_grid = VEL_CURVE_GRIDS[best_name]
    is_exact = all(abs(a - b) < _TOL for a, b in zip(v, ref_grid))
    return (best_name, is_exact)


# ── Timing grid analysis ──────────────────────────────────────────────────────

def swing_nudge_from_t_grid(t: List[float]) -> Tuple[float, float, bool]:
    """
    Derive (nudge_ms, swing_extra_ms, is_exact) from a 16-step T grid.

    The simplified timing model assumes:
      - Even steps (0, 2, 4 … 14) all share the same offset: ``nudge_ms``.
      - Odd steps (1, 3, 5 … 15) all share: ``nudge_ms + swing_extra_ms``.

    Parameters
    ----------
    t : 16-element list of per-step timing offsets in milliseconds.

    Returns
    -------
    (nudge_ms, swing_extra_ms, is_exact)
        nudge_ms       — mean offset on even steps, clamped to ±50 ms.
        swing_extra_ms — additional delay on odd steps (not converted to %).
                         Caller converts to swing_pct if BPM is known.
        is_exact       — True when every step is within _TOL ms of the
                         even/odd pattern described above.
    """
    if len(t) != 16:
        return (0.0, 0.0, False)

    even_vals = [t[i] for i in range(0, 16, 2)]
    odd_vals  = [t[i] for i in range(1, 16, 2)]

    nudge_ms       = sum(even_vals) / len(even_vals)
    mean_odd_ms    = sum(odd_vals)  / len(odd_vals)
    swing_extra_ms = mean_odd_ms - nudge_ms

    even_ok = all(abs(v - nudge_ms) < _TOL for v in even_vals)
    odd_ok  = all(abs(v - mean_odd_ms) < _TOL for v in odd_vals)
    is_exact = even_ok and odd_ok

    nudge_ms = max(-50.0, min(50.0, nudge_ms))
    return (nudge_ms, swing_extra_ms, is_exact)


# ── Combined conversion ───────────────────────────────────────────────────────

def grids_to_simple(
    v: List[float],
    t: List[float],
) -> Tuple[str, float, float, bool, str]:
    """
    Convert V and T grids to the nearest simplified Tier-1 preset values.

    Parameters
    ----------
    v : 16-step velocity multiplier grid.
    t : 16-step timing offset grid (ms).

    Returns
    -------
    (vel_curve, nudge_ms, swing_extra_ms, is_lossless, warning_msg)
        vel_curve      — nearest named velocity curve.
        nudge_ms       — timing nudge to apply to all notes.
        swing_extra_ms — additional ms on odd steps (convert to swing_pct
                         outside this module once BPM is available).
        is_lossless    — True when both V and T grids match their simplified
                         equivalents within _TOL.
        warning_msg    — human-readable description of lost precision;
                         empty string when is_lossless is True.
    """
    curve, curve_exact = vel_curve_from_grid(v)
    nudge, swing_extra, timing_exact = swing_nudge_from_t_grid(t)

    is_lossless = curve_exact and timing_exact

    parts: List[str] = []
    if not curve_exact:
        parts.append(
            f"Velocity grid → nearest preset is '{curve}', but "
            "some steps differ beyond the rounding tolerance."
        )
    if not timing_exact:
        parts.append(
            "Timing grid has irregular per-step offsets that cannot be "
            "expressed as uniform swing + nudge."
        )

    warning = '\n'.join(parts)
    return (curve, nudge, swing_extra, is_lossless, warning)
