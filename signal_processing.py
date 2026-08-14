"""
Traitement du signal acquis : SNR, zoom FFT, mise en forme en DataFrame
(comme dans POST_PROCESSING de ACQUISITION_GUI.py).
"""
import numpy as np
import pandas as pd
from scipy.signal import zoom_fft


def compute_snr(DATA, n_samples_r):
    signal_power = np.mean(DATA[0:int(n_samples_r / 2 * 0.9)] ** 2)
    noise_power = np.mean(DATA[int(n_samples_r / 2 * 1.1):] ** 2)
    if noise_power <= 0:
        return float("inf")
    return 10 * np.log10(signal_power / noise_power)


def compute_fft(DATA, fs_r, f_min_fft, f_max_fft, n_points_fft):
    FFT_SIGNAL = zoom_fft(DATA, [f_min_fft, f_max_fft], n_points_fft, fs=fs_r)
    FREQ_R = np.linspace(f_min_fft, f_max_fft, n_points_fft, endpoint=False)
    return FREQ_R, FFT_SIGNAL


def tube_dataframe(FREQ_R, FFT_SIGNAL):
    return pd.DataFrame({
        "FREQ": FREQ_R,
        "FFT Real": np.real(FFT_SIGNAL),
        "FFT Imag": np.imag(FFT_SIGNAL),
        "FFT Abs": np.abs(FFT_SIGNAL),
    })
