# Verified pitfalls (from independent testing, 2026-11)

These are behaviours confirmed against real VASP data, not guesses. They matter when
you interpret or hand off results.

## Energy zero points

- `-bandd` (`band.dat`) is referenced to the **VBM**, not to the Fermi level. If a
  report needs E_F, read `E-fermi` from OUTCAR and shift explicitly.
- `-bandp` instead shifts every eigenvalue so that the **OUTCAR Fermi energy is 0**
  (e.g. EIGENVAL −11.75/76.83 eV with E_F = 9.88 becomes −21.63/66.95 eV).

## Spectra line shape

- `-ir` and `-raman` broaden with a **Gaussian by default** (σ = FWHM/2.3548). Answer
  `L` for a Lorentzian. A Lorentzian with FWHM = 10 cm⁻¹ keeps ~1.1 % of the peak
  47 cm⁻¹ away (25.6 for a 2317 peak); a Gaussian is numerically zero there.
- `-ir` uses the Born charges from `vasprun.xml` and the mass-weighted eigenvectors from
  OUTCAR; silent modes get zero intensity — a useful sanity check.

## Thermodynamics

- `-thermo` clamps frequencies below 50 cm⁻¹ **only in the entropy**; ZPE and H use the raw
  frequencies. A soft mode therefore inflates S differently from H.
- `-teprop` is a constant-relaxation-time semiclassical BTE (rigid band). Absolute
  conductivity/ZT depend on τ; the Seebeck coefficient is the robust output.

## Imaginary frequencies

- `-freqfix` mode 1 displaces along a **mass-weighted eigenvector de-mass-weighted to a
  physical amplitude** (default 0.10 Å). The old `-zc` "correction factor" was
  dimensionless: with the default 1.0 it could move atoms by ~18 Å and destroy a molecule.
- All imaginary modes are listed; the default is the first one. Pick explicitly — the
  strongest imaginary mode is not necessarily the torsion/physical soft mode.
- Mode 2 applies the acoustic sum rule `Φ(i,i) = Φ(i,i) − Σ_j Φ(i,j)` on the rows present
  in the file. On a real MgSiO3 force-constant set the drift 1.813E-01 eV/Å² dropped to
  5.3E-15 and the Γ acoustic modes moved from −2.4/−2.4/−1.8 cm⁻¹ to −0.8/−0.1/0.0 cm⁻¹,
  with the optical branches unchanged.
- **ASR only removes numerical violations.** A genuine soft mode (charge-density wave,
  ferroelectric instability) must not be "fixed": check its convergence with the supercell
  size and the cutoff instead.
- A genuine ferroelectric soft mode *can* be followed: cubic SrTiO3 (5-atom cell, PBE,
  ENCUT 500, 4×4×4) has three degenerate Γ modes at −148.8/−149.4/−149.6 cm⁻¹. `-freqfix`
  mode 1 moved the atoms 0.100 Å along the first one (Ti against three O, the polar
  direction), the relaxation lowered the energy by 6.3 meV/cell at fixed volume, and the
  soft triplet hardened to +91.9/+98.5/+139.2 cm⁻¹. The residual −1.5…−4 cm⁻¹ are the
  Γ acoustic modes (finite-difference noise), not an instability.

## ISIF = 3 near a soft mode

- Relaxing both ions and cell (`ISIF = 3`) on a soft-mode system can end in
  `ZBRENT: fatal error in bracketing` → `I REFUSE TO CONTINUE WITH THIS SICK JOB`.
  The structure at that point is usually already good; do **not** restart from scratch.
  Copy CONTCAR to POSCAR, set `EDIFF = 1E-6` and `POTIM = 0.1` (default 0.5 is too long a
  line-search step), and continue. On cubic SrTiO3 this converged in 53 more ionic steps
  and reached −39.996197 eV (−52.9 meV/cell below the cubic cell, volume +4.0 %,
  3 short + 3 long Ti–O bonds of 1.889/2.077 Å).
- Never submit a frequency job on a structure whose relaxation aborted: kill it and fix
  the geometry first.

## Structures

- `-mos` builds layer 2 by mapping it onto the layer-1 supercell. For an anisotropic
  (rectangular) 2D lattice the match needs anisotropic strain; the tool prints the
  principal strains and warns above 3 %. A 7° twisted phosphorene cell already needs ~6 %,
  which is a strained model, not a strain-free moiré.
- `-kline`/`-khse`/`-kphonon` derive the path from the **actual cell** via spglib. Feeding a
  2-atom simple-cubic cell labelled "diamond" yields the wrong path; use the true
  primitive cell (fcc, spglib 227 for diamond).
- `-p2c` names the CIF after the current folder, not `out.cif`.

## POTCAR

- `-pbe/-lda/-pw91` take the library element names (`Sr_sv`, `Ti_pv`, `O`, …), not the
  chemical symbol only. A missing entry prints the expected folder path.

## Running examples

- Examples ship with a `run.log` recorded by the author. After replaying a command, compare
  your output with the shipped files; a mismatch in numbers is a real signal, a mismatch in
  leading whitespace or timestamps is not.
- Never run post-processing in the shipped example folder — copy it first, because qvasp
  overwrites POSCAR/KPOINTS/INCAR.
