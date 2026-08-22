"""
src/gui/mixer_panel.py
───────────────────────
Container panel for the Groove & Mixer section.

Holds:
  - A compact genre preset row with [Load Preset] and [Reset All] buttons
  - 10 TrackMixerStrip widgets (one per track, all collapsed by default)

Each strip's header always shows the gain fader and pan slider so the
user can adjust volume and stereo position without expanding the strip.

When the user selects a genre and clicks Load Preset, all 10 strips are
populated with theory-correct Tier-1 defaults from GroovePresetLibrary.
The user can then expand any individual strip and tweak the values.

SongGrooveSettings is returned by get_settings() and is passed to
GrooveProcessor before the FluidSynth render in the generation worker.

Cross-platform: pure Tkinter, no OS-specific APIs.

Public API::

    panel = MixerPanel(parent)
    panel.set_genre('trap')              # pre-select genre in dropdown
    settings = panel.get_settings()     # read SongGrooveSettings
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable, Dict, Optional

import numpy as np

from src.gui.styles import S
from src.gui.mixer_strip import TrackMixerStrip
from src.gui.tooltips import ToolTip
from src.midi.groove_settings import SongGrooveSettings, TrackGrooveSettings, TRACK_KEYS
from src.midi.groove_presets import GroovePresetLibrary

try:
    from src.gui.midi_preview_player import MIDIPreviewPlayer
    _PLAYER_AVAILABLE = True
except Exception:
    MIDIPreviewPlayer = None   # type: ignore
    _PLAYER_AVAILABLE = False


# Track keys in display order — matches the left panel track list.
_DISPLAY_ORDER = [
    'drums', 'bass', 'chords', 'lead', 'pad',
    'arp', 'stabs', 'texture', 'fx', 'percussion',
]

# Composition track name → groove key (mirrors app.py's _COMP_TRACK_TO_GROOVE_KEY).
_COMP_TO_GROOVE = {
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

_SOLO_DIR  = Path(__file__).resolve().parent.parent.parent / 'temp_output'
_WAVE_W    = 120   # must match mixer_strip._WAVE_W


class MixerPanel:
    """
    The GROOVE & MIXER collapsible section panel.

    Designed to be embedded into the ADVISOR tab of the right panel so the
    user can hear the effect of groove changes immediately by clicking
    [APPLY GROOVE & RE-RENDER] without regenerating the composition.

    Parameters
    ----------
    parent      : tk.Frame — the advisor tab inner frame.
    on_apply_fn : callable | None — called when the user clicks
                  [APPLY GROOVE & RE-RENDER].  Receives no arguments;
                  the caller reads get_settings() itself.
    """

    def __init__(
        self,
        parent:              tk.Frame,
        on_apply_fn=None,
        get_composition_fn:  Optional[Callable] = None,
    ) -> None:
        self._library    = GroovePresetLibrary()
        self._strips: Dict[str, TrackMixerStrip] = {}
        self._on_apply_fn        = on_apply_fn
        self._get_composition_fn = get_composition_fn

        # Shared solo player — one track plays at a time.
        self._solo_player      = MIDIPreviewPlayer() if _PLAYER_AVAILABLE else None
        self._active_solo_strip: Optional[TrackMixerStrip] = None

        # Hidden state — groove processing is always enabled.
        # Kept as a variable so get_settings() continues to work unchanged.
        self._apply_var = tk.BooleanVar(value=True)

        # ── Outer collapsible wrapper ──────────────────────────────────────────
        # Mirrors the style of CollapsibleSection but is self-contained so
        # MixerPanel does not depend on that class as a base.
        self._collapsed = True

        outer = tk.Frame(parent, bg=S.BG2)
        outer.pack(fill='x', padx=6, pady=4)
        self._outer = outer

        # Header row
        hdr = tk.Frame(outer, bg=S.BG2)
        hdr.pack(fill='x')

        self._arrow_var = tk.StringVar(value='▶')
        tk.Button(
            hdr,
            textvariable=self._arrow_var,
            command=self._toggle,
            font=('Consolas', 10, 'bold'),
            fg=S.ORANGE,
            bg=S.BG2,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG2,
            bd=0, padx=4, pady=0,
            cursor='hand2',
            highlightthickness=0,
            relief='flat',
        ).pack(side='left')

        tk.Label(
            hdr,
            text='GROOVE & MIXER',
            font=S.FN_H,
            fg=S.ORANGE,
            bg=S.BG2,
            anchor='w',
        ).pack(side='left', fill='x', padx=4)

        # Horizontal accent separator
        tk.Frame(outer, bg=S.ORANGE, height=1).pack(fill='x', pady=(2, 4))

        # ── Content frame (hidden when collapsed) ─────────────────────────────
        self._content = tk.Frame(outer, bg=S.BG2)
        # Content starts hidden; _toggle() will show it on first click.

        self._build_content()

    # ── Content construction ──────────────────────────────────────────────────

    def _build_content(self) -> None:
        """Build the preset row and all track strips."""
        c = self._content

        # ── Genre preset row (compact) ────────────────────────────────────────
        preset_row = tk.Frame(c, bg=S.BG2); preset_row.pack(fill='x', pady=(0, 6))
        tk.Label(
            preset_row,
            text='Genre preset:',
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
        ).pack(side='left')

        self._genre_var = tk.StringVar(value='pop')
        genre_cb = ttk.Combobox(
            preset_row,
            textvariable=self._genre_var,
            values=self._library.genre_list(),
            state='readonly',
            font=S.FN_X,
            width=12,
        )
        genre_cb.pack(side='left', padx=6)

        _load_btn = tk.Button(
            preset_row,
            text='Load Preset',
            font=S.FN_X,
            fg=S.ORANGE, bg=S.BG_BTN,
            activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
            bd=0, padx=8, pady=2,
            cursor='hand2',
            command=self._load_preset,
        )
        _load_btn.pack(side='left', padx=2)
        ToolTip(_load_btn,
                'Load theory-correct Tier-1 groove defaults for the selected genre\n'
                'into all 10 track strips.  Tier-2 humanise values (jitter, seed)\n'
                'are preserved so tuned randomisation settings are not overwritten.')

        # Reset All → Identity button: returns every track to a pass-through
        # state (no velocity scaling, no swing, no pan offset, etc.) in one
        # click.  Equivalent to the DAW "Bypass" concept applied to all tracks.
        _reset_btn = tk.Button(
            preset_row,
            text='Reset All',
            font=S.FN_X,
            fg=S.TXT_DIM, bg=S.BG_BTN,
            activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
            bd=0, padx=8, pady=2,
            cursor='hand2',
            command=self._reset_all,
        )
        _reset_btn.pack(side='left', padx=2)
        ToolTip(_reset_btn,
                'Reset every track strip to the identity (no-change) state.\n\n'
                'Identity means: no velocity scaling, no swing, no timing nudge,\n'
                'no pan offset, no humanisation — MIDI output is unchanged.\n\n'
                'Use this to hear the raw MIDI before any groove processing,\n'
                'or as a clean starting point before tweaking individual tracks.')

        # ── Thin divider before track strips ─────────────────────────────────
        tk.Frame(c, bg=S.BG3, height=1).pack(fill='x', pady=(2, 4))

        # ── Solo batch controls ───────────────────────────────────────────────
        if self._solo_player is not None:
            solo_ctrl = tk.Frame(c, bg=S.BG2)
            solo_ctrl.pack(fill='x', pady=(0, 4))

            self._btn_render_all = tk.Button(
                solo_ctrl,
                text='▶  RENDER ALL SOLOS',
                font=S.FN_X,
                fg=S.CYAN, bg=S.BG_BTN,
                activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
                bd=0, padx=10, pady=4, cursor='hand2', relief='flat',
                command=self._render_all_solos,
            )
            self._btn_render_all.pack(side='left', padx=(0, 4))
            ToolTip(self._btn_render_all,
                    'Render every track in isolation, one at a time.\n'
                    'Each strip\'s waveform appears as its render completes.\n'
                    'Reflects the composition as generated — raw preview,\n'
                    'no Groove & Mix post-processing applied.')

            self._btn_reset_solos = tk.Button(
                solo_ctrl,
                text='✕  RESET SOLOS',
                font=S.FN_X,
                fg=S.TXT_DIM, bg=S.BG_BTN,
                activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
                bd=0, padx=10, pady=4, cursor='hand2', relief='flat',
                command=self._reset_all_solos,
            )
            self._btn_reset_solos.pack(side='left')
            ToolTip(self._btn_reset_solos,
                    'Clear all cached solo renders.\n'
                    'Use this after re-generating or changing instrument\n'
                    'settings so you don\'t hear stale audio.')
        else:
            self._btn_render_all  = None
            self._btn_reset_solos = None

        # ── Track strips ──────────────────────────────────────────────────────
        _has_solo = self._solo_player is not None
        for track_key in _DISPLAY_ORDER:
            color = S.TRACK_CLR.get(track_key, S.CYAN)
            strip = TrackMixerStrip(
                c,
                track_key=track_key,
                color=color,
                solo_fn    = self._start_solo_render if _has_solo else None,
                stop_fn    = self._stop_solo         if _has_solo else None,
                play_fn    = self._play_solo_wav     if _has_solo else None,
                get_pos_fn = self._get_solo_pos      if _has_solo else None,
            )
            self._strips[track_key] = strip

        # ── Apply & Re-render button ───────────────────────────────────────────
        # Placed after all strips so the user can adjust settings and then
        # trigger a re-render in one click without switching panels.
        tk.Frame(c, bg=S.BG3, height=1).pack(fill='x', pady=(6, 4))
        apply_row = tk.Frame(c, bg=S.BG2); apply_row.pack(fill='x', pady=(0, 6))
        self._btn_apply = tk.Button(
            apply_row,
            text='APPLY GROOVE & RE-RENDER',
            font=S.FN_H,
            fg=S.BG,
            bg=S.ORANGE,
            activeforeground=S.BG,
            activebackground=S.YELLOW,
            bd=0,
            padx=12,
            pady=6,
            cursor='hand2',
            relief='flat',
            command=self._on_apply,
        )
        self._btn_apply.pack(fill='x', padx=4)
        tk.Label(
            apply_row,
            text='Applies groove settings to the current MIDI and re-renders audio',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
        ).pack(pady=(2, 0))

    # ── Public API ────────────────────────────────────────────────────────────

    def set_genre(self, genre: str) -> None:
        """
        Pre-select the genre in the preset dropdown.

        Called when the user changes genre in the main genre panel so
        the mixer's preset selector stays in sync.  Does NOT automatically
        load the preset — the user must click [Load Preset] to apply it.
        """
        genres = self._library.genre_list()
        if genre in genres:
            self._genre_var.set(genre)

    def get_settings(self, genre: Optional[str] = None) -> SongGrooveSettings:
        """
        Read all track strips and return a SongGrooveSettings.

        Called from the generation worker thread to capture the current
        state before processing starts.  All Tkinter variable reads happen
        on the main thread — this method must be called before spawning
        the worker thread, not from inside it.

        Parameters
        ----------
        genre : str | None
            Active genre string (e.g. 'trap').  When provided it is stored on
            SongGrooveSettings so GrooveProcessor can derive genre-aware
            MicroTimingEngine grids for unconfigured tracks.
        """
        tracks = {
            key: strip.get_settings()
            for key, strip in self._strips.items()
        }
        return SongGrooveSettings(
            tracks=tracks,
            apply_enabled=self._apply_var.get(),
            genre=genre,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def set_busy(self, busy: bool) -> None:
        """
        Disable the apply button while a re-render is in progress so the user
        cannot queue multiple concurrent renders.  Called by the app on worker
        thread start and completion.
        """
        state = 'disabled' if busy else 'normal'
        self._btn_apply.configure(state=state)

    def _on_apply(self) -> None:
        """Fire the apply callback if one was registered."""
        if self._on_apply_fn is not None:
            self._on_apply_fn()

    def _toggle(self) -> None:
        """Expand or collapse the panel content."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._content.pack_forget()
            self._arrow_var.set('▶')
        else:
            self._content.pack(fill='x')
            self._arrow_var.set('▼')

    def _load_preset(self) -> None:
        """
        Load theory-correct Tier-1 defaults for the selected genre into
        all track strips.

        Tier-2 (humanise) values are intentionally left untouched so that
        a user who has locked a seed or tuned humanise amounts does not
        lose those settings when switching genre presets.
        """
        genre = self._genre_var.get()
        preset: SongGrooveSettings = self._library.get(genre)

        for key, strip in self._strips.items():
            track_settings = preset.get(key)
            # Preserve existing Tier-2 values — only update Tier-1 fields.
            current = strip.get_settings()
            track_settings.vel_humanize       = current.vel_humanize
            track_settings.timing_humanize_ms = current.timing_humanize_ms
            track_settings.seed               = current.seed
            strip.load(track_settings)

    # ── Solo preview ──────────────────────────────────────────────────────────

    def _render_all_solos(self) -> None:
        """Sequentially render all 10 tracks in isolation in a single background thread."""
        comp = self._get_composition_fn() if self._get_composition_fn else None
        if comp is None:
            return

        self._stop_solo()
        if self._active_solo_strip is not None:
            self._active_solo_strip.set_solo_stopped()
            self._active_solo_strip = None

        keys = list(self._strips.keys())
        total = len(keys)

        if self._btn_render_all:
            self._btn_render_all.configure(state='disabled', fg=S.TXT_DIM)
        if self._btn_reset_solos:
            self._btn_reset_solos.configure(state='disabled')

        def _worker() -> None:
            for i, track_key in enumerate(keys):
                # Update button label on main thread
                label = f'Rendering {i + 1} / {total}…'
                if self._btn_render_all:
                    self._content.after(0, lambda l=label: self._btn_render_all.configure(text=l))

                strip = self._strips.get(track_key)
                if strip is None:
                    continue

                try:
                    solo_comp = self._make_solo_composition(comp, track_key)
                    self._neutralize_programs(solo_comp)
                    from src.rendering.builtin_synthesizer import BuiltinSynthesizer
                    from src.rendering.wav_writer import write_wav

                    synth   = BuiltinSynthesizer()
                    samples = synth.render_composition(solo_comp)
                    peaks   = self._compute_peaks(samples, _WAVE_W)

                    _SOLO_DIR.mkdir(parents=True, exist_ok=True)
                    wav_path = str(_SOLO_DIR / f'solo_{track_key}.wav')
                    write_wav(wav_path, samples, 44100)

                    bpm      = float(solo_comp.get('config', {}).get('bpm', 120.0))
                    duration = solo_comp.get('total_bars', 8) * 4 * (60.0 / bpm)

                    self._content.after(
                        0, lambda s=strip, w=wav_path, d=duration, p=peaks:
                        s._on_solo_ready(w, d, p, autoplay=False)
                    )
                except Exception as exc:
                    print(f'[MixerPanel] render-all error ({track_key}): {exc}')

            # Restore button on main thread
            def _done() -> None:
                if self._btn_render_all:
                    self._btn_render_all.configure(
                        text='▶  RENDER ALL SOLOS', state='normal', fg=S.CYAN)
                if self._btn_reset_solos:
                    self._btn_reset_solos.configure(state='normal')
            self._content.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _reset_all_solos(self) -> None:
        """Clear every strip's cached solo render and stop any active playback."""
        self._stop_solo()
        if self._active_solo_strip is not None:
            self._active_solo_strip.set_solo_stopped()
            self._active_solo_strip = None
        for strip in self._strips.values():
            strip.reset_solo()

    def _start_solo_render(self, track_key: str, done_cb: Callable) -> None:
        """Start a background solo render for *track_key*, call done_cb when ready."""
        comp = self._get_composition_fn() if self._get_composition_fn else None
        if comp is None:
            done_cb(None, 0.0, None)
            return

        # Stop any currently playing solo and notify the active strip.
        if self._active_solo_strip is not None:
            self._active_solo_strip.set_solo_stopped()
            self._active_solo_strip = None
        self._stop_solo()
        self._active_solo_strip = self._strips.get(track_key)

        def _worker() -> None:
            try:
                solo_comp = self._make_solo_composition(comp, track_key)
                self._neutralize_programs(solo_comp)
                from src.rendering.builtin_synthesizer import BuiltinSynthesizer
                from src.rendering.wav_writer import write_wav

                synth   = BuiltinSynthesizer()
                samples = synth.render_composition(solo_comp)
                peaks   = self._compute_peaks(samples, _WAVE_W)

                _SOLO_DIR.mkdir(parents=True, exist_ok=True)
                wav_path = str(_SOLO_DIR / f'solo_{track_key}.wav')
                write_wav(wav_path, samples, 44100)

                bpm      = float(solo_comp.get('config', {}).get('bpm', 120.0))
                duration = solo_comp.get('total_bars', 8) * 4 * (60.0 / bpm)

                self._content.after(0, lambda: done_cb(wav_path, duration, peaks))
            except Exception as exc:
                print(f'[MixerPanel] solo render error ({track_key}): {exc}')
                self._content.after(0, lambda: done_cb(None, 0.0, None))

        threading.Thread(target=_worker, daemon=True).start()

    def _make_solo_composition(self, comp: dict, track_key: str) -> dict:
        """Return a filtered composition containing only the tracks for *track_key*."""
        keep = {ct for ct, gk in _COMP_TO_GROOVE.items() if gk == track_key}
        return {
            'config':     comp.get('config', {}),
            'total_bars': comp.get('total_bars', 8),
            'tracks':     {k: v for k, v in comp.get('tracks', {}).items() if k in keep},
            'track_info': {k: dict(v) for k, v in comp.get('track_info', {}).items() if k in keep},
        }

    @staticmethod
    def _neutralize_programs(solo_comp: dict) -> None:
        """Reset every melodic track to program 0 (neutral timbre).

        Drums (channel 9) keep their synthesis path — kick/snare/hihat
        rhythm is content, not clothing. Everything else gets a plain
        default so the solo is unambiguously a note-content preview.
        """
        for info in solo_comp.get('track_info', {}).values():
            if info.get('channel', 0) != 9:
                info['program'] = 0

    def _stop_solo(self) -> None:
        if self._solo_player:
            self._solo_player.stop()

    def _play_solo_wav(self, wav_path: str, start_sec: float) -> None:
        if self._solo_player:
            self._solo_player.play_wav(wav_path, start_sec)

    def _get_solo_pos(self) -> float:
        return self._solo_player.get_current_sec() if self._solo_player else 0.0

    @staticmethod
    def _compute_peaks(samples: list, width: int) -> list:
        """Downsample *samples* to *width* peak values normalised 0.0–1.0."""
        arr = np.abs(np.array(samples, dtype=np.float32))
        n   = len(arr)
        if n == 0:
            return [0.0] * width
        pad = (-n) % width
        if pad:
            arr = np.pad(arr, (0, pad))
        peaks    = arr.reshape(width, -1).max(axis=1)
        peak_max = float(peaks.max())
        if peak_max < 1e-6:
            peak_max = 1.0
        return (peaks / peak_max).tolist()

    def _reset_all(self) -> None:
        """
        Reset every track strip to the identity TrackGrooveSettings.

        Identity = TrackGrooveSettings() defaults:
          - transpose_st = 0, gain_db = 0.0
          - vel_min/max = 64/100, vel_curve = 'flat', swing_pct = 50, nudge = 0
          - pan = 0, vel_humanize = 0, timing_humanize_ms = 0, seed = 0
          - use_advanced = False, v/t/p/e_grid = None

        The GrooveProcessor treats this as a pure pass-through — the MIDI
        output is identical to the unprocessed input.  Equivalent to the
        DAW "Bypass" concept applied to all tracks simultaneously.

        Cross-platform: pure Tkinter variable writes; no OS-specific code.
        """
        identity = TrackGrooveSettings()   # all defaults = no change
        for strip in self._strips.values():
            strip.load(identity)
