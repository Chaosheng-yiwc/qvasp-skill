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
def band_gap(path):
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        s = line.split()
        if len(s) >= 2:
            try:
                rows.append((float(s[0]), float(s[1])))
            except ValueError:
                continue
    if not rows:
        return _unsupported("band_gap", path, "no numeric columns")
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


# ----------------------------------------------------------------- DOSCAR ----
def dos_at_ef(path, ef=None):
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return _unsupported("dos_at_ef", path, "missing")
    if len(lines) < 7:
        return _unsupported("dos_at_ef", path, "too short for DOSCAR")
    head = lines[5].split()
    try:
        nat, _, _, nedos, fermi = int(head[0]), float(head[1]), float(head[2]), int(head[3]), float(head[4])
    except (IndexError, ValueError):
        return _unsupported("dos_at_ef", path, "DOSCAR header not recognised")
    ef = fermi if ef is None else ef
    total = []
    for line in lines[6:6 + nedos]:
        s = line.split()
        if len(s) < 3:
            continue
        try:
            total.append((float(s[0]), float(s[1]) + (float(s[2]) if len(s) > 2 else 0.0)))
        except ValueError:
            continue
    if not total:
        return _unsupported("dos_at_ef", path, "no DOS rows")
    e = np.array([r[0] for r in total])
    d = np.array([r[1] for r in total])
    n_ef = float(np.interp(ef, e, d))
    return {"kind": "dos_at_ef", "values": {
        "fermi_eV": round(ef, 4), "dos_at_ef": round(n_ef, 4),
        "dos_max": round(float(d.max()), 4), "points": int(len(e))},
        "units": {"dos_at_ef": "states/eV"}, "source": str(path), "sha256": sha(path)}


# ------------------------------------------------------- phonon band dat ----
def phonon_min(path):
    freq = []
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.strip().startswith("#"):
            continue
        s = line.split()
        if len(s) >= 2:
            try:
                freq.append(float(s[1]))
            except ValueError:
                continue
    if not freq:
        return _unsupported("phonon_min", path, "no frequencies")
    f = np.array(freq)
    gamma = [v for v in f[:12]]
    return {"kind": "phonon_min", "values": {
        "min_cm1": round(float(f.min()), 3),
        "max_cm1": round(float(f.max()), 3),
        "imaginary_count": int((f < -1e-6).sum()),
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
    arr = np.array(rows)
    return {"kind": "thermo", "values": {
        "rows": int(arr.shape[0]), "columns": int(arr.shape[1]),
        "first_row": arr[0].tolist(), "last_row": arr[-1].tolist()},
        "units": {}, "header": (header or "")[:200], "source": str(path), "sha256": sha(path)}


# ---------------------------------------------------------------- RDF.dat ---
def rdf_first_peak(path):
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.strip().startswith("#"):
            continue
        s = line.split()
        if len(s) >= 2:
            try:
                rows.append((float(s[0]), float(s[1])))
            except ValueError:
                continue
    if len(rows) < 5:
        return _unsupported("rdf_first_peak", path, "too few rows")
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
