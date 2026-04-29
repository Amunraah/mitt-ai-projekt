"""Genererar STL- och STEP-filer för slangavindan.

Användning:
    python generate_outputs.py                     # standard-variant
    python generate_outputs.py --variant all       # alla bonusvarianter
    python generate_outputs.py --variant through_bolt
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import cadquery as cq

from model import (
    build_assembly,
    build_hallare,
    build_pawl,
    build_slangoga,
    build_trumma,
)
from parameters import DEFAULT, Params


PARTS = {
    "hallare": build_hallare,
    "trumma": build_trumma,
    "pawl": build_pawl,
    "slangoga": build_slangoga,
}


def export_part(name: str, solid: cq.Workplane, out: Path) -> None:
    stl_path = out / f"{name}.stl"
    step_path = out / f"{name}.step"
    cq.exporters.export(solid, str(stl_path))
    cq.exporters.export(solid, str(step_path))
    print(f"  wrote {stl_path.name} + {step_path.name}")


def export_assembly(p: Params, out: Path, suffix: str = "") -> None:
    asm = build_assembly(p, exploded=False)
    asm.save(str(out / f"assembly{suffix}.step"))
    print(f"  wrote assembly{suffix}.step")
    exp = build_assembly(p, exploded=True)
    exp.save(str(out / f"exploded{suffix}.step"))
    print(f"  wrote exploded{suffix}.step")


def generate(p: Params, out: Path, prefix: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    print(f"\n--- variant '{prefix or 'default'}' ---")
    for name, builder in PARTS.items():
        export_part(f"{prefix}{name}" if prefix else name, builder(p), out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generera STL/STEP för slangavindan")
    parser.add_argument(
        "--variant",
        choices=("default", "through_bolt", "burner_slot", "all"),
        default="default",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent / "output",
    )
    args = parser.parse_args()

    if args.variant in ("default", "all"):
        generate(DEFAULT, args.out)
        export_assembly(DEFAULT, args.out)

    if args.variant in ("through_bolt", "all"):
        p = replace(DEFAULT, through_bolt=True)
        export_part("bracket_through_bolt", build_hallare(p), args.out)

    if args.variant in ("burner_slot", "all"):
        p = replace(DEFAULT, burner_slot=True)
        export_part("bracket_burner_slot", build_hallare(p), args.out)


if __name__ == "__main__":
    main()
