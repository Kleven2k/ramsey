# Real-Time Feedback Loop — RTL Modules

## What this is

Three SystemVerilog modules implementing a closed-loop feedback controller for NV-center
ODMR. After each readout window, the FPGA compares the measured photon count to a
threshold, decides the spin state, and optionally fires a corrective MW pulse — all within
100–400 ns, before the next pulse sequence begins.

This is the same primitive that commercial quantum controllers implement (Quantum Machines
OPX, Zurich Instruments HDAWG) at $100k–$300k. Built here on the Artix-7 at room
temperature for NV-center sensing.

---

## Why real-time feedback matters

**Without feedback (current system):**
```
laser init → MW pulse → readout → send counts to PC → PC fits Lorentzian → done
```
Open-loop. No correction during the measurement. Drift accumulates.

**With feedback:**
```
laser init → MW pulse → readout → FPGA decides spin state → conditional MW correction → next sequence
                                          ↑
                                   all in <400 ns
                                   inside coherence time
```

Enables:

- **Active reset** — detect dark state, apply π pulse, confirm |0⟩ before next sequence.
  Faster initialisation, more measurements per second, better sensitivity.
- **Error correction** — detect unexpected spin flip, apply corrective pulse. Extends
  effective coherence time.
- **Adaptive sensing** — detect resonance drift shot-by-shot, feed correction to MW
  frequency. Hardware version of the Python calibration engine, 1000× faster.

---

## Modules

### state_discriminator.sv

Latches spin state decision on falling edge of readout window (`gate`).

```
inputs:  count [31:0]      — from photon_counter u_sig_ctr
         threshold [31:0]  — UART-configurable register
         gate_in           — pulse_sequencer.gate

outputs: spin_state         — 1=bright |0⟩,  0=dark |1⟩ (needs correction)
         valid              — pulses 1 cycle when decision latched
```

---

### feedback_ctrl.sv

Fires conditional MW correction pulse when dark state detected.

```
inputs:  valid, spin_state, enable, correction_dur [31:0]
outputs: mw_correction     — OR with mw_gate in ramsey_top
         busy
```

---

### latency_counter.sv

Measures gate→correction latency in 10 ns steps. Read via UART STATUS packet.

```
inputs:  gate_in, mw_correction
outputs: latency_cycles [31:0], latency_valid
```

Target: 3 cycles = 30 ns decision latency. Correction pulse adds ~1 µs (`mw_dur` cycles).

---

## Integration into ramsey_top.sv

Three changes needed:

1. Instantiate the three modules (see RTL files for port names)
2. `assign mw_gate_out = mw_gate | mw_correction;`
3. Add two UART registers: `fb_threshold` and `fb_enable`

---

## Tests

11 cocotb tests in `sim/cocotb/feedback/test_feedback.py`. Run with:

```
cd c:\Users\fredr\Documents\ramsey
.venv\Scripts\activate
python sim/cocotb/feedback/runner_feedback.py
```

---

## Connection to qtech/ repo

The `CalibrationEngine` in `qtech/simulation/calibration_engine.py` runs the same
decision loop in Python at ~100 ms/shot via UART. This RTL does the same thing in
hardware at ~30 ns — 3 million times faster. The simulation work validated the algorithm
and threshold values before committing to RTL.
