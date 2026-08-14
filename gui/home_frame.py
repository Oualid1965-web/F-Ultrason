import tkinter as tk


class HomeFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="Contrôle Qualité Ultrason - Collage HAPS",
                 font=("Segoe UI", 20, "bold")).pack(pady=40)

        tk.Label(self, text="Que souhaitez-vous faire ?",
                 font=("Segoe UI", 13)).pack(pady=10)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=30)

        tk.Button(
            btn_frame, text="📁  Utiliser une base de référence existante",
            font=("Segoe UI", 12), width=42, height=3,
            command=lambda: controller.show_frame("SelectBaseFrame")
        ).grid(row=0, column=0, padx=20, pady=10)

        tk.Button(
            btn_frame, text="➕  Créer une nouvelle base de référence",
            font=("Segoe UI", 12), width=42, height=3,
            command=self.go_create
        ).grid(row=0, column=1, padx=20, pady=10)

        tk.Button(self, text="⚙ Paramètres", font=("Segoe UI", 10),
                  command=lambda: controller.show_frame("SettingsFrame")).pack(pady=15)

        tk.Label(
            self,
            text="Flux : Accueil → Base (existante / nouvelle) → Acquisition & comparaison → Résultat",
            font=("Segoe UI", 9), fg="#666666"
        ).pack(side="bottom", pady=15)

    def go_create(self):
        self.controller.state_data.pending_tubes = []
        self.controller.show_frame("CreateBaseFrame")

    def on_show(self):
        pass
