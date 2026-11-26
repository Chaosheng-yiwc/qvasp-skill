"""Smoke every MCP tool on a machine that has no qvasp and no scheduler.

Why this file exists
--------------------
A tool that shells out to a binary fails in two very different ways when that
binary is absent. The good one is a returned message: "qvasp binary not
available (tried 'qvasp -h'); install qvasp or set QVASP_BIN". The bad one is a
raw exception the model then has to interpret -- `qvasp_help` did exactly that
(`FileNotFoundError: [WinError 2]`) until 1.5.1, and `submit`/`job_alive` could
do the same on a machine without qsub.

`--argcheck` cannot catch this: it calls every tool with `{}`, and the empty-arg
guard returns before the subprocess is ever reached. This script passes *real*
arguments (a temp case directory with a POSCAR) while pointing QVASP_BIN at a
name that does not exist, so every code path that shells out is actually walked.

Run it with no qvasp installed -- that is the point:

    python tools/tool_smoke.py

Exit code is the number of failures, so CI and the release checklist can just
require exit 0.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent / "server" / "qvasp_mcp.py"

POSCAR = """diamond
   1.00000000000000
     3.5670000000000000    0.0000000000000000    0.0000000000000000
     0.0000000000000000    3.5670000000000000    0.0000000000000000
     0.0000000000000000    0.0000000000000000    3.5670000000000000
   C
     2
Direct
  0.0000000000000000  0.0000000000000000  0.0000000000000000
  0.2500000000000000  0.2500000000000000  0.2500000000000000
"""

INCAR = "ENCUT = 500\nISMEAR = 0\nSIGMA = 0.2\n"
KPOINTS = "gamma\n0\nGamma\n16 16 16\n0 0 0\n"
POTCAR = (
    "  PAW_PBE C 08Apr2002\n"
    "   ENMAX  =  400.000; ENMIN  =  300.000 eV\n"
    "   ZVAL   =    4.000\n"
)

# Words that mean "the tool leaked an exception instead of answering".
LEAKS = ("Traceback", "KeyError", "TypeError", "AttributeError", "NameError",
         "IndexError", "FileNotFoundError", "NotADirectoryError",
         "PermissionError", "ValueError:")


def load_server(root: Path):
    os.environ["QVASP_BIN"] = "qvasp-does-not-exist"  # the whole point
    os.environ["QVASP_SCHEDULER"] = "pbs"             # and no qsub either
    # The case must live inside the work root: the server refuses a cwd outside
    # it, and that refusal is a different message than the one under test.
    os.environ["QVASP_WORKROOT"] = str(root)
    spec = importlib.util.spec_from_file_location("qvasp_mcp", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_case(tmp: Path) -> Path:
    case = tmp / "case"
    case.mkdir()
    for name, body in (("POSCAR", POSCAR), ("INCAR", INCAR),
                       ("KPOINTS", KPOINTS), ("POTCAR", POTCAR)):
        (case / name).write_text(body)
    return case


def calls(case: Path) -> dict:
    """One call per tool, with arguments that reach the real work.

    Keep this list in step with TOOLS: the count is asserted at the end so a new
    tool cannot be added without a smoke case here."""
    p = str(case)
    return {
        "qvasp_run": {"command": "-pbe C"},
        "qvasp_help": {"topic": "band"},
        "workflow_check": {},
        "workflow_plan": {"workflow": "relax-only", "system": p},
        "workflow_run": {"workflow": "relax-only", "system": p},
        "workflow_resume": {"workflow": "relax-only", "system": p},
        "workflow_status": {"system": p},
        "structure_check": {"cwd": p},
        "result_extract": {"file": str(case / "POSCAR"), "kind": "band_gap"},
        "result_parse": {"file": str(case / "POSCAR"), "kind": "band_gap"},
        "report_build": {"system": p},
        "diagnose_log": {"text": "ZBRENT: fatal error in bracketing"},
        "aux_list": {},
        "aux_run": {"tool": "vaspkit", "cwd": p},
        "reference_lookup": {"property": "band_gap"},
        "result_compare": {"property": "band_gap", "value": 4.1, "unit": "eV"},
        "literature_record": {"property": "band_gap", "value": 4.1, "cwd": p},
        "preflight": {"cwd": p},
    }


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="qvasp-smoke-"))
    failures = []
    try:
        mod = load_server(tmp)
        case = make_case(tmp)
        wanted = calls(case)
        missing = sorted(set(mod.TOOLS) - set(wanted))
        if missing:
            failures.append(("coverage", f"no smoke case for {missing}"))
        for name, args in wanted.items():
            if name not in mod.TOOLS:
                failures.append((name, "listed here but not registered in TOOLS"))
                continue
            try:
                result = mod.TOOLS[name]["fn"](args)
            except Exception as exc:  # noqa: BLE001 - that is what we are testing
                failures.append((name, f"raised {type(exc).__name__}: {exc}"))
                continue
            text = json.dumps(result, ensure_ascii=False, default=str)
            hit = [word for word in LEAKS if word in text]
            if hit:
                failures.append((name, f"leaked {hit}: {text[:200]}"))
            # an error is fine -- it must just say what to install or set
            if isinstance(result, dict) and "error" in result:
                msg = str(result["error"])
                if "install" not in msg and "set QVASP" not in msg \
                        and "not available" not in msg and "not installed" not in msg \
                        and "needs" not in msg and "does not exist" not in msg \
                        and "cannot" not in msg and "nothing to report" not in msg \
                        and "unsourced" not in msg and "not a" not in msg:
                    failures.append((name, f"error message gives no way forward: {msg[:160]}"))
        print(f"{len(wanted)} tools exercised, {len(failures)} failure(s)")
        for name, detail in failures:
            print(f"  FAIL {name}: {detail}")
        return len(failures)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
