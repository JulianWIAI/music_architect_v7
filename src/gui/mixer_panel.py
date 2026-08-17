"""
src/gui/mixer_panel.py
───────────────────────
Container panel for the Groove & Mixer section.

Holds:
  - An "Apply groove to render" enable toggle
  - A genre preset dropdown with [Load Preset] button
  - 10 TrackMixerStrip widgets (one per track, all collapsed by default)

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

import tkinter as tk
from tkinter import ttk
from typing import Dict

from src.gui.styles import S
from src.gui.mixer_strip import TrackMixerStrip
from src.gui.tooltips import ToolTip
from src.midi.groove_settings import SongGrooveSettings, TrackGrooveSettings, TRACK_KEYS
from src.midi.groove_presets import GroovePresetLibrary


# Track keys in display order — matches the left panel track list.
_DISPLAY_ORDER = [
    'drums', 'bass', 'chords', 'lead', 'pad',
    'arp', 'stabs', 'texture', 'fx', 'percussion',
]


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
        parent:       tk.Frame,
        on_apply_fn=None,
    ) -> None:
        self._library    = GroovePresetLibrary()
        self._strips: Dict[str, TrackMixerStrip] = {}
        self._on_apply_fn = on_apply_fn

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
        """Build the enable toggle, preset row, and all track strips."""
        c = self._content

        # ── Enable toggle ─────────────────────────────────────────────────────
        top = tk.Frame(c, bg=S.BG2); top.pack(fill='x', pady=(0, 4))
        self._apply_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            top,
            text='Apply groove processing to every render',
            variable=self._apply_var,
            font=S.FN_S,
            fg=S.ORANGE,
            bg=S.BG2,
            selectcolor=S.BG3,
            activebackground=S.BG2,
            activeforeground=S.ORANGE,
        ).pack(side='left')

        # ── Genre preset row ──────────────────────────────────────────────────
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

        tk.Label(
            preset_row,
            text='← loads theory-correct defaults',
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
        ).pack(side='left', padx=6)

        # ── Thin divider before track strips ─────────────────────────────────
        tk.Frame(c, bg=S.BG3, height=1).pack(fill='x', pady=(2, 4))

        # ── Track strips ──────────────────────────────────────────────────────
        for track_key in _DISPLAY_ORDER:
            color = S.TRACK_CLR.get(track_key, S.CYAN)
            strip = TrackMixerStrip(c, track_key=track_key, color=color)
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

    def get_settings(self) -> SongGrooveSettings:
        """
        Read all track strips and return a SongGrooveSettings.

        Called from the generation worker thread to capture the current
        state before processing starts.  All Tkinter variable reads happen
        on the main thread — this method must be called before spawning
        the worker thread, not from inside it.
        """
        tracks = {
            key: strip.get_settings()
            for key, strip in self._strips.items()
        }
        return SongGrooveSettings(
            tracks=tracks,
            apply_enabled=self._apply_var.get(),
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
