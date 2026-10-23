The maps for **game-murder-mystery**, a social deduction game: everybody starts apart, one player is the murderer with a knife, one is the bystander with a gun, and the rest have to work out which is which. Several maps so far, dusk and both with more than one way round.

Every map is a **JSON document**, not a scene. A server reads the documents in its map directory and sends the one it is playing to every client when the map changes, so players need no map files at all. [`maps/README.md`](maps/README.md) is the format.

## The maps

| Map | What it is |
| --- | --- |
| `mm_mansion` (Blackwood Mansion) | Two storeys and a cellar: an entrance hall with a staircase, a dining room with a long table, a library, a kitchen and a servants' corridor that loops back to the hall, a back stair, bedrooms and a bathroom upstairs, and a garden with a hedge and a shed |
| `mm_motel` (Lonely Pines Motel) | Eight small rooms along a covered walkway in a U round a car park and a pool, an office, a diner with its kitchen, a laundry, a boiler room and a storage shed, and a back alley behind the rooms that joins both ends |
| `mm_silence_hollow` (Hollow Hill) | A small town of narrow rooms on three levels, a flooded cellar and several ways round; converted from a community map, see below |
| `mm_factory_winter` (Factory Winter) | A snowed-in village's meat factory: a maze of work rooms, offices and cold stores on several levels; converted from a community map, see below. The snowed village yards are in it, with 17 doors hung |
| `mm_office_murder` (Office) | A single-storey office floor: cubicle blocks, meeting rooms, a reception end and long corridors that loop; converted from a community map, see below |
| `mm_greenwood_estate` (Greenwood Estate) | A three-storey house with a cellar, set in a small forest clearing: bedrooms and a lounge, stairs between the floors, 7 doors hung, and a drive and a yard round it; converted from a community map, see below |
| `mm_mu_hotel` (Hotel) | A hotel in a run-down city block: a lobby and restrooms, corridors of rooms on several levels with stairs between them, 10 doors from the author's own plus 7 hung in doorways, and a street and yard round it; converted from a community map, see below |
| `mm_open_yard` (Open Yard) | An original, hand-built map: a big grass yard with a long hall and four rooms, a three-storey office tower, a flat-roofed office block and a pool. Made in the spirit of the sandbox starter yards shooters ship; no open remake whose terms allow porting was found, so none of any existing map's geometry is used |

## Converted maps and credits

These take the **layout** of a community map (walls, floors, stairs, doors, where people start) and nothing else: every texture, model and sound is replaced by this game's own CC0 art, and furniture is the nearest catalogue prop. Each is credited, linked, and **removed on request**: open an issue or write to the repository owner and the map goes.

| Map | Original | Author | Stated licence |
| --- | --- | --- | --- |
| `mm_silence_hollow` | [Workshop item 534296455](https://steamcommunity.com/sharedfiles/filedetails/?id=534296455), a small atmospheric map for murder-style modes | Danny Judas (textures and models by the Alchemilla team and Valve, none of which is used here) | none stated; the page does not forbid porting or sharing |
| `mm_factory_winter` | [Workshop item 3389912671](https://steamcommunity.com/sharedfiles/filedetails/?id=3389912671), a winter reworking of an abandoned mod's location for murder-style modes | FoKa (redesign); the original location is by Black Widow Games | none stated; the page does not forbid porting or sharing |
| `mm_office_murder` | [Workshop item 275775110](https://steamcommunity.com/sharedfiles/filedetails/?id=275775110), a single-storey office floor of cubicles, meeting rooms and long corridors for murder-style modes | Kammorne | none stated; the page does not forbid porting or sharing |
| `mm_greenwood_estate` | [Workshop item 286757719](https://steamcommunity.com/sharedfiles/filedetails/?id=286757719), a house from a residential estate put into a small forest, made for murder-style modes (in-game name `mu_greenwood`) | Kammorne | none stated; the page does not forbid porting or sharing |
| `mm_mu_hotel` | [GameBanana map 206520](https://gamebanana.com/maps/206520) (also Workshop item [1830568620](https://steamcommunity.com/sharedfiles/filedetails/?id=1830568620)), a hotel for murder-style modes | Neo_Wesker | Creative Commons Attribution-NonCommercial-NoDerivs 4.0 (GameBanana licence field); the page says editions and parts may be made and asks to be contacted on Steam, which is still to do |

Converted with `tools/import_bsp.py` (reads through dot-map's `tools/bsp`, cloned beside this repository or at `$DOTBSP_PATH`): `import_bsp.py mu_silence.bsp mm_silence_hollow "Hollow Hill" "Danny Judas" <url> --dusk --widen-doors --cover=18 --skip-door=9.58,0.0 --skip-door=24.54,-5.51 --ambience=amb_outdoor,amb_indoor`. The file is written once and kept; `build_maps.py` lists it in `IMPORTED` and `--check` only requires that it exists.

Office was converted with `import_bsp.py mu_office.bsp mm_office_murder "Office" Kammorne <url> --dusk --widen-doors --hang-doorways --dress=24 --ambience=amb_indoor,amb_indoor` (the Workshop archive is unpacked with the plain GMAD reader first). The source has no door entities for its meeting rooms and offices (only the lift doors), so `--hang-doorways` hangs a door in every 1.4 m doorway under a header (28 doors) and removes the author's own leaf standing in it, then settles the spawns again; `--dress=24` adds seeded plants, a bookcase, a sofa, bins and coat racks on open floor; the carpet and the painted walls take their colours by texture name in `TEXTURE_MAP`.

Greenwood Estate was converted with `import_bsp.py mu_greenwood.bsp mm_greenwood_estate "Greenwood Estate" Kammorne <url> --dusk --widen-doors --hang-doorways --dress=60 --dress-walls=80 --spread-spawns=24 --ambience=amb_outdoor,amb_indoor` (the Workshop archive unpacked with the plain GMAD reader). The author's own door entities give 7 doors; `--dress=60` adds seeded furniture on open floor; `--dress-walls=80` sets beds, shelves, cabinets, sofas, lamps and washers with their backs to the walls of every roofed room, chosen by floor texture and storey (tile is a kitchen or utility room, concrete a store, wood a lounge below and a bedroom above), keeping 0.7 m clear in front, stairs' feet and a 1.9 m square round every door free; `--spread-spawns=24` drops the author's starts that stand within 3.5 m of another (they come in pairs 1.2 m apart) and tops up with the clearest open floor, farthest first, a share to each floor (cellar, ground, upper, yard).

Hotel was converted with `import_bsp.py mu_hotel.bsp mm_mu_hotel "Hotel" Neo_Wesker https://gamebanana.com/maps/206520 --dusk --widen-doors --hang-doorways --dress=60 --dress-walls=80 --spread-spawns=24 --ambience=amb_wind,amb_indoor` (the GameBanana archive unpacked with `unrar`): the same options as Greenwood Estate, 24 spawns over its floors, and every texture, model and sound replaced by this game's own CC0 art.

Factory Winter was converted the same way, with the snowed ground and the doors that the map hangs: `import_bsp.py <bsp> mm_factory_winter "Factory Winter" FoKa <url> --dusk --max-lights=128 --skip-start=22 --terrain=snow --drop-beside=15.18,0.15,furniture_television_vintage --drop-beside=-3.34,0.31,furniture_books --drop-beside=-34.25,6.42,furniture_lounge_sofa` plus `--one-way=x,z` for the six doors that swing one way (-35.721,7.048; 5.179,-8.153; -38.148,3.315; -27.411,7.048; -31.366,3.315; -46.72,15.735) and `--skip-door=x,z` for the five that stay open (-3.658,3.796; -29.718,17.288; 14.44,2.315; -43.091,14.602; -46.835,21.793), and `--ambience=amb_wind,amb_industrial`. The importer cuts every brush with dot-map's `boxes.decompose`, so wedges are wedges.

The five converted maps take their air from the author's file (`import_bsp.py`'s `environment()`): the sun's colour, brightness and angle from `light_environment`, the shade's colour and strength from its ambient, the fog's colour, start, end and density cap from `env_fog_controller` (in metres), the sky from the sky's name (a mood painted in code, never the author's sky textures: `office` is an overcast afternoon, `sky_day02_09` an overcast winter one, `jungle` a clear day, `militia_hdr` a clear dusk), snow or rain volumes from `func_precipitation` (Factory Winter only, two volumes over the yard, so nothing falls indoors), and a lamp for each `point_spotlight` and `env_fire`. Their sound is dot-audio's CC0 stock chosen by what the author's soundscapes name (`--ambience=<outdoor>,<indoor>`): wind outdoors for the hotel and the factory, a breeze for Hollow Hill and Greenwood, room tone indoors, machinery under the factory's roofs; no sound from any of the author's files is carried. A finished map can take a rerun of just this with `--env-only=maps/<id>.json` (Hollow Hill, whose geometry is hand-edited): `import_bsp.py mu_silence.bsp --env-only=maps/mm_silence_hollow.json --ambience=amb_outdoor,amb_indoor --fog=14,40,0.55` (the author's fog, 11 to 18 m, buried the town from the overview; this one keeps the haze and loses the wall). Hollow Hill's flooded cellar is a see-through `water` box set into its basement by hand (the author's file has no water), drawn with a CC0 sea-foam photograph tinted blue-green. A hotel skin that is drawn in a floor material under a roof is retextured as ceiling by `retexture_ceilings`.

## How they are made

`tools/build_maps.py` writes every document in `maps/`. A wall with its doors and windows and a room with its floor, ceiling and lights are one call each.

```bash
python3 tools/build_maps.py                # rewrite maps/*.json
python3 tools/build_maps.py --check        # exit 1 if a file differs from what the builder writes
python3 tools/build_maps.py --sync-sizes   # copy prop sizes from ../game-murder-mystery
```

The props are Kenney's CC0 Furniture and Nature kits, which the game provides.

Ground that is a displacement in the source map is a `terrain` heightfield (dot-map's `dotbsp.terrain`, read by `DotMapTerrain`), not stepped boxes: `import_bsp.py` writes it, and `--graft-terrain=<map.json>` swaps it into a committed map while keeping every other box, prop and hand edit. `mm_factory_winter` is the one map that has it.

## License
MIT. See [LICENSE](LICENSE).
