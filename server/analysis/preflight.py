"""Pre-submission checks for a VASP case directory.

Everything here is a check that can be made from the input files alone, before any
CPU time is spent. The value of the module is that it says *why* a check exists and
what to do, so a bad input is caught in a second instead of after two hours of
a job that "finished" on the wrong answer.

Levels: ``error`` means the run is wrong or will not start; ``warning`` means it may
still be right but the reason has to be known. Nothing here is a physics opinion —
those live in the skill's references.
"""
from pathlib import Path

from . import structure

# ---------------------------------------------------------------- INCAR tags --
# Tags that VASP accepts. An unknown tag is *silently ignored*, which is why a
# typo turns into "the setting had no effect" rather than an error message.
KNOWN_TAGS = {
    "SYSTEM", "PREC", "ENCUT", "ENINI", "ENAUG", "EDIFF", "EDIFFG", "NELM", "NELMIN",
    "NELMDL", "ISMEAR", "SIGMA", "ISYM", "SYMPREC", "IBRION", "ISIF", "NSW", "POTIM",
    "NFREE", "IWAVPR", "ICHARG", "INIWAV", "ISPIN", "MAGMOM", "NUPDOWN", "LDAU",
    "LDAUTYPE", "LDAUL", "LDAUU", "LDAUJ", "LDAUPRINT", "LMAXMIX", "LASPH", "LMONO",
    "LFERMI", "LREAL", "ROPT", "LOPTICS", "NBANDS", "LBLUEOUT", "LCHARG", "LWAVE",
    "LVTOT", "LVHAR", "LELF", "LAECHG", "LORBIT", "RWIGS", "NEDOS", "EMIN", "EMAX",
    "ISMER", "KPAR", "NCORE", "NSIM", "NPAR", "LPLANE", "LSCALAPACK", "LSCALU",
    "ALGO", "IALGO", "LHFCALC", "HFSCREEN", "AEXX", "AGGAX", "AGGAC", "ALDAC",
    "PRECFOCK", "NKRED", "LMAXFOCK", "LDIAG", "GGA", "METAGGA", "CMBJ", "PARAM1",
    "PARAM2", "LUSE_VDW", "IVDW", "VDW_RADIUS", "VDW_SCALING", "VDW_D", "VDW_C6",
    "VDW_R0", "BPARAM", "CPARAM", "LVDW_EWALD", "ADDGRID", "PSTRESS", "EFIELD",
    "EFIELD_PEAD", "LSORBIT", "LMAXPAW", "AMIX", "AMIX_MAG", "BMIX", "BMIX_MAG",
    "WC", "INIMIX", "MIXPRE", "MAXMIX", "LDIPOL", "IDIPOL", "DIPOL", "LMONO",
    "LCOLD", "LTMP2", "KPOINTS_OPT", "IGPAR", "NPPSTR", "LPEAD", "LCALCEPS",
    "LEPSILON", "LCLIMB", "ISIF", "LBLUEOUT", "SIGMA", "LSCALAPACK", "NCONVC",
    "NBLK", "KBLOCK", "LCHGUESS", "ISTART", "LDOWNSAMPLE", "TEBEG", "TEEND",
    "SMASS", "MDALGO", "ANDERSEN_PROB", "LANGEVIN_GAMMA", "LANGEVIN_GAMMA_L",
    "PMASS", "POMASS", "NBLOCK", "KSPACING", "KGAMMA", "LOPTICS", "CSHIFT",
    "NALGO", "WEIMIN", "EBREAK", "DEPER", "TIME", "LCHARG", "LEPSILON",
    # output volume and the less common but perfectly real tags
    "NWRITE", "LORBMOM", "LOCPROJ", "GGA_COMPAT", "LSPECTRAL", "ANTIRES",
    "LNABLA", "LNONCOLLINEAR", "LMLSF", "LSYNCH", "NOMEGA", "ENCUTGW",
    "NBANDSGW", "LTRIPLET", "LSINGLES", "AEXX", "NBSEEIG", "LWRITE_SPINOR",
    "LWRITE_MMN_AMN", "LPEAD", "LCALCPOL", "LCALCEPS", "EFIELD_PEAD",
    # Vosko-Wilk-Nusair correlation and the mixing/low-level switches that show
    # up in older hand-written INCARs
    "VOSKOWN", "LMIXTAU", "IMIX", "LINT", "LTCTE", "LTETE", "LPADE", "MIXPRE",
}

# Tags that look plausible and are simply not VASP tags. They are the expensive
# kind of mistake: VASP parses them, ignores them, and the run is not what it says.
FAKE_TAGS = {"EXT_PRES", "EXTPRES", "PRESS", "PRESSURE", "LVDW", "IVDW_NL",
             "KPOINTS", "POTCAR", "NELM_MAX", "ISMEAR_DOS"}

SUFFIXES = ("_sv", "_pv", "_gw", "_h", "_s", "_d", "_3", "_2", "_1", "_of")


def _tokens(value):
    """Expand VASP's ``4*5.0`` repeat notation into a flat list of strings."""
    out = []
    for tok in value.replace(",", " ").split():
        if "*" in tok:
            n, _, v = tok.partition("*")
            try:
                out += [v] * int(n)
            except ValueError:
                out.append(tok)
        else:
            out.append(tok)
    return out


def read_incar(path):
    """Return ``(tags, duplicates)``; later duplicates win, as in VASP."""
    tags, dups, order = {}, [], []
    for raw in Path(path).read_text(errors="replace").splitlines():
        line = raw.split("#")[0].split("!")[0].strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().upper()
        val = val.split("#")[0].split("!")[0].strip()
        if not key:
            continue
        if key in tags:
            dups.append(key)
        else:
            order.append(key)
        tags[key] = val
    return tags, dups, order


def _suggest(key, pool):
    """The tag in ``pool`` that ``key`` was most likely meant to be, or None.

    A misspelt INCAR tag is the worst kind of input bug: VASP ignores unknown tags
    without a word, so 'KSPCACING = 0.1' looks like a convergence setting and does
    nothing at all. Naming the intended tag is the difference between a warning the
    user acts on and one they scroll past.
    """
    import difflib
    hit = difflib.get_close_matches(key, pool, n=1, cutoff=0.72)
    return hit[0] if hit else None


def _num(tags, key, default=None):
    try:
        return float(_tokens(tags[key])[0])
    except (KeyError, IndexError, ValueError):
        return default


def _ints(tags, key):
    try:
        return [int(round(float(x))) for x in _tokens(tags[key])]
    except (KeyError, ValueError):
        return None


def read_potcar(path):
    """Element names, ENMAX and ZVAL from the TITEL/ENMAX/ZVAL lines of a POTCAR."""
    names, enmax, zval = [], [], []
    for raw in Path(path).read_text(errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("TITEL"):
            parts = line.split("=", 1)[-1].split()
            # PAW_PBE Ba_sv 06Sep2000  ->  the element is the last non-date token
            elem = None
            for tok in parts:
                if tok.lower().startswith("paw") or tok.lower() in ("us", "nc", "ae"):
                    continue
                if any(ch.isdigit() for ch in tok) and "-" not in tok:
                    continue
                elem = tok
                break
            names.append(elem or (parts[-1] if parts else "?"))
        elif line.startswith("ENMAX"):
            try:
                enmax.append(float(line.split("=")[1].split(";")[0].strip()))
            except (IndexError, ValueError):
                pass
        elif line.startswith("ZVAL"):
            try:
                zval.append(float(line.split("=")[1].split()[0]))
            except (IndexError, ValueError):
                pass
    return {"elements": names, "enmax": enmax, "zval": zval}


def _bare(name):
    low = name.lower()
    for suf in SUFFIXES:
        if low.endswith(suf):
            return low[: -len(suf)]
    return low


def check_kpoints(path):
    """Return findings for a KPOINTS file: format, grid integers, line-mode points.

    Three formats exist and all three appear in real inputs:
      * a Gamma/Monkhorst grid          4-6 lines, integers on line 4
      * a line-mode path                points on line 2, endpoints in pairs
      * an explicit k-point list        count on line 2, 'rec'/'cart' on line 3,
                                        then one row of 4 numbers per k-point
    A checker that knows only the first two rejects perfectly good files, so the
    explicit list is handled here too.
    """
    out = []
    L = [x.rstrip() for x in Path(path).read_text(errors="replace").splitlines()]
    if not any(x.strip() for x in L):
        return [("error", "kpoints-empty", "KPOINTS is empty",
                 "write one, e.g. 'qvasp -k 0.03'")]
    if len(L) < 4:
        return [("error", "kpoints-length",
                 f"KPOINTS has {len(L)} lines; the shortest valid file has 4", "rewrite KPOINTS")]
    style = L[2].strip()[:1].lower()
    if style == "l":
        # line mode: points per segment live on line 2 (the "scale" slot)
        try:
            nseg_points = int(float(L[1].split()[0]))
        except (IndexError, ValueError):
            nseg_points = 0
        has_recip = "reciprocal" in " ".join(L[3:6]).lower()
        if not has_recip:
            out.append(("error", "kpoints-reciprocal",
                        "line-mode KPOINTS has no 'Reciprocal' line; the first endpoint is "
                        "consumed as the coordinate-system statement and the path silently "
                        "starts at the second point",
                        "insert a 'Reciprocal' line directly after the 'Line-mode' line"))
        if nseg_points < 1:
            out.append(("error", "kpoints-points",
                        f"points per segment reads as {nseg_points}; it belongs on line 2 "
                        "(the scale slot), not line 4",
                        "put the integer on line 2"))
        if nseg_points > 200:
            out.append(("warning", "kpoints-points",
                        f"{nseg_points} points per segment is far more than needed",
                        "20-40 is usual"))
        # The coordinate-system line is not an endpoint. Counting it made every
        # valid line-mode file look like it had an odd number of endpoints.
        body = [x for x in L[4 if has_recip else 3:]
                if x.strip() and not x.strip().startswith(("#", "!"))]
        if len(body) % 2:
            out.append(("error", "kpoints-endpoints",
                        "line-mode has an odd number of coordinate lines; endpoints must come "
                        "in pairs", "each segment needs its two endpoints"))
    elif style in ("r", "c"):
        # explicit list: NKPTS on line 2, coordinate system on line 3
        try:
            nk = int(float(L[1].split()[0]))
        except (IndexError, ValueError):
            nk = None
            out.append(("error", "kpoints-count",
                        f"the k-point count on line 2 reads {L[1].strip()[:20]!r}; an explicit "
                        "list needs the number of k-points there",
                        "put the integer count on line 2"))
        body = [x for x in L[3:]
                if x.strip() and not x.strip().startswith(("#", "!"))
                and len(x.split()) >= 3]
        if nk is not None and nk != len(body):
            out.append(("error", "kpoints-count",
                        f"line 2 promises {nk} k-points but the file lists {len(body)}; VASP "
                        "reads exactly the promised number and silently takes garbage or "
                        "stops early",
                        "make the count match the rows"))
    elif style in ("g", "m"):
        grid = L[3].split()[:3]
        try:
            vals = [float(x) for x in grid]
        except ValueError:
            vals = []
        if len(vals) != 3:
            out.append(("error", "kpoints-grid", "the grid line does not have three numbers",
                        "write three integers, e.g. '16 16 16'"))
        elif any(abs(v - round(v)) > 1e-9 for v in vals):
            out.append(("error", "kpoints-grid-int",
                        f"grid {grid} is not integral. A k-mesh written as a density "
                        "('0.1 0.1 0.1') parses as zero k-points, VASP does not complain and "
                        "the job idles at full load for hours",
                        "write integers; use 'qvasp -k 0.03' to get them"))
        elif any(round(v) < 1 for v in vals):
            out.append(("error", "kpoints-grid-int", "a grid entry is below 1", "use >= 1"))
        # Fortran list-directed READ continues on the same record, so writing the
        # shift on the grid line ('16 16 16 0 0 0') is legal and appears in real
        # input. Only complain when the whole shift is missing.
        if style == "g" and len(L) < 5 and len(L[3].split()) < 6:
            out.append(("error", "kpoints-gamma",
                        "Gamma-only KPOINTS has no shift: give three numbers after the grid "
                        "(on the same line or on the next one)",
                        "append '0 0 0'"))
    else:
        out.append(("error", "kpoints-style",
                    f"unknown KPOINTS style {L[2].strip()[:20]!r}; expected a line starting "
                    "with 'L' (line mode), 'G' (Gamma), 'M' (Monkhorst-Pack) or 'R'/'C' "
                    "(an explicit k-point list in reciprocal or Cartesian coordinates)",
                    "rewrite the third line"))
    return out


def read_kmesh(path):
    """Return the k-point count of a Gamma/Monkhorst grid, or None if not a valid grid.

    A density written as '0.1 0.1 0.1' is not a grid: VASP reads NKPTS = 0 and runs
    for hours without a complaint, so None here means "cannot be trusted as a count".
    """
    try:
        L = [x.rstrip() for x in Path(path).read_text(errors="replace").splitlines()]
        if len(L) < 4 or L[2].strip()[:1].lower() not in ("g", "m"):
            return None
        vals = [float(x) for x in L[3].split()[:3]]
        if len(vals) != 3 or any(abs(v - round(v)) > 1e-9 for v in vals) \
                or any(round(v) < 1 for v in vals):
            return None
        return int(round(vals[0]) * round(vals[1]) * round(vals[2]))
    except (OSError, IndexError, ValueError):
        return None


def check(cwd, potcar="POTCAR", poscar="POSCAR", incar="INCAR", kpoints="KPOINTS"):
    """Run every pre-submission check on a case directory."""
    d = Path(cwd)
    found = []          # (level, check, message, fix)
    skipped = []

    def add(level, name, msg, fix=""):
        found.append((level, name, msg, fix))

    # ---- required files
    # POSCAR is the one file every check needs. The other three are only
    # required for a *run*: a k-point generation case or a post-processing case
    # legitimately holds nothing but a structure, so their absence is reported
    # and the dependent checks are skipped instead of failing the directory.
    if not (d / poscar).exists():
        add("error", "missing-file", f"{poscar} is not in {d}", f"create {poscar}")
    for name, why in ((potcar, "potential metadata (species order, ENMAX, ZVAL)"),
                      (incar, "the settings a run would use"),
                      (kpoints, "the k-mesh a run would use")):
        if not (d / name).exists():
            add("warning", "missing-file",
                f"{name} is not in {d}: {why} cannot be checked, and this directory is not "
                "a complete run directory",
                f"add {name} if this case is meant to be submitted as it stands")

    # ---- structure
    nat, species, counts = None, None, None
    if (d / poscar).exists():
        try:
            s = structure.read_poscar(d / poscar)
            nat, species, counts = s["nat"], s["species"], s["counts"]
        except Exception as exc:
            add("error", "poscar-parse", f"{poscar} could not be read: {exc}",
                "check the scale line and the coordinate block length")
        else:
            if len(s["symbols"]) != nat:
                add("error", "poscar-count",
                    "the coordinate block is shorter than the atom counts promise",
                    "count the lines")

    # ---- POTCAR: species order is the silent killer
    pot = None
    if (d / potcar).exists():
        pot = read_potcar(d / potcar)
        if not pot["elements"]:
            add("error", "potcar-empty", "no TITEL line in POTCAR",
                "rebuild it with 'qvasp -pbe <elements>'")
        elif species:
            if len(pot["elements"]) != len(species):
                add("error", "potcar-count",
                    f"POTCAR has {len(pot['elements'])} potentials "
                    f"({', '.join(pot['elements'])}) but POSCAR has {len(species)} species "
                    f"({', '.join(species)})",
                    "concatenate one POTCAR per species, in POSCAR order")
            else:
                bad = [(a, b) for a, b in zip(species, pot["elements"])
                       if _bare(a) != _bare(b)]
                if bad:
                    pairs = ", ".join(f"POSCAR {a} vs POTCAR {b}" for a, b in bad)
                    add("error", "potcar-order",
                        f"species and potential order disagree: {pairs}. This converges "
                        "cleanly and gives a wrong material",
                        "reorder POTCAR (or the POSCAR species line) so the lists match")
            if pot["zval"] and nat:
                pass  # NELECT is informational, not a gate

    tags, dups, order = ({}, [], [])
    if (d / incar).exists():
        try:
            tags, dups, order = read_incar(d / incar)
        except Exception as exc:
            add("error", "incar-parse", f"{incar} could not be read: {exc}", "")

    # ---- unknown / fake tags
    for key in order:
        if key in FAKE_TAGS:
            add("error", "incar-fake-tag",
                f"{key} is not a VASP tag. VASP ignores unknown tags silently, so the run "
                "does what it would have done without it"
                + (" (external pressure is set by PSTRESS in kB, 1 GPa = 10 kB)"
                   if key in ("EXT_PRES", "EXTPRES") else ""),
                "use the real tag name")
        elif key not in KNOWN_TAGS:
            hint = _suggest(key, KNOWN_TAGS)
            add("warning", "incar-unknown-tag",
                f"{key} is not a VASP tag; VASP ignores it without a message"
                + (f" — did you mean {hint}?" if hint else
                   " (check the spelling: 'KSPCACING' for 'KSPACING' is the classic one)"),
                f"rename it to {hint}" if hint else "verify the spelling")

    for key in dups:
        add("warning", "incar-duplicate",
            f"{key} appears more than once; the last value wins, which is not always the "
            "one you meant", "keep one line per tag")

    # ---- ENCUT against the potentials actually present
    encut = _num(tags, "ENCUT")
    if tags:
        if encut is None:
            add("warning", "encut-missing",
                "no ENCUT: VASP falls back to the largest ENMAX of the potentials, which is "
                "usually too soft to be comparable with another run", "set ENCUT explicitly")
        elif pot and pot["enmax"]:
            top = max(pot["enmax"])
            if encut < top:
                add("error", "encut-low",
                    f"ENCUT = {encut:g} eV is below the largest ENMAX in POTCAR "
                    f"({top:g} eV): the hard species is under-converged and the energy is "
                    "not comparable with anything", f"set ENCUT >= {top:g}, usually "
                    f"{1.3 * top:.0f}")
            elif encut < 1.2 * top:
                add("warning", "encut-tight",
                    f"ENCUT = {encut:g} eV is only {encut / top:.2f} x the largest ENMAX "
                    f"({top:g} eV)", "1.3 x is the usual target")

    # ---- smearing vs task
    ismear = _num(tags, "ISMEAR")
    ibrion = _num(tags, "IBRION", -1)
    nsw = _num(tags, "NSW", 0)
    moving = (ibrion is not None and ibrion > 0) or (nsw and nsw > 0)
    if ismear is not None and int(ismear) == -5 and moving:
        add("error", "ismear-tetra-relax",
            "ISMEAR = -5 (tetrahedron) during a relaxation or MD: the tetrahedron forces "
            "are not variational, so the relaxation crawls or fails",
            "use ISMEAR = 0 with a small SIGMA while the geometry moves, -5 for the final "
            "static run")
    if ismear is not None and int(ismear) == -5:
        nk = read_kmesh(d / kpoints) if (d / kpoints).exists() else None
        # nk is None when the grid is unreadable, which check_kpoints already
        # reports; repeating it here as "0 k-points" would blame the wrong thing.
        if nk is not None and nk < 4:
            add("warning", "ismear-tetra-kpoints",
                f"ISMEAR = -5 with only {nk} k-points: the tetrahedron method needs more",
                "use ISMEAR = 0 or densify the mesh")

    # ---- electronic loop headroom
    nelm = _num(tags, "NELM")
    if nelm is not None and nelm <= 20:
        hard = (_num(tags, "LDAU") is not None and
                str(tags.get("LDAU", "")).lower().startswith(".t")) or \
               (_num(tags, "ISPIN") == 2)
        add("warning" if not hard else "error", "nelm-small",
            f"NELM = {nelm:g} is small"
            + (" and this run is magnetic/+U, where the first SCF often needs 60-100 steps"
               if hard else ""),
            "raise NELM to 100-200 rather than accept an unconverged run")

    # ---- magnetism arrays
    if nat and "MAGMOM" in tags:
        vals = _tokens(tags["MAGMOM"])
        if len(vals) != nat:
            add("error", "magmom-length",
                f"MAGMOM has {len(vals)} entries for {nat} atoms",
                "one entry per atom in POSCAR order (or use '4*5.0' notation)")
    if str(tags.get("LDAU", "")).lower().startswith(".t") and species:
        lens = {}
        for key in ("LDAUL", "LDAUU", "LDAUJ"):
            lens[key] = len(_tokens(tags.get(key, "")))
        wrong = {k: v for k, v in lens.items() if v != len(species)}
        if wrong:
            detail = ", ".join(f"{k}={v}" for k, v in wrong.items())
            add("error", "ldau-length",
                f"+U arrays must have one entry per POSCAR species ({len(species)}); "
                f"{detail}",
                "size every LDAU* array to the species list of this calculation, even "
                "the species that get no U (-1 / 0.0)")
        lmax = _num(tags, "LMAXMIX")
        if lmax is None:
            add("warning", "ldau-lmaxmix",
                "+U without LMAXMIX: the density mixing is truncated and convergence "
                "degrades", "LMAXMIX = 4 for d, 6 for f")

    # ---- restarts that need a file
    icharg = _num(tags, "ICHARG")
    if icharg is not None and int(icharg) >= 10:
        chg = d / "CHGCAR"
        outcar = d / "OUTCAR"
        archived = outcar.exists() and outcar.stat().st_size > 1000
        if not chg.exists():
            # Two very different situations look identical here. A directory that
            # already holds an OUTCAR is an archive of a finished run: the CHGCAR
            # was there when it ran and was not kept. A directory with no OUTCAR is
            # about to be submitted, and VASP will start from a superposition while
            # holding the charge fixed — silently the wrong calculation.
            if archived:
                add("warning", "icharg-no-chgcar",
                    f"ICHARG = {int(icharg)} and no CHGCAR: this directory looks like an "
                    f"archive of a finished run ({outcar.name} is present), so the density "
                    "was there when it ran and is simply not kept here",
                    "nothing to do if you are only reading results; copy the CHGCAR in if "
                    "you want to rerun it")
            else:
                add("error", "icharg-no-chgcar",
                    f"ICHARG = {int(icharg)} needs a CHGCAR in {d}, and there is none",
                    "copy the CHGCAR of the converging SCF run first")
        elif chg.stat().st_size < 10000:
            add("error", "icharg-empty-chgcar",
                f"CHGCAR is only {chg.stat().st_size} bytes: VASP creates an empty CHGCAR "
                "when it starts, so this is the residue of a crashed run, not a density",
                "copy the real CHGCAR (a 2-atom cell is ~1 MB)")
        else:
            add("warning", "icharg-encut",
                "ICHARG >= 10: the reading run must use the same ENCUT and FFT grid as the "
                "run that wrote the CHGCAR, or VASP aborts", "keep ENCUT identical")

    # ---- dispersion / +U / hybrid combinations that are known-broken
    addgrid = str(tags.get("ADDGRID", "")).lower()
    if addgrid.startswith(".t") and ("IVDW" in tags or
                                     str(tags.get("LUSE_VDW", "")).lower().startswith(".t")):
        add("error", "addgrid-vdw",
            "ADDGRID = .TRUE. is not supported with dispersion corrections: VASP aborts "
            "with 'I REFUSE TO CONTINUE WITH THIS SICK JOB'",
            "remove ADDGRID")
    metagga = str(tags.get("METAGGA", "")).strip().upper()
    if metagga and metagga not in ("", "NONE") and str(tags.get("LUSE_VDW", "")).lower().startswith(".t") \
            and _num(tags, "IVDW") in (202.0, 202):
        add("error", "vdw-double-count",
            "LUSE_VDW picks the rVV10 kernel and IVDW = 202 is MBD@rsSCS: enabling both "
            "counts dispersion twice",
            "for SCAN+rVV10 use METAGGA=SCAN LUSE_VDW=.TRUE. BPARAM=15.7 CPARAM=0.0093 and "
            "no IVDW line")
    if str(tags.get("LHFCALC", "")).lower().startswith(".t"):
        ncore = _num(tags, "NCORE")
        if ncore is not None and ncore > 1:
            add("warning", "hybrid-ncore",
                f"hybrid functional with NCORE = {ncore:g}: many VASP builds abort on such "
                "a layout", "NCORE = 1 for hybrids")

    # ---- ISIF / ENCUT combinations
    isif = _num(tags, "ISIF")
    if isif == 3 and encut is not None and pot and pot["enmax"] and encut < 1.1 * max(pot["enmax"]):
        add("warning", "isif3-encut",
            "cell relaxation (ISIF = 3) with a cutoff near the ENMAX floor: Pulay stress "
            "biases the volume", "ENCUT >= 1.3 x max(ENMAX) when the cell moves")

    # ---- selective dynamics survived the round trip
    if (d / poscar).exists():
        try:
            L = (d / poscar).read_text(errors="replace").splitlines()
            if len(L) > 7 and L[7].strip().lower().startswith("s"):
                flags = [x.split()[3:6] for x in L[9:9 + (nat or 0)] if len(x.split()) >= 6]
                frozen = sum(1 for f in flags if all(t.upper().startswith("F") for t in f))
                if frozen and frozen == len(flags):
                    add("warning", "selective-all-fixed",
                        "selective dynamics is on and every atom is fixed",
                        "leave the mobile atoms as T T T")
        except Exception:
            pass

    # ---- the k-point file itself
    if (d / kpoints).exists():
        try:
            for level, name, msg, fix in check_kpoints(d / kpoints):
                add(level, name, msg, fix)
        except Exception as exc:
            add("warning", "kpoints-parse",
                f"{kpoints} could not be read: {exc}",
                "the file must be 4-5 lines: comment, 0, style, grid, shift")

    # ---- parallel layout
    if "NPAR" in tags and "NCORE" in tags:
        add("warning", "parallel-both",
            "both NPAR and NCORE are set; NCORE wins and NPAR is ignored")

    counts_by_level = {}
    for level, name, msg, fix in found:
        counts_by_level[level] = counts_by_level.get(level, 0) + 1
    return {
        "cwd": str(d),
        "ok": counts_by_level.get("error", 0) == 0,
        "errors": counts_by_level.get("error", 0),
        "warnings": counts_by_level.get("warning", 0),
        "findings": [{"level": lv, "check": nm, "message": ms, "fix": fx}
                     for lv, nm, ms, fx in found],
        "not_checked": skipped or [
            "physics (functional, convergence of the quantity, choice of reference)",
            "walltime and queue limits",
            "whether the geometry is the one you meant to study",
        ],
    }
