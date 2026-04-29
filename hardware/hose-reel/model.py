"""CadQuery-byggare för slangavindan.

Varje build_* funktion är ren: tar Params och returnerar en cq.Workplane.
build_assembly() bygger en cq.Assembly, valfritt exploderad.

Geometriapproach: vi bygger med box-primitiver + union/cut. Det är mer robust
än polyline-baserade skisser och ger samma slutresultat.
"""

from __future__ import annotations

import math

import cadquery as cq

from parameters import Params


# ---------------------------------------------------------------------------
# Hållare (U-form: rygg + läpp + en arm; spegelsymmetrisk i Z är ej nödvändigt
# eftersom vi bara har en sida som hänger över kanten och en arm under)
# ---------------------------------------------------------------------------
def build_hallare(p: Params) -> cq.Workplane:
    t = p.hallare_tjocklek
    h = p.hallare_hojd
    d = p.hallare_djup
    arm = p.arm_langd
    w = p.hallare_bredd

    # Geometri (sett från sidan, Z = uppåt, X = framåt):
    #   - Läpp: liten horisontell platta som hänger över tubens kant.
    #     Sträcker sig från X=-d till X=0 vid Z=0..t.
    #   - Rygg: vertikal vägg som går neråt från läppen.
    #     Sträcker sig från X=0..t vid Z=-h..0.
    #   - Arm: horisontell platta i botten där axeln sitter.
    #     Sträcker sig från X=0..arm vid Z=-h..-h+t.

    lapp = (
        cq.Workplane("XY")
        .box(d, w, t, centered=(False, True, False))
        .translate((-d, 0, 0))
    )
    rygg = (
        cq.Workplane("XY")
        .box(t, w, h, centered=(False, True, False))
        .translate((0, 0, -h))
    )
    arm_solid = (
        cq.Workplane("XY")
        .box(arm, w, t, centered=(False, True, False))
        .translate((0, 0, -h))
    )

    body = lapp.union(rygg).union(arm_solid)

    # Borra axelhål genom armen (genom hela bredden i Y).
    body = (
        body.faces(">Y")
        .workplane(centerOption="CenterOfMass")
        .center(arm - 15.0 - (arm / 2.0), -h + t / 2.0 - (-h + t / 2.0))
        # förenklar: använd transform-baserad cut nedan istället
    )

    # Återbygg utan den misslyckade workplane-justeringen.
    body = lapp.union(rygg).union(arm_solid)

    # Axelhål: cylindrisk cut längs Y-axeln genom armen.
    axel_cut = (
        cq.Workplane("XZ")
        .center(arm - 15.0, -h + t / 2.0)
        .circle(p.axel_hol_diameter / 2.0)
        .extrude(w + 10, both=True)
    )
    body = body.cut(axel_cut)

    # Pawl-pinnehål: cylindrisk cut längs Y, högre upp på ryggen/armen.
    pawl_cut = (
        cq.Workplane("XZ")
        .center(arm - 15.0, -h + t / 2.0 + 18.0)
        .circle(p.pawl_pinne_diameter / 2.0)
        .extrude(w + 10, both=True)
    )
    body = body.cut(pawl_cut)

    # Bonusvariant: through-bolt i ryggen.
    if p.through_bolt:
        through_cut = (
            cq.Workplane("YZ")
            .center(0, -h / 2.0)
            .circle(p.axel_hol_diameter / 2.0)
            .extrude(t + 10, both=True)
        )
        body = body.cut(through_cut)

    # Bonusvariant: brännarslot i ena armen.
    if p.burner_slot:
        slot_cut = (
            cq.Workplane("XZ")
            .center(arm / 2.0, -h + t / 2.0)
            .rect(p.burner_slot_b, p.burner_slot_h)
            .extrude(w + 10, both=True)
        )
        body = body.cut(slot_cut)

    return body


# ---------------------------------------------------------------------------
# Trumma med fjäderkavitet och ratchet-kuggar
# ---------------------------------------------------------------------------
def build_trumma(p: Params) -> cq.Workplane:
    R_flans = p.trumma_diameter / 2.0
    R_nav = p.nav_diameter / 2.0
    bredd = p.trumma_bredd
    flans_t = p.flans_tjocklek

    # Bygg drum som union av tre cylindrar:
    #   - Två flänsar (radie R_flans, tjocklek flans_t) i ändarna.
    #   - Ett nav (radie R_nav) i mitten som binder ihop.
    flans_botten = (
        cq.Workplane("XY")
        .circle(R_flans)
        .extrude(flans_t)
    )
    nav = (
        cq.Workplane("XY")
        .circle(R_nav)
        .extrude(bredd)
    )
    flans_topp = (
        cq.Workplane("XY")
        .circle(R_flans)
        .extrude(flans_t)
        .translate((0, 0, bredd - flans_t))
    )
    drum = flans_botten.union(nav).union(flans_topp)

    # Borra centralt axelhål genom hela höjden.
    axel_cut = (
        cq.Workplane("XY")
        .circle(p.trumma_hol / 2.0)
        .extrude(bredd + 10)
        .translate((0, 0, -5))
    )
    drum = drum.cut(axel_cut)

    # Fjäderkavitet i botten-flänsen (uppåt från Z=0).
    fjader_cut = (
        cq.Workplane("XY")
        .circle(p.fjader_od / 2.0)
        .extrude(p.fjader_djup)
    )
    drum = drum.cut(fjader_cut)

    # Spår för fjäderns ytterände — tunn rektangulär cut radiellt utåt.
    ankare_cut = (
        cq.Workplane("XY")
        .center(p.fjader_od / 2.0 - 1.0, 0)
        .rect(p.fjader_ankare_bredd * 2, p.fjader_ankare_bredd)
        .extrude(p.fjader_djup)
    )
    drum = drum.cut(ankare_cut)

    # Ratchet-kuggar: små rektangulära cuts i topp-flänsens kant.
    n = p.pawl_kugg_antal
    kugg_djup = p.pawl_kugg_djup
    kugg_bredd = (2 * math.pi * R_flans / n) * 0.5

    for i in range(n):
        ang = 360.0 * i / n
        rad = math.radians(ang)
        cx = R_flans * math.cos(rad)
        cy = R_flans * math.sin(rad)
        # Skär en liten box i flänskanten, orienterad radiellt.
        kugg_cut = (
            cq.Workplane("XY")
            .center(cx, cy)
            .rect(kugg_djup * 2, kugg_bredd)
            .extrude(flans_t * 1.2)
            .translate((0, 0, bredd - flans_t * 1.1))
        )
        # Rotera så att rektangelns långsida är tangentiell.
        kugg_cut = kugg_cut.rotate((cx, cy, 0), (cx, cy, 1), ang)
        drum = drum.cut(kugg_cut)

    return drum


# ---------------------------------------------------------------------------
# Pawl (spärrhake) — enkel rektangulär arm med pivothål
# ---------------------------------------------------------------------------
def build_pawl(p: Params) -> cq.Workplane:
    L = p.pawl_langd
    w = p.pawl_bredd
    t = p.pawl_tjocklek

    body = (
        cq.Workplane("XY")
        .box(L, w, t, centered=(False, True, False))
    )

    # Pivothål nära ena änden.
    pivot_cut = (
        cq.Workplane("XY")
        .center(w / 2.0, 0)
        .circle(p.pawl_pinne_diameter / 2.0)
        .extrude(t + 10)
        .translate((0, 0, -5))
    )
    body = body.cut(pivot_cut)

    return body


# ---------------------------------------------------------------------------
# Slangöga (clip-ring som styr slangen)
# ---------------------------------------------------------------------------
def build_slangoga(p: Params) -> cq.Workplane:
    R_y = p.slangoga_yttre / 2.0
    R_i = p.slangoga_inre / 2.0
    t = p.slangoga_tjocklek

    return (
        cq.Workplane("XY")
        .circle(R_y)
        .circle(R_i)
        .extrude(t)
    )


# ---------------------------------------------------------------------------
# Sammansättning
# ---------------------------------------------------------------------------
def build_assembly(p: Params, exploded: bool = False) -> cq.Assembly:
    asm = cq.Assembly(name="hose_reel")
    explode = 60.0 if exploded else 0.0

    asm.add(
        build_hallare(p),
        name="hallare",
        loc=cq.Location(cq.Vector(0, 0, 0)),
        color=cq.Color("gray"),
    )
    drum_y = p.hallare_bredd / 2.0 - p.trumma_bredd / 2.0
    asm.add(
        build_trumma(p),
        name="trumma",
        loc=cq.Location(
            cq.Vector(
                p.arm_langd - 15.0,
                drum_y + explode,
                -p.hallare_hojd + p.hallare_tjocklek / 2.0,
            ),
        ),
        color=cq.Color("orange"),
    )
    asm.add(
        build_pawl(p),
        name="pawl",
        loc=cq.Location(
            cq.Vector(
                p.arm_langd - 15.0 - p.pawl_bredd / 2.0,
                p.hallare_bredd + explode * 1.5,
                -p.hallare_hojd + p.hallare_tjocklek / 2.0 + 18.0,
            ),
        ),
        color=cq.Color("red"),
    )
    asm.add(
        build_slangoga(p),
        name="slangoga",
        loc=cq.Location(
            cq.Vector(
                p.arm_langd + explode * 0.5,
                p.hallare_bredd / 2.0,
                -p.hallare_hojd / 2.0,
            ),
        ),
        color=cq.Color("blue"),
    )

    return asm
