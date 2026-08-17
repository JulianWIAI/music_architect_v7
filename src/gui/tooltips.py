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

    # ── Production Advisor — Palette selector ─────────────────────────────
    'advisor_palette': (
        "Active instrument palette — a curated set of instruments and effect\n"
        "chain adjustments for this genre.  Switching palettes changes the\n"
        "kick description, BDRA branch, instrument defaults in the builder,\n"
        "and the base chain_delta shown in the advisor and PDF guide."
    ),

    # ── Production Advisor — Query panel ──────────────────────────────────
    'advisor_genre': (
        "Genre to look up.\n"
        "Sets the palette, effect chain, BPM bucket, gain targets, and\n"
        "frequency allocation shown in the advisor output."
    ),
    'advisor_bpm': (
        "Tempo of your MIDI file in beats per minute (40–240).\n"
        "Used to match the correct BPM bucket and delay/reverb time targets."
    ),
    'advisor_key_root': "Root note of the key (e.g. C, F#, Bb).",
    'advisor_key_mode': (
        "Scale / mode of the key.\n"
        "Major = bright, energetic  |  Minor = darker, emotional\n"
        "Shown in the advisor output for reference; does not restrict palettes."
    ),
    'advisor_get_recommendations': (
        "Load full production recommendations for the genre / BPM / key\n"
        "you entered — without running the composition engine.\n"
        "Useful for any external MIDI file you already have."
    ),

    # ── Production Advisor — Instrument Builder ────────────────────────────
    'advisor_kick': (
        "Kick type — determines the timbral Branch (A / B / C).\n"
        "  Branch A  Pure sine / 808  — sub-focused, electronic\n"
        "  Branch B  Acoustic layered — natural, punchy transient\n"
        "  Branch C  Sub-boom / taiko — deep, orchestral impact\n"
        "All track comboboxes are filtered live to show only\n"
        "instruments that are compatible with the selected branch."
    ),
    'advisor_score': (
        "BDRA compatibility score (0–100).\n"
        "Measures how well the selected instruments satisfy the five\n"
        "psychoacoustic principles:\n"
        "  P1  Sub-bass exclusivity   — only one source below 80 Hz\n"
        "  P2  Register monotonicity  — roles occupy ascending spectral layers\n"
        "  P3  Attack contrast        — adjacent voices differ in onset time\n"
        "  P4  Density headroom       — total texture stays below masking threshold\n"
        "  P5  Timbral complementarity — kick and bass share a compatible profile\n"
        "Green ≥ 90  ·  Yellow ≥ 70  ·  Orange ≥ 50  ·  Red < 50"
    ),
    'advisor_apply': (
        "Copy the current instrument selection to the\n"
        "TRACKS & INSTRUMENTS panel in the Seed Composer.\n"
        "The next generation will use these exact GM programs."
    ),

    # ── Production Advisor — FX Variant panel ────────────────────────────
    'advisor_variant_bright': (
        "BRIGHT variant — a cleaner, more polished production flavour.\n"
        "Applies: air shelf +2-4 dB above 8 kHz (Fletcher-Munson equal-\n"
        "loudness compensation), shorter reverb pre-delays for transient\n"
        "clarity, and a higher reverb HPF for a brighter room tail."
    ),
    'advisor_variant_neutral': (
        "NEUTRAL variant — the genre reference chain with no modifications.\n"
        "Use this as the baseline before auditioning bright or dark flavours.\n"
        "Identical to the raw JSON effect chain for the selected genre."
    ),
    'advisor_variant_dark': (
        "DARK variant — a warmer, more saturated production flavour.\n"
        "Applies: tape saturation +2-5 dB (adds 2nd/3rd harmonic density),\n"
        "longer reverb decay tails (Haas-effect depth), and a lower reverb\n"
        "HPF for a darker, more atmospheric room character."
    ),

    # ── Production Advisor — Action strip ─────────────────────────────────
    'advisor_preview': (
        "Re-compose the beat with the pinned seed and currently selected\n"
        "instruments, render WAV via FluidSynth, then auto-play.\n"
        "Falls back to MIDI playback if FluidSynth is unavailable.\n"
        "The chosen SoundFont (see SOUNDFONT row above) is used for rendering."
    ),
    'advisor_save_wav': (
        "Save the FluidSynth-rendered WAV of this advisor preview.\n"
        "Enabled only after a successful preview render.\n"
        "The WAV uses the SoundFont and instruments selected in the advisor."
    ),
    'advisor_save_midi': (
        "Save the full-beat MIDI with program_change events for the\n"
        "currently selected instruments embedded.\n"
        "Available immediately after preview — no WAV render required."
    ),
    'advisor_save_vocal_midi': (
        "Save the vocal-ready MIDI scaffold (vocal_mask=True).\n"
        "Melody is collapsed to a monophonic lead line; the C4–C6 register\n"
        "is cleared in verse/chorus/hook sections for a vocalist to record over.\n"
        "Enabled when the Vocal-Ready checkbox is ticked before previewing."
    ),
    'advisor_export_pdf': (
        "Export a 10-section printable A4 production guide (PDF or .txt).\n"
        "Sections: palette, instruments, BPM targets, gain staging, effect\n"
        "chains, frequency allocation, parallel compression, M/S mastering.\n"
        "Falls back to a UTF-8 .txt file if fpdf2 is not installed."
    ),

    # ── Production Advisor — SoundFont picker ─────────────────────────────
    'advisor_sf_browse': (
        "Browse to any .sf2 SoundFont file on your computer.\n"
        "The selected font is used for all FluidSynth previews\n"
        "until you click 'Genre auto'.  Your choice is saved between sessions.\n"
        "Try commercial fonts (e.g. SGM-v2.01, Vienna Lite) to compare timbres."
    ),
    'advisor_sf_auto': (
        "Revert to automatic SoundFont routing by genre:\n"
        "  Fluid R3 GM      → trap · hip-hop · techno · dnb · phonk\n"
        "  GeneralUser GS   → pop · j-pop · edm · house\n"
        "  Arachno SF v1.0  → cinematic · classical"
    ),
    'advisor_sf_pro': (
        "Professional SoundFont mode.\n"
        "Applies the full mastering chain: genre EQ, bus compressor,\n"
        "LUFS normalisation, and true-peak limiter.\n"
        "Use for high-quality GM fonts (Crisis, SGM, MuseScore General, etc.)."
    ),
    'advisor_sf_retro': (
        "Retro / Game SoundFont mode.\n"
        "Bypasses the mastering chain and reduces gain so that 8-bit\n"
        "game SoundFonts (Mario, SNES-era, etc.) do not clip or distort.\n"
        "Chorus and reverb are also tamed to avoid harsh beating artifacts."
    ),
}
