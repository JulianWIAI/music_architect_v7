"""
waveform_widget.py

Interactive bar-chart waveform display for the Music Architect player.

Renders the amplitude envelope of a WAV file as vertical bars on a Tkinter
Canvas.  Bars to the left of the playhead are drawn in the theme's cyan
(already played); bars to the right are in a dim blue-grey (remaining).

Click / drag on the canvas to seek.  The host calls update_playhead() from
its polling loop to advance the playhead in sync with the audio backend.

The waveform is computed in a background thread via waveform_generator.py
so the UI stays responsive while reading large WAV files.

Public API
----------
    widget.load_wav(path)            — Compute and display waveform from file.
    widget.update_playhead(fraction) — Move playhead to 0.0–1.0 position.
    widget.reset()                   — Clear display (between generations).
    widget._duration                 — Float: total WAV duration in seconds.
"""

import threading
import tkinter as tk
from typing import Callable, List, Optional

from src.audio.waveform_generator import compute_waveform


class WaveformWidget(tk.Frame):
    """
    Bar-chart waveform with a live playhead and click-to-seek.

    Parameters
    ----------
    parent   : Tkinter parent widget.
    styles   : Application styles object (S from styles.py).
    on_seek  : Optional callback(fraction: float) triggered on click/drag.
    height   : Canvas height in pixels.
    """

    # ── Colours (match the cyberpunk theme) ───────────────────────────────────
    _COLOR_PLAYED   = "#00e5ff"   # cyan  — played portion
    _COLOR_UNPLAYED = "#1a2a44"   # dark blue-grey — remaining portion
    _COLOR_PLAYHEAD = "#ffffff"   # white vertical line
    _COLOR_BG       = "#07071a"   # S.BG

    def __init__(
        self,
        parent,
        styles,
        on_seek:  Optional[Callable[[float], None]] = None,
        height:   int = 72,
        **kwargs,
    ):
        super().__init__(parent, bg=styles.BG, **kwargs)
        self._S       = styles
        self._on_seek = on_seek
        self._height  = height

        # Waveform state
        self._bars:     List[float] = []    # amplitude bars [0.0–1.0]
        self._duration: float       = 0.0   # total audio duration in seconds
        self._playhead: float       = 0.0   # current position as fraction [0.0–1.0]

        self._build()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        S = self._S

        # Time label row above the canvas
        lbl_row = tk.Frame(self, bg=S.BG)
        lbl_row.pack(fill='x')

        self._lbl_current = tk.Label(
            lbl_row, text="00:00", font=S.FN_X, fg=S.CYAN,
            bg=S.BG, width=5, anchor='w',
        )
        self._lbl_current.pack(side='left', padx=(6, 0))

        tk.Label(
            lbl_row, text="WAVEFORM", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG,
        ).pack(side='left', expand=True)

        self._lbl_total = tk.Label(
            lbl_row, text="00:00", font=S.FN_X, fg=S.TXT_DIM,
            bg=S.BG, width=5, anchor='e',
        )
        self._lbl_total.pack(side='right', padx=(0, 6))

        # Main canvas — this is where bars and playhead are drawn
        self._canvas = tk.Canvas(
            self,
            bg                = self._COLOR_BG,
            height            = self._height,
            highlightthickness = 1,
            highlightbackground = S.BG3,
            cursor            = 'hand2',
        )
        self._canvas.pack(fill='x', expand=True, padx=4, pady=(0, 4))

        # Placeholder text shown before the first WAV is loaded
        self._canvas.create_text(
            10, self._height // 2,
            anchor = 'w',
            tags   = 'placeholder',
            text   = "Generate a song to see the waveform — click to seek",
            fill   = S.TXT_DIM,
            font   = S.FN_X,
        )

        # Bind resize and mouse events
        self._canvas.bind('<Configure>', self._on_resize)
        self._canvas.bind('<Button-1>',  self._on_click)
        self._canvas.bind('<B1-Motion>', self._on_click)   # drag to scrub

    # ── Public API ────────────────────────────────────────────────────────────

    def load_wav(self, wav_path: str) -> None:
        """
        Compute the waveform for *wav_path* in a background thread.

        Shows a 'Loading…' placeholder immediately; redraws as soon as the
        background thread finishes and posts the result back to the main thread.
        """
        self._bars     = []
        self._duration = 0.0
        self._playhead = 0.0
        self._canvas.delete('all')
        self._canvas.create_text(
            10, self._height // 2,
            anchor = 'w',
            tags   = 'placeholder',
            text   = "Loading waveform…",
            fill   = self._S.TXT_DIM,
            font   = self._S.FN_X,
        )
        self._lbl_current.config(text='00:00')
        self._lbl_total.config(text='00:00')

        # Calculate bar count from the canvas pixel width.
        # winfo_width() returns 1 when the canvas hasn't been drawn yet (e.g.
        # on the first render after launch).  Fall back to 800 bars so the
        # waveform is always high-resolution regardless of timing.
        w        = self._canvas.winfo_width()
        num_bars = max(800, w // 3) if w > 10 else 800

        thread = threading.Thread(
            target = self._compute_in_background,
            args   = (wav_path, num_bars),
            daemon = True,
        )
        thread.start()

    def update_playhead(self, fraction: float) -> None:
        """
        Move the playhead to *fraction* (0.0 = start, 1.0 = end).

        Must be called from the main thread (e.g. inside root.after() poll).
        """
        self._playhead = max(0.0, min(1.0, fraction))
        self._redraw()
        self._update_time_labels()

    def reset(self) -> None:
        """
        Clear the waveform display.

        Call this when a new generation starts so the previous song's waveform
        is not shown next to a 'Generating…' status.
        """
        self._bars     = []
        self._duration = 0.0
        self._playhead = 0.0
        self._canvas.delete('all')
        self._canvas.create_text(
            10, self._height // 2,
            anchor = 'w',
            tags   = 'placeholder',
            text   = "Generate a song to see the waveform — click to seek",
            fill   = self._S.TXT_DIM,
            font   = self._S.FN_X,
        )
        self._lbl_current.config(text='00:00')
        self._lbl_total.config(text='00:00')

    # ── Internal ──────────────────────────────────────────────────────────────

    def _compute_in_background(self, wav_path: str, num_bars: int) -> None:
        """Worker thread: decode WAV and post result back to the main thread."""
        bars, duration = compute_waveform(wav_path, num_bars=num_bars)
        # Schedule the UI update on the main thread to avoid Tkinter threading issues
        self._canvas.after(0, lambda: self._on_computed(bars, duration))

    def _on_computed(self, bars: List[float], duration: float) -> None:
        """Called on the main thread when waveform data is ready."""
        self._bars     = bars
        self._duration = duration
        self._lbl_total.config(text=self._fmt_time(duration))
        self._redraw()

    def _redraw(self) -> None:
        """Repaint the entire canvas from the stored bar data and playhead position."""
        if not self._bars:
            return

        self._canvas.delete('all')
        w = self._canvas.winfo_width()
        h = self._height
        if w <= 1:
            return

        n     = len(self._bars)
        bar_w = w / n
        # Pixel x-coordinate of the playhead
        cx    = int(self._playhead * w)

        for i, amp in enumerate(self._bars):
            x0 = int(i * bar_w) + 1
            # Each bar is at least 1 pixel wide; gap of 1px between bars
            x1 = max(x0 + 1, int((i + 1) * bar_w) - 1)
            # Scale bar height with 90% of canvas height to leave breathing room
            bar_h = max(2, int(amp * h * 0.90))
            y0    = (h - bar_h) // 2
            y1    = y0 + bar_h
            color = self._COLOR_PLAYED if x0 <= cx else self._COLOR_UNPLAYED
            self._canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline='')

        # Playhead: a bright vertical line at the current position
        if 0 <= cx <= w:
            self._canvas.create_line(
                cx, 0, cx, h,
                fill  = self._COLOR_PLAYHEAD,
                width = 2,
            )

    def _on_resize(self, _event) -> None:
        """Redraw when the canvas is resized (e.g. window resize)."""
        self._redraw()

    def _on_click(self, event) -> None:
        """
        Handle left-click or left-drag on the canvas.

        Computes the seek fraction from the click x-coordinate and:
          1. Moves the visual playhead immediately (so the UI feels responsive).
          2. Fires the on_seek callback so the audio backend can reposition.
        """
        w = self._canvas.winfo_width()
        if w <= 0 or not self._bars:
            return

        fraction       = max(0.0, min(1.0, event.x / w))
        self._playhead = fraction
        self._redraw()
        self._update_time_labels()

        if self._on_seek:
            self._on_seek(fraction)

    def _update_time_labels(self) -> None:
        """Refresh the elapsed / total time labels from the current state."""
        if self._duration > 0:
            elapsed = self._playhead * self._duration
            self._lbl_current.config(text=self._fmt_time(elapsed))
            self._lbl_total.config(text=self._fmt_time(self._duration))

    @staticmethod
    def _fmt_time(secs: float) -> str:
        """Format seconds as MM:SS string."""
        s = int(secs)
        return f"{s // 60:02d}:{s % 60:02d}"
