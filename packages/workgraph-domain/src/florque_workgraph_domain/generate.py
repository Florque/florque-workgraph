"""fwg-gen: regenerate committed artifacts from the ontology. ``--check`` fails on drift (CI)."""

from __future__ import annotations

import argparse
import sys

from florque_graph_core.generate import render_card, render_constraints, render_integrity

from florque_workgraph_domain import GENERATED_DIR, load


def artifacts() -> dict[str, str]:
    model = load()
    return {
        "card.md": render_card(model),
        "constraints.cypher": render_constraints(model),
        "integrity_checks.cypher": render_integrity(model),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fwg-gen", description=__doc__)
    ap.add_argument(
        "--check", action="store_true", help="exit 1 if generated files are out of date"
    )
    args = ap.parse_args(argv)
    drift = []
    for name, content in artifacts().items():
        path = GENERATED_DIR / name
        current = path.read_text() if path.exists() else None
        if current != content:
            drift.append(name)
            if not args.check:
                path.write_text(content)
    if args.check and drift:
        print(f"Generated artifacts out of date: {', '.join(drift)}. Run fwg-gen.", file=sys.stderr)
        return 1
    print("up to date" if not drift else f"wrote {', '.join(drift)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
