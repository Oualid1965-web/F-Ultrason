"""
Encapsule l'initialisation et l'acquisition NI-DAQ, adapté de ACQUISITION_GUI.py.

Si nidaqmx ou le matériel n'est pas disponible, le contrôleur passe en mode simulation
(données aléatoires, inutilisables pour juger un tube). Ce passage ne doit JAMAIS être
silencieux : après init_daq(), les appelants utilisent require_hardware(), qui refuse de
continuer en simulation sauf autorisation explicite (réglage AUTORISER_SIMULATION), et
diagnose() permet de contrôler le module, le pilote et la carte depuis l'application.
"""
import numpy as np

try:
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, TerminalConfiguration
    NIDAQ_AVAILABLE = True
    NIDAQ_IMPORT_ERROR = None
except Exception as _e:
    NIDAQ_AVAILABLE = False
    NIDAQ_IMPORT_ERROR = f"{type(_e).__name__}: {_e}"


class DaqUnavailableError(RuntimeError):
    """La carte d'acquisition n'est pas utilisable (l'application serait en simulation)."""


def _import_reason():
    return ("le module Python nidaqmx n'a pas pu être chargé"
            + (f" ({NIDAQ_IMPORT_ERROR})" if NIDAQ_IMPORT_ERROR else ""))


class DaqController:
    """Gère l'initialisation des tâches AI/AO et l'acquisition moyennée."""

    def __init__(self, cfg, ai_channel="ai0"):
        self.cfg = cfg
        self.ai_channel = ai_channel
        self.ai_task = None
        self.ao_task = None
        self.n_samples_r = int(cfg["T_SWEEP"] * cfg["FS_R"])
        self.fs_r_actual = cfg["FS_R"]
        self.fs_e_actual = cfg["FS_E"]
        self.simulated = not NIDAQ_AVAILABLE
        # Cause du passage en simulation (None tant que le matériel réel est utilisé)
        self.simulation_reason = None if NIDAQ_AVAILABLE else _import_reason()

    def unavailable_message(self):
        return (
            "La carte d'acquisition n'est pas utilisée : l'application génèrerait des données "
            "SIMULÉES (aléatoires), inutilisables pour juger un tube.\n\n"
            f"Cause : {self.simulation_reason or 'non précisée'}\n\n"
            "À vérifier : pilote NI-DAQmx installé, carte visible dans NI MAX, carte non réservée "
            "par un autre logiciel. Le menu Réglages > « Diagnostic de la carte d'acquisition » "
            "détaille chaque point.\n\n"
            "Pour tester l'interface sans matériel, mettez AUTORISER_SIMULATION à 1 dans les Réglages "
            "(rien ne sera alors enregistré)."
        )

    def require_hardware(self, allow_simulation=False):
        """À appeler juste après init_daq() : lève DaqUnavailableError si l'acquisition
        serait simulée, sauf si la simulation est explicitement autorisée."""
        if self.simulated and not allow_simulation:
            raise DaqUnavailableError(self.unavailable_message())

    def init_daq(self):
        """Initialise les tâches AI/AO. Retourne True si le matériel réel est utilisé."""
        cfg = self.cfg
        device_name = cfg["DEVICE_NAME"]
        FS_E = cfg["FS_E"]
        FS_R = cfg["FS_R"]
        T_SWEEP = cfg["T_SWEEP"]
        F_MIN = cfg["F_MIN"]
        F_MAX = cfg["F_MAX"]
        AMP = cfg["AMP"]

        if not NIDAQ_AVAILABLE:
            print("nidaqmx non disponible : mode simulation activé.")
            if NIDAQ_IMPORT_ERROR:
                print(f"  Détail : {NIDAQ_IMPORT_ERROR}")
            self.ai_task = None
            self.ao_task = None
            self.n_samples_r = int(T_SWEEP * FS_R)
            self.simulated = True
            self.simulation_reason = _import_reason()
            return False

        AI_0 = f"{device_name}Mod1/{self.ai_channel}"
        AO_0 = f"{device_name}Mod2/ao0"
        AO_1 = f"{device_name}Mod2/ao1"

        N_SAMPLES_E = int(T_SWEEP * FS_E)
        N_SAMPLES_R = int(T_SWEEP * FS_R)
        self.n_samples_r = N_SAMPLES_R

        t_E = np.linspace(0, N_SAMPLES_E / FS_E, N_SAMPLES_E, endpoint=False)
        FREQ = np.linspace(F_MIN, F_MAX - (F_MAX - F_MIN) / 2, int(N_SAMPLES_E / 2))
        INPUT_SIGNAL = AMP * np.sin(2 * np.pi * FREQ * t_E[:int(N_SAMPLES_E / 2)])
        INPUT_SIGNAL = np.concatenate((INPUT_SIGNAL, np.zeros(int(N_SAMPLES_E / 2))))

        try:
            ai_task = nidaqmx.Task()
            ao_task = nidaqmx.Task()

            ai_task.ai_channels.add_ai_voltage_chan(
                AI_0,
                terminal_config=TerminalConfiguration.PSEUDO_DIFF,
                min_val=-5.0,
                max_val=5.0
            )
            ai_task.timing.cfg_samp_clk_timing(
                rate=FS_R,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=N_SAMPLES_R,
            )

            ao_task.ao_channels.add_ao_voltage_chan(AO_0)
            ao_task.ao_channels.add_ao_voltage_chan(AO_1)
            ao_task.timing.cfg_samp_clk_timing(
                rate=FS_E,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=N_SAMPLES_E,
            )
            terminal_name = f"/{device_name}/ai/StartTrigger"
            ao_task.triggers.start_trigger.cfg_dig_edge_start_trig(terminal_name)

            self.fs_e_actual = ao_task.timing.samp_clk_rate
            self.fs_r_actual = ai_task.timing.samp_clk_rate
            self.n_samples_r = N_SAMPLES_R

            t_E = np.linspace(0, N_SAMPLES_E / self.fs_e_actual, N_SAMPLES_E, endpoint=False)
            FULL_SIGNAL = np.array([INPUT_SIGNAL, 5.0 * np.ones_like(t_E)])
            ao_task.write(FULL_SIGNAL, auto_start=False)

            self.ai_task = ai_task
            self.ao_task = ao_task
            self.simulated = False
            self.simulation_reason = None
            print("DAQ initialisé avec succès.")
            return True

        except Exception as e:      # DaqError, pilote absent, carte réservée ou introuvable...
            print(f"Erreur DAQ : {e}")
            # Fermer les tâches déjà créées avant de les abandonner, sinon le canal
            # (partagé entre Gauche et Droit pour l'excitation AO) reste réservé et
            # bloque silencieusement l'acquisition suivante.
            for t in (locals().get("ai_task"), locals().get("ao_task")):
                if t is not None:
                    try:
                        t.close()
                    except Exception:
                        pass
            self.ai_task = None
            self.ao_task = None
            self.simulated = True
            self.simulation_reason = f"{type(e).__name__}: {e}"
            return False

    def acquire(self, averages=None):
        """Réalise l'acquisition moyennée. Retourne un tableau numpy 1D (DATA)."""
        cfg = self.cfg
        averages = averages or cfg["AVERAGES"]
        n = self.n_samples_r

        if self.ai_task is None or self.ao_task is None:
            print("Tâches DAQ non initialisées -> génération de données simulées.")
            acquired = np.random.randn(n) * 0.05
            t = np.linspace(0, cfg["T_SWEEP"], n, endpoint=False)
            acquired[: n // 2] += 0.5 * np.exp(-3 * t[: n // 2]) * np.sin(2 * np.pi * 30000 * t[: n // 2])
        else:
            acquired = np.zeros(n)
            n_avg = 0
            try:
                while n_avg < averages:
                    self.ao_task.start()
                    self.ai_task.start()
                    acquired += np.array(self.ai_task.read(number_of_samples_per_channel=n)) / averages
                    print(f"Moyennes : {n_avg + 1}/{averages}", end="\r")
                    self.ai_task.stop()
                    self.ao_task.stop()
                    n_avg += 1
            finally:
                # Toujours libérer le matériel, même si une erreur survient pendant
                # l'acquisition — sinon l'acquisition suivante (ex. l'autre capteur)
                # échoue silencieusement car le canal reste réservé.
                try:
                    self.ai_task.close()
                except Exception:
                    pass
                try:
                    self.ao_task.close()
                except Exception:
                    pass
                self.ai_task = None
                self.ao_task = None

        DATA = acquired - np.mean(acquired[int(n / 2 * 1.1):])
        print("\nAcquisition terminée.")
        return DATA

    def close(self):
        for t in (self.ai_task, self.ao_task):
            if t is not None:
                try:
                    t.close()
                except Exception:
                    pass
        self.ai_task = None
        self.ao_task = None


def diagnose(cfg):
    """Contrôle pas à pas la chaîne d'acquisition : module Python, pilote NI-DAQmx, carte
    visible, voies utilisables. Retourne une liste de (niveau, texte), niveau parmi
    "ok", "err", "info". N'acquiert aucune donnée."""
    out = []
    if not NIDAQ_AVAILABLE:
        out.append(("err", f"Module Python nidaqmx non chargé : {NIDAQ_IMPORT_ERROR}"))
        out.append(("info", "Cause probable : l'exécutable a été construit sans les modules NI "
                            "(options --collect-all nidaqmx, nitypes et hightime), ou le paquet nidaqmx "
                            "n'est pas installé."))
        out.append(("err", "Résultat : l'acquisition réelle est IMPOSSIBLE dans cette installation."))
        return out
    try:
        import importlib.metadata as md
        version = md.version("nidaqmx")
    except Exception:
        version = "inconnue"
    out.append(("ok", f"Module Python nidaqmx chargé (version {version})."))

    try:
        from nidaqmx.system import System
        system = System.local()
        dv = system.driver_version
        major = getattr(dv, "major_version", None)
        if major is None:
            out.append(("ok", f"Pilote NI-DAQmx détecté : {dv}."))
        else:
            out.append(("ok", f"Pilote NI-DAQmx détecté : version {major}.{dv.minor_version}.{dv.update_version}."))
    except Exception as e:
        out.append(("err", f"Pilote NI-DAQmx introuvable ou inaccessible : {type(e).__name__}: {e}"))
        out.append(("info", "Installez NI-DAQmx (ni.com, via NI Package Manager), puis redémarrez le poste."))
        out.append(("err", "Résultat : l'acquisition réelle est IMPOSSIBLE tant que le pilote n'est pas installé."))
        return out

    try:
        names = [d.name for d in system.devices]
    except Exception as e:
        out.append(("err", f"Impossible de lister les cartes : {type(e).__name__}: {e}"))
        return out
    dev = cfg["DEVICE_NAME"]
    if names:
        out.append(("info", "Cartes vues par le pilote : " + ", ".join(names)))
    else:
        out.append(("err", "Aucune carte NI n'est vue par le pilote."))
        out.append(("info", "Ouvrez NI MAX > Devices and Interfaces > Network Devices (Périphériques et interfaces > "
                            "Périphériques réseau) : si le châssis n'y est pas, clic droit sur Network Devices > "
                            "Find Network NI-DAQmx Devices, puis saisissez son adresse IP dans Add Device Manually."))
    all_found = True
    for label, name in (("Châssis", dev), ("Module d'entrée (Mod1)", f"{dev}Mod1"), ("Module de sortie (Mod2)", f"{dev}Mod2")):
        if name in names:
            out.append(("ok", f"{label} « {name} » trouvé."))
        else:
            all_found = False
            out.append(("err", f"{label} « {name} » introuvable (nom attendu d'après le réglage DEVICE_NAME)."))

    ctrl = DaqController(cfg)
    ok = ctrl.init_daq()
    if ok:
        out.append(("ok", f"Initialisation des voies réussie : entrée {dev}Mod1/ai0, sorties {dev}Mod2/ao0 et ao1."))
        ctrl.close()
    else:
        out.append(("err", f"Initialisation des voies échouée : {ctrl.simulation_reason}"))
        out.append(("info", "Vérifiez aussi que la carte n'est pas réservée par un autre logiciel ou un autre poste "
                            "(un châssis réseau ne peut être utilisé que par un poste à la fois)."))
    if ok and all_found:
        out.append(("ok", "Résultat : l'acquisition réelle est possible."))
    else:
        out.append(("err", "Résultat : l'acquisition réelle est IMPOSSIBLE tant que les points en erreur ne sont pas corrigés."))
    return out
