# Implementation Plan

Progress tracker. Check items off as they are completed.

---

## Phase 1 — Cocotb sim infra + photon counter

### 1.1 Environment setup
- [✅] Install Icarus Verilog (`iverilog`) — v12.0 confirmed
- [✅] Install cocotb: `pip install cocotb` — v2.0.1 confirmed
- [ ] Install cocotb-bus (optional helpers): `pip install cocotb-bus`
- [✅] Verify: `iverilog -V` and `python -c "import cocotb"` both succeed

**Notes:**
- cocotb 2.0 renamed the `Clock` argument `units` → `unit`. Use `unit="ns"` going forward.
- iverilog defaults to 1 s simulator precision unless a `` `timescale `` directive is set. Always include `` `timescale 1ns/1ps `` in the tb wrapper, or the clock period will fail to resolve.

### 1.2 Directory structure
Dropped the Makefile approach — using a Python runner instead (no `make` dependency on Windows). Layout:
```
sim/cocotb/
└── photon_counter/
    ├── photon_counter_tb_wrapper.sv   ← instantiates DUT, sets timescale
    ├── runner_photon_counter.py       ← compiles with iverilog, runs via vvp
    └── test_photon_counter.py         ← cocotb test functions
```

### 1.3 photon_counter.sv — module spec

**Ports:**

| Port | Dir | Width | Description |
|---|---|---|---|
| `clk` | in | 1 | 100 MHz system clock |
| `rst` | in | 1 | Synchronous reset |
| `apd_in` | in | 1 | Asynchronous TTL from APD — must be double-FF synchronized |
| `gate` | in | 1 | Count enable — count only while high |
| `clear` | in | 1 | Synchronous clear of count register |
| `count` | out | 32 | Photon count — held stable after gate goes low |

**Behavior:**
- `apd_in` is asynchronous. Pass through a two-stage synchronizer (double-FF) before any logic.
- Detect rising edge on the synchronized signal. Increment `count` on each detected edge while `gate` is high.
- When `gate` goes low, hold `count` (do not clear — the pulse sequencer will read it out).
- `clear` resets `count` to zero synchronously. Intended to be asserted at the start of each new shot.
- `rst` resets everything including the synchronizer FFs.

**Key design note:** At 100 MHz clock and 10 MHz APD rate, there are 10 clock cycles per photon pulse minimum. The double-FF synchronizer introduces 2-cycle latency — acceptable. Back-to-back pulses faster than 2 cycles cannot be distinguished; this is a known hardware limit.

### 1.4 RTL implementation
- [x] Write `rtl/counter/photon_counter.sv` — synchronizer + edge detector + gated counter

### 1.5 Testbench files
- [x] Write `photon_counter_tb_wrapper.sv` — DUT instantiation + `` `timescale 1ns/1ps ``
- [x] Write `runner_photon_counter.py` — custom iverilog/vvp runner (no Makefile)
- [x] Write `test_photon_counter.py` — cocotb test functions

### 1.6 Testbench — test cases

- [✅] **test_basic_count** — drive N pulses during gate window, assert `count == N` after gate goes low
- [✅] **test_gate_inhibit** — drive pulses with `gate` low the whole time, assert `count == 0`
- [✅] **test_hold_after_gate** — verify count does not change after gate goes low (no spurious increments)
- [✅] **test_clear** — assert `clear` mid-window, verify count resets to zero and resumes counting
- [✅] **test_max_rate** — drive pulses every 10 clock cycles (10 MHz), verify all are counted correctly

### 1.7 Verification
- [✅] All 5 tests pass in simulation
- [✅] Waveform inspected in GTKWave — synchronizer delay and gated counting confirmed correct

---

## Phase 2 — Pulse sequencer FSM

**Goal:** Implement the core timing engine that drives the ODMR experiment. The FSM sequences through four states per shot: laser init pulse, MW pulse, readout window, reference window. Both `laser_gate` and `mw_gate` outputs must be timed with nanosecond precision. Design for Ramsey from day one — the FSM must support arbitrary pulse counts and free-precession delays, not just CW ODMR.

**FSM — one sweep point:**
```
IDLE → INIT_PULSE → MW1 → DEAD → MW2 → READOUT → REFERENCE → (repeat n_shots times)
     → sweep_point_done + next_freq → IDLE
```

**CW ODMR:** set `dead_time = 0` — MW1 and MW2 fuse into one continuous pulse.
**Ramsey:** `dead_time = τ` (free precession time), `mw_dur` = π/2 pulse width.
All duration inputs are in clock cycles (1 cycle = 10 ns at 100 MHz).

**Key design notes from literature (Cvetkovs et al. 2025):**
- `WAIT_DEBOUNCE` and `WAIT_DELAY` states needed in the SPI/frequency-step path — raw ADF4351 digital LD is unreliable. To be added when SPI master is integrated (Phase 5).

### 2.1 RTL
- [✅] Write `rtl/sequencer/pulse_sequencer.sv`
  - 7-state FSM: IDLE, INIT_PULSE, MW1, DEAD, MW2, READOUT, REFERENCE
  - Timer-based state duration (32-bit countdown in clock cycles)
  - Shot loop with `shot_count`, transitions back to INIT_PULSE until `n_shots` reached
  - Single-cycle pulses: `counter_clear`, `sweep_point_done`, `next_freq`
  - `counter_clear` asserted once per shot in MW2 (before READOUT gate opens)
  - `gate` high during READOUT only; `ref_gate` high during REFERENCE only (dedicated output, not derived from `laser_gate & ~gate`)

### 2.2 Simulation
- [✅] Write `sim/cocotb/pulse_sequencer/pulse_sequencer_tb_wrapper.sv`
- [✅] Write `sim/cocotb/pulse_sequencer/runner_pulse_sequencer.py`
- [✅] Write `sim/cocotb/pulse_sequencer/test_pulse_sequencer.py`

### 2.3 Test cases
- [✅] **test_cw_single_shot** — one shot, verify laser_gate, mw_gate, and gate durations
- [✅] **test_shot_loop** — n_shots=3, verify counter_clear fires 3 times, sweep_point_done once
- [✅] **test_ramsey** — dead_time > 0, verify gap between MW1 falling and MW2 rising
- [✅] **test_counter_clear** — verify counter_clear pulses exactly once per shot
- [✅] **test_busy** — verify busy goes high on run and low when returning to IDLE

**All 5 tests passing. 5/5.**

---

## Phase 3 — UART + Python readout

**Goal:** Establish a communication channel between the FPGA and PC before building the accumulator, so we have a working readout path to verify data with. The FPGA receives a frequency sweep table from Python and streams accumulated counts back. On the PC side, plot contrast vs frequency to confirm the data pipeline is correct.

### 3.1 RTL — UART byte layer
- [✅] Verify `rtl/uart/uart_rx.sv` and `rtl/uart/uart_tx.sv` — ported from a previous project, confirmed correct for 100 MHz / 115200 baud
- [✅] Verify `rtl/uart/uart_top.sv` — wraps RX + TX into a single module

### 3.2 RTL — Packet framing layer
- [✅] Write `rtl/uart/uart_interface.sv` — full packet framing on top of `uart_top`
  - RX FSM: 6 states (WAIT_HEADER → GET_TYPE → GET_LEN_HI → GET_LEN_LO → GET_PAYLOAD → GET_CRC)
  - TX FSM: 7 states (IDLE → HEADER → TYPE → LEN_HI → LEN_LO → PAYLOAD → CRC)
  - Start-bit guard (`tx_can_send`) prevents double-triggering between `tx_send` and `uart_tx` raising `tx_busy`
  - CRC = XOR of all payload bytes

### 3.3 Simulation
- [✅] Write `sim/cocotb/uart/uart_tb_wrapper.sv` — instantiates `uart_interface`, sets timescale
- [✅] Write `sim/cocotb/uart/runner_uart.py` — same iverilog/vvp pattern as photon counter
- [✅] Write `sim/cocotb/uart/test_uart.py` — 7 cocotb tests, all passing

### 3.4 Test cases
- [✅] **test_tx_byte** — basic smoke test: send ACK, verify round-trip via `uart_recv_packet`
- [✅] **test_rx_byte** — send a single raw 0xAA byte, verify no sim error
- [✅] **test_rx_packet** — send a valid 3-byte CONFIG packet, verify `rx_msg_type` and `rx_msg_len` latched correctly
- [✅] **test_rx_bad_crc** — send a packet with corrupted CRC, verify `rx_crc_ok` never fires
- [✅] **test_tx_packet** — send a 3-byte DATA packet with payload handshake via `tx_payload_req`, verify full frame
- [✅] **test_tx_zero_payload** — send an ACK, verify the raw wire frame byte-by-byte: `[0xAA][0x04][0x00][0x00][0x00]`
- [✅] **test_rx_noise_recovery** — send 4 garbage bytes before the header, verify FSM discards them and parses the valid packet

**Notes:**
- `rx_crc_ok` and `rx_msg_done` are single-cycle pulses on different cycles (msg_done fires on the last payload byte, crc_ok fires one byte later on the CRC byte). Always use `cocotb.start_soon(wait_crc())` **before** sending the packet to avoid missing the pulse.
- `tx_payload_req` fires once per byte starting from `TX_LEN_LO` (requesting byte 0), then once per consumed byte. The application has ~868 cycles per byte to respond.

### 3.5 Python control GUI
Structure: a `uart_comm.py` backend (packet logic only, no GUI) with a GUI on top. Keeps the serial layer testable independently and allows scripted sweeps without the GUI.

**Stack:** `pyserial` · `Dear PyGui` · `ctypes` (screen centering) · `numpy` (planned, contrast math)

**Files:**
- [✅] `python/uart_comm.py` — send/receive framed packets over serial; no GUI code
- [✅] `python/gui.py` — Dear PyGui control GUI, calls `uart_comm` as backend
- [✅] `python/lorentzian_fit.py` — scipy curve_fit on contrast dip, returns f0/FWHM/fitted_y
- [✅] `python/synthetic.py` — generates synthetic MSG_DATA payloads with Poisson noise for demo
- [✅] `python/test_uart.py` — standalone INIT/ACK round-trip test script

**What is implemented:**
- Connection bar with port selector, refresh button, connect/disconnect toggle (red/green)
- Status line showing last event (connected, ACK received, errors)
- TIMING section: n_shots, init_dur, mw_dur, readout_dur, ref_dur, dead_time input fields
- FREQUENCY section: freq_start, freq_stop, freq_step input fields
- INIT / CONFIG / START buttons with packet send callbacks
- Live ODMR plot (frequency vs contrast) with x/y axes
- MSG_DATA handler: unpacks sig/ref counts, computes contrast, updates plot
- Lorentzian fit overlaid on plot, f0 and FWHM shown in status bar
- DEMO button: runs synthetic ODMR sweep without hardware
- ConnectionError handling in all send callbacks

**CONFIG payload fix (April 12):**
Python on_config payload order corrected to match RTL case statement:
n_points(2) → n_shots(4) → init_dur(4) → mw_dur(4) → readout_dur(4) → ref_dur(4) → dead_time(4) → freq_table

**Remaining:**
- [ ] Reader thread exception handling — currently swallows errors silently on `except Exception: break`

---

## Phase 4 — BRAM shot accumulator

**Goal:** Average N shots per frequency point in hardware to reduce the data rate to the PC. BRAM stores two 32-bit values per frequency point — signal counts and reference counts separately — so the PC can compute the normalized contrast ratio. Read-modify-write on every shot.

### 4.1 RTL
- [✅] Write `rtl/accumulator/shot_accumulator.sv`
  - Separate `sig_mem` / `ref_mem` arrays (inferred BRAM), depth parameterised (default 1024)
  - 3-cycle read-modify-write pipeline: capture on gate fall → BRAM read → write back sum
  - `wr_ptr` advances on `sweep_point_done`, resets on `sweep_start` (renamed from `run` to avoid confusion with `pulse_sequencer.run`)
  - Host read port: registered `rd_sig` / `rd_ref` outputs
  - `ref_gate` input (dedicated, not derived from `laser_gate & ~gate`)

### 4.2 Simulation
- [✅] Write `sim/cocotb/accumulator/shot_accumulator_tb_wrapper.sv`
- [✅] Write `sim/cocotb/accumulator/runner_shot_accumulator.py`
- [✅] Write `sim/cocotb/accumulator/test_shot_accumulator.py`

### 4.3 Test cases
- [✅] **test_single_shot_signal** — signal window closes, count lands in sig_mem[0]
- [✅] **test_single_shot_reference** — reference window closes, count lands in ref_mem[0]
- [✅] **test_accumulation_multi_shot** — 3 shots sum correctly, not overwrite
- [✅] **test_freq_index_advances** — sweep_point_done increments pointer, each point independent
- [✅] **test_run_resets_pointer** — run resets freq_index to 0

**All 5 tests passing. 5/5.**

---

## Phase 5 — SPI master + ADF4351

**Goal:** Implement the SPI master and program the ADF4351 synthesizer to generate the target SiC transition frequency (~1.3 GHz for the V2 center in 4H-SiC). The ADF4351 requires writing 6 registers in the correct order at startup. Verify the output frequency with an SDR dongle before connecting to the RF chain.

**Key design note from literature (Cvetkovs et al. 2025):** Rather than pre-computing ADF4351 register values on the PC and sending them over UART, implement a **frequency calculator** in FPGA logic that computes INT, FRAC, MOD coefficients from a target frequency using the formula `fout = fref × (INT + FRAC/MOD)`. A Goldschmidt divider gives 8-cycle latency — negligible compared to PLL lock time. This keeps the PC interface simple (just send a frequency in MHz) and lets the FPGA handle all register computation.

### 5.1 RTL
- [✅] Write `rtl/spi/spi_master.sv`
  - Generic 32-bit shift-out, MSB-first, SPI mode 0 (CPOL=0, CPHA=0)
  - Parameterised `CLK_DIV` (SCLK half-period) and `LE_CYCLES` (latch enable pulse width)
  - Single-cycle `done` pulse after LE falls; `busy` held high throughout
- [✅] Write `rtl/spi/adf4351_ctrl.sv`
  - Sequences R5→R4→R3→R2→R1→R0 (R0 last triggers VCO lock)
  - Debounces `lock_detect` pin for `DEBOUNCE_CYCLES` before asserting `spi_ready`
  - `SPI_CLK_DIV` and `SPI_LE_CYCLES` parameterised for easy sim/hardware switching

### 5.2 Simulation — spi_master
- [✅] Write `sim/cocotb/spi/spi_master_tb_wrapper.sv`
- [✅] Write `sim/cocotb/spi/runner_spi.py`
- [✅] Write `sim/cocotb/spi/test_spi_master.py` — 7 tests, all passing
  - transfer_data, busy_and_done, le_pulse, sclk_idle_low, zero_word, ones_word, back_to_back

### 5.3 Simulation — adf4351_ctrl
- [✅] Write `sim/cocotb/spi/adf4351_tb_wrapper.sv`
- [✅] Write `sim/cocotb/spi/runner_adf4351.py`
- [✅] Write `sim/cocotb/spi/test_adf4351.py` — 5 tests, all passing
  - six_registers_sent, register_order, busy_during_transfer, debounce, ready_then_idle

### 5.4 Frequency calculator
- [✅] Write `rtl/spi/freq_calc.sv`
  - Sequential restoring divider: fvco/fref → INT, (remainder×MOD)/fref → FRAC
  - Combinational output divider selection (÷1…÷64) to keep VCO in 2.2–4.4 GHz
  - Fixed MOD=1000 → 25 kHz resolution at 25 MHz fref
  - R0/R1/R4 computed; R2/R3/R5 pass through as parameters
  - ~70 cycle latency (700 ns at 100 MHz)
- [✅] Write `sim/cocotb/spi/test_freq_calc.py` — 7 tests, all passing
  - integer_n_1350mhz, fractional_n, outdiv_4, r1_mod_packed, r4_base_preserved, fixed_registers, sequential_calculations

### 5.5 Remaining
- [ ] Integrate `freq_calc` + `adf4351_ctrl` + `pulse_sequencer` into `ramsey_top.sv`
- [ ] Verify ADF4351 output frequency with SDR dongle on hardware

---

## Phase 6 — End-to-end simulation test

**Goal:** Integrate all modules in cocotb and run a complete simulated ODMR sweep — fake APD counts injected at known rates, sequencer running, accumulator filling. Confirm the full data pipeline before touching any real hardware.

### 6.1 Integration wrapper
- [✅] Write `sim/cocotb/integration/integration_tb_wrapper.sv`
  - Connects `pulse_sequencer` → `photon_counter` (×2) → `shot_accumulator`
  - Signal APD (`apd_sig`) gated by `gate`; reference APD (`apd_ref`) gated by `ref_gate`
  - Both counters share `counter_clear` from sequencer
  - `spi_ready` tied high (synthesizer always ready in sim)
  - `run` → `pulse_sequencer.run`; `sweep_start` → `shot_accumulator.sweep_start`
- [✅] Write `sim/cocotb/integration/runner_integration.py`
- [✅] Write `sim/cocotb/integration/test_integration.py`

### 6.2 Test cases
- [✅] **test_single_freq_point** — N_SHOTS=3 shots, expected sig=12, ref=6 land in accumulator
- [✅] **test_multi_freq_sweep** — N_FREQ_POINTS=3 independent entries each with correct totals
- [✅] **test_freq_index_tracking** — freq_index advances with sweep_point_done, resets on sweep_start
- [✅] **test_signal_ref_independent** — sig and ref accumulate to different values (different rates)
- [✅] **test_busy_lifecycle** — busy high during sweep, low before and after

**All 5 tests passing. 5/5.**

**Note — cocotb NBA timing:** `sweep_point_done` rises in pulse_sequencer's NBA phase at clock N. `shot_accumulator` increments `wr_ptr` at clock N+1's NBA. `RisingEdge(clk)` in cocotb fires before the NBA phase of the target clock. Therefore reading `freq_index` after `sweep_point_done` requires `await ClockCycles(dut.clk, 2)` (not `RisingEdge`) to sample a value written by the previous clock's NBA.

### 6.3 Remaining (UART integration)
- [ ] Full end-to-end sim including UART: `ramsey_top.sv` in sim, trigger sweep from Python, verify `MSG_DATA` packet
  - Depends on Phase 5.5 (`ramsey_top.sv`) being complete

---

## Phase 7 — Hardware bring-up

**Goal:** Flash the bitstream and verify every output signal on an oscilloscope: laser gate timing, MW gate timing, readout vs reference window separation. Verify the ADF4351 output frequency with the SDR dongle. No APD connected yet — this phase is purely about confirming the FPGA outputs match what the simulation showed.

### Completed (April 6, 2026)
- [✅] Flash bitstream to Nexys Video (XC7A200T)
- [✅] INIT → ACK round-trip verified on real hardware (COM5, 115200 baud)
- [✅] CONFIG and START packets sending correctly
- [✅] FPGA correctly waits on lock_detect after START (ADF4351 not yet connected)

### Bugs found and fixed during bring-up
- `rst_n` on G4 (bank 35, 1.5V) was LVCMOS33 → 1.5V pull-up read as LOW → permanent reset.
  Fixed to LVCMOS15 in constraints/nexys_video.xdc.
- UART TX/RX pin assignment: uart_rx_pin=V18 (Sch=uart_rx_out), uart_tx_pin=AA19 (Sch=uart_tx_in).
  Confirmed correct after debugging with debug LEDs.

### Remaining
- [ ] ADF4351 module bench test (arriving April 23) — SPI comms, lock_detect verification
- [ ] Scope: laser_gate and mw_gate waveforms match configured timing
- [ ] Verify ADF4351 output frequency with SDR dongle

---

## Phase 8 — Real APD + first CW ODMR spectrum

**Goal:** Connect the real APD and observe the first ODMR contrast dip. Fit a Lorentzian to extract the resonance frequency and report the implied magnetic field in mT. Normalize signal counts by reference counts to remove laser intensity noise.

*(not started)*

---

## Phase 9 — Ramsey / pulsed sensing

**Goal:** Implement a Ramsey sequence — two π/2 pulses separated by a free-precession time τ. Sweep τ to extract T2* and measure AC field sensitivity η in T/√Hz. Exploit the long T2 available at 4 K. This is the primary scientific deliverable of the system.

*(not started)*

---

## Future ideas

### SNN-based adaptive readout

An SNN (spiking neural network) is a natural fit here — APD outputs are already spike trains, which is the native input format for SNNs. Possible applications once a working ODMR spectrum exists:

- **Real-time resonance tracking:** A trained SNN could track the resonance frequency continuously from the raw photon stream, avoiding the need for a full frequency sweep on every measurement.
- **Adaptive Ramsey:** Adjust the free-precession time τ or MW frequency in real-time based on recent shot outcomes — closing the feedback loop in hardware.
- **Photon discrimination:** Dark counts and laser scatter have different temporal statistics than signal photons. An SNN could learn to weight arrivals by their position within the gate window.

An SNN inference engine can be implemented on the Artix-7 using LUTs and DSPs (leaky integrate-and-fire neurons). The training would happen offline on real ODMR data, then the learned weights are loaded into the FPGA.

**Dependency:** Requires a working ODMR dataset (Phase 8+) to train on, and ties into a separate SNN project under development.

### Lock-in detection

Rather than just reading contrast from photon counts, implement **lock-in demodulation** for improved noise rejection. Modulate the MW frequency between two values (FSK) using two NCOs, and demodulate the detected signal at the modulation frequency. This produces a dispersive lineshape (derivative of the ODMR dip) rather than a Lorentzian — better suited for frequency tracking and more robust against slow drift.

For binary FSK the demodulator reduces to a conditional sign flip of each sample based on the current reference bit, followed by accumulation — no multiplier needed. Produces I and Q outputs for full phase-sensitive detection.

**Reference:** Cvetkovs et al. 2025 achieved ~100 nT/√Hz at 30 samples/second with this approach on NV-diamond. A concrete benchmark to compare against once Ramsey is working.

**Dependency:** Requires working CW ODMR (Phase 8) and a DAC output for the modulated MW drive signal.

### Resonance frequency tracking

Once lock-in detection is working, implement **auto-tracking** using a PID controller that adjusts the ADF4351 frequency in real-time based on the lock-in error signal. This eliminates the need for a full frequency sweep — the system locks onto the resonance and tracks it continuously, giving a live field measurement rather than a swept spectrum.

Cvetkovs et al. implement 8 simultaneous tracking instances cycling through a sequential FSM — useful if multiple defects or field components need to be tracked simultaneously.

**Dependency:** Lock-in detection + frequency calculator in FPGA (Phase 5 extension).

### Dear ImGui GUI upgrade

Cvetkovs et al. use **Dear ImGui** (C++) for their GUI, which includes a waterfall plot (frequency vs time as a 2D heat map) and magnetic field vector reconstruction display. Once the basic ODMR plot is working in Dear PyGui, a waterfall view and field vector overlay would be the natural next steps for the Ramsey GUI.
