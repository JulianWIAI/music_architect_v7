"""
Scans a directory for analysis JSON files and loads them into AnalysisJSON objects.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Tuple

from src.ingestion.analysis_schema import AnalysisJSON, load_analysis_json, validate_analysis_json

logger = logging.getLogger(__name__)


def scan_analysis_dir(directory: str | Path) -> List[Path]:
    """Return all .json files under *directory*, sorted by name for determinism."""
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"Analysis directory not found: {root}")
    paths = sorted(root.glob("**/*.json"))
    logger.info("Found %d JSON files in %s", len(paths), root)
    return paths


def load_all_analysis_files(
    directory: str | Path,
    skip_invalid: bool = True,
) -> List[Tuple[Path, AnalysisJSON]]:
    """
    Load every valid analysis JSON under *directory*.

    Returns a list of (path, AnalysisJSON) pairs.  Files that fail validation
    are logged as warnings and skipped when *skip_invalid* is True; they raise
    ValueError otherwise.
    """
    results: List[Tuple[Path, AnalysisJSON]] = []
    for path in scan_analysis_dir(directory):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            msg = f"Cannot read {path}: {exc}"
            if skip_invalid:
                logger.warning(msg)
                continue
            raise ValueError(msg) from exc

        errors = validate_analysis_json(raw)
        if errors:
            msg = f"Invalid analysis JSON {path}: {'; '.join(errors)}"
            if skip_invalid:
                logger.warning(msg)
                continue
            raise ValueError(msg)

        results.append((path, load_analysis_json(path)))

    logger.info("Loaded %d valid analysis files", len(results))
    return results
