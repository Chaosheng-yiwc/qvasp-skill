# qvasp toolkit

A skill pack for the [qvasp](https://qvasp.com/) VASP toolkit. It teaches the agent the
tool's real interface instead of letting it invent flags.

**Author:** Wencai Yi, Qufu Normal University (<yiwc@qfnu.edu.cn>).

**Citation:** W. Yi, G. Tang, X. Chen, B. Yang, X. Liu, "qvasp: A flexible toolkit for VASP
users in materials simulations", *Comput. Phys. Commun.* **257**, 107535 (2020),
[doi:10.1016/j.cpc.2020.107535](https://doi.org/10.1016/j.cpc.2020.107535); program archive
[doi:10.17632/2v4m39dt3n.1](https://doi.org/10.17632/2v4m39dt3n.1).

## What it contains

- **Skill `qvasp`** — when to use it, the rules (run in the calculation directory, never
  edit shipped examples, check `run.log`, verify one physical number), and the standard
  pipeline.
- **`references/commands.md`** — all 88 commands with arguments, required input files and
  outputs, transcribed from `qvasp -h`.
- **`references/workflows.md`** — end-to-end recipes: relax→SCF→band, DOS projections,
  phonons→thermo, optics, IR/Raman, the magnetic suite, imaginary-frequency fixing,
  thermoelectrics, MD analysis and surface energies.
- **`references/pitfalls.md`** — behaviours confirmed against real VASP data: the VBM/E_F
  energy zero of `-bandd`, the Gaussian default of `-ir`/`-raman`, the `-freqfix` amplitude
  semantics, what the acoustic sum rule can and cannot fix, moiré strain, element names for
  POTCAR, and more.
- **`references/parameters.md`** — the convergence and model decisions: ENCUT and k-mesh
  tests, smearing, functional choice (PBE / HSE / +U / dispersion), magnetism, slab and
  molecule settings, throughput knobs, and the five facts every reported number needs.
- **`references/errors.md`** — the failure-signature table: what to grep for in `vasp.log`,
  what it means, what to change, plus the triage order and the "finishes but is wrong"
  symptoms. Same table, machine-readable, drives the `diagnose_log` tool.
- **`references/ecosystem.md`** — the public VASP agent-skill landscape (the Nankai AICC
  collection, matsci-ai-skills, agent-skills, the DSH VASP periodic-table plugin), with
  licences, so the agent knows what exists before reinventing it.

## The MCP server (`server/`)

`server/qvasp_mcp.py` is a stdio JSON-RPC server with 17 tools. It runs qvasp and VASP on
the cluster so the agent does not have to hand-assemble command lines.

**Execution and workflows.** `qvasp_run` (88-command whitelist, argv only, `cwd` must stay
under `QVASP_WORKROOT`), `qvasp_help`, `workflow_plan`, `workflow_run`, `workflow_status`,
`workflow_resume`, `workflow_check`. Ten templates ship in `server/workflows/`
(`relax-only band-pbe band-hse dos-pbe phonon-pbe optics-hse elastic-pbe md-pbe surface-pbe
freqfix-molecule`); each is a DAG of stages built from the ten prototypes in
`server/stages.json` (`relax scf nscf hybrid dfpt elastic soc md transport post`). A stage
inherits its prototype's INCAR overrides and overrides only what differs; overrides
**replace** the matching tag rather than appending a second one. Every stage carries a gate
(`ionic_converged`, `scf_converged`, `file_present`, `no_error`, `frequencies_present`)
evaluated when the job ends. A stage whose step is not a qvasp command (phonopy forces,
`phonopy --fc-symmetry`) is marked `"kind": "manual"`: the engine prepares the directory,
records `state="manual"` with the note, and waits for the user to run it and call
`workflow_resume`; `workflow_check` rejects a manual stage without both a note and a gate.

**Diagnosis.** `diagnose_log` reads the tail of `vasp.log` / `OUTCAR` / `OSZICAR` /
`run.log`, matches it against `server/errors.json` (22 signatures), sorts fatal findings
first, reports the convergence markers and step counts, and returns the cause and the fix
per finding. Passing an unrecognised log returns `verdict: "no-marker"` rather than a guess.

`text=` triages a pasted error without any run directory — the usual "VASP died with this
line, what now" case. That mode reports `verdict: "failed"` / `"warning"` / `"no-match"`
from the text alone and says so in a `note`, because with no run on disk there is nothing
to say about convergence. Give both `cwd` and `text` and you get both reports.

**Analysis.** `structure_check` (lattice, volume, density, spglib symmetry, nearest-neighbour
distances, unambiguous defect flags — deliberately no coordination number, which is
unreliable in ionic crystals), `result_extract` (band gap, DOS at E_F, phonon minimum, MAE,
thermodynamics, RDF first peak — returns `unsupported` instead of guessing when a file does
not parse), `result_compare`, `reference_lookup`, `literature_record`, `report_build`
(writes a five-section `report.md`).

`report_build` needs only the case directory: with no `extract` list it looks for the known
outputs itself, one level deep, **last stage first**, and prints the relative path behind
every number. The order matters — each stage of a workflow keeps its own `EIGENVAL`, so
reading `00-relax/EIGENVAL` (relaxation, its own coarse mesh) instead of
`03-post/EIGENVAL` (band path) reports 4.1241 eV over 145 k-points where the answer is
4.1199 eV over 210. Quantities it could not find are listed with the file names it tried,
so a missing number is visibly missing rather than absent from the table.

`result_extract` accepts a file only after proving it is the type the requested value
needs: an EIGENVAL is recognised by `nbands` rows of `(band, energy, occupation)` in its
first k-block, a two-column `band.dat` must be >95% two-column lines, and a truncated
EIGENVAL is refused outright because a killed run leaves a header that still parses. A
file of the wrong type gets `unsupported` with the expected file named, never a number
read from the wrong column. Metal detection uses `min(empty) < max(occupied)` rather than
fractional occupations, since smearing leaves a 4 eV gap with occupations near 0.96.

`result_compare` classifies a computed value as `consistent`, `systematic`, `discrepant` or
`unverified` against `server/reference/references.json`. Every reference entry must carry a
DOI or URL, a retrieval date and its method conditions; a value with no source is reported
as `unverified` and must not be quoted as agreeing with experiment. `literature_record`
refuses an entry without a DOI or URL.

## Installation

The bundle is a host plugin: `index.js` syncs the bundled skill into `~/.agents/skills/qvasp`
and mounts the MCP entry with runtime-resolved paths. The sync overwrites the installed copy
when `x-version` goes up, and also when the packaged files changed while the version did not
(a content hash is recorded in `~/.agents/skills/.qvasp.skill-hash`), so a forgotten version
bump cannot leave stale reference files installed. If you edit the installed copy yourself,
your edits are kept until the next version bump. Install it with the plugin manager or
`dsh plugin --profile <profile> add qvasp-skill`, then start a new session; `qvasp` appears
in the skill catalog and the `mcp__qvasp__*` tools appear with it.

Nothing in the patch is machine-specific: the python interpreter and the path to
`server/qvasp_mcp.py` are computed at boot from the package location, which is why the
MCP entry is created from `apply()` instead of being written into `cordis.patch.yml`.
The interpreter search is `QVASP_PYTHON` → `python`/`python3` on PATH → the usual
conda and system install directories, because python is often installed on a machine
without being reachable from the PATH a GUI application inherits.

## Scope and limits

- The skill itself executes nothing: running qvasp uses the agent's shell or SSH tools.
  The MCP server needs `QVASP_BIN`, `QVASP_WORKROOT` and (on a cluster) `QVASP_SCHEDULER`;
  without them it still answers analysis and lint tools, and `qvasp_run` says the binary is
  unavailable instead of failing with a stack trace.
- The command table reflects qvasp v3.01 (2026-11-23 build). Regenerate it with
  `tools/gen_commands.py <qvasp-binary>` after an upgrade and review the diff.
- Cluster paths, scheduler names and POTCAR library entries are environment-specific and
  are kept out of the skill body on purpose. The MCP server reads them from the
  environment, with the cluster values as defaults.
- `diagnose_log` matches signatures, it does not prove a cause. Two findings at once are
  normal (a bad structure produces the hermitian warning and then the solver abort); fix
  the structurally-certain one first.
- `references/ecosystem.md` is a survey, not a vendored copy. Several of the projects it
  lists are non-commercial or unlicensed; nothing from them is redistributed here.
- `band-hse`'s `opt` strategy needs VASP ≥ 6.3 (KPOINTS_OPT). It was driven end to end
  with real PBS jobs: `00-relax` and `01-scf` completed, and the `KPOINTS_OPT` mechanism
  itself was validated with a PBE run (mesh SCF, band batches, `-bandd` output matching
  the `KPOINTS_OPT` EIGENVAL). The final hybrid numbers could not be produced on the
  college cluster: its `vasp_std` 6.5.1 segfaults at the first exact-exchange step
  regardless of ranks/KPAR/`KPOINTS_OPT` (6-job isolation matrix, 2026-11-24) — a
  cluster binary limitation, not a template bug. `NCORE = 1` is mandatory with
  `KPOINTS_OPT` + hybrid (VASP refuses anything else); the templates now set it.
- Ten templates, all linted; `band-pbe`, `relax-only`, `dos-pbe`, `phonon-pbe` and
  `elastic-pbe` have also been run end to end with real VASP 6.5.1 jobs (band gap 4.1199 eV
  cross-checked against EIGENVAL, diamond phonon Γ optical mode 1299.9 cm⁻¹, diamond
  B = 434.6 GPa against a PBE reference of ~433). `md-pbe`, `surface-pbe` and
  `freqfix-molecule` have been dry-run only; `band-hse` and `optics-hse` reach the hybrid
  stage, which the cluster binary cannot run (see above).


