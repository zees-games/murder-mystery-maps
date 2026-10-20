The maps for **game-murder-mystery**, a social deduction game: everybody starts apart, one player is the murderer with a knife, one is the bystander with a gun, and the rest have to work out which is which. Two maps so far, both dusk and both with more than one way round.

Every map is a **JSON document**, not a scene. A server reads the documents in its map directory and sends the one it is playing to every client when the map changes, so players need no map files at all. [`maps/README.md`](maps/README.md) is the format.

## The maps

| Map | What it is |
| --- | --- |
| `mm_mansion` (Blackwood Mansion) | Two storeys and a cellar: an entrance hall with a staircase, a dining room with a long table, a library, a kitchen and a servants' corridor that loops back to the hall, a back stair, bedrooms and a bathroom upstairs, and a garden with a hedge and a shed |
| `mm_motel` (Lonely Pines Motel) | Eight small rooms along a covered walkway in a U round a car park and a pool, an office, a diner with its kitchen, a laundry, a boiler room and a storage shed, and a back alley behind the rooms that joins both ends |
| `mm_silence_hollow` (Hollow Hill) | A small town of narrow rooms on three levels, a flooded cellar and several ways round; converted from a community map, see below |

## Converted maps and credits

These take the **layout** of a community map (walls, floors, stairs, doors, where people start) and nothing else: every texture, model and sound is replaced by this game's own CC0 art, and furniture is the nearest catalogue prop. Each is credited, linked, and **removed on request**: open an issue or write to the repository owner and the map goes.

| Map | Original | Author | Stated licence |
| --- | --- | --- | --- |
| `mm_silence_hollow` | [Workshop item 534296455](https://steamcommunity.com/sharedfiles/filedetails/?id=534296455), a small atmospheric map for murder-style modes | Danny Judas (textures and models by the Alchemilla team and Valve, none of which is used here) | none stated; the page does not forbid porting or sharing |

Converted with `tools/import_bsp.py` (reads through dot-map's `tools/bsp`, cloned beside this repository or at `$DOTBSP_PATH`): `import_bsp.py mu_silence.bsp mm_silence_hollow "Hollow Hill" "Danny Judas" <url> --dusk --widen-doors --cover=18 --skip-door=9.58,0.0 --skip-door=24.54,-5.51`. The file is written once and kept; `build_maps.py` lists it in `IMPORTED` and `--check` only requires that it exists.

## How they are made

`tools/build_maps.py` writes every document in `maps/`. A wall with its doors and windows and a room with its floor, ceiling and lights are one call each.

```bash
python3 tools/build_maps.py                # rewrite maps/*.json
python3 tools/build_maps.py --check        # exit 1 if a file differs from what the builder writes
python3 tools/build_maps.py --sync-sizes   # copy prop sizes from ../game-murder-mystery
```

The props are Kenney's CC0 Furniture and Nature kits, which the game provides.

## License
MIT. See [LICENSE](LICENSE).
