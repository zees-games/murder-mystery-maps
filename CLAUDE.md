# murder-mystery-maps

Maps for game-murder-mystery as JSON documents (`"kind": "murder_map"`), the sibling of hide-n-seek-maps. Nothing here runs in a game; the game reads `maps/*.json`. The format is defined and validated by game-murder-mystery's `game/mm_map_doc.gd`, so a format change starts there and is copied into `maps/README.md`.

## Layout

- `maps/*.json`: the documents, generated. Never hand-edit a built one; `--check` (and CI) fails when a file is not what the builder writes.
- `maps/README.md`: the mapper's copy of the format.
- `tools/build_maps.py`: the library half (the `Map` class, walls and doors, rooms, stairs, slabs, toy and spawn settling, furnishing helpers), copied from hide-n-seek-maps' builder, then this repository's own half: `DUSK`, `D`, `W`, `lit`, `mansion()`, `motel()`, `TOY_PLANS`, `MAPS`.
- `tools/prop_sizes.json`: prop sizes and resting tops, copied from the game's catalogue by `--sync-sizes`. Props must use ids in it.
- `project.godot`, `.github/workflows`: the pack that dot-bootstrap links into the game and the release that publishes it.

## Commands

```bash
python3 tools/build_maps.py                  # rewrite maps/*.json
python3 tools/build_maps.py --check          # must pass before a commit
python3 tools/build_maps.py --spots mm_motel # plan of the open floor, to choose toy and spawn places
python3 tools/build_maps.py --sync-sizes     # when the game has measured new models
```

Python only; no `heavy` needed. The game's own map check (in game-murder-mystery) is the real test of a map: run it after changing one.

## Rules

- Spawns are one group, `"spawns": {"players": [...]}`, at least 16, spread over different rooms, yards and storeys. The builder moves a spawn that landed on a prop and says so.
- A map needs more than one way round (a chase into a dead end ends the round), doors on most rooms, a couple of isolated spots (cellar, shed, back stair) and a couple of crowded ones (hall, diner).
- Dusk but readable: keep `DUSK`'s ambient_energy near 0.46 and fog under 0.002. Browsers draw at most 8 lights per surface, so a big room wants a few strong lights.
- Furniture must clear door swings (a door is 1.1 to 1.6 m wide and swings its whole width); the game's check fails a door that hits a prop.
- Props face +Z at yaw 0; `against(side, wall_at, along)` takes the wall's inner face. `W()` paints the inner face of an outer wall whose room is on the minus side with a separate thin skin, because `Map.wall`'s `inner` layer only paints the +z/+x side.
- Ground is `GROUND = -0.02` under floors at y 0; a hole in it (a cellar stairwell) is `floor_around`.
- Motel rooms are written once in `Frame` (u along the back wall, v towards the door) and used for every direction a wing faces.
- Nothing public may name another commercial game or engine. Markdown is never hard-wrapped.
- Toys are optional and settled to the nearest clear spot; a toy with no clear spot stops the build, so move its hint.

## Read before

| Before | Read |
| --- | --- |
| Changing the document format | game-murder-mystery's `game/mm_map_doc.gd`, then `maps/README.md` |
| Writing a new building | the library docstrings at the top of `tools/build_maps.py`; `mansion()` for a two-storey house, `motel()` for a single-storey layout |
| Adding a toy | hide-n-seek-maps' `maps/README.md` toy list is the same catalogue (`TOYS` in the builder) |
