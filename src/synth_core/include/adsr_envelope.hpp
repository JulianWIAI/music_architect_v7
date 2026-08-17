/**
 * @file adsr_envelope.hpp
 * @brief Attack / Decay / Sustain / Release amplitude envelope.
 *
 * Direct C++ port of src/rendering/adsr_envelope.py (ADSREnvelope class).
 * All timing values are in seconds; sustain is a normalised level in [0, 1].
 *
 * The envelope shape:
 *
 *   1 ─┐         ← peak at end of attack
 *      │\
 *  S ──│ ──────┐ ← sustain level held during note duration
 *      │       │\
 *   0 ─┼───────┼──→  time
 *      A   D   R
 *
 * get_amplitude() is called once per sample in the hot synthesis loop, so it
 * is declared noexcept and kept branchless where possible for the compiler.
 */

#pragma once

class ADSREnvelope {
public:
    /**
     * Construct an ADSR envelope.
     *
     * @param attack   Rise time from 0 to peak (seconds).
     * @param decay    Fall time from peak to sustain level (seconds).
     * @param sustain  Amplitude held while the note is on, in [0, 1].
     * @param release  Tail from note-off to silence (seconds).
     */
    ADSREnvelope(double attack, double decay,
                 double sustain, double release) noexcept;

    /**
     * Return the normalised envelope amplitude [0, 1] at time @p t.
     *
     * @param t        Elapsed time since note-on (seconds). Negative values → 0.
     * @param duration Note-off time measured from note-on (seconds).
     */
    double get_amplitude(double t, double duration) const noexcept;

private:
    double attack_;
    double decay_;
    double sustain_;
    double release_;
};
