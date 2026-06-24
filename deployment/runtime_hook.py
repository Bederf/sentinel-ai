"""PyInstaller runtime hook for SENTINEL backend.
Patches sys.path and data directory resolution for frozen executables."""
import os
import sys


def _setup_paths():
    bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(bundle_dir, "app", "data")
    if os.path.isdir(data_dir):
        os.environ.setdefault("SENTINEL_DATA_DIR", data_dir)
    ml_models = os.path.join(bundle_dir, "ml", "models")
    if os.path.isdir(ml_models):
        os.environ.setdefault("SENTINEL_ML_MODELS_DIR", ml_models)
    sys.path.insert(0, bundle_dir)


_setup_paths()
