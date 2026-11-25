# Choosing VASP parameters

qvasp writes templates with sensible defaults; this page is for the decisions the
defaults cannot make for you. Every number here is a starting point to be converged
on your own system, not a setting to copy blindly.

## The four convergence knobs

Run these tests once per chemical system, then keep the values for every later step
(band, DOS, phonon, optics all inherit them).

| knob | test | stop when |
| --- | --- | --- |
| `ENCUT` | single-point at 1.0, 1.1, 1.2, 1.3 × the largest `ENMAX` in POTCAR | total energy changes < 1 meV/atom |
| k-mesh | single-point at increasing density (qvasp `-k 0.04`, `-k 0.03`, `-k 0.02`) | energy < 1 meV/atom; for metals also check the Fermi-level DOS is smooth |
| `SIGMA` | metals only: 0.05, 0.1, 0.2 | energy and magnetic moment stop moving |
| cell / `POTIM` | relax from two starting volumes | both land on the same minimum |

`ENCUT` below the largest `ENMAX` is silently wrong rather than an error: VASP uses
the POTCAR's `ENMAX` per element, so mixing a hard element (O, F, first-row oxides)
with a soft one makes the soft species the limiting accuracy. The usual rule is
`ENCUT = 1.3 × max(ENMAX)`; qvasp's PBE templates start at 500 eV, which covers most
paw_pbe potentials but not all — check the POTCAR header.

An `ICHARG = 11` (non-self-consistent band/DOS) stage **must** use the same `ENCUT`
and the same FFT grid as the SCF that wrote its CHGCAR, otherwise VASP aborts with
`charge density could not be read from file CHGCAR for ICHARG>10` or warns
`dimensions on CHGCAR file are different`. The workflow templates carry `ENCUT: 500`
on both sides for this reason.

## Smearing

- `ISMEAR = -5` (tetrahedron): DOS and final static runs. Never during a relax — the
  forces from the tetrahedron method are not variational and relaxations crawl or fail.
- `ISMEAR = 0`, `SIGMA = 0.05`: insulators and semiconductors, relaxations of metals.
- `ISMEAR = 1` or `2`, `SIGMA = 0.2`: metals with large cells, or when `-5` fails with
  `Tetrahedron method fails for NKPT<6`.

If a gap comes out as exactly 0.0 eV, check `ISMEAR` before believing it: a metal
setting smears the gap shut.

## Functional

- PBE for geometry, phonons, elastic constants, surfaces. It is the reference the
  qvasp templates are built around.
- HSE06 (`qvasp -hse`) for band gaps and optical absorption. PBE underestimates gaps
  by 30–50 %; do not compare a PBE gap with an experimental one and call it an error.
  Screening (`HFSCREEN = 0.2`) is what makes hybrid calculations affordable.
- DFT+U for transition-metal oxides with localized 3d states. Use the Dudarev form
  (`LDAU = .TRUE.`, `LDAUTYPE = 2`, `LDAUJ = 0`) and one effective `LDAUU` per species;
  the value is not a physical quantity, so state the value and its source in the report.
  Start from a published set for the same oxidation state, never from a bare guess.
- `IVDW = 11` (DFT-D3 zero damping) or `12` (Becke–Johnson damping) for layered
  materials, molecular crystals and adsorption. Without it, graphite and molecular
  dimers come out essentially unbound.

## Magnetism

- Give a **high-spin** initial `MAGMOM` and let the calculation find the ground state;
  starting low and hoping it climbs is the usual reason a magnetic insulator comes out
  non-magnetic.
- For an antiferromagnet, break the symmetry explicitly (alternating signs on the
  magnetic sublattice) — a symmetric start stays in the non-magnetic solution.
- Check the moment in OUTCAR (`magnetization (x)`), not in the INCAR: compare it with
  the formal ionic moment (`qvasp -maginit` writes sensible formal values).
- A moment that is a little low (1.6 vs 1.7 μB for hcp Co) is normal for PBE; a moment
  that is zero when it should not be is a convergence problem, not a physics result.

## Slabs and molecules

- Slab: `LDIPOL = .TRUE.`, `IDIPOL = 3` for a polar slab; enough vacuum that the
  potential is flat in the middle (qvasp `-sur` can fix layers and add vacuum).
- Molecule/atom in a box: Γ point only, `ISMEAR = 0`, `SIGMA = 0.01`, and a box large
  enough that the density reaches zero at the boundary (15 Å is a minimum, 20 Å is safe).
- `LASPH = .TRUE.` for oxides and anything with d/f electrons — the aspherical
  corrections matter more than the extra cost.

## Performance settings that change nothing physical

`NCORE` (bands per core group), `KPAR` (k-point groups), `NSIM`, `LPLANE`. Set
`NCORE` to the cores per node and `KPAR` to the number of k-points you can afford
concurrently; both are pure throughput knobs. One exception: hybrid calculations need
`NCORE = 1` on many VASP builds, otherwise they abort in the FFT.

## What to record in a report

For every reported number: the `ENCUT`, the k-mesh, the functional (and `IVDW`/`LDAUU`
if used), the energy zero (VBM, Fermi level, or raw), and whether the run reached
`reached required accuracy` (ions) and `aborting loop because EDIFF is reached`
(electrons). A number without those five facts cannot be reproduced or compared.

## Reading a result you do not trust

- Convergence markers are not correctness. `reached required accuracy` only means the
  forces fell below `EDIFFG`; a wrong structure converges happily to a wrong answer.
- A relaxation that used all `NSW` steps did not converge. Loosen the **force** criterion
  (`EDIFFG`, e.g. −0.03) rather than the energy one — `EDIFF` controls the electronic
  loop and is usually already tight.
- Compare against a second implementation (`qvasp -eos`, `-elasticd`, `-bandd` versus
  the raw EIGENVAL) before publishing a number. A disagreement is a finding to explain,
  not a value to pick.
