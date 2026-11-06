#!/usr/bin/env python3
"""Trims an imported map to the game's box budget (6000): drops boxes wholly below a depth and small trim.

    tools/trim_boxes.py maps/<id>.json [--below=-4] [--max-dim=1.2] [--max-volume=0.3]

The importer has no box budget; a large source level (sunken_resort) comes out near 11000 boxes. Small
boxes (rails, pipe and tube slices, clutter) and the boxes under the walkable floors go; walls, floors
and stairs are larger than that and stay. Run it once after import_bsp.py; a rerun does nothing more.
"""
import json
import sys


def main(argv):
    path = argv[1]
    opt = dict(a[2:].split("=", 1) for a in argv[2:] if a.startswith("--"))
    below = float(opt.get("below", -4))
    max_dim = float(opt.get("max-dim", 1.2))
    max_vol = float(opt.get("max-volume", 0.3))
    with open(path) as f:
        doc = json.load(f)

    def drop(b):
        s = b["size"]
        return b["at"][1] + s[1] / 2 < below or (max(s) < max_dim and s[0] * s[1] * s[2] < max_vol)

    n = len(doc["boxes"])
    doc["boxes"] = [b for b in doc["boxes"] if not drop(b)]
    with open(path, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("%s: %d boxes -> %d" % (path, n, len(doc["boxes"])))


if __name__ == "__main__":
    main(sys.argv)
