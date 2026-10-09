"""
Correction des tubes déjà archivés, toutes archives confondues.

Un tube testé peut avoir été archivé à deux endroits indépendants :
  - l'archive IA (statut sain / défaut), utilisée pour entraîner le modèle IA ;
  - l'archive humidité / radial, utilisée pour entraîner les modèles humidité et radial.
Les deux entrées d'un même tube partagent son nom. Ce module les apparie par nom (puis par
date quand un nom revient plusieurs fois) pour les présenter comme UN tube modifiable :
nom, statut sain / défaut, humidité, radial. Quand l'attribut modifié n'existe que dans
l'autre archive, l'entrée manquante est créée à partir de la même courbe.

Chaque modification est consignée dans le champ "historique" des métadonnées. Les modèles
déjà entraînés ne sont pas modifiés : il faut les ré-entraîner ensuite.
"""
import itertools
import re

import pandas as pd

import defect_categorization as dcmod
import ia_model_manager as iamod

CATEGORY = "humidite"
LABEL_TO_INT = {"sain": 0, "defaut": 1}
LABEL_TEXT = {"sain": "sain", "defaut": "défaut"}


def _natural_key(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text or "")]


def _read_curve(csv_path):
    df = pd.read_csv(csv_path, sep=";")
    df.columns = df.columns.astype(str).str.strip()
    return df


def _fmt(v):
    return "—" if v is None else f"{v:g}"


def list_tube_pairs(base_folder):
    """Retourne une liste de dicts, un par tube archivé :
    {name, date, ia_csv, ia_label ("sain"/"defaut"/None), cat_meta, humidity, radial}.
    Les champs ia_* valent None si le tube n'est pas dans l'archive IA ; cat_meta, humidity
    et radial valent None s'il n'est pas dans l'archive humidité / radial."""
    groups = {}
    for r in iamod.list_archived_tubes(base_folder):
        groups.setdefault(r["tube"], {"ia": [], "cat": []})["ia"].append(r)
    for r in dcmod.list_labeled_tubes(base_folder, [CATEGORY]):
        groups.setdefault(r["tube"], {"ia": [], "cat": []})["cat"].append(r)

    pairs = []
    for name in sorted(groups, key=_natural_key):
        ia = sorted(groups[name]["ia"], key=lambda r: r["date"] or "")
        cat = sorted(groups[name]["cat"], key=lambda r: r["date"] or "")
        for a, b in itertools.zip_longest(ia, cat):
            pairs.append({
                "name": name,
                "date": (a or b)["date"],
                "ia_csv": a["csv_path"] if a else None,
                "ia_label": a["label"] if a else None,
                "cat_meta": b["meta_path"] if b else None,
                "humidity": b["value"] if b else None,
                "radial": b["radial"] if b else None,
            })
    return pairs


def apply_tube_changes(base_folder, pair, new_name, new_label, new_humidity, new_radial):
    """Applique les valeurs finales du formulaire à un tube de list_tube_pairs().

    new_name     : nom final (obligatoire)
    new_label    : "sain", "defaut" ou None (= ne pas toucher / ne pas créer d'archive IA)
    new_humidity : taux d'humidité en % ou None
    new_radial   : résistance radiale en bar ou None (= pas de radial)

    Les contrôles sont faits AVANT toute écriture. Retourne la liste des actions réalisées
    (vide si rien n'a changé). Lève ValueError si une valeur est invalide."""
    name = (new_name or "").strip()
    has_ia = pair["ia_csv"] is not None
    has_cat = pair["cat_meta"] is not None

    # ---- contrôles ----
    if not name:
        raise ValueError("Le nom du tube ne peut pas être vide.")
    if new_label not in (None, "sain", "defaut"):
        raise ValueError("Le statut doit être « sain » ou « défaut ».")
    if new_humidity is not None and new_humidity < 0:
        raise ValueError("L'humidité ne peut pas être négative.")
    if new_radial is not None and new_radial < 0:
        raise ValueError("La résistance radiale ne peut pas être négative.")
    if has_cat and new_humidity is None:
        raise ValueError("L'humidité ne peut pas être vide : ce tube est archivé avec une humidité.")
    if not has_cat and new_humidity is None and new_radial is not None:
        raise ValueError("Pour enregistrer un radial, renseignez aussi l'humidité du tube.")

    # ---- courbes lues AVANT toute écriture : changer le statut déplace le fichier IA, et la
    # création de l'entrée manquante a besoin de cette même courbe ----
    curve_for_cat = _read_curve(pair["ia_csv"]) if (not has_cat and new_humidity is not None) else None
    curve_for_ia = (_read_curve(pair["cat_meta"][:-5] + ".csv")
                    if (not has_ia and new_label is not None) else None)

    actions = []
    old_name = pair["name"]
    if name != old_name:
        actions.append(f"Nom : {old_name} → {name}")

    # ---- archive IA (sain / défaut) ----
    if has_ia:
        iamod.rename_archived_tube(pair["ia_csv"], name)
        if new_label is not None and new_label != pair["ia_label"]:
            iamod.relabel_archived_tube(pair["ia_csv"], new_label)
            actions.append(f"Statut : {LABEL_TEXT[pair['ia_label']]} → {LABEL_TEXT[new_label]}")
    elif new_label is not None:
        iamod.archive_tube(base_folder, name, curve_for_ia, LABEL_TO_INT[new_label],
                           extra_info={"cree_depuis": "archive humidité / radial"})
        actions.append(f"Archive IA créée (statut : {LABEL_TEXT[new_label]}) à partir de la courbe "
                       "de l'archive humidité / radial")

    # ---- archive humidité / radial ----
    if has_cat:
        dcmod.update_labeled_tube(pair["cat_meta"], tube=name, value=new_humidity,
                                  radial=new_radial, radial_unit="bar")
        if new_humidity != pair["humidity"]:
            actions.append(f"Humidité : {_fmt(pair['humidity'])} → {_fmt(new_humidity)} %")
        if new_radial != pair["radial"]:
            actions.append(f"Radial : {_fmt(pair['radial'])} → {_fmt(new_radial)} bar")
    elif new_humidity is not None:
        dcmod.archive_labeled_tube(base_folder, CATEGORY, name, curve_for_cat, value=new_humidity, unit="%",
                                   radial=new_radial, radial_unit="bar",
                                   extra_info={"cree_depuis": "archive IA"})
        txt = f"humidité {_fmt(new_humidity)} %"
        if new_radial is not None:
            txt += f", radial {_fmt(new_radial)} bar"
        actions.append(f"Archive humidité / radial créée ({txt}) à partir de la courbe de l'archive IA")
    return actions
