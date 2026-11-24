# Workflows

Each recipe assumes a clean calculation directory containing `POSCAR` (and VASP's
`POTCAR`, `KPOINTS` from the steps below). Run everything on the machine where VASP
and qvasp live, and submit VASP through the scheduler.

## Automated workflows (MCP server)

If the `qvasp-mcp` server is connected, these recipes are already encoded as templates
and can be run end to end instead of by hand:

| template | stages | use |
|---|---|---|
| `relax-only` | 1 | strategies `bulk` (ISIF=3) / `fixed-cell` (ISIF=2) |
| `band-pbe` | 4 | relax → scf → nscf line-mode → `-bandd` |
| `band-hse` | 3–4 | strategies `opt` (KPOINTS_OPT, VASP≥6.3) / `oneshot` (`-khse`) / `twostep` |
| `dos-pbe` | 4 | relax → scf → nscf dense mesh → `-dosd` |
| `phonon-pbe` | 5 | relax (EDIFFG −0.001) → `-phonon` → **manual** phonopy forces → **manual** FC → `-phonond` |
| `optics-hse` | 3–4 | strategies `opt` / `twostep` |
| `elastic-pbe` | 3 | tight relax → IBRION=6 at ENCUT 1000 → `-elasticd` |
| `md-pbe` | 3 | strategies `nvt` (`-msd`) / `nve` (`-mde`) |
| `surface-pbe` | 3 | bulk scf → slab scf → `-esurf` |
| `freqfix-molecule` | 4 | `-freq` → `-freqfix` → relax → `-freq` |

```
workflow_plan   {"workflow":"band-pbe","system":"<dir>"}          # show the DAG, run nothing
workflow_run    {"workflow":"band-pbe","system":"<dir>"}          # advance one stage
workflow_status {"system":"<dir>"}
workflow_check  {"workflow":"band-pbe"}                           # lint a template
```

`workflow_run` is resumable: each call submits the next stage, returns
`{"waiting": true}` while the job is queued, and evaluates the stage gate when it
ends. State lives in `<system>/workflow.json`, stage directories in `<system>/00-relax`,
`01-scf`, … Put `POSCAR` and `POTCAR` at the system root; everything else is derived.

A stage's `inputs` may name either an earlier stage (`"../00-relax/CONTCAR"`, resolved
against the stage directory) or a file the user left at the system root
(`"POSCAR-slab"`, no `../`). Both are tried, so a template does not have to know which
convention the other one uses.

**An `ICHARG = 11` stage must repeat the SCF cutoff.** VASP rebuilds its FFT grid from
`ENCUT`; if the grid no longer matches the one the charge density was written on, it
refuses the file:

```
WARNING: dimensions on CHGCAR file are different
ERROR: charge density could not be read from file CHGCAR for ICHARG>10
---->  I REFUSE TO CONTINUE WITH THIS SICK JOB ... BYE!!! <----
```

The `scf` prototype raises `ENCUT` to 500, so `nscf`, `dos-pbe/02-dos` and the
`ICHARG = 11` stages of `band-hse` (`opt`, `twostep`) all pin `ENCUT` to 500 as well. Change
the pair together or the second stage dies on a perfectly good CHGCAR.

A stage with `"kind": "manual"` is not a qvasp command — phonopy is the usual case.
The tool prepares the directory, records `state="manual"` with the note explaining the
step, and returns immediately. Run the step by hand, then call `workflow_resume`; the
stage's gate decides when it is done. Templates must give a manual stage both a note
and a gate, and `workflow_check` rejects one that does not.

Stage prototypes (`server/stages.json`) hold the INCAR overrides a stage inherits:
`relax scf nscf hybrid dfpt elastic soc md transport post`. A template stage names one
in `prototype` and overrides only what differs. Overrides replace any tag the qvasp
template already wrote — VASP takes the last duplicate, so appending would silently
lose the value.

`QVASP_SCHEDULER=none` is a dry run: inputs are written and nothing is submitted. In
that mode a stage whose upstream product does not exist yet is recorded as `prepared`
with a `notes` entry rather than failing, and a post-processing stage is skipped
outright — running it on an empty directory would "succeed" and record a fake result.

## 1. Relax → SCF → band

```
qvasp -relax                     # INCAR for ISIF=3 relaxation
# qsub, wait
cp CONTCAR POSCAR
qvasp -scf                       # SCF INCAR (CHGCAR)
# qsub, wait
qvasp -band                      # band INCAR
qvasp -kline                     # Line-mode KPOINTS from the current POSCAR
# qsub, wait
qvasp -bandd                     # band.dat for plotting
```

Check: `-bandd` reports the gap; `band.dat` energies are referenced to the VBM.

## 2. DOS and atom projections

```
qvasp -dos ; qvasp -k 0.02       # dense mesh
# qsub, wait
qvasp -dosd                      # DOS0.dat, DOS2.dat, ...
qvasp -ldos 1 2                  # sum of the atom-projected DOS of atoms 1 and 2
qvasp -dband                     # d-band centre from DOSCAR
```

## 3. Phonons → thermal properties

```
qvasp -phonon                    # finite-displacement INCAR
qvasp -kphonon                   # KPHON.conf for the supercell
# build the supercell, run the displacements (phonopy workflow), collect forces
qvasp -phonond                   # PhononBAND.dat + DOS
qvasp -thermo                    # H/S/G(T) from the frequencies
qvasp -zpe                       # zero-point energy
```

## 4. Optics

```
qvasp -optics                    # LOPTICS INCAR (needs many empty bands)
# qsub, wait (vasprun.xml must contain the dielectric function)
qvasp -opticsd                   # IMAG.dat / REAL.dat
```

## 5. IR and Raman

```
qvasp -freq                      # IBRION=5/6/8 + LEPSILON for IR intensities
# qsub, wait
qvasp -ir                        # ir.dat + ir_spectrum.dat (Gaussian by default)
qvasp -raman                     # raman.dat + raman_spectrum.dat
# (-raman first generates raman_m<i>_p/_m folders; run VASP in each, then collect)
```

## 6. Magnetic suite

```
qvasp -magm
   1) spinden   -> CHG_spin.vasp + local moments
   2) magconf   -> FM/ AFM_i/ folders with MAGMOM
   3) fitj      -> Heisenberg J from the energies of those folders
   4) curie     -> Tc (mean field + Monte Carlo)
   5) mae       -> three SOC runs (SAXIS x/y/z), then collect
   6) maginit   -> MAGMOM from a converged OUTCAR
```

`mae` needs a collinear `OUTCAR` with `LORBIT=11` first; it then writes
`MAE_x/ MAE_y/ MAE_z/` (LSORBIT, SAXIS along each axis). Run them with `vasp_ncl`,
then choose option 2 to collect `MAE.dat`.

## 7. Imaginary frequencies (`-freqfix`, alias `-zc`)

```
qvasp -freqfix
   1 = molecule / Gamma point : reads the soft mode from OUTCAR, de-mass-weights the
       eigenvector, normalises it and displaces the atoms by the requested amplitude
       (default 0.10 A).  Writes POSCAR, keeps POSCAR-bak, writes freqfix.dat.
       Then relax and recompute the frequencies.
   2 = periodic solid : reads phonopy FORCE_CONSTANTS, imposes the acoustic sum rule
       and writes FORCE_CONSTANTS_asr.  Rebuild the band structure with it.
```

## 8. Thermoelectrics

```
qvasp -scf ; qvasp -k 0.015      # dense SCF/NSCF
# qsub, wait (EIGENVAL on the dense grid)
qvasp -teprop                    # S, sigma, PF, kappa_e, ZT vs doping/T
```

## 9. MD analysis

```
qvasp -msd                       # MSD + diffusion coefficient
qvasp -rdf                       # g(r) and coordination number
qvasp -mde ; qvasp -mdm          # energy and magnetic-moment time series
qvasp -out2arc                   # .arc trajectory for visualisation
```

## 10. Surfaces

```
qvasp -cls                       # cleave the slab
# compute slab and bulk energies, then
qvasp -esurf                     # surface energy (J/m^2)
```
