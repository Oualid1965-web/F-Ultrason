"""
Point d'entrée de l'application de Contrôle Ultrason - Collage HAPS.

Lancement :
    python main.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import run

if __name__ == "__main__":
    run()
