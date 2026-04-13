# Future Applications for SiC Quantum Sensing

## Context

Ramsey is an FPGA-based ODMR readout system. This document captures thinking about
where that system — and SiC quantum sensing broadly — could evolve toward real applications.

---

## Near-term: NV Center in Diamond (Parallel Path)

**Why this is now a near-term target**

Prof. Bathen's reply (April 11) confirmed that SINTEF and FFI are already working on
applied NV-diamond systems. These are the most mature application-ready sensors. Our
ADF4351 covers 2.87 GHz (NV zero-field splitting in diamond) without hardware changes.

**Key parameters for NV diamond:**
- Zero-field splitting: **2.87 GHz**
- Typical ODMR contrast: 1–5% at room temperature
- Detection wavelength: ~637 nm (visible) → silicon APD, TTL-compatible with `apd_in`
- Room temperature operation: yes, well demonstrated

**Why this matters for Ramsey**

If SINTEF or FFI have a working NV pulsed setup, they use commercial instruments
(PulseBlaster, NI DAQ). Ramsey is a direct open-source replacement at ~$200. A test
at one of these labs — even a brief one — would be the strongest possible expo result.

**Status:** Frequency range confirmed compatible. Awaiting SINTEF/FFI introduction from
Prof. Bathen. Oslo collaborators with working setup may be accessible before expo.

---

## Near-term: Thermometry in SiC Power Electronics

**The opportunity**

SiC is already the dominant material for high-voltage power semiconductors — EV inverters,
solar inverters, industrial drives. The zero-field splitting of SiC defects shifts
predictably with temperature. A SiC quantum sensor embedded in or near a SiC power module
could measure junction temperature non-invasively and in real time, without electrical contact.

**Why junction temperature matters**

Junction temperature is currently estimated from thermal models, not measured directly.
Direct measurement would improve reliability, enable tighter thermal margins, and detect
early degradation.

**Why our system fits**

- Requires only ~1 MHz frequency resolution — within ADF4351 capability
- Room temperature operation — no cryostat needed
- Required sensitivity is mT range — achievable with current architecture
- SiC-on-SiC integration is a natural story: sensor material = device material

**Status:** No hardware changes required. Achievable with current RTL + a calibrated sensor.

---

## Medium-term: Current Sensing for EV Battery Management

**The opportunity**

Battery packs need per-cell current monitoring. Existing Hall sensors drift with temperature
and have limited precision. A SiC quantum sensor could measure current non-invasively by
detecting the magnetic field produced by the current — no electrical contact, no insertion loss.

**Required sensitivity**

~µT for a 1 A wire at 1 cm distance. Borderline achievable with an optimized version of
the current system — approximately 10-100x improvement needed over a basic implementation.

**Status:** Requires sensitivity optimization. Closer than bio-sensing by several orders of magnitude.

---

## Longer-term: GPS-Denied Navigation (Quantum Gyroscope)

**The opportunity**

Quantum gyroscopes measure rotation through spin coherence — the precession frequency shifts
with rotation rate. GPS-denied navigation is a large market: submarines, tunnels, space, military.

**Why SiC fits**

- SiC is radiation-hard — relevant for space applications
- Cheaper and more manufacturable than diamond NV centers
- Ramsey pulse mode (free precession) is already implemented in the Ramsey sequencer
  (`dead_time` parameter = free precession time τ)

**The gap**

Long coherence times (T₂) are required. This is a materials problem — longer T₂ requires
cleaner crystal growth and shallower, more controlled defect implantation. Not a software problem.

**Status:** Ramsey mode ready in RTL. Waiting on materials science.

---

## Long-term: Bio-sensing (Cellular Magnetic Field Imaging)

**The opportunity**

Cells produce magnetic fields during electrical signaling. Imaging those fields non-invasively
would allow observing how cells communicate — neurons, cardiac cells, etc.

**The gap**

Cells produce fields in the femtotesla (fT = 10⁻¹⁵ T) range. Current ODMR systems at room
temperature reach nanotesla (nT). That is a factor of ~10⁶ in sensitivity — not an engineering
iteration, a fundamental research frontier.

Additional requirements beyond sensitivity:
- Scanning confocal microscope (€100k+)
- Thin sensor membrane with surface-near defects (5-10 nm depth)
- Surface functionalization for cell adhesion
- Wet, 37°C operating environment

**Status:** 10+ year research horizon. Valid as a motivating vision, not a near-term target.

---

## Sensitivity Comparison

| Application                  | Sensitivity needed | Current system  | Gap              |
|------------------------------|--------------------|-----------------|------------------|
| Power electronics thermometry| ~1 MHz freq res    | Already there   | Materials only   |
| Current sensing (EV)         | ~µT                | Close           | 10-100x          |
| GPS-denied gyroscope         | Long T₂            | Ramsey ready    | Materials + DSP  |
| Bio-sensing                  | fT                 | Far             | ~10⁶×            |

---

## The Research Narrative

> "We are building the readout instrument for SiC quantum sensors. The near-term application
> is thermal and current characterization of SiC power devices — same material, natural
> integration. The long-term direction is navigation and eventually biological sensing as
> sensor coherence improves."

This arc starts with something testable at room temperature today, and has a clear scaling
path tied to progress in SiC materials science.

---

## What Crosses from Master's to PhD Level

A master's project builds a working instrument. A PhD contribution advances what it can
measure or how. Concrete directions that would cross that line:

1. **Closed-loop adaptive control** — track the resonance in real time, feed the center
   frequency back to the ADF4351. Turns the system into a real magnetometer.

2. **Sensitivity characterization** — measure magnetic field sensitivity in nT/√Hz,
   identify every noise source, push against the shot noise limit. Publishable metrology.

3. **Vector magnetometry** — SiC defects orient along different crystal axes. Reading
   multiple orientations simultaneously gives a vector field measurement.

4. **Pulsed vs CW systematic study** — the sequencer supports both modes. A rigorous
   comparison on a real SiC sensor would be a publishable characterization paper.
