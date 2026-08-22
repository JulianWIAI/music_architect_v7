"""
src/gui/piano_roll.py
---------------------
Read-only piano roll visualization widget for Music Architect V7.

Renders a composition dict as colored note rectangles on a scrollable
Tkinter canvas. The piano keyboard strip on the left scrolls vertically
in sync with the main note canvas. A row of track toggle buttons sits
above the canvas area.

Public API::

    widget = PianoRollWidget(parent_frame)
    widget.frame.pack(fill='both', expand=True)
    widget.load(composition_dict)   # call after generation
    widget.clear()                  # reset to empty state
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Set, Tuple

from src.gui.styles import S

# ── Layout constants ─────────────────────────────────────────────────────────
PIANO_KEY_W     = 36   # px — fixed left keyboard strip width
PIXELS_PER_BEAT = 40   # px — one beat = 40 pixels horizontally
NOTE_HEIGHT     = 7    # px — height of one semitone row
MIDI_LOW        = 21   # lowest MIDI note shown (A0)
MIDI_HIGH       = 108  # highest MIDI note shown (C8)
NUM_NOTES       = MIDI_HIGH - MIDI_LOW + 1   # 88 notes
TOTAL_HEIGHT    = NUM_NOTES * NOTE_HEIGHT    # canvas height in pixels
BAR_MARKER_H    = 16   # px — height of bar number header strip

# ── Track name → display key mapping ─────────────────────────────────────────
_COMP_TO_DISPLAY: Dict[str, str] = {
    '01_Kick':       'drums',
    '02_Percussion': 'percussion',
    '03_Bass':       'bass',
    '04_Melody':     'lead',
    '05_Chords':     'chords',
    '06_Pad':        'pad',
    '07_Arp':        'arp',
    '08_Stabs':      'stabs',
    '09_Texture':    'texture',
    '10_FX':         'fx',
}

# Ordered list of display keys for the toggle button row
_DISPLAY_ORDER: List[str] = [
    'drums', 'percussion', 'bass', 'lead', 'chords',
    'pad', 'arp', 'stabs', 'texture', 'fx',
]

# ── MIDI note helpers ─────────────────────────────────────────────────────────
# Black key pattern within an octave (0=C,1=C#,...,11=B)
_BLACK_KEYS: Set[int] = {1, 3, 6, 8, 10}

# Note name labels (C only) — used for octave labels on piano strip
_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _midi_to_y(midi: int) -> int:
    """Convert a MIDI note number to the top-y pixel on the note canvas."""
    # MIDI_HIGH is at y=0; notes decrease downward
    return (MIDI_HIGH - midi) * NOTE_HEIGHT


def _note_is_black(midi: int) -> bool:
    """Return True if the MIDI note corresponds to a black piano key."""
    return (midi % 12) in _BLACK_KEYS


class PianoRollWidget:
    """
    Read-only piano roll widget.

    Attributes
    ----------
    frame : tk.Frame
        The root frame to pack into the parent container.
    """

    def __init__(self, parent: tk.Frame) -> None:
        # Root frame — caller packs this
        self.frame = tk.Frame(parent, bg=S.BG2)

        # Internal state
        self._composition: Optional[dict] = None
        self._active_tracks: Set[str] = set(_DISPLAY_ORDER)  # all on by default
        self._toggle_btns: Dict[str, tk.Button] = {}
        self._total_bars: int = 0

        # Build all sub-widgets
        self._build_toggle_row()
        self._build_canvas_area()

        # Start in empty state
        self.clear()

    # ─────────────────────────────────────────────────────────────────────────
    #  Public API
    # ─────────────────────────────────────────────────────────────────────────

    def load(self, composition: dict) -> None:
        """Load a new composition dict and redraw the piano roll."""
        self._composition = composition
        self._total_bars  = int(composition.get('total_bars', 0))
        self._redraw()

    def clear(self) -> None:
        """Clear the canvas and show placeholder text."""
        self._composition = None
        self._total_bars  = 0
        self._key_canvas.delete('all')
        self._note_canvas.delete('all')
        # Show empty-state message centered in note canvas
        self._note_canvas.create_text(
            320, TOTAL_HEIGHT // 2,
            text="Generate a composition to see the piano roll.",
            fill=S.TXT_DIM,
            font=S.FN_S,
            anchor='center',
        )
        # Draw a faint piano keyboard in the key strip even in empty state
        self._draw_piano_keys()

    # ─────────────────────────────────────────────────────────────────────────
    #  Widget construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_toggle_row(self) -> None:
        """Build the row of track toggle buttons above the canvas."""
        row = tk.Frame(self.frame, bg=S.BG2)
        row.pack(fill='x', padx=2, pady=(2, 0))

        for key in _DISPLAY_ORDER:
            color = S.TRACK_CLR.get(key, S.TXT)
            btn = tk.Button(
                row,
                text=key.upper(),
                font=S.FN_XS,
                fg=color,
                bg=S.BG3,
                bd=0,
                padx=5,
                pady=3,
                relief='flat',
                cursor='hand2',
                activebackground=S.BG_INPUT,
                activeforeground=color,
                command=lambda k=key: self._toggle_track(k),
            )
            btn.pack(side='left', padx=1, pady=1)
            self._toggle_btns[key] = btn

        # Spacer
        tk.Frame(row, bg=S.BG2, width=8).pack(side='left')

        # All / None utility buttons
        tk.Button(
            row, text='All', font=S.FN_XS, fg=S.TXT, bg=S.BG3,
            bd=0, padx=6, pady=3, relief='flat', cursor='hand2',
            activebackground=S.BG_INPUT, activeforeground=S.TXT_BRT,
            command=self._activate_all,
        ).pack(side='left', padx=1, pady=1)

        tk.Button(
            row, text='None', font=S.FN_XS, fg=S.TXT_DIM, bg=S.BG3,
            bd=0, padx=6, pady=3, relief='flat', cursor='hand2',
            activebackground=S.BG_INPUT, activeforeground=S.TXT,
            command=self._deactivate_all,
        ).pack(side='left', padx=1, pady=1)

    def _build_canvas_area(self) -> None:
        """Build the piano key strip and scrollable note canvas."""
        # Outer frame holds: [key_strip | note_canvas | vscrollbar]
        canvas_outer = tk.Frame(self.frame, bg=S.BG)
        canvas_outer.pack(fill='both', expand=True, padx=2, pady=(2, 0))

        # ── Left: fixed piano key strip ──────────────────────────────────────
        self._key_canvas = tk.Canvas(
            canvas_outer,
            width=PIANO_KEY_W,
            bg=S.BG3,
            highlightthickness=0,
            bd=0,
        )
        self._key_canvas.pack(side='left', fill='y')

        # Configure scrollregion for key canvas (scrolled vertically only)
        self._key_canvas.configure(scrollregion=(0, 0, PIANO_KEY_W, TOTAL_HEIGHT))

        # ── Right: scrollable note canvas + vertical scrollbar ────────────────
        right_frame = tk.Frame(canvas_outer, bg=S.BG)
        right_frame.pack(side='left', fill='both', expand=True)

        self._note_canvas = tk.Canvas(
            right_frame,
            bg=S.BG,
            highlightthickness=0,
            bd=0,
        )
        self._note_canvas.grid(row=0, column=0, sticky='nsew')

        self._vscroll = ttk.Scrollbar(
            right_frame, orient='vertical',
            command=self._scroll_both_y,
        )
        self._vscroll.grid(row=0, column=1, sticky='ns')

        self._hscroll = ttk.Scrollbar(
            right_frame, orient='horizontal',
            command=self._note_canvas.xview,
        )
        self._hscroll.grid(row=1, column=0, sticky='ew')

        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)

        # Link scrollbars to canvases
        self._note_canvas.configure(
            xscrollcommand=self._hscroll.set,
            yscrollcommand=self._on_yscroll,
        )
        self._key_canvas.configure(
            yscrollcommand=self._on_yscroll,
        )

        # Mouse-wheel scrolling — bind on both canvases, sync both
        self._key_canvas.bind('<Enter>',  self._bind_mousewheel)
        self._key_canvas.bind('<Leave>',  self._unbind_mousewheel)
        self._note_canvas.bind('<Enter>', self._bind_mousewheel)
        self._note_canvas.bind('<Leave>', self._unbind_mousewheel)

        # Scroll to show middle C (MIDI 60) area by default after the widget
        # is first mapped so the scrollregion is known.
        self.frame.bind('<Map>', self._scroll_to_middle_c, add='+')

    # ─────────────────────────────────────────────────────────────────────────
    #  Scroll helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _scroll_both_y(self, *args) -> None:
        """Vertical scrollbar command — moves both canvases together."""
        self._key_canvas.yview(*args)
        self._note_canvas.yview(*args)

    def _on_yscroll(self, lo: str, hi: str) -> None:
        """Called by either canvas when its yview changes; updates scrollbar."""
        self._vscroll.set(lo, hi)

    def _bind_mousewheel(self, _event=None) -> None:
        """Bind mouse-wheel to scroll both canvases vertically."""
        if sys.platform == 'win32':
            self._key_canvas.bind_all('<MouseWheel>', self._on_mousewheel_win)
            self._note_canvas.bind_all('<MouseWheel>', self._on_mousewheel_win)
        elif sys.platform == 'darwin':
            self._key_canvas.bind_all('<MouseWheel>', self._on_mousewheel_mac)
            self._note_canvas.bind_all('<MouseWheel>', self._on_mousewheel_mac)
        else:
            self._key_canvas.bind_all('<Button-4>', self._on_scroll_up)
            self._key_canvas.bind_all('<Button-5>', self._on_scroll_down)
            self._note_canvas.bind_all('<Button-4>', self._on_scroll_up)
            self._note_canvas.bind_all('<Button-5>', self._on_scroll_down)

    def _unbind_mousewheel(self, _event=None) -> None:
        """Remove mouse-wheel bindings when pointer leaves the canvas area."""
        for canvas in (self._key_canvas, self._note_canvas):
            canvas.unbind_all('<MouseWheel>')
            canvas.unbind_all('<Button-4>')
            canvas.unbind_all('<Button-5>')

    def _on_mousewheel_win(self, event) -> None:
        units = int(-1 * event.delta / 120)
        self._key_canvas.yview_scroll(units, 'units')
        self._note_canvas.yview_scroll(units, 'units')

    def _on_mousewheel_mac(self, event) -> None:
        units = int(-1 * event.delta)
        self._key_canvas.yview_scroll(units, 'units')
        self._note_canvas.yview_scroll(units, 'units')

    def _on_scroll_up(self, _event=None) -> None:
        self._key_canvas.yview_scroll(-3, 'units')
        self._note_canvas.yview_scroll(-3, 'units')

    def _on_scroll_down(self, _event=None) -> None:
        self._key_canvas.yview_scroll(3, 'units')
        self._note_canvas.yview_scroll(3, 'units')

    def _scroll_to_middle_c(self, _event=None) -> None:
        """Scroll vertically so that middle C (MIDI 60) is roughly centred."""
        # Fraction of scrollregion that corresponds to MIDI 60
        y_mid_c = _midi_to_y(60)
        frac = y_mid_c / max(TOTAL_HEIGHT, 1)
        # Offset by half a visible window so middle C appears near centre
        frac = max(0.0, frac - 0.35)
        self._key_canvas.yview_moveto(frac)
        self._note_canvas.yview_moveto(frac)

    # ─────────────────────────────────────────────────────────────────────────
    #  Toggle helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_track(self, key: str) -> None:
        """Toggle visibility of a single track and redraw."""
        if key in self._active_tracks:
            self._active_tracks.discard(key)
        else:
            self._active_tracks.add(key)
        self._update_toggle_btn_states()
        if self._composition is not None:
            self._redraw()

    def _activate_all(self) -> None:
        self._active_tracks = set(_DISPLAY_ORDER)
        self._update_toggle_btn_states()
        if self._composition is not None:
            self._redraw()

    def _deactivate_all(self) -> None:
        self._active_tracks.clear()
        self._update_toggle_btn_states()
        if self._composition is not None:
            self._redraw()

    def _update_toggle_btn_states(self) -> None:
        """Refresh button foreground colors to reflect active/inactive state."""
        for key, btn in self._toggle_btns.items():
            if key in self._active_tracks:
                btn.configure(fg=S.TRACK_CLR.get(key, S.TXT))
            else:
                btn.configure(fg=S.TXT_DIM)

    # ─────────────────────────────────────────────────────────────────────────
    #  Drawing
    # ─────────────────────────────────────────────────────────────────────────

    def _redraw(self) -> None:
        """Full redraw of both canvases from current composition + active tracks."""
        if self._composition is None:
            return

        total_beats = self._total_bars * 4
        total_width = max(total_beats * PIXELS_PER_BEAT, 160)

        # Update scroll regions
        self._note_canvas.configure(
            scrollregion=(0, 0, total_width, TOTAL_HEIGHT + BAR_MARKER_H),
        )
        self._key_canvas.configure(
            scrollregion=(0, 0, PIANO_KEY_W, TOTAL_HEIGHT + BAR_MARKER_H),
        )

        # Clear both canvases
        self._note_canvas.delete('all')
        self._key_canvas.delete('all')

        # Draw layers in order (back → front)
        self._draw_note_bg(total_width)
        self._draw_bar_markers(total_width, total_beats)
        self._draw_notes()
        self._draw_piano_keys()

    def _draw_note_bg(self, total_width: int) -> None:
        """Draw alternating light/dark horizontal bands (white vs black keys)."""
        for midi in range(MIDI_LOW, MIDI_HIGH + 1):
            y  = _midi_to_y(midi) + BAR_MARKER_H
            y2 = y + NOTE_HEIGHT
            if _note_is_black(midi):
                fill = '#1a1a20'   # darker band for black keys
            else:
                fill = '#202028'   # slightly lighter for white keys
            self._note_canvas.create_rectangle(
                0, y, total_width, y2,
                fill=fill, outline='',
            )
        # Draw faint horizontal grid lines at every C note boundary
        for midi in range(MIDI_LOW, MIDI_HIGH + 1):
            if midi % 12 == 0:   # C note
                y = _midi_to_y(midi) + BAR_MARKER_H
                self._note_canvas.create_line(
                    0, y, total_width, y,
                    fill='#383848', width=1,
                )

    def _draw_bar_markers(self, total_width: int, total_beats: int) -> None:
        """Draw bar number labels and vertical lines at every bar/beat."""
        # Beat lines (very faint)
        for beat in range(total_beats + 1):
            x = beat * PIXELS_PER_BEAT
            self._note_canvas.create_line(
                x, BAR_MARKER_H, x, TOTAL_HEIGHT + BAR_MARKER_H,
                fill='#2a2a34', width=1,
            )

        # Bar lines (brighter) and bar number labels
        for bar in range(self._total_bars + 1):
            x = bar * 4 * PIXELS_PER_BEAT
            self._note_canvas.create_line(
                x, 0, x, TOTAL_HEIGHT + BAR_MARKER_H,
                fill='#3a3a4a', width=1,
            )
            if bar < self._total_bars:
                self._note_canvas.create_text(
                    x + 4, BAR_MARKER_H // 2,
                    text=str(bar + 1),
                    fill=S.TXT_DIM,
                    font=S.FN_XS,
                    anchor='w',
                )

        # Horizontal separator between bar header and note area
        self._note_canvas.create_line(
            0, BAR_MARKER_H, total_width, BAR_MARKER_H,
            fill='#3a3a4a', width=1,
        )

    def _draw_notes(self) -> None:
        """Draw all note rectangles for active tracks."""
        comp      = self._composition
        tracks    = comp.get('tracks', {})
        track_info = comp.get('track_info', {})

        for comp_name, display_key in _COMP_TO_DISPLAY.items():
            if display_key not in self._active_tracks:
                continue
            notes = tracks.get(comp_name, [])
            if not notes:
                continue

            # Determine if this is a drum/percussion channel
            ch = track_info.get(comp_name, {}).get('channel', 0)
            is_drum = (ch == 9)

            base_color = S.TRACK_CLR.get(display_key, S.TXT)
            # Drums get a slightly brighter highlight since they are short hits
            fill_color = _brighten(base_color) if is_drum else base_color

            for note in notes:
                # note = (time_beats, dur_beats, pitch_midi, velocity)
                if len(note) < 4:
                    continue
                time_beats, dur_beats, pitch_midi, velocity = (
                    float(note[0]), float(note[1]), int(note[2]), int(note[3])
                )

                if pitch_midi < MIDI_LOW or pitch_midi > MIDI_HIGH:
                    continue

                x1 = int(time_beats * PIXELS_PER_BEAT)
                x2 = int((time_beats + dur_beats) * PIXELS_PER_BEAT) - 1
                y1 = _midi_to_y(pitch_midi) + BAR_MARKER_H
                y2 = y1 + NOTE_HEIGHT - 1

                # Minimum visible width for very short notes
                if x2 <= x1:
                    x2 = x1 + 2

                # Velocity-based alpha simulation: modulate lightness slightly
                v_factor = velocity / 127.0
                note_fill = _velocity_tint(fill_color, v_factor)

                self._note_canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=note_fill,
                    outline='',
                )

    def _draw_piano_keys(self) -> None:
        """Draw the 88-key piano keyboard in the left strip."""
        c = self._key_canvas
        offset_y = BAR_MARKER_H  # align with note canvas header offset

        # Draw white keys first (full width), then black keys on top
        # White key colors
        wh_fill  = '#c8c8d0'
        wh_line  = '#404050'
        bk_fill  = '#1e1e28'
        bk_line  = '#101018'

        for midi in range(MIDI_LOW, MIDI_HIGH + 1):
            y  = _midi_to_y(midi) + offset_y
            y2 = y + NOTE_HEIGHT

            if _note_is_black(midi):
                # Black key — narrower, drawn over white
                key_w = int(PIANO_KEY_W * 0.62)
                c.create_rectangle(
                    0, y, key_w, y2,
                    fill=bk_fill, outline=bk_line, width=0,
                )
            else:
                # White key — full width
                c.create_rectangle(
                    0, y, PIANO_KEY_W, y2,
                    fill=wh_fill, outline=wh_line, width=1,
                )
                # Label C notes
                if midi % 12 == 0:
                    octave = (midi // 12) - 1
                    c.create_text(
                        PIANO_KEY_W - 3, y + NOTE_HEIGHT // 2,
                        text=f'C{octave}',
                        fill='#484858',
                        font=S.FN_XS,
                        anchor='e',
                    )

        # Header spacer above keys (matches bar marker height)
        c.create_rectangle(
            0, 0, PIANO_KEY_W, offset_y,
            fill=S.BG3, outline='',
        )


# ── Color utility helpers ─────────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Parse '#rrggbb' → (r, g, b)."""
    h = hex_color.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """(r, g, b) → '#rrggbb'."""
    return f'#{r:02x}{g:02x}{b:02x}'


def _brighten(hex_color: str, factor: float = 1.35) -> str:
    """Return a brightened version of a hex color (clamped to 255)."""
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(
        min(255, int(r * factor)),
        min(255, int(g * factor)),
        min(255, int(b * factor)),
    )


def _velocity_tint(hex_color: str, v: float) -> str:
    """
    Modulate note brightness based on velocity fraction (0.0 – 1.0).

    Low-velocity notes are rendered slightly darker; full-velocity notes
    use the track color as-is. Range kept subtle (0.70 – 1.00).
    """
    scale = 0.70 + 0.30 * v
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(
        min(255, int(r * scale)),
        min(255, int(g * scale)),
        min(255, int(b * scale)),
    )
