"""Build a markdown report from a workflow state, structure check and comparisons.

The report never states a literature value that is not in references.json or in a
per-case refs.json: everything else is printed as "unverified".
"""
import json
import os
import time
from pathlib import Path


def _table(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def build(system_dir, title=None, workflow=None, structure=None, extracted=None,
          comparisons=None, notes=None, missing=None):
    """Assemble the markdown report and write it to <system_dir>/report.md."""
    d = Path(system_dir)
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append(f"# {title or d.name} — result report")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append("")

    # ---- 1 provenance
    lines.append("## 1. Method and provenance")
    lines.append("")
    wf = workflow or (json.loads((d / "workflow.json").read_text())
                      if (d / "workflow.json").exists() else None)
    if wf:
        lines.append(f"- workflow: `{wf.get('workflow')}` (strategy: {wf.get('strategy')})")
        for sid, rec in (wf.get("stages") or {}).items():
            gate = rec.get("gate") or {}
            lines.append(f"- stage `{sid}`: {rec.get('state')}"
                         + (f", gate {gate.get('type')}={'pass' if gate.get('ok') else 'FAIL'}"
                            if gate else "")
                         + (f", job {rec.get('job_id')}" if rec.get("job_id") else ""))
    else:
        lines.append("- no workflow.json found: this report describes a manual run.")
    lines.append("")

    # ---- 2 structure
    lines.append("## 2. Structure check")
    lines.append("")
    if structure:
        lines.append(f"- file: `{structure.get('file')}`")
        lines.append(f"- atoms: {structure.get('natoms')} ({structure.get('formula')})")
        lines.append(f"- volume: {structure.get('volume_A3')} A^3, "
                     f"density {structure.get('density_g_cm3')} g/cm^3")
        sg = structure.get("symmetry") or {}
        if sg:
            lines.append(f"- symmetry: {sg.get('symbol')} (#{sg.get('number')}, "
                         f"{sg.get('n_operations')} operations)")
        lines.append(f"- nearest-neighbour range: {structure.get('nearest_nn_min_A')} - "
                     f"{structure.get('nearest_nn_max_A')} A")
        nn = structure.get("nearest_neighbours") or []
        if nn:
            lines.append("")
            lines.append("| atom | 1st | 2nd | 3rd | 4th |")
            lines.append("|---|---|---|---|---|")
            for i, shell in enumerate(nn):
                cells = [f"{s['to']} {s['d']:.3f}" for s in shell[:4]]
                cells += [""] * (4 - len(cells))
                lines.append(f"| {i + 1} | " + " | ".join(cells) + " |")
        findings = structure.get("findings") or []
        lines.append("")
        if findings:
            lines.append("**Findings:**")
            for f in findings:
                lines.append(f"- {f}")
        else:
            lines.append("No structural anomaly detected.")
    else:
        lines.append("- structure check not run.")
    lines.append("")

    # ---- 3 results
    lines.append("## 3. Computed results")
    lines.append("")
    if extracted:
        rows = []
        for item in extracted:
            src = item.get("source") or ""
            if src:
                # Relative to the case directory, so 01-scf/EIGENVAL and
                # 03-post/band.dat stay distinguishable in the table.
                try:
                    src = os.path.relpath(src, str(d))
                except ValueError:
                    src = src.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            if item.get("unsupported"):
                rows.append([item.get("kind"), "unsupported", item.get("unsupported"), "", src])
                continue
            for k, v in (item.get("values") or {}).items():
                rows.append([item.get("kind"), k, v,
                             (item.get("units") or {}).get(k, ""), src])
        lines.append(_table(rows, ["quantity", "field", "value", "unit", "file"]))
    else:
        lines.append("- no values extracted.")
    if missing:
        lines.append("")
        lines.append("Quantity not found in this directory (looked for):")
        for kind, names in missing.items():
            lines.append(f"- `{kind}`: {', '.join(f'`{n}`' for n in names)}")
    lines.append("")

    # ---- 4 comparison
    lines.append("## 4. Comparison with references")
    lines.append("")
    if comparisons:
        rows = []
        for c in comparisons:
            src = c.get("source") or {}
            rows.append([c.get("property"), c.get("computed"), c.get("reference"),
                         c.get("unit"), c.get("delta"), c.get("verdict"),
                         src.get("citation") or src.get("id") or "—"])
        lines.append(_table(rows, ["property", "computed", "reference", "unit",
                                   "delta", "verdict", "source"]))
        lines.append("")
        for c in comparisons:
            if c.get("reason"):
                lines.append(f"- **{c.get('property')}**: {c.get('verdict')} — {c['reason']}")
    else:
        lines.append("- no comparison performed (no sourced reference available).")
    lines.append("")

    # ---- 5 interpretation
    lines.append("## 5. Interpretation and limitations")
    lines.append("")
    if notes:
        for n in notes:
            lines.append(f"- {n}")
    else:
        lines.append("- none recorded.")
    lines.append("")
    lines.append("Values marked `unverified` have no sourced reference and must not be "
                 "quoted as agreeing with experiment.")
    lines.append("")

    text = "\n".join(lines)
    (d / "report.md").write_text(text, encoding="utf-8")
    return {"report": str(d / "report.md"), "bytes": len(text)}
