# Contrôle Ultrason — Collage HAPS

Application de bureau (Tkinter) qui réunit vos 4 scripts en un seul outil guidé :

- `ACQUISITION_GUI.py` → acquisition DAQ (`daq_acquisition.py`, `signal_processing.py`)
- `Base de reference.txt` → construction de la base saine (`reference_base_builder.py`)
- `Principal.txt` → comparaison Health Index + IA supervisée (`tube_comparator.py`, `ia_model_manager.py`)
- `Graphe.txt` → graphes de comparaison / défauts (`report_generator.py`)

## 1. Installation

Prérequis : Python 3.10+ et, pour l'acquisition réelle, le driver **NI-DAQmx** installé
(fourni par National Instruments — pas seulement le paquet Python).

```bash
cd UltrasonApp
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

> Sans matériel NI-DAQ branché ou sans le driver installé, l'application bascule
> automatiquement en **mode simulation** (données aléatoires) pour que vous puissiez
> tester toute l'interface sans matériel.

## 2. Lancement

```bash
python main.py
```

## 3. Flux d'utilisation

### Accueil
Deux choix : **utiliser une base existante** ou **créer une nouvelle base**.

### Créer une nouvelle base de référence
1. Donnez un nom à la base.
2. Ajoutez des tubes un par un, sans limite de nombre :
   - **Acquérir un tube (DAQ)** : lance une acquisition réelle (ou simulée) et l'ajoute
     à la liste ;
   - **Importer un tube (CSV)** : réutilise un fichier déjà exporté par
     `ACQUISITION_GUI.py` (`FREQ;FFT Real;FFT Imag;FFT Abs`).
3. Cliquez sur **Terminer et construire la base** quand vous avez fini. Le journal
   affiche exactement les mêmes sorties que `Base de reference.txt` :
   `SCORES TUBES (avant filtrage)`, `FILTRAGE OUTLIERS`, `TUBES REJETÉS`,
   `BASE SAINE EXPORTÉE`.
4. La base est enregistrée sur disque (`data/reference_bases/<nom>/`) — elle n'a plus
   besoin d'être recréée. Cliquez sur **Continuer vers les tests**.

### Utiliser une base existante
La liste de toutes les bases enregistrées s'affiche (nom, dates, nombre de tubes,
paramètre). Sélectionnez-en une pour passer directement aux tests.

### Tester un tube
- **Nouveau test (acquisition DAQ)** ou **Tester un tube existant (CSV)**.
- Le résultat s'affiche immédiatement : **ACCEPTÉ / SUSPECT / REJET** (ou **REJET IA**),
  avec le Health Index, la corrélation, le nombre de défauts P5/P95, le MAE, le Z max,
  le ratio d'énergie, et — si le modèle IA est actif — sa probabilité et son diagnostic.
- Les graphes reprennent ceux de `Graphe.txt` : signal temporel, zoom FFT, comparaison
  à la bande P5/P95 de la base saine, et détection des points en défaut.
- Chaque test est ajouté automatiquement à `resultats_tests.csv` dans le dossier de la
  base (équivalent du `RESULTATS_EXPORTES` de `Principal.txt`).
- **Ajouter ce tube à la base de référence** : enrichit la base saine avec ce nouveau
  tube et recalcule immédiatement les statistiques (moyenne/écart-type/P5/P95/SNR) —
  la base peut ainsi grandir indéfiniment sans jamais repartir de zéro.

### IA supervisée (nouveau) — archivage des défauts pour enrichir le modèle
Le Health Index (base saine) reste la première ligne de décision. L'IA vient en renfort
uniquement quand le Health Index est en dessous de `SEUIL_ACTIVATION_IA`, exactement
comme dans `Principal.txt`.

Pour que l'IA apprenne vos vrais cas de collage défectueux :
1. Après un test, une fois le diagnostic terrain confirmé (contrôle visuel, découpe,
   retour qualité...), cliquez sur **📌 Confirmer SAIN** ou **🚩 Confirmer DÉFAUT** —
   le tube est archivé dans `ia_archive/sain/` ou `ia_archive/defaut/` (propre à
   chaque base).
2. Quand vous avez au moins 2 exemples de chaque classe (idéalement beaucoup plus),
   cliquez sur **🧠 Entraîner / Mettre à jour le modèle IA**. Le modèle
   (RandomForest + StandardScaler, avec AUC en validation croisée affichée dans le
   journal) est réentraîné sur **tous** les tubes archivés pour cette base, et
   enregistré dans `ia_model.joblib`. Il est automatiquement activé pour les tests
   suivants (mis à jour dans `CHEMIN_MODELE_IA`).
3. Vous pouvez répéter l'archivage/entraînement à volonté au fil des contrôles : plus
   vous confirmez de cas, plus l'IA se précise. Le format du modèle produit est
   strictement compatible avec celui attendu par `Principal.txt`
   (`scaler`, `model`, `bins`, `freq_ref`, `parametre`, `auc_cv`, `n_sain`, `n_defaut`),
   donc un modèle entraîné sous Google Colab avec ce même format peut aussi être chargé
   manuellement via **Paramètres → CHEMIN_MODELE_IA**.

### Paramètres
Tous les seuils sont modifiables et persistés (`data/config.json`) :

- `PARAMETRE`, `SEUIL_SNR`, `SEUIL_ACCEPT`, `SEUIL_SUSPECT`, `DECIMATION`, `IQR_FACTOR`
- `SEUIL_ACTIVATION_IA`, `IA_N_BINS`, `CHEMIN_MODELE_IA`
- Tous les paramètres d'acquisition DAQ (`DEVICE_NAME`, `T_SWEEP`, `FS_E`, `F_MIN`,
  `F_MAX`, `AMP`, `FS_R`, `AVERAGES`, `N_POINTS_FFT`, `F_MIN_FFT`, `F_MAX_FFT`).

## 4. Organisation des données

```
data/
  config.json
  reference_bases/
    <Nom_de_la_base>/
      base_saine.csv          # Frequency_Hz, Mean_HAPS, STD_HAPS, P5_HAPS, P95_HAPS, SNR
      metadata.json           # nom, dates, tubes utilisés/rejetés, scores
      tubes/                  # copie brute des tubes utilisés (pour l'enrichissement)
      resultats_tests.csv     # historique de tous les tests réalisés sur cette base
      ia_archive/
        sain/                 # tubes confirmés sains (archivés depuis l'interface)
        defaut/                # tubes confirmés défectueux
      ia_model.joblib          # modèle IA entraîné (si applicable)
```

## 5. Limites connues / pistes d'amélioration

- L'acquisition DAQ bloque momentanément l'interface pendant la durée du balayage
  (`T_SWEEP × AVERAGES`) ; pour des balayages longs, on peut faire évoluer
  `daq_acquisition.py` vers un thread dédié.
- L'export PDF illustré de `Graphe.txt` n'est pas encore automatisé (les graphes
  sont affichés à l'écran) ; il est facile d'ajouter un bouton « Exporter en PDF »
  en réutilisant `matplotlib.backends.backend_pdf.PdfPages` sur `self.figure`.
