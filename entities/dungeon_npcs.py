import random

from core.game import GameState
from items.items import torch, lesser_healing_potion, greater_healing_potion, meat, green_apple, fromage, bread, mushroom, full_plate_armor, robes_of_protection, adamantine_long_sword, staff_of_magi, duelists_rapier, dwarven_battle_axe, dragonsbane_warhammer, flameheart_flail, flameheart_short_sword, CampfireKit
from entities.base_entity import NPC

class DungeonHealer(NPC):
    def __init__(self, x, y):
        dialogue = [
            "Rest here, adventurer. The path ahead is perilous.",
            "I can mend your wounds, for a small favor...",
            "The dungeon's darkness drains even the strongest. Take a moment."
        ]
        super().__init__(x, y, 'H', 'Healer', (0, 255, 255), dialogue) # Cyan color
    
        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }    

    def offer_rest(self, player, game):
        game.message_log.add_message(f"{self.name}: You feel your wounds mend.", (0, 255, 0))
        player.hp = player.max_hp # Full heal for simplicity
        # Or implement short rest with hit dice

class DungeonMerchant(NPC):
    def __init__(self, x, y):
        dialogue = [
            "Welcome to my shop! What would you like to buy?",
            "I have the finest goods in the land!",
            "Feel free to browse my wares.",
            "If you have something to sell, I'm all ears!",
            "Careful out there… but first, care to buy a potion or two?"
        ]
        super().__init__(x, y, 'rc', 'Dungeon Merchant', (255, 215, 100), dialogue)  # Different char/color for tavern merchant
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
            fromage,
            torch,
        ]
        # Chance-based items with their spawn probabilities (fewer and simpler than dungeon merchant)
        chance_items_with_chance = [
            (duelists_rapier, 0.5),
            (staff_of_magi, 0.4),
            (full_plate_armor, 0.45),
            (adamantine_long_sword, 0.45),
            (flameheart_flail, 0.45),
            (flameheart_short_sword, 0.4),
            (robes_of_protection, 0.45),
            (dwarven_battle_axe, 0.4),
            (dragonsbane_warhammer, 0.4),
            # Add more tavern-specific items and chances if desired
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
        for item_template, chance in chance_items_with_chance:
            if random.random() < chance:
                new_item = item_template.__class__(
                    name=item_template.name,
                    char=item_template.char,
                    color=item_template.color,
                    description=item_template.description,
                    **{k: v for k, v in item_template.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                )
                self.items_for_sale.append(new_item)

    def offer_trade(self, player, game):
        """Handle the trading logic with the player."""
        game.message_log.add_message(f"{self.name}: Welcome, traveler! Care to browse my wares?", (0, 255, 0))
        game.message_log.add_message("Items for sale:", (200, 200, 255))

        # Display items for sale
        for item in self.items_for_sale:
            game.message_log.add_message(f"{item.name} - {item.price} gold", (255, 255, 255))

        # Allow player to buy or sell
        game.message_log.add_message("Type 'buy {item}' to buy and 'sell {item}' to sell.", (200, 200, 255))
        game.message_log.add_message("Type your input:", (200, 200, 255))
        game.message_log.add_message(" ", (200, 200, 255))

        # Set the game state to trade temporarily
        game.game_state = GameState.TRADE  # Set game state to trade
        game.message_log.show_input_area = True  # Show input area for trade input
        game.message_log.current_input = ""  # Clear input when activating the input area



    def buy_item(self, player, item_name):
        for item in self.items_for_sale:
            if item.name.lower() == item_name.lower():
                if player.gold >= item.price:
                    player.gold -= item.price
    
                    # Create a new instance of the item to add to player inventory
                    new_item = item.__class__(
                        name=item.name,
                        char=item.char,
                        color=item.color,
                        description=item.description,
                        **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                    )
    
                    if player.inventory.add_item(new_item):
                        self.items_for_sale.remove(item)  # Remove the original from merchant
                        return f"You bought {item.name}!"
                    else:
                        return "Your inventory is full!"
                else:
                    return "Scram! you don't have enough gold!"
        return "We don't sell that kind of item here!"
    


    def sell_item(self, player, item_name):
        """Logic to sell an item."""
        for item in player.inventory.items:  # Access the player's inventory items
            if item.name.lower() == item_name.lower():  # Case insensitive comparison
                player.inventory.remove_item(item)  # Remove the item from the player's inventory
                player.gold += item.price // 2  # Assuming the merchant pays half the price
                self.items_for_sale.append(item)  # Add the item back to the merchant's inventory
                return f"You sold {item.name}!"
        return "Item not found in your inventory."


class Bartender(NPC):
    def __init__(self, x, y):
        dialogue = [
            "Welcome to The Prancing Pony! What can I get you?",
            "The dungeon's been acting up lately. Strange sounds at night...",
            "You look like an adventurer. The dungeon entrance is just outside.",
            "Be careful out there. Many who enter don't return.",
            "Need a drink before you face the depths?",
        ]
        super().__init__(x, y, 'A', 'Bartender', (255, 215, 0), dialogue) # <--- CHANGED 'B' to 'A'        
