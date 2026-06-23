import random
from core. game import GameState
from core.inventory import Inventory

# ── D&D 5e XP Progression Table ────────────────────────────────────────────
XP_PROGRESSION = {
    1: 0,
    2: 300,
    3: 900,
    4: 2700,
    5: 6500,
    6: 14000,
    7: 23000,
    8: 34000,
    9: 48000,
    10: 64000,
    11: 85000,
    12: 100000,
    13: 120000,
    14: 140000,
    15: 165000,
    16: 195000,
    17: 225000,
    18: 265000,
    19: 305000,
    20: 355000,
}

from core.abilities import (
    Parry, SecondWind, SpiritualWeapon, DivineStrike, HealingWord, SummonCelestial, PowerAttack, CunningActionDash, 
    Evasion, FireBolt, MistyStep, SpotTrapsAbility, DisarmTrapsAbility, DetectMagic, MageHand, Fireball, RayOfFrost, 
    ActionSurge, CunningActionHide, ThrowKnife, Guard, SummonImp, PreciseStrike, PrepTime, CureWounds, SacredFlame
)

from core.status_effects import (
    BlessingOfBloodlust, BlessingOfFortitude, CurseOfRot, ParryBuff, StatusEffect, DivineStrikeBuff, Poisoned, 
    AcidBurned, PowerAttackBuff, CunningActionDashBuff, EvasionBuff, Burning, Torchlight, ActionSurgeEffect, Hidden, 
    CurseOfWeakness, CurseOfBlindness, BlessingOfAgility, BlessingOfStrength, GuardBuff, PreciseStrikeBuff, Prepared, 
    FleetFooted, AppliedToxins, SpotTrapsEffect, DetectMagicEffect
)

from items.items import ( 
    torch, Food, Potion, holy_symbol, throwing_knife, bread, green_apple, iron_long_sword, steel_mace, 
    chainmail_armor, iron_short_sword, pole_arm, steel_long_sword, steel_battle_axe, oak_staff, padded_armor, 
    half_plate_armor, iron_dagger, silver_dagger, dragonsbane_warhammer, glass_orb, robes, lesser_healing_potion, 
    greater_healing_potion, thieves_tools, round_shield, kite_shield, tower_shield, spell_book, staff_of_magi, 
    scale_mail_armor, sturdy_quarterstaff, leather_cap, iron_helmet, steel_helmet, hood_of_shadows, great_helm, 
    mages_circlet, leather_boots, iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers,
    Item, CampfireKit, Weapon, Armor, OffHand, Accessory,
    Helmet, Boots, FocusItem, WEAPON_CATEGORIES, ARMOR_CATEGORIES, 
)

from entities.monster import Goblin, GoblinArcher, GiantRat
from core.floating_text import FloatingText
    

class Player: # This is our base class for playable characters
    _ability_name_map = {
        "STR": "strength",
        "DEX": "dexterity",
        "CON": "constitution",
        "INT": "intelligence",
        "WIS": "wisdom",
        "CHA": "charisma",
    }
    
    def __init__(self, x, y, char, name, color):
        # Core Entity Attributes (common to all entities, including player)
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.alive = True
        self.blocks_movement = True
        self.facing_right = False  # Default facing left
        self.initiative = 0
        self.gold = 50

        # Player-specific attributes
        self.level = 3
        self.current_xp = 900  # Cumulative XP (player starts at level 1)
        self.xp_to_next_level = XP_PROGRESSION.get(self.level + 1, float('inf'))  # XP needed for next level

        # --- D&D 5e Ability Scores (Base values, will be overridden by subclasses) ---
        self.strength = 10
        self.dexterity = 10
        self.constitution = 10
        self.intelligence = 10
        self.wisdom = 10
        self.charisma = 10

        # --- Race (Base value, will be overridden by subclasses) ---
        self.race = None
        self.has_darkvision = 0 
        self.damage_resistances = []

        # --- NEW: Racial Proficiencies ---
        self.skill_proficiencies = []
        self.weapon_proficiencies = [] # e.g., ["shortsword", "longsword"]
        self.armor_proficiencies = []  # e.g., ["light", "medium"]       

        # --- Class Proficiencies ---
        self.class_weapon_proficiencies = []  
        self.class_armor_proficiencies = []  
       
        # --- Saving Throw Proficiencies (Base values, will be overridden by subclasses) ---
        self.saving_throw_proficiencies = {
            "STR": False, "DEX": False, "CON": False,
            "INT": False, "WIS": False, "CHA": False,
        }
        
        # --- Class-specific attributes (to be set by subclasses) ---
        self.hit_die = 6 # Default hit die (e.g., d6 for Wizard)
        self.class_name = "Adventurer" # Default class name

        # --- Derived Stats ---
        self.proficiency_bonus = 2 # Starts at +2 for level 1
        
        # --- Weapon Proficiency Penalty ---
        self.weapon_proficiency_penalty = 0 

        # --- Initialize equipped items BEFORE calculating AC/HP ---
        self.equipped_weapon = None
        self.equipped_off_hand = None
        self.equipped_armor = None
        self.equipped_accessory1 = None
        self.equipped_accessory2 = None
        self.equipped_helmet = None
        self.equipped_boots  = None
        self.equipped_focus  = None

        self.starting_equipment = None 
        

        self.remaining_torchlight_duration = 0
        self.vision_radius = 4

        # Recalculate max HP and AC based on base stats and equipped gear
        self.max_hp = 0 
        self.hp = 0     

        self.hunger = 100  # Max hunger value
        self.hunger_decrease_rate = 1  # Hunger decreases by 1 per turn
        self.hunger_threshold = 25  # Increase threshold for hunger warnings
        self.turns_since_last_hunger_decrease = 0 

        self.spell_bonus = 0  # Bonus to spell attack rolls and save DCs
        self.attack_power = 0  # Base attack power
        self.attack_bonus = 0  

        self.armor_class = 0  
        
        self.inventory = Inventory(capacity=30)
        self.inventory.owner = self # Ensure inventory owner is set
        
        self.quick_bar = {
            'q': None,  # Slot for 'q' key
            'f': None   # Slot for 'f' key
        }


        # --- Abilities (Base abilities, subclasses will add/override) ---
        self.abilities = {} 

        # Initialize abilities scaling for level 1
        for ability in self.abilities.values():
            if hasattr(ability, 'scale_with_level'):
                ability.scale_with_level(self.level)        
        
        # --- Status Effects ---
        self.active_status_effects = []

        self.cunning_action_ready = False
        self.dash_active = False # <--- NEW: Flag for dash status      

        self.current_action_state = None  
        self.extra_turns = 0
        self.hidden_turns = 0

    def update_hunger(self, game_instance):
        """Decrease hunger every 2 turns."""
        self.turns_since_last_hunger_decrease += 1
        if self.turns_since_last_hunger_decrease >= 4:  
            if self.hunger > 0:
                self.hunger -= self.hunger_decrease_rate
            self.turns_since_last_hunger_decrease = 0  # Reset the counter

            # Auto-consume one food item when hunger drops to or below the threshold.
            if self.hunger <= self.hunger_threshold:
                food_item = next((item for item in self.inventory.items if isinstance(item, Food)), None)
                if food_item:
                    game_instance.message_log.add_message(f"{self.name} is hungry and eats {food_item.name}.", (200, 200, 100))
                    self.eat_food(food_item, game_instance)
                    return

            # Check if hunger has reached 0
            if self.hunger <= 0:
                self.hunger = 0
                hunger_death_msgs = [
                    f"{self.name} collapses, starved beyond saving...",
                    f"{self.name}'s body gives out, hunger claiming the last breath...",
                    f"Weak and withered, {self.name} falls to the ground — no strength left to rise...",
                    f"With hollow eyes and an empty stomach, {self.name} succumbs to hunger...",
                    f"The dungeon claims another victim, as {self.name} dies in silence...",
                    f"{self.name}'s life flickers out, consumed by starvation..."
                ]
                game_instance.message_log.add_message(random.choice(hunger_death_msgs), (255, 0, 0))
                self.die(game_instance)  # Call the die method and pass game_instance

    def equip_to_quick_bar(self, item, slot_key, game_instance):
        # Ensure item is in inventory before trying to equip it
        if item not in self.inventory.items:
            game_instance.message_log.add_message(f"{item.name} is not in your inventory.", (255, 100, 100))
            return False 

        # Prevent adding the same item to multiple quick bar slots
        for slot, quick_item in self.quick_bar.items():
            if quick_item is item:
                game_instance.message_log.add_message(f"{item.name} is already in a quick bar slot.", (255, 100, 100))
                return False

        # If an item is already in the slot, move it back to inventory
        prev_item = self.quick_bar.get(slot_key)
        if prev_item:
            self.inventory.add_item(prev_item)
            game_instance.message_log.add_message(f"{prev_item.name} returned to inventory.", (150, 150, 150))

        # Move the new item from inventory to the quick bar
        self.inventory.remove_item(item)
        self.quick_bar[slot_key] = item
        game_instance.message_log.add_message(f"Equipped {item.name} to Quick Bar slot '{slot_key}'.", (0, 255, 0))
        
        return True


    def use_quick_bar_item(self, slot_key, game_instance):
        item = self.quick_bar.get(slot_key)
        if item:
            # Try to use the item (consume or activate)
            if self.use_item(item, game_instance):
                # If item was consumed (Potion or Food), clear the slot
                if isinstance(item, (Potion, Food)):
                    self.quick_bar[slot_key] = None
                    game_instance.message_log.add_message(f"{item.name} consumed from Quick Bar slot '{slot_key}'.", (100, 255, 100))
                return True
            # If not consumable, try to equip it (Weapon, Armor, OffHand, Accessory)
            elif isinstance(item, (Weapon, Armor, OffHand, Accessory)):
                # Determine what is currently equipped of this type
                currently_equipped = None
                if isinstance(item, Weapon):
                    currently_equipped = self.equipped_weapon
                elif isinstance(item, Armor):
                    currently_equipped = self.equipped_armor
                elif isinstance(item, OffHand):
                    currently_equipped = self.equipped_off_hand
                elif isinstance(item, Accessory):
                    # For accessories, we need to find which slot it's in
                    if self.equipped_accessory1 == item:
                        currently_equipped = self.equipped_accessory1
                    elif self.equipped_accessory2 == item:
                        currently_equipped = self.equipped_accessory2

                if self.equip_item(item, game_instance, from_quick_bar=True):
                    # Swap the previously equipped item (if any) into the quick bar slot
                    if currently_equipped:
                        self.quick_bar[slot_key] = currently_equipped
                        game_instance.message_log.add_message(
                            f"{item.name} equipped from Quick Bar slot '{slot_key}'. {currently_equipped.name} swapped in.",
                            (100, 255, 100)
                        )
                    else:
                        self.quick_bar[slot_key] = None
                        game_instance.message_log.add_message(
                            f"{item.name} equipped from Quick Bar slot '{slot_key}'.",
                            (100, 255, 100)
                        )
                    return True
                else:
                    # equip_item handles error messages
                    return False
            else:
                # Message already handled by use_item or equip_item
                return False
        else:
            game_instance.message_log.add_message(f"Quick Bar slot '{slot_key}' is empty.", (150, 150, 150))
            return False
    

    def set_facing_direction(self, facing_right: bool):
        """Set player's facing direction."""
        self.facing_right = facing_right
   
    def eat_food(self, food_item, game_instance):
        """Consume food to restore hunger."""
        if not isinstance(food_item, Food):
            not_food_msgs = [
                "You can't eat that!",
                "That’s no meal, friend...",
                "Biting into that would be a poor idea...",
                "Your stomach recoils — that's not food!"
            ]
            game_instance.message_log.add_message(random.choice(not_food_msgs), (255, 100, 100))
            return False
    
        if self.hunger >= 100:
            not_hungry_msgs = [
                "You're not hungry right now.",
                "Your belly is already full.",
                "No room for another bite.",
                "You pat your stomach — satisfied enough for now."
            ]
            game_instance.message_log.add_message(random.choice(not_hungry_msgs), (150, 150, 150))
            return False
    
        self.hunger = min(self.hunger + food_item.healing_value, 100)  # Restore hunger, max 100
    
        eat_msgs = [
            f"{self.name} eats the {food_item.name} and feels more satiated!",
            f"{self.name} devours the {food_item.name}, easing the pangs of hunger...",
            f"{self.name} chews the {food_item.name}, strength returning bit by bit...",
            f"The taste of {food_item.name} fills {self.name}'s mouth, banishing the emptiness...",
            f"With a grateful bite, {self.name} finishes the {food_item.name} and feels renewed."
        ]
        game_instance.message_log.add_message(random.choice(eat_msgs), (0, 255, 0))
    
        self.inventory.remove_item(food_item)  # Remove food after consumption
        return True
    

    def get_ability_modifier(self, score):
        return (score - 10) // 2 # Standard D&D 5e ability modifier calculation
    
    def get_spell_modifier(self):
        """Calculate spell attack modifier and save DC based on the highest of INT, WIS, or CHA."""
        spellcasting_ability = max(
            [("INT", self.intelligence), ("WIS", self.wisdom), ("CHA", self.charisma)],
            key=lambda x: x[1]
        )[0]  # Get the ability name with the highest score

        if spellcasting_ability == "INT":
            return self.get_ability_modifier(self.intelligence)
        elif spellcasting_ability == "WIS":
            return self.get_ability_modifier(self.wisdom)
        elif spellcasting_ability == "CHA":
            return self.get_ability_modifier(self.charisma)
        else:
            return 0  # Fallback, should never happen

    def update_attack_power(self):
        """Recalculate the attack power based on the primary stat and equipped items."""
        # Base attack power from primary stat
        base_attack_power = self.get_ability_modifier(self.dexterity)
        base_spell_bonus = self.get_spell_modifier() 
    
        # Initialize attack power and attack bonus
        self.attack_power = base_attack_power
        self.attack_bonus = base_attack_power + self.proficiency_bonus  # Base attack bonus
        self.spell_bonus = base_spell_bonus 
    
        # Check if a main weapon is equipped
        if self.equipped_weapon:
            self.attack_power += self.equipped_weapon.damage_modifier  # Add weapon's damage modifier
            self.attack_bonus += self.equipped_weapon.attack_bonus  # Add weapon's attack bonus
            self.spell_bonus += self.equipped_weapon.spell_bonus  # Add weapon's spell bonus

            self.attack_bonus += self.weapon_proficiency_penalty
            self.attack_power += self.weapon_proficiency_penalty
            self.spell_bonus += self.weapon_proficiency_penalty
    
        # Check if an off-hand weapon is equipped
        if self.equipped_off_hand:
            # Off-hand weapons typically do not get the proficiency bonus
            self.attack_power += self.equipped_off_hand.damage_modifier  # Add off-hand weapon's damage modifier
            self.attack_bonus += self.equipped_off_hand.attack_bonus  # Add off-hand weapon's attack bonus
            self.spell_bonus += self.equipped_off_hand.spell_bonus  # Add off-hand weapon's spell bonus
            
            self.attack_bonus += self.weapon_proficiency_penalty
            self.attack_power += self.weapon_proficiency_penalty
            self.spell_bonus += self.weapon_proficiency_penalty

        # Add focus item spell bonus
        if self.equipped_focus:
            self.spell_bonus += self.equipped_focus.spell_bonus

        print(f"Updated Attack Power: {self.attack_power}")  # Debugging output
        print(f"Updated Attack Bonus: {self.attack_bonus}")  # Debugging output
        print(f"Updated Spell Bonus: {self.spell_bonus}")  # Debugging output


    def get_saving_throw_bonus(self, ability_name):
        attribute_name = self._ability_name_map.get(ability_name.upper())
        if not attribute_name:
            raise ValueError(f"Invalid ability name for saving throw: {ability_name}")
        ability_score = getattr(self, attribute_name)
        modifier = self.get_ability_modifier(ability_score)

        if self.saving_throw_proficiencies.get(ability_name.upper(), False):
            return modifier + self.proficiency_bonus
        return modifier

    def make_saving_throw(self, ability_name, dc, game_instance):
        d20_roll = random.randint(1, 20)
        save_bonus = self.get_saving_throw_bonus(ability_name)
        save_total = d20_roll + save_bonus
        print(f"DEBUG: {self.name} {ability_name} Save: Roll={d20_roll}, Bonus={save_bonus}, Total={save_total}, DC={dc}") # ADD THIS

        game_instance.message_log.add_message(
            f"You make a {ability_name} saving throw: {d20_roll} + {save_bonus} = {save_total} (DC {dc})",
            (150, 200, 255)
        )

        if save_total >= dc:
            game_instance.message_log.add_message(
                f"Your {ability_name} save succeeds!",
                (100, 255, 100)
            )
            return True
        else:
            game_instance.message_log.add_message(
                f"Your {ability_name} save fails!",
                (255, 100, 100)
            )
            return False

    def _calculate_max_hp(self):
        con_modifier = self.get_ability_modifier(self.constitution)
        
        # Level 1 HP
        max_hp = self.hit_die + con_modifier
        
        # HP for subsequent levels (using average roll + CON modifier)
        average_roll = (self.hit_die // 2) + 1 
        
        if self.level > 1:
            max_hp += (self.level - 1) * (average_roll + con_modifier)
            
        return max(1, max_hp) # Ensure HP is at least 1

    def _calculate_ac(self):
        """Calculate the player's armor class based on all equipped items."""
        base_ac = 10 + self.get_ability_modifier(self.dexterity)

        if self.equipped_armor:
            base_ac += self.equipped_armor.ac_bonus
        if self.equipped_off_hand:
            base_ac += self.equipped_off_hand.ac_bonus
        if self.equipped_helmet:
            base_ac += self.equipped_helmet.ac_bonus
        if self.equipped_boots:
            base_ac += self.equipped_boots.ac_bonus

        # Apply persistent proficiency penalties per slot
        base_ac += getattr(self, 'armor_penalty_helmet', 0)
        base_ac += getattr(self, 'armor_penalty_armor', 0)
        base_ac += getattr(self, 'armor_penalty_boots', 0)

        for effect in self.active_status_effects:
            if isinstance(effect, ParryBuff):
                base_ac += effect.ac_bonus
            elif isinstance(effect, GuardBuff):
                base_ac += effect.ac_bonus
            elif isinstance(effect, EvasionBuff):
                base_ac += effect.dodge_bonus
            elif isinstance(effect, FleetFooted):
                base_ac += effect.ac_bonus
            elif isinstance(effect, BlessingOfAgility):
                base_ac += effect.ac_bonus

        return base_ac


    def attack(self, target):
        return 0 

    def get_next_level_xp_threshold(self):
        """Return the total XP required to reach the next level (D&D 5e table)."""
        next_level = self.level + 1
        if next_level > 20:
            return float('inf')  # No more leveling after level 20
        return XP_PROGRESSION.get(next_level, float('inf'))

    def gain_xp(self, amount, game_instance=None):
        self.current_xp += amount
        while self.level < 20 and self.current_xp >= self.get_next_level_xp_threshold():
            self.level_up(game_instance)

    def take_damage(self, amount, game_instance, damage_type=None): 
        damage_taken = amount
        
        # NEW: Apply damage resistance
        if damage_type and damage_type in self.damage_resistances:
            original_damage = damage_taken
            damage_taken = int(damage_taken / 2) # Halve the damage
            game_instance.message_log.add_message(
                f"{self.name} resists the {damage_type} damage! ({original_damage} -> {damage_taken})",
                (100, 255, 100)
            )

        evasion_buff = None
        for effect in self.active_status_effects:
            if isinstance(effect, EvasionBuff):
                evasion_buff = effect
                break
        
        if evasion_buff:
            original_damage = damage_taken # Store original damage for logging
            damage_taken = int(damage_taken * evasion_buff.damage_reduction_multiplier)
            # Add a message for half damage
            if damage_taken < original_damage: # Only if damage was actually reduced
                game_instance.message_log.add_message(f"{self.name} evades, taking only {damage_taken} damage!", (100, 255, 100))
                
        self.hp -= damage_taken

        if self.hp <= 0:
            self.alive = False
            self.die()
        return damage_taken

    def heal(self, amount):
        old_hp = self.hp
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp
        return self.hp - old_hp

    def level_up(self, game_instance=None):
        if self.level >= 20:
            if game_instance:
                game_instance.message_log.add_message(
                    "You have reached the maximum level of 20!", (255, 215, 0)
                )
            return
        
        self.level += 1
        
        if game_instance:
            next_threshold = self.get_next_level_xp_threshold()
            if next_threshold != float('inf'):
                game_instance.message_log.add_message(
                    f"You have reached level {self.level}! ({self.current_xp}/{next_threshold} XP)",
                    (0, 255, 255)
                )
            else:
                game_instance.message_log.add_message(
                    f"You have reached level {self.level}!",
                    (0, 255, 255)
                )

        if self.level in [5, 9, 13, 17]:
            self.proficiency_bonus += 1
            if game_instance:
                game_instance.message_log.add_message(
                    f"Your proficiency bonus increased to +{self.proficiency_bonus}!",
                    (0, 255, 255)
                )

        asi_levels = [4, 8, 12, 16, 19]
        if self.level in asi_levels:
            self.dexterity += 1
            self.constitution += 1
            if game_instance:
                game_instance.message_log.add_message(
                    f"You feel stronger! Dexterity and Constitution increased!",
                    (0, 255, 255)
                )

        # Recalculate max HP based on new level/CON
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp # Heal to full on level up
        

        # Scale abilities
        for ability in self.abilities.values():
            if hasattr(ability, 'scale_with_level'):
                ability.scale_with_level(self.level)

        # --- Recalculate attack power and attack bonus after leveling up ---
        self.update_attack_power()  # Ensure attack power and bonus are updated
        
        self.armor_class = self._calculate_ac() # Recalculate AC

    def roll_initiative(self):
        self.initiative = random.randint(1, 20) + self.get_ability_modifier(self.dexterity)

    def move_in_tavern(self, dx, dy, game_map, npcs):
        new_x = self.x + dx
        new_y = self.y + dy

        for npc in npcs:
            if npc.x == new_x and npc.y == new_y and npc.alive:
                return False

        if game_map.is_walkable(new_x, new_y):
            self.x = new_x
            self.y = new_y
            return True

        return False

    def move_or_attack(self, dx, dy, game_map, entities):
        new_x = self.x + dx
        new_y = self.y + dy

        target = None
        for entity in entities:
            if entity != self and entity.alive:
                if hasattr(entity, 'occupies_tile'):
                    is_on_target = entity.occupies_tile(new_x, new_y)
                else:
                    is_on_target = (entity.x == new_x and entity.y == new_y)
                if is_on_target:
                    target = entity
                    break

        if target:
            return True
        elif game_map.is_walkable(new_x, new_y):
            # Do not move into any blocking entity's occupied tile (supports multi-tile)
            for entity in entities:
                if entity is self or not getattr(entity, 'alive', True) or not getattr(entity, 'blocks_movement', False):
                    continue
                if hasattr(entity, 'occupies_tile'):
                    if entity.occupies_tile(new_x, new_y):
                        return False
                else:
                    if getattr(entity, 'x', None) == new_x and getattr(entity, 'y', None) == new_y:
                        return False
            self.x = new_x
            self.y = new_y
            return True

        return False


    def rest(self, game_instance):
        """Handle resting mechanics and reset ability cooldowns."""
        print("Rest method called")  # Debugging statement

        # Check for enemies within 10 tiles
        for entity in game_instance.entities:
            if entity != self and entity.alive:
                distance = self.distance_to(entity.x, entity.y)
                if distance < 10:  # If any enemy is within 10 tiles
                    rest_block_msgs = [
                        "You cannot rest; enemies are too close!",
                        "Your instincts scream danger — this is no place to rest!",
                        "Shadows shift nearby... you cannot lower your guard now.",
                        "The scrape of claws echoes too near — rest must wait.",
                        "You tighten your grip on your weapon. Rest will have to wait.",
                        "The dungeon stirs with hostile presence... too risky to sleep."
                    ]
                    game_instance.message_log.add_message(random.choice(rest_block_msgs), (255, 0, 0))
                    return False


        # Check if the Campfire Kit is on the ground
        campfire_kit = next((item for item in game_instance.game_map.items_on_ground if isinstance(item, CampfireKit)), None)

        # Check if the player is adjacent to the Campfire Kit
        if campfire_kit and self.is_adjacent_to(campfire_kit):
            # Fully recover HP and remove status effects
            self.hp = self.max_hp
            for effect in list(self.active_status_effects):
                effect.on_end(self, game_instance)
            self.active_status_effects.clear()  # Remove all status effects after processing on_end
            campfire_msgs = [
                f"{self.name} rests by the campfire, the flames chasing away the dungeon's chill...",
                f"The warmth of the campfire eases {self.name}'s wounds and weary spirit...",
                f"{self.name} finds brief peace by the fire, recovering strength and clarity...",
                f"As the fire crackles, {self.name}'s body mends and their mind steadies...",
                f"The campfire glows softly, restoring {self.name} to full vigor..."
            ]
            game_instance.message_log.add_message(random.choice(campfire_msgs), (0, 255, 0))
        
            # Reset ability cooldowns
            for ability in self.abilities.values():
                ability.current_cooldown = 0  # Reset cooldown for each ability
        
            # Increase ambush chance (e.g., from 20% to 50%)
            if random.random() < 0.3:  # 30% chance for ambush
                ambush_msgs = [
                    "The fire flickers... shadows shift — an ambush!",
                    "Rustling breaks the quiet — danger approaches!",
                    "The dungeon is never safe... creatures lunge from the dark!",
                    "Eyes glint beyond the firelight — you've been found!",
                    "Your moment of respite shatters as enemies close in!"
                ]
                game_instance.message_log.add_message(random.choice(ambush_msgs), (255, 0, 0))
                self.trigger_ambush(game_instance)
                return True  # Resting was interrupted by ambush
        else:
            need_fire_msgs = [
                "You must be near a campfire to safely rest.",
                "The dungeon’s chill forbids rest without firelight.",
                "A campfire’s warmth is needed before you can settle down.",
                "You can’t rest here — too dark, too cold, too dangerous.",
                "Without a campfire, rest slips beyond reach..."
            ]
            game_instance.message_log.add_message(random.choice(need_fire_msgs), (255, 0, 0))
            return False  # Cannot rest if not adjacent to a campfire
        

        return True  # Indicate successful resting


    def trigger_ambush(self, game_instance):
        """Spawn enemies for an ambush."""
        num_enemies = random.randint(1, 3)  # Spawn 1 to 3 enemies
    
        player_x, player_y = self.x, self.y
    
        spawned_enemies = []

        ambush_text = FloatingText(self.x, self.y, "AMBUSH!", (180, 0, 0))
        game_instance.floating_texts.append(ambush_text)   

        # Spawn enemies 5 tiles away from the player
        for _ in range(num_enemies):
            # Attempt to find a valid spawn position
            for _ in range(10):  # Retry up to 10 times to find a valid position
                # Randomly choose a direction to spawn the enemy
                direction = random.choice([(0, 5), (0, -5), (5, 0), (-5, 0), (3, 3), (3, -3), (-3, 3), (-3, -3)])
                enemy_x = player_x + direction[0]
                enemy_y = player_y + direction[1]
    
                # Ensure the spawn position is within the map bounds and walkable
                if 0 <= enemy_x < game_instance.game_map.width and 0 <= enemy_y < game_instance.game_map.height:
                    if game_instance.game_map.is_walkable(enemy_x, enemy_y):
                        # Create a random enemy (for example, a Goblin)
                        enemy = random.choice([Goblin, GoblinArcher, GiantRat])  # Add more enemy types as needed
                        spawned_enemy = enemy(enemy_x, enemy_y)  # Instantiate the enemy
                        game_instance.entities.append(spawned_enemy)  # Add to the game entities
                        spawned_enemies.append(spawned_enemy)  # Add to the list of spawned enemies
                        game_instance.message_log.add_message(f"A {spawned_enemy.name} appears from the shadows!", (255, 150, 0))
                        break  # Exit the retry loop once a valid position is found
            else:
                # If no valid position was found after 10 attempts, log a message
                game_instance.message_log.add_message("DEBUG: Could not find a valid spawn position for an enemy.", (255, 0, 0))
    
        # Update the turn order to include the new enemies
        game_instance.turn_order.extend(spawned_enemies)  # Add all spawned enemies to the turn order
        game_instance.turn_order = sorted(game_instance.turn_order, key=lambda e: e.initiative, reverse=True)  # Sort by initiative


    def die(self, game_instance=None):
        """
        Handles the player's death.
        Sets alive to False and logs a death message.
        """
        self.alive = False
        if game_instance:
            game_instance.message_log.add_message(f"{self.name} has fallen!", (255, 0, 0))
        print(f"{self.name} has died.") # For console debugging 


    def is_adjacent_to(self, other):
        """Check adjacency (including diagonals). Supports multi-tile entities."""
        # If other has a footprint, compute min Chebyshev distance to its occupied rectangle
        footprint_size = getattr(other, 'footprint_size', 1)
        if footprint_size > 1:
            left = other.x
            right = other.x + footprint_size - 1
            top = other.y
            bottom = other.y + footprint_size - 1

            # Compute minimal dx, dy to the rectangle
            if self.x < left:
                dx = left - self.x
            elif self.x > right:
                dx = self.x - right
            else:
                dx = 0

            if self.y < top:
                dy = top - self.y
            elif self.y > bottom:
                dy = self.y - bottom
            else:
                dy = 0

            # Adjacent if Chebyshev distance == 1 (touching any edge/corner) and not overlapping
            return max(dx, dy) == 1

        # Single-tile fallback
        dx = abs(self.x - other.x)
        dy = abs(self.y - other.y)
        return dx <= 1 and dy <= 1 and (dx != 0 or dy != 0)

    def use_item(self, item, game_instance):
        from items.items import Potion, Food # Ensure Food is imported here too
        if isinstance(item, Potion):
            return item.use(self, game_instance) # Potion's use method handles removal
        elif isinstance(item, Food): # NEW: Check for Food type
            return self.eat_food(item, game_instance) # Call the new eat_food method
        
        game_instance.message_log.add_message(f"You can't use {item.name} this way.", (255, 100, 100))
        return False

    def has_thieves_tools(self):
        """Return True if the player has Thieves' Tools in inventory or equipped off-hand."""
        if self.equipped_off_hand and self.equipped_off_hand.name.lower() == "thieves' tools":
            return True
        for item in self.inventory.items:
            if getattr(item, "name", "").lower() == "thieves' tools":
                return True
        return False

    def update_thieves_tools_ability(self):
        if self.has_thieves_tools():
            self.add_scaled_ability("Spot Traps", SpotTrapsAbility())
            self.add_scaled_ability("Disarm Traps", DisarmTrapsAbility())
        else:
            self.abilities.pop("Spot Traps", None)
            self.abilities.pop("Disarm Traps", None)

    def add_scaled_ability(self, key, ability):
        self.abilities[key] = ability
        if hasattr(ability, 'scale_with_level'):
            ability.scale_with_level(self.level)

    def has_throwing_knife(self):
        """Return True if the player has a Throwing Knife in inventory or equipped off-hand."""
        if self.equipped_off_hand and self.equipped_off_hand.name.lower() == "throwing knife":
            return True
        for item in self.inventory.items:
            if getattr(item, "name", "").lower() == "throwing knife":
                return True
        return False

    def update_throw_knife_ability(self):
        if self.has_throwing_knife():
            self.add_scaled_ability("Throwing Knife", ThrowKnife())
        else:
            self.abilities.pop("Throwing Knife", None)

    def has_spell_book_equipped(self):
        return (
            self.equipped_focus is not None and
            (getattr(self.equipped_focus, 'category', None) or '').lower() == 'spellbook'
        )

    def update_spellbook_abilities(self):
        if self.class_name == "Wizard" and self.has_spell_book_equipped():
            self.add_scaled_ability("Fireball", Fireball())
            self.add_scaled_ability("Summon Imp", SummonImp())
        else:
            self.abilities.pop("Fireball", None)
            self.abilities.pop("Summon Imp", None)

    def has_shield_equipped(self):
        return (
            self.equipped_off_hand is not None and
            (getattr(self.equipped_off_hand, 'category', None) or '').lower() == 'shield'
        )

    def update_guard_ability(self):
        if self.class_name in ["Fighter", "Cleric"] and self.has_shield_equipped():
            self.add_scaled_ability("Guard", Guard())
        else:
            self.abilities.pop("Guard", None)

    def has_holy_symbol_equipped(self):
        print(f"Debug: Focus Item Check")
        return (
            self.equipped_focus is not None and 
            (getattr(self.equipped_focus, 'category', None) or '').lower() == 'holy symbol'
        ) 
    
    def update_holy_symbol_abilities(self):
        if self.class_name == "Cleric" and self.has_holy_symbol_equipped():
            self.add_scaled_ability("Summons Celestial", SummonCelestial())
            self.add_scaled_ability("Spiritual Weapon", SpiritualWeapon())
        else:
            self.abilities.pop("Summons Celestial", None)
            self.abilities.pop("Spiritual Weapon", None)

    def equip_item(self, item, game_instance, from_quick_bar=False):
        if isinstance(item, Weapon):
            # Check if the weapon is two-handed
            if item.is_two_handed:  # Assuming you have an attribute to check if it's two-handed
                # Automatically unequip the off-hand item
                if self.equipped_off_hand:
                    self.inventory.add_item(self.equipped_off_hand) 
                    game_instance.message_log.add_message(f"You unequip {self.equipped_off_hand.name}.", (150, 150, 150))
                    self.equipped_off_hand = None  # Clear the off-hand slot

                    # Recalculate AC after equipping the shield
                    self.armor_class = self._calculate_ac()  # Recalculate AC to include the shield's defense bonus

                    # Recalculate attack bonus after equipping the off-hand weapon
                    self.update_attack_power()  # Call the method to update the attack bonus                    
                    self.update_spellbook_abilities()

            # If the player is equipping a weapon, check for existing equipped weapon
            if self.equipped_weapon:
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_weapon) 
                game_instance.message_log.add_message(f"You unequip {self.equipped_weapon.name}.", (150, 150, 150))
            
            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_weapon = item
            

            standardized_weapon_name = item.name.lower().replace(" ", "")
            
            self.weapon_proficiency_penalty = 0 # Reset to 0 before checking

            # Check if the player is proficient with the weapon category
            weapon_category = None
            for category, weapons in WEAPON_CATEGORIES.items():
                if standardized_weapon_name in [w.lower().replace(" ", "") for w in weapons]:
                    weapon_category = category
                    break
                
            # Check proficiency
            if weapon_category is None:
                self.weapon_proficiency_penalty = -8  # No category found, apply penalty
                game_instance.message_log.add_message(f"You are not proficient with {item.name}. Attack rolls with it will be penalized by {self.weapon_proficiency_penalty}.", (255, 100, 100))
            else:
                if weapon_category not in self.weapon_proficiencies and weapon_category not in self.class_weapon_proficiencies:
                    self.weapon_proficiency_penalty = -8  # No category found, apply penalty
                    game_instance.message_log.add_message(f"You are not proficient with {item.name}. Attack rolls with it will be penalized by {self.weapon_proficiency_penalty}.", (255, 100, 100))
                else:
                    game_instance.message_log.add_message(f"You are proficient with {item.name}.", (100, 255, 100))

            # Recalculate attack bonus after equipping the weapon
            self.update_attack_power()  
            
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True

        elif isinstance(item, Helmet):
            if self.equipped_helmet:
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_helmet)
                game_instance.message_log.add_message(f"You unequip {self.equipped_helmet.name}.", (150, 150, 150))

            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_helmet = item

            # Check for armor proficiency based on categories
            proficiency_penalty = 0
            standardized_helmet_name = item.name.lower().replace(" ", "")

            # Check if the player is proficient with the armor category
            armor_category = None
            for category, armors in ARMOR_CATEGORIES.items():
                if standardized_helmet_name in [a.lower().replace(" ", "") for a in armors]:
                    armor_category = category
                    break
                
            # Check proficiency
            if armor_category is None:
                proficiency_penalty = -4  # No category found
                game_instance.message_log.add_message(f"You are not proficient with {item.name}. Armor rolls will be penalized by {proficiency_penalty}.", (255, 100, 100))
            else:
                if armor_category not in self.armor_proficiencies and armor_category not in self.class_armor_proficiencies:
                    proficiency_penalty = -4  # Example penalty for non-proficiency
                    game_instance.message_log.add_message(f"You are not proficient with {item.name}. Armor rolls will be penalized by {proficiency_penalty}.", (255, 100, 100))
                else:
                    game_instance.message_log.add_message(f"You are proficient with {item.name}.", (100, 255, 100))


            self.armor_penalty_helmet = proficiency_penalty
            self.armor_class = self._calculate_ac()

            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True

        elif isinstance(item, Armor):
            if self.equipped_armor:
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_armor) 
                game_instance.message_log.add_message(f"You unequip {self.equipped_armor.name}.", (150, 150, 150))

            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_armor = item

            # Check for armor proficiency based on categories
            proficiency_penalty = 0
            standardized_armor_name = item.name.lower().replace(" ", "")

            # Check if the player is proficient with the armor category
            armor_category = None
            for category, armors in ARMOR_CATEGORIES.items():
                if standardized_armor_name in [a.lower().replace(" ", "") for a in armors]:
                    armor_category = category
                    break
                
            # Check proficiency
            if armor_category is None:
                proficiency_penalty = -4  # No category found
                game_instance.message_log.add_message(f"You are not proficient with {item.name}. Armor rolls will be penalized by {proficiency_penalty}.", (255, 100, 100))
            else:
                if armor_category not in self.armor_proficiencies and armor_category not in self.class_armor_proficiencies:
                    proficiency_penalty = -4  # Example penalty for non-proficiency
                    game_instance.message_log.add_message(f"You are not proficient with {item.name}. Armor rolls will be penalized by {proficiency_penalty}.", (255, 100, 100))
                else:
                    game_instance.message_log.add_message(f"You are proficient with {item.name}.", (100, 255, 100))


            self.armor_penalty_armor = proficiency_penalty
            self.armor_class = self._calculate_ac()

            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True
        
        elif isinstance(item, Boots):
            if self.equipped_boots:
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_boots)
                game_instance.message_log.add_message(f"You unequip {self.equipped_boots.name}.", (150, 150, 150))

            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_boots = item

            # Check for armor proficiency based on categories
            proficiency_penalty = 0
            standardized_boots_name = item.name.lower().replace(" ", "")

            # Check if the player is proficient with the armor category
            armor_category = None
            for category, armors in ARMOR_CATEGORIES.items():
                if standardized_boots_name in [a.lower().replace(" ", "") for a in armors]:
                    armor_category = category
                    break
                
            # Check proficiency
            if armor_category is None:
                proficiency_penalty = -4  # No category found
                game_instance.message_log.add_message(f"You are not proficient with {item.name}. Armor rolls will be penalized by {proficiency_penalty}.", (255, 100, 100))
            else:
                if armor_category not in self.armor_proficiencies and armor_category not in self.class_armor_proficiencies:
                    proficiency_penalty = -4  # Example penalty for non-proficiency
                    game_instance.message_log.add_message(f"You are not proficient with {item.name}. Armor rolls will be penalized by {proficiency_penalty}.", (255, 100, 100))
                else:
                    game_instance.message_log.add_message(f"You are proficient with {item.name}.", (100, 255, 100))


            self.armor_penalty_boots = proficiency_penalty
            self.armor_class = self._calculate_ac()

            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True


        elif isinstance(item, OffHand):  # Handle off-hand items
            # Check if a two-handed weapon is already equipped
            if self.equipped_weapon and self.equipped_weapon.is_two_handed:
                game_instance.message_log.add_message(f"You cannot equip {item.name} while wielding a two-handed weapon.", (255, 0, 0)) 
                return False
            
            if self.equipped_off_hand:
                # If current off-hand is a torch, save remaining Torchlight duration back to torch item and remove effect
                if self.equipped_off_hand.name.lower() == "torch":
                    torchlight_effect = None
                    for effect in self.active_status_effects:
                        if effect.name == "Torchlight":
                            torchlight_effect = effect
                            break
                    if torchlight_effect:
                        self.equipped_off_hand.remaining_duration = torchlight_effect.turns_left
                        self.active_status_effects.remove(torchlight_effect)
                        game_instance.message_log.add_message(f"{self.name}'s torchlight fades but the glow lingers in the torch.", (255, 165, 0))

                # Add old off-hand item back to inventory
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_off_hand)
                game_instance.message_log.add_message(f"You unequip {self.equipped_off_hand.name}.", (150, 150, 150))

            # Remove new item from inventory and equip it
            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_off_hand = item
            game_instance.message_log.add_message(f"You equip {item.name} in your off-hand.", (0, 255, 0))

            # If new item is a torch, apply Torchlight effect with torch's stored duration
            if item.name.lower() == "torch":
                duration = getattr(item, 'remaining_duration', 2500)
                self.add_status_effect("Torchlight", duration=duration, game_instance=game_instance)
                game_instance.message_log.add_message(f"{self.name} equips a torch with {duration} turns remaining.", (255, 165, 0))

            # Recalculate AC after equipping the shield
            self.armor_class = self._calculate_ac()

            # Recalculate attack bonus after equipping the off-hand weapon
            self.update_attack_power()
            self.update_throw_knife_ability()
            self.update_spellbook_abilities()
            self.update_thieves_tools_ability()
            self.update_guard_ability()

            return True

        elif isinstance(item, Accessory):
            # Determine which accessory slot to use
            if self.equipped_accessory1 is None:
                slot = 1
                self.equipped_accessory1 = item
            elif self.equipped_accessory2 is None:
                slot = 2
                self.equipped_accessory2 = item
            else:
                game_instance.message_log.add_message("You already have two accessories equipped. Unequip one first.", (255, 100, 100))
                return False

            if not from_quick_bar:
                self.inventory.remove_item(item)
            game_instance.message_log.add_message(f"You equip {item.name} in accessory slot {slot}.", (0, 255, 0))

            # Apply accessory bonuses
            if item.ac_bonus:
                self.armor_class += item.ac_bonus
            if item.hp_bonus:
                self.max_hp += item.hp_bonus
                self.hp += item.hp_bonus  # Also heal for the bonus

            return True

        elif isinstance(item, Helmet):
            if self.equipped_helmet:
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_helmet)
                game_instance.message_log.add_message(f"You unequip {self.equipped_helmet.name}.", (150, 150, 150))
                # Remove old helmet stat bonuses
                self.intelligence += -self.equipped_helmet.intelligence_bonus
            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_helmet = item
            # Apply new helmet stat bonuses
            if item.intelligence_bonus:
                self.intelligence += item.intelligence_bonus
            self.armor_class = self._calculate_ac()
            self.update_attack_power()
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True

        elif isinstance(item, Boots):
            if self.equipped_boots:
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_boots)
                game_instance.message_log.add_message(f"You unequip {self.equipped_boots.name}.", (150, 150, 150))
                # Remove old boots stat bonuses
                if self.equipped_boots.dexterity_bonus:
                    self.dexterity -= self.equipped_boots.dexterity_bonus
            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_boots = item
            # Apply new boots stat bonuses
            if item.dexterity_bonus:
                self.dexterity += item.dexterity_bonus
            self.armor_class = self._calculate_ac()
            self.update_attack_power()
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True

        elif isinstance(item, FocusItem):
            if self.equipped_focus:
                if not from_quick_bar:
                    self.inventory.add_item(self.equipped_focus)
                game_instance.message_log.add_message(f"You unequip {self.equipped_focus.name}.", (150, 150, 150))
                # Remove old focus bonuses
                if self.equipped_focus.intelligence_bonus:
                    self.intelligence -= self.equipped_focus.intelligence_bonus
                if self.equipped_focus.wisdom_bonus:
                    self.wisdom -= self.equipped_focus.wisdom_bonus
            if not from_quick_bar:
                self.inventory.remove_item(item)
            self.equipped_focus = item
            # Apply new focus bonuses
            if item.intelligence_bonus:
                self.intelligence += item.intelligence_bonus
            if item.wisdom_bonus:
                self.wisdom += item.wisdom_bonus
            self.update_attack_power()
            self.update_holy_symbol_abilities()
            self.update_spellbook_abilities()
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True

    def unequip_item(self, item, game_instance, remove_from_inventory=False):
        if isinstance(item, Weapon):
            if self.equipped_weapon == item:
                if remove_from_inventory:
                    if self.inventory.remove_item(item):
                        game_instance.message_log.add_message(f"{item.name} removed from inventory.", (150, 150, 150))
                    else:
                        game_instance.message_log.add_message(f"Failed to remove {item.name} from inventory.", (255, 0, 0))
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
                self.equipped_weapon = None
                self.weapon_proficiency_penalty = 0
                self.update_attack_power()
                return True
    
        elif isinstance(item, OffHand):
            if self.equipped_off_hand == item:
                if remove_from_inventory:
                    if self.inventory.remove_item(item):
                        game_instance.message_log.add_message(f"{item.name} removed from inventory.", (150, 150, 150))
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
              
                # If unequipping a torch, save remaining duration and remove Torchlight effect
                if item.name.lower() == "torch":
                    torchlight_effect = None
                    for effect in self.active_status_effects:
                        if effect.name == "Torchlight":
                            torchlight_effect = effect
                            break
                    if torchlight_effect:
                        item.remaining_duration = torchlight_effect.turns_left
                        self.active_status_effects.remove(torchlight_effect)
                        game_instance.message_log.add_message(f"{self.name}'s torchlight fades but the glow lingers in the torch.", (255, 165, 0))
                self.equipped_off_hand = None
                self.armor_class = self._calculate_ac()  

                self.update_attack_power()
                self.update_throw_knife_ability()
                self.update_spellbook_abilities()
                self.update_guard_ability()
                return True

        elif isinstance(item, Armor):
            if self.equipped_armor == item:
                if remove_from_inventory:
                    if self.inventory.remove_item(item):
                        game_instance.message_log.add_message(f"{item.name} removed from inventory.", (150, 150, 150))
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
                self.equipped_armor = None
                self.armor_class = 0
                return True

        elif isinstance(item, Accessory):
            if self.equipped_accessory1 == item:
                if remove_from_inventory:
                    if self.inventory.remove_item(item):
                        game_instance.message_log.add_message(f"{item.name} removed from inventory.", (150, 150, 150))
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
                if item.ac_bonus:
                    self.armor_class -= item.ac_bonus
                if item.hp_bonus:
                    self.max_hp -= item.hp_bonus
                    if self.hp > self.max_hp:
                        self.hp = self.max_hp
                self.equipped_accessory1 = None
                return True
            elif self.equipped_accessory2 == item:
                if remove_from_inventory:
                    if self.inventory.remove_item(item):
                        game_instance.message_log.add_message(f"{item.name} removed from inventory.", (150, 150, 150))
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
                if item.ac_bonus:
                    self.armor_class -= item.ac_bonus
                if item.hp_bonus:
                    self.max_hp -= item.hp_bonus
                    if self.hp > self.max_hp:
                        self.hp = self.max_hp
                self.equipped_accessory2 = None
                self.update_holy_symbol_abilities()
                return True

        elif isinstance(item, Helmet):
            if self.equipped_helmet == item:
                if remove_from_inventory:
                    self.inventory.remove_item(item)
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
                if item.intelligence_bonus:
                    self.intelligence -= item.intelligence_bonus
                self.equipped_helmet = None
                self.armor_class = 0
                self.update_attack_power()
                return True

        elif isinstance(item, Boots):
            if self.equipped_boots == item:
                if remove_from_inventory:
                    self.inventory.remove_item(item)
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
                if item.dexterity_bonus:
                    self.dexterity -= item.dexterity_bonus
                self.equipped_boots = None
                self.armor_class = 0
                self.update_attack_power()
                return True

        elif isinstance(item, FocusItem):
            if self.equipped_focus == item:
                if remove_from_inventory:
                    self.inventory.remove_item(item)
                else:
                    self.inventory.add_item(item)
                    game_instance.message_log.add_message(f"You unequip {item.name}.", (150, 150, 150))
                if item.intelligence_bonus:
                    self.intelligence -= item.intelligence_bonus
                if item.wisdom_bonus:
                    self.wisdom -= item.wisdom_bonus
                self.equipped_focus = None
                self.update_attack_power()
                self.update_holy_symbol_abilities()
                self.update_spellbook_abilities()
                return True


    def get_equipped_items(self):
        """Returns a tuple of all equipped items."""
        return (self.equipped_weapon, self.equipped_armor, self.equipped_off_hand,
                self.equipped_accessory1, self.equipped_accessory2,
                self.equipped_helmet, self.equipped_boots, self.equipped_focus)

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        """Adds a status effect to the player."""
        new_effect = None
        
        if effect_name == "Poisoned":
            new_effect = Poisoned(duration, source)
        
        elif effect_name == "AcidBurned":
            new_effect = AcidBurned(duration, source)
        
        elif effect_name == "Burning":
            new_effect = Burning(duration, source)   
        
        elif effect_name == "CurseOfBlindness":
            new_effect = CurseOfBlindness(duration)  

        elif effect_name == "CurseOfRot":
            new_effect = CurseOfRot(duration)

        elif effect_name == "CurseOfWeakness":
            new_effect = CurseOfWeakness(duration)

        elif effect_name == "BlessingOfStrength":
            new_effect = BlessingOfStrength(duration)

        elif effect_name == "BlessingOfFortitude":
            new_effect = BlessingOfFortitude(duration)

        elif effect_name == "BlessingOfBloodlust":
            new_effect = BlessingOfBloodlust(duration)

        elif effect_name == "BlessingOfAgility":
            new_effect = BlessingOfAgility(duration)

        elif effect_name == "PowerAttackBuff":
            new_effect = PowerAttackBuff(duration)
        
        elif effect_name == "DivineStrikeBuff":
            new_effect = DivineStrikeBuff(duration)

        elif effect_name == "PreciseStrikeBuff":
            new_effect = PreciseStrikeBuff(duration)
        
        elif effect_name == "Prepared":
            new_effect = Prepared(duration)
        
        elif effect_name == "FleetFooted":
            new_effect = FleetFooted(duration)
        
        elif effect_name == "AppliedToxins":
            new_effect = AppliedToxins(duration)
        
        elif effect_name == "CunningActionDashBuff":
            new_effect = CunningActionDashBuff(duration)
        
        elif effect_name == "EvasionBuff":
            new_effect = EvasionBuff(duration)          

        elif effect_name == "Guard":
            guard_bonus = getattr(source, 'ac_bonus', 5)
            new_effect = GuardBuff(duration, ac_bonus=guard_bonus, source=source)
        
        elif effect_name == "ParryBuff":
            parry_bonus = getattr(source, 'ac_bonus', 3)
            new_effect = ParryBuff(duration, ac_bonus=parry_bonus, source=source)

        elif effect_name == "Torchlight":
            new_effect = Torchlight(duration)
        
        elif effect_name == "ActionSurgeEffect":
            new_effect = ActionSurgeEffect(duration)
        
        elif effect_name == "Hidden":
            new_effect = Hidden(duration)

        elif effect_name == "SpotTrapsEffect":
            new_effect = SpotTrapsEffect(duration)

        elif effect_name == "DetectMagicEffect":
            new_effect = DetectMagicEffect(duration)

        if new_effect:
            for existing_effect in self.active_status_effects:
                if type(existing_effect) is type(new_effect):
                    existing_effect.turns_left = new_effect.duration
                    game_instance.message_log.add_message(f"{self.name}'s {new_effect.name} effect is refreshed.", (200, 200, 255))
                    return
            self.active_status_effects.append(new_effect)
            print(f"DEBUG: {effect_name} successfully added to {self.name}.") # ADD THIS            
        else:
            game_instance.message_log.add_message(f"Warning: Attempted to add unknown status effect: {effect_name}", (255, 0, 0))
            print(f"Warning: Attempted to add unknown status effect: {effect_name}")


    def process_status_effects(self, game_instance):
        """Processes active status effects and ability cooldowns on the player."""
        effects_to_remove = []
        action_surge_effect = None
        hidden_buff = None

        for effect in self.active_status_effects:
            if isinstance(effect, ActionSurgeEffect):
                action_surge_effect = effect
            elif isinstance(effect, Hidden):
                hidden_buff = effect

            # Call apply_effect for continuous effects (like poison damage)
            effect.apply_effect(self, game_instance)
            
            # Only tick down effects that manage their own duration
            # ActionSurgeEffect and Hidden use player counters as source of truth
            if not isinstance(effect, (ActionSurgeEffect, Hidden)):
                effect.tick_down()
                if effect.turns_left <= 0:
                    effects_to_remove.append(effect)

        # Sync ActionSurgeEffect with player's extra_turns counter (source of truth)
        if action_surge_effect:
            visual_duration = self.extra_turns 
            action_surge_effect.turns_left = visual_duration
            action_surge_effect.name = f"Action Surge"

            if self.extra_turns <= 0:
                effects_to_remove.append(action_surge_effect)

        # Sync Hidden with player's hidden_turns counter (source of truth)
        if hidden_buff:
            visual_duration = self.hidden_turns 
            hidden_buff.turns_left = visual_duration
            hidden_buff.name = f"Hidden turns"

            if self.hidden_turns <= 0:
                effects_to_remove.append(hidden_buff)   

        for effect in effects_to_remove:
            self.active_status_effects.remove(effect)
            effect.on_end(self, game_instance)

            if isinstance(effect, CunningActionDashBuff):
                self.dash_active = False       

        # Recalculate armor class after any status changes that may affect defense
        self.armor_class = self._calculate_ac()

        for ability_name, ability_obj in self.abilities.items():
            ability_obj.tick_cooldown()

        # Sync torch duration with equipped torch item
        if self.equipped_off_hand and self.equipped_off_hand.name.lower() == "torch":
            torchlight_effect = None
            for effect in self.active_status_effects:
                if effect.name == "Torchlight":
                    torchlight_effect = effect
                    break
            if torchlight_effect:
                self.equipped_off_hand.remaining_duration = torchlight_effect.turns_left
            else:
                # Torchlight expired, set torch duration to 0
                self.equipped_off_hand.remaining_duration = 0            
    
    def distance_to(self, other_x, other_y):
        """Calculate the Chebyshev distance to another point."""
        dx = abs(self.x - other_x)
        dy = abs(self.y - other_y)
        return max(dx, dy) # Chebyshev distance (for grid-based movement)

    def _scale_all_abilities(self):
        """Scale all abilities based on current player level."""
        for ability in self.abilities.values():
            if hasattr(ability, 'scale_with_level'):
                ability.scale_with_level(self.level)


class Fighter(Player):
    def __init__(self, x, y, char, name, color):
        super().__init__(x, y, char, name, color)
        self.class_name = "Fighter"
        self.hit_die = 10
        
        self.strength = 15
        self.dexterity = 13
        self.constitution = 14
        self.intelligence = 8
        self.wisdom = 12
        self.charisma = 10

        self.saving_throw_proficiencies = {
            "STR": True, "CON": True,
            "DEX": False, "INT": False, 
            "WIS": False, "CHA": False,
        }

        self.primary_stat = 'strength'  # Set primary stat for Fighter        
        
        # Set starting equipment
        self.inventory.add_item(CampfireKit())  
        self.inventory.add_item(throwing_knife)
        self.inventory.add_item(bread)
        self.inventory.add_item(lesser_healing_potion)
        self.inventory.add_item(torch)

        self.equipped_weapon = iron_short_sword
        self.equipped_off_hand = round_shield
        self.equipped_helmet = iron_helmet
        self.equipped_armor = chainmail_armor
        self.equipped_boots = leather_boots
       
        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()

        # Class-specific weapon and armor proficiencies
        self.class_weapon_proficiencies = ["Battleaxe", "Handaxe", "Light Hammer", "Warhammer", "Hammer", "Shortsword", "Longsword", "Dagger", "Mace", "Flail", "Rapier", "Polearm"]
        self.class_armor_proficiencies = ["Light", "Medium", "Heavy", "Shield"]  # Fighters can wear all types of armor

        self.weapon_proficiencies = self.class_weapon_proficiencies.copy()
        self.armor_proficiencies = self.class_armor_proficiencies.copy()
       
        # Fighter's primary attack stat is Strength
        self.attack_power = self.get_ability_modifier(self.strength) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.strength) + self.proficiency_bonus + self.equipped_weapon.attack_bonus     

        # Fighter abilities
        self.abilities["Power Attack"] = PowerAttack() 
        self.abilities["Precise Strike"] = PreciseStrike()
        self.abilities["Parry"] = Parry()
        self.abilities["Second Wind"] = SecondWind()
        self.abilities["Action Surge"] = ActionSurge()
        self.update_throw_knife_ability()
        self.update_guard_ability()
        self._scale_all_abilities()  # Scale abilities after adding them


class Rogue(Player):
    def __init__(self, x, y, char, name, color):
        super().__init__(x, y, char, name, color)
        self.class_name = "Rogue"
        self.hit_die = 8

        self.strength = 8
        self.dexterity = 15
        self.constitution = 13
        self.intelligence = 12
        self.wisdom = 10
        self.charisma = 14

        self.saving_throw_proficiencies = {
            "DEX": True, "INT": True,
            "STR": False, "CON": False, 
            "WIS": False, "CHA": False,
        }

        self.primary_stat = 'dexterity'  # Set primary stat for Fighter 

        # Set starting equipment
        self.inventory.add_item(thieves_tools)
        self.inventory.add_item(bread)
        self.inventory.add_item(bread)
        self.inventory.add_item(throwing_knife)
        self.inventory.add_item(lesser_healing_potion)
        self.inventory.add_item(CampfireKit())  # Add the Campfire Kit to the player's inventory
        self.inventory.add_item(dwarven_stompers)
        self.inventory.add_item(great_helm)
        self.inventory.add_item(torch)

        self.equipped_weapon = iron_short_sword
        self.equipped_off_hand = iron_dagger
        self.equipped_helmet = leather_cap
        self.equipped_armor = padded_armor
        self.equipped_boots = leather_boots

        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()

        # Class-specific weapon and armor proficiencies
        self.class_weapon_proficiencies = ["Dagger", "Shortsword", "Rapier", "Hand Crossbow"]
        self.class_armor_proficiencies = ["Light"]  # Rogues can wear light armor
        
        self.weapon_proficiencies = self.class_weapon_proficiencies.copy()
        self.armor_proficiencies = self.class_armor_proficiencies.copy()

        # Rogue's primary attack stat is Dexterity
        self.attack_power = self.get_ability_modifier(self.dexterity) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus + self.equipped_weapon.attack_bonus

        # Rogue abilities
        self.abilities["Cunning Action"] = CunningActionDash()
        self.abilities["Evasion"] = Evasion()
        self.abilities["Cunning Action: Hide"] = CunningActionHide()
        self.abilities["Prep Time"] = PrepTime()
        self.update_throw_knife_ability()
        self.update_thieves_tools_ability()
        self._scale_all_abilities()  # Scale abilities after adding them


class Wizard(Player):
    def __init__(self, x, y, char, name, color):
        super().__init__(x, y, char, name, color)
        self.class_name = "Wizard"
        self.hit_die = 6     

        self.strength = 8
        self.dexterity = 12
        self.constitution = 13
        self.intelligence = 15
        self.wisdom = 10
        self.charisma = 10

        self.saving_throw_proficiencies = {
            "INT": True, "WIS": True,
            "STR": False, "DEX": False, 
            "CON": False, "CHA": False,
        }

        self.primary_stat = 'intelligence'  # Set primary stat for Fighter 

        # Set starting equipment
        self.inventory.add_item(bread)
        self.inventory.add_item(bread)
        self.inventory.add_item(lesser_healing_potion)
        self.inventory.add_item(CampfireKit())  # Add the Campfire Kit to the player's inventory
        self.inventory.add_item(torch)
        self.inventory.add_item(spell_book)

        self.equipped_weapon = oak_staff
        self.equipped_off_hand = glass_orb
        self.equipped_helmet = mages_circlet
        self.equipped_armor = robes
        self.equipped_boots = leather_boots
        self.equipped_focus = spell_book
        
        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        # These calculations MUST happen AFTER race traits are applied.
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()

        # Class-specific weapon and armor proficiencies
        self.class_weapon_proficiencies = ["Dagger", "Quarterstaff", "Orb"]  # Wizards typically use these
        self.class_armor_proficiencies = ["Light"]  # Wizards can wear light armor
        
        self.weapon_proficiencies = self.class_weapon_proficiencies.copy()
        self.armor_proficiencies = self.class_armor_proficiencies.copy()
        
        # Wizard's primary attack stat is Intelligence (for spells) or Dexterity (for weapons)
        # For basic weapon attacks, let's use Dexterity for now.
        # For spell attack rolls, it would be Intelligence.
        self.spell_bonus = self.get_spell_modifier() + self.proficiency_bonus
        self.attack_power = self.get_ability_modifier(self.dexterity) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus + self.equipped_weapon.attack_bonus
        
        # Wizard abilities (e.g., Spellcasting - will be complex)
        # self.abilities["spellcasting"] = Spellcasting()
        self.abilities["Fire Bolt"] = FireBolt()
        self.abilities["Ray of Frost"] = RayOfFrost()
        self.abilities["Misty Step"] = MistyStep()
        self.abilities["Mage Hand"] = MageHand()
        self.abilities["Detect Magic"] = DetectMagic()
        self.update_spellbook_abilities()
        self.update_throw_knife_ability()
        self._scale_all_abilities()  # Scale abilities after adding them

class Cleric(Player):
    def __init__(self, x, y, char, name, color):
        super().__init__(x, y, char, name, color)
        self.class_name = "Cleric"
        self.hit_die = 8

        self.strength = 14
        self.dexterity = 10
        self.constitution = 13
        self.intelligence = 12
        self.wisdom = 15
        self.charisma = 8

        self.saving_throw_proficiencies = {
            "WIS": True, "CHA": True,
            "STR": False, "DEX": False, 
            "CON": False, "INT": False,
        }

        self.primary_stat = 'wisdom'  # Set primary stat for Cleric 

        # Set starting equipment
        self.inventory.add_item(bread)
        self.inventory.add_item(bread)
        self.inventory.add_item(lesser_healing_potion)
        self.inventory.add_item(CampfireKit())  # Add the Campfire Kit to the player's inventory
        self.inventory.add_item(torch)
        self.inventory.add_item(holy_symbol)

        self.equipped_weapon = steel_mace
        self.equipped_off_hand = kite_shield
        self.equipped_helmet = leather_cap
        self.equipped_armor = scale_mail_armor
        self.equipped_boots = leather_boots
        
        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        # These calculations MUST happen
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()

        # Class-specific weapon and armor proficiencies
        self.class_weapon_proficiencies = ["Mace", "Warhammer", "Flail", "Quarterstaff", "Light Hammer"]  # Clerics typically use these
        self.class_armor_proficiencies = ["Light", "Medium", "Shield"]  # Clerics can wear light and medium armor, and use shields

        self.weapon_proficiencies = self.class_weapon_proficiencies.copy()
        self.armor_proficiencies = self.class_armor_proficiencies.copy()

        # Cleric's primary attack stat is Wisdom (for spells) or Strength (for weapons)
        # For basic weapon attacks, let's use Strength for now.
        # For spell attack rolls, it would be Wisdom.
        self.spell_bonus = self.get_spell_modifier() + self.proficiency_bonus
        self.attack_power = self.get_ability_modifier(self.strength) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.strength) + self.proficiency_bonus + self.equipped_weapon.attack_bonus

        # Cleric abilities
        self.abilities["Cure Wounds"] = CureWounds()
        self.abilities["Sacred Flame"] = SacredFlame()
        self.abilities["Healing Word"] = HealingWord()
        self.abilities["Divine Strike"] = DivineStrike()
        self.update_throw_knife_ability()
        self.update_guard_ability()
        self.update_holy_symbol_abilities()
        self._scale_all_abilities()  # Scale abilities after adding them

class Sorcerer(Player):
    def __init__(self, x, y, char, name, color):
        super().__init__(x, y, char, name, color)
        self.class_name = "Sorcerer"
        self.hit_die = 6

        self.strength = 8
        self.dexterity = 12
        self.constitution = 13
        self.intelligence = 14
        self.wisdom = 10
        self.charisma = 15

        self.saving_throw_proficiencies = {
            "CHA": True, "CON": True,
            "STR": False, "DEX": False, 
            "INT": False, "WIS": False,
        }

        self.primary_stat = 'charisma'  # Set primary stat for Sorcerer 

        # Set starting equipment
        self.inventory.add_item(bread)
        self.inventory.add_item(bread)
        self.inventory.add_item(lesser_healing_potion)
        self.inventory.add_item(CampfireKit())  # Add the Campfire Kit to the player's inventory
        self.inventory.add_item(torch)

        self.equipped_weapon = oak_staff
        self.equipped_off_hand = spell_book
        self.equipped_helmet = mages_circlet
        self.equipped_armor = robes
        self.equipped_boots = leather_boots
        
        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        # These calculations MUST happen
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()

        # Class-specific weapon and armor proficiencies
        self.class_weapon_proficiencies = ["dagger", "quarterstaff", "orb"]  # Sorcerers typically use these
        self.class_armor_proficiencies = ["light"]  # Sorcerers can wear light armor

        self.weapon_proficiencies = self.class_weapon_proficiencies.copy()
        self.armor_proficiencies = self.class_armor_proficiencies.copy()

        # Sorcerer's primary attack stat is Charisma (for spells) or Dexterity (for weapons)
        # For basic weapon attacks, let's use Dexterity for now.
        # For spell attack rolls, it would be Charisma.
        self.spell_bonus = self.get_spell_modifier() + self.proficiency_bonus
        self.attack_power = self.get_ability_modifier(self.dexterity) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus + self.equipped_weapon.attack_bonus

        # Sorcerer abilities
        self.abilities["Fire Bolt"] = FireBolt()
        self.abilities["Ray of Frost"] = RayOfFrost()
        self.abilities["Misty Step"] = MistyStep()
        self.abilities["Mage Hand"] = MageHand()
        self.abilities["Detect Magic"] = DetectMagic()