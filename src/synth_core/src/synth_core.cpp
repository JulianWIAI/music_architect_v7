/**
 * @file synth_core.cpp
 * @brief SynthCore implementation — note synthesis and drum dispatch.
 *
 * This file contains the two inner synthesis loops that replace the Python
 * hot-path in builtin_synthesizer.py:
 *
 *   synthesize_note()  — per-sample additive harmonic synthesis + ADSR
 *   synthesize_drum()  — delegates to DrumSynthesizer, applies velocity
 *
 * Both methods return a pybind11 Python tuple:
 *   (start_sample_index: int, samples: numpy.ndarray[float32])
 *
 * The numpy array is created directly in C++ (no extra copy) via
 * py::array_t<float> and filled through an unchecked accessor.
 *
 * Performance
 * -----------
 * The innermost loop in synthesize_note() computes, per sample:
 *   • ADSREnvelope::get_amplitude() — 4–7 comparisons, 2 multiplies
 *   • N harmonic oscillator evaluations — N = 2–5 for most timbres
 * At 44 100 Hz and N=4, a one-second note executes ~176 400 iterations.
 * In Python this takes ~150 ms; in C++ (O3) it takes ~1–3 ms (50–100×).
 */

#include "synth_core.hpp"
#include "adsr_envelope.hpp"
#include "instrument_timbres.hpp"
#include "oscillator.hpp"

#include <cmath>   // std::pow, std::abs

// ── Constants ────────────────────────────────────────────────────────────────

// A4 (MIDI note 69) = 440 Hz; standard equal-temperament tuning
static constexpr double kA4Freq   = 440.0;
static constexpr double kA4Note   = 69.0;
// Per-note scaling factor applied after harmonic normalisation (matches Python)
static constexpr double kNoteGain = 0.4;

// ── Constructor ──────────────────────────────────────────────────────────────

SynthCore::SynthCore(int sample_rate)
    : sample_rate_(sample_rate),
      drums_(sample_rate)   // DrumSynthesizer shares the same sample rate
{}

// ── midi_to_freq ─────────────────────────────────────────────────────────────

double SynthCore::midi_to_freq(int midi_note) noexcept {
    // Equal-temperament: f = 440 * 2^((note − 69) / 12)
    return kA4Freq * std::pow(2.0, (midi_note - kA4Note) / 12.0);
}

// ── synthesize_note ───────────────────────────────────────────────────────────

py::tuple SynthCore::synthesize_note(int    midi_note,
                                     double start_time,
                                     double duration,
                                     double velocity,
                                     int    program) const {
    /**
     * Additive harmonic synthesis with ADSR envelope.
     *
     * Exact port of BuiltinSynthesizer.synthesize_note():
     *
     *   for i in range(n_samples):
     *       t   = i / sample_rate
     *       amp = envelope.get_amplitude(t, duration) * vel_scale
     *       s   = sum( oscillator(freq*(h+1), t) * harmonics[h]
     *                  for h, h_amp in enumerate(harmonics)
     *                  if freq*(h+1) <= sample_rate/2 )
     *       samples.append(s / harmonic_sum * amp * 0.4)
     */

    // Look up instrument timbre (O(1) hash map lookup)
    const Timbre& timbre = get_timbre(program);

    // Fundamental frequency for this MIDI note
    const double freq = midi_to_freq(midi_note);

    // Total sample count includes release tail
    const double total_dur  = duration + timbre.release;
    const size_t n_samples  = static_cast<size_t>(total_dur * sample_rate_);
    const int    start_idx  = static_cast<int>(start_time * sample_rate_);

    // Velocity-to-amplitude scale [0, 1]
    const double vel_scale = velocity / 127.0;

    // Nyquist limit — harmonics above this are skipped to prevent aliasing
    const double nyquist = static_cast<double>(sample_rate_) * 0.5;

    // Precompute: how many harmonics are below Nyquist? (avoids checking each sample)
    const size_t n_harmonics = timbre.harmonics.size();
    size_t valid_harmonics = 0;
    for (size_t h = 0; h < n_harmonics; ++h) {
        if (freq * static_cast<double>(h + 1) <= nyquist) {
            ++valid_harmonics;
        } else {
            break;  // harmonics are in ascending frequency order
        }
    }

    // Inline ADSR parameters (avoids ADSREnvelope object overhead per sample)
    const double A = timbre.attack;
    const double D = timbre.decay;
    const double S = timbre.sustain;
    const double R = timbre.release;

    const OscillatorType osc_type = timbre.osc_type;
    const double harmonic_sum     = timbre.harmonic_sum;
    const double inv_sr           = 1.0 / static_cast<double>(sample_rate_);
    const double gain             = kNoteGain / harmonic_sum * vel_scale;

    // Allocate output numpy array (float32, 1-D, C-contiguous)
    py::array_t<float> result(static_cast<py::ssize_t>(n_samples));
    auto buf = result.mutable_unchecked<1>();  // direct pointer, no bounds check overhead

    for (size_t i = 0; i < n_samples; ++i) {
        const double t = static_cast<double>(i) * inv_sr;

        // ── Inline ADSR ───────────────────────────────────────────────────────
        double amp;
        if (t < A) {
            amp = (A > 0.0) ? t / A : 1.0;
        } else {
            const double t2 = t - A;
            if (t2 < D) {
                amp = 1.0 - (1.0 - S) * (t2 / D);
            } else if (t < duration) {
                amp = S;
            } else {
                const double t3 = t - duration;
                amp = (t3 < R) ? S * (1.0 - t3 / R) : 0.0;
            }
        }

        // ── Additive harmonic sum ─────────────────────────────────────────────
        double sample = 0.0;
        for (size_t h = 0; h < valid_harmonics; ++h) {
            sample += oscillate(freq * static_cast<double>(h + 1), t, osc_type)
                      * timbre.harmonics[h];
        }

        // Normalise, apply ADSR amplitude and velocity, write to output array
        buf(static_cast<py::ssize_t>(i)) = static_cast<float>(sample * amp * gain);
    }

    // Return as Python tuple (start_sample_index, numpy_array)
    return py::make_tuple(start_idx, result);
}

// ── synthesize_drum ───────────────────────────────────────────────────────────

py::tuple SynthCore::synthesize_drum(int midi_note, double start_time, double velocity) {
    /**
     * Retrieve the cached drum sample and apply velocity scaling.
     *
     * Port of BuiltinSynthesizer.synthesize_drum():
     *   raw = self.drum_cache[midi_note]
     *   return start_idx, [s * vel_scale for s in raw]
     */
    const double vel_scale = velocity / 127.0;
    const int    start_idx = static_cast<int>(start_time * sample_rate_);

    // Get the pre-generated (and cached) sample buffer for this drum note
    const std::vector<float>& raw = drums_.get_sample(midi_note);
    const size_t n = raw.size();

    // Allocate output numpy array and fill with velocity-scaled values
    py::array_t<float> result(static_cast<py::ssize_t>(n));
    auto buf = result.mutable_unchecked<1>();

    const float fvel = static_cast<float>(vel_scale);
    for (size_t i = 0; i < n; ++i) {
        buf(static_cast<py::ssize_t>(i)) = raw[i] * fvel;
    }

    return py::make_tuple(start_idx, result);
}
