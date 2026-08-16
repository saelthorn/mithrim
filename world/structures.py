from dataclasses import dataclass, field
import random

from entities.base_entity import NPC
from entities.town_npcs import TownNPC, Innkeeper, Shopkeeper, Townsfolk, Blacksmith, Priest
from entities.monster import GiantRat, Goblin, Skeleton, Wolf, Orc
from entities.companions import RACE_CLASS_VISUALS, FIGHTER, RANGER, ROGUE, WIZARD, CLERIC

from world.tile import (
    ground, grass, road, tall_grass, wall, tavern_floor, floor, bar_counter_two, bar_counter_three, bar_counter_four, 
    table, crate, tavern_barrel_two, altar, door, forge, anvil, shelf, bed, hay, bar_counter, bar_counter_five, bar_counter_six,
    shelf_three, bar_counter, shelf_two, tavern_barrel, tavern_crate, cob_web, wood_plank, tavern_floor, ladder, tavern_cobweb
)


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
    # Maps a tile_map char to a Monster factory `(x, y) -> Monster`, the
    # monster equivalent of npc_map above. Lets a blueprint declare a
    # squatter or guardian baked directly into its ASCII art (e.g. 'r'
    # for a giant rat nesting in an abandoned cabin) instead of monsters
    # being spawned separately by whatever encounter/room system placed
    # the building.
    monster_map: dict[str, object] = field(default_factory=dict)


def build_blueprint(key, name, tile_map, char_map, default_tile=ground, walkable_chars=None, description="", npc_map=None, monster_map=None):
    return StructureBlueprint(
        key=key,
        name=name,
        tile_map=tuple(tile_map),
        char_map=dict(char_map),
        default_tile=default_tile,
        walkable_chars=frozenset(walkable_chars or ()),
        description=description,
        npc_map=dict(npc_map or {}),
        monster_map=dict(monster_map or {}),
    )


# NPC factories used by blueprint npc_map entries below. Each takes (x, y)
# and returns an NPC instance, matching the signature place_structure calls.
def _spawn_innkeeper(x, y):
    return Innkeeper(x, y)


def _spawn_shopkeeper(x, y):
    return Shopkeeper(x, y)


def _spawn_villager(x, y):
    return Townsfolk(x, y)

def _spawn_blacksmith(x, y):
    return Blacksmith(x, y)

def _spawn_priest(x, y):
    return Priest(x, y)


#: Odds that a tavern patron spawns as a race+class adventurer worth
#: recruiting rather than a plain villager. Kept low so a tavern still
#: mostly reads as an ordinary room full of ordinary tavern-goers, with
#: a recruitable adventurer only turning up in it every so often.
TAVERN_PATRON_ADVENTURER_CHANCE = 0.5

#: Level a rolled adventurer patron is treated as, both for their own
#: pre-recruit HP (below) and for the CombatCompanion they become on
#: recruiting (see game.py's recruit_combat_companion(), which now reads
#: this same `.level` back off the patron instead of defaulting to 6) --
#: a "journeyman, not a hero" only holds if the patron's toughness in
#: the tavern and once hired are actually the same level, not two
#: unrelated numbers that happen to both sound low.
TAVERN_PATRON_LEVEL = 6

#: class name -> CompanionClass, the same pairing game.py's own
#: COMPANION_CLASSES dict uses -- kept as a local copy here rather than
#: importing that dict, since it lives on the Game class and would pull
#: in all of game.py just to look up a hit_die. Used by
#: _spawn_tavern_patron() to give a rolled adventurer real HP instead of
#: whatever NPC's own bare-villager default is.
_ADVENTURER_CLASSES_BY_NAME = {
    companion_class.name: companion_class
    for companion_class in (FIGHTER, RANGER, ROGUE, WIZARD, CLERIC)
}


def _spawn_tavern_patron(x, y):
    """
    A tavern patron. Most of the time this is just a plain villager --
    same as any other Townsfolk in town -- so a tavern doesn't read as
    wall-to-wall hired swords. TAVERN_PATRON_ADVENTURER_CHANCE of the
    time it's instead visually a race+class adventurer, drawn from
    entities/companions.py's RACE_CLASS_VISUALS (the same table
    game.py's character creation uses for the player's own sprite),
    marking them as someone actually worth recruiting.

    Either way this is still a Townsfolk underneath (dialogue,
    wandering/socializing schedule, everything else about them is
    unchanged) -- only the sprite, and whether `visual_race`/
    `visual_class` get stashed on it, differ.

    `visual_race`/`visual_class` are stashed on the NPC so a future
    recruiting interaction (see game.py's recruit_combat_companion(),
    which already accepts a race + CompanionClass pair) can read back
    which race/class this patron's sprite represents, rather than the
    choice only existing as a char/color pair that gets thrown away.

    They also get modest combat stats (`attack_power`, `proficiency_
    bonus`, `armor_class`, `hp`/`max_hp`) that a plain villager never
    needs -- looking like an adventurer is also what TownNPC.
    _is_adventurer() checks to decide that this patron fights back (see
    town_npcs.py's "-- alert / fear --" section) instead of fleeing when
    a monster wanders into town, and TownNPC.attack() needs those fields
    to actually swing.
    """
    patron = Townsfolk(x, y)

    if random.random() >= TAVERN_PATRON_ADVENTURER_CHANCE:
        return patron

    race, class_name = random.choice(list(RACE_CLASS_VISUALS.keys()))
    char, color = RACE_CLASS_VISUALS[(race, class_name)]

    patron.char = char
    patron.color = color
    patron.visual_race = race
    patron.visual_class = class_name

    # A journeyman-level fighter, not a hero -- enough to hold their own
    # against a single stray monster, not to solo a warband. Deliberately
    # not scaled to the player's own level: a tavern patron's toughness
    # shouldn't quietly track the player's progression.
    patron.attack_power = 1
    patron.proficiency_bonus = 1
    patron.armor_class = 13
    patron.level = TAVERN_PATRON_LEVEL

    # HP drawn from the same class data a recruited companion uses (see
    # CombatCompanion._recalculate_stats() in entities/companions.py),
    # computed at TAVERN_PATRON_LEVEL with that exact formula (hit_die +
    # constitution modifier, plus one average-roll-and-modifier step per
    # level past 1) rather than NPC's own bare-villager hp default --
    # so an adventurer patron can actually take a hit or two before
    # _is_adventurer() sends them into melee, and so their HP matches
    # what they'll have the instant they're recruited at this same
    # level. Falls back to the plain villager default if this class/race
    # pairing has no matching CompanionClass yet (see RACE_CLASS_VISUALS'
    # docstring on Ranger's own entry).
    companion_class = _ADVENTURER_CLASSES_BY_NAME.get(class_name)
    if companion_class is not None:
        con_modifier = (companion_class.ability_scores["constitution"] - 10) // 2
        average_roll = (companion_class.hit_die // 2) + 1
        max_hp = companion_class.hit_die + con_modifier
        if TAVERN_PATRON_LEVEL > 1:
            max_hp += (TAVERN_PATRON_LEVEL - 1) * (average_roll + con_modifier)
        patron.max_hp = max(1, max_hp)
        patron.hp = patron.max_hp

    return patron


# Monster factories used by blueprint monster_map entries below -- the
# monster equivalent of the NPC factories above. Each takes (x, y) and
# returns a Monster instance, matching the same `(x, y) -> entity`
# signature npc_map factories use, so npcs_for_placement() and
# monsters_for_placement() can share the exact same char-in-ASCII-art
# spawning logic (see _spawns_from_entity_map()).
def _spawn_giant_rat(x, y):
    return GiantRat(x, y)


def _spawn_goblin(x, y):
    return Goblin(x, y)

def _spawn_orc(x, y):
    return Orc(x, y)

def _spawn_skeleton(x, y):
    return Skeleton(x, y)


def _spawn_wolf(x, y):
    return Wolf(x, y)


STRUCTURE_BLUEPRINTS = {
    "witch_hut": build_blueprint(
        "witch_hut",
        "Witch Hut",
        [
            "##+##",
            "#...#",
            "#...#",
            "##+##",
        ],
        {"#": wall, ".": tavern_floor, "+": door},
        walkable_chars={".", "+"},
        description="A crooked hut for swamp witches.",
    ),
    "windmill": build_blueprint(
        "windmill",
        "Windmill",
        [
            "#####",
            "#...#",
            "#...#",
            "#...#",
            "##+##",
        ],
        {"#": wall, ".": tavern_floor, "+": door},
        walkable_chars={".", "+"},
        description="A windmill for grinding grain.",
    ),
    "small_cabin": build_blueprint(
        "small_cabin",
        "Cabin",
        [
            "        ",
            " ###### ",
            " #bs.w# ",
            " #.p.t# ",
            " #w.wp# ",
            " ###+## ",
            "        ",
        ],
        {"#": wall, "w": tavern_cobweb, "p": wood_plank, ".": tavern_floor, "V": tavern_floor, "+": door, "b": bed, "t": table, "s": shelf},
        walkable_chars={".", "V", "+"},
        description="A simple frontier cabin.",
        npc_map={"V": _spawn_villager},
    ),
    "watch_tower": build_blueprint(
        "watch_tower",
        "Watchtower",
        [
            "  #####  ",
            " ##twt## ",
            " #p...l# ",
            " +..===# ",
            " #.wp.b# ",
            " ##b.b## ",
            "  #####  ",
        ],
        {"#": wall, ".": tavern_floor, "l": ladder, "+": door, "b": bed, "t": table, "w": tavern_cobweb, "p": wood_plank, "c": tavern_crate, "b": tavern_barrel, "=": bar_counter},
        walkable_chars={".", "+"},
        description="A defensive tower on a hilltop.",
    ),
    "shrine": build_blueprint(
        "shrine",
        "Shrine",
        [
            "  #  ",
            " #&# ",
        ],
        {"#": wall, ".": floor, "&": altar},
        walkable_chars={"."},
        description="A simple stone shrine.",
    ),
    "shop": build_blueprint(
        "shop",
        "Shop",
        [
            "        ",
            " #+#### ",
            " #.sts# ",
            " #..Sb# ",
            " #.===# ",
            " #...c# ",
            " ##+### ",
            "        ",
        ],
        {"#": wall, ".": tavern_floor, "b": tavern_barrel, "c": tavern_crate, "S": tavern_floor, "+": door, "s": shelf, "t": shelf_two, "=": bar_counter},
        walkable_chars={".", "S", "+"},
        description="A traveling merchant's storefront.",
        npc_map={"S": _spawn_shopkeeper},
    ),
    "tavern": build_blueprint(
        "tavern",
        "Tavern",
        [
            "            ",
            "  ######### ",
            "  +..sh..o# ",
            " ##k....7.# ",
            " #p.....|A# ",
            " #t..t..|.# ",
            " #p..pk.|c# ",
            " ######+### ",
            "            ",
        ],
        {"#": wall, ".": tavern_floor, "s": shelf, "h": shelf_two, "o": tavern_floor, "c": tavern_crate, "b": tavern_barrel, "p": tavern_floor, "A": tavern_floor, "k": tavern_barrel_two, "I": bar_counter_two, "|": bar_counter_three, "7": bar_counter_four, "t": table, "+": door},
        walkable_chars={".", "p", "A", "o", "+"},
        description="A rowdy wayside tavern.",
        npc_map={"A": _spawn_innkeeper, "p": _spawn_tavern_patron, "g": _spawn_goblin, "o": _spawn_orc},
    ),

    "blacksmith": build_blueprint(
        # SQUARE + CHIMNEY: compact square with a stack poking out the roofline
        "blacksmith",
        "Blacksmith",
        [
            "          ",
            " #######  ",
            " #.|F.s#  ",
            " +.|.N.#  ",
            " #.7.B.#  ",
            " #.....#  ",
            " #######  ",
            "          ",
        ],
        {"#": wall, ".": floor, "B": floor, "F": forge, "N": anvil, "s": shelf_three, "+": door, "|": bar_counter_five, "7": bar_counter_six},
        walkable_chars={".", "B", "+"},
        description="A soot-stained smithy, its chimney visible over the rooftops.",
        npc_map={"B": _spawn_blacksmith},
    ),

    "general_store": build_blueprint(
        # WIDE RECTANGLE: long, low shopfront -- unmistakably squat compared to everything else
        "general_store",
        "General Store",
        [
            "              ",
            " ############ ",
            " +..........# ",
            " #.s..M..s..# ",
            " #.s..K.p...# ",
            " ######+##### ",
        ],
        {"#": wall, ".": tavern_floor, "s": shelf, "M": bar_counter, "K": tavern_floor, "p": tavern_floor, "+": door},
        walkable_chars={".", "K", "p", "+"},
        description="A cramped general store selling a bit of everything.",
        npc_map={"K": _spawn_shopkeeper, "p": _spawn_villager},
    ),

    "house": build_blueprint(
        # SMALL SQUARE: deliberately the plainest, smallest footprint -- reads as "just a house"
        "house",
        "House",
        [
            "        ",
            " ###### ",
            " +..ss# ",
            " #...V# ",
            " #.b.t# ",
            " ###### ",
            "        ",
        ],
        {"#": wall, ".": tavern_floor, "b": bed, "t": table, "V": tavern_floor, "+": door, "s": shelf,},
        walkable_chars={".", "V", "+"},
        description="A modest villager's home.",
        npc_map={"V": _spawn_villager},
    ),

    "stable": build_blueprint(
        # LONG BARN: very elongated and short -- the most stretched-out silhouette on the map
        "stable",
        "Stable",
        [
            "                ",
            " ############## ",
            " +............# ",
            " #h.h.h.h.h.h.# ",
            " ############## ",
            "                ",
        ],
        {"#": wall, ".": floor, "h": hay, "+": door},
        walkable_chars={".", "+"},
        description="A drafty stable smelling of hay and horses.",
        npc_map={},
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
    return _spawns_from_entity_map(blueprint.npc_map, blueprint, placed_tiles) if blueprint else []


def monsters_for_placement(structure_id, placed_tiles):
    """
    Instantiate the Monsters a structure's blueprint declares in its
    monster_map, given the placed_tiles returned by place_structure()/
    place_structure_at_anchor() -- the monster equivalent of
    npcs_for_placement() above, for blueprints that want a squatter or
    guardian (giant rats nesting in a cabin, a skeleton warding a shrine,
    ...) baked directly into their ASCII art instead of spawned
    separately by whatever encounter/room system placed the building.
    """
    blueprint = get_structure_blueprint(structure_id)
    return _spawns_from_entity_map(blueprint.monster_map, blueprint, placed_tiles) if blueprint else []


def _spawns_from_entity_map(entity_map, blueprint, placed_tiles):
    """
    Shared by npcs_for_placement()/monsters_for_placement(): instantiate
    whatever `entity_map` (a blueprint's npc_map or monster_map) declares,
    at the exact positions marked in its ASCII art (e.g. the 'A' in the
    tavern layout, or a monster_map's 'r' in a cabin layout).

    place_structure() only returns the flat list of placed (x, y, tile)
    tuples, so to recover *which* placed tile corresponds to which char we
    re-walk blueprint.tile_map from the structure's origin (its top-left
    corner, i.e. the minimum x/y among placed_tiles) rather than changing
    place_structure's return shape, which other callers rely on.
    """
    if not entity_map or not placed_tiles:
        return []

    origin_x = min(x for x, _, _ in placed_tiles)
    origin_y = min(y for _, y, _ in placed_tiles)
    placed_positions = {(x, y) for x, y, _ in placed_tiles}

    spawns = []
    for dy, row in enumerate(blueprint.tile_map):
        for dx, char in enumerate(row):
            spawn_entity = entity_map.get(char)
            if spawn_entity is None:
                continue
            gx, gy = origin_x + dx, origin_y + dy
            if (gx, gy) in placed_positions:
                spawns.append(spawn_entity(gx, gy))
    return spawns


def bounding_box_for_footprints(footprints, game_map, pad=4):
    """
    Compute a (min_x, min_y, max_x, max_y) box spanning every placed_tiles
    list in `footprints`, padded outward by `pad` tiles and clamped to
    the map -- used as TownNPC.wander_bounds so wandering stays roughly
    within the town/building's surroundings (roads, plaza) instead of
    drifting off toward the horizon. Returns None if `footprints` is
    empty (nothing to bound).
    """
    # Materialize first -- `footprints` may be a one-shot generator (see
    # create_town_npcs()'s call site), and walking it twice (once for xs,
    # once for ys) would silently leave the second pass empty otherwise.
    footprints = list(footprints)
    xs = [x for placed_tiles in footprints for x, _y, _tile in placed_tiles]
    ys = [y for placed_tiles in footprints for _x, y, _tile in placed_tiles]
    if not xs:
        return None
    return (
        max(0, min(xs) - pad),
        max(0, min(ys) - pad),
        min(game_map.width - 1, max(xs) + pad),
        min(game_map.height - 1, max(ys) + pad),
    )


def assign_npc_schedule_anchors(npcs, wander_bounds):
    """
    Post-processing step for freshly spawned TownNPCs: gives each one a
    shared `wander_bounds`, without changing any NPC factory's
    `(x, y) -> NPC` signature -- blueprint.npc_map entries and the
    Innkeeper/Shopkeeper/Townsfolk/... constructors are untouched; this
    only sets an attribute afterward, the same way place_structure()'s
    callers already treat "where things end up" as separate from "how
    they're built".

    `home` deliberately isn't touched here -- TownNPC.__init__() already
    defaults it to the NPC's own spawn tile (their designated spot from
    the blueprint's npc_map, e.g. a bed, a stall, a corner of a house),
    which is exactly where SLEEPING should send them. Doors are only
    ever a waypoint astar() naturally routes through on the way there
    (see TownNPC._pathfind_toward()), never the destination itself.
    """
    for npc in npcs:
        if isinstance(npc, TownNPC):
            npc.wander_bounds = wander_bounds


def create_town_npcs(game_map, town_buildings):
    """Create a small static population for overworld town buildings.

    If a building's blueprint declares an npc_map and/or a monster_map,
    its NPCs and monsters are spawned at the exact spots marked in the
    ASCII art. Otherwise this falls back to the older per-structure_id
    placement below, so blueprints that haven't been given an npc_map
    yet still get populated.

    Every spawned TownNPC also gets a wander_bounds shared across the
    whole town via assign_npc_schedule_anchors() -- see
    TownNPC.take_turn(). `home` needs no help here: it already defaults
    to each NPC's own spawn tile. assign_npc_schedule_anchors() is a
    no-op for anything that isn't a TownNPC, so mixing a blueprint's
    monster_map spawns (e.g. a squatter left behind after a raid) into
    the same list here is safe.
    """
    npcs = []
    occupied = set()

    wander_bounds = bounding_box_for_footprints(
        (placed_tiles for _structure_id, placed_tiles in town_buildings), game_map
    )

    for structure_id, placed_tiles in town_buildings:
        blueprint = get_structure_blueprint(structure_id)
        if blueprint and (blueprint.npc_map or blueprint.monster_map):
            spawned = npcs_for_placement(structure_id, placed_tiles) + monsters_for_placement(structure_id, placed_tiles)
            assign_npc_schedule_anchors(spawned, wander_bounds)
            npcs.extend(spawned)
            occupied.update((entity.x, entity.y) for entity in spawned)
            continue

        positions = _walkable_structure_positions(game_map, placed_tiles, occupied)
        if not positions:
            continue

        structure_npcs = []
        if structure_id == "tavern":
            x, y = positions[len(positions) // 2]
            npc = Innkeeper(x, y)
            structure_npcs.append(npc)
            occupied.add((x, y))

            remaining = [pos for pos in positions if pos not in occupied]
            for x, y in random.sample(remaining, min(2, len(remaining))):
                npc = _spawn_tavern_patron(x, y)
                structure_npcs.append(npc)
                occupied.add((x, y))

        elif structure_id == "shop":
            x, y = positions[len(positions) // 2]
            npc = Shopkeeper(x, y)
            structure_npcs.append(npc)
            occupied.add((x, y))

        elif structure_id == "house":
            x, y = random.choice(positions)
            npc = Townsfolk(x, y)
            structure_npcs.append(npc)
            occupied.add((x, y))

        assign_npc_schedule_anchors(structure_npcs, wander_bounds)
        npcs.extend(structure_npcs)

    return npcs