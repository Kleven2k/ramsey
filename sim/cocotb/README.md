# Verification

All RTL modules are verified with [cocotb](https://www.cocotb.org/) at 100 MHz. Each testbench drives the DUT with a software clock and asserts cycle-accurate behaviour against known-good values.

## Running the tests

Requires [Icarus Verilog](https://bleyer.org/icarus/) and cocotb in your venv:

```bash
pip install cocotb
cd sim/cocotb/<module>
python runner_<module>.py
```

All 49 tests across 8 modules should pass.

## Overview

| Module | Tests | Source |
|--------|-------|--------|
| `photon_counter` | 5 | [photon_counter/](photon_counter/) |
| `pulse_sequencer` | 5 | [pulse_sequencer/](pulse_sequencer/) |
| `shot_accumulator` | 5 | [accumulator/](accumulator/) |
| `uart` | 7 | [uart/](uart/) |
| `spi_master` | 7 | [spi/](spi/) |
| `adf4351_ctrl` | 5 | [spi/](spi/) |
| `freq_calc` | 7 | [spi/](spi/) |
| `integration` | 5 | [integration/](integration/) |

---

## photon_counter

Counts TTL rising edges on `apd_in` while `gate` is high. The count is held after the gate closes and cleared on the next `counter_clear` pulse before the following readout window.

| Test | What it checks |
|------|----------------|
| `test_basic_count` | Pulses injected during gate window are counted correctly |
| `test_gate_inhibit` | Pulses outside the gate window are ignored |
| `test_hold_after_gate` | Count register holds its value after gate goes low |
| `test_clear` | `counter_clear` resets the count to zero |
| `test_max_rate` | Pulses at minimum 4-cycle period (25 MHz) — all counted correctly |

---

## pulse_sequencer

Generates the laser gate, MW gate, counter clear, and reference gate signals with nanosecond-precision timing. Supports both CW-ODMR (single MW pulse) and Ramsey (two π/2 pulses with free-precession gap).

| Test | What it checks |
|------|----------------|
| `test_cw_single_shot` | Init / drive / readout phase durations match configured values |
| `test_shot_loop` | Sequencer repeats for exactly `n_shots` and asserts `sweep_point_done` |
| `test_ramsey` | Two MW pulses with correct `dead_time` gap between them |
| `test_counter_clear` | `counter_clear` is asserted before each readout window opens |
| `test_busy` | `busy` goes high on `run` and low after final shot completes |

---

## shot_accumulator

Accumulates photon counts across multiple shots for each frequency point in a sweep. Signal and reference counts are stored in separate entries indexed by `freq_index`, which advances on each `sweep_point_done` and resets on `sweep_start`.

| Test | What it checks |
|------|----------------|
| `test_single_shot_signal` | Signal count written to correct address after one shot |
| `test_single_shot_reference` | Reference count stored independently from signal |
| `test_accumulation_multi_shot` | Counts from repeated shots add up correctly |
| `test_freq_index_advances` | `freq_index` increments on `sweep_point_done` |
| `test_run_resets_pointer` | `sweep_start` resets write pointer back to address 0 |

---

## uart

Implements the full packet framing layer: `[0xAA][TYPE][LEN_HI][LEN_LO][PAYLOAD][CRC]` where CRC is XOR of all payload bytes. Handles both TX and RX paths.

| Test | What it checks |
|------|----------------|
| `test_tx_byte` | Single byte transmitted with correct start/stop framing at 115200 baud |
| `test_rx_byte` | Single byte received and decoded correctly |
| `test_rx_packet` | Full packet received; header, type, length, payload, and CRC all parsed |
| `test_rx_bad_crc` | Packet with corrupted CRC is rejected |
| `test_tx_packet` | Full packet transmitted with correct byte order |
| `test_tx_zero_payload` | Zero-length payload packet handled correctly |
| `test_rx_noise_recovery` | Receiver recovers cleanly after a framing error |

---

## spi_master

32-bit SPI master clocked at a configurable rate. Shifts data MSB-first on MOSI, pulses LE (latch enable) after the final bit, and asserts `done` for one cycle on completion.

| Test | What it checks |
|------|----------------|
| `test_transfer_data` | 32-bit word clocked out MSB-first; MOSI matches input bit-by-bit |
| `test_busy_and_done` | `busy` high during transfer; `done` pulses for exactly one cycle |
| `test_le_pulse` | LE asserted after final SCLK edge with correct width |
| `test_sclk_idle_low` | SCLK is low when no transfer is in progress |
| `test_zero_word` | All-zero word transferred without glitches |
| `test_ones_word` | All-ones word transferred without glitches |
| `test_back_to_back` | Two consecutive transfers complete without gap errors |

---

## adf4351_ctrl

Controls the ADF4351 PLL by programming all six registers (R5 → R0) over SPI on each frequency update. The register sequence must be sent in descending order per the ADF4351 datasheet.

| Test | What it checks |
|------|----------------|
| `test_six_registers_sent` | Exactly six SPI transfers occur per frequency update |
| `test_register_order` | Registers are sent R5 first, R0 last |
| `test_busy_during_transfer` | `busy` is asserted for the full six-register sequence |
| `test_debounce` | `lock_detect` glitch shorter than debounce window does not assert `spi_ready` |
| `test_ready_then_idle` | `spi_ready` correctly gates the next transfer |

---

## freq_calc

Combinational module that converts a target frequency (in kHz) to the six ADF4351 register words. Computes integer-N and fractional-N PLL divider values, selects the output divider, and packs the result into the ADF4351 register format.

| Test | What it checks |
|------|----------------|
| `test_integer_n_1350mhz` | Integer-N divider words correct at 1350 MHz (SiC V2) |
| `test_fractional_n` | Fractional-N MOD/FRAC values correct for non-integer target |
| `test_outdiv_4` | Output divider field set correctly when frequency requires division |
| `test_r1_mod_packed` | MOD value packed into R1 register bits [14:3] |
| `test_r4_base_preserved` | Fixed R4 base fields not overwritten by frequency calculation |
| `test_fixed_registers` | R3, R5 contain correct fixed values independent of frequency |
| `test_sequential_calculations` | Back-to-back calculations for different frequencies produce independent results |

*Register values cross-checked against ADF4351 datasheet equations*

---

## integration

End-to-end testbench wiring `pulse_sequencer → photon_counter × 2 → shot_accumulator`. APD pulses are injected by background coroutines at known rates each time a gate window opens, and the accumulated totals are read back and compared to expected values.

Signal path: `apd_sig → photon_counter (gate) → shot_accumulator.sig_count`  
Reference path: `apd_ref → photon_counter (ref_gate) → shot_accumulator.ref_count`

| Test | What it checks |
|------|----------------|
| `test_single_freq_point` | One frequency point: N shots accumulate to expected totals |
| `test_multi_freq_sweep` | Multiple frequency points each accumulate independently |
| `test_freq_index_tracking` | `freq_index` advances per point and resets on `sweep_start` |
| `test_signal_ref_independent` | Signal and reference paths accumulate to different values |
| `test_busy_lifecycle` | `busy` high during sweep, low before and after |

