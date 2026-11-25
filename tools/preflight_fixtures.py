"""Self-test for server/analysis/preflight.py: 17 broken and 3 legitimate inputs.

    python tools/preflight_fixtures.py

Every fixture is built in a temporary directory, so the repository is never
touched. The point of the suite is not that the checker finds something -- it is
that each case is reported for the *right* reason and that the legitimate ones
stay quiet. Six of the checks in preflight.py were rewritten because this suite
(or a 71-case scan of the real examples) showed them rejecting valid input.

Exit code is the number of cases whose verdict does not match the expectation.
"""
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "server"))
from analysis import preflight  # noqa: E402

POSCAR_OK = """diamond
  3.567
  0.0 0.5 0.5
  0.5 0.0 0.5
  0.5 0.5 0.0
C
2
Direct
  0.00 0.00 0.00
  0.25 0.25 0.25
"""
POTCAR_C = """  PAW_PBE C 08Apr2002
   4.0000000000000000
   parameters from PSCTR are:
   VRHFIN =C: s2p2
   TITEL  = PAW_PBE C 08Apr2002
   LULTRA =        F    use ultrasoft PP ?
   ENMAX  =  400.000; ENMIN  =  300.000 eV
   ZVAL   =    4.000
"""
POTCAR_N = """  PAW_PBE N 08Apr2002
   5.0000000000000000
   TITEL  = PAW_PBE N 08Apr2002
   ENMAX  =  400.000; ENMIN  =  300.000 eV
   ZVAL   =    5.000
"""
INCAR_OK = """SYSTEM = diamond
PREC = Normal
ENCUT = 520
EDIFF = 1E-6
ISMEAR = 0
SIGMA = 0.05
IBRION = 2
ISIF = 3
NSW = 50
EDIFFG = -0.01
"""
KPTS_OK = """auto
0
Gamma
16 16 16
0 0 0
"""
KPTS_LINE = """k-path
21
Line-mode
Reciprocal
  0.0 0.0 0.0
  0.5 0.0 0.5

  0.5 0.0 0.5
  0.5 0.25 0.75
"""

ROOT = Path(tempfile.mkdtemp(prefix="qvasp-preflight-"))
CASES = {}


def make(name, **files):
    d = ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    for fn, text in files.items():
        if text is None:
            continue
        (d / fn).write_text(text, encoding="utf-8")
    return d


# name -> (directory, expected ok, checks that must fire)
CASES["ok-gamma"] = (make("ok-gamma", POSCAR=POSCAR_OK, POTCAR=POTCAR_C,
                          INCAR=INCAR_OK, KPOINTS=KPTS_OK), True, [])
CASES["ok-line"] = (make("ok-line", POSCAR=POSCAR_OK, POTCAR=POTCAR_C,
                         INCAR=INCAR_OK, KPOINTS=KPTS_LINE), True, [])
CASES["ok-list"] = (make(
    "ok-list", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, INCAR=INCAR_OK,
    KPOINTS="explicit list\n3\nrec\n"
            "  0.0 0.0 0.0 1\n  0.5 0.0 0.0 1\n  0.5 0.5 0.0 1\n"), True, [])
CASES["ok-list-sameline"] = (make(
    "ok-list-sameline", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, INCAR=INCAR_OK,
    KPOINTS="Gamma, shift on the grid line\n0\nGamma\n8 8 8 0 0 0\n"), True, [])

CASES["ok-line-norecip"] = (make(
    "ok-line-norecip", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, INCAR=INCAR_OK,
    KPOINTS=KPTS_LINE.replace("Reciprocal\n", "")), False, ["kpoints-reciprocal"])
CASES["order"] = (make(
    "order",
    POSCAR="""CN
  6.0
  1.0 0.0 0.0
  0.0 1.0 0.0
  0.0 0.0 1.0
C N
1 1
Direct
  0.00 0.00 0.00
  0.50 0.50 0.50
""",
    POTCAR=POTCAR_N + POTCAR_C, INCAR=INCAR_OK, KPOINTS=KPTS_OK), False, ["potcar-order"])
CASES["noposcar"] = (make("noposcar", POTCAR=POTCAR_C, INCAR=INCAR_OK,
                          KPOINTS=KPTS_OK), False, ["missing-file"])
CASES["empty-potcar"] = (make("empty-potcar", POSCAR=POSCAR_OK, POTCAR="",
                              INCAR=INCAR_OK, KPOINTS=KPTS_OK), False, ["potcar-empty"])
CASES["ldau"] = (make(
    "ldau", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, KPOINTS=KPTS_OK,
    INCAR=INCAR_OK + "LDAU = .TRUE.\nLDAUTYPE = 2\nLDAUL = 2\nLDAUU = 4.0\nLDAUJ = 0.0\n"),
    True, ["ldau-lmaxmix"])
CASES["icharg"] = (make(
    "icharg", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, KPOINTS=KPTS_OK,
    INCAR=INCAR_OK + "ICHARG = 11\n"), False, ["icharg-no-chgcar"])
CASES["hybrid"] = (make(
    "hybrid", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, KPOINTS=KPTS_OK,
    INCAR=INCAR_OK + "LHFCALC = .TRUE.\nHFSCREEN = 0.2\nAEXX = 0.25\nNCORE = 4\n"),
    True, ["hybrid-ncore"])
CASES["scan-vdw"] = (make(
    "scan-vdw", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, KPOINTS=KPTS_OK,
    INCAR=INCAR_OK + "METAGGA = SCAN\nLUSE_VDW = .TRUE.\nIVDW = 202\n"),
    False, ["vdw-double-count"])
CASES["addgrid-vdw"] = (make(
    "addgrid-vdw", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, KPOINTS=KPTS_OK,
    INCAR=INCAR_OK + "ADDGRID = .TRUE.\nIVDW = 11\n"), False, ["addgrid-vdw"])
CASES["isf3-low"] = (make(
    "isf3-low", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, KPOINTS=KPTS_OK,
    INCAR=INCAR_OK.replace("ENCUT = 520", "ENCUT = 420")), True,
    ["encut-tight", "isif3-encut"])
CASES["gamma-4line"] = (make(
    "gamma-4line", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, INCAR=INCAR_OK,
    KPOINTS="auto\n0\nGamma\n16 16 16\n"), False, ["kpoints-gamma"])
CASES["list-count-wrong"] = (make(
    "list-count-wrong", POSCAR=POSCAR_OK, POTCAR=POTCAR_C, INCAR=INCAR_OK,
    KPOINTS="explicit list\n5\nrec\n  0.0 0.0 0.0 1\n  0.5 0.0 0.0 1\n"),
    False, ["kpoints-count"])

bad = 0
for name, (d, want_ok, want_checks) in CASES.items():
    r = preflight.check(str(d))
    fired = [f["check"] for f in r["findings"]]
    problems = []
    if r["ok"] != want_ok:
        problems.append(f"ok={r['ok']} wanted {want_ok}")
    for check in want_checks:
        if check not in fired:
            problems.append(f"missing {check}")
    if not want_checks and fired:
        problems.append(f"should be silent, fired {fired}")
    if problems:
        bad += 1
        print(f"FAIL {name:16s} e={r['errors']} w={r['warnings']} fired={fired} :: "
              + "; ".join(problems))
    else:
        print(f"ok   {name:16s} e={r['errors']} w={r['warnings']} fired={fired}")

# read_kmesh must only answer for a well-formed integer grid, because the number
# it returns decides how many k-points a calculation will actually use. A Gamma
# file that is missing its shift line still names a 16x16x16 mesh: the missing
# shift is its own error (kpoints-gamma), and the mesh size stays answerable --
# conflating the two would make the "too few k-points for ISMEAR = -5" check
# report nothing at all for such a file.
kmesh_want = {"ok-gamma": 4096, "ok-line": None, "gamma-4line": 4096}
for name, want in kmesh_want.items():
    got = preflight.read_kmesh(CASES[name][0] / "KPOINTS")
    if got != want:
        bad += 1
        print(f"FAIL read_kmesh({name}) = {got}, wanted {want}")
    else:
        print(f"ok   read_kmesh({name}) = {got}")

shutil.rmtree(ROOT, ignore_errors=True)
print(f"\n{len(CASES) + len(kmesh_want)} cases, {bad} failure(s)")
sys.exit(bad)
