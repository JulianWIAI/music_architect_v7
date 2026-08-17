/**
 * @file adsr_envelope.cpp
 * @brief ADSREnvelope implementation.
 *
 * Exact port of src/rendering/adsr_envelope.py — all branch conditions and
 * arithmetic are identical to the Python original so that rendered audio is
 * bit-for-bit compatible between the C++ and Python paths.
 */

#include "adsr_envelope.hpp"

// ── Constructor ──────────────────────────────────────────────────────────────

ADSREnvelope::ADSREnvelope(double attack, double decay,
                           double sustain, double release) noexcept
    : attack_(attack), decay_(decay), sustain_(sustain), release_(release)
{}

// ── get_amplitude ─────────────────────────────────────────────────────────────

double ADSREnvelope::get_amplitude(double t, double duration) const noexcept {
    // Mirror of adsr_envelope.py::get_amplitude()

    if (t < 0.0) {
        // Before note-on
        return 0.0;
    }

    if (t < attack_) {
        // Attack phase: linear ramp from 0 to 1
        return t / attack_;
    }

    // Time since end of attack
    const double t2 = t - attack_;
    if (t2 < decay_) {
        // Decay phase: linear fall from 1 to sustain_
        return 1.0 - (1.0 - sustain_) * (t2 / decay_);
    }

    if (t < duration) {
        // Sustain phase: constant amplitude while note is held
        return sustain_;
    }

    // Time since note-off
    const double t3 = t - duration;
    if (t3 < release_) {
        // Release phase: linear fade from sustain_ to 0
        return sustain_ * (1.0 - t3 / release_);
    }

    // After full release: silence
    return 0.0;
}
