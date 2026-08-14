"""
Comparaison d'un tube testé à la base saine (Health Index), et scoring optionnel
par le modèle IA supervisé, adapté de "Principal.txt".
"""
import os
import numpy as np
import joblib


def load_reference_arrays(df_ref, seuil_snr):
    colonnes = ["Frequency_Hz", "Mean_HAPS", "STD_HAPS", "P5_HAPS", "P95_HAPS", "SNR"]
    for c in colonnes:
        if c not in df_ref.columns:
            raise ValueError(f"Colonne absente dans la base saine : {c}")

    freq_ref = df_ref["Frequency_Hz"].values
    mean_ref = df_ref["Mean_HAPS"].values
    std_ref = df_ref["STD_HAPS"].values
    p5_ref = df_ref["P5_HAPS"].values
    p95_ref = df_ref["P95_HAPS"].values
    snr_ref = df_ref["SNR"].values

    mask = snr_ref >= seuil_snr
    return {
        "freq": freq_ref[mask],
        "mean": mean_ref[mask],
        "std": std_ref[mask],
        "p5": p5_ref[mask],
        "p95": p95_ref[mask],
        "snr": snr_ref[mask],
    }


def correlation_snr(x, y, w):
    w = w / (np.max(w) + 1e-12)
    xm = np.sum(w * x) / np.sum(w)
    ym = np.sum(w * y) / np.sum(w)
    num = np.sum(w * (x - xm) * (y - ym))
    den = np.sqrt(np.sum(w * (x - xm) ** 2) * np.sum(w * (y - ym) ** 2)) + 1e-12
    return num / den


def calcul_health_index(y, ref):
    x = ref["mean"]

    corr = correlation_snr(x, y, ref["snr"])
    corr_score = corr * 100

    defauts = (y < ref["p5"]) | (y > ref["p95"])
    ratio_defauts = np.mean(defauts)
    score_conformite = 100 - ratio_defauts * 100

    mae = np.mean(np.abs(x - y))

    energie_ref = np.sum(x ** 2)
    energie_test = np.sum(y ** 2)
    ratio_energie = energie_test / (energie_ref + 1e-12)
    score_energie = np.clip(100 - abs(1 - ratio_energie) * 100, 0, 100)

    z = np.abs(y - x) / (ref["std"] + 1e-12)
    zmax = np.max(z)
    score_z = 100 - np.clip(zmax * 10, 0, 100)

    health_index = (
        0.50 * corr_score
        + 0.20 * score_conformite
        + 0.20 * score_z
        + 0.10 * score_energie
    )
    health_index = float(np.clip(health_index, 0, 100))

    return {
        "health_index": health_index,
        "correlation": corr_score,
        "nb_defauts": int(np.sum(defauts)),
        "ratio_defauts": ratio_defauts * 100,
        "mae": mae,
        "energie_ratio": ratio_energie,
        "zmax": zmax,
        "mask_defauts": defauts,
    }


def classify(health, seuil_accept, seuil_suspect):
    if health >= seuil_accept:
        return "ACCEPTE"
    elif health >= seuil_suspect:
        return "SUSPECT"
    return "REJET"


def evaluate_with_ia(freq_test, signal_test, modele_path):
    """Score IA optionnel. Retourne (proba, erreur_ou_None)."""
    if not modele_path or not os.path.exists(modele_path):
        return None, "MODELE INDISPONIBLE"
    try:
        bundle = joblib.load(modele_path)
        scaler = bundle["scaler"]
        model = bundle["model"]
        bins = bundle["bins"]
        freq_ia = bundle["freq_ref"]

        y_ia = np.interp(freq_ia, freq_test, signal_test)
        features = []
        for i in range(len(bins) - 1):
            mask = (freq_ia >= bins[i]) & (freq_ia < bins[i + 1])
            vals = y_ia[mask]
            features.append(vals.mean() if len(vals) else 0.0)

        X = np.array(features).reshape(1, -1)
        Xs = scaler.transform(X)
        proba = model.predict_proba(Xs)[0, 1]
        return float(proba), None
    except Exception as e:
        return None, f"Erreur IA : {e}"


def evaluate_tube(freq_test, signal_test, df_ref, cfg):
    ref = load_reference_arrays(df_ref, cfg["SEUIL_SNR"])
    y = np.interp(ref["freq"], freq_test, signal_test)

    analyse = calcul_health_index(y, ref)
    health = analyse["health_index"]
    statut_base = classify(health, cfg["SEUIL_ACCEPT"], cfg["SEUIL_SUSPECT"])

    proba_ia = None
    diagnostic_ia = "NON UTILISE"
    if health < cfg["SEUIL_ACTIVATION_IA"] and cfg.get("CHEMIN_MODELE_IA"):
        proba_ia, err = evaluate_with_ia(freq_test, signal_test, cfg["CHEMIN_MODELE_IA"])
        if err:
            diagnostic_ia = err
        elif proba_ia is not None:
            if proba_ia >= 0.8 and health < 70:
                diagnostic_ia = "DEFAUT COLLAGE PROBABLE"
            elif proba_ia >= 0.3:
                diagnostic_ia = "DOUTE IA"
            else:
                diagnostic_ia = "IA PLUTOT SAIN"

    if statut_base == "ACCEPTE":
        statut_final = "ACCEPTE"
    elif diagnostic_ia == "DEFAUT COLLAGE PROBABLE":
        statut_final = "REJET IA"
    else:
        statut_final = statut_base

    return {
        "ref": ref,
        "y_interp": y,
        "health_index": round(health, 2),
        "correlation": round(analyse["correlation"], 2),
        "nb_defauts": analyse["nb_defauts"],
        "ratio_defauts": round(analyse["ratio_defauts"], 2),
        "mae": round(float(analyse["mae"]), 4),
        "zmax": round(float(analyse["zmax"]), 2),
        "energie_ratio": round(float(analyse["energie_ratio"]), 3),
        "mask_defauts": analyse["mask_defauts"],
        "statut_base": statut_base,
        "probabilite_ia": None if proba_ia is None else round(proba_ia, 3),
        "diagnostic_ia": diagnostic_ia,
        "statut_final": statut_final,
    }
