"""
harvest_production_seeds.py — Golden Harvest of Gen3 best architectural blueprints.

Actions
-------
1. Reads batch_gen3/<genre>/math_fitness_report.json for all 10 genres.
2. Extracts Top-3 golden_matrices per genre (already ranked by the grader).
3. Writes individual blueprint files to production_seeds/<genre>/.
   Filename: <genre>_top_<rank>_<score>.json
4. Archives batch_gen3/ → vault/batch_gen3/ (historical reference, non-destructive).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

GENRES = [
    "cinematic", "classical", "edm", "hiphop",
    "house", "jpop", "phonk", "pop", "techno", "trap",
]

BATCH_GEN3_DIR    = Path("batch_gen3")
PRODUCTION_DIR    = Path("production_seeds")
VAULT_DIR         = Path("vault")
HARVEST_TIMESTAMP = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
GENERATION        = 3
TOP_N             = 3

# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_tag(score: float) -> str:
    return f"{score:.2f}"


def _build_blueprint(golden: dict, genre: str, rank: int) -> dict:
    params = golden.get("generation_params", {})
    return {
        "schema_version": "1.0",
        "production_metadata": {
            "genre":             genre,
            "rank":              rank,
            "score":             golden["score"],
            "source_batch":      f"batch_gen{GENERATION}",
            "source_track":      golden["track_name"],
            "harvest_timestamp": HARVEST_TIMESTAMP,
            "generation":        GENERATION,
        },
        # Full parameter set — seed_value is the reproduction key
        "generation_params": {
            "genre":              params.get("genre",              genre),
            "bpm":                params.get("bpm"),
            "key":                params.get("key"),
            "root":               params.get("root"),
            "scale":              params.get("scale"),
            "scale_locked":       params.get("scale_locked",       True),
            "complexity":         params.get("complexity",         5),
            "tension_multiplier": params.get("tension_multiplier", 0.5),
            "mutation":           params.get("mutation",           0.0),
            "seed_value":         params.get("seed_value"),        # reproduction key
            "humanize_amount":    params.get("humanize_amount",    0.6),
        },
        # Musical DNA
        "structure":         golden.get("structure",         []),
        "chord_progression": golden.get("chord_progression", []),
        # Grader breakdown for audit
        "fitness": {
            "score":    golden["score"],
            "breakdown": golden.get("breakdown", {}),
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def harvest() -> None:
    PRODUCTION_DIR.mkdir(exist_ok=True)

    total_written = 0
    missing_genres: list[str] = []

    print(f"\n{'='*60}")
    print(f"  GOLDEN HARVEST — Gen{GENERATION} Top-{TOP_N} per genre")
    print(f"  {HARVEST_TIMESTAMP}")
    print(f"{'='*60}\n")

    for genre in GENRES:
        report_path = BATCH_GEN3_DIR / genre / "math_fitness_report.json"
        if not report_path.exists():
            print(f"  [SKIP] {genre}: no fitness report at {report_path}")
            missing_genres.append(genre)
            continue

        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)

        matrices = report.get("golden_matrices", [])
        if not matrices:
            print(f"  [SKIP] {genre}: golden_matrices array is empty")
            missing_genres.append(genre)
            continue

        out_dir = PRODUCTION_DIR / genre
        out_dir.mkdir(exist_ok=True)

        written_this_genre = 0
        for golden in matrices[:TOP_N]:
            rank  = golden["rank"]
            score = golden["score"]

            blueprint  = _build_blueprint(golden, genre, rank)
            filename   = f"{genre}_top_{rank}_{_score_tag(score)}.json"
            out_path   = out_dir / filename

            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(blueprint, fh, indent=2, ensure_ascii=False)

            seed = blueprint["generation_params"].get("seed_value", "?")
            print(f"  [{genre.upper():10s}] #{rank}  score={score:.4f}  seed={seed}  -> {filename}")
            written_this_genre += 1

        total_written += written_this_genre
        print()

    # ── Archive batch_gen3 → vault ────────────────────────────────────────────
    vault_target = VAULT_DIR / f"batch_gen{GENERATION}"
    if BATCH_GEN3_DIR.exists() and not vault_target.exists():
        VAULT_DIR.mkdir(exist_ok=True)
        shutil.move(str(BATCH_GEN3_DIR), str(vault_target))
        print(f"  [VAULT] batch_gen{GENERATION}/ archived -> {vault_target}/")
    elif vault_target.exists():
        print(f"  [VAULT] {vault_target} already exists — skipping move")
    else:
        print(f"  [WARN]  batch_gen{GENERATION}/ not found — nothing to archive")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Harvest complete: {total_written} blueprints written")
    print(f"  Output: {PRODUCTION_DIR.resolve()}/")
    if missing_genres:
        print(f"  Missing genres: {', '.join(missing_genres)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    harvest()
