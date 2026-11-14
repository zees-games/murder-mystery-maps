The maps for game-murder-mystery, a social deduction game: everybody starts apart, one player is the murderer with a knife, one is the bystander with a gun, and the rest work out which is which. Three maps of our own and 14 converted from community maps.

A map is a JSON document, not a scene. The server reads every `.json` file in its map directory and sends the current map to each client, so players need no map files. To add a map, drop one file in the directory. The format is in [maps/README.md](maps/README.md).

## Our maps

| Map | What is in it |
| --- | --- |
| `mm_mansion` (Blackwood Mansion) | Two storeys and a cellar: entrance hall, dining room, library, kitchen, a servants' corridor that loops back, bedrooms, a garden with a hedge and shed |
| `mm_motel` (Lonely Pines Motel) | Rooms along a covered walkway in a U round a car park and pool, an upper storey with a balcony, an office, diner, laundry and boiler room, a back alley |
| `mm_open_yard` (Open Yard) | A big grass yard with a long hall and four rooms, a three-storey office tower, an office block and a pool |

## Converted community maps

Each keeps the author's layout (walls, floors, stairs, doors, starts). Every texture, model and sound is replaced with this game's CC0 art and furniture is the nearest catalogue prop. The full licence entries are in [licence.json](licence.json).

| Map | Author | Source | Licence |
| --- | --- | --- | --- |
| `mm_factory_winter` (Factory Winter) | FoKa (redesign); the original location is by Black Widow Games | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3389912671) | none stated |
| `mm_greenwood_estate` (Greenwood Estate) | Kammorne | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=286757719) | none stated |
| `mm_mu_hotel` (Hotel) | Neo_Wesker | [GameBanana](https://gamebanana.com/maps/206520) | CC BY-NC-ND 4.0 |
| `mm_murder_mansion` (Murder Mansion) | Grimm | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=481179223) | none stated |
| `mm_office_murder` (Office) | Kammorne | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=275775110) | none stated |
| `mm_silence_hollow` (Hollow Hill) | Danny Judas (textures and models by the Alchemilla team and Valve, none of which is used here) | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=534296455) | none stated |
| `mm_villa` (Villa) | korka007 | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=2633639653) | none stated |
| `mm_functionalist_night` (Functionalist Night) | VITAPLEX | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3382694345) | none stated |
| `mm_mountainresort` (Mountain Resort) | prvec | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=2312309380) | none stated |
| `mm_airbus` (Airbus) | Officer_B (uploaded by Zaratusa) | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=253297309) | none stated |
| `mm_deco_mansion` (Deco Mansion) | Gastly_Furby_777 | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3698815153) | none stated |
| `mm_rooftops_2016` (Rooftops 2016) | youmenow1 | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=534491717) | none stated |
| `mm_sunken_resort` (Sunken Resort) | Praisemantas | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3376822715) | none stated |
| `mm_warehouse` (Warehouse) | Max Power | [Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=177889282) | none stated |

"None stated" means the source page gives no licence. `mm_mountainresort`'s page says "Do not reupload any content" and bars paid-work use without the author's consent; it is converted by the owner's decision and removed on request. `mm_mu_hotel`'s author asks to be contacted on Steam about editions; that contact is still to do.

If you made one of these maps and want it removed, open an issue at <https://github.com/zees-games/murder-mystery-maps/issues> and it goes.

## Building the maps

`tools/build_maps.py` writes the own maps. A wall with its doors and windows and a room with its floor, ceiling and lights are one call each. Props are Kenney's CC0 Furniture and Nature kits, which the game provides.

```bash
python3 tools/build_maps.py                # rewrite maps/*.json
python3 tools/build_maps.py --check        # exit 1 if a file differs from the builder's output
python3 tools/build_maps.py --sync-sizes   # copy prop sizes from ../game-murder-mystery
```

Converted maps come from `tools/import_bsp.py`, which reads through dot-map-convert (cloned beside this repository, or set `DOTBSP_PATH`). Each converted file is written once and kept; `--check` only requires that it exists. The importer takes lighting, fog, sky and ambient sound from the author's file, but never the author's art or audio. The exact command for each map is in [docs/import-notes.md](docs/import-notes.md).

Ground that is a displacement in the source map becomes a `terrain` heightfield. `--graft-terrain=<map.json>` swaps one into a committed map and keeps every other box, prop and hand edit.

Some maps were renamed (`mm_villa`, `mm_functionalist_night`, `mm_sunken_resort`) because the hide-n-seek pack uses the same base ids and the catalogue refuses a second map with an id.

## Licence

MIT, see [LICENSE](LICENSE). The converted maps keep the licences listed above.
