#!/usr/bin/env python3
"""qvasp MCP server: run qvasp, execute staged VASP workflows, parse results.

Speaks the Model Context Protocol over stdio (newline-delimited JSON-RPC 2.0).
No third-party dependencies; Python >= 3.8.

Configuration (environment):
  QVASP_BIN        path to the qvasp executable          (default: qvasp on PATH)
  QVASP_WORKROOT   directory workflows may live under    (default: $HOME)
  QVASP_SCHEDULER  pbs | slurm | none                    (default: pbs)
  QVASP_PY         unused placeholder

Tools:
  qvasp_run        run one qvasp subcommand in a directory
  qvasp_help       bounded help text / command list
  workflow_plan    expand a workflow template into stages (no execution)
  workflow_run     execute the next ready stage(s); submits VASP jobs
  workflow_status  stage/job state of a workflow directory
  workflow_resume  continue a workflow whose job has finished
  workflow_check   lint a template (prototypes, commands, gates)
  structure_check  symmetry / geometry sanity of a POSCAR
  result_extract   parse a VASP output into typed values
  result_compare   classify a computed value against sourced references
  reference_lookup / literature_record   curated and user-recorded references
  report_build     assemble report.md from the recorded analysis
  diagnose_log     explain a failed run from its logs (signature table)
  aux_list / aux_run   optional bridges to vaspkit, p4vasp, bader, phonopy

Safety: every command is validated against the `qvasp -h` command list and executed
with an argv list (never a shell); every cwd must resolve under QVASP_WORKROOT.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

QVASP_BIN = os.environ.get("QVASP_BIN", "qvasp")
WORKROOT = Path(os.environ.get("QVASP_WORKROOT", str(Path.home()))).resolve()
SCHEDULER = os.environ.get("QVASP_SCHEDULER", "pbs")
TEMPLATE_DIR = Path(__file__).resolve().parent / "workflows"
STATE = "workflow.json"

_cmds = None


def qvasp_commands():
    """Whitelist of real qvasp commands, parsed from `qvasp -h` once.

    Returns [] when the binary is unavailable (not installed / QVASP_BIN wrong):
    every caller must treat an empty whitelist as "cannot verify command names"
    rather than "no commands exist"."""
    global _cmds
    if _cmds is None:
        try:
            out = subprocess.run([QVASP_BIN, "-h"], capture_output=True, text=True,
                                 timeout=30).stdout
            _cmds = sorted(set(re.findall(r"qvasp\s+(-[A-Za-z0-9_]+)", out)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            # FileNotFoundError when qvasp is not on PATH; keep the server usable
            # for template linting and analysis tools that do not need the binary.
            _cmds = []
            print(f"[qvasp_mcp] warning: cannot run '{QVASP_BIN} -h' ({exc}); "
                  f"command whitelist unavailable. Install qvasp or set QVASP_BIN.",
                  file=sys.stderr)
    return _cmds


def safe_cwd(cwd):
    p = (WORKROOT / cwd).resolve() if not os.path.isabs(cwd) else Path(cwd).resolve()
    if WORKROOT != p and WORKROOT not in p.parents:
        raise ValueError(f"cwd {p} is outside QVASP_WORKROOT {WORKROOT}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def tail(path, n=60):
    try:
        return "\n".join(Path(path).read_text(errors="replace").splitlines()[-n:])
    except OSError:
        return ""


# --------------------------------------------------------------------- tools --
def run_qvasp(args):
    """Run one qvasp subcommand. Kept apart from tool_workflow_run so that a
    workflow stage can call it without re-entering the workflow runner."""
    cmd = str(args.get("command") or "").strip()
    if not cmd:
        return err("qvasp_run needs 'command', e.g. \"-pbe C H\" or \"-sc 2 2 2\"; "
                   "see qvasp_help for the 88 subcommands")
    sub = [tok for tok in cmd.split() if tok.startswith("-")]
    if not qvasp_commands():
        return err(f"qvasp binary not available (tried '{QVASP_BIN} -h'); "
                   f"install qvasp or set QVASP_BIN")
    if not sub or sub[0] not in qvasp_commands():
        return err(f"unknown qvasp command {sub[:1]}; see qvasp_help")
    cwd = safe_cwd(args.get("cwd", "."))
    argv = [QVASP_BIN] + cmd.split()
    stdin = "\n".join(args.get("stdin", [])) + ("\n" if args.get("stdin", []) else "")
    before = {p.name for p in cwd.iterdir() if p.is_file()}
    t0 = time.time()
    run_env = None
    env_src = args.get("env_sources")
    if env_src:
        # `subprocess.run("export ...", shell=True, env=env)` cannot mutate the
        # parent dict — each shell exits with its own copy.  The sources are
        # therefore applied here as text: PATH gets appended, KEY=VALUE pairs
        # are set, and only truly sourced files would still need a wrapper.
        run_env = dict(os.environ)
        for part in env_src.split("\n"):
            part = part.strip()
            if not part:
                continue
            if part.startswith("export PATH"):
                extra = part.split("=", 1)[1].replace("$PATH", run_env.get("PATH", ""))
                run_env["PATH"] = extra
            elif part.startswith("export "):
                kv = part[len("export "):]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    run_env[k] = v.replace("$PATH", run_env.get("PATH", ""))
    proc = subprocess.run(argv, cwd=str(cwd), input=stdin, capture_output=True, text=True,
                          timeout=args.get("timeout_s", 600), env=run_env)
    out = (proc.stdout or "") + (proc.stderr or "")
    after = {p.name for p in cwd.iterdir() if p.is_file()}
    return {
        "exit_code": proc.returncode,
        "elapsed_s": round(time.time() - t0, 2),
        "cwd": str(cwd),
        "new_files": sorted(after - before),
        "stdout_tail": "\n".join(out.splitlines()[-60:]),
        "qvasp_error": bool(re.search(r"\[qvasp ERROR\]", out)),
    }


def tool_help(args):
    topic = args.get("topic")
    if topic:
        out = subprocess.run([QVASP_BIN, "-h"], capture_output=True, text=True, timeout=30).stdout
        hits = [ln for ln in out.splitlines() if topic in ln]
        return {"commands": qvasp_commands(), "matching_lines": hits[:20]}
    return {"commands": qvasp_commands(), "count": len(qvasp_commands())}


# ------------------------------------------------------------------ workflows --
def kpoints_stdin(stage):
    """Answers for the interactive k-point generators (-kline/-khse ask for the
    dimensionality). Without them the prompt reads EOF and the command aborts
    with 'ERROR: invalid dimensionality'. 3 = bulk is the default assumption;
    a stage may override it with "dim": 2 or 1."""
    return [str(stage.get("dim", 3))]


def load_template(wf_id):
    path = TEMPLATE_DIR / f"{wf_id}.json"
    if not path.exists():
        raise ValueError(f"no template {wf_id} in {TEMPLATE_DIR}")
    return json.loads(path.read_text(encoding="utf-8"))


STAGES_FILE = Path(__file__).resolve().parent / "stages.json"
_stages = None


def stage_prototypes():
    """The prototype registry (server/stages.json), loaded once."""
    global _stages
    if _stages is None:
        _stages = json.loads(STAGES_FILE.read_text(encoding="utf-8"))["prototypes"]
    return _stages


def expand_stage(stage):
    """Merge a stage with its prototype. The stage always wins.

    Lists (requires/produces) are replaced, not concatenated, so a stage can
    narrow a prototype without silently inheriting a stale requirement.
    """
    proto = stage.get("prototype")
    if not proto:
        return dict(stage)
    reg = stage_prototypes()
    if proto not in reg:
        raise ValueError(f"unknown prototype {proto}; known: {sorted(reg)}")
    merged = dict(reg[proto])
    merged.pop("note", None)
    merged.update({k: v for k, v in stage.items() if k != "prototype"})
    if "overrides" in reg[proto] or "overrides" in stage:
        ov = dict(reg[proto].get("overrides") or {})
        ov.update(stage.get("overrides") or {})
        merged["overrides"] = ov
    merged["prototype"] = proto
    return merged


def stages_of(tpl, strategy=None):
    if "strategies" in tpl:
        strat = strategy or tpl.get("default_strategy")
        if strat not in tpl["strategies"]:
            raise ValueError(f"unknown strategy {strat}; choose one of {sorted(tpl['strategies'])}")
        stages, strat = tpl["strategies"][strat]["stages"], strat
    else:
        stages, strat = tpl.get("stages", []), strategy
    return [expand_stage(s) for s in stages], strat


GATE_TYPES = {"ionic_converged", "scf_converged", "file_present", "no_error",
              "frequencies_present"}


def validate_template(tpl):
    """Static checks: prototypes exist, commands are real, gates are known,
    and every `requires` file is produced by an earlier stage or shipped by the user."""
    problems, warnings = [], []
    strats = list((tpl.get("strategies") or {"_": {}}).keys())
    total = 0
    for strat in strats:
        try:
            stages, _ = stages_of(tpl, None if strat == "_" else strat)
        except ValueError as exc:
            problems.append(f"[{strat}] {exc}")
            continue
        total = max(total, len(stages))
        available = {"POSCAR", "POTCAR", "KPOINTS", "INCAR"}
        for st in stages:
            sid = st.get("id")
            if not sid:
                problems.append(f"[{strat}] a stage has no id")
                continue
            for req in st.get("requires") or []:
                if req not in available:
                    warnings.append(f"[{strat}] stage {sid} needs {req}, which no earlier "
                                    f"stage produces (the user must supply it)")
            gate = st.get("gate")
            if gate:
                if gate.get("type") not in GATE_TYPES:
                    problems.append(f"[{strat}] stage {sid} has unknown gate {gate.get('type')}")
                elif gate.get("type") == "file_present" and not gate.get("file"):
                    problems.append(f"[{strat}] stage {sid} file_present gate names no file")
            cmd = st.get("qvasp")
            # Skip command-name checks when the qvasp binary is unavailable
            # (empty whitelist): linting structure/gates must not depend on it.
            if cmd and qvasp_commands() and cmd.split()[0] not in qvasp_commands():
                problems.append(f"[{strat}] stage {sid} runs {cmd}, not a qvasp command")
            if st.get("kind") == "manual" and not (st.get("note") or "").strip():
                problems.append(f"[{strat}] manual stage {sid} has no note saying what to do")
            if st.get("kind") == "manual" and not st.get("gate"):
                problems.append(f"[{strat}] manual stage {sid} has no gate to tell when it is done")
            if st.get("kpoints") and qvasp_commands() and st["kpoints"].split()[0] not in qvasp_commands():
                problems.append(f"[{strat}] stage {sid} kpoints {st['kpoints']} is not a command")
            if st.get("kpoints_opt") and qvasp_commands() and st["kpoints_opt"].split()[0] not in qvasp_commands():
                problems.append(f"[{strat}] stage {sid} kpoints_opt {st['kpoints_opt']} is not a command")
            available |= set(st.get("produces") or [])
    return {"workflow": tpl.get("id"), "strategies": strats, "stages": total,
            "problems": problems, "warnings": warnings, "ok": not problems}


def tool_check(args):
    name = args.get("workflow")
    ids = [name] if name else sorted(p.stem for p in TEMPLATE_DIR.glob("*.json"))
    results = [validate_template(load_template(i)) for i in ids]
    return {"checked": ids, "results": results,
            "ok": all(r.get("ok") for r in results),
            "problems": [p for r in results for p in (r.get("problems") or [])]}


def plan(wf_id, system, strategy=None):
    tpl = load_template(wf_id)
    stages, strat = stages_of(tpl, strategy)
    return {"workflow": wf_id, "system": system,
            "strategy": strat,
            "stage_dir": str(Path(system) / "workflow"),
            "stages": [{k: v for k, v in s.items() if k in
                        ("id", "kind", "prototype", "qvasp", "kpoints", "kpoints_opt",
                         "inputs", "overrides", "requires", "produces", "gate")}
                       for s in stages]}


def workflow_state(root):
    p = Path(root) / STATE
    return json.loads(p.read_text()) if p.exists() else None


def apply_overrides(incar_path, overrides):
    """Set INCAR tags, replacing any value the template already had.

    Appending would leave two lines for the same tag; VASP then warns and the
    winner depends on parse order, so a workflow could silently run with the
    template value instead of the stage's.
    """
    p = Path(incar_path)
    if not overrides or not p.exists():
        return
    kept, seen = [], set()
    for line in p.read_text(errors="replace").splitlines():
        tag = line.split("=")[0].strip().upper() if "=" in line else ""
        if tag and tag in {k.upper() for k in overrides}:
            seen.add(tag)
            continue
        kept.append(line)
    kept.append("")
    kept.append("# --- workflow overrides ---")
    for k, v in overrides.items():
        if isinstance(v, bool):
            v = ".TRUE." if v else ".FALSE."
        kept.append(f"  {k} = {v}")
    p.write_text("\n".join(kept) + "\n")


def vasp_log_failure(cwd):
    """The line that killed a job, if the job died instead of finishing.

    A missing binary, a scheduler kill or a VASP abort all leave the real cause
    in vasp.log; reporting only "no convergence marker" sends the user hunting
    through the OUTCAR for something that never ran.
    """
    log = Path(cwd) / "vasp.log"
    if not log.exists():
        return None
    txt = log.read_text(errors="replace")
    for marker in ("execvp error", "command not found", "KILLED BY SIGNAL",
                   "ZBRENT: fatal", "I REFUSE TO CONTINUE", "VERY BAD NEWS",
                   "Error EDDDAV", "No such file or directory"):
        for line in txt.splitlines():
            if marker in line:
                return line.strip()[:300]
    return None


def check_gate(kind, cwd, spec):
    cwd = Path(cwd)
    if kind == "ionic_converged":
        txt = (cwd / "OUTCAR").read_text(errors="replace") if (cwd / "OUTCAR").exists() else ""
        ok = "reached required accuracy" in txt
        if ok:
            return True, "OUTCAR has reached required accuracy"
        died = vasp_log_failure(cwd)
        return False, ("job failed: " + died) if died else "no convergence marker"
    if kind == "scf_converged":
        # "F=" on the final OSZICAR line means the SCF loop exited normally.
        # A run that hits NELM also prints F=, so the marker alone is not enough:
        # the electronic step count must be below NELM as well.
        lines = tail(cwd / "OSZICAR", 6).splitlines()
        last = next((ln for ln in reversed(lines) if "F=" in ln), "")
        if not last:
            return False, "OSZICAR has no F= line (SCF did not run)"
        n_elec = last.split()[0] if last.split() else ""
        nelm = 60
        inc = cwd / "INCAR"
        if inc.exists():
            for ln in inc.read_text(errors="replace").splitlines():
                s = ln.replace("=", " ").split()
                if len(s) >= 2 and s[0].upper() == "NELM":
                    try:
                        nelm = int(float(s[1]))
                    except ValueError:
                        pass
        try:
            hit_limit = int(n_elec) >= nelm
        except ValueError:
            hit_limit = False
        if hit_limit:
            return False, f"SCF stopped at NELM={nelm} without converging"
        return True, f"SCF converged after {n_elec} electronic steps"
    if kind == "file_present":
        ok = (cwd / spec).exists() and (cwd / spec).stat().st_size > 0
        return ok, f"{spec} present" if ok else f"{spec} missing/empty"
    if kind == "no_error":
        txt = (cwd / "vasp.log").read_text(errors="replace") if (cwd / "vasp.log").exists() else ""
        bad = [m for m in ("ZBRENT: fatal", "I REFUSE TO CONTINUE", "KILLED BY SIGNAL",
                           "Error EDDDAV", "VERY BAD NEWS") if m in txt]
        return not bad, ("vasp.log clean" if not bad else "vasp.log reports: " + "; ".join(bad))
    if kind == "frequencies_present":
        txt = (cwd / "OUTCAR").read_text(errors="replace") if (cwd / "OUTCAR").exists() else ""
        ok = "f/i=" in txt or "THz" in txt
        return ok, "frequencies in OUTCAR" if ok else "no frequency block in OUTCAR"
    return True, "no gate"


def submit(cwd, template):
    cwd = Path(cwd)
    if SCHEDULER == "none":
        return None
    if SCHEDULER == "pbs":
        if not (cwd / "vasp.pbs").exists():
            raise ValueError("vasp.pbs missing in " + str(cwd))
        out = subprocess.run([scheduler_tool("qsub"), "vasp.pbs"], cwd=str(cwd),
                             capture_output=True, text=True)
    else:
        out = subprocess.run([scheduler_tool("sbatch"), "run.sh"], cwd=str(cwd),
                             capture_output=True, text=True)
    job = (out.stdout or "").strip().split()[0] if out.stdout.strip() else ""
    if not job:
        raise ValueError("submit failed: " + (out.stderr or out.stdout or "no output").strip())
    return {"job_id": job, "raw": out.stdout.strip(), "error": out.stderr.strip()}


def tool_plan(args):
    wf = str(args.get("workflow") or "").strip()
    if not wf:
        return err("workflow_plan needs 'workflow'; list valid names with workflow_check")
    return plan(wf, args.get("system", "."), args.get("strategy"))


VASP_CMD = os.environ.get("QVASP_VASP_CMD", "vasp_std")


def resolve_vasp():
    """Absolute path to the VASP binary.

    Compute nodes do not inherit the login shell's PATH, so a bare `vasp_std` in
    the job script dies with `execvp error on file vasp_std (No such file or
    directory)`. Resolve it here, where the login environment is still visible.
    """
    if "/" in VASP_CMD:
        return VASP_CMD
    found = shutil.which(VASP_CMD)
    if found:
        return found
    for cand in ("/public/software/vasp/vasp.6.5.1/bin/vasp_std",
                 "/opt/vasp/bin/vasp_std", "/usr/local/bin/vasp_std"):
        if Path(cand).exists():
            return cand
    return VASP_CMD

PBS_TEMPLATE = """#!/bin/sh -f
#PBS -N {name}
#PBS -l nodes=1:ppn={cores}
#PBS -l walltime={walltime}
#PBS -q {queue}
#PBS -V
#PBS -S /bin/bash

cd $PBS_O_WORKDIR
ulimit -s unlimited
export OMP_STACKSIZE=512M
export OMP_NUM_THREADS=1
{env_sources}
NP=`cat $PBS_NODEFILE | wc -l`
mpirun -n $NP {vasp} > vasp.log 2>&1
"""

# The Intel/IMPI environment files this cluster needs before mpirun works.
# Without them the job dies immediately with "mpirun: command not found".
ENV_SOURCES = os.environ.get(
    "QVASP_ENV_SOURCES",
    "source /public/environment/intel2020.env\nsource /public/environment/impi2019.env")
POST_ENV_SOURCES = os.environ.get(
    "QVASP_POST_ENV_SOURCES",
    "export PATH=$PATH:$HOME/.local/bin")
QUEUE = os.environ.get("QVASP_QUEUE", "batch")

# Torque lives outside the login PATH on this cluster; look for it explicitly
# rather than assuming the caller exported it.
SCHEDULER_BIN = {}


def scheduler_tool(name):
    """Absolute path of a scheduler command, or the bare name if not found.

    The cache is keyed by command name: caching a single path and returning it
    for every name made `qstat` resolve to the `qsub` binary, and the job state
    check then asked qsub for the queue -- `qstat: Unknown queue destination
    vasp.pbs`, which the server reported as a failed submission.
    """
    if name not in SCHEDULER_BIN:
        found = shutil.which(name)
        for cand in ("/opt/tsce4/torque6/bin", "/usr/local/bin", "/usr/bin"):
            if not found and (Path(cand) / name).exists():
                found = str(Path(cand) / name)
        SCHEDULER_BIN[name] = found or name
    return SCHEDULER_BIN[name]


def write_pbs(cwd):
    path = Path(cwd) / "vasp.pbs"
    if path.exists():
        return path
    path.write_text(PBS_TEMPLATE.format(name=Path(cwd).name, cores=12, walltime="24:00:00",
                                        queue=QUEUE, env_sources=ENV_SOURCES,
                                        vasp=resolve_vasp()))
    return path


def job_alive(job_id):
    if not job_id or SCHEDULER == "none":
        return False
    tool = "qstat" if SCHEDULER == "pbs" else "squeue"
    exe = scheduler_tool(tool)
    out = subprocess.run([exe, "-j", job_id] if tool == "squeue" else [exe, job_id],
                         capture_output=True, text=True)
    text = (out.stdout or "") + (out.stderr or "")
    if "Unknown Job Id" in text or "Invalid job id" in text:
        return False
    return text.strip() != "" and out.returncode == 0


def tool_workflow_run(args):
    """Advance a workflow by one stage. (Named distinctly from run_qvasp, which
    runs a single qvasp command — a shared name made this call itself.)"""
    wf = str(args.get("workflow") or "").strip()
    if not wf:
        return err("workflow_run needs 'workflow' and 'system' (the case directory); "
                   "list valid names with workflow_check")
    root = safe_cwd(args.get("system", "."))
    tpl = load_template(wf)
    st = workflow_state(root) or {"workflow": wf, "system": str(root), "stages": {}}
    stages, strat = stages_of(tpl, args.get("strategy") or st.get("strategy"))
    st["strategy"] = strat
    for stage in stages:
        sid = stage["id"]
        dry_notes = []
        rec = st["stages"].setdefault(sid, {"state": "pending"})
        if rec["state"] == "done":
            continue
        if rec["state"] == "prepared" and SCHEDULER == "none":
            # dry run: inputs were written last time, walk on to the next stage
            continue
        cwd = root / sid
        if rec["state"] == "manual":
            # the user was asked to run this step by hand; check whether the
            # product appeared, and keep asking if it did not
            gate = stage.get("gate")
            if gate:
                ok, msg = check_gate(gate.get("type"), cwd, gate.get("file", ""))
                rec["gate"] = {"type": gate.get("type"), "ok": ok, "detail": msg}
                if not ok:
                    return {"stage": sid, "manual": stage.get("note", ""),
                            "waiting_for": msg, "cwd": str(cwd),
                            "hint": "run this step by hand, then call workflow_resume"}
            rec["state"] = "done"
            save(root, st)
            continue
        if rec["state"] == "submitted" and stage.get("kind", "calc") == "calc":
            if job_alive(rec.get("job_id")):
                return {"waiting": True, "stage": sid, "job_id": rec.get("job_id"),
                        "hint": "call workflow_status/workflow_resume when the job ends"}
            gate = stage.get("gate")
            if gate:
                ok, msg = check_gate(gate.get("type"), cwd, gate.get("file", ""))
                rec["gate"] = {"type": gate.get("type"), "ok": ok, "detail": msg}
                if not ok:
                    rec.update(state="failed", error=msg)
                    save(root, st)
                    return {"stage": sid, "gate_failed": msg}
            rec["state"] = "done"
            save(root, st)
            continue
        cwd.mkdir(parents=True, exist_ok=True)
        # The first stage has nothing to inherit from, so it takes the structure
        # files the user dropped at the system root. Later stages copy from the
        # previous stage through `inputs`.
        if not stage.get("inputs"):
            for name in ("POSCAR", "POTCAR", "KPOINTS", "INCAR", "MAGMOM"):
                s = root / name
                if s.exists() and not (cwd / name).exists():
                    shutil.copy2(s, cwd / name)
        for src, dst in (stage.get("inputs") or {}).items():
            # Two conventions have to work, and the templates use both:
            #   "../00-relax/CONTCAR"  relative to this stage's directory
            #   "POSCAR-slab"          a file the user left at the system root
            # Resolving only against the root silently sent "../x" one level
            # above the system, so a real run failed on a file that was there.
            cand = [(cwd / src).resolve(), (root / src).resolve()]
            s = next((c for c in cand if c.exists()), None)
            if s is not None:
                # a destination may name a sub-directory (e.g. "bulk/OUTCAR"),
                # because some qvasp commands read fixed folder names
                (cwd / dst).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, cwd / dst)
            elif SCHEDULER == "none":
                # dry run: nothing has been computed yet, so a missing upstream
                # product is expected — prepare the inputs and say so.
                dry_notes.append(f"{src} not available yet (dry run)")
            else:
                rec.update(state="failed",
                           error=f"input {src} not produced by an earlier stage")
                save(root, st)
                return {"stage": sid, "failed": f"missing input {src}"}
        # POTCAR never comes from `inputs` (it is licensed and user-supplied),
        # so carry it forward from the root for every calc stage.
        if stage.get("kind", "calc") == "calc" and not (cwd / "POTCAR").exists():
            if (root / "POTCAR").exists():
                shutil.copy2(root / "POTCAR", cwd / "POTCAR")
            else:
                rec.update(state="failed", error="POTCAR missing at the system root")
                save(root, st)
                return {"stage": sid, "failed": "POTCAR missing at the system root"}
        if SCHEDULER == "none" and not (cwd / "POSCAR").exists() and (root / "POSCAR").exists() \
                and (stage.get("kpoints") or stage.get("kpoints_opt")):
            # k-point generation needs a structure to read the lattice from.
            # In a dry run the upstream CONTCAR does not exist yet, so borrow
            # the root POSCAR and say so — the path itself only depends on the
            # lattice type, which relaxation does not change.
            shutil.copy2(root / "POSCAR", cwd / "POSCAR")
            dry_notes.append("POSCAR borrowed from the system root to build the k-point file (dry run)")
        kind = stage.get("kind", "calc")
        if kind == "manual":
            # Some steps are not qvasp commands at all: phonopy -f, phonopy
            # --fc-symmetry, a hand edit. The tool cannot run them, so it stops
            # here and says what the user has to do. Recording them as done
            # would be a lie, and a gate error would blame the wrong thing.
            rec.update(state="manual", note=stage.get("note", ""))
            save(root, st)
            return {"stage": sid, "manual": stage.get("note", ""),
                    "cwd": str(cwd),
                    "hint": "run this step by hand, then call workflow_resume"}
        if SCHEDULER == "none" and dry_notes and kind == "post":
            # A post-processing stage has nothing to chew on in a dry run.
            # Running it on an empty directory would "succeed" and record a
            # fake done state, so stop here and report why.
            rec.update(state="prepared", note="dry run: upstream products missing")
            save(root, st)
            return {"stage": sid, "prepared": str(cwd), "notes": dry_notes,
                    "hint": "post stage skipped in dry run: its inputs do not exist yet"}
        log = ""
        if stage.get("qvasp"):
            extra_env = POST_ENV_SOURCES if kind == "post" else ""
            r = run_qvasp({"command": stage["qvasp"], "cwd": str(cwd), "stdin": stage.get("stdin", []),
                           "env_sources": extra_env})
            log = r["stdout_tail"]
            if r["exit_code"] != 0 or r["qvasp_error"]:
                rec.update(state="failed", error=log)
                save(root, st)
                return {"failed": sid, "log": log}
            if kind == "calc":
                apply_overrides(cwd / "INCAR", stage.get("overrides"))
        if stage.get("kpoints_opt"):
            # band path -> KPOINTS_OPT, then a uniform mesh -> KPOINTS
            run_qvasp({"command": stage["kpoints_opt"], "cwd": str(cwd),
                       "stdin": kpoints_stdin(stage)})
            src = cwd / "KPOINTS"
            if src.exists():
                src.replace(cwd / "KPOINTS_OPT")
            if stage.get("kpoints"):
                run_qvasp({"command": stage["kpoints"], "cwd": str(cwd),
                           "stdin": kpoints_stdin(stage)})
        elif stage.get("kpoints"):
            run_qvasp({"command": stage["kpoints"], "cwd": str(cwd),
                       "stdin": kpoints_stdin(stage)})
        if kind == "calc":
            write_pbs(cwd)
            try:
                sub = submit(cwd, tpl)
            except ValueError as exc:
                rec.update(state="failed", error=str(exc))
                save(root, st)
                return {"stage": sid, "failed": str(exc)}
            if sub is None:
                # QVASP_SCHEDULER=none: inputs are prepared but nothing runs.
                rec.update(state="prepared", note="scheduler disabled: inputs only")
                save(root, st)
                out = {"stage": sid, "prepared": str(cwd),
                       "hint": "QVASP_SCHEDULER=none — inputs written, no job submitted"}
                if dry_notes:
                    out["notes"] = dry_notes
                return out
            rec.update(state="submitted", **sub)
            save(root, st)
            out = {"stage": sid, "submitted": sub}
            if dry_notes:
                out["notes"] = dry_notes
            return out
        gate = stage.get("gate")
        if gate and SCHEDULER != "none":
            ok, msg = check_gate(gate.get("type"), cwd, gate.get("file", ""))
            rec["gate"] = {"type": gate.get("type"), "ok": ok, "detail": msg}
            if not ok:
                rec.update(state="failed", error=msg)
                save(root, st)
                return {"stage": sid, "gate_failed": msg}
        rec["state"] = "done"
        save(root, st)
    return {"workflow": wf, "done": True, "stages": {k: v["state"] for k, v in st["stages"].items()}}


def save(root, st):
    (Path(root) / STATE).write_text(json.dumps(st, indent=1))


def tool_status(args):
    root = safe_cwd(args.get("system", "."))
    st = workflow_state(root)
    if not st:
        return {"error": "no workflow in " + str(root)}
    # A submitted stage whose job has already left the queue is reported as
    # still "submitted" in workflow.json; say so explicitly instead of making
    # the caller poll a job id that no longer exists.
    for sid, rec in (st.get("stages") or {}).items():
        if rec.get("state") == "submitted" and rec.get("job_id"):
            if not job_alive(rec["job_id"]):
                rec["note"] = (f"job {rec['job_id']} has left the queue; call "
                               f"workflow_resume to evaluate its gate")
                rec["job_finished"] = True
    return st


def tool_resume(args):
    wf = args.get("workflow")
    if not wf:
        return err("workflow_resume needs 'workflow' (and 'system', the case directory); "
                   "list valid names with workflow_check")
    return tool_workflow_run({"workflow": wf, "system": args.get("system", "."),
                              "strategy": args.get("strategy")})


# ------------------------------------------------------------- analysis ----
def _analysis():
    import sys as _sys
    here = Path(__file__).resolve().parent
    # the module may sit either next to analysis/ or one level above server/
    for cand in (here, here / "server"):
        if (cand / "analysis").is_dir() and str(cand) not in _sys.path:
            _sys.path.insert(0, str(cand))
            break
    from analysis import parsers, structure, compare, report  # noqa: PLC0415
    return parsers, structure, compare, report


def tool_structure_check(args):
    _, structure, _, _ = _analysis()
    path = safe_cwd(args.get("cwd", ".")) / args.get("file", "POSCAR")
    if not path.exists():
        return err(f"{path} not found")
    return structure.check(str(path), symprec=args.get("symprec", 1e-3))


def tool_result_extract(args):
    if "file" not in args or "kind" not in args:
        return err("result_extract needs 'file' (e.g. OUTCAR/EIGENVAL/DOSCAR) and 'kind' "
                   "(known: band_gap, dos_at_ef, mae, phonon_min, rdf_first_peak, thermo)")
    parsers, _, _, _ = _analysis()
    path = safe_cwd(args.get("cwd", ".")) / args["file"]
    if not path.exists():
        return err(f"{path} not found")
    return parsers.extract(args["kind"], str(path))


def tool_result_compare(args):
    _, _, compare, _ = _analysis()
    if "value" not in args and "computed" in args:
        args = dict(args, value=args["computed"])
    if not str(args.get("property") or "").strip():
        return err("result_compare needs 'property' (e.g. \"band_gap\") so the library "
                   "knows which quantity is being compared")
    if "value" not in args:
        return err("result_compare needs the computed value as 'value' "
                   "(e.g. {\"property\":\"band_gap\",\"value\":1.17,\"unit\":\"eV\"})")
    if "unit" not in args:
        return err("result_compare needs the unit of the computed value, "
                   "because a comparison across units is meaningless")
    computed = {"value": args["value"], "unit": args["unit"]}
    hits = compare.lookup(args["property"], args.get("formula"), args.get("phase"))
    if not hits:
        return {"verdict": "unverified",
                "reason": f"no reference for {args['property']} of {args.get('formula')}",
                "computed": computed}
    results = [compare.compare(computed, rec, args.get("method", "pbe")) for rec in hits]
    results.sort(key=lambda r: {"consistent": 0, "systematic": 1,
                                "discrepant": 2, "unverified": 3}[r["verdict"]])
    return {"property": args["property"], "computed": computed, "matches": results,
            "best": results[0]}


def tool_reference_lookup(args):
    _, _, compare, _ = _analysis()
    prop = str(args.get("property") or "").strip()
    if not prop:
        return err("reference_lookup needs 'property' (e.g. \"band_gap\", \"raman\", "
                   "\"k1\", \"dos_at_ef\") plus optionally 'formula' and 'phase'")
    hits = compare.lookup(prop, args.get("formula"), args.get("phase"))
    return {"property": prop, "count": len(hits), "records": hits}


def tool_literature_record(args):
    """Append a sourced value to <cwd>/refs.json (per-case, never the shipped library)."""
    cwd = safe_cwd(args.get("cwd", "."))
    entry = {k: args.get(k) for k in ("property", "value", "unit", "formula", "phase",
                                      "method", "conditions", "citation", "doi", "url")}
    if not (entry.get("doi") or entry.get("url")):
        return err("a literature record needs a doi or a url — unsourced values are refused")
    path = cwd / "refs.json"
    data = json.loads(path.read_text()) if path.exists() else {"records": []}
    data["records"].append(entry)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return {"written": str(path), "records": len(data["records"])}


def tool_report_build(args):
    _, structure, _, report = _analysis()
    raw = str(args.get("system") or "").strip()
    if not raw:
        return err("report_build needs 'system' (the case directory, relative to QVASP_WORKROOT); "
                   "it does not default to the workroot root, because that writes report.md "
                   "outside the case it is supposed to describe")
    target = (WORKROOT / raw).resolve() if not os.path.isabs(raw) else Path(raw).resolve()
    if WORKROOT != target and WORKROOT not in target.parents:
        return err(f"cwd {target} is outside QVASP_WORKROOT {WORKROOT}")
    if not target.is_dir():
        return err(f"report_build: {target} does not exist; it reports on a directory that already holds a run")
    poscar = target / str(args.get("poscar") or "POSCAR")
    extracts = args.get("extract") or []
    compares = args.get("compare") or []
    if not (target / STATE).exists() and not poscar.exists() and not extracts:
        return err(f"report_build: nothing to report in {target} "
                   f"(no {STATE}, no {poscar.name}, no 'extract' items); "
                   "pass the case directory that holds the run, or the values to extract")
    for item in extracts:
        if not isinstance(item, dict) or not item.get("file") or not item.get("kind"):
            return err("each 'extract' item needs 'file' and 'kind', "
                       r'e.g. {"file": "EIGENVAL", "kind": "band_gap"}')
    for item in compares:
        if not isinstance(item, dict) or not item.get("property") or item.get("value") is None:
            return err("each 'compare' item needs 'property' and 'value', "
                       r'e.g. {"property": "band_gap", "value": 4.12, "unit": "eV"}')
    cwd = safe_cwd(raw)
    st = None
    if poscar.exists():
        st = structure.check(str(poscar))
    extracted = []
    for item in extracts:
        p = cwd / item["file"]
        if p.exists():
            parsers, _, _, _ = _analysis()
            extracted.append(parsers.extract(item["kind"], str(p)))
    auto_missing = None
    if str(args.get("auto") or "").lower() in ("1", "true", "yes", "on") or (
            not extracts and not compares):
        # Nothing was named: read whatever the directory actually holds instead
        # of asking the caller to guess the file layout first.
        parsers, _, _, _ = _analysis()
        auto, auto_missing = parsers.discover(str(cwd))
        extracted.extend(auto)
    comparisons = []
    for item in compares:
        _, _, compare, _ = _analysis()
        hits = compare.lookup(item["property"], item.get("formula"), item.get("phase"))
        if hits:
            r = compare.compare({"value": item["value"], "unit": item.get("unit", "")},
                                hits[0], item.get("method", "pbe"))
            r["property"] = item["property"]
            comparisons.append(r)
        else:
            comparisons.append({"property": item["property"], "verdict": "unverified",
                                "computed": item["value"], "reference": None,
                                "unit": item.get("unit", ""), "reason": "no sourced reference"})
    return report.build(str(cwd), title=args.get("title"), structure=st,
                        extracted=extracted, comparisons=comparisons,
                        notes=args.get("notes"), missing=auto_missing)


# -------------------------------------------------------------- diagnosis --
ERRORS_PATH = Path(__file__).resolve().parent / "errors.json"

# Files worth scanning, in the order a human would read them.
DIAG_FILES = ("vasp.log", "OUTCAR", "OSZICAR", "run.log", "stdout.log", "slurm.out")

_CONVERGED = (
    ("reached required accuracy", "relaxation converged (forces below EDIFFG)"),
    ("aborting loop because EDIFF is reached", "electronic loop converged (EDIFF reached)"),
    ("General timing and accounting", "VASP reached its normal end-of-run banner"),
)


def _error_table():
    """Load the machine-readable failure signatures (server/errors.json)."""
    try:
        return json.loads(ERRORS_PATH.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, ValueError):
        return []


def _scan(text, entries):
    """Match every signature against the text; report the first matching line."""
    hits = []
    for entry in entries:
        try:
            m = re.search(entry["pattern"], text, re.IGNORECASE)
        except re.error:
            continue
        if not m:
            continue
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.end())
        line = text[start:end if end != -1 else len(text)].strip()
        hits.append({
            "id": entry.get("id"),
            "severity": entry.get("severity"),
            "category": entry.get("category"),
            "matched": line[:200],
            "meaning": entry.get("meaning"),
            "fix": entry.get("fix"),
            **({"qvasp": entry["qvasp"]} if entry.get("qvasp") else {}),
        })
    order = {"fatal": 0, "warning-then-fatal": 1, "warning": 2}
    hits.sort(key=lambda h: order.get(h["severity"], 3))
    return hits


def _convergence(text):
    seen = [msg for marker, msg in _CONVERGED if marker in text]
    steps = len(re.findall(r"^\s*(?:DAV|RMM|CG|DIA):\s*\d+", text, re.MULTILINE))
    ionic = len(re.findall(r"^\s*\d+\s+F=", text, re.MULTILINE))
    return {"markers": seen, "electronic_steps": steps, "ionic_steps": ionic,
            "converged": bool(seen)}


def tool_diagnose_log(args):
    """Explain a failed (or suspicious) VASP/qvasp run from its log files."""
    cwd = safe_cwd(args.get("cwd", "."))
    named = args.get("files") or list(DIAG_FILES)
    texts, scanned, missing = {}, [], []
    for name in named:
        p = cwd / name
        if p.is_file():
            texts[name] = p.read_text(errors="replace")
            scanned.append(name)
        else:
            missing.append(name)
    # A pasted error message is a first-class input: the common case is
    # "here is the line VASP died on, what do I do", with no run directory at
    # all. Only fail when there is neither a log file nor text to look at.
    pasted = str(args.get("text") or "")
    if not texts and not pasted:
        return err(f"no log file found in {cwd} (looked for {', '.join(named)}); "
                   f"pass files=[...] or the error text as 'text'")
    merged = "\n".join(texts.values())
    entries = _error_table()
    hits = _scan(merged, entries) if texts else []
    conv = _convergence(merged) if texts else {"markers": [], "electronic_steps": 0,
                                               "ionic_steps": 0, "converged": False}
    # With text only there is no run, so a "converged"/"no-marker" verdict would
    # be a statement about nothing; report only what the text itself proves.
    verdict = ("failed" if any(h["severity"] == "fatal" for h in hits)
               else "converged" if conv["converged"]
               else "no-marker" if texts else "unknown")
    out = {"cwd": str(cwd), "files": scanned, "missing": missing,
           "verdict": verdict, "convergence": conv,
           "findings": hits, "table_entries": len(entries)}
    if pasted:
        out["from_text"] = _scan(pasted, entries)
        if not texts:
            # nothing was scanned on disk, so the text decides the verdict
            out["verdict"] = ("failed" if any(h["severity"] == "fatal" for h in out["from_text"])
                              else "warning" if out["from_text"] else "no-match")
            out["note"] = ("diagnosed from the pasted text only; no log file was read. "
                           "Pass cwd=<run directory> to also check its files.")
    return out


# ------------------------------------------------------------- aux backends --
# qvasp is the reference implementation here; these bridges exist so the agent
# can cross-check a number with the tool a given user already has installed.
AUX_CANDIDATES = {
    "vaspkit": ("vaspkit", ["/public/software/vaspkit.1.12/bin/vaspkit",
                            "/public/software/vaspkit/bin/vaspkit",
                            "/opt/vaspkit/bin/vaspkit"]),
    "p4vasp": ("p4vasp", ["/usr/local/bin/p4vasp", "/usr/bin/p4vasp"]),
    "bader": ("bader", ["USERDefine/TooLs/bader.x", "USERDefine/TooLs/bader"]),
    "phonopy": ("phonopy", ["~/.local/bin/phonopy"]),
    "phonopy-init": ("phonopy-init", ["~/.local/bin/phonopy-init"]),
}


_aux_cache = {}


def _aux_fallbacks(spec):
    """Expand the fallback list: ~ home, and paths relative to the qvasp install.

    qvasp ships its companion binaries under <qvasp-dir>/USERDefine/TooLs, so a
    relative entry is resolved next to the configured QVASP_BIN as well as in the
    current directory. Nothing here is required — a miss just means "not installed"."""
    out = []
    qdir = None
    binpath = shutil.which(QVASP_BIN) or QVASP_BIN
    if binpath and os.path.sep in binpath:
        qdir = Path(binpath).resolve().parent
    for cand in spec:
        if cand.startswith("~"):
            out.append(os.path.expanduser(cand))
        elif os.path.isabs(cand):
            out.append(cand)
        else:
            if qdir:
                out.append(str(qdir / cand))
            out.append(cand)
    return out


def aux_tool(name):
    """Resolve an auxiliary VASP tool by name, falling back to known paths.

    Same discipline as scheduler_tool(): the cache is keyed by *name* so that
    asking for a second tool cannot return the first one's path."""
    if name in _aux_cache:
        return _aux_cache[name]
    exe, fallbacks = AUX_CANDIDATES.get(name, (name, []))
    found = shutil.which(exe)
    if not found:
        for cand in _aux_fallbacks(fallbacks):
            if Path(cand).is_file() and os.access(cand, os.X_OK):
                found = cand
                break
    _aux_cache[name] = found
    return found


def tool_aux_run(args):
    """Run a companion VASP tool (vaspkit, p4vasp, bader, phonopy) in a directory."""
    name = str(args.get("tool", "")).strip()
    if name not in AUX_CANDIDATES:
        return err(f"aux_run needs 'tool' one of {sorted(AUX_CANDIDATES)}")
    exe = aux_tool(name)
    if not exe:
        return err(f"{name} is not installed here; looked for {name} on PATH and in "
                   f"{AUX_CANDIDATES[name][1]}")
    cwd = safe_cwd(args.get("cwd", "."))
    argv = [exe] + [str(a) for a in (args.get("args") or [])]
    before = {p.name for p in cwd.iterdir() if p.is_file()}
    stdin = "\n".join(args.get("stdin", [])) + ("\n" if args.get("stdin") else "")
    try:
        proc = subprocess.run(argv, cwd=str(cwd), input=stdin, capture_output=True,
                              text=True, timeout=args.get("timeout_s", 300))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return err(f"{name} could not be run: {exc}")
    out = (proc.stdout or "") + (proc.stderr or "")
    after = {p.name for p in cwd.iterdir() if p.is_file()}
    return {"tool": name, "exe": exe, "exit_code": proc.returncode,
            "cwd": str(cwd), "new_files": sorted(after - before),
            "stdout_tail": "\n".join(out.splitlines()[-50:])}


def tool_aux_list(args):
    """Report which companion tools are available on this machine."""
    return {"backends": {n: aux_tool(n) for n in sorted(AUX_CANDIDATES)}}


def err(msg):
    return {"error": msg}


TOOLS = {
    "qvasp_run": {"fn": run_qvasp, "desc": "Run one qvasp subcommand in a directory",
                  "schema": {"type": "object", "properties": {
                      "command": {"type": "string"}, "cwd": {"type": "string"},
                      "stdin": {"type": "array", "items": {"type": "string"}},
                      "timeout_s": {"type": "number"}}, "required": ["command"]}},
    "qvasp_help": {"fn": tool_help, "desc": "List qvasp commands or grep the help",
                   "schema": {"type": "object", "properties": {"topic": {"type": "string"}}}},
    "workflow_plan": {"fn": tool_plan, "desc": "Expand a workflow template into stages",
                      "schema": {"type": "object", "properties": {
                          "workflow": {"type": "string"}, "system": {"type": "string"},
                          "strategy": {"type": "string"}}, "required": ["workflow"]}},
    "workflow_run": {"fn": tool_workflow_run, "desc": "Execute the next ready workflow stage",
                     "schema": {"type": "object", "properties": {
                         "workflow": {"type": "string"}, "system": {"type": "string"},
                         "strategy": {"type": "string"}},
                         "required": ["workflow"]}},
    "workflow_status": {"fn": tool_status, "desc": "Show workflow stage/job state",
                        "schema": {"type": "object", "properties": {"system": {"type": "string"}}}},
    "workflow_resume": {"fn": tool_resume, "desc": "Continue a workflow after a job finished",
                        "schema": {"type": "object", "properties": {
                            "workflow": {"type": "string"}, "system": {"type": "string"},
                            "strategy": {"type": "string"}},
                            "required": ["workflow"]}},
    "workflow_check": {"fn": tool_check,
                       "desc": "Static check of a workflow template (prototypes, commands, gates)",
                       "schema": {"type": "object", "properties": {
                           "workflow": {"type": "string"}}}},
    "structure_check": {"fn": tool_structure_check,
                        "desc": "Symmetry, coordination, bond lengths and vacuum of a POSCAR",
                        "schema": {"type": "object", "properties": {
                            "cwd": {"type": "string"}, "file": {"type": "string"},
                            "symprec": {"type": "number"}}}},
    "result_extract": {"fn": tool_result_extract,
                       "desc": "Parse a qvasp/VASP output into typed values",
                       "schema": {"type": "object", "properties": {
                           "cwd": {"type": "string"}, "file": {"type": "string"},
                           "kind": {"type": "string", "enum": [
                               "band_gap", "dos_at_ef", "phonon_min", "mae",
                               "thermo", "rdf_first_peak"]}},
                           "required": ["file", "kind"]}},
    "result_compare": {"fn": tool_result_compare,
                       "desc": "Compare a computed value with sourced references",
                       "schema": {"type": "object", "properties": {
                           "property": {"type": "string"}, "value": {"type": "number"},
                           "unit": {"type": "string"}, "formula": {"type": "string"},
                           "phase": {"type": "string"}, "method": {"type": "string"}},
                           "required": ["property", "value", "unit"]}},
    "reference_lookup": {"fn": tool_reference_lookup,
                         "desc": "Search the bundled reference library",
                         "schema": {"type": "object", "properties": {
                             "property": {"type": "string"}, "formula": {"type": "string"},
                             "phase": {"type": "string"}}, "required": ["property"]}},
    "literature_record": {"fn": tool_literature_record,
                          "desc": "Record a sourced literature value in <cwd>/refs.json",
                          "schema": {"type": "object", "properties": {
                              "cwd": {"type": "string"}, "property": {"type": "string"},
                              "value": {"type": "number"}, "unit": {"type": "string"},
                              "formula": {"type": "string"}, "phase": {"type": "string"},
                              "method": {"type": "string"}, "conditions": {"type": "string"},
                              "citation": {"type": "string"}, "doi": {"type": "string"},
                              "url": {"type": "string"}}, "required": ["property", "value"]}},
    "report_build": {"fn": tool_report_build,
                     "desc": ("Write <system>/report.md: provenance, structure check, values "
                              "(each with the file it came from), comparison with references, "
                              "verdict. With no 'extract' list it reads whatever the directory "
                              "already holds, and lists the quantities it could not find."),
                     "schema": {"type": "object", "properties": {
                         "system": {"type": "string",
                                    "description": "case directory, relative to QVASP_WORKROOT "
                                                   "(required; this is where report.md is written)"},
                         "title": {"type": "string"},
                         "poscar": {"type": "string",
                                    "description": "structure file name inside the case "
                                                   "(default POSCAR)"},
                         "auto": {"type": "boolean",
                                  "description": "scan the directory for known outputs even when "
                                                 "'extract' is given (default: on when 'extract' "
                                                 "is empty)"},
                         "extract": {"type": "array", "items": {"type": "object"},
                                     "description": "explicit values: "
                                                    '[{"file": "02-band/EIGENVAL", '
                                                    '"kind": "band_gap"}]'},
                         "compare": {"type": "array", "items": {"type": "object"},
                                     "description": "reference comparisons: "
                                                    '[{"property": "band_gap", "value": 4.12, '
                                                    '"unit": "eV", "formula": "C"}]'},
                         "notes": {"type": "array", "items": {"type": "string"}}}}},
    "diagnose_log": {"fn": tool_diagnose_log,
                     "desc": ("Explain a failed VASP/qvasp run: matched error signatures with fixes. "
                              "Give either cwd=<run directory> to read its log files, or text=<the "
                              "error message you pasted>, or both."),
                     "schema": {"type": "object", "properties": {
                         "cwd": {"type": "string",
                                 "description": "run directory to scan (relative to QVASP_WORKROOT); "
                                                "omit when you only have an error message"},
                         "files": {"type": "array", "items": {"type": "string"},
                                   "description": "log file names to read in cwd "
                                                  "(default vasp.log, OUTCAR, OSZICAR, run.log, "
                                                  "stdout.log, slurm.out)"},
                         "text": {"type": "string",
                                  "description": "error text to match, e.g. the last lines of "
                                                 "vasp.log pasted by the user"}}}},
    "aux_list": {"fn": tool_aux_list,
                 "desc": "Which companion tools (vaspkit, p4vasp, bader, phonopy) are installed",
                 "schema": {"type": "object", "properties": {}}},
    "aux_run": {"fn": tool_aux_run,
                "desc": "Run a companion VASP tool in a directory for an independent cross-check",
                "schema": {"type": "object", "properties": {
                    "tool": {"type": "string", "enum": sorted(AUX_CANDIDATES)},
                    "cwd": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "stdin": {"type": "array", "items": {"type": "string"}},
                    "timeout_s": {"type": "number"}}, "required": ["tool"]}},
    "result_parse": {"fn": tool_result_extract,
                     "desc": "Alias of result_extract",
                     "schema": {"type": "object", "properties": {
                         "cwd": {"type": "string"}, "file": {"type": "string"},
                         "kind": {"type": "string"}}, "required": ["file", "kind"]}},
}


# ---------------------------------------------------------------------- mcp --
def reply(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def handle(msg):
    method = msg.get("method")
    if method == "initialize":
        return reply(msg["id"], {"protocolVersion": "2024-11-05",
                                 "capabilities": {"tools": {}},
                                 "serverInfo": {"name": "qvasp", "version": "0.1.0"}})
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return reply(msg["id"], {"tools": [
            {"name": n, "description": t["desc"], "inputSchema": t["schema"]}
            for n, t in TOOLS.items()]})
    if method == "tools/call":
        name = msg["params"]["name"]
        args = msg["params"].get("arguments", {})
        try:
            result = TOOLS[name]["fn"](args)
        except Exception as exc:  # noqa: BLE001 - report to the caller
            result = {"error": f"{type(exc).__name__}: {exc}"}
        return reply(msg["id"], {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                                 "isError": "error" in result})
    if method in ("ping",):
        return reply(msg["id"], {})
    return {"jsonrpc": "2.0", "id": msg.get("id"),
            "error": {"code": -32601, "message": f"method {method} not found"}}


def main():
    if "--selftest" in sys.argv:
        print(json.dumps({"commands": len(qvasp_commands()),
                          "templates": [p.stem for p in TEMPLATE_DIR.glob("*.json")]}, ensure_ascii=False))
        return 0
    if "--argcheck" in sys.argv:
        # Every tool must answer a call with no arguments without leaking a traceback.
        # Models omit arguments routinely, so this is a release gate, not a nicety.
        bad = []
        for name, spec in TOOLS.items():
            try:
                out = spec["fn"]({})
            except Exception as exc:  # noqa: BLE001
                bad.append({"tool": name, "raised": f"{type(exc).__name__}: {exc}"})
                continue
            msg = json.dumps(out, ensure_ascii=False)
            leaks = [w for w in ("Traceback", "KeyError", "TypeError", "AttributeError",
                                 "NameError", "IndexError") if w in msg]
            if leaks:
                bad.append({"tool": name, "leaked": leaks, "message": msg[:200]})
        print(json.dumps({"tools": len(TOOLS), "problems": bad}, ensure_ascii=False))
        return 0 if not bad else 1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        out = handle(msg)
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


