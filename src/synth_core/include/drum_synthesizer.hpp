/**
 * @file drum_synthesizer.hpp
 * @brief Percussion sample synthesizer with per-note caching.
 *
 * Ported from the generate_*_sample() functions in
 * src/rendering/instrument_timbres.py and the drum_cache dict in
 * src/rendering/builtin_synthesizer.py.
 *
 * Each GM drum note number is synthesized on first access and stored in an
 * internal cache.  Subsequent hits for the same note re-use the cached buffer.
 * This matches the Python behaviour exactly.
 *
 * Cross-platform notes
 * --------------------
 * The random noise generator uses std::mt19937 seeded at construction so that
 * the drum sounds are deterministic across platforms (unlike Python's random
 * module which can differ between interpreter versions).
 */

#pragma once

#include <unordered_map>
#include <vector>
#include <random>

class DrumSynthesizer {
public:
    /**
     * Construct a DrumSynthesizer.
     *
     * @param sample_rate  Audio sample rate in Hz (default 44 100).
     * @param rng_seed     Seed for the noise RNG.  Fixed default ensures
     *                     reproducible drum sounds across platforms.
     */
    explicit DrumSynthesizer(int sample_rate = 44100,
                             unsigned int rng_seed = 42) noexcept;

    /**
     * Return a const reference to the cached raw sample buffer for
     * @p midi_note.  Generates and caches the buffer on first access.
     *
     * The buffer is normalised to the range [−1, +1] before caching.
     * Velocity scaling is applied by the caller (SynthCore::synthesize_drum).
     */
    const std::vector<float>& get_sample(int midi_note);

private:
    int sample_rate_;

    // Mersenne-Twister RNG used for all noise-based percussion
    std::mt19937 rng_;
    std::uniform_real_distribution<double> dist_; // uniform [−1, +1]

    // midi_note → pre-generated sample buffer
    std::unordered_map<int, std::vector<float>> cache_;

    // ── Sample generators — direct ports of instrument_timbres.py ──────────

    /** Kick: pitch-swept sine (40–150 Hz) with exponential amplitude decay. */
    std::vector<float> generate_kick(double duration = 0.3);

    /** Snare: decaying 180 Hz tone mixed with bandpass noise. */
    std::vector<float> generate_snare(double duration = 0.2);

    /**
     * Hi-hat: high-passed noise.
     * @param is_open  True → slower decay (open hi-hat); False → fast (closed).
     */
    std::vector<float> generate_hihat(double duration = 0.08,
                                      bool   is_open  = false);

    /** Crash cymbal: slow-decaying noise with a 3 kHz spectral partial. */
    std::vector<float> generate_crash(double duration = 1.0);

    /** Select the right generator for @p midi_note, generate, and cache. */
    void generate_and_cache(int midi_note);
};
