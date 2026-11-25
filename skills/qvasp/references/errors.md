# VASP and qvasp failure modes

Every entry below was either reproduced here or is standard VASP behaviour; the
`grep` string is what you search for in `vasp.log` / `OUTCAR` / `OSZICAR`. Work
one change at a time and write down what you changed — a chain of simultaneous
edits cannot be diagnosed later.

## How to triage

1. Read the **last** 40 lines of `vasp.log`, not the first error you find. VASP
   often prints a warning that is harmless and then the real abort.
2. If the job died at step 1, the input is wrong (POTCAR order, KPOINTS
   mismatch, missing CHGCAR). If it died after 20+ ionic steps, the physics or
   the relaxation controls are wrong.
3. Check whether the job *finished*: `reached required accuracy` in `OUTCAR`
   for a relaxation, `aborting loop because EDIFF is reached` for a static run.
   A job that exits 0 without either marker has not converged.
4. Re-run in a fresh directory with the same inputs before changing anything.
   Half-written `WAVECAR`/`CHGCAR` from a killed job cause failures that look
   like input errors.

## Crash and abort messages

| grep for | what it means | what to do |
| --- | --- | --- |
| `ZBRENT: fatal error in bracketing` | line search bracketed a step it could not resolve — usual cause is a soft mode, an over-large `POTIM`, or a structure that is not the one you think | `cp CONTCAR POSCAR`, set `IBRION = 1`, `POTIM = 0.1`, `EDIFF = 1E-6`, restart. If it recurs, the structure is near a soft mode: relax with `ISIF = 2` first |
| `Error EDDDAV: Call to ZHEGV failed` | the Davidson/blocked-Davidson solver hit a numerically bad subspace, usually with too few bands per core or an aggressive mixer | delete `WAVECAR`, set `ALGO = Normal` (not `Fast`), reduce `NCORE`/`NSIM`, retry |
| `WARNING: Sub-Space-Matrix is not hermitian in DAV` | nearly always two atoms sitting on top of each other, or a lattice so distorted that the plane-wave basis is inconsistent | check the smallest interatomic distance first (a POSCAR with a duplicated atom is the usual culprit); only then try `ALGO = All` with smaller `AMIX` |
| `BRMIX: very serious problems` | charge mixing diverged | `AMIX = 0.2`, `BMIX = 0.0001`; for magnetic systems also `AMIX_MAG = 0.8`, `BMIX_MAG = 0.0001`; verify `NELECT` matches the POTCAR `ZVAL` sum |
| `charge density could not be read from file CHGCAR for ICHARG>10` | the `CHGCAR` was written with a different plane-wave cutoff than the run reading it, so the FFT grids differ | make `ENCUT` **identical** in the writing and the reading `INCAR`. qvasp's `-band` template uses `ENCUT = 400`; a hybrid or high-cutoff SCF run leaves a `CHGCAR` on a `500` grid and the band step then aborts. Set `ENCUT` explicitly in both |
| `WARNING: dimensions on CHGCAR file are different` | same root cause as the line above, one step earlier | as above |
| `Tetrahedron method fails for the calculation of the k-point dependent` | `ISMEAR = -5` was used in a run where the k-mesh moves (relaxation, MD) | use `ISMEAR = 0` with a small `SIGMA` while the geometry changes; keep `-5` for the final static run and for DOS |
| `TOO FEW BANDS` | `NBANDS` too small for the requested eigenvalue count | raise `NBANDS` to about 1.3–2× the default; with `LOPTICS`/hybrids even more |
| `VERY BAD NEWS! internal error in subroutine SGRCON` (or `IBZKPT`, `PRICEL`) | the symmetry finder was handed a structure that is only approximately symmetric | `SYMPREC = 1E-4`; if it persists, `ISYM = 0` and accept the cost |
| `inverse of rotation matrix was not found` | symmetry rotation could not be inverted at the working precision | `ISYM = 0` for that run |
| `LAPACK: Routine ZPOTRF failed` | overlapping atoms, often produced by an over-large `POTIM` on a stiff mode | inspect the last frames of `XDATCAR`, rebuild the `POSCAR` from a good frame, restart with `POTIM = 0.1`–`0.2` |
| `KILLED BY SIGNAL` / `oom-kill` | out of memory | fewer ranks per node, or lower `KPAR`, or `NCORE` equal to the cores per node; the memory scales with `NBANDS × NPW × N_kpoints` and with `LOPTICS` |
| `mpirun: command not found` | the job script's environment was not sourced on the compute node | source the cluster's Intel/MPI environment inside the job script (`source .../intel2020.env`, `source .../impi2019.env`) before `mpirun` |
| `execvp error on file vasp_std` | the binary name has no absolute path and the compute node does not inherit your login `PATH` | use an absolute path in the job script, e.g. `/public/software/vasp/vasp.6.5.1/bin/vasp_std` |
| `forrtl: severe (24): end-of-file during read` | a fixed-format read ran past the end of a file — most often a `POSCAR` whose coordinate block is shorter than the header promises | count the atoms: the header says N, the coordinate block must have N lines. qvasp 3.01 fixed a reader that consumed one extra line when the mode line read `Cartesian` |

## Runs that finish but are wrong

| symptom | why | fix |
| --- | --- | --- |
| `NSW` ionic steps used up with no `reached required accuracy` | the force criterion, not the energy criterion, ends a relaxation | loosen `EDIFFG` (for example `-0.03` instead of `-0.01`); lowering `EDIFF` does nothing |
| energy drifts a few meV between identical runs | k-mesh, `SIGMA` or `PREC` differs, or the run started from a different `WAVECAR` | freeze the full `INCAR` in a comment, and compare `NBANDS`, `ENCUT` and the k-point count in `OUTCAR` |
| magnetic moment much smaller than expected | starting `MAGMOM` too small, or the state collapsed to a low-spin solution | start from a larger moment (e.g. 3–5 μB on the magnetic ion), break symmetry with `ISYM = 0` for the initial SCF, then check the final `magnetization (x)` table |
| gap is zero in a system you believe is a semiconductor | the k-mesh misses the band edges, or `ISMEAR = -5` shifted the occupations | denser mesh, `ISMEAR = 0` with `SIGMA = 0.05`, read the band edges from `EIGENVAL` rather than from `DOSCAR` |
| DOS does not integrate to the expected electron count | the projection needs `LORBIT = 11` and a `RWIGS`-free POTCAR, and the spin channel doubles the count | check `NELECT` and integrate the total DOS, not a projected one |
| relaxation ends at a higher energy than it started | an over-large `POTIM` walked into a different basin | restart from the lowest-energy frame of `XDATCAR` with `POTIM = 0.1` |

## qvasp-specific messages

| message | meaning | fix |
| --- | --- | --- |
| `I can't find CONTCAR or POSCAR file here` from `-bandd` / `-3dband` | the post-processing step needs the lattice | run it in a directory that has `CONTCAR` or `POSCAR` (3.01 accepts `POSCAR` as a fallback; earlier versions demanded `CONTCAR`) |
| `ERROR: invalid dimensionality` from `-kline` / `-khse` / `-kphonon` | these commands ask for the dimensionality interactively and read EOF | answer the prompt (`1`, `2` or `3`) or pass the dimension through whatever wrapper you use |
| `POSCAR not found (2); writing commented v4 templates.` from `-phonon` | `-phonon` takes only named options (`--dim`, `--vac`, `--chain`, `--n`, `--out`); any other token is treated as a POSCAR filename | `qvasp -phonon --dim 2 2 2`, not `qvasp -phonon 2 2 2` |
| `[qvasp ERROR] POSCAR not found` from `-elasticd` / `-findcell` / `-findsym` | the command needs the structure to pick its template | keep a `POSCAR` in the working directory; in a staged workflow copy the upstream `CONTCAR` to `POSCAR` |
| `phonopy_disp.yaml could not be found` from `-phonond` | the phonon run was continued in a directory that never had the displacement file | copy `phonopy.yaml`, `phonopy_disp.yaml` and `FORCE_SETS` from the directory that ran the displacements; `-phonond` deliberately never re-initialises, because a fresh `phonopy_disp.yaml` may describe different displacements or a different supercell and the forces would then be silently mis-assigned |
| `FORCE_SETS missing/empty` | the forces were never extracted | `phonopy-init -f disp-*/vasprun.xml` (phonopy ≥ 4; the old `phonopy -f` was moved to `phonopy-init`) |
| `POTCAR missing at the system root` (workflow stage) | the stage directory has no `POTCAR` and none was staged from the system root | put `POTCAR` (or `qvasp -pbe/-lda/-pw91 <elements>`) at the root of the case directory |
| `cwd ... is outside QVASP_WORKROOT` | the MCP server refuses to touch files outside its sandbox | pass a path under `QVASP_WORKROOT`, or raise the root |

## Reading a result you do not trust

- Energy zero points differ per command. `-bandd` writes `band.dat` referred to
  the valence-band maximum; `-bandp` shifts by the `E_F` recorded in `OUTCAR`.
  State which zero a reported gap or band position uses.
- A convergence marker is not a correctness proof. Cross-check one number
  against an independent path (a second k-mesh, a different `ISMEAR`, or an
  analytic value) before publishing it.
- Whenever a value is compared with experiment, record the source (DOI or URL)
  next to it. An unsourced comparison is not evidence.
