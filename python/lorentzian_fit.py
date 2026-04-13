import numpy as np
from scipy.optimize import curve_fit


def _lorentzian(f, f0, a, gamma):
    """Single Lorentzian dip.

    f     : frequency array (MHz)
    f0    : center frequency (MHz)
    a     : contrast depth (positive value, dip goes negative)
    gamma : full-width at half-maximum (MHz)
    """
    return -a * (gamma / 2) ** 2 / ((f - f0) ** 2 + (gamma / 2) ** 2)


def fit(freqs_mhz, contrast):
    """Fit a Lorentzian dip to ODMR contrast data.

    Parameters
    ----------
    freqs_mhz : list or array of float
        Frequency axis in MHz.
    contrast  : list or array of float
        Contrast values (ΔPL/PL), dip is negative.

    Returns
    -------
    dict with keys:
        f0          : center frequency (MHz)
        a           : contrast depth (positive)
        gamma       : linewidth FWHM (MHz)
        f0_err      : 1-sigma uncertainty on f0 (MHz)
        fitted_y    : fitted curve evaluated at freqs_mhz
    or None if the fit failed.
    """
    f = np.asarray(freqs_mhz, dtype=float)
    c = np.asarray(contrast,   dtype=float)

    if len(f) < 5:
        return None

    # ── Initial guess from smoothed data (robust against shot noise) ─────────
    window = max(1, len(c) // 20)
    c_smooth = np.convolve(c, np.ones(window) / window, mode='same')
    min_idx  = int(np.argmin(c_smooth))
    f0_guess = f[min_idx]
    a_guess  = max(-c_smooth[min_idx], 1e-6)    # depth is positive
    # Estimate linewidth from smoothed curve
    half = -a_guess / 2
    below_half = f[c_smooth < half]
    gamma_guess = float(below_half[-1] - below_half[0]) if len(below_half) >= 2 \
                  else (f[-1] - f[0]) / 10

    p0     = [f0_guess, a_guess, gamma_guess]
    bounds = (
        [f[0],  0,    0           ],   # lower: f0 inside range, a>0, gamma>0
        [f[-1], 1.0,  f[-1]-f[0] ],   # upper: reasonable contrast and width
    )

    try:
        popt, pcov = curve_fit(_lorentzian, f, c, p0=p0, bounds=bounds, maxfev=10000)
    except (RuntimeError, ValueError):
        return None

    f0, a, gamma = popt
    perr = np.sqrt(np.diag(pcov))

    return {
        "f0":       float(f0),
        "a":        float(a),
        "gamma":    float(gamma),
        "f0_err":   float(perr[0]),
        "fitted_y": _lorentzian(f, *popt).tolist(),
    }


def zero_crossing(freqs_mhz, error_signal):
    """Find the resonance frequency from a lock-in (FSK) error signal.

    The error signal is the derivative of the ODMR dip: contrast(f+df) - contrast(f-df).
    The resonance is at the zero crossing where the signal transitions from
    negative to positive (dispersive lineshape).

    Parameters
    ----------
    freqs_mhz    : list or array of float — frequency axis (MHz)
    error_signal : list or array of float — lock-in error values

    Returns
    -------
    dict with keys:
        f0       : resonance frequency at zero crossing (MHz)
        fitted_y : error signal (passed through for plotting)
    or None if no zero crossing found.
    """
    f   = np.asarray(freqs_mhz,    dtype=float)
    err = np.asarray(error_signal,  dtype=float)

    if len(f) < 3:
        return None

    # Smooth lightly before finding zero crossing
    window  = max(1, len(err) // 10)
    smooth  = np.convolve(err, np.ones(window) / window, mode='same')

    # Find all sign changes (neg→pos = resonance centre, pos→neg = baseline)
    signs        = np.sign(smooth)
    transitions  = np.where(np.diff(signs))[0]

    if len(transitions) == 0:
        return None

    # Pick the transition with the steepest slope — most likely the resonance
    slopes = np.abs(np.diff(smooth)[transitions])
    best   = transitions[int(np.argmax(slopes))]

    # Linear interpolation to sub-point precision
    x0, x1 = f[best], f[best + 1]
    y0, y1 = smooth[best], smooth[best + 1]
    if y1 == y0:
        return None
    f0 = float(x0 - y0 * (x1 - x0) / (y1 - y0))

    return {
        "f0":       f0,
        "fitted_y": err.tolist(),
    }
