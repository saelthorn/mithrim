from dataclasses import dataclass, field
import random

from entities.base_entity import NPC
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
    # Maps a tile_map char to an NPC factory `(x, y) -> NPC`, letting a
    # blueprint declare its own population directly in the ASCII art
    # (e.g. 'A' for an innkeeper) instead of NPCs being placed afterwards.
    npc_map: dict[str, object] = field(default_factory=dict)


def build_blueprint(key, name, tile_map, char_map, default_tile=ground, walkable_chars=None, description="", npc_map=None):
    return StructureBlueprint(
        key=key,
        name=name,
        tile_map=tuple(tile_map),
        char_map=dict(char_map),
        default_tile=default_tile,
        walkable_chars=frozenset(walkable_chars or ()),
        description=description,
        npc_map=dict(npc_map or {}),
    )


class TownNPC(NPC):
    def __init__(self, x, y, char, name, color, dialogue=None):
        super().__init__(x, y, char, name, color, dialogue)


class Townsfolk(TownNPC):
    def __init__(self, x, y, name=None):
        dialogue = [
            "Roads have been busier since the old entrances opened again.",
            "Mind the wilds after dusk. The grass gets quiet before trouble.",
            "If you are heading below, make sure you have food and light.",
            "Every town around here has a story about someone who went missing.",
        ]
        super().__init__(x, y, 'p', name or random.choice(TOWNSFOLK_NAMES), (205, 205, 185), dialogue)


class Innkeeper(TownNPC):
    def __init__(self, x, y):
        dialogue = [
            "Welcome in, traveler. Warm floorboards beat cold roads.",
            "Most adventurers ask about dungeons. The wise ones ask about supper.",
            "You can learn plenty by listening before you descend.",
        ]
        super().__init__(x, y, 'A', 'Innkeeper', (255, 215, 120), dialogue)


class Shopkeeper(TownNPC):
    def __init__(self, x, y):
        dialogue = [
            "I am still unpacking the shelves, but I know a good buyer when I see one.",
            "Bring back anything odd from the ruins. Odd things sell.",
            "A careful blade and a dry torch are worth more than bravado.",
        ]
        super().__init__(x, y, 'rc', 'Shopkeeper', (230, 200, 120), dialogue)


TOWNSFOLK_NAMES = [
    "Mara", "Edrin", "Tess", "Borin", "Lysa", "Corren", "Nessa", "Tobin"
]


# NPC factories used by blueprint npc_map entries below. Each takes (x, y)
# and returns an NPC instance, matching the signature place_structure calls.
def _spawn_innkeeper(x, y):
    return Innkeeper(x, y)


def _spawn_shopkeeper(x, y):
    return Shopkeeper(x, y)


def _spawn_villager(x, y):
    return Townsfolk(x, y)


STRUCTURE_BLUEPRINTS = {
    "witch_hut": build_blueprint(
        "witch_hut",
        "Witch Hut",
        [
            "##.##",
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
            "##.##",
            "#...#",
            "#.p..",
            "#...#",
            "#####",
        ],
        {"#": wall, ".": tavern_floor, "p": tavern_floor},
        walkable_chars={".", "p"},
        description="A simple frontier cabin.",
        npc_map={"p": _spawn_villager},
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
            " #.# ",
            " . . ",
        ],
        {"#": wall, ".": floor},
        walkable_chars={"."},
        description="A simple stone shrine.",
    ),
    "shop": build_blueprint(
        "shop",
        "Shop",
        [
            "#####",
            "#...#",
            "#.S..",
            "#...#",
            "##.##",
        ],
        {"#": wall, ".": tavern_floor, "S": tavern_floor},
        walkable_chars={".", "S"},
        description="A traveling merchant's storefront.",
        npc_map={"S": _spawn_shopkeeper},
    ),
    "tavern": build_blueprint(
        "tavern",
        "Tavern",
        [
            " #######",
            " ......#",
            "##.....#",
            "#p....A#",
            "#.p....#",
            "####.###",
        ],
        {"#": wall, ".": tavern_floor, "p": tavern_floor, "A": tavern_floor},
        walkable_chars={".", "p", "A"},
        description="A rowdy wayside tavern.",
        npc_map={"A": _spawn_innkeeper, "p": _spawn_villager},
    ),
    "house": build_blueprint(
        "house",
        "House",
        [
            "###.#",
            "#...#",
            "#.V.#",
            "#...#",
            "##.##",
        ],
        {"#": wall, ".": tavern_floor, "V": tavern_floor},
        walkable_chars={".", "V"},
        description="A modest family home.",
        npc_map={"V": _spawn_villager},
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

    search_radius = max(3, min(game_map.width, game_map.height) // 2)

    # Expand outward from the anchor ring by ring (radius 0 = the anchor's
    # own origin) and return the first valid spot found. The old version
    # scanned offset_x/offset_y from -search_radius upward in a fixed
    # top-left-to-bottom-right order and returned the first success —
    # since search_radius spans up to half the map and the block-list
    # check now passes on almost any tile, that first candidate sat near
    # -search_radius, i.e. close to the map's corner rather than the
    # anchor, so towns kept drifting toward the top-left. Checking rings
    # in increasing radius order guarantees the closest valid position to
    # the anchor is the one that gets used.
    for radius in range(search_radius + 1):
        for offset_x in range(-radius, radius + 1):
            for offset_y in range(-radius, radius + 1):
                if max(abs(offset_x), abs(offset_y)) != radius:
                    continue  # already checked at a smaller radius

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


def _walkable_structure_positions(game_map, placed_tiles, occupied):
    positions = []
    for x, y, _ in placed_tiles:
        if (x, y) in occupied:
            continue
        if hasattr(game_map, "is_walkable"):
            walkable = game_map.is_walkable(x, y)
        else:
            walkable = not getattr(game_map.tiles[y][x], "blocked", True)
        if walkable:
            positions.append((x, y))
    return positions


def npcs_for_placement(structure_id, placed_tiles):
    """
    Instantiate the NPCs a structure's blueprint declares in its npc_map,
    given the placed_tiles returned by place_structure()/
    place_structure_at_anchor(). Public so any caller that places a
    structure directly — not just create_town_npcs()'s per-chunk town
    roll — can spawn its population too (e.g. the player's starting
    tavern, placed on its own in game.py).
    """
    blueprint = get_structure_blueprint(structure_id)
    return _npc_spawns_from_blueprint(blueprint, placed_tiles) if blueprint else []


def _npc_spawns_from_blueprint(blueprint, placed_tiles):
    """
    Instantiate the NPCs a blueprint declares in its npc_map, at the exact
    positions marked in its ASCII art (e.g. the 'A' in the tavern layout).

    place_structure() only returns the flat list of placed (x, y, tile)
    tuples, so to recover *which* placed tile corresponds to which char we
    re-walk blueprint.tile_map from the structure's origin (its top-left
    corner, i.e. the minimum x/y among placed_tiles) rather than changing
    place_structure's return shape, which other callers rely on.
    """
    if not blueprint.npc_map or not placed_tiles:
        return []

    origin_x = min(x for x, _, _ in placed_tiles)
    origin_y = min(y for _, y, _ in placed_tiles)
    placed_positions = {(x, y) for x, y, _ in placed_tiles}

    spawns = []
    for dy, row in enumerate(blueprint.tile_map):
        for dx, char in enumerate(row):
            spawn_npc = blueprint.npc_map.get(char)
            if spawn_npc is None:
                continue
            gx, gy = origin_x + dx, origin_y + dy
            if (gx, gy) in placed_positions:
                spawns.append(spawn_npc(gx, gy))
    return spawns


def create_town_npcs(game_map, town_buildings):
    """Create a small static population for overworld town buildings.

    If a building's blueprint declares an npc_map, its NPCs are spawned at
    the exact spots marked in the ASCII art. Otherwise this falls back to
    the older per-structure_id placement below, so blueprints that haven't
    been given an npc_map yet still get populated.
    """
    npcs = []
    occupied = set()

    for structure_id, placed_tiles in town_buildings:
        blueprint = get_structure_blueprint(structure_id)
        if blueprint and blueprint.npc_map:
            spawned = npcs_for_placement(structure_id, placed_tiles)
            npcs.extend(spawned)
            occupied.update((npc.x, npc.y) for npc in spawned)
            continue

        positions = _walkable_structure_positions(game_map, placed_tiles, occupied)
        if not positions:
            continue

        if structure_id == "tavern":
            x, y = positions[len(positions) // 2]
            npc = Innkeeper(x, y)
            npcs.append(npc)
            occupied.add((x, y))

            remaining = [pos for pos in positions if pos not in occupied]
            for x, y in random.sample(remaining, min(2, len(remaining))):
                npc = Townsfolk(x, y)
                npcs.append(npc)
                occupied.add((x, y))

        elif structure_id == "shop":
            x, y = positions[len(positions) // 2]
            npc = Shopkeeper(x, y)
            npcs.append(npc)
            occupied.add((x, y))

        elif structure_id == "house":
            x, y = random.choice(positions)
            npc = Townsfolk(x, y)
            npcs.append(npc)
            occupied.add((x, y))

    return npcs