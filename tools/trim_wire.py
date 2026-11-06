"""Fit an imported map under the wire limit after import_bsp.py: drop small boxes away from doors, round to centimetres.

    python3 tools/trim_wire.py maps/mm_deco_mansion.json [--min-volume=0.055]

import_bsp.py's --min-box-volume also drops the door jambs, which loses the doors that need them to hang, so the importer runs at a low floor and this
cuts the rest here: a box under the floor stays when it lies within 1.2 m of a door.
"""
import json
import sys

path = sys.argv[1]
floor = 0.055
for a in sys.argv[2:]:
    if a.startswith("--min-volume="):
        floor = float(a.split("=")[1])

doc = json.load(open(path))
doors = [d["at"] for d in doc.get("doors", [])]


def near_door(b):
    return any(abs(b["at"][0] - p[0]) < 1.2 and abs(b["at"][2] - p[2]) < 1.2 and abs(b["at"][1] - p[1]) < 1.6 for p in doors)


def volume(b):
    s = b["size"]
    return s[0] * s[1] * s[2]


before = len(doc["boxes"])
doc["boxes"] = [b for b in doc["boxes"] if volume(b) >= floor or near_door(b)]
for b in doc["boxes"]:
    b["at"] = [round(v, 2) for v in b["at"]]
    b["size"] = [round(max(v, 0.01), 2) for v in b["size"]]
print("boxes %d -> %d" % (before, len(doc["boxes"])))
json.dump(doc, open(path, "w"), indent=1)
