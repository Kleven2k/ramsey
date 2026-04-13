# Reading Guide

What to understand, what to read, and what questions to be able to answer at each stage of the project. Follows the same progression as the implementation plan — physics first, then technique, then hardware, then analysis.

### Reading order summary
```
1. Susskind chapters 1–4          — build quantum intuition
         ↓
2. Doherty et al. 2013            — understand the NV/defect physics deeply
         ↓
3. Degen et al. 2017 (sec 1–4)   — understand sensing protocols
         ↓
4. Widmann et al. 2015            — see SiC spin coherence demonstrated
         ↓
5. Professor's papers             — understand the specific system you are targeting
         ↓
6. Rondin et al. 2014             — practical sensing sequences for the FPGA
```

---

## Stage 1 — Spin defect physics

The foundational layer. Everything else builds on this.

### What to know
- What a spin defect is: a lattice vacancy or impurity that carries an unpaired electron spin (S = 1 for divacancy, S = 3/2 for silicon vacancy V2 in 4H-SiC)
- Why the spin state affects fluorescence: spin-selective intersystem crossing means the ms = 0 and ms = ±1 states emit different amounts of light under optical excitation — this is the contrast you are measuring
- Zero-field splitting (D): the energy gap between ms = 0 and ms = ±1 in the absence of any external field. For V2 in 4H-SiC, D ≈ 1.35 GHz
- The Zeeman effect: an external magnetic field B splits the ms = +1 and ms = −1 levels further. The resonance frequency shifts by γ·B, giving you a field measurement
- Why coherence time matters: T2* sets how long the spin stays in a superposition — longer T2* means narrower Ramsey fringes and better field sensitivity
- The difference between spin-½ and spin-1: start with spin-½ for intuition, then extend to spin-1. The SiC defects are spin-1 (divacancy) or spin-3/2 (V2), which adds structure to the energy levels but the core physics is the same

### Questions to be able to answer
- Why does the fluorescence dip at the resonance frequency?
- What is the difference between T1, T2, and T2*?
- Why does lowering temperature extend T2* in SiC?
- Why is the divacancy (kk, hh configurations) different from the silicon vacancy (V2)?
- What limits contrast in SiC compared to NV centers in diamond?

### What to read
- **"Quantum Mechanics: The Theoretical Minimum" — Susskind & Friedman** Focus on spin-½ first, which gives all the intuition needed before stepping up to spin-1. Read the first four chapters.
- **"Introduction to Quantum Mechanics" — Griffiths** Chapter 4 (spin) is the relevant section. Use as a reference rather than reading cover to cover.
- **"The nitrogen-vacancy colour centre in diamond" — Doherty et al., Physics Reports 2013** The definitive review paper. Covers electronic structure, spin Hamiltonian, optical transitions, and sensing protocols. Read carefully once and reference constantly. The physics transfers directly to SiC defects.
- **"Quantum registers based on spin qubits" — Wrachtrup group (Stuttgart) lecture notes** Search for the Stuttgart NV lecture notes. Published excellent pedagogical material online. Very practical, connects theory directly to experiment.
- **Christle et al., Nature Materials 2015** — first coherent control of divacancy spins in SiC
- **Koehl et al., Nature 2011** — room-temperature coherent control of SiC defects
- **Awschalom et al., Science 2018** — review of quantum technologies with SiC, good overview

---

## Stage 2 — ODMR technique

How you actually measure the spin state optically.

### What to know
- CW ODMR: continuous laser + swept MW frequency. Simple but linewidth-limited by power broadening
- Pulsed ODMR: laser init pulse → MW pulse → readout window → reference window. Better contrast, avoids power broadening
- The role of the reference window: a second readout without MW normalizes out laser intensity fluctuations
- Why you need a gate: the APD sees photons at all times, but only photons in the readout window are spin-state-dependent
- Shot noise: with N photon counts, the statistical uncertainty is √N. More shots and longer gates improve SNR as √(n_shots)

### Questions to be able to answer
- Why does pulsed ODMR give better contrast than CW?
- What determines the optimal readout window duration?
- How does the reference window normalization reduce noise?
- What is the shot-noise limit and how close can you get to it?
- How do you choose n_shots for a given target SNR?

### What to read
- **"Sensing with NV centers" — Rondin et al., Reports on Progress in Physics 2014** Covers DC and AC magnetometry, Ramsey sequences, spin echo, sensitivity calculations. Well written and practical. Directly relevant to what the FPGA implements.
- **Dréau et al., Physical Review B 2011** — optimal pulsed ODMR protocol for NV centers, directly applicable to SiC
- **"Silicon carbide for quantum spintronics" — Castelletto & Boretti, Journal of Physics: Photonics 2020** Good overview of SiC defects as qubit platforms. Covers silicon vacancy and divacancy, optical properties, and spin coherence.

---

## Stage 3 — Ramsey spectroscopy

The step beyond CW ODMR that gives real sensitivity.

### What to know
- The Ramsey sequence: π/2 pulse → free precession for time τ → π/2 pulse → readout
- What you are measuring: the phase accumulated during τ due to the local field. The spin precesses at the Larmor frequency; any field shift shows up as a phase offset in the fringes
- T2* decay: the fringe contrast decays as e^(−τ/T2*). The optimal τ is of order T2*
- How to extract the field: fit the fringe pattern to extract the precession frequency, compare to zero-field value
- AC field sensitivity: η ∝ 1 / (γ · √(T2* · n_shots · τ_sequence)). Longer T2* directly improves sensitivity
- Hahn echo: a π pulse inserted at τ/2 refocuses slow dephasing and extends effective coherence beyond T2*. The first step toward dynamical decoupling

### Questions to be able to answer
- What is the difference between a Ramsey sequence and a Hahn echo?
- Why does the fringe contrast decay, and what causes the decay envelope shape?
- How do you set the π/2 pulse length? What happens if it is wrong?
- What is the shot-noise-limited AC field sensitivity in T/√Hz for your expected T2*?
- Why does a Hahn echo extend the coherence time beyond T2*?

### What to read
- **"Quantum sensing" — Degen, Reinhard & Cappellaro, Reviews of Modern Physics 2017** The standard reference for quantum sensing protocols — Ramsey, spin echo, dynamical decoupling, sensitivity limits. Read sections 1–4 carefully, the rest as needed.
- **Maze et al., Nature 2008** — nanoscale magnetic sensing with NV centers, the canonical Ramsey sensing paper
- **Taylor et al., Nature Physics 2008** — high-sensitivity magnetometry with NV centers
- **Simin et al., Physical Review Applied 2016** — Ramsey spectroscopy of SiC divacancy specifically
- **Widmann et al., Nature Materials 2015** — landmark paper demonstrating room-temperature spin coherence in SiC. Short, readable, directly relevant.
- **Dynamical decoupling reviews — Biercuk or Bylander** When implementing XY-8 and CPMG sequences on the FPGA, these reviews explain the pulse sequence logic clearly.

---

## Stage 4 — Hardware and optics

What you need to understand to build and align the setup.

### What to know
- AOM (acousto-optic modulator): how it gates a CW laser with nanosecond precision. Rise time, extinction ratio, diffraction efficiency
- APD (avalanche photodiode): dead time, dark count rate, afterpulsing. Why you gate the counter rather than the detector
- RF chain: ADF4351 output power (~0 dBm), why you need an amplifier (+20–30 dB), switch placement before the amplifier to protect it
- Optical filtering: why you need a notch or longpass filter to reject laser scatter from APD counts
- Cryostat interface: what signals go cold (sample, coil, optionally detector), what stays warm (FPGA, ADF4351, laser)
- Fiber coupling: single-mode vs multimode for collection efficiency
- Confocal microscopy basics: even without building the optics, understanding what is happening in the cryostat helps design the electronics correctly

### Questions to be able to answer
- What AOM rise time do you need for your shortest pulse (init_dur)?
- What is the minimum dead time between the laser gate and the readout window?
- Why does the RF switch go before the amplifier rather than after?
- What filter OD (optical density) do you need to suppress 532 nm scatter below your dark count rate?
- How do you verify the ADF4351 output frequency before connecting to the RF chain?

### What to read
- **ADF4351 datasheet** — register map, reference input, output power settings
- **AOM driver datasheet** for your specific unit — modulation bandwidth and input signal requirements
- **Excelitas SPCM datasheet** — dead time, dark counts, max count rate
- **"Confocal microscopy for quantum optics" — Wrachtrup or Jelezko group tutorials** Look for published pedagogical material from these groups on confocal setups
- **"Lock-in detection techniques" — Stanford Research Systems application notes** SR Systems publishes free application notes that are among the clearest explanations available. Relevant if digital lock-in is implemented on the FPGA.
- Ramsey system_overview.md hardware section

---

## Stage 5 — Data analysis

What to do with the numbers once you have them.

### What to know
- Lorentzian fit: center frequency, linewidth (FWHM), contrast, offset. How to extract uncertainty from the fit
- Normalizing contrast: (signal − reference) / reference. What residual drift looks like and when it matters
- Converting frequency to field: Δf = γ·B, where γ ≈ 28 MHz/mT for electron spin. Report in mT or µT depending on scale
- Ramsey fringe fitting: sinusoidal oscillation with exponential decay envelope. Fit to extract T2* and precession frequency
- Sensitivity estimate: use the fitted linewidth and contrast to estimate what field sensitivity the system has achieved

### Questions to be able to answer
- How do you propagate fit uncertainties to the field measurement uncertainty?
- What SNR do you need to reliably fit the Lorentzian?
- How does power broadening affect the fitted linewidth, and how do you correct for it?
- What does a non-Lorentzian lineshape tell you about the sample?
- How do you compare your measured sensitivity to the shot-noise limit?

### What to read
- Any numerical methods reference for nonlinear least-squares fitting (`scipy.optimize.curve_fit` is sufficient to start)
- Dréau et al. 2011 (cited above) — contains the sensitivity derivation in a readable form
- **Levine et al., PRX Quantum 2019** — practical guide to NV magnetometry protocols, directly transferable to SiC

---

## Open questions specific to this project

Things worth investigating before or during hardware bring-up that are not fully resolved in the literature for this exact configuration:

- What is the optimal laser power for the V2 center in the specific SiC sample to balance contrast and power broadening?
- What is the thermal spin polarization at 4 K, and does it meaningfully help contrast compared to optical initialization?
- How does the zero-field splitting D vary with temperature between 300 K and 4 K for V2? Relevant for calibration
- What is the practical T2* for the divacancy in the sample — literature values vary significantly with sample quality and isotopic composition
- How much RF power reaches the defect given the coil geometry and cryostat feedthrough losses?
- Which defect to focus on: V2 (silicon vacancy, S = 3/2, brighter) or divacancy (S = 1, longer T2*)? Depends on the professor's sample and target experiment
