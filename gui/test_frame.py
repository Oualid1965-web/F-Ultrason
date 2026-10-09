import os
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog, ttk

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import config as cfgmod
import daq_acquisition as daqmod
import signal_processing as spmod
import tube_comparator as tcmod
import reference_base_builder as rbb
import report_generator as rgmod
import ia_model_manager as iamod
import defect_categorization as dcmod
import archive_editor as aedmod
from .status_banner import StatusBanner


# Catégorie catégorisable (valeur continue), en plus de la décision bon/mauvais
# collage (gérée séparément par l'IA supervisée ci-dessous). Ajouter une catégorie
# ici suffirait à la refaire apparaître, mais pour l'instant seule l'humidité est
# gardée en plus de la décision de collage.
DEFECT_CATEGORIES = {
    "humidite": {"label": "Humidité", "unit": "%",
                 "prompt": "Taux d'humidité mesuré pour ce tube (%) — mesure de référence, pas une estimation :"},
}


class TestFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        header = tk.Frame(self)
        header.pack(fill="x", pady=8, padx=15)
        self.base_label = tk.Label(header, text="Base : -", font=("Segoe UI", 13, "bold"))
        self.base_label.pack(side="left")
        tk.Button(header, text="Accueil", command=lambda: controller.show_frame("HomeFrame")
                  ).pack(side="right", padx=5)
        tk.Button(header, text="Changer de base", command=lambda: controller.show_frame("SelectBaseFrame")
                  ).pack(side="right", padx=5)
        tk.Button(header, text="📏 Tests de position des capteurs",
                  command=self.go_position_tests).pack(side="right", padx=5)

        self.ia_label = tk.Label(self, text="IA : -", font=("Segoe UI", 9), fg="#555555")
        self.ia_label.pack(anchor="w", padx=18)

        actions = tk.Frame(self)
        actions.pack(pady=5)
        tk.Button(actions, text="🎙 Nouveau test (acquisition DAQ)", font=("Segoe UI", 11),
                  command=self.new_test_daq).grid(row=0, column=0, padx=8)
        tk.Button(actions, text="📂 Tester un tube existant (CSV)", font=("Segoe UI", 11),
                  command=self.new_test_import).grid(row=0, column=1, padx=8)

        # Bandeau en deux moitiés : verdict Health Index (gauche) et décision de l'IA (droite)
        self.banner = StatusBanner(self)
        self.banner.pack(fill="x", padx=15, pady=6)

        # Rangée de boutons du bas, réservée AVANT le corps de la page : c'est le corps
        # (graphique + colonne de droite) qui se réduit si la fenêtre est basse, jamais
        # cette rangée.
        bottom = tk.Frame(self)
        bottom.pack(side="bottom", pady=6)
        self.enrich_btn = tk.Button(bottom, text="➕ Ajouter ce tube à la base de référence",
                                     font=("Segoe UI", 10), state="disabled", command=self.enrich_base)
        self.enrich_btn.grid(row=0, column=0, padx=8)
        self.export_btn = tk.Button(bottom, text="💾 Exporter les données du tube (CSV)",
                                     font=("Segoe UI", 10), state="disabled", command=self.export_tube)
        self.export_btn.grid(row=0, column=1, padx=8)

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=15, pady=5)

        self.figure = Figure(figsize=(9, 6))
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)

        # Colonne de droite défilable : elle contient beaucoup de boutons (IA, humidité,
        # radial) et dépasserait sinon du bas de la fenêtre, masquant les derniers.
        # Elle est placée AVANT le graphique pour garder sa largeur complète : c'est le
        # graphique qui se réduit si la fenêtre est étroite.
        info_wrap = tk.Frame(body)
        info_wrap.pack(side="right", fill="y", padx=(10, 0))
        self.canvas.get_tk_widget().pack(side="left", fill="both", expand=True)
        info_scroll = ttk.Scrollbar(info_wrap, orient="vertical")
        info_scroll.pack(side="right", fill="y")
        info_canvas = tk.Canvas(info_wrap, highlightthickness=0, yscrollcommand=info_scroll.set)
        info_canvas.pack(side="left", fill="y")
        info_scroll.config(command=info_canvas.yview)
        info_col = tk.Frame(info_canvas)
        info_canvas.create_window((0, 0), window=info_col, anchor="nw")

        def _sync_info_canvas(event=None):
            info_canvas.configure(scrollregion=info_canvas.bbox("all"),
                                  width=info_col.winfo_reqwidth())
        info_col.bind("<Configure>", _sync_info_canvas)

        def _on_info_wheel(event):
            info_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        info_canvas.bind("<Enter>", lambda e: info_canvas.bind_all("<MouseWheel>", _on_info_wheel))
        info_canvas.bind("<Leave>", lambda e: info_canvas.unbind_all("<MouseWheel>"))
        self.info_canvas = info_canvas

        self.info_text = tk.Text(info_col, width=40, height=12, font=("Consolas", 9), state="disabled")
        self.info_text.pack(fill="both", expand=False)

        tk.Label(info_col, text="Archivage du tube testé :",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
        confirm_frame = tk.Frame(info_col)
        confirm_frame.pack(anchor="w")
        self.archive_sain_btn = tk.Button(confirm_frame, text="📌 Confirmer SAIN", state="disabled",
                                           command=lambda: self.archive_current(0))
        self.archive_sain_btn.grid(row=0, column=0, padx=3, pady=2)
        self.archive_defaut_btn = tk.Button(confirm_frame, text="🚩 Confirmer DÉFAUT", state="disabled",
                                             command=lambda: self.archive_current(1))
        self.archive_defaut_btn.grid(row=0, column=1, padx=3, pady=2)
        self.archive_category_btn = tk.Button(
            info_col, text="📌 Archiver avec humidité (et radial)",
            font=("Segoe UI", 9), state="disabled", command=self.archive_category)
        self.archive_category_btn.pack(anchor="w", fill="x", pady=(4, 2))

        self.archive_count_label = tk.Label(info_col, text="IA : 0 sain / 0 défaut",
                                             font=("Segoe UI", 9), fg="#555555")
        self.archive_count_label.pack(anchor="w")
        self.category_count_label = tk.Label(info_col, text="Humidité : 0 tube",
                                              font=("Segoe UI", 9), fg="#555555")
        self.category_count_label.pack(anchor="w")
        self.radial_count_label = tk.Label(info_col, text="Radial : 0 tube",
                                            font=("Segoe UI", 9), fg="#555555")
        self.radial_count_label.pack(anchor="w")

        tk.Button(info_col, text="🧠 Entraîner les modèles (IA, humidité, radial)",
                  font=("Segoe UI", 9, "bold"), command=self.train_all
                  ).pack(anchor="w", pady=(8, 2), fill="x")
        tk.Button(info_col, text="✏️ Corriger un tube archivé",
                  font=("Segoe UI", 9), command=self.edit_archived_tube
                  ).pack(anchor="w", pady=(2, 2), fill="x")

        self._current_tube_df = None
        self._current_tube_name = None
        self._current_eval = None

    def on_show(self):
        st = self.controller.state_data
        meta = st.current_base_meta or {}
        nb = len(meta.get("tubes_utilises", []))
        self.base_label.config(
            text=f"Base : {meta.get('nom', '?')}  |  {nb} tubes  |  "
                 f"MAJ : {meta.get('date_maj', meta.get('date_creation', '?'))}"
        )
        self._refresh_ia_status()
        self._refresh_category_count()
        self._refresh_radial_count()

    def _refresh_ia_status(self):
        st = self.controller.state_data
        cfg = st.cfg
        model_path = cfg.get("CHEMIN_MODELE_IA", "")
        active = "actif" if model_path and os.path.exists(model_path) else "inactif (base saine seule)"
        n_sain, n_defaut = (0, 0)
        if st.current_base_folder:
            n_sain, n_defaut = iamod.count_archives(st.current_base_folder)
        self.ia_label.config(text=f"IA supervisée : {active}   |   Archives disponibles : "
                                   f"{n_sain} sain(s) / {n_defaut} défaut(s)")
        self.archive_count_label.config(text=f"IA : {n_sain} sain / {n_defaut} défaut")

    def _show_info(self, ev, snr_acq):
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", tk.END)
        snr_txt = "N/A" if snr_acq is None else f"{snr_acq:.2f} dB"
        lines = [
            f"SNR acquisition : {snr_txt}",
            f"Health Index : {ev['health_index']} %",
            f"Corrélation : {ev['correlation']} %",
            f"Défauts P5/P95 : {ev['nb_defauts']} ({ev['ratio_defauts']} %)",
            f"MAE : {ev['mae']}",
            f"Z max : {ev['zmax']}",
            f"Ratio énergie : {ev['energie_ratio']}",
            f"Probabilité IA : {ev['probabilite_ia']}",
            f"Diagnostic IA : {ev['diagnostic_ia']}",
            f"STATUT FINAL : {ev['statut_final']}",
        ]
        for cat, info in (ev.get("categorisation") or {}).items():
            lines.append(f"  -> {cat.capitalize()} estimé(e) : {info['valeur']} {info['unite']}")
        self.info_text.insert(tk.END, "\n".join(lines))
        self.info_text.config(state="disabled")

    def _process_tube(self, name, DATA, fs_r, n_samples_r, tube_df, simulated=False):
        st = self.controller.state_data
        cfg = dict(st.cfg)
        cfg["MODELES_CATEGORISATION"] = dcmod.discover_models(st.current_base_folder)
        FREQ_R = tube_df["FREQ"].values
        FFT_SIGNAL = tube_df["FFT Real"].values + 1j * tube_df["FFT Imag"].values

        snr_acq = spmod.compute_snr(DATA, n_samples_r) if DATA is not None else None

        ev = tcmod.evaluate_tube(FREQ_R, tube_df[cfg["PARAMETRE"]].values, st.current_df_ref, cfg)

        rgmod.plot_test_result(self.figure, DATA, fs_r, n_samples_r, FREQ_R, FFT_SIGNAL, ev)
        self.canvas.draw()

        self._show_info(ev, snr_acq)

        if simulated:
            # Données aléatoires (simulation autorisée dans les Réglages) : aucun verdict
            # valable, rien n'est enregistré, et toutes les actions d'archivage restent bloquées.
            self.banner.show_simulation()
            self._current_tube_df = None
            self._current_tube_name = None
            self._current_eval = None
            for btn in (self.enrich_btn, self.export_btn, self.archive_sain_btn,
                        self.archive_defaut_btn, self.archive_category_btn):
                btn.config(state="disabled")
            return

        self.banner.show(ev)
        results_csv = os.path.join(st.current_base_folder, "resultats_tests.csv")
        rgmod.append_result_csv(results_csv, name, ev, snr_acq)

        self._current_tube_df = tube_df
        self._current_tube_name = name
        self._current_eval = ev
        self.enrich_btn.config(state="normal")
        self.export_btn.config(state="normal")
        self.archive_sain_btn.config(state="normal")
        self.archive_defaut_btn.config(state="normal")
        self.archive_category_btn.config(state="normal")
        self._refresh_category_count()
        self._refresh_radial_count()

    def go_position_tests(self):
        self.controller.show_frame("PositionTestFrame")

    def new_test_daq(self):
        st = self.controller.state_data
        if st.current_df_ref is None:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        cfg = st.cfg
        name = simpledialog.askstring("Nom du tube", "Nom / référence du tube testé :", parent=self)
        if not name:
            return
        try:
            daq = daqmod.DaqController(cfg)
            daq.init_daq()
            # Refuse de continuer si la carte n'est pas utilisée (données simulées), sauf
            # autorisation explicite dans les Réglages.
            daq.require_hardware(cfg.get("AUTORISER_SIMULATION", 0))
            DATA = daq.acquire()
            FREQ_R, FFT_SIGNAL = spmod.compute_fft(
                DATA, daq.fs_r_actual, cfg["F_MIN_FFT"], cfg["F_MAX_FFT"], cfg["N_POINTS_FFT"]
            )
            tube_df = spmod.tube_dataframe(FREQ_R, FFT_SIGNAL)
            self._process_tube(name, DATA, daq.fs_r_actual, daq.n_samples_r, tube_df,
                               simulated=daq.simulated)
        except Exception as e:
            messagebox.showerror("Erreur d'acquisition", str(e))

    def new_test_import(self):
        st = self.controller.state_data
        if st.current_df_ref is None:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        path = filedialog.askopenfilename(title="Sélectionner un fichier tube (CSV)",
                                           filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path, sep=";")
            df.columns = df.columns.astype(str).str.strip()
            name = os.path.basename(path)
            self._process_tube(name, None, None, None, df)
        except Exception as e:
            messagebox.showerror("Erreur d'import", str(e))

    def enrich_base(self):
        st = self.controller.state_data
        if self._current_tube_df is None:
            return
        if not messagebox.askyesno(
            "Confirmation",
            "Ajouter ce tube à la base de référence et recalculer les statistiques (base saine) ?"
        ):
            return
        cfg = st.cfg
        log_win, log = self._open_log_window("Mise à jour de la base de référence")
        try:
            result = rbb.enrich_reference_base(
                st.current_base_folder,
                [{"nom": self._current_tube_name, "df": self._current_tube_df}],
                cfg, log=log
            )
            st.current_df_ref = result["df_clean"]
            st.current_base_meta = rbb.load_metadata(st.current_base_folder)
            self.on_show()
            messagebox.showinfo("Base mise à jour", "La base de référence a été recalculée avec succès.")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def export_tube(self):
        if self._current_tube_df is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=self._current_tube_name or "tube.csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if path:
            self._current_tube_df.to_csv(path, sep=";", index=False)
            messagebox.showinfo("Export", f"Tube exporté vers {path}")

    # ------------------------------------------------------------------
    # IA supervisée : archivage des tubes confirmés + (ré)entraînement
    # ------------------------------------------------------------------

    def archive_current(self, label):
        st = self.controller.state_data
        if self._current_tube_df is None or not st.current_base_folder:
            return
        libelle = "SAIN" if label == 0 else "DÉFAUT DE COLLAGE"
        if not messagebox.askyesno(
            "Confirmer l'archivage",
            f"Confirmez-vous que ce tube est réellement « {libelle} » "
            "(contrôle terrain) ?\nIl sera utilisé pour entraîner le modèle IA."
        ):
            return
        try:
            iamod.archive_tube(
                st.current_base_folder, self._current_tube_name, self._current_tube_df,
                label, extra_info={"health_index": self._current_eval["health_index"] if self._current_eval else None}
            )
            self._refresh_ia_status()
            messagebox.showinfo("Archivé", f"Tube archivé comme « {libelle} ».")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def _open_log_window(self, title):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("560x420")
        txt = tk.Text(win, font=("Consolas", 9))
        txt.pack(fill="both", expand=True)

        def log(msg):
            txt.insert(tk.END, str(msg) + "\n")
            txt.see(tk.END)
            txt.update_idletasks()

        return win, log

    # ------------------------------------------------------------------
    # Catégorisation des défauts (humidité, manque/excès de colle...) : mêmes
    # principes que l'IA supervisée ci-dessus, mais valeur continue (régression)
    # au lieu d'un simple sain/défaut. La résistance radiale est transversale à
    # toutes les catégories (voir defect_categorization.train_radial_model).
    # ------------------------------------------------------------------

    def _current_category(self):
        return "humidite"

    def _refresh_category_count(self):
        st = self.controller.state_data
        if not st.current_base_folder:
            return
        cat = self._current_category()
        info = DEFECT_CATEGORIES[cat]
        n, vmin, vmax = dcmod.count_labeled_archives(st.current_base_folder, cat)
        txt = f"Humidité : {n} tube(s)"
        if n:
            txt += f" ({vmin:g} à {vmax:g} {info['unit']})"
        self.category_count_label.config(text=txt)

    def _refresh_radial_count(self):
        st = self.controller.state_data
        if not st.current_base_folder:
            return
        n, vmin, vmax = dcmod.count_radial_archives(st.current_base_folder, list(DEFECT_CATEGORIES.keys()))
        txt = f"Radial : {n} tube(s)"
        if n:
            txt += f" ({vmin:g} à {vmax:g} bar)"
        self.radial_count_label.config(text=txt)

    def archive_category(self):
        st = self.controller.state_data
        if self._current_tube_df is None or not st.current_base_folder:
            return
        cat = self._current_category()
        info = DEFECT_CATEGORIES[cat]
        valeur = simpledialog.askfloat(f"{info['label']} connu(e)", info["prompt"], parent=self)
        if valeur is None:
            return
        radial = simpledialog.askfloat(
            "Résistance radiale (optionnel)",
            "Résistance radiale connue pour ce tube (bar) — laissez vide si non mesurée "
            "pour l'instant, vous pourrez l'ajouter plus tard :",
            parent=self,
        )
        try:
            dcmod.archive_labeled_tube(
                st.current_base_folder, cat, self._current_tube_name,
                self._current_tube_df, value=valeur, unit=info["unit"],
                radial=radial, radial_unit="bar",
                extra_info={"health_index": self._current_eval["health_index"] if self._current_eval else None}
            )
            self._refresh_category_count()
            self._refresh_radial_count()
            msg = f"Tube archivé — {info['label']} : {valeur} {info['unit']}."
            if radial is not None:
                msg += f"\nRésistance radiale : {radial} bar."
                if "radial" not in dcmod.discover_models(st.current_base_folder):
                    msg += ("\n\n⚠ Le modèle Radial n'a encore jamais été entraîné — "
                            "l'archivage seul ne suffit pas. Cliquez sur « Entraîner le "
                            "modèle Radial » quand vous aurez assez de tubes pour qu'il "
                            "s'affiche dans les résultats.")
            messagebox.showinfo("Archivé", msg)
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    # ------------------------------------------------------------------
    # Entraînement unique et correction des tubes archivés
    # ------------------------------------------------------------------

    def train_all(self):
        """Entraîne d'un coup les trois modèles : IA (bon / mauvais collage), humidité et
        radial. Un modèle qui n'a pas assez d'exemples est simplement ignoré, avec la raison."""
        st = self.controller.state_data
        if not st.current_base_folder:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        cfg = st.cfg
        base = st.current_base_folder
        n_bins = cfg.get("IA_N_BINS", 20)
        log_win, log = self._open_log_window("Entraînement des modèles : IA, humidité, radial")
        results = []

        def run(title, short, fn):
            log("\n" + "=" * 56 + f"\n{title}\n" + "=" * 56)
            try:
                results.append(("ok", fn()))
            except ValueError as e:                    # pas assez d'exemples
                log(f"⚠ Ignoré : {e}")
                results.append(("skip", f"{short} : ignoré, {str(e).split('. ')[0].rstrip('.')}."))
            except Exception as e:
                log(f"✖ Erreur : {e}")
                results.append(("err", f"{short} : erreur, {e}"))

        def train_ia():
            model_path, b = iamod.train_ia_model(base, cfg, n_bins=n_bins, log=log)
            cfg["CHEMIN_MODELE_IA"] = model_path
            cfgmod.save_config(cfg)
            auc = b.get("auc_cv")
            return (f"IA : {b['n_sain']} sain(s) et {b['n_defaut']} défaut(s)"
                    + (f", AUC {auc:.2f}" if auc is not None else ""))

        def train_humidity():
            _, b = dcmod.train_regression_model(base, "humidite", cfg, n_bins=n_bins, log=log)
            return (f"Humidité : {b['n_samples']} tubes"
                    + (f", R² {b['r2_cv']:.2f}" if b["r2_cv"] is not None else ""))

        def train_radial():
            _, b = dcmod.train_radial_model(base, list(DEFECT_CATEGORIES.keys()), cfg, n_bins=n_bins, log=log)
            return (f"Radial : {b['n_samples']} tubes"
                    + (f", R² {b['r2_cv']:.2f}" if b["r2_cv"] is not None else ""))

        run("1. Modèle IA (bon / mauvais collage)", "IA", train_ia)
        run("2. Modèle humidité", "Humidité", train_humidity)
        run("3. Modèle radial", "Radial", train_radial)

        self._refresh_ia_status()
        self._refresh_category_count()
        self._refresh_radial_count()

        marks = {"ok": "✔", "skip": "⚠", "err": "✖"}
        lines = [f"{marks[kind]} {text}" for kind, text in results]
        trained = sum(1 for kind, _ in results if kind == "ok")
        msg = "\n".join(lines)
        if trained:
            msg += ("\n\nLes modèles entraînés sont utilisés automatiquement lors des prochains tests."
                    "\nAUC et R² viennent d'une validation croisée sur les acquisitions : plusieurs "
                    "acquisitions d'un même tube se ressemblent, ce qui les rend optimistes. "
                    "Validez sur des tubes jamais archivés.")
        if trained == len(results):
            messagebox.showinfo("Modèles entraînés", msg)
        else:
            messagebox.showwarning("Entraînement terminé", msg)

    def edit_archived_tube(self):
        """Corrige un tube déjà archivé, quelle que soit l'archive : nom, statut sain / défaut,
        humidité, radial. Les deux archives (IA et humidité / radial) sont tenues cohérentes."""
        st = self.controller.state_data
        if not st.current_base_folder:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        base = st.current_base_folder
        win = tk.Toplevel(self)
        win.title("Corriger un tube archivé")
        win.geometry("960x660")

        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="Rechercher un tube :", font=("Segoe UI", 10)).pack(side="left")
        search_var = tk.StringVar()
        tk.Entry(top, textvariable=search_var, width=24).pack(side="left", padx=6)
        count_lbl = tk.Label(top, text="", font=("Segoe UI", 10), fg="#555555")
        count_lbl.pack(side="right")

        columns = ("tube", "statut", "humidite", "radial", "date")
        tree = ttk.Treeview(win, columns=columns, show="headings", selectmode="browse", height=13)
        for c, h, w in zip(columns, ("Tube", "Statut IA", "Humidité", "Radial", "Archivé le"),
                           (250, 100, 120, 120, 190)):
            tree.heading(c, text=h)
            tree.column(c, width=w)
        tree.pack(fill="both", expand=True, padx=10, pady=4)

        form = tk.LabelFrame(win, text="Corriger le tube sélectionné", font=("Segoe UI", 10, "bold"),
                             padx=10, pady=8)
        form.pack(fill="x", padx=10, pady=6)
        name_var, status_var, hum_var, rad_var = (tk.StringVar() for _ in range(4))
        tk.Label(form, text="Nom :").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        tk.Entry(form, textvariable=name_var, width=28).grid(row=0, column=1, sticky="w")
        tk.Label(form, text="Statut :").grid(row=0, column=2, sticky="e", padx=(18, 4))
        ttk.Combobox(form, state="readonly", width=12, textvariable=status_var,
                     values=["", "Sain", "Défaut"]).grid(row=0, column=3, sticky="w")
        tk.Label(form, text="Humidité (%) :").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        tk.Entry(form, textvariable=hum_var, width=12).grid(row=1, column=1, sticky="w")
        tk.Label(form, text="Radial (bar) :").grid(row=1, column=2, sticky="e", padx=(18, 4))
        tk.Entry(form, textvariable=rad_var, width=12).grid(row=1, column=3, sticky="w")
        tk.Label(form, text=("Statut vide : tube non archivé en IA (laissez vide pour ne rien créer). "
                             "Radial vide : non mesuré. La virgule est acceptée pour les nombres."),
                 font=("Segoe UI", 9), fg="#555555", wraplength=880, justify="left"
                 ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        result_lbl = tk.Label(win, text="", font=("Segoe UI", 9, "bold"), wraplength=900, justify="left")
        result_lbl.pack(anchor="w", padx=10)
        reminder = tk.Label(win, text="", font=("Segoe UI", 9, "bold"), fg="#b31412",
                            wraplength=900, justify="left")
        reminder.pack(anchor="w", padx=10)

        rows = {}
        status_text = {"sain": "Sain", "defaut": "Défaut"}
        keep_result = {"on": False}   # garde le message vert pendant la re-sélection automatique

        def clear_form():
            for v in (name_var, status_var, hum_var, rad_var):
                v.set("")

        def on_select(event=None):
            sel = tree.selection()
            if not sel:
                return
            p = rows[sel[0]]
            name_var.set(p["name"])
            status_var.set(status_text.get(p["ia_label"], ""))
            hum_var.set("" if p["humidity"] is None else str(p["humidity"]))
            rad_var.set("" if p["radial"] is None else str(p["radial"]))
            if not keep_result["on"]:
                result_lbl.config(text="")

        def refresh(select_name=None):
            pairs = aedmod.list_tube_pairs(base)
            needle = search_var.get().strip().lower()
            tree.delete(*tree.get_children())
            rows.clear()
            shown = 0
            for i, p in enumerate(pairs):
                if needle and needle not in p["name"].lower():
                    continue
                iid = str(i)
                rows[iid] = p
                shown += 1
                tree.insert("", "end", iid=iid, values=(
                    p["name"], status_text.get(p["ia_label"], "—"),
                    "—" if p["humidity"] is None else f"{p['humidity']:g} %",
                    "—" if p["radial"] is None else f"{p['radial']:g} bar",
                    p["date"] or "",
                ))
            count_lbl.config(text=f"{shown} tube(s) affiché(s) sur {len(pairs)}")
            clear_form()
            if select_name:
                for iid, p in rows.items():
                    if p["name"] == select_name:
                        tree.selection_set(iid)
                        tree.see(iid)
                        on_select()
                        break
            self._refresh_ia_status()
            self._refresh_category_count()
            self._refresh_radial_count()

        def parse_number(text, label):
            text = text.strip().replace(",", ".")
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                raise ValueError(f"{label} : « {text} » n'est pas un nombre.")

        def save():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Attention", "Sélectionnez d'abord un tube dans la liste.", parent=win)
                return
            p = rows[sel[0]]
            new_name = name_var.get().strip()
            try:
                hum = parse_number(hum_var.get(), "Humidité")
                rad = parse_number(rad_var.get(), "Radial")
                label = {"Sain": "sain", "Défaut": "defaut", "": None}[status_var.get()]
                if new_name and new_name != p["name"] and any(
                        q["name"] == new_name for q in aedmod.list_tube_pairs(base)):
                    if not messagebox.askyesno(
                            "Nom déjà utilisé",
                            f"Un autre tube archivé s'appelle déjà « {new_name} ».\n"
                            "Continuer quand même ?", parent=win):
                        return
                actions = aedmod.apply_tube_changes(base, p, new_name, label, hum, rad)
            except ValueError as e:
                messagebox.showerror("Valeur invalide", str(e), parent=win)
                return
            except Exception as e:
                messagebox.showerror(
                    "Erreur", f"La correction a échoué : {e}\n\nLa liste est actualisée : vérifiez l'état "
                              "réel du tube avant de recommencer.", parent=win)
                refresh()
                return
            if not actions:
                result_lbl.config(text="Aucune modification à enregistrer.", fg="#555555")
                return
            keep_result["on"] = True
            refresh(select_name=new_name)
            result_lbl.config(text="Enregistré : " + " ; ".join(actions), fg="#1e8e3e")
            win.after(300, lambda: keep_result.update(on=False))
            reminder.config(text="Les modèles déjà entraînés ne tiennent pas compte de cette correction : "
                                 "cliquez sur « Entraîner les modèles ».")

        tree.bind("<<TreeviewSelect>>", on_select)
        search_var.trace_add("write", lambda *a: refresh())

        btns = tk.Frame(win)
        btns.pack(pady=(4, 12))
        tk.Button(btns, text="💾 Enregistrer la correction", font=("Segoe UI", 10, "bold"),
                  command=save).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="🧠 Entraîner les modèles", font=("Segoe UI", 10),
                  command=self.train_all).grid(row=0, column=1, padx=6)
        tk.Button(btns, text="Fermer", font=("Segoe UI", 10), command=win.destroy).grid(row=0, column=2, padx=6)

        refresh()
