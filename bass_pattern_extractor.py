"""
Bass Pattern Extractor & Generator
Learns melodic and rhythmic bass patterns from timeline CSVs.
Extracts: rhythm patterns, note intervals, phrase shapes, and groove characteristics.
"""

import csv
import json
import random
import math
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional, Any


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

# Chord intervals for determining chord tones
CHORD_INTERVALS = {
    'major': [0, 4, 7], 'minor': [0, 3, 7], 'maj7': [0, 4, 7, 11],
    'min7': [0, 3, 7, 10], '7': [0, 4, 7, 10], 'dim': [0, 3, 6],
    'dim7': [0, 3, 6, 9], 'aug': [0, 4, 8], 'sus4': [0, 5, 7],
    'sus2': [0, 2, 7], 'min': [0, 3, 7], 'maj': [0, 4, 7],
}


# ═══════════════════════════════════════════════════════════════════════════════
# BASS PATTERN EXTRACTOR
# ═══════════════════════════════════════════════════════════════════════════════

class BassPatternExtractor:
    """
    Extracts bass patterns from timeline CSV files.
    Learns: rhythms, intervals relative to chord, phrase shapes, groove types.
    """
    
    BASS_THRESHOLD = 0.015  # Minimum intensity to count as a bass hit
    
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
                            'bass': float(row.get('bass', 0)),
                            'chord_root': row.get('chord_root', 'C'),
                            'chord_quality': row.get('chord_quality', 'maj7'),
                        }
                        rows.append(parsed)
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
        return rows
    
    def quantize_to_bars(self, timeline: List[Dict], bpm: float) -> List[Dict]:
        """
        Quantize timeline into bars with bass patterns and chord context.
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
                'bass_intensities': [0.0] * self.steps_per_bar,
                'chord_roots': [],
                'chord_qualities': [],
            })
        
        start_time = timeline[0]['time']
        
        # Fill bars with data
        for row in timeline:
            relative_time = row['time'] - start_time
            bar_idx = min(int(relative_time / seconds_per_bar), num_bars - 1)
            time_in_bar = relative_time - (bar_idx * seconds_per_bar)
            step_idx = min(int(time_in_bar / seconds_per_step), self.steps_per_bar - 1)
            
            # Take max intensity at each step
            bars[bar_idx]['bass_intensities'][step_idx] = max(
                bars[bar_idx]['bass_intensities'][step_idx], 
                row['bass']
            )
            
            # Track chords
            if row['chord_root']:
                bars[bar_idx]['chord_roots'].append(row['chord_root'])
                bars[bar_idx]['chord_qualities'].append(row['chord_quality'])
        
        return bars
    
    def classify_groove_type(self, rhythm: Tuple[int, ...], intensities: List[float]) -> str:
        """
        Classify the bass groove type based on rhythm pattern.
        
        Types:
        - 'sustained': Long notes, few hits (808 style)
        - 'rhythmic': Regular pattern, follows kick
        - 'melodic': Many notes, walking bass style
        - 'syncopated': Off-beat emphasis
        - 'sparse': Minimal, space-focused
        """
        hits = sum(rhythm)
        
        if hits <= 2:
            return 'sustained'
        elif hits <= 4:
            on_beats = sum(rhythm[i] for i in [0, 4, 8, 12])
            off_beats = hits - on_beats
            if off_beats > on_beats:
                return 'syncopated'
            return 'sparse'
        elif hits <= 8:
            on_beats = sum(rhythm[i] for i in [0, 4, 8, 12])
            if on_beats >= hits * 0.6:
                return 'rhythmic'
            return 'syncopated'
        else:
            return 'melodic'
    
    def extract_interval_pattern(self, bar: Dict) -> Tuple[int, ...]:
        """
        Extract the interval pattern relative to the main chord root.
        """
        rhythm = tuple(1 if v > self.BASS_THRESHOLD else 0 for v in bar['bass_intensities'])
        
        # Get the predominant chord root for this bar
        if bar['chord_roots']:
            main_root = Counter(bar['chord_roots']).most_common(1)[0][0]
            main_quality = Counter(bar['chord_qualities']).most_common(1)[0][0]
        else:
            main_root = 'C'
            main_quality = 'maj7'
        
        # Get chord tones for this chord
        chord_intervals = CHORD_INTERVALS.get(main_quality, CHORD_INTERVALS['major'])
        
        # Build interval pattern based on position in bar
        intervals = []
        for i, hit in enumerate(rhythm):
            if hit:
                if i == 0:
                    intervals.append(0)  # Root on beat 1
                elif i == 8:
                    intervals.append(random.choice([0, 7]))  # Root or fifth on beat 3
                elif i in [4, 12]:
                    intervals.append(random.choice(chord_intervals))
                else:
                    intervals.append(random.choice(chord_intervals + [2, 5, 10]))
        
        return tuple(intervals)
    
    def extract_patterns_from_timeline(self, filepath: str, 
                                        bpm: float = 120.0) -> Optional[Dict]:
        """
        Extract all bass patterns from a timeline CSV.
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
        groove_types = []
        interval_patterns = []
        densities = []
        
        for bar in bars:
            intensities = bar['bass_intensities']
            
            # Binary rhythm pattern
            rhythm = tuple(1 if v > self.BASS_THRESHOLD else 0 for v in intensities)
            
            # Skip empty bars
            if sum(rhythm) == 0:
                continue
            
            rhythm_patterns.append(rhythm)
            
            # Velocity pattern (0=off, 1=soft, 2=medium, 3=hard)
            velocity = []
            for v in intensities:
                if v <= self.BASS_THRESHOLD:
                    velocity.append(0)
                elif v <= 0.05:
                    velocity.append(1)
                elif v <= 0.12:
                    velocity.append(2)
                else:
                    velocity.append(3)
            velocity_patterns.append(tuple(velocity))
            
            # Groove classification
            groove = self.classify_groove_type(rhythm, intensities)
            groove_types.append(groove)
            
            # Interval pattern
            intervals = self.extract_interval_pattern(bar)
            if intervals:
                interval_patterns.append(intervals)
            
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
        
        # Deduplicate patterns
        unique_rhythms = list(set(rhythm_patterns))
        unique_velocities = list(set(velocity_patterns))
        unique_intervals = list(set(interval_patterns))
        
        # Groove type distribution
        groove_dist = dict(Counter(groove_types))
        
        return {
            'rhythm_patterns': [list(p) for p in unique_rhythms],
            'velocity_patterns': [list(p) for p in unique_velocities],
            'interval_patterns': [list(p) for p in unique_intervals],
            'groove_distribution': groove_dist,
            'pattern_transitions': {
                str(list(k)): {str(list(kk)): vv for kk, vv in v.items()}
                for k, v in transition_probs.items()
            },
            'density_stats': {
                'min': min(densities) if densities else 0,
                'max': max(densities) if densities else 0,
                'avg': round(sum(densities) / len(densities), 2) if densities else 0,
            },
            'pattern_counts': {
                'rhythms': len(unique_rhythms),
                'velocities': len(unique_velocities),
                'intervals': len(unique_intervals),
            },
        }


def extract_bass_patterns_enhanced(timeline_path: str, bpm: float = 120.0) -> Dict:
    """
    Drop-in function for seed_builder.py to extract bass patterns.
    """
    extractor = BassPatternExtractor(steps_per_bar=16)
    result = extractor.extract_patterns_from_timeline(timeline_path, bpm)
    return result if result else {}


# ═══════════════════════════════════════════════════════════════════════════════
# BASS PATTERN GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class LearnedBassGenerator:
    """
    Generates bass lines using patterns learned from seeds.
    Combines rhythm patterns, intervals, and groove characteristics.
    """
    
    def __init__(self):
        self.genre_patterns = {}      # {genre: {rhythms: [...], intervals: [...], ...}}
        self.genre_transitions = {}   # {genre: {pattern: {next: prob}}}
        self.genre_grooves = {}       # {genre: {groove_type: count}}
        self.global_patterns = {'rhythms': [], 'velocities': [], 'intervals': []}
        self.global_transitions = {}

    def load_from_seeds(self, seeds: List[Dict]):
        """
        Load bass patterns from seed dictionaries.
        Bass patterns are stored in instrument_patterns.pattern_transitions.bass
        """
        for seed in seeds:
            genre = seed.get('genre', 'unknown')

            # Initialize genre if needed
            if genre not in self.genre_patterns:
                self.genre_patterns[genre] = {'rhythms': [], 'velocities': [], 'intervals': []}
                self.genre_transitions[genre] = defaultdict(Counter)
                self.genre_grooves[genre] = defaultdict(int)

            # ══════════════════════════════════════════════════════════════
            # METHOD 1: Check for dedicated bass_patterns field (new format)
            # ══════════════════════════════════════════════════════════════
            bass_data = seed.get('bass_patterns', {})
            if isinstance(bass_data, dict) and bass_data.get('rhythm_patterns'):
                rhythms = bass_data.get('rhythm_patterns', [])
                for r in rhythms:
                    if isinstance(r, list) and len(r) == 16:
                        self.genre_patterns[genre]['rhythms'].append(r)
                        self.global_patterns['rhythms'].append(r)

                velocities = bass_data.get('velocity_patterns', [])
                for v in velocities:
                    if isinstance(v, list) and len(v) == 16:
                        self.genre_patterns[genre]['velocities'].append(v)
                        self.global_patterns['velocities'].append(v)

                intervals = bass_data.get('interval_patterns', [])
                for iv in intervals:
                    if isinstance(iv, list):
                        self.genre_patterns[genre]['intervals'].append(iv)
                        self.global_patterns['intervals'].append(iv)

                grooves = bass_data.get('groove_distribution', {})
                if isinstance(grooves, dict):
                    for groove_type, count in grooves.items():
                        self.genre_grooves[genre][groove_type] += count

                trans = bass_data.get('pattern_transitions', {})
                if isinstance(trans, dict):
                    for pat_str, followers in trans.items():
                        if isinstance(followers, dict):
                            for next_str, prob in followers.items():
                                self.genre_transitions[genre][pat_str][next_str] += prob
                continue  # Got data from new format, skip old format check

            # ══════════════════════════════════════════════════════════════
            # METHOD 2: Extract from instrument_patterns (current format)
            # ══════════════════════════════════════════════════════════════
            inst_patterns = seed.get('instrument_patterns', {})
            if not isinstance(inst_patterns, dict):
                continue

            # Get bass patterns from pattern_transitions
            transitions = inst_patterns.get('pattern_transitions', {})
            if isinstance(transitions, dict):
                bass_trans = transitions.get('bass', {})
                if isinstance(bass_trans, dict):
                    for pat_str, followers in bass_trans.items():
                        # pat_str is like "[1, 0, 0, 0, 1, 0, ...]"
                        try:
                            # Parse the pattern string back to list
                            import json as json_module
                            pattern = json_module.loads(pat_str)
                            if isinstance(pattern, list) and len(pattern) == 16:
                                self.genre_patterns[genre]['rhythms'].append(pattern)
                                self.global_patterns['rhythms'].append(pattern)

                            # Also store transitions
                            if isinstance(followers, dict):
                                for next_str, prob in followers.items():
                                    self.genre_transitions[genre][pat_str][next_str] += prob
                        except (json_module.JSONDecodeError, ValueError):
                            continue

            # Get bass density/velocity info from instrument_patterns.bass
            bass_info = inst_patterns.get('bass', {})
            if isinstance(bass_info, dict):
                hits = bass_info.get('hits', [])
                if hits:
                    # Classify groove type based on density
                    density = bass_info.get('density', 0)
                    if density < 0.1:
                        self.genre_grooves[genre]['sustained'] += 1
                    elif density < 0.3:
                        self.genre_grooves[genre]['sparse'] += 1
                    elif density < 0.5:
                        self.genre_grooves[genre]['rhythmic'] += 1
                    else:
                        self.genre_grooves[genre]['melodic'] += 1

        # ══════════════════════════════════════════════════════════════
        # Deduplicate patterns
        # ══════════════════════════════════════════════════════════════
        for genre in self.genre_patterns:
            for pat_type in ['rhythms', 'velocities', 'intervals']:
                patterns = self.genre_patterns[genre].get(pat_type, [])
                if patterns:
                    unique = list(set(tuple(p) for p in patterns))
                    self.genre_patterns[genre][pat_type] = [list(p) for p in unique]

        for pat_type in ['rhythms', 'velocities', 'intervals']:
            patterns = self.global_patterns.get(pat_type, [])
            if patterns:
                unique = list(set(tuple(p) for p in patterns))
                self.global_patterns[pat_type] = [list(p) for p in unique]

        # Print stats
        total_rhythms = len(self.global_patterns.get('rhythms', []))
        total_genres = len([g for g in self.genre_patterns if self.genre_patterns[g].get('rhythms')])
        print(f"  ✓ Bass patterns loaded: {total_rhythms} rhythms across {total_genres} genres")

    def get_patterns_for_genre(self, genre: str, pattern_type: str) -> List[List[int]]:
        """Get patterns for a specific genre and type."""
        if genre in self.genre_patterns:
            patterns = self.genre_patterns[genre].get(pattern_type, [])
            if patterns:
                return patterns
        return self.global_patterns.get(pattern_type, [])
    
    def pick_groove_type(self, genre: str) -> str:
        """Pick a groove type weighted by genre distribution."""
        if genre in self.genre_grooves and self.genre_grooves[genre]:
            grooves = self.genre_grooves[genre]
            total = sum(grooves.values())
            r = random.uniform(0, total)
            cumulative = 0
            for groove, count in grooves.items():
                cumulative += count
                if r <= cumulative:
                    return groove
        return random.choice(['sustained', 'rhythmic', 'melodic', 'syncopated', 'sparse'])
    
    def generate_rhythm_sequence(self, genre: str, num_bars: int, 
                                  complexity: float = 0.5) -> List[List[int]]:
        """
        Generate a sequence of bass rhythm patterns using Markov chains.
        """
        patterns = self.get_patterns_for_genre(genre, 'rhythms')
        
        if not patterns:
            return [self._generate_fallback_rhythm(complexity) for _ in range(num_bars)]
        
        transitions = self.genre_transitions.get(genre, {})
        sequence = []
        
        # Pick starting pattern
        current = random.choice(patterns)
        sequence.append(current)
        
        for _ in range(num_bars - 1):
            current_str = str(current)
            
            # Use Markov chain with some randomness based on complexity
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
                if random.random() < complexity * 0.3:
                    current = random.choice(patterns)
                else:
                    target_density = sum(current)
                    similar = [p for p in patterns if abs(sum(p) - target_density) <= 2]
                    current = random.choice(similar) if similar else random.choice(patterns)
            
            sequence.append(current)
        
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
            
            # Try to find an interval pattern with matching length
            matching = [p for p in interval_patterns if len(p) == num_hits]
            
            if matching:
                intervals = list(random.choice(matching))
            else:
                # Generate intervals based on position
                intervals = []
                hit_positions = [i for i, v in enumerate(rhythm) if v == 1]
                
                for pos in hit_positions:
                    if pos == 0:
                        intervals.append(0)  # Root on beat 1
                    elif pos == 8:
                        intervals.append(random.choice([0, 7]))
                    elif pos in [4, 12]:
                        intervals.append(random.choice([0, 4, 7]))
                    else:
                        intervals.append(random.choice([0, 2, 3, 4, 5, 7, 10]))
            
            sequence.append(intervals)
        
        return sequence
    
    def _generate_fallback_rhythm(self, complexity: float) -> List[int]:
        """Generate a simple bass rhythm when no learned patterns available."""
        pattern = [0] * 16
        
        pattern[0] = 1  # Always hit beat 1
        
        if complexity > 0.3:
            pattern[8] = 1
        if complexity > 0.5:
            pattern[4] = 1
            pattern[12] = 1
        if complexity > 0.7:
            for i in [2, 6, 10, 14]:
                if random.random() < complexity * 0.4:
                    pattern[i] = 1
        
        return pattern
    
    def mutate_pattern(self, pattern: List[int], rate: float = 0.1) -> List[int]:
        """Slightly mutate a pattern for variation."""
        mutated = pattern.copy()
        for i in range(len(mutated)):
            if random.random() < rate:
                mutated[i] = 1 - mutated[i]
        if sum(mutated) == 0:
            mutated[0] = 1
        return mutated


# ═══════════════════════════════════════════════════════════════════════════════
# BASS MIDI GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def note_name_to_midi(note: str, octave: int = 2) -> int:
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


def generate_bass_from_learned_patterns(
    bass_generator: LearnedBassGenerator,
    genre: str,
    chord_progression: List[str],
    structure: List[Tuple[str, int]],
    complexity: int,
    humanize_amount: float,
    bpm: float,
    volume: float = 0.8
) -> List[Tuple[float, float, int, int]]:
    """
    Generate bass MIDI events using learned patterns.
    
    Args:
        bass_generator: Loaded LearnedBassGenerator instance
        genre: Music genre
        chord_progression: List of chord strings
        structure: List of (section_type, num_bars) tuples
        complexity: 0-10 complexity setting
        humanize_amount: 0-1 humanization
        bpm: Beats per minute
        volume: 0-1 volume multiplier
        
    Returns:
        List of (time, duration, midi_note, velocity) tuples
    """
    notes = []
    total_bars = sum(bars for _, bars in structure)
    complexity_float = complexity / 10.0
    base_velocity = int(90 * volume)
    
    # Generate rhythm sequences
    rhythm_sequence = bass_generator.generate_rhythm_sequence(
        genre, total_bars, complexity_float
    )
    
    # Generate interval sequences
    interval_sequence = bass_generator.generate_interval_sequence(
        genre, rhythm_sequence, chord_progression
    )
    
    bar_idx = 0
    chord_idx = 0
    
    for section_type, section_bars in structure:
        energy = _section_energy(section_type)
        
        for local_bar in range(section_bars):
            if bar_idx >= len(rhythm_sequence):
                break
            
            bar_time = bar_idx * 4
            
            # Get current chord
            if chord_idx < len(chord_progression):
                chord_str = chord_progression[chord_idx]
            else:
                chord_str = chord_progression[chord_idx % len(chord_progression)] if chord_progression else 'Cmaj7'
            
            root, quality = parse_chord_string(chord_str)
            root_midi = note_name_to_midi(root, 2)
            
            # Get patterns for this bar
            rhythm = rhythm_sequence[bar_idx] if bar_idx < len(rhythm_sequence) else [1] + [0] * 15
            intervals = interval_sequence[bar_idx] if bar_idx < len(interval_sequence) else [0]
            
            # Section modifications
            if section_type == 'intro':
                fade = (local_bar + 1) / max(1, section_bars)
                energy *= fade
            elif section_type == 'outro':
                fade = 1.0 - (local_bar / max(1, section_bars))
                energy *= fade
            elif section_type == 'break':
                energy *= 0.3
            elif section_type == 'build':
                build_pct = (local_bar + 1) / section_bars
                energy *= (0.5 + build_pct * 0.5)
            
            # Convert rhythm pattern to MIDI events
            interval_idx = 0
            
            for step in range(16):
                if rhythm[step] == 1:
                    step_time = bar_time + (step / 4)
                    
                    # Get interval for this hit
                    if interval_idx < len(intervals):
                        interval = intervals[interval_idx]
                        interval_idx += 1
                    else:
                        interval = 0
                    
                    # Calculate MIDI note
                    midi_note = root_midi + interval
                    
                    # Keep in bass range (28-60)
                    while midi_note > 60:
                        midi_note -= 12
                    while midi_note < 28:
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
                    
                    # For sustained genres, extend notes
                    groove = bass_generator.pick_groove_type(genre)
                    if groove == 'sustained' and sum(rhythm) <= 2:
                        duration = min(duration * 1.5, 3.8)
                    
                    duration = max(0.1, duration)
                    
                    # Humanize
                    h_offset = (random.random() - 0.5) * 0.02 * humanize_amount
                    vel_variation = random.randint(-8, 8) * humanize_amount
                    
                    velocity = int(base_velocity * energy + vel_variation)
                    velocity = max(40, min(127, velocity))
                    
                    if step == 0:
                        velocity = min(127, velocity + 10)
                    
                    notes.append((
                        step_time + h_offset,
                        duration,
                        midi_note,
                        velocity
                    ))
            
            bar_idx += 1
            chord_idx += 1
    
    return notes


def _section_energy(section_type: str) -> float:
    """Get energy level for a section type."""
    energy_map = {
        'intro': 0.5, 'verse': 0.7, 'pre_chorus': 0.8, 'chorus': 1.0,
        'drop': 1.0, 'bridge': 0.6, 'breakdown': 0.4, 'build': 0.8,
        'outro': 0.5, 'break': 0.3, 'climax': 1.0, 'tension': 0.75,
        'resolution': 0.6, 'exposition': 0.7, 'development': 0.8,
        'recapitulation': 0.9, 'coda': 0.5,
    }
    return energy_map.get(section_type, 0.7)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST / DEMO
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"Extracting bass patterns from: {filepath}")
        
        extractor = BassPatternExtractor()
        result = extractor.extract_patterns_from_timeline(filepath)
        
        if result:
            print(f"\n✓ Patterns extracted successfully!")
            print(f"\nPattern counts:")
            for ptype, count in result['pattern_counts'].items():
                print(f"  {ptype}: {count}")
            
            print(f"\nGroove distribution:")
            for groove, count in result['groove_distribution'].items():
                print(f"  {groove}: {count}")
            
            print(f"\nDensity stats:")
            stats = result['density_stats']
            print(f"  Min: {stats['min']} notes/bar")
            print(f"  Max: {stats['max']} notes/bar")
            print(f"  Avg: {stats['avg']} notes/bar")
            
            print(f"\nSample bass rhythms:")
            for i, pat in enumerate(result['rhythm_patterns'][:5]):
                visual = ''.join(['█' if v else '·' for v in pat])
                print(f"  {visual}")
        else:
            print("Failed to extract patterns")
    else:
        print("Usage: python bass_pattern_extractor.py <timeline.csv>")
