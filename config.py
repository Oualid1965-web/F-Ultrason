"""
Gestion centralisée des paramètres de l'application (persistés en JSON).
"""
import json
import os
import sys

if getattr(sys, "frozen", False):
    # Exécutable PyInstaller (--onefile) : les fichiers sont extraits dans un
    # dossier temporaire différent à chaque lancement. On stocke donc les
    # données à côté du .exe (persistant d'un lancement à l'autre).
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(APP_DIR, "data")
REF_BASES_DIR = os.path.join(DATA_DIR, "reference_bases")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

os.makedirs(REF_BASES_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    # ---- Analyse / Comparaison (Principal.txt / Graphe.txt) ----
    "PARAMETRE": "FFT Abs",
    "SEUIL_SNR": 5,
    "SEUIL_ACCEPT": 80,
    "SEUIL_SUSPECT": 65,
    "SEUIL_ACTIVATION_IA": 90,
    "DECIMATION": 10,
    "IQR_FACTOR": 1.5,

    # ---- IA supervisée (archivage + entraînement) ----
    "CHEMIN_MODELE_IA": "",   # chemin vers le modèle .joblib actif
    "IA_N_BINS": 20,          # nombre de bandes de fréquence utilisées comme features IA

    # ---- Acquisition DAQ (ACQUISITION_GUI.py) ----
    "DEVICE_NAME": "cDAQ9185-1FA54B4",
    "T_SWEEP": 0.5,
    "FS_E": 100e3,
    "F_MIN": 18.0e3,
    "F_MAX": 50.0e3,
    "AMP": 5.0,
    "FS_R": 102400,
    "AVERAGES": 2,
    "N_POINTS_FFT": 10000,
    "F_MIN_FFT": 20.0e3,
    "F_MAX_FFT": 45.0e3,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
            return merged
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
