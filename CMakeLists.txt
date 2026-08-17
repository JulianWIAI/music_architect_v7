# CMakeLists.txt — Build the synth_core pybind11 extension module.
#
# Supported compilers (cross-platform):
#   macOS  : Apple Clang  (Xcode Command Line Tools)
#   Windows: MSVC 2019/2022  or  MinGW-w64 / Clang-cl
#   Linux  : GCC or Clang (not the primary target but works unchanged)
#
# Prerequisites
# -------------
#   pip install pybind11    (puts pybind11 where find_package can see it)
#   cmake --version >= 3.15
#
# Build (out-of-source, recommended)
# ------------------------------------
#   mkdir build && cd build
#   cmake .. -DCMAKE_BUILD_TYPE=Release
#   cmake --build . --config Release
#
#   The compiled module lands in build/ as:
#     synth_core.cpython-3XX-darwin.so        (macOS)
#     synth_core.cpython-3XX-win_amd64.pyd    (Windows)
#
# Alternatively, use setup.py (simpler for Python users):
#   pip install pybind11
#   python setup.py build_ext --inplace

cmake_minimum_required(VERSION 3.15)
project(synth_core LANGUAGES CXX)

# ── C++ standard ─────────────────────────────────────────────────────────────
# C++17 required for:
#   • structured bindings (auto [a, b] = ...)
#   • std::unordered_map with emplace
#   • if constexpr (used in release builds)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)   # Disable GNU extensions for MSVC compatibility

# ── Find pybind11 ─────────────────────────────────────────────────────────────
# pybind11 installed via pip exposes a cmake config at the pybind11 package root.
# Running `python -m pybind11 --cmakedir` prints the path; cmake can pick it up
# automatically when pybind11 is installed in the active Python environment.
find_package(pybind11 CONFIG REQUIRED)

# ── Source files ─────────────────────────────────────────────────────────────
set(SYNTH_SOURCES
    src/synth_core/src/adsr_envelope.cpp
    src/synth_core/src/oscillator.cpp
    src/synth_core/src/instrument_timbres.cpp
    src/synth_core/src/drum_synthesizer.cpp
    src/synth_core/src/synth_core.cpp
    src/synth_core/src/bindings.cpp
)

# ── Extension module target ───────────────────────────────────────────────────
# pybind11_add_module() creates a shared library with the correct Python
# extension suffix (.so / .pyd) and links against the Python runtime.
pybind11_add_module(synth_core ${SYNTH_SOURCES})

# Include our own headers
target_include_directories(synth_core PRIVATE src/synth_core/include)

# ── Optimisation flags ────────────────────────────────────────────────────────
# MSVC and GCC/Clang use different flag syntax.
# $<CXX_COMPILER_ID:MSVC> evaluates to 1 on MSVC, 0 otherwise.
target_compile_options(synth_core PRIVATE
    # MSVC: max speed optimisation, enable AVX2 SIMD
    $<$<CXX_COMPILER_ID:MSVC>:/O2 /arch:AVX2 /fp:fast>

    # GCC / Clang (macOS, Linux, MinGW):
    # -O3          : full optimisation
    # -ffast-math  : allow re-association and flush-to-zero (safe for audio)
    # -march=native: tune for the build machine's CPU (remove if building
    #                a redistributable binary — use -march=x86-64 instead)
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-O3 -ffast-math -march=native>
)

# ── Install rule ──────────────────────────────────────────────────────────────
# cmake --install build/ copies synth_core.so to the project root so that
# `import synth_core` works when running python from the project root.
install(TARGETS synth_core DESTINATION ${CMAKE_SOURCE_DIR})
