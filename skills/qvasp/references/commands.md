# qvasp command reference

Transcribed from `qvasp -h` (v3.01, 2026-11-23 build). Regenerate with
`tools/gen_commands.py` and diff when qvasp is upgraded.

"needs" = files that must be in the current directory; "writes" = main outputs
(qvasp also prints a summary and may write log/temp files).

## INCAR templates

| command | purpose | args | needs | writes |
|---|---|---|---|---|
| `-relax` | structure optimisation | none | POSCAR | INCAR |
| `-scf` | self-consistent calculation | none | POSCAR | INCAR |
| `-band` | band structure | none | POSCAR | INCAR |
| `-dos` | density of states | none | POSCAR | INCAR |
| `-elf` | electron localisation function | none | POSCAR | INCAR |
| `-wk` | work function | none | POSCAR | INCAR |
| `-bader` | Bader charge | none | POSCAR | INCAR |
| `-hse` | HSE06 | none | POSCAR | INCAR |
| `-md` | molecular dynamics | none | POSCAR | INCAR |
| `-elastic` | elastic constants | none | POSCAR | INCAR |
| `-partchg` | partial charge density | none | POSCAR | INCAR |
| `-freq` | frequency (IBRION=5/6/8) | none | POSCAR | INCAR |
| `-optics` | optical properties (LOPTICS) | none | POSCAR | INCAR |
| `-phonon` | phonon (finite displacement) | none | POSCAR | INCAR |
| `-ts` | transition state (NEB/dimer) | none | POSCAR | INCAR |
| `-lobster` | LOBSTER | none | POSCAR | INCAR |

## POSCAR / structure

| command | purpose | args | needs | writes |
|---|---|---|---|---|
| `-fix` | fix atomic layers | none | POSCAR | POSCAR |
| `-it` | insert images for TS (method 1) | none | POSCAR | POSCAR-*, folders |
| `-itms` | insert images for TS (method 2) | none | POSCAR | POSCAR-*, folders |
| `-sc` | supercell | `na nb nc` | POSCAR | POSCAR |
| `-freqfix` (`-zc`) | remove imaginary modes: 1 = molecule/Γ (displace along an OUTCAR soft mode by an Å amplitude), 2 = solid (ASR fix of FORCE_CONSTANTS) | modes via menu | OUTCAR / FORCE_CONSTANTS | POSCAR + POSCAR-bak + freqfix.dat, or FORCE_CONSTANTS_asr |
| `-c2p` | CIF → POSCAR | file | .cif | POSCAR |
| `-sqs` | special quasi-random structure | none | POSCAR | POSCAR |
| `-p2c` | POSCAR → CIF | none | POSCAR | `<folder>.cif` |
| `-findsym` | symmetry analysis | none | POSCAR | stdout |
| `-findcell` | primitive cell | none | POSCAR | POSCAR |
| `-defect` | inequivalent defect sites | none | POSCAR | list/stdout |
| `-neb` | align NEB endpoints | none | POSCARs | POSCAR |
| `-sw` | switch (a,b,c) axes | none | POSCAR | POSCAR |
| `-orthcell` | orthogonal cell | none | POSCAR | POSCAR |
| `-redlat` | redefine lattice setting | none | POSCAR | POSCAR |
| `-cls` | cleave surface | none | POSCAR | POSCAR |
| `-nanotube` | roll nanosheet | none | POSCAR | POSCAR |
| `-hej` | heterojunction | POS1 POS2 | two POSCARs | POSCAR |
| `-mos` | moiré superlattice | POS1 POS2 | two POSCARs | `moires-*.vasp` |
| `-as` | adsorption sites | none | POSCAR | stdout |

## KPOINTS

| command | purpose | args | writes |
|---|---|---|---|
| `-k` | automatic mesh from k-density | `density` | KPOINTS |
| `-3k` | 3D mesh variant | `density` | KPOINTS |
| `-kline` | band path (Line mode) | none | KPOINTS |
| `-khse` | HSE06 mesh + path | none | KPOINTS |
| `-kphonon` | phonon supercell mesh | none | KPHON.conf |
| `-3dkpoints` | 3D band KPOINTS | none | KPOINTS |

## POTCAR

| command | purpose | args | writes |
|---|---|---|---|
| `-pbe` | POTCAR from PAW_PBE | `ELE ...` | POTCAR |
| `-lda` | POTCAR from PAW_LDA | `ELE ...` | POTCAR |
| `-pw91` | POTCAR from PAW_PW91 | `ELE ...` | POTCAR |
| `-cp` | check the POTCAR | none | stdout |

Element names must match the local library entries (e.g. `Sr_sv`, `Ti_pv`, `O`).

## Post-processing: band / DOS

| command | purpose | needs | writes |
|---|---|---|---|
| `-bandd` | band data | OUTCAR, EIGENVAL | `band.dat` |
| `-dosd` | DOS data | DOSCAR | `DOS*.dat` |
| `-ldos i j ...` | sums the atom-projected DOS of the listed atoms | DOSCAR | `LDOS.dat` |
| `-bandp` | k-projected bands (energies shifted so E_F = 0) | OUTCAR, EIGENVAL | `PBAND.dat` |
| `-banduf` | band unfolding / EBS | OUTCAR, EIGENVAL | `EBS.dat` |
| `-3dband` | 3D band for 2D materials | OUTCAR, EIGENVAL | `3Dband.dat` |
| `-scissorb` | scissor-corrected band | `band.dat` | corrected file |
| `-scissord` | scissor-corrected DOS | `DOS*.dat` | corrected file |
| `-effmass` | carrier effective mass | EIGENVAL, KPOINTS | stdout/table |

## Post-processing: charge / work function

| command | needs | writes |
|---|---|---|
| `-baderd` | ACF.dat (Henkelman code) | charge table |
| `-dband` | DOSCAR | d-band centre |
| `-wkd` | LOCPOT | work function |
| `-chgdif` | two CHGCARs | difference data |
| `-wfn` | WAVECAR | `WFN_REAL.vasp`, `WFN_IMAG.vasp` |

## Surfaces

| command | needs | writes |
|---|---|---|
| `-esurf` | slab + bulk energies (OUTCARs) | surface energy |

## Post-processing: magnetic / optical

| command | needs | writes |
|---|---|---|
| `-opticsd` | vasprun.xml (LOPTICS) | `IMAG.dat`, `REAL.dat` |
| `-ir` | OUTCAR (IBRION=5..8, LEPSILON) | `ir.dat`, `ir_spectrum.dat` |
| `-raman` | OUTCAR + `raman_m<i>_p/_m` vasprun.xml | `raman.dat`, `raman_spectrum.dat` |
| `-magm` | menu: maginit / spinden / magconf / fitj / curie / mae | `MAGMOM`, `CHG_spin.vasp`, FM/AFM folders, J table, Tc, `MAE.dat` |

Both `-ir` and `-raman` broadened spectra default to a **Gaussian**; answer `L` for a
Lorentzian lifetime line shape.

## Post-processing: thermo / lattice

| command | needs | writes |
|---|---|---|
| `-phonond` | phonopy output (FORCE_CONSTANTS, band.yaml) | `PhononBAND.dat`, DOS |
| `-elasticd` | OUTCAR (IBRION=6) | elastic constants |
| `-thermo` | OUTCAR frequencies / gas or surface mode | `thermo.dat` |
| `-teprop` | EIGENVAL (NSCF dense grid) | `thermo.dat` (S, σ, PF, κe, ZT) |
| `-e` | OUTCAR | energy/enthalpy |
| `-eos` | E–V data | B0, V0 |
| `-zpe` | OUTCAR frequencies | ZPE |

## Post-processing: MD analysis / misc

| command | needs | writes |
|---|---|---|
| `-msd` | XDATCAR | MSD, diffusion |
| `-rdf` | XDATCAR/POSCAR | `RDF.dat`, CN |
| `-out2arc` | OUTCAR | `.arc` trajectory |
| `-gauss` | OUTCAR | Gauss.log |
| `-mde` | OSZICAR, OUTCAR | `mde.dat` |
| `-mdm` | OSZICAR, OUTCAR (ISPIN=2) | `mdm.dat` |

## Jobs / misc

| command | purpose |
|---|---|
| `-showstatus` | print the job queue status |
| `-clean` | remove VASP output files (asks for confirmation) |
| `-help` / `-h` | full help |

## Customizable tools (wrappers / external)

| command | purpose |
|---|---|
| `-vaspkit` | call VASPKIT |
| `-atomkit` | call atomkit |
| `-post_VASP` | call the post_VASP toolkit |
| `-den2vasp` | CASTEP density → CHGCAR |
| `-res2vasp` | `.res` → POSCAR |
| `-ueff` | fit U for LDA+U by linear response |
| `-piez` | piezoelectric/elastic tensor extraction |


