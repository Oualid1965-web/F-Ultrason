import os
import tkinter as tk
from tkinter import messagebox, simpledialog

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tkinter import ttk

import daq_acquisition as daqmod
import signal_processing as spmod
import tube_comparator as tcmod
import report_generator as rgmod


STATUS_COLORS = {
    "ACCEPTE": "#1e8e3e",
    "SUSPECT": "#f9ab00",
    "REJET": "#d93025",
    "REJET IA": "#b31412",
}

# Positions testées, en cm depuis le centre — les deux capteurs sont positionnés
# à la MÊME distance du centre à chaque étape (ex. Gauche à 4 cm ET Droit à 4 cm).
POSITIONS_CM = [0, 2, 4, 6, 8, 10, 12, 14, 16]

SIDE_TO_CHANNEL = {"Gauche": "ai0", "Droit": "ai1"}


class PositionTestFrame(tk.Frame):
    """Tests de position des capteurs : mêmes seuils, même pipeline d'évaluation
    (evaluate_tube, cfg) que les tests normaux — seule la position/le côté testés
    changent, pour garder des résultats strictement comparables."""

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.pos_index = 0
        self._current_tube_df = None
        self._current_tube_name = None

        header = tk.Frame(self)
        header.pack(fill="x", pady=8, padx=15)
        self.base_label = tk.Label(header, text="Base : -", font=("Segoe UI", 13, "bold"))
        self.base_label.pack(side="left")
        tk.Button(header, text="Accueil", command=lambda: controller.show_frame("HomeFrame")
                  ).pack(side="right", padx=5)
        tk.Button(header, text="↩ Retour aux tests normaux", command=lambda: controller.show_frame("TestFrame")
                  ).pack(side="right", padx=5)

        tk.Label(
            self, text="📏 Tests de position des capteurs",
            font=("Segoe UI", 14, "bold")
        ).pack(pady=(0, 4))
        tk.Label(
            self,
            text="Positionnez les DEUX capteurs à la même distance du centre à chaque étape "
                 "(ex. Gauche 4 cm ET Droit 4 cm), puis acquérez chaque côté séparément.",
            font=("Segoe UI", 9), fg="#555555"
        ).pack(pady=(0, 8))

        # --- Sélecteur de position ---
        pos_frame = tk.Frame(self)
        pos_frame.pack(pady=4)
        tk.Button(pos_frame, text="◀ Position précédente", command=self.prev_position
                  ).grid(row=0, column=0, padx=6)
        self.pos_label = tk.Label(pos_frame, text="", font=("Segoe UI", 15, "bold"), width=26)
        self.pos_label.grid(row=0, column=1, padx=10)
        tk.Button(pos_frame, text="Position suivante ▶", command=self.next_position
                  ).grid(row=0, column=2, padx=6)

        jump_frame = tk.Frame(self)
        jump_frame.pack(pady=4)
        tk.Label(jump_frame, text="Aller directement à :", font=("Segoe UI", 9)).pack(side="left", padx=4)
        self.pos_combo = ttk.Combobox(
            jump_frame, state="readonly", width=10,
            values=[f"{p} cm" for p in POSITIONS_CM]
        )
        self.pos_combo.pack(side="left")
        self.pos_combo.bind("<<ComboboxSelected>>", self._on_jump)

        # --- Boutons d'acquisition par côté ---
        acq_frame = tk.Frame(self)
        acq_frame.pack(pady=8)
        tk.Button(acq_frame, text="🎙🎙 Acquérir Gauche + Droit", font=("Segoe UI", 12, "bold"),
                  bg="#1e5c8e", fg="white",
                  command=self.acquire_both).grid(row=0, column=0, columnspan=2, padx=8, pady=(0, 6))
        tk.Button(acq_frame, text="🎙 Acquérir Gauche seul (ai0)", font=("Segoe UI", 9),
                  command=lambda: self.acquire_side("Gauche")).grid(row=1, column=0, padx=8)
        tk.Button(acq_frame, text="🎙 Acquérir Droit seul (ai1)", font=("Segoe UI", 9),
                  command=lambda: self.acquire_side("Droit")).grid(row=1, column=1, padx=8)

        self.status_label = tk.Label(self, text="Aucun test effectué", font=("Segoe UI", 14, "bold"),
                                      fg="white", bg="#888888", pady=6)
        self.status_label.pack(fill="x", padx=15, pady=6)

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=15, pady=5)

        self.figure = Figure(figsize=(7.5, 5))
        self.canvas = FigureCanvasTkAgg(self.figure, master=body)
        self.canvas.get_tk_widget().pack(side="left", fill="both", expand=True)

        right_col = tk.Frame(body, width=340)
        right_col.pack(side="left", fill="y", padx=10)

        self.info_text = tk.Text(right_col, width=42, height=14, font=("Consolas", 9), state="disabled")
        self.info_text.pack(fill="both", expand=False)

        tk.Label(right_col, text="Résultats de cette session :",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
        columns = ("position", "cote", "health", "statut")
        self.tree = ttk.Treeview(right_col, columns=columns, show="headings", height=10)
        for c, h, w in zip(columns, ("Position", "Côté", "Health Index", "Statut"), (70, 60, 90, 90)):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)

        self._refresh_pos_label()

    # ------------------------------------------------------------------
    def on_show(self):
        st = self.controller.state_data
        meta = st.current_base_meta or {}
        nb = len(meta.get("tubes_utilises", []))
        self.base_label.config(
            text=f"Base : {meta.get('nom', '?')}  |  {nb} tubes  |  position tests"
        )

    def _refresh_pos_label(self):
        pos = POSITIONS_CM[self.pos_index]
        self.pos_label.config(text=f"Position actuelle : {pos} cm du centre")
        self.pos_combo.set(f"{pos} cm")

    def prev_position(self):
        if self.pos_index > 0:
            self.pos_index -= 1
            self._refresh_pos_label()

    def next_position(self):
        if self.pos_index < len(POSITIONS_CM) - 1:
            self.pos_index += 1
            self._refresh_pos_label()

    def _on_jump(self, event=None):
        val = self.pos_combo.get().replace(" cm", "")
        try:
            self.pos_index = POSITIONS_CM.index(int(val))
        except ValueError:
            pass

    # ------------------------------------------------------------------
    def _set_status(self, statut):
        color = STATUS_COLORS.get(statut, "#888888")
        self.status_label.config(text=f"Résultat : {statut}", bg=color)

    def _show_info(self, ev, snr_acq, position_cm, side):
        self.info_text.config(state="normal")
        self.info_text.delete("1.0", tk.END)
        snr_txt = "N/A" if snr_acq is None else f"{snr_acq:.2f} dB"
        lines = [
            f"Position : {position_cm} cm  |  Côté : {side}",
            "",
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
        self.info_text.insert(tk.END, "\n".join(lines))
        self.info_text.config(state="disabled")

    # ------------------------------------------------------------------
    def acquire_side(self, side):
        st = self.controller.state_data
        if st.current_df_ref is None:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        position_cm = POSITIONS_CM[self.pos_index]
        name = simpledialog.askstring(
            "Nom du tube",
            f"Nom / référence du tube testé (position {position_cm} cm, côté {side}) :",
            parent=self,
        )
        if not name:
            return
        self._acquire_and_log(side, position_cm, name)

    def acquire_both(self):
        """Acquiert Gauche puis Droit en un seul clic, à la position actuelle."""
        st = self.controller.state_data
        if st.current_df_ref is None:
            messagebox.showwarning("Attention", "Aucune base de référence chargée.")
            return
        position_cm = POSITIONS_CM[self.pos_index]
        name = simpledialog.askstring(
            "Nom du tube",
            f"Nom / référence du tube testé (position {position_cm} cm, "
            "les deux capteurs) :",
            parent=self,
        )
        if not name:
            return
        ok_g = self._acquire_and_log("Gauche", position_cm, name)
        ok_d = self._acquire_and_log("Droit", position_cm, name)
        if ok_g and ok_d:
            messagebox.showinfo(
                "Acquisition terminée",
                f"Gauche et Droit acquis à {position_cm} cm.\n"
                "Positionnez les deux capteurs à la position suivante avant de recliquer."
            )

    def _acquire_and_log(self, side, position_cm, name):
        """Fait UNE acquisition (un seul canal AI, ai0 ou ai1 selon side), l'évalue
        avec le même pipeline que les tests normaux, l'affiche et la journalise.
        Retourne True si l'acquisition a réussi, False sinon."""
        st = self.controller.state_data
        cfg = st.cfg
        try:
            ai_channel = SIDE_TO_CHANNEL[side]
            daq = daqmod.DaqController(cfg, ai_channel=ai_channel)
            daq.init_daq()
            DATA = daq.acquire()
            FREQ_R, FFT_SIGNAL = spmod.compute_fft(
                DATA, daq.fs_r_actual, cfg["F_MIN_FFT"], cfg["F_MAX_FFT"], cfg["N_POINTS_FFT"]
            )
            tube_df = spmod.tube_dataframe(FREQ_R, FFT_SIGNAL)

            snr_acq = spmod.compute_snr(DATA, daq.n_samples_r) if DATA is not None else None
            # Même appel evaluate_tube, même cfg -> mêmes seuils que les tests normaux.
            ev = tcmod.evaluate_tube(FREQ_R, tube_df[cfg["PARAMETRE"]].values, st.current_df_ref, cfg)

            rgmod.plot_test_result(self.figure, DATA, daq.fs_r_actual, daq.n_samples_r,
                                    FREQ_R, FFT_SIGNAL, ev)
            self.canvas.draw()
            self.update_idletasks()

            self._set_status(ev["statut_final"])
            self._show_info(ev, snr_acq, position_cm, side)

            results_csv = os.path.join(st.current_base_folder, "resultats_tests_position.csv")
            amp_max = round(float(tube_df["FFT Abs"].max()), 4)
            rgmod.append_position_result_csv(results_csv, name, position_cm, side, ev, snr_acq,
                                              amplitude_fft_max=amp_max)

            self.tree.insert("", 0, values=(
                f"{position_cm} cm", side, ev["health_index"], ev["statut_final"]
            ))

            self._current_tube_df = tube_df
            self._current_tube_name = name
            return True
        except Exception as e:
            messagebox.showerror("Erreur d'acquisition", f"Côté {side} : {e}")
            return False
