"""
track_metadata_panel.py

Compact two-column metadata display panel embedded in the OUTPUT tab.

Displays the standard metadata fields that music players typically show:
  Title, Artist, Album, Genre, Year, Duration, Bitrate, Sample Rate.

All fields are backed by tk.StringVar so they update instantly when
update() is called from the main thread — no widget destruction needed.

Usage
-----
    panel = TrackMetadataPanel(parent, styles=S)
    panel.pack(fill='x')
    ...
    panel.update(metadata)   # AudioMetadata instance from audio_metadata.py
"""

import tkinter as tk
from typing import Optional

from src.audio.audio_metadata import AudioMetadata


class TrackMetadataPanel(tk.Frame):
    """
    Two-column key/value metadata panel styled to match the cyberpunk theme.

    The title row spans the full width at the top.  Below it, metadata pairs
    are laid out in a compact grid: label (dim) on the left, value on the right.
    """

    def __init__(self, parent, styles, **kwargs):
        super().__init__(parent, bg=styles.BG2, **kwargs)
        self._S = styles
        # Dict of field_key → StringVar, populated by _build()
        self._vars: dict = {}
        self._build()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        S = self._S

        # ── Title / song name ─────────────────────────────────────────────────
        self._title_var = tk.StringVar(value="No composition generated yet")
        tk.Label(
            self,
            textvariable = self._title_var,
            font         = S.FN_S,
            fg           = S.CYAN,
            bg           = S.BG2,
            anchor       = 'w',
            wraplength   = 600,
        ).pack(fill='x', padx=8, pady=(6, 2))

        # Thin separator line
        tk.Frame(self, bg=S.BG3, height=1).pack(fill='x', padx=8, pady=(0, 4))

        # ── Metadata key/value grid ───────────────────────────────────────────
        # Two pairs per row to keep the panel compact:
        #   [Artist label][Artist value]    [Genre label][Genre value]
        #   [Album  label][Album  value]    [Year  label][Year  value]
        #   [Duration lbl][Duration value]  [Bitrate lbl][Bitrate value]
        #   [Sample rate label][value]
        grid = tk.Frame(self, bg=S.BG2)
        grid.pack(fill='x', padx=8, pady=(0, 6))

        # (field_key, display_label) pairs — order matches typical player layout
        fields = [
            ('artist',      'Artist'),
            ('album',       'Album'),
            ('genre',       'Genre'),
            ('year',        'Year'),
            ('duration',    'Duration'),
            ('bitrate',     'Bitrate'),
            ('sample_rate', 'Sample rate'),
        ]

        for row_idx, (key, label) in enumerate(fields):
            var = tk.StringVar(value="—")
            self._vars[key] = var

            tk.Label(
                grid,
                text   = label,
                font   = S.FN_X,
                fg     = S.TXT_DIM,
                bg     = S.BG2,
                width  = 12,
                anchor = 'w',
            ).grid(row=row_idx, column=0, sticky='w', pady=1)

            tk.Label(
                grid,
                textvariable = var,
                font         = S.FN_X,
                fg           = S.TXT,
                bg           = S.BG2,
                anchor       = 'w',
            ).grid(row=row_idx, column=1, sticky='w', padx=(4, 0), pady=1)

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, metadata: Optional[AudioMetadata]) -> None:
        """
        Refresh all displayed fields from an AudioMetadata instance.
        Passing None resets everything to the 'no composition' placeholder.
        """
        if metadata is None:
            self._title_var.set("No composition generated yet")
            for var in self._vars.values():
                var.set("—")
            return

        self._title_var.set(metadata.title)
        self._vars['artist'].set(metadata.artist)
        self._vars['album'].set(metadata.album)
        self._vars['genre'].set(metadata.genre)
        self._vars['year'].set(metadata.year)
        self._vars['duration'].set(metadata.duration_str)
        self._vars['bitrate'].set(metadata.bitrate_str)
        self._vars['sample_rate'].set(metadata.sample_rate_str)
