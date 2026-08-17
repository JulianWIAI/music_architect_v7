/**
 * @file bindings.cpp
 * @brief pybind11 module definition for the synth_core extension.
 *
 * This file is the only place where the Python/C++ boundary is defined.
 * It exposes SynthCore to Python under the module name "synth_core".
 *
 * Python usage (after building):
 *
 *   import synth_core
 *
 *   core = synth_core.SynthCore(sample_rate=44100)
 *
 *   # Returns (start_sample_index: int, samples: numpy.ndarray[float32])
 *   start, arr = core.synthesize_note(midi_note=60, start_time=0.0,
 *                                     duration=0.5, velocity=100, program=0)
 *
 *   start, arr = core.synthesize_drum(midi_note=36, start_time=0.0, velocity=127)
 *
 *   hz = synth_core.SynthCore.midi_to_freq(69)  # → 440.0
 *
 * Return type contract
 * --------------------
 * Both synthesize_note() and synthesize_drum() return a Python tuple:
 *   ( int,  numpy.ndarray[numpy.float32, ndim=1] )
 * The numpy array is C-contiguous and owns its memory.  It can be used
 * directly in numpy slice assignment for buffer mixing:
 *
 *   buffer[start:start+len(arr)] += arr
 */

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>   // py::array_t — must be included for numpy return types

#include "synth_core.hpp"

namespace py = pybind11;

// ── Module definition ─────────────────────────────────────────────────────────

PYBIND11_MODULE(synth_core, m) {
    m.doc() =
        "synth_core — C++ synthesizer core for Music Architect.\n\n"
        "Provides additive harmonic synthesis (synthesize_note) and\n"
        "percussion synthesis (synthesize_drum) that replace the pure\n"
        "Python hot-path in src/rendering/builtin_synthesizer.py.\n\n"
        "Both methods are 50–200× faster than the equivalent Python\n"
        "implementation; the API is identical so the Python wrapper\n"
        "in builtin_synthesizer.py can call either transparently.";

    // ── SynthCore class ───────────────────────────────────────────────────────

    py::class_<SynthCore>(m, "SynthCore",
        "Main synthesizer class.  Create one instance per render session.\n\n"
        "Thread safety: the drum sample cache is NOT thread-safe.  If you\n"
        "need concurrent rendering, create one SynthCore per thread.")

        // Constructor
        .def(py::init<int>(),
             py::arg("sample_rate") = 44100,
             "Construct a SynthCore.\n\n"
             "Args:\n"
             "    sample_rate: Audio sample rate in Hz (default 44100).")

        // synthesize_note
        .def("synthesize_note",
             &SynthCore::synthesize_note,
             py::arg("midi_note"),
             py::arg("start_time"),
             py::arg("duration"),
             py::arg("velocity"),
             py::arg("program") = 0,
             "Synthesize a single melodic note using additive harmonic synthesis.\n\n"
             "Args:\n"
             "    midi_note:  MIDI note number 0–127.\n"
             "    start_time: Note start time in seconds.\n"
             "    duration:   Note-on duration in seconds (release tail is\n"
             "                added automatically from the instrument's ADSR).\n"
             "    velocity:   MIDI velocity 0–127.\n"
             "    program:    GM program number (instrument). Default 0.\n\n"
             "Returns:\n"
             "    tuple[int, numpy.ndarray[float32]]:\n"
             "        (start_sample_index, samples)")

        // synthesize_drum
        .def("synthesize_drum",
             &SynthCore::synthesize_drum,
             py::arg("midi_note"),
             py::arg("start_time"),
             py::arg("velocity"),
             "Synthesize a drum hit using cached percussion buffers.\n\n"
             "The sample for each midi_note is generated once on first access\n"
             "and cached for subsequent hits (same behaviour as the Python\n"
             "drum_cache dict in BuiltinSynthesizer).\n\n"
             "Args:\n"
             "    midi_note:  GM drum note number (e.g. 36=kick, 38=snare,\n"
             "                42=closed hi-hat, 46=open hi-hat, 49=crash).\n"
             "    start_time: Hit time in seconds.\n"
             "    velocity:   MIDI velocity 0–127.\n\n"
             "Returns:\n"
             "    tuple[int, numpy.ndarray[float32]]:\n"
             "        (start_sample_index, samples)")

        // sample_rate property (read-only)
        .def_property_readonly("sample_rate",
             &SynthCore::sample_rate,
             "Audio sample rate this instance was constructed with (read-only).")

        // midi_to_freq static method
        .def_static("midi_to_freq",
             &SynthCore::midi_to_freq,
             py::arg("midi_note"),
             "Convert a MIDI note number to frequency in Hz.\n\n"
             "Uses equal temperament: f = 440 × 2^((note − 69) / 12).\n\n"
             "Args:\n"
             "    midi_note: MIDI note number (e.g. 69 → 440.0 Hz).\n\n"
             "Returns:\n"
             "    float: Frequency in Hz.");
}
