# Ramsey

Open-source FPGA-based pulse sequencer and photon counter for optically detected magnetic resonance (ODMR) readout of spin defects in diamond and silicon carbide.

Targets the **Nexys Video Artix-7** development board (~$200). Designed to replace commercial instruments (PulseBlaster, NI DAQ) in quantum sensing experiments.

## What it does

- Generates laser and microwave pulse sequences for pulsed ODMR
- Counts photons in gated readout and reference windows
- Streams contrast data over UART to a Python GUI in real time
- Fits Lorentzian dips to extract resonance frequency → magnetic field
- Lock-in (FSK) detection mode for improved noise rejection

## Hardware

| Component | Part | Purpose |
|-----------|------|---------|
| FPGA board | Nexys Video (Artix-7 XC7A200T) | Pulse sequencer + photon counter |
| MW source | ADF4351 module | 35 MHz – 4.4 GHz sweep |
| Detector | Silicon APD (TBD) | Single-photon counting |

## Repository layout

```
rtl/          SystemVerilog source — pulse sequencer, photon counter, UART, SPI
sim/          cocotb testbenches
constraints/  Nexys Video XDC pin constraints
scripts/      Vivado build TCL script
python/       GUI, Lorentzian fitting, UART comms, characterization script
notebooks/    Physics background (ODMR, Zeeman, shot noise, lock-in)
docs/         System overview, project plan, research notes
data/         Characterization data schema
```

## Getting started

### Build the bitstream

Requires Vivado 2023.x:

```bash
vivado -mode batch -source scripts/build.tcl
```

### Run the GUI

```bash
cd python
pip install -r requirements.txt   # or activate your venv
python gui.py
```

### Run simulations

```bash
cd sim/cocotb/<module>
python runner_<module>.py
```

## Sensors targeted

| Defect | Host | Zero-field splitting |
|--------|------|---------------------|
| NV center | Diamond | 2870 MHz |
| V2 silicon vacancy | 4H-SiC | 1350 MHz |
| PL6 | 4H-SiC | 1380 MHz |

## Status

- FPGA pulse sequencer and photon counter: working
- UART protocol and Python GUI: working
- ADF4351 SPI driver: implemented, bench test pending (module in transit)
- Lock-in (FSK) mode: implemented, not yet tested on hardware
- First light: pending ADF4351 arrival

## References

- [ODMR lab manual, Uni Siegen](https://www.physik.uni-siegen.de/nano-optics/education/teaching/lab_courses/odmr_manual_v1.3.1.pdf)
