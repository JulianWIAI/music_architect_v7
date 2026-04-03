"""
═══════════════════════════════════════════════════════════════════════════════
FUSION INTEGRATION GUIDE FOR composition_engine.py
═══════════════════════════════════════════════════════════════════════════════

Follow these steps to add Cross-Genre Fusion to your composition engine:
"""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Add import at top of composition_engine.py
# ═══════════════════════════════════════════════════════════════════════════════

"""
Add this import with your other imports:

from genre_fusion import GenreFusionEngine, FusionConfig, FUSION_PRESETS
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Add fusion_engine to __init__
# ═══════════════════════════════════════════════════════════════════════════════

"""
In __init__, add:

    self.fusion_engine = None
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Initialize fusion_engine in load_seeds()
# ═══════════════════════════════════════════════════════════════════════════════

"""
At the end of load_seeds(), after loading lead patterns, add:

    # Initialize fusion engine
    self.fusion_engine = GenreFusionEngine(
        self.pattern_generator,
        self.bass_generator,
        self.lead_generator
    )
    print(f"◢ FUSION ENGINE READY ◣")
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Modify compose() to support fusion
# ═══════════════════════════════════════════════════════════════════════════════

"""
In the compose() method, after the random seed setup, add this block:

        # ═══════════════════════════════════════════════════════════════
        # FUSION HANDLING
        # ═══════════════════════════════════════════════════════════════
        fusion_config = getattr(config, 'fusion', None)
        using_fusion = fusion_config is not None and self.fusion_engine is not None
        
        if using_fusion:
            print(f"◢ FUSION MODE: {' + '.join(fusion_config.genres)} ◣")
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Modify BPM selection for fusion
# ═══════════════════════════════════════════════════════════════════════════════

"""
Replace the BPM auto-selection block with:

        # Auto-select BPM from genre or fusion
        if config.bpm is None:
            if using_fusion:
                config.bpm = self.fusion_engine.get_fused_bpm(fusion_config, GENRE_BPM)
            else:
                bpm_range = GENRE_BPM.get(config.genre, (100, 130))
                genre_seeds = self.genre_seeds.get(config.genre, [])
                if genre_seeds:
                    bpms = [s['dna']['bpm'] for s in genre_seeds if 'dna' in s]
                    if bpms:
                        config.bpm = random.choice(bpms)
                    else:
                        config.bpm = random.uniform(*bpm_range)
                else:
                    config.bpm = random.uniform(*bpm_range)
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Modify chord progression generation for fusion
# ═══════════════════════════════════════════════════════════════════════════════

"""
In generate_chord_progression(), add fusion matrix support.
Replace the matrix selection:

        # Get the transition matrix for this genre (or fused matrix)
        fusion_config = getattr(config, 'fusion', None)
        if fusion_config and self.fusion_engine:
            matrix = self.fusion_engine.get_fused_chord_matrix(
                fusion_config, self.genre_matrices
            )
            if not matrix:
                matrix = self.genre_matrices.get(config.genre, self.global_matrix)
        else:
            matrix = self.genre_matrices.get(config.genre, self.global_matrix)
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: Modify drum generation to use fusion
# ═══════════════════════════════════════════════════════════════════════════════

"""
Replace the drum generation section in compose():

        if config.tracks.get('drums', {}).get('enabled', True):
            if using_fusion and self.fusion_engine:
                # Use fused patterns
                tracks['drums'] = self._generate_fused_drums(
                    fusion_config, structure, config
                )
            elif self.pattern_generator and self.pattern_generator.global_patterns.get('kick'):
                tracks['drums'] = generate_drums_from_learned_patterns(
                    self.pattern_generator,
                    config.genre,
                    structure,
                    config.complexity,
                    config.humanize_amount,
                    config.bpm or 120
                )
            else:
                tracks['drums'] = self.generate_drum_track(config, structure, total_bars)
            track_info['drums'] = {'channel': 9, 'program': 0}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: Add the fused drum generation method
# ═══════════════════════════════════════════════════════════════════════════════

FUSED_DRUMS_METHOD = '''
    def _generate_fused_drums(self, fusion_config, structure, config):
        """Generate drums using fused patterns from multiple genres."""
        KICK = 36
        SNARE = 38
        HIHAT_CLOSED = 42
        HIHAT_OPEN = 46
        CRASH = 49
        
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        h_amt = config.humanize_amount
        bpm = config.bpm or 120
        
        # Get fused patterns for each instrument
        kick_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'kick', total_bars, complexity_float
        )
        snare_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'snare', total_bars, complexity_float
        )
        hihat_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'hihat', total_bars, complexity_float
        )
        
        bar_idx = 0
        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            
            for local_bar in range(section_bars):
                if bar_idx >= len(kick_patterns):
                    break
                
                bar_time = bar_idx * 4
                
                kick_pat = kick_patterns[bar_idx] if bar_idx < len(kick_patterns) else [0]*16
                snare_pat = snare_patterns[bar_idx] if bar_idx < len(snare_patterns) else [0]*16
                hihat_pat = hihat_patterns[bar_idx] if bar_idx < len(hihat_patterns) else [0]*16
                
                # Section modifications
                if section_type == 'intro':
                    fade = (local_bar + 1) / max(1, section_bars)
                    kick_pat = [int(v * fade) for v in kick_pat]
                    snare_pat = [int(v * (fade * 0.5)) for v in snare_pat]
                elif section_type == 'outro':
                    fade = 1.0 - (local_bar / max(1, section_bars))
                    kick_pat = [int(v * fade) for v in kick_pat]
                    snare_pat = [int(v * fade) for v in snare_pat]
                elif section_type == 'break':
                    kick_pat = [0] * 16
                    snare_pat = [0] * 16
                    hihat_pat = [v if i % 8 == 0 else 0 for i, v in enumerate(hihat_pat)]
                elif section_type == 'build':
                    build_pct = (local_bar + 1) / section_bars
                    if build_pct > 0.7:
                        for i in range(16):
                            if i % 2 == 0 and random.random() < build_pct * 0.5:
                                snare_pat[i] = 1
                
                # Convert to MIDI
                for step in range(16):
                    step_time = bar_time + (step / 4)
                    h_offset = (random.random() - 0.5) * 0.02 * h_amt
                    
                    if kick_pat[step] > 0:
                        vel = int(80 + random.randint(-8, 8) * h_amt)
                        vel = int(vel * energy)
                        notes.append((step_time + h_offset, 0.25, KICK, max(40, min(127, vel))))
                    
                    if snare_pat[step] > 0:
                        vel = int(90 + random.randint(-10, 10) * h_amt)
                        vel = int(vel * energy)
                        notes.append((step_time + h_offset, 0.25, SNARE, max(40, min(127, vel))))
                    
                    if hihat_pat[step] > 0:
                        vel = int(70 + random.randint(-6, 6) * h_amt)
                        vel = int(vel * energy)
                        hat = HIHAT_OPEN if random.random() < 0.08 else HIHAT_CLOSED
                        dur = 0.4 if hat == HIHAT_OPEN else 0.15
                        notes.append((step_time + h_offset, dur, hat, max(30, min(127, vel))))
                
                # Crash on first bar of chorus/drop
                if local_bar == 0 and section_type in ('chorus', 'drop', 'climax'):
                    notes.append((bar_time, 1.0, CRASH, int(100 * energy)))
                
                bar_idx += 1
        
        return notes
'''


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9: Similar updates for bass and lead (optional but recommended)
# ═══════════════════════════════════════════════════════════════════════════════

FUSED_BASS_METHOD = '''
    def _generate_fused_bass(self, fusion_config, chord_progression, structure, config):
        """Generate bass using fused patterns from multiple genres."""
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        
        # Get fused bass patterns
        bass_patterns = self.fusion_engine.get_fused_patterns(
            fusion_config, 'bass', total_bars, complexity_float
        )
        
        # Similar to generate_bass_from_learned_patterns but using fused patterns
        # ... (implementation similar to drums)
        
        return notes
'''


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 10: Add fusion support to CompositionConfig
# ═══════════════════════════════════════════════════════════════════════════════

"""
In the CompositionConfig dataclass, add:

    fusion: Optional[FusionConfig] = None  # For cross-genre fusion
"""


# ═══════════════════════════════════════════════════════════════════════════════
# USAGE EXAMPLES
# ═══════════════════════════════════════════════════════════════════════════════

USAGE_EXAMPLES = '''
# Example 1: Use a preset
from genre_fusion import FusionConfig

config = CompositionConfig()
config.fusion = FusionConfig.from_preset('cyber_ninja')  # trap + techno
composition = engine.compose(config)

# Example 2: Custom fusion
config = CompositionConfig()
config.fusion = FusionConfig.custom('jpop', 'cinematic', 0.7)  # 70% jpop, 30% cinematic
composition = engine.compose(config)

# Example 3: Multi-genre fusion (3+ genres)
config = CompositionConfig()
config.fusion = FusionConfig(
    genres=['trap', 'jpop', 'cinematic'],
    weights=[0.5, 0.3, 0.2],  # 50% trap, 30% jpop, 20% cinematic
    blend_mode='weighted'
)
composition = engine.compose(config)

# Example 4: Layered fusion (rhythm from one, melody from another)
config = CompositionConfig()
config.fusion = FusionConfig(
    genres=['trap', 'classical'],
    weights=[0.7, 0.3],
    blend_mode='layered'
)
composition = engine.compose(config)
'''

print("See this file for integration instructions!")
print("\nKey files needed:")
print("  - genre_fusion.py (the fusion system)")
print("  - composition_engine.py (needs modifications)")
print("\nPresets available:")
for name in ['cyber_ninja', 'anime_boss', 'lofi_samurai', 'dark_mage', 'final_boss']:
    print(f"  🎮 {name}")
