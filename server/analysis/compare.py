"""Compare a computed value with a reference record and classify the deviation.

The classification distinguishes

  consistent   within the method's expected error (or the experimental uncertainty)
  systematic   outside that window but of the sign and size typical for the method
  discrepant   outside the window and not explained by the method
  unverified   no reference (or no source) available

Nothing here invents a reference: a record without a source is treated as missing.
"""
import json
from pathlib import Path

REF_PATH = Path(__file__).resolve().parent.parent / "reference" / "references.json"

# typical fractional error of a method when the reference record has no bias entry
DEFAULT_BIAS = {"pbe": -0.3, "hse": -0.1, "experiment": 0.0}


def load_references(path=None):
    p = Path(path) if path else REF_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("records", [])


def lookup(property_name, formula=None, phase=None):
    hits = []
    for rec in load_references():
        if rec.get("property") != property_name:
            continue
        mat = rec.get("material", {})
        if formula and mat.get("formula", "").replace(" ", "") != formula.replace(" ", ""):
            continue
        if phase and mat.get("phase") and mat["phase"] != phase:
            continue
        hits.append(rec)
    return hits


def _has_source(rec):
    src = rec.get("source") or {}
    return bool(src.get("id") or src.get("url"))


def compare(computed, reference, method="pbe", tolerance=None):
    """Return the verdict for one computed value against one reference record."""
    if not reference or not _has_source(reference):
        return {"verdict": "unverified", "reason": "no sourced reference available"}
    if reference.get("unit") != computed.get("unit"):
        return {"verdict": "unverified",
                "reason": f"unit mismatch: {computed.get('unit')} vs {reference.get('unit')}"}
    ref = float(reference["value"])
    val = float(computed["value"])
    delta = val - ref
    rel = delta / ref if ref else None
    bias = (reference.get("bias_expectation") or {}).get(method)
    if bias is None:
        bias = DEFAULT_BIAS.get(method, 0.0)
    expected = bias * ref
    band = tolerance if tolerance is not None else max(0.25 * abs(expected), 3 * reference.get("uncertainty", 0.0), 1e-9)
    if abs(delta - expected) <= band:
        verdict = "consistent"
        why = f"delta {delta:+.4g} is within the expected {method} offset {expected:+.4g} +/- {band:.4g}"
    elif (delta * expected > 0) and abs(delta) <= 2.0 * abs(expected) + band:
        verdict = "systematic"
        why = f"delta {delta:+.4g} is larger than expected {expected:+.4g} but has the method's sign"
    else:
        verdict = "discrepant"
        why = f"delta {delta:+.4g} is outside the expected {method} window {expected:+.4g} +/- {band:.4g}"
    return {"verdict": verdict, "reason": why,
            "computed": val, "reference": ref, "unit": computed.get("unit"),
            "delta": round(delta, 6), "relative": None if rel is None else round(rel, 6),
            "expected_offset": round(expected, 6), "tolerance": round(band, 6),
            "source": reference.get("source", {})}
