# qvasp MCP server

Standalone Python MCP server shipped with the `qvasp-skill` plugin. It exposes
17 tools over stdio (`transport: stdio`, launched by `@deepseek-ai/dsh-mcp-client`).

## Layout

```
qvasp_mcp.py        entry point + 17 tool implementations
stages.json         10 stage prototypes (relax/scf/nscf/hybrid/dfpt/elastic/soc/md/transport/post)
workflows/*.json    10 workflow templates (band-pbe, band-hse, dos-pbe, phonon-pbe,
                    optics-hse, elastic-pbe, relax-only, md-pbe, surface-pbe, freqfix-molecule)
errors.json         22 VASP/qvasp failure signatures used by diagnose_log
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
`report_build`, `diagnose_log`, `aux_list`, `aux_run`.

## Notes for editing

- `qvasp_commands()` tolerates a missing binary: it returns `[]` with a stderr
  warning so `workflow_check` works on machines without qvasp (e.g. a laptop).
  A real run reports
  `qvasp binary not available (tried 'qvasp -h'); install qvasp or set QVASP_BIN`.
- Scheduler commands are resolved **per name** (`SCHEDULER_BIN` dict). Do not
  collapse it to a single cached value: caching the first lookup made `qstat`
  calls return the `qsub` path and marked successfully submitted stages as failed.
  `aux_tool()` follows the same rule for the companion backends.
- `ENCUT` must match across an `ICHARG = 11` stage: the nscf prototype (and the
  dos/band-hse workflow stages) carry `ENCUT: 500` so the CHGCAR from an
  `ENCUT = 500` SCF can be re-read. Mismatch gives
  `charge density could not be read from file CHGCAR for ICHARG>10`.
- The `inputs` map resolves each source against two candidates: the stage
  working directory first, then the workflow root (so `../00-relax/CONTCAR`
  works from either layout).
- Stage prototypes are loaded with `encoding="utf-8-sig"` — Windows editors
  write a BOM and plain `utf-8` would fail.
- `diagnose_log` reads `server/errors.json`; a bad regex in one entry is skipped,
  never fatal (`_scan` catches `re.error`). Keep patterns specific — a bare
  `error` would match harmless warnings. Signatures are matched case-insensitively
  against the concatenation of the scanned files, and the reported `matched` line
  is the first one that hit.
- `diagnose_log` also accepts `text=` alone. A pasted error with no run directory is
  the common case ("VASP died with this line, what now"), so it must never require a
  file: with no files and no text it returns a message telling you to pass one.
  Text-only mode reports `failed`/`warning`/`no-match` and sets `note`, because a
  convergence verdict would be a statement about a run that was never read.
- Every tool guards its required arguments before touching them; a call with `{}` must
  return a readable hint, never a raw `KeyError` (models omit arguments routinely).
- `report_build` requires `system` and refuses an empty, missing or contentless
  directory. It must not default to the workroot root: `report.build()` writes
  `report.md` **into the directory it is given**, so a silent default left a
  `report.md` one level above every case, describing nothing. It also validates
  each `extract` item (`file` + `kind`) and each `compare` item (`property` +
  `value`) before running anything.
- `parsers.discover()` walks sub-directories in **reverse name order**, so the
  last stage wins. Every workflow stage keeps an `EIGENVAL`: `00-relax` has the
  one from the relaxation on its own coarse mesh, `02-band`/`03-post` have the
  one on the band path. Walking forwards silently reported the relaxation's
  numbers (4.1241 eV, 145 k-points) as the band gap; walking backwards gives
  4.1199 eV over 210 k-points, which is the value the independent check agrees
  with. The report prints the relative path each value came from for the same
  reason: a number without its stage is not reproducible.
- `aux_run` returns the tool's own output verbatim and interprets nothing. When a
  backend is missing the answer is `null` from `aux_list` and a plain error from
  `aux_run`, so a machine without the optional backend is not a broken install.
- **Every parser in `analysis/parsers.py` must prove the file is the type it
  claims.** A parser that skips the check does not fail loudly — it returns a
  plausible number read from the wrong column, which is worse than an error.
  The guards, and why each one exists:
  - `band_gap` reads EIGENVAL only when the first k-block yields `nbands` rows
    whose third column is an occupation in `[0, 1]`. A header of three integers
    is not enough: CHGCAR opens that way too.
  - `band_gap` accepts the two-column `band.dat` only when >95% of data lines are
    exactly two columns; otherwise OUTCAR/CHGCAR/DOSCAR would be read as band
    tables.
  - `band_gap` refuses a truncated EIGENVAL (`kpts_read < nkpts`). A killed job
    leaves a valid header and a partial band list, and its "gap" looks fine.
  - Metal detection is `min(empty) < max(occupied)`, **not** fractional
    occupations: with `ISMEAR = 0, SIGMA = 0.2` a 4.12 eV gap still has
    occupations of 0.961.
  - `phonon_min` rejects the `&`-separated block layout (that is `-bandd` output)
    and requires a comment header naming the frequency axis. It also counts only
    `f < -1 cm^-1` as imaginary: the acoustic branches of a stable crystal come
    out at ~1e-5 cm^-1, and counting those reported three soft modes for diamond.
  - `dos_at_ef` parses line 6 as `EMAX EMIN NEDOS EF` (the first field is the top
    of the energy window, not an atom count) and sums the spin columns.
  - `thermo` requires at least 5 columns and a first column that is a temperature
    in `0..5000 K`; `rdf_first_peak` requires an r/g(r) header, `r` starting at 0
    and `g(r->0)` near zero.
  - Any new parser needs the same treatment plus a wrong-file test: feed it a
    real EIGENVAL, a real `band.dat` and a real OUTCAR and check that it refuses
    all three with a message naming the expected file.
