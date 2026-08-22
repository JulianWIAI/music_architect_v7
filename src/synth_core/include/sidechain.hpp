/**
 * @file sidechain.hpp
 * @brief Sidechain envelope follower for kick/808-triggered gain reduction.
 *
 * SidechainFollower implements genre-typical sidechain compression using
 * pre-scheduled trigger points derived from MIDI kick event times.  Because
 * the trigger source is known analytically (from the composition dict) this
 * avoids the look-ahead latency of a traditional envelope detector and gives
 * cleaner, more consistent results for synthesised audio.
 *
 * Algorithm
 * ----------
 * At each trigger sample the internal envelope attacks toward 1.0 via a
 * one-pole IIR ramp controlled by attack_ms.  Between triggers the envelope
 * releases exponentially toward 0.0 via a separate IIR coefficient derived
 * from release_ms.  Output gain per sample:
 *
 *   gain[n] = 1.0 - depth * envelope[n]
 *
 * depth ∈ [0, 1] controls maximum gain reduction:
 *   depth = 0   → no ducking (unity gain)
 *   depth = 0.7 → 70 % ducking at peak (classic EDM pump)
 *   depth = 1.0 → full mute at kick transient
 *
 * Genre-typical values
 * --------------------
 *   EDM / House  : depth 0.65–0.75, release 60–90 ms
 *   Trap / Phonk : depth 0.50–0.60, release 120–150 ms
 *   Techno       : depth 0.70–0.80, release 50–70 ms
 *   DnB          : depth 0.40–0.50, release 50–70 ms
 *   Pop / Hip-hop: depth 0.15–0.30, release 100–130 ms
 *
 * Cross-platform: standard C++17 only — no POSIX or Windows APIs.
 */

#pragma once

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>   // std::vector<int> ↔ Python list auto-conversion

#include <cmath>
#include <vector>

namespace py = pybind11;


class SidechainFollower {
public:
    /**
     * Construct a SidechainFollower.
     *
     * @param sample_rate  Audio sample rate in Hz (default 48 000).
     * @param attack_ms    Attack time in milliseconds.  Set to 0 or near-0 for
     *                     an instant attack that gives the sharpest pump onset.
     * @param release_ms   Release (decay) time constant in milliseconds.
     *                     Controls how long the gain stays reduced after each kick.
     * @param depth        Peak gain reduction depth: 0 = no ducking, 1 = full mute.
     */
    explicit SidechainFollower(
        int   sample_rate  = 48'000,
        float attack_ms    = 1.0f,
        float release_ms   = 100.0f,
        float depth        = 0.5f
    );

    // ── Configuration ──────────────────────────────────────────────────────────

    /**
     * Replace the full trigger list.
     *
     * trigger_samples is a list of absolute sample indices (within the song)
     * where kick hits occur.  The list does not need to be pre-sorted.
     * Resets the internal envelope to 0 so the first trigger re-initialises
     * cleanly regardless of any previous state.
     */
    void set_triggers(const std::vector<int>& trigger_samples);

    /** Update depth (no click — takes effect at the start of the next sample). */
    void set_depth(float depth) noexcept { depth_ = depth; }

    /** Recompute the release IIR coefficient from a new release_ms value. */
    void set_release_ms(float release_ms) noexcept;

    // ── Processing ────────────────────────────────────────────────────────────

    /**
     * Process one block of audio starting at sample_offset.
     *
     * Envelope state persists across calls so this method can be called
     * repeatedly for consecutive blocks (standard streaming usage).
     *
     * @param input          C-contiguous numpy.ndarray[float32, ndim=1].
     * @param sample_offset  Absolute sample index of input[0] in the song
     *                       timeline.  Used to match triggers to this block.
     * @return               Gain-reduced numpy.ndarray[float32, ndim=1].
     */
    py::array_t<float> process(py::array_t<float> input, int sample_offset);

    // ── Accessors ─────────────────────────────────────────────────────────────

    int   sample_rate()  const noexcept { return sample_rate_; }
    float depth()        const noexcept { return depth_; }
    float envelope()     const noexcept { return envelope_; }

private:
    int   sample_rate_;
    float depth_;
    float attack_coeff_;         // one-pole IIR coefficient for attack ramp
    float release_coeff_;        // one-pole IIR coefficient for release decay
    float envelope_  { 0.0f };  // current envelope state (survives across blocks)

    std::vector<int> triggers_;  // sorted absolute sample positions of kick hits
    int trigger_cursor_ { 0 };  // iterator position into triggers_ (avoids linear scan)
};
