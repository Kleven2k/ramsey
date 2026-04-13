# Ramsey

### Description

> Open-source FPGA-based pulse sequencer and photon counting system for ODMR readout of spin defects in SiC and diamond. Targets the Nexys Video Artix-7 board. Replaces commercial instruments (PulseBlaster, NI DAQ) with a ~$200 dev board. Designed for integration with cryogenic quantum sensing experiments.

### Folder structure
```
ramsey/
├── rtl/
│   ├── counter/
│   │   └── photon_counter.sv    # Gated TTL photon counter with 2-FF synchronizer
│   ├── uart/
│   │   ├── uart_rx.sv           # UART byte receiver
│   │   ├── uart_tx.sv           # UART byte transmitter
│   │   ├── uart_top.sv          # RX + TX wrapper
│   │   └── uart_interface.sv    # Packet framing layer (PC comms)
│   ├── sequencer/
│   │   └── pulse_sequencer.sv   # 7-state ODMR timing FSM
│   ├── accumulator/
│   │   └── shot_accumulator.sv  # BRAM read-modify-write shot averager
│   ├── spi/
│   │   ├── spi_master.sv        # Generic 32-bit SPI master (mode 0, MSB-first)
│   │   ├── adf4351_ctrl.sv      # ADF4351 register sequencer + lock-detect debounce
│   │   └── freq_calc.sv         # INT/FRAC/MOD calculator from target frequency
│   └── ramsey_top.sv            # Top-level: connects all sub-modules to I/O
├── constraints/                 # Vivado XDC pin constraints (planned)
├── scripts/
│   └── build.tcl                # Vivado batch build — synth + impl + bitstream
├── sim/
│   └── cocotb/
│       ├── photon_counter/      # 5 tests — all passing
│       │   ├── photon_counter_tb_wrapper.sv
│       │   ├── runner_photon_counter.py
│       │   └── test_photon_counter.py
│       ├── uart/                # 7 tests — all passing
│       │   ├── uart_tb_wrapper.sv
│       │   ├── runner_uart.py
│       │   └── test_uart.py
│       ├── pulse_sequencer/     # 5 tests — all passing
│       │   ├── pulse_sequencer_tb_wrapper.sv
│       │   ├── runner_pulse_sequencer.py
│       │   └── test_pulse_sequencer.py
│       ├── accumulator/         # 5 tests — all passing
│       │   ├── shot_accumulator_tb_wrapper.sv
│       │   ├── runner_shot_accumulator.py
│       │   └── test_shot_accumulator.py
│       ├── spi/                 # 19 tests — all passing
│           ├── spi_master_tb_wrapper.sv
│           ├── runner_spi.py
│           ├── test_spi_master.py
│           ├── adf4351_tb_wrapper.sv
│           ├── runner_adf4351.py
│           ├── test_adf4351.py
│           ├── freq_calc_tb_wrapper.sv
│           ├── runner_freq_calc.py
│           └── test_freq_calc.py
│       └── integration/         # 5 tests — all passing
│           ├── integration_tb_wrapper.sv
│           ├── runner_integration.py
│           └── test_integration.py
├── python/
│   ├── uart_comm.py             # Packet send/receive backend
│   ├── gui.py                   # Dear PyGui control GUI
│   └── lorentzian_fit.py        # Fit contrast dip, extract resonance frequency (planned)
├── docs/
│   ├── system_overview.md
│   ├── plan.md                  # Implementation progress tracker
│   ├── fpga_odmr_roadmap.svg
│   ├── ADF4351.pdf
│   └── research/
│       ├── research_context.md  # Scientific motivation, expected results, applications
│       ├── reading_guide.md     # What to study, questions to answer, papers to read
│       ├── SiC/                 # SiC-specific papers
│       ├── coreNV_defect_physics/
│       └── professor/           # Papers from the lab
└── .gitignore
```

## RTL Modules

### photon_counter.sv

Counts TTL pulses from an APD detector within a timed gate window.

```
apd_in (async) → [FF1] → [FF2] → [FF3] → edge detect → gate? → count++
                  sync_0   sync_1   sync_2
```

- **Synchronizer (FF1 + FF2):** `apd_in` arrives asynchronously and could change at any point relative to the clock edge. Sampling it directly risks metastability. Two back-to-back FFs give the signal time to settle before it is used by any logic.
- **Edge detector (FF3):** Compares `sync_1` (now) against `sync_2` (one cycle ago). When `sync_1=1` and `sync_2=0`, a rising edge just occurred. Produces a single-cycle pulse per photon.
- **Gated counter:** Increments only when both `gate` is high and a rising edge is detected. Holds its value when `gate` goes low — the pulse sequencer reads it out at the end of the measurement window. Only `clear` or `rst` resets it.

The 3-cycle total latency (2 sync + 1 edge detect) is irrelevant for counting — the gate just needs to stay open long enough to capture all photons in the readout window. Verified in cocotb simulation at up to 10 MHz input rate.

---

### uart_interface.sv

Single module owning both RX and TX paths, the baud rate generator, packet framing, and CRC. Wraps `uart_top` internally. The rest of the FPGA only sees application-level signals — no raw UART bytes leave the module.

```
                         ┌──────────────────────────────┐
                         │       uart_interface.sv       │
                         │                               │
  rx_msg_type     ◄──────│  RX path                      │◄──── rx_pin
  rx_msg_len      ◄──────│  • 2-FF sync on rx_pin        │
  rx_payload_byte ◄──────│  • start/data/stop detect     │
  rx_payload_valid◄──────│  • packet framing             │
  rx_msg_done     ◄──────│  • CRC accumulation           │
  rx_crc_ok       ◄──────│                               │
                         │                               │
  tx_msg_type    ───────►│  TX path                      │────► tx_pin
  tx_msg_len     ───────►│  • header + type + length     │
  tx_payload_byte───────►│  • payload byte stream        │
  tx_payload_req  ◄──────│  • CRC append                 │
  tx_send        ───────►│  • start bit guard            │
  tx_busy         ◄──────│                               │
                         └──────────────────────────────┘
```

**Application interface signals:**

| Signal | Dir | Description |
|---|---|---|
| `rx_msg_type` | Out | Message type of the current packet |
| `rx_msg_len` | Out | Payload length in bytes |
| `rx_payload_byte` | Out | Current payload byte (streamed) |
| `rx_payload_valid` | Out | Single-cycle pulse per payload byte |
| `rx_msg_done` | Out | Single-cycle pulse on last payload byte |
| `rx_crc_ok` | Out | Single-cycle pulse after CRC byte — high if CRC matched |
| `tx_msg_type` | In | Message type to send |
| `tx_msg_len` | In | Payload length (0 for no payload) |
| `tx_payload_byte` | In | Next payload byte from application |
| `tx_payload_req` | Out | Pulse to advance to next payload byte |
| `tx_send` | In | Pulse to start sending a packet |
| `tx_busy` | Out | High while transmission in progress |

**Packet frame (all messages):**
```
[0xAA] [TYPE: 1B] [LENGTH: 2B big-endian] [PAYLOAD: N B] [CRC: 1B]
```
CRC = XOR of all payload bytes. Header `0xAA`, type, and length bytes are not included in the CRC.

**Message types:**

| Type | Direction | Name | Payload |
|---|---|---|---|
| `0x01` | PC → FPGA | INIT | ADF4351 R1–R5 (5 × uint32) |
| `0x02` | PC → FPGA | CONFIG | See CONFIG payload table below |
| `0x03` | PC → FPGA | START | None |
| `0x04` | FPGA → PC | ACK | None |
| `0x05` | FPGA → PC | DATA | signal_counts[] + ref_counts[] (N × uint32 each) |
| `0x06` | FPGA → PC | STATUS | 1 byte: 0=IDLE 1=CONFIGURED 2=RUNNING 3=DONE 4=ERROR |

**CONFIG payload (0x02):**

| Bytes | Field | Type | Description |
|-------|-------|------|-------------|
| 0–1 | `n_points` | uint16 | Number of frequency table entries (2× sweep points in lock-in mode) |
| 2–5 | `n_shots` | uint32 | Shots averaged per point |
| 6–9 | `init_dur` | uint32 | Laser init pulse, clock cycles (1 cycle = 10 ns) |
| 10–13 | `mw_dur` | uint32 | MW pulse width, clock cycles |
| 14–17 | `readout_dur` | uint32 | Readout window, clock cycles |
| 18–21 | `ref_dur` | uint32 | Reference window, clock cycles |
| 22–25 | `dead_time` | uint32 | Dead time between windows, clock cycles |
| 26 | `lock_in_en` | uint8 | 1 = FSK lock-in mode, 0 = standard sweep |
| 27–30 | `delta_f_khz` | uint32 | FSK half-step in kHz (ignored when lock_in_en=0) |
| 31+ | `freq_table` | uint32 × N | Target frequency in kHz per entry — FPGA freq_calc converts to ADF4351 registers |

For Ramsey: `mw_dur` = π/2 pulse width, `dead_time` = free-precession time τ. No protocol changes needed.

**Lock-in (FSK) mode:**

When `lock_in_en=1`, Python builds an interleaved frequency table — for each sweep point at frequency f, two entries are sent: f+Δf then f−Δf. The FPGA sweeps all 2N entries normally. On receipt, Python demodulates the pairs:

```
error[i] = contrast(f_i + df) - contrast(f_i - df)   ≈  2·df · dC/df
```

This produces a dispersive (derivative) lineshape. The resonance frequency is the zero crossing. The FPGA has no knowledge of lock-in mode — it stores `lock_in_en_r` and `delta_f_khz_r` for future use by a hardware tracking loop.

**Workflow:** run standard mode first to see the Lorentzian dip and measure linewidth. Set df ≈ linewidth/2, then enable lock-in for improved SNR near resonance.

**Typical exchange:**
```
PC   →  FPGA :  INIT    (ADF4351 fixed registers)
FPGA →  PC   :  ACK
PC   →  FPGA :  CONFIG  (timing + frequency table)
FPGA →  PC   :  ACK
PC   →  FPGA :  START
FPGA →  PC   :  DATA    (signal + ref counts, sent when sweep completes)
```

**TX timing note:** `tx_payload_req` pulses once per byte. The application has ~8680 clock cycles (one full UART byte at 115200 baud: 10 bit-periods × 868 cycles/bit) to present the next byte on `tx_payload_byte` — sufficient for BRAM-backed sources. A start-bit guard (`tx_can_send = !tx_busy && !tx_start`) prevents double-triggering on the one-cycle gap between asserting the start pulse and `uart_tx` raising `tx_busy`.

---

### pulse_sequencer.sv

Timing engine for ODMR experiments. Sequences one shot — laser init, two MW pulses with optional free-precession gap, readout window, reference window — then repeats `n_shots` times before signalling the accumulator and returning to IDLE.

```
IDLE → INIT_PULSE → MW1 → DEAD → MW2 → READOUT → REFERENCE ──┐
  ▲                                                            │ shot_count + 1 < n_shots
  │  sweep_point_done + next_freq                             ▼
  └────────────────────────────────────────────────────── (repeat)
```

**Ports:**

| Signal | Dir | Description |
|---|---|---|
| `run` | In | Single-cycle pulse to start a sweep point |
| `n_shots [31:0]` | In | Shots to average per frequency point |
| `init_dur [31:0]` | In | Laser init pulse duration (clock cycles) |
| `mw_dur [31:0]` | In | MW pulse duration — π/2 for Ramsey (clock cycles) |
| `dead_time [31:0]` | In | Free precession time τ — 0 for CW ODMR (clock cycles) |
| `readout_dur [31:0]` | In | Signal readout window duration (clock cycles) |
| `ref_dur [31:0]` | In | Reference window duration (clock cycles) |
| `spi_ready` | In | ADF4351 has settled at the new frequency |
| `laser_gate` | Out | High during INIT_PULSE and READOUT/REFERENCE windows |
| `mw_gate` | Out | High during MW1 and MW2 |
| `gate` | Out | Photon counter enable — high during READOUT only |
| `ref_gate` | Out | Reference counter enable — high during REFERENCE only |
| `counter_clear` | Out | Single-cycle pulse once per shot (in MW2, before READOUT opens) |
| `sweep_point_done` | Out | Single-cycle pulse when all n_shots are complete |
| `next_freq` | Out | Single-cycle pulse requesting next frequency step |
| `busy` | Out | High while sequencer is running |

**CW ODMR vs Ramsey:**
- CW: `dead_time = 0` — MW1 and MW2 fuse into one continuous pulse
- Ramsey: `dead_time = τ`, `mw_dur` = π/2 pulse width

All duration inputs are in clock cycles (1 cycle = 10 ns at 100 MHz).

---

### shot_accumulator.sv

Accumulates signal and reference photon counts into separate BRAM arrays, one entry per frequency point. Triggered by the falling edge of `gate` (signal window) and `ref_gate` (reference window) from `pulse_sequencer`. The host reads back accumulated data via a registered read port after `sweep_point_done`.

**Read-modify-write pipeline (3 cycles):**
```
Cycle 0: gate falls → latch count + address
Cycle 1: BRAM read data valid
Cycle 2: write back (existing + new count)
```

**Ports:**

| Signal | Dir | Description |
|---|---|---|
| `gate` | In | Signal readout window (from pulse_sequencer) |
| `ref_gate` | In | Reference window (from pulse_sequencer) |
| `sweep_point_done` | In | Advance write pointer to next frequency point |
| `sweep_start` | In | Reset write pointer to 0 for new sweep |
| `sig_count [31:0]` | In | Photon count from signal window (from photon_counter) |
| `ref_count [31:0]` | In | Photon count from reference window (from photon_counter) |
| `rd_addr` | In | Host read address |
| `rd_sig [31:0]` | Out | Accumulated signal counts at rd_addr |
| `rd_ref [31:0]` | Out | Accumulated reference counts at rd_addr |
| `freq_index` | Out | Current write pointer (active frequency point) |

Depth is parameterised (default 1024 points). Separate `sig_mem` / `ref_mem` arrays keep addressing simple and allow signal and reference to be read independently.

---

### spi_master.sv

Generic 32-bit SPI master. Shifts data out MSB-first in SPI mode 0 (CPOL=0, CPHA=0), then pulses LE (latch enable) to commit the word to the peripheral. Designed for write-only peripherals such as the ADF4351.

- SCLK frequency = `clk / (2 × CLK_DIV)` — parameterised, default 10 MHz
- Single-cycle `done` pulse after LE falls
- `busy` held high for the entire transfer including LE

---

### adf4351_ctrl.sv

Programs the ADF4351 PLL synthesizer by writing all 6 registers in the order R5→R4→R3→R2→R1→R0 (R0 last triggers VCO lock). After R0 is written, waits for `lock_detect` to assert and debounces it for `DEBOUNCE_CYCLES` before asserting `spi_ready`.

```
load → [R5] → [R4] → [R3] → [R2] → [R1] → [R0] → DEBOUNCE → spi_ready
```

Internally instantiates `spi_master`. `SPI_CLK_DIV` and `SPI_LE_CYCLES` are parameterised for easy switching between simulation (fast) and hardware (10 MHz SCLK).

---

### freq_calc.sv

Computes ADF4351 register values from a target output frequency in kHz. Replaces the need to send pre-computed register values from the PC — the host only needs to send a frequency.

**Algorithm:**
1. Select output divider D ∈ {1,2,4,8,16,32,64} so VCO frequency falls in 2.2–4.4 GHz
2. Restoring division: fvco / fref → INT + remainder
3. Multiply remainder by MOD, divide by fref → FRAC
4. Pack INT, FRAC, MOD, OUTDIV into R0/R1/R4; R2/R3/R5 pass through as parameters

**Formula:** `fout = fref × (INT + FRAC/MOD) / OUTDIV`

With fixed MOD=1000 and fref=25 MHz this gives 25 kHz resolution. Total latency ≈ 70 cycles (700 ns) — negligible compared to PLL lock time (~1 ms).

---

## Simulation

All modules are verified with [cocotb](https://www.cocotb.org/) against an Icarus Verilog backend. No Makefile — each module has its own Python runner that compiles with `iverilog` and executes with `vvp`.

```
python sim/cocotb/<module>/runner_<module>.py          # run all tests
python sim/cocotb/<module>/runner_<module>.py <test>   # run one test
```

VCD waveforms are written to `sim/cocotb/<module>/sim_build_<module>/dump.vcd` and can be opened in GTKWave.

### photon_counter — 5 tests, all passing

| Test | What it checks |
|---|---|
| `test_basic_count` | N pulses during gate window → `count == N` |
| `test_gate_inhibit` | Pulses with gate low the whole time → `count == 0` |
| `test_hold_after_gate` | Count does not change after gate goes low |
| `test_clear` | `clear` mid-window resets count, counting resumes |
| `test_max_rate` | 10 MHz pulse rate (one pulse every 10 cycles), all counted correctly |

### pulse_sequencer — 5 tests, all passing

| Test | What it checks |
|---|---|
| `test_cw_single_shot` | laser_gate, mw_gate, gate durations match init_dur/mw_dur/readout_dur |
| `test_shot_loop` | n_shots=3: counter_clear fires 3×, sweep_point_done fires once |
| `test_ramsey` | dead_time gap between MW1 falling and MW2 rising matches dead_time |
| `test_counter_clear` | counter_clear pulses exactly once per shot (in MW2 before readout) |
| `test_busy` | busy high on run, low when returning to IDLE |

### shot_accumulator — 5 tests, all passing

| Test | What it checks |
|---|---|
| `test_single_shot_signal` | Signal window closes → count lands in sig_mem[0] |
| `test_single_shot_reference` | Reference window closes → count lands in ref_mem[0] |
| `test_accumulation_multi_shot` | 3 shots sum correctly (not overwrite) |
| `test_freq_index_advances` | sweep_point_done increments pointer; each freq point independent |
| `test_run_resets_pointer` | run resets freq_index to 0 |

### spi_master — 7 tests, all passing

| Test | What it checks |
|---|---|
| `test_transfer_data` | 0xDEADBEEF shifts out MSB-first, sampled on every SCLK rising edge |
| `test_busy_and_done` | busy high during transfer, done single-cycle after LE falls |
| `test_le_pulse` | LE rises after last bit, falls before done |
| `test_sclk_idle_low` | SCLK=0 at rest (SPI mode 0) |
| `test_zero_word` | All-zero word: sdata stays low for all 32 bits |
| `test_ones_word` | All-ones word: sdata stays high for all 32 bits |
| `test_back_to_back` | Two consecutive transfers both produce correct data |

### adf4351_ctrl — 5 tests, all passing

| Test | What it checks |
|---|---|
| `test_six_registers_sent` | Exactly 6 LE pulses fired (one per register) |
| `test_register_order` | Data order is R5→R4→R3→R2→R1→R0 |
| `test_busy_during_transfer` | busy high from load until spi_ready |
| `test_debounce` | spi_ready does not assert if lock_detect glitches before debounce completes |
| `test_ready_then_idle` | After spi_ready, controller returns to IDLE; spi_ready is single-cycle |

### freq_calc — 7 tests, all passing

| Test | What it checks |
|---|---|
| `test_integer_n_1350mhz` | 1350 MHz: INT=108, FRAC=0, OUTDIV÷2 |
| `test_fractional_n` | 1350.050 MHz: FRAC=4 computed correctly |
| `test_outdiv_4` | 800 MHz: ÷4 divider selected |
| `test_r1_mod_packed` | R1 always contains MOD=1000 and PHASE=1 |
| `test_r4_base_preserved` | R4 bits outside [22:20] unchanged from R4_BASE |
| `test_fixed_registers` | R2/R3/R5 match configured parameters |
| `test_sequential_calculations` | Two back-to-back calculations produce independent correct results |

### integration — 5 tests, all passing

End-to-end test wiring `pulse_sequencer` → `photon_counter` (×2) → `shot_accumulator`. Background coroutines inject fake APD pulses at known rates during each gate/ref_gate window. N_SHOTS=3, N_FREQ_POINTS=3, SIG_PULSES=4/shot, REF_PULSES=2/shot.

| Test | What it checks |
|---|---|
| `test_single_freq_point` | 3 shots at one freq point → sig=12, ref=6 in accumulator |
| `test_multi_freq_sweep` | 3 freq points each independently accumulate correct totals |
| `test_freq_index_tracking` | freq_index increments after each sweep_point_done, resets on sweep_start |
| `test_signal_ref_independent` | sig and ref land in separate entries with different values |
| `test_busy_lifecycle` | busy high during sweep, low before and after |

### uart_interface — 7 tests, all passing

| Test | What it checks |
|---|---|
| `test_tx_byte` | Smoke test: ACK packet round-trips through `uart_recv_packet` |
| `test_rx_byte` | Single raw byte received without simulation error |
| `test_rx_packet` | Valid 3-byte CONFIG packet: `rx_msg_type` and `rx_msg_len` latched correctly |
| `test_rx_bad_crc` | Corrupted CRC byte: `rx_crc_ok` never fires |
| `test_tx_packet` | 3-byte DATA packet with `tx_payload_req` handshake: full frame verified |
| `test_tx_zero_payload` | ACK frame verified byte-by-byte: `[0xAA][0x04][0x00][0x00][0x00]` |
| `test_rx_noise_recovery` | 4 garbage bytes before header: FSM discards them and parses the valid packet |

---

## Python Control GUI

Two-layer structure: a serial backend (`uart_comm.py`) that only deals with packet framing, and a GUI (`gui.py`) on top. The backend can also be imported directly for scripted sweeps.

**Stack:** `pyserial` · `Dear PyGui` · `ctypes` · `numpy` (planned)

```
python/
├── uart_comm.py      ← packet send/receive, no GUI code
├── gui.py            ← control GUI, calls uart_comm as backend
├── lorentzian_fit.py ← scipy curve_fit on contrast dip, returns f0/FWHM/fitted_y
├── synthetic.py      ← generates synthetic MSG_DATA payloads with Poisson noise (DEMO mode)
└── test_uart.py      ← standalone INIT/ACK round-trip test script
```

### GUI elements

**Connection bar** (top, always visible)

| Element | What it does |
|---|---|
| Port dropdown | Lists available serial ports via `uart_comm.list_ports()` |
| ↺ button | Rescans and refreshes the port list |
| Connect button | Opens the serial port and starts the background reader thread. Turns green when connected, red when disconnected. Label toggles between Connect / Disconnect |
| Status text | Shows the last event: connected, ACK received, error message, data received |

**Control panel** (left)

| Element | What it does |
|---|---|
| n_shots | Number of shots averaged per frequency point — more shots = better SNR |
| init | Laser initialization pulse, clock cycles |
| MW | MW pulse duration — full pulse for CW ODMR, π/2 width for Ramsey |
| dead | Dead time — 0 for CW ODMR, free-precession time τ for Ramsey |
| readout | Readout window duration, clock cycles |
| ref | Reference window duration, clock cycles |
| start (MHz) | Lower bound of the frequency sweep |
| stop (MHz) | Upper bound of the frequency sweep |
| step (MHz) | Frequency step size |
| enable (lock-in) | Toggles FSK lock-in mode — sends interleaved ±df freq table |
| df (MHz) | FSK half-step — set to ~linewidth/2 after a standard sweep |
| INIT button | Sends `MSG_INIT` — loads ADF4351 fixed registers |
| CONFIG button | Packs all parameters into `MSG_CONFIG` and sends to FPGA |
| START button | Sends `MSG_START` — triggers sweep; FPGA responds with `MSG_DATA` |
| DEMO button | Runs a synthetic ODMR sweep locally without hardware |

**Plot panel** (right)

| Element | What it does |
|---|---|
| ODMR Spectrum plot | X axis: frequency (MHz), Y axis: normalized contrast. Line series `contrast_series` is updated when a `MSG_DATA` packet arrives |

### Packet flow

```
[INIT]   → MSG_INIT          → FPGA programs ADF4351 registers
           MSG_ACK            ← status: "ACK received"
[CONFIG] → MSG_CONFIG payload → FPGA stores timing + frequency parameters
           MSG_ACK            ← status: "ACK received"
[START]  → MSG_START          → FPGA runs sweep
           MSG_DATA payload   ← contrast points pushed to plot
```

Python is sufficient for this role — the bottleneck is the 115200 baud UART link (~70 ms to receive a 100-point sweep), not the GUI or parsing. If the system ever moves toward higher-throughput applications (e.g. medical imaging / magnetometry over a 2D sample), the reconstruction core would move to C++ or Rust with Python retained as the orchestration and display layer.

**Hardware status (April 2026):** INIT → ACK round-trip verified on Nexys Video. CONFIG and START
sending correctly. ADF4351 module arriving April 23 — SPI bring-up and frequency verification pending.

---

## Hardware Setup

### Signal chain overview

```
                    ┌─────────────────────────────────────┐
                    │              FPGA                    │
                    │                                      │
                    │  SPI ──────────────► ADF4351         │
                    │  MW_GATE ──────────► RF switch ──► amplifier ──► coil/antenna
                    │  LASER_GATE ───────► AOM driver  ──► AOM ──► fiber ──► sample
                    │  APD_IN ◄──────────── APD  ◄──── fluorescence from sample
                    │  UART ◄────────────► PC             │
                    └─────────────────────────────────────┘
```

### FPGA signal interface

| Signal | Direction | Notes |
|---|---|---|
| `spi_clk / mosi / cs` | Out | ADF4351 programming |
| `mw_gate` | Out | To RF switch (low-power side, before amplifier) |
| `laser_gate` | Out | To AOM driver — gates spin initialization and readout |
| `apd_in` | In | TTL pulses from APD, 10+ MHz capable |
| `uart_tx / rx` | Bidirectional | PC communication |

### Key hardware decisions

**Microwave path**
- ADF4351 outputs ~0 dBm. Requires an external amplifier (+20–30 dB, e.g. ZHL-16W-43+) before the sample.
- RF switch (e.g. ZASWA-2-50DR+) goes between the ADF4351 and the amplifier — switch on the low-power side for protection and cleaner isolation.
- Coil or antenna geometry depends on the cryostat sample mount. Typically a small loop or stripline directly on the mount.

**Laser path**
- Green laser (532 nm typical) must be gated per pulse sequence.
- An AOM (acousto-optic modulator) is the standard approach for nanosecond-precision gating of a CW laser. The FPGA drives the AOM driver with `LASER_GATE`.
- Without an AOM, direct laser diode modulation or a mechanical shutter can support CW ODMR but not pulsed experiments.

**Detection path**
- APD (e.g. Excelitas SPCM) outputs one TTL pulse per detected photon directly into FPGA GPIO.
- Optical filtering (notch or longpass) on the collection path is required to reject laser scatter from APD counts — this is an optics concern, not FPGA.
- At cryogenic temperatures an SNSPD may be used instead; output characteristics differ from APD.

**Cryostat interface**
- FPGA and ADF4351 board remain at room temperature.
- Only the sample, coil, and optionally the detector are cold.
- RF and signal lines pass through the cryostat via SMA feedthroughs; optical path via fiber feedthrough.

## Roadmap
![alt text](fpga_odmr_roadmap.svg)