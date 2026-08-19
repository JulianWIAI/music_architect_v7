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
#include <pybind11/stl.h>     // automatic std::vector ↔ Python list conversion

#include "synth_core.hpp"
#include "saturation.hpp"     // SaturationProcessor — DSP saturation + de-clicking

namespace py = pybind11;

// ── Module definition ─────────────────────────────────────────────────────────

PYBIND11_MODULE(synth_core, m) {
    m.doc() =
        "synth_core — C++ synthesizer and DSP core for Music Architect.\n\n"
        "Provides:\n"
        "  SynthCore          — additive harmonic synthesis (note + drum).\n"
        "  SaturationProcessor — saturation/drive with built-in de-clicking.\n\n"
        "Audio buffers are passed as numpy.ndarray[float32] — zero-copy\n"
        "via pybind11 buffer protocol (satisfies the numpy.ctypeslib\n"
        "constraint from the project's architecture notes).";

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

    // ── SaturationProcessor class ─────────────────────────────────────────────
    //
    // Exposes the saturation/drive DSP processor to Python.  Buffers are
    // exchanged as numpy float32 arrays — no Python list conversion needed,
    // satisfying the architecture's zero-copy buffer-handoff constraint.

    // Expose the Type enum so Python callers can use synth_core.SaturationType.TAPE_SOFT
    py::enum_<SaturationProcessor::Type>(m, "SaturationType",
        "Saturation algorithm identifier for SaturationProcessor.")
        .value("NONE",           SaturationProcessor::Type::NONE)
        .value("TAPE_SOFT",      SaturationProcessor::Type::TAPE_SOFT)
        .value("TUBE_TANH",      SaturationProcessor::Type::TUBE_TANH)
        .value("HARD_CLIP",      SaturationProcessor::Type::HARD_CLIP)
        .value("ASYMMETRIC_SOFT",SaturationProcessor::Type::ASYMMETRIC_SOFT)
        .value("VINYL_TAPE",     SaturationProcessor::Type::VINYL_TAPE)
        .value("WAVESHAPER",     SaturationProcessor::Type::WAVESHAPER)
        .export_values();

    py::class_<SaturationProcessor>(m, "SaturationProcessor",
        "Saturation / drive processor with built-in per-sample parameter smoothing.\n\n"
        "Drive changes applied via set_drive() are smoothed over smoothing_ms\n"
        "milliseconds so no click is produced even during live automation.\n\n"
        "Audio buffers are numpy.ndarray[float32, ndim=1] — zero-copy handoff.")

        .def(py::init<int, float>(),
             py::arg("sample_rate")  = 48'000,
             py::arg("smoothing_ms") = 5.0f,
             "Construct a SaturationProcessor.\n\n"
             "Args:\n"
             "    sample_rate:  Audio sample rate in Hz (default 48000).\n"
             "    smoothing_ms: Drive-change smoothing window in ms (default 5.0).")

        .def("set_type",
             &SaturationProcessor::set_type,
             py::arg("type"),
             "Select the saturation algorithm via SaturationType enum.")

        .def("set_type_from_string",
             &SaturationProcessor::set_type_from_string,
             py::arg("name"),
             "Select saturation algorithm by name string.\n\n"
             "Accepted: 'none','tape_soft','tube_tanh','hard_clip',\n"
             "'asymmetric_soft','vinyl_tape','waveshaper'.")

        .def("set_drive",
             &SaturationProcessor::set_drive,
             py::arg("drive_pct"),
             "Set target drive level (0.0–100.0 %).\n\n"
             "The change is smoothed internally — no click on rapid calls.")

        .def("process",
             &SaturationProcessor::process,
             py::arg("input"),
             "Process one block of audio samples.\n\n"
             "Args:\n"
             "    input: numpy.ndarray[float32, ndim=1]  (read-only).\n\n"
             "Returns:\n"
             "    numpy.ndarray[float32, ndim=1] — processed block.")

        .def_property_readonly("sample_rate", &SaturationProcessor::sample_rate,
             "Sample rate this processor was constructed with.")

        .def_property_readonly("current_drive", &SaturationProcessor::current_drive,
             "Current smoothed drive value in percent (not the target).");
}
