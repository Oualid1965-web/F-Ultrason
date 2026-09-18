import os
import sys
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import messagebox

import config as cfgmod
from .home_frame import HomeFrame
from .select_base_frame import SelectBaseFrame
from .create_base_frame import CreateBaseFrame
from .test_frame import TestFrame
from .position_test_frame import PositionTestFrame
from .settings_frame import SettingsFrame


class AppState:
    """État partagé entre les pages de l'application."""

    def __init__(self):
        self.cfg = cfgmod.load_config()
        self.current_base_folder = None
        self.current_base_meta = None
        self.current_df_ref = None
        self.pending_tubes = []  # tubes en cours d'ajout lors de la création d'une base


class UltrasonApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Contrôle Ultrason - Collage HAPS")
        self.geometry("1280x820")
        self.minsize(1050, 700)
        self.state_data = AppState()

        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (HomeFrame, SelectBaseFrame, CreateBaseFrame, TestFrame, PositionTestFrame, SettingsFrame):
            frame = F(container, self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("HomeFrame")

    def show_frame(self, name):
        frame = self.frames[name]
        if hasattr(frame, "on_show"):
            frame.on_show()
        frame.tkraise()

    def report_callback_exception(self, exc, val, tb):
        """Filet de sécurité global : l'app tourne en mode --windowed (sans console),
        donc toute erreur non explicitement gérée disparaissait silencieusement
        jusqu'ici (l'écran restait figé, sans aucun message). Désormais elle est
        écrite dans erreurs.log ET affichée à l'écran, quel que soit l'endroit du
        programme où elle survient (changement de page, clic sur un bouton...)."""
        log_text = "".join(traceback.format_exception(exc, val, tb))
        log_path = None
        try:
            if getattr(sys, "frozen", False):
                log_dir = os.path.dirname(os.path.abspath(sys.executable))
            else:
                log_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(log_dir, "erreurs.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 70 + "\n")
                f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                f.write(log_text)
        except Exception:
            pass
        where = f"\n\nDétail enregistré dans : {log_path}" if log_path else ""
        messagebox.showerror(
            "Erreur inattendue",
            f"Une erreur inattendue est survenue :\n\n{val}{where}"
        )


def run():
    app = UltrasonApp()
    app.mainloop()
