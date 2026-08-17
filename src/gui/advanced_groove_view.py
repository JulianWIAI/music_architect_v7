"""
src/gui/advanced_groove_view.py
────────────────────────────────
Advanced per-step grid editor for a single track.

Replaces the simplified Tier-1 controls (vel_curve, swing, nudge, pan) with
four 16-step grids that expose the underlying data directly:

  V — Velocity multiplier per 16th-note step (0.0–2.0, neutral 1.0).
      Replaces the vel_curve combobox and vel_min/vel_max spinboxes.

  T — Timing offset per step in ms (−50 to +50, neutral 0.0).
      Replaces swing_pct and timing_nudge_ms together.

  P — Pan position per step (−63 L to +63 R, neutral 0).
      Per-step stereo placement; no simplified equivalent.

  E — Expression (MIDI CC11) per step (0–127, neutral 64).
      Per-step dynamic envelope; no simplified equivalent.

Gain (CC7, constant per track) and Transpose stay in the persistent row
outside this view because they have no meaningful per-step equivalents.

[Export Grid JSON] writes the current V / T / P / E arrays for this track
to a user-chosen file for corpus analysis or third-party tool input.

Cross-platform: pure Tkinter + tkinter.filedialog.  No platform-specific code.

Public API::

    view = AdvancedGrooveView(parent, track_key='lead', color=S.CYAN)
    view.load_from_simple(track_groove_settings)
    settings, lossless, warning = view.to_groove_settings(base_settings)
    data = view.get_export_data()   # {'track':..., 'V':[...], 'T':[...], ...}
    view.frame.pack(fill='x')       # caller controls visibility
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Tuple

from src.gui.styles import S
from src.gui.step_grid_editor import StepGridEditor
from src.gui.tooltips import ToolTip
from src.midi.groove_settings import TrackGrooveSettings
from src.midi.grid_to_preset import VEL_CURVE_GRIDS, grids_to_simple


class AdvancedGrooveView:
    """
    Four-tab grid editor (V / T / P / E) that replaces the Tier-1 simplified
    controls when the user enables Advanced mode on a TrackMixerStrip.

    Parameters
    ----------
    parent    : Tkinter parent frame (caller controls visibility of self.frame).
    track_key : GUI track key (e.g. 'lead') — used in exported file names.
    color     : Accent colour inherited from the parent TrackMixerStrip.
    """

    def __init__(
        self,
        parent:    tk.Frame,
        track_key: str,
        color:     str,
    ) -> None:
        self._track_key = track_key
        self._color     = color

        self._frame = tk.Frame(parent, bg=S.BG2)
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the V / T / P / E notebook and the Export button."""

        # ttk.Notebook gives four tabs without consuming much vertical space.
        nb = ttk.Notebook(self._frame)
        nb.pack(fill='both', expand=True, pady=(0, 4))

        # ── V tab: velocity multiplier per step ───────────────────────────────
        v_tab = tk.Frame(nb, bg=S.BG2, padx=4, pady=2)
        nb.add(v_tab, text='  V  ')
        tk.Label(
            v_tab,
            text='Velocity multiplier per step  (1.0 = unchanged, Ctrl+click resets)',
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w',
        ).pack(fill='x')
        self._v_grid = StepGridEditor(
            v_tab,
            from_=0.0, to=2.0, neutral=1.0, resolution=0.01,
            label='V', unit='×', color=self._color,
        )
        self._v_grid.frame.pack(fill='x')

        # ── T tab: timing offset per step ─────────────────────────────────────
        t_tab = tk.Frame(nb, bg=S.BG2, padx=4, pady=2)
        nb.add(t_tab, text='  T  ')
        tk.Label(
            t_tab,
            text='Timing offset per step in ms  (0.0 = on-grid, Ctrl+click resets)',
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w',
        ).pack(fill='x')
        self._t_grid = StepGridEditor(
            t_tab,
            from_=-50.0, to=50.0, neutral=0.0, resolution=0.5,
            label='T', unit='ms', color=S.YELLOW,
        )
        self._t_grid.frame.pack(fill='x')

        # ── P tab: pan position per step ──────────────────────────────────────
        p_tab = tk.Frame(nb, bg=S.BG2, padx=4, pady=2)
        nb.add(p_tab, text='  P  ')
        tk.Label(
            p_tab,
            text='Pan per step  (0 = centre, −63 = full-L, +63 = full-R, Ctrl+click resets)',
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w',
        ).pack(fill='x')
        self._p_grid = StepGridEditor(
            p_tab,
            from_=-63, to=63, neutral=0, resolution=1,
            label='P', unit='', color=S.CYAN,
        )
        self._p_grid.frame.pack(fill='x')

        # ── E tab: expression (CC11) per step ─────────────────────────────────
        e_tab = tk.Frame(nb, bg=S.BG2, padx=4, pady=2)
        nb.add(e_tab, text='  E  ')
        tk.Label(
            e_tab,
            text='Expression CC11 per step  (64 = neutral, 127 = full, Ctrl+click resets)',
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w',
        ).pack(fill='x')
        self._e_grid = StepGridEditor(
            e_tab,
            from_=0, to=127, neutral=64, resolution=1,
            label='E', unit='', color=S.GREEN,
        )
        self._e_grid.frame.pack(fill='x')

        # ── Export button ─────────────────────────────────────────────────────
        _export_btn = tk.Button(
            self._frame,
            text='Export Grid JSON',
            font=S.FN_X,
            fg=self._color,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0, padx=8, pady=3,
            cursor='hand2',
            command=self._export_json,
        )
        _export_btn.pack(anchor='e', padx=4, pady=(0, 2))
        ToolTip(_export_btn,
                'Export V, T, P and E grids for this track as a JSON file.\n\n'
                'V  — velocity multipliers  (16 floats, neutral = 1.0)\n'
                'T  — timing offsets in ms  (16 floats, neutral = 0.0)\n'
                'P  — pan positions         (16 ints,   neutral = 0)\n'
                'E  — expression CC11       (16 ints,   neutral = 64)\n\n'
                'Use the exported file for corpus analysis, machine learning,\n'
                'or as input to another researcher\'s tool.')

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def frame(self) -> tk.Frame:
        """Outer container frame — caller packs/forgets this to toggle visibility."""
        return self._frame

    def load_from_simple(self, s: TrackGrooveSettings) -> None:
        """
        Expand simplified Tier-1 settings into the four grids.

        V ← vel_curve lookup table (from VEL_CURVE_GRIDS).
        T ← per-step offsets derived from swing_pct and timing_nudge_ms.
             Off-beat steps (odd indices) get the swing delay in ms on top
             of the uniform nudge.  The swing-to-ms conversion uses 120 BPM
             as a reference; the stored T values are in ms and applied as-is
             by GrooveProcessor regardless of actual BPM.
        P ← all steps filled with the constant ``s.pan`` value.
        E ← all steps at neutral (64); no simplified equivalent.

        If *s* already carries raw grid data (``s.use_advanced=True``) those
        arrays are loaded directly without conversion.
        """
        # V grid
        if s.use_advanced and s.v_grid is not None:
            self._v_grid.set_values(s.v_grid)
        else:
            curve = s.vel_curve if s.vel_curve in VEL_CURVE_GRIDS else 'flat'
            self._v_grid.set_values(VEL_CURVE_GRIDS[curve])

        # T grid — convert swing_pct + nudge_ms to per-step ms offsets.
        if s.use_advanced and s.t_grid is not None:
            self._t_grid.set_values(s.t_grid)
        else:
            nudge = s.timing_nudge_ms
            # Use 120 BPM as reference tempo: 16th note = 125 ms.
            # swing_extra = (swing_pct / 100 − 0.5) × 2 × 125 ms
            sixteenth_ms = 125.0
            swing_extra  = (s.swing_pct / 100.0 - 0.5) * 2.0 * sixteenth_ms
            t_vals = [nudge + (swing_extra if i % 2 == 1 else 0.0)
                      for i in range(16)]
            self._t_grid.set_values(t_vals)

        # P grid
        if s.use_advanced and s.p_grid is not None:
            self._p_grid.set_values(s.p_grid)
        else:
            self._p_grid.set_values([float(s.pan)] * 16)

        # E grid
        if s.use_advanced and s.e_grid is not None:
            self._e_grid.set_values(s.e_grid)
        else:
            self._e_grid.reset_all()   # neutral = 64

    def to_groove_settings(
        self,
        base: TrackGrooveSettings,
    ) -> Tuple[TrackGrooveSettings, bool, str]:
        """
        Read all four grids and return a TrackGrooveSettings with grid data.

        The simplified Tier-1 fields are also filled with the nearest
        lossless-or-approximate equivalents so the caller can restore the
        simplified view if the user switches back.

        Parameters
        ----------
        base : Existing settings — Tier-2 values and Transpose/Gain are
               preserved; only the grid-derived fields are replaced.

        Returns
        -------
        (settings, is_lossless, warning_msg)
            settings     — TrackGrooveSettings with use_advanced=True and all
                           four grid arrays populated.
            is_lossless  — True when V and T grids can be expressed exactly
                           using the simplified Tier-1 controls.
            warning_msg  — Human-readable description of lost precision;
                           empty string when is_lossless is True.
        """
        v = self._v_grid.get_values()
        t = self._t_grid.get_values()
        p = self._p_grid.get_values()
        e = self._e_grid.get_values()

        # Derive best simplified approximation for fallback fields.
        curve, nudge, _swing_extra_ms, lossless, warning = grids_to_simple(v, t)

        # Use mean P as the constant pan for simplified fallback.
        mean_pan = int(round(sum(p) / len(p)))
        mean_pan = max(-63, min(63, mean_pan))

        settings = TrackGrooveSettings(
            # Persistent Tier-1 fields (not managed by grids)
            transpose_st       = base.transpose_st,
            gain_db            = base.gain_db,
            # Simplified approximation (used if user reverts to simple mode)
            vel_min            = base.vel_min,
            vel_max            = base.vel_max,
            vel_curve          = curve,
            swing_pct          = base.swing_pct,   # kept; needs BPM to recalculate
            timing_nudge_ms    = nudge,
            pan                = mean_pan,
            # Tier-2 values preserved from base
            vel_humanize       = base.vel_humanize,
            timing_humanize_ms = base.timing_humanize_ms,
            seed               = base.seed,
            # Advanced grid data
            use_advanced       = True,
            v_grid             = v,
            t_grid             = t,
            p_grid             = p,
            e_grid             = e,
        )
        return settings, lossless, warning

    def get_export_data(self) -> dict:
        """
        Return the four grid arrays as a plain dict for JSON serialisation.

        Keys: 'track', 'V', 'T', 'P', 'E'.
        """
        return {
            'track': self._track_key,
            'V':     self._v_grid.get_values(),
            'T':     self._t_grid.get_values(),
            'P':     self._p_grid.get_values(),
            'E':     self._e_grid.get_values(),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _export_json(self) -> None:
        """Write the four grid vectors to a user-chosen JSON file."""
        data = self.get_export_data()
        path = filedialog.asksaveasfilename(
            title='Export Grid JSON',
            defaultextension='.json',
            initialfile=f'{self._track_key}_groove_grid.json',
            filetypes=[
                ('JSON files', '*.json'),
                ('All files',  '*.*'),
            ],
        )
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, indent=2)
            messagebox.showinfo(
                'Export complete',
                f'Grid data for track "{self._track_key}" written to:\n{path}',
                parent=self._frame,
            )
        except OSError as exc:
            messagebox.showerror(
                'Export failed',
                str(exc),
                parent=self._frame,
            )
