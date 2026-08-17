/**
 * @file drum_synthesizer.cpp
 * @brief Percussion sample generation and caching.
 *
 * Ported from src/rendering/instrument_timbres.py:
 *   generate_kick_sample(), generate_snare_sample(),
 *   generate_hihat_sample(), generate_crash_sample()
 *
 * and from src/rendering/builtin_synthesizer.py (drum_cache + synthesize_drum).
 *
 * Implementation notes
 * --------------------
 * - All synthesis is done with C doubles then stored as float to match the
 *   Python original (which uses math.sin / math.exp returning Python floats
 *   that are 64-bit under the hood).
 * - Noise is generated with std::uniform_real_distribution<double>(-1.0, 1.0)
 *   which matches Python's (random.random() * 2 - 1).
 * - The kick uses freq*t (not phase accumulation) to match Python exactly.
 * - Sample values are scaled to match the Python amplitude constants (0.8,
 *   0.7, 0.4, 0.35) without modification.
 */

#include "drum_synthesizer.hpp"
#include <cmath>   // std::exp, std::sin, std::abs

// ── Constants ────────────────────────────────────────────────────────────────

static constexpr double kPi  = 3.14159265358979323846;
static constexpr double k2Pi = 2.0 * kPi;

// ── Constructor ──────────────────────────────────────────────────────────────

DrumSynthesizer::DrumSynthesizer(int sample_rate, unsigned int rng_seed) noexcept
    : sample_rate_(sample_rate),
      rng_(rng_seed),
      dist_(-1.0, 1.0)  // uniform [−1, +1]
{}

// ── Public: get_sample ────────────────────────────────────────────────────────

const std::vector<float>& DrumSynthesizer::get_sample(int midi_note) {
    // Cache hit — return existing buffer
    auto it = cache_.find(midi_note);
    if (it != cache_.end()) {
        return it->second;
    }
    // Cache miss — generate and insert
    generate_and_cache(midi_note);
    return cache_.at(midi_note);
}

// ── Private: generate_and_cache ───────────────────────────────────────────────

void DrumSynthesizer::generate_and_cache(int midi_note) {
    // Mirror of BuiltinSynthesizer.synthesize_drum() note→generator mapping

    std::vector<float> buf;

    if (midi_note == 36) {
        // GM 36: Bass Drum 1 (kick)
        buf = generate_kick(0.3);

    } else if (midi_note == 38 || midi_note == 37 ||
               midi_note == 39 || midi_note == 40) {
        // GM 38: Snare, 37: Side Stick, 39: Hand Clap, 40: Electric Snare
        buf = generate_snare(0.2);

    } else if (midi_note == 42 || midi_note == 44) {
        // GM 42: Closed Hi-Hat, 44: Pedal Hi-Hat
        buf = generate_hihat(0.08, /*is_open=*/false);

    } else if (midi_note == 46) {
        // GM 46: Open Hi-Hat
        buf = generate_hihat(0.3, /*is_open=*/true);

    } else if (midi_note == 49) {
        // GM 49: Crash Cymbal 1
        buf = generate_crash(1.0);

    } else if (midi_note == 51) {
        // GM 51: Ride Cymbal 1 — open hi-hat with 0.15 s duration
        buf = generate_hihat(0.15, /*is_open=*/true);

    } else if (midi_note == 45 || midi_note == 47 || midi_note == 50) {
        // GM 45: Low Tom, 47: Mid Tom, 50: High Tom — short kick variant
        buf = generate_kick(0.15);

    } else {
        // All other drum notes → short snare
        buf = generate_snare(0.1);
    }

    cache_.emplace(midi_note, std::move(buf));
}

// ── Private: sample generators ────────────────────────────────────────────────

std::vector<float> DrumSynthesizer::generate_kick(double duration) {
    /**
     * Pitch-swept sine (40–150 Hz) with exponential amplitude decay.
     *
     * Python original (instrument_timbres.py):
     *   freq = 40 + 110 * exp(−t * 30)
     *   amp  = exp(−t * 8)
     *   s    = sin(2π·freq·t) · amp
     *   transient click added for t < 0.005 s
     */
    const int n = static_cast<int>(sample_rate_ * duration);
    std::vector<float> out;
    out.reserve(static_cast<size_t>(n));

    const double inv_sr = 1.0 / sample_rate_;

    for (int i = 0; i < n; ++i) {
        const double t    = i * inv_sr;
        const double freq = 40.0 + 110.0 * std::exp(-t * 30.0);  // frequency sweep
        const double amp  = std::exp(-t * 8.0);                   // amplitude decay
        double s = std::sin(k2Pi * freq * t) * amp;

        // Transient click at onset (matches Python: if t < 0.005 add a blip)
        if (t < 0.005) {
            s += (0.005 - t) / 0.005 * 0.5;
        }

        out.push_back(static_cast<float>(s * 0.8));
    }
    return out;
}

std::vector<float> DrumSynthesizer::generate_snare(double duration) {
    /**
     * Decaying 180 Hz sine tone mixed with broadband noise.
     *
     * Python original:
     *   tone  = sin(2π·180·t) · exp(−t·20)
     *   noise = (random()*2−1)  · exp(−t·12)
     *   s     = (tone·0.4 + noise·0.6) · 0.7
     */
    const int n = static_cast<int>(sample_rate_ * duration);
    std::vector<float> out;
    out.reserve(static_cast<size_t>(n));

    const double inv_sr = 1.0 / sample_rate_;

    for (int i = 0; i < n; ++i) {
        const double t     = i * inv_sr;
        const double tone  = std::sin(k2Pi * 180.0 * t) * std::exp(-t * 20.0);
        const double noise = dist_(rng_) * std::exp(-t * 12.0);
        out.push_back(static_cast<float>((tone * 0.4 + noise * 0.6) * 0.7));
    }
    return out;
}

std::vector<float> DrumSynthesizer::generate_hihat(double duration, bool is_open) {
    /**
     * High-passed noise with fast (closed) or slow (open) decay.
     *
     * Python original:
     *   dur   = 0.3 if is_open else duration
     *   decay = 5   if is_open else 25
     *   noise = (random()*2−1) · exp(−t·decay)
     *   hp    = noise · (0.8 + 0.2·sin(2π·8000·t))
     *   s     = hp · 0.4
     */
    const double dur   = is_open ? 0.3 : duration;
    const double decay = is_open ? 5.0 : 25.0;

    const int n = static_cast<int>(sample_rate_ * dur);
    std::vector<float> out;
    out.reserve(static_cast<size_t>(n));

    const double inv_sr = 1.0 / sample_rate_;

    for (int i = 0; i < n; ++i) {
        const double t     = i * inv_sr;
        const double noise = dist_(rng_) * std::exp(-t * decay);
        // Simple high-emphasis by amplitude-modulating noise with an 8 kHz partial
        const double hp    = noise * (0.8 + 0.2 * std::sin(k2Pi * 8000.0 * t));
        out.push_back(static_cast<float>(hp * 0.4));
    }
    return out;
}

std::vector<float> DrumSynthesizer::generate_crash(double duration) {
    /**
     * Slow-decaying noise cymbal with a 3 kHz spectral partial.
     *
     * Python original:
     *   noise = (random()*2−1) · exp(−t·3)
     *   tone  = sin(2π·3000·t) · exp(−t·5) · 0.2
     *   s     = (noise·0.7 + tone) · 0.35
     */
    const int n = static_cast<int>(sample_rate_ * duration);
    std::vector<float> out;
    out.reserve(static_cast<size_t>(n));

    const double inv_sr = 1.0 / sample_rate_;

    for (int i = 0; i < n; ++i) {
        const double t     = i * inv_sr;
        const double noise = dist_(rng_) * std::exp(-t * 3.0);
        const double tone  = std::sin(k2Pi * 3000.0 * t) * std::exp(-t * 5.0) * 0.2;
        out.push_back(static_cast<float>((noise * 0.7 + tone) * 0.35));
    }
    return out;
}
