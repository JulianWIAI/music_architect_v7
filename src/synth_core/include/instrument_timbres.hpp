/**
 * @file instrument_timbres.hpp
 * @brief Instrument timbre registry — GM program number → synthesis parameters.
 *
 * Ported from src/rendering/instrument_timbres.py (INSTRUMENT_TIMBRES dict and
 * DEFAULT_TIMBRE).  All timbre data is compiled into a static table so there
 * is no runtime parsing overhead.
 *
 * A Timbre bundles everything synthesize_note() needs for one instrument:
 * harmonic weights, a pre-computed harmonic sum (avoids recomputing per note),
 * ADSR parameters, and the oscillator waveform type.
 */

#pragma once

#include <vector>
#include "oscillator.hpp"

/**
 * Complete synthesis parameters for one instrument.
 *
 * Maps directly to one entry in the Python INSTRUMENT_TIMBRES dict:
 *   { 'harmonics': [...], 'adsr': (A, D, S, R), 'type': 'sine' }
 */
struct Timbre {
    std::vector<double> harmonics;  ///< Per-harmonic amplitude weights
                                    ///< (index 0 = fundamental, index 1 = 2nd harmonic, …)
    double harmonic_sum;            ///< Sum of all harmonic weights (pre-computed for
                                    ///< normalisation; avoids recomputing per sample)
    double attack;                  ///< ADSR attack time (seconds)
    double decay;                   ///< ADSR decay time (seconds)
    double sustain;                 ///< ADSR sustain level [0, 1]
    double release;                 ///< ADSR release time (seconds)
    OscillatorType osc_type;        ///< Waveform shape
};

/**
 * Return a const reference to the Timbre for GM program number @p program.
 *
 * If @p program is not in the registry the default timbre is returned.
 * The returned reference is valid for the entire program lifetime (static data).
 */
const Timbre& get_timbre(int program) noexcept;
