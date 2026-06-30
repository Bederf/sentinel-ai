"""PyInstaller runtime hook for SENTINEL backend.
Runs before app startup. Patches sys.path and data dir resolution
to work correctly inside the PyInstaller bundle."""

import os
import sys


def _setup_paths():
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(bundle_dir, "app", "data")
    if os.path.isdir(data_dir):
        os.environ.setdefault("SENTINEL_DATA_DIR", data_dir)
        sys.path.insert(0, bundle_dir)


_setup_paths()
