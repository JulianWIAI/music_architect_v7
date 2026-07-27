"""
Music Architect V7 — Entry Point
=================================
An AI-powered MIDI composition engine with an evolutionary fitness loop,
10-track generation pipeline, and commercial sync watermarking.

Usage
-----
Launch the graphical user interface (default):
    python main.py

Run the evolutionary batch pipeline (Trap / Hip-Hop):
    python main.py batch evolutionary

Run the commercial sync pipeline (Pop / House / EDM, bright scales only):
    python main.py batch commercial

Watermark the generated MIDI catalog:
    python main.py watermark
    python main.py watermark --extract path/to/file.mid

Options for 'batch':
    --out-dir DIR        Output directory  (default: ./output_run)
    --genres GENRE ...   Override genre list
    --score-floor FLOAT  Minimum fitness score for sibling pass (default 45.0)
    --skip-to-gen N      Resume from generation N (1, 2, or 3)

Options for 'watermark':
    --extract FILE       Decode and verify the watermark in FILE
    --out-dir DIR        Output directory  (default: ./Watermarked_Catalog)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def _check_dependencies() -> None:
    """
    Verify that required packages are installed.
    Attempts an automatic pip install for missing core packages.
    'pygame' is optional (only needed for in-app audio preview).
    """
    import subprocess

    # (package_to_import, pip_install_name) pairs
    required = [
        ("midiutil", "MIDIUtil"),
        ("mido",     "mido"),
        ("tkinter",  None),          # bundled with CPython, not pip-installable
    ]

    for module_name, pip_name in required:
        try:
            __import__(module_name)
        except ImportError:
            if pip_name is None:
                print(f"  [WARN] {module_name} not found — install Python with Tk support")
                continue
            print(f"  Installing {pip_name} ...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name, "-q"])

    # pygame is optional — used only for WAV preview inside the GUI
    try:
        import pygame  # noqa: F401
    except ImportError:
        print("  [INFO] pygame not installed — audio preview disabled (pip install pygame)")


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def _launch_gui() -> None:
    """Start the Tkinter GUI application."""
    from src.gui.app import main as gui_main
    gui_main()


def _run_batch(args: argparse.Namespace) -> None:
    """
    Dispatch to the correct batch pipeline.

    'evolutionary' targets Trap and Hip-Hop with dark/aggressive scales.
    'commercial'   targets Pop, House, and EDM locked to bright scales only.
    Both pipelines use a 3-generation evolutionary fitness loop.
    """
    out_dir = Path(args.out_dir)

    if args.pipeline == "evolutionary":
        # Evolutionary Trap/Hip-Hop pipeline (omni_render)
        from src.pipeline.omni_render import main as evo_main
        sys.argv = [sys.argv[0]]          # clear argv so the pipeline's own argparse is clean
        if args.out_dir:
            sys.argv += ["--out-dir", str(out_dir)]
        evo_main()

    elif args.pipeline == "commercial":
        # Commercial sync pipeline — bright scales, Pop/House/EDM
        from src.pipeline.batch_commercial import main as comm_main
        sys.argv = [sys.argv[0], "--out-dir", str(out_dir)]
        if hasattr(args, "score_floor") and args.score_floor:
            sys.argv += ["--score-floor", str(args.score_floor)]
        if hasattr(args, "skip_to_gen") and args.skip_to_gen:
            sys.argv += ["--skip-to-gen", str(args.skip_to_gen)]
        if hasattr(args, "genres") and args.genres:
            sys.argv += ["--genres"] + args.genres
        comm_main()

    else:
        print(f"Unknown pipeline '{args.pipeline}'. Choose: evolutionary | commercial")
        sys.exit(1)


def _run_watermark(args: argparse.Namespace) -> None:
    """
    Run the dual-layer steganographic watermarking tool.

    Layer 1 injects a copyright MetaMessage track into every MIDI file.
    Layer 2 hides a per-file fingerprint in note velocity LSBs.
    """
    from src.tools.watermark_engine import watermark_catalog, extract_watermark

    if args.extract:
        # Decode and verify the watermark in a single file
        extract_watermark(args.extract)
    else:
        # Watermark every .mid file in the catalog directories
        watermark_catalog(out_root=Path(args.out_dir))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """
    Build the top-level argument parser with sub-commands.

    Sub-commands
    ------------
    (none)      Launch the GUI  [default when no sub-command is given]
    batch       Run a batch generation pipeline
    watermark   Watermark or inspect the MIDI catalog
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Music Architect V7 — AI MIDI composition engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                            # GUI\n"
            "  python main.py batch evolutionary         # Trap/HipHop pipeline\n"
            "  python main.py batch commercial           # Pop/House/EDM pipeline\n"
            "  python main.py watermark                  # Watermark catalog\n"
            "  python main.py watermark --extract f.mid  # Verify watermark\n"
        ),
    )

    sub = parser.add_subparsers(dest="command")

    # ── batch sub-command ─────────────────────────────────────────────────────
    batch_p = sub.add_parser("batch", help="Run a batch generation pipeline")
    batch_p.add_argument(
        "pipeline",
        choices=["evolutionary", "commercial"],
        help="'evolutionary' = Trap/HipHop  |  'commercial' = Pop/House/EDM",
    )
    batch_p.add_argument("--out-dir",     default="output_run",  metavar="DIR")
    batch_p.add_argument("--genres",      nargs="+",             metavar="GENRE")
    batch_p.add_argument("--score-floor", type=float,            metavar="FLOAT")
    batch_p.add_argument("--skip-to-gen", type=int, choices=[1, 2, 3], metavar="N")

    # ── watermark sub-command ─────────────────────────────────────────────────
    wm_p = sub.add_parser("watermark", help="Watermark or inspect the MIDI catalog")
    wm_p.add_argument(
        "--extract",
        metavar="FILE",
        help="Decode and verify the watermark in a single .mid file",
    )
    wm_p.add_argument("--out-dir", default="Watermarked_Catalog", metavar="DIR")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Parse command-line arguments and dispatch to the correct subsystem.
    Falls back to the GUI when no sub-command is given.
    """
    parser = _build_parser()
    args   = parser.parse_args()

    _check_dependencies()

    if args.command == "batch":
        _run_batch(args)
    elif args.command == "watermark":
        _run_watermark(args)
    else:
        # Default: no sub-command → launch the GUI
        _launch_gui()


if __name__ == "__main__":
    main()
