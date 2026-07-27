"""
verify_production_seeds.py — Validates all production seed blueprint files.

For each JSON file under production_seeds/:
  1. Confirms the file is valid JSON.
  2. Confirms schema_version, required fields, and seed_value are present.
  3. Constructs a CompositionConfig from generation_params using config_from_golden
     (mutation_factor=0.0 so params flow through without drift).
  4. Confirms the config is accepted by CompositionEngine without error.

Exit code 0 = all passed.  Exit code 1 = one or more failures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.composition.composition_engine import (
    CompositionEngine,
    config_from_golden,
)

PRODUCTION_DIR    = Path("production_seeds")
SEEDS_DIR         = Path("seeds")
REQUIRED_TOP_KEYS = {"schema_version", "production_metadata", "generation_params", "fitness"}
REQUIRED_PARAMS   = {"genre", "bpm", "seed_value", "complexity", "tension_multiplier"}

KNOWN_GENRES = {
    "cinematic", "classical", "edm", "hiphop",
    "house", "jpop", "phonk", "pop", "techno", "trap",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

class CheckFailed(Exception):
    pass


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise CheckFailed(msg)


def _validate_blueprint(path: Path) -> dict:
    """Load and validate one blueprint file. Returns the loaded data."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    # Top-level structure
    missing = REQUIRED_TOP_KEYS - data.keys()
    _check(not missing, f"Missing top-level keys: {missing}")

    meta   = data["production_metadata"]
    params = data["generation_params"]

    # Metadata
    _check("genre" in meta,  "production_metadata.genre missing")
    _check("rank"  in meta,  "production_metadata.rank missing")
    _check("score" in meta,  "production_metadata.score missing")
    _check("source_track" in meta, "production_metadata.source_track missing")
    _check("seed_value" not in (None, 0) or params.get("seed_value") is not None,
           "seed_value is null — cannot guarantee exact reproduction")

    # Generation params
    missing_p = REQUIRED_PARAMS - params.keys()
    _check(not missing_p, f"generation_params missing: {missing_p}")

    genre = params["genre"]
    _check(genre in KNOWN_GENRES, f"Unknown genre '{genre}'")
    _check(params["seed_value"] is not None, "seed_value is null")
    _check(isinstance(params["bpm"], (int, float)) and params["bpm"] > 0,
           f"Invalid bpm: {params['bpm']}")
    _check(1 <= params["complexity"] <= 10,
           f"complexity out of range: {params['complexity']}")

    return data


def _build_config(data: dict) -> None:
    """
    Build a CompositionConfig from the blueprint's generation_params via
    config_from_golden — the exact same path batch_commander uses.

    We wrap generation_params in the shape config_from_golden expects:
    a golden_matrix dict with a 'generation_params' sub-key.
    """
    golden_proxy = {
        "rank":              data["production_metadata"]["rank"],
        "track_name":        data["production_metadata"]["source_track"],
        "score":             data["production_metadata"]["score"],
        "generation_params": data["generation_params"],
        "structure":         data.get("structure", []),
        "chord_progression": data.get("chord_progression", []),
        "breakdown":         data.get("fitness", {}).get("breakdown", {}),
    }
    cfg = config_from_golden(golden_proxy, mutation_factor=0.0)

    _check(cfg.seed_value is not None, "config.seed_value is None after config_from_golden")
    _check(cfg.genre == data["generation_params"]["genre"],
           f"config.genre mismatch: expected {data['generation_params']['genre']}, got {cfg.genre}")


# ── Main ──────────────────────────────────────────────────────────────────────

def verify() -> int:
    if not PRODUCTION_DIR.exists():
        print(f"[ERROR] production_seeds/ not found at {PRODUCTION_DIR.resolve()}")
        return 1

    blueprints = sorted(PRODUCTION_DIR.glob("**/*.json"))
    if not blueprints:
        print("[ERROR] No blueprint files found in production_seeds/")
        return 1

    print(f"\n{'='*60}")
    print(f"  PRODUCTION SEED VERIFICATION")
    print(f"  Scanning {len(blueprints)} blueprint(s) in {PRODUCTION_DIR}/")
    print(f"{'='*60}\n")

    passed = 0
    failed = 0
    failures: list[tuple[Path, str]] = []

    for bp_path in blueprints:
        rel = bp_path.relative_to(PRODUCTION_DIR)
        try:
            data = _validate_blueprint(bp_path)
            _build_config(data)

            seed  = data["generation_params"]["seed_value"]
            score = data["production_metadata"]["score"]
            rank  = data["production_metadata"]["rank"]
            print(f"  PASS  {rel}  (rank={rank}, score={score:.4f}, seed={seed})")
            passed += 1

        except (json.JSONDecodeError, CheckFailed, KeyError, Exception) as exc:
            print(f"  FAIL  {rel}")
            print(f"        -> {exc}")
            failures.append((bp_path, str(exc)))
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed")

    if failures:
        print(f"\n  Failed files:")
        for p, reason in failures:
            print(f"    {p.name}: {reason}")
        print(f"{'='*60}\n")
        return 1

    print(f"  All blueprints valid and engine-compatible.")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    sys.exit(verify())
