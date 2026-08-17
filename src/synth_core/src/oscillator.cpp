/**
 * @file oscillator.cpp
 * @brief Waveform oscillator implementation.
 *
 * Ported from BuiltinSynthesizer.oscillator() in builtin_synthesizer.py.
 * The arithmetic is identical to the Python original: the saw, square, and
 * triangle waves use freq*t (not phase accumulation) so output matches the
 * existing Python synthesizer exactly.
 *
 * Cross-platform note: M_PI is not guaranteed by the C++ standard (it is a
 * POSIX extension absent in MSVC by default).  We define kPi as a constexpr
 * to avoid any platform-specific preprocessor guards.
 */

#include "oscillator.hpp"
#include <cmath>   // std::sin, std::fmod, std::abs

// ── Constants ────────────────────────────────────────────────────────────────

static constexpr double kPi      = 3.14159265358979323846;
static constexpr double k2Pi     = 2.0 * kPi;
static constexpr double kInvUnit = 1.0;  // fmod normaliser: freq*t mod 1

// ── oscillator_type_from_string ──────────────────────────────────────────────

OscillatorType oscillator_type_from_string(const std::string& name) noexcept {
    if (name == "saw")      return OscillatorType::SAW;
    if (name == "square")   return OscillatorType::SQUARE;
    if (name == "triangle") return OscillatorType::TRIANGLE;
    // "sine" and any unknown string both map to SINE (matches Python fallback)
    return OscillatorType::SINE;
}

// ── oscillate ────────────────────────────────────────────────────────────────

double oscillate(double freq, double t, OscillatorType type) noexcept {
    // Mirror of builtin_synthesizer.py::oscillator()
    switch (type) {
        case OscillatorType::SINE:
            // Standard sine wave
            return std::sin(k2Pi * freq * t);

        case OscillatorType::SAW: {
            // Sawtooth: 2·frac(freq·t) − 1  (rises from −1 to +1)
            // std::fmod matches Python's '%' for positive arguments
            double phase = std::fmod(freq * t, kInvUnit);
            if (phase < 0.0) phase += 1.0;   // guard for t < 0 edge cases
            return 2.0 * phase - 1.0;
        }

        case OscillatorType::SQUARE:
            // Square: +1 while sin > 0, else −1
            return (std::sin(k2Pi * freq * t) > 0.0) ? 1.0 : -1.0;

        case OscillatorType::TRIANGLE: {
            // Triangle: 2·|2·frac(freq·t) − 1| − 1
            double phase = std::fmod(freq * t, kInvUnit);
            if (phase < 0.0) phase += 1.0;
            return 2.0 * std::abs(2.0 * phase - 1.0) - 1.0;
        }
    }
    // Unreachable but silences warnings on MSVC
    return std::sin(k2Pi * freq * t);
}
