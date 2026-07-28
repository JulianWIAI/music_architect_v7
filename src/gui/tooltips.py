"""
tooltips.py — Hover tooltip widget and text definitions for Seed Composer.

Provides:
  - ToolTip: attaches a popup help text to any Tkinter widget on <Enter>/<Leave>
  - TOOLTIPS: dict mapping widget keys to human-readable explanations
"""

import tkinter as tk


class ToolTip:
    """
    Displays a small floating label when the user hovers over a widget.

    Usage:
        ToolTip(widget, "This button does X")
    """

    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self._tip_window: tk.Toplevel | None = None
        widget.bind('<Enter>', self._show)
        widget.bind('<Leave>', self._hide)

    def _show(self, event=None):
        if self._tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)          # No title bar / decorations
        tw.wm_geometry(f"+{x}+{y}")
        # Tooltip label styled to match the cyberpunk dark theme
        tk.Label(
            tw,
            text=self.text,
            justify='left',
            background="#1a1a50",
            foreground="#d0d8f0",
            font=("Consolas", 8),
            relief='solid',
            borderwidth=1,
            wraplength=320,
            padx=6,
            pady=4,
        ).pack()

    def _hide(self, event=None):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


# ─────────────────────────────────────────────────────────────────────────────
# Tooltip text registry — key → description shown on hover
# ─────────────────────────────────────────────────────────────────────────────

TOOLTIPS: dict[str, str] = {
    # ── Seed Database ──────────────────────────────────────────────────────
    'dataset_entry': (
        "Path to your CSV dataset root folder.\n"
        "Expected structure:\n"
        "  root/<source>/<song_id>/time_data.csv\n"
        "  root/<source>/<song_id>/chords.csv\n"
        "  root/<source>/<song_id>/timeline.csv"
    ),
    'seeds_entry': (
        "Folder where generated seed JSON files are saved and loaded from.\n"
        "Default: <project>/seeds/"
    ),
    'btn_build_seeds': (
        "Scan all CSV triples in your dataset and build seed JSON files.\n"
        "Extracts BPM, key, chord transitions, and instrument patterns from each song.\n"
        "Only needed when you have new training data."
    ),
    'btn_load_seeds': (
        "Load existing seed JSON files from the Seeds Dir.\n"
        "Seeds guide the composer toward real music patterns.\n"
        "You can generate without seeds using music-theory fallback mode."
    ),

    # ── Genre ──────────────────────────────────────────────────────────────
    'genre': (
        "Select the musical genre.\n"
        "Each genre sets unique BPM ranges, scales, instrumentation and rhythmic patterns."
    ),

    # ── Parameters ─────────────────────────────────────────────────────────
    'bpm_auto': (
        "Auto/Random: BPM is picked randomly within the genre's typical range.\n"
        "Uncheck to lock a specific tempo."
    ),
    'bpm_scale': (
        "Beats Per Minute — controls the tempo.\n"
        "40 = very slow ballad   |   120 = dance   |   200 = very fast"
    ),
    'key_auto': (
        "Auto/Random: the musical key is chosen randomly.\n"
        "Uncheck to fix the root note and mode."
    ),
    'key_root': "Root note of the musical key (e.g. C, F#, Bb).",
    'key_mode': (
        "Major = bright, energetic sound.\n"
        "Minor = darker, emotional sound."
    ),
    'chord_auto': (
        "Auto/Random: the starting chord is derived automatically from the key.\n"
        "Uncheck to force a specific starting chord."
    ),
    'chord_root': "Root note of the first chord in the progression.",
    'chord_quality': (
        "Chord quality:\n"
        "  maj7  = warm, jazzy\n"
        "  m     = minor (sad/dark)\n"
        "  7     = dominant (tension)\n"
        "  sus4  = suspended (floating)\n"
        "  dim   = diminished (dissonant)"
    ),
    'complexity_scale': (
        "Controls how dense and layered the composition is.\n"
        "  0  = minimal / ambient\n"
        "  5  = balanced (recommended)\n"
        " 10  = dense, many notes and layers"
    ),
    'humanize_scale': (
        "Adds subtle timing and velocity variations to feel more human.\n"
        "  0   = perfectly quantized (robotic grid)\n"
        " 60   = natural feel (recommended)\n"
        "100   = maximum groove / looseness"
    ),
    'mutation_scale': (
        "How much patterns deviate from learned seed conventions.\n"
        "  SAFE (0–30%)  = stays close to genre rules\n"
        "  MID  (30–70%) = creative variations\n"
        "  CHAOS (70–100%) = experimental, unpredictable"
    ),
    'seed_entry': (
        "Numeric seed for the random number generator.\n"
        "Same seed + same settings = exact same song every time.\n"
        "Leave empty to get a different result each generation."
    ),
    'btn_rand_seed': "Generate a new random seed value.",

    # ── Tracks & Instruments ───────────────────────────────────────────────
    'track_enabled': "Enable or disable this instrument track.",
    'track_volume': "Volume for this track (0 = silent, 100 = full).",
    'track_instrument': "GM (General MIDI) instrument for this track.",
    'btn_rand_instrument': "Pick a random instrument suited to this track's role.",
    'btn_randomize_all': "Randomize ALL instrument assignments at once.",

    # ── Generate ───────────────────────────────────────────────────────────
    'prompt_entry': (
        "Describe your track in plain English — the AI decoder sets parameters for you.\n"
        "Examples:\n"
        "  'dark aggressive trap at 140 bpm'\n"
        "  'slow chill lofi with piano'\n"
        "  'euphoric edm drop in C major'\n"
        "Press Enter or Generate after typing."
    ),
    'btn_generate': (
        "Compose a new song with the current settings.\n"
        "Generation is fast — WAV audio can be rendered separately via the WAV button."
    ),
    'btn_batch': (
        "Generate 5 songs at once with randomised parameter variations.\n"
        "All songs are exported as MIDI files to the /cinematic_batch folder.\n"
        "Much faster than generating one at a time."
    ),

    # ── Output / Playback ──────────────────────────────────────────────────
    'btn_play': (
        "Preview the last generated composition.\n"
        "Plays MIDI directly — no WAV rendering needed."
    ),
    'btn_stop': "Stop current playback.",
    'btn_midi': "Save the composition as a .mid MIDI file.",
    'btn_wav': (
        "Render and save as a .wav audio file.\n"
        "Requires FluidSynth. Rendering may take a few seconds."
    ),
    'btn_json': (
        "Export the full composition data as JSON.\n"
        "Includes all notes, structure, chord progressions and metadata."
    ),
}
