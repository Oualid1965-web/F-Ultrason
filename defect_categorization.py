"""
Catégorisation supplémentaire des défauts détectés (au-delà de CONFORME/REJET) :
prédiction d'une valeur continue (ex. taux d'humidité en %) à partir du signal, par
apprentissage supervisé sur des tubes archivés à des valeurs connues.

Généralisable à d'autres catégories continues plus tard (ex. épaisseur de colle en
excès) : il suffit d'appeler ces mêmes fonctions avec un `category` différent — aucune
modification de ce fichier n'est nécessaire pour ajouter une nouvelle catégorie.

Fonctionne sur le même principe que ia_model_manager.py (features = amplitude moyenne
par bande de fréquence), mais avec un RandomForestRegressor au lieu d'un classifieur,
puisque la cible (ex. taux d'humidité) est une valeur continue, pas une classe binaire.
"""
import os
import glob
import json
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import KFold, cross_val_predict
    from sklearn.metrics import r2_score
    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False


def _archive_dir(base_folder, category):
    d = os.path.join(base_folder, "categorisation_archive", category)
    os.makedirs(d, exist_ok=True)
    return d


def archive_labeled_tube(base_folder, category, tube_name, tube_df, value, unit="", extra_info=None):
    """Archive un tube avec une valeur connue (ex. taux d'humidité mesuré en laboratoire
    ou par un instrument de référence) pour servir d'exemple d'entraînement."""
    d = _archive_dir(base_folder, category)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(
        c for c in os.path.splitext(tube_name)[0] if c.isalnum() or c in (" ", "_", "-")
    ).strip().replace(" ", "_")
    fn = f"{safe}_{ts}.csv"
    path = os.path.join(d, fn)
    tube_df.to_csv(path, sep=";", index=False)

    meta_path = path.replace(".csv", ".json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "tube": tube_name,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "value": value,
            "unit": unit,
            "extra": extra_info or {},
        }, f, indent=2, ensure_ascii=False)
    return path


def count_labeled_archives(base_folder, category):
    """Retourne (nombre_de_tubes, valeur_min, valeur_max) archivés pour cette catégorie."""
    d = os.path.join(base_folder, "categorisation_archive", category)
    if not os.path.isdir(d):
        return 0, None, None
    values = []
    for fn in glob.glob(os.path.join(d, "*.json")):
        with open(fn, encoding="utf-8") as f:
            meta = json.load(f)
        v = meta.get("value")
        if v is not None:
            values.append(v)
    if not values:
        return 0, None, None
    return len(values), min(values), max(values)


def _load_labeled_archive(base_folder, category):
    d = os.path.join(base_folder, "categorisation_archive", category)
    records = []
    if not os.path.isdir(d):
        return records
    for fn in sorted(glob.glob(os.path.join(d, "*.csv"))):
        meta_path = fn.replace(".csv", ".json")
        if not os.path.exists(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        df = pd.read_csv(fn, sep=";")
        df.columns = df.columns.astype(str).str.strip()
        records.append({
            "nom": os.path.basename(fn), "df": df,
            "value": meta["value"], "unit": meta.get("unit", ""),
        })
    return records


def _build_features(freq_ref, bins, freq_test, signal_test):
    y = np.interp(freq_ref, freq_test, signal_test)
    feats = []
    for i in range(len(bins) - 1):
        mask = (freq_ref >= bins[i]) & (freq_ref < bins[i + 1])
        vals = y[mask]
        feats.append(float(vals.mean()) if len(vals) else 0.0)
    return feats


def train_regression_model(base_folder, category, cfg, n_bins=None, log=print):
    if not SKLEARN_AVAILABLE:
        raise RuntimeError(
            "scikit-learn n'est pas installé. Exécutez : pip install scikit-learn"
        )

    n_bins = n_bins or cfg.get("IA_N_BINS", 20)
    records = _load_labeled_archive(base_folder, category)
    n = len(records)
    log(f"Tubes archivés disponibles pour '{category}' : {n}")

    if n < 4:
        raise ValueError(
            f"Il faut au moins 4 tubes archivés avec une valeur '{category}' connue pour "
            f"entraîner le modèle (actuellement {n}). Archivez des tubes à des valeurs "
            "différentes (ex. plusieurs taux d'humidité distincts)."
        )

    parametre = cfg["PARAMETRE"]
    freq_ref = records[0]["df"]["FREQ"].values
    bins = np.linspace(freq_ref.min(), freq_ref.max(), n_bins + 1)

    X, y_vals = [], []
    for rec in records:
        df = rec["df"]
        feats = _build_features(freq_ref, bins, df["FREQ"].values, df[parametre].values)
        X.append(feats)
        y_vals.append(rec["value"])

    X = np.array(X)
    y_vals = np.array(y_vals, dtype=float)
    unit = records[0].get("unit", "")

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    model = RandomForestRegressor(n_estimators=200, max_depth=4, random_state=42)

    r2_cv = None
    n_splits = min(5, n)
    if n_splits >= 3:
        try:
            kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
            pred_cv = cross_val_predict(model, Xs, y_vals, cv=kf)
            r2_cv = float(r2_score(y_vals, pred_cv))
            log(f"R² en validation croisée ({n_splits} plis) : {r2_cv:.3f}")
        except Exception as e:
            log(f"Validation croisée impossible ({e}) : entraînement sans R².")
    else:
        log("Pas assez d'exemples pour une validation croisée (R² non calculé, "
            "prédictions à interpréter avec prudence).")

    model.fit(Xs, y_vals)

    bundle = {
        "scaler": scaler,
        "model": model,
        "bins": bins,
        "freq_ref": freq_ref,
        "parametre": parametre,
        "category": category,
        "unit": unit,
        "r2_cv": r2_cv,
        "n_samples": n,
        "value_min": float(y_vals.min()),
        "value_max": float(y_vals.max()),
        "date_entrainement": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    model_path = os.path.join(base_folder, f"categorisation_{category}_model.joblib")
    joblib.dump(bundle, model_path)
    log(f"\nModèle '{category}' entraîné et enregistré -> {model_path}")
    return model_path, bundle


def discover_models(base_folder):
    """Détecte automatiquement tous les modèles de catégorisation déjà entraînés
    dans le dossier de la base (categorisation_<category>_model.joblib), sans
    configuration manuelle. Retourne {category: chemin_du_modele}."""
    found = {}
    if not base_folder or not os.path.isdir(base_folder):
        return found
    for fn in glob.glob(os.path.join(base_folder, "categorisation_*_model.joblib")):
        name = os.path.basename(fn)
        category = name[len("categorisation_"):-len("_model.joblib")]
        if category:
            found[category] = fn
    return found


def evaluate_regression(freq_test, signal_test, model_path):
    """Retourne (valeur_predite, unite, erreur_ou_None). N'échoue jamais bruyamment —
    utilisé comme information complémentaire, jamais comme critère de décision principal."""
    if not model_path or not os.path.exists(model_path):
        return None, "", "MODELE INDISPONIBLE"
    try:
        bundle = joblib.load(model_path)
        scaler = bundle["scaler"]
        model = bundle["model"]
        bins = bundle["bins"]
        freq_ref = bundle["freq_ref"]
        unit = bundle.get("unit", "")

        feats = _build_features(freq_ref, bins, freq_test, signal_test)
        X = np.array(feats).reshape(1, -1)
        Xs = scaler.transform(X)
        pred = model.predict(Xs)[0]
        return float(pred), unit, None
    except Exception as e:
        return None, "", f"Erreur catégorisation : {e}"
