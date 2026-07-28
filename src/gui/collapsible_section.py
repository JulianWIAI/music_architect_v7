"""
collapsible_section.py — A collapsible panel widget for the Seed Composer UI.

Provides:
  - CollapsibleSection: a labelled panel that can be toggled open/closed
    with a ▼/▶ arrow button in the header row.

Works on macOS and Windows (pure Tkinter, no platform-specific APIs).
"""

import tkinter as tk
from src.gui.styles import S


class CollapsibleSection:
    """
    A section panel whose content can be hidden or revealed by clicking
    the arrow toggle button in the header.

    Args:
        parent:    Parent Tkinter widget.
        title:     Section heading text (displayed in caps).
        color:     Accent color for the title and separator line.
        collapsed: If True (default), the section starts hidden.

    Attributes:
        content_frame (tk.Frame): Pack widgets into this frame — it is the
                                  frame that gets hidden/shown on toggle.
        outer (tk.Frame):         The outermost container frame.

    Example::

        cs = CollapsibleSection(parent, "PARAMETERS", S.PURPLE, collapsed=True)
        tk.Label(cs.content_frame, text="Hello").pack()
    """

    def __init__(self, parent: tk.Widget, title: str, color: str, collapsed: bool = True):
        self._collapsed = collapsed
        self._color = color

        # Outermost container — same padding as _section() helper
        self.outer = tk.Frame(parent, bg=S.BG2)
        self.outer.pack(fill='x', padx=6, pady=4)

        # ── Header row: toggle arrow + title label ──────────────────────
        header = tk.Frame(self.outer, bg=S.BG2)
        header.pack(fill='x')

        self._arrow_var = tk.StringVar(value="▶" if collapsed else "▼")

        # Arrow toggle button — styled to blend with the dark theme
        self._toggle_btn = tk.Button(
            header,
            textvariable=self._arrow_var,
            command=self._toggle,
            font=("Consolas", 10, "bold"),
            fg=color,
            bg=S.BG2,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG2,
            bd=0,
            padx=4,
            pady=0,
            cursor='hand2',
            highlightthickness=0,
            relief='flat',
        )
        self._toggle_btn.pack(side='left')

        # Section title
        tk.Label(
            header,
            text=title,
            font=S.FN_H,
            fg=color,
            bg=S.BG2,
            anchor='w',
        ).pack(side='left', fill='x', padx=4)

        # Horizontal separator line (1 px, accent colour)
        tk.Frame(self.outer, bg=color, height=1).pack(fill='x', pady=(2, 4))

        # ── Content area ────────────────────────────────────────────────
        # Hidden initially if collapsed=True; revealed by _toggle()
        self.content_frame = tk.Frame(self.outer, bg=S.BG2)
        if not collapsed:
            self.content_frame.pack(fill='x')

    # ── Private ──────────────────────────────────────────────────────────

    def _toggle(self):
        """Flip the collapsed/expanded state."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.content_frame.pack_forget()
            self._arrow_var.set("▶")
        else:
            self.content_frame.pack(fill='x')
            self._arrow_var.set("▼")
