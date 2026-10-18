The maps for **game-murder-mystery**, a social deduction game: everybody starts apart, one player is the murderer with a knife, one is the bystander with a gun, and the rest have to work out which is which. Two maps so far, both dusk and both with more than one way round.

Every map is a **JSON document**, not a scene. A server reads the documents in its map directory and sends the one it is playing to every client when the map changes, so players need no map files at all. [`maps/README.md`](maps/README.md) is the format.

## The maps

| Map | What it is |
| --- | --- |
| `mm_mansion` (Blackwood Mansion) | Two storeys and a cellar: an entrance hall with a staircase, a dining room with a long table, a library, a kitchen and a servants' corridor that loops back to the hall, a back stair, bedrooms and a bathroom upstairs, and a garden with a hedge and a shed |
| `mm_motel` (Lonely Pines Motel) | Eight small rooms along a covered walkway in a U round a car park and a pool, an office, a diner with its kitchen, a laundry, a boiler room and a storage shed, and a back alley behind the rooms that joins both ends |

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
