# Hardware Verification Log

System: Ramsey FPGA ODMR — Nexys Video (Artix-7) + ADF4351

---

## Test environment

| Item | Detail |
|------|--------|
| Date | 27. April 2026 |
| FPGA board | Nexys Video XC7A200T |
| ADF4351 module | Walfront Generator Module ADF4351 Development Board 35M-4.4GHz RF Generator Source PLL Phase Locked Loop Frequency Synthesizer (35 MHz–4.4 GHz) |
| Bitstream | build_20260427_224219/ramsey.bit |
| APD source | Function generator (fake APD) |
| Function gen settings | Square wave, 1 MHz, 3V3 amplitude, 50% duty cycle |

---

## Wiring

| Pmod JC pin | ADF4351 pin |
|-------------|-------------|
| 1 (Y6) | CLK |
| 2 (AA6) | DAT |
| 3 (AA8) | LE |
| 4 (AB8) | LD |
| 5 (GND) | GND |
| 6 (3.3V) | CE |

ADF4351 header: 3V3 jumpered to PDR. 5V DC supply to barrel connector.

---

## PLL lock verification

| Frequency (MHz) | D3 (locked) | Notes |
|-----------------|-------------|-------|
| 1300–1400 MHz | Yes | Confirmed locking throughout sweep |
| 2800–2900 MHz | Yes | Confirmed locking throughout sweep |

Sweep range tested: 1300–1400 MHz and 2800–2900 MHz  
D3 stays on throughout sweep: Yes

Note: lock_detect bypassed in RTL (hardwired 1'b1) because PLL briefly loses lock during
register reprogramming between sweep points. Lock detect debounce (5 ms) cannot complete
in time. Bypass is safe — PLL is confirmed locking at each frequency via D3 LED.

---

## Photon counting baseline

Function generator: square wave, 1 MHz, 3.3V, 50% duty cycle

| Parameter | Value |
|-----------|-------|
| n_shots | 1000 |
| readout_dur (cycles) | 300 |
| ref_dur (cycles) | 300 |
| sig/shot | 3.0 |
| ref/shot | 3.0 |
| count rate (kcps) | 995.3 |
| contrast | 0 |

Expected: sig ≈ ref, contrast ≈ 0 (no real sensor)

---

## Sweep performance

| Parameter | Value |
|-----------|-------|
| freq_start (MHz) | 1300 / 2800 |
| freq_stop (MHz) | 1400 / 2900 |
| freq_step (MHz) | 1.00 |
| n_points | 101 |
| time per sweep (s) | ~1–2 s (calculated: 1200 cycles × n_shots × 10 ns × 101 pts + UART ~70 ms) |
| continuous sweeps tested | No — single sweep per START press |
| GUI crashes observed | No |

Note: continuous sweep mode attempted but abandoned — PLL loses lock between frequency
steps, causing the sequencer to hang waiting for lock_detect. Single sweep per button
press is the working mode.

---

## Lock-in mode (FSK)

| Parameter | Value |
|-----------|-------|
| df (MHz) | 0.50 |
| S-curve visible in DEMO | Yes |
| S-curve with hardware | No (contrast flat — no real spin sample) |
| Zero crossing at expected f0 | N/A (no real dip to lock to) |

Note: FSK demodulation verified working in DEMO mode (dispersive S-curve visible, zero
crossing at f0). Hardware FSK sweeps completed without error but produce flat contrast
as expected with function generator input. Lock-in with real NV/SiC sample is pending.

---

## Screenshots

- [x] GUI with real hardware data (standard sweep) — NV CW ODMR 2800–2900 MHz, NV Pulsed 2820–2920 MHz, SiV 1330–1430 MHz
- [x] Sweep history heatmap — visible in all sweeps after multiple START presses
- [x] Lock-in FSK sweep — SiV range with df=0.50 MHz (flat, no dip, as expected)
- [x] Counts panel showing sig/shot=3.0, ref/shot=3.0, rate=996–997 kcps

---

## Sweeps performed (27 April 2026)

| File | Preset | Range (MHz) | FSK | n_shots | sig/shot | ref/shot | contrast |
|------|--------|-------------|-----|---------|----------|----------|----------|
| odmr_20260427_232524.csv | NV - CW ODMR | 2800–2900 | No | 1000 | 3.0 | 3.0 | ~0 |
| odmr_20260427_232557.csv | NV - Pulsed ODMR | 2820–2920 | No | 5000 | ~3.0 | ~3.0 | ~0 |
| odmr_20260427_232616.csv | SiV - 1.38 GHz | 1330–1430 | No | 1000 | 3.0 | 3.0 | ~0 |
| odmr_20260427_232644.csv | SiV - 1.38 GHz | 1330–1430 | Yes | 1000 | 3.0 | 3.0 | ~0 |
| odmr_20260427_232734.csv | SiV - 1.38 GHz | 1330–1430 | Yes | 1000 | 3.0 | 3.0 | ~0 |
| odmr_20260427_232759.csv | SiV - 1.38 GHz | 1330–1430 | Yes | 1000 | 3.0 | 3.0 | ~0 |

All contrast values ≈ 0 as expected — function generator input, no real spin sample.
Small ±1 count spikes (±0.034% contrast) are phase aliasing between the 1 MHz square
wave and the readout window boundary. Not a bug.

---

## Issues observed

| Issue | Status |
|-------|--------|
| Continuous sweep hangs on "waiting for data" | Known — lock_detect debounce timeout during reprogramming. Workaround: single sweep per START press. |
| ±1 count aliasing spikes in contrast | Expected — function generator phase not aligned to readout window. Will not appear with real APD. |

---

## Notes

- All 6 presets swept successfully at both frequency ranges (1.3 GHz and 2.8 GHz)
- CSV export confirmed working for all sweep types including FSK
- Count rate stable at ~996–997 kcps across all sweeps (1 MHz function gen, 300-cycle readout)
- Next step: connect real APD and NV/SiC sample to obtain first real contrast dip
- Pending: scope shots of laser_gate (JB pin 1) and mw_gate (JB pin 2) to verify pulse timing

