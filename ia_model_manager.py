"""
Gestion de l'IA supervisée : archivage des tubes confirmés (sain / défaut de collage)
et entraînement / mise à jour du modèle, pour enrichir la détection au-delà de la
seule base saine statistique (Approche A de Principal.txt).

Chaque tube testé peut être archivé par l'opérateur, une fois le diagnostic terrain
confirmé (contrôle visuel, découpe, etc.) :
    - "sain"   -> label 0
    - "défaut" -> label 1 (collage défectueux confirmé)

Le bouton "Entraîner / Mettre à jour le modèle IA" reconstruit un modèle à partir
de TOUS les tubes archivés pour la base courante, et produit un fichier .joblib
strictement compatible avec le format attendu par tube_comparator.evaluate_with_ia
(et donc avec Principal.txt) : {"scaler", "model", "bins", "freq_ref", "parametre",
"auc_cv", "n_sain", "n_defaut"}.
"""
import os
import glob
import json
import shutil
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import roc_auc_score
    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False


def _archive_dir(base_folder, label):
    sub = "sain" if label == 0 else "defaut"
    d = os.path.join(base_folder, "ia_archive", sub)
    os.makedirs(d, exist_ok=True)
    return d


def archive_tube(base_folder, tube_name, tube_df, label, extra_info=None):
    """
    Archive un tube testé comme exemple d'entraînement.
    label : 0 = sain confirmé, 1 = défaut de collage confirmé
    """
    d = _archive_dir(base_folder, label)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
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
            "label": "defaut" if label == 1 else "sain",
            "extra": extra_info or {},
        }, f, indent=2, ensure_ascii=False)

    return path


def count_archives(base_folder):
    sain_dir = os.path.join(base_folder, "ia_archive", "sain")
    defaut_dir = os.path.join(base_folder, "ia_archive", "defaut")
    n_sain = len(glob.glob(os.path.join(sain_dir, "*.csv"))) if os.path.isdir(sain_dir) else 0
    n_defaut = len(glob.glob(os.path.join(defaut_dir, "*.csv"))) if os.path.isdir(defaut_dir) else 0
    return n_sain, n_defaut


def list_archived_tubes(base_folder):
    """Liste les tubes archivés (sain et défaut) avec leurs métadonnées, pour pouvoir
    les consulter ou corriger leur statut. Retourne une liste de dicts :
    {"csv_path", "label" ("sain"/"defaut"), "tube", "date"}."""
    records = []
    for sub in ("sain", "defaut"):
        d = os.path.join(base_folder, "ia_archive", sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(glob.glob(os.path.join(d, "*.csv"))):
            tube, date = os.path.basename(fn), ""
            meta_path = fn[:-4] + ".json"
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, encoding="utf-8") as f:
                        meta = json.load(f)
                    tube = meta.get("tube", tube)
                    date = meta.get("date", "")
                except Exception:
                    pass
            records.append({"csv_path": fn, "label": sub, "tube": tube, "date": date})
    return records


def relabel_archived_tube(csv_path, new_label):
    """Change le statut d'un tube DÉJÀ archivé ("sain" <-> "defaut") : déplace son
    CSV et ses métadonnées dans l'autre dossier, met à jour l'étiquette et garde une
    trace du changement (champ "historique") pour la traçabilité.
    new_label : "sain" ou "defaut". Retourne le nouveau chemin du CSV.
    Le modèle IA déjà entraîné n'est PAS modifié : il faut le ré-entraîner ensuite."""
    if new_label not in ("sain", "defaut"):
        raise ValueError("new_label doit valoir 'sain' ou 'defaut'.")
    src_dir = os.path.dirname(csv_path)
    ia_root = os.path.dirname(src_dir)
    current = os.path.basename(src_dir)
    if current == new_label:
        return csv_path

    dst_dir = os.path.join(ia_root, new_label)
    os.makedirs(dst_dir, exist_ok=True)
    base = os.path.basename(csv_path)[:-4]
    dst_base, k = base, 1
    while os.path.exists(os.path.join(dst_dir, dst_base + ".csv")):
        k += 1
        dst_base = f"{base}_{k}"
    new_csv = os.path.join(dst_dir, dst_base + ".csv")

    old_meta = csv_path[:-4] + ".json"
    meta = {}
    if os.path.exists(old_meta):
        try:
            with open(old_meta, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
    meta.setdefault("tube", base)
    meta["label"] = new_label
    meta.setdefault("historique", []).append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "de": current,
        "vers": new_label,
    })

    shutil.move(csv_path, new_csv)
    with open(new_csv[:-4] + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    if os.path.exists(old_meta):
        os.remove(old_meta)
    return new_csv


def _load_archive(base_folder):
    records = []
    for label, sub in ((0, "sain"), (1, "defaut")):
        d = os.path.join(base_folder, "ia_archive", sub)
        if not os.path.isdir(d):
            continue
        for fn in sorted(glob.glob(os.path.join(d, "*.csv"))):
            df = pd.read_csv(fn, sep=";")
            df.columns = df.columns.astype(str).str.strip()
            records.append({"nom": os.path.basename(fn), "df": df, "label": label})
    return records


def _build_features(freq_ia, bins, freq_test, signal_test):
    y = np.interp(freq_ia, freq_test, signal_test)
    feats = []
    for i in range(len(bins) - 1):
        mask = (freq_ia >= bins[i]) & (freq_ia < bins[i + 1])
        vals = y[mask]
        feats.append(float(vals.mean()) if len(vals) else 0.0)
    return feats


def train_ia_model(base_folder, cfg, n_bins=None, log=print):
    if not SKLEARN_AVAILABLE:
        raise RuntimeError(
            "scikit-learn n'est pas installé. Exécutez : pip install scikit-learn"
        )

    n_bins = n_bins or cfg.get("IA_N_BINS", 20)
    records = _load_archive(base_folder)
    n_sain = sum(1 for r in records if r["label"] == 0)
    n_defaut = sum(1 for r in records if r["label"] == 1)

    log(f"Tubes archivés disponibles : {n_sain} sain(s) / {n_defaut} défaut(s)")

    if n_sain < 2 or n_defaut < 2:
        raise ValueError(
            "Il faut au moins 2 tubes archivés 'sain' ET 2 archivés 'défaut' pour "
            f"entraîner le modèle IA (actuellement {n_sain} sain(s) / {n_defaut} défaut(s)). "
            "Testez et archivez davantage de tubes (via les boutons de confirmation "
            "après un test)."
        )

    parametre = cfg["PARAMETRE"]
    freq_ia = records[0]["df"]["FREQ"].values
    bins = np.linspace(freq_ia.min(), freq_ia.max(), n_bins + 1)

    X, y_labels = [], []
    for rec in records:
        df = rec["df"]
        feats = _build_features(freq_ia, bins, df["FREQ"].values, df[parametre].values)
        X.append(feats)
        y_labels.append(rec["label"])

    X = np.array(X)
    y_labels = np.array(y_labels)

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    model = RandomForestClassifier(
        n_estimators=200, max_depth=4, random_state=42, class_weight="balanced"
    )

    auc_cv = None
    n_splits = min(5, n_sain, n_defaut)
    if n_splits >= 2:
        try:
            skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
            proba_cv = cross_val_predict(model, Xs, y_labels, cv=skf, method="predict_proba")[:, 1]
            auc_cv = float(roc_auc_score(y_labels, proba_cv))
            log(f"AUC en validation croisée ({n_splits} plis) : {auc_cv:.3f}")
        except Exception as e:
            log(f"Validation croisée impossible ({e}) : entraînement sans AUC.")
    else:
        log("Pas assez d'exemples pour une validation croisée (AUC non calculée).")

    model.fit(Xs, y_labels)

    bundle = {
        "scaler": scaler,
        "model": model,
        "bins": bins,
        "freq_ref": freq_ia,
        "parametre": parametre,
        "auc_cv": auc_cv if auc_cv is not None else 0.5,
        "n_sain": n_sain,
        "n_defaut": n_defaut,
        "date_entrainement": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    model_path = os.path.join(base_folder, "ia_model.joblib")
    joblib.dump(bundle, model_path)
    log(f"\nModèle IA entraîné et enregistré -> {model_path}")

    return model_path, bundle
