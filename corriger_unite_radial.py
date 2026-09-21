"""
Corrige l'étiquette d'unité des archives de catégorisation déjà enregistrées :
remplace "radial_unit": "N" par "bar" dans les fichiers de métadonnées existants.

NE TOUCHE PAS à la valeur numérique du radial elle-même — les valeurs saisies
étaient déjà en bar, seule l'étiquette affichée était fausse. Aucune conversion
n'est faite, juste une correction de texte dans les métadonnées.

Utilisation :
    python corriger_unite_radial.py "C:/chemin/vers/data/reference_bases/NOM_BASE"
"""
import os
import sys
import glob
import json


def corriger_unite(base_folder):
    pattern = os.path.join(base_folder, "categorisation_archive", "*", "*.json")
    fichiers = glob.glob(pattern)
    if not fichiers:
        print(f"Aucun fichier trouvé dans : {pattern}")
        return

    corriges = 0
    deja_bon = 0
    sans_radial = 0

    for fn in fichiers:
        with open(fn, encoding="utf-8") as f:
            meta = json.load(f)

        if meta.get("radial") is None:
            sans_radial += 1
            continue

        ancienne_unite = meta.get("radial_unit")
        if ancienne_unite == "bar":
            deja_bon += 1
            continue

        meta["radial_unit"] = "bar"
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        corriges += 1
        print(f"  Corrigé : {os.path.basename(fn)} "
              f"(radial={meta['radial']}, unité '{ancienne_unite}' -> 'bar')")

    print(f"\nTerminé : {corriges} fichier(s) corrigé(s), "
          f"{deja_bon} déjà en bar, {sans_radial} sans valeur radiale.")
    print("Les valeurs numériques n'ont pas été modifiées — seule l'étiquette d'unité l'a été.")

    if corriges > 0:
        print("\nIMPORTANT : si un modèle Radial a déjà été entraîné avec cette base, "
              "il reste valide (il ne stocke pas l'unité affichée) — pas besoin de le "
              "réentraîner à cause de ce correctif.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        base_folder = sys.argv[1]
    else:
        base_folder = input("Chemin du dossier de la base (data/reference_bases/NOM_BASE) : ").strip()
        base_folder = base_folder.strip('"').strip("'")

    if not os.path.isdir(base_folder):
        print(f"Dossier introuvable : {base_folder}")
        sys.exit(1)

    corriger_unite(base_folder)
    input("\nAppuyez sur Entrée pour fermer...")
