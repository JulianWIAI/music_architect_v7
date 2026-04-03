"""
═══════════════════════════════════════════════════════════════════════
  ◢ SEED COMPOSER — CYBERPUNK EDITION v2 ◣
  AI-Powered Music Generation Studio
  
  Fixes in v2:
  - Permission error fixed (stops playback before regenerating)
  - All 128 GM instruments available
  - Drum kit selection (Standard, Room, Power, Electronic, etc.)
  - Auto = truly random BPM/key/chord (not fixed)
  - Random instrument button per track
  - Clear seed file location display
  - Supports nested dataset folder structure
═══════════════════════════════════════════════════════════════════════
"""

import sys
import os
import threading
import queue
import random
import json
import math
import time as time_module
import uuid
from pathlib import Path
from typing import Optional, Dict

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# When frozen as a single .exe, output files go next to the .exe, not in a temp folder
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from composition_engine import (
        CompositionEngine, CompositionConfig, GENRE_BPM,
        GENRE_INSTRUMENTS, STRUCTURE_TEMPLATES
    )
    from seed_builder import SeedBuilder
    from wav_renderer import WAVRenderer
    ENGINE_AVAILABLE = True
except ImportError as e:
    ENGINE_AVAILABLE = False
    IMPORT_ERROR = str(e)

try:
    from genre_fusion import FusionConfig, FUSION_PRESETS
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False
    FUSION_PRESETS = {}

try:
    import pygame
    import pygame.mixer
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════
#  STYLE
# ═══════════════════════════════════════════════════════════════════════

class S:
    BG = "#07071a"; BG2 = "#0c0c28"; BG3 = "#111138"
    BG_INPUT = "#0e0e2e"; BG_BTN = "#1a1a50"
    BG_BTN_HOV = "#2a2a70"; BG_BTN_ACT = "#3a3aaa"
    CYAN = "#00e5ff"; PINK = "#ff0080"; PURPLE = "#a855f7"
    GREEN = "#00ff88"; YELLOW = "#ffd500"; ORANGE = "#ff6b00"
    RED = "#ff2040"; BLUE = "#4488ff"
    TXT = "#d0d8f0"; TXT_DIM = "#445577"; TXT_BRT = "#ffffff"; DIM = "#445577"
    FN_XS = ("Consolas",8)
    TRACK_CLR = {'drums':'#ff2040','bass':'#ff6b00','chords':'#00e5ff',
                 'lead':'#a855f7','pad':'#00ff88','arp':'#ffd500'}
    GENRE_CLR = {'pop':'#ff69b4','hiphop':'#ffa500','trap':'#ff2040',
                 'cinematic':'#4488ff','classical':'#a855f7','techno':'#00e5ff',
                 'jpop':'#ff69b4','phonk':'#ff6b00'}
    FN_T = ("Consolas",15,"bold"); FN_H = ("Consolas",11,"bold")
    FN_B = ("Consolas",10); FN_S = ("Consolas",9)
    FN_X = ("Consolas",8); FN_BIG = ("Consolas",20,"bold")


# ═══════════════════════════════════════════════════════════════════════
#  ALL 128 GM INSTRUMENTS
# ═══════════════════════════════════════════════════════════════════════

GM_INSTRUMENTS = {
    0:"Acoustic Grand Piano",1:"Bright Acoustic Piano",2:"Electric Grand Piano",
    3:"Honky-tonk Piano",4:"Electric Piano 1",5:"Electric Piano 2",
    6:"Harpsichord",7:"Clavinet",8:"Celesta",9:"Glockenspiel",
    10:"Music Box",11:"Vibraphone",12:"Marimba",13:"Xylophone",
    14:"Tubular Bells",15:"Dulcimer",16:"Drawbar Organ",17:"Percussive Organ",
    18:"Rock Organ",19:"Church Organ",20:"Reed Organ",21:"Accordion",
    22:"Harmonica",23:"Tango Accordion",24:"Nylon Guitar",25:"Steel Guitar",
    26:"Jazz Electric Guitar",27:"Clean Electric Guitar",28:"Muted Guitar",
    29:"Overdriven Guitar",30:"Distortion Guitar",31:"Guitar Harmonics",
    32:"Acoustic Bass",33:"Finger Electric Bass",34:"Pick Electric Bass",
    35:"Fretless Bass",36:"Slap Bass 1",37:"Slap Bass 2",
    38:"Synth Bass 1",39:"Synth Bass 2",40:"Violin",41:"Viola",
    42:"Cello",43:"Contrabass",44:"Tremolo Strings",45:"Pizzicato Strings",
    46:"Orchestral Harp",47:"Timpani",48:"String Ensemble 1",
    49:"String Ensemble 2",50:"Synth Strings 1",51:"Synth Strings 2",
    52:"Choir Aahs",53:"Voice Oohs",54:"Synth Voice",55:"Orchestra Hit",
    56:"Trumpet",57:"Trombone",58:"Tuba",59:"Muted Trumpet",
    60:"French Horn",61:"Brass Section",62:"Synth Brass 1",63:"Synth Brass 2",
    64:"Soprano Sax",65:"Alto Sax",66:"Tenor Sax",67:"Baritone Sax",
    68:"Oboe",69:"English Horn",70:"Bassoon",71:"Clarinet",
    72:"Piccolo",73:"Flute",74:"Recorder",75:"Pan Flute",
    76:"Blown Bottle",77:"Shakuhachi",78:"Whistle",79:"Ocarina",
    80:"Square Lead",81:"Sawtooth Lead",82:"Calliope Lead",83:"Chiff Lead",
    84:"Charang Lead",85:"Voice Lead",86:"Fifths Lead",87:"Bass + Lead",
    88:"New Age Pad",89:"Warm Pad",90:"Polysynth Pad",91:"Choir Pad",
    92:"Bowed Pad",93:"Metallic Pad",94:"Halo Pad",95:"Sweep Pad",
    96:"Rain (FX)",97:"Soundtrack (FX)",98:"Crystal (FX)",99:"Atmosphere (FX)",
    100:"Brightness (FX)",101:"Goblins (FX)",102:"Echoes (FX)",103:"Sci-Fi (FX)",
    104:"Sitar",105:"Banjo",106:"Shamisen",107:"Koto",
    108:"Kalimba",109:"Bag Pipe",110:"Fiddle",111:"Shanai",
    112:"Tinkle Bell",113:"Agogo",114:"Steel Drums",115:"Woodblock",
    116:"Taiko Drum",117:"Melodic Tom",118:"Synth Drum",119:"Reverse Cymbal",
    120:"Guitar Fret Noise",121:"Breath Noise",122:"Seashore",123:"Bird Tweet",
    124:"Telephone Ring",125:"Helicopter",126:"Applause",127:"Gunshot",
}

# GM Drum Kits (channel 10 program changes)
DRUM_KITS = {
    0: "Standard Kit", 8: "Room Kit", 16: "Power Kit",
    24: "Electronic Kit", 25: "TR-808 Kit", 32: "Jazz Kit",
    40: "Brush Kit", 48: "Orchestra Kit", 56: "SFX Kit",
}

# Instruments good for each track role (for random selection)
ROLE_INSTRUMENTS = {
    'bass': [32,33,34,35,36,37,38,39,43,87],
    'chords': [0,1,2,4,5,6,16,17,18,24,25,26,27,48,49,50,52,61,62,89],
    'lead': [40,56,64,65,66,68,71,73,80,81,82,83,84,85,86],
    'pad': [48,49,50,51,52,53,54,88,89,90,91,92,93,94,95,97,99],
    'arp': [8,9,10,11,12,46,80,81,98,100,104,108,114],
}

NOTES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
QUALITIES = ['maj7','min7','7','major','minor','sus4','sus2','dim7','aug']


# ═══════════════════════════════════════════════════════════════════════
#  MIDI PREVIEW PLAYER
# ═══════════════════════════════════════════════════════════════════════

class MIDIPreviewPlayer:
    def __init__(self):
        self.is_playing = False
        self._initialized = False

    def _init(self):
        if not PYGAME_AVAILABLE: return False
        if not self._initialized:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=2048)
                self._initialized = True
            except: return False
        return True

    def play_wav(self, wav_path):
        if not self._init(): return False
        try:
            self.stop()
            pygame.mixer.music.load(wav_path)
            pygame.mixer.music.play()
            self.is_playing = True
            return True
        except Exception as e:
            print(f"Play error: {e}")
            return False

    def stop(self):
        """Stop playback AND unload the file to release the file lock."""
        if self._initialized and PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()  # KEY FIX: release file lock
            except: pass
        self.is_playing = False

    def is_busy(self):
        if self._initialized and PYGAME_AVAILABLE:
            try: return pygame.mixer.music.get_busy()
            except: return False
        return False

    def cleanup(self):
        self.stop()
        if self._initialized and PYGAME_AVAILABLE:
            try: pygame.mixer.quit()
            except: pass


# ═══════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════

class SeedComposerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("◢ SEED COMPOSER — CYBERPUNK EDITION ◣")
        self.root.geometry("1300x920")
        self.root.minsize(1100, 750)
        self.root.configure(bg=S.BG)

        self.engine = None
        self.current_composition = None
        self.current_midi_path = None
        self.current_wav_path = None
        self.player = MIDIPreviewPlayer()
        self.msg_queue = queue.Queue()
        self.is_generating = False
        self.seeds_loaded = False
        self.track_vars = {}
        self.generation_counter = 0  # For unique filenames

        self._build_gui()
        self._init_engine()
        self._poll_queue()

    # ─────────────────────────────────────────────────────────────
    #  GUI CONSTRUCTION
    # ─────────────────────────────────────────────────────────────

    def _build_gui(self):
        main = tk.Frame(self.root, bg=S.BG)
        main.pack(fill='both', expand=True, padx=6, pady=6)

        # Title
        tf = tk.Frame(main, bg=S.BG2, height=50)
        tf.pack(fill='x', pady=(0, 6)); tf.pack_propagate(False)
        tk.Label(tf, text="◢ SEED COMPOSER ◣", font=S.FN_BIG,
                 fg=S.CYAN, bg=S.BG2).pack(side='left', padx=15, pady=8)
        tk.Label(tf, text="AI-POWERED MUSIC GENERATION STUDIO v2",
                 font=S.FN_S, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=10)
        self.status_label = tk.Label(tf, text="● INIT", font=S.FN_S, fg=S.YELLOW, bg=S.BG2)
        self.status_label.pack(side='right', padx=15)

        content = tk.Frame(main, bg=S.BG)
        content.pack(fill='both', expand=True)

        # LEFT — Controls
        left = tk.Frame(content, bg=S.BG2, width=540)
        left.pack(side='left', fill='y', padx=(0, 4)); left.pack_propagate(False)

        lc = tk.Canvas(left, bg=S.BG2, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient='vertical', command=lc.yview)
        sf = tk.Frame(lc, bg=S.BG2)
        sf.bind('<Configure>', lambda e: lc.configure(scrollregion=lc.bbox('all')))
        lc.create_window((0, 0), window=sf, anchor='nw', width=520)
        lc.configure(yscrollcommand=sb.set)
        lc.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        lc.bind_all("<MouseWheel>", lambda e: lc.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._build_seed_section(sf)
        self._build_genre_section(sf)
        self._build_params_section(sf)
        self._build_tracks_section(sf)
        self._build_generate_section(sf)

        # RIGHT — Output
        right = tk.Frame(content, bg=S.BG2)
        right.pack(side='right', fill='both', expand=True)
        self._build_output_panel(right)

    # ─── Seed Section ───

    def _build_seed_section(self, parent):
        frame = self._section(parent, "◢ SEED DATABASE ◣", S.CYAN)

        # Dataset path
        row = tk.Frame(frame, bg=S.BG2); row.pack(fill='x', pady=2)
        tk.Label(row, text="Dataset:", font=S.FN_S, fg=S.TXT, bg=S.BG2).pack(side='left')
        self.dataset_entry = tk.Entry(row, font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
                                       insertbackground=S.CYAN, width=30)
        self.dataset_entry.insert(0, r"C:\Users\julia\Desktop\Analysis\Music\Research_training_data")
        self.dataset_entry.pack(side='left', padx=4, fill='x', expand=True)
        self._cbtn(row, "📁", self._browse_dataset, S.CYAN).pack(side='left', padx=2)

        # Seeds output path
        row2 = tk.Frame(frame, bg=S.BG2); row2.pack(fill='x', pady=2)
        tk.Label(row2, text="Seeds Dir:", font=S.FN_S, fg=S.TXT, bg=S.BG2).pack(side='left')
        self.seeds_entry = tk.Entry(row2, font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
                                     insertbackground=S.CYAN, width=30)
        # Default seeds dir next to this script
        default_seeds = os.path.join(APP_DIR, "seeds")
        self.seeds_entry.insert(0, default_seeds)
        self.seeds_entry.pack(side='left', padx=4, fill='x', expand=True)
        self._cbtn(row2, "📁", self._browse_seeds, S.CYAN).pack(side='left', padx=2)

        # Buttons
        row3 = tk.Frame(frame, bg=S.BG2); row3.pack(fill='x', pady=4)
        self._cbtn(row3, "⚡ BUILD SEEDS FROM CSVs", self._build_seeds,
                   S.PINK, wide=True).pack(side='left', padx=2, fill='x', expand=True)
        self._cbtn(row3, "📂 LOAD SEEDS", self._load_seeds,
                   S.GREEN, wide=True).pack(side='left', padx=2, fill='x', expand=True)

        # Status with clickable path
        self.seed_status = tk.Label(frame, text="No seeds loaded — build or load seeds, or generate without",
                                     font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w', wraplength=480)
        self.seed_status.pack(fill='x', pady=2)

    # ─── Genre ───

    def _build_genre_section(self, parent):
        frame = self._section(parent, "◢ GENRE ◣", S.PINK)
        
        # Standard genre selection
        self.genre_var = tk.StringVar(value='pop')
        genres = ['pop','hiphop','trap','cinematic','classical','techno','jpop','phonk']
        self.genre_list = genres  # Store for custom fusion dropdowns
        grid = tk.Frame(frame, bg=S.BG2); grid.pack(fill='x', pady=4)
        for i, g in enumerate(genres):
            c = S.GENRE_CLR.get(g, S.CYAN)
            tk.Radiobutton(grid, text=g.upper(), variable=self.genre_var, value=g,
                           font=S.FN_S, fg=c, bg=S.BG2, selectcolor=S.BG3,
                           activebackground=S.BG3, activeforeground=c,
                           indicatoron=0, bd=0, padx=10, pady=5, width=9,
                           relief='flat', highlightthickness=1, highlightbackground=S.BG3,
                           command=self._on_genre_change
                           ).grid(row=i//4, column=i%4, padx=2, pady=2, sticky='ew')
            grid.columnconfigure(i%4, weight=1)
        
        # ─── FUSION MODE ───
        if FUSION_AVAILABLE and FUSION_PRESETS:
            fusion_frame = tk.Frame(frame, bg=S.BG2)
            fusion_frame.pack(fill='x', pady=(10, 4))
            
            # Fusion checkbox
            self.fusion_enabled = tk.BooleanVar(value=False)
            fusion_cb = tk.Checkbutton(
                fusion_frame, text="🎮 FUSION MODE", variable=self.fusion_enabled,
                font=S.FN_S, fg=S.ORANGE, bg=S.BG2, selectcolor=S.BG3,
                activebackground=S.BG2, activeforeground=S.ORANGE,
                command=self._on_fusion_toggle
            )
            fusion_cb.pack(side='left', padx=5)
            
            # Fusion preset dropdown
            self.fusion_preset_var = tk.StringVar(value='cyber_ninja')
            fusion_presets = list(FUSION_PRESETS.keys())
            
            self.fusion_combo = ttk.Combobox(
                fusion_frame, 
                textvariable=self.fusion_preset_var,
                values=fusion_presets,
                state='disabled',
                width=18,
                font=S.FN_S
            )
            self.fusion_combo.pack(side='left', padx=10)
            
            # Fusion description label
            self.fusion_desc_var = tk.StringVar(value="")
            self.fusion_desc_label = tk.Label(
                fusion_frame, textvariable=self.fusion_desc_var,
                font=S.FN_XS, fg=S.DIM, bg=S.BG2, anchor='w'
            )
            self.fusion_desc_label.pack(side='left', padx=10, fill='x', expand=True)
            
            # Bind preset change
            self.fusion_combo.bind('<<ComboboxSelected>>', self._on_fusion_preset_change)
            
            # ─── CUSTOM FUSION ROW ───
            custom_frame = tk.Frame(frame, bg=S.BG2)
            custom_frame.pack(fill='x', pady=(6, 4))
            
            # Custom fusion checkbox
            self.fusion_custom = tk.BooleanVar(value=False)
            custom_cb = tk.Checkbutton(
                custom_frame, text="🎨 CUSTOM MIX", variable=self.fusion_custom,
                font=S.FN_S, fg=S.CYAN, bg=S.BG2, selectcolor=S.BG3,
                activebackground=S.BG2, activeforeground=S.CYAN,
                command=self._on_custom_fusion_toggle
            )
            custom_cb.pack(side='left', padx=5)
            
            # Genre 1 dropdown
            self.fusion_genre1 = tk.StringVar(value='trap')
            self.fusion_genre1_combo = ttk.Combobox(
                custom_frame, textvariable=self.fusion_genre1,
                values=genres, state='disabled', width=10, font=S.FN_S
            )
            self.fusion_genre1_combo.pack(side='left', padx=4)
            self.fusion_genre1_combo.bind('<<ComboboxSelected>>', self._update_fusion_colors)
            
            # Genre 1 percentage label (colored)
            self.genre1_pct_label = tk.Label(
                custom_frame, text="60%", font=("Consolas", 11, "bold"),
                fg=S.GENRE_CLR.get('trap', S.CYAN), bg=S.BG2, width=4
            )
            self.genre1_pct_label.pack(side='left', padx=2)
            
            # Ratio slider with custom styling
            slider_frame = tk.Frame(custom_frame, bg=S.BG2)
            slider_frame.pack(side='left', padx=4)
            
            self.fusion_ratio = tk.IntVar(value=60)
            self.fusion_ratio_scale = tk.Scale(
                slider_frame, from_=10, to=90, orient='horizontal',
                variable=self.fusion_ratio, length=120, sliderlength=20,
                font=S.FN_XS, fg=S.CYAN, bg=S.BG2, troughcolor=S.BG3,
                highlightthickness=0, bd=0, state='disabled',
                showvalue=False, command=self._on_ratio_change
            )
            self.fusion_ratio_scale.pack()
            
            # Genre 2 percentage label (colored)
            self.genre2_pct_label = tk.Label(
                custom_frame, text="40%", font=("Consolas", 11, "bold"),
                fg=S.GENRE_CLR.get('jpop', S.PINK), bg=S.BG2, width=4
            )
            self.genre2_pct_label.pack(side='left', padx=2)
            
            # Genre 2 dropdown
            self.fusion_genre2 = tk.StringVar(value='jpop')
            self.fusion_genre2_combo = ttk.Combobox(
                custom_frame, textvariable=self.fusion_genre2,
                values=genres, state='disabled', width=10, font=S.FN_S
            )
            self.fusion_genre2_combo.pack(side='left', padx=4)
            self.fusion_genre2_combo.bind('<<ComboboxSelected>>', self._update_fusion_colors)
            
            # Visual blend bar
            blend_frame = tk.Frame(frame, bg=S.BG2)
            blend_frame.pack(fill='x', pady=(2, 4), padx=40)
            
            self.blend_canvas = tk.Canvas(blend_frame, height=8, bg=S.BG3, 
                                          highlightthickness=1, highlightbackground=S.BG3)
            self.blend_canvas.pack(fill='x')
            self.blend_canvas.bind('<Configure>', self._draw_blend_bar)
            
        else:
            self.fusion_enabled = tk.BooleanVar(value=False)
            self.fusion_preset_var = tk.StringVar(value='cyber_ninja')
            self.fusion_custom = tk.BooleanVar(value=False)

    def _on_fusion_toggle(self):
        """Called when fusion checkbox is toggled."""
        enabled = self.fusion_enabled.get()
        if enabled:
            self.fusion_combo.config(state='readonly')
            self._on_fusion_preset_change(None)
            self._set_status("FUSION MODE ACTIVE", S.ORANGE)
            # Disable custom when enabling preset mode
            if not self.fusion_custom.get():
                pass  # Keep preset enabled
        else:
            self.fusion_combo.config(state='disabled')
            self.fusion_desc_var.set("")
            # Also disable custom fusion
            self.fusion_custom.set(False)
            self._on_custom_fusion_toggle()
            self._set_status("READY", S.GREEN)

    def _on_custom_fusion_toggle(self):
        """Called when custom fusion checkbox is toggled."""
        custom = self.fusion_custom.get()
        
        if custom:
            # Enable custom controls
            self.fusion_enabled.set(True)  # Auto-enable fusion mode
            self.fusion_combo.config(state='disabled')  # Disable preset
            self.fusion_genre1_combo.config(state='readonly')
            self.fusion_genre2_combo.config(state='readonly')
            self.fusion_ratio_scale.config(state='normal')
            self._update_fusion_colors()
            self._set_status("CUSTOM FUSION MODE", S.CYAN)
        else:
            # Disable custom controls
            self.fusion_genre1_combo.config(state='disabled')
            self.fusion_genre2_combo.config(state='disabled')
            self.fusion_ratio_scale.config(state='disabled')
            if self.fusion_enabled.get():
                self.fusion_combo.config(state='readonly')
                self._on_fusion_preset_change(None)

    def _on_ratio_change(self, value):
        """Called when ratio slider changes."""
        ratio = int(float(value))
        # Update percentage labels with colors
        g1 = self.fusion_genre1.get()
        g2 = self.fusion_genre2.get()
        c1 = S.GENRE_CLR.get(g1, S.CYAN)
        c2 = S.GENRE_CLR.get(g2, S.PINK)
        
        self.genre1_pct_label.config(text=f"{ratio}%", fg=c1)
        self.genre2_pct_label.config(text=f"{100-ratio}%", fg=c2)
        
        # Redraw blend bar
        self._draw_blend_bar()

    def _update_fusion_colors(self, event=None):
        """Update colors when genres change."""
        g1 = self.fusion_genre1.get()
        g2 = self.fusion_genre2.get()
        c1 = S.GENRE_CLR.get(g1, S.CYAN)
        c2 = S.GENRE_CLR.get(g2, S.PINK)
        ratio = self.fusion_ratio.get()
        
        self.genre1_pct_label.config(text=f"{ratio}%", fg=c1)
        self.genre2_pct_label.config(text=f"{100-ratio}%", fg=c2)
        
        # Redraw blend bar
        self._draw_blend_bar()

    def _draw_blend_bar(self, event=None):
        """Draw the colorful blend bar showing genre mix."""
        if not hasattr(self, 'blend_canvas'):
            return
        
        canvas = self.blend_canvas
        canvas.delete("all")
        
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        
        if width < 10:
            return
        
        g1 = self.fusion_genre1.get() if hasattr(self, 'fusion_genre1') else 'trap'
        g2 = self.fusion_genre2.get() if hasattr(self, 'fusion_genre2') else 'jpop'
        c1 = S.GENRE_CLR.get(g1, S.CYAN)
        c2 = S.GENRE_CLR.get(g2, S.PINK)
        ratio = self.fusion_ratio.get() if hasattr(self, 'fusion_ratio') else 60
        
        # Draw genre 1 portion
        x1_end = int(width * ratio / 100)
        canvas.create_rectangle(0, 0, x1_end, height, fill=c1, outline="")
        
        # Draw genre 2 portion
        canvas.create_rectangle(x1_end, 0, width, height, fill=c2, outline="")

    def _on_fusion_preset_change(self, event):
        """Called when fusion preset is changed."""
        preset_name = self.fusion_preset_var.get()
        if preset_name in FUSION_PRESETS:
            preset = FUSION_PRESETS[preset_name]
            genres = " + ".join(preset['genres'])
            weights = "/".join([f"{int(w*100)}%" for w in preset['weights']])
            desc = f"{genres} ({weights})"
            self.fusion_desc_var.set(desc)

    # ─── Parameters ───

    def _build_params_section(self, parent):
        frame = self._section(parent, "◢ PARAMETERS ◣", S.PURPLE)

        # BPM
        r = tk.Frame(frame, bg=S.BG2); r.pack(fill='x', pady=3)
        tk.Label(r, text="BPM:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.bpm_auto = tk.BooleanVar(value=True)
        tk.Checkbutton(r, text="Auto/Random", variable=self.bpm_auto, font=S.FN_X,
                       fg=S.GREEN, bg=S.BG2, selectcolor=S.BG3,
                       activebackground=S.BG2, command=self._toggle_bpm).pack(side='left')
        self.bpm_scale = tk.Scale(r, from_=40, to=200, orient='horizontal',
                                   font=S.FN_X, fg=S.PURPLE, bg=S.BG2,
                                   troughcolor=S.BG_INPUT, highlightthickness=0,
                                   length=180, state='disabled')
        self.bpm_scale.set(120)
        self.bpm_scale.pack(side='left', padx=4, fill='x', expand=True)

        # Key
        r2 = tk.Frame(frame, bg=S.BG2); r2.pack(fill='x', pady=3)
        tk.Label(r2, text="Key:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.key_auto = tk.BooleanVar(value=True)
        tk.Checkbutton(r2, text="Auto/Random", variable=self.key_auto, font=S.FN_X,
                       fg=S.GREEN, bg=S.BG2, selectcolor=S.BG3,
                       activebackground=S.BG2, command=self._toggle_key).pack(side='left')
        self.key_root = ttk.Combobox(r2, values=NOTES, width=4, state='disabled')
        self.key_root.set('C'); self.key_root.pack(side='left', padx=2)
        self.key_mode = ttk.Combobox(r2, values=['major','minor'], width=6, state='disabled')
        self.key_mode.set('major'); self.key_mode.pack(side='left', padx=2)

        # Starting Chord
        r3 = tk.Frame(frame, bg=S.BG2); r3.pack(fill='x', pady=3)
        tk.Label(r3, text="Start Chord:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.chord_auto = tk.BooleanVar(value=True)
        tk.Checkbutton(r3, text="Auto/Random", variable=self.chord_auto, font=S.FN_X,
                       fg=S.GREEN, bg=S.BG2, selectcolor=S.BG3,
                       activebackground=S.BG2, command=self._toggle_chord).pack(side='left')
        self.chord_root = ttk.Combobox(r3, values=NOTES, width=4, state='disabled')
        self.chord_root.set('C'); self.chord_root.pack(side='left', padx=2)
        self.chord_quality = ttk.Combobox(r3, values=QUALITIES, width=6, state='disabled')
        self.chord_quality.set('maj7'); self.chord_quality.pack(side='left', padx=2)

        # Complexity
        r4 = tk.Frame(frame, bg=S.BG2); r4.pack(fill='x', pady=3)
        tk.Label(r4, text="Complexity:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.complexity_scale = tk.Scale(r4, from_=0, to=10, orient='horizontal',
                                          font=S.FN_X, fg=S.ORANGE, bg=S.BG2,
                                          troughcolor=S.BG_INPUT, highlightthickness=0, length=220)
        self.complexity_scale.set(5)
        self.complexity_scale.pack(side='left', padx=4, fill='x', expand=True)

        # Humanize
        r5 = tk.Frame(frame, bg=S.BG2); r5.pack(fill='x', pady=3)
        tk.Label(r5, text="Humanize:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.humanize_scale = tk.Scale(r5, from_=0, to=100, orient='horizontal',
                                        font=S.FN_X, fg=S.GREEN, bg=S.BG2,
                                        troughcolor=S.BG_INPUT, highlightthickness=0, length=220)
        self.humanize_scale.set(60)
        self.humanize_scale.pack(side='left', padx=4, fill='x', expand=True)

        # Mutation / Chaos Slider
        r_mut = tk.Frame(frame, bg=S.BG2); r_mut.pack(fill='x', pady=3)
        tk.Label(r_mut, text="🎲 Mutation:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        
        # Mutation scale with gradient-like labels
        mut_frame = tk.Frame(r_mut, bg=S.BG2)
        mut_frame.pack(side='left', fill='x', expand=True)
        
        tk.Label(mut_frame, text="SAFE", font=S.FN_XS, fg=S.GREEN, bg=S.BG2).pack(side='left')
        
        self.mutation_scale = tk.Scale(mut_frame, from_=0, to=100, orient='horizontal',
                                        font=S.FN_X, fg=S.YELLOW, bg=S.BG2,
                                        troughcolor=S.BG_INPUT, highlightthickness=0, length=180,
                                        command=self._on_mutation_change)
        self.mutation_scale.set(0)
        self.mutation_scale.pack(side='left', padx=4)
        
        tk.Label(mut_frame, text="CHAOS", font=S.FN_XS, fg=S.RED, bg=S.BG2).pack(side='left')
        
        # Mutation percentage display
        self.mutation_label = tk.Label(r_mut, text="0%", font=("Consolas", 10, "bold"),
                                        fg=S.GREEN, bg=S.BG2, width=5)
        self.mutation_label.pack(side='left', padx=4)

        # Seed
        r6 = tk.Frame(frame, bg=S.BG2); r6.pack(fill='x', pady=3)
        tk.Label(r6, text="Seed:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.seed_entry = tk.Entry(r6, font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
                                    insertbackground=S.CYAN, width=12)
        self.seed_entry.pack(side='left', padx=2)
        tk.Label(r6, text="(empty=random)", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=4)
        self._cbtn(r6, "🎲", self._random_seed, S.YELLOW).pack(side='left')

    # ─── Tracks ───

    def _build_tracks_section(self, parent):
        frame = self._section(parent, "◢ TRACKS & INSTRUMENTS ◣", S.GREEN)

        # Randomize all button
        top_row = tk.Frame(frame, bg=S.BG2); top_row.pack(fill='x', pady=(0, 4))
        self._cbtn(top_row, "🎲 RANDOMIZE ALL INSTRUMENTS", self._randomize_all_instruments,
                   S.YELLOW, wide=True).pack(fill='x')

        tracks = ['drums','bass','chords','lead','pad','arp']
        for track in tracks:
            color = S.TRACK_CLR.get(track, S.CYAN)
            row = tk.Frame(frame, bg=S.BG2); row.pack(fill='x', pady=2)

            # Enable
            enabled = tk.BooleanVar(value=(track != 'arp'))
            tk.Checkbutton(row, text=track.upper(), variable=enabled, font=S.FN_S,
                           fg=color, bg=S.BG2, selectcolor=S.BG3,
                           activebackground=S.BG2, width=7, anchor='w').pack(side='left')

            # Volume
            tk.Label(row, text="Vol:", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left')
            vol = tk.Scale(row, from_=0, to=100, orient='horizontal', font=S.FN_X,
                           fg=color, bg=S.BG2, troughcolor=S.BG_INPUT,
                           highlightthickness=0, length=80, showvalue=0)
            vol.set(80 if track != 'arp' else 50)
            vol.pack(side='left', padx=2)

            # Instrument selector
            if track == 'drums':
                kit_values = [f"{k}: {v}" for k, v in sorted(DRUM_KITS.items())]
                inst = ttk.Combobox(row, values=kit_values, width=20, font=S.FN_X)
                inst.set("0: Standard Kit")
            else:
                inst_values = [f"{k}: {v}" for k, v in sorted(GM_INSTRUMENTS.items())]
                inst = ttk.Combobox(row, values=inst_values, width=20, font=S.FN_X)
                default_prog = GENRE_INSTRUMENTS.get('pop', {}).get(track, 0)
                inst.set(f"{default_prog}: {GM_INSTRUMENTS.get(default_prog, 'Piano')}")
            inst.pack(side='left', padx=4)

            # Random button per track
            self._cbtn(row, "🎲", lambda t=track: self._randomize_track_instrument(t),
                       S.YELLOW).pack(side='left', padx=2)

            self.track_vars[track] = {'enabled': enabled, 'volume': vol, 'instrument': inst}

    # ─── Generate ───

    def _build_generate_section(self, parent):
        frame = self._section(parent, "◢ GENERATE ◣", S.YELLOW)
        r = tk.Frame(frame, bg=S.BG2); r.pack(fill='x', pady=6)
        self.gen_btn = self._cbtn(r, "⚡ GENERATE NEW SONG ⚡", self._generate,
                                   S.CYAN, wide=True, big=True)
        self.gen_btn.pack(fill='x', padx=4, ipady=8)

        # ── ADD THIS NEXT TO YOUR NORMAL GENERATE BUTTON ──
        self.btn_batch = ttk.Button(
            r,  # Change this to whatever frame holds your buttons
            text="Generate Batch (5x)",
            command=self._on_generate_batch
        )
        self.btn_batch.pack(side=tk.LEFT, padx=5)
    # ─── Output Panel ───

    def _build_output_panel(self, parent):
        info_frame = self._section(parent, "◢ COMPOSITION OUTPUT ◣", S.CYAN)

        self.info_text = tk.Text(info_frame, font=S.FN_S, bg=S.BG, fg=S.TXT,
                                  insertbackground=S.CYAN, height=18, wrap='word',
                                  state='disabled', bd=0, highlightthickness=1,
                                  highlightbackground=S.BG3)
        self.info_text.pack(fill='both', expand=True, pady=4)
        for tag, color in [('header',S.CYAN),('value',S.GREEN),('section',S.PINK),
                           ('chord',S.PURPLE),('dim',S.TXT_DIM),('warn',S.YELLOW)]:
            self.info_text.tag_configure(tag, foreground=color,
                                          font=S.FN_H if tag == 'header' else S.FN_S)

        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(info_frame, variable=self.progress_var, maximum=100).pack(fill='x', pady=2)
        self.progress_label = tk.Label(info_frame, text="", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2)
        self.progress_label.pack(fill='x')

        # Playback
        bf = tk.Frame(parent, bg=S.BG2); bf.pack(fill='x', padx=6, pady=4)
        self._cbtn(bf, "▶ PLAY", self._play_preview, S.GREEN, wide=True).pack(side='left', padx=2, fill='x', expand=True)
        self._cbtn(bf, "■ STOP", self._stop_playback, S.RED, wide=True).pack(side='left', padx=2, fill='x', expand=True)

        # Export
        ef = tk.Frame(parent, bg=S.BG2); ef.pack(fill='x', padx=6, pady=2)
        self._cbtn(ef, "💾 MIDI", self._export_midi, S.PURPLE, wide=True).pack(side='left', padx=2, fill='x', expand=True)
        self._cbtn(ef, "🔊 WAV", self._export_wav, S.ORANGE, wide=True).pack(side='left', padx=2, fill='x', expand=True)
        self._cbtn(ef, "📋 JSON", self._export_json, S.BLUE, wide=True).pack(side='left', padx=2, fill='x', expand=True)

        # Log
        lf = self._section(parent, "◢ CONSOLE ◣", S.TXT_DIM)
        self.log_text = tk.Text(lf, font=S.FN_X, bg=S.BG, fg=S.TXT_DIM,
                                 height=8, wrap='word', state='disabled', bd=0)
        self.log_text.pack(fill='both', expand=True, pady=2)

    # ─────────────────────────────────────────────────────────────
    #  GUI HELPERS
    # ─────────────────────────────────────────────────────────────

    def _section(self, parent, title, color):
        outer = tk.Frame(parent, bg=S.BG2); outer.pack(fill='x', padx=6, pady=4)
        tk.Label(outer, text=title, font=S.FN_H, fg=color, bg=S.BG2, anchor='w').pack(fill='x', pady=2)
        tk.Frame(outer, bg=color, height=1).pack(fill='x', pady=(0, 4))
        content = tk.Frame(outer, bg=S.BG2); content.pack(fill='x')
        return content

    def _cbtn(self, parent, text, command, color, wide=False, big=False):
        font = S.FN_H if big else S.FN_S
        btn = tk.Button(parent, text=text, command=command, font=font, fg=color,
                        bg=S.BG_BTN, activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
                        bd=0, padx=10 if wide else 6, pady=4 if big else 2, cursor='hand2',
                        highlightthickness=1, highlightbackground=color)
        btn.bind('<Enter>', lambda e: btn.configure(bg=S.BG_BTN_HOV))
        btn.bind('<Leave>', lambda e: btn.configure(bg=S.BG_BTN))
        return btn

    def _log(self, msg):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', f"{msg}\n")
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _set_status(self, text, color=S.YELLOW):
        self.status_label.configure(text=f"● {text}", fg=color)

    def _info_clear(self):
        self.info_text.configure(state='normal')
        self.info_text.delete('1.0', 'end')
        self.info_text.configure(state='disabled')

    def _info_add(self, text, tag=None):
        self.info_text.configure(state='normal')
        self.info_text.insert('end', text, tag) if tag else self.info_text.insert('end', text)
        self.info_text.see('end')
        self.info_text.configure(state='disabled')

    # ─────────────────────────────────────────────────────────────
    #  TOGGLE CALLBACKS
    # ─────────────────────────────────────────────────────────────

    def _toggle_bpm(self):
        self.bpm_scale.configure(state='disabled' if self.bpm_auto.get() else 'normal')

    def _toggle_key(self):
        st = 'disabled' if self.key_auto.get() else 'readonly'
        self.key_root.configure(state=st); self.key_mode.configure(state=st)

    def _toggle_chord(self):
        st = 'disabled' if self.chord_auto.get() else 'readonly'
        self.chord_root.configure(state=st); self.chord_quality.configure(state=st)

    def _on_genre_change(self):
        genre = self.genre_var.get()
        defaults = GENRE_INSTRUMENTS.get(genre, GENRE_INSTRUMENTS.get('pop', {}))
        for track, prog in defaults.items():
            if track in self.track_vars and self.track_vars[track]['instrument']:
                name = GM_INSTRUMENTS.get(prog, "Piano")
                self.track_vars[track]['instrument'].set(f"{prog}: {name}")
        self._log(f"Genre → {genre.upper()}")

    def _random_seed(self):
        self.seed_entry.delete(0, 'end')
        self.seed_entry.insert(0, str(random.randint(1, 999999)))

    def _on_mutation_change(self, value):
        """Update mutation label color based on value."""
        val = int(float(value))
        self.mutation_label.config(text=f"{val}%")
        
        # Color gradient from green (safe) to yellow to red (chaos)
        if val <= 30:
            color = S.GREEN
        elif val <= 60:
            color = S.YELLOW
        elif val <= 80:
            color = S.ORANGE
        else:
            color = S.RED
        
        self.mutation_label.config(fg=color)
        self.mutation_scale.config(fg=color)

    def _randomize_track_instrument(self, track):
        """Randomize instrument for a single track."""
        if track == 'drums':
            kit = random.choice(list(DRUM_KITS.items()))
            self.track_vars[track]['instrument'].set(f"{kit[0]}: {kit[1]}")
        else:
            pool = ROLE_INSTRUMENTS.get(track, list(GM_INSTRUMENTS.keys()))
            prog = random.choice(pool)
            name = GM_INSTRUMENTS.get(prog, "Unknown")
            self.track_vars[track]['instrument'].set(f"{prog}: {name}")
        self._log(f"Randomized {track}: {self.track_vars[track]['instrument'].get()}")

    def _randomize_all_instruments(self):
        """Randomize all track instruments at once."""
        for track in self.track_vars:
            self._randomize_track_instrument(track)
        self._log("🎲 All instruments randomized!")

    # ─────────────────────────────────────────────────────────────
    #  ENGINE
    # ─────────────────────────────────────────────────────────────

    def _init_engine(self):
        if not ENGINE_AVAILABLE:
            self._set_status(f"ENGINE ERROR: {IMPORT_ERROR}", S.RED)
            self._log(f"Import error: {IMPORT_ERROR}")
            return
        self.engine = CompositionEngine()
        self._set_status("READY — Load seeds or generate without", S.GREEN)
        self._log("Engine ready. Seeds not loaded — using music theory fallback.")
        self._log(f"To load seeds, point Seeds Dir to your JSON seeds folder and click LOAD.")

    # ─────────────────────────────────────────────────────────────
    #  SEED OPERATIONS
    # ─────────────────────────────────────────────────────────────

    def _browse_dataset(self):
        p = filedialog.askdirectory(title="Select Dataset Root (Research_training_data)")
        if p:
            self.dataset_entry.delete(0, 'end')
            self.dataset_entry.insert(0, p)

    def _browse_seeds(self):
        p = filedialog.askdirectory(title="Select Seeds Directory")
        if p:
            self.seeds_entry.delete(0, 'end')
            self.seeds_entry.insert(0, p)

    def _build_seeds(self):
        dataset_dir = self.dataset_entry.get().strip()
        seeds_dir = self.seeds_entry.get().strip() or "seeds"
        if not dataset_dir:
            messagebox.showwarning("No Dataset", "Select your CSV dataset directory first.")
            return
        if not os.path.exists(dataset_dir):
            messagebox.showwarning("Not Found", f"Directory not found:\n{dataset_dir}")
            return

        self._set_status("BUILDING SEEDS...", S.PINK)
        self._log(f"Building from: {dataset_dir}")
        self._log(f"Output to: {os.path.abspath(seeds_dir)}")

        def _worker():
            try:
                builder = SeedBuilder(dataset_dir, seeds_dir)
                count = builder.build_all_seeds(
                    progress_callback=lambda i, t, s: self.msg_queue.put(('progress', i, t, f"{s}"))
                )
                if count > 0:
                    builder.save_seeds()
                    builder.export_genre_matrices()
                    self.msg_queue.put(('seed_done', count, seeds_dir))
                else:
                    self.msg_queue.put(('seed_fail', 'No valid CSV triples found. Check folder structure.'))
            except Exception as e:
                self.msg_queue.put(('seed_fail', str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _load_seeds(self):
        seeds_dir = self.seeds_entry.get().strip() or "seeds"
        if not os.path.exists(seeds_dir):
            messagebox.showwarning("Not Found", f"Seeds directory not found:\n{seeds_dir}\n\n"
                                   f"Build seeds first, or browse to an existing seeds folder.")
            return

        self._set_status("LOADING SEEDS...", S.CYAN)
        try:
            self.engine = CompositionEngine(seeds_dir)
            self.engine.load_seeds()
            n = len(self.engine.seeds)
            genres = list(self.engine.genre_seeds.keys())
            self.seeds_loaded = True
            abs_path = os.path.abspath(seeds_dir)
            self.seed_status.configure(
                text=f"✓ {n} seeds loaded from: {abs_path}\nGenres: {', '.join(genres)}",
                fg=S.GREEN
            )
            self._set_status(f"LOADED: {n} seeds", S.GREEN)
            self._log(f"✓ {n} seeds from {abs_path}")
            self._log(f"  Genres: {genres}")
        except Exception as e:
            self._set_status(f"LOAD ERROR: {e}", S.RED)
            self._log(f"Error: {e}")

    # ─────────────────────────────────────────────────────────────
    #  GENERATION
    # ─────────────────────────────────────────────────────────────

    def _build_config(self):
        config = CompositionConfig()
        config.genre = self.genre_var.get()

        # BPM: None means the engine picks randomly from genre range or seeds
        config.bpm = None if self.bpm_auto.get() else float(self.bpm_scale.get())

        # Key: None means random
        config.key = None if self.key_auto.get() else f"{self.key_root.get()} {self.key_mode.get()}"

        # Chord: None means random
        config.starting_chord = None if self.chord_auto.get() else \
            f"{self.chord_root.get()}{self.chord_quality.get()}"

        config.complexity = int(self.complexity_scale.get())
        config.humanize_amount = self.humanize_scale.get() / 100.0
        
        # Mutation / Chaos factor
        if hasattr(self, 'mutation_scale'):
            config.mutation = self.mutation_scale.get() / 100.0
        else:
            config.mutation = 0.0

        seed_text = self.seed_entry.get().strip()
        config.seed_value = int(seed_text) if seed_text.isdigit() else None

        for track_name, vd in self.track_vars.items():
            if track_name not in config.tracks:
                config.tracks[track_name] = {'enabled': True, 'volume': 0.8, 'instrument': None}
            config.tracks[track_name]['enabled'] = vd['enabled'].get()
            config.tracks[track_name]['volume'] = vd['volume'].get() / 100.0
            if vd['instrument'] is not None:
                try:
                    config.tracks[track_name]['instrument'] = int(vd['instrument'].get().split(':')[0])
                except (ValueError, IndexError):
                    pass

        # ─── FUSION CONFIG ───
        if FUSION_AVAILABLE and self.fusion_enabled.get():
            # Check if using custom fusion
            if hasattr(self, 'fusion_custom') and self.fusion_custom.get():
                # Custom fusion with user-selected genres and ratio
                genre1 = self.fusion_genre1.get()
                genre2 = self.fusion_genre2.get()
                ratio = self.fusion_ratio.get() / 100.0  # Convert to 0-1
                config.fusion = FusionConfig.custom(genre1, genre2, ratio)
                print(f"◢ CUSTOM FUSION: {genre1.upper()} {int(ratio*100)}% + {genre2.upper()} {int((1-ratio)*100)}% ◣")
            else:
                # Preset fusion
                preset_name = self.fusion_preset_var.get()
                try:
                    config.fusion = FusionConfig.from_preset(preset_name)
                    print(f"◢ FUSION PRESET: {preset_name.upper()} ◣")
                except Exception as e:
                    print(f"Fusion error: {e}")

        return config

    def _generate(self):
        if self.is_generating:
            return
        if not self.engine:
            messagebox.showerror("No Engine", "Composition engine not available.")
            return

        # FIX: Stop playback and release file lock before regenerating
        self.player.stop()
        time_module.sleep(0.1)  # Give OS time to release

        self.is_generating = True
        self.generation_counter += 1
        self._set_status("COMPOSING...", S.PINK)
        self._info_clear()
        self._info_add("◢ GENERATING NEW COMPOSITION... ◣\n", 'header')
        self.progress_var.set(0)

        config = self._build_config()
        gen_id = self.generation_counter  # Unique ID for this generation

        def _worker():
            try:
                self.msg_queue.put(('gen_progress', 10, "Building chord progression..."))
                composition = self.engine.compose(config)
                self.msg_queue.put(('gen_progress', 50, "Exporting MIDI..."))

                # Use unique filenames to avoid permission conflicts
                temp_dir = Path(APP_DIR) / "temp_output"
                temp_dir.mkdir(exist_ok=True)
                midi_path = str(temp_dir / f"preview_{gen_id}.mid")
                self.engine.export_midi(composition, midi_path)

                self.msg_queue.put(('gen_progress', 70, "Rendering preview audio..."))
                wav_path = str(temp_dir / f"preview_{gen_id}.wav")
                renderer = WAVRenderer()
                renderer.render_composition_to_wav(composition, wav_path)

                # Clean up old preview files
                for old in temp_dir.glob("preview_*.wav"):
                    if str(old) != wav_path:
                        try: old.unlink()
                        except: pass
                for old in temp_dir.glob("preview_*.mid"):
                    if str(old) != midi_path:
                        try: old.unlink()
                        except: pass

                self.msg_queue.put(('gen_done', composition, midi_path, wav_path))
            except Exception as e:
                self.msg_queue.put(('gen_error', str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_generate_batch(self):
        """Triggers a 5-song cinematic batch generation on a background thread."""
        if not getattr(self, 'engine', None):
            self._info_add("Engine not loaded yet.", "warn")
            return

        # Disable button to prevent spam-clicking
        self.btn_batch.config(state=tk.DISABLED)
        self._set_status("GENERATING BATCH...", "orange")  # Adjust colors to your UI theme

        # Grab current genre from your UI (update 'self.genre_var' if yours is named differently)
        genre = self.genre_var.get().lower()

        def batch_worker():
            try:
                # Triggers the new function in composition_engine
                self.engine.generate_batch(
                    count=5,
                    genre=genre,
                    base_output_dir=os.path.join(APP_DIR, "cinematic_batch")
                )

                # Update UI safely from thread
                self.root.after(0, lambda: self._set_status("BATCH COMPLETE", "green"))
                self.root.after(0, lambda: self._info_add(
                    f"Successfully exported 5 {genre} tracks to /cinematic_batch/", "info"))

            except Exception as e:
                # 1. Capture the error string immediately before 'e' disappears
                error_msg = str(e)

                # 2. Pass it into the lambda as a default argument (m=error_msg) to lock it in memory
                self.root.after(0, lambda: self._set_status("BATCH ERROR", "red"))
                self.root.after(0, lambda m=error_msg: self._info_add(f"Error: {m}", "warn"))
            finally:
                self.root.after(0, lambda: self.btn_batch.config(state=tk.NORMAL))

        # Start the background thread
        threading.Thread(target=batch_worker, daemon=True).start()

    def _display_composition(self, comp):
        self._info_clear()
        c = comp['config']
        self._info_add("═══════════════════════════════════════\n", 'dim')
        self._info_add("    ◢ COMPOSITION GENERATED ◣\n", 'header')
        self._info_add("═══════════════════════════════════════\n\n", 'dim')

        for label, val in [("GENRE", c['genre'].upper()), ("BPM", c['bpm']),
                           ("KEY", c['key']), ("COMPLEXITY", f"{c['complexity']}/10"),
                           ("BARS", comp['total_bars']),
                           ("DURATION", f"{comp['duration_seconds']:.1f}s")]:
            self._info_add(f"{label:12s}", 'section')
            self._info_add(f"{val}\n", 'value')

        self._info_add("\n◢ STRUCTURE ◣\n", 'header')
        for stype, bars in comp['structure']:
            self._info_add(f"  [{stype.upper():12s}] ", 'section')
            self._info_add(f"{bars} bars\n")

        self._info_add("\n◢ CHORDS ◣\n", 'header')
        prog = comp['chord_progression']
        for i in range(0, min(len(prog), 32), 4):
            self._info_add(f"  {' → '.join(prog[i:i+4])}\n", 'chord')
        if len(prog) > 32:
            self._info_add(f"  ... ({len(prog)-32} more)\n", 'dim')

        self._info_add("\n◢ TRACKS ◣\n", 'header')
        for name, events in comp['tracks'].items():
            self._info_add(f"  {name.upper():8s}", 'section')
            self._info_add(f" {len(events)} events\n", 'value')

    # ─────────────────────────────────────────────────────────────
    #  PLAYBACK & EXPORT
    # ─────────────────────────────────────────────────────────────

    def _play_preview(self):
        if not self.current_wav_path or not os.path.exists(self.current_wav_path):
            messagebox.showinfo("No Preview", "Generate a song first!")
            return
        if self.player.play_wav(self.current_wav_path):
            self._set_status("PLAYING", S.GREEN)
        else:
            msg = "Install pygame for playback:\npip install pygame" if not PYGAME_AVAILABLE else "Playback failed"
            self._log(msg)

    def _stop_playback(self):
        self.player.stop()
        self._set_status("STOPPED", S.YELLOW)

    def _export_midi(self):
        if not self.current_composition: messagebox.showinfo("", "Generate first!"); return
        p = filedialog.asksaveasfilename(
            defaultextension=".mid", filetypes=[("MIDI", "*.mid")],
            initialfile=f"SeedComposer_{self.current_composition['config']['genre']}.mid")
        if p:
            self.engine.export_midi(self.current_composition, p)
            self._log(f"MIDI → {p}"); self._set_status("MIDI EXPORTED", S.GREEN)

    def _export_wav(self):
        if not self.current_composition: messagebox.showinfo("", "Generate first!"); return
        p = filedialog.asksaveasfilename(
            defaultextension=".wav", filetypes=[("WAV", "*.wav")],
            initialfile=f"SeedComposer_{self.current_composition['config']['genre']}.wav")
        if not p: return
        self._set_status("RENDERING WAV...", S.ORANGE)
        def _w():
            try:
                WAVRenderer().render_composition_to_wav(self.current_composition, p)
                self.msg_queue.put(('wav_done', p))
            except Exception as e:
                self.msg_queue.put(('wav_error', str(e)))
        threading.Thread(target=_w, daemon=True).start()

    def _export_json(self):
        if not self.current_composition: messagebox.showinfo("", "Generate first!"); return
        p = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile=f"SeedComposer_{self.current_composition['config']['genre']}.json")
        if p:
            export = {k: v for k, v in self.current_composition.items() if k != 'tracks'}
            export['track_sizes'] = {k: len(v) for k, v in self.current_composition['tracks'].items()}
            with open(p, 'w') as f: json.dump(export, f, indent=2, default=str)
            self._log(f"JSON → {p}"); self._set_status("JSON EXPORTED", S.GREEN)

    # ─────────────────────────────────────────────────────────────
    #  MESSAGE QUEUE
    # ─────────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _handle_msg(self, msg):
        t = msg[0]
        if t == 'progress':
            _, cur, total, txt = msg
            self.progress_var.set(cur/total*100)
            self.progress_label.configure(text=f"[{cur}/{total}] {txt}")
        elif t == 'seed_done':
            _, count, sd = msg
            abs_path = os.path.abspath(sd)
            self.seed_status.configure(text=f"✓ Built {count} seeds → {abs_path}", fg=S.GREEN)
            self._set_status(f"SEEDS BUILT: {count}", S.GREEN)
            self._log(f"✓ {count} seeds saved to {abs_path}")
            self.progress_var.set(100)
            self.seeds_entry.delete(0, 'end')
            self.seeds_entry.insert(0, sd)
            self._load_seeds()
        elif t == 'seed_fail':
            self._set_status(f"SEED ERROR: {msg[1]}", S.RED)
            self._log(f"Error: {msg[1]}")
        elif t == 'gen_progress':
            self.progress_var.set(msg[1])
            self.progress_label.configure(text=msg[2])
            self._info_add(f"  {msg[2]}\n", 'dim')
        elif t == 'gen_done':
            _, comp, midi, wav = msg
            self.current_composition = comp
            self.current_midi_path = midi
            self.current_wav_path = wav
            self.is_generating = False
            self.progress_var.set(100)
            self.progress_label.configure(text="Done!")
            self._display_composition(comp)
            self._set_status("READY — Hit Play or Export", S.GREEN)
            c = comp['config']
            self._log(f"✓ {c['genre'].upper()} | {c['bpm']} BPM | {c['key']} | "
                      f"{comp['total_bars']} bars | {comp['duration_seconds']:.1f}s")

            # UPDATE GUI to show what Auto/Random actually picked
            # BPM
            if self.bpm_auto.get():
                self.bpm_scale.configure(state='normal')
                self.bpm_scale.set(int(c['bpm']))
                self.bpm_scale.configure(state='disabled')
            # Key
            if self.key_auto.get():
                parts = c['key'].split()
                if parts:
                    self.key_root.configure(state='readonly')
                    self.key_root.set(parts[0])
                    self.key_root.configure(state='disabled')
                if len(parts) > 1:
                    self.key_mode.configure(state='readonly')
                    self.key_mode.set(parts[1])
                    self.key_mode.configure(state='disabled')
            # Starting chord
            if self.chord_auto.get() and c.get('starting_chord'):
                sc = c['starting_chord']
                # Parse root and quality
                if len(sc) > 1 and sc[1] in '#b':
                    cr, cq = sc[:2], sc[2:] or 'maj7'
                else:
                    cr, cq = sc[0], sc[1:] or 'maj7'
                self.chord_root.configure(state='readonly')
                self.chord_root.set(cr)
                self.chord_root.configure(state='disabled')
                self.chord_quality.configure(state='readonly')
                self.chord_quality.set(cq)
                self.chord_quality.configure(state='disabled')
        elif t == 'gen_error':
            self.is_generating = False
            self._set_status(f"ERROR: {msg[1]}", S.RED)
            self._info_add(f"\n⚠ ERROR: {msg[1]}\n", 'warn')
        elif t == 'wav_done':
            self._set_status("WAV EXPORTED", S.GREEN)
            self._log(f"WAV → {msg[1]}")
        elif t == 'wav_error':
            self._set_status(f"WAV ERROR: {msg[1]}", S.RED)

    def cleanup(self):
        self.player.cleanup()


# ═══════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def main():
    root = tk.Tk()
    try:
        import ctypes
        root.update()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
    except: pass

    style = ttk.Style(); style.theme_use('clam')
    style.configure('TCombobox', fieldbackground=S.BG_INPUT, background=S.BG_BTN,
                    foreground=S.TXT, arrowcolor=S.CYAN)
    style.map('TCombobox',
              fieldbackground=[('disabled', S.BG_INPUT), ('readonly', S.BG_INPUT)],
              foreground=[('disabled', S.CYAN), ('readonly', S.TXT)],
              background=[('disabled', S.BG_BTN)])
    style.configure('TProgressbar', troughcolor=S.BG_INPUT, background=S.CYAN)

    app = SeedComposerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
