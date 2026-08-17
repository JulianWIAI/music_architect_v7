"""
src/gui/mixer_strip.py
───────────────────────
A collapsible per-track mixer strip widget.

Layout when expanded
────────────────────
  ─── PERSISTENT (both modes) ──────────────────────────────────────────
  Transpose : slider  −24 … +24 st   [−12] [0] [+12]
  Gain      : slider  −6.0 … +6.0 dB

  ─── VIEW SLOT (mutually exclusive) ───────────────────────────────────
  SIMPLIFIED:
    Swing %   : slider  50.0 … 66.0 %     Nudge : spinbox  −50 … +50 ms
    Vel min   : spinbox 1 … 127           Vel max: spinbox 1 … 127
    Vel curve : combobox (flat / accent_1 / accent_1_3 / crescendo / decrescendo)
    Pan       : slider  −63 … +63
  ADVANCED:
    Notebook tabs: V | T | P | E  (16-step grids per tab)
    [Export Grid JSON]

  ─── TIER 2: HUMANISE (always visible) ───────────────────────────────
  Vel jitter : slider  0 … 30            Time jitter: slider 0 … 20 ms
  Seed       : entry field + [Roll] button

  ─── TOGGLE ──────────────────────────────────────────────────────────
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
from typing import Optional

from src.gui.styles import S
from src.gui.tooltips import ToolTip
from src.midi.groove_settings import TrackGrooveSettings, VEL_CURVES

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
    ) -> None:
        self._track_key    = track_key
        self._color        = color
        self._collapsed    = True
        self._use_advanced = False          # True → advanced view is shown

        self._outer = tk.Frame(parent, bg=S.BG2)
        self._outer.pack(fill='x', pady=1)

        self._build_header()
        self._build_content()
        self._content.pack_forget()         # starts collapsed

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        """Compact always-visible row: arrow toggle + track name + live summary."""
        hdr = tk.Frame(self._outer, bg=S.BG3)
        hdr.pack(fill='x')

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

        tk.Label(
            hdr,
            text=self._track_key.upper(),
            font=S.FN_S, fg=self._color, bg=S.BG3,
            width=11, anchor='w',
        ).pack(side='left')

        # Live summary: shows only changed values (updated on any Tier-1 change).
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
        1. Persistent row  — Transpose + Gain (both modes).
        2. View slot       — _simple_frame (default) or _adv_view.frame.
        3. Tier-2 section  — Vel jitter, Time jitter, Seed (both modes).
        4. Toggle button   — [ADVANCED ▸] / [◂ SIMPLIFIED].
        """
        self._content = tk.Frame(self._outer, bg=S.BG2, padx=8, pady=4)

        # ── 1. Persistent rows (Transpose + Gain) ────────────────────────────
        self._sep_label(self._content, '─── TIER 1: DETERMINISTIC ───────────────')

        # Transpose row
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

        # Gain row (CC7 — track-level, no per-step equivalent in grid mode)
        r_gain = tk.Frame(self._content, bg=S.BG2); r_gain.pack(fill='x', pady=1)
        tk.Label(r_gain, text='Gain (CC7):', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=11, anchor='w').pack(side='left')
        self._gain_var = tk.DoubleVar(value=0.0)
        _gain_sl = tk.Scale(
            r_gain,
            variable=self._gain_var,
            from_=-6.0, to=6.0, resolution=0.5, orient='horizontal',
            font=S.FN_X, fg=self._color, bg=S.BG2,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=120,
            showvalue=0,
            command=lambda _: self._update_summary(),
        )
        _gain_sl.pack(side='left', padx=2)
        ToolTip(_gain_sl, 'Track output volume in dB — written as MIDI CC7 (channel volume)\n'
                          'at the very start of the track.\n'
                          '0 dB = nominal (CC7=100).  Range: −6 to +6 dB.')
        self._gain_lbl = tk.Label(r_gain, text='0.0 dB', font=S.FN_X,
                                   fg=S.TXT, bg=S.BG2, width=8)
        self._gain_lbl.pack(side='left')
        self._gain_var.trace_add('write', lambda *_: self._gain_lbl.configure(
            text=f'{self._gain_var.get():+.1f} dB'))
        tk.Label(r_gain, text='(applies in both Simple and Advanced modes)',
                 font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=8)

        # ── 2. View slot — contains _simple_frame or _adv_view.frame ─────────
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

        # ── 3. Tier-2 section (always visible) ───────────────────────────────
        self._sep_label(self._content, '─── TIER 2: HUMANISE (seeded) ──────────')

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
        ToolTip(_vh_sl, 'Tier-2 velocity humanisation: adds a random ±N velocity\n'
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
        ToolTip(_th_sl, 'Tier-2 timing humanisation: adds a random ±N ms offset\n'
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
                'Transpose and Gain remain visible in both modes.')

        if not _ADV_AVAILABLE:
            tk.Label(toggle_row, text='(advanced view unavailable)',
                     font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='right', padx=6)

        self._update_summary()

    def _build_simple_view(self, parent: tk.Frame) -> None:
        """
        Build the simplified Tier-1 controls inside *parent*.

        Creates the Swing/Nudge, Vel min/max/Curve, and Pan rows.
        Transpose and Gain are in the persistent section above the view slot.
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

        # Pan
        r_pan = tk.Frame(parent, bg=S.BG2); r_pan.pack(fill='x', pady=(1, 4))
        tk.Label(r_pan, text='Pan:', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=5, anchor='w').pack(side='left')
        self._pan_var = tk.IntVar(value=0)
        _pan_sl = tk.Scale(
            r_pan,
            variable=self._pan_var,
            from_=-63, to=63, orient='horizontal',
            font=S.FN_X, fg=self._color, bg=S.BG2,
            troughcolor=S.BG_INPUT, highlightthickness=0, length=120,
            showvalue=0,
        )
        _pan_sl.pack(side='left', padx=2)
        ToolTip(_pan_sl, 'Stereo pan position — written as MIDI CC10 at track start.\n'
                         '0 = centre · −63 = full left · +63 = full right.\n'
                         'In Advanced mode the P grid gives per-step pan control.')
        self._pan_lbl = tk.Label(r_pan, text='C', font=S.FN_X,
                                  fg=S.TXT, bg=S.BG2, width=5)
        self._pan_lbl.pack(side='left')
        self._pan_var.trace_add('write', lambda *_: self._update_pan_label())

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, s: TrackGrooveSettings) -> None:
        """
        Populate all widgets from a TrackGrooveSettings instance.

        If *s* carries advanced grid data (``s.use_advanced=True``) the view
        switches to advanced mode and loads the grids directly.
        """
        # Persistent fields (always loaded regardless of mode)
        self._transpose_var.set(s.transpose_st)
        self._gain_var.set(max(-6.0, min(6.0, s.gain_db)))

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
        self._pan_var.set(max(-63, min(63, s.pan)))

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

        # Persistent fields
        transpose = int(self._transpose_var.get())
        gain      = float(self._gain_var.get())

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
            pan                = int(self._pan_var.get()),
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
            # Build the base settings (persistent + Tier 2 only) for the conversion.
            seed: Optional[int] = None
            if self._seed_var.get().strip().isdigit():
                seed = int(self._seed_var.get().strip())
            base = TrackGrooveSettings(
                transpose_st       = int(self._transpose_var.get()),
                gain_db            = float(self._gain_var.get()),
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

    def _update_summary(self) -> None:
        """Refresh the one-line summary shown in the collapsed header."""
        tr  = self._transpose_var.get()
        g   = self._gain_var.get()
        parts = []
        if self._use_advanced:
            parts.append('[ADV]')
        if tr != 0:
            parts.append(f'{tr:+d}st')
        if abs(g) > 0.1:
            parts.append(f'{g:+.1f}dB')
        # Only read simple-mode vars if the widgets exist (they always do —
        # the vars persist even when the frame is hidden).
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

    @staticmethod
    def _sep_label(parent: tk.Frame, text: str) -> None:
        """Draw a dimmed separator label styled like a section divider."""
        tk.Label(
            parent,
            text=text,
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor='w',
        ).pack(fill='x', pady=(4, 1))
