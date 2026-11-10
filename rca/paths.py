"""Repository paths and config loading. Data folders may be symlinks to a larger disk."""
from __future__ import annotations

import functools
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CANONICAL_DIR = DATA_DIR / "canonical"
CACHE_DIR = DATA_DIR / "cache"
TOPOLOGY_DIR = DATA_DIR / "topology"
SPLITS_CSV = DATA_DIR / "splits.csv"
RUNS_DIR = ROOT / "runs"
RESULTS_DIR = ROOT / "results"
REPORTS_DIR = ROOT / "reports"

DATASETS = ["RE1-OB", "RE1-SS", "RE1-TT", "RE2-OB", "RE2-SS", "RE2-TT", "RE3-OB", "RE3-SS", "RE3-TT"]


@functools.lru_cache(maxsize=None)
def system_config() -> dict:
    with open(CONFIG_DIR / "system.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=None)
def models_config() -> dict:
    with open(CONFIG_DIR / "models.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env() -> None:
    """Load KEY=VALUE lines from the git-ignored .env into os.environ (without overriding)."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
