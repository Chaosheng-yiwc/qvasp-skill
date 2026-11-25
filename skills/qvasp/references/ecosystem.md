# The VASP agent-skill ecosystem

qvasp's own reference is authoritative for qvasp. For everything around qvasp —
choice of functional, GW, NEB, machine-learned potentials, visualisation — these
public projects are worth knowing. They are listed, not vendored: each keeps its
own licence and its own update cycle, so read them at the source.

Check the licence before reusing text. Several are **non-commercial only**, which
is incompatible with copying their prose into an MIT package. When in doubt, cite
the repository and link to it instead of copying.

## Dedicated VASP skills

| project | licence | what it is good for |
| --- | --- | --- |
| [JCLiuGroup/AI-Computational-Chemist](https://github.com/JCLiuGroup/AI-Computational-Chemist) (JCLiu Group, Nankai University) | CC BY-NC 4.0 (non-commercial) | The largest public collection: 16 tool skills (`vasp`, `vaspkit`, `cp2k`, `gaussian`, `lammps`, `gromacs`, `deepmd`, `mlp`, `lobster`, `catmap`, `multiwfn`, `ovito`, `phonopy`, `structure-prep`, `hpc-submit`, `report`), 4 orchestration procedures, and a 21-document knowledge library on bonding analysis, electrochemistry, electronic structure and surface thermodynamics. The `tools/vasp/references/errors.md` table and the `u-values-magmom` reference are the most useful parts to read alongside this pack. **Non-commercial licence — do not copy its text into an MIT bundle.** |
| [Hongyu-yu/matsci-ai-skills](https://github.com/Hongyu-yu/matsci-ai-skills) | MIT | Compact skills for VASP input generation and parameter choice; MIT, so the ideas (not the prose) can be reused freely. |
| [aimat-lab/agent-skills](https://github.com/aimat-lab/agent-skills) | unspecified | Wide-but-shallow coverage across ASE, VASP, LAMMPS and PyTorch workflows. Useful as a checklist of what an agent might be asked to do; check the licence before reuse. |
| [bowenphys/dsh-vasp-periodic-table](https://github.com/bowenphys/dsh-vasp-periodic-table) | MIT | A DeepSeek Harness plugin exposing the VASP periodic table (PAW potentials, `ZVAL`, `ENMAX`, `MAGMOM`, POTCAR snippets). Complements `qvasp -pbe/-lda/-pw91` when you need the numeric parameters rather than the POTCAR file. |

## MCP servers and agent tooling for VASP

| project | licence | what it is good for |
| --- | --- | --- |
| [NabKh/vasp-mcp](https://github.com/NabKh/vasp-mcp) | MIT | A read-only MCP server that lints VASP inputs before submission and summarises a finished run (convergence, energies, forces, per-spin band gaps, crash causes). Narrower than this pack and read-only, which makes it a good independent second opinion on the diagnosis. |
| [hkqai/MatClaw](https://github.com/hkqai/MatClaw) | AGPL-3.0 | Tool and skill library for materials agents covering the wider simulation stack. AGPL: read it for ideas, do not copy code into a permissively licensed bundle. |
| VASPilot ([arXiv:2508.07035](https://arxiv.org/abs/2508.07035)) | paper + code | A CrewAI-based multi-agent layer over an MCP tool server for autonomous VASP runs. Useful as a design reference for how an agent should plan, submit and report a calculation. |

## How to use this list

- Before inventing a parameter set, check whether one of these projects already
  documents it — but verify the recommendation against your own system.
- When two tools disagree on the same number, treat that as a finding to explain
  (different energy zero, different smearing, different k-mesh), not as a reason
  to pick the answer you prefer.
- qvasp's own paper is the citation for the commands in this pack:
  W. Yi, G. Tang, X. Chen, B. Yang, X. Liu, *Comput. Phys. Commun.* **257**,
  107535 (2020), [doi:10.1016/j.cpc.2020.107535](https://doi.org/10.1016/j.cpc.2020.107535).
