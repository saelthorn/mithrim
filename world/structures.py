from dataclasses import dataclass, field
import random

from entities.base_entity import NPC
from world.tile import (
    ground, grass, road, tall_grass, wall, tavern_floor, floor, bar_counter_two, bar_counter_three, bar_counter_four, 
    table, crate, tavern_barrel_two, altar, door, forge, anvil, shelf, bed, hay, bar_counter
)

from core.game import GameState
from items.items import (
    torch, throwing_knife, lesser_healing_potion, greater_healing_potion, meat, green_apple, fromage, bread, mushroom, 
    carrot, spell_book, holy_symbol, full_plate_armor, robes_of_protection, adamantine_long_sword, staff_of_magi, 
    duelists_rapier, dwarven_battle_axe, dragonsbane_warhammer, flameheart_flail, flameheart_short_sword, scale_mail_armor, 
    sturdy_quarterstaff, leather_cap, iron_helmet, steel_helmet, hood_of_shadows, great_helm, mages_circlet, leather_boots, 
    iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers, silver_dagger, round_shield, iron_short_sword,
    CampfireKit, Food, Weapon, Helmet, Armor, Boots, OffHand, FocusItem
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


def _clone_item(item):
    """
    Return a fresh instance of `item`, matching the clone pattern
    merchants already use when handing out one of their own template
    items, so the player never ends up aliasing the template object
    itself. Shared by Shopkeeper's stocking/bulk-buy and Innkeeper's
    food menu below.
    """
    if isinstance(item, CampfireKit):
        return CampfireKit()
    return item.__class__(
        name=item.name,
        char=item.char,
        color=item.color,
        description=item.description,
        **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
    )


def _buy_from_stock(seller, player, item_name):
    """
    Shared "buy an item (or every food item at once) from a merchant's
    items_for_sale list" logic, used by both Shopkeeper.buy_item() and
    Innkeeper.buy_item() so the purchase rules (afford-check, inventory-
    full refund, bulk "all food" buy) only live in one place. `seller`
    only needs an `items_for_sale` list -- it doesn't need to be a
    Shopkeeper itself, which is what lets Innkeeper reuse this too.
    """
    if item_name == "all food":
        food_items = [item for item in seller.items_for_sale if isinstance(item, Food)]
        if not food_items:
            return "No food items are available for sale."

        purchased_items = []
        total_cost = 0
        for item in list(food_items):
            if player.gold < item.price:
                continue

            new_item = _clone_item(item)
            if player.inventory.add_item(new_item):
                player.gold -= item.price
                total_cost += item.price
                purchased_items.append(item.name)
                seller.items_for_sale.remove(item)
            else:
                break

        if not purchased_items:
            return "You couldn't buy any food. Check your gold or inventory space."
        item_list = ", ".join(purchased_items)
        player.update_throw_knife_ability()
        player.update_spellbook_abilities()
        player.update_guard_ability()
        return f"You bought {len(purchased_items)} food items for {total_cost} gold: {item_list}."

    for item in seller.items_for_sale:
        if item.name.lower() == item_name.lower():
            if player.gold >= item.price:
                player.gold -= item.price

                # Give the actual item instance to the player
                if player.inventory.add_item(item):
                    seller.items_for_sale.remove(item)  # Remove the item from the seller
                    player.update_throw_knife_ability()
                    player.update_spellbook_abilities()
                    player.update_guard_ability()
                    return f"You bought {item.name}!"
                else:
                    # If adding failed, refund the player
                    player.gold += item.price
                    return "Your inventory is full!"
            else:
                return "Scram! you don't have enough gold!"
    return "We don't sell that kind of item here!"


class Townsfolk(TownNPC):
    def __init__(self, x, y, name=None):
        dialogue = [
            "Roads have been busier since the old entrances opened again.",
            "Mind the wilds after dusk. The grass gets quiet before trouble.",
            "If you are heading below, make sure you have food and light.",
            "Every town around here has a story about someone who went missing.",
        ]
        super().__init__(x, y, 'p', name or random.choice(TOWNSFOLK_NAMES), (205, 205, 185), dialogue)


class Blacksmith(TownNPC):
    def __init__(self, x, y, name=None):
        dialogue = [
            "I am still unpacking the shelves, but I know a good buyer when I see one.",
            "Bring back anything odd from the ruins. Odd things sell.",
            "A careful blade and a dry torch are worth more than bravado.",            
        ]
        super().__init__(x, y, 'p', name or random.choice(TOWNSFOLK_NAMES), (205, 205, 185), dialogue)


class Priest(TownNPC):
    def __init__(self, x, y, name=None):
        dialogue = [
            "Roads have been busier since the old entrances opened again.",
            "Mind the wilds after dusk. The grass gets quiet before trouble.",
            "If you are heading below, make sure you have food and light.",
            "Every town around here has a story about someone who went missing.",
        ]
        super().__init__(x, y, 'p', name or random.choice(TOWNSFOLK_NAMES), (205, 205, 185), dialogue)



class Innkeeper(TownNPC):
    #: Gold charged for a night's stay -- see rest_player().
    rest_cost = 5
    #: Hours the world clock advances per rest -- see rest_player().
    rest_hours = 8

    def __init__(self, x, y):
        dialogue = [
            "Welcome in, traveler. Warm floorboards beat cold roads.",
            "Most adventurers ask about dungeons. The wise ones ask about supper.",
            "You can learn plenty by listening before you descend.",
        ]
        super().__init__(x, y, 'A', 'Innkeeper', (255, 215, 120), dialogue)

        # A small, fixed food menu -- unlike Shopkeeper, the innkeeper
        # doesn't restock randomly or carry equipment, only supper and a
        # bed. See structures.STRUCTURE_BLUEPRINTS' "tavern" blueprint.
        food_menu = [bread, meat, fromage, green_apple, carrot, mushroom]
        self.items_for_sale = [_clone_item(item) for item in food_menu]

    def offer_trade(self, player, game):
        """
        Open the same shop overlay Shopkeeper.offer_trade() uses (see
        game.py's render_shop_menu()/handle_shop_menu_input()) scoped to
        the innkeeper's food menu -- that overlay only needs an object
        with .name/.items_for_sale/.buy_item()/.sell_item(), so it works
        unmodified for any merchant-shaped NPC, not just Shopkeeper.
        """
        game._previous_game_state = game.game_state
        game._shop_menu_merchant  = self
        game._shop_selected_index = 0
        game._shop_mode           = "buy"
        game.game_state           = GameState.SHOP_MENU

    def buy_item(self, player, item_name):
        return _buy_from_stock(self, player, item_name)

    def sell_item(self, player, item_name):
        """The innkeeper doesn't buy anything back -- kept so the shared
        shop overlay's SELL tab has something safe to call rather than
        crashing if a player tabs over to it out of habit."""
        return f'{self.name} shakes their head. "I only deal in food and lodging here."'

    def rest_player(self, player, game):
        """
        Handle the player paying for a night's stay: charges rest_cost
        gold, fully restores HP, and advances the world clock by a full
        night through StorySystems.fire_rest() -- the canonical inn/camp
        rest path story_integration.py's docstring already earmarks for
        this, so any story timer (deadlines, decay, scheduled events)
        sees it exactly like any other rest.

        Returns a message string for the caller to log, matching
        buy_item()/sell_item()'s "return a string, let the caller log
        it" convention.
        """
        if player.gold < self.rest_cost:
            return f"You can't afford a room tonight. A bed costs {self.rest_cost} gold."

        player.gold -= self.rest_cost
        player.hp = player.max_hp

        # Some classes track further per-rest resources (spell slots,
        # ability charges, ...) behind their own long_rest() hook; restore
        # those too if present, without this needing to know their shape.
        long_rest = getattr(player, "long_rest", None)
        if callable(long_rest):
            long_rest()

        game.stories.fire_rest(self.rest_hours)
        return f"You rest through the night and wake up refreshed. (-{self.rest_cost} gold)"


class Shopkeeper(TownNPC):
    def __init__(self, x, y):
        dialogue = [
            "I am still unpacking the shelves, but I know a good buyer when I see one.",
            "Bring back anything odd from the ruins. Odd things sell.",
            "A careful blade and a dry torch are worth more than bravado.",
        ]
        super().__init__(x, y, 'rc', 'Shopkeeper', (230, 200, 120), dialogue)

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }
        # Default items always sold
        default_items = [
            CampfireKit(),
            lesser_healing_potion,
            greater_healing_potion,
            meat,
            bread,
            carrot,
            fromage,
            torch,
            throwing_knife,
        ]
        # Chance-based items with their spawn probabilities (fewer and simpler than dungeon merchant)
        chance_items_with_chance = [
            (duelists_rapier, 0.3),
            (staff_of_magi, 0.3),
            (full_plate_armor, 0.35),
            (scale_mail_armor, 0.4),
            (sturdy_quarterstaff, 0.6),
            (iron_helmet, 0.7),
            (leather_cap, 0.8),
            (steel_helmet, 0.6),
            (hood_of_shadows, 0.4),
            (great_helm, 0.3),
            (mages_circlet, 0.4),
            (leather_boots, 0.8),
            (iron_greaves, 0.8),
            (boots_of_speed, 0.4),
            (boots_of_stealth, 0.4),
            (dwarven_stompers, 0.3),
            (adamantine_long_sword, 0.5),
            (flameheart_flail, 0.5),
            (flameheart_short_sword, 0.4),
            (robes_of_protection, 0.35),
            (dwarven_battle_axe, 0.45),
            (dragonsbane_warhammer, 0.3),
            (spell_book, 0.25),
            (holy_symbol, 0.25),
            (carrot, 0.3),
            (mushroom, 0.3),
            (green_apple, 0.3),
            (bread, 0.3),
            (meat, 0.3),
        ]

        self.items_for_sale = []
       
        # Add default items
        for item in default_items:
            if isinstance(item, CampfireKit):
                self.items_for_sale.append(CampfireKit()) # Create a new instance directly
            else:
                # Create a new instance for other items
                new_item = item.__class__(
                    name=item.name,
                    char=item.char,
                    color=item.color,
                    description=item.description,
                    **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                )
                self.items_for_sale.append(new_item)
    
        # Add chance-based items
        for item, chance in chance_items_with_chance:
            if random.random() < chance:
                new_item = item.__class__(
                    name=item.name,
                    char=item.char,
                    color=item.color,
                    description=item.description,
                    **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                )
                self.items_for_sale.append(new_item)

    def offer_trade(self, player, game):
        """Open the shop menu overlay instead of the legacy text-input trade flow."""
        game._previous_game_state  = game.game_state
        game._shop_menu_merchant   = self
        game._shop_selected_index  = 0
        game._shop_mode            = "buy"
        game.game_state            = GameState.SHOP_MENU



    def buy_item(self, player, item_name):
        return _buy_from_stock(self, player, item_name)
    


    def sell_item(self, player, item_name):
        """Logic to sell an item or multiple items."""
        # Handle bulk selling
        if item_name == "all equipments":
            equipments = [item for item in player.inventory.items if isinstance(item, (Weapon, OffHand, Armor, Helmet, Boots, FocusItem))]
            if not equipments:
                return "You don't have any equipments to sell."
            total_gold = 0
            for item in equipments:
                player.inventory.remove_item(item)
                total_gold += item.price // 2
                self.items_for_sale.append(item)
            player.gold += total_gold
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_holy_symbol_abilities()
            player.update_guard_ability()
            return f"You sold {len(equipments)} equipment(s) for {total_gold} gold!"

        if item_name == "all weapons":
            weapons = [item for item in player.inventory.items if isinstance(item, (Weapon, OffHand))]
            if not weapons:
                return "You don't have any weapons to sell."
            total_gold = 0
            for item in weapons:
                player.inventory.remove_item(item)
                total_gold += item.price // 2
                self.items_for_sale.append(item)
            player.gold += total_gold
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_guard_ability()
            return f"You sold {len(weapons)} weapon(s) for {total_gold} gold!"

        if item_name == "all armors":
            armor_items = [item for item in player.inventory.items if isinstance(item, (Helmet, Armor, Boots))]
            if not armor_items:
                return "You don't have any armor to sell."
            total_gold = 0
            for item in armor_items:
                player.inventory.remove_item(item)
                total_gold += item.price // 2
                self.items_for_sale.append(item)
            player.gold += total_gold
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_holy_symbol_abilities()
            player.update_guard_ability()
            return f"You sold {len(armor_items)} armor item(s) for {total_gold} gold!"
        
        # Handle single item selling
        for item in player.inventory.items:  # Access the player's inventory items
            if item.name.lower() == item_name.lower():  # Case insensitive comparison
                player.inventory.remove_item(item)  # Remove the item from the player's inventory
                player.gold += item.price // 2  # Assuming the merchant pays half the price
                self.items_for_sale.append(item)  # Add the item back to the merchant's inventory
                player.update_throw_knife_ability()
                player.update_spellbook_abilities()
                player.update_holy_symbol_abilities()
                player.update_guard_ability()
                return f"You sold {item.name}!"
        return "Item not found in your inventory."


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

def _spawn_blacksmith(x, y):
    return Blacksmith(x, y)

def _spawn_priest(x, y):
    return Priest(x, y)

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
            "  #  ",
            "  #  ",
            "#####",
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
            "       ",
            " ##+## ",
            " #...# ",
            " #.p.+ ",
            " #...# ",
            " ##### ",
            "       ",
        ],
        {"#": wall, ".": tavern_floor, "p": tavern_floor, "+": door},
        walkable_chars={".", "p", "+"},
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
            "##+##",
        ],
        {"#": wall, ".": tavern_floor, "+": door},
        walkable_chars={".", "+"},
        description="A defensive tower on a hilltop.",
    ),
    "shrine": build_blueprint(
        "shrine",
        "Shrine",
        [
            "  #  ",
            " #&# ",
            " #.# ",
        ],
        {"#": wall, ".": floor, "&": altar},
        walkable_chars={"."},
        description="A simple stone shrine.",
    ),
    "shop": build_blueprint(
        "shop",
        "Shop",
        [
            "       ",
            " ##### ",
            " #...# ",
            " #.S.+ ",
            " #...# ",
            " ##+## ",
            "       ",
        ],
        {"#": wall, ".": tavern_floor, "S": tavern_floor, "+": door},
        walkable_chars={".", "S", "+"},
        description="A traveling merchant's storefront.",
        npc_map={"S": _spawn_shopkeeper},
    ),
    "tavern": build_blueprint(
        "tavern",
        "Tavern",
        [
            "          ",
            "  ####### ",
            "  +.....# ",
            " ##k..7.# ",
            " #p...|A# ",
            " #tp..|.# ",
            " ####+### ",
            "          ",
        ],
        {"#": wall, ".": tavern_floor, "p": tavern_floor, "A": tavern_floor, "k": tavern_barrel_two, "I": bar_counter_two, "|": bar_counter_three, "7": bar_counter_four, "t": table, "+": door},
        walkable_chars={".", "p", "A", "+"},
        description="A rowdy wayside tavern.",
        npc_map={"A": _spawn_innkeeper, "p": _spawn_villager},
    ),
    "house": build_blueprint(
        "house",
        "House",
        [
            "       ",
            " ###+# ",
            " #...# ",
            " #.V.# ",
            " #...# ",
            " ##+## ",
            "       ",
        ],
        {"#": wall, ".": tavern_floor, "V": tavern_floor, "+": door},
        walkable_chars={".", "V", "+"},
        description="A modest family home.",
        npc_map={"V": _spawn_villager},
    ),

    "blacksmith": build_blueprint(
        # SQUARE + CHIMNEY: compact square with a stack poking out the roofline
        "blacksmith",
        "Blacksmith",
        [
            "   ##     ",
            " #######  ",
            " +..F..#  ",
            " #...N.#  ",
            " #...B.#  ",
            " #s....#  ",
            " #######  ",
            "          ",
        ],
        {"#": wall, ".": tavern_floor, "B": tavern_floor, "F": forge, "N": anvil, "s": shelf, "+": door},
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
            " +....# ",
            " #...V# ",
            " #.b.t# ",
            " ###### ",
            "        ",
        ],
        {"#": wall, ".": tavern_floor, "b": bed, "t": table, "V": tavern_floor, "+": door},
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