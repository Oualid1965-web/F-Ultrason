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


STATUS_COLORS = {
    "CONFORME": "#1e8e3e",
    "REJET": "#d93025",
    "REJET IA": "#b31412",
}

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

        self.status_label = tk.Label(self, text="Aucun test effectué", font=("Segoe UI", 16, "bold"),
                                      fg="white", bg="#888888", pady=8)
        self.status_label.pack(fill="x", padx=15, pady=6)

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=15, pady=5)

        self.figure = Figure(figsize=(9, 6))
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)
        self.canvas.get_tk_widget().pack(side="left", fill="both", expand=True)

        info_col = tk.Frame(body, width=300)
        info_col.pack(side="left", fill="y", padx=10)
        self.info_text = tk.Text(info_col, width=40, height=18, font=("Consolas", 9), state="disabled")
        self.info_text.pack(fill="both", expand=False)

        tk.Label(info_col, text="Confirmation terrain (archivage IA) :",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
        confirm_frame = tk.Frame(info_col)
        confirm_frame.pack(anchor="w")
        self.archive_sain_btn = tk.Button(confirm_frame, text="📌 Confirmer SAIN", state="disabled",
                                           command=lambda: self.archive_current(0))
        self.archive_sain_btn.grid(row=0, column=0, padx=3, pady=2)
        self.archive_defaut_btn = tk.Button(confirm_frame, text="🚩 Confirmer DÉFAUT", state="disabled",
                                             command=lambda: self.archive_current(1))
        self.archive_defaut_btn.grid(row=0, column=1, padx=3, pady=2)

        self.archive_count_label = tk.Label(info_col, text="Archives : 0 sain / 0 défaut",
                                             font=("Segoe UI", 9), fg="#555555")
        self.archive_count_label.pack(anchor="w", pady=(4, 0))

        tk.Button(info_col, text="🧠 Entraîner / Mettre à jour le modèle IA",
                  font=("Segoe UI", 9, "bold"), command=self.train_ia).pack(anchor="w", pady=(10, 2), fill="x")

        # --- Catégorisation Humidité, en plus de la décision bon/mauvais collage (IA) ---
        tk.Label(info_col, text="Catégorisation — Humidité :",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(14, 2))

        self.archive_category_btn = tk.Button(
            info_col, text="📌 Archiver ce tube avec un taux d'humidité connu",
            font=("Segoe UI", 9), state="disabled", command=self.archive_category)
        self.archive_category_btn.pack(anchor="w", fill="x", pady=(4, 0))
        self.category_count_label = tk.Label(info_col, text="Archives : 0",
                                              font=("Segoe UI", 9), fg="#555555")
        self.category_count_label.pack(anchor="w", pady=(2, 0))
        tk.Button(info_col, text="🧠 Entraîner le modèle Humidité",
                  font=("Segoe UI", 9, "bold"), command=self.train_category
                  ).pack(anchor="w", pady=(4, 8), fill="x")

        tk.Label(info_col, text="Résistance radiale (optionnelle, toutes catégories) :",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
        tk.Button(info_col, text="🔧 Ajouter/modifier le radial d'un tube archivé",
                  font=("Segoe UI", 9), command=self.edit_radial_archive
                  ).pack(anchor="w", fill="x")
        self.radial_count_label = tk.Label(info_col, text="Tubes avec radial connu : 0",
                                            font=("Segoe UI", 9), fg="#555555")
        self.radial_count_label.pack(anchor="w", pady=(2, 0))
        tk.Button(info_col, text="🧠 Entraîner le modèle Radial",
                  font=("Segoe UI", 9, "bold"), command=self.train_radial
                  ).pack(anchor="w", pady=(4, 2), fill="x")

        bottom = tk.Frame(self)
        bottom.pack(pady=6)
        self.enrich_btn = tk.Button(bottom, text="➕ Ajouter ce tube à la base de référence",
                                     font=("Segoe UI", 10), state="disabled", command=self.enrich_base)
        self.enrich_btn.grid(row=0, column=0, padx=8)
        self.export_btn = tk.Button(bottom, text="💾 Exporter les données du tube (CSV)",
                                     font=("Segoe UI", 10), state="disabled", command=self.export_tube)
        self.export_btn.grid(row=0, column=1, padx=8)

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
        self.archive_count_label.config(text=f"Archives : {n_sain} sain / {n_defaut} défaut")

    def _set_status(self, statut):
        color = STATUS_COLORS.get(statut, "#888888")
        self.status_label.config(text=f"Résultat : {statut}", bg=color)

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
            f"Statut base saine : {ev['statut_base']}",
            f"Probabilité IA : {ev['probabilite_ia']}",
            f"Diagnostic IA : {ev['diagnostic_ia']}",
            "",
            f"STATUT FINAL : {ev['statut_final']}",
        ]
        for cat, info in (ev.get("categorisation") or {}).items():
            lines.append(f"  -> {cat.capitalize()} estimé(e) : {info['valeur']} {info['unite']}")
        self.info_text.insert(tk.END, "\n".join(lines))
        self.info_text.config(state="disabled")

    def _process_tube(self, name, DATA, fs_r, n_samples_r, tube_df):
        st = self.controller.state_data
        cfg = dict(st.cfg)
        cfg["MODELES_CATEGORISATION"] = dcmod.discover_models(st.current_base_folder)
        FREQ_R = tube_df["FREQ"].values
        FFT_SIGNAL = tube_df["FFT Real"].values + 1j * tube_df["FFT Imag"].values

        snr_acq = spmod.compute_snr(DATA, n_samples_r) if DATA is not None else None

        ev = tcmod.evaluate_tube(FREQ_R, tube_df[cfg["PARAMETRE"]].values, st.current_df_ref, cfg)

        rgmod.plot_test_result(self.figure, DATA, fs_r, n_samples_r, FREQ_R, FFT_SIGNAL, ev)
        self.canvas.draw()

        self._set_status(ev["statut_final"])
        self._show_info(ev, snr_acq)

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
            DATA = daq.acquire()
            FREQ_R, FFT_SIGNAL = spmod.compute_fft(
                DATA, daq.fs_r_actual, cfg["F_MIN_FFT"], cfg["F_MAX_FFT"], cfg["N_POINTS_FFT"]
            )
            tube_df = spmod.tube_dataframe(FREQ_R, FFT_SIGNAL)
            self._process_tube(name, DATA, daq.fs_r_actual, daq.n_samples_r, tube_df)
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

    def train_ia(self):
        st = self.controller.state_data
        if not st.current_base_folder:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        cfg = st.cfg
        log_win, log = self._open_log_window("Entraînement du modèle IA")
        try:
            model_path, bundle = iamod.train_ia_model(
                st.current_base_folder, cfg, n_bins=cfg.get("IA_N_BINS", 20), log=log
            )
            cfg["CHEMIN_MODELE_IA"] = model_path
            cfgmod.save_config(cfg)
            self._refresh_ia_status()
            messagebox.showinfo(
                "Modèle IA entraîné",
                f"Modèle entraîné sur {bundle['n_sain']} sain(s) / {bundle['n_defaut']} défaut(s).\n"
                f"AUC (validation croisée) : {bundle['auc_cv']:.3f}\n\n"
                "Ce modèle est désormais utilisé automatiquement lors des prochains tests."
            )
        except Exception as e:
            messagebox.showerror("Erreur d'entraînement", str(e))

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
        txt = f"Archives : {n}"
        if n:
            txt += f" ({vmin}{info['unit']} à {vmax}{info['unit']})"
        self.category_count_label.config(text=txt)

    def _refresh_radial_count(self):
        st = self.controller.state_data
        if not st.current_base_folder:
            return
        n, vmin, vmax = dcmod.count_radial_archives(st.current_base_folder, list(DEFECT_CATEGORIES.keys()))
        txt = f"Tubes avec radial connu : {n}"
        if n:
            txt += f" ({vmin} à {vmax} bar)"
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

    def train_category(self):
        st = self.controller.state_data
        if not st.current_base_folder:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        cat = self._current_category()
        info = DEFECT_CATEGORIES[cat]
        cfg = st.cfg
        log_win, log = self._open_log_window(f"Entraînement du modèle {info['label']}")
        try:
            model_path, bundle = dcmod.train_regression_model(
                st.current_base_folder, cat, cfg, n_bins=cfg.get("IA_N_BINS", 20), log=log
            )
            r2_txt = "N/A" if bundle["r2_cv"] is None else f"{bundle['r2_cv']:.3f}"
            messagebox.showinfo(
                f"Modèle {info['label']} entraîné",
                f"Modèle entraîné sur {bundle['n_samples']} tube(s) "
                f"({bundle['value_min']}{info['unit']} à {bundle['value_max']}{info['unit']}).\n"
                f"R² (validation croisée) : {r2_txt}\n\n"
                "Ce modèle est désormais utilisé automatiquement : dès qu'un tube "
                "est classé REJET, cette valeur estimée s'affichera."
            )
        except Exception as e:
            messagebox.showerror("Erreur d'entraînement", str(e))

    def train_radial(self):
        st = self.controller.state_data
        if not st.current_base_folder:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        cfg = st.cfg
        log_win, log = self._open_log_window("Entraînement du modèle Radial")
        try:
            model_path, bundle = dcmod.train_radial_model(
                st.current_base_folder, list(DEFECT_CATEGORIES.keys()), cfg,
                n_bins=cfg.get("IA_N_BINS", 20), log=log
            )
            r2_txt = "N/A" if bundle["r2_cv"] is None else f"{bundle['r2_cv']:.3f}"
            messagebox.showinfo(
                "Modèle Radial entraîné",
                f"Modèle entraîné sur {bundle['n_samples']} tube(s), toutes catégories confondues "
                f"({bundle['value_min']} à {bundle['value_max']} bar).\n"
                f"R² (validation croisée) : {r2_txt}"
            )
        except Exception as e:
            messagebox.showerror("Erreur d'entraînement", str(e))

    def edit_radial_archive(self):
        """Parcourt les tubes déjà archivés (toutes catégories) pour y ajouter ou
        corriger une valeur de résistance radiale, sans refaire d'acquisition —
        utile pour les tubes déjà testés avant que le suivi radial n'existe."""
        st = self.controller.state_data
        if not st.current_base_folder:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        records = dcmod.list_labeled_tubes(st.current_base_folder, list(DEFECT_CATEGORIES.keys()))
        if not records:
            messagebox.showinfo("Aucune archive", "Aucun tube archivé pour l'instant.")
            return

        win = tk.Toplevel(self)
        win.title("Modifier une archive — ajouter/corriger le radial")
        win.geometry("620x400")

        columns = ("tube", "categorie", "valeur", "radial")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=15)
        for c, h, w in zip(columns, ("Tube", "Catégorie", "Valeur", "Radial actuel"), (160, 130, 120, 120)):
            tree.heading(c, text=h)
            tree.column(c, width=w)
        tree.pack(fill="both", expand=True, padx=8, pady=8)

        for rec in records:
            label = DEFECT_CATEGORIES.get(rec["category"], {}).get("label", rec["category"])
            radial_txt = "-" if rec["radial"] is None else f"{rec['radial']} {rec['radial_unit']}"
            tree.insert("", "end", iid=rec["meta_path"], values=(
                rec["tube"], label, f"{rec['value']} {rec['unit']}", radial_txt
            ))

        def on_edit():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Attention", "Sélectionnez un tube dans la liste.", parent=win)
                return
            meta_path = sel[0]
            radial = simpledialog.askfloat(
                "Résistance radiale", "Nouvelle valeur de résistance radiale (bar) :", parent=win
            )
            if radial is None:
                return
            dcmod.update_radial(meta_path, radial, radial_unit="bar")
            values = list(tree.item(meta_path)["values"])
            values[3] = f"{radial} bar"
            tree.item(meta_path, values=values)
            self._refresh_radial_count()
            refresh_reminder()

        tk.Button(win, text="Modifier le radial du tube sélectionné", command=on_edit
                  ).pack(pady=(0, 4))

        reminder_label = tk.Label(win, text="", font=("Segoe UI", 9, "bold"), fg="#b31412")
        reminder_label.pack(pady=(0, 8))

        def refresh_reminder():
            if "radial" not in dcmod.discover_models(st.current_base_folder):
                reminder_label.config(
                    text="⚠ N'oubliez pas de cliquer sur « Entraîner le modèle Radial » "
                         "une fois vos valeurs saisies — l'archivage seul ne suffit pas."
                )
            else:
                reminder_label.config(text="")

        refresh_reminder()
