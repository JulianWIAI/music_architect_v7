/**
 * @file synth_core.hpp
 * @brief Main C++ synthesizer class exposed to Python via pybind11.
 *
 * SynthCore replaces the hot-path methods of BuiltinSynthesizer
 * (src/rendering/builtin_synthesizer.py).  It contains:
 *   - Per-sample note synthesis (additive harmonics + ADSR) in C++.
 *   - Drum hit synthesis via DrumSynthesizer (cached, noisy percussion).
 *
 * Composition rendering (track iteration, buffer mixing) stays in Python
 * using numpy, which is already a C extension — the overhead of dict
 * parsing and loop control in Python is negligible compared to the
 * per-sample arithmetic that this class accelerates.
 *
 * Return types
 * ------------
 * Both synthesize_note() and synthesize_drum() return a Python tuple
 *   (start_sample_index: int, samples: numpy.ndarray float32)
 * so the Python caller can slice the result directly into a numpy buffer.
 *
 * pybind11 dependency
 * -------------------
 * This header includes pybind11/numpy.h so that the return types of
 * synthesize_note() and synthesize_drum() can be declared here.
 * All other headers (adsr_envelope, oscillator, timbres, drums) are
 * pure C++ and have no pybind11 dependency.
 */

#pragma once

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>

#include "drum_synthesizer.hpp"

namespace py = pybind11;

class SynthCore {
public:
    /**
     * Construct a SynthCore.
     *
     * @param sample_rate  Audio sample rate in Hz.  Must match the sample
     *                     rate used by the rest of the rendering pipeline.
     */
    explicit SynthCore(int sample_rate = 44100);

    // ── Melodic synthesis ────────────────────────────────────────────────────

    /**
     * Synthesize a single melodic note using additive harmonic synthesis.
     *
     * Matches BuiltinSynthesizer.synthesize_note() exactly.
     *
     * @param midi_note   MIDI note number (0–127).
     * @param start_time  Note start time in seconds; used to compute the
     *                    start sample index returned in the tuple.
     * @param duration    Note-on duration (seconds).  Release tail is added
     *                    automatically from the instrument's ADSR.
     * @param velocity    MIDI velocity (0–127).
     * @param program     GM program number (instrument).  Uses default timbre
     *                    for programs not in the timbre registry.
     * @return Python tuple: (start_sample_index: int,
     *                        samples: numpy.ndarray[float32])
     */
    py::tuple synthesize_note(int    midi_note,
                              double start_time,
                              double duration,
                              double velocity,
                              int    program = 0) const;

    // ── Percussion synthesis ─────────────────────────────────────────────────

    /**
     * Synthesize a percussion hit using the internal DrumSynthesizer.
     *
     * Matches BuiltinSynthesizer.synthesize_drum() exactly.
     *
     * @param midi_note   GM drum note number (e.g. 36 = kick, 38 = snare).
     * @param start_time  Hit time in seconds.
     * @param velocity    MIDI velocity (0–127).
     * @return Python tuple: (start_sample_index: int,
     *                        samples: numpy.ndarray[float32])
     */
    py::tuple synthesize_drum(int midi_note, double start_time, double velocity);

    // ── Utility ──────────────────────────────────────────────────────────────

    /**
     * Convert a MIDI note number to its equal-temperament frequency in Hz.
     * A4 (MIDI 69) = 440 Hz.
     */
    static double midi_to_freq(int midi_note) noexcept;

    /** Return the sample rate this instance was constructed with. */
    int sample_rate() const noexcept { return sample_rate_; }

private:
    int sample_rate_;
    DrumSynthesizer drums_; // Owns the drum sample cache
};
