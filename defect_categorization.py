"""
Catégorisation supplémentaire des défauts détectés (au-delà de CONFORME/REJET) :
prédiction d'une valeur continue (ex. taux d'humidité en %) à partir du signal, par
apprentissage supervisé sur des tubes archivés à des valeurs connues.

Généralisable à d'autres catégories continues (ex. manque de colle, excès de colle) :
il suffit d'appeler ces mêmes fonctions avec un `category` différent — aucune
modification de ce fichier n'est nécessaire pour ajouter une nouvelle catégorie.

En plus de la valeur qui définit la catégorie (ex. taux d'humidité), chaque tube
archivé peut porter une valeur "radial" optionnelle (résistance radiale mesurée),
transversale à toutes les catégories. Un modèle Radial séparé peut être entraîné en
regroupant tous les tubes (de n'importe quelle catégorie) qui ont cette valeur
renseignée — voir train_radial_model().

Fonctionne sur le même principe que ia_model_manager.py (features = amplitude moyenne
par bande de fréquence), mais avec un RandomForestRegressor au lieu d'un classifieur,
puisque la cible (ex. taux d'humidité, résistance radiale) est une valeur continue.
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


def archive_labeled_tube(base_folder, category, tube_name, tube_df, value, unit="",
                          radial=None, radial_unit="bar", extra_info=None):
    """Archive un tube avec une valeur connue (ex. taux d'humidité mesuré en laboratoire
    ou par un instrument de référence) pour servir d'exemple d'entraînement.
    `radial` est optionnel — laissez None si la résistance radiale n'est pas encore
    connue pour ce tube ; elle pourra être ajoutée plus tard via update_radial()."""
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
            "radial": radial,
            "radial_unit": radial_unit,
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


def count_radial_archives(base_folder, categories):
    """Retourne (nombre_de_tubes, min, max) ayant une valeur radiale renseignée,
    toutes catégories confondues parmi celles fournies."""
    values = []
    for cat in categories:
        for rec in list_labeled_tubes(base_folder, [cat]):
            if rec.get("radial") is not None:
                values.append(rec["radial"])
    if not values:
        return 0, None, None
    return len(values), min(values), max(values)


def list_labeled_tubes(base_folder, categories):
    """Liste les tubes archivés (métadonnées uniquement, pas les courbes) pour une ou
    plusieurs catégories — utilisé pour parcourir/éditer des archives existantes
    (ex. ajouter une valeur radiale après coup)."""
    records = []
    for category in categories:
        d = os.path.join(base_folder, "categorisation_archive", category)
        if not os.path.isdir(d):
            continue
        for fn in sorted(glob.glob(os.path.join(d, "*.json"))):
            with open(fn, encoding="utf-8") as f:
                meta = json.load(f)
            records.append({
                "meta_path": fn,
                "category": category,
                "tube": meta.get("tube"),
                "date": meta.get("date"),
                "value": meta.get("value"),
                "unit": meta.get("unit", ""),
                "radial": meta.get("radial"),
                "radial_unit": meta.get("radial_unit", "bar"),
            })
    return records


def update_radial(meta_path, radial_value, radial_unit="bar"):
    """Ajoute ou modifie la valeur radiale d'un tube DÉJÀ archivé, sans toucher au
    reste de ses métadonnées ni à sa courbe. `meta_path` vient de list_labeled_tubes()."""
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["radial"] = radial_value
    meta["radial_unit"] = radial_unit
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


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
            "radial": meta.get("radial"), "radial_unit": meta.get("radial_unit", "bar"),
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


def _train_from_records(records, model_name, base_folder, cfg, n_bins, log,
                         target_key="value", unit=None):
    n = len(records)
    if n < 4:
        raise ValueError(
            f"Il faut au moins 4 tubes archivés avec une valeur '{model_name}' connue "
            f"pour entraîner ce modèle (actuellement {n})."
        )

    parametre = cfg["PARAMETRE"]
    freq_ref = records[0]["df"]["FREQ"].values
    bins = np.linspace(freq_ref.min(), freq_ref.max(), n_bins + 1)

    X, y_vals = [], []
    for rec in records:
        df = rec["df"]
        feats = _build_features(freq_ref, bins, df["FREQ"].values, df[parametre].values)
        X.append(feats)
        y_vals.append(rec[target_key])

    X = np.array(X)
    y_vals = np.array(y_vals, dtype=float)
    if unit is None:
        unit = records[0].get("unit" if target_key == "value" else "radial_unit", "")

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
        "category": model_name,
        "unit": unit,
        "r2_cv": r2_cv,
        "n_samples": n,
        "value_min": float(y_vals.min()),
        "value_max": float(y_vals.max()),
        "date_entrainement": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    model_path = os.path.join(base_folder, f"categorisation_{model_name}_model.joblib")
    joblib.dump(bundle, model_path)
    log(f"\nModèle '{model_name}' entraîné et enregistré -> {model_path}")
    return model_path, bundle


def train_regression_model(base_folder, category, cfg, n_bins=None, log=print):
    """Entraîne le modèle d'UNE catégorie (ex. humidite, colle_manque, colle_exces)
    sur sa propre valeur définissante — n'utilise PAS la valeur radiale."""
    if not SKLEARN_AVAILABLE:
        raise RuntimeError("scikit-learn n'est pas installé. Exécutez : pip install scikit-learn")
    n_bins = n_bins or cfg.get("IA_N_BINS", 20)
    records = _load_labeled_archive(base_folder, category)
    log(f"Tubes archivés disponibles pour '{category}' : {len(records)}")
    return _train_from_records(records, category, base_folder, cfg, n_bins, log, target_key="value")


def train_radial_model(base_folder, categories, cfg, n_bins=None, log=print):
    """Entraîne le modèle Radial en regroupant tous les tubes ayant une valeur radiale
    renseignée, dans TOUTES les catégories fournies (humidité, manque de colle, excès
    de colle...) — la catégorie d'origine du tube n'a pas d'importance ici, seule la
    résistance radiale mesurée compte."""
    if not SKLEARN_AVAILABLE:
        raise RuntimeError("scikit-learn n'est pas installé. Exécutez : pip install scikit-learn")
    n_bins = n_bins or cfg.get("IA_N_BINS", 20)
    records = []
    for cat in categories:
        records += [r for r in _load_labeled_archive(base_folder, cat) if r.get("radial") is not None]
    log(f"Tubes archivés avec valeur radiale connue (toutes catégories) : {len(records)}")
    return _train_from_records(records, "radial", base_folder, cfg, n_bins, log, target_key="radial")


def corriger_unite_radial_toutes_bases(ref_bases_dir, log=print):
    """Corrige l'étiquette d'unité (ex. "N" -> "bar") des archives de catégorisation
    sur TOUTES les bases de référence trouvées dans ref_bases_dir. Ne touche jamais
    à la valeur numérique du radial, seulement à son étiquette d'unité. Retourne
    (total_corriges, total_deja_bon, total_sans_radial, nb_bases)."""
    if not os.path.isdir(ref_bases_dir):
        log(f"Dossier introuvable : {ref_bases_dir}")
        return 0, 0, 0, 0

    noms_bases = sorted(
        d for d in os.listdir(ref_bases_dir)
        if os.path.isdir(os.path.join(ref_bases_dir, d))
    )
    if not noms_bases:
        log("Aucune base de référence trouvée.")
        return 0, 0, 0, 0

    total_corriges = total_deja_bon = total_sans_radial = 0
    for nom in noms_bases:
        base_folder = os.path.join(ref_bases_dir, nom)
        pattern = os.path.join(base_folder, "categorisation_archive", "*", "*.json")
        fichiers = glob.glob(pattern)
        c = d = s = 0
        for fn in fichiers:
            with open(fn, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("radial") is None:
                s += 1
                continue
            ancienne_unite = meta.get("radial_unit")
            if ancienne_unite == "bar":
                d += 1
                continue
            meta["radial_unit"] = "bar"
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            c += 1
            log(f"  [{nom}] Corrigé : {os.path.basename(fn)} "
                f"(radial={meta['radial']}, unité '{ancienne_unite}' -> 'bar')")
        if c or d or s:
            log(f"[{nom}] {c} corrigé(s), {d} déjà en bar, {s} sans valeur radiale.")
        total_corriges += c
        total_deja_bon += d
        total_sans_radial += s

    log(f"\nTOTAL, {len(noms_bases)} base(s) : {total_corriges} corrigé(s), "
        f"{total_deja_bon} déjà en bar, {total_sans_radial} sans valeur radiale.")
    return total_corriges, total_deja_bon, total_sans_radial, len(noms_bases)


def discover_models(base_folder):
    """Détecte automatiquement tous les modèles de catégorisation déjà entraînés
    dans le dossier de la base (categorisation_<category>_model.joblib), sans
    configuration manuelle. Retourne {category: chemin_du_modele} — inclut "radial"
    comme une catégorie parmi d'autres, exactement comme humidite/colle_manque/etc."""
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
