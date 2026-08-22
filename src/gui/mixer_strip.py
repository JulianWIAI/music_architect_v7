"""
src/gui/mixer_strip.py
───────────────────────
A collapsible per-track mixer strip widget.

Layout — header (always visible)
─────────────────────────────────
  [▶] TRACK   [━━━━━━━━━━━━━━] +0.0 dB  │  [pan━━━━] C   <summary>

Layout when expanded
────────────────────
  Transpose : slider  −24 … +24 st   [−12] [0] [+12]

  GROOVE
  Swing %   : slider  50.0 … 66.0 %     Nudge : spinbox  −50 … +50 ms
  Vel min   : spinbox 1 … 127           Vel max: spinbox 1 … 127
  Vel curve : combobox (flat / accent_1 / accent_1_3 / crescendo / decrescendo)

  HUMANIZE
  Vel jitter : slider  0 … 30            Time jitter: slider 0 … 20 ms
  Seed       : entry field + [Roll] button

  [ADVANCED ▸]  /  [◂ SIMPLIFIED]

All widgets are pure Tkinter — no platform-specific APIs.
Works on macOS and Windows.

Public API::

    strip = TrackMixerStrip(parent, track_key='lead', color=S.TRACK_CLR['lead'])
    strip.load(track_groove_settings)   # populate from a TrackGrooveSettings
    s = strip.get_settings()            # read back a TrackGrooveSettings
"""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

_WAVE_W: int = 120   # solo waveform canvas width in pixels
_WAVE_H: int = 22    # solo waveform canvas height in pixels

from src.gui.styles import S
from src.gui.tooltips import ToolTip
from src.midi.groove_settings import TrackGrooveSettings, VEL_CURVES
from src.gui.fader_utils import (
    _pos_to_db, _db_to_pos,
    _GAIN_STEPS, _GAIN_MIN_DB, _GAIN_MAX_DB, _GAIN_INF_FLOOR,
)

# AdvancedGrooveView is optional — import failure just disables the toggle.
try:
    from src.gui.advanced_groove_view import AdvancedGrooveView
    _ADV_AVAILABLE = True
except Exception:
    AdvancedGrooveView = None   # type: ignore
    _ADV_AVAILABLE     = False


class TrackMixerStrip:
    """
    Collapsible mixer + groove strip for one track.

    The gain fader and pan slider are always visible in the header row so
    the user never needs to expand a strip just to adjust volume or pan.

    Parameters
    ----------
    parent    : Parent Tkinter frame (must exist before construction).
    track_key : GUI track key string, e.g. 'lead', 'bass'.
    color     : Accent hex colour for the header label and separator.
    """

    def __init__(
        self,
        parent:    tk.Frame,
        track_key: str,
        color:     str,
        solo_fn:     Optional[Callable] = None,  # (track_key, done_cb) -> None
        stop_fn:     Optional[Callable] = None,  # () -> None
        play_fn:     Optional[Callable] = None,  # (wav_path, start_sec) -> None
        get_pos_fn:  Optional[Callable] = None,  # () -> float
    ) -> None:
        self._track_key    = track_key
        self._color        = color
        self._collapsed    = True
        self._use_advanced = False          # True → advanced view is shown

        # Solo preview state
        self._solo_fn          = solo_fn
        self._stop_fn          = stop_fn
        self._play_fn          = play_fn
        self._get_pos_fn       = get_pos_fn
        self._solo_wav:    Optional[str]  = None
        self._solo_duration:   float      = 0.0
        self._is_solo_playing: bool       = False
        self._solo_peaks:  Optional[list] = None
        self._playhead_id                 = None
        self._solo_btn:    Optional[tk.Button] = None
        self._wave_canvas: Optional[tk.Canvas] = None

        self._outer = tk.Frame(parent, bg=S.BG2)
        self._outer.pack(fill='x', pady=1)

        self._build_header()
        self._build_content()
        self._content.pack_forget()         # starts collapsed

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        """
        Always-visible header row.

        Layout: [▶] TRACK_NAME  [gain━━━━━━] +0.0 dB  │  [pan━━] C  <summary>

        Gain and pan are placed here so they are accessible without expanding
        the strip — matching standard DAW channel-strip behaviour.
        """
        hdr = tk.Frame(self._outer, bg=S.BG3)
        hdr.pack(fill='x')

        # Collapse / expand toggle arrow
        self._arrow_var = tk.StringVar(value='▶')
        tk.Button(
            hdr,
            textvariable=self._arrow_var,
            command=self._toggle,
            font=S.FN_X,
            fg=self._color, bg=S.BG3,
            activeforeground=S.TXT_BRT, activebackground=S.BG3,
            bd=0, padx=4, pady=1,
            cursor='hand2',
            highlightthickness=0, relief='flat',
        ).pack(side='left')

        # Track name label — narrower than before to make room for fader
        tk.Label(
            hdr,
            text=self._track_key.upper(),
            font=S.FN_S, fg=self._color, bg=S.BG3,
            width=7, anchor='w',
        ).pack(side='left')

        # ── Gain fader (always visible) ───────────────────────────────────────
        _unity_step = int(_db_to_pos(0.0) * _GAIN_STEPS)   # = 800 at 0 dB
        self._gain_pos_var = tk.IntVar(value=_unity_step)
        _gain_sl = tk.Scale(
            hdr,
            variable=self._gain_pos_var,
            from_=0, to=_GAIN_STEPS, resolution=1, orient='horizontal',
            font=S.FN_X, fg=self._color, bg=S.BG3,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=130,
            showvalue=0,
            command=lambda _: self._update_gain_label(),
        )
        _gain_sl.pack(side='left', padx=2)
        _gain_sl.bind('<Double-Button-1>', lambda _: self._reset_gain())
        ToolTip(_gain_sl,
                'Track output volume in dB.\n'
                'Also written as MIDI CC7 (channel volume) in the FluidSynth path.\n\n'
                '−∞ = silence · 0 dB = unity (no change) · +6 dB = full boost\n'
                'Unity (0 dB) is at 80 % of slider travel.\n\n'
                'Double-click to reset to 0 dB.')
        self._gain_pos_var.trace_add('write', lambda *_: self._update_gain_label())

        # Numeric dB readout
        self._gain_lbl = tk.Label(hdr, text='+0.0 dB', font=S.FN_X,
                                   fg=S.TXT, bg=S.BG3, width=8)
        self._gain_lbl.pack(side='left')

        # Thin visual divider between gain and pan
        tk.Label(hdr, text='│', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG3).pack(side='left', padx=2)

        # ── Pan slider (always visible) ───────────────────────────────────────
        self._pan_var = tk.IntVar(value=0)
        _pan_sl = tk.Scale(
            hdr,
            variable=self._pan_var,
            from_=-63, to=63, orient='horizontal',
            font=S.FN_X, fg=self._color, bg=S.BG3,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=60,
            showvalue=0,
        )
        _pan_sl.pack(side='left', padx=2)
        _pan_sl.bind('<Double-Button-1>', lambda _: self._pan_var.set(0))
        ToolTip(_pan_sl, 'Stereo pan position — written as MIDI CC10 at track start.\n'
                         '0 = centre · −63 = full left · +63 = full right.\n'
                         'In Advanced mode the P grid gives per-step pan control.\n\n'
                         'Double-click to reset to centre.')
        self._pan_var.trace_add('write', lambda *_: self._update_pan_label())

        # Pan position text (C / L## / R##)
        self._pan_lbl = tk.Label(hdr, text='C', font=S.FN_X,
                                  fg=S.TXT, bg=S.BG3, width=4)
        self._pan_lbl.pack(side='left')

        # ── Solo preview button + waveform canvas ─────────────────────────────
        if self._solo_fn is not None:
            self._solo_btn_var = tk.StringVar(value='S')
            self._solo_btn = tk.Button(
                hdr,
                textvariable=self._solo_btn_var,
                command=self._on_solo_click,
                font=S.FN_X, fg=S.CYAN, bg=S.BG3,
                activeforeground=S.TXT_BRT, activebackground=S.BG3,
                bd=0, padx=4, pady=1, cursor='hand2',
                highlightthickness=0, relief='flat', width=3,
            )
            self._solo_btn.pack(side='left', padx=(8, 2))
            ToolTip(self._solo_btn,
                    'Solo — render this track alone and preview it.\n'
                    'S = no render yet  ·  ▶ = ready, click to play\n'
                    '■ = playing, click to stop\n'
                    'Click on the waveform to seek to any position.')

            self._wave_canvas = tk.Canvas(
                hdr, width=_WAVE_W, height=_WAVE_H,
                bg=S.BG_INPUT, highlightthickness=1,
                highlightbackground='#333',
            )
            self._wave_canvas.pack(side='left', padx=2)
            self._wave_canvas.bind('<Button-1>', self._on_canvas_click)
            ToolTip(self._wave_canvas,
                    'Solo waveform preview.\nClick anywhere to seek to that position.')

        # Live summary — shows only non-visible settings when collapsed.
        # Gain and pan are excluded here because they are always visible.
        self._summary_var = tk.StringVar(value='')
        tk.Label(
            hdr,
            textvariable=self._summary_var,
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG3,
            anchor='w',
        ).pack(side='left', fill='x', expand=True, padx=4)

    # ── Content ───────────────────────────────────────────────────────────────

    def _build_content(self) -> None:
        """
        Build the full expanded content panel.

        Structure
        ---------
        1. Transpose row.
        2. GROOVE section — Swing/Nudge, Vel min/max/Curve.
        3. HUMANIZE section — Vel jitter, Time jitter, Seed.
        4. Toggle button — [ADVANCED ▸] / [◂ SIMPLIFIED].

        Gain and pan have been moved to _build_header() and are no longer
        present here.
        """
        self._content = tk.Frame(self._outer, bg=S.BG2, padx=8, pady=4)

        # ── 1. Transpose row ──────────────────────────────────────────────────
        r_tr = tk.Frame(self._content, bg=S.BG2); r_tr.pack(fill='x', pady=1)
        tk.Label(r_tr, text='Transpose:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=11, anchor='w').pack(side='left')
        self._transpose_var = tk.IntVar(value=0)
        _tr_sl = tk.Scale(
            r_tr,
            variable=self._transpose_var,
            from_=-24, to=24, orient='horizontal',
            font=S.FN_X, fg=self._color, bg=S.BG2,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=160,
            showvalue=0,
            command=lambda _: self._update_summary(),
        )
        _tr_sl.pack(side='left', padx=2)
        ToolTip(_tr_sl, 'Semitone pitch shift applied to every note on this track.\n'
                        '−12 = one octave down · 0 = unchanged · +12 = one octave up.\n'
                        'Applied without recomposing the song.')
        self._transpose_lbl = tk.Label(r_tr, text='0 st', font=S.FN_X,
                                       fg=S.TXT, bg=S.BG2, width=6)
        self._transpose_lbl.pack(side='left')
        self._transpose_var.trace_add('write', lambda *_: self._transpose_lbl.configure(
            text=f'{self._transpose_var.get():+d} st'))
        _b12n = tk.Button(r_tr, text='-12', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG_BTN,
                  bd=0, padx=4, cursor='hand2',
                  command=lambda: self._transpose_var.set(-12))
        _b12n.pack(side='left', padx=2)
        ToolTip(_b12n, 'Jump to −12 st (one octave down).')
        _b0 = tk.Button(r_tr, text='0', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG_BTN,
                  bd=0, padx=4, cursor='hand2',
                  command=lambda: self._transpose_var.set(0))
        _b0.pack(side='left', padx=1)
        ToolTip(_b0, 'Reset transpose to 0 (no shift).')
        _b12p = tk.Button(r_tr, text='+12', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG_BTN,
                  bd=0, padx=4, cursor='hand2',
                  command=lambda: self._transpose_var.set(12))
        _b12p.pack(side='left', padx=2)
        ToolTip(_b12p, 'Jump to +12 st (one octave up).')

        # ── 2. View slot — contains _simple_frame or _adv_view.frame ─────────
        # Thin divider + "GROOVE" section title
        tk.Frame(self._content, bg=S.BG3, height=1).pack(fill='x', pady=(6, 2))
        tk.Label(self._content, text='GROOVE', font=S.FN_X, fg=S.TXT_DIM,
                 bg=S.BG2, anchor='w').pack(fill='x')

        self._view_slot = tk.Frame(self._content, bg=S.BG2)
        self._view_slot.pack(fill='x')

        # Simple Tier-1 controls (visible by default)
        self._simple_frame = tk.Frame(self._view_slot, bg=S.BG2)
        self._simple_frame.pack(fill='x')
        self._build_simple_view(self._simple_frame)

        # Advanced view (hidden by default)
        if _ADV_AVAILABLE:
            self._adv_view = AdvancedGrooveView(
                self._view_slot,
                track_key=self._track_key,
                color=self._color,
            )
            # _adv_view.frame is NOT packed yet — visible only in advanced mode
        else:
            self._adv_view = None

        # ── 3. HUMANIZE section ───────────────────────────────────────────────
        tk.Frame(self._content, bg=S.BG3, height=1).pack(fill='x', pady=(6, 2))
        tk.Label(self._content, text='HUMANIZE', font=S.FN_X, fg=S.TXT_DIM,
                 bg=S.BG2, anchor='w').pack(fill='x')

        r_vel_hum = tk.Frame(self._content, bg=S.BG2); r_vel_hum.pack(fill='x', pady=1)
        tk.Label(r_vel_hum, text='Vel jitter:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=10, anchor='w').pack(side='left')
        self._vel_hum_var = tk.IntVar(value=0)
        _vh_sl = tk.Scale(
            r_vel_hum,
            variable=self._vel_hum_var,
            from_=0, to=30, orient='horizontal',
            font=S.FN_X, fg=S.YELLOW, bg=S.BG2,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=100,
            showvalue=0,
        )
        _vh_sl.pack(side='left', padx=2)
        ToolTip(_vh_sl, 'Velocity humanisation: adds a random ±N velocity\n'
                        'to each note on every render.\n'
                        'Lock the Seed below to make the variation reproducible.\n'
                        '0 = off  ·  10 = subtle  ·  30 = expressive')
        self._vel_hum_lbl = tk.Label(r_vel_hum, text='±0', font=S.FN_X,
                                      fg=S.TXT, bg=S.BG2, width=4)
        self._vel_hum_lbl.pack(side='left')
        self._vel_hum_var.trace_add('write', lambda *_: self._vel_hum_lbl.configure(
            text=f'±{self._vel_hum_var.get()}'))

        tk.Label(r_vel_hum, text='Time:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=6, anchor='w').pack(side='left', padx=(8, 0))
        self._time_hum_var = tk.DoubleVar(value=0.0)
        _th_sl = tk.Scale(
            r_vel_hum,
            variable=self._time_hum_var,
            from_=0.0, to=20.0, resolution=0.5, orient='horizontal',
            font=S.FN_X, fg=S.YELLOW, bg=S.BG2,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=100,
            showvalue=0,
        )
        _th_sl.pack(side='left', padx=2)
        ToolTip(_th_sl, 'Timing humanisation: adds a random ±N ms offset\n'
                        'to each note on every render.\n'
                        'Lock the Seed below to make the variation reproducible.\n'
                        '0 = off  ·  5 ms = subtle  ·  20 ms = very loose')
        self._time_hum_lbl = tk.Label(r_vel_hum, text='±0 ms', font=S.FN_X,
                                       fg=S.TXT, bg=S.BG2, width=7)
        self._time_hum_lbl.pack(side='left')
        self._time_hum_var.trace_add('write', lambda *_: self._time_hum_lbl.configure(
            text=f'±{self._time_hum_var.get():.1f} ms'))

        r_seed = tk.Frame(self._content, bg=S.BG2); r_seed.pack(fill='x', pady=(1, 4))
        tk.Label(r_seed, text='Seed:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=6, anchor='w').pack(side='left')
        self._seed_var = tk.StringVar(value='')
        _seed_ent = tk.Entry(
            r_seed,
            textvariable=self._seed_var,
            font=S.FN_X, fg=S.TXT, bg=S.BG_INPUT,
            insertbackground=self._color, width=10,
        )
        _seed_ent.pack(side='left', padx=2)
        ToolTip(_seed_ent, 'Humanisation seed — same integer = identical Vel and\n'
                           'Timing variation every render (reproducible groove).\n'
                           'Leave blank for a fresh random variation each time.\n'
                           'Use [Roll] to generate and lock a random seed.')
        tk.Label(r_seed, text='(blank = new each render)', font=S.FN_X,
                 fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=4)
        _roll_btn = tk.Button(r_seed, text='Roll', font=S.FN_X, fg=S.YELLOW, bg=S.BG_BTN,
                  bd=0, padx=6, cursor='hand2',
                  activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
                  command=self._roll_seed)
        _roll_btn.pack(side='left', padx=2)
        ToolTip(_roll_btn, 'Generate a random seed and lock it.\n'
                           'The same seed gives identical humanisation every render.')
        _clear_btn = tk.Button(r_seed, text='Clear', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG_BTN,
                  bd=0, padx=6, cursor='hand2',
                  activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
                  command=lambda: self._seed_var.set(''))
        _clear_btn.pack(side='left', padx=2)
        ToolTip(_clear_btn, 'Remove the locked seed — humanisation will be\n'
                            'randomly different on every render.')

        # ── 4. ADVANCED / SIMPLIFIED toggle button ────────────────────────────
        tk.Frame(self._content, bg=S.BG3, height=1).pack(fill='x', pady=(4, 2))
        toggle_row = tk.Frame(self._content, bg=S.BG2)
        toggle_row.pack(fill='x', pady=(0, 2))

        self._adv_btn_text = tk.StringVar(value='ADVANCED  ▸')
        self._adv_btn = tk.Button(
            toggle_row,
            textvariable=self._adv_btn_text,
            font=S.FN_X,
            fg=S.YELLOW, bg=S.BG_BTN,
            activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
            bd=0, padx=8, pady=3,
            cursor='hand2' if _ADV_AVAILABLE else 'arrow',
            command=self._toggle_advanced,
            state='normal' if _ADV_AVAILABLE else 'disabled',
        )
        self._adv_btn.pack(side='right')
        ToolTip(self._adv_btn,
                'Toggle Advanced grid mode.\n\n'
                'ADVANCED: replaces the five simplified Tier-1 controls with\n'
                '  four 16-step grids for doctoral-level per-step control:\n'
                '  V  velocity multiplier · T  timing offset (ms)\n'
                '  P  per-step pan        · E  per-step expression (CC11)\n\n'
                'SIMPLIFIED: converts the grids back to the nearest named\n'
                '  preset (with a warning if the conversion loses precision).\n\n'
                'Transpose, Gain and Pan remain visible in both modes.')

        if not _ADV_AVAILABLE:
            tk.Label(toggle_row, text='(advanced view unavailable)',
                     font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='right', padx=6)

        self._update_summary()

    def _build_simple_view(self, parent: tk.Frame) -> None:
        """
        Build the simplified groove controls inside *parent*.

        Creates Swing/Nudge, Vel min/max/Curve rows.
        Gain and Pan have been moved to the header; Transpose is in the
        persistent row above the view slot.
        """
        # Swing + Nudge
        r_sw = tk.Frame(parent, bg=S.BG2); r_sw.pack(fill='x', pady=1)
        tk.Label(r_sw, text='Swing:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=7, anchor='w').pack(side='left')
        self._swing_var = tk.DoubleVar(value=50.0)
        _sw_sl = tk.Scale(
            r_sw,
            variable=self._swing_var,
            from_=50.0, to=66.0, resolution=0.5, orient='horizontal',
            font=S.FN_X, fg=self._color, bg=S.BG2,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=100,
            showvalue=0,
            command=lambda _: self._update_summary(),
        )
        _sw_sl.pack(side='left', padx=2)
        ToolTip(_sw_sl, 'Off-beat 16th-note swing delay.\n'
                        '50 % = perfectly straight (no swing).\n'
                        '66 % = full triplet shuffle feel.\n'
                        'In Advanced mode the T grid replaces this control.')
        self._swing_lbl = tk.Label(r_sw, text='50.0 %', font=S.FN_X,
                                    fg=S.TXT, bg=S.BG2, width=7)
        self._swing_lbl.pack(side='left')
        self._swing_var.trace_add('write', lambda *_: self._swing_lbl.configure(
            text=f'{self._swing_var.get():.1f} %'))

        tk.Label(r_sw, text='Nudge:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=7, anchor='w').pack(side='left', padx=(8, 0))
        self._nudge_var = tk.DoubleVar(value=0.0)
        _nudge_sb = tk.Spinbox(
            r_sw,
            textvariable=self._nudge_var,
            from_=-50.0, to=50.0, increment=1.0, format='%.1f',
            font=S.FN_X, fg=S.TXT, bg=S.BG_INPUT,
            insertbackground=self._color, width=6,
            command=self._update_summary,
        )
        _nudge_sb.pack(side='left', padx=2)
        ToolTip(_nudge_sb, 'Fixed timing offset added to every note on this track.\n'
                           'Negative = push ahead of the grid (tight / early).\n'
                           'Positive = drag behind the grid (lazy / late).\n'
                           'In Advanced mode the T grid replaces this control.')
        tk.Label(r_sw, text='ms', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left')

        # Vel min / max / curve
        r_vel = tk.Frame(parent, bg=S.BG2); r_vel.pack(fill='x', pady=1)
        tk.Label(r_vel, text='Vel min:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=8, anchor='w').pack(side='left')
        self._vel_min_var = tk.IntVar(value=1)
        _vmin_sb = tk.Spinbox(
            r_vel,
            textvariable=self._vel_min_var,
            from_=1, to=126, increment=1,
            font=S.FN_X, fg=S.TXT, bg=S.BG_INPUT,
            insertbackground=self._color, width=4,
            command=self._update_summary,
        )
        _vmin_sb.pack(side='left', padx=2)
        ToolTip(_vmin_sb, 'Velocity floor (1–126).\n'
                          'All notes are rescaled so the quietest note plays at this level.')
        tk.Label(r_vel, text='max:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=(4, 0))
        self._vel_max_var = tk.IntVar(value=127)
        _vmax_sb = tk.Spinbox(
            r_vel,
            textvariable=self._vel_max_var,
            from_=2, to=127, increment=1,
            font=S.FN_X, fg=S.TXT, bg=S.BG_INPUT,
            insertbackground=self._color, width=4,
            command=self._update_summary,
        )
        _vmax_sb.pack(side='left', padx=2)
        ToolTip(_vmax_sb, 'Velocity ceiling (2–127).\n'
                          'All notes are rescaled so the loudest note plays at this level.')
        tk.Label(r_vel, text='Curve:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=6, anchor='w').pack(side='left', padx=(8, 0))
        self._curve_var = tk.StringVar(value='flat')
        _curve_cb = ttk.Combobox(
            r_vel,
            textvariable=self._curve_var,
            values=VEL_CURVES, state='readonly',
            font=S.FN_X, width=14,
        )
        _curve_cb.pack(side='left', padx=2)
        ToolTip(_curve_cb, 'Velocity accent pattern across the 4/4 bar.\n'
                           '  flat        = no accents (uniform loudness)\n'
                           '  accent_1    = beat 1 louder (+12 %)\n'
                           '  accent_1_3  = beats 1 & 3 louder (+10 %)\n'
                           '  crescendo   = builds from 80 % to 100 %\n'
                           '  decrescendo = fades from 100 % to 80 %\n'
                           'In Advanced mode the V grid replaces this control.')
        self._curve_var.trace_add('write', lambda *_: self._update_summary())

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, s: TrackGrooveSettings) -> None:
        """
        Populate all widgets from a TrackGrooveSettings instance.

        If *s* carries advanced grid data (``s.use_advanced=True``) the view
        switches to advanced mode and loads the grids directly.
        """
        # Gain and pan are now in the header — load them first.
        _clamped_db = max(_GAIN_MIN_DB, min(_GAIN_MAX_DB, s.gain_db))
        self._gain_pos_var.set(int(_db_to_pos(_clamped_db) * _GAIN_STEPS))
        self._pan_var.set(max(-63, min(63, s.pan)))

        # Transpose (always loaded)
        self._transpose_var.set(s.transpose_st)

        # Tier-2 fields (always loaded)
        self._vel_hum_var.set(max(0, min(30, s.vel_humanize)))
        self._time_hum_var.set(max(0.0, min(20.0, s.timing_humanize_ms)))
        self._seed_var.set(str(s.seed) if s.seed is not None else '')

        # Simple Tier-1 fields (always updated so switching back to simple works)
        self._swing_var.set(max(50.0, min(66.0, s.swing_pct)))
        self._nudge_var.set(max(-50.0, min(50.0, s.timing_nudge_ms)))
        self._vel_min_var.set(max(1, min(126, s.vel_min)))
        self._vel_max_var.set(max(2, min(127, s.vel_max)))
        self._curve_var.set(s.vel_curve if s.vel_curve in VEL_CURVES else 'flat')

        if s.use_advanced and _ADV_AVAILABLE and self._adv_view is not None:
            # Switch to advanced mode and load the grid data.
            self._adv_view.load_from_simple(s)
            if not self._use_advanced:
                self._simple_frame.pack_forget()
                self._adv_view.frame.pack(fill='x')
                self._use_advanced = True
                self._adv_btn_text.set('◂  SIMPLIFIED')
                self._adv_btn.configure(fg=S.TXT_DIM)
        else:
            # Ensure simple mode is visible.
            if self._use_advanced:
                if self._adv_view is not None:
                    self._adv_view.frame.pack_forget()
                self._simple_frame.pack(fill='x')
                self._use_advanced = False
                self._adv_btn_text.set('ADVANCED  ▸')
                self._adv_btn.configure(fg=S.YELLOW)

        self._update_summary()

    def get_settings(self) -> TrackGrooveSettings:
        """
        Read all widgets and return a TrackGrooveSettings instance.

        In advanced mode the four grid arrays are included and
        ``use_advanced=True`` is set so GrooveProcessor uses them.
        """
        seed: Optional[int] = None
        if self._seed_var.get().strip().isdigit():
            seed = int(self._seed_var.get().strip())

        # Header fields (gain and pan)
        gain = _pos_to_db(self._gain_pos_var.get() / _GAIN_STEPS)
        pan  = int(self._pan_var.get())

        # Persistent fields
        transpose = int(self._transpose_var.get())

        # Tier-2 fields
        vel_hum  = int(self._vel_hum_var.get())
        time_hum = float(self._time_hum_var.get())

        if self._use_advanced and self._adv_view is not None:
            # Build a base with the persistent + Tier-2 values, then ask the
            # advanced view to fill in the grid data and simplified fallbacks.
            base = TrackGrooveSettings(
                transpose_st       = transpose,
                gain_db            = gain,
                vel_min            = max(1, min(126, int(self._vel_min_var.get()))),
                vel_max            = max(2, min(127, int(self._vel_max_var.get()))),
                vel_humanize       = vel_hum,
                timing_humanize_ms = time_hum,
                seed               = seed,
            )
            settings, _lossless, _warning = self._adv_view.to_groove_settings(base)
            return settings

        # Simple mode: read all Tier-1 widget values directly.
        return TrackGrooveSettings(
            transpose_st       = transpose,
            vel_min            = max(1, min(126, int(self._vel_min_var.get()))),
            vel_max            = max(2, min(127, int(self._vel_max_var.get()))),
            vel_curve          = self._curve_var.get(),
            swing_pct          = float(self._swing_var.get()),
            timing_nudge_ms    = float(self._nudge_var.get()),
            gain_db            = gain,
            pan                = pan,
            vel_humanize       = vel_hum,
            timing_humanize_ms = time_hum,
            seed               = seed,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _toggle(self) -> None:
        """Expand or collapse the content panel."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._content.pack_forget()
            self._arrow_var.set('▶')
        else:
            self._content.pack(fill='x')
            self._arrow_var.set('▼')

    def _toggle_advanced(self) -> None:
        """
        Switch between Simplified and Advanced views.

        Simple → Advanced
            Reads the current simplified settings and expands them into the
            four grids so the user can see and edit the underlying data.

        Advanced → Simple
            Converts the four grids back to the nearest named preset.
            Shows a confirmation dialog if the conversion is not lossless.
        """
        if self._adv_view is None:
            return

        if not self._use_advanced:
            # ── Simple → Advanced ─────────────────────────────────────────────
            current = self.get_settings()       # reads simple vars before flag flips
            self._adv_view.load_from_simple(current)

            self._simple_frame.pack_forget()
            self._adv_view.frame.pack(fill='x')
            self._use_advanced = True
            self._adv_btn_text.set('◂  SIMPLIFIED')
            self._adv_btn.configure(fg=S.TXT_DIM)

        else:
            # ── Advanced → Simple ─────────────────────────────────────────────
            # Build the base settings (persistent + Tier 2 only) for conversion.
            seed: Optional[int] = None
            if self._seed_var.get().strip().isdigit():
                seed = int(self._seed_var.get().strip())
            base = TrackGrooveSettings(
                transpose_st       = int(self._transpose_var.get()),
                gain_db            = _pos_to_db(self._gain_pos_var.get() / _GAIN_STEPS),
                vel_min            = max(1, min(126, int(self._vel_min_var.get()))),
                vel_max            = max(2, min(127, int(self._vel_max_var.get()))),
                swing_pct          = float(self._swing_var.get()),
                vel_humanize       = int(self._vel_hum_var.get()),
                timing_humanize_ms = float(self._time_hum_var.get()),
                seed               = seed,
            )
            adv_settings, lossless, warning = self._adv_view.to_groove_settings(base)

            if not lossless:
                msg = (
                    'Some grid settings cannot be represented exactly in Simplified '
                    'mode — the nearest preset values will be loaded.\n\n'
                    f'{warning}\n\n'
                    'Continue switching to Simplified?'
                )
                if not messagebox.askyesno(
                    'Loss of Precision',
                    msg,
                    parent=self._outer,
                ):
                    return  # user cancelled — stay in advanced mode

            # Apply simplified approximation back into the simple controls.
            self._curve_var.set(adv_settings.vel_curve)
            self._nudge_var.set(adv_settings.timing_nudge_ms)
            self._pan_var.set(adv_settings.pan)

            self._adv_view.frame.pack_forget()
            self._simple_frame.pack(fill='x')
            self._use_advanced = False
            self._adv_btn_text.set('ADVANCED  ▸')
            self._adv_btn.configure(fg=S.YELLOW)

        self._update_summary()

    def _roll_seed(self) -> None:
        """Generate a random seed and lock it."""
        self._seed_var.set(str(random.randint(1, 999_999)))

    def _update_gain_label(self) -> None:
        """Refresh the numeric dB readout next to the gain slider."""
        db = _pos_to_db(self._gain_pos_var.get() / _GAIN_STEPS)
        if db <= _GAIN_INF_FLOOR:
            self._gain_lbl.configure(text='-∞ dB')
        else:
            self._gain_lbl.configure(text=f'{db:+.1f} dB')
        self._update_summary()

    def _reset_gain(self) -> None:
        """Reset the gain fader to 0 dB (unity) on double-click."""
        self._gain_pos_var.set(int(_db_to_pos(0.0) * _GAIN_STEPS))

    def _update_summary(self) -> None:
        """
        Refresh the one-line summary shown in the collapsed header.

        Gain and pan are excluded from the summary because they are always
        visible in the header row — no need to duplicate them here.
        """
        tr = self._transpose_var.get()
        parts = []
        if self._use_advanced:
            parts.append('[ADV]')
        if tr != 0:
            parts.append(f'{tr:+d}st')
        try:
            vlo = self._vel_min_var.get()
            vhi = self._vel_max_var.get()
            sw  = self._swing_var.get()
            if not self._use_advanced:
                if vlo != 1 or vhi != 127:
                    parts.append(f'v{vlo}-{vhi}')
                if abs(sw - 50.0) > 0.1:
                    parts.append(f'sw{sw:.0f}%')
        except Exception:
            pass
        self._summary_var.set('  '.join(parts) if parts else '')

    def _update_pan_label(self) -> None:
        """Show L / C / R text next to the pan slider."""
        p = self._pan_var.get()
        if p < -5:
            self._pan_lbl.configure(text=f'L{abs(p)}')
        elif p > 5:
            self._pan_lbl.configure(text=f'R{p}')
        else:
            self._pan_lbl.configure(text='C')

    # ── Solo preview ──────────────────────────────────────────────────────────

    def _on_solo_click(self) -> None:
        """Toggle solo playback for this track."""
        if self._is_solo_playing:
            if self._stop_fn:
                self._stop_fn()
            self._set_solo_state('idle')
        elif self._solo_wav:
            if self._play_fn:
                self._play_fn(self._solo_wav, 0.0)
            self._set_solo_state('playing')
            self._start_playhead()
        else:
            self._set_solo_state('rendering')
            if self._solo_fn:
                self._solo_fn(self._track_key, self._on_solo_ready)

    def _on_solo_ready(
        self,
        wav_path: Optional[str],
        duration_sec: float,
        peaks: Optional[list],
        autoplay: bool = True,
    ) -> None:
        """Called on the main thread by MixerPanel when the background render finishes."""
        if wav_path:
            self._solo_wav      = wav_path
            self._solo_duration = duration_sec
            self._solo_peaks    = peaks
            self._draw_waveform()
            if autoplay:
                if self._play_fn:
                    self._play_fn(wav_path, 0.0)
                self._set_solo_state('playing')
                self._start_playhead()
            else:
                self._set_solo_state('idle')  # shows ▶, ready but not playing
        else:
            self._set_solo_state('idle')

    def set_solo_stopped(self) -> None:
        """Called by MixerPanel when another strip takes over playback."""
        self._set_solo_state('idle')

    def reset_solo(self) -> None:
        """Clear cached solo render and return to the un-rendered S state."""
        if self._stop_fn and self._is_solo_playing:
            self._stop_fn()
        self._solo_wav      = None
        self._solo_duration = 0.0
        self._solo_peaks    = None
        self._set_solo_state('idle')

    def _set_solo_state(self, state: str) -> None:
        """Update S button appearance and internal playing flag."""
        if self._solo_btn is None:
            return
        if state == 'rendering':
            self._is_solo_playing = False
            self._solo_btn_var.set('···')
            self._solo_btn.configure(state='disabled', cursor='arrow', fg=S.TXT_DIM)
        elif state == 'playing':
            self._is_solo_playing = True
            self._solo_btn_var.set('■')
            self._solo_btn.configure(state='normal', cursor='hand2', fg=S.YELLOW)
        else:  # idle
            self._is_solo_playing = False
            self._solo_btn_var.set('▶' if self._solo_wav else 'S')
            self._solo_btn.configure(state='normal', cursor='hand2', fg=S.CYAN)
        if state != 'playing':
            if self._playhead_id is not None:
                try:
                    self._outer.after_cancel(self._playhead_id)
                except Exception:
                    pass
                self._playhead_id = None
            self._draw_waveform()

    def _draw_waveform(self) -> None:
        """Paint the peak waveform onto the canvas from pre-computed peaks."""
        if self._wave_canvas is None:
            return
        self._wave_canvas.delete('all')
        if not self._solo_peaks:
            return
        mid_y = _WAVE_H // 2
        self._wave_canvas.create_line(0, mid_y, _WAVE_W, mid_y, fill='#2a2a2a', width=1)
        for x, p in enumerate(self._solo_peaks):
            h = max(1, int(p * mid_y * 0.92))
            self._wave_canvas.create_line(
                x, mid_y - h, x, mid_y + h,
                fill=self._color, width=1,
            )

    def _start_playhead(self) -> None:
        """Cancel any existing poll and start a fresh one."""
        if self._playhead_id is not None:
            try:
                self._outer.after_cancel(self._playhead_id)
            except Exception:
                pass
            self._playhead_id = None
        self._poll_playhead()

    def _poll_playhead(self) -> None:
        """Redraw waveform + playhead cursor every 100 ms while playing."""
        if not self._is_solo_playing or self._wave_canvas is None:
            return
        if self._get_pos_fn and self._solo_duration > 0:
            pos = self._get_pos_fn()
            if pos >= self._solo_duration:
                self._set_solo_state('idle')
                return
            ratio = min(1.0, pos / self._solo_duration)
            x = int(ratio * _WAVE_W)
            self._draw_waveform()
            self._wave_canvas.create_line(x, 0, x, _WAVE_H, fill='white', width=1)
        self._playhead_id = self._outer.after(100, self._poll_playhead)

    def _on_canvas_click(self, event: tk.Event) -> None:
        """Seek solo playback to the clicked position in the waveform."""
        if self._solo_wav is None or self._solo_duration <= 0:
            return
        w = self._wave_canvas.winfo_width() or _WAVE_W
        ratio    = max(0.0, min(1.0, event.x / w))
        seek_sec = ratio * self._solo_duration
        if self._play_fn:
            self._play_fn(self._solo_wav, seek_sec)
        if not self._is_solo_playing:
            self._set_solo_state('playing')
        self._start_playhead()
