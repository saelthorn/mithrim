from dataclasses import dataclass, field

from world.tile import ground, grass, road, tall_grass, wall, tavern_floor, floor


@dataclass(frozen=True)
class StructureBlueprint:
    key: str
    name: str
    tile_map: tuple[str, ...]
    char_map: dict[str, object]
    default_tile: object = ground
    walkable_chars: frozenset[str] = field(default_factory=frozenset)
    description: str = ""


def build_blueprint(key, name, tile_map, char_map, default_tile=ground, walkable_chars=None, description=""):
    return StructureBlueprint(
        key=key,
        name=name,
        tile_map=tuple(tile_map),
        char_map=dict(char_map),
        default_tile=default_tile,
        walkable_chars=frozenset(walkable_chars or ()),
        description=description,
    )


STRUCTURE_BLUEPRINTS = {
    "witch_hut": build_blueprint(
        "witch_hut",
        "Witch Hut",
        [
            "#####",
            "#...#",
            "#...#",
            "#...#",
            "##.##",
        ],
        {"#": wall, ".": tavern_floor},
        walkable_chars={"."},
        description="A crooked hut for swamp witches.",
    ),
    "windmill": build_blueprint(
        "windmill",
        "Windmill",
        [
            "  #  ",
            "  #  ",
            "#####",
            "#...#",
            "##.##",
        ],
        {"#": wall, ".": tavern_floor},
        walkable_chars={"."},
        description="A windmill for grinding grain.",
    ),
    "small_cabin": build_blueprint(
        "small_cabin",
        "Cabin",
        [
            "#####",
            "#...#",
            "#...#",
            "#...#",
            "##.##",
        ],
        {"#": wall, ".": tavern_floor},
        walkable_chars={"."},
        description="A simple frontier cabin.",
    ),
    "watch_tower": build_blueprint(
        "watch_tower",
        "Watchtower",
        [
            "  #  ",
            "  #  ",
            "#####",
            "#...#",
            "##.##",
        ],
        {"#": wall, ".": tavern_floor},
        walkable_chars={"."},
        description="A defensive tower on a hilltop.",
    ),
    "shrine": build_blueprint(
        "shrine",
        "Shrine",
        [
            "  #  ",
            " #.# ",
            "  #  ",
            " . . ",
        ],
        {"#": wall, ".": floor},
        walkable_chars={"."},
        description="A simple stone shrine.",
    ),
}


def register_structure_blueprint(blueprint):
    STRUCTURE_BLUEPRINTS[blueprint.key] = blueprint
    return blueprint


def get_structure_blueprint(structure_id):
    return STRUCTURE_BLUEPRINTS.get(structure_id)


def place_structure(game_map, structure_id, origin_x, origin_y, tile_overrides=None):
    blueprint = get_structure_blueprint(structure_id)
    if blueprint is None:
        return None

    width = len(blueprint.tile_map[0])
    height = len(blueprint.tile_map)

    if origin_x < 0 or origin_y < 0:
        return None

    if origin_x + width > game_map.width or origin_y + height > game_map.height:
        return None

    placed = []
    for dy, row in enumerate(blueprint.tile_map):
        for dx, char in enumerate(row):
            gx = origin_x + dx
            gy = origin_y + dy
            tile = tile_overrides.get((gx, gy)) if tile_overrides else None
            if tile is None:
                tile = blueprint.char_map.get(char, blueprint.default_tile)
            if tile is None:
                continue
            game_map.tiles[gy][gx] = tile
            placed.append((gx, gy, tile))

    return placed


def _is_structure_base_tile(tile):
    """
    Whether it's safe to overwrite `tile` with part of a structure footprint.

    This used to be an allow-list of a few "plain ground" tiles
    (ground/grass/tall_grass/road). That was too narrow: overworld landmark
    anchors (e.g. Watchtower/Shrine in the mountains, Witch Hut in the
    swamp) are frequently handed tree, mountain, or lake tiles, none of
    which were in the allow-list. In terrain dominated by those tiles,
    place_structure_at_anchor's search window could never find a fully
    "clean" footprint, so it silently gave up and the structure was never
    placed on the map at all.

    Instead we block-list the handful of tiles that genuinely shouldn't be
    built over (water, dungeon entrances, other structures' walls) and
    allow everything else, since the structure's own tiles fully overwrite
    whatever terrain was there anyway.
    """
    from world.tile import dungeon_entrance
    from world.water_features import is_water_tile

    if tile is None:
        return False
    if tile is dungeon_entrance or tile is wall:
        return False
    if is_water_tile(tile):
        return False
    return True


def place_structure_at_anchor(game_map, structure_id, anchor_x, anchor_y, tile_overrides=None):
    blueprint = get_structure_blueprint(structure_id)
    if blueprint is None:
        return None

    width = len(blueprint.tile_map[0])
    height = len(blueprint.tile_map)

    if width >= game_map.width or height >= game_map.height:
        return None

    origin_x = max(0, min(anchor_x - max(1, width // 2), game_map.width - width))
    origin_y = max(0, min(anchor_y - max(1, height // 2), game_map.height - height))

    for offset_x in range(-3, 4):
        for offset_y in range(-3, 4):
            candidate_x = origin_x + offset_x
            candidate_y = origin_y + offset_y
            if candidate_x < 0 or candidate_y < 0:
                continue
            if candidate_x + width > game_map.width or candidate_y + height > game_map.height:
                continue

            if not all(_is_structure_base_tile(game_map.tiles[candidate_y + dy][candidate_x + dx]) for dy in range(height) for dx in range(width)):
                continue

            if tile_overrides:
                candidate_tile_overrides = {
                    (gx, gy): tile for (gx, gy), tile in tile_overrides.items()
                    if candidate_x <= gx < candidate_x + width and candidate_y <= gy < candidate_y + height
                }
            else:
                candidate_tile_overrides = None

            placed = place_structure(game_map, structure_id, candidate_x, candidate_y, candidate_tile_overrides)
            if placed:
                return placed

    return None