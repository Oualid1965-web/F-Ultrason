"""
Encapsule l'initialisation et l'acquisition NI-DAQ, adapté de ACQUISITION_GUI.py.
Si nidaqmx / le matériel n'est pas disponible, l'application bascule automatiquement
en mode simulation (données aléatoires) pour permettre de tester l'interface sans
matériel branché.
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


class DaqController:
    """Gère l'initialisation des tâches AI/AO et l'acquisition moyennée."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.ai_task = None
        self.ao_task = None
        self.n_samples_r = int(cfg["T_SWEEP"] * cfg["FS_R"])
        self.fs_r_actual = cfg["FS_R"]
        self.fs_e_actual = cfg["FS_E"]
        self.simulated = not NIDAQ_AVAILABLE

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
            return False

        AI_0 = f"{device_name}Mod1/ai0"
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
            print("DAQ initialisé avec succès.")
            return True

        except nidaqmx.DaqError as e:
            print(f"Erreur DAQ : {e}")
            self.ai_task = None
            self.ao_task = None
            self.simulated = True
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
            while n_avg < averages:
                self.ao_task.start()
                self.ai_task.start()
                acquired += np.array(self.ai_task.read(number_of_samples_per_channel=n)) / averages
                print(f"Moyennes : {n_avg + 1}/{averages}", end="\r")
                self.ai_task.stop()
                self.ao_task.stop()
                n_avg += 1
            self.ai_task.close()
            self.ao_task.close()
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
