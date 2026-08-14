import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import config as cfgmod


FIELDS = [
    ("--- Analyse / Comparaison ---", None),
    ("PARAMETRE", "choice", ["FFT Abs", "FFT Real", "FFT Imag"]),
    ("SEUIL_SNR", "float"),
    ("SEUIL_ACCEPT", "float"),
    ("SEUIL_SUSPECT", "float"),
    ("DECIMATION", "int"),
    ("IQR_FACTOR", "float"),

    ("--- IA supervisée ---", None),
    ("SEUIL_ACTIVATION_IA", "float"),
    ("IA_N_BINS", "int"),
    ("CHEMIN_MODELE_IA", "file"),

    ("--- Acquisition DAQ ---", None),
    ("DEVICE_NAME", "str"),
    ("T_SWEEP", "float"),
    ("FS_E", "float"),
    ("F_MIN", "float"),
    ("F_MAX", "float"),
    ("AMP", "float"),
    ("FS_R", "float"),
    ("AVERAGES", "int"),
    ("N_POINTS_FFT", "int"),
    ("F_MIN_FFT", "float"),
    ("F_MAX_FFT", "float"),
]

HELP_TEXT = {
    "PARAMETRE": "Colonne FFT utilisée pour la comparaison (Abs recommandé).",
    "SEUIL_SNR": "SNR minimal (dB) pour qu'un point de fréquence soit pris en compte.",
    "SEUIL_ACCEPT": "Health Index (%) au-dessus duquel le tube est ACCEPTÉ.",
    "SEUIL_SUSPECT": "Health Index (%) au-dessus duquel le tube est SUSPECT (sinon REJET).",
    "DECIMATION": "Sous-échantillonnage des points fréquence (accélère les calculs).",
    "IQR_FACTOR": "Facteur IQR pour le rejet des tubes atypiques à la création de la base.",
    "SEUIL_ACTIVATION_IA": "Health Index en-dessous duquel l'IA est consultée en renfort.",
    "IA_N_BINS": "Nombre de bandes de fréquence utilisées comme variables IA à l'entraînement.",
    "CHEMIN_MODELE_IA": "Modèle .joblib actif (mis à jour automatiquement après entraînement).",
}


class SettingsFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.vars = {}

        tk.Label(self, text="Paramètres", font=("Segoe UI", 16, "bold")).pack(pady=15)

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        form = tk.Frame(canvas)
        form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=20)
        scrollbar.pack(side="right", fill="y")

        row = 0
        for item in FIELDS:
            key = item[0]
            if item[1] is None:
                tk.Label(form, text=key, font=("Segoe UI", 11, "bold")).grid(
                    row=row, column=0, columnspan=3, sticky="w", pady=(18, 5))
                row += 1
                continue
            kind = item[1]
            tk.Label(form, text=key, font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", padx=5, pady=3)

            if kind == "choice":
                var = tk.StringVar()
                ttk.Combobox(form, textvariable=var, values=item[2], width=27, state="readonly").grid(
                    row=row, column=1, padx=5, pady=3, sticky="w")
            elif kind == "file":
                var = tk.StringVar()
                fr = tk.Frame(form)
                fr.grid(row=row, column=1, padx=5, pady=3, sticky="w")
                tk.Entry(fr, textvariable=var, width=24).pack(side="left")
                tk.Button(fr, text="...", command=lambda v=var: self._browse(v)).pack(side="left")
            else:
                var = tk.StringVar()
                tk.Entry(form, textvariable=var, width=30).grid(row=row, column=1, padx=5, pady=3, sticky="w")

            if key in HELP_TEXT:
                tk.Label(form, text=HELP_TEXT[key], font=("Segoe UI", 8), fg="#777777",
                         wraplength=380, justify="left").grid(row=row, column=2, sticky="w", padx=10)

            self.vars[key] = (var, kind)
            row += 1

        btns = tk.Frame(self)
        btns.pack(pady=15)
        tk.Button(btns, text="💾 Enregistrer", font=("Segoe UI", 11), command=self.save
                  ).grid(row=0, column=0, padx=10)
        tk.Button(btns, text="Retour", font=("Segoe UI", 11),
                  command=lambda: controller.show_frame("HomeFrame")).grid(row=0, column=1, padx=10)

    def _browse(self, var):
        path = filedialog.askopenfilename(
            title="Sélectionner le modèle IA (.joblib)",
            filetypes=[("Modèle joblib", "*.joblib"), ("Tous les fichiers", "*.*")]
        )
        if path:
            var.set(path)

    def on_show(self):
        cfg = self.controller.state_data.cfg
        for key, (var, kind) in self.vars.items():
            var.set(str(cfg.get(key, "")))

    def save(self):
        cfg = self.controller.state_data.cfg
        try:
            for key, (var, kind) in self.vars.items():
                val = var.get()
                if kind == "float":
                    cfg[key] = float(val)
                elif kind == "int":
                    cfg[key] = int(float(val))
                else:
                    cfg[key] = val
        except ValueError as e:
            messagebox.showerror("Erreur", f"Valeur invalide : {e}")
            return
        cfgmod.save_config(cfg)
        messagebox.showinfo("Paramètres", "Paramètres enregistrés avec succès.")
