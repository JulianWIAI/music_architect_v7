"""
setup.py — Build the synth_core C++ extension module using pybind11.

This is the recommended build path for Python developers.
cmake is NOT required — pybind11 is used directly via setuptools.

Prerequisites
-------------
    pip install pybind11

Build (in-place — the .so/.pyd appears in the project root):
    python setup.py build_ext --inplace

Or install into the current Python environment:
    pip install -e .

After building, 'import synth_core' works when running from the project root:
    python main.py   # BuiltinSynthesizer auto-detects and uses C++ core

Cross-platform notes
--------------------
Windows (MSVC / Visual Studio 2019+):
    The pybind11 setup helpers automatically detect MSVC and set /O2 /arch:AVX2.
    You need the "Desktop Development with C++" workload installed in VS.
    Run from a Developer Command Prompt or let pip invoke MSVC automatically.

macOS (Apple Clang):
    Xcode Command Line Tools required:  xcode-select --install
    The helpers set -O3 -ffast-math automatically.

Linux (GCC / Clang):
    Works out of the box.  python3-dev package must be installed.
"""

import sys
from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext

# ── Extension definition ───────────────────────────────────────────────────────

_SOURCES = [
    "src/synth_core/src/adsr_envelope.cpp",
    "src/synth_core/src/oscillator.cpp",
    "src/synth_core/src/instrument_timbres.cpp",
    "src/synth_core/src/drum_synthesizer.cpp",
    "src/synth_core/src/synth_core.cpp",
    "src/synth_core/src/bindings.cpp",
]

# Extra compiler flags for maximum performance.
# These are additive — pybind11 setup_helpers already set safe defaults.
_EXTRA_FLAGS_WINDOWS = ["/O2", "/arch:AVX2", "/fp:fast"]

# macOS ships a universal2 Python that compiles for both arm64 and x86_64 in
# a single pass.  -march=native picks the current CPU's arch (e.g. apple-m1)
# which the x86_64 slice of clang doesn't recognise, so we omit it on macOS.
# On Linux the single-arch toolchain handles -march=native correctly.
if sys.platform == "darwin":
    _EXTRA_FLAGS_UNIX = ["-O3", "-ffast-math"]
else:
    _EXTRA_FLAGS_UNIX = ["-O3", "-ffast-math", "-march=native"]

_extra_compile_args = (
    _EXTRA_FLAGS_WINDOWS if sys.platform == "win32" else _EXTRA_FLAGS_UNIX
)

ext = Pybind11Extension(
    # Module name as seen by Python: `import synth_core`
    name="synth_core",
    sources=_SOURCES,
    include_dirs=["src/synth_core/include"],
    extra_compile_args=_extra_compile_args,
    # C++17: required for structured bindings and constexpr if
    cxx_std=17,
)

# ── Setup ─────────────────────────────────────────────────────────────────────

setup(
    name="synth_core",
    version="1.0.0",
    description="C++ synthesizer core for Music Architect (pybind11)",
    ext_modules=[ext],
    cmdclass={"build_ext": build_ext},
    # Minimum Python version — pybind11 requires 3.7+
    python_requires=">=3.9",
)
