from pathlib import Path
import os


def project_root(root=None) -> Path:
    return Path(root or os.environ.get("EDU_TUTOR_ROOT") or Path(__file__).resolve().parents[2]).resolve()


def initialize(root=None) -> Path:
    root = project_root(root)
    for name in (".local", ".local/models", ".local/audio", "runs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root
