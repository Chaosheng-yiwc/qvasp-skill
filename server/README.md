# qvasp MCP server

A stdio JSON-RPC server that runs qvasp and VASP on a cluster and analyses the results.
It has no dependencies beyond the Python standard library plus `numpy`/`spglib` for the
structure check.

## Registration

Register it as a DSH MCP server (see the `dsh-doc` skill for the patch syntax). The
server speaks newline-delimited JSON-RPC on stdin/stdout.

```yaml
- id: mcp-qvasp
  name: "@deepseek-ai/dsh-mcp-client"
  config:
    serverName: qvasp
    transport: stdio
    command: python3
    args: ["/path/to/qvasp-mcp/qvasp_mcp.py"]
    env:
      QVASP_BIN: /path/to/qvasp
      QVASP_WORKROOT: /path/to/scratch
```

## Environment

| variable | default | meaning |
|---|---|---|
| `QVASP_BIN` | `qvasp` | the executable to run |
| `QVASP_WORKROOT` | `$HOME` | every `cwd` argument must resolve inside this tree |
| `QVASP_SCHEDULER` | `pbs` | `pbs`, `slurm` or `none` (dry run) |
| `QVASP_QUEUE` | `batch` | PBS queue name |
| `QVASP_ENV_SOURCES` | Intel + IMPI env files | shell lines prepended to the job script |
| `QVASP_VASP_CMD` | `vasp_std` | VASP binary inside the job script |

`QVASP_SCHEDULER=none` writes the inputs and submits nothing: a stage whose upstream
product does not exist yet is recorded as `prepared` with a note, and a post-processing
stage is skipped rather than run on an empty directory.

## Tools

Execution: `qvasp_run`, `qvasp_help`, `workflow_plan`, `workflow_run`, `workflow_status`,
`workflow_resume`, `workflow_check`.
Analysis: `structure_check`, `result_extract`, `result_parse`, `result_compare`,
`reference_lookup`, `literature_record`, `report_build`.

Self-test:

```bash
python3 qvasp_mcp.py --selftest      # {"commands": 88, "templates": [...]}
```

## Layout

```
qvasp_mcp.py            server, tool table, workflow engine
stages.json             stage prototypes (INCAR overrides, gates, produced files)
workflows/*.json        workflow templates (DAGs of stages)
analysis/               structure check, result parsers, reference comparison, report
reference/references.json   sourced literature values with DOI/URL and retrieval date
```

## Workflow model

A template is a list of stages. Each stage names a `prototype` from `stages.json` and
overrides only what differs; a stage with no `prototype` is self-contained. Stages are
executed in order, each in its own directory under the system root:

```
<system>/00-relax/   <system>/01-scf/   <system>/02-band/   ...
<system>/workflow.json
```

`inputs` copies files from an earlier stage into the stage directory (`{"../01-scf/CONTCAR":
"POSCAR"}`), or takes a file the user left at the system root (`{"POSCAR-slab": "POSCAR"}`).
Both spellings are tried — resolved against the stage directory first, then against the
system root — so a template does not have to know which convention the other one used.
`POTCAR` is never copied through `inputs` — it is licensed and user-supplied, so every calc
stage takes it from the system root.

A stage may set `"kind": "manual"` when the step is not a qvasp command (phonopy forces,
`phonopy --fc-symmetry`). The engine prepares the directory, records `state="manual"` with
the stage's note, and returns; run the step by hand and call `workflow_resume`. Such a
stage must carry both a `note` and a `gate`, and `workflow_check` rejects one that does not —
without a gate there is no way to tell that the manual step finished.

`workflow_run` is resumable. One call advances the workflow as far as it can: it submits
the next stage and returns, or returns `{"waiting": true}` while that job is queued, or
evaluates the gate once the job is gone and continues. State is in `workflow.json`, so a
new process can pick up where the last one stopped (`workflow_resume`).

`apply_overrides` **replaces** any tag the qvasp template already wrote instead of
appending a second line. VASP keeps the last duplicate and warns, so appending would make
the effective value depend on parse order.

### ENCUT must match across an `ICHARG = 11` stage

VASP rebuilds its FFT grid from `ENCUT`. A non-self-consistent stage that reads a charge
density written by a different cutoff gets a grid mismatch and refuses the file:

```
WARNING: dimensions on CHGCAR file are different
ERROR: charge density could not be read from file CHGCAR for ICHARG>10
---->  I REFUSE TO CONTINUE WITH THIS SICK JOB ... BYE!!! <----
```

The file is intact; the cutoff is the problem. The `scf` prototype raises `ENCUT` to 500,
so every stage that sets `ICHARG = 11` (`nscf` in `stages.json`, and the `ICHARG = 11`
stages of `dos-pbe` and the `opt`/`twostep` strategies of `band-hse`) pins `ENCUT` to the
same value. If you change the SCF cutoff, change the pair together.

### Scheduler commands are resolved per name

`scheduler_tool()` caches one absolute path per command name. An earlier version cached a
single path and returned it for every name, so `qstat` resolved to the `qsub` binary and the
job-state check ran `qsub vasp.pbs` — `qstat: Unknown queue destination vasp.pbs`, which
surfaced as `submit failed` on a stage that had in fact been submitted correctly.

## Analysis rules

- `structure_check` reports lattice, volume, density, spglib symmetry, per-atom nearest
  neighbour distances and only unambiguous defects (atoms closer than 0.6 Å, atoms with no
  neighbour within 3 Å). It deliberately does **not** report coordination numbers: covalent
  radius cutoffs fail in ionic crystals (a 5-atom SrTiO₃ cell would give Sr = 26).
- `result_extract` returns `unsupported` when a file does not parse, instead of guessing.
- `result_compare` classifies against `reference/references.json` as `consistent`,
  `systematic` (within the expected functional bias), `discrepant` or `unverified`. An
  entry without a DOI/URL or with mismatched units is always `unverified`.
- `report_build` writes `report.md` with a fixed closing sentence: values marked
  `unverified` have no sourced reference and must not be quoted as agreeing with experiment.
