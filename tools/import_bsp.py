#!/usr/bin/env python3
"""Converts a Source 1 community .bsp (VBSP 19/20) into a murder_map document.

    tools/import_bsp.py <map.bsp> <id> "<Name>" <author> <page-url> [--out=maps/<id>.json] [--style=yard] [--field=round_seconds=300] [--drop-beside=x,z,kind] [--clear=x0,z0,x1,z1] [--prune-pockets] [--widen-doors] [--no-doors] [--slide-doors] [--terrain] [--dusk] [--skip-start=N] [--skip-door=x,z] [--cover=N] [--cover-gap=m] [--blurb=text] [--drop-kind=id] [--thin=id:N]

Adapted from hide-n-seek-maps' importer (copied, not linked): one spawn group, `players`, from the author's starts plus the clearest open floor up to 24.

--field=<name>=<number> sets a document number (round_seconds); --drop-beside, --clear, --prune-pockets, --widen-doors, --no-doors, --slide-doors, --terrain, --drop-kind, --thin are as in that importer; a rerun keeps them.

What it does, and why each choice:

- The world's brushes become BOXES, because a map document has no meshes. Each brush's convex
  hull is found (dotbsp's reader, dot-map/tools/bsp) and its bounding
  box is written; a brush that is NOT a box (a roof slope, a stair) is cut into slabs along its
  longer horizontal axis, each slab as tall as the brush is at the slab's middle, so a ramp
  becomes a staircase of 0.3 m risers rather than a block twice its height.
- Axes: Source is Z-up, godot = (x, z, -y). Scale: 1 unit = 0.01905 m (the engine's own
  0.75 inch), which makes a 108-unit door 2.06 m, fits the game's 1.4 m x 2.3 m door convention.
- Textures are NOT carried. The author's textures are replaced with the game's own materials
  (Kenney's grid under pastels, ph_materials.gd); TEXTURE_MAP says which, by name.
- prop_physics become catalogue props by PROP_MAP (the author's HL2 models have no licence we can
  ship; the catalogue is Kenney, CC0). A model with no entry is dropped and counted. PROP_MAP is
  the prop-hunt importer's, whose catalogue has bottles and cans (a disguise); this game's has
  none, and a hider is a person, so HS_SWAP turns a crate or a barrel into a box or a bin a
  person crouches behind and drops what is hand-sized (bottles, mugs, cartons, cans).
- Each prop_door_rotating becomes a real door (`add_doors`): the doorway beside its hinge is
  measured from the finished boxes, and a door that does not find one is reported, not guessed.
- info_player_start entries are shared out between the two teams; `light` entities become omni lights.
- Tool brushes (skybox, clip, trigger, hint, nodraw-only) are dropped.

The output goes through build_maps.Map.build(), so spawns are settled and checked there.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _dotbsp_path():
    """dot-map's tools/bsp: $DOTBSP_PATH, else the sibling checkout dot-bootstrap makes."""
    for p in (os.environ.get("DOTBSP_PATH", ""), os.path.join(HERE, "..", "..", "dot-map", "tools", "bsp")):
        if p and os.path.isfile(os.path.join(p, "dotbsp", "reader.py")):
            return os.path.abspath(p)
    sys.exit("import_bsp: dot-map's tools/bsp was not found; clone dot-map beside this "
             "repository (dot-bootstrap does) or set DOTBSP_PATH to its tools/bsp")


sys.path.insert(1, _dotbsp_path())
from dotbsp import reader as bsp_read  # noqa: E402  (the family's one reader)
from dotbsp import boxes as dboxes, docboxes, lights as dlights  # noqa: E402  (the shared passes over a document's boxes)
import build_maps  # noqa: E402

S = 0.01905
SKIP_STARTS = set()   # --skip-start=N: the author's Nth start, which the build says is inside a box
SKIP_DOORS = []   # --skip-door=x,z (finished coordinates): a doorway left open, for a door the game's swing check refuses

# This game's catalogue has no food_* or survival_*: a person hides, not a bottle. "" drops.
HS_SWAP = {
    "food_watermelon": "nature_crop_melon", "survival_barrel": "furniture_trashcan",
    "survival_bucket": "", "survival_bottle": "", "survival_bottle_large": "", "survival_box": "furniture_cardboard_box_closed",
    "food_carton_small": "", "food_soda_can": "", "survival_box_large": "furniture_cardboard_box_closed",
    "food_mug": "", "food_cup_coffee": "", "survival_chest": "furniture_cardboard_box_closed", "food_banana": "", "food_pot": "",
}
SLAB = 28.0     # source units: ~0.53 m, a slope's riser

TOOLS = ("TOOLS/", "tools/")
TEXTURE_MAP = [
    ("CEILINGTILE", "ceiling", None),
    ("OFFCEILING", "concrete", None),
    ("CARPET", "carpet", None),
    ("BLINDS", "glass", None),
    ("LIGHTCOVER", "glass", (1.00, 1.00, 0.92)),
    ("OFFWNDW", "glass", None),
    ("TRUSS", "metal", None),
    ("DRTRIM", "metal", None),
    ("ELEVDR", "metal", None),
    ("PARTICLEBOARD", "wood", None),
    ("OFFDR", "wood", None),
    ("DESKTOP", "wood", None),
    ("WALLOFFICE", "paint", (0.92, 0.94, 1.00)),
    ("OFFWLLB", "plaster", (0.90, 0.95, 1.00)),
    ("OFFWLLC", "paint", (0.96, 0.94, 0.88)),
    ("BUILDING_TEMPLATE", "plaster", (0.95, 0.90, 0.82)),
    ("GLASSWINDOW", "glass", None),
    ("CEILING01", "ceiling", None),
    ("BUILDING", "concrete", None),
    ("PLASTER", "plaster", (0.95, 0.92, 0.84)),
    ("GRASS", "grass", (0.85, 0.95, 0.75)),
    ("ACOUSTICCEILING", "ceiling", None),
    ("TILEFLOOR", "tile", None),
    ("WOODFLOOR", "parquet", None),
    ("TILEROOF", "roof", (1.00, 0.72, 0.62)),
    ("COMBINEGLASS", "glass", None),
    ("CONCRETE", "concrete", None),
    ("STONE", "stone", None),
    ("BRICK", "brick", None),
    ("WOOD", "wood", None),
    ("METAL", "metal", None),
    ("DEV/", "flat", (0.8, 0.8, 0.82)),
]

# HL2 model -> catalogue id. Pieces with no counterpart in the catalogue are left out.
PROP_MAP = {
    "furniture_lamp01a": "furniture_lamp_round_table",
    "watermelon01": "food_watermelon",
    "chair_wood01": "furniture_chair",
    "oildrum001": "survival_barrel",
    "metal_paintcan001a": "survival_bucket",
    "garbage_newspaper001a": "furniture_books",
    "cardboard_box001b": "furniture_cardboard_box_closed",
    "furnituretable001a": "furniture_table",
    "glassbottle01a": "survival_bottle",
    "trashbin01a": "furniture_trashcan",
    "plasticcrate01a": "survival_box",
    "garbage_milkcarton002a": "food_carton_small",
    "popcan01a": "food_soda_can",
    "wood_crate001a": "survival_box_large",
    "wood_crate002a": "survival_box",
    "furniturecouch001a": "furniture_lounge_sofa",
    "tv_monitor01": "furniture_television_vintage",
    "furnituredresser001a": "furniture_cabinet_bed_drawer_table",
    "breenglobe": "nature_pot_small",
    "monitor01a": "furniture_computer_screen",
    "computer01_keyboard": "furniture_computer_keyboard",
    "breenclock": "furniture_radio",
    "huladoll": "furniture_bear",
    # An office (ph_office221): paper, drawers, screens and boxes.
    "file_cabinet1": "furniture_side_table_drawers",
    "file_cabinet2": "furniture_side_table_drawers",
    "file_cabinet3": "furniture_side_table_drawers",
    "chair_office": "furniture_chair_desk",
    "binderredlabel": "furniture_books",
    "bindergreen": "furniture_books",
    "binderblue": "furniture_books",
    "bindergraylabel01a": "furniture_books",
    "bindergraylabel01b": "furniture_books",
    "binderbluelabel": "furniture_books",
    "bindergreenlabel": "furniture_books",
    "clipboard": "furniture_books",
    "cardboard_box01": "furniture_cardboard_box_closed",
    "cardboard_box02": "furniture_cardboard_box_closed",
    "cardboard_box03": "furniture_cardboard_box_closed",
    "cardboard_box001a": "furniture_cardboard_box_closed",
    "cardboard_box003a": "furniture_cardboard_box_open",
    "cardboard_box003b": "furniture_cardboard_box_open",
    "cardboard_box004a": "furniture_cardboard_box_closed",
    "box01a": "survival_box",
    "box01b": "survival_box",
    "file_box": "survival_box",
    "plant01": "furniture_potted_plant",
    "cactus": "nature_cactus_tall",
    "coffee_mug": "food_mug",
    "coffee_mug2": "food_mug",
    "coffee_mug3": "food_mug",
    "garbage_coffeemug001a_forevergibs": "food_cup_coffee",
    "phone": "furniture_speaker_small",
    "projector": "furniture_speaker_small",
    "projector_remote": "furniture_computer_mouse",
    "computer_caseb": "furniture_speaker",
    "computer_keyboard": "furniture_computer_keyboard",
    "computer_monitor": "furniture_computer_screen",
    "computer_mouse": "furniture_computer_mouse",
    "trash_can": "furniture_trashcan",
    "trash_can_p": "furniture_trashcan",
    "garbage_beercan01a": "food_soda_can",
    "garbage_plasticbottle001a": "survival_bottle",
    "garbage_plasticbottle002a": "survival_bottle",
    "garbage_plasticbottle002a_fullsheet": "survival_bottle",
    "garbage_takeoutcarton001a": "food_carton_small",
    "suitcase_passenger_physics": "survival_chest",
    "metalbucket01a": "survival_bucket",
    "pi_bucket": "survival_bucket",
    "tv_plasma": "furniture_television_modern",
    "table_coffee": "furniture_table_coffee",
    # A flat (ph_apartment): the kitchen table's leftovers, bedroom and living room.
    "garbage_metalcan002a": "food_soda_can",
    "garbage_plasticbottle003a": "survival_bottle",
    "garbage_coffeemug001a": "food_mug",
    "garbage_glassbottle001a": "survival_bottle",
    "garbage_glassbottle003a": "survival_bottle",
    "garbage_milkcarton001a": "food_carton_small",
    "water_bottle": "survival_bottle",
    "bottle03": "survival_bottle",
    "wood_table": "furniture_table",
    "furniture_shelf01a": "furniture_bookcase_closed",
    "furniturechair001a": "furniture_chair",
    "chairantique": "furniture_chair",
    "bed": "furniture_bed_double",
    "potted_plant1": "furniture_potted_plant",
    "potted_plant2": "furniture_potted_plant",
    "potted_plant3": "furniture_potted_plant",
    "bananna": "food_banana",
    "doll01": "furniture_bear",
    "trashdumpster01a": "survival_box_large",
    "furnituretable003a": "furniture_side_table",
    "desklamp01": "furniture_lamp_square_table",
    "radio": "furniture_radio",
    # A hotel (ph_hotel) and a ruined church with a cellar (ph_abandoned_church).
    "furniture_couch01a": "furniture_lounge_sofa",
    "couch": "furniture_lounge_sofa",
    "sofa": "furniture_lounge_sofa",
    "sofa_chair": "furniture_lounge_chair",
    "furnituredrawer001a": "furniture_cabinet_bed_drawer",
    "furnituredrawer002a": "furniture_cabinet_bed_drawer",
    "furnituredrawer003a": "furniture_side_table_drawers",
    "furniture_cabinetdrawer01a": "furniture_cabinet_bed_drawer",
    "bookshelf1": "furniture_bookcase_closed",
    "shelfunit01a": "furniture_bookcase_open",
    "furnitureshelf001a": "furniture_bookcase_open",
    "kitchen_shelf001a": "furniture_bookcase_open_low",
    "newspaperstack01": "furniture_books",
    "paper_towels": "food_carton_small",
    "furnituresink001a": "furniture_kitchen_sink",
    "furniturestove001a": "furniture_kitchen_stove",
    "cafeteria_table001a": "furniture_table",
    "cafeteria_bench001a": "furniture_bench",
    "furnituretable002a": "furniture_table",
    "chair02a": "furniture_chair",
    "controlroom_desk001a": "furniture_desk",
    "metalpot001a": "food_pot",
    "metalpot002a": "food_pot",
    "pot01a": "food_pot",
    "jar01a": "survival_bottle",
    "jar01b": "survival_bottle",
    "glassjug01": "survival_bottle_large",
    "vendingmachine": "furniture_kitchen_fridge_small",
    "kennel": "survival_box_large",
    "citizenradio": "furniture_radio",
    "pottery04a": "nature_pot_small",
    "pottery02a": "nature_pot_small",
    "metalbucket02a": "survival_bucket",
    "garbage_metalcan001a": "furniture_trashcan",
    "garbage_bag001a": "survival_bucket",
    "wine_barrel": "survival_barrel",
    "grainbasket01a": "survival_bucket",
    "grainbasket01b": "survival_bucket",
    "grainbasket01c": "survival_bucket",
    "claypot01": "nature_pot_small",
    "claypot01_damage_01": "nature_pot_small",
    "claypot01_damage_02": "nature_pot_small",
    "claypot01_damage_03": "nature_pot_small",
    "claypot01_damage_04": "nature_pot_small",
    "claypot02": "nature_pot_large",
    "claypot02_damage_01": "nature_pot_large",
    "claypot02_damage_02": "nature_pot_large",
    "claypot02_damage_03": "nature_pot_large",
    "claypot02_damage_04": "nature_pot_large",
    "pottery_large01a": "nature_pot_large",
    "gravestone001a": "nature_stone_large_a",
    "shrub_01a": "nature_plant_bush_small",
    "bramble001a": "nature_plant_bush",
    "militiarock05": "nature_rock_small_a",
    "hallo_pumpkin_l": "nature_crop_pumpkin",
    "hallo_pumpkin_m": "nature_crop_pumpkin",
    "hallo_pumpkin_s": "nature_crop_pumpkin",
    "hallo_pumpkin_xl": "nature_crop_pumpkin",
    "concrete_chunk03a": "nature_stone_small_a",
    "concrete_chunk04a": "nature_stone_small_a",
    "concrete_chunk05g": "nature_stone_small_a",
    "concrete_chunk02a": "nature_stone_small_a",
    "concrete_chunk09a": "nature_stone_small_a",
    "grainbasket01c_gib1": "survival_bucket",
    "grainbasket01c_gib2": "survival_bucket",
    "wood_pallet_debris_03": "survival_box",
    "wood_pallet_debris_04": "survival_box",
    "wood_pallet_debris_06": "survival_box",
    "wood_pallet_debris_11": "survival_box",
    "wood_pallet_debris_12": "survival_box",
}


# The author left every wall that is not a house as a developer grid. Those are given a
# suburban surface by what the box IS, since its texture says nothing: size and height tell a
# neighbour's tall wall from a fence, a path, a roof slab or a shed. Every name is an existing
# PhMaterials surface; the tint only chooses which pastel family it is.


# Every entity class an author uses for a loose prop; the _dynamic ones are placed furniture
# that does not move in the original, which a catalogue prop is not either (it is a disguise).
PROP_CLASSES = ("prop_physics", "prop_physics_multiplayer", "prop_physics_override",
                "prop_dynamic", "prop_dynamic_override")
START_CLASSES = ("info_player_start", "info_player_terrorist", "info_player_counterterrorist",
                 "info_player_deathmatch", "info_player_teamspawn")


def gd(p):
    return (p[0] * S, p[2] * S, -p[1] * S)


def kv(e, k, default=None):
    return e.get(k, default)


def vec(s):
    return [float(x) for x in s.split()]


def planes_of(bsp, index):
    first, count, _ = bsp.brushes[index]
    return [bsp.planes[s[0]][:4] for s in bsp.brushsides[first:first + count] if not s[3]]


def z_range(planes, x, y):
    lo, hi = -1e9, 1e9
    for nx, ny, nz, d in planes:
        if abs(nz) < 1e-6:
            continue
        z = (d - nx * x - ny * y) / nz
        if nz > 0:
            hi = min(hi, z)
        else:
            lo = max(lo, z)
    return lo, hi


def box_in_frame(pts, phi, tol):
    """The hull's extents in a frame turned phi degrees about z, or None when some corner is not
    a corner of that bounding box. (x0, x1), (y0, y1), (z0, z1), in the turned frame."""
    c, sn = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    q = [(p[0] * c + p[1] * sn, -p[0] * sn + p[1] * c, p[2]) for p in pts]
    x0, x1 = min(p[0] for p in q), max(p[0] for p in q)
    y0, y1 = min(p[1] for p in q), max(p[1] for p in q)
    z0, z1 = min(p[2] for p in q), max(p[2] for p in q)
    for p in q:
        if not ((abs(p[0] - x0) < tol or abs(p[0] - x1) < tol) and (abs(p[1] - y0) < tol or abs(p[1] - y1) < tol)
                and (abs(p[2] - z0) < tol or abs(p[2] - z1) < tol)):
            return None
    return (x0, x1), (y0, y1), (z0, z1)


def turned_box(bsp, index, pts):
    """(box, phi) when the brush is a box turned about the vertical axis, else None. The author's
    building is not always on the grid (a room at thirty degrees to the rest), and cutting such a
    wall into axis-aligned slabs gives a saw-tooth the players catch on. The angle is each upright
    side's direction modulo 90, tried in turn; the document's boxes carry a yaw."""
    first, count, _ = bsp.brushes[index]
    tried = set()
    for sd in bsp.brushsides[first:first + count]:
        if sd[3]:
            continue
        nx, ny, nz, _d = bsp.planes[sd[0]][:4]
        if abs(nz) > 1e-4:
            continue
        phi = round(math.degrees(math.atan2(ny, nx)) % 90.0, 2)
        if phi in tried or phi < 0.05 or phi > 89.95:
            continue
        tried.add(phi)
        # Four-decimal planes at 1000 units leave a unit of slack in the corners.
        box = box_in_frame(pts, phi, 1.5)
        if box is not None:
            return box, phi
    return None


def prism_box(pts):
    """(box, phi) for a brush that is a vertical prism of any plan shape: the smallest turned
    rectangle round its plan. A curved wall is a run of such wedges and a column of a round room
    is one; the box overhangs the wedge by a sliver, where cutting it into axis-aligned slabs (a
    slope's treatment, wrong for a plan shape) bit chunks out of the room. None for a brush whose
    top or bottom is not flat and level."""
    zs = sorted({round(p[2], 1) for p in pts})
    if len(zs) != 2:
        return None
    low = {(round(p[0], 1), round(p[1], 1)) for p in pts if abs(p[2] - zs[0]) < 0.15}
    high = {(round(p[0], 1), round(p[1], 1)) for p in pts if abs(p[2] - zs[1]) < 0.15}
    if low != high or len(low) < 3:
        return None
    plan = [(x, y, zs[0]) for x, y in low]
    best = None
    for (ax, ay), (bx_, by) in ((p, q) for p in low for q in low if p != q):
        phi = math.degrees(math.atan2(by - ay, bx_ - ax)) % 90.0
        box = box_in_frame(plan, phi, 1e9)
        area = (box[0][1] - box[0][0]) * (box[1][1] - box[1][0])
        if best is None or area < best[0] - 1e-6:
            best = (area, phi, box)
    _a, phi, box = best
    return (box[0], box[1], (zs[0], zs[1])), phi


def brush_boxes(bsp, index):
    """[((x range), (y range), (z range), phi)] in Source units, the ranges in a frame turned phi
    degrees (0 for most), and whether the brush had to be cut into slabs."""
    pts = bsp.brush_hull(index)
    if len(pts) < 4:
        return [], 0
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    z0, z1 = min(p[2] for p in pts), max(p[2] for p in pts)
    box_vol = (x1 - x0) * (y1 - y0) * (z1 - z0)
    # Hull volume from the corner points: a brush is a box when every corner is a box corner.
    corners = sum(1 for p in pts if (abs(p[0] - x0) < 0.5 or abs(p[0] - x1) < 0.5) and (abs(p[1] - y0) < 0.5 or abs(p[1] - y1) < 0.5) and (abs(p[2] - z0) < 0.5 or abs(p[2] - z1) < 0.5))
    if corners == len(pts):
        return [((x0, x1), (y0, y1), (z0, z1), 0.0)], 0
    tb = turned_box(bsp, index, pts)
    if tb is not None:
        return [tb[0] + (tb[1],)], 0
    pb = prism_box(pts)
    if pb is not None:
        return [pb[0] + (pb[1],)], 0
    pl = planes_of(bsp, index)
    out = []
    if x1 - x0 >= y1 - y0:
        n = max(1, math.ceil((x1 - x0) / SLAB))
        for i in range(n):
            a, b = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n
            lo, hi = z_range(pl, (a + b) / 2, (y0 + y1) / 2)
            lo, hi = max(lo, z0), min(hi, z1)
            if hi - lo > 0.5:
                out.append(((a, b), (y0, y1), (lo, hi), 0.0))
    else:
        n = max(1, math.ceil((y1 - y0) / SLAB))
        for i in range(n):
            a, b = y0 + (y1 - y0) * i / n, y0 + (y1 - y0) * (i + 1) / n
            lo, hi = z_range(pl, (x0 + x1) / 2, (a + b) / 2)
            lo, hi = max(lo, z0), min(hi, z1)
            if hi - lo > 0.5:
                out.append(((x0, x1), (a, b), (lo, hi), 0.0))
    return out, 1


# Furniture a crouching person fits behind, for a map the author furnished too thinly to hide in
# (the author's own props were mostly bottles, which this game's catalogue has not: --cover).
COVER_INDOOR = ("furniture_bed_single", "furniture_bookcase_closed_wide", "furniture_cabinet_bed_drawer", "furniture_lounge_sofa",
                "furniture_kitchen_cabinet", "furniture_bed_double", "furniture_cabinet_television", "furniture_side_table_drawers")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    out_path = None
    style = ""
    fields = {}
    drops = []
    clears = []
    pockets = False
    widen = False
    no_doors = False
    slide = False
    cover = 0
    dusk = False
    max_lights = 128
    cover = 0
    cover_gap = 3.0
    blurb = ""
    cover_gap = 2.5
    cover_clear = 2.0
    hiders_far = 0.0
    hiders_at = None
    cover_away = (0.0, 0.0)
    lobby = None
    cover_seed = 7
    drop_kinds = []
    thin = {}
    terrain = False
    for a in argv[1:]:
        if a.startswith("--out="):
            out_path = a[6:]
        elif a.startswith("--cover="):
            cover = int(a[8:])
        elif a.startswith("--cover-gap="):
            cover_gap = float(a[12:])
        elif a.startswith("--skip-door="):
            SKIP_DOORS.append(tuple(float(t) for t in a[12:].split(",")))
        elif a.startswith("--skip-start="):
            SKIP_STARTS.add(int(a[13:]))
        elif a.startswith("--max-lights="):
            max_lights = int(a[13:])
        elif a == "--dusk":
            dusk = True
        elif a.startswith("--blurb="):
            blurb = a[8:]
        elif a == "--widen-doors":
            widen = True
        elif a == "--no-doors":
            no_doors = True
        elif a.startswith("--drop-kind="):
            drop_kinds.append(a[12:])
        elif a.startswith("--thin="):
            k, _, n = a[7:].partition(":")
            thin[k] = int(n)
        elif a == "--slide-doors":
            slide = True
        elif a == "--terrain":
            terrain = True
        elif a == "--prune-pockets":
            pockets = True
        elif a.startswith("--style="):
            style = a[8:]
        elif a.startswith("--field="):
            k, _, v = a[8:].partition("=")
            fields[k] = float(v)
        elif a.startswith("--clear="):
            clears.append(tuple(float(t) for t in a[8:].split(",")))
        elif a.startswith("--drop-beside="):
            t = a[14:].split(",")
            drops.append((float(t[0]), float(t[1]), t[2] if len(t) > 2 else ""))
    bsp_path, mid, name, author, url = args[:5]
    bsp = bsp_read.Bsp(bsp_path).load()
    m = build_maps.Map(
        mid, name, blurb or "Converted from %s by %s (%s)." % (os.path.basename(bsp_path), author, url),
        dict(build_maps.DUSK) if dusk else {"sky_top": [0.32, 0.52, 0.82], "sky_horizon": [0.72, 0.82, 0.92], "ground": [0.35, 0.33, 0.30],
         "sun_pitch": -55, "sun_yaw": 30, "sun_energy": 1.0, "ambient": [0.62, 0.66, 0.72], "ambient_energy": 0.5},
        kill_y=-20.0)
    m.doc["author"] = author
    m.doc.update(fields)
    m.doc["source"] = url

    sliced = skipped = 0
    for bi in sorted(bsp.model_brushes(0)):
        names = docboxes.brush_material_names(bsp, bi)
        mt = docboxes.majority_material(names, TEXTURE_MAP, ("flat", None))
        invisible = False
        if mt is None:
            # The author's sky box is the map's wall: solid to a player, drawn as nothing.
            if any("TOOLSSKYBOX" in n for n in names):
                mt, invisible = ("flat", None), True
            else:
                skipped += 1
                continue
        boxes, was_sliced = brush_boxes(bsp, bi)
        sliced += was_sliced
        for (x0, x1), (y0, y1), (z0, z1), phi in boxes:
            if phi:
                # A turned box: its centre back out of the turned frame, its sides as measured,
                # its yaw the same angle (Source turns counter-clockwise seen from above, and so
                # does godot about +y once y is flipped to -z).
                if x1 - x0 < 0.05 or y1 - y0 < 0.05 or z1 - z0 < 0.05:
                    continue
                c, sn = math.cos(math.radians(phi)), math.sin(math.radians(phi))
                lx, ly = (x0 + x1) / 2, (y0 + y1) / 2
                gx, gy, gz = gd((lx * c - ly * sn, lx * sn + ly * c, (z0 + z1) / 2))
                bx = m.box((gx, gy, gz), ((x1 - x0) * S, (z1 - z0) * S, (y1 - y0) * S), mt[0], mt[1], yaw=phi)
            else:
                # Source y is godot -z: the box's range flips.
                bx = m.span(x0 * S, x1 * S, z0 * S, z1 * S, -y1 * S, -y0 * S, mt[0], mt[1])
            if invisible and bx is not None:
                bx["visible"] = False
            elif bx is not None and mt[0] == "flat" and style == "yard":
                bx["mat"], tint = docboxes.suburban_surface(bx["at"], bx["size"])
                if tint is not None:
                    bx["tint"] = list(tint)
                else:
                    bx.pop("tint", None)
    if terrain:
        n = 0
        tris = []
        for f in bsp.model_faces(0):
            if f[6] >= 0:
                tris += bsp.displacement_tris(f)
        for c in dboxes.terrain_cells(tris):
            # terrain_cells names the axes as the map does (z is height); this loop's y is the height, z the map's y.
            (x0, x1), (y0, y1), (z0, z1), mat = c["x"], c["z"], c["y"], "grass"
            m.span(x0 * S, x1 * S, y0 * S, y1 * S, -z1 * S, -z0 * S, mat, (0.85, 0.9, 0.78))
            n += 1
        print("terrain: %d ground boxes from the displacements" % n)
    print("brushes %d  tool-only %d  sliced %d  boxes %d" % (len(bsp.model_brushes(0)), skipped, sliced, len(m.boxes)))

    docboxes.drop_door_leaves(m.boxes)
    docboxes.prune_far_scenery(m.boxes, [gd(vec(e["origin"])) for e in bsp.entities if e.get("classname") in START_CLASSES])

    # Props: sit on the highest solid box under the footprint when one is within reach of the
    # source height, else at the source height (a lamp on a table the author placed as a prop).
    def support(x, z, pid, yaw, ymax):
        """The highest thing under the footprint no higher than ymax: a box's top, or a prop
        already set down (`rest_on`, its collision as the game measured it). The catalogue's
        table is not the author's table, so a lamp set at the author's table-top height would
        hang in the air; it is put on whatever is really there instead."""
        best = 0.0 if ymax >= 0.0 else None
        fw, fd = build_maps.footprint(pid, yaw) if pid else (0.0, 0.0)
        for b in m.boxes:
            if not b.get("solid", True):
                continue
            if docboxes.within(b, x, z, 0.001):
                t = b["at"][1] + b["size"][1] / 2
                if t <= ymax and (best is None or t > best):
                    best = t
        for q in (m.props if pid else ()):
            qw, qd = build_maps.footprint(q["id"], q.get("yaw", 0.0))
            # Well inside the footprint, not on its rim: a round bin's corner is air.
            if abs(x - q["at"][0]) <= qw / 2 - 0.08 and abs(z - q["at"][2]) <= qd / 2 - 0.08:
                t = q["at"][1] + build_maps.rest_on(q, x - q["at"][0], z - q["at"][2], pid, yaw)
                if t <= ymax and (best is None or t > best):
                    best = t
        return best

    dropped = {}
    placed = []
    lights = []
    for e in bsp.entities:
        cls = e.get("classname")
        if cls in PROP_CLASSES:
            # Keys are matched lower-cased: authors spell one model Chair_office and chair_office.
            key = os.path.splitext(os.path.basename(e.get("model", "")))[0].lower()
            pid = PROP_MAP.get(key)
            pid = HS_SWAP.get(pid, pid)
            if not pid:
                dropped[key] = dropped.get(key, 0) + 1
                continue
            placed.append((vec(e["origin"])[2], e, pid))
        elif cls in ("light", "light_spot"):
            o = vec(e["origin"])
            gx, gy, gz = gd(o)
            c = vec(e.get("_light", "255 255 255 200"))
            lights.append((gx, gy, gz, min(1.2, c[3] / 200.0), [c[0] / 255, c[1] / 255, c[2] / 255]))
    # A map documents at most 128 lights and a browser draws 8 a surface: keep the author's lights at least
    # `gap` metres apart, widening the gap until they fit, each kept one a little stronger for those it stood for.
    kept_l, gap = dlights.thin_by_gap(lights, max_lights)
    for gx, gy, gz, en, col in kept_l:
        m.light(gx, gy, gz, rng=9.0 + gap, energy=dlights.strengthen(en, gap), colour=col)
    if gap:
        print("lights: %d of the author's %d kept, %.1f m apart" % (len(kept_l), len(lights), gap))
    def floor_corners_ok(x, z, pid, yaw, y):
        """A prop standing on the ground has solid floor under every corner of its footprint:
        the author's cellar stair is a hole in the floor, and a crate on its rim hung half over it."""
        fw, fd = build_maps.footprint(pid, yaw)
        for dx in (-fw / 2 + 0.03, fw / 2 - 0.03):
            for dz in (-fd / 2 + 0.03, fd / 2 - 0.03):
                ok = False
                for b in m.boxes:
                    if not b.get("solid", True):
                        continue
                    if docboxes.within(b, x + dx, z + dz):
                        if abs(b["at"][1] + b["size"][1] / 2 - y) < 0.06:
                            ok = True
                            break
                if not ok:
                    return False
        return True

    # Lowest first, so a table is down before the lamp the author put on it.
    for _, e, pid in sorted(placed, key=lambda t: t[0]):
        ang = vec(e.get("angles", "0 0 0"))
        gx, gy, gz = gd(vec(e["origin"]))
        yaw = (ang[1] + 90.0) % 360.0
        y = support(gx, gz, pid, yaw, gy + 0.35)
        if y is None:
            y = max(gy, 0.0)
        if y < 0.06 and not floor_corners_ok(gx, gz, pid, yaw, y) and not any(
                abs(q["at"][0] - gx) < 0.01 and abs(q["at"][2] - gz) < 0.01 for q in m.props):
            dropped["(over a hole)"] = dropped.get("(over a hole)", 0) + 1
            continue
        m.prop(pid, gx, gz, yaw=yaw, y=y)
    starts = [e for e in bsp.entities if e.get("classname") in START_CLASSES]
    gstarts = [gd(vec(e["origin"])) for e in starts]
    ys = sorted((support(g[0], g[2], None, 0.0, g[1] + 0.6) or g[1] - 0.05) for g in gstarts)
    floor_y = 0.0
    if cover:
        # Furniture to crouch behind on each floor the author's starts stand on (a map furnished thinly),
        # a share of the count for each, seeded so a rerun is the same.
        levels = sorted({round(support(g[0], g[2], None, 0.0, g[1] + 0.6) or max(g[1] - 0.05, 0.0), 2) for g in gstarts})
        for lv in levels:
            print("cover furniture at floor %.2f: %d placed" % (lv, docboxes.scatter_cover(m, max(2, cover // len(levels)), 7, COVER_INDOOR, spacing=cover_gap, clear=1.6, floor_y=lv)))
    # Everybody starts apart: the author's starts (they stand on whatever floor is under them), then
    # the clearest open floor until there are 24, at least 6 m from any other start.
    for i, e in enumerate(starts):
        if i in SKIP_STARTS:
            continue
        gx, gy, gz = gstarts[i]
        ang = vec(e.get("angles", "0 0 0"))
        floor = support(gx, gz, None, 0.0, gy + 0.6)
        if floor is None:
            print("start %d at (%.1f, %.1f, %.1f) has no floor under it: left out" % (i, gx, gy, gz))
            continue
        m.spawn(gx, gz, yaw=ang[1] - 90.0, y=floor + 0.05)
    have = [(sp["at"][0], sp["at"][2]) for sp in m.spawns["players"]]
    for size, x, z in m.spots(step=2.0, top=200):
        if len(m.spawns["players"]) >= 24:
            break
        if all((x - a) ** 2 + (z - b) ** 2 >= 36.0 for a, b in have):
            m.spawn(x, z, yaw=0.0, y=0.05)
            have.append((x, z))
    print("props %d  lights %d  spawns %d  dropped models %s" % (len(m.props), len(m.lights), len(starts), dropped))
    doc = m.build()
    # Move the map so its origin stands on open ground. The collision audit tests a drawn
    # MultiMesh by its bounds, which a headless renderer reports as a point at the origin; a
    # map whose origin hangs in the air (this one's was outside the yard) fails it for every prop.
    ground = [b for b in doc["boxes"] if b.get("solid", True) and abs(b["at"][1] + b["size"][1] / 2) < 0.05
              and b["size"][0] > 4.0 and b["size"][2] > 4.0]
    oy = 0.0
    if not ground:
        # A flat on the author's first floor (ph_apartment): the play floor is a metre or so above
        # the world's zero, with the building's footing under it. Lower the whole map so the floor
        # the spawns stand on is y = 0, which is where the game, the audit and the bots expect it.
        ys = sorted(sp["at"][1] for sp in doc["spawns"]["players"])
        oy = round(ys[len(ys) // 2] - 0.05, 3)
        ground = [b for b in doc["boxes"] if b.get("solid", True) and abs(b["at"][1] + b["size"][1] / 2 - oy) < 0.05
                  and b["size"][0] > 4.0 and b["size"][2] > 4.0]
    ox = oz = 0.0
    if ground:
        cx = sum(sp["at"][0] for sp in doc["spawns"]["players"]) / len(doc["spawns"]["players"])
        cz = sum(sp["at"][2] for sp in doc["spawns"]["players"]) / len(doc["spawns"]["players"])
        g = min(ground, key=lambda b: (b["at"][0] - cx) ** 2 + (b["at"][2] - cz) ** 2)
        ox, oz = g["at"][0], g["at"][2]
        def shift(o):
            if isinstance(o, dict):
                if isinstance(o.get("at"), list) and len(o["at"]) == 3:
                    o["at"] = [round(o["at"][0] - ox, 3), round(o["at"][1] - oy, 3), round(o["at"][2] - oz, 3)]
                for v in o.values():
                    shift(v)
            elif isinstance(o, list):
                for v in o:
                    shift(v)
        for key in ("boxes", "props", "lights", "spawns", "toys", "doors"):
            shift(doc.get(key))
    # A start far below the rest is another area of the author's (a pit, a sealed cellar the conversion has no floor for).
    ysp = sorted(sp["at"][1] for sp in doc["spawns"]["players"])
    low = [sp for sp in doc["spawns"]["players"] if sp["at"][1] < ysp[len(ysp) // 2] - 8.0]
    for sp in low:
        doc["spawns"]["players"].remove(sp)
    if low:
        print("left out %d starts more than 8 m below the rest" % len(low))
    if pockets:
        print("pruned %d props that left a pocket the bots cannot leave" % docboxes.prune_pockets(doc, build_maps.size_of, build_maps.footprint, spawn_key="players"))
    # Spots are found beside props, so taking the prop away takes the spot: for a place the
    # headless_bots trace names as cut off (a slot between a row of furniture and a wall).
    for x0, z0, x1, z1 in clears:
        gone = [q for q in doc["props"] if x0 <= q["at"][0] <= x1 and z0 <= q["at"][2] <= z1]
        for q in gone:
            doc["props"].remove(q)
        print("cleared %d props from the cubby (%.1f, %.1f) to (%.1f, %.1f)" % (len(gone), x0, z0, x1, z1))
    for dx, dz, kind in drops:
        near = [q for q in doc["props"] if not kind or q["id"] == kind]
        near.sort(key=lambda q: (q["at"][0] - dx) ** 2 + (q["at"][2] - dz) ** 2)
        if near and (near[0]["at"][0] - dx) ** 2 + (near[0]["at"][2] - dz) ** 2 <= 1.8 ** 2:
            doc["props"].remove(near[0])
            print("dropped %s at %s beside (%.1f, %.1f)" % (near[0]["id"], near[0]["at"], dx, dz))
    seen = {}
    kept = []
    for q in doc["props"]:
        if q["id"] in drop_kinds:
            continue
        if q["id"] in thin:
            seen[q["id"]] = seen.get(q["id"], 0) + 1
            if seen[q["id"]] % thin[q["id"]]:
                continue
        kept.append(q)
    if len(kept) != len(doc["props"]):
        print("dropped %d props by kind" % (len(doc["props"]) - len(kept)))
        doc["props"][:] = kept
    if not no_doors:
        docboxes.add_doors(m, doc, bsp.entities, (ox, oy, oz), slide, scale=S, skip=SKIP_DOORS)
    if widen:
        print("widened %d doorways to 1.4 m" % docboxes.widen_doors(doc["boxes"], doors=doc["doors"]))
    out_path = out_path or os.path.join(build_maps.ROOT, "maps", mid + ".json")
    with open(out_path, "w") as f:
        f.write(json.dumps(doc, indent=1) + "\n")
    print("wrote", out_path)


if __name__ == "__main__":
    main(sys.argv)
