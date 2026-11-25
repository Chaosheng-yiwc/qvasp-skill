"""Parsers that turn qvasp / VASP output files into typed, comparable records.

Every parser returns {"kind", "values", "units", "source", "sha256"} or
{"kind", "unsupported": reason, "head": first lines}.  Nothing is guessed: an
unrecognised format is reported, never silently coerced.
"""
import hashlib
import re
from pathlib import Path

import numpy as np


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _head(path, n=12):
    try:
        return "\n".join(Path(path).read_text(errors="replace").splitlines()[:n])
    except OSError:
        return ""


def _unsupported(kind, path, why):
    return {"kind": kind, "unsupported": why, "source": str(path), "head": _head(path)}


# --------------------------------------------------------------- band.dat ----
def _eigenval_header(lines):
    """Locate the 'NELECT NKPTS NBANDS' line; return (index, nelect, nkpts, nbands).

    The line position is not fixed in the wild (VASP writes 5 lines before it,
    some builds differ), so scan the head of the file for three integers.
    """
    for i, line in enumerate(lines[:12]):
        tok = line.split()
        if len(tok) == 3 and all(t.lstrip("+-").isdigit() for t in tok):
            return i, int(tok[0]), int(tok[1]), int(tok[2])
    return None, None, None, None


def _looks_like_eigenval(lines):
    """True when the head parses as an EIGENVAL, not merely 'three integers'.

    CHGCAR also opens with a lattice and small integers, so the header scan
    alone is not enough: require the first k-point block to yield nbands rows
    whose third column is a VASP occupation in [0, 1].
    """
    idx, nelect, nkpts, nbands = _eigenval_header(lines)
    if idx is None or nkpts <= 0 or nbands < 2:
        return False
    i = idx + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return False
    i += 1                                  # k-point coordinate line
    rows = 0
    for _ in range(nbands):
        if i >= len(lines):
            return False
        tok = lines[i].split()
        i += 1
        if len(tok) < 3:
            return False
        try:
            occ = float(tok[2])
        except ValueError:
            return False
        if not -0.01 <= occ <= 1.01:
            return False
        rows += 1
    return rows == nbands


def _eigenval_bands(lines):
    """Return (bands, nkpts, nbands, kpts_read) where bands are (k, E, occ).

    kpts_read is returned so the caller can refuse a truncated file: a run that
    was killed mid-write leaves a valid header and a partial band list, and a
    gap computed from it is silently wrong.
    """
    idx, nelect, nkpts, nbands = _eigenval_header(lines)
    out = []
    i = idx + 1
    kpts_read = 0
    for ik in range(nkpts):
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        i += 1                      # skip the k-point coordinate line
        kpts_read += 1
        for _ in range(nbands):
            if i >= len(lines):
                return out, nkpts, nbands, kpts_read
            tok = lines[i].split()
            i += 1
            if len(tok) >= 3:
                try:
                    out.append((ik, float(tok[1]), float(tok[2])))
                except ValueError:
                    continue
    return out, nkpts, nbands, kpts_read


def band_gap(path):
    lines = Path(path).read_text(errors="replace").splitlines()
    if _looks_like_eigenval(lines):
        return _eigenval_gap(path, lines)
    rows = []
    two_col = 0
    other = 0
    for line in lines:
        s = line.split()
        if not s or s[0].startswith("#"):
            continue
        if len(s) == 2:
            try:
                rows.append((float(s[0]), float(s[1])))
                two_col += 1
                continue
            except ValueError:
                pass
        other += 1
    if not rows:
        return _unsupported("band_gap", path,
                            "neither an EIGENVAL nor a two-column k/E table")
    # DOSCAR, CHGCAR, OUTCAR and friends also contain numbers. Only a file whose
    # data lines are overwhelmingly two-column can be a band.dat; otherwise the
    # "gap" would be read out of unrelated columns.
    if other > two_col * 0.05:
        return _unsupported(
            "band_gap", path,
            f"not a band table: {other} of {other + two_col} data lines are not "
            "two-column k/E rows (use EIGENVAL or the band.dat from qvasp -bandd)")
    k = np.array([r[0] for r in rows])
    e = np.array([r[1] for r in rows])
    ef = 0.0
    vbm = e[e <= ef].max() if np.any(e <= ef) else None
    cbm = e[e > ef].min() if np.any(e > ef) else None
    if vbm is None or cbm is None:
        return _unsupported("band_gap", path, "single-sided spectrum (no gap)")
    return {"kind": "band_gap", "values": {
        "gap_eV": round(float(cbm - vbm), 4),
        "vbm_eV": round(float(vbm), 4),
        "cbm_eV": round(float(cbm), 4),
        "k_range": [round(float(k.min()), 4), round(float(k.max()), 4)]},
        "units": {"gap_eV": "eV"}, "source": str(path), "sha256": sha(path)}


def _eigenval_gap(path, lines):
    """Gap from EIGENVAL: VBM = highest occupied, CBM = lowest empty over all k."""
    bands, nkpts, nbands, kpts_read = _eigenval_bands(lines)
    if not bands:
        return _unsupported("band_gap", path, "EIGENVAL header parsed but no band rows")
    if kpts_read < nkpts:
        # A killed job leaves a valid header and a partial band list. A gap
        # computed from it looks fine and is wrong, so refuse instead.
        return _unsupported(
            "band_gap", path,
            f"EIGENVAL is truncated ({kpts_read} of {nkpts} k-points); "
            "the run did not finish, so no gap can be quoted")
    occ = [b for b in bands if b[2] > 0.5]
    emp = [b for b in bands if b[2] <= 0.5]
    if not occ or not emp:
        return _unsupported("band_gap", path,
                            "EIGENVAL has only occupied or only empty bands "
                            "(metal, or too few bands)")
    vbm = max(occ, key=lambda b: b[1])
    cbm = min(emp, key=lambda b: b[1])
    if cbm[1] < vbm[1]:
        # A metal: some occupied state lies above an empty one. Do not use
        # fractional occupations as the test -- smearing (ISMEAR=0, SIGMA=0.2)
        # leaves a 4 eV gap with occupations around 0.96.
        return {"kind": "band_gap", "values": {
            "gap_eV": 0.0, "metallic": True,
            "nkpts": nkpts, "nbands": nbands},
            "units": {"gap_eV": "eV"}, "source": str(path), "sha256": sha(path)}
    vals = {"gap_eV": round(cbm[1] - vbm[1], 4),
            "vbm_eV": round(vbm[1], 4), "cbm_eV": round(cbm[1], 4),
            "vbm_k": vbm[0], "cbm_k": cbm[0],
            "nkpts": nkpts, "nbands": nbands}
    if nbands < 2:
        return _unsupported("band_gap", path, "EIGENVAL has a single band")
    return {"kind": "band_gap", "values": vals, "units": {"gap_eV": "eV"},
            "source": str(path), "sha256": sha(path)}


# ----------------------------------------------------------------- DOSCAR ----
def dos_at_ef(path, ef=None):
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return _unsupported("dos_at_ef", path, "missing")
    if len(lines) < 7:
        return _unsupported("dos_at_ef", path, "too short for DOSCAR")
    head = lines[5].split()
    # VASP writes "EMAX EMIN NEDOS EF 1.0" on line 6 -- the first field is the
    # top of the energy window, not the atom count.
    try:
        float(head[0]), float(head[1]), int(float(head[2])), float(head[3])
    except (IndexError, ValueError):
        return _unsupported("dos_at_ef", path, "DOSCAR header not recognised")
    emax, emin, nedos, fermi = (float(head[0]), float(head[1]),
                               int(float(head[2])), float(head[3]))
    if nedos <= 0 or emax <= emin:
        return _unsupported(
            "dos_at_ef", path,
            f"implausible DOSCAR header (EMAX {emax}, EMIN {emin}, NEDOS {nedos})")
    ef = fermi if ef is None else ef
    total = []
    for line in lines[6:6 + nedos]:
        s = line.split()
        if len(s) < 3:
            continue
        try:
            total.append((float(s[0]), sum(float(x) for x in s[1:])))
        except ValueError:
            continue
    if not total:
        return _unsupported("dos_at_ef", path, "no DOS rows")
    e = np.array([r[0] for r in total])
    d = np.array([r[1] for r in total])
    n_ef = float(np.interp(ef, e, d))
    return {"kind": "dos_at_ef", "values": {
        "fermi_eV": round(ef, 4), "dos_at_ef": round(n_ef, 4),
        "dos_max": round(float(d.max()), 4), "points": int(len(e)),
        "e_range": [round(float(e.min()), 3), round(float(e.max()), 3)]},
        "units": {"dos_at_ef": "states/eV"}, "source": str(path), "sha256": sha(path)}


# ------------------------------------------------------- phonon band dat ----
def phonon_min(path):
    freq = []
    blocks = 0
    header = False
    for line in Path(path).read_text(errors="replace").splitlines():
        s = line.split()
        if s and s[0] == "&":
            blocks += 1
            continue
        if line.strip().startswith("#"):
            low = line.lower()
            if ("phonon" in low or "frequenc" in low or "cm-1" in low
                    or "segments" in low):
                header = True
            continue
        if len(s) >= 2:
            try:
                freq.append(float(s[1]))
            except ValueError:
                continue
    if blocks:
        # qvasp -bandd writes one block per band, separated by '&'. Reading that
        # as a phonon spectrum returns band energies in place of frequencies.
        return _unsupported(
            "phonon_min", path,
            "this is a band-structure table (data blocks separated by '&'), "
            "not a phonon dispersion; use PhononBAND.dat from qvasp -phonond")
    if not freq:
        return _unsupported("phonon_min", path, "no frequencies")
    if not header:
        # A phonopy/qphonon dispersion always carries a comment header naming the
        # spectrum. band.dat has none, and reading its energies as cm^-1 looks
        # plausible, so refuse rather than guess.
        return _unsupported(
            "phonon_min", path,
            "no phonon header (expected a comment line naming the frequency axis); "
            "pass PhononBAND.dat from qvasp -phonond")
    f = np.array(freq)
    if f.size < 20:
        return _unsupported("phonon_min", path,
                            f"only {f.size} frequency rows; a dispersion has thousands")
    if float(np.abs(f).max()) > 20000.0:
        return _unsupported(
            "phonon_min", path,
            f"largest value {float(np.abs(f).max()):.0f} is far outside any phonon "
            "frequency range (cm^-1)")
    gamma = [v for v in f[:12]]
    return {"kind": "phonon_min", "values": {
        "min_cm1": round(float(f.min()), 3),
        "max_cm1": round(float(f.max()), 3),
        # |f| < 1 cm^-1 is numerical noise: the three acoustic branches at Gamma
        # come out at -1.6e-5 cm^-1 in a perfectly stable crystal. Counting those
        # as imaginary would report three soft modes for diamond.
        "imaginary_count": int((f < -1.0).sum()),
        "noise_floor_cm1": 1.0,
        "gamma_window_cm1": [round(float(min(gamma)), 3), round(float(max(gamma)), 3)]},
        "units": {"min_cm1": "cm^-1"}, "source": str(path), "sha256": sha(path)}


# ------------------------------------------------------------- MAE.dat ------
def mae(path):
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        s = line.split()
        if len(s) == 3 and s[0].startswith("MAE"):
            try:
                rows.append((s[0], float(s[1]), float(s[2])))
            except ValueError:
                continue
    if not rows:
        return _unsupported("mae", path, "no MAE rows")
    easy = min(rows, key=lambda r: r[2])
    mae_mev = max(r[2] for r in rows)
    return {"kind": "mae", "values": {
        "easy_axis": easy[0], "mae_meV": round(mae_mev, 4),
        "axes": {r[0]: r[2] for r in rows}},
        "units": {"mae_meV": "meV"}, "source": str(path), "sha256": sha(path)}


# ------------------------------------------------------------ thermo.dat ----
def thermo(path):
    rows = []
    header = None
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.startswith("#"):
            header = line
            continue
        s = line.split()
        if len(s) >= 4:
            try:
                rows.append([float(x) for x in s])
            except ValueError:
                continue
    if not rows:
        return _unsupported("thermo", path, "no table rows")
    # thermo.dat is the only 5+ column table qvasp writes, and its first column
    # is a temperature in K. Anything else (EIGENVAL, a lattice, POSCAR) would
    # otherwise be reported as a thermodynamic table.
    if len(rows[0]) < 5:
        return _unsupported("thermo", path,
                            f"table has {len(rows[0])} columns; thermo.dat has 5 "
                            "(T, ZPE, H, T*S, G)")
    temps = [r[0] for r in rows]
    if min(temps) < 0.0 or max(temps) > 5000.0:
        return _unsupported(
            "thermo", path,
            f"first column ranges {min(temps):.1f}..{max(temps):.1f}; a temperature "
            "column must be positive and below 5000 K")
    arr = np.array(rows)
    return {"kind": "thermo", "values": {
        "rows": int(arr.shape[0]), "columns": int(arr.shape[1]),
        "first_row": arr[0].tolist(), "last_row": arr[-1].tolist()},
        "units": {}, "header": (header or "")[:200], "source": str(path), "sha256": sha(path)}


# ---------------------------------------------------------------- RDF.dat ---
def rdf_first_peak(path):
    rows = []
    has_header = False
    for line in Path(path).read_text(errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            low = stripped.lower()
            if "r(" in low.replace(" ", "") or "g(r)" in low or "rdf" in low:
                has_header = True
            continue
        s = stripped.split()
        if len(s) >= 2:
            try:
                rows.append((float(s[0]), float(s[1])))
            except ValueError:
                continue
    if len(rows) < 5:
        return _unsupported("rdf_first_peak", path, "too few rows")
    # g(r) starts at 0 for r -> 0 and approaches 1 at large r; a generic numeric
    # file usually does not. r must also start near zero and increase.
    if rows[0][0] > 0.5:
        return _unsupported(
            "rdf_first_peak", path,
            f"first column starts at {rows[0][0]:.3f}; an RDF runs from r = 0")
    if not (0.0 <= rows[0][1] <= 0.5) or not has_header:
        return _unsupported(
            "rdf_first_peak", path,
            "not an RDF table (needs an r/g(r) header and g(r -> 0) near zero)")
    r = np.array([x[0] for x in rows])
    g = np.array([x[1] for x in rows])
    i = int(np.argmax(g))
    return {"kind": "rdf_first_peak", "values": {
        "first_peak_r": round(float(r[i]), 3), "first_peak_g": round(float(g[i]), 3)},
        "units": {"first_peak_r": "Angstrom"}, "source": str(path), "sha256": sha(path)}


PARSERS = {
    "band_gap": band_gap,
    "dos_at_ef": dos_at_ef,
    "phonon_min": phonon_min,
    "mae": mae,
    "thermo": thermo,
    "rdf_first_peak": rdf_first_peak,
}


def extract(kind, path):
    if kind in PARSERS:
        return PARSERS[kind](path)
    return _unsupported(kind, path, f"no parser for {kind}; known: {sorted(PARSERS)}")
