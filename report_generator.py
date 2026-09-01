"""
Génération des graphes de comparaison (adapté de Graphe.txt / POST_PROCESSING)
et export cumulatif des résultats de test (adapté de RESULTATS_EXPORTES / Principal.txt).
"""
import os
from datetime import datetime

import numpy as np
import pandas as pd


def plot_test_result(figure, DATA, fs_r, n_samples_r, FREQ_R, FFT_SIGNAL, eval_result):
    figure.clear()
    ref = eval_result["ref"]
    y = eval_result["y_interp"]
    mask_defauts = eval_result["mask_defauts"]

    # --- Signal temporel (si disponible, i.e. acquisition DAQ réelle) ---
    ax1 = figure.add_subplot(2, 2, 1)
    if DATA is not None and fs_r and n_samples_r:
        t_R = np.linspace(0, n_samples_r / fs_r, n_samples_r, endpoint=False)
        ax1.plot(t_R * 1000, DATA)
        ax1.set_xlabel("Temps (ms)")
        ax1.set_ylabel("Signal (V)")
        ax1.set_title("Signal UT acquis")
        ax1.grid(True)
    else:
        ax1.axis("off")
        ax1.text(0.5, 0.5, "Signal temporel non disponible\n(tube importé)",
                  ha="center", va="center")

    # --- Zoom FFT du tube testé ---
    ax2 = figure.add_subplot(2, 2, 2)
    ax2.plot(FREQ_R, np.abs(FFT_SIGNAL), 'k', lw=1)
    ax2.set_xlabel("Fréquence (Hz)")
    ax2.set_ylabel("FFT Abs")
    ax2.set_title("Zoom FFT du tube testé")
    ax2.grid(True)

    # --- Comparaison à la base saine ---
    ax3 = figure.add_subplot(2, 2, 3)
    f = ref["freq"]
    ax3.fill_between(f, ref["p5"], ref["p95"], alpha=0.3, label="Zone conforme P5/P95")
    ax3.plot(f, ref["mean"], linewidth=2, label="Moyenne base saine")
    ax3.plot(f, y, linewidth=1, label="Tube évalué")
    ax3.set_xlabel("Fréquence (Hz)")
    ax3.set_ylabel("Amplitude")
    ax3.set_title("Comparaison à la base de référence")
    ax3.legend(fontsize=8)
    ax3.grid(True)

    # --- Détection défauts P5/P95 ---
    ax4 = figure.add_subplot(2, 2, 4)
    ax4.plot(f, y, label="Tube", lw=1)
    if np.any(mask_defauts):
        ax4.scatter(f[mask_defauts], y[mask_defauts], color="red", s=10, label="Défauts")
    ax4.fill_between(f, ref["p5"], ref["p95"], alpha=0.2)
    ax4.set_xlabel("Fréquence (Hz)")
    ax4.set_ylabel("Amplitude")
    ax4.set_title("Détection défauts P5/P95")
    ax4.legend(fontsize=8)
    ax4.grid(True)

    figure.tight_layout()


def append_result_csv(results_csv_path, tube_name, eval_result, snr_acquisition):
    row = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fichier": tube_name,
        "SNR_acquisition_dB": None if snr_acquisition is None or np.isnan(snr_acquisition) else round(float(snr_acquisition), 2),
        "Health_Index": eval_result["health_index"],
        "Correlation_%": eval_result["correlation"],
        "Defauts_P5_P95": eval_result["nb_defauts"],
        "Ratio_Defauts_%": eval_result["ratio_defauts"],
        "MAE": eval_result["mae"],
        "Zmax": eval_result["zmax"],
        "Energie_ratio": eval_result["energie_ratio"],
        "Statut_Base_Saine": eval_result["statut_base"],
        "Probabilite_IA": eval_result["probabilite_ia"],
        "Diagnostic_IA": eval_result["diagnostic_ia"],
        "Statut_Final": eval_result["statut_final"],
    }
    df_row = pd.DataFrame([row])
    if os.path.exists(results_csv_path):
        df_row.to_csv(results_csv_path, mode="a", header=False, index=False)
    else:
        df_row.to_csv(results_csv_path, mode="w", header=True, index=False)
    return row


def append_position_result_csv(results_csv_path, tube_name, position_cm, cote, eval_result, snr_acquisition,
                                amplitude_fft_max=None):
    """Identique à append_result_csv, avec Position_cm et Cote en plus — utilisé par
    les tests de position des capteurs. Les autres colonnes ont exactement les mêmes
    seuils/caractéristiques que les tests normaux (même cfg, même evaluate_tube)."""
    row = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fichier": tube_name,
        "Position_cm": position_cm,
        "Cote": cote,
        "SNR_acquisition_dB": None if snr_acquisition is None or np.isnan(snr_acquisition) else round(float(snr_acquisition), 2),
        "Health_Index": eval_result["health_index"],
        "Correlation_%": eval_result["correlation"],
        "Defauts_P5_P95": eval_result["nb_defauts"],
        "Ratio_Defauts_%": eval_result["ratio_defauts"],
        "MAE": eval_result["mae"],
        "Zmax": eval_result["zmax"],
        "Energie_ratio": eval_result["energie_ratio"],
        "Statut_Base_Saine": eval_result["statut_base"],
        "Probabilite_IA": eval_result["probabilite_ia"],
        "Diagnostic_IA": eval_result["diagnostic_ia"],
        "Statut_Final": eval_result["statut_final"],
        "Amplitude_FFT_max": amplitude_fft_max,
    }
    df_row = pd.DataFrame([row])
    if os.path.exists(results_csv_path):
        df_row.to_csv(results_csv_path, mode="a", header=False, index=False)
    else:
        df_row.to_csv(results_csv_path, mode="w", header=True, index=False)
    return row
