"""
src/midi/groove_processor.py
─────────────────────────────
Applies SongGrooveSettings to a MIDI file and writes a modified copy.

Transforms applied per track (in order):
  1. Transpose       — shift all note pitches by ±N semitones (Tier 1)
  2. Swing           — delay off-beat 16th notes (Tier 1)
  3. Timing nudge    — fixed ±ms offset for every note (Tier 1)
  4. Timing humanise — seeded random ±ms jitter per note (Tier 2)
  5. Velocity clamp  — rescale all velocities to [vel_min, vel_max] (Tier 1)
  6. Velocity curve  — accent pattern multipliers across the bar (Tier 1)
  7. Velocity humanise — seeded random ±vel jitter per note (Tier 2)
  8. Gain CC7        — write CC7 at track start for mixer volume (Tier 1)
  9. Pan CC10        — write CC10 at track start for stereo position (Tier 1)

Cross-platform: uses mido (pure-Python), no OS-specific code.
Reads/writes standard MIDI format 1 files.

Public API::

    ok = GrooveProcessor().process(
        midi_in  = 'preview.mid',
        midi_out = 'preview_groove.mid',
        settings = song_groove_settings,
        bpm      = 140.0,
    )
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

try:
    import mido
    _MIDO_AVAILABLE = True
except ImportError:
    _MIDO_AVAILABLE = False

from src.midi.groove_settings import SongGrooveSettings, TrackGrooveSettings
from src.midi.grid_to_preset import VEL_CURVE_GRIDS

try:
    from src.midi.genre_profiles import GenreProfileLibrary as _GenreProfileLibrary
    from src.midi.micro_timing_engine import MicroTimingEngine as _MicroTimingEngine
    _MICRO_TIMING_AVAILABLE = True
except ImportError:
    _MICRO_TIMING_AVAILABLE = False


# ── MIDI track-name → GUI track key mapping ────────────────────────────────────
# The composition engine names MIDI tracks '01_Kick', '03_Bass', etc.
# This map converts those names to the GUI keys used in track_vars / SongGrooveSettings.
_MIDI_NAME_TO_KEY: Dict[str, str] = {
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

# Single source of truth for velocity-curve grids lives in grid_to_preset.py.
# Alias kept here for readability inside _apply_track.
_CURVE_MULTIPLIERS = VEL_CURVE_GRIDS


def _db_to_cc7(gain_db: float) -> int:
    """
    Convert a gain in dB to a MIDI CC7 (volume) value 0-127.

    0 dB maps to CC7=100 (standard nominal level for GM).  Values at or
    below -59.9 dB are treated as −∞ and return CC7=0 (silence).
    The nominal (0 dB) point is anchored at CC7=100 so there is headroom
    above for boosts up to +6 dB.
    """
    if gain_db <= -59.9:
        return 0   # −∞ / silence
    nominal_cc7    = 100
    amplitude_mult = 10 ** (gain_db / 20.0)
    cc7 = int(nominal_cc7 * amplitude_mult)
    return max(0, min(127, cc7))


def _pan_to_cc10(pan: int) -> int:
    """
    Convert pan (-64 to +63) to MIDI CC10 (0-127).

    0 (center) maps to CC10=64, which is the GM standard for centre.
    -64 maps to CC10=0 (hard left), +63 maps to CC10=127 (hard right).
    """
    return max(0, min(127, 64 + pan))


def _get_tempo_from_midi(mid: 'mido.MidiFile') -> int:
    """Extract the first set_tempo message from the MIDI file (microseconds per beat)."""
    for track in mid.tracks:
        for msg in track:
            if msg.type == 'set_tempo':
                return msg.tempo
    return 500_000  # default 120 BPM


def _delta_to_abs(track: 'mido.MidiTrack') -> List[tuple]:
    """
    Convert a mido track with delta times to a list of (abs_tick, message) tuples.

    mido stores message times as delta ticks (time since previous message).
    Converting to absolute ticks simplifies time-based transformations.
    """
    abs_time = 0
    result = []
    for msg in track:
        abs_time += msg.time
        result.append((abs_time, msg))
    return result


def _abs_to_delta(abs_msgs: List[tuple]) -> List['mido.Message']:
    """
    Convert a list of (abs_tick, message) tuples back to delta-time mido messages.

    Messages are sorted by absolute tick to fix any ordering disrupted by
    timing transforms (swing or humanise can reorder very close notes).
    """
    # Sort by absolute time; preserve insertion order for simultaneous events.
    sorted_msgs = sorted(abs_msgs, key=lambda x: x[0])
    result = []
    prev_tick = 0
    for abs_tick, msg in sorted_msgs:
        delta = max(0, abs_tick - prev_tick)
        result.append(msg.copy(time=delta))
        prev_tick = abs_tick
    return result


def _apply_track(
    track: 'mido.MidiTrack',
    settings: TrackGrooveSettings,
    ticks_per_beat: int,
    bpm: float,
) -> 'mido.MidiTrack':
    """
    Apply all groove transforms to a single MIDI track.

    Parameters
    ----------
    track          : Input mido MidiTrack.
    settings       : Groove settings for this track.
    ticks_per_beat : From the MIDI file header.
    bpm            : Composition tempo (used for ms→tick conversion).

    Returns a new MidiTrack with all transforms applied.
    """
    # ── Pre-compute constants ─────────────────────────────────────────────────
    ticks_per_second   = ticks_per_beat * (bpm / 60.0)
    ms_to_ticks        = ticks_per_second / 1000.0

    # 16th-note duration in ticks (4/4 assumed).
    sixteenth_ticks    = ticks_per_beat / 4.0

    # Bar duration in ticks (16 sixteenth notes per 4/4 bar).
    bar_ticks          = sixteenth_ticks * 16

    # Swing offset for off-beat 16ths (ticks to add to off-beat notes).
    # At 50 % (straight) this is 0; at 66 % it equals a full triplet feel.
    swing_offset_ticks = (settings.swing_pct / 100.0 - 0.5) * 2.0 * sixteenth_ticks

    # Fixed timing nudge in ticks (can be negative to push ahead of grid).
    nudge_ticks        = settings.timing_nudge_ms * ms_to_ticks

    # Tier-2 seeded RNG — identical seed → identical humanisation.
    rng = random.Random(settings.effective_seed())

    # Velocity curve multiplier table (indexed by 16th step 0-15).
    curve = _CURVE_MULTIPLIERS.get(settings.vel_curve, _CURVE_MULTIPLIERS['flat'])

    # CC7 / CC10 values derived from Tier-1 gain and pan settings.
    cc7_val  = _db_to_cc7(settings.gain_db)
    cc10_val = _pan_to_cc10(settings.pan)

    # ── Build absolute-time message list ──────────────────────────────────────
    abs_msgs: List[Tuple[int, 'mido.Message']] = []

    # Inject CC7 (volume) and CC10 (pan) at tick 0 of the track.
    # Find the channel from the first channel message to avoid hard-coding it.
    channel = 0
    for msg in track:
        if hasattr(msg, 'channel'):
            channel = msg.channel
            break

    abs_msgs.append((0, mido.Message('control_change', channel=channel,
                                     control=7, value=cc7_val, time=0)))

    # Inject constant CC10 (pan) only in simple mode.
    # In advanced mode with a P grid, per-step CC10 is injected per note_on below.
    _adv_p = settings.use_advanced and settings.p_grid and len(settings.p_grid) == 16
    if not _adv_p:
        abs_msgs.append((0, mido.Message('control_change', channel=channel,
                                         control=10, value=cc10_val, time=0)))

    # ── Process each message ──────────────────────────────────────────────────
    for abs_tick, msg in _delta_to_abs(track):

        if msg.type in ('note_on', 'note_off'):
            # ── 1. Transpose ─────────────────────────────────────────────────
            new_pitch = max(0, min(127, msg.note + settings.transpose_st))

            # ── 2 & 3. Timing: T grid (advanced) or swing + nudge (simple) ───
            tick_in_bar = abs_tick % int(bar_ticks) if bar_ticks > 0 else 0
            step_in_bar = tick_in_bar / sixteenth_ticks if sixteenth_ticks > 0 else 0
            step_index  = int(round(step_in_bar)) % 16

            if settings.use_advanced and settings.t_grid and len(settings.t_grid) == 16:
                # T grid gives the total per-step timing offset in ms.
                # This replaces both swing and uniform nudge simultaneously.
                new_tick = max(0, abs_tick + int(settings.t_grid[step_index] * ms_to_ticks))
            else:
                # Off-beat 16ths: odd steps (1, 3, 5 … 15) get the swing delay.
                new_tick = abs_tick
                if step_index % 2 == 1:
                    new_tick = abs_tick + int(swing_offset_ticks)
                # Fixed nudge applied to all notes.
                new_tick = max(0, new_tick + int(nudge_ticks))

            # ── 4. Timing humanise (Tier 2, seeded random) ───────────────────
            if settings.timing_humanize_ms > 0.001:
                jitter_ticks = rng.uniform(
                    -settings.timing_humanize_ms,
                     settings.timing_humanize_ms
                ) * ms_to_ticks
                new_tick = max(0, new_tick + int(jitter_ticks))

            # ── 5-7. Velocity transforms (note_on only; note_off vel=0 kept) ─
            new_vel = msg.velocity
            if msg.type == 'note_on' and msg.velocity > 0:
                # 5. Clamp: rescale from [1,127] to [vel_min, vel_max].
                ratio   = (msg.velocity - 1) / 126.0
                new_vel = int(settings.vel_min + ratio * (settings.vel_max - settings.vel_min))

                # 6. Velocity multiplier: V grid (advanced) or named curve (simple).
                if settings.use_advanced and settings.v_grid and len(settings.v_grid) == 16:
                    step_mult = max(0.0, settings.v_grid[step_index])
                else:
                    step_mult = curve[step_index]
                new_vel = int(new_vel * step_mult)

                # 7. Velocity humanise (Tier 2).
                if settings.vel_humanize > 0:
                    new_vel += rng.randint(-settings.vel_humanize, settings.vel_humanize)

                new_vel = max(1, min(127, new_vel))

                # ── 8a. Per-step pan CC10 (advanced mode with P grid) ─────────
                # Injected just before the note so playback applies the new pan
                # before this note sounds.  Stable sort keeps CC before note_on.
                if _adv_p:
                    pan_val = _pan_to_cc10(int(round(settings.p_grid[step_index])))
                    abs_msgs.append((new_tick, mido.Message(
                        'control_change', channel=channel,
                        control=10, value=pan_val, time=0,
                    )))

                # ── 8b. Per-step expression CC11 (advanced mode with E grid) ──
                _adv_e = settings.use_advanced and settings.e_grid and len(settings.e_grid) == 16
                if _adv_e:
                    expr_val = max(0, min(127, int(round(settings.e_grid[step_index]))))
                    abs_msgs.append((new_tick, mido.Message(
                        'control_change', channel=channel,
                        control=11, value=expr_val, time=0,
                    )))

            abs_msgs.append((
                new_tick,
                msg.copy(note=new_pitch, velocity=new_vel, time=0),
            ))

        else:
            # Pass non-note messages (CC, meta, etc.) through unchanged.
            # Skip CC7 and CC10 — we inject fresh values at tick 0 so any
            # original CC7/CC10 in the MIDI must be removed to prevent them
            # from overriding our values at playback time.
            if msg.type == 'control_change' and msg.control == 7:
                continue   # replaced by our gain_db → CC7 at tick 0
            if msg.type == 'control_change' and msg.control == 10 and not _adv_p:
                continue   # replaced by our pan → CC10 at tick 0
            abs_msgs.append((abs_tick, msg))

    # ── Reassemble track with delta times ─────────────────────────────────────
    new_track = mido.MidiTrack()
    for delta_msg in _abs_to_delta(abs_msgs):
        new_track.append(delta_msg)
    return new_track


class GrooveProcessor:
    """
    Reads a MIDI file, applies SongGrooveSettings, and writes the result.

    Designed to be called from a background thread — no Tkinter calls, no
    global state.  Instantiate and call process() for each render.
    """

    def process(
        self,
        midi_in:  str,
        midi_out: str,
        settings: SongGrooveSettings,
        bpm:      float = 120.0,
    ) -> bool:
        """
        Apply groove settings to *midi_in* and write the result to *midi_out*.

        Parameters
        ----------
        midi_in  : Path to the source MIDI file.
        midi_out : Path where the processed MIDI will be written.
                   Can equal midi_in; the original is never partially overwritten.
        settings : SongGrooveSettings containing per-track transformations.
        bpm      : Composition tempo; used for ms→tick conversion of nudge
                   and humanise offsets.

        Returns
        -------
        True on success, False on any failure (mido unavailable, parse error, etc.).
        """
        if not _MIDO_AVAILABLE:
            print('[GrooveProcessor] mido not available — groove processing skipped')
            return False

        if not settings.apply_enabled or not settings.has_any_effect():
            # Nothing to do — copy the file only if paths differ.
            if midi_in != midi_out:
                import shutil
                shutil.copy2(midi_in, midi_out)
            return True

        try:
            mid = mido.MidiFile(midi_in)
            ticks_per_beat = mid.ticks_per_beat

            # Use tempo from the MIDI file itself if available, as it may differ
            # from the config bpm passed in (e.g. due to tempo automation).
            midi_tempo = _get_tempo_from_midi(mid)
            effective_bpm = 60_000_000 / midi_tempo if midi_tempo > 0 else bpm

            # ── Genre-aware micro-timing grids ────────────────────────────────
            # When SongGrooveSettings.genre is set, derive a 16-step V grid and
            # T grid from MicroTimingEngine (genre-aware velocity curves + swing +
            # jitter).  These replace the flat curve / simple swing path for any
            # track the user has not manually configured in advanced mode.
            _micro_v_grid = None
            _micro_t_grid = None
            if _MICRO_TIMING_AVAILABLE and settings.genre:
                try:
                    _profile = _GenreProfileLibrary().get(settings.genre, effective_bpm)
                    _engine  = _MicroTimingEngine(_profile)
                    _micro_v_grid, _micro_t_grid = _engine.get_bar_params()
                except Exception:
                    pass  # silently fall back to the existing flat/swing path

            new_mid = mido.MidiFile(type=mid.type, ticks_per_beat=ticks_per_beat)

            for track in mid.tracks:
                # Identify which GUI track key this MIDI track belongs to.
                track_name = ''
                for msg in track:
                    if msg.type == 'track_name':
                        track_name = msg.name
                        break

                track_key = _MIDI_NAME_TO_KEY.get(track_name)
                track_settings = settings.get(track_key) if track_key else None

                # Skip processing tracks with identity settings or unknown names.
                if track_settings is None or track_settings.is_identity():
                    new_mid.tracks.append(track)
                    continue

                # Inject genre micro-timing grids for tracks the user has not
                # manually configured (no advanced mode, no custom v_grid).
                # dataclasses.replace() creates a shallow copy — original unchanged.
                applied_settings = track_settings
                if (
                    _micro_v_grid is not None
                    and not track_settings.use_advanced
                    and track_settings.v_grid is None
                ):
                    from dataclasses import replace as _dc_replace
                    applied_settings = _dc_replace(
                        track_settings,
                        use_advanced = True,
                        v_grid       = _micro_v_grid,
                        t_grid       = _micro_t_grid,
                    )

                new_mid.tracks.append(
                    _apply_track(track, applied_settings, ticks_per_beat, effective_bpm)
                )

            new_mid.save(midi_out)
            return True

        except Exception as exc:
            print(f'[GrooveProcessor] Error: {exc}')
            return False
