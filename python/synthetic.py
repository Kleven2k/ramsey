"""
synthetic.py — Generate fake ODMR DATA packet payloads for offline GUI testing.

Produces a realistic Lorentzian contrast dip with shot noise, then packs it
into the same binary format the FPGA sends:
  n_points × 8 bytes: [sig uint32 BE][ref uint32 BE]
"""

import numpy as np


def generate_data_payload(
    freqs_mhz,
    f0_mhz      = None,   # dip center — defaults to middle of sweep
    contrast    = 0.05,   # dip depth as a fraction (0.05 = 5%)
    gamma_mhz   = 5.0,    # linewidth FWHM in MHz
    ref_counts  = 50000,  # reference photon count per point (sets shot noise level)
    n_shots     = 1,      # averaging (higher = less noise)
    seed        = None,
):
    """Return a bytearray formatted as a MSG_DATA payload.

    Parameters
    ----------
    freqs_mhz   : list of float — frequency axis in MHz
    f0_mhz      : float — ODMR dip center frequency (MHz)
    contrast    : float — dip depth ΔPL/PL (positive, e.g. 0.05 for 5%)
    gamma_mhz   : float — linewidth FWHM (MHz)
    ref_counts  : int   — mean reference photon counts per point
    n_shots     : int   — number of shots averaged (scales down noise)
    seed        : int   — random seed for reproducibility
    """
    rng = np.random.default_rng(seed)
    f   = np.asarray(freqs_mhz, dtype=float)

    if f0_mhz is None:
        f0_mhz = float(f[len(f) // 2])

    # Ideal contrast curve (negative dip)
    ideal = -contrast * (gamma_mhz / 2) ** 2 / ((f - f0_mhz) ** 2 + (gamma_mhz / 2) ** 2)

    # Shot noise: sigma = 1/sqrt(N) relative to ref_counts
    sigma = np.sqrt(ref_counts) / n_shots

    ref_arr = rng.poisson(ref_counts, size=len(f)).astype(np.int64)
    sig_arr = rng.poisson(
        np.clip(ref_counts * (1 + ideal), 1, None), size=len(f)
    ).astype(np.int64)

    # Pack as MSG_DATA payload: [sig uint32 BE][ref uint32 BE] per point
    payload = bytearray()
    for sig, ref in zip(sig_arr, ref_arr):
        payload += int(sig).to_bytes(4, 'big')
        payload += int(ref).to_bytes(4, 'big')

    return payload


def default_sweep(start=1280.0, stop=1380.0, step=2.0, **kwargs):
    """Convenience wrapper: build a freq list and return (freqs_mhz, payload)."""
    freqs = []
    f = start
    while f <= stop + 1e-9:
        freqs.append(round(f, 6))
        f += step
    payload = generate_data_payload(freqs, **kwargs)
    return freqs, payload
