"""
Lead Melody Pattern Extractor & Generator
Learns melodic patterns from timeline CSVs.
Extracts: rhythm patterns, melodic contours, interval sequences, phrase structures.
"""

import csv
import json
import random
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

NOTE_TO_MIDI = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7,
    'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11,
}

MIDI_TO_NOTE = {0: 'C', 1: 'C#', 2: 'D', 3: 'D#', 4: 'E', 5: 'F', 
                6: 'F#', 7: 'G', 8: 'G#', 9: 'A', 10: 'A#', 11: 'B'}

# Melodic contour types
CONTOUR_UP = 'up'
CONTOUR_DOWN = 'down'
CONTOUR_STAY = 'stay'
CONTOUR_JUMP_UP = 'jump_up'
CONTOUR_JUMP_DOWN = 'jump_down'


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD PATTERN EXTRACTOR
# ═══════════════════════════════════════════════════════════════════════════════

class LeadPatternExtractor:
    """
    Extracts lead/melody patterns from timeline CSV files.
    Learns: rhythm patterns, melodic contours, interval movements, phrase structures.
    """
    
    SYNTH_THRESHOLD = 0.02  # Minimum intensity to count as a synth/lead hit
    
    def __init__(self, steps_per_bar: int = 16):
        self.steps_per_bar = steps_per_bar
    
    def parse_timeline_csv(self, filepath: str) -> List[Dict]:
        """Parse timeline CSV into list of events."""
        rows = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    try:
                        parsed = {
                            'time': float(row.get('time_seconds', 0)),
                            'synth': float(row.get('synth', 0)),
                            'pad': float(row.get('pad', 0)),
                            'chord_root': row.get('chord_root', 'C'),
                            'chord_quality': row.get('chord_quality', 'maj7'),
                            'dominant_instrument': row.get('dominant_instrument', ''),
                        }
                        rows.append(parsed)
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
        return rows
    
    def quantize_to_bars(self, timeline: List[Dict], bpm: float) -> List[Dict]:
        """
        Quantize timeline into bars with lead/synth patterns.
        """
        if not timeline:
            return []
        
        seconds_per_beat = 60.0 / bpm
        seconds_per_bar = seconds_per_beat * 4
        seconds_per_step = seconds_per_bar / self.steps_per_bar
        
        total_duration = timeline[-1]['time'] - timeline[0]['time']
        num_bars = int(total_duration / seconds_per_bar) + 1
        
        # Initialize bars
        bars = []
        for _ in range(num_bars):
            bars.append({
                'synth_intensities': [0.0] * self.steps_per_bar,
                'chord_roots': [],
                'chord_qualities': [],
                'is_lead_dominant': [False] * self.steps_per_bar,
            })
        
        start_time = timeline[0]['time']
        
        # Fill bars with data
        for row in timeline:
            relative_time = row['time'] - start_time
            bar_idx = min(int(relative_time / seconds_per_bar), num_bars - 1)
            time_in_bar = relative_time - (bar_idx * seconds_per_bar)
            step_idx = min(int(time_in_bar / seconds_per_step), self.steps_per_bar - 1)
            
            # Take max intensity at each step
            bars[bar_idx]['synth_intensities'][step_idx] = max(
                bars[bar_idx]['synth_intensities'][step_idx], 
                row['synth']
            )
            
            # Track if lead/synth is dominant
            if 'synth' in row.get('dominant_instrument', '').lower() or \
               'lead' in row.get('dominant_instrument', '').lower():
                bars[bar_idx]['is_lead_dominant'][step_idx] = True
            
            # Track chords
            if row['chord_root']:
                bars[bar_idx]['chord_roots'].append(row['chord_root'])
                bars[bar_idx]['chord_qualities'].append(row['chord_quality'])
        
        return bars
    
    def classify_phrase_type(self, rhythm: Tuple[int, ...], intensities: List[float]) -> str:
        """
        Classify the melodic phrase type based on rhythm pattern.
        
        Types:
        - 'sustained': Long notes, few hits
        - 'staccato': Short, punchy notes
        - 'flowing': Smooth, connected notes
        - 'rhythmic': Strong rhythmic emphasis
        - 'sparse': Minimal, space-focused
        """
        hits = sum(rhythm)
        
        if hits <= 2:
            return 'sustained'
        elif hits <= 4:
            # Check if hits are evenly spaced
            hit_positions = [i for i, v in enumerate(rhythm) if v == 1]
            if len(hit_positions) >= 2:
                gaps = [hit_positions[i+1] - hit_positions[i] for i in range(len(hit_positions)-1)]
                if len(set(gaps)) == 1:  # All gaps equal
                    return 'rhythmic'
            return 'sparse'
        elif hits <= 8:
            # Check for consecutive hits (flowing melody)
            consecutive = 0
            max_consecutive = 0
            for v in rhythm:
                if v == 1:
                    consecutive += 1
                    max_consecutive = max(max_consecutive, consecutive)
                else:
                    consecutive = 0
            if max_consecutive >= 3:
                return 'flowing'
            return 'rhythmic'
        else:
            return 'flowing'
    
    def extract_contour_pattern(self, intensities: List[float]) -> List[str]:
        """
        Extract melodic contour from intensity changes.
        Since we don't have actual pitches, we infer contour from intensity patterns.
        Returns list of contour movements: 'up', 'down', 'stay', 'jump_up', 'jump_down'
        """
        contours = []
        prev_intensity = None
        
        for intensity in intensities:
            if intensity <= self.SYNTH_THRESHOLD:
                continue
            
            if prev_intensity is not None:
                diff = intensity - prev_intensity
                if abs(diff) < 0.02:
                    contours.append(CONTOUR_STAY)
                elif diff > 0.1:
                    contours.append(CONTOUR_JUMP_UP)
                elif diff > 0:
                    contours.append(CONTOUR_UP)
                elif diff < -0.1:
                    contours.append(CONTOUR_JUMP_DOWN)
                else:
                    contours.append(CONTOUR_DOWN)
            
            prev_intensity = intensity
        
        return contours
    
    def extract_interval_suggestions(self, bar: Dict) -> List[int]:
        """
        Generate interval suggestions based on chord context and rhythm.
        These are relative to the chord root.
        """
        rhythm = tuple(1 if v > self.SYNTH_THRESHOLD else 0 for v in bar['synth_intensities'])
        
        # Get the predominant chord for this bar
        if bar['chord_roots']:
            main_quality = Counter(bar['chord_qualities']).most_common(1)[0][0]
        else:
            main_quality = 'maj7'
        
        # Chord tones based on quality
        if 'min' in main_quality:
            chord_tones = [0, 3, 7, 10]  # Minor 7th
        elif 'dim' in main_quality:
            chord_tones = [0, 3, 6, 9]
        elif '7' in main_quality:
            chord_tones = [0, 4, 7, 10]  # Dominant 7th
        else:
            chord_tones = [0, 4, 7, 11]  # Major 7th
        
        # Scale tones for passing notes
        if 'min' in main_quality:
            scale_tones = [0, 2, 3, 5, 7, 8, 10]  # Natural minor
        else:
            scale_tones = [0, 2, 4, 5, 7, 9, 11]  # Major
        
        # Build interval pattern based on position
        intervals = []
        hit_positions = [i for i, v in enumerate(rhythm) if v == 1]
        
        for idx, pos in enumerate(hit_positions):
            beat = pos // 4  # Which beat (0-3)
            
            if pos == 0 or beat == 0:
                # Strong beat: chord tone
                intervals.append(random.choice(chord_tones))
            elif pos % 4 == 0:
                # On-beat: prefer chord tone
                intervals.append(random.choice(chord_tones))
            elif pos % 2 == 0:
                # Off-beat: scale tone
                intervals.append(random.choice(scale_tones))
            else:
                # Weak position: any scale tone or chromatic approach
                intervals.append(random.choice(scale_tones + [1, 6, 8]))
        
        return intervals
    
    def extract_patterns_from_timeline(self, filepath: str, 
                                        bpm: float = 120.0) -> Optional[Dict]:
        """
        Extract all lead/melody patterns from a timeline CSV.
        """
        timeline = self.parse_timeline_csv(filepath)
        
        if not timeline:
            return None
        
        bars = self.quantize_to_bars(timeline, bpm)
        
        if len(bars) < 2:
            return None
        
        # Extract patterns from each bar
        rhythm_patterns = []
        velocity_patterns = []
        phrase_types = []
        contour_patterns = []
        interval_patterns = []
        densities = []
        
        for bar in bars:
            intensities = bar['synth_intensities']
            
            # Binary rhythm pattern
            rhythm = tuple(1 if v > self.SYNTH_THRESHOLD else 0 for v in intensities)
            
            # Skip empty or very sparse bars
            if sum(rhythm) < 1:
                continue
            
            rhythm_patterns.append(rhythm)
            
            # Velocity pattern (0=off, 1=soft, 2=medium, 3=hard)
            velocity = []
            for v in intensities:
                if v <= self.SYNTH_THRESHOLD:
                    velocity.append(0)
                elif v <= 0.05:
                    velocity.append(1)
                elif v <= 0.15:
                    velocity.append(2)
                else:
                    velocity.append(3)
            velocity_patterns.append(tuple(velocity))
            
            # Phrase type classification
            phrase = self.classify_phrase_type(rhythm, intensities)
            phrase_types.append(phrase)
            
            # Contour pattern
            contour = self.extract_contour_pattern(intensities)
            if contour:
                contour_patterns.append(tuple(contour))
            
            # Interval suggestions
            intervals = self.extract_interval_suggestions(bar)
            if intervals:
                interval_patterns.append(tuple(intervals))
            
            # Density (notes per bar)
            densities.append(sum(rhythm))
        
        if not rhythm_patterns:
            return None
        
        # Build pattern transitions (Markov chain)
        transitions = defaultdict(Counter)
        for i in range(len(rhythm_patterns) - 1):
            current = rhythm_patterns[i]
            next_pat = rhythm_patterns[i + 1]
            transitions[current][next_pat] += 1
        
        # Convert to probabilities
        transition_probs = {}
        for pat, followers in transitions.items():
            total = sum(followers.values())
            transition_probs[pat] = {k: round(v / total, 4) for k, v in followers.items()}
        
        # Build contour transitions
        contour_transitions = defaultdict(Counter)
        for i in range(len(contour_patterns) - 1):
            if contour_patterns[i] and contour_patterns[i+1]:
                # Use last contour of current phrase to predict first of next
                current_end = contour_patterns[i][-1] if contour_patterns[i] else 'stay'
                next_start = contour_patterns[i+1][0] if contour_patterns[i+1] else 'stay'
                contour_transitions[current_end][next_start] += 1
        
        # Deduplicate patterns
        unique_rhythms = list(set(rhythm_patterns))
        unique_velocities = list(set(velocity_patterns))
        unique_contours = list(set(contour_patterns))
        unique_intervals = list(set(interval_patterns))
        
        # Phrase type distribution
        phrase_dist = dict(Counter(phrase_types))
        
        return {
            'rhythm_patterns': [list(p) for p in unique_rhythms],
            'velocity_patterns': [list(p) for p in unique_velocities],
            'contour_patterns': [list(p) for p in unique_contours],
            'interval_patterns': [list(p) for p in unique_intervals],
            'phrase_distribution': phrase_dist,
            'pattern_transitions': {
                str(list(k)): {str(list(kk)): vv for kk, vv in v.items()}
                for k, v in transition_probs.items()
            },
            'contour_transitions': {
                k: dict(v) for k, v in contour_transitions.items()
            },
            'density_stats': {
                'min': min(densities) if densities else 0,
                'max': max(densities) if densities else 0,
                'avg': round(sum(densities) / len(densities), 2) if densities else 0,
            },
            'pattern_counts': {
                'rhythms': len(unique_rhythms),
                'velocities': len(unique_velocities),
                'contours': len(unique_contours),
                'intervals': len(unique_intervals),
            },
        }


def extract_lead_patterns_enhanced(timeline_path: str, bpm: float = 120.0) -> Dict:
    """
    Drop-in function for seed_builder.py to extract lead patterns.
    """
    extractor = LeadPatternExtractor(steps_per_bar=16)
    result = extractor.extract_patterns_from_timeline(timeline_path, bpm)
    return result if result else {}


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD PATTERN GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class LearnedLeadGenerator:
    """
    Generates lead melodies using patterns learned from seeds.
    Combines rhythm patterns, contours, intervals, and phrase structures.
    """
    
    def __init__(self):
        self.genre_patterns = {}      # {genre: {rhythms: [...], contours: [...], ...}}
        self.genre_transitions = {}   # {genre: {pattern: {next: prob}}}
        self.genre_phrases = {}       # {genre: {phrase_type: count}}
        self.genre_contour_trans = {} # {genre: {contour: {next_contour: prob}}}
        self.global_patterns = {'rhythms': [], 'velocities': [], 'contours': [], 'intervals': []}
        self.global_transitions = {}
    
    def load_from_seeds(self, seeds: List[Dict]):
        """
        Load lead patterns from seed dictionaries.
        Synth/lead patterns are in instrument_patterns.pattern_transitions.synth
        """
        import json as json_module
        
        for seed in seeds:
            genre = seed.get('genre', 'unknown')
            
            # Initialize genre if needed
            if genre not in self.genre_patterns:
                self.genre_patterns[genre] = {'rhythms': [], 'velocities': [], 'contours': [], 'intervals': []}
                self.genre_transitions[genre] = defaultdict(Counter)
                self.genre_phrases[genre] = defaultdict(int)
                self.genre_contour_trans[genre] = defaultdict(Counter)
            
            # ══════════════════════════════════════════════════════════════
            # METHOD 1: Check for dedicated lead_patterns field (new format)
            # ══════════════════════════════════════════════════════════════
            lead_data = seed.get('lead_patterns', {})
            if isinstance(lead_data, dict) and lead_data.get('rhythm_patterns'):
                self._load_from_lead_data(genre, lead_data)
                continue
            
            # ══════════════════════════════════════════════════════════════
            # METHOD 2: Extract from instrument_patterns (current format)
            # ══════════════════════════════════════════════════════════════
            inst_patterns = seed.get('instrument_patterns', {})
            if not isinstance(inst_patterns, dict):
                continue
            
            # Get synth patterns from pattern_transitions
            transitions = inst_patterns.get('pattern_transitions', {})
            if isinstance(transitions, dict):
                # Try 'synth' first, then 'lead' if synth doesn't exist
                synth_trans = transitions.get('synth', {})
                if not synth_trans:
                    synth_trans = transitions.get('lead', {})
                
                if isinstance(synth_trans, dict):
                    for pat_str, followers in synth_trans.items():
                        try:
                            # Parse the pattern string "[1, 0, 0, ...]" back to list
                            pattern = json_module.loads(pat_str)
                            if isinstance(pattern, list) and len(pattern) == 16:
                                self.genre_patterns[genre]['rhythms'].append(pattern)
                                self.global_patterns['rhythms'].append(pattern)
                            
                            # Store transitions
                            if isinstance(followers, dict):
                                for next_str, prob in followers.items():
                                    self.genre_transitions[genre][pat_str][next_str] += prob
                        except (json_module.JSONDecodeError, ValueError, TypeError):
                            continue
            
            # ══════════════════════════════════════════════════════════════
            # METHOD 3: Extract from drum_patterns if it has synth/pad
            # This is where the updated rhythm_pattern_extractor puts them
            # ══════════════════════════════════════════════════════════════
            drum_patterns = inst_patterns.get('drum_patterns', {})
            if isinstance(drum_patterns, dict):
                # Get synth patterns
                synth_pats = drum_patterns.get('synth', [])
                if isinstance(synth_pats, list):
                    for pat in synth_pats:
                        if isinstance(pat, list) and len(pat) == 16:
                            self.genre_patterns[genre]['rhythms'].append(pat)
                            self.global_patterns['rhythms'].append(pat)
                
                # Also get pad patterns as melodic reference
                pad_pats = drum_patterns.get('pad', [])
                if isinstance(pad_pats, list):
                    for pat in pad_pats:
                        if isinstance(pat, list) and len(pat) == 16:
                            self.genre_patterns[genre]['rhythms'].append(pat)
                            self.global_patterns['rhythms'].append(pat)
            
            # ══════════════════════════════════════════════════════════════
            # Get synth/lead info for phrase classification
            # ══════════════════════════════════════════════════════════════
            synth_info = inst_patterns.get('synth', {})
            if isinstance(synth_info, dict):
                density = synth_info.get('density', 0)
                if density > 0:
                    if density < 0.1:
                        self.genre_phrases[genre]['sustained'] += 1
                    elif density < 0.3:
                        self.genre_phrases[genre]['sparse'] += 1
                    elif density < 0.5:
                        self.genre_phrases[genre]['rhythmic'] += 1
                    else:
                        self.genre_phrases[genre]['flowing'] += 1
            
            # Also check 'pad' patterns as melodic reference
            pad_trans = transitions.get('pad', {}) if isinstance(transitions, dict) else {}
            if isinstance(pad_trans, dict):
                for pat_str, followers in pad_trans.items():
                    try:
                        pattern = json_module.loads(pat_str)
                        if isinstance(pattern, list) and len(pattern) == 16:
                            # Pad patterns can inform melodic rhythm too
                            self.genre_patterns[genre]['rhythms'].append(pattern)
                            self.global_patterns['rhythms'].append(pattern)
                    except (json_module.JSONDecodeError, ValueError, TypeError):
                        continue
        
        # Deduplicate patterns
        self._deduplicate_patterns()
        
        # Print stats
        total_rhythms = len(self.global_patterns.get('rhythms', []))
        total_genres = len([g for g in self.genre_patterns if self.genre_patterns[g].get('rhythms')])
        print(f"  ✓ Lead patterns loaded: {total_rhythms} rhythms across {total_genres} genres")
    
    def _load_from_lead_data(self, genre: str, lead_data: Dict):
        """Load from dedicated lead_patterns field."""
        rhythms = lead_data.get('rhythm_patterns', [])
        for r in rhythms:
            if isinstance(r, list) and len(r) == 16:
                self.genre_patterns[genre]['rhythms'].append(r)
                self.global_patterns['rhythms'].append(r)
        
        velocities = lead_data.get('velocity_patterns', [])
        for v in velocities:
            if isinstance(v, list) and len(v) == 16:
                self.genre_patterns[genre]['velocities'].append(v)
                self.global_patterns['velocities'].append(v)
        
        contours = lead_data.get('contour_patterns', [])
        for c in contours:
            if isinstance(c, list):
                self.genre_patterns[genre]['contours'].append(c)
                self.global_patterns['contours'].append(c)
        
        intervals = lead_data.get('interval_patterns', [])
        for iv in intervals:
            if isinstance(iv, list):
                self.genre_patterns[genre]['intervals'].append(iv)
                self.global_patterns['intervals'].append(iv)
        
        phrases = lead_data.get('phrase_distribution', {})
        if isinstance(phrases, dict):
            for phrase_type, count in phrases.items():
                self.genre_phrases[genre][phrase_type] += count
        
        trans = lead_data.get('pattern_transitions', {})
        if isinstance(trans, dict):
            for pat_str, followers in trans.items():
                if isinstance(followers, dict):
                    for next_str, prob in followers.items():
                        self.genre_transitions[genre][pat_str][next_str] += prob
        
        contour_trans = lead_data.get('contour_transitions', {})
        if isinstance(contour_trans, dict):
            for cont, followers in contour_trans.items():
                if isinstance(followers, dict):
                    for next_cont, prob in followers.items():
                        self.genre_contour_trans[genre][cont][next_cont] += prob
    
    def _deduplicate_patterns(self):
        """Remove duplicate patterns."""
        for genre in self.genre_patterns:
            for pat_type in ['rhythms', 'velocities', 'contours', 'intervals']:
                patterns = self.genre_patterns[genre].get(pat_type, [])
                if patterns:
                    unique = list(set(tuple(p) if isinstance(p, list) else p for p in patterns))
                    self.genre_patterns[genre][pat_type] = [list(p) if isinstance(p, tuple) else p for p in unique]
        
        for pat_type in ['rhythms', 'velocities', 'contours', 'intervals']:
            patterns = self.global_patterns.get(pat_type, [])
            if patterns:
                unique = list(set(tuple(p) if isinstance(p, list) else p for p in patterns))
                self.global_patterns[pat_type] = [list(p) if isinstance(p, tuple) else p for p in unique]
    
    def get_patterns_for_genre(self, genre: str, pattern_type: str) -> List:
        """Get patterns for a specific genre and type."""
        if genre in self.genre_patterns:
            patterns = self.genre_patterns[genre].get(pattern_type, [])
            if patterns:
                return patterns
        return self.global_patterns.get(pattern_type, [])
    
    def pick_phrase_type(self, genre: str) -> str:
        """Pick a phrase type weighted by genre distribution."""
        if genre in self.genre_phrases and self.genre_phrases[genre]:
            phrases = self.genre_phrases[genre]
            total = sum(phrases.values())
            if total > 0:
                r = random.uniform(0, total)
                cumulative = 0
                for phrase, count in phrases.items():
                    cumulative += count
                    if r <= cumulative:
                        return phrase
        return random.choice(['sustained', 'flowing', 'rhythmic', 'sparse', 'staccato'])
    
    def generate_rhythm_sequence(self, genre: str, num_bars: int, 
                                  complexity: float = 0.5,
                                  section_type: str = 'verse') -> List[List[int]]:
        """
        Generate a sequence of lead rhythm patterns using Markov chains.
        """
        patterns = self.get_patterns_for_genre(genre, 'rhythms')
        
        if not patterns:
            return [self._generate_fallback_rhythm(complexity, section_type) for _ in range(num_bars)]
        
        transitions = self.genre_transitions.get(genre, {})
        sequence = []
        
        # Pick starting pattern based on section type
        if section_type in ('intro', 'outro', 'break'):
            # Prefer sparser patterns
            sparse_patterns = [p for p in patterns if sum(p) <= 4]
            current = random.choice(sparse_patterns) if sparse_patterns else random.choice(patterns)
        elif section_type in ('chorus', 'drop', 'climax'):
            # Prefer denser patterns
            dense_patterns = [p for p in patterns if sum(p) >= 4]
            current = random.choice(dense_patterns) if dense_patterns else random.choice(patterns)
        else:
            current = random.choice(patterns)
        
        sequence.append(current)
        
        for _ in range(num_bars - 1):
            current_str = str(current)
            
            # Use Markov chain with complexity-based randomness
            if current_str in transitions and random.random() > complexity * 0.4:
                followers = transitions[current_str]
                total = sum(followers.values())
                r = random.uniform(0, total)
                cumulative = 0
                
                chosen = None
                for next_str, prob in followers.items():
                    cumulative += prob
                    if r <= cumulative:
                        try:
                            chosen = json.loads(next_str)
                        except:
                            pass
                        break
                
                if chosen:
                    current = chosen
                else:
                    current = random.choice(patterns)
            else:
                # Random selection with density preference
                if random.random() < complexity * 0.3:
                    current = random.choice(patterns)
                else:
                    target_density = sum(current)
                    similar = [p for p in patterns if abs(sum(p) - target_density) <= 2]
                    current = random.choice(similar) if similar else random.choice(patterns)
            
            sequence.append(current)
        
        return sequence
    
    def generate_contour_sequence(self, num_notes: int, genre: str) -> List[str]:
        """
        Generate a melodic contour sequence.
        """
        contours = self.get_patterns_for_genre(genre, 'contours')
        contour_trans = self.genre_contour_trans.get(genre, {})
        
        if not contours and not contour_trans:
            # Fallback: generate musical contours
            return self._generate_fallback_contour(num_notes)
        
        sequence = []
        current = random.choice([CONTOUR_STAY, CONTOUR_UP, CONTOUR_DOWN])
        
        for _ in range(num_notes):
            sequence.append(current)
            
            # Use contour transitions if available
            if current in contour_trans and contour_trans[current]:
                followers = contour_trans[current]
                total = sum(followers.values())
                r = random.uniform(0, total)
                cumulative = 0
                for next_cont, prob in followers.items():
                    cumulative += prob
                    if r <= cumulative:
                        current = next_cont
                        break
            else:
                # Musical fallback: tend toward stepwise motion
                weights = {
                    CONTOUR_STAY: 0.2,
                    CONTOUR_UP: 0.3,
                    CONTOUR_DOWN: 0.3,
                    CONTOUR_JUMP_UP: 0.1,
                    CONTOUR_JUMP_DOWN: 0.1,
                }
                current = random.choices(list(weights.keys()), list(weights.values()))[0]
        
        return sequence
    
    def generate_interval_sequence(self, genre: str, rhythm_sequence: List[List[int]],
                                    chord_progression: List[str]) -> List[List[int]]:
        """
        Generate interval sequences that match the rhythm patterns.
        """
        interval_patterns = self.get_patterns_for_genre(genre, 'intervals')
        sequence = []
        
        for bar_idx, rhythm in enumerate(rhythm_sequence):
            num_hits = sum(rhythm)
            
            if num_hits == 0:
                sequence.append([])
                continue
            
            # Get chord context
            if bar_idx < len(chord_progression):
                chord_str = chord_progression[bar_idx]
                quality = chord_str[1:] if len(chord_str) > 1 else 'maj'
            else:
                quality = 'maj'
            
            # Chord tones based on quality
            if 'min' in quality.lower():
                chord_tones = [0, 3, 7, 10]
                scale_tones = [0, 2, 3, 5, 7, 8, 10]
            else:
                chord_tones = [0, 4, 7, 11]
                scale_tones = [0, 2, 4, 5, 7, 9, 11]
            
            # Try to find matching interval pattern
            matching = [p for p in interval_patterns if len(p) == num_hits]
            
            if matching:
                intervals = list(random.choice(matching))
            else:
                # Generate based on position and contour
                intervals = []
                hit_positions = [i for i, v in enumerate(rhythm) if v == 1]
                
                prev_interval = 0
                for idx, pos in enumerate(hit_positions):
                    if pos == 0:
                        interval = random.choice(chord_tones)
                    elif pos % 4 == 0:
                        interval = random.choice(chord_tones)
                    else:
                        # Stepwise motion from previous
                        step = random.choice([-2, -1, 1, 2])
                        interval = prev_interval + step
                        # Keep in scale
                        if interval not in scale_tones:
                            interval = min(scale_tones, key=lambda x: abs(x - interval))
                    
                    intervals.append(interval % 12)
                    prev_interval = interval
            
            sequence.append(intervals)
        
        return sequence
    
    def _generate_fallback_rhythm(self, complexity: float, section_type: str) -> List[int]:
        """Generate a simple lead rhythm when no learned patterns available."""
        pattern = [0] * 16
        
        # Density based on section
        if section_type in ('intro', 'outro', 'break'):
            positions = [0, 8] if complexity < 0.5 else [0, 4, 8, 12]
        elif section_type in ('chorus', 'drop'):
            positions = [0, 2, 4, 6, 8, 10, 12, 14][:int(4 + complexity * 4)]
        else:
            positions = [0, 4, 8, 12][:int(2 + complexity * 2)]
        
        for pos in positions:
            if random.random() < 0.8:
                pattern[pos] = 1
        
        return pattern
    
    def _generate_fallback_contour(self, num_notes: int) -> List[str]:
        """Generate musical contour when no learned patterns available."""
        contours = []
        direction = random.choice([1, -1])  # Start going up or down
        
        for i in range(num_notes):
            if i % 4 == 0:
                # Change direction periodically
                direction = random.choice([1, -1])
            
            if direction > 0:
                contours.append(random.choice([CONTOUR_UP, CONTOUR_STAY]))
            else:
                contours.append(random.choice([CONTOUR_DOWN, CONTOUR_STAY]))
            
            # Occasional jumps
            if random.random() < 0.1:
                contours[-1] = CONTOUR_JUMP_UP if direction > 0 else CONTOUR_JUMP_DOWN
        
        return contours


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD MIDI GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def note_name_to_midi(note: str, octave: int = 5) -> int:
    """Convert note name to MIDI number."""
    base = note[:2] if len(note) > 1 and note[1] in '#b' else note[0]
    return NOTE_TO_MIDI.get(base, 0) + (octave + 1) * 12


def parse_chord_string(chord_str: str) -> Tuple[str, str]:
    """Parse 'Amin7' → ('A', 'min7')."""
    if not chord_str:
        return ('C', 'major')
    if len(chord_str) > 1 and chord_str[1] in '#b':
        root = chord_str[:2]
        quality = chord_str[2:] if len(chord_str) > 2 else 'major'
    else:
        root = chord_str[0]
        quality = chord_str[1:] if len(chord_str) > 1 else 'major'
    return root, quality or 'major'


def get_scale_notes(root: str, quality: str, octave: int = 5) -> List[int]:
    """Get scale notes for melody generation."""
    root_midi = note_name_to_midi(root, octave)
    
    if 'min' in quality.lower():
        intervals = [0, 2, 3, 5, 7, 8, 10]  # Natural minor
    else:
        intervals = [0, 2, 4, 5, 7, 9, 11]  # Major
    
    return [root_midi + i for i in intervals]


def generate_lead_from_learned_patterns(
    lead_generator: LearnedLeadGenerator,
    genre: str,
    chord_progression: List[str],
    structure: List[Tuple[str, int]],
    complexity: int,
    humanize_amount: float,
    bpm: float,
    volume: float = 0.75,
    key: str = 'C major'
) -> List[Tuple[float, float, int, int]]:
    """
    Generate lead melody MIDI events using learned patterns.
    
    Args:
        lead_generator: Loaded LearnedLeadGenerator instance
        genre: Music genre
        chord_progression: List of chord strings
        structure: List of (section_type, num_bars) tuples
        complexity: 0-10 complexity setting
        humanize_amount: 0-1 humanization
        bpm: Beats per minute
        volume: 0-1 volume multiplier
        key: Key signature (e.g., 'C major', 'A minor')
        
    Returns:
        List of (time, duration, midi_note, velocity) tuples
    """
    notes = []
    total_bars = sum(bars for _, bars in structure)
    complexity_float = complexity / 10.0
    base_velocity = int(85 * volume)
    
    # Parse key
    key_parts = key.split()
    key_root = key_parts[0] if key_parts else 'C'
    is_minor = 'minor' in key.lower()
    
    bar_idx = 0
    chord_idx = 0
    prev_note = None
    
    for section_type, section_bars in structure:
        energy = _section_energy(section_type)
        
        # Lead plays less in intro/outro
        if section_type in ('intro', 'outro') and complexity < 7:
            # Sparse or no lead
            if random.random() < 0.3:
                bar_idx += section_bars
                chord_idx += section_bars
                continue
        
        # Generate rhythm sequence for this section
        rhythm_sequence = lead_generator.generate_rhythm_sequence(
            genre, section_bars, complexity_float, section_type
        )
        
        # Generate interval sequence
        section_chords = chord_progression[chord_idx:chord_idx + section_bars]
        interval_sequence = lead_generator.generate_interval_sequence(
            genre, rhythm_sequence, section_chords
        )
        
        # Generate contour for melodic direction
        total_notes = sum(sum(r) for r in rhythm_sequence)
        contour_sequence = lead_generator.generate_contour_sequence(total_notes, genre)
        contour_idx = 0
        
        for local_bar in range(section_bars):
            if local_bar >= len(rhythm_sequence):
                break
            
            bar_time = bar_idx * 4
            
            # Get current chord
            if chord_idx < len(chord_progression):
                chord_str = chord_progression[chord_idx]
            else:
                chord_str = chord_progression[chord_idx % len(chord_progression)] if chord_progression else 'Cmaj7'
            
            root, quality = parse_chord_string(chord_str)
            scale = get_scale_notes(root, quality, 5)  # Lead in octave 5
            root_midi = note_name_to_midi(root, 5)
            
            # Get patterns for this bar
            rhythm = rhythm_sequence[local_bar]
            intervals = interval_sequence[local_bar] if local_bar < len(interval_sequence) else []
            
            # Section energy adjustments
            section_vel = base_velocity * energy
            if section_type == 'break':
                section_vel *= 0.5
            elif section_type in ('chorus', 'drop', 'climax'):
                section_vel *= 1.1
            
            # Convert rhythm to MIDI events
            interval_idx = 0
            
            for step in range(16):
                if rhythm[step] == 1:
                    step_time = bar_time + (step / 4)
                    
                    # Get interval
                    if interval_idx < len(intervals):
                        interval = intervals[interval_idx]
                        interval_idx += 1
                    else:
                        interval = 0
                    
                    # Calculate base note
                    midi_note = root_midi + interval
                    
                    # Apply contour
                    if contour_idx < len(contour_sequence):
                        contour = contour_sequence[contour_idx]
                        contour_idx += 1
                        
                        if prev_note is not None:
                            if contour == CONTOUR_UP:
                                # Move up by step
                                candidates = [n for n in scale if n > prev_note and n <= prev_note + 4]
                                if candidates:
                                    midi_note = min(candidates)
                            elif contour == CONTOUR_DOWN:
                                # Move down by step
                                candidates = [n for n in scale if n < prev_note and n >= prev_note - 4]
                                if candidates:
                                    midi_note = max(candidates)
                            elif contour == CONTOUR_JUMP_UP:
                                midi_note = prev_note + random.choice([5, 7, 8])
                            elif contour == CONTOUR_JUMP_DOWN:
                                midi_note = prev_note - random.choice([5, 7, 8])
                            elif contour == CONTOUR_STAY:
                                midi_note = prev_note
                    
                    # Keep in playable range (60-84 = C4-C6)
                    while midi_note > 84:
                        midi_note -= 12
                    while midi_note < 60:
                        midi_note += 12
                    
                    # Calculate duration
                    next_hit = None
                    for future_step in range(step + 1, 16):
                        if rhythm[future_step] == 1:
                            next_hit = future_step
                            break
                    
                    if next_hit:
                        duration = (next_hit - step) / 4 - 0.05
                    else:
                        duration = (16 - step) / 4 - 0.1
                    
                    # Phrase type affects duration
                    phrase = lead_generator.pick_phrase_type(genre)
                    if phrase == 'staccato':
                        duration = min(duration, 0.25)
                    elif phrase == 'sustained':
                        duration = min(duration * 1.5, 2.0)
                    
                    duration = max(0.1, duration)
                    
                    # Humanize
                    h_offset = (random.random() - 0.5) * 0.025 * humanize_amount
                    vel_variation = random.randint(-10, 10) * humanize_amount
                    
                    velocity = int(section_vel + vel_variation)
                    velocity = max(40, min(127, velocity))
                    
                    # Accent strong beats
                    if step == 0:
                        velocity = min(127, velocity + 8)
                    elif step == 8:
                        velocity = min(127, velocity + 4)
                    
                    notes.append((
                        step_time + h_offset,
                        duration,
                        midi_note,
                        velocity
                    ))
                    
                    prev_note = midi_note
            
            bar_idx += 1
            chord_idx += 1
    
    return notes


def _section_energy(section_type: str) -> float:
    """Get energy level for a section type."""
    energy_map = {
        'intro': 0.4, 'verse': 0.6, 'pre_chorus': 0.7, 'chorus': 0.9,
        'drop': 1.0, 'bridge': 0.55, 'breakdown': 0.4, 'build': 0.75,
        'outro': 0.35, 'break': 0.25, 'climax': 1.0, 'tension': 0.7,
        'resolution': 0.5, 'exposition': 0.6, 'development': 0.75,
        'recapitulation': 0.85, 'coda': 0.45,
    }
    return energy_map.get(section_type, 0.6)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST / DEMO
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"Extracting lead patterns from: {filepath}")
        
        extractor = LeadPatternExtractor()
        result = extractor.extract_patterns_from_timeline(filepath)
        
        if result:
            print(f"\n✓ Patterns extracted successfully!")
            print(f"\nPattern counts:")
            for ptype, count in result['pattern_counts'].items():
                print(f"  {ptype}: {count}")
            
            print(f"\nPhrase distribution:")
            for phrase, count in result['phrase_distribution'].items():
                print(f"  {phrase}: {count}")
            
            print(f"\nDensity stats:")
            stats = result['density_stats']
            print(f"  Min: {stats['min']} notes/bar")
            print(f"  Max: {stats['max']} notes/bar")
            print(f"  Avg: {stats['avg']} notes/bar")
            
            print(f"\nSample lead rhythms:")
            for i, pat in enumerate(result['rhythm_patterns'][:5]):
                visual = ''.join(['█' if v else '·' for v in pat])
                print(f"  {visual}")
            
            print(f"\nSample contours:")
            for i, cont in enumerate(result['contour_patterns'][:3]):
                print(f"  {' → '.join(cont[:8])}")
        else:
            print("Failed to extract patterns")
    else:
        print("Usage: python lead_pattern_extractor.py <timeline.csv>")
        print("\nThis module provides:")
        print("  - LeadPatternExtractor: Extract melody patterns from CSVs")
        print("  - LearnedLeadGenerator: Generate melodies from seeds")
        print("  - generate_lead_from_learned_patterns(): Full melody generator")
