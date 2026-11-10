"""Ground truth must be unreachable from tools and agents (SPEC 3.1, 5, 14)."""
import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARDED = ["rca/tools", "rca/agent", "rca/control", "rca/guardrails"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


@pytest.mark.parametrize("pkg", GUARDED)
def test_no_truth_import(pkg):
    for p in (ROOT / pkg).rglob("*.py"):
        imps = _imports(p)
        assert "rca.truth" not in imps, f"{p} imports rca.truth"
        assert "rca.scoring" not in imps, f"{p} imports rca.scoring"
        src = p.read_text(encoding="utf-8")
        assert "truth.json" not in src or p.name == "data.py", f"{p} mentions truth.json"


def test_runtime_import_does_not_load_truth():
    code = ("import sys; import rca.tools.traces, rca.tools.metrics, rca.tools.logs, rca.tools.topology, "
            "rca.tools.faults, rca.tools.rank, rca.control.zscore, rca.guardrails.submit, rca.agent.tools; "
            "print('rca.truth' in sys.modules, 'rca.scoring' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False False"


def test_casedata_refuses_truth(tmp_path):
    from rca.tools.data import CaseData

    d = tmp_path / "DS" / "c1"
    d.mkdir(parents=True)
    (d / "truth.json").write_text(json.dumps({"gt_service": "x"}))
    cd = CaseData("DS", "c1", root=tmp_path)
    with pytest.raises(PermissionError):
        cd._path("truth.json")


def test_case_ids_are_opaque():
    from rca.adapter.layout import case_id_for

    cid = case_id_for("RE2-OB", Path("/x/RE2-OB/cartservice_cpu/1"))
    assert cid.startswith("c") and "cart" not in cid and "cpu" not in cid and "OB" not in cid
