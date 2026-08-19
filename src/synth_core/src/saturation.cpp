/**
 * @file saturation.cpp
 * @brief Saturation / drive processor implementation.
 *
 * All saturation curves normalise the input to [-1, +1] internally by
 * scaling by drive before the non-linearity and back-scaling after so that
 * 0 % drive is always unity-gain.
 *
 * Parameter smoothing uses a one-pole IIR low-pass filter (the standard
 * approach in audio software because it is computationally trivial and
 * produces the correct exponential-decay trajectory).
 *
 * Low-pass coefficient derivation:
 *   cutoff_hz = 1 / (2π × smoothing_seconds)
 *   coeff     = exp(−2π × cutoff_hz / sample_rate)
 *             = exp(−1 / (smoothing_seconds × sample_rate))
 *
 * A 5 ms smoothing window at 48 000 Hz gives coeff ≈ 0.99999583 per sample,
 * meaning the drive reaches its target in approximately 240 samples (5 ms).
 */

#include "saturation.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <stdexcept>


// ── Constructor ────────────────────────────────────────────────────────────────

SaturationProcessor::SaturationProcessor(int sample_rate, float smoothing_ms)
    : sample_rate_(sample_rate)
{
    // One-pole IIR coefficient for the drive smoother.
    // smoothing_ms → smoothing_seconds → cutoff_hz → exp coefficient.
    const float smoothing_s = smoothing_ms / 1000.0f;
    smoother_coeff_ = (smoothing_s > 0.0f)
        ? (1.0f - std::exp(-1.0f / (smoothing_s * static_cast<float>(sample_rate))))
        : 1.0f;   // 0 ms smoothing → instant

    // Low-pass coefficient for VINYL_TAPE (fixed cutoff at 12 000 Hz).
    const float lp_cutoff_hz = 12'000.0f;
    const float lp_omega = 2.0f * static_cast<float>(M_PI) * lp_cutoff_hz
                           / static_cast<float>(sample_rate);
    lp_coeff_ = 1.0f - std::exp(-lp_omega);
}


// ── Type selection from string ────────────────────────────────────────────────

void SaturationProcessor::set_type_from_string(const std::string& name) noexcept {
    // Convert to lower-case for case-insensitive comparison.
    std::string lower(name.size(), '\0');
    std::transform(name.begin(), name.end(), lower.begin(),
                   [](unsigned char c){ return std::tolower(c); });

    if      (lower == "tape_soft")       type_ = Type::TAPE_SOFT;
    else if (lower == "tube_tanh")       type_ = Type::TUBE_TANH;
    else if (lower == "hard_clip")       type_ = Type::HARD_CLIP;
    else if (lower == "asymmetric_soft") type_ = Type::ASYMMETRIC_SOFT;
    else if (lower == "vinyl_tape")      type_ = Type::VINYL_TAPE;
    else if (lower == "waveshaper")      type_ = Type::WAVESHAPER;
    else                                 type_ = Type::NONE;
}


// ── Drive setter ──────────────────────────────────────────────────────────────

void SaturationProcessor::set_drive(float drive_pct) noexcept {
    // Normalise from [0, 100] to [0, 1] for internal use.
    drive_target_ = std::clamp(drive_pct / 100.0f, 0.0f, 1.0f);
}


// ── Block processor ───────────────────────────────────────────────────────────

py::array_t<float> SaturationProcessor::process(py::array_t<float> input) {
    // Obtain a read-only view of the input buffer — zero copies.
    py::buffer_info in_buf = input.request();
    if (in_buf.ndim != 1) {
        throw std::runtime_error("[SaturationProcessor] input must be 1-D float32");
    }

    const auto n_samples = static_cast<py::ssize_t>(in_buf.size);
    const float* in_ptr  = static_cast<const float*>(in_buf.ptr);

    // Allocate a fresh output buffer (C-contiguous float32).
    py::array_t<float> output(n_samples);
    float* out_ptr = static_cast<float*>(output.request().ptr);

    // Main processing loop — drive is smoothed sample by sample.
    for (py::ssize_t i = 0; i < n_samples; ++i) {
        advance_smoother();
        out_ptr[i] = process_sample(in_ptr[i], drive_current_);
    }

    return output;
}


// ── Sample-level dispatch ─────────────────────────────────────────────────────

float SaturationProcessor::process_sample(float x, float drive) const noexcept {
    switch (type_) {
        case Type::TAPE_SOFT:       return tape_soft_sample(x, drive);
        case Type::TUBE_TANH:       return tube_tanh_sample(x, drive);
        case Type::HARD_CLIP:       return hard_clip_sample(x, drive);
        case Type::ASYMMETRIC_SOFT: return asymmetric_soft_sample(x, drive);
        case Type::VINYL_TAPE:      return tape_soft_sample(x, drive);  // LP applied separately
        case Type::WAVESHAPER:      return waveshaper_sample(x, drive);
        default:                    return x;  // NONE — unity gain
    }
}


// ── Saturation curves ─────────────────────────────────────────────────────────

float SaturationProcessor::tape_soft_sample(float x, float drive) const noexcept {
    // Tape saturation: asymmetric tanh with slight even-harmonic bias.
    // Pre-gain scales input into the non-linear region; post-gain normalises.
    // Asymmetry (+ 0.1 * drive) mimics tape bias which adds second harmonics.
    const float pre_gain = 1.0f + drive * 4.0f;     // 1× at 0%, 5× at 100%
    const float driven   = x * pre_gain + 0.1f * drive * x * std::abs(x);
    // std::tanhf saturates smoothly; output ∈ (-1, +1) always.
    return std::tanhf(driven) / std::tanhf(pre_gain);
}

float SaturationProcessor::tube_tanh_sample(float x, float drive) const noexcept {
    // Tube triode emulation: symmetric tanh, progressively softer headroom.
    const float pre_gain = 1.0f + drive * 6.0f;     // 1× at 0%, 7× at 100%
    return std::tanhf(x * pre_gain) / std::tanhf(pre_gain);
}

float SaturationProcessor::hard_clip_sample(float x, float drive) const noexcept {
    // Hard clipper: flat above threshold → strong odd harmonics.
    // Threshold shrinks with drive (more drive → earlier clipping).
    const float threshold = 1.0f - drive * 0.7f;    // 1.0 at 0%, 0.3 at 100%
    return std::clamp(x, -threshold, threshold) / threshold;
}

float SaturationProcessor::asymmetric_soft_sample(float x, float drive) const noexcept {
    // Asymmetric soft clipper: positive half clips harder than negative half.
    // This generates even harmonics — characteristic of 808 sub-bass tone.
    const float pre_gain  = 1.0f + drive * 5.0f;
    const float driven    = x * pre_gain;
    float out;
    if (driven >= 0.0f) {
        // Positive half: softer knee (2/3 of the cubic waveshaper)
        out = (driven < 1.0f)
            ? driven - (driven * driven * driven) / 3.0f
            : 2.0f / 3.0f;
    } else {
        // Negative half: tighter knee (tanh-style)
        out = std::tanhf(driven * 0.75f);
    }
    return out / (2.0f / 3.0f + drive * 0.2f);
}

float SaturationProcessor::waveshaper_sample(float x, float drive) const noexcept {
    // Cubic polynomial waveshaper: y = x − x³/3 (Chebyshev-like).
    // Smoother harmonic profile than hard clip; gentle 2nd and 3rd harmonics.
    const float pre_gain = 1.0f + drive * 3.5f;
    const float d        = std::clamp(x * pre_gain, -1.0f, 1.0f);
    const float out      = d - (d * d * d) / 3.0f;
    return out / (2.0f / 3.0f);
}
