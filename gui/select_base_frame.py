import os
import tkinter as tk
from tkinter import ttk, messagebox

import config as cfgmod
import reference_base_builder as rbb


class SelectBaseFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        tk.Label(self, text="Sélectionner une base de référence",
                 font=("Segoe UI", 16, "bold")).pack(pady=20)

        columns = ("nom", "date_creation", "date_maj", "nb_tubes", "parametre")
        headers = ("Nom", "Créée le", "Mise à jour", "Nb tubes", "Paramètre")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=15)
        for c, h, w in zip(columns, headers, (220, 150, 150, 90, 110)):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w)
        self.tree.pack(padx=20, pady=10, fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.select_base())

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Sélectionner", font=("Segoe UI", 11),
                  command=self.select_base).grid(row=0, column=0, padx=10)
        tk.Button(btn_frame, text="Actualiser", font=("Segoe UI", 11),
                  command=self.on_show).grid(row=0, column=1, padx=10)
        tk.Button(btn_frame, text="Retour", font=("Segoe UI", 11),
                  command=lambda: controller.show_frame("HomeFrame")).grid(row=0, column=2, padx=10)

        self._bases_by_iid = {}

    def on_show(self):
        self.tree.delete(*self.tree.get_children())
        self._bases_by_iid = {}
        bases = rbb.list_reference_bases(cfgmod.REF_BASES_DIR)
        if not bases:
            messagebox.showinfo("Info", "Aucune base de référence enregistrée pour le moment.\n"
                                         "Utilisez « Créer une nouvelle base de référence » depuis l'accueil.")
        for meta in bases:
            iid = self.tree.insert("", "end", values=(
                meta.get("nom", "?"),
                meta.get("date_creation", "?"),
                meta.get("date_maj", meta.get("date_creation", "?")),
                len(meta.get("tubes_utilises", [])),
                meta.get("parametre", "?"),
            ))
            self._bases_by_iid[iid] = meta

    def select_base(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Attention", "Veuillez sélectionner une base dans la liste.")
            return
        meta = self._bases_by_iid[sel[0]]
        base_folder = meta["_folder"]
        df_ref = rbb.load_reference_base(os.path.join(base_folder, "base_saine.csv"))

        st = self.controller.state_data
        st.current_base_folder = base_folder
        st.current_base_meta = meta
        st.current_df_ref = df_ref

        self.controller.show_frame("TestFrame")
