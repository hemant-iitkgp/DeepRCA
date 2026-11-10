"""Raw RCAEval folder layout: <dataset>/<service>_<fault>[_<variant>]/<repetition>/."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from rca.paths import RAW_DIR

# The fault token is the last "_"-separated token that looks like a fault label; an optional
# numeric variant may follow (one RE3 folder is "<service>_f3_1").
_FOLDER_RE = re.compile(r"^(?P<service>.+?)_(?P<fault>cpu|mem|disk|delay|loss|socket|f\d+)(?:_(?P<variant>\d+))?$")


def parse_folder(name: str) -> dict:
    m = _FOLDER_RE.match(name)
    if not m:
        raise ValueError(f"unrecognised case folder {name!r}")
    return {"service": m["service"], "fault": m["fault"], "variant": m["variant"] or ""}


def list_raw_cases(dataset: str) -> tuple[list[Path], list[str]]:
    """Return (case dirs, stray entries). Cases are numbered repetition folders."""
    root = RAW_DIR / dataset
    cases, stray = [], []
    for sf in sorted(p for p in root.iterdir() if p.is_dir()):
        for rep in sorted(sf.iterdir()):
            if rep.is_dir() and rep.name.isdigit():
                cases.append(rep)
            else:
                stray.append(f"{sf.name}/{rep.name}")
    return cases, stray


def case_id_for(dataset: str, case_dir: Path) -> str:
    """Opaque, deterministic case ID: no service, fault, system or dataset name in it."""
    key = f"{dataset}/{case_dir.parent.name}/{case_dir.name}"
    return "c" + hashlib.sha1(key.encode()).hexdigest()[:10]
