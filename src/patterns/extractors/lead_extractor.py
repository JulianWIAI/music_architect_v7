"""
LeadPatternExtractor

Reads a timeline CSV and produces structured lead/melody-pattern data:
  - Binary 16-step rhythm patterns per bar
  - Velocity layers
  - Melodic contour sequences (inferred from intensity dynamics)
  - Interval suggestions relative to the chord root
  - Phrase-type classification (sustained / staccato / flowing / rhythmic / sparse)
  - Markov-chain transition tables
"""

import csv
import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional

CONTOUR_UP = 'up'
CONTOUR_DOWN = 'down'
CONTOUR_STAY = 'stay'
CONTOUR_JUMP_UP = 'jump_up'
CONTOUR_JUMP_DOWN = 'jump_down'


class LeadPatternExtractor:
    """
    Extracts lead / melody patterns from a timeline CSV.

    Because timeline CSVs contain intensity values rather than actual pitches,
    melodic contour is inferred from intensity dynamics and chord-aware interval
    suggestions are generated from the bar's predominant chord quality.
    """

    SYNTH_THRESHOLD = 0.02

    def __init__(self, steps_per_bar: int = 16):
        self.steps_per_bar = steps_per_bar

    # ─── PARSING ──────────────────────────────────────────────────────────────

    def parse_timeline_csv(self, filepath: str) -> List[Dict]:
        rows = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter=';'):
                    try:
                        rows.append({
                            'time': float(row.get('time_seconds', 0)),
                            'synth': float(row.get('synth', 0)),
                            'pad': float(row.get('pad', 0)),
                            'chord_root': row.get('chord_root', 'C'),
                            'chord_quality': row.get('chord_quality', 'maj7'),
                            'dominant_instrument': row.get('dominant_instrument', ''),
                        })
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f'Error parsing {filepath}: {e}')
        return rows

    # ─── QUANTISATION ─────────────────────────────────────────────────────────

    def quantize_to_bars(self, timeline: List[Dict], bpm: float) -> List[Dict]:
        if not timeline:
            return []
        spb = 60.0 / bpm
        spbar = spb * 4
        spstep = spbar / self.steps_per_bar
        duration = timeline[-1]['time'] - timeline[0]['time']
        num_bars = int(duration / spbar) + 1

        bars = [
            {
                'synth_intensities': [0.0] * self.steps_per_bar,
                'chord_roots': [],
                'chord_qualities': [],
                'is_lead_dominant': [False] * self.steps_per_bar,
            }
            for _ in range(num_bars)
        ]

        start = timeline[0]['time']
        for row in timeline:
            rel = row['time'] - start
            bi = min(int(rel / spbar), num_bars - 1)
            si = min(int((rel - bi * spbar) / spstep), self.steps_per_bar - 1)
            bars[bi]['synth_intensities'][si] = max(bars[bi]['synth_intensities'][si], row['synth'])
            dom = row.get('dominant_instrument', '').lower()
            if 'synth' in dom or 'lead' in dom:
                bars[bi]['is_lead_dominant'][si] = True
            if row['chord_root']:
                bars[bi]['chord_roots'].append(row['chord_root'])
                bars[bi]['chord_qualities'].append(row['chord_quality'])

        return bars

    # ─── CLASSIFICATION ───────────────────────────────────────────────────────

    def classify_phrase_type(self, rhythm: Tuple[int, ...], intensities: List[float]) -> str:
        hits = sum(rhythm)
        if hits <= 2:
            return 'sustained'
        if hits <= 4:
            positions = [i for i, v in enumerate(rhythm) if v == 1]
            if len(positions) >= 2:
                gaps = [positions[i + 1] - positions[i] for i in range(len(positions) - 1)]
                if len(set(gaps)) == 1:
                    return 'rhythmic'
            return 'sparse'
        if hits <= 8:
            consecutive = max_consecutive = 0
            for v in rhythm:
                consecutive = consecutive + 1 if v == 1 else 0
                max_consecutive = max(max_consecutive, consecutive)
            return 'flowing' if max_consecutive >= 3 else 'rhythmic'
        return 'flowing'

    def extract_contour_pattern(self, intensities: List[float]) -> List[str]:
        """Infer melodic contour from intensity-level changes between hits."""
        contours = []
        prev = None
        for intensity in intensities:
            if intensity <= self.SYNTH_THRESHOLD:
                continue
            if prev is not None:
                diff = intensity - prev
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
            prev = intensity
        return contours

    def extract_interval_suggestions(self, bar: Dict) -> List[int]:
        """Generate chord-aware interval suggestions for the hits in a bar."""
        rhythm = tuple(1 if v > self.SYNTH_THRESHOLD else 0 for v in bar['synth_intensities'])
        main_quality = Counter(bar['chord_qualities']).most_common(1)[0][0] if bar['chord_qualities'] else 'maj7'

        if 'min' in main_quality:
            chord_tones = [0, 3, 7, 10]
            scale_tones = [0, 2, 3, 5, 7, 8, 10]
        elif 'dim' in main_quality:
            chord_tones = [0, 3, 6, 9]
            scale_tones = [0, 2, 3, 5, 6, 8, 9]
        elif '7' in main_quality:
            chord_tones = [0, 4, 7, 10]
            scale_tones = [0, 2, 4, 5, 7, 9, 10]
        else:
            chord_tones = [0, 4, 7, 11]
            scale_tones = [0, 2, 4, 5, 7, 9, 11]

        intervals = []
        for idx, pos in enumerate(i for i, v in enumerate(rhythm) if v == 1):
            beat = pos // 4
            if pos == 0 or beat == 0:
                intervals.append(random.choice(chord_tones))
            elif pos % 4 == 0:
                intervals.append(random.choice(chord_tones))
            elif pos % 2 == 0:
                intervals.append(random.choice(scale_tones))
            else:
                intervals.append(random.choice(scale_tones + [1, 6, 8]))
        return intervals

    # ─── MAIN EXTRACTION ──────────────────────────────────────────────────────

    def extract_patterns_from_timeline(
        self, filepath: str, bpm: float = 120.0
    ) -> Optional[Dict]:
        timeline = self.parse_timeline_csv(filepath)
        if not timeline:
            return None

        bars = self.quantize_to_bars(timeline, bpm)
        if len(bars) < 2:
            return None

        rhythm_patterns, velocity_patterns, phrase_types = [], [], []
        contour_patterns, interval_patterns, densities = [], [], []

        for bar in bars:
            intensities = bar['synth_intensities']
            rhythm = tuple(1 if v > self.SYNTH_THRESHOLD else 0 for v in intensities)
            if sum(rhythm) < 1:
                continue

            rhythm_patterns.append(rhythm)

            vel = []
            for v in intensities:
                if v <= self.SYNTH_THRESHOLD:
                    vel.append(0)
                elif v <= 0.05:
                    vel.append(1)
                elif v <= 0.15:
                    vel.append(2)
                else:
                    vel.append(3)
            velocity_patterns.append(tuple(vel))
            phrase_types.append(self.classify_phrase_type(rhythm, intensities))

            contour = self.extract_contour_pattern(intensities)
            if contour:
                contour_patterns.append(tuple(contour))

            ivs = self.extract_interval_suggestions(bar)
            if ivs:
                interval_patterns.append(tuple(ivs))

            densities.append(sum(rhythm))

        if not rhythm_patterns:
            return None

        # Markov transitions (rhythm)
        trans: defaultdict = defaultdict(Counter)
        for i in range(len(rhythm_patterns) - 1):
            trans[rhythm_patterns[i]][rhythm_patterns[i + 1]] += 1
        transition_probs = {
            pat: {k: round(v / sum(fol.values()), 4) for k, v in fol.items()}
            for pat, fol in trans.items()
        }

        # Markov transitions (contour)
        ctrans: defaultdict = defaultdict(Counter)
        for i in range(len(contour_patterns) - 1):
            if contour_patterns[i] and contour_patterns[i + 1]:
                ctrans[contour_patterns[i][-1]][contour_patterns[i + 1][0]] += 1

        return {
            'rhythm_patterns': [list(p) for p in set(rhythm_patterns)],
            'velocity_patterns': [list(p) for p in set(velocity_patterns)],
            'contour_patterns': [list(p) for p in set(contour_patterns)],
            'interval_patterns': [list(p) for p in set(interval_patterns)],
            'phrase_distribution': dict(Counter(phrase_types)),
            'pattern_transitions': {
                str(list(k)): {str(list(kk)): vv for kk, vv in v.items()}
                for k, v in transition_probs.items()
            },
            'contour_transitions': {k: dict(v) for k, v in ctrans.items()},
            'density_stats': {
                'min': min(densities) if densities else 0,
                'max': max(densities) if densities else 0,
                'avg': round(sum(densities) / len(densities), 2) if densities else 0,
            },
            'pattern_counts': {
                'rhythms': len(set(rhythm_patterns)),
                'velocities': len(set(velocity_patterns)),
                'contours': len(set(contour_patterns)),
                'intervals': len(set(interval_patterns)),
            },
        }


def extract_lead_patterns_enhanced(timeline_path: str, bpm: float = 120.0) -> Dict:
    """Adapter for extracting lead patterns from a timeline CSV."""
    result = LeadPatternExtractor(steps_per_bar=16).extract_patterns_from_timeline(
        timeline_path, bpm
    )
    return result if result else {}
