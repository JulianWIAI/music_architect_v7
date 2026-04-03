"""
═══════════════════════════════════════════════════════════════════════
  SEED BUILDER — CSV Dataset → Musical DNA Seeds (JSON)
  
  Supports YOUR folder layout:
    Research_training_data/
      GigaMIDI_training_data/
        000fbebecb7d7bf2018ceaccbdbe2e73/
          000fbebecb7d7bf2018ceaccbdbe2e73_time_data.csv
          000fbebecb7d7bf2018ceaccbdbe2e73_chords.csv
          000fbebecb7d7bf2018ceaccbdbe2e73_timeline.csv
      Jamendo_training_data/
        1100/
          1100_time_data.csv
          ...
═══════════════════════════════════════════════════════════════════════
"""

import csv
import json
import os
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional
from bass_pattern_extractor import extract_bass_patterns_enhanced
from rhythm_pattern_extractor import extract_instrument_patterns_enhanced



# ═══════════════════════════════════════════════════════════════════════
#  GENRE CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════

def classify_genre(time_data: dict, stats: dict) -> str:
    bpm = time_data.get('bpm', 120)
    time_sig = time_data.get('time_signature', '4/4')
    syncopation = time_data.get('syncopation_score', 0.5)
    duration = time_data.get('duration', 180)
    kick_d = stats.get('kick_density', 0)
    hihat_d = stats.get('hihat_density', 0)
    bass_d = stats.get('bass_density', 0)
    synth_d = stats.get('synth_density', 0)
    pad_d = stats.get('pad_density', 0)
    harm = stats.get('harmonic_ratio_avg', 0.5)
    chord_v = stats.get('chord_variety', 5)

    sc = {k: 0 for k in ['pop','hiphop','trap','cinematic','classical','techno','jpop','phonk']}

    if 60 <= bpm <= 90:     sc['hiphop'] += 3; sc['cinematic'] += 2
    elif 90 < bpm <= 115:   sc['pop'] += 2; sc['hiphop'] += 2; sc['jpop'] += 1
    elif 115 < bpm <= 135:  sc['pop'] += 3; sc['jpop'] += 2
    elif 135 < bpm <= 155:  sc['trap'] += 3; sc['phonk'] += 3; sc['techno'] += 2
    elif bpm > 155:         sc['techno'] += 4; sc['phonk'] += 2

    if pad_d > 0.15:    sc['cinematic'] += 3; sc['classical'] += 2
    if synth_d > 0.1:   sc['techno'] += 2; sc['jpop'] += 1
    if hihat_d > 0.05:  sc['trap'] += 3; sc['phonk'] += 2
    if kick_d > 0.08:   sc['techno'] += 2
    if bass_d > 0.2:    sc['hiphop'] += 2; sc['trap'] += 1
    if syncopation > 0.7: sc['hiphop'] += 2
    if syncopation < 0.3: sc['classical'] += 2; sc['cinematic'] += 1
    if harm > 0.8:      sc['classical'] += 2; sc['cinematic'] += 2
    elif harm < 0.5:    sc['trap'] += 2; sc['phonk'] += 2
    if time_sig in ('3/4','6/8'): sc['classical'] += 3; sc['cinematic'] += 2
    if chord_v > 8:     sc['jpop'] += 2; sc['classical'] += 1
    elif chord_v < 4:   sc['trap'] += 2; sc['phonk'] += 2; sc['techno'] += 1
    if duration > 300:  sc['cinematic'] += 2; sc['classical'] += 2

    return max(sc, key=sc.get)


# ═══════════════════════════════════════════════════════════════════════
#  CSV PARSERS
# ═══════════════════════════════════════════════════════════════════════

def parse_time_data_csv(filepath: str) -> dict:
    data = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            param = row.get('parameter', '')
            value = row.get('value', '')
            try:
                data[param] = value if '/' in value else float(value)
            except (ValueError, TypeError):
                data[param] = value
    return data

def parse_chords_csv(filepath: str) -> List[dict]:
    chords = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter=';'):
            try:
                chords.append({
                    'start': float(row['start_time']), 'end': float(row['end_time']),
                    'chord': row['chord'], 'root': row['root'], 'quality': row['quality'],
                })
            except (ValueError, KeyError):
                continue
    return chords

def parse_timeline_csv(filepath: str) -> List[dict]:
    events = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter=';'):
            try:
                events.append({
                    'time': float(row['time_seconds']), 'chord': row['chord'],
                    'chord_root': row['chord_root'], 'chord_quality': row['chord_quality'],
                    'kick': float(row.get('kick', 0)), 'snare': float(row.get('snare', 0)),
                    'hihat': float(row.get('hihat', 0)), 'bass': float(row.get('bass', 0)),
                    'synth': float(row.get('synth', 0)), 'pad': float(row.get('pad', 0)),
                    'harmonic_ratio': float(row.get('harmonic_ratio', 0)),
                    'dominant_instrument': row.get('dominant_instrument', 'bass'),
                })
            except (ValueError, KeyError):
                continue
    return events


# ═══════════════════════════════════════════════════════════════════════
#  ANALYSIS HELPERS
# ═══════════════════════════════════════════════════════════════════════

def build_chord_transitions(chords):
    trans = defaultdict(Counter)
    for i in range(len(chords) - 1):
        trans[chords[i]['chord']][chords[i+1]['chord']] += 1
    result = {}
    for ch, fol in trans.items():
        total = sum(fol.values())
        result[ch] = {k: v/total for k, v in fol.items()}
    return result

def extract_instrument_patterns(timeline, bpm):
    if not timeline or bpm <= 0: return {}
    bd = 60.0 / bpm
    sixteenth = bd / 4.0
    instruments = ['kick','snare','hihat','bass','synth','pad']
    patterns = {}
    for inst in instruments:
        hits = [{'time': round(round(ev['time']/sixteenth)*sixteenth, 4),
                 'velocity': round(min(1.0, ev.get(inst,0)), 3)}
                for ev in timeline if ev.get(inst,0) > 0.02]
        if hits:
            bar_len = bd * 4
            early = [h for h in hits if h['time'] < bar_len * 4]
            phits = [{'pos': round((h['time'] % bar_len) / bd, 4), 'vel': h['velocity']} for h in early]
            patterns[inst] = {'hits': phits[:64], 'density': len(hits)/max(1,len(timeline)),
                              'avg_velocity': round(sum(h['velocity'] for h in hits)/max(1,len(hits)), 3)}
        else:
            patterns[inst] = {'hits': [], 'density': 0.0, 'avg_velocity': 0.0}
    return patterns

def compute_timeline_stats(timeline, chords):
    if not timeline: return {}
    n = len(timeline)
    return {
        'kick_density': sum(1 for e in timeline if e['kick'] > 0.02) / n,
        'snare_density': sum(1 for e in timeline if e['snare'] > 0.02) / n,
        'hihat_density': sum(1 for e in timeline if e['hihat'] > 0.02) / n,
        'bass_density': sum(e['bass'] for e in timeline) / n,
        'synth_density': sum(e['synth'] for e in timeline) / n,
        'pad_density': sum(e['pad'] for e in timeline) / n,
        'harmonic_ratio_avg': sum(e['harmonic_ratio'] for e in timeline) / n,
        'dominant_instrument': Counter(e['dominant_instrument'] for e in timeline).most_common(1)[0][0],
        'chord_variety': len(set(c['chord'] for c in chords)) if chords else 0,
    }

def extract_song_structure(timeline, chords, time_data):
    if not timeline:
        return [{"type": "verse", "start": 0, "end": 180, "energy": 0.5}]
    duration = time_data.get('duration', timeline[-1]['time'] if timeline else 180)
    bpm = time_data.get('bpm', 120)
    bar_len = (60.0 / bpm) * 4
    bars = []
    t = 0
    while t < duration:
        bar_end = t + bar_len
        evts = [e for e in timeline if t <= e['time'] < bar_end]
        energy = sum(e['kick']+e['snare']+e['hihat']+e['bass']+e['synth']+e['pad'] for e in evts)/max(1,len(evts)) if evts else 0
        bars.append({'start': round(t,2), 'end': round(bar_end,2), 'energy': round(energy,4)})
        t = bar_end
    if not bars:
        return [{"type": "verse", "start": 0, "end": duration, "energy": 0.5}]
    max_e = max(b['energy'] for b in bars) or 1
    sections = []; cur = None; sec_start = 0
    for i, bar in enumerate(bars):
        ne = bar['energy'] / max_e
        if ne < 0.15:   st = 'intro' if i < 4 else ('outro' if i > len(bars)-4 else 'break')
        elif ne < 0.4:  st = 'verse'
        elif ne < 0.7:  st = 'chorus'
        else:           st = 'drop'
        if st != cur:
            if cur: sections.append({'type': cur, 'start': round(sec_start,2), 'end': round(bar['start'],2), 'energy': round(ne,3)})
            cur = st; sec_start = bar['start']
    if cur: sections.append({'type': cur, 'start': round(sec_start,2), 'end': round(duration,2), 'energy': 0.5})
    return sections or [{"type": "verse", "start": 0, "end": duration, "energy": 0.5}]


# ═══════════════════════════════════════════════════════════════════════
#  SEED BUILDER CLASS
# ═══════════════════════════════════════════════════════════════════════

class SeedBuilder:
    def __init__(self, dataset_dir: str, output_dir: str = "seeds"):
        self.dataset_dir = Path(dataset_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.seeds = []
        self.genre_seeds = defaultdict(list)
        self.source_seeds = defaultdict(list)

    def _detect_source(self, filepath: str) -> str:
        fp = filepath.lower()
        if 'gigamidi' in fp: return 'GigaMIDI'
        if 'jamendo' in fp: return 'Jamendo'
        return 'Unknown'

    def find_csv_triples(self):
        """Find CSV triples in nested song-folder structure."""
        all_csvs = list(self.dataset_dir.rglob("*.csv"))
        print(f"  Scanning {self.dataset_dir}...")
        print(f"  Found {len(all_csvs)} CSV files total")

        # Group by parent folder
        by_folder = defaultdict(list)
        for f in all_csvs:
            by_folder[str(f.parent)].append(f)

        triples = []
        for folder, files in by_folder.items():
            td = ch = tl = key = None
            for f in files:
                name = f.stem
                if name.endswith('_time_data'):
                    td = str(f); key = name[:-10]
                elif name.endswith('_chords'):
                    ch = str(f); key = key or name[:-7]
                elif name.endswith('_timeline'):
                    tl = str(f); key = key or name[:-9]
            if td and ch and tl and key:
                triples.append((td, ch, tl, key))

        print(f"  ✓ {len(triples)} complete song triples found")
        return triples

    def process_single_song(self, td_path, ch_path, tl_path, song_id):
        try:
            td = parse_time_data_csv(td_path)
            chords = parse_chords_csv(ch_path)
            timeline = parse_timeline_csv(tl_path)
            if not chords and not timeline: return None
            bpm = td.get('bpm', 120)
            if isinstance(bpm, str): bpm = 120

            transitions = build_chord_transitions(chords)
            patterns = extract_instrument_patterns_enhanced(tl_path, bpm)
            bass_patterns = extract_bass_patterns_enhanced(tl_path, bpm)
            stats = compute_timeline_stats(timeline, chords)
            structure = extract_song_structure(timeline, chords, td)
            genre = classify_genre(td, stats)
            source = self._detect_source(td_path)

            progression = [f"{c['root']}{c['quality']}" for c in chords[:200]]

            return {
                'song_id': song_id, 'source': source, 'genre': genre,
                'dna': {
                    'bpm': round(bpm, 2) if isinstance(bpm, (int, float)) else 120,
                    'key': td.get('key', 'C major'),
                    'time_signature': td.get('time_signature', '4/4'),
                    'syncopation': round(td.get('syncopation_score', 0.5), 3) if isinstance(td.get('syncopation_score'), (int, float)) else 0.5,
                    'duration': round(td.get('duration', 180), 2) if isinstance(td.get('duration'), (int, float)) else 180,
                },
                'chord_transitions': transitions,
                'chord_roots_used': list(set(c['root'] for c in chords)),
                'chord_qualities_used': list(set(c['quality'] for c in chords)),
                'progression_sample': progression[:50],
                'instrument_patterns': patterns,
                'bass_patterns': bass_patterns,
                'structure': structure,
                'stats': stats,
            }
        except Exception as e:
            print(f"  ⚠ Error: {song_id}: {e}")
            return None

    def build_all_seeds(self, progress_callback=None):
        triples = self.find_csv_triples()
        total = len(triples)
        success = 0
        for i, (td, ch, tl, sid) in enumerate(triples):
            if progress_callback:
                progress_callback(i+1, total, sid)
            seed = self.process_single_song(td, ch, tl, sid)
            if seed:
                self.seeds.append(seed)
                self.genre_seeds[seed['genre']].append(seed)
                self.source_seeds[seed['source']].append(seed)
                success += 1
            if (i+1) % 100 == 0:
                print(f"  [{i+1}/{total}] {success} seeds...")
        print(f"◢ COMPLETE: {success}/{total} seeds ◣")
        for src, seeds in self.source_seeds.items():
            genres = Counter(s['genre'] for s in seeds)
            print(f"  {src}: {len(seeds)} songs — {dict(genres)}")
        return success

    def save_seeds(self):
        mp = self.output_dir / "master_seeds.json"
        with open(mp, 'w', encoding='utf-8') as f:
            json.dump(self.seeds, f, indent=2, default=str)
        print(f"  ✓ Master: {mp} ({len(self.seeds)} seeds)")

        for genre, seeds in self.genre_seeds.items():
            p = self.output_dir / f"seeds_{genre}.json"
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(seeds, f, indent=2, default=str)
            print(f"  ✓ {genre}: {len(seeds)} seeds")

        for source, seeds in self.source_seeds.items():
            p = self.output_dir / f"seeds_source_{source}.json"
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(seeds, f, indent=2, default=str)
            print(f"  ✓ Source {source}: {len(seeds)} seeds")

        stats = {
            'total_seeds': len(self.seeds),
            'by_genre': {g: len(s) for g, s in self.genre_seeds.items()},
            'by_source': {s: len(ss) for s, ss in self.source_seeds.items()},
            'output_dir': str(self.output_dir.resolve()),
        }
        with open(self.output_dir / "seed_stats.json", 'w') as f:
            json.dump(stats, f, indent=2)

    def build_merged_transition_matrix(self, genre=None):
        target = self.genre_seeds.get(genre, []) if genre else self.seeds
        merged = defaultdict(Counter)
        for seed in target:
            for ch, fol in seed.get('chord_transitions', {}).items():
                for nc, p in fol.items():
                    merged[ch][nc] += p
        result = {}
        for ch, fol in merged.items():
            total = sum(fol.values())
            result[ch] = {k: round(v/total, 4) for k, v in fol.items()}
        return result

    def export_genre_matrices(self):
        md = self.output_dir / "matrices"
        md.mkdir(exist_ok=True)
        for genre in self.genre_seeds:
            matrix = self.build_merged_transition_matrix(genre)
            with open(md / f"matrix_{genre}.json", 'w') as f:
                json.dump(matrix, f, indent=2)
            print(f"  ✓ Matrix {genre}: {len(matrix)} chords")
        gm = self.build_merged_transition_matrix()
        with open(md / "matrix_global.json", 'w') as f:
            json.dump(gm, f, indent=2)
        print(f"  ✓ Global matrix: {len(gm)} chords")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_dir", help="Root folder with CSV subfolders")
    parser.add_argument("-o", "--output", default="seeds")
    args = parser.parse_args()
    builder = SeedBuilder(args.dataset_dir, args.output)
    count = builder.build_all_seeds()
    if count > 0:
        builder.save_seeds()
        builder.export_genre_matrices()
        print(f"\n◢ DONE: {count} seeds in {Path(args.output).resolve()} ◣")
