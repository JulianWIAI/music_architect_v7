"""
src/rendering/composition_groover.py
──────────────────────────────────────
Applies SongGrooveSettings to a composition dict's event timestamps.

This is the built-in synthesiser equivalent of GrooveProcessor, which
works on MIDI files.  GrooveProcessor cannot be used on the built-in path
because there is no MIDI file — events live as

    (time_beats, duration_beats, pitch, velocity)

tuples in the composition dict.  All transforms are performed in beat-space
instead of MIDI tick-space.

Transforms applied per track (in order, matching GrooveProcessor._apply_track):

  Simple mode
  ───────────
  1. Swing         — off-beat 16th steps (1, 3, 5 … 15) shifted by swing_offset
  2. Timing nudge  — fixed ±ms offset converted to beats
  3. Timing humanise — seeded random ±jitter in beats
  4. Velocity clamp  — rescale [1, 127] → [vel_min, vel_max]
  5. Velocity curve  — per-step accent multiplier from VEL_CURVE_GRIDS
  6. Velocity humanise — seeded random ±velocity jitter
  7. Transpose       — semitone shift on pitch

  Advanced mode (use_advanced=True)
  ──────────────────────────────────
  Steps 1–2 are replaced by t_grid[step] ms offset.
  Step 5 is replaced by v_grid[step] velocity multiplier.
  Steps 3, 4, 6, 7 still apply.

Guarantees
──────────
• The original composition dict is never modified — a deep copy is returned.
• Events are re-sorted by time after swing so playback order stays correct.
• time_beats is clamped to ≥ 0 so notes never land before the start.
"""

from __future__ import annotations

import copy
import random
from typing import List, Tuple

from src.midi.groove_settings import SongGrooveSettings, TrackGrooveSettings
from src.midi.grid_to_preset import VEL_CURVE_GRIDS

# Composition track name → SongGrooveSettings track key
_MIDI_NAME_TO_KEY: dict = {
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

# 4/4 time constants (shared with GrooveProcessor's tick-space equivalents)
_SIXTEENTH = 0.25   # one 16th note = 0.25 beats
_BAR_BEATS = 4.0    # one bar      = 4.0  beats


class CompositionGroover:
    """
    Apply SongGrooveSettings groove transforms to a composition dict.

    Usage::

        from src.rendering.composition_groover import CompositionGroover

        grooved = CompositionGroover.apply(composition, groove_settings)
        samples = synthesizer.render_composition(grooved)
    """

    @staticmethod
    def apply(composition: dict, settings: SongGrooveSettings) -> dict:
        """
        Return a deep copy of *composition* with groove transforms applied.

        Parameters
        ----------
        composition : dict
            Composition dict from CompositionEngine.compose().
        settings    : SongGrooveSettings
            Per-track groove settings from MixerPanel.get_settings().

        Returns
        -------
        dict
            Modified deep copy.  The original is not mutated.
        """
        if not settings.apply_enabled or not settings.has_any_effect():
            return composition

        bpm  = float(composition.get('config', {}).get('bpm', 120.0))
        comp = copy.deepcopy(composition)

        for track_name, events in comp.get('tracks', {}).items():
            groove_key    = _MIDI_NAME_TO_KEY.get(track_name)
            if groove_key is None:
                continue
            track_settings = settings.get(groove_key)
            if track_settings.is_identity():
                continue
            comp['tracks'][track_name] = _apply_track(events, track_settings, bpm)

        return comp


# ── Per-track transform ───────────────────────────────────────────────────────

def _apply_track(
    events:   list,
    s:        TrackGrooveSettings,
    bpm:      float,
) -> list:
    """
    Apply all groove transforms to one track's event list.

    Returns a new list sorted by time_beats.
    """
    # ms → beats conversion: 1 beat = 60/bpm seconds
    ms_to_beats = bpm / (60.0 * 1000.0)

    # Simple-mode precomputed values
    swing_offset_beats = (s.swing_pct / 100.0 - 0.5) * 2.0 * _SIXTEENTH
    nudge_beats        = s.timing_nudge_ms * ms_to_beats
    humanize_range     = s.timing_humanize_ms * ms_to_beats

    # Seeded RNG for reproducible humanisation
    rng = random.Random(s.effective_seed())

    # Velocity curve table (16 per-step multipliers)
    curve    = VEL_CURVE_GRIDS.get(s.vel_curve, VEL_CURVE_GRIDS['flat'])
    vel_span = s.vel_max - s.vel_min

    result: list = []
    for event in events:
        if len(event) < 4:
            result.append(event)
            continue

        t, dur, pitch, vel = float(event[0]), event[1], int(event[2]), int(event[3])

        # 16th-step index within the current bar (0–15)
        beat_in_bar = t % _BAR_BEATS
        step_idx    = int(round(beat_in_bar / _SIXTEENTH)) % 16

        # ── Timing transforms ────────────────────────────────────────────────
        if s.use_advanced and s.t_grid and len(s.t_grid) == 16:
            # Advanced mode: per-step ms grid replaces swing and nudge
            t += s.t_grid[step_idx] * ms_to_beats
        else:
            # Simple mode: swing on odd 16th steps, then global nudge
            if step_idx % 2 == 1:
                t += swing_offset_beats
            t += nudge_beats

        # Timing humanise (applies in both modes)
        if humanize_range > 0.0:
            t += rng.uniform(-humanize_range, humanize_range)

        t = max(0.0, t)

        # ── Velocity transforms ──────────────────────────────────────────────
        # Clamp/rescale to [vel_min, vel_max]
        if vel_span > 0:
            vel = s.vel_min + int((vel - 1) / 126.0 * vel_span)
        vel = max(1, min(127, vel))

        # Per-step velocity multiplier
        if s.use_advanced and s.v_grid and len(s.v_grid) == 16:
            vel = int(vel * s.v_grid[step_idx])
        else:
            vel = int(vel * curve[step_idx])
        vel = max(1, min(127, vel))

        # Velocity humanise
        if s.vel_humanize > 0:
            vel += rng.randint(-s.vel_humanize, s.vel_humanize)
            vel = max(1, min(127, vel))

        # ── Pitch transform ──────────────────────────────────────────────────
        pitch = max(0, min(127, pitch + s.transpose_st))

        result.append((t, dur, pitch, vel))

    # Re-sort by time — swing can shift off-beat notes past nearby on-beat ones
    result.sort(key=lambda e: e[0])
    return result
