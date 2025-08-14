import random
from core.inventory import Inventory
from core.abilities import SecondWind, PowerAttack, CunningAction, Evasion, FireBolt, MistyStep
from core.status_effects import StatusEffect, Poisoned, AcidBurned, PowerAttackBuff, CunningActionDashBuff, EvasionBuff
from items.items import long_sword, chainmail_armor, short_sword, leather_armor, dagger, robes, lesser_healing_potion, greater_healing_potion
from entities.races import Human, HillDwarf # Import the races you've defined
    

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
        self.initiative = 0

        # Player-specific attributes
        self.level = 1
        self.current_xp = 0
        self.xp_to_next_level = 20 # Base XP to level up

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
        
        # --- Initialize equipped items BEFORE calculating AC/HP ---
        self.equipped_weapon = None
        self.equipped_armor = None

        self.starting_equipment = None 
        
        # Recalculate max HP and AC based on base stats and equipped gear
        self.max_hp = 0 # Will be set by subclass
        self.hp = 0     # Will be set by subclass
        
        self.attack_power = 0 # Will be set by subclass
        self.attack_bonus = 0 # Will be set by subclass
        self.armor_class = 0  # Will be set by subclass
        
        self.inventory = Inventory(capacity=10)
        self.inventory.owner = self # Ensure inventory owner is set
        
        # --- Abilities (Base abilities, subclasses will add/override) ---
        self.abilities = {} # <--- Initialized as empty dictionary
        
        # --- Status Effects ---
        self.active_status_effects = []

        self.cunning_action_ready = False
        self.disengaged = False # <--- NEW: Flag for disengage status
        self.dash_active = False # <--- NEW: Flag for dash status      

        self.current_action_state = None  

    def get_ability_modifier(self, score):
        return (score - 10) // 2

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
        base_ac = 10 + self.get_ability_modifier(self.dexterity)
        
        if self.equipped_armor:
            base_ac += self.equipped_armor.ac_bonus
        return base_ac

    def attack(self, target):
        return 0

    def gain_xp(self, amount, game_instance=None):
        self.current_xp += amount
        while self.current_xp >= self.xp_to_next_level:
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
        return damage_taken

    def heal(self, amount):
        old_hp = self.hp
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp
        return self.hp - old_hp

    def level_up(self, game_instance=None):
        self.level += 1
        self.current_xp -= self.xp_to_next_level
        self.xp_to_next_level = int(self.xp_to_next_level * 1.5) # XP curve

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
        
        # --- NEW: Re-evaluate proficiency penalty on level up ---
        proficiency_penalty = 0
        if self.equipped_weapon:
            standardized_weapon_name = self.equipped_weapon.name.lower().replace(" ", "")
            if standardized_weapon_name not in self.weapon_proficiencies:
                proficiency_penalty = -4 # Same penalty as in equip_item
        
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus # Base attack bonus
        if self.equipped_weapon: # Add weapon's bonus if equipped
            self.attack_bonus += self.equipped_weapon.attack_bonus + proficiency_penalty # Apply penalty here
        
        # Recalculate attack_power based on primary attack stat and equipped weapon
        # This needs to be dynamic based on class's primary attack stat
        # For now, let's assume Dexterity is the primary attack stat for simplicity in base class
        # Subclasses will override this if needed.
        self.attack_power = self.get_ability_modifier(self.dexterity)
        if self.equipped_weapon:
            self.attack_power += self.equipped_weapon.damage_modifier
        
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
            if entity.x == new_x and entity.y == new_y and entity != self and entity.alive:
                target = entity
                break

        if target:
            return True
        elif game_map.is_walkable(new_x, new_y):
            self.x = new_x
            self.y = new_y
            return True

        return False

    def is_adjacent_to(self, other):
        """Check if next to another entity (cardinal directions + diagonals)"""
        dx = abs(self.x - other.x)
        dy = abs(self.y - other.y)
        return dx <= 1 and dy <= 1 and (dx != 0 or dy != 0)

    def use_item(self, item, game_instance):
        from items.items import Potion
        if isinstance(item, Potion):
            item.use(self, game_instance)
            return True
        game_instance.message_log.add_message(f"You can't use {item.name} this way.", (255, 100, 100))
        return False

    def equip_item(self, item, game_instance):
        from items.items import Weapon, Armor
        if isinstance(item, Weapon):
            if self.equipped_weapon:
                self.inventory.add_item(self.equipped_weapon) 
                game_instance.message_log.add_message(f"You unequip {self.equipped_weapon.name}.", (150, 150, 150))
            
            self.inventory.remove_item(item)
            
            self.equipped_weapon = item
            
            # --- NEW: Check for weapon proficiency ---
            proficiency_penalty = 0
            # Convert weapon name to a standardized format for proficiency check (e.g., lowercase, no spaces)
            standardized_weapon_name = item.name.lower().replace(" ", "") 
            
            # Check if the player is proficient with this specific weapon
            # For now, we'll assume proficiency names match item names (e.g., "shortsword" proficiency for "Short Sword")
            if standardized_weapon_name not in self.weapon_proficiencies:
                proficiency_penalty = -4 # Example penalty for non-proficiency
                game_instance.message_log.add_message(f"You are not proficient with {item.name}. Attack rolls with it will be penalized by {proficiency_penalty}.", (255, 100, 100))
            else:
                game_instance.message_log.add_message(f"You are proficient with {item.name}.", (100, 255, 100))
            # Recalculate attack bonus based on new weapon and proficiency
            # This should be based on the class's primary attack stat
            # For now, assuming DEX for base class, subclasses will override.
            self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus + item.attack_bonus + proficiency_penalty
            
            # Recalculate attack_power based on primary attack stat and equipped weapon
            self.attack_power = self.get_ability_modifier(self.dexterity) + item.damage_modifier
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        """Adds a status effect to the player."""
        new_effect = None
        
        if effect_name == "Poisoned":
            new_effect = Poisoned(duration, source)
        elif effect_name == "AcidBurned":
            new_effect = AcidBurned(duration, source)
        elif effect_name == "PowerAttackBuff":
            new_effect = PowerAttackBuff(duration)
        elif effect_name == "CunningActionDashBuff":
            new_effect = CunningActionDashBuff(duration)
        elif effect_name == "EvasionBuff":
            new_effect = EvasionBuff(duration)
        if new_effect:
            for existing_effect in self.active_status_effects:
                if type(existing_effect) is type(new_effect):
                    existing_effect.turns_left = new_effect.duration
                    game_instance.message_log.add_message(f"{self.name}'s {new_effect.name} effect is refreshed.", (200, 200, 255))
                    return
            self.active_status_effects.append(new_effect)
        else:
            game_instance.message_log.add_message(f"Warning: Attempted to add unknown status effect: {effect_name}", (255, 0, 0))
            print(f"Warning: Attempted to add unknown status effect: {effect_name}")


    def process_status_effects(self, game_instance):
        """Processes active status effects and ability cooldowns on the player."""
        effects_to_remove = []
        for effect in self.active_status_effects:
            # Call apply_effect for continuous effects (like poison damage)
            effect.apply_effect(self, game_instance) # <--- Ensure this is called
            
            effect.tick_down()
            if effect.turns_left <= 0:
                effects_to_remove.append(effect)
        
        for effect in effects_to_remove:
            self.active_status_effects.remove(effect)
            effect.on_end(self, game_instance)

            if isinstance(effect, CunningActionDashBuff):
                self.dash_active = False       
        
        for ability_name, ability_obj in self.abilities.items():
            ability_obj.tick_cooldown()

    def distance_to(self, other_x, other_y):
        """Calculate the Chebyshev distance to another point."""
        dx = abs(self.x - other_x)
        dy = abs(self.y - other_y)
        return max(dx, dy) # Chebyshev distance (for grid-based movement)


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
            "DEX": False, "INT": False, "WIS": False, "CHA": False,
        }
        
        # Set starting equipment
        self.equipped_weapon = long_sword
        self.equipped_armor = chainmail_armor

        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()

        # Fighter's primary attack stat is Strength
        self.attack_power = self.get_ability_modifier(self.strength) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.strength) + self.proficiency_bonus + self.equipped_weapon.attack_bonus

        # Fighter abilities
        self.abilities["second_wind"] = SecondWind()
        self.abilities["power_attack"] = PowerAttack() 


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
            "STR": False, "CON": False, "WIS": False, "CHA": False,
        }

        # Set starting equipment
        self.inventory.add_item(lesser_healing_potion)

        self.equipped_weapon = short_sword
        self.equipped_armor = leather_armor

        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()

        # Rogue's primary attack stat is Dexterity
        self.attack_power = self.get_ability_modifier(self.dexterity) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus + self.equipped_weapon.attack_bonus

        # Rogue abilities
        self.abilities["cunning_action"] = CunningAction()
        self.abilities["evasion"] = Evasion()


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
            "STR": False, "DEX": False, "CON": False, "CHA": False,
        }

        # --- NEW: Set and apply race traits ---
        # For now, hardcode Human. This will be chosen by the player later.
        self.race = HillDwarf() # Or HillDwarf() to test that race
        # Pass 'self' (the player instance) and 'game_instance' (which is not available here yet)
        # We'll need to pass game_instance from Game.__init__ to Player.__init__
        # For now, we'll apply traits in Game.__init__ after player creation.
        # This is a temporary workaround for Phase 1 simplicity.
        # The proper place for apply_traits is after player is fully initialized and game_instance is available.
        # So, we'll move the apply_traits call to Game.__init__ for now.
        
        # Set starting equipment
        self.inventory.add_item(lesser_healing_potion)
        self.inventory.add_item(greater_healing_potion)

        self.equipped_weapon = dagger
        self.equipped_armor = robes
        
        # Recalculate HP, AC, Attack Power, Attack Bonus based on new stats AND equipped gear
        # These calculations MUST happen AFTER race traits are applied.
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.armor_class = self._calculate_ac()
        
        # Wizard's primary attack stat is Intelligence (for spells) or Dexterity (for weapons)
        # For basic weapon attacks, let's use Dexterity for now.
        # For spell attack rolls, it would be Intelligence.
        self.attack_power = self.get_ability_modifier(self.dexterity) + self.equipped_weapon.damage_modifier
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus + self.equipped_weapon.attack_bonus
        
        # Wizard abilities (e.g., Spellcasting - will be complex)
        # self.abilities["spellcasting"] = Spellcasting()
        self.abilities["fire_bolt"] = FireBolt()
        self.abilities["misty_step"] = MistyStep()
