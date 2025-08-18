import random
from entities.dungeon_npcs import DungeonHealer # <--- NEW IMPORT
from entities.base_entity import NPC

class NPC:
    def __init__(self, x, y, char, name, color, dialogue=None):
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.dialogue = dialogue or []
        self.alive = True
        self.blocks_movement = True
        self.initiative = 0

    def roll_initiative(self):
        self.initiative = random.randint(1, 20)

    def get_dialogue(self):
        """Return random dialogue line"""
        if self.dialogue:
            return random.choice(self.dialogue)
        return f"{self.name} nods at you."

    def take_turn(self, player, game_map, game):
        """NPCs generally don't take active turns in the same way as monsters.
        This method is a placeholder to prevent AttributeError."""
        pass # Do nothing for most NPCs

class Bartender(NPC):
    def __init__(self, x, y):
        dialogue = [
            "Welcome to The Prancing Pony! What can I get you?",
            "The dungeon's been acting up lately. Strange sounds at night...",
            "You look like an adventurer. The dungeon entrance is just outside.",
            "Be careful out there. Many who enter don't return.",
            "Need a drink before you face the depths?",
        ]
        super().__init__(x, y, 'A', 'Bartender', (255, 215, 0), dialogue)

class Merchant(NPC):
    def __init__(self, x, y):
        dialogue = [
            "Welcome to my shop! What would you like to buy?",
            "I have the finest goods in the land!",
            "Feel free to browse my wares.",
            "If you have something to sell, I'm all ears!"
        ]
        super().__init__(x, y, 'M', 'Merchant', (255, 215, 0), dialogue)  # Yellow color for the Merchant

    def offer_trade(self, player, game):
        """Handle the trading logic with the player."""
        game.message_log.add_message(f"{self.name}: What do you wish to trade?", (0, 255, 0))
        # Here you can implement the logic for displaying items for sale and handling purchases
        # For simplicity, let's just show a placeholder message for now
        game.message_log.add_message("Items for sale: Healing Potion (10 gold)", (200, 200, 255))
        # Implement actual trading logic later


class Patron(NPC):
    def __init__(self, x, y, name):
        dialogue = [
            "I heard there's treasure deep in the dungeon.",
            "The monsters have been getting stronger lately.",
            "My cousin went into that dungeon last week... haven't seen him since.",
            "They say there are ancient artifacts buried below.",
            "Be careful in there, adventurer.",
            "The deeper you go, the more dangerous it gets.",
            "I once made it to the third level... barely escaped!",
        ]
        super().__init__(x, y, 'p', name, (200, 200, 200), dialogue)

def create_tavern_npcs(game_map, door_position):
    """Create NPCs for the tavern"""
    npcs = []

    # Bartender behind the bar
    bar_y = 13
    bartender_x = game_map.width // 2 - 6
    bartender_y = bar_y - 1  # Behind the bar
    if bartender_y > 0:
        bartender = Bartender(bartender_x, bartender_y)
        npcs.append(bartender)

    # Add a Merchant NPC
    merchant_x = 5  # Position the Merchant
    merchant_y = 1  # Same row as the bartender
    merchant = Merchant(merchant_x, merchant_y)
    npcs.append(merchant)

    # Add some patrons at tables/chairs
    patron_positions = []
    patron_names = ["Old Tom", "Merchant Mary", "Warrior Bill", "Sage Alice"]

    # Find available chair positions
    for y in range(2, game_map.height - 2):
        for x in range(2, game_map.width - 2):
            if (hasattr(game_map.tiles[y][x], 'char') and
                game_map.tiles[y][x].char == 'c' and
                len(patron_positions) < 3):  # Limit to 3 patrons
                patron_positions.append((x, y))

    # Create patrons
    for i, (x, y) in enumerate(patron_positions[:3]):
        if i < len(patron_names):
            patron = Patron(x, y, patron_names[i])
            npcs.append(patron)

    # --- NEW: Add a DungeonHealer to the tavern ---
    healer_x = 3  # One tile right of the fireplace
    healer_y = game_map.height // 2 - 4
    if game_map.is_walkable(healer_x, healer_y) and \
       not any(npc.x == healer_x and npc.y == healer_y for npc in npcs):
        tavern_healer = DungeonHealer(healer_x, healer_y)
        npcs.append(tavern_healer)

    return npcs



