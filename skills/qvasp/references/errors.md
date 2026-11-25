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
| `forrtl: severe (59): list-directed I/O syntax error` + `0 types 0 ions` | the second line of `POSCAR` is not a plain number. VASP reads that line as the universal scaling factor; a leftover label, a unit or an empty line makes the whole header shift by one line | the layout is `comment` / `scale` / three lattice vectors / species names / counts. Put the scale (usually `1.0`) on line 2 and nothing else |
| `I REFUSE TO CONTINUE WITH THIS SICK JOB` (message above it varies) | VASP's generic refusal. The line **before** it is the real error — read upwards | `ADDGRID = .TRUE.` together with a TS/vdW correction, `SYMPREC` too tight for the cell, or a mangled `POSCAR` are the common ones |
| `Inconsistent Bravais lattice types found for crystalline and reciprocal lattice` | the cell is a hair off hexagonal symmetry: an `a*sqrt(3)/2` written to 6 decimals is already ~4e-5 off, which exceeds `SYMPREC = 1e-5` | write lattice vectors to ≥10 decimals, or set `SYMPREC = 1E-4` |
| `ERROR: ADDGRID=.TRUE. is not supported for TS correction methods` | `ADDGRID` and the Tkatchenko-Scheffler dispersion are mutually exclusive | drop `ADDGRID` for that run |
| `qsub: cannot connect to server (null) ... could not connect to trqauthd` | a compute node cannot reach the Torque server; a self-resubmitting pipeline dies at its second link | submit only from the login node, or `ssh` back to it (`ssh -o BatchMode=yes <login> /opt/.../qsub <abs job.pbs>`) |
| a child job runs in the wrong directory | a job submitted from inside another PBS job inherits `PBS_O_WORKDIR` (and friends) from its parent | `unset PBS_O_WORKDIR PBS_O_HOME PBS_O_LOGNAME PBS_O_HOST` before the inner `qsub`, and pass `qsub -d <absolute dir>` |
| every rank dies in `FFT: planning ... GRID`, rank 0 `SIGSEGV`, others `SIGKILL` | `vasp_std` is built with OpenMP; 12 MPI ranks × 12 threads exhausts the node's memory | `ulimit -s unlimited`, `export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1` in the job script |
| `mpirun` aborts inside `MPI_Init` on the whole node | a broken MPI/launcher pairing (seen with VASP 6.3.1 multi-process and with Intel MPI's default SSH bootstrap inside PBS) | use a working build (6.5.1 here) and a single-node launcher: `mpirun -bootstrap fork -n N ...` |


## Inputs VASP accepts and silently ignores

These produce no message at all. The job converges, the file is there, and the
number is wrong — the most expensive class of mistake, because nothing to grep
for exists. `preflight` flags the ones it can prove from the files.

| what you wrote | what VASP did | what to write |
| --- | --- | --- |
| a tag that is not a VASP tag (`EXT_PRES`, `PRESS`, `KSPCACING`, `LVDW`, …) | parsed the line, ignored it, and continued as if it were absent | the real tag. External pressure is `PSTRESS` in **kB** (`1 GPa = 10 kB`); the k-point density tag is `KSPACING`. A misspelled tag is invisible in the output: eight "pressure points" all ran at 0 GPa and all had identical energies |
| `KSPACING` while a `KPOINTS` file is present | the file wins; `KSPACING` is then dead weight | keep one mechanism. `KGAMMA` belongs with `KSPACING` |
| a k-mesh written as a density in `KPOINTS` (`0.1 0.1 0.1`) | read the three numbers as integers, got `NKPTS = 0`, and spun at full load for hours without writing a result | the three numbers are **counts**, e.g. `16 16 16`. A Gamma-only file is 5 lines: `K-Points Gamma only` / `0` / `Gamma` / `1 1 1` / `0 0 0` |
| a line-mode `KPOINTS` with the segment point count on the fourth line | took the count from the **scale line (2nd)** instead, generated 2 points per segment, and said nothing | point count on line 2. Verify with `Generated N points on each line segment` in `OUTCAR` |
| a line-mode `KPOINTS` without the word `Reciprocal` | consumed the first corner as the coordinate-system line, so the path started at the second point | write `Reciprocal` on line 3 (or `rec`); verify `total of N k-points` equals segments × points per segment |
| `MAGMOM = 4*5.0 6*0.0` when the cell has 11 atoms | used what it could and defaulted the rest | the expanded count must equal `NIONS`. Always expand by hand or with the tool |
| `LDAUU`/`LDAUJ`/`LDAUL` shorter than the species list | padded with zeros, so one species silently lost its +U | one entry per species **in POSCAR order**, including the ones you do not want to correct (`-1` for `LDAUL`, `0.0` for `LDAUU/J`) |
| `METAGGA = SCAN` + `LUSE_VDW = .TRUE.` **and** `IVDW = 202` | applied two different van der Waals mechanisms at once | `IVDW = 202` is MBD@rsSCS, a post-hoc correction; rVV10 is triggered by `LUSE_VDW`. rVV10: `METAGGA = SCAN`, `LUSE_VDW = .TRUE.`, `BPARAM = 15.7`, `CPARAM = 0.0093` and **no** `IVDW` line |

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
