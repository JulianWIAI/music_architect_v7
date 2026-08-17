/**
 * @file oscillator.hpp
 * @brief Waveform oscillator types and sample computation.
 *
 * Ported from the oscillator() function in src/rendering/builtin_synthesizer.py.
 * Four classic waveforms are supported, matching the 'type' strings used in
 * instrument_timbres.py / instrument_timbres.cpp.
 *
 * oscillate() is called in the innermost sample loop: it is noexcept and
 * written to allow the compiler to inline and auto-vectorise it.
 */

#pragma once

#include <string>

/**
 * Waveform type.
 *
 * Integer values are used internally for the switch in oscillate()
 * and must not be changed — instrument_timbres.cpp uses them directly.
 */
enum class OscillatorType : int {
    SINE     = 0,   ///< sin(2π·f·t)
    SAW      = 1,   ///< Sawtooth: 2·frac(f·t) − 1
    SQUARE   = 2,   ///< ±1 depending on sign of sin(2π·f·t)
    TRIANGLE = 3    ///< Absolute-value triangle wave
};

/**
 * Convert a string name to an OscillatorType.
 *
 * Accepts "sine", "saw", "square", "triangle" (case-sensitive, matches Python).
 * Unknown strings silently fall back to SINE.
 */
OscillatorType oscillator_type_from_string(const std::string& name) noexcept;

/**
 * Compute one output sample of the oscillator waveform.
 *
 * Frequencies are computed as @p freq * (harmonic index + 1) by the caller;
 * this function receives the already-scaled harmonic frequency.
 *
 * @param freq  Instantaneous frequency in Hz.
 * @param t     Time in seconds from note start (used as phase input).
 * @param type  Waveform shape.
 * @return      Sample value in the range [−1, +1].
 */
double oscillate(double freq, double t, OscillatorType type) noexcept;
