"""
inspect_drums.py — Checks drum pattern diversity across batch runs.
Samples tracks from multiple genres and prints unique kick/snare fingerprints.
"""
import mido
from pathlib import Path
from collections import Counter


def get_drum_pattern(midi_path):
    try:
        mid = mido.MidiFile(str(midi_path))
        tpb = mid.ticks_per_beat
        step = tpb // 4  # 16th note

        kicks, snares, hihats = set(), set(), set()
        for track in mid.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if (msg.type == 'note_on' and msg.velocity > 0
                        and hasattr(msg, 'channel') and msg.channel == 9):
                    step_idx = (abs_tick // step) % 16
                    if msg.note in (35, 36):
                        kicks.add(step_idx)
                    elif msg.note in (38, 40):
                        snares.add(step_idx)
                    elif msg.note in (42, 44, 46):
                        hihats.add(step_idx)

        return (frozenset(kicks), frozenset(snares), frozenset(hihats))
    except Exception as e:
        return None


GENRES = ["pop", "hiphop", "trap", "cinematic", "techno", "jpop", "phonk", "edm", "house", "dnb"]
RUNS   = ["Generation3", "vocals_generation_3"]
SAMPLE = 20  # tracks per genre


for run in RUNS:
    base = Path(run)
    all_patterns = []
    genre_patterns = {}

    for genre in GENRES:
        genre_dir = base / genre
        if not genre_dir.exists():
            continue
        track_dirs = sorted(p for p in genre_dir.iterdir() if p.is_dir())[:SAMPLE]
        gp = []
        for td in track_dirs:
            mids = list(td.glob("*.mid"))
            if mids:
                p = get_drum_pattern(mids[0])
                if p:
                    gp.append(p)
                    all_patterns.append(p)
        genre_patterns[genre] = gp

    unique_total = len(set(all_patterns))
    total = len(all_patterns)

    print(f"\n{'='*70}")
    print(f"  {run}  —  {unique_total} unique drum patterns out of {total} tracks sampled")
    print(f"{'='*70}")

    for genre, pats in genre_patterns.items():
        if not pats:
            continue
        unique_in_genre = len(set(pats))
        # Count most common kick pattern
        kick_counter = Counter(p[0] for p in pats)
        most_common_kick, count = kick_counter.most_common(1)[0]
        kick_grid  = ''.join('X' if i in most_common_kick else '.' for i in range(16))
        print(f"\n  [{genre.upper()}]  {unique_in_genre}/{len(pats)} unique patterns")
        print(f"    Most common kick  ({count}/{len(pats)} tracks): {kick_grid}")

        # Print all unique kick fingerprints
        shown = set()
        for p in pats:
            k = p[0]
            if k not in shown:
                shown.add(k)
                s = p[1]
                kg = ''.join('X' if i in k else '.' for i in range(16))
                sg = ''.join('X' if i in s else '.' for i in range(16))
                print(f"    kick  : {kg}")
                print(f"    snare : {sg}")
                print()
