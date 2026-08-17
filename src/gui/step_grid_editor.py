"""
src/gui/step_grid_editor.py
────────────────────────────
Compact 16-step vertical slider grid for the Advanced Groove editor.

Each of the 16 cells maps to one 16th-note position in a 4/4 bar, labelled
in jazz/drum-rudiment notation:  1  1e  1+  1a  2  2e  2+  2a  …  4a

Interactions
------------
  Drag      — adjust the step value.
  Hover     — a status label below the grid shows the numeric value.
  Ctrl+click — reset the cell to its neutral value (1.0 for V, 0.0 for T).
  [Reset all] button — set every cell to neutral in one click.

Cross-platform: pure Tkinter, no platform-specific APIs.
On macOS, Ctrl+click is NOT a right-click in Tkinter's event model, so the
<Control-Button-1> binding works as expected on both macOS and Windows.

Public API::

    grid = StepGridEditor(
        parent,
        from_=0.0, to=2.0, neutral=1.0, resolution=0.01,
        label='V', unit='×', color=S.CYAN,
    )
    values = grid.get_values()          # List[float], 16 elements
    grid.set_values([1.0] * 16)
    grid.reset_all()
    grid.frame.pack(fill='x')           # caller controls geometry
"""

from __future__ import annotations

import tkinter as tk
from typing import List

from src.gui.styles import S
from src.gui.tooltips import ToolTip


# Jazz/drum notation for the 16 16th-note positions in a 4/4 bar.
# Position numbering: 1 (downbeat), 1e (e-of-1), 1+ (and-of-1), 1a (ah-of-1) …
JAZZ_STEP_LABELS: List[str] = [
    '1',  '1e', '1+', '1a',
    '2',  '2e', '2+', '2a',
    '3',  '3e', '3+', '3a',
    '4',  '4e', '4+', '4a',
]

# Height of the slider track in pixels.  Wider + taller = easier to grab on
# both Windows (where the trough defines the click target) and macOS.
_SLIDER_LEN   = 90
_SLIDER_WIDTH  = 18   # trough width; do NOT use pack_propagate(False) — let cells grow


class StepGridEditor:
    """
    A horizontal row of 16 labelled vertical sliders representing one
    groove parameter across every 16th-note of a 4/4 bar.

    Parameters
    ----------
    parent      : Tkinter parent frame (caller manages packing of self.frame).
    from_       : Minimum slider value — mapped to the bottom of the track.
    to          : Maximum slider value — mapped to the top of the track.
    neutral     : Value applied by Ctrl+click reset.
    resolution  : Smallest slider increment.
    label       : Short name shown in the section header (e.g. 'V').
    unit        : Unit string appended in the hover tooltip (e.g. '×', 'ms').
    color       : Accent colour for slider thumbs and the section label.
    """

    def __init__(
        self,
        parent:     tk.Frame,
        from_:      float = 0.0,
        to:         float = 2.0,
        neutral:    float = 1.0,
        resolution: float = 0.01,
        label:      str   = 'V',
        unit:       str   = '×',
        color:      str   = '',
    ) -> None:
        self._neutral    = neutral
        self._unit       = unit
        self._color      = color or S.CYAN
        self._from       = float(from_)
        self._to         = float(to)
        self._resolution = resolution

        # ── Outer container (caller packs this) ───────────────────────────────
        self._frame = tk.Frame(parent, bg=S.BG2)

        # ── Section header row ────────────────────────────────────────────────
        hdr = tk.Frame(self._frame, bg=S.BG2)
        hdr.pack(fill='x', padx=2)

        tk.Label(
            hdr,
            text=f'{label}   ({unit})',
            font=S.FN_S,
            fg=self._color,
            bg=S.BG2,
            anchor='w',
        ).pack(side='left')

        _reset_btn = tk.Button(
            hdr,
            text='Reset all',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0, padx=4, pady=0,
            cursor='hand2',
            command=self.reset_all,
        )
        _reset_btn.pack(side='right')
        ToolTip(_reset_btn, 'Set every step back to its neutral value\n'
                            '(1.0 for V · 0.0 for T · 0 for P · 64 for E).\n'
                            'Ctrl+click on a single slider resets just that step.')

        # ── Slider row ────────────────────────────────────────────────────────
        grid_row = tk.Frame(self._frame, bg=S.BG2)
        grid_row.pack(fill='x', padx=2, pady=(2, 0))

        # Shared hover-value display (single label below the grid).
        self._hover_var = tk.StringVar(value='')
        tk.Label(
            self._frame,
            textvariable=self._hover_var,
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor='w',
            height=1,
        ).pack(fill='x', padx=2)

        self._vars:    List[tk.DoubleVar] = []
        self._sliders: List[tk.Scale]     = []

        for i in range(16):
            # No fixed width and NO pack_propagate(False) — the Scale must render
            # at its natural size so Windows registers clicks on the trough area.
            cell = tk.Frame(grid_row, bg=S.BG2)
            cell.pack(side='left', padx=1)

            var = tk.DoubleVar(value=neutral)
            self._vars.append(var)

            # Vertical slider: from_=to, to=from_ so the thumb sits at the top
            # for high values (visually: tall bar = high value).
            # _SLIDER_WIDTH=18 provides a large-enough trough for both Windows
            # (trough-based hit-test) and macOS (thumb-based hit-test).
            sl = tk.Scale(
                cell,
                variable=var,
                from_=self._to,       # top of track = maximum value
                to=self._from,        # bottom = minimum value
                resolution=resolution,
                orient='vertical',
                length=_SLIDER_LEN,
                width=_SLIDER_WIDTH,
                showvalue=0,
                fg=self._color,
                bg=S.BG2,
                troughcolor=S.BG_INPUT,
                activebackground=self._color,
                highlightthickness=0,
                bd=0,
            )
            sl.pack()
            self._sliders.append(sl)

            # Jazz-notation step label centred below each slider.
            tk.Label(
                cell,
                text=JAZZ_STEP_LABELS[i],
                font=('Consolas', 7),
                fg=S.TXT_DIM,
                bg=S.BG2,
                anchor='center',
            ).pack(fill='x')

            # ── Event bindings — closures capture i and var via default args ──
            def _enter(event, idx=i, v=var):
                """Show step value in the shared hover label when cursor enters."""
                val = v.get()
                fmt = f'{val:.3g}' if self._resolution < 1 else f'{val:.0f}'
                self._hover_var.set(
                    f'Step {JAZZ_STEP_LABELS[idx]}: {fmt} {self._unit}'
                )

            def _leave(event):
                self._hover_var.set('')

            def _ctrl_reset(event, v=var):
                """Ctrl+click resets the step to its neutral value."""
                v.set(self._neutral)

            sl.bind('<Enter>',            _enter)
            sl.bind('<Motion>',           _enter)   # refresh label while hovering
            sl.bind('<B1-Motion>',        _enter)   # refresh label while dragging
            sl.bind('<Leave>',            _leave)
            sl.bind('<Control-Button-1>', _ctrl_reset)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def frame(self) -> tk.Frame:
        """Outer container frame — caller packs this into its layout."""
        return self._frame

    def get_values(self) -> List[float]:
        """Return the current 16 step values as a list of floats."""
        return [v.get() for v in self._vars]

    def set_values(self, values: List[float]) -> None:
        """
        Load up to 16 values into the grid.

        Elements past position 15 are ignored.  Missing elements (when
        len(values) < 16) are filled with the neutral value.
        """
        for i, var in enumerate(self._vars):
            if i < len(values):
                clamped = max(self._from, min(self._to, float(values[i])))
                var.set(clamped)
            else:
                var.set(self._neutral)

    def reset_all(self) -> None:
        """Set every step to the neutral value."""
        for var in self._vars:
            var.set(self._neutral)
