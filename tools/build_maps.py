#!/usr/bin/env python3
"""Writes every map in maps/ from the plans below.

A map is a JSON document (see game-murder-mystery's game/mm_map_doc.gd and maps/README.md), and
nothing stops a mapper writing one by hand. These are generated instead because a building is
hundreds of boxes that have to meet: a wall with a door in it is five boxes whose edges are
the door's, a room's floor, ceiling and light belong to the room, and a stairwell is a dozen
slabs that must line up with the storeys.

    tools/build_maps.py                 # rewrite every map
    tools/build_maps.py --check         # fail if a file on disk is not what this would write
    tools/build_maps.py --sync-sizes    # copy prop sizes from ../game-murder-mystery (when it is there)
    tools/build_maps.py --spots mm_motel [y]   # the clearest open floor on a map, for placing toys

The library half (the `Map` class, `load_sizes`, `rest_on`, `footprint`, walls and doors, rooms,
stairs, slabs, toy settling, spawn settling and facing, and the furnishing helpers) is copied
from hide-n-seek-maps' tools/build_maps.py at the commit that created this repository
(2026-10-18); what is this repository's own is the murder-mystery half below it.

Conventions, which every function below keeps:

- Metres, degrees. y is up and every floor's top is at y 0 unless a room says otherwise.
- A box's `at` is its centre. A prop's `at` is the middle of its footprint ON the floor.
- A prop's FRONT faces +Z at yaw 0 (Kenney's furniture does: a stove's door, a desk's drawers),
  so a sofa against a north wall (the wall at the smaller z) faces into the room at yaw 0, one
  against a south wall at yaw 180, against a west wall at 90 and an east wall at -90.
- Doors are 1.4 m wide and 2.3 m tall.
- Stairs are thin slabs, 0.22 m a step (see `flight`). A player steps 0.4.
- A door is a hole in a wall with a fifth element, a dict of the door's options: `(3.0, 4.4,
  0.0, DOOR_H, {"name": "bedroom door"})`. The panel is cut to the hole, so the two cannot
  disagree. See `Map.door`.
- Spawns are one group, `players`: a round starts with everybody apart.
"""

import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIZES_FILE = os.path.join(HERE, "prop_sizes.json")
GAME_CATALOGUE = os.path.join(ROOT, "..", "game-murder-mystery", "props", "catalogue.json")
GAME_PIECES = os.path.join(ROOT, "..", "game-murder-mystery", "props", "pieces.json")

WALL = 0.2          # an interior wall
OUTER = 0.3         # an exterior wall, brick outside and paint inside
DOOR_W = 1.4
GROUND = -0.02      # the ground round the buildings, a hair under their floors (see Map.room)
DOOR_H = 2.3
SILL = 0.9          # a window's bottom
HEAD = 2.2          # a window's top


def r(v):
    return round(v, 3)


def v3(x, y, z):
    return [r(x), r(y), r(z)]


def load_sizes():
    with open(SIZES_FILE) as f:
        return json.load(f)["props"]


SIZES = load_sizes() if os.path.exists(SIZES_FILE) else {}


def size_of(pid):
    s = SIZES.get(pid)
    if s is None:
        raise SystemExit("unknown prop %s (run --sync-sizes?)" % pid)
    return s["size"]


def rest_on(under, dx, dz, pid, yaw):
    """How high above `under`'s base a prop `pid` set down at (dx, dz) from its middle comes to
    rest: the highest of the support's `tops` (the game's collision, sampled on a grid by its
    tools/measure_props.gd) under the prop's footprint, or the support's box top when it collides
    as its box."""
    s = SIZES[under["id"]]
    tops = s.get("tops")
    sx, sy, sz = s["size"]
    if not tops:
        return sy
    n = int(round(len(tops) ** 0.5))
    # Into the support's own frame: the map turns it by its yaw about +y (multiples of 90 here),
    # world = (x cos + z sin, -x sin + z cos), so local = (wx cos - wz sin, wx sin + wz cos).
    turn = int(round(under.get("yaw", 0.0))) % 360
    lx, lz = {0: (dx, dz), 90: (-dz, dx), 180: (-dx, -dz), 270: (dz, -dx)}.get(turn, (dx, dz))
    w, d = footprint(pid, (yaw - under.get("yaw", 0.0)))
    best = None
    nearest = None
    for k in range(n):
        for i in range(n):
            h = tops[k * n + i]
            if h is None:
                continue
            x = -sx / 2 + (i + 0.5) * sx / n
            z = -sz / 2 + (k + 0.5) * sz / n
            gap = max(abs(x - lx) - w / 2, abs(z - lz) - d / 2, 0.0)
            if gap <= 0.0 and (best is None or h > best):
                best = h
            if nearest is None or gap < nearest[0]:
                nearest = (gap, h)
    if best is None:
        best = nearest[1] if nearest else sy
    return best


def footprint(pid, yaw):
    """A prop's width (x) and depth (z) once turned by yaw (multiples of 90 only)."""
    sx, sy, sz = size_of(pid)
    if int(round(yaw)) % 180 == 90 or int(round(yaw)) % 180 == -90:
        return sz, sx
    return sx, sz


class Map:
    def __init__(self, mid, name, blurb, environment, round_seconds=0.0, kill_y=-20.0):
        self.doc = {
            "format": 1, "kind": "murder_map", "id": mid, "name": name, "author": "murder-mystery-maps",
            "blurb": blurb, "environment": environment, "kill_y": kill_y,
        }
        if round_seconds:
            self.doc["round_seconds"] = round_seconds
        self.boxes = []
        self.props = []
        self.lights = []
        self.doors = []
        self.toys = []
        self.spawns = {"players": []}

    # --- Boxes -------------------------------------------------------------

    def box(self, at, size, mat, tint=None, yaw=0.0, solid=True, visible=True):
        b = {"at": v3(*at), "size": v3(*size), "mat": mat}
        if tint is not None:
            b["tint"] = [r(c) for c in tint]
        if yaw:
            b["yaw"] = r(yaw)
        if not solid:
            b["solid"] = False
        if not visible:
            b["visible"] = False
        self.boxes.append(b)
        return b

    def span(self, x0, x1, y0, y1, z0, z1, mat, tint=None, solid=True):
        """A box from its corners."""
        if x1 - x0 <= 0.001 or y1 - y0 <= 0.001 or z1 - z0 <= 0.001:
            return None
        return self.box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0), mat, tint, solid=solid)

    def floor(self, x0, z0, x1, z1, mat, tint=None, y=0.0, thick=0.2):
        return self.span(x0, x1, y - thick, y, z0, z1, mat, tint)

    def floor_around(self, x0, z0, x1, z1, hole, mat, tint=None, y=0.0, thick=0.2):
        """A floor with a rectangle (hx0, hz0, hx1, hz1) left out of it, as four boxes: a pool
        or a pond sunk into ground that would otherwise cover it."""
        hx0, hz0, hx1, hz1 = hole
        for a, b, c, d in ((x0, z0, x1, hz0), (x0, hz1, x1, z1), (x0, hz0, hx0, hz1), (hx1, hz0, x1, hz1)):
            self.floor(a, b, c, d, mat, tint, y, thick)

    def ceiling(self, x0, z0, x1, z1, height, mat="ceiling", tint=None, roof="roof", roof_tint=None, eave=0.3):
        self.span(x0, x1, height, height + 0.1, z0, z1, mat, tint)
        if roof:
            self.span(x0 - eave, x1 + eave, height + 0.1, height + 0.35, z0 - eave, z1 + eave, roof, roof_tint)

    def overlay(self, x0, z0, x1, z1, mat, tint=None, y=0.0):
        """Paint on a floor: a line, a path. Drawn a hair above it and solid to nothing."""
        return self.span(x0, x1, y + 0.002, y + 0.012, z0, z1, mat, tint, solid=False)

    def wall(self, a, b, along, mat, tint=None, height=3.2, y0=0.0, thick=WALL, holes=(), glass=True,
             inner=None, inner_tint=None):
        """A wall along x (along='x', at z=b[1]) or z (along='z', at x=b[0]) from a to b.

        a and b are (x, z). holes are (from, to, bottom, top) measured along the wall from a.
        A hole with bottom > 0 is a window and gets a pane of glass. `inner` is the material
        of a second, thinner layer on the room side (+z for an x wall, +x for a z wall); an
        exterior wall is brick outside and paint inside.
        """
        if along == "x":
            start, end = min(a[0], b[0]), max(a[0], b[0])
            fixed = a[1]
        else:
            start, end = min(a[1], b[1]), max(a[1], b[1])
            fixed = a[0]

        length = end - start
        cuts = sorted([tuple(h[:4]) for h in holes], key=lambda h: h[0])
        doorways = set()
        for h in holes:
            if len(h) > 4 and h[4] is not None:
                doorways.add(tuple(h[:4]))
                opts = dict(h[4])
                # A pair of leaves, hung from either side of the hole and meeting in the middle.
                if opts.pop("leaves", 1) == 2:
                    mid = start + (h[0] + h[1]) / 2
                    self.door(along, start + h[0], mid, fixed, y0 + h[2], y0 + h[3], hinge="start",
                              wall_mat=mat, wall_tint=tint, wall_thick=thick, **opts)
                    self.door(along, mid, start + h[1], fixed, y0 + h[2], y0 + h[3], hinge="end",
                              wall_mat=mat, wall_tint=tint, wall_thick=thick, **opts)
                    continue
                self.door(along, start + h[0], start + h[1], fixed, y0 + h[2], y0 + h[3],
                          wall_mat=mat, wall_tint=tint, wall_thick=thick, **opts)
        layers = [(mat, tint, thick, 0.0)]
        if inner:
            layers = [(mat, tint, thick - 0.06, -0.03), (inner, inner_tint, 0.06, (thick - 0.06) / 2.0)]

        for lmat, ltint, lthick, shift in layers:
            pos = 0.0
            for h0, h1, hb, ht in cuts:
                self._wall_piece(along, start + pos, start + h0, fixed + shift, y0, y0 + height, lthick, lmat, ltint)
                if hb > 0.0:
                    self._wall_piece(along, start + h0, start + h1, fixed + shift, y0, y0 + hb, lthick, lmat, ltint)
                if ht < height:
                    self._wall_piece(along, start + h0, start + h1, fixed + shift, y0 + ht, y0 + height, lthick, lmat, ltint)
                pos = h1
            self._wall_piece(along, start + pos, start + length, fixed + shift, y0, y0 + height, lthick, lmat, ltint)

        if glass:
            for h0, h1, hb, ht in cuts:
                if hb > 0.0 and (h0, h1, hb, ht) not in doorways:
                    self._wall_piece(along, start + h0, start + h1, fixed, y0 + hb, y0 + ht, 0.04, "glass", None)

    def _wall_piece(self, along, p0, p1, fixed, y0, y1, thick, mat, tint):
        if p1 - p0 <= 0.001 or y1 - y0 <= 0.001:
            return
        if along == "x":
            self.span(p0, p1, y0, y1, fixed - thick / 2, fixed + thick / 2, mat, tint)
        else:
            self.span(fixed - thick / 2, fixed + thick / 2, y0, y1, p0, p1, mat, tint)

    def door(self, along, p0, p1, fixed, y0, y1, name="", hinge="start", into="+", motion=None,
             secret=False, open=False, mat=None, tint=None, seconds=None, away=True, travel=None, angle=100.0,
             wall_mat="wood", wall_tint=None, wall_thick=WALL):
        """A door panel filling the hole from p0 to p1 (world, along the wall) and y0 to y1, in
        the wall along `along` at `fixed`.

        `hinge` is the end of the hole it hangs from ('start' is the smaller coordinate), `into`
        the side it swings to when it is opened from nowhere in particular ('+' is +z for an x
        wall, +x for a z wall); the game swings it away from whoever opens it unless `away` is
        False. `motion` is 'swing', 'slide' (along the wall, towards the hinge end) or 'lift'
        (up, a shutter). A secret door slides, is the wall's own material, has no handle, and is
        nearly the wall's thickness, so it reads as wall.
        """
        width, height = p1 - p0, y1 - y0
        mid = (p0 + p1) / 2
        if along == "x":
            at, yaw, side = (mid, y0 + height / 2, fixed), 0.0, (-1 if hinge == "start" else 1)
        else:
            # Turned 90 degrees, the panel's own +x is world -z: the start (smaller z) is its right.
            at, yaw, side = (fixed, y0 + height / 2, mid), 90.0, (1 if hinge == "start" else -1)
        # In a thick wall (a castle's, a tower's) a swinging door hangs on the face it opens
        # towards, square and one way only: in the middle of a deep opening it would swing into
        # the opening's own sides.
        sign_into = 1 if into == "+" else -1
        if wall_thick > 0.45 and not secret and (motion or "swing") == "swing":
            shift = sign_into * (wall_thick / 2 - 0.06)
            at = (at[0], at[1], at[2] + shift) if along == "x" else (at[0] + shift, at[1], at[2])
            away = False
            angle = min(angle, 90.0)
        if secret:
            motion = motion or "slide"
            thick = max(wall_thick - 0.03, 0.05)
            mat = mat or wall_mat
            tint = tint if tint is not None else wall_tint
        else:
            motion = motion or "swing"
            thick = 0.06
            mat = mat or "wood"
            tint = tint if tint is not None else (0.55, 0.4, 0.28)
        # The free edge's local z is side * width * sin(angle), and local z is the into-axis for
        # both kinds of wall, so the angle's sign is into times side.
        sign = (1 if into == "+" else -1) * side
        # A plain door has a finger's gap round it; a secret one a hair's, or its outline shows.
        gap = 0.006 if secret else 0.03
        d = {"at": v3(*at), "size": v3(width - gap, height - gap * 0.6, thick), "motion": motion,
             "hinge": "left" if side < 0 else "right", "mat": mat}
        if yaw:
            d["yaw"] = yaw
        if motion == "swing":
            d["angle"] = r(angle * sign)
            if not away:
                d["away"] = False
        if tint is not None:
            d["tint"] = [r(c) for c in tint]
        if name:
            d["name"] = name
        if secret:
            d["secret"] = True
        if open:
            d["open"] = True
        if seconds:
            d["seconds"] = seconds
        if travel:
            d["travel"] = travel
        self.doors.append(d)
        return d

    # --- Props, lights, spawns ----------------------------------------------

    def prop(self, pid, x, z, yaw=0.0, y=0.0, pitch=0.0, roll=0.0):
        size_of(pid)
        p = {"id": pid, "at": v3(x, y, z)}
        if yaw:
            p["yaw"] = r(yaw)
        if pitch:
            p["pitch"] = r(pitch)
        if roll:
            p["roll"] = r(roll)
        self.props.append(p)
        return p

    def on(self, pid, under, dx=0.0, dz=0.0, yaw=0.0):
        """A prop standing on top of another one, `under` a prop dict this built, resting on what
        is under its footprint there (`rest_on`): a pillow on a bed's mattress, not at the height
        of its headboard, which is what the bed's box top was."""
        top = under["at"][1] + rest_on(under, dx, dz, pid, yaw)
        return self.prop(pid, under["at"][0] + dx, under["at"][2] + dz, yaw, y=top)

    def against(self, pid, side, wall_at, along, gap=0.04, y=0.0):
        """A prop with its back to a wall. side is where the wall is: 'n' (smaller z), 's', 'w'
        (smaller x), 'e'. wall_at is the wall's inner face; along is the other coordinate."""
        yaw = {"n": 0.0, "s": 180.0, "w": 90.0, "e": -90.0}[side]
        w, d = footprint(pid, yaw)
        if side == "n":
            return self.prop(pid, along, wall_at + d / 2 + gap, yaw, y)
        if side == "s":
            return self.prop(pid, along, wall_at - d / 2 - gap, yaw, y)
        if side == "w":
            return self.prop(pid, wall_at + w / 2 + gap, along, yaw, y)
        return self.prop(pid, wall_at - w / 2 - gap, along, yaw, y)

    def light(self, x, y, z, rng=9.0, energy=1.0, colour=(1.0, 0.95, 0.85)):
        self.lights.append({"at": v3(x, y, z), "range": r(rng), "energy": r(energy), "colour": [r(c) for c in colour]})

    def spawn(self, x, z, yaw=0.0, y=0.05):
        self.spawns["players"].append({"at": v3(x, y, z), "yaw": r(yaw)})

    def lamp_panel(self, x, z, height, w=1.2, d=0.4):
        """A ceiling light fitting: drawn, not solid, with the light under it."""
        self.span(x - w / 2, x + w / 2, height - 0.06, height, z - d / 2, z + d / 2, "flat", (2.6, 2.6, 2.4), solid=False)

    # --- Rooms ----------------------------------------------------------------

    def room(self, x0, z0, x1, z1, floor_mat, floor_tint=None, height=3.2, ceiling="ceiling", roof="roof",
             lights=1, energy=1.1, roof_tint=None, eave=0.3):
        """A floor, a ceiling over it with a roof above, and its lamps. Walls are separate.

        `eave` is how far the roof reaches past the room: over the walls, and out past the
        building. A room beside a taller one wants less, or its roof shows inside the other.

        Its floor is at y 0 and the ground round a building is two centimetres lower (`GROUND`):
        at the same height, the two are drawn in stripes of each other. The ground goes down
        rather than the floor up, so that a rug laid on a floor is not laid under it."""
        self.floor(x0, z0, x1, z1, floor_mat, floor_tint)
        if ceiling:
            self.ceiling(x0, z0, x1, z1, height, ceiling, None, roof, roof_tint, eave)
        cols = max(1, int(round((x1 - x0) / 8.0)))
        rows = max(1, int(round((z1 - z0) / 8.0)))
        if lights:
            for i in range(cols):
                for j in range(rows):
                    lx = x0 + (i + 0.5) * (x1 - x0) / cols
                    lz = z0 + (j + 0.5) * (z1 - z0) / rows
                    self.lamp_panel(lx, lz, height)
                    self.light(lx, height - 0.5, lz, rng=max(x1 - x0, z1 - z0) / max(cols, rows) * 1.25 + 3.0, energy=energy)

    # --- Spawns ----------------------------------------------------------------

    PERSON = 0.45       # a person's radius and a little, for "is this spawn clear"
    PERSON_H = 1.9

    def _blocked(self, x, y, z):
        """What a person standing at (x, y, z) would be inside, or None. Props by their turned
        footprint, solid boxes by their extent; both as axis-aligned rectangles, which is
        generous for a turned one and so errs towards moving a spawn that was fine."""
        lo, hi = y + 0.1, y + self.PERSON_H
        for p in self.props:
            sx, sy, sz = size_of(p["id"])
            yaw = math.radians(p.get("yaw", 0.0))
            w = abs(sx * math.cos(yaw)) + abs(sz * math.sin(yaw))
            d = abs(sx * math.sin(yaw)) + abs(sz * math.cos(yaw))
            py = p["at"][1]
            if py + sy < lo or py > hi:
                continue
            if abs(x - p["at"][0]) < w / 2 + self.PERSON and abs(z - p["at"][2]) < d / 2 + self.PERSON:
                return p["id"]
        for b in self.boxes:
            if b.get("solid", True) is False:
                continue
            (bx, by, bz), (sx, sy, sz) = b["at"], b["size"]
            if by + sy / 2 < lo or by - sy / 2 > hi:
                continue
            if b.get("yaw"):
                yaw = math.radians(b["yaw"])
                sx, sz = abs(sx * math.cos(yaw)) + abs(sz * math.sin(yaw)), abs(sx * math.sin(yaw)) + abs(sz * math.cos(yaw))
            if abs(x - bx) < sx / 2 + self.PERSON and abs(z - bz) < sz / 2 + self.PERSON:
                return "a %s box" % b["mat"]
        return None

    def _floored(self, x, y, z, edge=0.1):
        for b in self.boxes:
            if b.get("solid", True) is False:
                continue
            (bx, by, bz), (sx, sy, sz) = b["at"], b["size"]
            if abs(by + sy / 2 - y) < 0.12 and abs(x - bx) < sx / 2 - edge and abs(z - bz) < sz / 2 - edge:
                return True
        return False

    def _settle_spawns(self):
        """Moves every spawn that a prop or a wall stands on to the nearest clear spot.

        A spawn is written where a room's plan says the players start, before the room is
        furnished, and a sofa put down later lands on it: mg-prop-hunt's headless_maps found
        six (a living room's corner sofa, an office desk, a hallway bench). Moving them here
        rather than by hand keeps a re-furnished room right without anybody remembering to."""
        for side, spots in self.spawns.items():
            for i, s in enumerate(spots):
                x, y, z = s["at"]
                what = self._blocked(x, y, z)
                if what is None:
                    continue
                found = None
                for ring in range(1, 9):
                    step = ring * 0.5
                    for k in range(8 * ring):
                        a = 2.0 * math.pi * k / (8 * ring)
                        cx, cz = x + step * math.cos(a), z + step * math.sin(a)
                        if self._blocked(cx, y, cz) is None and self._floored(cx, y, cz):
                            found = (cx, cz)
                            break
                    if found:
                        break
                if found is None:
                    raise SystemExit("%s: %s spawn %d at %s is inside %s and nothing near it is clear" % (self.doc["id"], side, i, s["at"], what))
                s["at"] = v3(found[0], y, found[1])
                print("  %s: %s spawn %d moved off %s to %s" % (self.doc["id"], side, i, what, s["at"]), file=sys.stderr)

    def _face_spawns(self):
        """Turns every spawn towards the middle of the map's furniture.

        The game's yaw 0 looks along -Z and its formula is yaw = atan2(-dx, -dz); the
        hand-written yaws assumed the other way round, and a browser render found a hunter
        released on Willow Lane's street looking at empty sky. Every map but the school had
        most of its spawns facing away. Computed rather than written per spawn, so a moved
        spawn or a re-furnished room cannot point the wrong way again."""
        if not self.props:
            return
        cx = sum(p["at"][0] for p in self.props) / len(self.props)
        cz = sum(p["at"][2] for p in self.props) / len(self.props)
        for spots in self.spawns.values():
            for s in spots:
                dx, dz = cx - s["at"][0], cz - s["at"][2]
                if abs(dx) + abs(dz) > 0.01:
                    s["yaw"] = r(math.degrees(math.atan2(-dx, -dz)))

    # --- Toys ----------------------------------------------------------------------

    def toy(self, tid, x, z, yaw=0.0, y=0.0, links=None, on=None, near=4.0, group=None):
        """One of dot-props' toys (a beach ball, a swing, a switch...), placed by id. Settled
        at build (`_settle_toys`) to the nearest clear, floored spot within `near` metres, so a
        hint in the right part of the map is enough. Returns its index, which a switch's
        `links` names."""
        if tid not in TOYS:
            raise SystemExit("%s: no toy called %s (dot-props' stock: %s)" % (self.doc["id"], tid, ", ".join(sorted(TOYS))))
        t = {"toy": tid, "at": v3(x, y, z)}
        if yaw:
            t["yaw"] = r(yaw)
        if links:
            t["links"] = list(links)
        if on is not None:
            t["on"] = bool(on)
        t["_near"] = near
        if group is not None:
            # Moved together, by one offset: a rack of pins stays a rack.
            t["_group"] = group
        self.toys.append(t)
        return len(self.toys) - 1

    @staticmethod
    def _toy_rect(t, at=None):
        """A toy's footprint as an axis-aligned (x0, z0, x1, z1), turned by its yaw, with the
        room a person needs round it."""
        w, d, h, loose = TOYS[t["toy"]]
        w, d = TOY_CLEAR.get(t["toy"], (w, d))
        x, _, z = at if at is not None else t["at"]
        yaw = math.radians(t.get("yaw", 0.0))
        ww = abs(w * math.cos(yaw)) + abs(d * math.sin(yaw))
        dd = abs(w * math.sin(yaw)) + abs(d * math.cos(yaw))
        pad = 0.15 if loose else 0.6
        return (x - ww / 2 - pad, z - dd / 2 - pad, x + ww / 2 + pad, z + dd / 2 + pad)

    def _toy_clear(self, t, x, y, z, placed):
        """What a toy at (x, y, z) would stand in, or None: a prop, a solid box between its
        floor and its top, a spawn, another toy, or no floor under every corner."""
        w, d, h, loose = TOYS[t["toy"]]
        x0, z0, x1, z1 = self._toy_rect(t, (x, y, z))
        lo, hi = y + 0.06, y + h
        for p in self.props:
            sx, sy, sz = size_of(p["id"])
            yaw = math.radians(p.get("yaw", 0.0))
            pw = abs(sx * math.cos(yaw)) + abs(sz * math.sin(yaw))
            pd = abs(sx * math.sin(yaw)) + abs(sz * math.cos(yaw))
            py = p["at"][1]
            if py + sy < lo or py > hi:
                continue
            if p["at"][0] + pw / 2 > x0 and p["at"][0] - pw / 2 < x1 and p["at"][2] + pd / 2 > z0 and p["at"][2] - pd / 2 < z1:
                return p["id"]
        for b in self.boxes:
            if b.get("solid", True) is False:
                continue
            (bx, by, bz), (sx, sy, sz) = b["at"], b["size"]
            if by + sy / 2 <= lo or by - sy / 2 >= hi:
                continue
            if b.get("yaw"):
                yaw = math.radians(b["yaw"])
                sx, sz = abs(sx * math.cos(yaw)) + abs(sz * math.sin(yaw)), abs(sx * math.sin(yaw)) + abs(sz * math.cos(yaw))
            if bx + sx / 2 > x0 and bx - sx / 2 < x1 and bz + sz / 2 > z0 and bz - sz / 2 < z1:
                return "a %s box" % b["mat"]
        for d_ in self.doors:
            (dx, dy, dz) = d_["at"]
            if abs(dx - x) < (x1 - x0) / 2 + 1.6 and abs(dz - z) < (z1 - z0) / 2 + 1.6 and abs(dy - y) < 2.5:
                return "a door's swing"
        for side in self.spawns.values():
            for s in side:
                sx_, sy_, sz_ = s["at"]
                if abs(sy_ - y) < 1.0 and x0 - 0.6 < sx_ < x1 + 0.6 and z0 - 0.6 < sz_ < z1 + 0.6:
                    return "a spawn"
        for o in placed:
            ox0, oz0, ox1, oz1 = self._toy_rect(o)
            if abs(o["at"][1] - y) < 1.5 and ox1 > x0 and ox0 < x1 and oz1 > z0 and oz0 < z1:
                return "the %s" % o["toy"]
        pad = 0.15 if loose else 0.6
        for cx, cz in ((x, z), (x0 + pad, z0 + pad), (x1 - pad, z0 + pad), (x0 + pad, z1 - pad), (x1 - pad, z1 - pad)):
            if not self._floored(cx, y, cz, edge=0.0):
                return "no floor"
        return None

    def _settle_toys(self):
        """Moves every toy whose spot is taken to the nearest clear one within its `near`, and
        stops the build when there is none: a toy in a wall, on a spawn or over the pond is a
        map bug, and printing it is how the plan below gets fixed."""
        placed = []
        done = set()
        for i, t in enumerate(self.toys):
            if i in done:
                continue
            if "_group" in t:
                members = [k for k, o in enumerate(self.toys) if o.get("_group") == t["_group"]]
                self._settle_group(members, placed)
                done.update(members)
                continue
            near = t.pop("_near")
            x, y, z = t["at"]
            what = self._toy_clear(t, x, y, z, placed)
            if what is not None:
                found = None
                for ring in range(1, int(near / 0.5) + 1):
                    step = ring * 0.5
                    for k in range(8 * ring):
                        a = 2.0 * math.pi * k / (8 * ring)
                        cx, cz = x + step * math.cos(a), z + step * math.sin(a)
                        if self._toy_clear(t, cx, y, cz, placed) is None:
                            found = (cx, cz)
                            break
                    if found:
                        break
                if found is None:
                    raise SystemExit("%s: toy %d (%s) at %s is in %s and nothing within %.1f m is clear" % (self.doc["id"], i, t["toy"], t["at"], what, near))
                t["at"] = v3(found[0], y, found[1])
            # On the floor's top, not the hint's: the ground outside is a hair under 0.
            t["at"][1] = r(self._floor_top(t["at"][0], y, t["at"][2]))
            placed.append(t)

    def _settle_group(self, members, placed):
        group = [self.toys[k] for k in members]
        near = max(g.pop("_near") for g in group)
        for g in group:
            g.pop("_group")
        def clash(dx, dz):
            for g in group:
                x, y, z = g["at"]
                what = self._toy_clear(g, x + dx, y, z + dz, placed)
                if what is not None:
                    return what
            return None
        what = clash(0.0, 0.0)
        offset = (0.0, 0.0)
        if what is not None:
            offset = None
            for ring in range(1, int(near / 0.5) + 1):
                step = ring * 0.5
                for k in range(8 * ring):
                    a = 2.0 * math.pi * k / (8 * ring)
                    if clash(step * math.cos(a), step * math.sin(a)) is None:
                        offset = (step * math.cos(a), step * math.sin(a))
                        break
                if offset:
                    break
            if offset is None:
                raise SystemExit("%s: a set of %d %s at %s is in %s and nothing within %.1f m is clear" % (self.doc["id"], len(group), group[0]["toy"], group[0]["at"], what, near))
        for g in group:
            x, y, z = g["at"]
            g["at"] = v3(x + offset[0], y, z + offset[1])
            g["at"][1] = r(self._floor_top(g["at"][0], y, g["at"][2]))
            placed.append(g)

    def _floor_top(self, x, y, z):
        best = y
        for b in self.boxes:
            if b.get("solid", True) is False:
                continue
            (bx, by, bz), (sx, sy, sz) = b["at"], b["size"]
            top = by + sy / 2
            if abs(top - y) < 0.12 and abs(x - bx) < sx / 2 and abs(z - bz) < sz / 2:
                best = top if best == y else max(best, top)
        return best

    def spots(self, y=0.0, step=1.0, top=40):
        """The open floor at height y, clearest first: (clearance, x, z). For choosing where a
        toy goes (`--spots`)."""
        xs = [b["at"][0] for b in self.boxes] or [0.0]
        zs = [b["at"][2] for b in self.boxes] or [0.0]
        out = []
        x = min(xs)
        probe = {"toy": "_probe"}
        while x <= max(xs):
            z = min(zs)
            while z <= max(zs):
                if self._floored(x, y, z, edge=0.0):
                    for size in (6.0, 4.5, 3.0, 2.0, 1.2):
                        TOYS["_probe"] = (size, size, 2.0, True)
                        if self._toy_clear(probe | {"at": [x, y, z]}, x, y, z, []) is None:
                            out.append((size, r(x), r(z)))
                            break
                z += step
            x += step
        TOYS.pop("_probe", None)
        out.sort(key=lambda s: -s[0])
        return out[:top]

    def build(self):
        plan = TOY_PLANS.get(self.doc["id"])
        if plan is not None:
            plan(self)
        self._settle_spawns()
        self._face_spawns()
        self._settle_toys()
        self.doc["boxes"] = self.boxes
        self.doc["props"] = self.props
        self.doc["lights"] = self.lights
        self.doc["doors"] = self.doors
        self.doc["spawns"] = self.spawns
        if self.toys:
            self.doc["toys"] = self.toys
        return self.doc




# --- Furnishing ------------------------------------------------------------------

def bathroom(m, x0, z0, x1, z1, stalls=2, doors=True, y=0.0):
    """Stalls with toilets along the back, sinks along the side. With `doors`, every stall has
    one, which opens outward only (inward, the toilet is in the way) and stops a hand's width
    off the floor, as a stall's does."""
    stall_w = 1.5
    for i in range(stalls):
        sx = x0 + 0.2 + i * stall_w
        m.prop("furniture_toilet", sx + stall_w / 2, z1 - 0.6, 180.0, y=y)
        if i > 0:
            m.span(sx - 0.03, sx + 0.03, y + 0.15, y + 2.0, z1 - 1.7, z1, "metal", (0.75, 0.82, 0.88))
        if doors:
            m.door("x", sx + 0.03 if i > 0 else sx, sx + stall_w - 0.03, z1 - 1.7, y + 0.15, y + 2.0, name="stall door",
                   hinge="start", into="-", away=False, angle=90.0, mat="metal", tint=(0.62, 0.72, 0.8))
    m.span(x0 + 0.2 + stalls * stall_w - 0.03, x0 + 0.2 + stalls * stall_w + 0.03, y + 0.15, y + 2.0, z1 - 1.7, z1, "metal", (0.75, 0.82, 0.88))
    for i in range(2):
        m.against("furniture_bathroom_sink_square", "e", x1, z0 + 1.0 + i * 1.2, y=y)
    m.prop("furniture_trashcan", x1 - 0.4, z0 + 0.2, y=y)
    m.against("furniture_bathroom_cabinet", "w", x0, z0 + 0.8, y=y)


def tree_ring(m, x0, z0, x1, z1, step, kinds, seed):
    """Trees along the edge of an area, a little irregular."""
    i = 0
    for x in frange(x0, x1, step):
        for z in (z0, z1):
            kind = kinds[(i * 7 + seed) % len(kinds)]
            m.prop(kind, x + ((i * 37) % 5 - 2) * 0.3, z + ((i * 53) % 5 - 2) * 0.3, (i * 47) % 360)
            i += 1
    for z in frange(z0 + step, z1 - step + 0.01, step):
        for x in (x0, x1):
            kind = kinds[(i * 7 + seed) % len(kinds)]
            m.prop(kind, x + ((i * 37) % 5 - 2) * 0.3, z + ((i * 53) % 5 - 2) * 0.3, (i * 47) % 360)
            i += 1


def frange(a, b, step):
    out = []
    v = a
    while v <= b + 1e-6:
        out.append(v)
        v += step
    return out


def fence(m, x0, z0, x1, z1, height=1.6, mat="wood", tint=(0.62, 0.48, 0.34), gaps=(), skip=(), gate=None):
    """A fence round an area, as thin walls with gates (gaps: (side, from, to)), leaving out the
    sides in `skip`: a garden's side along its house, which is the house's wall. `gate` is a
    door's options, hung in every gap; without it a gap is just a gap."""
    sides = {
        "n": ((x0, z0), (x1, z0), "x"),
        "s": ((x0, z1), (x1, z1), "x"),
        "w": ((x0, z0), (x0, z1), "z"),
        "e": ((x1, z0), (x1, z1), "z"),
    }
    for side, (a, b, along) in sides.items():
        if side in skip:
            continue
        holes = [(g0, g1, 0.0, height, dict(gate, mat=gate.get("mat", mat), tint=gate.get("tint", tint)) if gate else None)
                 for gs, g0, g1 in gaps if gs == side]
        m.wall(a, b, along, mat, tint, height=height, thick=0.12, holes=holes, glass=False)


STEP = 0.22         # a stair's rise; a player steps 0.4
CRAWL_H = 1.1       # a crawl space's height; a person crouched is 0.95


def room_at(m, x0, z0, x1, z1, y, floor_mat, floor_tint=None, height=3.2, ceiling="ceiling", roof="roof",
            lights=1, energy=1.1, roof_tint=None, eave=0.3, floor=True):
    """`Map.room` for a room whose floor is at `y`: an upper storey, a mezzanine, a loft.
    `floor=False` when the slab under it is laid separately (a storey with a stair hole)."""
    if floor:
        m.floor(x0, z0, x1, z1, floor_mat, floor_tint, y=y)
    if ceiling:
        m.ceiling(x0, z0, x1, z1, y + height, ceiling, None, roof, roof_tint, eave)
    cols = max(1, int(round((x1 - x0) / 8.0)))
    rows = max(1, int(round((z1 - z0) / 8.0)))
    if lights:
        for i in range(cols):
            for j in range(rows):
                lx = x0 + (i + 0.5) * (x1 - x0) / cols
                lz = z0 + (j + 0.5) * (z1 - z0) / rows
                m.lamp_panel(lx, lz, y + height)
                m.light(lx, y + height - 0.5, lz, rng=max(x1 - x0, z1 - z0) / max(cols, rows) * 1.25 + 3.0, energy=energy)


def flight(m, x0, x1, z0, z1, y0, y1, ascend, mat="wood", tint=None, thick=0.3):
    """A straight flight of stairs filling x0..x1, z0..z1, climbing from y0 to y1 in the
    direction `ascend` ('n' towards smaller z, 's', 'w', 'e'). Each step is a slab `thick`
    deep rather than a block to the floor, so the space under a flight is room: for the flight
    below it in a stairwell, or for somebody hiding under the stairs."""
    rise = y1 - y0
    n = max(1, int(math.ceil(rise / STEP)))
    for i in range(n):
        top = y0 + rise * (i + 1) / n
        bottom = max(y0, top - thick)
        f0, f1 = i / n, (i + 1) / n
        if ascend == "s":
            m.span(x0, x1, bottom, top, z0 + (z1 - z0) * f0, z0 + (z1 - z0) * f1, mat, tint)
        elif ascend == "n":
            m.span(x0, x1, bottom, top, z1 - (z1 - z0) * f1, z1 - (z1 - z0) * f0, mat, tint)
        elif ascend == "e":
            m.span(x0 + (x1 - x0) * f0, x0 + (x1 - x0) * f1, bottom, top, z0, z1, mat, tint)
        else:
            m.span(x1 - (x1 - x0) * f1, x1 - (x1 - x0) * f0, bottom, top, z0, z1, mat, tint)


def railing(m, x0, z0, x1, z1, y, height=1.0, mat="metal", tint=(0.35, 0.37, 0.40)):
    """A rail along one edge (a line, so x0 == x1 or z0 == z1): a top bar and posts, solid, so
    nobody walks off a gallery but a seeker below can see through it."""
    m.span(min(x0, x1) - 0.04, max(x0, x1) + 0.04, y + height - 0.06, y + height, min(z0, z1) - 0.04, max(z0, z1) + 0.04, mat, tint)
    m.span(min(x0, x1) - 0.04, max(x0, x1) + 0.04, y + 0.45, y + 0.5, min(z0, z1) - 0.04, max(z0, z1) + 0.04, mat, tint)
    length = max(abs(x1 - x0), abs(z1 - z0))
    posts = max(1, int(length / 1.5))
    for i in range(posts + 1):
        t = i / posts
        px, pz = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
        m.span(px - 0.04, px + 0.04, y, y + height, pz - 0.04, pz + 0.04, mat, tint)



def car(m, x, z, along, tint):
    """A parked car: a body and a cabin, solid, a little over a metre high. Crouch behind it."""
    if along == "x":
        m.span(x - 2.1, x + 2.1, 0.2, 1.0, z - 0.85, z + 0.85, "metal", tint)
        m.span(x - 1.0, x + 0.9, 1.0, 1.5, z - 0.75, z + 0.75, "glass", None)
    else:
        m.span(x - 0.85, x + 0.85, 0.2, 1.0, z - 2.1, z + 2.1, "metal", tint)
        m.span(x - 0.75, x + 0.75, 1.0, 1.5, z - 1.0, z + 0.9, "glass", None)



def boundary(m, x0, z0, x1, z1, height=3.0, mat="brick", tint=None):
    """The edge of the map: four walls nobody climbs."""
    t = 0.4
    m.span(x0 - t, x1 + t, 0.0, height, z0 - t, z0, mat, tint)
    m.span(x0 - t, x1 + t, 0.0, height, z1, z1 + t, mat, tint)
    m.span(x0 - t, x0, 0.0, height, z0, z1, mat, tint)
    m.span(x1, x1 + t, 0.0, height, z0, z1, mat, tint)


# --- Furnishing a home -----------------------------------------------------------------------

def living_room(m, x0, z0, x1, z1, y=0.0):
    """A sofa against the north wall facing a television on the south, a rug, a chair, a lamp,
    a bookcase and a plant: the room everybody passes through."""
    cx = (x0 + x1) / 2
    m.against("furniture_lounge_sofa", "n", z0, cx, y=y)
    m.prop("furniture_rug_rectangle", cx, (z0 + z1) / 2, y=y)
    m.prop("furniture_table_coffee", cx, z0 + 2.0, y=y)
    m.against("furniture_cabinet_television", "s", z1, cx, y=y)
    m.prop("furniture_television_modern", cx, z1 - 0.35, 180.0, y=y + 0.71)
    m.against("furniture_lounge_chair", "w", x0, z1 - 1.0, y=y)
    m.against("furniture_bookcase_closed_doors", "e", x1, z0 + 1.0, y=y)
    m.prop("furniture_potted_plant", x1 - 0.45, z1 - 0.45, y=y)
    m.prop("furniture_lamp_round_floor", x0 + 0.35, z0 + 0.35, y=y)


def bedroom(m, x0, z0, x1, z1, y=0.0, double=True):
    """A bed against the north wall, a wardrobe (a tall closed bookcase), a desk and a chest."""
    cx = (x0 + x1) / 2
    m.against("furniture_bed_double" if double else "furniture_bed_single", "n", z0, cx, y=y)
    m.against("furniture_cabinet_bed_drawer_table", "n", z0, cx - (1.5 if double else 1.0), y=y)
    m.against("furniture_bookcase_closed_wide", "e", x1, z1 - 1.2, y=y)
    m.against("furniture_desk", "w", x0, z1 - 1.2, y=y)
    m.prop("furniture_chair_desk", x0 + 1.3, z1 - 1.2, -90.0, y=y)
    m.prop("furniture_rug_round", cx, (z0 + z1) / 2 + 0.6, y=y)


def kitchen_row(m, x0, x1, z, side, y=0.0):
    """Units against a wall from x0 to x1: fridge, sink, stove, cabinets, with the small things on top."""
    pids = ["furniture_kitchen_fridge", "furniture_kitchen_cabinet", "furniture_kitchen_sink",
            "furniture_kitchen_stove", "furniture_kitchen_cabinet_drawer", "furniture_kitchen_cabinet"]
    x = x0 + 0.55
    placed = []
    for pid in pids:
        if x + 0.5 > x1:
            break
        placed.append(m.against(pid, side, z, x, y=y))
        x += 1.0
    for p in placed:
        if p["id"] == "furniture_kitchen_cabinet":
            m.on("furniture_kitchen_microwave", p)
            break


def bath(m, x0, z0, x1, z1, y=0.0):
    """A toilet, a sink and a shower: a room with one door."""
    m.against("furniture_toilet", "n", z0, x0 + 0.6, y=y)
    m.against("furniture_bathroom_sink", "n", z0, x0 + 1.6, y=y)
    m.prop("furniture_shower", x1 - 0.75, z1 - 0.75, y=y)



def slab(m, x0, z0, x1, z1, y, holes, mat, tint=None, thick=0.2):
    """A floor slab from x0..x1, z0..z1 with its top at y, leaving rectangular `holes` (hx0, hz0,
    hx1, hz1) open: an upper storey over a stairwell or two. Cut into strips at every hole's x
    edges, and each strip into the z runs no hole covers, so it is a handful of boxes."""
    xs = sorted({x0, x1} | {h[0] for h in holes if x0 < h[0] < x1} | {h[2] for h in holes if x0 < h[2] < x1})
    for a, b in zip(xs, xs[1:]):
        cuts = sorted((max(h[1], z0), min(h[3], z1)) for h in holes if h[0] < b and h[2] > a)
        at = z0
        for c0, c1 in cuts:
            if c0 > at:
                m.span(a, b, y - thick, y, at, c0, mat, tint)
            at = max(at, c1)
        if at < z1:
            m.span(a, b, y - thick, y, at, z1, mat, tint)


def lights_over(m, x0, z0, x1, z1, height, energy=1.0, colour=(1.0, 0.95, 0.85)):
    """A room's ceiling lamps and their lights, one per eight metres or so, under `height`."""
    cols = max(1, int(round((x1 - x0) / 8.0)))
    rows = max(1, int(round((z1 - z0) / 8.0)))
    for i in range(cols):
        for j in range(rows):
            lx = x0 + (i + 0.5) * (x1 - x0) / cols
            lz = z0 + (j + 0.5) * (z1 - z0) / rows
            m.lamp_panel(lx, lz, height)
            m.light(lx, height - 0.5, lz, rng=max(x1 - x0, z1 - z0) / max(cols, rows) * 1.25 + 3.0, energy=energy, colour=colour)



TOYS = {
    "beach_ball": (1.0, 1.0, 1.0, True),
    "football": (0.24, 0.24, 0.24, True),
    "bowling_ball": (0.22, 0.22, 0.22, True),
    "bowling_pin": (0.12, 0.12, 0.38, True),
    "barrel": (0.6, 0.6, 0.85, True),
    "tyre": (0.28, 0.8, 0.8, True),
    "punching_bag": (2.0, 1.2, 2.7, False),
    "swing": (2.4, 2.8, 2.4, False),
    "seesaw": (3.2, 0.6, 0.9, False),
    "merry_go_round": (2.8, 2.8, 1.3, False),
    "wobbly_platform": (1.6, 1.6, 0.6, False),
    "trampoline": (2.4, 2.4, 0.5, False),
    "bounce_pad": (1.2, 1.2, 0.2, False),
    "light_switch": (0.3, 0.3, 1.1, False),
    "lamp_post": (0.4, 0.4, 2.8, False),
    "fountain": (1.8, 1.8, 1.1, False),
    "horn": (0.5, 0.6, 1.5, False),
    "bell": (1.4, 0.4, 2.3, False),
}

# The room a launcher's flight needs clear, instead of its footprint: a trampoline throws a
# person 2.3 m up wherever they were heading, and a pad 5 m along its arrow (+z) and back down,
# so neither may stand where the flight would land them on a roof or a wall top that was meant
# to be reached another way (or not at all).
TOY_CLEAR = {
    "trampoline": (7.0, 7.0),
    "bounce_pad": (2.4, 14.0),
}

def lamps_on_a_switch(m, lamps, switch, y=0.0):
    """Lamp posts and the switch that turns them all on and off together."""
    ids = [m.toy("lamp_post", lx, lz, y=y, near=3.0) for (lx, lz) in lamps]
    m.toy("light_switch", switch[0], switch[1], y=y, links=ids, near=3.0)




# --- What a murder-mystery map adds -------------------------------------------------------------
#
# A round of social deduction starts with everybody apart and one of them holding a knife, so a
# map is judged by: more than one way round (a chase into a dead end is over), doors on most
# rooms (a shut door is a wall to a witness), some isolated spots (a cellar, a shed, a back
# stair: where one person is alone with another) and some crowded ones (a hall, a lounge, a
# diner: where nobody can do anything). Lit for dusk, but readable: the environment values
# stay near hs_manor's brightness.

DUSK = {
    "sky_top": [0.30, 0.34, 0.58], "sky_horizon": [0.92, 0.66, 0.52], "ground": [0.30, 0.30, 0.27],
    "sun_pitch": -14, "sun_yaw": 235, "sun_energy": 0.8, "sun_colour": [1.0, 0.76, 0.56],
    "ambient": [0.58, 0.58, 0.70], "ambient_energy": 0.46, "fog": 0.0012,
}

WARM = (1.0, 0.84, 0.62)


def D(name="door", **kw):
    """A door's options for a hole: a name, and anything `Map.door` takes (`w` is the hole's width)."""
    d = {"name": name}
    d.update(kw)
    return d


def W(m, x0, z0, x1, z1, doors=(), wins=(), gaps=(), y0=0.0, height=3.2, mat="plaster", tint=None,
      thick=WALL, outer=False, inward="+", inner_tint=None):
    """A wall from (x0, z0) to (x1, z1) (one coordinate the same) with its holes given by their
    centre along the wall, in world coordinates: `doors` are a centre or (centre, options) (the
    hole is `w` wide, 1.3 by default), `wins` are (centre, width) windows, `gaps` (centre, width)
    openings with nothing in them. An `outer` wall is brick outside and paint inside; `inward`
    says on which side of it ('+' is +z for a wall along x, +x for one along z) the room is."""
    if abs(z1 - z0) < 1e-9:
        along, start, fixed = "x", min(x0, x1), z0
    else:
        along, start, fixed = "z", min(z0, z1), x0
    holes, plain = [], []
    for d in doors:
        c, opts = d if isinstance(d, tuple) else (d, {})
        opts = dict(opts)
        w = opts.pop("w", 1.3)
        opts.setdefault("name", "door")
        holes.append((c - w / 2 - start, c + w / 2 - start, 0.0, DOOR_H, opts))
        plain.append(holes[-1][:4])
    for c, w in wins:
        holes.append((c - w / 2 - start, c + w / 2 - start, SILL, HEAD))
        plain.append(holes[-1][:4])
    for c, w in gaps:
        holes.append((c - w / 2 - start, c + w / 2 - start, 0.0, height))
        plain.append(holes[-1][:4])
    a, b = (x0, z0), (x1, z1)
    if not outer:
        m.wall(a, b, along, mat, tint, height=height, y0=y0, thick=thick, holes=holes)
        return
    paint = inner_tint if inner_tint is not None else (0.9, 0.85, 0.76)
    m.wall(a, b, along, "brick", tint, height=height, y0=y0, thick=OUTER, holes=holes,
           inner="paint" if inward == "+" else None, inner_tint=paint)
    if inward != "+":
        # The room is on the smaller side: a thin skin of paint on that face, with the same
        # holes but no doors or glass of its own.
        off = -(OUTER / 2 + 0.02)
        if along == "x":
            m.wall((x0, z0 + off), (x1, z1 + off), along, "paint", paint, height=height, y0=y0, thick=0.04, holes=plain, glass=False)
        else:
            m.wall((x0 + off, z0), (x1 + off, z1), along, "paint", paint, height=height, y0=y0, thick=0.04, holes=plain, glass=False)


def lit(m, x0, z0, x1, z1, height, energy=0.9, colour=WARM, cell=9.0):
    """A room's ceiling lamps and their lights: one per `cell` metres, warm, just under `height`."""
    cols = max(1, int(round((x1 - x0) / cell)))
    rows = max(1, int(round((z1 - z0) / cell)))
    for i in range(cols):
        for j in range(rows):
            lx = x0 + (i + 0.5) * (x1 - x0) / cols
            lz = z0 + (j + 0.5) * (z1 - z0) / rows
            m.lamp_panel(lx, lz, height)
            m.light(lx, height - 0.5, lz, rng=max((x1 - x0) / cols, (z1 - z0) / rows) * 0.85 + 3.0, energy=energy, colour=colour)


# --- Blackwood Mansion -------------------------------------------------------------------------

def mansion():
    """Blackwood Mansion: two storeys round an entrance hall, in a walled garden.

    The loops: hall - servants' corridor - kitchen - dining room - hall; hall - corridor - lounge
    - hall; upstairs, corridor - master - guest room - gallery - corridor; and the main stair up,
    the back stair down. Crowded: the hall, the lounge, the dining room. Alone: the cellar under
    the kitchen (one stair), the back stair, the garden shed and the hedge pocket behind it."""
    m = Map(
        "mm_mansion", "Blackwood Mansion",
        "A dinner party at a country house, and one of the guests brought a knife. Stay in company; the cellar, the back stair and the shed are far from help.",
        DUSK, round_seconds=300,
    )
    UP, UH = 3.4, 3.0
    TOP = UP + UH
    cream = (0.9, 0.84, 0.74)
    dark = (0.5, 0.36, 0.28)
    red = (0.62, 0.3, 0.3)
    stairwell = (3.0, -2.0, 5.9, 8.0)
    back_hole = (14.3, -11.6, 16.3, -5.1)
    cellar = (-19.5, -11.5, -12.0, -5.0)

    # The grounds, with the cellar's hole under them.
    m.floor_around(-25, -20, 25, 20, cellar, "grass", (0.7, 0.85, 0.65), y=GROUND)
    boundary(m, -25, -20, 25, 20, height=2.8, mat="hedge", tint=(0.55, 0.75, 0.55))
    m.overlay(-1.5, 10.15, 1.5, 20, "sand", (0.9, 0.85, 0.74))
    m.overlay(-9, 14, 9, 17, "sand", (0.9, 0.85, 0.74))
    m.overlay(-1.0, -20, 1.0, -12.15, "sand", (0.9, 0.85, 0.74))

    # Floors: tile in the kitchen (with the cellar stair's hole), wood in the back, parquet at the front.
    m.floor_around(-20, -12, -8, -2, (-19.5, -11.5, -17.5, -8.0), "tile", (0.85, 0.82, 0.74))
    m.floor(-8, -12, 20, -2, "wood_floor", (0.72, 0.58, 0.44))
    m.floor(-20, -2, 20, 10, "parquet")
    slab(m, -20, -12, 20, 10, UP, [stairwell, back_hole], "carpet", red)
    m.ceiling(-20, -12, 20, 10, TOP, "ceiling", None, "roof", (0.36, 0.28, 0.3), 0.5)

    # --- The shell ---
    W(m, -20, -12, 20, -12, wins=[(-13, 1.6), (-4, 1.6), (4, 1.6), (11, 1.4), (17.5, 1.0)], outer=True, inward="+", height=3.2)
    W(m, -20, 10, 20, 10, doors=[(0, D("front door", w=2.4, leaves=2)), (14, D("terrace door"))],
      wins=[(-17, 1.6), (-11, 1.6), (-3.8, 1.2), (3.8, 1.2), (9, 1.6), (18, 1.6)], outer=True, inward="-", height=3.2)
    W(m, -20, -12, -20, 10, doors=[(-4, D("back door"))], wins=[(-9, 1.2), (3, 1.6), (7.5, 1.6)], outer=True, inward="+", height=3.2)
    W(m, 20, -12, 20, 10, doors=[(-3.5, D("garden door"))], wins=[(-8.5, 1.0), (2, 1.6), (6.5, 1.6)], outer=True, inward="-", height=3.2)
    W(m, -20, -12, 20, -12, wins=[(-14, 1.6), (-4, 1.6), (4, 1.6), (11, 1.0), (17.5, 1.0)], outer=True, inward="+", y0=UP, height=UH)
    W(m, -20, 10, 20, 10, wins=[(-17, 1.6), (-11, 1.6), (-3, 1.6), (9.5, 1.6), (16.5, 1.6)], outer=True, inward="-", y0=UP, height=UH)
    W(m, -20, -12, -20, 10, wins=[(-7, 1.6), (1, 1.6), (7, 1.6)], outer=True, inward="+", y0=UP, height=UH)
    W(m, 20, -12, 20, 10, wins=[(-8.5, 1.0), (3, 1.6), (7, 1.6)], outer=True, inward="-", y0=UP, height=UH)

    # --- Ground floor walls ---
    W(m, -20, -2, 20, -2, doors=[(-14, D("kitchen door")), (-3, D("hall door")), (10, D("lounge door"))], tint=cream)
    W(m, -8, -12, -8, -2, doors=[(-3.5, D("servants' door"))], tint=cream)
    W(m, -8, -5, 20, -5, doors=[(0, D("library door", w=1.5)), (11, D("study door")), (18.5, D("back stair door"))], tint=cream)
    W(m, -6, -2, -6, 10, doors=[(5, D("dining room door", w=1.8, leaves=2))], tint=cream)
    W(m, 6, -2, 6, 10, doors=[(9.2, D("lounge door", w=1.4))], tint=cream)
    W(m, 8, -12, 8, -5, doors=[(-8, D("library side door"))], tint=cream)
    W(m, 14, -12, 14, -5, doors=[(-8, D("servants' stair door"))], tint=cream)

    # --- Upper walls ---
    W(m, -20, -2, 20, -2, doors=[(-14, D("guest room door")), (-3, D("gallery door")), (12, D("blue room door")), (17, D("nursery door"))],
      gaps=[(4.45, 2.9)], y0=UP, height=UH, tint=cream)
    W(m, -8, -12, -8, -2, doors=[(-3.5, D("master bedroom door"))], y0=UP, height=UH, tint=cream)
    W(m, -8, -5, 20, -5, doors=[(-4, D("east bedroom door")), (4, D("west bedroom door")), (11, D("bathroom door", w=1.1)),
                                (18.5, D("back stair landing door"))], y0=UP, height=UH, tint=cream)
    W(m, 0, -12, 0, -5, y0=UP, height=UH, tint=cream)
    W(m, 8, -12, 8, -5, y0=UP, height=UH, tint=cream)
    W(m, 14, -12, 14, -5, y0=UP, height=UH, tint=cream)
    W(m, -6, -2, -6, 10, doors=[(5, D("guest room door"))], y0=UP, height=UH, tint=cream)
    W(m, 6, -2, 6, 10, y0=UP, height=UH, tint=cream)
    W(m, 13, -2, 13, 10, doors=[(4, D("nursery connecting door"))], y0=UP, height=UH, tint=cream)

    # --- Stairs: the grand stair up the hall's east side, the back stair in the north-east ---
    flight(m, 3.0, 5.9, -2.0, 8.0, 0.0, UP, "n", "wood", dark)
    railing(m, 3.0, -2.0, 3.0, 8.0, UP, mat="wood", tint=dark)
    railing(m, 3.0, 8.0, 5.9, 8.0, UP, mat="wood", tint=dark)
    flight(m, 14.3, 16.3, -11.6, -5.1, 0.0, UP, "n", "wood", (0.55, 0.45, 0.35))
    railing(m, 16.3, -10.6, 16.3, -5.1, UP, mat="wood", tint=dark)

    # --- The cellar: a stone room under the kitchen, one stair down ---
    m.floor(-19.5, -11.5, -12.0, -5.0, "concrete", (0.6, 0.6, 0.6), y=-3.0)
    W(m, -19.5, -11.5, -12.0, -11.5, y0=-3.0, height=2.8, mat="stone", thick=0.3)
    W(m, -19.5, -5.0, -12.0, -5.0, y0=-3.0, height=2.8, mat="stone", thick=0.3)
    W(m, -19.5, -11.5, -19.5, -5.0, y0=-3.0, height=2.8, mat="stone", thick=0.3)
    W(m, -12.0, -11.5, -12.0, -5.0, y0=-3.0, height=2.8, mat="stone", thick=0.3)
    flight(m, -19.35, -17.5, -11.35, -8.0, -3.0, 0.0, "s", "wood", dark)
    railing(m, -17.5, -11.35, -17.5, -8.0, 0.0, mat="wood", tint=dark)
    m.light(-15.5, -1.2, -8.5, rng=9.0, energy=0.8, colour=(1.0, 0.8, 0.55))
    m.light(-17.5, 1.4, -9.5, rng=5.0, energy=0.6, colour=(1.0, 0.8, 0.55))
    for i in range(3):
        m.against("furniture_bookcase_open", "e", -12.15, -10.5 + i * 1.3, y=-3.0)
    m.against("furniture_cardboard_box_closed", "n", -11.35, -14.2, y=-3.0)
    m.against("furniture_cardboard_box_open", "n", -11.35, -13.0, y=-3.0)
    m.against("furniture_cardboard_box_closed", "s", -5.15, -15.0, y=-3.0)
    m.against("furniture_cardboard_box_closed", "s", -5.15, -13.9, y=-3.0)
    m.prop("furniture_table", -15.0, -7.2, y=-3.0)
    m.prop("furniture_chair", -15.0, -6.1, 180.0, y=-3.0)

    # --- Lights ---
    lit(m, -20, -12, -8, -2, 3.2)                      # kitchen
    lit(m, -20, -2, -6, 10, 3.2, 1.0)                  # dining room
    lit(m, -6, -2, 6, 10, 3.2, 1.1)                    # hall
    lit(m, 6, -2, 20, 10, 3.2, 1.0)                    # lounge
    lit(m, -8, -12, 8, -5, 3.2)                        # library
    lit(m, 8, -12, 14, -5, 3.2)                        # study
    lit(m, 14, -12, 20, -5, 3.2, 0.7)                  # back stair
    lit(m, -8, -5, 20, -2, 3.2, 0.7)                   # servants' corridor
    lit(m, -20, -12, -8, -2, TOP, 0.9)                 # master
    lit(m, -20, -2, -6, 10, TOP)                       # guest room
    lit(m, -6, -2, 3, 10, TOP, 1.0)                    # gallery
    lit(m, -8, -5, 20, -2, TOP, 0.8)                   # upper corridor
    lit(m, -8, -12, 0, -5, TOP)
    lit(m, 0, -12, 8, -5, TOP)
    lit(m, 8, -12, 14, -5, TOP, 0.9)
    lit(m, 14, -12, 20, -5, TOP, 0.7)
    lit(m, 6, -2, 13, 10, TOP)
    lit(m, 13, -2, 20, 10, TOP)
    m.light(4.4, 4.2, 3.0, rng=9.0, energy=0.9, colour=WARM)   # the stair
    m.light(0.0, 2.8, 5.0, rng=8.0, energy=0.7, colour=WARM)   # the chandelier

    # --- Furnishing: ground floor ---
    # Hall (crowded): a rug, a bench, side tables with lamps, the coat stand, plants.
    m.prop("furniture_rug_rectangle", -1.5, 4.5)
    m.against("furniture_bench_cushion", "w", -5.85, 0.4)
    for sx in (-4.9, 1.0):
        t = m.against("furniture_side_table_drawers", "n", -1.85, sx)
        m.on("furniture_lamp_round_table", t)
    m.prop("furniture_coat_rack_standing", -5.2, 9.1)
    m.prop("furniture_potted_plant", 2.4, -0.9)
    m.prop("furniture_potted_plant", 2.2, 9.2)
    m.prop("furniture_rug_doormat", 0.0, 9.2)
    m.prop("furniture_table_round", -1.5, 4.5)
    for dx, dz, yaw in ((-1.15, 0.0, 90.0), (1.15, 0.0, -90.0)):
        m.prop("furniture_chair_cushion", -1.5 + dx, 4.5 + dz, yaw)

    # Dining room: a long table of four, ten chairs, a sideboard, plants.
    for i in range(4):
        m.prop("furniture_table_cross_cloth", -16.0 + i * 2.0, 6.5)
    for i in range(4):
        x = -16.0 + i * 2.0
        m.prop("furniture_chair_cushion", x, 5.45)
        m.prop("furniture_chair_cushion", x, 7.55, 180.0)
    m.prop("furniture_chair_cushion", -17.9, 6.5, 90.0)
    m.against("furniture_cabinet_television_doors", "s", 9.85, -13.0)
    m.against("furniture_bookcase_closed_doors", "w", -19.85, 8.8)
    m.against("furniture_bookcase_closed_doors", "w", -19.85, 0.6)
    m.prop("furniture_rug_rectangle", -13.0, 6.5)
    m.prop("furniture_lamp_round_floor", -19.5, 9.4)
    m.prop("furniture_potted_plant", -6.7, 9.2)
    m.prop("furniture_potted_plant", -7.0, -0.8)
    m.prop("furniture_lamp_round_floor", -9.0, 9.4)

    # Kitchen: the row, an island, a table, a dresser.
    kitchen_row(m, -17.5, -8.2, -11.85, "n")
    for i in range(4):
        m.prop("furniture_kitchen_bar", -15.0 + i * 1.0, -7.0, 180.0)
    for i in range(3):
        m.prop("furniture_stool_bar", -14.5 + i * 1.0, -5.9, 180.0)
    m.prop("furniture_table", -12.5, -4.0)
    m.prop("furniture_chair", -12.5, -4.9)
    m.prop("furniture_chair", -12.5, -3.1, 180.0)
    m.against("furniture_kitchen_fridge_large", "e", -8.15, -10.4, y=0.0)
    m.against("furniture_bookcase_open", "s", -2.15, -10.5)
    m.prop("furniture_trashcan", -18.2, -2.6)

    # Library: books on the north wall, a desk, armchairs round a table, a rug.
    for i, x in enumerate((-7.4, -6.4, -5.4, -2.4, -1.4, -0.4, 0.6, 1.4, 5.4, 6.4, 7.4)):
        m.against("furniture_bookcase_closed" if i % 2 else "furniture_bookcase_open", "n", -11.85, x)
    m.against("furniture_desk", "e", 7.85, -10.6)
    m.prop("furniture_chair_desk", 6.5, -10.6, -90.0)
    m.prop("furniture_rug_rectangle", -2.5, -8.0)
    m.prop("furniture_table_round", -2.5, -8.0)
    m.prop("furniture_lounge_chair", -4.4, -8.0, 90.0)
    m.prop("furniture_lounge_chair", -0.6, -8.0, -90.0)
    m.against("furniture_bookcase_open_low", "s", -5.15, -6.6)
    m.prop("furniture_lamp_round_floor", -7.4, -6.0)
    m.prop("furniture_potted_plant", 7.2, -5.8)

    # Study.
    m.against("furniture_desk", "n", -11.85, 11.0)
    m.prop("furniture_chair_desk", 11.0, -10.6, 180.0)
    m.against("furniture_bookcase_closed_wide", "e", 13.85, -10.5)
    m.prop("furniture_lounge_chair", 9.2, -6.3)
    m.prop("furniture_lamp_square_floor", 8.6, -11.3)

    # Servants' corridor: sparse, so a person in it is seen from both ends.
    m.prop("furniture_coat_rack_standing", -6.0, -4.4)
    m.against("furniture_side_table", "n", -4.9, 5.5)
    m.prop("furniture_potted_plant", 19.2, -4.4)
    m.against("furniture_bench", "n", -4.9, 14.2)

    # Back stair room.
    m.prop("furniture_potted_plant", 19.3, -11.2)
    m.against("furniture_cardboard_box_closed", "e", 19.85, -9.0)
    m.against("furniture_cardboard_box_closed", "e", 19.85, -8.2)
    m.against("furniture_bookcase_closed", "e", 19.85, -6.2)
    m.prop("furniture_rug_doormat", 18.5, -5.7)

    # Lounge (crowded): sofa, armchairs, a coffee table, a television, a bar with stools, bookcases.
    m.prop("furniture_rug_rectangle", 15.5, 3.5, 90.0)
    m.prop("furniture_lounge_sofa", 12.8, 3.5, 90.0)
    m.prop("furniture_table_coffee", 15.4, 3.5, 90.0)
    m.prop("furniture_lounge_chair", 15.4, 0.7)
    m.prop("furniture_lounge_chair", 15.4, 6.3, 180.0)
    tvc = m.against("furniture_cabinet_television", "e", 19.85, 3.5)
    m.on("furniture_television_modern", tvc, yaw=-90.0)
    for x in (15.5, 16.5, 17.5, 18.5):
        m.against("furniture_bookcase_closed", "n", -1.85, x)
    for i in range(4):
        m.prop("furniture_kitchen_bar", 8.6 + i, 8.6, 180.0)
    for i in range(3):
        m.prop("furniture_stool_bar", 9.1 + i, 7.7)
    m.prop("furniture_lamp_square_floor", 19.5, -1.3)
    m.prop("furniture_lamp_square_floor", 7.0, 4.6)
    m.prop("furniture_potted_plant", 19.4, 9.2)
    m.prop("furniture_potted_plant", 6.7, -1.3)
    m.prop("furniture_lounge_sofa", 9.0, 0.2)
    m.prop("furniture_table_coffee_square", 9.0, 1.6)

    # --- Furnishing: upper floor ---
    bedroom(m, -7.7, -11.7, -0.3, -5.3, y=UP)
    bedroom(m, 0.3, -11.7, 7.7, -5.3, y=UP, double=False)
    bedroom(m, -19.7, -11.7, -8.3, -6.0, y=UP)
    m.against("furniture_lounge_sofa", "s", -2.15, -17.5, y=UP)
    m.prop("furniture_potted_plant", -9.0, -11.0, y=UP)
    m.prop("furniture_lamp_round_floor", -19.4, -3.0, y=UP)
    m.prop("furniture_rug_doormat", -9.2, -3.5, 90.0, y=UP)
    # Bathroom: the usual three, and a bath.
    bath(m, 8.2, -11.7, 13.8, -5.3, y=UP)
    m.against("furniture_bathtub", "e", 13.85, -8.6, y=UP)
    m.overlay(8.1, -11.85, 13.9, -5.1, "tile", (0.85, 0.9, 0.92), y=UP)
    # Back stair landing.
    m.prop("furniture_potted_plant", 19.3, -11.2, y=UP)
    m.against("furniture_bench", "e", 19.85, -8.5, y=UP)
    # Guest room, off the gallery and the master.
    m.against("furniture_bed_single", "w", -19.85, 1.5, y=UP)
    m.against("furniture_cabinet_bed_drawer_table", "w", -19.85, 3.0, y=UP)
    m.against("furniture_bookcase_closed_wide", "s", 9.85, -14.2, y=UP)
    m.against("furniture_desk", "s", 9.85, -8.8, y=UP)
    m.prop("furniture_chair_desk", -8.8, 8.7, 0.0, y=UP)
    m.prop("furniture_lounge_chair", -9.0, 6.5, -90.0, y=UP)
    m.prop("furniture_rug_round", -14.0, 3.5, y=UP)
    m.prop("furniture_potted_plant", -6.8, 9.2, y=UP)
    # Gallery (crowded): seats round a table, over the hall.
    m.prop("furniture_table_round", -2.0, 5.0, y=UP)
    for dx, dz, yaw in ((-1.1, 0.0, 90.0), (1.1, 0.0, -90.0), (0.0, -1.1, 180.0)):
        m.prop("furniture_chair_cushion", -2.0 + dx, 5.0 + dz, yaw, y=UP)
    m.against("furniture_bench_cushion", "w", -5.85, 0.8, y=UP)
    m.against("furniture_bookcase_open", "s", 9.85, -1.2, y=UP)
    m.prop("furniture_potted_plant", 2.4, 9.2, y=UP)
    m.prop("furniture_rug_rectangle", -2.0, 5.0, y=UP)
    # The blue room (a double) and the nursery (bunks).
    m.against("furniture_bed_double", "w", 6.15, 7.0, y=UP)
    m.against("furniture_cabinet_bed_drawer_table", "w", 6.15, 5.2, y=UP)
    m.against("furniture_bookcase_closed_wide", "s", 9.85, 11.8, y=UP)
    m.against("furniture_desk", "n", -1.85, 9.0, y=UP)
    m.prop("furniture_chair_desk", 9.0, -0.35, 180.0, y=UP)
    m.prop("furniture_rug_round", 10.0, 5.0, y=UP)
    m.against("furniture_bed_bunk", "e", 19.85, 8.0, y=UP)
    m.against("furniture_bed_single", "e", 19.85, 4.0, y=UP)
    m.against("furniture_bookcase_open_low", "s", 9.85, 17.0, y=UP)
    m.prop("furniture_rug_round", 16.0, 5.0, y=UP)
    # Corridor.
    m.against("furniture_side_table", "n", -4.9, 8.0, y=UP)
    m.against("furniture_bench", "n", -4.9, 14.2, y=UP)
    m.prop("furniture_potted_plant", -7.3, -4.5, y=UP)

    # --- The grounds ---
    # Terrace and shed.
    m.floor(8, 10.15, 20, 13, "stone", (0.78, 0.74, 0.68))
    m.prop("furniture_table_round", 11.0, 11.8)
    m.prop("furniture_chair", 9.6, 11.8, 90.0)
    m.prop("furniture_chair", 12.4, 11.8, -90.0)
    m.prop("nature_plant_bush_large", 18.5, 12.0)
    m.floor(9.0, -19.0, 14.0, -15.0, "wood_floor", (0.55, 0.42, 0.3))
    m.ceiling(9.0, -19.0, 14.0, -15.0, 2.6, "wood", None, "roof", (0.35, 0.28, 0.25), 0.3)
    W(m, 9.0, -19.0, 14.0, -19.0, height=2.6, mat="wood", tint=(0.6, 0.45, 0.32), thick=0.15)
    W(m, 9.0, -15.0, 14.0, -15.0, doors=[(11.5, D("shed door"))], height=2.6, mat="wood", tint=(0.6, 0.45, 0.32), thick=0.15)
    W(m, 9.0, -19.0, 9.0, -15.0, wins=[(-17.0, 0.8)], height=2.6, mat="wood", tint=(0.6, 0.45, 0.32), thick=0.15)
    W(m, 14.0, -19.0, 14.0, -15.0, height=2.6, mat="wood", tint=(0.6, 0.45, 0.32), thick=0.15)
    m.light(11.5, 2.1, -17.0, rng=5.5, energy=0.7, colour=(1.0, 0.82, 0.55))
    m.against("furniture_bookcase_open_low", "n", -18.85, 10.5)
    m.against("furniture_bookcase_open_low", "n", -18.85, 12.5)
    m.against("furniture_cardboard_box_closed", "w", 9.1, -16.4)
    m.against("furniture_cardboard_box_open", "w", 9.1, -17.4)
    m.against("furniture_cardboard_box_closed", "e", 13.9, -16.0)
    m.prop("nature_log_stack", 12.3, -18.0)
    m.prop("nature_pot_large", 10.4, -15.9)
    # The hedge pocket: a U of hedge open to the south, with benches.
    m.span(-18.0, -6.0, 0.0, 1.9, -17.5, -16.5, "hedge", (0.6, 0.85, 0.6))
    m.span(-18.0, -17.0, 0.0, 1.9, -16.5, -13.0, "hedge", (0.6, 0.85, 0.6))
    m.span(-7.0, -6.0, 0.0, 1.9, -16.5, -13.0, "hedge", (0.6, 0.85, 0.6))
    m.prop("furniture_bench", -12.0, -15.7)
    m.prop("furniture_bench", -15.5, -14.4, 90.0)
    m.prop("nature_stone_large_a", -9.0, -14.5)
    m.prop("nature_flower_red_a", -10.0, -15.4)
    # Free-standing hedge rows in the south garden, with gaps.
    m.span(-22.0, -12.0, 0.0, 1.5, 15.5, 16.3, "hedge", (0.6, 0.85, 0.6))
    m.span(-8.0, -3.0, 0.0, 1.5, 17.5, 18.3, "hedge", (0.6, 0.85, 0.6))
    m.span(4.0, 9.0, 0.0, 1.5, 17.5, 18.3, "hedge", (0.6, 0.85, 0.6))
    m.span(12.0, 22.0, 0.0, 1.5, 15.5, 16.3, "hedge", (0.6, 0.85, 0.6))
    for x, z in ((-23, 0), (-23, 8), (-23, -6), (23, 0), (23, -8), (23, 8), (-15, 12), (16, 14)):
        m.prop("nature_tree_oak" if (x + z) % 2 else "nature_tree_detailed", x, z, (x * 7 + z * 13) % 360)
    for x in (-18, -13, -8, 8, 13, 18):
        m.prop("nature_plant_bush", x, 10.9)
    tree_ring(m, -24.0, -19.0, 24.0, 19.0, 6.0, ["nature_tree_tall", "nature_tree_oak", "nature_tree_default", "nature_tree_fat"], 5)
    # The ring is a plain row of trees: keep it off the shed and the paths.
    m.props[:] = [p for p in m.props if not (p["id"].startswith("nature_tree") and (
        (8.0 < p["at"][0] < 15.0 and -20.0 < p["at"][2] < -14.0) or (abs(p["at"][0]) < 2.8 and abs(p["at"][2]) > 12.0)))]
    m.prop("nature_rock_large_a", -21.5, 12.0)
    m.prop("nature_rock_small_a", 21.5, -12.5)

    # --- Spawns: one group, apart. Each is a different room or yard. ---
    ground = [(-14.0, 8.4, "dining room"), (-11.0, 1.0, "dining room"), (-11.0, -9.0, "kitchen"), (0.0, 7.0, "hall"),
              (-2.5, 0.5, "hall"), (-3.0, -8.0, "library"), (3.5, -9.5, "library"), (11.0, -8.5, "study"),
              (17.5, -8.5, "back stair"), (12.5, 6.5, "lounge"), (17.0, 1.5, "lounge"), (-15.5, -9.0, "cellar"),
              (-22.5, 2.0, "west garden"), (0.0, 15.0, "front lawn"), (22.5, -10.0, "east garden"), (11.0, -17.3, "garden shed")]
    for x, z, room in ground:
        m.spawn(x, z, y=(-3.0 + 0.05) if room == "cellar" else 0.05)
    for x, z in ((-2.0, -8.0), (5.5, -7.5), (11.0, -8.5), (-14.0, -8.0), (-12.0, 6.0), (-2.0, 1.0), (10.0, 4.0), (17.0, 3.0), (17.5, -8.5)):
        m.spawn(x, z, y=UP + 0.05)
    return m.build()



def toys_mansion(m):
    """A country house's: lamps on a switch up the drive, a football on the lawn, the dinner gong
    in the dining room, and barrels in the cellar."""
    lamps_on_a_switch(m, [(-3.0, 13.0), (3.0, 13.0), (-3.0, 18.0), (3.0, 18.0)], (2.4, 11.2))
    m.toy("football", -8.0, 14.0, near=6.0)
    m.toy("bell", -7.2, 0.6, near=3.0)
    m.toy("barrel", -13.2, -10.0, y=-3.0, near=2.0)
    m.toy("barrel", -13.2, -8.8, y=-3.0, near=2.0)
    m.toy("beach_ball", 16.0, 12.0, near=4.0)


# --- Lonely Pines Motel --------------------------------------------------------------------------

class Frame:
    """A room seen from its back wall, so that its furniture is written once for every way a
    wing faces. `u` runs along the back wall and `v` from it to the front (the door side);
    `front` is the world direction of the front: 's' is +z, 'n' -z, 'e' +x, 'w' -x. A prop with
    `rel` 0 faces the front, 180 the back, 90 towards +u and -90 towards -u."""

    def __init__(self, m, front, x0, z0, x1, z1, y=0.0):
        self.m, self.front, self.y = m, front, y
        self.x0, self.z0, self.x1, self.z1 = x0, z0, x1, z1
        if front in ("s", "n"):
            self.U, self.V = x1 - x0, z1 - z0
        else:
            self.U, self.V = z1 - z0, x1 - x0
        self.yaw = {"s": 0.0, "n": 180.0, "e": 90.0, "w": -90.0}[front]

    def xz(self, u, v):
        f = self.front
        if f == "s":
            return self.x0 + u, self.z0 + v
        if f == "n":
            return self.x1 - u, self.z1 - v
        if f == "e":
            return self.x0 + v, self.z1 - u
        return self.x1 - v, self.z0 + u

    def prop(self, pid, u, v, rel=0.0, y=0.0):
        x, z = self.xz(u, v)
        yaw = (self.yaw + rel + 180.0) % 360.0 - 180.0
        return self.m.prop(pid, x, z, yaw, y=self.y + y)

    def wall_prop(self, pid, wall, along, y=0.0, gap=0.04, face=0.15):
        """A prop with its back to one of the room's four walls, `along` that wall."""
        sx, _, sz = size_of(pid)
        if wall == "back":
            return self.prop(pid, along, face + gap + sz / 2, 0.0, y)
        if wall == "front":
            return self.prop(pid, along, self.V - face - gap - sz / 2, 180.0, y)
        if wall == "lo":
            return self.prop(pid, face + gap + sz / 2, along, 90.0, y)
        return self.prop(pid, self.U - face - gap - sz / 2, along, -90.0, y)

    def part(self, u0, v0, u1, v1, doors=(), height=3.0):
        """An interior partition from (u0, v0) to (u1, v1); a door is (u, v, options)."""
        xa, za = self.xz(u0, v0)
        xb, zb = self.xz(u1, v1)
        along_x = abs(za - zb) < 1e-9
        ds = []
        for u, v, opts in doors:
            px, pz = self.xz(u, v)
            ds.append((px if along_x else pz, opts))
        W(self.m, xa, za, xb, zb, doors=ds, height=height, y0=self.y, tint=(0.88, 0.84, 0.76))


def motel_room(m, fr):
    """One of the motel's eight rooms: a bathroom in the back corner behind a partition and a
    door, a single bed with its table and lamp, a desk, a television, an armchair, a doormat."""
    fr.part(0.0, 2.5, 2.3, 2.5, doors=[(1.7, 2.5, D("bathroom door", w=0.9))])
    fr.part(2.3, 0.0, 2.3, 2.5)
    fr.prop("furniture_shower_round", 0.8, 0.8)
    fr.prop("furniture_toilet", 1.85, 0.7)
    fr.prop("furniture_bathroom_sink", 0.6, 2.05, 180.0)
    fr.wall_prop("furniture_bed_single", "back", 3.55)
    table = fr.wall_prop("furniture_cabinet_bed_drawer_table", "back", 4.55)
    m.on("furniture_lamp_round_table", table)
    fr.wall_prop("furniture_desk", "hi", 3.7)
    fr.prop("furniture_chair_desk", 3.2, 3.7, 90.0)
    tv = fr.wall_prop("furniture_cabinet_television_doors", "lo", 4.4)
    m.on("furniture_television_modern", tv, yaw=tv.get("yaw", 0.0))
    fr.prop("furniture_lounge_chair", 1.7, 3.9, -90.0)
    fr.prop("furniture_rug_doormat", 2.5, fr.V - 0.7)
    fr.prop("furniture_potted_plant", fr.U - 0.5, fr.V - 0.6)
    fr.prop("furniture_trashcan", 4.5, 5.2)


def motel_wing(m, front, x0, z0, x1, z1, n, number):
    """A wing of `n` rooms facing `front`: floor, ceiling, outer and party walls, a door and a
    window to the walkway and a window at the back of every room, and the rooms themselves."""
    H = 3.0
    axis_x = front in ("s", "n")
    step = ((x1 - x0) if axis_x else (z1 - z0)) / n
    back_c = {"s": z0, "n": z1, "e": x0, "w": x1}[front]
    front_c = {"s": z1, "n": z0, "e": x1, "w": x0}[front]
    back_in = "+" if front in ("s", "e") else "-"
    front_in = "-" if back_in == "+" else "+"
    m.floor(x0, z0, x1, z1, "carpet", (0.55, 0.42, 0.36))
    m.ceiling(x0, z0, x1, z1, H, "ceiling", None, "roof", (0.4, 0.3, 0.28), 0.1)
    rooms = []
    for k in range(n):
        if axis_x:
            fr = Frame(m, front, x0 + k * step, z0, x0 + (k + 1) * step, z1)
        else:
            fr = Frame(m, front, x0, z0 + k * step, x1, z0 + (k + 1) * step)
        rooms.append(fr)
    ax = 0 if axis_x else 1
    doors = [(fr.xz(2.5, fr.V)[ax], D("room %d" % (number + k), w=1.1)) for k, fr in enumerate(rooms)]
    wins = [(fr.xz(4.0, fr.V)[ax], 1.0) for fr in rooms]
    back_wins = [(fr.xz(3.9, 0.0)[ax], 1.0) for fr in rooms] + [(fr.xz(1.0, 0.0)[ax], 0.6) for fr in rooms]
    if axis_x:
        W(m, x0, back_c, x1, back_c, wins=back_wins, outer=True, inward=back_in, height=H)
        W(m, x0, front_c, x1, front_c, doors=doors, wins=wins, outer=True, inward=front_in, height=H)
        for k in range(n + 1):
            p = x0 + k * step
            W(m, p, z0, p, z1, outer=k in (0, n), inward="+" if k == 0 else "-", height=H)
    else:
        W(m, back_c, z0, back_c, z1, wins=back_wins, outer=True, inward=back_in, height=H)
        W(m, front_c, z0, front_c, z1, doors=doors, wins=wins, outer=True, inward=front_in, height=H)
        for k in range(n + 1):
            p = z0 + k * step
            W(m, x0, p, x1, p, outer=k in (0, n), inward="+" if k == 0 else "-", height=H)
    for fr in rooms:
        lit(m, min(fr.x0, fr.x1), min(fr.z0, fr.z1), max(fr.x0, fr.x1), max(fr.z0, fr.z1), H, 0.85)
        motel_room(m, fr)
    return rooms


def post_row(m, x0, z0, x1, z1, step, top=2.8):
    """Posts along a covered walkway's open edge."""
    n = max(1, int(round(max(abs(x1 - x0), abs(z1 - z0)) / step)))
    for i in range(n + 1):
        px = x0 + (x1 - x0) * i / n
        pz = z0 + (z1 - z0) * i / n
        m.span(px - 0.1, px + 0.1, 0.0, top, pz - 0.1, pz + 0.1, "wood", (0.45, 0.35, 0.28))


def lamp_pole(m, x, z, height=4.5, energy=1.0):
    m.span(x - 0.07, x + 0.07, 0.0, height, z - 0.07, z + 0.07, "metal", (0.3, 0.3, 0.33))
    m.span(x - 0.35, x + 0.35, height, height + 0.1, z - 0.2, z + 0.2, "flat", (2.4, 2.0, 1.4), solid=False)
    m.light(x, height - 0.3, z, rng=10.0, energy=energy, colour=(1.0, 0.8, 0.5))


def motel():
    """Lonely Pines Motel: eight rooms in a U of covered walkway round a car park and a pool, an
    office and a diner on the road side, a laundry and a boiler room at the corners of the
    walkway, a storage shed, and a back alley that runs behind the rooms and round both ends.

    The loop: the alley joins the west and east strips, which come out beside the office and the
    diner; the laundry and the boiler room have a door onto the walkway and one onto the alley,
    so the walkway, the alley and the road make a ring. Crowded: the diner. Alone: the shed, the
    laundry at the far end of the alley, the rooms."""
    m = Map(
        "mm_motel", "Lonely Pines Motel",
        "A night at a roadside motel, and one of the guests is not here to sleep. The rooms lock from the inside; the alley does not.",
        DUSK, round_seconds=300,
    )
    H = 3.0
    m.floor(-25, -20, 25, 20, "grass", (0.65, 0.78, 0.6), y=GROUND)
    boundary(m, -25, -20, 25, 20, height=3.0, mat="brick", tint=(0.8, 0.7, 0.66))

    # Ground: the alley and the side strips, the car park, the driveway, the pool deck.
    m.floor(-25, -20, 25, -16, "asphalt", (0.75, 0.75, 0.78))
    m.floor(-25, -16, -20, 20, "sidewalk", (0.9, 0.88, 0.84))
    m.floor(20, -16, 25, 20, "sidewalk", (0.9, 0.88, 0.84))
    m.floor(-12, -8, 0, 8, "asphalt")
    m.floor(0, -8, 12, -6, "asphalt")
    m.floor(0, 6, 12, 8, "asphalt")
    m.floor(-9.85, 8, 1.85, 20, "asphalt")
    m.floor(0, -6, 12, 6, "tile", (0.8, 0.86, 0.9))
    for z in (-6.0, -2.0, 2.0, 5.0):
        m.overlay(-11.5, z, -8.5, z + 0.12, "line", (1.3, 1.3, 1.3))
    m.overlay(-9.0, 8.5, 1.5, 8.62, "line", (1.3, 1.3, 1.3))

    # The pool: a low coping round water you can wade across, a fence with four gates.
    m.overlay(2, -4, 10, 4, "water")
    for a, b, c, d in ((1.7, 10.3, -4.3, -4.0), (1.7, 10.3, 4.0, 4.3), (1.7, 2.0, -4.0, 4.0), (10.0, 10.3, -4.0, 4.0)):
        m.span(a, b, 0.0, 0.25, c, d, "stone", (0.85, 0.85, 0.8))
    fence(m, 0.5, -5.5, 11.5, 5.5, height=1.2, mat="metal", tint=(0.7, 0.72, 0.75),
          gaps=[("w", 4.5, 6.5), ("e", 4.5, 6.5), ("n", 5.0, 7.0), ("s", 5.0, 7.0)], gate={"name": "pool gate"})
    for z in (-3.0, 0.0, 3.0):
        m.prop("furniture_bench_cushion_low", 11.0, z, -90.0)
    m.prop("nature_plant_bush_small", 1.2, -5.0)
    m.prop("nature_plant_bush_small", 1.2, 5.0)

    # --- The rooms: north wing (4), west wing (2), east wing (2) ---
    rooms_all = (motel_wing(m, "e", -20, -10, -14, 0, 2, 1) + motel_wing(m, "s", -10, -16, 10, -10, 4, 3)
                 + motel_wing(m, "w", 14, -10, 20, 0, 2, 7))

    # Covered walkways, with posts and lights.
    for x0, z0, x1, z1 in ((-14, -10, 14, -8), (-14, -8, -12, 0), (12, -8, 14, 0)):
        m.floor(x0, z0, x1, z1, "concrete", (0.8, 0.78, 0.74))
        m.ceiling(x0, z0, x1, z1, 2.8, "ceiling", None, "roof", (0.4, 0.3, 0.28), 0.1)
    post_row(m, -13.0, -8.1, 13.0, -8.1, 4.0)
    post_row(m, -12.1, -4.0, -12.1, 0.0, 2.0)
    post_row(m, 12.1, -4.0, 12.1, 0.0, 2.0)
    for x in (-10.0, -2.0, 6.0, 12.0):
        m.lamp_panel(x, -9.0, 2.8)
        m.light(x, 2.4, -9.0, rng=8.0, energy=0.85, colour=WARM)
    for z in (-4.0,):
        m.light(-13.0, 2.4, z, rng=7.0, energy=0.8, colour=WARM)
        m.light(13.0, 2.4, z, rng=7.0, energy=0.8, colour=WARM)

    # --- Laundry (west corner) and the boiler room (east corner) ---
    for (x0, x1, west, tag) in ((-14.0, -10.0, True, "laundry"), (10.0, 14.0, False, "boiler room")):
        m.floor(x0, -16, x1, -10, "tile", (0.8, 0.8, 0.76))
        m.ceiling(x0, -16, x1, -10, H, "ceiling", None, "roof", (0.4, 0.3, 0.28), 0.1)
        cx = (x0 + x1) / 2
        W(m, x0, -16, x1, -16, doors=[(cx, D("alley door"))], outer=True, inward="+", height=H)
        W(m, x0, -10, x1, -10, doors=[(cx, D("%s door" % tag))], outer=True, inward="-", height=H)
        side = x0 if west else x1
        W(m, side, -16, side, -10, wins=[(-13.0, 0.8)], outer=True, inward="+" if west else "-", height=H)
        lit(m, x0, -16, x1, -10, H, 0.8)
    for i, pid in enumerate(("furniture_washer", "furniture_washer", "furniture_dryer", "furniture_dryer")):
        m.against(pid, "w", -13.85, -14.9 + i * 1.05)
    m.against("furniture_washer_dryer_stacked", "e", -10.15, -12.0)
    m.against("furniture_cardboard_box_closed", "e", -10.15, -14.6)
    m.against("furniture_cardboard_box_open", "e", -10.15, -13.6)
    m.against("furniture_trashcan", "w", -13.85, -10.9)
    m.against("furniture_bookcase_open", "e", 13.85, -14.8)
    m.against("furniture_bookcase_open", "e", 13.85, -13.6)
    m.against("furniture_cardboard_box_closed", "w", 10.15, -15.0)
    m.against("furniture_cardboard_box_closed", "w", 10.15, -14.0)
    m.against("furniture_kitchen_fridge_small", "w", 10.15, -11.2)

    # --- The storage shed, north of the west wing ---
    m.floor(-19, -15, -15, -11.5, "wood_floor", (0.55, 0.42, 0.3))
    m.ceiling(-19, -15, -15, -11.5, 2.6, "wood", None, "roof", (0.35, 0.28, 0.25), 0.3)
    wood = (0.6, 0.45, 0.32)
    W(m, -19, -15, -15, -15, doors=[(-17, D("shed door"))], height=2.6, mat="wood", tint=wood, thick=0.15)
    W(m, -19, -11.5, -15, -11.5, height=2.6, mat="wood", tint=wood, thick=0.15)
    W(m, -19, -15, -19, -11.5, wins=[(-13.2, 0.8)], height=2.6, mat="wood", tint=wood, thick=0.15)
    W(m, -15, -15, -15, -11.5, height=2.6, mat="wood", tint=wood, thick=0.15)
    m.light(-17, 2.1, -13.2, rng=5.0, energy=0.7, colour=(1.0, 0.82, 0.55))
    m.against("furniture_bookcase_open_low", "s", -11.65, -17.8)
    m.against("furniture_cardboard_box_closed", "w", -18.85, -13.8)
    m.against("furniture_cardboard_box_closed", "w", -18.85, -12.8)
    m.against("furniture_cardboard_box_open", "e", -15.15, -13.2)
    m.prop("nature_log_stack", -16.4, -12.3)

    # --- Office (south-west), with its desk, counter and keys ---
    m.floor(-18, 8, -10, 14, "wood_floor", (0.7, 0.55, 0.42))
    m.ceiling(-18, 8, -10, 14, H, "ceiling", None, "roof", (0.4, 0.3, 0.28), 0.1)
    W(m, -18, 8, -10, 8, doors=[(-14, D("office door"))], wins=[(-16.5, 1.6), (-11.5, 1.2)], outer=True, inward="+", height=H)
    W(m, -18, 14, -10, 14, wins=[(-14, 1.4)], outer=True, inward="-", height=H)
    W(m, -18, 8, -18, 14, doors=[(11, D("office back door"))], outer=True, inward="+", height=H)
    W(m, -10, 8, -10, 14, doors=[(11, D("office side door"))], outer=True, inward="-", height=H)
    lit(m, -18, 8, -10, 14, H, 0.9)
    office = Frame(m, "n", -18, 8, -10, 14)
    desk = office.wall_prop("furniture_desk", "back", 4.0)
    m.on("furniture_computer_screen", desk, yaw=desk.get("yaw", 0.0))
    office.prop("furniture_chair_desk", 4.0, 1.7, 180.0)
    for i in range(3):
        office.prop("furniture_kitchen_bar", 2.5 + i, 3.0, 0.0)
    office.wall_prop("furniture_bookcase_open", "back", 1.0)
    office.wall_prop("furniture_bookcase_closed", "back", 7.0)
    office.prop("furniture_coat_rack_standing", 0.7, 5.0)
    radio_table = office.wall_prop("furniture_side_table", "hi", 4.5)
    m.on("furniture_radio", radio_table, yaw=radio_table.get("yaw", 0.0))
    office.prop("furniture_lounge_sofa", 1.4, 4.3, 90.0)
    office.prop("furniture_rug_doormat", 4.0, 5.3)
    office.prop("furniture_potted_plant", 7.4, 5.4)

    # --- Diner and its kitchen (south-east) ---
    m.floor(2, 8, 14, 16, "tile_check", (0.9, 0.85, 0.85))
    m.floor(14, 8, 20, 16, "tile", (0.85, 0.85, 0.82))
    m.ceiling(2, 8, 20, 16, H, "ceiling", None, "roof", (0.4, 0.3, 0.28), 0.1)
    W(m, 2, 8, 20, 8, doors=[(6, D("diner door", w=1.6, leaves=2))], wins=[(3.0, 1.2), (10, 2.0), (12.8, 0.8), (17, 1.2)], outer=True, inward="+", height=H)
    W(m, 2, 16, 20, 16, doors=[(8, D("diner back door"))], wins=[(4, 1.6), (12, 1.6), (17, 1.2)], outer=True, inward="-", height=H)
    W(m, 2, 8, 2, 16, wins=[(12, 1.6)], outer=True, inward="+", height=H)
    W(m, 20, 8, 20, 16, doors=[(12, D("kitchen back door"))], outer=True, inward="-", height=H)
    W(m, 14, 8, 14, 16, doors=[(12, D("kitchen door"))], tint=(0.88, 0.84, 0.76))
    lit(m, 2, 8, 14, 16, H, 1.0)
    lit(m, 14, 8, 20, 16, H, 0.9, colour=(1.0, 0.95, 0.85))
    diner = Frame(m, "n", 2, 8, 14, 16)
    for i in range(6):
        diner.prop("furniture_kitchen_bar", 2.5 + i, 4.0, 0.0)
    for i in range(5):
        diner.prop("furniture_stool_bar", 3.0 + i, 4.9, 0.0)
    for i in range(4):
        diner.wall_prop("furniture_bench_cushion", "back", 2.4 + i * 2.4)
        diner.prop("furniture_table", 2.4 + i * 2.4, 1.6, 90.0)
        diner.prop("furniture_chair", 2.4 + i * 2.4, 2.5, 180.0)
    for u in (2.0, 5.0, 11.0):
        diner.prop("furniture_table", u, 6.6)
        diner.prop("furniture_chair_cushion", u - 0.5, 6.0, 180.0 + 0.0)
        diner.prop("furniture_chair_cushion", u + 0.5, 7.2, 0.0)
    diner.prop("furniture_speaker", 0.5, 4.0)
    diner.prop("furniture_potted_plant", 11.6, 7.4)
    diner.prop("furniture_rug_doormat", 8.0, 7.3)
    kitchen_row(m, 14.2, 19.8, 8.15, "n")
    kitchen_row(m, 14.2, 19.8, 15.85, "s")
    m.prop("furniture_table", 16.8, 12.0)
    m.prop("furniture_trashcan", 19.4, 12.8)

    # --- The road side and the alley ---
    # Cars in the car park and the driveway, and a van-sized wreck in the alley.
    for x, z, tint in ((-10.0, -4.5, (0.7, 0.2, 0.2)), (-10.0, 2.5, (0.25, 0.35, 0.6)), (-4.0, -5.5, (0.85, 0.8, 0.7)),
                       (-4.0, 4.5, (0.2, 0.2, 0.22)), (-6.0, 14.0, (0.35, 0.5, 0.35))):
        car(m, x, z, "z", tint)
    car(m, 4.0, -18.0, "x", (0.5, 0.45, 0.35))
    for x, z in ((-16.5, -18.3), (14.5, -18.4)):
        m.span(x - 1.1, x + 1.1, 0.0, 1.25, z - 0.65, z + 0.65, "metal", (0.2, 0.42, 0.28))
    m.prop("furniture_cardboard_box_closed", -2.0, -17.0)
    m.prop("furniture_cardboard_box_open", 9.0, -18.6)
    # Lamp poles, and the sign by the driveway.
    for x, z in ((-6.0, -1.0), (6.0, 7.0), (-6.0, 8.0), (0.0, -7.0), (-4.0, 16.5), (18.0, 18.0)):
        lamp_pole(m, x, z)
    m.span(3.9, 4.1, 0.0, 5.0, 18.4, 4.6 + 14.0, "metal", (0.25, 0.25, 0.3))
    m.span(2.4, 5.6, 4.1, 5.7, 18.5, 18.75, "flat", (2.2, 0.5, 0.4))
    m.light(4.0, 4.4, 17.0, rng=9.0, energy=0.9, colour=(1.0, 0.45, 0.35))
    # Trees and bushes down the strips and along the front.
    for z in (-12, -6, 0, 6, 12):
        m.prop("nature_tree_tall", -23.2, z + 1.0, z * 7 % 360)
        m.prop("nature_tree_oak", 23.2, z - 1.0, z * 11 % 360)
    for x in (-22, -16, 10, 16, 22):
        m.prop("nature_tree_default", x, 18.6, x * 5 % 360)
    for x in (-8, -4, 8, 13):
        m.prop("nature_plant_bush", x, 19.2)
    for x, z in ((17.0, -13.0), (-22.5, -17.5), (22.5, -17.5)):
        m.prop("nature_tree_pine_tall_a", x, z)
    m.prop("furniture_bench", 17.0, -11.0)
    m.prop("nature_rock_large_a", 17.5, -14.5)

    # --- Spawns: one group, apart: rooms, the offices, the yards. ---
    for fr in rooms_all:
        x, z = fr.xz(3.0, 4.7)
        m.spawn(x, z)
    for x, z in ((-14.0, 11.5), (6.0, 11.0), (17.0, 11.0), (-12.0, -13.0), (12.0, -13.0), (-17.0, -13.2),
                 (-8.0, 0.0), (-3.0, 12.0), (-22.5, 6.0), (22.5, -6.0), (0.0, -18.0), (15.0, -18.0), (-15.0, -18.0)):
        m.spawn(x, z)
    return m.build()


def toys_motel(m):
    """Lamps along the front, a ball by the pool, a bell in the diner."""
    lamps_on_a_switch(m, [(-6.0, 11.0), (-6.0, 17.0), (0.0, 12.0)], (-8.5, 9.0))
    m.toy("beach_ball", 6.0, 0.0, near=3.0)
    m.toy("football", -16.0, 4.0, near=5.0)
    m.toy("bell", 3.2, 10.0, near=3.0)
    m.toy("barrel", -17.0, -14.3, near=3.0)


TOY_PLANS = {"mm_mansion": toys_mansion, "mm_motel": toys_motel}

MAPS = {"mm_mansion": mansion, "mm_motel": motel}


def write_all(check):
    stale = []
    for mid, make in MAPS.items():
        doc = make()
        text = json.dumps(doc, indent=1, sort_keys=False) + "\n"
        path = os.path.join(ROOT, "maps", mid + ".json")
        if check:
            have = open(path).read() if os.path.exists(path) else ""
            if have != text:
                stale.append(mid)
            continue
        with open(path, "w") as f:
            f.write(text)
        print("%-14s %5d boxes %5d props %3d lights %3d doors  %s" % (mid, len(doc["boxes"]), len(doc["props"]), len(doc["lights"]), len(doc["doors"]), doc["name"]))
    if check:
        if stale:
            print("stale: %s (run tools/build_maps.py)" % ", ".join(stale))
            return 1
        print("every map is what the builder writes")
    return 0


def sync_sizes():
    with open(GAME_CATALOGUE) as f:
        cat = json.load(f)
    sizes = {p["id"]: {"size": p["size"]} for p in cat["props"]}
    # Where a thing set down on a prop rests, from the game's part-shaped collision.
    if os.path.exists(GAME_PIECES):
        with open(GAME_PIECES) as f:
            tops = json.load(f).get("tops", {})
        for pid, grid in tops.items():
            if pid in sizes:
                sizes[pid]["tops"] = grid
    with open(SIZES_FILE, "w") as f:
        json.dump({"comment": "Prop sizes from game-murder-mystery's props/catalogue.json, and where a thing set down on a prop rests (tops, from its props/pieces.json), copied by tools/build_maps.py --sync-sizes. The builder stands props against walls and on each other with these; the game measures the models, this is a copy.", "props": sizes}, f, indent=1, sort_keys=True)
        f.write("\n")
    print("copied %d prop sizes" % len(sizes))


if __name__ == "__main__":
    if "--spots" in sys.argv:
        at = sys.argv.index("--spots")
        mid = sys.argv[at + 1]
        y = float(sys.argv[at + 2]) if len(sys.argv) > at + 2 else 0.0
        # The map without its toys, so the spots are the ones a toy could take.
        TOY_PLANS.pop(mid, None)
        holder = {}
        real_build = Map.build
        def capture(self):
            holder["m"] = self
            return real_build(self)
        Map.build = capture
        MAPS[mid]()
        m = holder["m"]
        # A plan of the floor at y, a character a metre: '@' 4 m clear round it, 'o' 2.5 m,
        # '.' 1.2 m, ',' floor with less, ' ' no floor; 'S' a spawn, 'D' a door. North (-z) up.
        xs = [b["at"][0] for b in m.boxes]
        zs = [b["at"][2] for b in m.boxes]
        x0, x1, z0, z1 = int(min(xs)), int(max(xs)) + 1, int(min(zs)), int(max(zs)) + 1
        print("x from %d to %d, z from %d (top) to %d; a tick every 10 m" % (x0, x1, z0, z1))
        print("     " + "".join("|" if x % 10 == 0 else " " for x in range(x0, x1)))
        spawn_at = {(round(s_["at"][0]), round(s_["at"][2])) for side in m.spawns.values() for s_ in side if abs(s_["at"][1] - y) < 1.0}
        door_at = {(round(d["at"][0]), round(d["at"][2])) for d in m.doors if abs(d["at"][1] - y - 1.15) < 1.5}
        for z in range(z0, z1):
            row = []
            for x in range(x0, x1):
                if (x, z) in spawn_at:
                    row.append("S")
                    continue
                if (x, z) in door_at:
                    row.append("D")
                    continue
                if not m._floored(x + 0.0, y, z + 0.0, edge=0.0):
                    row.append(" ")
                    continue
                ch = ","
                for size, c in ((4.0, "@"), (2.5, "o"), (1.2, ".")):
                    TOYS["_probe"] = (size, size, 2.0, True)
                    if m._toy_clear({"toy": "_probe", "at": [x, y, z]}, x, y, z, []) is None:
                        ch = c
                        break
                row.append(ch)
            TOYS.pop("_probe", None)
            print("%4d " % z + "".join(row) + ("  -" if z % 10 == 0 else ""))
        sys.exit(0)
    if "--sync-sizes" in sys.argv:
        sync_sizes()
        sys.exit(0)
    sys.exit(write_all("--check" in sys.argv))
