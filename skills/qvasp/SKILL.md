---
x-version: 8
name: qvasp
description: Use when a task involves qvasp or VASP input preparation and post-processing — INCAR/KPOINTS/POTCAR templates, structure editing (supercell, surface, moiré, defects), band/DOS/charge/phonon/optical/magnetic/thermo post-processing, MD analysis, fixing imaginary frequencies, or diagnosing a VASP crash / non-converged run. Provides the exact 88-command reference, the standard workflows, the known pitfalls, and a failure-signature table so commands, flags and error fixes are never guessed.
whenToUse: The user mentions qvasp, VASP post-processing (band/DOS/POTCAR/KPOINTS), phonons, Bader charges, work function, optical/IR/Raman spectra, MD trajectory analysis, a VASP error message or a job that failed to converge, or asks to compute/verify something with VASP on a cluster.
---

# qvasp

`qvasp` is a single Fortran executable that writes VASP inputs, computes post-processing
data from VASP outputs, and converts between structure formats. It has 88 commands listed by `qvasp -h`.
Never invent a flag: look it up in `references/commands.md` (generated from `qvasp -h`)
or ask `qvasp -h`.

Implemented and maintained by **Wencai Yi**, Qufu Normal University. Cite it as:

> W. Yi, G. Tang, X. Chen, B. Yang, X. Liu, "qvasp: A flexible toolkit for VASP users in
> materials simulations", *Comput. Phys. Commun.* **257**, 107535 (2020),
> [doi:10.1016/j.cpc.2020.107535](https://doi.org/10.1016/j.cpc.2020.107535)

## Rules

1. **Run in the working directory of the calculation.** qvasp reads `OUTCAR`, `DOSCAR`,
   `EIGENVAL`, `CHGCAR`, `LOCPOT`, `vasprun.xml`, `XDATCAR`, `FORCE_CONSTANTS`, … from
   the current directory and writes new files there. Pass the directory explicitly when
   the shell is not already in it.
2. **Never modify an original example/calculation folder.** Copy it to a scratch
   directory first; qvasp overwrites `POSCAR`, `KPOINTS`, `INCAR` and writes many outputs.
3. **Read `run.log` after every example-level run.** A command can exit 0 while printing
   `[qvasp ERROR]` or a warning on stdout.
4. **Check the prerequisites before running.** Template commands need nothing; post-processing
   commands need the specific VASP output listed in `references/commands.md`; spectrum
   commands need a DFPT/finite-displacement run (`IBRION=5..8`, `LEPSILON` for IR).
5. **Prefer the physical check.** After post-processing, confirm one physical number
   (gap, Fermi level, peak position, ASR drift, total charge) against the raw VASP file or
   a reference value; do not trust the tool blindly.
6. **Long jobs go through the scheduler.** Use `qsub`/`sbatch`; never run VASP in a
   foreground shell that can time out.
7. **A tag VASP does not know is not an error.** It is parsed, ignored and never
   mentioned again, so a misspelled `KSPACING` or an invented `EXT_PRES` looks exactly
   like a setting that was applied. Read the unknown-tag warnings in
   `references/errors.md` and let `preflight` check the files.

## Typical pipeline

```
# 1. inputs
qvasp -relax | -scf | -band | -dos | -freq | ...     # writes INCAR
qvasp -k 0.03                                        # KPOINTS by k-density
qvasp -pbe Si O                                      # POTCAR from the local PAW_PBE library
# 2. run VASP (qsub)
# 3. post-process in the finished folder
qvasp -e ; qvasp -bandd ; qvasp -dosd ; qvasp -phonond ; qvasp -thermo ...
```

Detailed recipes for band/DOS, phonons, optics, magnetic, thermo and MD are in
`references/workflows.md`. Known traps are in `references/pitfalls.md`.

## If the `qvasp-mcp` server is connected

Prefer the tools over hand-written command lines — they enforce the same rules and
record what was run.

| need | tool |
|---|---|
| run one qvasp command | `qvasp_run` (whitelisted commands, `cwd` confined to the work root) |
| look up a flag | `qvasp_help` |
| a full relax → band / DOS / phonon / optics / elastic / MD / surface job | `workflow_plan`, `workflow_run`, `workflow_status`, `workflow_resume` |
| lint a workflow template | `workflow_check` |
| is this structure sane | `structure_check` (symmetry, density, nearest neighbours, overlaps) |
| pull a number out of an output | `result_extract` (`band_gap`, `dos_at_ef`, `phonon_min`, `mae`, `thermo`, `rdf_first_peak`) |
| is that number right | `result_compare` + `reference_lookup` — `consistent` / `systematic` / `discrepant` / `unverified` |
| cite a value you found | `literature_record` (refuses an entry without a DOI or URL) |
| write the report | `report_build` with `system=<case dir>` → `report.md` there; it reads the last stage's files itself and names the file behind every number |
| the job crashed or never converged | `diagnose_log` — matches the log against a table of VASP/qvasp failure signatures and returns the cause plus the fix |
| check the inputs before spending walltime on them | `preflight` — species/POTCAR order, `ENCUT` vs `ENMAX`, `MAGMOM`/`LDAU` array lengths, tags VASP ignores, smearing vs the task, missing `CHGCAR`. It answers from the files alone, so run it before `qsub`; `workflow_run` calls it on every calculation stage and refuses to submit on an error |

`workflow_run` is resumable and returns `{"waiting": true}` while a job is queued. Call it
again (or `workflow_resume`) after the job ends; it evaluates the stage gate then.

A stage that comes back with `"manual": "<instruction>"` is not a qvasp command — phonopy
is the usual case. Do what the note says, then call `workflow_resume`; the stage's gate
decides when it is finished.

A value that comes back `unverified` has no sourced reference behind it. Never present it
as agreeing with experiment — report it as this calculation's own result.

## When a VASP job fails

Read the tail of `vasp.log` (not the first warning you see), then check it against
`references/errors.md` — or call `diagnose_log`, which matches the same table and returns
the cause and the fix. Paste the failing line as `text=` when there is no run directory to
scan; pass `cwd=` as well when there is, and you get the file report too. The two facts
that decide most cases:

- A job that exits 0 **without** `reached required accuracy` (relaxation) or without
  `aborting loop because EDIFF is reached` (static) has not converged.
- For a relaxation that ran out of `NSW`, the criterion to loosen is `EDIFFG` (force),
  not `EDIFF` (energy).

Change one thing at a time and write down what you changed.

## Where the details are

- `references/commands.md` — all 88 commands with arguments, required inputs and outputs.
- `references/workflows.md` — end-to-end recipes (relax→band, phonon→thermo, optics, freqfix).
- `references/pitfalls.md` — verified caveats (energy zero points, line-shape defaults, ASR, etc.).
- `references/parameters.md` — choosing ENCUT, k-mesh, smearing, functional, +U, dispersion, magnetism, slab/molecule settings, and what to record with every reported number.
- `references/errors.md` — VASP/qvasp failure signatures: what to grep for, what it means, what to do.
- `references/ecosystem.md` — the public VASP agent-skill landscape, with licences, for
  cross-checking and for knowing what else exists.

## Environment

- `qvasp` lives on the Linux cluster; run it over SSH where VASP is installed.
- VASP templates assume the cluster's `vasp_std`; POTCAR comes from the qvasp POTCAR library
  (`qvasp -pbe/-lda/-pw91 ELE ...`), so element names must match the library entries
  (for example `Sr_sv`, `Ti_pv`, `O`).


