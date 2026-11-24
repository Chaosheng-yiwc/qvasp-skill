#!/usr/bin/env python3
"""Regenerate the command list from a qvasp binary's `-h` output.

Usage:  python3 tools/gen_commands.py /path/to/qvasp [--write]

The help screen is a two-column box: every content line is

    | qvasp -cmd  description        | qvasp -other  description        |

and the two columns advance through *different* section headers, so this parser
tracks the current section per column, not per line. It prints a markdown table
(command | description) that can be merged into
`skills/qvasp/references/commands.md`; the "needs"/"writes" columns of that file
are maintained by hand.
"""
import pathlib
import re
import subprocess
import sys

CELL = re.compile(r"^\s*qvasp\s+(-[A-Za-z0-9_]+)\s*(.*)$")


def parse(help_text: str):
    left_section = right_section = "(general)"
    left, right = [], []
    for raw in help_text.splitlines():
        line = raw.strip()
        if line.startswith("+") and "=" in line:
            titles = [p.strip("= ") for p in line.strip("+").split("+")]
            titles = [t for t in titles if t]
            if titles:
                left_section = titles[0]
            if len(titles) > 1:
                right_section = titles[1]
            elif titles:
                right_section = titles[0]
            # a section border can carry command cells as well (-clean, -cp);
            # fall through so they are collected instead of being dropped
            if "qvasp -" not in line:
                continue
        if "|" not in line:
            continue
        cells = [c for c in line.split("|")]
        # drop the empty cells produced by the leading/trailing box borders
        cells = [c for c in cells if c.strip()]
        for idx, cell in enumerate(cells):
            m = CELL.match(cell)
            if not m:
                continue
            entry = (m.group(1), m.group(2).strip())
            if idx == 0:
                left.append((left_section, entry))
            else:
                right.append((right_section, entry))
    return left + right


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    binary = sys.argv[1]
    text = subprocess.run([binary, "-h"], capture_output=True, text=True).stdout
    rows = parse(text)
    out = ["# qvasp command list", "", f"{len(rows)} entries from `{binary} -h`.", "",
           "| section | command | description |", "|---|---|---|"]
    for section, (cmd, desc) in rows:
        out.append(f"| {section} | `{cmd}` | {desc} |")
    body = "\n".join(out) + "\n"
    if "--write" in sys.argv:
        target = (pathlib.Path(__file__).resolve().parent.parent
                  / "skills" / "qvasp" / "references" / "commands_generated.md")
        target.write_text(body, encoding="utf-8")
        print(f"wrote {target} ({len(rows)} entries)")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
