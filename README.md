# qvasp-skill

[qvasp](https://qvasp.com) toolkit for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness):
a **skill pack** (88-command reference, standard workflows, verified pitfalls, a VASP
failure-signature table, and a survey of the wider VASP skill ecosystem) plus a
**stdio MCP server** (17 tools) that turns the model from "guessing qvasp flags" into
"running standard, checked procedures".

- Author: **Wencai Yi**, Qufu Normal University (<yiwc@qfnu.edu.cn>)
- qvasp itself: https://qvasp.com — single Fortran executable for VASP input
  preparation and post-processing, 88 commands via `qvasp -h`.

## Citation

If this pack helps your work, cite the tool it wraps:

> W. Yi, G. Tang, X. Chen, B. Yang, X. Liu, "qvasp: A flexible toolkit for VASP users in
> materials simulations", *Computer Physics Communications* **257**, 107535 (2020).
> [doi:10.1016/j.cpc.2020.107535](https://doi.org/10.1016/j.cpc.2020.107535)

The program itself is archived at [doi:10.17632/2v4m39dt3n.1](https://doi.org/10.17632/2v4m39dt3n.1).

## What it gives the model

| Layer | Tool | Purpose |
| --- | --- | --- |
| Skill | `qvasp` (skill library) | Exact 88-command reference, 10 workflow recipes, verified pitfalls — never invent a flag |
| Skill | `references/errors.md` | VASP/qvasp failure signatures: what to grep for, why it happened, what to change |
| Skill | `references/ecosystem.md` | The public VASP agent-skill landscape and the tools around qvasp, with licences, for cross-checking |
| MCP | `qvasp_run` | Run a whitelisted qvasp command with optional stdin; returns exit code, new files, stdout tail |
| MCP | `qvasp_help` | Look up any command's usage from the real binary |
| MCP | `workflow_plan` / `workflow_run` / `workflow_status` / `workflow_resume` | Drive multi-stage calculations (10 templates: band-pbe, band-hse, dos-pbe, phonon-pbe, optics-hse, elastic-pbe, relax-only, md-pbe, surface-pbe, freqfix-molecule) with gates (ionic/scf convergence, no VASP error, …) |
| MCP | `workflow_check` | Lint a workflow template against real stages/gates |
| MCP | `structure_check` | Symmetry + geometry sanity of a POSCAR (spglib space group, nearest neighbours, overlap/impossible-distance findings) |
| MCP | `result_extract` / `result_compare` | Pull numbers from OUTCAR/EIGENVAL/DOSCAR/… and compare against reference or literature values |
| MCP | `reference_lookup` / `literature_record` | Verified reference values for known materials (Raman modes, band gaps, …) |
| MCP | `report_build` | Assemble a per-calculation report from the recorded analysis |
| MCP | `diagnose_log` | Explain a failed or non-converged run: matched signature, cause, fix |

Standard procedures + gates + independent cross-checks make results reproducible and
token-cheap: the model runs one tool call instead of paging through raw VASP output.

## Install

Inside DeepSeek Harness (plugin market or CLI):

```
dsh plugin --profile <your-profile> add qvasp-skill
```

or via npm:

```
npm install -g qvasp-skill
dsh plugin --profile <your-profile> add qvasp-skill
```

or from GitHub releases:

```
dsh plugin --profile <your-profile> add github:Chaosheng-yiwc/qvasp-skill
```

On startup the bundle:

1. syncs the `qvasp` skill into your skill library (`~/.agents/skills/qvasp`,
   x-version gated — your edits survive upgrades);
2. mounts the MCP server (`mcp__qvasp__*` tools) using a python found on PATH
   (`python3`/`python`, or set `QVASP_PYTHON` explicitly).

## Configuring the MCP server

The tools talk to a real qvasp binary. Point them at yours with environment
variables (read by `server/qvasp_mcp.py`):

| Variable | Meaning | Default |
| --- | --- | --- |
| `QVASP_BIN` | qvasp executable | `qvasp` on PATH |
| `QVASP_WORKROOT` | Root directory the tools may operate under | `$HOME` |
| `QVASP_SCHEDULER` | `pbs` / `slurm` / `none` | auto |

If no python is found at boot the MCP tools are skipped with a warning and the
skill still works (set `QVASP_PYTHON` and restart the session).

## Local development

```
git clone https://github.com/Chaosheng-yiwc/qvasp-skill
cd qvasp-skill
python server/qvasp_mcp.py --selftest   # needs qvasp on PATH for full check
node --check index.js                   # syntax check
```

The server is dependency-free Python ≥ 3.8 (stdlib only) and speaks newline-delimited
JSON-RPC 2.0 over stdio (`initialize`, `tools/list`, `tools/call`, `ping`).

## License

MIT — see [LICENSE](LICENSE).
