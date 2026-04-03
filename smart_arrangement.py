"""
═══════════════════════════════════════════════════════════════════════════════
  SMART ARRANGEMENT AI
  Learns song structure patterns from analyzed seeds to generate
  authentic section progressions.
  
  Features:
  - Learns which sections follow which (Markov chain)
  - Genre-specific arrangement patterns
  - Intro/outro detection
  - Energy flow analysis
  - Build-up to drop patterns
═══════════════════════════════════════════════════════════════════════════════
"""

import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT ARRANGEMENT RULES (fallback when no seeds available)
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_TRANSITIONS = {
    'pop': {
        'intro': {'verse': 0.8, 'pre_chorus': 0.2},
        'verse': {'pre_chorus': 0.5, 'chorus': 0.3, 'verse': 0.2},
        'pre_chorus': {'chorus': 0.9, 'drop': 0.1},
        'chorus': {'verse': 0.4, 'bridge': 0.3, 'chorus': 0.2, 'outro': 0.1},
        'bridge': {'chorus': 0.7, 'break': 0.2, 'outro': 0.1},
        'break': {'chorus': 0.6, 'build': 0.4},
        'build': {'chorus': 0.5, 'drop': 0.5},
        'drop': {'verse': 0.3, 'break': 0.3, 'outro': 0.4},
        'outro': {},
    },
    'trap': {
        'intro': {'build': 0.6, 'verse': 0.4},
        'verse': {'build': 0.4, 'chorus': 0.3, 'drop': 0.3},
        'build': {'drop': 0.9, 'chorus': 0.1},
        'drop': {'verse': 0.3, 'break': 0.4, 'drop': 0.2, 'outro': 0.1},
        'break': {'build': 0.7, 'verse': 0.3},
        'chorus': {'drop': 0.5, 'verse': 0.3, 'bridge': 0.2},
        'bridge': {'drop': 0.6, 'build': 0.4},
        'outro': {},
    },
    'hiphop': {
        'intro': {'verse': 0.9, 'chorus': 0.1},
        'verse': {'chorus': 0.5, 'verse': 0.3, 'bridge': 0.2},
        'chorus': {'verse': 0.6, 'bridge': 0.2, 'outro': 0.2},
        'bridge': {'chorus': 0.5, 'verse': 0.3, 'outro': 0.2},
        'break': {'verse': 0.5, 'chorus': 0.5},
        'outro': {},
    },
    'techno': {
        'intro': {'build': 0.7, 'verse': 0.3},
        'build': {'drop': 0.9, 'climax': 0.1},
        'drop': {'break': 0.4, 'drop': 0.3, 'build': 0.2, 'outro': 0.1},
        'break': {'build': 0.8, 'drop': 0.2},
        'verse': {'build': 0.6, 'break': 0.4},
        'climax': {'break': 0.5, 'outro': 0.5},
        'outro': {},
    },
    'cinematic': {
        'intro': {'build': 0.5, 'tension': 0.3, 'verse': 0.2},
        'build': {'climax': 0.7, 'tension': 0.3},
        'tension': {'build': 0.4, 'climax': 0.4, 'break': 0.2},
        'climax': {'break': 0.4, 'resolution': 0.4, 'outro': 0.2},
        'break': {'build': 0.5, 'tension': 0.3, 'resolution': 0.2},
        'resolution': {'outro': 0.6, 'build': 0.4},
        'verse': {'tension': 0.5, 'build': 0.5},
        'outro': {},
    },
    'jpop': {
        'intro': {'verse': 0.8, 'pre_chorus': 0.2},
        'verse': {'pre_chorus': 0.6, 'chorus': 0.2, 'verse': 0.2},
        'pre_chorus': {'chorus': 0.95, 'drop': 0.05},
        'chorus': {'verse': 0.4, 'bridge': 0.3, 'break': 0.2, 'outro': 0.1},
        'bridge': {'chorus': 0.8, 'break': 0.2},
        'break': {'chorus': 0.5, 'build': 0.5},
        'build': {'chorus': 0.7, 'drop': 0.3},
        'drop': {'chorus': 0.5, 'outro': 0.5},
        'outro': {},
    },
    'phonk': {
        'intro': {'build': 0.6, 'verse': 0.4},
        'verse': {'drop': 0.4, 'build': 0.4, 'chorus': 0.2},
        'build': {'drop': 0.9, 'chorus': 0.1},
        'drop': {'verse': 0.3, 'break': 0.3, 'drop': 0.3, 'outro': 0.1},
        'break': {'build': 0.6, 'drop': 0.4},
        'chorus': {'drop': 0.6, 'verse': 0.4},
        'bridge': {'drop': 0.8, 'build': 0.2},
        'outro': {},
    },
    'classical': {
        'intro': {'exposition': 0.8, 'verse': 0.2},
        'exposition': {'development': 0.6, 'bridge': 0.4},
        'development': {'recapitulation': 0.5, 'bridge': 0.3, 'break': 0.2},
        'bridge': {'development': 0.4, 'recapitulation': 0.4, 'coda': 0.2},
        'recapitulation': {'coda': 0.6, 'bridge': 0.4},
        'break': {'development': 0.5, 'recapitulation': 0.5},
        'coda': {'outro': 1.0},
        'verse': {'development': 0.5, 'exposition': 0.5},
        'outro': {},
    },
}

# Section bar lengths by energy level
SECTION_BAR_RANGES = {
    'intro': (4, 8),
    'verse': (8, 16),
    'pre_chorus': (4, 8),
    'chorus': (8, 16),
    'drop': (8, 16),
    'bridge': (4, 8),
    'break': (2, 4),
    'build': (4, 8),
    'climax': (8, 16),
    'tension': (4, 8),
    'resolution': (4, 8),
    'outro': (4, 8),
    'exposition': (8, 16),
    'development': (8, 16),
    'recapitulation': (8, 16),
    'coda': (4, 8),
    'variation': (4, 8),
}


# ═══════════════════════════════════════════════════════════════════════════════
# SMART ARRANGEMENT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class SmartArrangementEngine:
    """
    Learns and generates intelligent song structures based on genre patterns.
    """
    
    def __init__(self):
        self.genre_transitions = {}
        self.genre_section_lengths = {}
        self.genre_energy_profiles = {}
        self._loaded = False
    
    def load_from_seeds(self, seeds: List[Dict]):
        """Learn arrangement patterns from seed data."""
        
        for seed in seeds:
            genre = seed.get('genre', 'pop')
            structure = seed.get('structure', [])
            
            if not structure:
                continue
            
            if genre not in self.genre_transitions:
                self.genre_transitions[genre] = defaultdict(Counter)
                self.genre_section_lengths[genre] = defaultdict(list)
                self.genre_energy_profiles[genre] = []
            
            # Extract section sequence
            sections = []
            for section in structure:
                if isinstance(section, dict):
                    sec_type = section.get('type', 'verse')
                    start = section.get('start', 0)
                    end = section.get('end', start + 16)
                    energy = section.get('energy', 0.5)
                    duration = end - start
                    sections.append((sec_type, duration, energy))
                elif isinstance(section, tuple):
                    sec_type, bars = section[:2]
                    sections.append((sec_type, bars * 4, 0.5))  # Assume 4 seconds per bar
            
            # Learn transitions
            for i in range(len(sections) - 1):
                current_type = sections[i][0]
                next_type = sections[i + 1][0]
                self.genre_transitions[genre][current_type][next_type] += 1
            
            # Learn section lengths
            for sec_type, duration, energy in sections:
                # Convert duration to bars (assuming ~2 seconds per bar at 120 BPM)
                bars = max(2, int(duration / 2))
                self.genre_section_lengths[genre][sec_type].append(bars)
            
            # Store energy profile
            energy_profile = [s[2] for s in sections]
            self.genre_energy_profiles[genre].append(energy_profile)
        
        # Normalize transitions to probabilities
        for genre in self.genre_transitions:
            for section, followers in self.genre_transitions[genre].items():
                total = sum(followers.values())
                if total > 0:
                    for next_sec in followers:
                        followers[next_sec] = followers[next_sec] / total
        
        self._loaded = True
        
        # Print stats
        total_patterns = sum(
            sum(len(followers) for followers in genre_trans.values())
            for genre_trans in self.genre_transitions.values()
        )
        print(f"◢ SMART ARRANGEMENT: Learned {total_patterns} transition patterns ◣")
    
    def get_transition_matrix(self, genre: str) -> Dict[str, Dict[str, float]]:
        """Get transition matrix for a genre."""
        if genre in self.genre_transitions and self.genre_transitions[genre]:
            return dict(self.genre_transitions[genre])
        return DEFAULT_TRANSITIONS.get(genre, DEFAULT_TRANSITIONS['pop'])
    
    def get_section_length(self, genre: str, section_type: str, complexity: int = 5) -> int:
        """Get a typical section length for this genre and section type."""
        # Check learned lengths
        if genre in self.genre_section_lengths:
            lengths = self.genre_section_lengths[genre].get(section_type, [])
            if lengths:
                # Pick from learned lengths with some variation
                base = random.choice(lengths)
                # Add complexity influence
                if complexity >= 7:
                    base = int(base * 1.2)
                elif complexity <= 3:
                    base = int(base * 0.8)
                return max(2, min(24, base))
        
        # Fallback to defaults
        min_bars, max_bars = SECTION_BAR_RANGES.get(section_type, (4, 8))
        
        # Adjust for complexity
        if complexity >= 7:
            max_bars = int(max_bars * 1.3)
        elif complexity <= 3:
            max_bars = int(max_bars * 0.7)
            min_bars = max(2, int(min_bars * 0.7))
        
        return random.randint(min_bars, max_bars)
    
    def generate_structure(self, genre: str, target_duration_bars: int = 64,
                          complexity: int = 5, mutation: float = 0.0) -> List[Tuple[str, int]]:
        """
        Generate a smart song structure using learned patterns.
        
        Args:
            genre: Target genre
            target_duration_bars: Approximate total bars (e.g., 64 for ~3 min at 120 BPM)
            complexity: 0-10 complexity level
            mutation: 0-1 how much to randomize/mutate the structure
            
        Returns:
            List of (section_type, bars) tuples
        """
        matrix = self.get_transition_matrix(genre)
        
        structure = []
        current_bars = 0
        
        # Always start with intro
        current_section = 'intro'
        intro_bars = self.get_section_length(genre, 'intro', complexity)
        structure.append(('intro', intro_bars))
        current_bars += intro_bars
        
        # Track section counts to avoid too many repeats
        section_counts = Counter({'intro': 1})
        max_section_repeats = 3 if complexity >= 7 else 2
        
        # Generate middle sections
        max_iterations = 30  # Safety limit
        iteration = 0
        
        while current_bars < target_duration_bars - 8 and iteration < max_iterations:
            iteration += 1
            
            # Get possible next sections
            transitions = matrix.get(current_section, {})
            
            if not transitions:
                # No transitions defined, pick a random common section
                common_sections = ['verse', 'chorus', 'bridge', 'drop', 'build']
                next_section = random.choice(common_sections)
            else:
                # Apply mutation: sometimes pick unexpected section
                if mutation > 0 and random.random() < mutation * 0.4:
                    # Mutate: pick any section with some probability
                    all_sections = list(set(
                        list(transitions.keys()) + 
                        ['verse', 'chorus', 'drop', 'bridge', 'build', 'break']
                    ))
                    next_section = random.choice(all_sections)
                else:
                    # Normal: weighted random based on learned probabilities
                    next_section = self._weighted_choice(transitions)
            
            # Avoid too many repeats
            if section_counts[next_section] >= max_section_repeats:
                # Try to find alternative
                alternatives = [s for s in transitions.keys() 
                               if section_counts[s] < max_section_repeats]
                if alternatives:
                    next_section = random.choice(alternatives)
                elif current_bars > target_duration_bars * 0.7:
                    # We're near the end, go to outro
                    break
            
            # Get section length
            section_bars = self.get_section_length(genre, next_section, complexity)
            
            # Apply mutation to length
            if mutation > 0 and random.random() < mutation * 0.3:
                # Mutate length: +/- 50%
                mutation_factor = 1.0 + (random.random() - 0.5) * mutation
                section_bars = max(2, int(section_bars * mutation_factor))
            
            # Check if adding this section would exceed target
            if current_bars + section_bars > target_duration_bars + 8:
                section_bars = max(2, target_duration_bars - current_bars - 4)
            
            structure.append((next_section, section_bars))
            current_bars += section_bars
            section_counts[next_section] += 1
            current_section = next_section
        
        # Add outro
        outro_bars = self.get_section_length(genre, 'outro', complexity)
        structure.append(('outro', outro_bars))
        
        return structure
    
    def _weighted_choice(self, options: Dict[str, float]) -> str:
        """Choose from weighted options."""
        if not options:
            return 'verse'
        
        items = list(options.items())
        weights = [w for _, w in items]
        total = sum(weights)
        
        if total == 0:
            return random.choice([k for k, _ in items])
        
        r = random.uniform(0, total)
        cumulative = 0
        
        for item, weight in items:
            cumulative += weight
            if r <= cumulative:
                return item
        
        return items[-1][0]
    
    def analyze_energy_flow(self, structure: List[Tuple[str, int]]) -> List[float]:
        """Analyze the energy flow of a structure."""
        energy_map = {
            'intro': 0.3, 'verse': 0.55, 'pre_chorus': 0.65,
            'chorus': 0.85, 'drop': 1.0, 'bridge': 0.5,
            'break': 0.2, 'build': 0.7, 'climax': 1.0,
            'tension': 0.75, 'resolution': 0.5, 'outro': 0.25,
            'exposition': 0.6, 'development': 0.75,
            'recapitulation': 0.7, 'coda': 0.4, 'variation': 0.65,
        }
        
        return [energy_map.get(sec_type, 0.5) for sec_type, _ in structure]


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def create_smart_arrangement_engine(seeds: List[Dict]) -> SmartArrangementEngine:
    """Create and initialize a smart arrangement engine from seeds."""
    engine = SmartArrangementEngine()
    engine.load_from_seeds(seeds)
    return engine


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═══════════════════════════════════════════")
    print("  SMART ARRANGEMENT AI - Demo")
    print("═══════════════════════════════════════════\n")
    
    engine = SmartArrangementEngine()
    
    for genre in ['pop', 'trap', 'cinematic', 'techno']:
        print(f"🎵 {genre.upper()} Structure (complexity=7, mutation=0.2):")
        structure = engine.generate_structure(genre, target_duration_bars=64, 
                                              complexity=7, mutation=0.2)
        total_bars = 0
        for sec_type, bars in structure:
            print(f"   [{sec_type:12s}] {bars:2d} bars")
            total_bars += bars
        print(f"   Total: {total_bars} bars\n")
