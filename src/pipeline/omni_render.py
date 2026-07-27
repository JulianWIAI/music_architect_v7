"""
omni_render.py — 3-generation evolutionary batch runner for Music Architect V7.

Generation schedule
-------------------
Gen 1 :  100 tracks / genre  — free exploration
Gen 2 :  250 tracks / genre  — seeded from top 20 % of Gen 1
Gen 3 :  500 tracks / genre  — seeded from top 20 % of Gen 2

Genres : hiphop, trap   (vocal_mask=OFF throughout)

Bridge Experiment
-----------------
Run after the evolutionary run to probe the "Musical Chaos Threshold":
  20 tracks at mut=0.15  (controlled creativity)
  20 tracks at mut=0.25  (high mutation / boundary territory)
Both batches use Gen 3 golden seeds with vocal_mask=True.
A chaos_threshold_report.json is written comparing penalty averages
and flagging any metric where the 0.25 batch breaks benchmark tolerances.

Watchdog
--------
Each track composition runs in a daemon thread. If it does not complete
within WATCHDOG_S seconds (default 30), the seed is logged to
`watchdog_log.json` and the runner skips to the next track.
The hung daemon thread is harmless — it is cleaned up when the process exits.

Scoring
-------
Tracks are graded by `telemetry_grader_midi.calculate_midi_fitness`, which
returns a score in [0, 115]:
  - 100 pts base (penalties deducted for scale errors, rhythm, density, motif, range)
  - +15 pts God Mode bonus (macro-dynamics, polyrhythmic integrity, humanization delta)

Output layout
-------------
evolutionary_run/
  gen1/hiphop/  track_000/ ... track_099/
  gen1/trap/    track_000/ ... track_099/
  gen2/hiphop/  track_000/ ... track_249/
  ...
  gen3/trap/    track_000/ ... track_499/

bridge_experiment/
  mut_015/hiphop/   20 tracks, vocal_mask=True, mut=0.15
  mut_015/trap/     20 tracks, vocal_mask=True, mut=0.15
  mut_025/hiphop/   20 tracks, vocal_mask=True, mut=0.25
  mut_025/trap/     20 tracks, vocal_mask=True, mut=0.25
  chaos_threshold_report.json

Each generation directory also contains:
  batch_manifest.json       — render_seed + score per track
  math_fitness_report.json  — full grader output
  evolutionary_pool.json    — golden matrices for next generation (gen 1 & 2 only)
  watchdog_log.json         — seeds that timed out (if any)

CLI
---
python omni_render.py              # run full 3-generation evolutionary run
python omni_render.py --bridge     # run bridge experiment only (needs gen3 pools)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# -- Batch helpers (all module-level callables, safe to import) ----------------
from src.orchestration.batch_commander import (
    _config_free,
    _config_from_pool,
    _build_seed_info,
    _melody_to_raw_notes,
    _split_into_phrases,
    _TPQN,
)
from src.orchestration.telemetry_grader_midi import _process_genre

# -- Composition stack ---------------------------------------------------------
from src.composition.composition_engine import (
    CompositionEngine,
    GoldenMatrixPool,
)
from src.composition.genre_constants import GENRE_BPM

try:
    from src.core.orchestrator import Orchestrator as _Orchestrator
    _ORC_AVAILABLE = True
except ImportError:
    _ORC_AVAILABLE = False

try:
    from src.export.utau_bridge import export as _utau_export, RawNote as _RawNote
    _UTAU_OK = True
except ImportError:
    _UTAU_OK = False

# -- Run configuration ---------------------------------------------------------

GENRES: List[str] = ["hiphop", "trap"]

GENRE_PROMPTS: Dict[str, str] = {
    "hiphop": "hip hop boom bap groove 90bpm",
    "trap":   "trap dark 808 aggressive 140bpm",
}

GEN_SIZES: List[int] = [100, 250, 500]   # tracks per genre per generation

TOP_PCT:     float = 0.20   # fraction of top scorers that seed the next gen
# Decreasing mutation schedule: broad exploration early, tight refinement late.
# Gen 1->2: 0.10 — moderate-broad, explore around 20 diverse golden seeds
# Gen 2->3: 0.05 — tight, refine 50 confirmed winners toward commercial target
MUT_SCHEDULE: List[float] = [0.10, 0.05]   # index 0 = gen1->gen2, index 1 = gen2->gen3
WATCHDOG_S:  int   = 30     # seconds before aborting a single track

# Production batch settings (--production)
PROD_MUT:         float = 0.15    # bridge-validated controlled creativity
PROD_COUNT:       int   = 300     # tracks per genre — instrumental pass
PROD_SCORE_FLOOR: float = 45.0    # minimum fitness score for production pack


# -----------------------------------------------------------------------------
# Watchdog-protected compose
# -----------------------------------------------------------------------------

def _compose_watchdog(
    orc,
    config,
    seed_pool_path: Optional[str],
    timeout: int = WATCHDOG_S,
) -> dict:
    """
    Run orc.compose(config) in a daemon thread.

    Returns the composition dict on success.
    Raises TimeoutError if the thread is still alive after `timeout` seconds.
    The hung thread is a background daemon and will not block process exit.
    """
    result: List[Optional[dict]]  = [None]
    error:  List[Optional[Exception]] = [None]

    def _worker() -> None:
        try:
            result[0] = orc.compose(config, seed_pool_path=seed_pool_path)
        except Exception as exc:  # noqa: BLE001
            error[0] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise TimeoutError(
            f"Composition exceeded {timeout}s  (seed={config.seed_value})"
        )
    if error[0] is not None:
        raise error[0]
    return result[0]  # type: ignore[return-value]


# -----------------------------------------------------------------------------
# Single-generation runner
# -----------------------------------------------------------------------------

def _run_gen(
    genre:            str,
    count:            int,
    outdir:           Path,
    seed_pool_path:   Optional[str],
    engine:           CompositionEngine,
    orc,
    gen_label:        str,
    mut_factor:       float = 0.07,
    vocal_mask:       bool  = False,
    generation_level: Optional[int] = None,
) -> List[dict]:
    """
    Generate `count` tracks for `genre` into `outdir`.

    generation_level — integer generation number for metadata tagging (derived
                       from gen_label if not provided: "gen3" -> 3).
    vocal_mask       — whether to activate vocal mask on composition.

    Returns the list of per-track manifest entries (including render_seed).
    """
    if generation_level is None:
        try:
            generation_level = int(gen_label.lstrip("gen").split("_")[0])
        except (ValueError, IndexError):
            generation_level = 0
    outdir.mkdir(parents=True, exist_ok=True)

    bpm_range    = GENRE_BPM.get(genre, (85, 115))
    target_bpm   = sum(bpm_range) / 2.0
    target_scale: Optional[str] = None
    strict_scale = False
    base_tension = 0.5

    pool: Optional[GoldenMatrixPool] = None
    if seed_pool_path and Path(seed_pool_path).exists():
        pool = GoldenMatrixPool.from_report(seed_pool_path, mut_factor)

    mode_label = (
        f"golden injection  pool={pool.summary()}" if pool
        else f"free exploration  bpm~{target_bpm:.0f}"
    )
    print(f"\n  [{gen_label.upper()}] {genre.upper()}  {count} tracks -> {outdir}")
    print(f"  {mode_label}")

    batch_tracks:  List[dict] = []
    timed_out_seeds: List[int] = []

    for i in range(count):
        track_name = f"track_{i:03d}"
        track_dir  = outdir / track_name
        track_dir.mkdir(exist_ok=True)

        # -- Build config ------------------------------------------------------
        if pool is not None:
            config, gen_params, golden_source = _config_from_pool(pool)
        else:
            config, gen_params, golden_source = _config_free(
                genre, target_bpm, bpm_range,
                target_scale, strict_scale, base_tension,
            )
        config.vocal_mask = vocal_mask

        t_start = time.time()

        # -- Compose (watchdog-protected) --------------------------------------
        try:
            comp = _compose_watchdog(orc, config, seed_pool_path, WATCHDOG_S)
        except TimeoutError as exc:
            elapsed = time.time() - t_start
            seed    = gen_params["seed_value"]
            print(f"  [WATCHDOG] WATCHDOG [{i+1}/{count}] {track_name}  seed={seed}  ({elapsed:.0f}s) — skipped")
            timed_out_seeds.append(seed)
            (track_dir / "watchdog_timeout.json").write_text(
                json.dumps({"seed": seed, "elapsed_s": round(elapsed, 1)}),
                encoding="utf-8",
            )
            continue
        except Exception as exc:
            print(f"  [ERROR] ERROR [{i+1}/{count}] {track_name}: {exc}")
            continue

        t_elapsed = round(time.time() - t_start, 3)
        gen_params["bpm"] = comp["config"]["bpm"]

        # -- MIDI export -------------------------------------------------------
        midi_path = track_dir / f"{track_name}.mid"
        try:
            engine.export_midi(comp, str(midi_path))
        except Exception as exc:
            print(f"  [WARN] MIDI export failed {track_name}: {exc}")

        # -- USTX export (optional) --------------------------------------------
        ustx_path = track_dir / f"{track_name}.ustx"
        if _UTAU_OK:
            melody_notes = comp["tracks"].get("04_Melody", [])
            if melody_notes:
                try:
                    phrases = _split_into_phrases(_melody_to_raw_notes(melody_notes))
                    if phrases:
                        _utau_export(
                            output_path=ustx_path,
                            phrases=phrases,
                            tpqn=_TPQN,
                            bpm=comp["config"]["bpm"],
                            song_name=track_name,
                            singer="TIGER DS",
                        )
                except Exception:
                    pass

        # -- Write per-track metadata (render_seed surfaced at top level) ------
        render_seed       = gen_params["seed_value"]
        track_note_counts = {k: len(v) for k, v in comp["tracks"].items()}
        total_notes       = sum(track_note_counts.values())

        metadata: dict = {
            "track_index":       i,
            "render_seed":       render_seed,
            "generation":        gen_label,
            "generation_level":  generation_level,
            "genre":             genre,
            "generation_mode":   "golden_injection" if pool else "free_exploration",
            "generation_params": gen_params,
            "seed_info":         _build_seed_info(engine, genre),
            "outputs": {
                "midi_path":         str(midi_path.relative_to(outdir)),
                "ustx_path":         (str(ustx_path.relative_to(outdir))
                                      if ustx_path.exists() else None),
                "track_note_counts": track_note_counts,
                "total_notes":       total_notes,
            },
            "structure":          comp["structure"],
            "chord_progression":  comp["chord_progression"][:32],
            "generation_timestamp":        time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generation_duration_seconds": t_elapsed,
            "vocal_mask_active":           vocal_mask,
        }
        if golden_source:
            metadata["golden_source"] = golden_source

        with open(track_dir / "generation_metadata.json", "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)

        # -- Append to batch manifest ------------------------------------------
        batch_tracks.append({
            "track_index":     i,
            "track_name":      track_name,
            "render_seed":     render_seed,
            "generation_level": generation_level,
            "bpm":             round(gen_params["bpm"], 2),
            "key":             gen_params["key"],
            "total_notes":     total_notes,
            "elapsed_s":       t_elapsed,
            "vocal_mask":      vocal_mask,
            "golden_source":   golden_source,
        })

        print(
            f"  [{i+1:>4}/{count}] {track_name}"
            f"  bpm={gen_params['bpm']:.1f}"
            f"  key={gen_params['key']:<18}"
            f"  notes={total_notes}"
            f"  seed={render_seed}"
            + (f"  [#{golden_source['rank']} s={golden_source['score']:.1f}]"
               if golden_source else "")
            + f"  ({t_elapsed:.2f}s)"
        )

    # -- Write batch manifest --------------------------------------------------
    manifest = {
        "generation":       gen_label,
        "generation_level": generation_level,
        "genre":            genre,
        "vocal_mask":       vocal_mask,
        "count_requested":  count,
        "count_completed":  len(batch_tracks),
        "timed_out_count":  len(timed_out_seeds),
        "seed_pool":        seed_pool_path,
        "mutation_factor":  mut_factor,
        "tracks":           batch_tracks,
    }
    with open(outdir / "batch_manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    if timed_out_seeds:
        with open(outdir / "watchdog_log.json", "w", encoding="utf-8") as fh:
            json.dump({"timed_out_seeds": timed_out_seeds}, fh, indent=2)
        print(f"\n  Watchdog: {len(timed_out_seeds)} seed(s) timed out — see watchdog_log.json")

    return batch_tracks


# -----------------------------------------------------------------------------
# Grade + build evolutionary pool
# -----------------------------------------------------------------------------

def _grade_and_pool(
    genre_dir:  Path,
    top_pct:    float = TOP_PCT,
    mut_factor: float = 0.07,
) -> Tuple[dict, Path]:
    """
    Grade a completed generation directory and write:
      - math_fitness_report.json  (full grader output, max score 115)
      - evolutionary_pool.json    (top top_pct% as GoldenMatrixPool input)

    Returns (report_dict, evolutionary_pool_path).
    """
    print(f"\n  Grading {genre_dir.name.upper()} ...")
    report = _process_genre(genre_dir)
    n_scored = report["tracks_scored"]

    # Write full grader report
    report_path = genre_dir / "math_fitness_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"  {n_scored} tracks scored  ->  {report_path.name}")

    # Print top-5 summary
    leaderboard = report.get("leaderboard", [])
    if leaderboard:
        print(f"  {'Rank':<5} {'Track':<14} {'Score':>7}  {'GodMode':>8}")
        print(f"  {'-'*40}")
        for e in leaderboard[:5]:
            gm = (report["golden_matrices"][e["rank"] - 1]["breakdown"]
                  .get("god_mode", {}).get("total_bonus", 0.0)
                  if e["rank"] <= 5 else 0.0)
            print(f"  #{e['rank']:<4} {e['track_name']:<14} {e['score']:>7.2f}  +{gm:>5.1f}")

    # Build evolutionary pool from top top_pct%
    n_keep = max(1, int(len(leaderboard) * top_pct))
    top    = leaderboard[:n_keep]

    if top:
        print(f"\n  Top {n_keep}/{n_scored} selected ({top_pct*100:.0f}%)"
              f"  score range [{top[-1]['score']:.2f} to {top[0]['score']:.2f}]")

    golden_matrices = [
        {
            "rank":              i + 1,
            "track_name":        e["track_name"],
            "score":             e["score"],
            "generation_params": e["generation_params"],
            "seed_info":         {},
            "structure":         [],
            "chord_progression": [],
            "breakdown":         e.get("penalties", {}),
        }
        for i, e in enumerate(top)
    ]

    evo_pool = {
        "genre":           genre_dir.name,
        "source_gen":      str(genre_dir),
        "top_pct":         top_pct,
        "tracks_scored":   n_scored,
        "golden_count":    n_keep,
        "mutation_factor": mut_factor,
        "golden_matrices": golden_matrices,
    }
    evo_pool_path = genre_dir / "evolutionary_pool.json"
    with open(evo_pool_path, "w", encoding="utf-8") as fh:
        json.dump(evo_pool, fh, indent=2)
    print(f"  Evolutionary pool ({n_keep} seeds) -> {evo_pool_path.name}")

    # ── Merge fitness scores back into batch_manifest.json ────────────
    # Gives every track entry a 'fitness_score' and 'penalties' field
    # so the manifest is self-contained for downstream analysis.
    manifest_path = genre_dir / "batch_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            score_map = {e["track_name"]: e for e in leaderboard}
            for t in manifest.get("tracks", []):
                lb = score_map.get(t.get("track_name"), {})
                t["fitness_score"] = lb.get("score", None)
                t["penalties"]     = lb.get("penalties", {})
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"  [WARN] Could not merge scores into manifest: {exc}")

    # ── Archive pool to generation_archive/ (immutable copy per gen) ──
    _archive_pool(evo_pool, genre_dir, mut_factor)

    return report, evo_pool_path


def _archive_pool(evo_pool: dict, genre_dir: Path, mut_factor: float) -> None:
    """
    Copy the evolutionary pool to generation_archive/<genre>/ with a
    timestamped filename so each generation's top seeds are permanently
    preserved regardless of future overwrites.
    """
    genre   = genre_dir.name
    gen_tag = genre_dir.parent.name   # e.g. "gen1", "gen2", "gen3"
    ts      = time.strftime("%Y%m%d_%H%M%S")

    archive_dir = Path("generation_archive") / genre
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_name = f"{gen_tag}_{genre}_top{evo_pool['golden_count']}_mut{int(mut_factor*100):03d}_{ts}.json"
    archive_path = archive_dir / archive_name
    archive_path.write_text(json.dumps(evo_pool, indent=2), encoding="utf-8")
    print(f"  Archive -> generation_archive/{genre}/{archive_name}")


# -----------------------------------------------------------------------------
# Bridge Experiment — Musical Chaos Threshold
# -----------------------------------------------------------------------------

_BRIDGE_MUT_LEVELS: List[float] = [0.15, 0.25]
_BRIDGE_COUNT: int = 20


def _avg_penalties(report: dict) -> dict:
    """Average each penalty field across all scored tracks in a report."""
    keys = ["scale_adherence", "rhythmic_variance", "chord_density",
            "motif_repetition", "melodic_range"]
    sums = {k: 0.0 for k in keys}
    gm_bonus_sum = 0.0
    gm_macro_sum = 0.0
    gm_poly_sum  = 0.0
    gm_hum_sum   = 0.0
    n = len(report.get("leaderboard", []))
    if n == 0:
        return {}

    for entry in report["leaderboard"]:
        pen = entry.get("penalties", {})
        for k in keys:
            sums[k] += pen.get(k, 0.0)

    # god_mode details live in golden_matrices (top 5 only) — use those for bonus avg
    for gm in report.get("golden_matrices", []):
        bd = gm.get("breakdown", {})
        gm_bonus_sum += bd.get("god_mode", {}).get("total_bonus", 0.0)
        gm_macro_sum += bd.get("god_mode", {}).get("macro_dynamics", {}).get("bonus", 0.0)
        gm_poly_sum  += bd.get("god_mode", {}).get("polyrhythmic_integrity", {}).get("bonus", 0.0)
        gm_hum_sum   += bd.get("god_mode", {}).get("humanization_delta", {}).get("bonus", 0.0)

    gm_n = max(len(report.get("golden_matrices", [])), 1)
    avg_score = (sum(e["score"] for e in report["leaderboard"]) / n)

    return {
        "n_tracks": n,
        "avg_score": round(avg_score, 4),
        "penalties": {k: round(sums[k] / n, 4) for k in keys},
        "total_penalty_avg": round(sum(sums.values()) / n, 4),
        "god_mode_avg": {
            "total_bonus":             round(gm_bonus_sum / gm_n, 4),
            "macro_dynamics_bonus":    round(gm_macro_sum / gm_n, 4),
            "polyrhythmic_bonus":      round(gm_poly_sum  / gm_n, 4),
            "humanization_bonus":      round(gm_hum_sum   / gm_n, 4),
        },
    }


def _compare_batches(stats_015: dict, stats_025: dict) -> dict:
    """
    Compare mut=0.15 vs mut=0.25 per-metric averages.
    Returns a breach summary and per-metric deltas.
    """
    breach_threshold_pct = 20.0   # flag if a penalty increases by > 20 %
    breaches: List[dict] = []
    improvements: List[dict] = []
    per_metric: dict = {}

    pen_015 = stats_015.get("penalties", {})
    pen_025 = stats_025.get("penalties", {})

    for metric in pen_015:
        v_015 = pen_015.get(metric, 0.0)
        v_025 = pen_025.get(metric, 0.0)
        delta = v_025 - v_015
        pct_change = (delta / max(v_015, 0.001)) * 100.0
        entry = {
            "mut_015_avg": round(v_015, 4),
            "mut_025_avg": round(v_025, 4),
            "delta":       round(delta, 4),
            "pct_change":  round(pct_change, 2),
        }
        if pct_change > breach_threshold_pct:
            entry["verdict"] = "BREACH"
            breaches.append(metric)
        elif pct_change < -breach_threshold_pct:
            entry["verdict"] = "IMPROVEMENT"
            improvements.append(metric)
        else:
            entry["verdict"] = "STABLE"
        per_metric[metric] = entry

    score_delta = stats_025["avg_score"] - stats_015["avg_score"]
    chaos_detected = len(breaches) >= 2 or (
        stats_025["avg_score"] < stats_015["avg_score"] * 0.85
    )

    return {
        "chaos_detected":      chaos_detected,
        "score_015_avg":       stats_015["avg_score"],
        "score_025_avg":       stats_025["avg_score"],
        "score_delta":         round(score_delta, 4),
        "breached_metrics":    breaches,
        "improved_metrics":    improvements,
        "breach_threshold_pct": breach_threshold_pct,
        "per_metric":          per_metric,
        "god_mode_015":        stats_015.get("god_mode_avg", {}),
        "god_mode_025":        stats_025.get("god_mode_avg", {}),
    }


# -----------------------------------------------------------------------------
# System Snapshot — research audit trail
# -----------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        return "unreadable"
    return h.hexdigest()[:16]   # first 16 hex chars is enough for identity


def write_system_snapshot(
    out_path: Path = Path("system_snapshot_gen3.json"),
    genres:   List[str] = None,
    gen3_root: Path = Path("evolutionary_run/gen3"),
) -> dict:
    """
    Capture a point-in-time snapshot of the generator codebase and the Gen 3
    seed manifests.  Written to *out_path* for research audit trail.

    Contents
    --------
    - timestamp and git commit hash
    - system_config (mutation schedule, watchdog, top_pct, vocal_mask, etc.)
    - intro_variety_protocol (80/20 split parameters)
    - per-file sha256 fingerprints for all src/ Python files
    - gen3_seed_summaries: top-5 seeds per genre from the previous Gen 3 pool
    """
    if genres is None:
        genres = GENRES

    # Git commit hash (best-effort — may not be available)
    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        git_hash = "unavailable"

    # Fingerprint all Python source files
    src_files: dict = {}
    for p in sorted(Path("src").rglob("*.py")):
        src_files[p.as_posix()] = {
            "sha256_prefix": _sha256(p),
            "size_bytes":    p.stat().st_size,
            "modified":      time.strftime("%Y-%m-%dT%H:%M:%S",
                                           time.localtime(p.stat().st_mtime)),
        }
    # Also fingerprint the runner itself
    for name in ("omni_render.py",):
        p = Path(name)
        if p.exists():
            src_files[name] = {
                "sha256_prefix": _sha256(p),
                "size_bytes":    p.stat().st_size,
                "modified":      time.strftime("%Y-%m-%dT%H:%M:%S",
                                               time.localtime(p.stat().st_mtime)),
            }

    # Gen 3 seed summaries from the previous evolutionary run
    gen3_seed_summaries: dict = {}
    for genre in genres:
        pool_path = gen3_root / genre / "evolutionary_pool.json"
        if pool_path.exists():
            try:
                pool = json.loads(pool_path.read_text(encoding="utf-8"))
                matrices = pool.get("golden_matrices", [])
                gen3_seed_summaries[genre] = {
                    "pool_path":    pool_path.as_posix(),
                    "golden_count": pool.get("golden_count", len(matrices)),
                    "top_5": [
                        {
                            "rank":  m["rank"],
                            "score": m["score"],
                            "seed":  m.get("generation_params", {}).get("seed_value"),
                            "key":   m.get("generation_params", {}).get("key"),
                            "bpm":   m.get("generation_params", {}).get("bpm"),
                        }
                        for m in matrices[:5]
                    ],
                }
            except Exception as exc:
                gen3_seed_summaries[genre] = {"error": str(exc)}
        else:
            gen3_seed_summaries[genre] = {"note": "no Gen 3 pool found (first run)"}

    snapshot = {
        "snapshot_type":    "pre_run_state",
        "timestamp":        time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_commit":       git_hash,
        "system_config": {
            "genres":            GENRES,
            "gen_sizes":         GEN_SIZES,
            "top_pct":           TOP_PCT,
            "mutation_schedule": MUT_SCHEDULE,
            "watchdog_s":        WATCHDOG_S,
            "vocal_mask":        False,
        },
        "intro_variety_protocol": {
            "enabled":       True,
            "variety_pct":   80,
            "signature_pct": 20,
            "legacy_archetypes": {
                "built_in":  ["staccato", "atmospheric", "arpeggio"],
                "pop":       ["piano_staccato", "pluck_arpeggio", "atmospheric_pad"],
                "house":     ["lpf_bass_groove", "percussive_build", "chord_stab"],
                "edm":       ["filter_sweep", "mono_pluck", "impact_drone"],
            },
            "billboard_archetypes": [
                "pedal_point",
                "syncopated_anticipation",
                "four_chord_loop",
                "inverted_filter_sweep",
            ],
            "billboard_genre_pools": {
                "trap":   ["syncopated_anticipation", "pedal_point"],
                "hiphop": ["syncopated_anticipation", "pedal_point"],
                "pop":    ["pedal_point", "four_chord_loop", "syncopated_anticipation"],
                "house":  ["syncopated_anticipation", "inverted_filter_sweep"],
                "edm":    ["pedal_point", "inverted_filter_sweep", "syncopated_anticipation"],
            },
            "signature": "single sustained chord per bar (genre brand anchor)",
        },
        "section_archetypes": {
            "drop_climax":  "dense 8th-note stabs",
            "chorus":       "syncopated 4-hit grid (3 grids randomised per bar)",
            "build":        "escalating density bar-by-bar (1 -> 4 hits)",
            "break":        "sparse: 35% chance per bar",
            "outro":        "fade_sustain / dissolve / descending_arp",
        },
        "source_file_fingerprints": src_files,
        "gen3_seed_summaries":      gen3_seed_summaries,
    }

    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"  Snapshot -> {out_path.resolve()}")
    return snapshot


# -----------------------------------------------------------------------------
# Validate pipeline integration (Step 4 check)
# -----------------------------------------------------------------------------

def validate_pipeline() -> bool:
    """
    Pre-flight check: confirm all five pipeline requirements are satisfied.
    Prints a status table and returns True if everything passes.
    """
    checks = []

    # 1. IntroVarietyProtocol integrated (80/20 split in generate_chord_track)
    try:
        from src.composition.composition_engine import CompositionEngine
        import inspect
        src = inspect.getsource(CompositionEngine.generate_chord_track)
        ok1 = "_INTRO_VARIETY_PCT" in src and "_INTRO_SIGNATURE" in src
    except Exception:
        ok1 = False
    checks.append(("IntroVarietyProtocol (80/20)", ok1))

    # 2. BillboardIntroMatrix registered and reachable
    try:
        from src.generators.intro import BillboardIntroMatrix
        ok2 = len(BillboardIntroMatrix.ARCHETYPE_NAMES) >= 4
    except Exception:
        ok2 = False
    checks.append(("BillboardIntroMatrix (4 archetypes)", ok2))

    # 3. Registry dispatches Billboard names correctly
    try:
        from src.composition.intro_archetype_registry import get_archetypes, _BILLBOARD_NAMES
        trap_pool = get_archetypes('trap') or ()
        ok3 = any(a in _BILLBOARD_NAMES for a in trap_pool)
    except Exception:
        ok3 = False
    checks.append(("Registry: Billboard names in trap/hiphop pools", ok3))

    # 4. System snapshot function present
    checks.append(("System snapshot writer", callable(write_system_snapshot)))

    # 5. generation_archive/ copying present (checked via function source)
    ok5 = "_archive_pool" in inspect.getsource(_grade_and_pool)
    checks.append(("generation_archive/ copy on grade", ok5))

    # 6. Watchdog resource throttling (WATCHDOG_S > 0)
    checks.append(("Watchdog resource throttling", WATCHDOG_S > 0))

    all_pass = all(ok for _, ok in checks)
    print("\n  Pipeline Integration Check")
    print(f"  {'Check':<40} {'Status'}")
    print(f"  {'-'*52}")
    for label, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  {label:<40} {status}")
    print()
    return all_pass


def run_bridge_experiment(
    engine,
    orc,
    base_dir: Path = Path("bridge_experiment"),
    gen3_root: Path = Path("evolutionary_run/gen3"),
    genres: List[str] = None,
) -> None:
    """
    Musical Chaos Threshold experiment.

    For each genre, generates _BRIDGE_COUNT tracks at mut=0.15 and mut=0.25
    using Gen 3 golden seeds with vocal_mask=True.  Grades both batches and
    writes a chaos_threshold_report.json comparing penalty averages.
    """
    if genres is None:
        genres = GENRES

    base_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    header = f"BRIDGE EXPERIMENT — Musical Chaos Threshold  {ts}"
    print(f"\n{'='*len(header)}")
    print(header)
    print(f"Genres : {genres}")
    print(f"Count  : {_BRIDGE_COUNT} tracks per mutation level per genre")
    print(f"Levels : {_BRIDGE_MUT_LEVELS}  (vocal_mask=True, Gen 3 seeds)")
    print(f"{'='*len(header)}\n")

    full_report: dict = {
        "experiment":      "Musical Chaos Threshold",
        "timestamp":       ts,
        "bridge_count":    _BRIDGE_COUNT,
        "mut_levels":      _BRIDGE_MUT_LEVELS,
        "vocal_mask":      True,
        "source_gen":      "gen3",
        "genres":          {},
    }

    for genre in genres:
        genre_upper = genre.upper()
        print(f"\n{'-'*60}")
        print(f"  GENRE: {genre_upper}")
        print(f"{'-'*60}")

        # Locate Gen 3 pool
        pool_path = gen3_root / genre / "evolutionary_pool.json"
        if not pool_path.exists():
            print(f"  [SKIP] Gen 3 pool not found: {pool_path}")
            full_report["genres"][genre] = {"error": f"pool not found: {pool_path}"}
            continue

        genre_stats: dict = {}

        for mut in _BRIDGE_MUT_LEVELS:
            mut_label = f"mut_{int(mut * 100):03d}"    # 0.15 -> "mut_015"
            outdir    = base_dir / mut_label / genre
            gen_label = f"bridge_{mut_label}"

            print(f"\n  [{genre_upper}] mut={mut}  ->  {outdir}")

            _run_gen(
                genre            = genre,
                count            = _BRIDGE_COUNT,
                outdir           = outdir,
                seed_pool_path   = str(pool_path),
                engine           = engine,
                orc              = orc,
                gen_label        = gen_label,
                mut_factor       = mut,
                vocal_mask       = True,
                generation_level = 4,   # bridge is "generation 4" conceptually
            )

            # Grade immediately
            print(f"\n  Grading {genre_upper} mut={mut} ...")
            report = _process_genre(outdir)
            report_path = outdir / "math_fitness_report.json"
            with open(report_path, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2)
            print(f"  {report['tracks_scored']} tracks scored -> {report_path.name}")

            stats = _avg_penalties(report)
            genre_stats[mut_label] = stats
            print(f"  avg_score={stats['avg_score']:.2f}  "
                  f"total_penalty_avg={stats['total_penalty_avg']:.2f}")

        # Compare mut=0.15 vs mut=0.25 for this genre
        if "mut_015" in genre_stats and "mut_025" in genre_stats:
            comparison = _compare_batches(genre_stats["mut_015"], genre_stats["mut_025"])
            genre_stats["comparison"] = comparison

            chaos = comparison["chaos_detected"]
            verdict = "CHAOS THRESHOLD CROSSED" if chaos else "below chaos threshold"
            delta   = comparison["score_delta"]
            print(f"\n  [{genre_upper}] Chaos verdict: {verdict}")
            print(f"  Score delta (025-015): {delta:+.2f}")
            if comparison["breached_metrics"]:
                print(f"  Breached metrics: {comparison['breached_metrics']}")
            if comparison["improved_metrics"]:
                print(f"  Improved metrics: {comparison['improved_metrics']}")

        full_report["genres"][genre] = genre_stats

    # Load benchmark god_mode_targets for context
    benchmark_context: dict = {}
    for genre in genres:
        bm_path = Path("benchmarks_dir") / f"{genre.capitalize()}_benchmark.json"
        if bm_path.exists():
            with open(bm_path, encoding="utf-8") as f:
                bm = json.load(f)
            benchmark_context[genre] = bm.get("god_mode_targets", {})
    full_report["benchmark_god_mode_targets"] = benchmark_context

    # Write master chaos threshold report
    chaos_path = base_dir / "chaos_threshold_report.json"
    with open(chaos_path, "w", encoding="utf-8") as fh:
        json.dump(full_report, fh, indent=2)

    print(f"\n{'='*60}")
    print(f"  Bridge Experiment complete")
    print(f"  Report -> {chaos_path.resolve()}")

    # Summary table
    print(f"\n  {'Genre':<10} {'Score 0.15':>10} {'Score 0.25':>10} {'Delta':>8} {'Chaos?':>10}")
    print(f"  {'-'*50}")
    for genre in genres:
        gs = full_report["genres"].get(genre, {})
        cmp = gs.get("comparison", {})
        s15 = cmp.get("score_015_avg", "-")
        s25 = cmp.get("score_025_avg", "-")
        dlt = cmp.get("score_delta", "-")
        chaos = "YES" if cmp.get("chaos_detected") else "no"
        s15_s = f"{s15:.2f}" if isinstance(s15, float) else str(s15)
        s25_s = f"{s25:.2f}" if isinstance(s25, float) else str(s25)
        dlt_s = f"{dlt:+.2f}" if isinstance(dlt, float) else str(dlt)
        print(f"  {genre:<10} {s15_s:>10} {s25_s:>10} {dlt_s:>8} {chaos:>10}")
    print(f"{'='*60}\n")


# -----------------------------------------------------------------------------
# Production batch — Gen 3 seeds → instrumental + vocal-ready siblings
# -----------------------------------------------------------------------------

def _load_gen3_archive(genre: str) -> Optional[str]:
    """
    Return path to the best seed pool for a genre.
    Priority order:
      1. prod_calibrated_*.json  — hand-curated calibrated pools (highest quality)
      2. gen3_*.json             — Gen 3 archive sorted by mtime (newest first)
    """
    archive_dir = Path("generation_archive") / genre
    if not archive_dir.exists():
        return None
    # Priority 1: production-calibrated pools
    prod_cal = sorted(archive_dir.glob("prod_calibrated_*.json"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if prod_cal:
        return str(prod_cal[0])
    # Priority 2: Gen 3 archive by mtime so newest file always wins regardless
    # of naming convention (alphabetical sort broke when 'calibrated' < 'top100')
    gen3 = sorted(archive_dir.glob("gen3_*.json"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return str(gen3[0]) if gen3 else None


def _load_benchmark(genre: str) -> dict:
    """Load benchmark targets+tolerances for a genre (best-effort)."""
    path = Path("benchmarks_dir") / f"{genre.capitalize()}_benchmark.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _passes_benchmark(
    bpm: float,
    score: float,
    benchmark: dict,
    score_floor: float,
) -> Tuple[bool, str]:
    """Return (passes, reason_str) for the production benchmark filter."""
    if score < score_floor:
        return False, f"score {score:.2f} < floor {score_floor:.2f}"
    if benchmark:
        try:
            bpm_target = benchmark["targets"]["rhythm"]["bpm"]
            bpm_tol    = benchmark["tolerances"]["rhythm"]["bpm"]
            if abs(bpm - bpm_target) > bpm_tol:
                return False, (
                    f"bpm {bpm:.1f} outside "
                    f"[{bpm_target - bpm_tol:.1f}, {bpm_target + bpm_tol:.1f}]"
                )
        except (KeyError, TypeError):
            pass
    return True, "ok"


def _run_sibling_pass(
    winner_dirs: List[Path],
    out_root:    Path,
    genre:       str,
    engine:      CompositionEngine,
    orc,
) -> List[dict]:
    """
    Render one vocal-ready sibling for each instrumental winner.

    Uses the winner's exact generation_params but vocal_mask=True.
    The same seed_value makes the composition deterministic — the only
    difference is the vocal frequency mask applied on top.
    """
    from src.composition.composition_config import CompositionConfig

    outdir = out_root / genre
    outdir.mkdir(parents=True, exist_ok=True)

    manifest_entries: List[dict] = []
    total = len(winner_dirs)
    print(f"\n  [VOCAL SIBLINGS] {genre.upper()}  {total} winners -> {outdir}")

    for idx, win_dir in enumerate(winner_dirs):
        meta_path = win_dir / "generation_metadata.json"
        if not meta_path.exists():
            print(f"  [SKIP] No metadata in {win_dir.name}")
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [SKIP] Cannot read {win_dir.name}: {exc}")
            continue

        params     = meta.get("generation_params", {})
        track_name = f"sibling_{idx:03d}_{win_dir.name}"
        track_dir  = outdir / track_name
        track_dir.mkdir(exist_ok=True)

        config = CompositionConfig(
            genre              = params.get("genre", genre),
            bpm                = params.get("bpm"),
            key                = params.get("key"),
            complexity         = params.get("complexity", 5),
            mutation           = PROD_MUT,
            seed_value         = params.get("seed_value"),
            tension_multiplier = params.get("tension_multiplier", 0.0),
            humanize_amount    = params.get("humanize_amount", 0.6),
            vocal_mask         = True,
        )

        t_start = time.time()
        try:
            comp = _compose_watchdog(orc, config, None, WATCHDOG_S)
        except TimeoutError:
            print(f"  [WATCHDOG] {track_name} timed out — skipped")
            continue
        except Exception as exc:
            print(f"  [ERROR] {track_name}: {exc}")
            continue
        t_elapsed = round(time.time() - t_start, 3)

        midi_path = track_dir / f"{track_name}.mid"
        try:
            engine.export_midi(comp, str(midi_path))
        except Exception as exc:
            print(f"  [WARN] MIDI export failed {track_name}: {exc}")

        sibling_meta = {
            "sibling_index":              idx,
            "source_instrumental":        str(win_dir),
            "source_seed":                params.get("seed_value"),
            "genre":                      genre,
            "generation_params":          params,
            "vocal_mask_active":          True,
            "generation_timestamp":       time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generation_duration_seconds": t_elapsed,
        }
        (track_dir / "generation_metadata.json").write_text(
            json.dumps(sibling_meta, indent=2), encoding="utf-8"
        )

        manifest_entries.append({
            "track_name":          track_name,
            "source_instrumental": win_dir.name,
            "seed":                params.get("seed_value"),
            "bpm":                 round(float(params.get("bpm") or 0), 2),
            "key":                 params.get("key"),
            "elapsed_s":           t_elapsed,
        })

        print(
            f"  [{idx+1:>3}/{total}] {track_name}"
            f"  bpm={float(params.get('bpm') or 0):.1f}"
            f"  key={str(params.get('key', '?')):<16}"
            f"  seed={params.get('seed_value')}"
            f"  ({t_elapsed:.2f}s)"
        )

    return manifest_entries


def run_production_batch(
    engine,
    orc,
    genres:         List[str] = None,
    count:          int       = PROD_COUNT,
    mut:            float     = PROD_MUT,
    score_floor:    float     = PROD_SCORE_FLOOR,
    out_root:       Path      = Path("production_run"),
    bpm_filter:     bool      = True,
    skip_gen:       bool      = False,
) -> None:
    """
    Production burn — two-pass pipeline built on Gen 3 golden seeds.

    Phase 1 (Instrumental):
      - `count` tracks/genre, seeded from generation_archive/ Gen 3 winners
      - mut=0.15 (bridge-validated controlled creativity)
      - vocal_mask=OFF
      - Grade via calculate_midi_fitness
      - Benchmark filter: score >= score_floor AND BPM within genre tolerance

    Phase 2 (Vocal Siblings):
      - One sibling per Phase 1 winner, exact same seed/params
      - vocal_mask=ON  (vocal frequency space C4–C6 cleared in verse/hook/chorus)
      - Perfectly paired instrumental + vocal-ready tracks

    Output layout
    -------------
    production_run/
      instrumental/{genre}/   track_000/ ... (300 per genre, pre-filter)
      vocal_ready/{genre}/    sibling_000_track_NNN/ ... (winners only)
      production_pack_manifest.json
    """
    if genres is None:
        genres = GENRES

    total_t0 = time.time()
    run_ts   = time.strftime("%Y%m%d_%H%M%S")
    header   = f"MUSIC ARCHITECT V7  —  PRODUCTION BATCH  {run_ts}"
    print(f"\n{'='*len(header)}")
    print(header)
    print(f"  Genres      : {genres}")
    print(f"  Count       : {count} tracks/genre  (instrumental pass)")
    print(f"  Mutation    : {mut}  (bridge-validated controlled creativity)")
    print(f"  Score floor : {score_floor}  (production benchmark minimum)")
    print(f"  Seed source : Gen 3 golden winners  (generation_archive/)")
    print(f"{'='*len(header)}\n")

    instr_root = out_root / "instrumental"
    vocal_root = out_root / "vocal_ready"
    instr_root.mkdir(parents=True, exist_ok=True)
    vocal_root.mkdir(parents=True, exist_ok=True)

    pack_manifest: dict = {
        "run_timestamp": run_ts,
        "mutation":      mut,
        "score_floor":   score_floor,
        "genres":        {},
    }

    for genre in genres:
        genre_t0 = time.time()
        print(f"\n{'-'*60}")
        print(f"  PHASE 1  —  INSTRUMENTAL  [{genre.upper()}]")
        print(f"{'-'*60}")

        # Seed lock: most recent Gen 3 archive
        archive_path = _load_gen3_archive(genre)
        if archive_path:
            print(f"  Seed source : {Path(archive_path).name}")
        else:
            fallback = (
                Path("evolutionary_run") / "gen3" / genre / "evolutionary_pool.json"
            )
            archive_path = str(fallback) if fallback.exists() else None
            print(f"  Seed source : {'gen3 pool fallback' if archive_path else 'free exploration'}")

        genre_instr_dir = instr_root / genre

        # skip_gen=True: reuse existing tracks (e.g. to rerun filter only)
        n_existing = sum(1 for p in genre_instr_dir.iterdir() if p.is_dir()) \
                     if genre_instr_dir.exists() else 0
        if skip_gen and n_existing >= count:
            print(f"  skip_gen=True: reusing {n_existing} existing tracks in {genre_instr_dir}")
        else:
            _run_gen(
                genre             = genre,
                count             = count,
                outdir            = genre_instr_dir,
                seed_pool_path    = archive_path,
                engine            = engine,
                orc               = orc,
                gen_label         = "prod_instr",
                mut_factor        = mut,
                vocal_mask        = False,
                generation_level  = 4,
            )

        # Grade Phase 1
        print(f"\n  Grading Phase 1 [{genre.upper()}] ...")
        report     = _process_genre(genre_instr_dir)
        report_path = genre_instr_dir / "math_fitness_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        leaderboard = report.get("leaderboard", [])
        score_map   = {e["track_name"]: e["score"] for e in leaderboard}
        print(f"  {report['tracks_scored']} tracks scored  ->  {report_path.name}")
        if leaderboard:
            top = leaderboard[0]
            print(f"  Top track   : {top['track_name']}  score={top['score']:.2f}")

        # Benchmark filter: score floor is always applied.
        # BPM range is skipped when bpm_filter=False (e.g. for trap which evolves
        # toward 130-165 BPM, outside the benchmark sample's 126.9 average).
        benchmark  = _load_benchmark(genre)
        bpm_target = benchmark.get("targets", {}).get("rhythm", {}).get("bpm")
        bpm_tol    = benchmark.get("tolerances", {}).get("rhythm", {}).get("bpm")
        if bpm_filter and bpm_target:
            print(
                f"  BPM filter  : {bpm_target:.1f} +/- {bpm_tol:.1f}"
                f"  ->  [{bpm_target - bpm_tol:.1f}, {bpm_target + bpm_tol:.1f}]"
            )
        else:
            _bpm_info = f"{bpm_target:.1f}" if bpm_target else "?"
            print(f"  BPM filter  : OFF  (score-only, benchmark BPM={_bpm_info})")

        winner_dirs: List[Path] = []
        rejected_count = 0
        for track_dir in sorted(
            p for p in genre_instr_dir.iterdir() if p.is_dir()
        ):
            track_name = track_dir.name
            score      = score_map.get(track_name, 0.0)
            bpm        = 0.0
            meta_path  = track_dir / "generation_metadata.json"
            if meta_path.exists():
                try:
                    m   = json.loads(meta_path.read_text(encoding="utf-8"))
                    bpm = float(m.get("generation_params", {}).get("bpm") or 0)
                except Exception:
                    pass
            # Pass an empty benchmark dict when BPM filter is disabled
            bmark = benchmark if bpm_filter else {}
            passes, _ = _passes_benchmark(bpm, score, bmark, score_floor)
            if passes:
                winner_dirs.append(track_dir)
            else:
                rejected_count += 1

        pass_rate = len(winner_dirs) / max(1, report["tracks_scored"]) * 100
        print(
            f"\n  Benchmark filter : {len(winner_dirs)} passed / "
            f"{report['tracks_scored']} total  ({pass_rate:.1f}% pass rate)"
            f"  |  {rejected_count} rejected"
        )

        # Phase 2: vocal siblings for each winner
        print(f"\n{'-'*60}")
        print(f"  PHASE 2  —  VOCAL SIBLINGS  [{genre.upper()}]  "
              f"({len(winner_dirs)} tracks, vocal_mask=ON)")
        print(f"{'-'*60}")

        sibling_entries = _run_sibling_pass(
            winner_dirs = winner_dirs,
            out_root    = vocal_root,
            genre       = genre,
            engine      = engine,
            orc         = orc,
        )

        genre_elapsed = time.time() - genre_t0
        pack_manifest["genres"][genre] = {
            "instrumental_generated": count,
            "graded_count":           report["tracks_scored"],
            "passed_filter":          len(winner_dirs),
            "pass_rate_pct":          round(pass_rate, 1),
            "vocal_siblings":         len(sibling_entries),
            "score_floor":            score_floor,
            "top_score":              leaderboard[0]["score"] if leaderboard else 0,
            "elapsed_s":              round(genre_elapsed, 1),
            "instrumental_dir":       str(genre_instr_dir),
            "vocal_dir":              str(vocal_root / genre),
        }

    # Write pack manifest
    manifest_path = out_root / "production_pack_manifest.json"
    manifest_path.write_text(json.dumps(pack_manifest, indent=2), encoding="utf-8")

    total_elapsed = time.time() - total_t0
    print(f"\n{'='*60}")
    print(f"  PRODUCTION BATCH COMPLETE  —  {total_elapsed/60:.1f} min")
    print()
    print(f"  {'Genre':<10} {'Instrumental':>13} {'Passed':>7} {'Siblings':>9}")
    print(f"  {'-'*44}")
    for genre, stats in pack_manifest["genres"].items():
        print(
            f"  {genre.upper():<10}"
            f"  {stats['instrumental_generated']:>12}"
            f"  {stats['passed_filter']:>6}"
            f"  {stats['vocal_siblings']:>8}"
        )
    print()
    print(f"  Manifest -> {manifest_path.resolve()}")
    print(f"{'='*60}\n")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main(engine=None, orc=None) -> None:
    root_dir = Path("evolutionary_run")
    root_dir.mkdir(exist_ok=True)

    run_ts = time.strftime("%Y%m%d_%H%M%S")
    header = f"MUSIC ARCHITECT V7  —  EVOLUTIONARY BATCH  {run_ts}"
    print(f"\n{'='*len(header)}")
    print(header)
    print(f"Genres : {GENRES}")
    print(f"Sizes  : {GEN_SIZES}  (tracks/genre/generation)")
    mut_str = " -> ".join(f"{m}" for m in MUT_SCHEDULE)
    print(f"Elite  : top {TOP_PCT*100:.0f}%  |  mutation schedule [{mut_str}]  |  watchdog {WATCHDOG_S}s")
    print(f"{'='*len(header)}\n")

    # -- Pre-flight: validate all four pipeline requirements -------------------
    print("Pre-flight pipeline validation ...")
    if not validate_pipeline():
        print("  [WARN] One or more pipeline checks failed — see output above.")
        print("         Continuing anyway; check the log for integration gaps.\n")
    else:
        print("  All pipeline checks passed.\n")

    # -- System snapshot (audit trail for thesis / reproducibility) -----------
    print("Writing pre-run system snapshot ...")
    write_system_snapshot(genres=GENRES)
    print()

    # -- Initialise composition stack (or reuse if passed from __main__) -------
    if engine is None:
        print("Initialising composition stack (loading seeds) ...")
        t0     = time.time()
        engine = CompositionEngine(seeds_dir="seeds")
        engine.load_seeds()
        orc    = _Orchestrator(engine) if _ORC_AVAILABLE else None
        print(f"Ready in {time.time()-t0:.1f}s  "
              f"({'modular orchestrator' if orc else 'legacy engine'})\n")

    # pool_paths[genre] = path to evolutionary_pool.json from the previous gen
    pool_paths: Dict[str, Optional[str]] = {g: None for g in GENRES}

    total_t0 = time.time()

    for gen_idx, gen_size in enumerate(GEN_SIZES):
        gen_num   = gen_idx + 1
        gen_label = f"gen{gen_num}"

        # Mutation used to PRODUCE this gen (0.0 = free for gen1)
        this_mut = MUT_SCHEDULE[gen_idx - 1] if gen_idx > 0 else 0.0
        # Mutation baked into the pool that will SEED the next gen
        next_mut = MUT_SCHEDULE[gen_idx] if gen_idx < len(MUT_SCHEDULE) else MUT_SCHEDULE[-1]

        divider = "-" * 65
        print(f"\n{divider}")
        print(f"  GENERATION {gen_num}  |  {gen_size} tracks / genre  "
              f"|  {'golden injection  mut=' + str(this_mut) if gen_num > 1 else 'free exploration'}")
        print(divider)

        gen_t0 = time.time()

        # -- Generate ----------------------------------------------------------
        for genre in GENRES:
            genre_dir = root_dir / gen_label / genre
            _run_gen(
                genre             = genre,
                count             = gen_size,
                outdir            = genre_dir,
                seed_pool_path    = pool_paths[genre],
                engine            = engine,
                orc               = orc,
                gen_label         = gen_label,
                mut_factor        = this_mut,
                vocal_mask        = False,
                generation_level  = gen_num,
            )

        gen_elapsed = time.time() - gen_t0
        print(f"\n  Generation {gen_num} completed in {gen_elapsed:.1f}s")

        # -- Grade + build pools for next generation ---------------------------
        is_last = gen_num == len(GEN_SIZES)
        print(f"\n{'-'*40}")
        print(f"  GRADING GENERATION {gen_num}"
              + (f"  (next gen will use mut={next_mut})" if not is_last else "  (final)"))
        print(f"{'-'*40}")

        for genre in GENRES:
            genre_dir = root_dir / gen_label / genre
            _, evo_pool_path = _grade_and_pool(
                genre_dir, top_pct=TOP_PCT, mut_factor=next_mut
            )
            if not is_last:
                pool_paths[genre] = str(evo_pool_path)

    total_elapsed = time.time() - total_t0
    print(f"\n{'='*65}")
    print(f"  EVOLUTIONARY RUN COMPLETE  —  {total_elapsed/60:.1f} min total")
    print(f"  Output : {root_dir.resolve()}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Music Architect V7 — evolutionary batch runner"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Explicit alias: run the full 3-generation evolutionary chain (default behaviour)",
    )
    parser.add_argument(
        "--bridge",
        action="store_true",
        help="Run the Bridge Experiment (Musical Chaos Threshold) instead of the main evolutionary run",
    )
    parser.add_argument(
        "--bridge-genres",
        nargs="+",
        default=None,
        metavar="GENRE",
        help="Genres for bridge experiment (default: all GENRES)",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help=(
            "Production burn: 300 tracks/genre from Gen 3 seeds, mut=0.15, "
            "benchmark-filtered. Outputs paired instrumental + vocal-ready siblings."
        ),
    )
    parser.add_argument(
        "--prod-genres",
        nargs="+",
        default=None,
        metavar="GENRE",
        help="Genres for production batch (default: all GENRES)",
    )
    parser.add_argument(
        "--prod-count",
        type=int,
        default=PROD_COUNT,
        metavar="N",
        help=f"Tracks per genre for production instrumental pass (default: {PROD_COUNT})",
    )
    parser.add_argument(
        "--prod-mut",
        type=float,
        default=PROD_MUT,
        metavar="F",
        help=f"Mutation factor for production batch (default: {PROD_MUT})",
    )
    parser.add_argument(
        "--prod-floor",
        type=float,
        default=PROD_SCORE_FLOOR,
        metavar="F",
        help=f"Minimum fitness score for production pack (default: {PROD_SCORE_FLOOR})",
    )
    parser.add_argument(
        "--no-bpm-filter",
        action="store_true",
        help=(
            "Disable the BPM benchmark range check — use score-only filtering. "
            "Useful when the generator's evolved BPM range differs from the benchmark sample."
        ),
    )
    parser.add_argument(
        "--skip-gen",
        action="store_true",
        help=(
            "Skip Phase 1 generation if tracks already exist. "
            "Re-applies the benchmark filter and regenerates vocal siblings only."
        ),
    )
    args = parser.parse_args()

    # Initialise composition stack once (shared by all modes)
    print("Initialising composition stack (loading seeds) ...")
    _t0     = time.time()
    _engine = CompositionEngine(seeds_dir="seeds")
    _engine.load_seeds()
    _orc    = _Orchestrator(_engine) if _ORC_AVAILABLE else None
    print(f"Ready in {time.time()-_t0:.1f}s\n")

    if args.production:
        run_production_batch(
            engine      = _engine,
            orc         = _orc,
            genres      = args.prod_genres or GENRES,
            count       = args.prod_count,
            mut         = args.prod_mut,
            score_floor = args.prod_floor,
            bpm_filter  = not args.no_bpm_filter,
            skip_gen    = args.skip_gen,
        )
    elif args.bridge:
        run_bridge_experiment(
            engine  = _engine,
            orc     = _orc,
            genres  = args.bridge_genres or GENRES,
        )
    else:
        main(engine=_engine, orc=_orc)
