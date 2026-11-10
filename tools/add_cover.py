"""Stand crouch-height cover (sofas, cabinets, beds) on clear floor near an imported map's spawns, after import_bsp.py.

    python3 tools/add_cover.py maps/mm_sunken_resort.json [--count=16]

The importer's own --cover needs the source .bsp; this works on the kept document, so it can run again after an import. A place is
taken when a floor box lies under it, no box or prop crosses the footprint above the floor, and it is 1.6 m from any door and spawn.
"""
import json
import math
import sys

path = sys.argv[1]
count = 16
for a in sys.argv[2:]:
    if a.startswith("--count="):
        count = int(a.split("=")[1])

CHOICES = [("furniture_lounge_sofa", 2.254, 0.943), ("furniture_kitchen_cabinet", 0.989, 1.035), ("furniture_bed_single", 1.313, 2.587),
           ("furniture_side_table_drawers", 1.229, 0.511), ("furniture_bookcase_open_low", 0.92, 0.575), ("furniture_desk", 1.689, 0.902)]

doc = json.load(open(path))
boxes = doc["boxes"]
spawns = doc["spawns"]["players"]
doors = [d["at"] for d in doc.get("doors", [])]


def overlap(b, x, z, hx, hz, y0, y1):
    return (abs(b["at"][0] - x) < b["size"][0] / 2 + hx and abs(b["at"][2] - z) < b["size"][2] / 2 + hz
            and b["at"][1] + b["size"][1] / 2 > y0 and b["at"][1] - b["size"][1] / 2 < y1)


def floor_under(x, z, y):
    return any(abs(b["at"][0] - x) < b["size"][0] / 2 and abs(b["at"][2] - z) < b["size"][2] / 2
               and abs(b["at"][1] + b["size"][1] / 2 - y) < 0.12 for b in boxes)


placed = []
for s in spawns * 3:
    if len(placed) >= count:
        break
    sx, sy, sz = s["at"]
    for ring in (2.6, 3.4, 4.2):
        done = False
        for k in range(12):
            ang = math.radians(k * 30 + len(placed) * 17)
            x, z = sx + math.cos(ang) * ring, sz + math.sin(ang) * ring
            pid, w, dpt = CHOICES[len(placed) % len(CHOICES)]
            r = max(w, dpt) / 2 + 0.2
            if not all(floor_under(x + dx, z + dz, sy) for dx in (-r, 0, r) for dz in (-r, 0, r)):
                continue
            if any(overlap(b, x, z, r, r, sy + 0.05, sy + 2.0) for b in boxes):
                continue
            if any(math.hypot(x - p[0], z - p[2]) < r + 1.6 and abs(p[1] - sy) < 2 for p in doors):
                continue
            if any(math.hypot(x - q["at"][0], z - q["at"][2]) < r + 1.0 and abs(q["at"][1] - sy) < 2 for q in spawns + placed):
                continue
            if any(math.hypot(x - q["at"][0], z - q["at"][2]) < 2.5 and abs(q["at"][1] - sy) < 2 for q in placed):
                continue
            q = {"id": pid, "at": [round(x, 2), round(sy, 3), round(z, 2)], "yaw": float(k * 30 % 180)}
            placed.append(q)
            done = True
            break
        if done:
            break

print("cover props placed: %d" % len(placed))
doc["props"] += placed
json.dump(doc, open(path, "w"), indent=1)
