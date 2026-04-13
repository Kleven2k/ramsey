# Research Context

Scientific motivation, expected results, and potential applications of the Ramsey system.

---

## What to expect from the measurements

### CW ODMR at room temperature

The first result will be a fluorescence contrast dip of **1–5%** in the signal/reference ratio at the resonance frequency. For the silicon vacancy (V2) in 4H-SiC this sits around **1.35 GHz**. The linewidth will be a few MHz, broadened by strain, magnetic noise, and laser power.

| Parameter | Room temperature | 4 K |
|---|---|---|
| Contrast | 1–3% | Improved |
| Linewidth | 5–20 MHz | Narrowed |
| T2* | Tens of ns | Up to µs (divacancy) |

Expect the first spectrum to look noisy. The two most common culprits are laser power instability (reference window normalization helps) and RF pickup from the ADF4351 coupling into the APD signal path.

### What the GUI will show

A roughly Lorentzian dip when plotting contrast vs frequency. Once a Lorentzian can be fitted and the center frequency extracted, the local magnetic field follows directly from the zero-field splitting and gyromagnetic ratio:

```
f = f0 + γ·B
```

where `f0` ≈ 1.35 GHz, `γ` is the gyromagnetic ratio, and `B` is the field at the defect site. The defect acts as an atomic-scale magnetometer embedded in the crystal.

### The measurement progression

Each phase builds on the last:

```
CW ODMR → Ramsey → T2* measurement → sensitivity in T/√Hz
```

A sensitivity number in T/√Hz is the currency of the field — it's how results compare against SQUIDs, atomic magnetometers, and NV-diamond systems. That is a publishable result.

### Why SiC specifically

SiC defects have weaker contrast than NV centers in diamond but compensate with longer coherence times, particularly at cryogenic temperatures. The material advantage is significant:

- Commercial semiconductor — fabrication infrastructure already exists
- Can be isotopically purified to reduce magnetic noise from nuclear spins
- Compatible with standard semiconductor processing (doping, etching, integration with electronics) in ways diamond is not
- Biocompatible — implantable sensor applications are not ruled out long-term
- 4 K operation is achievable with a pulse tube cooler, no liquid helium handling required

---

## Potential applications

The core capability is nanoscale magnetic field sensing — measuring fields at a single point with high sensitivity and, in scanning geometries, nanometer spatial resolution.

### Neuroscience and biology
- Neurons generate ~pT magnetic fields when firing. An array of SiC sensors at nT/√Hz sensitivity could map neural activity non-invasively with higher spatial resolution than current MEG systems
- Imaging magnetic signatures of single cells or proteins
- Studying magnetotaxis in bacteria and other biological systems that use magnetic fields

### Materials science
- Mapping magnetic domains in novel materials at nanometer resolution — relevant for spintronics and next-generation memory devices
- Characterizing 2D materials (graphene, transition metal dichalcogenides) where magnetic properties emerge at the monolayer scale

### Condensed matter physics
- Detecting exotic magnetic phases: skyrmions, spin liquids, magnetic monopole-like excitations
- Probing superconductors: mapping vortex distributions, measuring local fields near grain boundaries

### Electronics and fault analysis
- Imaging current flow in integrated circuits by detecting the magnetic field the current generates — non-destructive failure analysis at the chip level, without decapsulation

### Geology and archaeology
- Scanning rocks or artifacts for remnant magnetization — paleomagnetic studies use bulk measurements today, a scanning sensor would give full spatial maps

### Medical imaging
The most ambitious direction. A dense array of SiC sensors with sufficient sensitivity could image magnetic fields from the heart (MCG) or brain (MEG) without the infrastructure burden of current SQUID-based systems. SQUIDs require ~4 K or lower and careful shielding; a SiC-based system operating at 4 K via pulse tube cooler removes liquid helium handling and is more practical for a clinical setting.

This remains 5–15 years from being practical at the single-sensor level. The foundational measurement being built here — a calibrated, sensitive magnetometer based on a spin defect — is the same physics that underlies all of it.

---

## Software scaling note

For the current research phase, Python is sufficient. The bottleneck is always the UART link and the FPGA accumulation time, not the PC.

If the system moves toward medical imaging or any application requiring real-time reconstruction from large datasets (e.g. voxel-by-voxel field maps), the stack would evolve:

| Layer | Research | Clinical / high-throughput |
|---|---|---|
| Hardware control | Python | Python (retained) |
| Reconstruction | Python / numpy | C++ or Rust |
| GPU acceleration | Not needed | CUDA |
| Regulatory (IEC 62304) | N/A | Requires validated, auditable build |

The clean split between `uart_comm.py` (backend) and `gui.py` (frontend) makes this transition easier — the backend can be wrapped or replaced without touching the GUI.
