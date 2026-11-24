# qvasp MCP server

Standalone Python MCP server shipped with the `qvasp-skill` plugin. It exposes
14 tools over stdio (`transport: stdio`, launched by `@deepseek-ai/dsh-mcp-client`).

## Layout

```
qvasp_mcp.py        entry point + 14 tool implementations
stages.json         10 stage prototypes (relax/scf/nscf/hybrid/dfpt/elastic/soc/md/transport/post)
workflows/*.json    10 workflow templates (band-pbe, band-hse, dos-pbe, phonon-pbe,
                    optics-hse, elastic-pbe, relax-only, md-pbe, surface-pbe, freqfix-molecule)
analysis/           structure_check / result_extract / report_build helpers
reference/          references.json (literature values used by result_compare)
```

## Environment variables

| variable         | meaning                                             | default                  |
|------------------|-----------------------------------------------------|--------------------------|
| `QVASP_BIN`      | path to the qvasp executable                        | `qvasp` on PATH          |
| `QVASP_WORKROOT` | root all tool working directories must live under   | `/public/home/yiwc/deepseekh` |
| `QVASP_SCHEDULER`| job scheduler: `torque` or `none` (dry run)         | `torque`                 |
| `QVASP_QUEUE`    | PBS queue used by generated job scripts             | `batch`                  |
| `QVASP_PYTHON`   | python for the MCP process itself (set by host)     | —                        |

## Tools

`qvasp_run`, `qvasp_help`, `workflow_plan`, `workflow_run`, `workflow_status`,
`workflow_resume`, `workflow_check`, `structure_check`, `result_extract`,
`result_parse` (alias), `result_compare`, `reference_lookup`, `literature_record`,
`report_build`.

## Notes for editing

- `qvasp_commands()` tolerates a missing binary: it returns `[]` with a stderr
  warning so `workflow_check` works on machines without qvasp (e.g. a laptop).
  A real run reports
  `qvasp binary not available (tried 'qvasp -h'); install qvasp or set QVASP_BIN`.
- Scheduler commands are resolved **per name** (`SCHEDULER_BIN` dict). Do not
  collapse it to a single cached value: caching the first lookup made `qstat`
  calls return the `qsub` path and marked successfully submitted stages as failed.
- `ENCUT` must match across an `ICHARG = 11` stage: the nscf prototype (and the
  dos/band-hse workflow stages) carry `ENCUT: 500` so the CHGCAR from an
  `ENCUT = 500` SCF can be re-read. Mismatch gives
  `charge density could not be read from file CHGCAR for ICHARG>10`.
- The `inputs` map resolves each source against two candidates: the stage
  working directory first, then the workflow root (so `../00-relax/CONTCAR`
  works from either layout).
- Stage prototypes are loaded with `encoding="utf-8-sig"` — Windows editors
  write a BOM and plain `utf-8` would fail.
