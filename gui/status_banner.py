import tkinter as tk

GREEN = "#1e8e3e"
RED = "#d93025"
GRAY = "#6B7280"


class StatusBanner(tk.Frame):
    """Bandeau de résultat coupé en deux moitiés égales :
    - gauche : BON COLLAGE (vert) / MAUVAIS COLLAGE (rouge), selon le Health Index ;
    - droite : la décision de l'IA, avec la même convention de couleurs (gris si
      l'IA n'est pas entraînée ou indisponible).
    Les deux décisions sont indépendantes : un désaccord entre elles est visible tel quel."""

    def __init__(self, parent, title_size=16):
        super().__init__(parent)
        self.columnconfigure(0, weight=1, uniform="half")
        self.columnconfigure(1, weight=1, uniform="half")
        self._halves = []
        for col in (0, 1):
            frame = tk.Frame(self, bg=GRAY)
            frame.grid(row=0, column=col, sticky="nsew", padx=(0, 2) if col == 0 else (2, 0))
            title = tk.Label(frame, text="", font=("Segoe UI", title_size, "bold"),
                             fg="white", bg=GRAY)
            title.pack(fill="x", pady=(4, 0))
            sub = tk.Label(frame, text="", font=("Segoe UI", 10), fg="white", bg=GRAY)
            sub.pack(fill="x", pady=(0, 4))
            self._halves.append((frame, title, sub))
        self.reset()

    def _paint(self, idx, color, title, sub):
        frame, title_lbl, sub_lbl = self._halves[idx]
        for w in (frame, title_lbl, sub_lbl):
            w.config(bg=color)
        title_lbl.config(text=title)
        sub_lbl.config(text=sub)

    def reset(self):
        self._paint(0, GRAY, "Aucun test effectué", "Décision selon le Health Index")
        self._paint(1, GRAY, "Décision de l'IA", "En attente d'un test")

    def show_simulation(self):
        """Affiché à la place du verdict quand l'acquisition était simulée (aléatoire) :
        aucun verdict n'est valable et rien n'est enregistré."""
        violet = "#6A1B9A"
        self._paint(0, violet, "MODE SIMULATION", "Données aléatoires : aucun verdict valable")
        self._paint(1, violet, "Rien n'est enregistré", "Vérifiez la carte : Réglages > Diagnostic")

    def show(self, ev):
        """ev : résultat d'evaluate_tube (ou un dict équivalent) avec les clés
        statut_base, health_index, et optionnellement decision_ia, probabilite_ia,
        diagnostic_ia."""
        # --- moitié gauche : Health Index ---
        statut = ev.get("statut_base")
        color = GREEN if statut == "BON COLLAGE" else RED if statut == "MAUVAIS COLLAGE" else GRAY
        self._paint(0, color, statut or "-", f"Health Index : {ev.get('health_index')} %")

        # --- moitié droite : décision de l'IA ---
        decision = ev.get("decision_ia")
        proba = ev.get("probabilite_ia")
        if decision in ("BON COLLAGE", "MAUVAIS COLLAGE") and isinstance(proba, (int, float)):
            color = GREEN if decision == "BON COLLAGE" else RED
            self._paint(1, color, decision, f"IA : probabilité de défaut {proba * 100:.0f} %")
        elif ev.get("diagnostic_ia") in (None, "NON UTILISE"):
            self._paint(1, GRAY, "IA non entraînée", "Aucun modèle IA actif")
        else:
            self._paint(1, GRAY, "IA indisponible", str(ev.get("diagnostic_ia"))[:60])
