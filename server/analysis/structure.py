"""Structure sanity checks: symmetry, coordination, bond lengths, vacuum.

Everything is computed from the POSCAR itself; nothing is taken from a log.
Findings are returned as a list so the caller can print or gate on them.
"""
from pathlib import Path

import numpy as np

MASS = {"H": 1.008, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998,
        "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
        "S": 32.06, "Cl": 35.45, "K": 39.098, "Ca": 40.078, "Ti": 47.867,
        "V": 50.942, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845, "Co": 58.933,
        "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Sr": 87.62, "Mo": 95.95,
        "Bi": 208.980, "Te": 127.60, "Se": 78.971, "Ge": 72.630, "Ga": 69.723}

COVALENT = {"H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
            "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07, "S": 1.05,
            "Cl": 1.02, "K": 2.03, "Ca": 1.76, "Ti": 1.60, "V": 1.53, "Cr": 1.39,
            "Mn": 1.39, "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22,
            "Sr": 1.95, "Mo": 1.54, "Bi": 1.48, "Te": 1.38, "Se": 1.20,
            "Ge": 1.20, "Ga": 1.22}


def read_poscar(path):
    L = Path(path).read_text(errors="replace").splitlines()
    scale = float(L[1].split()[0])
    cell = np.array([[float(x) for x in L[i].split()[:3]] for i in (2, 3, 4)]) * scale
    species = L[5].split()
    counts = [int(x) for x in L[6].split()]
    nat = sum(counts)
    start = 8
    if L[7].strip()[:1].lower() == "s":
        start = 9
    direct = L[start - 1].strip()[:1].lower() in ("d", "")
    raw = np.array([[float(x) for x in L[start + i].split()[:3]] for i in range(nat)])
    frac = raw if direct else raw @ np.linalg.inv(cell)
    symbols = []
    for s, c in zip(species, counts):
        symbols += [s] * c
    return {"cell": cell, "frac": frac, "symbols": symbols, "nat": nat,
            "species": species, "counts": counts}


def _min_image_distances(frac, cell, i):
    """All distances from atom i to every atom (and its periodic images)."""
    d = frac - frac[i]
    d -= np.round(d)
    out = []
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            for c in (-1, 0, 1):
                out.append(np.linalg.norm((d + np.array([a, b, c])) @ cell, axis=1))
    return np.array(out)


def check(path, symprec=1e-3, vacuum_warn=10.0):
    s = read_poscar(path)
    cell, frac, symbols, nat = s["cell"], s["frac"], s["symbols"], s["nat"]
    volume = abs(np.linalg.det(cell))
    lengths = np.linalg.norm(cell, axis=1)
    findings = []

    masses = np.array([MASS.get(x, 12.0) for x in symbols])
    density = masses.sum() / 0.602214076 / volume  # g/cm^3

    # ---- neighbour distances
    # A coordination *number* needs chemistry (covalent radii fail for ionic
    # crystals: Sr-O 2.68 A and Sr-Ti 3.44 A are both "bonded" by that rule).
    # So this reports the nearest-neighbour distance list per atom and flags
    # only unambiguous defects: overlaps (< 0.6 A) and isolated atoms (nothing
    # within 3.0 A). The distances are the evidence; the user reads the shell.
    nearest = []
    all_nn = []
    for i in range(nat):
        pairs = []
        for j in range(nat):
            base = frac[j] - frac[i]
            for a in (-1, 0, 1):
                for b in (-1, 0, 1):
                    for c in (-1, 0, 1):
                        r = float(np.linalg.norm((base + np.array([a, b, c])) @ cell))
                        if r > 0.3:
                            pairs.append((round(r, 3), symbols[j]))
        pairs.sort()
        uniq = []
        for r, sym in pairs:
            if not uniq or abs(r - uniq[-1][0]) > 0.05:
                uniq.append((r, sym))
        nearest.append([{"d": r, "to": sym} for r, sym in uniq[:6]])
        if uniq:
            all_nn.append(uniq[0][0])
        if not uniq or uniq[0][0] > 3.0:
            findings.append(f"atom {i + 1} ({symbols[i]}) has no neighbour within 3.0 A")
        elif uniq[0][0] < 0.6:
            findings.append(f"atom {i + 1} ({symbols[i]}) overlaps a neighbour at "
                            f"{uniq[0][0]:.3f} A")

    # ---- overlapping atoms (explicit pair check, independent of the shells)
    for i in range(nat):
        for j in range(i + 1, nat):
            r = np.linalg.norm((frac[j] - frac[i] - np.round(frac[j] - frac[i])) @ cell)
            if r < 0.5:
                findings.append(f"atoms {i + 1}/{j + 1} are {r:.3f} A apart — overlapping")

    # ---- vacuum: only meaningful for a cell that is periodic in 2D or 0D
    vacuum = {}
    for axis, name in enumerate("abc"):
        z = np.sort(frac[:, axis] % 1.0)
        gaps = np.diff(np.concatenate([z, [z[0] + 1.0]]))
        vacuum[name] = float(gaps.max() * lengths[axis])
    maxvac = max(vacuum.values())
    if vacuum_warn * 0.4 <= maxvac < vacuum_warn:
        findings.append("largest empty gap is only %.2f A (axis %s): a slab or molecule "
                        "needs more vacuum" % (maxvac, max(vacuum, key=vacuum.get)))

    # ---- symmetry
    sg = None
    try:
        import spglib
        numbers = []
        for sym in symbols:
            numbers.append({"Sr": 38, "Ti": 22, "O": 8, "C": 6, "N": 7, "Si": 14,
                            "H": 1, "Bi": 83, "Te": 52, "Co": 27, "Fe": 26}.get(sym, 6))
        ds = spglib.get_symmetry_dataset((cell, frac, numbers), symprec=symprec)
        if ds:
            sg = {"number": int(ds.number), "symbol": ds.international,
                  "n_operations": len(ds.rotations)}
    except Exception as exc:  # pragma: no cover - spglib optional
        findings.append(f"symmetry check skipped: {type(exc).__name__}")

    return {
        "file": str(path),
        "natoms": nat,
        "formula": "".join(f"{s}{c}" for s, c in zip(s["species"], s["counts"])),
        "volume_A3": round(float(volume), 4),
        "lattice_lengths": [round(float(x), 4) for x in lengths],
        "density_g_cm3": round(float(density), 4),
        "symmetry": sg,
        "nearest_neighbours": nearest,
        "nearest_nn_min_A": round(float(min(all_nn)), 4) if all_nn else None,
        "nearest_nn_max_A": round(float(max(all_nn)), 4) if all_nn else None,
        "vacuum_A": {k: round(v, 3) for k, v in vacuum.items()},
        "findings": findings,
        "ok": not findings,
    }
