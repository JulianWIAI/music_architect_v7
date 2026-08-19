"""
src/arrangement/fill_generator.py
───────────────────────────────────
Fill and transition event descriptor generator.

``FillGenerator`` produces lists of **event dicts** that describe musical
fill events at bar/beat resolution.  These descriptors are *data*, not audio:
they are consumed by the groove processor, MIDI generator, or DSP layer to
schedule actual note-on/CC/parameter-ramp actions.

Each event dict has the shape::

    {
        "bar_offset":      int,    # 0-based bar within the fill window
        "beat_offset":     float,  # 0.0 – 3.9 beat position within the bar
        "event_type":      str,    # "note" | "cc" | "velocity_curve" | "parameter_ramp"
        "target":          str,    # e.g. "snare", "hat", "filter_cutoff"
        "value":           float,  # MIDI note / CC value / multiplier / target param value
        "duration_beats":  float,  # event duration in beats
        "intensity":       float,  # 0.0 – 1.0 relative intensity
    }

The caller decides how to map these descriptors to actual MIDI or DSP output.
"""

from __future__ import annotations

import random
import warnings
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.midi.genre_profiles import GenreProfile


# Standard MIDI percussion note numbers (General MIDI channel 10 convention).
_SNARE_NOTE:  int = 38
_HAT_CLOSED:  int = 42
_HAT_OPEN:    int = 46
_KICK_NOTE:   int = 36
_CRASH_NOTE:  int = 49
_TOM_HIGH:    int = 50

# CC numbers for common modulation targets.
_CC_FILTER_CUTOFF:  int = 74
_CC_REVERB_SEND:    int = 91
_CC_EXPRESSION:     int = 11
_CC_RISER_PITCH:    int = 73
_CC_PORTAMENTO:     int = 65   # portamento on/off
_CC_PORTAMENTO_TIME: int = 5


class FillGenerator:
    """
    Generates fill event descriptor dicts for a given fill type and position.

    A single ``FillGenerator`` instance is reusable across sections.
    The optional ``seed`` parameter controls the random variation applied to
    otherwise deterministic fill patterns (ghost-note velocities, slight
    timing variance descriptors, etc.).
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        fill_type: str,
        section_bars: int,
        position_bar: int,
        profile: "GenreProfile",
    ) -> List[dict]:
        """
        Generate fill events for *fill_type* starting at *position_bar*.

        Parameters
        ----------
        fill_type : str
            One of the recognised fill type strings (see module docstring).
        section_bars : int
            Total length of the section in bars (used to compute fill window
            duration for multi-bar fills).
        position_bar : int
            0-based bar index within the section at which the fill begins.
        profile : GenreProfile
            Active genre profile (used to scale intensity values).

        Returns
        -------
        List[dict]
            Ordered list of event descriptor dicts.  May be empty for
            unrecognised fill types.
        """
        # Compute how many bars are available for the fill (from position_bar
        # to the end of the section).
        fill_bars = max(1, section_bars - position_bar)

        # Normalised intensity derived from profile velocity range.
        vel_range = profile.velocity_max - profile.velocity_min
        base_intensity = (vel_range / 127.0) * 0.75 + 0.25  # 0.25–1.0

        # Dispatch to the appropriate builder.
        dispatch: Dict[str, object] = {
            "drum_fill_2bar":     self._drum_fill_2bar,
            "drum_fill_1bar":     self._drum_fill_1bar,
            "snare_roll":         self._snare_roll,
            "hat_triplet_roll":   self._hat_triplet_roll,
            "hat_variation":      self._hat_variation,
            "filter_sweep":       self._filter_sweep,
            "pitch_riser":        self._pitch_riser,
            "tacet_1beat":        self._tacet_1beat,
            "orchestral_riser":   self._orchestral_riser,
            "808_slide":          self._808_slide,
            "sub_bass_drop":      self._sub_bass_drop,
            "stutter":            self._stutter,
            "abrupt_silence":     self._abrupt_silence,
            "noise_burst":        self._noise_burst,
            "vinyl_skip":         self._vinyl_skip,
            "chord_chop_entry":   self._chord_chop_entry,
        }

        builder = dispatch.get(fill_type)
        if builder is None:
            warnings.warn(
                f"FillGenerator: unrecognised fill_type '{fill_type}'. "
                "Returning empty event list.",
                stacklevel=2,
            )
            return []

        return builder(fill_bars=fill_bars, intensity=base_intensity)  # type: ignore[operator]

    # ------------------------------------------------------------------
    # Fill type implementations
    # ------------------------------------------------------------------

    def _drum_fill_2bar(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Two-bar drum fill: escalating snare ghost notes in bar 0, dense
        triplet snare pattern resolving in bar 1.
        """
        events: List[dict] = []
        bar_count = min(2, fill_bars)

        # Bar 0: ascending ghost notes on all 16th positions.
        for step in range(16):
            beat = step / 4.0
            # Ghost velocity ramps from 40 % → 80 % of intensity.
            ghost_vel = (0.40 + 0.40 * (step / 15.0)) * intensity * 127
            events.append({
                "bar_offset": 0,
                "beat_offset": beat,
                "event_type": "note",
                "target": "snare",
                "value": min(127.0, ghost_vel),
                "duration_beats": 0.25,
                "intensity": 0.40 + 0.40 * (step / 15.0),
            })

        if bar_count < 2:
            return events

        # Bar 1: triplet snare roll — 3 hits per beat for 4 beats = 12 hits.
        for beat_idx in range(4):
            for triplet in range(3):
                beat_offset = beat_idx + triplet / 3.0
                trip_intensity = intensity * (0.7 + 0.3 * (beat_idx / 3.0))
                events.append({
                    "bar_offset": 1,
                    "beat_offset": beat_offset,
                    "event_type": "note",
                    "target": "snare",
                    "value": min(127.0, trip_intensity * 127),
                    "duration_beats": 1 / 3.0,
                    "intensity": trip_intensity,
                })

        return events

    def _drum_fill_1bar(self, fill_bars: int, intensity: float) -> List[dict]:
        """Standard 16th-note snare fill across one bar."""
        events: List[dict] = []
        for step in range(16):
            beat = step / 4.0
            step_vel = (0.50 + 0.50 * (step / 15.0)) * intensity * 127
            events.append({
                "bar_offset": 0,
                "beat_offset": beat,
                "event_type": "note",
                "target": "snare",
                "value": min(127.0, step_vel),
                "duration_beats": 0.25,
                "intensity": 0.50 + 0.50 * (step / 15.0),
            })
        return events

    def _snare_roll(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        16 evenly-spaced snare hits across fill_bars bars with velocity
        escalating from intensity×0.5 to 1.0.
        """
        events: List[dict] = []
        total_beats = fill_bars * 4.0
        for i in range(16):
            beat_offset_abs = (i / 16.0) * total_beats
            bar_offset = int(beat_offset_abs // 4)
            beat_in_bar = beat_offset_abs % 4.0
            frac = i / 15.0
            esc_intensity = intensity * (0.5 + 0.5 * frac)
            events.append({
                "bar_offset": bar_offset,
                "beat_offset": beat_in_bar,
                "event_type": "note",
                "target": "snare",
                "value": min(127.0, esc_intensity * 127),
                "duration_beats": total_beats / 16.0,
                "intensity": esc_intensity,
            })
        return events

    def _hat_triplet_roll(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Hi-hat triplet roll: 3 hits per beat, with the interval between hits
        shrinking as the fill progresses (simulated acceleration).
        """
        events: List[dict] = []
        total_beats = fill_bars * 4
        for beat_idx in range(total_beats):
            # Acceleration: later beats have slightly less spacing (cosmetic).
            for triplet in range(3):
                beat_frac = beat_idx + triplet / 3.0
                bar = beat_frac // 4
                beat_in_bar = beat_frac % 4.0
                acc_intensity = intensity * (0.55 + 0.45 * (beat_idx / max(1, total_beats - 1)))
                events.append({
                    "bar_offset": int(bar),
                    "beat_offset": beat_in_bar,
                    "event_type": "note",
                    "target": "hat",
                    "value": float(_HAT_CLOSED),
                    "duration_beats": 1 / 3.0,
                    "intensity": acc_intensity,
                })
        return events

    def _hat_variation(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Hi-hat pattern shift: emits a velocity_curve change event for the hat
        track, effective for the duration of fill_bars.
        """
        return [{
            "bar_offset": 0,
            "beat_offset": 0.0,
            "event_type": "velocity_curve",
            "target": "hat",
            "value": 0.0,    # 0 = signal to swap to an alternate hat pattern
            "duration_beats": fill_bars * 4.0,
            "intensity": intensity,
        }]

    def _filter_sweep(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        CC ramp on filter_cutoff from current position (assumed 64) to 127
        over fill_bars bars.
        """
        return [{
            "bar_offset": 0,
            "beat_offset": 0.0,
            "event_type": "parameter_ramp",
            "target": "filter_cutoff",
            "value": 127.0,
            "duration_beats": fill_bars * 4.0,
            "intensity": intensity,
        }]

    def _pitch_riser(self, fill_bars: int, intensity: float) -> List[dict]:
        """CC ramp on riser_pitch from 40 to 127 over fill_bars bars."""
        return [{
            "bar_offset": 0,
            "beat_offset": 0.0,
            "event_type": "parameter_ramp",
            "target": "riser_pitch",
            "value": 127.0,
            "duration_beats": fill_bars * 4.0,
            "intensity": intensity,
        }]

    def _tacet_1beat(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Silence event 1 beat before the end of the fill window.
        Creates a dramatic pause right before the drop.
        """
        silence_beat_abs = fill_bars * 4.0 - 1.0
        bar = int(silence_beat_abs // 4)
        beat = silence_beat_abs % 4.0
        return [{
            "bar_offset": bar,
            "beat_offset": beat,
            "event_type": "cc",
            "target": "all_notes_off",
            "value": 0.0,
            "duration_beats": 1.0,
            "intensity": intensity,
        }]

    def _orchestral_riser(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Orchestral riser: simultaneous velocity_curve ramp (crescendo) and
        reverb_size ramp over fill_bars (up to 8 bars).
        """
        ramp_bars = min(8, fill_bars)
        ramp_beats = ramp_bars * 4.0
        return [
            {
                "bar_offset": 0,
                "beat_offset": 0.0,
                "event_type": "parameter_ramp",
                "target": "velocity_curve_scale",
                "value": 1.0,
                "duration_beats": ramp_beats,
                "intensity": intensity,
            },
            {
                "bar_offset": 0,
                "beat_offset": 0.0,
                "event_type": "parameter_ramp",
                "target": "reverb_size",
                "value": 1.0,   # ramp to max reverb
                "duration_beats": ramp_beats,
                "intensity": intensity,
            },
        ]

    def _808_slide(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        808 portamento pitch ramp: CC portamento-time ramp over fill_bars bars.
        """
        return [{
            "bar_offset": 0,
            "beat_offset": 0.0,
            "event_type": "parameter_ramp",
            "target": "808_portamento",
            "value": 64.0,   # moderate portamento depth
            "duration_beats": fill_bars * 4.0,
            "intensity": intensity,
        }]

    def _sub_bass_drop(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Sub-bass drop: CC11 expression ramps to 0, then an all-notes-off event.
        Creates the sensation of the bass disappearing before the drop.
        """
        return [
            {
                "bar_offset": 0,
                "beat_offset": 0.0,
                "event_type": "parameter_ramp",
                "target": "sub_bass_expression",
                "value": 0.0,
                "duration_beats": fill_bars * 4.0 - 1.0,
                "intensity": intensity,
            },
            {
                "bar_offset": fill_bars - 1 if fill_bars > 0 else 0,
                "beat_offset": 3.0,
                "event_type": "cc",
                "target": "all_notes_off",
                "value": 0.0,
                "duration_beats": 1.0,
                "intensity": intensity,
            },
        ]

    def _stutter(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Stutter: 4 rapid notes at 1/32-note intervals starting at beat 3.5.
        """
        events: List[dict] = []
        start_beat = 3.5
        step_size = 0.125   # 1/32 note in beats (at 4/4)
        for i in range(4):
            beat_pos = start_beat + i * step_size
            bar = int(beat_pos // 4)
            beat_in_bar = beat_pos % 4.0
            events.append({
                "bar_offset": min(bar, fill_bars - 1),
                "beat_offset": beat_in_bar,
                "event_type": "note",
                "target": "snare",
                "value": min(127.0, intensity * 127 * (0.6 + 0.4 * i / 3)),
                "duration_beats": step_size,
                "intensity": intensity,
            })
        return events

    def _abrupt_silence(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Abrupt silence: all-notes-off at fill start, re-entry event at fill end.
        """
        re_entry_bar = fill_bars - 1 if fill_bars > 1 else 0
        return [
            {
                "bar_offset": 0,
                "beat_offset": 0.0,
                "event_type": "cc",
                "target": "all_notes_off",
                "value": 0.0,
                "duration_beats": fill_bars * 4.0 - 0.5,
                "intensity": intensity,
            },
            {
                "bar_offset": re_entry_bar,
                "beat_offset": 3.5,
                "event_type": "cc",
                "target": "reentry_signal",
                "value": 1.0,
                "duration_beats": 0.5,
                "intensity": intensity,
            },
        ]

    def _noise_burst(self, fill_bars: int, intensity: float) -> List[dict]:
        """Single high-velocity noise event at bar 0 beat 0."""
        return [{
            "bar_offset": 0,
            "beat_offset": 0.0,
            "event_type": "note",
            "target": "noise",
            "value": 127.0,
            "duration_beats": 0.125,
            "intensity": intensity,
        }]

    def _vinyl_skip(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Vinyl skip: pitch_drift CC event + a small timing stagger descriptor.
        """
        # Random stagger within ±25 ms (encoded as a fractional beat offset).
        stagger_ms = self._rng.uniform(-25.0, 25.0)
        # Approximate: at 120 BPM, 1 beat = 500 ms → stagger in beats.
        stagger_beats = stagger_ms / 500.0
        return [
            {
                "bar_offset": 0,
                "beat_offset": 0.0,
                "event_type": "parameter_ramp",
                "target": "pitch_drift",
                "value": self._rng.uniform(0.2, 0.8),  # random pitch bump
                "duration_beats": 0.5,
                "intensity": intensity * 0.6,
            },
            {
                "bar_offset": 0,
                "beat_offset": max(0.0, 0.25 + stagger_beats),
                "event_type": "cc",
                "target": "timing_stagger",
                "value": stagger_ms,
                "duration_beats": 0.25,
                "intensity": intensity * 0.4,
            },
        ]

    def _chord_chop_entry(self, fill_bars: int, intensity: float) -> List[dict]:
        """
        Chord chop entry: activates the chop LFO velocity_curve for the chord
        track.  Used in future bass at the chorus/drop entry point.
        """
        return [{
            "bar_offset": 0,
            "beat_offset": 0.0,
            "event_type": "velocity_curve",
            "target": "chord_chop_lfo",
            "value": 1.0,   # 1.0 = activate chop LFO
            "duration_beats": fill_bars * 4.0,
            "intensity": intensity,
        }]
