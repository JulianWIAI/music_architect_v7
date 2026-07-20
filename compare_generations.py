"""
compare_generations.py — Cross-generation fitness comparison.

Usage
-----
# Compare any number of generation folders in order:
python compare_generations.py vocals_generation_1 vocals_generation_2 vocals_generation_3

# Compare the non-vocal runs:
python compare_generations.py Generation1 Generation2 Generation3
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional


GENRES = ["pop", "hiphop", "trap", "cinematic", "classical",
          "techno", "jpop", "phonk", "edm", "house", "dnb"]


def _load_report(gen_dir: Path, genre: str) -> Optional[dict]:
    p = gen_dir / genre / "math_fitness_report.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _top_score(report: dict) -> float:
    lb = report.get("leaderboard", [])
    return lb[0]["score"] if lb else 0.0


def _avg_score(report: dict) -> float:
    lb = report.get("leaderboard", [])
    if not lb:
        return 0.0
    return round(sum(e["score"] for e in lb) / len(lb), 2)


def print_comparison(gen_dirs: List[Path]) -> None:
    labels = [d.name for d in gen_dirs]

    print()
    print("=" * 80)
    print("  GENERATION COMPARISON — Top Score & Average Score per Genre")
    print("=" * 80)

    # Header
    col = 11
    header = f"  {'Genre':<11}"
    for lbl in labels:
        short = lbl.replace("vocals_generation_", "vG").replace("Generation", "G")
        header += f"  {short+' Top':>10}  {short+' Avg':>10}"
    # Delta columns between consecutive gens
    for i in range(len(gen_dirs) - 1):
        s1 = labels[i].replace("vocals_generation_", "vG").replace("Generation", "G")
        s2 = labels[i+1].replace("vocals_generation_", "vG").replace("Generation", "G")
        header += f"  {s1+'->'+s2:>12}"
    print(header)
    print("  " + "-" * 78)

    genre_rows = []
    for genre in GENRES:
        reports = [_load_report(d, genre) for d in gen_dirs]
        if all(r is None for r in reports):
            continue

        row = f"  {genre.upper():<11}"
        tops = []
        avgs = []
        for r in reports:
            if r:
                t = _top_score(r)
                a = _avg_score(r)
                tops.append(t)
                avgs.append(a)
                row += f"  {t:>10.2f}  {a:>10.2f}"
            else:
                tops.append(None)
                avgs.append(None)
                row += f"  {'--':>10}  {'--':>10}"

        for i in range(len(gen_dirs) - 1):
            if tops[i] is not None and tops[i+1] is not None:
                delta = tops[i+1] - tops[i]
                sign  = "+" if delta >= 0 else ""
                row += f"  {sign+f'{delta:.2f}':>12}"
            else:
                row += f"  {'--':>12}"

        print(row)
        genre_rows.append((genre, tops, avgs))

    # Summary row
    print("  " + "-" * 78)
    sum_row = f"  {'AVERAGE':<11}"
    all_tops = [[] for _ in gen_dirs]
    all_avgs = [[] for _ in gen_dirs]
    for _, tops, avgs in genre_rows:
        for i, (t, a) in enumerate(zip(tops, avgs)):
            if t is not None:
                all_tops[i].append(t)
                all_avgs[i].append(a)

    col_tops = []
    for i, (ts, av) in enumerate(zip(all_tops, all_avgs)):
        mt = round(sum(ts) / len(ts), 2) if ts else 0.0
        ma = round(sum(av) / len(av), 2) if av else 0.0
        col_tops.append(mt)
        sum_row += f"  {mt:>10.2f}  {ma:>10.2f}"
    for i in range(len(gen_dirs) - 1):
        if col_tops[i] and col_tops[i+1]:
            delta = col_tops[i+1] - col_tops[i]
            sign  = "+" if delta >= 0 else ""
            sum_row += f"  {sign+f'{delta:.2f}':>12}"
    print(sum_row)
    print()


def print_golden_seeds(gen_dirs: List[Path]) -> None:
    """Print the Top-5 golden seeds that guided each subsequent generation."""
    # For Gen N, show seeds that guided Gen N+1
    for i, src_dir in enumerate(gen_dirs[:-1]):
        next_lbl = gen_dirs[i+1].name
        print("=" * 80)
        print(f"  GOLDEN SEEDS from {src_dir.name}  ->  guided {next_lbl}")
        print("=" * 80)
        for genre in GENRES:
            report = _load_report(src_dir, genre)
            if not report:
                continue
            matrices = report.get("golden_matrices", [])
            if not matrices:
                continue
            print(f"\n  [{genre.upper()}]")
            print(f"    {'Rank':<5} {'Track':<14} {'Score':>7}  {'BPM':>6}  {'Key':<16}  {'Complexity':>10}")
            print(f"    {'-'*65}")
            for m in matrices:
                p  = m.get("generation_params", {})
                print(
                    f"    #{m.get('rank','?'):<4} "
                    f"{m.get('track_name','?'):<14} "
                    f"{m.get('score', 0):>7.2f}  "
                    f"{p.get('bpm', 0):>6.1f}  "
                    f"{p.get('key', '?'):<16}  "
                    f"{p.get('complexity', '?'):>10}"
                )
        print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    root = Path(__file__).parent
    gen_dirs = []
    for arg in sys.argv[1:]:
        p = root / arg
        if not p.exists():
            print(f"[WARN] Directory not found, skipping: {p}")
        else:
            gen_dirs.append(p)

    if not gen_dirs:
        print("[ERROR] No valid generation directories found.")
        sys.exit(1)

    print_comparison(gen_dirs)
    if len(gen_dirs) > 1:
        print_golden_seeds(gen_dirs)


if __name__ == "__main__":
    main()
