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

## How to use this list

- Before inventing a parameter set, check whether one of these projects already
  documents it — but verify the recommendation against your own system.
- When two tools disagree on the same number, treat that as a finding to explain
  (different energy zero, different smearing, different k-mesh), not as a reason
  to pick the answer you prefer.
- qvasp's own paper is the citation for the commands in this pack:
  W. Yi, G. Tang, X. Chen, B. Yang, X. Liu, *Comput. Phys. Commun.* **257**,
  107535 (2020), [doi:10.1016/j.cpc.2020.107535](https://doi.org/10.1016/j.cpc.2020.107535).
