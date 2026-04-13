# Sensor Expo — Student Competition

## Event

University sensor expo, student showcase competition.
**Date: ~June 2, 2026** (56 days from April 6, 2026)

> "New sensor concepts that can push the limits of today's sensors."

---

## Abstract (draft)

Cells communicate using tiny magnetic fields. We are building the instrument that can
measure them — starting with a quantum sensor made from the same silicon carbide used
in electric vehicle power electronics.

Ramsey is an FPGA-based ODMR (Optically Detected Magnetic Resonance) readout system
for SiC color center quantum sensors. It sequences laser and microwave pulses with
nanosecond precision, counts single photons, and streams calibrated contrast spectra
to a PC in real time. The near-term application is non-contact temperature and current
sensing inside SiC power devices. The long-term direction is navigation and biological
field sensing as sensor coherence improves.

The full stack — RTL, firmware, Python GUI, and RF hardware — is designed and built
from scratch as a master's side project.

---

## What to Show

**Minimum viable demo (no lab access needed)**
- GUI running with a pre-recorded ODMR dip dataset
- Live Lorentzian fit updating on screen as data arrives
- Pulse sequencer timing diagram — visual, immediately communicates what the system does
- System architecture diagram

**Target demo (with hardware)**
- Live FPGA connected via UART — INIT → CONFIG → START → DATA round-trip on screen
- ADF4351 sweeping frequencies, lock_detect going high between steps
- Photon counts streaming in real time

**Stretch goal (with lab access)**
- Real ODMR dip from an actual SiC sensor
- Fitted resonance frequency shown on the plot

---

## Timeline

### Week 1 — April 1–7 (Act now)
- [x] Order ADF4351 module — shipped, arriving April 23
- [x] Send email to professor — sent April 6, **reply received April 11**
- [ ] Submit expo abstract
- [x] Start `python/lorentzian_fit.py`

### Week 2–3 — April 8–21 (Software + prep)
- [x] Complete `lorentzian_fit.py` — scipy curve_fit on contrast dip, extract center frequency
- [x] Integrate fit into GUI — fitted curve overlaid on data, center frequency in status bar
- [x] Build synthetic demo — DEMO button, realistic ODMR dip with noise
- [x] Flash bitstream to Nexys Video, verify UART INIT/ACK round-trip
- [x] CONFIG and START sending correctly over real UART
- [ ] Draft poster layout

### Week 4–5 — April 22 – May 7 (Hardware arrives)
- [ ] Bench test ADF4351 module — SPI communication, verify lock_detect
- [ ] Scope check: laser_gate and mw_gate waveforms match configured timing
- [ ] Full system test without optics — photon counter, pulse sequencer verified
- [ ] Refine poster content based on what is working

### Week 6–8 — May 8–25 (Push for real data)
- [ ] Lab visit with professor (if arranged) — attempt real ODMR measurement
- [ ] If lab access: capture and document first real contrast spectrum
- [ ] If no lab access: finalize synthetic demo, focus on polish
- [ ] Rehearse explanation for general audience (30-second and 3-minute versions)

### Week 9 — May 26 – June 2 (Final polish)
- [ ] Print poster
- [ ] Final rehearsal
- [ ] Prepare backup: pre-recorded demo video in case of hardware failure on the day

---

## Presentation Narrative

**For a general audience (30 seconds)**
> "We're building a sensor that can detect tiny magnetic fields — the kind produced by
> electric currents in a battery cell, or eventually by nerve cells firing. The sensor
> is made from silicon carbide, the same material in EV power electronics. I built the
> readout electronics from scratch."

**For a technical audience (3 minutes)**
> Lead with the ODMR concept — laser initialises spin state, microwave drives transition,
> fluorescence dip reveals resonance frequency, field shifts that frequency.
> Show the pulse timing diagram.
> Show the GUI with live (or pre-recorded) contrast spectrum and Lorentzian fit.
> Explain the stack: FPGA pulse sequencer → photon counter → UART → Python GUI.
> Finish with the application roadmap: thermometry → navigation → bio-sensing.

---

## Critical Path

The two actions that determine whether this demo has real hardware or not:
1. ~~**Order the ADF4351 module this week**~~ — ordered April 6, shipped, arriving April 23
2. ~~**Email the professor this week**~~ — sent April 6, reply received April 11

## Collaboration Opportunities (April 11)

Prof. Bathen replied with three significant offers:
- **SINTEF / FFI introduction** — applied NV-diamond groups, likely using commercial instruments
  that Ramsey could replace. Accept this introduction.
- **Oslo collaborators with working pulsed setup** — potential early test site before our
  own hardware is complete. This is the most time-sensitive opportunity for the expo.
- **She wants to see the system when it's done** — informal but genuine interest.

Open question: which detector do they use for ODMR specifically (APD = TTL-compatible,
or analog)? Clarify in reply.

## Hardware Bring-up Notes (April 6)

Bugs found and fixed during first hardware test:
- `rst_n` IOSTANDARD was LVCMOS33 in a 1.5V bank (G4/bank 35) — FPGA read reset as permanently asserted. Fixed to LVCMOS15.
- UART TX/RX pins were swapped — `uart_rx_pin` belongs on V18, `uart_tx_pin` on AA19.

First successful ACK received from real hardware April 6, 2026.
