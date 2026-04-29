"""Renderar bilder av slangavindan som SVG och PNG.

SVG-vyer är 2D-projektioner via CadQuery's inbyggda exporter.
PNG-vyer är 3D-renderingar via VTK med flera kameravinklar.
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
from cadquery.occ_impl.assembly import toCAF

from model import (
    build_assembly,
    build_hallare,
    build_pawl,
    build_slangoga,
    build_trumma,
)
from parameters import DEFAULT


OUT = Path(__file__).parent / "output"
OUT.mkdir(parents=True, exist_ok=True)


def export_svg(name: str, shape, opts: dict) -> None:
    path = OUT / f"{name}.svg"
    cq.exporters.export(shape, str(path), opt=opts)
    print(f"  wrote {path.name}")


def main() -> None:
    parts = {
        "hallare": build_hallare(DEFAULT),
        "trumma": build_trumma(DEFAULT),
        "pawl": build_pawl(DEFAULT),
        "slangoga": build_slangoga(DEFAULT),
    }

    iso_opts = {
        "width": 800,
        "height": 600,
        "marginLeft": 20,
        "marginTop": 20,
        "showAxes": False,
        "projectionDir": (1.0, -1.0, 0.6),
        "strokeWidth": 0.4,
        "strokeColor": (40, 40, 40),
        "hiddenColor": (180, 180, 180),
        "showHidden": False,
    }
    front_opts = {**iso_opts, "projectionDir": (0.0, -1.0, 0.0)}
    side_opts = {**iso_opts, "projectionDir": (1.0, 0.0, 0.0)}
    top_opts = {**iso_opts, "projectionDir": (0.0, 0.0, 1.0)}

    print("--- per-part SVG (iso) ---")
    for name, solid in parts.items():
        export_svg(f"{name}_iso", solid, iso_opts)

    print("--- assembly SVG ---")
    asm = build_assembly(DEFAULT, exploded=False)
    asm_compound = asm.toCompound()
    export_svg("assembly_iso", asm_compound, iso_opts)
    export_svg("assembly_front", asm_compound, front_opts)
    export_svg("assembly_side", asm_compound, side_opts)
    export_svg("assembly_top", asm_compound, top_opts)

    print("--- exploded SVG ---")
    exp = build_assembly(DEFAULT, exploded=True)
    export_svg("exploded_iso", exp.toCompound(), iso_opts)


if __name__ == "__main__":
    main()
