import random
import pygame

from core.game import GameState
from items.items import lesser_healing_potion, greater_healing_potion, dagger, short_sword, long_sword, battle_axe, quarterstaff, leather_armor, chainmail_armor, robes
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
        super().__init__(x, y, 'A', 'Merchant', (255, 215, 0), dialogue)  # Yellow color for the Merchant


        # Define items for sale
        self.items_for_sale = [
            lesser_healing_potion,  # Assuming these are defined as instances of Potion
            greater_healing_potion,
            dagger,
            short_sword,
            leather_armor,
            chainmail_armor,
        ]

    def offer_trade(self, player, game):
        """Handle the trading logic with the player."""
        game.message_log.add_message(f"{self.name}: What do you wish to trade?", (0, 255, 0))
        game.message_log.add_message("Items for sale:", (200, 200, 255))

        # Display items for sale
        for item in self.items_for_sale:
            game.message_log.add_message(f"{item.name} - {item.price} gold", (255, 255, 255))

        # Allow player to buy or sell
        game.message_log.add_message("Press 'B' to buy or 'S' to sell an item.", (200, 200, 255))
        game.message_log.add_message("Type your command:", (200, 200, 255))

        # Wait for player input
        game.game_state = GameState.TRADE  # Set game state to trade


    def buy_item(self, player, item_name):
        """Handle the logic for buying an item."""
        for item in self.items_for_sale:
            if item.name.lower() == item_name.lower():  # Case insensitive comparison
                if player.gold >= item.price:  # Assuming player has a gold attribute
                    player.gold -= item.price
                    player.inventory.add_item(item)  # Add the item to the player's inventory
                    self.items_for_sale.remove(item)  # Remove the item from the merchant's inventory
                    return f"You bought {item.name}!"
                else:
                    return "You don't have enough gold!"
        return "Item not found in merchant's inventory."


    def sell_item(self, player, item_name):
        """Logic to sell an item."""
        for item in player.inventory.items:  # Access the player's inventory items
            if item.name.lower() == item_name.lower():  # Case insensitive comparison
                player.inventory.remove_item(item)  # Remove the item from the player's inventory
                player.gold += item.price // 2  # Assuming the merchant pays half the price
                self.items_for_sale.append(item)  # Add the item back to the merchant's inventory
                return f"You sold {item.name}!"
        return "Item not found in your inventory."




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



def create_tavern_npcs(game_map, door_position, game_instance):
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

    game_instance.merchant = merchant

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



