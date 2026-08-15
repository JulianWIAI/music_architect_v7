"""
export_dialog.py

Modal "Export Audio" dialog — inspired by professional DAW export screens.

Layout
------
┌──────────────────────────────────────────────────────────┐
│  EXPORT AUDIO                                        [X]  │
├──────────────────────────────────────────────────────────┤
│  FILENAME & LOCATION                                      │
│  [filename_entry]               [Browse output folder]   │
│  Save to: [path_entry.............................]       │
├──────────────────────────────────────────────────────────┤
│  FORMAT PRESETS              │  CUSTOM SETTINGS          │
│  ┌──────────────────────┐   │  File Type   [WAV ▼]      │
│  │ ◉ WAV — Mastering    │   │  Sample Rate [44100 ▼]    │
│  │   WAV — CD Quality   │   │  Bit Depth   [16-bit ▼]   │
│  │   FLAC — Lossless    │   │  Channels    [Stereo ▼]   │
│  │   MP3 — 320 kbps     │   │  Bitrate     [320 kbps ▼] │
│  │   MP3 — 192 kbps     │   │  (disabled for WAV/FLAC)  │
│  │   ...                │   │                           │
│  └──────────────────────┘   │  Est. size: 45.2 MB       │
│  [description text]          │  ⚠ ffmpeg required...     │
├──────────────────────────────────────────────────────────┤
│  ▓▓▓▓▓▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒ (progress bar, hidden at start)   │
├──────────────────────────────────────────────────────────┤
│  [Cancel]                                   [EXPORT]     │
└──────────────────────────────────────────────────────────┘

Usage (from app.py)
-------------------
    ExportDialog(
        parent       = self.root,
        styles       = S,
        source_wav   = self.current_wav_path,
        composition  = self.current_composition,
        gen_number   = self.generation_counter,
        log_fn       = self._log,
    )
"""

import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.export.export_config import (
    AudioFormat,
    DEFAULT_PRESETS,
    ExportPreset,
    estimate_size_bytes,
    format_size,
)
from src.export.audio_converter import (
    convert,
    ffmpeg_available,
    read_wav_duration,
)

try:
    from src.dsp.mastering_chain import MasteringChain
    from src.gui.mastering_panel import MasteringPanel
    _MASTERING_AVAILABLE = True
except Exception:
    _MASTERING_AVAILABLE = False


# ── Constants for the settings dropdowns ─────────────────────────────────────

_SAMPLE_RATES  = ['22050', '44100', '48000', '88200', '96000']
_BIT_DEPTHS    = ['16', '24', '32']
_CHANNELS      = ['Mono', 'Stereo']
_BITRATES      = ['64', '96', '128', '160', '192', '256', '320']
_FORMAT_NAMES  = ['WAV', 'MP3', 'FLAC', 'OGG']
_FORMAT_MAP    = {
    'WAV':  AudioFormat.WAV,
    'MP3':  AudioFormat.MP3,
    'FLAC': AudioFormat.FLAC,
    'OGG':  AudioFormat.OGG,
}


class ExportDialog(tk.Toplevel):
    """
    Modal audio export dialog.

    Opens as a child of *parent* and grabs all keyboard/mouse events until
    the user clicks Cancel or Export.
    """

    def __init__(
        self,
        parent,
        styles,
        source_wav:  Optional[str] = None,
        composition: Optional[dict] = None,
        gen_number:  int            = 1,
        log_fn                      = None,
        variant_id:  str            = 'neutral',
    ):
        super().__init__(parent)

        self._S           = styles
        self._source_wav  = source_wav
        self._composition = composition
        self._gen_number  = gen_number
        self._log         = log_fn or (lambda msg: None)
        self._variant_id  = variant_id
        self._mastering_panel: Optional['MasteringPanel'] = None

        # Duration from the WAV file header — used for size estimation
        self._duration_sec: float = read_wav_duration(source_wav) if source_wav else 0.0

        # Currently selected preset index (-1 = custom / no selection)
        self._selected_idx: int = 0
        # Flag that prevents _on_setting_change → _refresh_size → _on_setting_change loops
        self._updating: bool    = False
        # Preset row frames (for highlight toggling)
        self._preset_rows: list = []

        self._has_ffmpeg = ffmpeg_available()

        self._configure_window(parent)
        self._build()
        self._select_preset(0)

    # ── Window setup ──────────────────────────────────────────────────────────

    def _configure_window(self, parent):
        self.title("EXPORT AUDIO")
        self.resizable(True, False)
        self.configure(bg=self._S.BG2)
        self.grab_set()           # modal: captures all events
        self.focus_set()

        # Center on the parent window — extra height for the mastering panel
        self.update_idletasks()
        self.geometry("680x760")
        x = parent.winfo_rootx() + max(0, (parent.winfo_width()  - 680) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - 760) // 2)
        self.geometry(f"680x760+{x}+{y}")

        # Close via X button = same as Cancel
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build(self):
        S = self._S

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=S.BG3, height=40)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="EXPORT AUDIO", font=S.FN_H,
            fg=S.CYAN, bg=S.BG3,
        ).pack(side='left', padx=12, pady=8)
        if self._has_ffmpeg:
            badge_text  = "ffmpeg ✓"
            badge_color = S.GREEN
        else:
            badge_text  = "ffmpeg not found — WAV only"
            badge_color = S.YELLOW
        tk.Label(
            hdr, text=badge_text, font=S.FN_X,
            fg=badge_color, bg=S.BG3,
        ).pack(side='right', padx=12)

        # ── Filename & Location ───────────────────────────────────────────────
        loc_frame = tk.Frame(self, bg=S.BG2, pady=6)
        loc_frame.pack(fill='x', padx=10)
        tk.Label(
            loc_frame, text="FILENAME & LOCATION",
            font=S.FN_S, fg=S.TXT_DIM, bg=S.BG2,
        ).pack(anchor='w', pady=(0, 4))

        name_row = tk.Frame(loc_frame, bg=S.BG2)
        name_row.pack(fill='x')
        tk.Label(name_row, text="Name:", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=7, anchor='w').pack(side='left')
        self._filename_var = tk.StringVar(value=self._default_filename())
        tk.Entry(
            name_row, textvariable=self._filename_var,
            font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
            insertbackground=S.CYAN, relief='flat', bd=4,
        ).pack(side='left', fill='x', expand=True, padx=(4, 0))

        path_row = tk.Frame(loc_frame, bg=S.BG2)
        path_row.pack(fill='x', pady=(4, 0))
        tk.Label(path_row, text="Folder:", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                 width=7, anchor='w').pack(side='left')
        self._folder_var = tk.StringVar(value=self._default_folder())
        tk.Entry(
            path_row, textvariable=self._folder_var,
            font=S.FN_X, bg=S.BG_INPUT, fg=S.TXT,
            insertbackground=S.CYAN, relief='flat', bd=4,
        ).pack(side='left', fill='x', expand=True, padx=(4, 4))
        tk.Button(
            path_row, text="Browse…", font=S.FN_X,
            fg=S.CYAN, bg=S.BG3, bd=0, padx=8, pady=4,
            relief='flat', cursor='hand2',
            activeforeground=S.TXT_BRT, activebackground=S.BG3,
            command=self._browse_folder,
        ).pack(side='left')

        # Thin divider
        tk.Frame(self, bg=S.BG3, height=1).pack(fill='x', padx=10, pady=(6, 0))

        # ── Body: presets (left) + settings (right) ───────────────────────────
        body = tk.Frame(self, bg=S.BG2)
        body.pack(fill='both', expand=True, padx=10, pady=6)

        self._build_presets_panel(body)
        tk.Frame(body, bg=S.BG3, width=1).pack(side='left', fill='y', padx=(6, 6))
        self._build_settings_panel(body)

        # ── Mastering chain panel ─────────────────────────────────────────────
        tk.Frame(self, bg=S.BG3, height=1).pack(fill='x', padx=10, pady=(6, 0))
        if _MASTERING_AVAILABLE:
            self._mastering_panel = MasteringPanel(self, styles=S)
            self._mastering_panel.pack(fill='x', padx=10)
        else:
            tk.Label(
                self, text="Mastering unavailable (numpy/scipy missing)",
                font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
            ).pack(anchor='w', padx=10, pady=4)

        # ── Progress bar (hidden until export starts) ─────────────────────────
        tk.Frame(self, bg=S.BG3, height=1).pack(fill='x', padx=10, pady=(4, 0))
        self._prog_frame = tk.Frame(self, bg=S.BG2)
        self._prog_frame.pack(fill='x', padx=10, pady=(4, 0))
        self._prog_var = tk.DoubleVar()
        self._prog_bar = ttk.Progressbar(
            self._prog_frame, variable=self._prog_var, maximum=100,
        )
        self._prog_bar.pack(fill='x')
        self._prog_lbl = tk.Label(
            self._prog_frame, text="", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
        )
        self._prog_lbl.pack(anchor='w')
        self._prog_frame.pack_forget()    # hidden until export

        # ── Footer buttons ────────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=S.BG2)
        btn_row.pack(fill='x', padx=10, pady=8)

        tk.Button(
            btn_row, text="Cancel", font=S.FN_S,
            fg=S.TXT_DIM, bg=S.BG3, bd=0, padx=16, pady=6,
            relief='flat', cursor='hand2',
            activeforeground=S.TXT_BRT, activebackground=S.BG3,
            command=self._on_cancel,
        ).pack(side='left')

        self._export_btn = tk.Button(
            btn_row, text="  EXPORT  ", font=S.FN_S,
            fg=S.BG, bg=S.CYAN, bd=0, padx=20, pady=6,
            relief='flat', cursor='hand2',
            activeforeground=S.BG, activebackground=S.GREEN,
            command=self._on_export,
        )
        self._export_btn.pack(side='right')

    # ── Presets panel (left column) ───────────────────────────────────────────

    def _build_presets_panel(self, parent):
        S = self._S
        frame = tk.Frame(parent, bg=S.BG2, width=310)
        frame.pack(side='left', fill='y')
        frame.pack_propagate(False)

        tk.Label(
            frame, text="FORMAT PRESETS", font=S.FN_S, fg=S.TXT_DIM, bg=S.BG2,
        ).pack(anchor='w', pady=(0, 4))

        # Scrollable container for the preset rows
        canvas = tk.Canvas(frame, bg=S.BG, highlightthickness=0)
        sb     = tk.Scrollbar(frame, orient='vertical', command=canvas.yview, bg=S.BG3)
        inner  = tk.Frame(canvas, bg=S.BG)
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units'))

        for idx, preset in enumerate(DEFAULT_PRESETS):
            row = self._build_preset_row(inner, preset, idx)
            self._preset_rows.append(row)

        # Description label below the list
        self._desc_var = tk.StringVar()
        tk.Label(
            frame, textvariable=self._desc_var,
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
            wraplength=290, justify='left', anchor='w',
        ).pack(fill='x', pady=(6, 0))

    def _build_preset_row(self, parent, preset: ExportPreset, idx: int) -> tk.Frame:
        """Build one clickable preset row and return its frame widget."""
        S  = self._S
        is_lossy   = preset.fmt in (AudioFormat.MP3, AudioFormat.OGG)
        is_ffmpeg  = preset.fmt != AudioFormat.WAV
        greyed_out = is_ffmpeg and not self._has_ffmpeg

        bg    = S.BG if not greyed_out else S.BG2
        fg_nm = S.TXT if not greyed_out else S.TXT_DIM

        row = tk.Frame(parent, bg=bg, cursor='hand2' if not greyed_out else 'arrow')
        row.pack(fill='x', pady=1)

        # Format badge (WAV / MP3 / FLAC / OGG)
        fmt_lbl = tk.Label(
            row,
            text   = preset.fmt.value.upper(),
            font   = S.FN_X,
            fg     = S.TXT_BRT if not greyed_out else S.TXT_DIM,
            bg     = preset.fmt_color,
            width  = 5,
            pady   = 4,
        )
        fmt_lbl.pack(side='left', padx=(4, 4))

        # Middle: quality badge + name line + size
        mid = tk.Frame(row, bg=bg)
        mid.pack(side='left', fill='both', expand=True)

        top = tk.Frame(mid, bg=bg)
        top.pack(fill='x')

        # Quality badge pill
        tk.Label(
            top,
            text    = preset.quality_tag,
            font    = S.FN_X,
            fg      = S.BG if not greyed_out else S.TXT_DIM,
            bg      = preset.quality_color if not greyed_out else S.BG3,
            padx    = 4,
            pady    = 1,
        ).pack(side='left', padx=(0, 5))

        # Preset name
        tk.Label(
            top, text=preset.name, font=S.FN_X, fg=fg_nm, bg=bg, anchor='w',
        ).pack(side='left')

        # File size estimate
        size_var = tk.StringVar(value='…')
        tk.Label(
            row, textvariable=size_var, font=S.FN_X,
            fg=S.CYAN if not greyed_out else S.TXT_DIM,
            bg=bg, width=9, anchor='e',
        ).pack(side='right', padx=6)

        # Bind click to all sub-widgets
        def on_click(_event, i=idx, disabled=greyed_out):
            if not disabled:
                self._select_preset(i)

        for w in (row, fmt_lbl, mid, top):
            w.bind('<Button-1>', on_click)

        # Store widgets we need to update later
        row._size_var  = size_var   # type: ignore[attr-defined]
        row._bg_normal = bg          # type: ignore[attr-defined]

        return row

    # ── Settings panel (right column) ─────────────────────────────────────────

    def _build_settings_panel(self, parent):
        S = self._S
        frame = tk.Frame(parent, bg=S.BG2)
        frame.pack(side='left', fill='both', expand=True)

        tk.Label(
            frame, text="CUSTOM SETTINGS", font=S.FN_S, fg=S.TXT_DIM, bg=S.BG2,
        ).pack(anchor='w', pady=(0, 4))

        grid = tk.Frame(frame, bg=S.BG2)
        grid.pack(fill='x')

        # Helper: one settings row
        def row(label, var, values, row_idx, state='readonly'):
            tk.Label(
                grid, text=label, font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                width=13, anchor='w',
            ).grid(row=row_idx, column=0, sticky='w', pady=3)
            cb = ttk.Combobox(
                grid, textvariable=var, values=values,
                state=state, width=14, font=S.FN_X,
            )
            cb.grid(row=row_idx, column=1, sticky='w', padx=(4, 0), pady=3)
            cb.bind('<<ComboboxSelected>>', self._on_setting_change)
            return cb

        self._fmt_var  = tk.StringVar()
        self._rate_var = tk.StringVar()
        self._depth_var= tk.StringVar()
        self._ch_var   = tk.StringVar()
        self._br_var   = tk.StringVar()

        self._cb_fmt   = row("File type",    self._fmt_var,   _FORMAT_NAMES, 0)
        self._cb_rate  = row("Sample rate",  self._rate_var,  _SAMPLE_RATES, 1)
        self._cb_depth = row("Bit depth",    self._depth_var, [f"{d}-bit" for d in _BIT_DEPTHS], 2)
        self._cb_ch    = row("Channels",     self._ch_var,    _CHANNELS,     3)
        self._cb_br    = row("Bitrate",      self._br_var,    [f"{b} kbps" for b in _BITRATES], 4)

        # Separator
        tk.Frame(frame, bg=S.BG3, height=1).pack(fill='x', pady=(10, 6))

        # Estimated size display
        size_row = tk.Frame(frame, bg=S.BG2)
        size_row.pack(fill='x')
        tk.Label(size_row, text="Est. file size", font=S.FN_X, fg=S.TXT_DIM,
                 bg=S.BG2, width=13, anchor='w').pack(side='left')
        self._size_lbl = tk.Label(
            size_row, text="—", font=S.FN_S, fg=S.CYAN, bg=S.BG2,
        )
        self._size_lbl.pack(side='left', padx=(4, 0))

        # Duration display
        dur_row = tk.Frame(frame, bg=S.BG2)
        dur_row.pack(fill='x', pady=(2, 0))
        tk.Label(dur_row, text="Duration", font=S.FN_X, fg=S.TXT_DIM,
                 bg=S.BG2, width=13, anchor='w').pack(side='left')
        dur_s = int(self._duration_sec)
        dur_str = f"{dur_s // 60:02d}:{dur_s % 60:02d}" if dur_s > 0 else "—"
        tk.Label(dur_row, text=dur_str, font=S.FN_X, fg=S.TXT, bg=S.BG2).pack(side='left', padx=(4, 0))

        # ffmpeg warning (shown when MP3/FLAC/OGG requested without ffmpeg)
        self._warn_var = tk.StringVar()
        self._warn_lbl = tk.Label(
            frame, textvariable=self._warn_var,
            font=S.FN_X, fg=S.YELLOW, bg=S.BG2,
            wraplength=320, justify='left', anchor='w',
        )
        self._warn_lbl.pack(fill='x', pady=(8, 0))

    # ── Preset selection logic ─────────────────────────────────────────────────

    def _select_preset(self, idx: int) -> None:
        """Highlight preset row *idx*, populate the settings dropdowns, refresh size."""
        S  = self._S
        self._selected_idx = idx
        preset = DEFAULT_PRESETS[idx]

        # Highlight selected row; reset others
        for i, row in enumerate(self._preset_rows):
            row.configure(bg=S.CYAN if i == idx else row._bg_normal)

        # Update description
        self._desc_var.set(preset.description)

        # Populate dropdowns without triggering _on_setting_change
        self._updating = True
        self._fmt_var.set(preset.fmt.value.upper())
        self._rate_var.set(str(preset.sample_rate))
        self._depth_var.set(f"{preset.bit_depth}-bit")
        self._ch_var.set("Stereo" if preset.channels == 2 else "Mono")
        self._br_var.set(f"{preset.bitrate_kbps} kbps" if preset.bitrate_kbps else "320 kbps")
        self._updating = False

        # Enable / disable bit-depth and bitrate based on format
        is_lossy = preset.fmt in (AudioFormat.MP3, AudioFormat.OGG)
        self._cb_depth.configure(state='disabled' if is_lossy else 'readonly')
        self._cb_br.configure(state='disabled'    if not is_lossy else 'readonly')

        # Auto-update the filename extension
        self._update_filename_extension(preset.fmt.value)

        # ffmpeg warning
        if preset.fmt != AudioFormat.WAV and not self._has_ffmpeg:
            self._warn_var.set(
                f"⚠  {preset.fmt.value.upper()} requires ffmpeg, which was not found on "
                "PATH.  Install ffmpeg to enable this format."
            )
        else:
            self._warn_var.set('')

        self._refresh_sizes()

    def _on_setting_change(self, _event=None) -> None:
        """
        Called when the user changes a dropdown manually.

        Deselects all presets (shows custom state) and refreshes the size estimate.
        """
        if self._updating:
            return
        # Deselect all preset rows
        S = self._S
        for row in self._preset_rows:
            row.configure(bg=row._bg_normal)
        self._selected_idx = -1
        self._desc_var.set("Custom settings")

        # Enable/disable bit-depth and bitrate based on selected format
        fmt_str = self._fmt_var.get()
        is_lossy = fmt_str in ('MP3', 'OGG')
        self._cb_depth.configure(state='disabled' if is_lossy else 'readonly')
        self._cb_br.configure(state='disabled'    if not is_lossy else 'readonly')

        # Update filename extension
        fmt_val = _FORMAT_MAP.get(fmt_str, AudioFormat.WAV).value
        self._update_filename_extension(fmt_val)

        # ffmpeg warning
        needs_ffmpeg = fmt_str in ('MP3', 'FLAC', 'OGG')
        if needs_ffmpeg and not self._has_ffmpeg:
            self._warn_var.set(
                f"⚠  {fmt_str} requires ffmpeg, which was not found on PATH."
            )
        else:
            self._warn_var.set('')

        self._refresh_sizes()

    # ── Size estimation ───────────────────────────────────────────────────────

    def _refresh_sizes(self) -> None:
        """
        Recompute file size estimates for every preset row and the custom
        settings panel, then update all labels.
        """
        # Update each preset row's size label
        for idx, (row, preset) in enumerate(zip(self._preset_rows, DEFAULT_PRESETS)):
            sz = estimate_size_bytes(preset, self._duration_sec)
            row._size_var.set(format_size(sz))

        # Update the custom settings size label
        custom = self._build_preset_from_settings()
        if custom:
            sz = estimate_size_bytes(custom, self._duration_sec)
            self._size_lbl.config(text=format_size(sz))
        else:
            self._size_lbl.config(text='—')

    def _build_preset_from_settings(self) -> Optional[ExportPreset]:
        """
        Read the current custom settings dropdowns and return an ExportPreset.
        Returns None when a value cannot be parsed.
        """
        try:
            fmt_str  = self._fmt_var.get()
            fmt      = _FORMAT_MAP.get(fmt_str, AudioFormat.WAV)
            rate     = int(self._rate_var.get())
            depth    = int(self._depth_var.get().replace('-bit', ''))
            channels = 2 if self._ch_var.get() == 'Stereo' else 1
            bitrate  = int(self._br_var.get().replace(' kbps', ''))
            return ExportPreset(
                name='Custom', description='', fmt=fmt,
                sample_rate=rate, bit_depth=depth,
                channels=channels, bitrate_kbps=bitrate,
            )
        except Exception:
            return None

    # ── Filename helpers ──────────────────────────────────────────────────────

    def _default_filename(self) -> str:
        """Generate a sensible default filename from the composition config."""
        if self._composition:
            cfg   = self._composition.get('config', {})
            genre = cfg.get('genre', 'song')
            n     = self._gen_number
            return f"{genre}_song_{n:03d}"
        return "seed_composer_export"

    def _default_folder(self) -> str:
        """Default output folder: Music/SeedComposerExports in the user's home dir."""
        home = Path.home()
        folder = home / "Music" / "SeedComposerExports"
        return str(folder)

    def _update_filename_extension(self, ext: str) -> None:
        """
        Replace the extension in the filename entry when the format changes.
        Leaves the base name intact.
        """
        current = self._filename_var.get()
        base    = current.rsplit('.', 1)[0] if '.' in current else current
        self._filename_var.set(f"{base}.{ext}")

    def _browse_folder(self) -> None:
        """Open a folder-picker dialog and update the folder entry."""
        folder = filedialog.askdirectory(
            title       = "Choose export folder",
            initialdir  = self._folder_var.get(),
        )
        if folder:
            self._folder_var.set(folder)

    # ── Export action ─────────────────────────────────────────────────────────

    def _on_export(self) -> None:
        """
        Validate inputs, build the output path, and run the converter in a
        background thread so the dialog stays responsive.
        """
        if not self._source_wav or not os.path.exists(self._source_wav):
            messagebox.showerror(
                "No audio", "No rendered WAV file found.\nGenerate a song first.",
                parent=self,
            )
            return

        # Build destination path
        filename = self._filename_var.get().strip()
        folder   = self._folder_var.get().strip()
        if not filename:
            messagebox.showerror("Missing filename", "Please enter a filename.", parent=self)
            return
        if not folder:
            messagebox.showerror("Missing folder", "Please choose an output folder.", parent=self)
            return

        # Ensure folder exists before starting
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as exc:
            messagebox.showerror("Folder error", str(exc), parent=self)
            return

        # Resolve preset
        if self._selected_idx >= 0:
            preset = DEFAULT_PRESETS[self._selected_idx]
        else:
            preset = self._build_preset_from_settings()
            if preset is None:
                messagebox.showerror("Settings error", "Could not read export settings.", parent=self)
                return

        # Ensure filename has the correct extension
        base = filename.rsplit('.', 1)[0] if '.' in filename else filename
        dst  = os.path.join(folder, f"{base}.{preset.fmt.value}")

        # Warn if the file already exists
        if os.path.exists(dst):
            if not messagebox.askyesno(
                "Overwrite?",
                f"{os.path.basename(dst)} already exists.\nOverwrite it?",
                parent=self,
            ):
                return

        # Show progress bar and disable the export button
        self._prog_frame.pack(fill='x', padx=10, pady=(4, 0))
        self._prog_var.set(0)
        self._prog_lbl.config(text=f"Exporting → {os.path.basename(dst)} …")
        self._export_btn.config(state='disabled', text="Exporting…")
        self.update_idletasks()

        # Read mastering settings on the main thread before handing off
        mastering_enabled   = False
        mastering_target_id = 'streaming'
        if _MASTERING_AVAILABLE and self._mastering_panel is not None:
            ms_settings         = self._mastering_panel.get_settings()
            mastering_enabled   = ms_settings.get('enabled', False)
            mastering_target_id = ms_settings.get('target_id', 'streaming')

        # Run conversion off the main thread to keep the UI alive
        thread = threading.Thread(
            target=self._run_export,
            args=(preset, dst, mastering_enabled, mastering_target_id),
            daemon=True,
        )
        thread.start()

    def _run_export(self, preset: ExportPreset, dst: str,
                    mastering_enabled: bool = False,
                    mastering_target_id: str = 'streaming') -> None:
        """
        Worker thread: optionally apply mastering chain, then convert and write.

        When mastering is enabled the full DSP chain (EQ → compression →
        parallel compression → M/S → LUFS normalisation → limiter) is applied
        to a temp WAV before the format converter runs.  The temp file is
        cleaned up whether the conversion succeeds or fails.
        """
        def progress_cb(fraction: float):
            self._prog_var.set(fraction * 100)

        src = self._source_wav
        tmp_mastered = None

        try:
            if mastering_enabled and _MASTERING_AVAILABLE:
                self.after(0, lambda: self._prog_lbl.config(
                    text="Applying mastering chain…"
                ))
                genre = 'pop'
                if self._composition:
                    genre = self._composition.get('config', {}).get('genre', 'pop')

                # Write mastered audio to a temp file; ffmpeg converts from there
                fd, tmp_mastered = tempfile.mkstemp(suffix='_mastered.wav')
                import os as _os; _os.close(fd)

                chain = MasteringChain()
                ok_m, msg_m = chain.process(
                    wav_in     = src,
                    wav_out    = tmp_mastered,
                    genre      = genre,
                    variant_id = self._variant_id,
                    target_id  = mastering_target_id,
                )
                if ok_m:
                    self._log(f"  Mastering: {msg_m}")
                    src = tmp_mastered   # feed the mastered WAV to ffmpeg
                else:
                    self._log(f"  Mastering skipped ({msg_m}) — exporting dry signal")

            ok, message = convert(src, dst, preset, on_progress=progress_cb)

        finally:
            # Always clean up the intermediate mastered temp file
            if tmp_mastered and tmp_mastered != src:
                try:
                    import os as _os
                    if _os.path.exists(tmp_mastered):
                        _os.unlink(tmp_mastered)
                except Exception:
                    pass

        # Schedule result handling on the main (Tkinter) thread
        self.after(0, lambda: self._on_export_done(ok, message, dst))

    def _on_export_done(self, ok: bool, message: str, dst: str) -> None:
        """Called on the main thread after conversion completes."""
        self._export_btn.config(state='normal', text="  EXPORT  ")
        self._prog_var.set(100 if ok else 0)

        if ok:
            self._prog_lbl.config(text=f"✓ {message}")
            self._log(f"✓ Export: {dst}\n  {message}")
            messagebox.showinfo(
                "Export complete",
                f"Saved to:\n{dst}\n\n{message}",
                parent=self,
            )
            self.destroy()
        else:
            self._prog_lbl.config(text=f"✗ Export failed")
            self._log(f"✗ Export failed: {message}")
            messagebox.showerror(
                "Export failed",
                message,
                parent=self,
            )

    # ── Cancel ────────────────────────────────────────────────────────────────

    def _on_cancel(self) -> None:
        """Close the dialog without exporting."""
        self.destroy()
