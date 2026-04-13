"""
characterize.py — Ramsey system characterization script.

Runs a single ODMR sweep using the current hardware settings, fits the result,
computes sensitivity figures, and saves everything to data/characterization_<timestamp>.json.

Usage:
    python characterize.py [--port COM3] [--out ../data]

Requires the FPGA to be connected and the ADF4351 to be locked.
"""

import argparse
import json
import os
import datetime
import numpy as np

import lorentzian_fit

# ── Constants ─────────────────────────────────────────────────────────────────
GAMMA_E_MHZ_PER_MT = 28.0   # electron gyromagnetic ratio


def compute_sensitivity(fit: dict, n_photons: float | None,
                        rep_rate_hz: float | None) -> dict:
    """
    Compute Cramer-Rao sensitivity from fit parameters and photon count.

    Returns a dict with sigma_f0_khz, sigma_b_ut, sigma_b_1s_ut, bottleneck.
    """
    result = {
        "sigma_f0_khz":  None,
        "sigma_b_ut":    None,
        "sigma_b_1s_ut": None,
        "bottleneck":    None,
    }

    if n_photons is None or n_photons <= 0:
        result["bottleneck"] = "photon count not measured"
        return result

    gamma = fit["linewidth_mhz"]
    a     = fit["contrast_depth"]

    if a <= 0 or gamma <= 0:
        result["bottleneck"] = "fit parameters invalid"
        return result

    sigma_f0_mhz  = gamma / (2 * a * np.sqrt(n_photons))
    sigma_b_mt    = sigma_f0_mhz / GAMMA_E_MHZ_PER_MT

    result["sigma_f0_khz"] = round(sigma_f0_mhz * 1000, 3)
    result["sigma_b_ut"]   = round(sigma_b_mt * 1000, 3)

    if rep_rate_hz is not None and rep_rate_hz > 0:
        sigma_b_1s = sigma_b_mt * 1000 / np.sqrt(rep_rate_hz)
        result["sigma_b_1s_ut"] = round(sigma_b_1s, 4)

    # Identify the dominant bottleneck
    if gamma > 10:
        result["bottleneck"] = "linewidth too broad — reduce MW power"
    elif a < 0.02:
        result["bottleneck"] = "contrast too low — check collection / laser alignment"
    elif n_photons < 500:
        result["bottleneck"] = "photon count low — improve collection or increase readout window"
    else:
        result["bottleneck"] = "none — operating near optimum"

    return result


def run(port: str, out_dir: str, sensor: str, operator: str, notes: str) -> str:
    """
    Collect one ODMR sweep, fit, compute sensitivity, save JSON.
    Returns the path to the saved file.
    """
    # ── TODO: replace stubs with real hardware calls once FPGA is connected ──
    # from uart import send_config, read_packet
    # freqs_mhz, contrast, n_readout, n_ref, hw = acquire_sweep(port, ...)

    # Stub: synthetic data for schema development
    freqs_mhz    = list(np.linspace(2840, 2900, 100))
    f0_true      = 2870.0
    a_true, g_true = 0.05, 8.0
    contrast = [
        -a_true * (g_true / 2)**2 / ((f - f0_true)**2 + (g_true / 2)**2)
        + float(np.random.normal(0, 0.003))
        for f in freqs_mhz
    ]
    n_readout = None   # replace with real photon count from hardware
    n_ref     = None
    hw = {
        "mw_power_dbm":      None,
        "laser_power_mw":    None,
        "init_laser_us":     5.0,
        "mw_pulse_us":       1.0,
        "readout_window_us": 1.0,
        "ref_window_us":     1.0,
        "n_points":          len(freqs_mhz),
        "n_avg":             100,
        "rep_rate_hz":       None,
    }
    # ── end stub ──────────────────────────────────────────────────────────────

    fit_raw = lorentzian_fit.fit(freqs_mhz, contrast)
    fit = {
        "f0_mhz":         round(fit_raw["f0"],    4) if fit_raw else None,
        "f0_err_mhz":     round(fit_raw["f0_err"], 4) if fit_raw else None,
        "contrast_depth": round(fit_raw["a"],      4) if fit_raw else None,
        "linewidth_mhz":  round(fit_raw["gamma"],  4) if fit_raw else None,
    } if fit_raw else {"f0_mhz": None, "f0_err_mhz": None,
                       "contrast_depth": None, "linewidth_mhz": None}

    sensitivity = compute_sensitivity(fit, n_readout, hw["rep_rate_hz"])

    record = {
        "meta": {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "sensor":    sensor,
            "operator":  operator,
            "notes":     notes,
        },
        "hardware": hw,
        "odmr": {
            "freqs_mhz": [round(f, 4) for f in freqs_mhz],
            "contrast":  [round(c, 6) for c in contrast],
            "fit":       fit,
        },
        "photons": {
            "readout_counts_per_shot": n_readout,
            "ref_counts_per_shot":     n_ref,
        },
        "sensitivity": sensitivity,
    }

    ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(out_dir, f"characterization_{ts}.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)

    print(f"Saved: {out}")
    if fit_raw:
        print(f"  f0       = {fit['f0_mhz']:.3f} MHz")
        print(f"  contrast = {fit['contrast_depth']*100:.1f} %")
        print(f"  linewidth= {fit['linewidth_mhz']:.2f} MHz")
    if sensitivity["sigma_b_ut"]:
        print(f"  sigma_B  = {sensitivity['sigma_b_ut']:.1f} uT/shot")
    if sensitivity["sigma_b_1s_ut"]:
        print(f"  sigma_B  = {sensitivity['sigma_b_1s_ut']:.2f} uT/sqrt(Hz)")
    print(f"  bottleneck: {sensitivity['bottleneck']}")

    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ramsey system characterization")
    parser.add_argument("--port",     default="COM3",        help="Serial port")
    parser.add_argument("--out",      default="../data",     help="Output directory")
    parser.add_argument("--sensor",   default="NV_diamond",  help="Sensor type")
    parser.add_argument("--operator", default="",            help="Your name")
    parser.add_argument("--notes",    default="",            help="Free-text notes")
    args = parser.parse_args()

    run(args.port, args.out, args.sensor, args.operator, args.notes)
