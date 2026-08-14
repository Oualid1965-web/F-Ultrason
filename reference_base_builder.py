"""
Construction, sauvegarde, chargement et enrichissement des bases de référence
("base saine"), adapté de "Base de reference.txt".

Chaque base est stockée dans son propre dossier :

    data/reference_bases/<nom_base>/
        base_saine.csv        -> Frequency_Hz, Mean_HAPS, STD_HAPS, P5_HAPS, P95_HAPS, SNR
        metadata.json          -> nom, dates, tubes utilisés/rejetés, scores
        tubes/                 -> copie brute de chaque tube utilisé (pour pouvoir
                                   enrichir la base plus tard sans tout reperdre)
        resultats_tests.csv    -> historique des tests réalisés sur cette base
        ia_archive/sain|defaut -> tubes archivés pour l'entraînement du modèle IA
        ia_model.joblib         -> modèle IA entraîné (optionnel)
"""
import numpy as np
import pandas as pd
import os
import json
from datetime import datetime


def build_reference_base(tube_records, parametre, decimation, seuil_snr_display=5, iqr_factor=1.5, log=print):
    """
    tube_records: liste de {"nom": str, "df": DataFrame brut (colonnes FREQ, FFT Real/Imag/Abs)}
    Reproduit la logique de "Base de reference.txt" (score de corrélation en leave-one-out
    + filtrage des outliers par IQR) puis calcule les statistiques de la base saine.
    """
    tubes = []
    for rec in tube_records:
        df = rec["df"].copy()
        df.columns = df.columns.astype(str).str.strip()
        df = df.iloc[::decimation, :].reset_index(drop=True)
        if "FREQ" not in df.columns or parametre not in df.columns:
            raise ValueError(f"Le tube '{rec['nom']}' ne contient pas les colonnes requises (FREQ, {parametre}).")
        tubes.append({"nom": rec["nom"], "freq": df["FREQ"].values, "signal": df[parametre].values})

    if len(tubes) < 2:
        raise ValueError("Il faut au moins 2 tubes pour construire une base de référence fiable.")

    # Harmonise la longueur si des tubes ont un nombre de points légèrement différent
    min_len = min(len(t["signal"]) for t in tubes)
    for t in tubes:
        t["signal"] = t["signal"][:min_len]
        t["freq"] = t["freq"][:min_len]
    freq_ref = tubes[0]["freq"]

    matrice = np.array([t["signal"] for t in tubes])

    mean_init = np.mean(matrice, axis=0)
    std_init = np.std(matrice, axis=0)
    snr_init = np.abs(mean_init) / (std_init + 1e-12)
    mask_snr = snr_init >= seuil_snr_display

    def score_tube(base, test):
        base_mean = np.mean(base, axis=0)
        x = base_mean[mask_snr]
        y = test[mask_snr]
        if len(x) < 10 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
            return 0.0
        corr = np.corrcoef(x, y)[0, 1]
        return corr * 100

    scores = []
    for i in range(len(tubes)):
        test = matrice[i]
        base = np.delete(matrice, i, axis=0)
        scores.append(score_tube(base, test))
    scores = np.array(scores)

    log("=== SCORES TUBES (avant filtrage) ===")
    for i, t in enumerate(tubes):
        log(f"{t['nom']} --> {scores[i]:.2f} %")

    Q1 = np.percentile(scores, 25)
    Q3 = np.percentile(scores, 75)
    IQR = Q3 - Q1
    borne_inf = Q1 - iqr_factor * IQR
    mask_good = scores >= borne_inf

    matrice_clean = matrice[mask_good]
    tubes_clean = [t for t, keep in zip(tubes, mask_good) if keep]

    log("\n=== FILTRAGE OUTLIERS ===")
    log(f"Tubes totaux : {len(tubes)}")
    log(f"Tubes conservés : {len(tubes_clean)}")
    log(f"Tubes rejetés : {len(tubes) - len(tubes_clean)}")
    log(f"Borne IQR : {round(borne_inf, 2)}")

    log("\n=== TUBES REJETÉS ===")
    any_rejected = False
    for i, keep in enumerate(mask_good):
        if not keep:
            any_rejected = True
            log(f"{tubes[i]['nom']} --> {scores[i]:.2f} %")
    if not any_rejected:
        log("(aucun)")

    if len(tubes_clean) < 2:
        raise ValueError(
            "Trop de tubes rejetés : impossible de construire une base fiable "
            "(minimum 2 tubes conservés)."
        )

    mean_clean = np.mean(matrice_clean, axis=0)
    std_clean = np.std(matrice_clean, axis=0)
    p5_clean = np.percentile(matrice_clean, 5, axis=0)
    p95_clean = np.percentile(matrice_clean, 95, axis=0)
    snr_clean = np.abs(mean_clean) / (std_clean + 1e-12)

    df_clean = pd.DataFrame({
        "Frequency_Hz": freq_ref,
        "Mean_HAPS": mean_clean,
        "STD_HAPS": std_clean,
        "P5_HAPS": p5_clean,
        "P95_HAPS": p95_clean,
        "SNR": snr_clean
    })

    log("\n=== BASE SAINE EXPORTÉE ===")
    log(f"{len(tubes_clean)} tubes utilisés sur {len(tubes)} fournis.")

    return {
        "df_clean": df_clean,
        "tubes_used": [t["nom"] for t in tubes_clean],
        "tubes_rejected": [t["nom"] for t, keep in zip(tubes, mask_good) if not keep],
        "scores": {t["nom"]: float(s) for t, s in zip(tubes, scores)},
        "parametre": parametre,
        "decimation": decimation,
    }


def _safe_name(name):
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
    return safe or f"BASE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def save_reference_base(result, base_name, tube_records, ref_bases_dir):
    """
    tube_records : tubes BRUTS (non décimés) réellement fournis à build_reference_base
                   -> conservés sur disque pour permettre un enrichissement futur.
    """
    safe = _safe_name(base_name)
    base_folder = os.path.join(ref_bases_dir, safe)
    counter = 1
    while os.path.isdir(base_folder):
        counter += 1
        base_folder = os.path.join(ref_bases_dir, f"{safe}_{counter}")
    tubes_folder = os.path.join(base_folder, "tubes")
    os.makedirs(tubes_folder, exist_ok=True)

    csv_path = os.path.join(base_folder, "base_saine.csv")
    result["df_clean"].to_csv(csv_path, index=False)

    used = set(result["tubes_used"])
    for rec in tube_records:
        if rec["nom"] in used:
            fn = _safe_name(os.path.splitext(rec["nom"])[0]) + ".csv"
            rec["df"].to_csv(os.path.join(tubes_folder, fn), sep=";", index=False)

    metadata = {
        "nom": base_name,
        "date_creation": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date_maj": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parametre": result["parametre"],
        "decimation": result["decimation"],
        "tubes_utilises": result["tubes_used"],
        "tubes_rejetes": result["tubes_rejected"],
        "scores": result["scores"],
    }
    with open(os.path.join(base_folder, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return base_folder


def load_metadata(base_folder):
    with open(os.path.join(base_folder, "metadata.json"), "r", encoding="utf-8") as f:
        meta = json.load(f)
    meta["_folder"] = base_folder
    return meta


def list_reference_bases(ref_bases_dir):
    bases = []
    if not os.path.isdir(ref_bases_dir):
        return bases
    for entry in sorted(os.listdir(ref_bases_dir)):
        folder = os.path.join(ref_bases_dir, entry)
        meta_path = os.path.join(folder, "metadata.json")
        if os.path.isdir(folder) and os.path.exists(meta_path):
            try:
                bases.append(load_metadata(folder))
            except Exception:
                continue
    return bases


def load_reference_base(csv_path):
    return pd.read_csv(csv_path)


def load_existing_tubes(base_folder):
    """Recharge les tubes bruts stockés pour une base, en vue d'un enrichissement."""
    tubes_folder = os.path.join(base_folder, "tubes")
    records = []
    if not os.path.isdir(tubes_folder):
        return records
    for fn in sorted(os.listdir(tubes_folder)):
        if fn.endswith(".csv"):
            df = pd.read_csv(os.path.join(tubes_folder, fn), sep=";")
            df.columns = df.columns.astype(str).str.strip()
            records.append({"nom": fn, "df": df})
    return records


def enrich_reference_base(base_folder, new_tube_records, cfg, log=print):
    """Recalcule la base en incluant les tubes bruts déjà stockés + les nouveaux tubes."""
    existing = load_existing_tubes(base_folder)
    all_records = existing + new_tube_records

    result = build_reference_base(
        all_records, cfg["PARAMETRE"], cfg["DECIMATION"],
        seuil_snr_display=cfg["SEUIL_SNR"], iqr_factor=cfg.get("IQR_FACTOR", 1.5),
        log=log
    )

    csv_path = os.path.join(base_folder, "base_saine.csv")
    result["df_clean"].to_csv(csv_path, index=False)

    tubes_folder = os.path.join(base_folder, "tubes")
    os.makedirs(tubes_folder, exist_ok=True)
    used = set(result["tubes_used"])
    existing_names = {rec["nom"] for rec in existing}
    for rec in new_tube_records:
        if rec["nom"] in used:
            fn = _safe_name(os.path.splitext(rec["nom"])[0]) + ".csv"
            if fn in existing_names:
                fn = _safe_name(os.path.splitext(rec["nom"])[0]) + f"_{datetime.now().strftime('%H%M%S')}.csv"
            rec["df"].to_csv(os.path.join(tubes_folder, fn), sep=";", index=False)

    meta = load_metadata(base_folder)
    meta["date_maj"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta["tubes_utilises"] = result["tubes_used"]
    meta["tubes_rejetes"] = result["tubes_rejected"]
    meta["scores"] = result["scores"]
    meta.pop("_folder", None)
    with open(os.path.join(base_folder, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return result
