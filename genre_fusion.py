"""
═══════════════════════════════════════════════════════════════════════════════
  CROSS-GENRE FUSION SYSTEM
  Blends musical DNA from multiple genres to create unique hybrid styles.
  
  Presets named after character classes for personality!
═══════════════════════════════════════════════════════════════════════════════
"""

import random
from typing import List, Dict, Tuple, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════════════════════
# FUSION PRESETS
# ═══════════════════════════════════════════════════════════════════════════════

FUSION_PRESETS = {
    'cyber_ninja': {
        'genres': ['trap', 'techno'],
        'weights': [0.6, 0.4],
        'description': 'Fast, aggressive beats with electronic edge',
        'bpm_range': (140, 160),
    },
    'paladin': {
        'genres': ['cinematic', 'classical'],
        'weights': [0.5, 0.5],
        'description': 'Epic orchestral power and majesty',
        'bpm_range': (80, 110),
    },
    'anime_boss': {
        'genres': ['jpop', 'cinematic'],
        'weights': [0.7, 0.3],
        'description': 'J-Pop energy with epic orchestral moments',
        'bpm_range': (130, 150),
    },
    'lofi_samurai': {
        'genres': ['hiphop', 'jpop'],
        'weights': [0.65, 0.35],
        'description': 'Chill beats with Japanese melodic influence',
        'bpm_range': (75, 95),
    },
    'dark_mage': {
        'genres': ['phonk', 'cinematic'],
        'weights': [0.55, 0.45],
        'description': 'Dark, aggressive atmosphere with orchestral depth',
        'bpm_range': (130, 145),
    },
    'street_fighter': {
        'genres': ['trap', 'jpop'],
        'weights': [0.5, 0.5],
        'description': 'Hard-hitting beats with anime flair',
        'bpm_range': (140, 155),
    },
    'space_pirate': {
        'genres': ['techno', 'cinematic'],
        'weights': [0.6, 0.4],
        'description': 'Futuristic electronic with epic scope',
        'bpm_range': (125, 145),
    },
    'shadow_assassin': {
        'genres': ['phonk', 'trap'],
        'weights': [0.5, 0.5],
        'description': 'Dark, aggressive, maximum intensity',
        'bpm_range': (135, 160),
    },
    'healing_bard': {
        'genres': ['pop', 'classical'],
        'weights': [0.6, 0.4],
        'description': 'Uplifting melodies with orchestral warmth',
        'bpm_range': (100, 125),
    },
    'mech_pilot': {
        'genres': ['techno', 'jpop'],
        'weights': [0.55, 0.45],
        'description': 'High-energy electronic anime vibes',
        'bpm_range': (135, 155),
    },
    'drift_king': {
        'genres': ['phonk', 'hiphop'],
        'weights': [0.6, 0.4],
        'description': 'Aggressive cowbell-driven street racing energy',
        'bpm_range': (130, 150),
    },
    'final_boss': {
        'genres': ['cinematic', 'trap'],
        'weights': [0.5, 0.5],
        'description': 'Epic orchestral meets hard-hitting production',
        'bpm_range': (100, 140),
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# FUSION CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FusionConfig:
    """Configuration for genre fusion."""
    genres: List[str]
    weights: List[float]
    blend_mode: str = 'weighted'
    
    def __post_init__(self):
        total = sum(self.weights)
        if total > 0:
            self.weights = [w / total for w in self.weights]
    
    @classmethod
    def from_preset(cls, preset_name: str) -> 'FusionConfig':
        """Create FusionConfig from a named preset."""
        if preset_name not in FUSION_PRESETS:
            raise ValueError(f"Unknown preset: {preset_name}")
        preset = FUSION_PRESETS[preset_name]
        return cls(genres=preset['genres'], weights=preset['weights'])
    
    @classmethod
    def custom(cls, genre1: str, genre2: str, ratio: float = 0.5) -> 'FusionConfig':
        """Create custom fusion between two genres."""
        return cls(genres=[genre1, genre2], weights=[ratio, 1.0 - ratio])


# ═══════════════════════════════════════════════════════════════════════════════
# GENRE FUSION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class GenreFusionEngine:
    """Blends patterns from multiple genres to create hybrid styles."""
    
    def __init__(self, pattern_generator, bass_generator=None, lead_generator=None):
        self.pattern_generator = pattern_generator
        self.bass_generator = bass_generator
        self.lead_generator = lead_generator
    
    def get_fused_patterns(self, fusion_config: FusionConfig, 
                           instrument: str, num_bars: int,
                           complexity: float = 0.5) -> List[List[int]]:
        """Get patterns by blending multiple genres."""
        genres = fusion_config.genres
        weights = fusion_config.weights
        
        # Collect patterns from each genre
        genre_patterns = {}
        for genre in genres:
            patterns = self.pattern_generator.get_patterns_for_genre(genre, instrument)
            if patterns:
                genre_patterns[genre] = patterns
        
        if not genre_patterns:
            return [[0] * 16 for _ in range(num_bars)]
        
        # Generate sequence with weighted selection
        sequence = []
        
        for bar in range(num_bars):
            # Choose genre based on weights
            r = random.random()
            cumulative = 0
            chosen_genre = genres[0]
            
            for genre, weight in zip(genres, weights):
                cumulative += weight
                if r <= cumulative:
                    chosen_genre = genre
                    break
            
            # Get pattern from chosen genre
            if chosen_genre in genre_patterns:
                patterns = genre_patterns[chosen_genre]
                
                # Cross-pollinate occasionally based on complexity
                if complexity > 0.5 and random.random() < complexity * 0.3:
                    other_genres = [g for g in genre_patterns.keys() if g != chosen_genre]
                    if other_genres:
                        chosen_genre = random.choice(other_genres)
                        patterns = genre_patterns[chosen_genre]
                
                pattern = random.choice(patterns)
            else:
                all_patterns = [p for pats in genre_patterns.values() for p in pats]
                pattern = random.choice(all_patterns) if all_patterns else [0] * 16
            
            sequence.append(pattern)
        
        return sequence
    
    def get_fused_bpm(self, fusion_config: FusionConfig,
                      genre_bpm_ranges: Dict[str, Tuple[int, int]]) -> float:
        """Calculate a fused BPM from multiple genres."""
        genres = fusion_config.genres
        weights = fusion_config.weights
        
        # Check for preset BPM range
        for preset_name, preset in FUSION_PRESETS.items():
            if preset['genres'] == genres:
                bpm_range = preset.get('bpm_range', (100, 140))
                return random.uniform(*bpm_range)
        
        # Weighted average
        total_bpm = 0
        total_weight = 0
        
        for genre, weight in zip(genres, weights):
            if genre in genre_bpm_ranges:
                min_bpm, max_bpm = genre_bpm_ranges[genre]
                avg_bpm = (min_bpm + max_bpm) / 2
                total_bpm += avg_bpm * weight
                total_weight += weight
        
        if total_weight > 0:
            base_bpm = total_bpm / total_weight
            return base_bpm + random.uniform(-10, 10)
        
        return 120.0
    
    def get_fused_chord_matrix(self, fusion_config: FusionConfig,
                               genre_matrices: Dict[str, Dict]) -> Dict:
        """Blend chord transition matrices from multiple genres."""
        genres = fusion_config.genres
        weights = fusion_config.weights
        
        fused_matrix = defaultdict(lambda: defaultdict(float))
        
        for genre, weight in zip(genres, weights):
            if genre not in genre_matrices:
                continue
            
            matrix = genre_matrices[genre]
            for chord, transitions in matrix.items():
                for next_chord, prob in transitions.items():
                    fused_matrix[chord][next_chord] += prob * weight
        
        # Normalize
        result = {}
        for chord, transitions in fused_matrix.items():
            total = sum(transitions.values())
            if total > 0:
                result[chord] = {nc: p / total for nc, p in transitions.items()}
        
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  CROSS-GENRE FUSION SYSTEM")
    print("═══════════════════════════════════════════")
    print("\nAvailable Presets:\n")
    
    for name, preset in FUSION_PRESETS.items():
        genres = " + ".join(preset['genres'])
        weights = "/".join([f"{int(w*100)}%" for w in preset['weights']])
        print(f"  🎮 {name.upper()}")
        print(f"     {genres} ({weights})")
        print(f"     {preset['description']}")
        print()
