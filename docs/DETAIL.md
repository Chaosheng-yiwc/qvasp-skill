# qvasp toolkit

A skill pack for the [qvasp](https://qvasp.com/) VASP toolkit. It teaches the agent the
tool's real interface instead of letting it invent flags.

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

## The MCP server (`server/`)

`server/qvasp_mcp.py` is a stdio JSON-RPC server with 13 tools. It runs qvasp and VASP on
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

**Analysis.** `structure_check` (lattice, volume, density, spglib symmetry, nearest-neighbour
distances, unambiguous defect flags — deliberately no coordination number, which is
unreliable in ionic crystals), `result_extract` (band gap, DOS at E_F, phonon minimum, MAE,
thermodynamics, RDF first peak — returns `unsupported` instead of guessing when a file does
not parse), `result_compare`, `reference_lookup`, `literature_record`, `report_build`
(writes a five-section `report.md`).

`result_compare` classifies a computed value as `consistent`, `systematic`, `discrepant` or
`unverified` against `server/reference/references.json`. Every reference entry must carry a
DOI or URL, a retrieval date and its method conditions; a value with no source is reported
as `unverified` and must not be quoted as agreeing with experiment. `literature_record`
refuses an entry without a DOI or URL.

## Installation

The bundle is configuration-only: its patch mounts a second
`@deepseek-ai/dsh-skill-filesystem` provider that scans only this pack's `skills/`
directory. Install it with the plugin manager (local directory), then start a new session;
`qvasp` appears in the skill catalog.

The patch contains the absolute path of `skills/` because the skill provider resolves
`customSkillDirs` against the process working directory. If the pack is moved, update that
one line (or reinstall from the new location).

## Scope and limits

- The skill itself executes nothing: running qvasp uses the agent's shell or SSH tools.
  The MCP server is the structured layer and has to be registered separately (see
  `server/README.md`), because it needs cluster-specific environment variables
  (`QVASP_BIN`, `QVASP_WORKROOT`, `QVASP_SCHEDULER`).
- The command table reflects qvasp v3.01 (2026-11-23 build). Regenerate it with
  `tools/gen_commands.py <qvasp-binary>` after an upgrade and review the diff.
- Cluster paths, scheduler names and POTCAR library entries are environment-specific and
  are kept out of the skill body on purpose. The MCP server reads them from the
  environment, with the cluster values as defaults.
- `band-hse`'s `opt` strategy needs VASP ≥ 6.3 (KPOINTS_OPT) and has not been run
  end-to-end on real VASP yet; `oneshot` and `twostep` do not depend on it.
- Of the ten templates, `band-pbe`, `relax-only`, `md-pbe`, `surface-pbe` and
  `freqfix-molecule` have been through a dry run; `band-pbe` and `relax-only` have also
  submitted real jobs. `dos-pbe`, `phonon-pbe`, `optics-hse` and `elastic-pbe` are linted
  but not yet run end to end.


