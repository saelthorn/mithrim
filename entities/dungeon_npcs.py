import random
from entities.base_entity import NPC
from core.floating_text import FloatingText


from core.game import GameState

from items.items import (
    torch, throwing_knife, lesser_healing_potion, greater_healing_potion, meat, green_apple, fromage, bread, mushroom, 
    carrot, spell_book, holy_symbol, full_plate_armor, robes_of_protection, adamantine_long_sword, staff_of_magi, 
    duelists_rapier, dwarven_battle_axe, dragonsbane_warhammer, flameheart_flail, flameheart_short_sword, scale_mail_armor, 
    sturdy_quarterstaff, leather_cap, iron_helmet, steel_helmet, hood_of_shadows, great_helm, mages_circlet, leather_boots, 
    iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers, silver_dagger, round_shield, iron_short_sword,
    CampfireKit, Food, Weapon, Helmet, Armor, Boots, OffHand, FocusItem
)


class DungeonHealer(NPC):
    def __init__(self, x, y):
        self.x1 = x
        self.y1 = y        
        
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
        self.x1 = x
        self.y1 = y        
        
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
    
                    # Give the actual item instance to the player
                    if player.inventory.add_item(item):
                        self.items_for_sale.remove(item)  # Remove the item from merchant
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



_PRISONER_NAMES = [
    "Silas the Fallen", "Mara the Chained", "Old Wick",
    "Brother Dorath",   "Elara Dusk",       "Convict No. 7",
    "The Nameless One",
]

_PRISONER_DIALOGUES = [
    "Thank the gods… I thought I'd rot here. Take this — you've earned it.",
    "You opened it! Here, I kept this hidden from the guards. It's yours now.",
    "Freedom… I never thought I'd see it again. Please, take this.",
    "Quick — before more come. I found this in a crack in the wall. Take it.",
    "Bless you, stranger. This is all I have left. Keep it safe.",
    "They took everything from me… except this. It's yours.",
]

_PRISONER_FREED_LINES = [
    "Thank you again, adventurer. Stay safe out there.",
    "I'll find my way out. Go — there's more danger ahead.",
    "You gave me my life back. I won't forget it.",
]

_PRISONER_LOOT = [
    greater_healing_potion, lesser_healing_potion,
    silver_dagger,          iron_short_sword,
    torch,                  iron_helmet,
    round_shield,           bread,
    green_apple,
]


class PrisonerNPC(NPC):
    def __init__(self, x, y):
        self.x1 = x
        self.y1 = y

        name = random.choice(_PRISONER_NAMES)
        super().__init__(x, y, 'pnp', name, (200, 160, 120))
        self.dialogue_line  = random.choice(_PRISONER_DIALOGUES)
        self.reward_item    = self._make_reward()
        self.has_been_freed = False
        self.reward_given   = False   # True once the player has collected the reward

    # ── NPC interface ──────────────────────────────────────────────────────

    def get_dialogue(self):
        if self.has_been_freed:
            return random.choice(_PRISONER_FREED_LINES)
        return "...help… is someone there? The door — can you open it?"

    # ── Helpers ───────────────────────────────────────────────────────────

    def _make_reward(self):
        template = random.choice(_PRISONER_LOOT)
        try:
            init_vars = {
                k: v for k, v in vars(template).items()
                if k not in ('owner', 'x', 'y')
            }
            item = template.__class__(**init_vars)
        except Exception:
            item = template.__class__(
                name=template.name,
                char=template.char,
                color=template.color,
                description=getattr(template, 'description', ''),
            )
        item.x = self.x
        item.y = self.y
        return item

    def free(self, player, game_instance):
        """
        Mark the prisoner as freed.  Called when the cell door is opened.
        Only sets the flag and prints a flavour line — no reward is granted here.
        The reward is given when the player talks to the prisoner (F key).
        """
        if self.has_been_freed:
            return
        self.has_been_freed = True

        game_instance.message_log.add_message(
            f'{self.name}: "{self.dialogue_line}"', (220, 200, 140)
        )
        game_instance.floating_texts.append(
            FloatingText(self.x, self.y, "FREED!", (100, 255, 150), y_speed=0.5)
        )

    def give_reward(self, player, game_instance):
        """
        Grant the prisoner's reward item to the player.
        Called once when the player presses F while adjacent to a freed prisoner.
        Subsequent calls print a 'nothing left to give' message and return early.
        """
        if not self.has_been_freed:
            return

        if self.reward_given:
            game_instance.message_log.add_message(
                f'{self.name}: "You\'ve already taken all I have. Safe travels."',
                (220, 200, 140),
            )
            return

        self.reward_given = True

        if player.inventory.add_item(self.reward_item):
            game_instance.message_log.add_message(
                f"You receive the {self.reward_item.name}!",
                self.reward_item.color,
            )
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_thieves_tools_ability()
            player.update_guard_ability()
            player.update_holy_symbol_abilities()
        else:
            self.reward_item.x = player.x
            self.reward_item.y = player.y
            game_instance.game_map.items_on_ground.append(self.reward_item)
            game_instance.message_log.add_message(
                f"Inventory full! The {self.reward_item.name} drops to the floor.",
                self.reward_item.color,
            )




class EncounterVictim(NPC):
    """
    A bystander tied to a WORLD_ENCOUNTER_MENU scenario - the merchants being
    robbed, the guards making their last stand, the figure bound to the altar,
    etc. Before the fight is over the player can only talk to it (see
    combat_resolved(), driven by the `linked_monsters` list set on spawn).
    Once every monster tied to the encounter is dead, talking to it (F key)
    counts as rescuing it: it says its thanks and, if the scenario gives it
    one, hands over a reward - an item for the "sacrifice" victim, mirroring
    how PrisonerNPC.free()/give_reward() works in a dungeon, or gold for a
    rescued merchant.
    """
    def __init__(self, x, y, char, name, color, dialogue_line,
                 thanks_lines=None, after_lines=None, reward_item=None, reward_gold=0):
        super().__init__(x, y, char, name, color, [dialogue_line])
        self._danger_dialogue = dialogue_line
        self._thanks_lines = thanks_lines or [f"{name} nods gratefully."]
        self._after_lines  = after_lines or [f"{name} gives you a quiet nod."]

        self.linked_monsters = []   # Set by _spawn_world_encounter_victims once the monster group exists
        self.rescued          = False
        self.reward_item      = reward_item
        self.reward_gold      = reward_gold
        self.reward_given     = False

    def combat_resolved(self):
        """True once every monster tied to this encounter is dead (or none were ever linked)."""
        return not any(getattr(monster, 'alive', False) for monster in self.linked_monsters)

    def get_dialogue(self):
        if not self.combat_resolved():
            return self._danger_dialogue
        return random.choice(self._after_lines if self.rescued else self._thanks_lines)

    def interact(self, player, game):
        """
        Called when the player presses F next to this victim in the
        overworld. Talk-only until combat_resolved(); the first interaction
        afterward rescues it (thanks + reward), later ones just repeat a
        generic line - same shape as PrisonerNPC.free() + give_reward().
        """
        first_rescue = self.combat_resolved() and not self.rescued
        line = self.get_dialogue()
        game.message_log.add_message(f'{self.name}: "{line}"', (200, 200, 255))

        if first_rescue:
            self.rescued = True
            game.floating_texts.append(FloatingText(self.x, self.y, "SAVED!", (100, 255, 150), y_speed=0.5))
            self._give_reward(player, game)

    def _give_reward(self, player, game):
        if self.reward_given:
            return
        self.reward_given = True

        if self.reward_gold:
            player.gold += self.reward_gold
            game.message_log.add_message(f"You receive {self.reward_gold} gold!", (255, 215, 0))

        if self.reward_item is not None:
            if player.inventory.add_item(self.reward_item):
                game.message_log.add_message(
                    f"You receive the {self.reward_item.name}!", self.reward_item.color
                )
                player.update_throw_knife_ability()
                player.update_spellbook_abilities()
                player.update_thieves_tools_ability()
                player.update_guard_ability()
                player.update_holy_symbol_abilities()
            else:
                self.reward_item.x = player.x
                self.reward_item.y = player.y
                game.game_map.items_on_ground.append(self.reward_item)
                game.message_log.add_message(
                    f"Inventory full! The {self.reward_item.name} drops to the floor.",
                    self.reward_item.color,
                )


class Trader(EncounterVictim):
    def __init__(self, x, y, char, name, color, dialogue_line):
        super().__init__(x, y, char, name, color, dialogue_line) 

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
    
                    # Give the actual item instance to the player
                    if player.inventory.add_item(item):
                        self.items_for_sale.remove(item)  # Remove the item from merchant
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


class GuardVictim(EncounterVictim):
    """
    The town guards from the "undead last stand" world encounter. Unlike a
    plain EncounterVictim, guards actually fight: each turn they close in on
    the nearest living monster and attack it with a simple d20 roll, mirroring
    the 1d20 + attack_bonus vs armor_class pattern used by Monster.attack()
    in entities/monster.py, just simplified down to a single flat damage die.
    """
    DETECTION_RANGE = 8  # Chebyshev tiles - how far a guard will notice a monster worth fighting

    def __init__(self, x, y, char, name, color, dialogue_line):
        super().__init__(x, y, char, name, color, dialogue_line)
        self.armor_class     = 14
        self.attack_bonus    = 4
        self.damage_dice     = (1, 8)   # 1d8, roughly a longsword
        self.damage_modifier = 2
        self.hp = self.max_hp = 16

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }  

    def _nearest_monster(self, game):
        from entities.monster import Monster
        nearest, nearest_dist = None, float('inf')
        for entity in game.entities:
            if not isinstance(entity, Monster) or not entity.alive:
                continue
            dist = max(abs(self.x - entity.x), abs(self.y - entity.y))
            if dist < nearest_dist:
                nearest, nearest_dist = entity, dist
        return nearest, nearest_dist

    def _attack(self, target, game):
        roll = random.randint(1, 20)
        attack_total = roll + self.attack_bonus
        game.message_log.add_message(
            f"{self.name} attacks the {target.name}! "
            f"(d20: {roll} + {self.attack_bonus} = {attack_total} vs AC {target.armor_class})",
            self.color
        )
        if attack_total >= target.armor_class:
            num_dice, die_type = self.damage_dice
            damage = sum(random.randint(1, die_type) for _ in range(num_dice)) + self.damage_modifier
            target.take_damage(damage, game)
            game.floating_texts.append(FloatingText(target.x, target.y, f"{damage}", (255, 80, 80)))
            game.floating_texts.append(FloatingText(target.x, target.y - 0.5, "HIT!", (255, 80, 80)))
        else:
            game.message_log.add_message(f"{self.name}'s attack misses.", (150, 150, 150))

            game.floating_texts.append(FloatingText(target.x, target.y, "MISS!", (200, 200, 200), y_speed=0.5))            
            

    def _move_towards(self, target, game, game_map):
        from core.pathfinding import astar
        path = astar(game_map, (self.x, self.y), (target.x, target.y),
                     entities=[e for e in game.entities if e is not self],
                     moving_entity=self, ignore_destructible=True)
        if not path or len(path) < 2:
            return

        next_x, next_y = path[1]
        occupied = any(e is not self and getattr(e, 'alive', False) and e.x == next_x and e.y == next_y
                       for e in game.entities)
        if game_map.is_walkable(next_x, next_y) and not occupied:
            self.x, self.y = next_x, next_y

    def take_turn(self, player, game_map, game):
        if not self.alive:
            return

        target, distance = self._nearest_monster(game)
        if target is None or distance > self.DETECTION_RANGE:
            return  # Nothing worth fighting nearby - stand fast, same as a plain victim

        if distance <= 1:
            self._attack(target, game)
        else:
            self._move_towards(target, game, game_map)


# Char/color/dialogue presets for each scenario's bystanders, keyed the same
# way scenarios reference them in game.py's WORLD_ENCOUNTER_SCENARIOS via
# the "victim" field. Kept here alongside the other NPC definitions so new
# victim types are added in one place. "cls" defaults to EncounterVictim -
# only "guard" uses the combat-capable GuardVictim.
ENCOUNTER_VICTIM_PRESETS = {
    "merchant": {
        "char": "td", "color": (200, 160, 80),
        "names": ["Merchant", "Trader"],
        "dialogue": "Thank the gods - help us, they're taking everything!",
        "thanks": [
            "You saved my goods and my hide! Here, take this for your trouble.",
            "Bless you, traveler! Please, take some coin for your help.",
        ],
        "after": ["Safe travels, friend - thanks again for earlier."],
        "reward_gold_range": (8, 20),
    },
    "child": {
        "char": "ch", "color": (230, 210, 180),
        "names": ["Frightened Child"],
        "dialogue": "P-please... don't let them get me...",
        "thanks": ["Y-you saved me... thank you, thank you!"],
        "after": ["The child clings close to you, still shaking."],
    },
    "sacrifice": {
        "char": "pnp", "color": (180, 180, 220),
        "names": ["Bound Figure"],
        "dialogue": "Please... cut me loose before they finish the chant...",
        "thanks": [
            "Free at last... here, take this - it's the least I can offer.",
            "I thought I was done for. Please, take this for saving me.",
        ],
        "after": ["Thank you again, adventurer. I'll not forget this."],
        "reward_pool": _PRISONER_LOOT,
    },
    "guard": {
        "char": "g", "color": (150, 170, 220),
        "names": ["Town Guard"],
        "dialogue": "We can't hold much longer - lend us a hand!",
        "thanks": ["We held the line thanks to you. Well fought, adventurer."],
        "after": ["Still catching my breath - but we're alive, thanks to you."],
        "cls": GuardVictim,
    },
}


def _make_reward_item(template, x, y):
    """
    Clones an item template into a standalone instance for handing to the
    player - same approach as PrisonerNPC._make_reward() above.
    """
    try:
        init_vars = {k: v for k, v in vars(template).items() if k not in ('owner', 'x', 'y')}
        item = template.__class__(**init_vars)
    except Exception:
        item = template.__class__(
            name=template.name,
            char=template.char,
            color=template.color,
            description=getattr(template, 'description', ''),
        )
    item.x = x
    item.y = y
    return item


def make_encounter_victims(victim_key, count, positions):
    """
    Builds `count` EncounterVictim (or GuardVictim, per preset) NPCs of the
    given preset (see ENCOUNTER_VICTIM_PRESETS) at the given (x, y) positions.
    Extra positions beyond `count` are ignored; fewer positions than `count`
    just yields fewer victims.
    """
    preset = ENCOUNTER_VICTIM_PRESETS.get(victim_key)
    if preset is None:
        return []

    victim_cls = preset.get("cls", EncounterVictim)
    reward_pool = preset.get("reward_pool")
    gold_min, gold_max = preset.get("reward_gold_range", (0, 0))

    victims = []
    for (x, y) in positions[:count]:
        name = random.choice(preset["names"])
        reward_item = _make_reward_item(random.choice(reward_pool), x, y) if reward_pool else None
        reward_gold = random.randint(gold_min, gold_max) if gold_max else 0
        victims.append(victim_cls(
            x, y, preset["char"], name, preset["color"], preset["dialogue"],
            thanks_lines=preset.get("thanks"), after_lines=preset.get("after"),
            reward_item=reward_item, reward_gold=reward_gold,
        ))
    return victims