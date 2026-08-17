"""
src/gui/scrollable_frame.py
----------------------------
Reusable vertically-scrollable container widget for Tkinter.

Wraps a tk.Canvas + tk.Scrollbar pair so that any collection of child
widgets can be scrolled vertically inside a fixed-height parent.  The
public API is intentionally minimal: pack / place / grid the
ScrollableFrame itself, then add child widgets to ``self.inner`` instead
of directly to the parent.

Cross-platform mouse-wheel support
------------------------------------
Windows  : <MouseWheel> event,  event.delta / 120  gives scroll clicks
macOS    : <MouseWheel> event,  event.delta         gives scroll clicks
Linux    : <Button-4> (scroll up), <Button-5> (scroll down)

All three variants are handled here so the widget works without any
platform-specific code at the call site.

Conflict avoidance with other scrollable areas
------------------------------------------------
When the pointer *enters* this widget, it registers a global
bind_all(<MouseWheel>) so mouse-wheel events are directed here.  When
the pointer *leaves*, the global binding is released so other scrollable
areas (e.g. the left panel) can reclaim it when the pointer enters them.
This pattern is idiomatic for Tkinter multi-scroll-area layouts.

Usage example
--------------
    from src.gui.scrollable_frame import ScrollableFrame

    sf = ScrollableFrame(parent, bg=S.BG2)
    sf.pack(fill='both', expand=True)

    # Add children to sf.inner — NOT to sf directly
    tk.Label(sf.inner, text="Hello").pack()
    SomeWidget(sf.inner, ...).pack(fill='x')
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk


class ScrollableFrame(tk.Frame):
    """
    A vertically scrollable container.

    Parameters
    ----------
    parent          : Tkinter parent widget.
    bg              : Background colour applied to canvas and inner frame.
    scrollbar_bg    : Scrollbar trough / track colour.
    scrollbar_width : Width of the scrollbar in pixels (default 12).
    **kwargs        : Forwarded to the outer tk.Frame constructor.

    Attributes
    ----------
    inner  : tk.Frame  — Add child widgets here.
    canvas : tk.Canvas — Exposed for advanced event binding if needed.
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        bg:              str = "#1e1e22",
        scrollbar_bg:    str = "#27272d",
        scrollbar_width: int = 12,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=bg, **kwargs)

        self._bg = bg

        # ── Canvas ──────────────────────────────────────────────────────────
        self.canvas = tk.Canvas(
            self,
            bg=bg,
            highlightthickness=0,
            yscrollincrement=4,   # 4 px per scroll click — smooth feel
        )

        # ── Scrollbar ────────────────────────────────────────────────────────
        # Styled to match the dark theme; uses ttk.Scrollbar so it inherits
        # the application's configured ttk style on all platforms.
        self._scrollbar = ttk.Scrollbar(
            self,
            orient='vertical',
            command=self.canvas.yview,
        )
        self.canvas.configure(yscrollcommand=self._scrollbar.set)

        # Scrollbar on right edge; canvas fills the rest
        self._scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)

        # ── Inner frame ──────────────────────────────────────────────────────
        # All child widgets are packed / gridded into self.inner.
        self.inner = tk.Frame(self.canvas, bg=bg)

        # Embed inner frame as a canvas window anchored at top-left
        self._window_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor='nw',
        )

        # ── Size tracking bindings ────────────────────────────────────────────
        # Update scroll region whenever inner frame content changes size
        self.inner.bind('<Configure>', self._on_inner_configure)

        # Stretch inner frame to match canvas width on resize so child widgets
        # fill the full horizontal space (prevents narrow content strips)
        self.canvas.bind('<Configure>', self._on_canvas_configure)

        # ── Mouse-wheel bindings ─────────────────────────────────────────────
        # Register on Enter/Leave so only the hovered scroll area captures
        # the wheel — multiple ScrollableFrames can coexist without conflict.
        self.canvas.bind('<Enter>', self._on_enter)
        self.canvas.bind('<Leave>', self._on_leave)
        # Also trigger on inner frame entry so scrolling works while the
        # pointer is over child widgets rather than the canvas background.
        self.inner.bind('<Enter>', self._on_enter)
        self.inner.bind('<Leave>', self._on_leave)

    # ── Private — size tracking ───────────────────────────────────────────────

    def _on_inner_configure(self, _event) -> None:
        """Update the canvas scroll region to fit all inner content."""
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas_configure(self, event) -> None:
        """Stretch the inner frame to fill the canvas width."""
        self.canvas.itemconfig(self._window_id, width=event.width)

    # ── Private — mouse-wheel management ─────────────────────────────────────

    def _on_enter(self, _event=None) -> None:
        """Claim the global mousewheel binding for this canvas."""
        if sys.platform == 'win32':
            # Windows: delta is a multiple of 120 (one notch = 120)
            self.canvas.bind_all(
                '<MouseWheel>',
                lambda e, c=self.canvas: c.yview_scroll(
                    int(-1 * e.delta / 120), 'units'),
            )
        elif sys.platform == 'darwin':
            # macOS: delta is in scroll-unit clicks already (no divisor)
            self.canvas.bind_all(
                '<MouseWheel>',
                lambda e, c=self.canvas: c.yview_scroll(
                    int(-1 * e.delta), 'units'),
            )
        else:
            # Linux: separate events for up (Button-4) and down (Button-5)
            self.canvas.bind_all(
                '<Button-4>',
                lambda e, c=self.canvas: c.yview_scroll(-3, 'units'),
            )
            self.canvas.bind_all(
                '<Button-5>',
                lambda e, c=self.canvas: c.yview_scroll(3, 'units'),
            )

    def _on_leave(self, _event=None) -> None:
        """Release the global mousewheel binding."""
        self.canvas.unbind_all('<MouseWheel>')
        self.canvas.unbind_all('<Button-4>')
        self.canvas.unbind_all('<Button-5>')

    # ── Public helpers ────────────────────────────────────────────────────────

    def scroll_to_top(self) -> None:
        """Scroll the content back to the top (e.g. after content refresh)."""
        self.canvas.yview_moveto(0.0)
