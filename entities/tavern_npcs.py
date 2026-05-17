import random
import pygame

from core.game import GameState
from items.items import (
    torch, throwing_knife, lesser_healing_potion, kite_shield, greater_healing_potion, apprentices_staff, half_plate_armor, 
    meat, green_apple, fromage, bread, carrot, spell_book, holy_symbol, mushroom, silver_dagger, iron_short_sword, adamantine_long_sword, staff_of_magi, 
    duelists_rapier, dwarven_battle_axe, dragonsbane_warhammer, steel_long_sword, steel_battle_axe, oak_staff, padded_armor, 
    chainmail_armor, robes, scale_mail_armor, sturdy_quarterstaff, leather_cap, iron_helmet, steel_helmet, hood_of_shadows, great_helm, mages_circlet, leather_boots, 
    iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers,CampfireKit, Food, Weapon, Helmet, Armor, Boots, OffHand
)

from entities.dungeon_npcs import DungeonHealer 
from entities.base_entity import NPC


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
            "Welcome to my tavern shop! Looking for something special?",
            "I have some fine goods and tasty treats.",
            "Feel free to browse my selection.",
            "If you want to sell something, just let me know.",
            "Careful out there, adventurer!"
        ]
        super().__init__(x, y, 'rc', 'Tavern Merchant', (255, 215, 100), dialogue)  # Different char/color for tavern merchant
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
            throwing_knife,
            meat,
            bread,
            carrot,
            fromage,
            torch,
        ]
        # Chance-based items with their spawn probabilities (fewer and simpler than dungeon merchant)
        chance_items_with_chance = [
            (silver_dagger, 0.5),
            (steel_long_sword, 0.4),
            (half_plate_armor, 0.45),
            (scale_mail_armor, 0.4),
            (sturdy_quarterstaff, 0.4),
            (apprentices_staff, 0.45),
            (kite_shield, 0.4),
            (greater_healing_potion, 0.3),
            (spell_book, 0.25),
            (holy_symbol, 0.25),
            # Add more tavern-specific items and chances if desired
        ]

        self.items_for_sale = []
       
        # Add default items
        for item in default_items:
            if isinstance(item, CampfireKit):
                self.items_for_sale.append(item)
            else:
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
        game.message_log.add_message("Or use 'buy all food', 'sell all weapons', or 'sell all armor'.", (200, 200, 255))
        game.message_log.add_message("Type your input:", (200, 200, 255))
        game.message_log.add_message(" ", (200, 200, 255))

        # Set the game state to trade temporarily
        game.game_state = GameState.TRADE  # Set game state to trade
        game.message_log.show_input_area = True  # Show input area for trade input
        game.message_log.current_input = ""  # Clear input when activating the input area



    def buy_item(self, player, item_name):
        if item_name == "all food":
            food_items = [item for item in self.items_for_sale if isinstance(item, Food)]
            if not food_items:
                return "No food items are available for sale."

            purchased_items = []
            total_cost = 0
            for item in list(food_items):
                if player.gold < item.price:
                    continue

                new_item = item.__class__(
                    name=item.name,
                    char=item.char,
                    color=item.color,
                    description=item.description,
                    **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                )

                if player.inventory.add_item(new_item):
                    player.gold -= item.price
                    total_cost += item.price
                    purchased_items.append(item.name)
                    self.items_for_sale.remove(item)
                else:
                    break

            if not purchased_items:
                return "You couldn't buy any food. Check your gold or inventory space."
            item_list = ", ".join(purchased_items)
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_guard_ability()
            return f"You bought {len(purchased_items)} food items for {total_cost} gold: {item_list}."

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
                        player.update_throw_knife_ability()
                        player.update_spellbook_abilities()
                        player.update_guard_ability()
                        return f"You bought {item.name}!"
                    else:
                        return "Your inventory is full!"
                else:
                    return "Scram! you don't have enough gold!"
        return "We don't sell that kind of item here!"
    


    def sell_item(self, player, item_name):
        """Logic to sell an item or multiple items."""
        # Handle bulk selling
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
                total_gold += item.price 
                self.items_for_sale.append(item)
            player.gold += total_gold
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
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
                player.update_guard_ability()
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



