

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seed_builder import SeedBuilder

# ═══════════════════════════════════════════════════════════════════════
#  CONFIGURATION — Edit these paths for your system
# ═══════════════════════════════════════════════════════════════════════

# Your main dataset root folder
DATASET_ROOT = r"C:\Users\julia\Desktop\Analysis\Music\Privat"

# Where to save the generated seed files
# (same folder as this script, or change to wherever you want)
OUTPUT_DIR = Path(r"C:\Users\julia\Desktop\Analysis\Music\Seeds_private")


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         ◢ BATCH SEED BUILDER — 3000 SONG DATASET ◣        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    if not os.path.exists(DATASET_ROOT):
        print(f"⚠ Dataset not found at: {DATASET_ROOT}")
        print(f"  Edit DATASET_ROOT in this script to point to your folder.")
        alt = input("Enter your dataset path (or press Enter to exit): ").strip()
        if not alt:
            return
        if not os.path.exists(alt):
            print(f"⚠ Path not found: {alt}")
            return
        dataset = alt
    else:
        dataset = DATASET_ROOT

    print(f"◢ Dataset: {dataset}")
    print(f"◢ Output:  {OUTPUT_DIR}")
    print()

    start = time.time()
    builder = SeedBuilder(dataset, OUTPUT_DIR)

    def progress(i, total, song_id):
        pct = i / total * 100
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"\r  [{bar}] {pct:.1f}% ({i}/{total}) {song_id[:30]:30s}", end="", flush=True)

    count = builder.build_all_seeds(progress_callback=progress)
    print()  # Newline after progress bar

    if count > 0:
        print()
        print("◢ SAVING SEEDS... ◣")
        builder.save_seeds()
        builder.export_genre_matrices()

        elapsed = time.time() - start
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print(f"║  ✓ {count} seeds built in {elapsed:.1f}s")
        print(f"║  ✓ Saved to: {Path(OUTPUT_DIR).resolve()}")
        print(f"║")
        print(f"║  Genre breakdown:")
        for genre, seeds in sorted(builder.genre_seeds.items()):
            print(f"║    {genre:12s}: {len(seeds):4d} songs")
        print(f"║")
        print(f"║  Source breakdown:")
        for source, seeds in sorted(builder.source_seeds.items()):
            print(f"║    {source:12s}: {len(seeds):4d} songs")
        print(f"║")
        print(f"║  Now open the GUI and click '📂 LOAD EXISTING SEEDS'")
        print(f"║  Point it to: {Path(OUTPUT_DIR).resolve()}")
        print("╚══════════════════════════════════════════════════════════════╝")
    else:
        print("◢ NO SEEDS CREATED ◣")
        print("  Check that your CSV files have the correct naming:")
        print("    <song_id>_time_data.csv")
        print("    <song_id>_chords.csv")
        print("    <song_id>_timeline.csv")


if __name__ == "__main__":
    main()
