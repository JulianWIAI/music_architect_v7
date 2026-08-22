/**
 * @file sidechain.cpp
 * @brief SidechainFollower implementation.
 *
 * IIR coefficient derivation
 * ---------------------------
 * Standard one-pole low-pass in the form:
 *   y[n] = y[n-1] + coeff * (target - y[n-1])
 *
 * The coefficient that makes y reach target in ~T seconds is:
 *   coeff = 1 - exp(-1 / (T_seconds * sample_rate))
 *
 * At coeff → 1.0  the filter converges instantly (0 ms).
 * At coeff → 0.0  the filter is infinitely slow (oo ms).
 *
 * For the attack path we ramp envelope TOWARD 1.0.
 * For the release path we ramp envelope TOWARD 0.0.
 * These two coefficients are independent so they can have very different times.
 */

#include "sidechain.hpp"

#include <algorithm>   // std::sort
#include <cmath>       // std::exp, std::max


// ── Constructor ───────────────────────────────────────────────────────────────

SidechainFollower::SidechainFollower(
    int   sample_rate,
    float attack_ms,
    float release_ms,
    float depth
)
    : sample_rate_(sample_rate)
    , depth_(depth)
{
    const float eps = 1e-6f;   // guard against log(0) for 0 ms times

    // Attack coefficient — for near-instant attack set attack_ms ≈ 0.
    const float attack_s  = std::max(attack_ms,  eps) / 1000.0f;
    attack_coeff_  = (attack_ms < eps)
        ? 1.0f   // instant: envelope jumps to 1 in one sample
        : (1.0f - std::exp(-1.0f / (attack_s * static_cast<float>(sample_rate))));

    // Release coefficient.
    const float release_s = std::max(release_ms, eps) / 1000.0f;
    release_coeff_ = 1.0f - std::exp(-1.0f / (release_s * static_cast<float>(sample_rate)));
}


// ── set_triggers ──────────────────────────────────────────────────────────────

void SidechainFollower::set_triggers(const std::vector<int>& trigger_samples) {
    triggers_        = trigger_samples;
    std::sort(triggers_.begin(), triggers_.end());
    trigger_cursor_  = 0;     // restart iteration from the beginning of the song
    envelope_        = 0.0f;  // reset envelope so first block starts clean
}


// ── set_release_ms ────────────────────────────────────────────────────────────

void SidechainFollower::set_release_ms(float release_ms) noexcept {
    const float release_s = std::max(release_ms, 1e-6f) / 1000.0f;
    release_coeff_ = 1.0f - std::exp(
        -1.0f / (release_s * static_cast<float>(sample_rate_)));
}


// ── process ───────────────────────────────────────────────────────────────────

py::array_t<float> SidechainFollower::process(
    py::array_t<float> input,
    int                sample_offset
) {
    // Zero-copy read access to the numpy input buffer.
    py::buffer_info in_buf = input.request();
    const float* in_ptr    = static_cast<const float*>(in_buf.ptr);
    const int    n         = static_cast<int>(in_buf.size);

    // Allocate a fresh output buffer — same size as input.
    py::array_t<float> output(n);
    py::buffer_info    out_buf = output.request();
    float*             out_ptr = static_cast<float*>(out_buf.ptr);

    // Fast-forward trigger_cursor_ past any triggers that ended before this block.
    // This avoids rescanning from the beginning on every process() call so the
    // overall algorithm stays O(total_triggers + total_samples), not O(N * T).
    const int block_end = sample_offset + n;
    while (trigger_cursor_ < static_cast<int>(triggers_.size()) &&
           triggers_[trigger_cursor_] < sample_offset) {
        ++trigger_cursor_;
    }

    // Local copy of cursor so we can advance it without touching the member
    // until the end of the block (re-entrant-safe).
    int local_cursor = trigger_cursor_;

    for (int i = 0; i < n; ++i) {
        const int abs_sample = sample_offset + i;

        // Fire all triggers that land on this sample (multiple simultaneous
        // triggers are rare but handled correctly by taking the highest).
        while (local_cursor < static_cast<int>(triggers_.size()) &&
               triggers_[local_cursor] == abs_sample) {
            // Attack: ramp envelope toward 1.0.
            // With attack_coeff_ ≈ 1.0 this is effectively instantaneous.
            envelope_ += attack_coeff_ * (1.0f - envelope_);
            ++local_cursor;
        }

        // Release: exponential decay toward 0.
        // Runs every sample regardless of triggers so the pump tails off smoothly.
        envelope_ -= release_coeff_ * envelope_;

        // Clamp to [0, 1] to prevent floating-point drift from accumulating.
        if (envelope_ < 0.0f) envelope_ = 0.0f;
        if (envelope_ > 1.0f) envelope_ = 1.0f;

        // Apply gain: gain = 1 - depth * envelope.
        // At envelope=1 → gain = (1-depth); at envelope=0 → gain = 1.
        out_ptr[i] = in_ptr[i] * (1.0f - depth_ * envelope_);
    }

    // Persist cursor so the next process() call resumes from where we stopped.
    trigger_cursor_ = local_cursor;

    return output;
}
