/**
 * @file instrument_timbres.cpp
 * @brief Static GM instrument timbre registry.
 *
 * Ported from src/rendering/instrument_timbres.py (INSTRUMENT_TIMBRES dict
 * and DEFAULT_TIMBRE).  All values are copied verbatim from the Python source
 * so the C++ and Python synthesizers produce identical output.
 *
 * Data is stored in a static unordered_map initialised once at program start.
 * get_timbre() returns by const reference — zero-copy, O(1) lookup.
 *
 * Adding new instruments
 * ----------------------
 * Append an entry to the kTimbreData initialiser list below, following the
 * existing pattern:  { gm_program, { {harmonics}, harmonic_sum,
 *                                     A, D, S, R, OscillatorType } }
 * harmonic_sum must equal std::accumulate of the harmonics vector.
 */

#include "instrument_timbres.hpp"
#include <unordered_map>
#include <numeric>   // std::accumulate

// ── Default timbre (used for any unregistered GM program) ─────────────────────

static const Timbre kDefaultTimbre = {
    /* harmonics     */ { 1.0, 0.3, 0.1 },
    /* harmonic_sum  */ 1.4,          // 1.0 + 0.3 + 0.1
    /* attack        */ 0.01,
    /* decay         */ 0.10,
    /* sustain       */ 0.70,
    /* release       */ 0.20,
    /* osc_type      */ OscillatorType::SINE
};

// ── Timbre table ─────────────────────────────────────────────────────────────
// Format: { gm_program, Timbre{ harmonics, harmonic_sum, A, D, S, R, type } }
// Mirrors INSTRUMENT_TIMBRES in instrument_timbres.py line-by-line.

static const std::unordered_map<int, Timbre> kTimbreMap = {

    // ── Acoustic / Electric Piano ──────────────────────────────────────────────
    {  0, { { 1.0, 0.5, 0.25, 0.12, 0.06 },    // GM 0: Acoustic Grand Piano
            1.93,                                // sum
            0.005, 0.3, 0.3, 0.4,
            OscillatorType::SINE } },

    {  4, { { 1.0, 0.6, 0.3, 0.15 },            // GM 4: Electric Piano 1
            2.05,                                // sum
            0.005, 0.2, 0.4, 0.3,
            OscillatorType::SINE } },

    // ── Bass ──────────────────────────────────────────────────────────────────
    { 33, { { 1.0, 0.7, 0.3 },                  // GM 33: Electric Bass (finger)
            2.0,                                 // sum
            0.01, 0.1, 0.8, 0.1,
            OscillatorType::SINE } },

    { 38, { { 1.0, 0.8, 0.5, 0.3 },             // GM 38: Synth Bass 1
            2.6,                                 // sum
            0.005, 0.05, 0.9, 0.05,
            OscillatorType::SAW } },

    { 87, { { 1.0, 0.9, 0.6, 0.4 },             // GM 87: Lead 8 (bass + lead)
            2.9,                                 // sum
            0.002, 0.05, 0.85, 0.05,
            OscillatorType::SAW } },

    // ── Strings ───────────────────────────────────────────────────────────────
    { 40, { { 1.0, 0.4, 0.2, 0.1 },             // GM 40: Violin
            1.7,                                 // sum
            0.15, 0.1, 0.8, 0.3,
            OscillatorType::SINE } },

    { 42, { { 1.0, 0.5, 0.25 },                 // GM 42: Cello
            1.75,                                // sum
            0.1, 0.1, 0.85, 0.3,
            OscillatorType::SINE } },

    { 43, { { 1.0, 0.6, 0.3 },                  // GM 43: Contrabass
            1.9,                                 // sum
            0.08, 0.1, 0.8, 0.2,
            OscillatorType::SINE } },

    { 46, { { 1.0, 0.3, 0.15 },                 // GM 46: Orchestral Harp
            1.45,                                // sum
            0.02, 0.1, 0.7, 0.3,
            OscillatorType::SINE } },

    { 48, { { 1.0, 0.4, 0.2, 0.1 },             // GM 48: String Ensemble 1
            1.7,                                 // sum
            0.2, 0.15, 0.75, 0.4,
            OscillatorType::SINE } },

    // ── Lead Synths ───────────────────────────────────────────────────────────
    { 80, { { 1.0, 0.5, 0.3, 0.2, 0.1 },        // GM 80: Lead 1 (square)
            2.1,                                 // sum
            0.01, 0.05, 0.8, 0.1,
            OscillatorType::SAW } },

    { 81, { { 1.0, 0.7, 0.5, 0.3 },             // GM 81: Lead 2 (sawtooth)
            2.5,                                 // sum
            0.01, 0.05, 0.85, 0.1,
            OscillatorType::SQUARE } },

    // ── Orchestra ─────────────────────────────────────────────────────────────
    { 68, { { 1.0, 0.3, 0.1 },                  // GM 68: Oboe
            1.4,                                 // sum
            0.05, 0.1, 0.7, 0.2,
            OscillatorType::SINE } },

    // ── Pads ──────────────────────────────────────────────────────────────────
    { 88, { { 1.0, 0.3, 0.15, 0.08 },           // GM 88: Pad 1 (new age)
            1.53,                                // sum
            0.4, 0.2, 0.7, 0.5,
            OscillatorType::SINE } },

    { 89, { { 1.0, 0.4, 0.2, 0.1 },             // GM 89: Pad 2 (warm)
            1.7,                                 // sum
            0.3, 0.2, 0.65, 0.6,
            OscillatorType::SINE } },

    { 92, { { 1.0, 0.2, 0.1 },                  // GM 92: Pad 5 (bowed glass)
            1.3,                                 // sum
            0.5, 0.3, 0.6, 0.8,
            OscillatorType::SINE } },

    { 95, { { 1.0, 0.5, 0.3, 0.2 },             // GM 95: Pad 8 (sweep)
            2.0,                                 // sum
            0.3, 0.15, 0.7, 0.5,
            OscillatorType::SAW } },

    // ── Vibraphone / Bells ────────────────────────────────────────────────────
    { 11, { { 1.0, 0.6, 0.4, 0.2, 0.1 },        // GM 11: Vibraphone
            2.3,                                 // sum
            0.005, 0.3, 0.2, 0.5,
            OscillatorType::SINE } },
};

// ── get_timbre ────────────────────────────────────────────────────────────────

const Timbre& get_timbre(int program) noexcept {
    auto it = kTimbreMap.find(program);
    return (it != kTimbreMap.end()) ? it->second : kDefaultTimbre;
}
