"""
═══════════════════════════════════════════════════════════════════════════════
  RHYTHM PATTERN EXTRACTOR (Complete Version)
  Extracts drum, bass, synth, AND pad patterns from timeline CSVs.
  These patterns are used by Markov chains to generate unique rhythms.
═══════════════════════════════════════════════════════════════════════════════
"""

import csv
import json
import random
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional


class RhythmPatternExtractor:
    """
    Extracts quantized rhythm patterns from timeline CSV files.
    Converts continuous intensity values into discrete 16-step patterns per bar.
    Includes: kick, snare, hihat, bass, synth, and pad extraction.
    """
    
    THRESHOLDS = {
        'kick': 0.03,
        'snare': 0.02,
        'hihat': 0.01,
        'bass': 0.02,
        'synth': 0.02,
        'pad': 0.02,
    }
    
    VELOCITY_LEVELS = {
        'soft': 0.05,
        'medium': 0.10,
        'hard': 0.20,
    }
    
    def __init__(self, steps_per_bar: int = 16):
        self.steps_per_bar = steps_per_bar
        
    def parse_timeline_csv(self, filepath: str) -> List[Dict]:
        """Parse a timeline CSV file into a list of time-stamped events."""
        rows = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    try:
                        parsed = {
                            'time': float(row.get('time_seconds', 0)),
                            'kick': float(row.get('kick', 0)),
                            'snare': float(row.get('snare', 0)),
                            'hihat': float(row.get('hihat', 0)),
                            'bass': float(row.get('bass', 0)),
                            'synth': float(row.get('synth', 0)),
                            'pad': float(row.get('pad', 0)),
                            'chord_root': row.get('chord_root', 'C'),
                            'chord_quality': row.get('chord_quality', 'maj7'),
                        }
                        rows.append(parsed)
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
        return rows
    
    def estimate_bpm(self, timeline: List[Dict], default_bpm: float = 120.0) -> float:
        """Estimate BPM from kick drum patterns."""
        if len(timeline) < 10:
            return default_bpm
            
        kick_times = [row['time'] for row in timeline if row['kick'] > self.THRESHOLDS['kick'] * 2]
        
        if len(kick_times) < 4:
            return default_bpm
            
        intervals = [kick_times[i+1] - kick_times[i] for i in range(len(kick_times)-1)]
        valid_intervals = [i for i in intervals if 0.2 < i < 2.0]
        
        if not valid_intervals:
            return default_bpm
            
        quantized = [round(i * 20) / 20 for i in valid_intervals]
        most_common = Counter(quantized).most_common(1)
        
        if most_common:
            beat_interval = most_common[0][0]
            estimated_bpm = 60.0 / beat_interval
            
            while estimated_bpm < 60:
                estimated_bpm *= 2
            while estimated_bpm > 180:
                estimated_bpm /= 2
                
            return round(estimated_bpm, 1)
            
        return default_bpm
    
    def quantize_to_bars(self, timeline: List[Dict], bpm: float) -> List[Dict[str, List[float]]]:
        """Quantize timeline data into bars with step-based patterns."""
        if not timeline:
            return []
            
        seconds_per_beat = 60.0 / bpm
        seconds_per_bar = seconds_per_beat * 4
        seconds_per_step = seconds_per_bar / self.steps_per_bar
        
        total_duration = timeline[-1]['time'] - timeline[0]['time']
        num_bars = int(total_duration / seconds_per_bar) + 1
        
        # Initialize bars with all instruments
        bars = []
        for _ in range(num_bars):
            bars.append({
                'kick': [0.0] * self.steps_per_bar,
                'snare': [0.0] * self.steps_per_bar,
                'hihat': [0.0] * self.steps_per_bar,
                'bass': [0.0] * self.steps_per_bar,
                'synth': [0.0] * self.steps_per_bar,
                'pad': [0.0] * self.steps_per_bar,
                'chord_roots': [],
            })
        
        start_time = timeline[0]['time']
        
        for row in timeline:
            relative_time = row['time'] - start_time
            bar_idx = int(relative_time / seconds_per_bar)
            
            if bar_idx >= num_bars:
                bar_idx = num_bars - 1
                
            time_in_bar = relative_time - (bar_idx * seconds_per_bar)
            step_idx = int(time_in_bar / seconds_per_step)
            
            if step_idx >= self.steps_per_bar:
                step_idx = self.steps_per_bar - 1
            
            # Take maximum intensity at each step for all instruments
            for inst in ['kick', 'snare', 'hihat', 'bass', 'synth', 'pad']:
                bars[bar_idx][inst][step_idx] = max(bars[bar_idx][inst][step_idx], row[inst])
            
            if row['chord_root']:
                bars[bar_idx]['chord_roots'].append(row['chord_root'])
        
        return bars
    
    def convert_to_binary_pattern(self, intensities: List[float], threshold: float) -> Tuple[int, ...]:
        """Convert intensity values to binary pattern (hit/no-hit)."""
        return tuple(1 if v > threshold else 0 for v in intensities)
    
    def convert_to_velocity_pattern(self, intensities: List[float], threshold: float) -> Tuple[int, ...]:
        """Convert intensity values to velocity pattern (0, 1, 2, 3 levels)."""
        pattern = []
        for v in intensities:
            if v <= threshold:
                pattern.append(0)
            elif v <= self.VELOCITY_LEVELS['soft']:
                pattern.append(1)
            elif v <= self.VELOCITY_LEVELS['medium']:
                pattern.append(2)
            else:
                pattern.append(3)
        return tuple(pattern)
    
    def extract_patterns_from_timeline(self, filepath: str, 
                                        provided_bpm: Optional[float] = None) -> Optional[Dict]:
        """
        Extract all rhythm patterns from a single timeline CSV.
        """
        timeline = self.parse_timeline_csv(filepath)
        
        if not timeline:
            return None
            
        bpm = provided_bpm or self.estimate_bpm(timeline)
        bars = self.quantize_to_bars(timeline, bpm)
        
        if len(bars) < 2:
            return None
        
        # All instruments to extract
        all_instruments = ['kick', 'snare', 'hihat', 'bass', 'synth', 'pad']
        
        patterns = {inst: [] for inst in all_instruments}
        velocity_patterns = {inst: [] for inst in all_instruments}
        
        for bar in bars:
            for inst in all_instruments:
                binary = self.convert_to_binary_pattern(bar[inst], self.THRESHOLDS[inst])
                velocity = self.convert_to_velocity_pattern(bar[inst], self.THRESHOLDS[inst])
                
                if sum(binary) > 0:
                    patterns[inst].append(binary)
                    velocity_patterns[inst].append(velocity)
        
        # Build pattern transitions (Markov chains) for ALL instruments
        transitions = {}
        for inst in all_instruments:
            inst_patterns = patterns[inst]
            if len(inst_patterns) < 2:
                continue
                
            trans = defaultdict(Counter)
            for i in range(len(inst_patterns) - 1):
                current = inst_patterns[i]
                next_pat = inst_patterns[i + 1]
                trans[current][next_pat] += 1
            
            transitions[inst] = {}
            for pat, followers in trans.items():
                total = sum(followers.values())
                transitions[inst][pat] = {k: round(v / total, 4) for k, v in followers.items()}
        
        # Deduplicate patterns
        unique_patterns = {inst: list(set(pats)) for inst, pats in patterns.items()}
        unique_velocity = {inst: list(set(pats)) for inst, pats in velocity_patterns.items()}
        
        return {
            'bpm': bpm,
            'num_bars': len(bars),
            'drum_patterns': {
                inst: [list(p) for p in unique_patterns[inst]]
                for inst in all_instruments
            },
            'drum_velocity_patterns': {
                inst: [list(p) for p in unique_velocity[inst]]
                for inst in all_instruments
            },
            'bass_patterns': [list(p) for p in unique_patterns['bass']],
            'bass_velocity_patterns': [list(p) for p in unique_velocity['bass']],
            'pattern_transitions': {
                inst: {
                    str(list(k)): {str(list(kk)): vv for kk, vv in v.items()}
                    for k, v in trans.items()
                }
                for inst, trans in transitions.items()
            },
            'pattern_counts': {inst: len(unique_patterns[inst]) for inst in all_instruments},
        }


def extract_instrument_patterns_enhanced(timeline_path: str, bpm: float = 120.0) -> Dict:
    """Drop-in replacement for seed_builder.py"""
    extractor = RhythmPatternExtractor(steps_per_bar=16)
    result = extractor.extract_patterns_from_timeline(timeline_path, bpm)
    return result if result else {}


# ═══════════════════════════════════════════════════════════════════════════════
# LEARNED PATTERN GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class LearnedPatternGenerator:
    """Generates new patterns using Markov chains from learned seeds."""
    
    def __init__(self):
        self.genre_patterns = {}
        self.genre_transitions = {}
        self.global_patterns = {'kick': [], 'snare': [], 'hihat': [], 'bass': [], 'synth': [], 'pad': []}
        self.global_transitions = {}
        
    def load_from_seeds(self, seeds: List[Dict]):
        """Load patterns from a list of seed dictionaries."""
        for seed in seeds:
            genre = seed.get('genre', 'unknown')
            patterns = seed.get('instrument_patterns', {})
            
            if not patterns:
                continue
            
            if genre not in self.genre_patterns:
                self.genre_patterns[genre] = {'kick': [], 'snare': [], 'hihat': [], 'bass': [], 'synth': [], 'pad': []}
                self.genre_transitions[genre] = {}
            
            # Collect drum patterns (including synth and pad)
            drum_pats = patterns.get('drum_patterns', {})
            for inst in ['kick', 'snare', 'hihat', 'synth', 'pad']:
                inst_pats = drum_pats.get(inst, [])
                if isinstance(inst_pats, list):
                    for p in inst_pats:
                        if isinstance(p, list) and len(p) == 16:
                            self.genre_patterns[genre][inst].append(p)
                            self.global_patterns[inst].append(p)
            
            # Collect bass patterns
            bass_pats = patterns.get('bass_patterns', [])
            if isinstance(bass_pats, list):
                for p in bass_pats:
                    if isinstance(p, list) and len(p) == 16:
                        self.genre_patterns[genre]['bass'].append(p)
                        self.global_patterns['bass'].append(p)
            
            # Collect transitions
            trans = patterns.get('pattern_transitions', {})
            for inst, inst_trans in trans.items():
                if not isinstance(inst_trans, dict):
                    continue
                if inst not in self.genre_transitions[genre]:
                    self.genre_transitions[genre][inst] = defaultdict(Counter)
                for pat_str, followers in inst_trans.items():
                    if isinstance(followers, dict):
                        for next_str, prob in followers.items():
                            self.genre_transitions[genre][inst][pat_str][next_str] += prob
        
        # Deduplicate patterns
        for genre in self.genre_patterns:
            for inst in self.genre_patterns[genre]:
                unique = list(set(tuple(p) for p in self.genre_patterns[genre][inst] if p))
                self.genre_patterns[genre][inst] = [list(p) for p in unique]
        
        for inst in self.global_patterns:
            unique = list(set(tuple(p) for p in self.global_patterns[inst] if p))
            self.global_patterns[inst] = [list(p) for p in unique]
    
    def get_patterns_for_genre(self, genre: str, instrument: str) -> List[List[int]]:
        """Get all patterns for a specific genre and instrument."""
        if genre in self.genre_patterns and self.genre_patterns[genre].get(instrument):
            return self.genre_patterns[genre][instrument]
        return self.global_patterns.get(instrument, [])
    
    def generate_pattern_sequence(self, genre: str, instrument: str, 
                                   num_bars: int, complexity: float = 0.5) -> List[List[int]]:
        """Generate a sequence of patterns using Markov chain transitions."""
        patterns = self.get_patterns_for_genre(genre, instrument)
        
        if not patterns:
            return [[0] * 16 for _ in range(num_bars)]
        
        transitions = {}
        if genre in self.genre_transitions and instrument in self.genre_transitions[genre]:
            transitions = self.genre_transitions[genre][instrument]
        
        sequence = []
        current = random.choice(patterns)
        sequence.append(current)
        
        for _ in range(num_bars - 1):
            current_str = str(current)
            
            if current_str in transitions and random.random() > complexity * 0.3:
                followers = transitions[current_str]
                total = sum(followers.values())
                r = random.uniform(0, total)
                cumulative = 0
                
                for next_str, prob in followers.items():
                    cumulative += prob
                    if r <= cumulative:
                        try:
                            current = json.loads(next_str)
                        except:
                            current = random.choice(patterns)
                        break
                else:
                    current = random.choice(patterns)
            else:
                if random.random() < complexity * 0.4:
                    current = random.choice(patterns)
                else:
                    similar = [p for p in patterns if sum(p) == sum(current)]
                    current = random.choice(similar) if similar else random.choice(patterns)
            
            sequence.append(current)
        
        return sequence


# ═══════════════════════════════════════════════════════════════════════════════
# DRUM GENERATOR FROM LEARNED PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

def generate_drums_from_learned_patterns(
    pattern_generator: LearnedPatternGenerator,
    genre: str,
    structure: List[Tuple[str, int]],
    complexity: int,
    humanize_amount: float,
    bpm: float
) -> List[Tuple[float, float, int, int]]:
    """Generate drum MIDI events using learned patterns."""
    KICK = 36
    SNARE = 38
    HIHAT_CLOSED = 42
    HIHAT_OPEN = 46
    CRASH = 49
    
    notes = []
    total_bars = sum(bars for _, bars in structure)
    complexity_float = complexity / 10.0
    
    kick_patterns = pattern_generator.generate_pattern_sequence(genre, 'kick', total_bars, complexity_float)
    snare_patterns = pattern_generator.generate_pattern_sequence(genre, 'snare', total_bars, complexity_float)
    hihat_patterns = pattern_generator.generate_pattern_sequence(genre, 'hihat', total_bars, complexity_float)
    
    bar_idx = 0
    
    for section_type, section_bars in structure:
        energy = _section_energy(section_type)
        
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
                hihat_pat = [int(v * fade) for v in hihat_pat]
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
            
            for step in range(16):
                step_time = bar_time + (step / 4)
                h_offset = (random.random() - 0.5) * 0.02 * humanize_amount
                
                if kick_pat[step] > 0:
                    vel = int(80 + random.randint(-8, 8) * humanize_amount)
                    vel = int(vel * energy)
                    notes.append((step_time + h_offset, 0.25, KICK, max(40, min(127, vel))))
                
                if snare_pat[step] > 0:
                    vel = int(90 + random.randint(-10, 10) * humanize_amount)
                    vel = int(vel * energy)
                    notes.append((step_time + h_offset, 0.25, SNARE, max(40, min(127, vel))))
                
                if hihat_pat[step] > 0:
                    vel = int(70 + random.randint(-6, 6) * humanize_amount)
                    vel = int(vel * energy)
                    hat = HIHAT_OPEN if random.random() < 0.08 else HIHAT_CLOSED
                    dur = 0.4 if hat == HIHAT_OPEN else 0.15
                    notes.append((step_time + h_offset, dur, hat, max(30, min(127, vel))))
            
            if local_bar == 0 and section_type in ('chorus', 'drop', 'climax'):
                notes.append((bar_time, 1.0, CRASH, int(100 * energy)))
            
            bar_idx += 1
    
    return notes


def _section_energy(section_type: str) -> float:
    """Get energy level for a section type."""
    energy_map = {
        'intro': 0.5, 'verse': 0.7, 'pre_chorus': 0.8, 'chorus': 1.0,
        'drop': 1.0, 'bridge': 0.6, 'breakdown': 0.4, 'build': 0.8,
        'outro': 0.5, 'break': 0.2, 'climax': 1.0, 'pre-chorus': 0.8,
    }
    return energy_map.get(section_type, 0.7)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"Extracting patterns from: {filepath}")
        
        extractor = RhythmPatternExtractor()
        result = extractor.extract_patterns_from_timeline(filepath)
        
        if result:
            print(f"\n✓ BPM detected: {result['bpm']}")
            print(f"✓ Bars analyzed: {result['num_bars']}")
            print(f"\nPattern counts:")
            for inst, count in result['pattern_counts'].items():
                print(f"  {inst}: {count} unique patterns")
        else:
            print("Failed to extract patterns")
    else:
        print("Usage: python rhythm_pattern_extractor.py <timeline.csv>")
