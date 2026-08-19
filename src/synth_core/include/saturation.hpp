/**
 * @file saturation.hpp
 * @brief Saturation / drive processor with built-in per-sample parameter smoothing.
 *
 * Provides six saturation curves commonly used in music production:
 *
 *  TAPE_SOFT      — Asymmetric tanh with second-harmonic bias, emulates tape
 *                   compression.  Drive 2–10 % adds warmth without harshness.
 *
 *  TUBE_TANH      — Symmetric tanh curve, emulates triode tube saturation.
 *                   Progressively softer clipping as drive increases.
 *
 *  HARD_CLIP      — Digital hard clipper: linear passthrough below threshold,
 *                   flat above it.  Produces aggressive, odd harmonics.
 *
 *  ASYMMETRIC_SOFT — Positive and negative half-cycles clip at different
 *                   thresholds, producing even harmonics (808 character).
 *
 *  VINYL_TAPE     — Combines TAPE_SOFT with a first-order low-pass (12 kHz)
 *                   to emulate vinyl bandwidth limiting.
 *
 *  WAVESHAPER     — Cubic polynomial transfer function; smoother than tanh
 *                   at moderate drives.
 *
 * Parameter smoothing (de-clicking)
 * -----------------------------------
 * The drive parameter is smoothed internally via a one-pole IIR low-pass
 * filter before each sample is processed.  Changing set_drive() therefore
 * never causes an audible click: the new value is reached after
 * ~smoothing_ms milliseconds.  This satisfies the design constraint that
 * "parameter values in C++ must always be interpolated over a few milliseconds".
 *
 * Cross-platform: standard C++17 only, no POSIX or Windows APIs.
 */

#pragma once

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <string>

namespace py = pybind11;


class SaturationProcessor {
public:
    /** Saturation algorithm identifier. */
    enum class Type {
        NONE,
        TAPE_SOFT,
        TUBE_TANH,
        HARD_CLIP,
        ASYMMETRIC_SOFT,
        VINYL_TAPE,
        WAVESHAPER
    };

    /**
     * Construct a SaturationProcessor.
     *
     * @param sample_rate   Audio sample rate in Hz (default 48 000).
     * @param smoothing_ms  Parameter-change smoothing window in milliseconds.
     *                      Drives the one-pole IIR coefficient used for
     *                      de-clicking when set_drive() is called mid-stream.
     */
    explicit SaturationProcessor(int   sample_rate  = 48'000,
                                  float smoothing_ms = 5.0f);

    // ── Configuration ─────────────────────────────────────────────────────────

    /**
     * Select the saturation algorithm.
     *
     * Can be called between process() blocks without producing a click because
     * the drive envelope transitions continuously.
     */
    void set_type(Type type) noexcept { type_ = type; }

    /**
     * Convenience setter: parse type from a string name.
     *
     * Accepted values (case-insensitive): "none", "tape_soft", "tube_tanh",
     * "hard_clip", "asymmetric_soft", "vinyl_tape", "waveshaper".
     * Unknown names silently fall back to NONE.
     */
    void set_type_from_string(const std::string& name) noexcept;

    /**
     * Set the target drive level (0.0 – 100.0 %).
     *
     * The change is applied gradually via the internal smoother so no click
     * is produced even if set_drive() is called every block.
     *
     * @param drive_pct  Drive amount in percent.  0 = unity gain, no saturation.
     *                   100 = maximum saturation per curve.
     */
    void set_drive(float drive_pct) noexcept;

    /** Return the current (smoothed, not target) drive percent. */
    float current_drive() const noexcept { return drive_current_; }

    // ── Processing ────────────────────────────────────────────────────────────

    /**
     * Process one block of audio samples.
     *
     * Accepts and returns a 1-D numpy float32 array.  Processing is in-place
     * on a fresh output buffer (input is not modified).
     *
     * The drive smoother runs sample-by-sample inside this call so parameter
     * automation is artefact-free.
     *
     * @param input  C-contiguous numpy.ndarray[float32, ndim=1].
     * @return       Processed numpy.ndarray[float32, ndim=1] of the same length.
     */
    py::array_t<float> process(py::array_t<float> input);

    // ── Utility ──────────────────────────────────────────────────────────────

    int  sample_rate()  const noexcept { return sample_rate_; }
    Type type()         const noexcept { return type_; }

private:
    // ── Scalar per-sample processor (called inside process()) ─────────────────

    /**
     * Apply the selected saturation curve to a single sample.
     *
     * @param x      Input sample (should be in approximately [-1, +1]).
     * @param drive  Current smoothed drive, normalised to [0, 1].
     * @return       Saturated output sample.
     */
    float process_sample(float x, float drive) const noexcept;

    float tape_soft_sample      (float x, float drive) const noexcept;
    float tube_tanh_sample      (float x, float drive) const noexcept;
    float hard_clip_sample      (float x, float drive) const noexcept;
    float asymmetric_soft_sample(float x, float drive) const noexcept;
    float waveshaper_sample     (float x, float drive) const noexcept;

    // ── One-pole IIR smoother ─────────────────────────────────────────────────

    /**
     * Step the drive smoother by one sample.
     *
     * drive_current_ is the actual drive used for this sample.
     * drive_target_  is the destination requested by set_drive().
     *
     * Coefficient formula:
     *   coeff = exp(-2π × cutoff_hz / sample_rate)
     * where cutoff_hz corresponds to the desired smoothing time.
     */
    inline void advance_smoother() noexcept {
        drive_current_ += smoother_coeff_ * (drive_target_ - drive_current_);
    }

    // ── Member data ───────────────────────────────────────────────────────────

    int   sample_rate_;
    Type  type_           { Type::NONE };

    float drive_target_   { 0.0f };   // requested drive (0–1 normalised)
    float drive_current_  { 0.0f };   // smoothed drive  (0–1 normalised)
    float smoother_coeff_ { 0.0f };   // IIR coefficient, computed in constructor

    // State for VINYL_TAPE first-order low-pass (12 kHz cutoff).
    float lp_state_       { 0.0f };
    float lp_coeff_       { 0.0f };
};
