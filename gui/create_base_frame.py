import os
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog

import pandas as pd

import config as cfgmod
import daq_acquisition as daqmod
import signal_processing as spmod
import reference_base_builder as rbb


class CreateBaseFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="Création d'une nouvelle base de référence",
                 font=("Segoe UI", 16, "bold")).pack(pady=15)

        top = tk.Frame(self)
        top.pack(pady=5)
        tk.Label(top, text="Nom de la base :", font=("Segoe UI", 11)).grid(row=0, column=0, padx=5)
        self.name_entry = tk.Entry(top, font=("Segoe UI", 11), width=35)
        self.name_entry.grid(row=0, column=1, padx=5)

        btns = tk.Frame(self)
        btns.pack(pady=10)
        tk.Button(btns, text="🎙 Acquérir un tube (DAQ)", font=("Segoe UI", 11),
                  command=self.acquire_tube).grid(row=0, column=0, padx=8)
        tk.Button(btns, text="📂 Importer un/des tube(s) (CSV)", font=("Segoe UI", 11),
                  command=self.import_tube).grid(row=0, column=1, padx=8)
        tk.Button(btns, text="🗑 Retirer le tube sélectionné", font=("Segoe UI", 11),
                  command=self.remove_selected).grid(row=0, column=2, padx=8)

        tk.Label(
            self,
            text="Ajoutez autant de tubes que nécessaire (nombre illimité), "
                 "puis cliquez sur « Terminer » pour construire la base.",
            font=("Segoe UI", 9), fg="#666666"
        ).pack()

        mid = tk.Frame(self)
        mid.pack(fill="both", expand=True, padx=20, pady=10)

        left = tk.Frame(mid)
        left.pack(side="left", fill="y", padx=(0, 10))
        tk.Label(left, text="Tubes ajoutés :", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=42, height=20, font=("Segoe UI", 10))
        self.listbox.pack(fill="y", expand=False)

        right = tk.Frame(mid)
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="Journal (résultats de construction) :",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.log_text = tk.Text(right, font=("Consolas", 9), state="disabled")
        self.log_text.pack(fill="both", expand=True)

        bottom = tk.Frame(self)
        bottom.pack(pady=10)
        self.finish_btn = tk.Button(bottom, text="✅ Terminer et construire la base",
                                     font=("Segoe UI", 11, "bold"), command=self.finish_base)
        self.finish_btn.grid(row=0, column=0, padx=8)
        self.continue_btn = tk.Button(bottom, text="➡ Continuer vers les tests",
                                       font=("Segoe UI", 11), state="disabled",
                                       command=self.go_to_tests)
        self.continue_btn.grid(row=0, column=1, padx=8)
        tk.Button(bottom, text="Retour à l'accueil", font=("Segoe UI", 11),
                  command=lambda: controller.show_frame("HomeFrame")).grid(row=0, column=2, padx=8)

    def on_show(self):
        self.controller.state_data.pending_tubes = []
        self.listbox.delete(0, tk.END)
        self._log_clear()
        self.continue_btn.config(state="disabled")

    def _log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.log_text.update_idletasks()

    def _log_clear(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

    def acquire_tube(self):
        cfg = self.controller.state_data.cfg
        nom = simpledialog.askstring("Nom du tube", "Nom / référence du tube :", parent=self)
        if not nom:
            return
        try:
            daq = daqmod.DaqController(cfg)
            daq.init_daq()
            DATA = daq.acquire()
            FREQ_R, FFT_SIGNAL = spmod.compute_fft(
                DATA, daq.fs_r_actual, cfg["F_MIN_FFT"], cfg["F_MAX_FFT"], cfg["N_POINTS_FFT"]
            )
            df = spmod.tube_dataframe(FREQ_R, FFT_SIGNAL)
            snr = spmod.compute_snr(DATA, daq.n_samples_r)
            self.controller.state_data.pending_tubes.append({"nom": nom, "df": df})
            tag = " [simulation]" if daq.simulated else ""
            self.listbox.insert(tk.END, f"{nom} (DAQ, SNR={snr:.1f} dB){tag}")
        except Exception as e:
            messagebox.showerror("Erreur d'acquisition", str(e))

    def import_tube(self):
        paths = filedialog.askopenfilenames(
            title="Sélectionner un ou plusieurs fichiers tube (CSV)",
            filetypes=[("CSV files", "*.csv")]
        )
        for path in paths:
            try:
                df = pd.read_csv(path, sep=";")
                df.columns = df.columns.astype(str).str.strip()
                nom = os.path.basename(path)
                self.controller.state_data.pending_tubes.append({"nom": nom, "df": df})
                self.listbox.insert(tk.END, f"{nom} (importé)")
            except Exception as e:
                messagebox.showerror("Erreur d'import", f"{path} : {e}")

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        for i in reversed(sel):
            self.listbox.delete(i)
            del self.controller.state_data.pending_tubes[i]

    def finish_base(self):
        st = self.controller.state_data
        tubes = st.pending_tubes
        if len(tubes) < 2:
            messagebox.showwarning("Attention", "Ajoutez au moins 2 tubes avant de construire la base.")
            return
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showwarning("Attention", "Veuillez donner un nom à la base.")
            return

        cfg = st.cfg
        self._log_clear()
        try:
            result = rbb.build_reference_base(
                tubes, cfg["PARAMETRE"], cfg["DECIMATION"],
                seuil_snr_display=cfg["SEUIL_SNR"], iqr_factor=cfg.get("IQR_FACTOR", 1.5),
                log=self._log
            )
        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            return

        base_folder = rbb.save_reference_base(result, name, tubes, cfgmod.REF_BASES_DIR)
        self._log(f"\nDossier de la base -> {base_folder}")
        messagebox.showinfo("Base créée", f"La base '{name}' a été créée et enregistrée avec succès.")

        st.current_base_folder = base_folder
        st.current_base_meta = rbb.load_metadata(base_folder)
        st.current_df_ref = result["df_clean"]

        self.continue_btn.config(state="normal")

    def go_to_tests(self):
        self.controller.show_frame("TestFrame")
