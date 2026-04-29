"""Parametrar för slangavinda — single source of truth.

Alla mått i millimeter. Svenska namn enligt skill-definitionen
(.claude/agents/3d-slangavinda.md).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    # === GASOLTUB (referens, ej printad) ===
    tub_diameter: float = 300.0
    tub_kanthojd: float = 15.0
    tub_total_hojd: float = 550.0

    # === SLANG ===
    slang_diameter: float = 9.0
    slang_ytter: float = 15.0
    slang_langd: float = 15000.0

    # === HÅLLARE (U-plåt-stil) ===
    hallare_bredd: float = 70.0
    hallare_hojd: float = 80.0
    hallare_djup: float = 15.0
    hallare_tjocklek: float = 3.0
    arm_langd: float = 40.0
    axel_hol_diameter: float = 8.4

    # === TRUMMA ===
    trumma_diameter: float = 180.0
    trumma_bredd: float = 90.0
    trumma_hol: float = 8.4
    flans_tjocklek: float = 4.0
    nav_diameter: float = 60.0

    # === FJÄDERHUS (för självretrakterande klockfjäder) ===
    fjader_od: float = 52.0
    fjader_id: float = 7.0
    fjader_djup: float = 12.0
    fjader_ankare_bredd: float = 2.0

    # === SPÄRRHAKE (pawl + ratchet-kuggar) ===
    pawl_kugg_antal: int = 24
    pawl_kugg_djup: float = 2.5
    pawl_pinne_diameter: float = 3.2
    pawl_langd: float = 35.0
    pawl_bredd: float = 8.0
    pawl_tjocklek: float = 5.0

    # === SLANGÖGA ===
    slangoga_yttre: float = 24.0
    slangoga_inre: float = 16.0
    slangoga_tjocklek: float = 4.0

    # === BONUSVARIANTER ===
    through_bolt: bool = False
    burner_slot: bool = False
    burner_slot_b: float = 25.0
    burner_slot_h: float = 60.0


DEFAULT = Params()
