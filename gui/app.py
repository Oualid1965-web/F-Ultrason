import tkinter as tk

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


def run():
    app = UltrasonApp()
    app.mainloop()
