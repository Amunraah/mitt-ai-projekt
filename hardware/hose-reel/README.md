# Slangavinda för gasoltub (självretrakterande)

Parametrisk 3D-modell av en liten slangavinda som hängs över kanten på en
standard 11 kg gasoltub. Slangen rullar tillbaka av sig själv via en metall-
klockfjäder och låses i utdraget läge med en spärrhake.

## Renderingar

| Vy | Bild |
|---|---|
| Sammansättning (iso) | `output/assembly_iso.png` |
| Exploderad vy | `output/exploded_iso.png` |
| Hållare | `output/hallare_iso.png` |
| Trumma | `output/trumma_iso.png` |
| Pawl | `output/pawl_iso.png` |
| Slangöga | `output/slangoga_iso.png` |

Ortografiska vyer av sammansättningen finns även som
`assembly_front.png`, `assembly_side.png`, `assembly_top.png`. Generera om
med `python render_images.py` om du ändrar parametrar.

## BOM (Bill of Materials)

| Artikel | Antal | Anmärkning |
|---|---|---|
| 3D-printad hållare | 1 | PETG eller ASA |
| 3D-printad trumma | 1 | PETG eller ASA |
| 3D-printad pawl (spärrhake) | 1 | PETG eller ASA |
| 3D-printad slangöga | 1 | PETG |
| M8×80 skruv + mutter | 1 | Axel mellan armarna |
| M3×20 skruv + mutter | 1 | Pawl-pivot |
| Klockfjäder Ø50/Ø6/0,3×2000 mm | 1 | "Tape measure spring", finns billigt online |
| M8 brickor | 2 | Distans mellan trumma och hållare |

## Filer

| Fil | Beskrivning |
|---|---|
| `parameters.py` | Alla mått som dataclass (svenska variabelnamn) |
| `model.py` | CadQuery-byggare per del + assembly |
| `generate_outputs.py` | CLI som skriver STL + STEP till `output/` |
| `requirements.txt` | `cadquery>=2.4` |
| `output/*.stl` | Färdiga print-filer |
| `output/*.step` | CAD-utbyte (öppna i FreeCAD, Fusion 360, viewer.autodesk.com) |

## Installation och körning

```bash
cd hardware/hose-reel
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python generate_outputs.py --variant all
```

Förgenererade STL/STEP ligger redan i `output/` så du kan printa direkt om du
inte vill installera CadQuery.

## Print-inställningar

| Del | Material | Orientering | Supports | Infill | Layer | Walls |
|---|---|---|---|---|---|---|
| Hållare | PETG/ASA | Plant på baksidan | Inga | 40 % gyroid | 0,2 mm | 4 |
| Trumma | PETG/ASA | Axel vertikal (en fläns mot byggplattan) | Inga | 25 % gyroid | 0,2 mm | 3 |
| Pawl | PETG/ASA | Plant | Inga | 60 % gyroid | 0,15 mm | 4 |
| Slangöga | PETG | Plant | Inga | 30 % | 0,2 mm | 3 |

PETG är default. ASA är uppgraderingen för svensk tak-sommarvärme och närhet
till brännare. PLA undviks (kryper i värme).

## Montering

1. Fäst klockfjäderns innerände i axelns platta del (fila en plan yta på M8-skruven).
2. Tryck in fjädern i trummans nav-kavitet (botten-flänsen). Ytterändens hake greppar i det radiella spåret.
3. Trä axeln (M8-skruven) genom första armen, genom trumman, genom andra armen. Bricka mellan trumma och respektive arm.
4. Skruva på muttern. Lagom åtdragning så trumman snurrar fritt.
5. Förspann fjädern: vrid trumman 5–10 varv innan slangen rullas på, så den retracterar med kraft.
6. Vira slangen runt trumman, trä igenom slangögat, fäst slangögat på hållarens framsida med en liten skruv.
7. Montera pawlen med M3-skruven på sidan av hållaren — så att näsan greppar trummans flänskuggar.

## Användning

- Dra ut slangen — du hör pawlen klicka.
- Släpp — slangen låser i utdraget läge.
- För att retraktera: knuffa pawlen åt sidan med ett finger; håll tills slangen är hemrullad.

## Bonusvarianter

Genererade som separata STL-filer:

- `bracket_through_bolt.stl` — extra hål i ryggen för en skruv som klämmer hållaren mot tubens kant (extra stabilitet).
- `bracket_burner_slot.stl` — variant med slot i ena armen för att hänga brännaren bredvid.

## Verifiering

```bash
python -c "from model import *; from parameters import DEFAULT; \
print(build_trumma(DEFAULT).val().BoundingBox().DiagonalLength)"
# förväntas vara ~210 mm
```

Öppna `output/assembly.step` i [viewer.autodesk.com](https://viewer.autodesk.com)
eller `output/hallare.stl` i [3dviewer.net](https://3dviewer.net) för visuell
sanity-check.

## Öppna risker / antaganden

- Inga referensbilder bifogades trots att uppdraget refererar till bilder 1–5. Måtten i specifikationen används som sanning. Designen kan revideras om bilderna kommer fram.
- Klockfjäderns dimensioner är antagna på en vanlig generisk modell. Justera `fjader_od/id/djup` i `parameters.py` om du har en specifik fjäder.
- Spärrhakemekanismen är förenklad jämfört med kommersiella retract-reels. Testa i fysisk prototyp innan slutgiltig design låses.
