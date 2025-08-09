import random
from core.inventory import Inventory
from core.abilities import SecondWind, PowerAttack # <--- NEW IMPORT
from core.status_effects import StatusEffect, Poisoned # Ensure StatusEffect is imported


class Player:
    _ability_name_map = {
        "STR": "strength",
        "DEX": "dexterity",
        "CON": "constitution",
        "INT": "intelligence",
        "WIS": "wisdom",
        "CHA": "charisma",
    }
    
    def __init__(self, x, y, char, name, color):
        self.level = 1
        self.current_xp = 0
        self.xp_to_next_level = 20
        self.alive = True
       
        # --- D&D 5e Ability Scores ---
        self.strength = 10
        self.dexterity = 14
        self.constitution = 13
        self.intelligence = 10
        self.wisdom = 12
        self.charisma = 8
       
        # --- Saving Throw Proficiencies (Example: Player is proficient in DEX and CON saves) ---
        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }
       

        # --- Derived Stats ---
        self.proficiency_bonus = 2
        
        # --- Initialize equipped items BEFORE calculating AC/HP ---
        self.equipped_weapon = None
        self.equipped_armor = None
        
        self.max_hp = self._calculate_max_hp() # This calls get_ability_modifier
        self.hp = self.max_hp
        
        self.attack_power = 6
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus # This calls get_ability_modifier
        self.armor_class = self._calculate_ac() # This calls get_ability_modifier
        
        self.x = x
        self.y = y
        
        self.char = char
        self.name = name
        self.color = color
        self.initiative = 0
        
        self.inventory = Inventory(capacity=10)
        self.inventory.owner = self # Ensure inventory owner is set
        
        # --- Abilities ---
        self.abilities = {
            "second_wind": SecondWind(),
            # "power_attack": PowerAttack(), # PowerAttack needs a proper status effect system first
        }
        
        # --- Status Effects ---
        self.active_status_effects = []

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
        base_hp_at_level_1 = 12  # D&D 5e Player starts with 12 HP at level 1
        con_modifier = self.get_ability_modifier(self.constitution)
        return base_hp_at_level_1 + (self.level - 1) * (6 + con_modifier)

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

    def take_damage(self, amount):
        damage_taken = amount
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
        self.xp_to_next_level = int(self.xp_to_next_level * 1.5)

        asi_levels = [4, 8, 12, 16, 19]
        if self.level in asi_levels:
            self.dexterity += 1
            self.constitution += 1
            if game_instance:
                game_instance.message_log.add_message(
                    f"You feel stronger! Dexterity and Constitution increased!",
                    (0, 255, 255)
                )

        self.proficiency_bonus = 2 + ((self.level - 1) // 4)

        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp
        self.attack_power += 1
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus
        self.armor_class = self._calculate_ac()

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

    # --- NEW: Item Usage and Equipping ---
    def use_item(self, item, game_instance):
        """Attempts to use an item from inventory."""
        from items.items import Potion # Import here to avoid circular dependency
        if isinstance(item, Potion):
            item.use(self, game_instance)
            return True
        game_instance.message_log.add_message(f"You can't use {item.name} this way.", (255, 100, 100))
        return False

    def equip_item(self, item, game_instance):
        """Attempts to equip an item from inventory."""
        from items.items import Weapon, Armor # Import here to avoid circular dependency
        if isinstance(item, Weapon):
            if self.equipped_weapon:
                # If there's an old weapon, put it back in inventory
                self.inventory.add_item(self.equipped_weapon) 
                game_instance.message_log.add_message(f"You unequip {self.equipped_weapon.name}.", (150, 150, 150))
            
            # Remove the new item from inventory BEFORE equipping it
            self.inventory.remove_item(item) # <--- ADD THIS LINE
            
            self.equipped_weapon = item
            self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus + item.attack_bonus
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True
        elif isinstance(item, Armor):
            if self.equipped_armor:
                # If there's old armor, put it back in inventory
                self.inventory.add_item(self.equipped_armor) 
                game_instance.message_log.add_message(f"You unequip {self.equipped_armor.name}.", (150, 150, 150))
            
            # Remove the new item from inventory BEFORE equipping it
            self.inventory.remove_item(item) # <--- ADD THIS LINE
            
            self.equipped_armor = item
            self.armor_class = self._calculate_ac() # Recalculate AC
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            return True
        game_instance.message_log.add_message(f"You can't equip {item.name}.", (255, 100, 100))
        return False

    # --- NEW: Status Effect Management ---
    def add_status_effect(self, effect_name, duration, source=None):
        """Adds a status effect to the player."""
        # This is a simplified placeholder. A real system would check for duplicates,
        # apply immediate effects, etc.
        if effect_name == "Poisoned":
            new_effect = Poisoned(duration, source)
            self.active_status_effects.append(new_effect)
        # Add other effects here
        # For PowerAttack, you'd define a PowerAttackBuff class in status_effects.py
        # and add it here.


    def process_status_effects(self, game_instance):
        """Processes active status effects and ability cooldowns on the player."""
        effects_to_remove = []
        for effect in self.active_status_effects:
            effect.apply_effect(self, game_instance)
            effect.tick_down()
            if effect.turns_left <= 0:
                effects_to_remove.append(effect)
        
        for effect in effects_to_remove:
            self.active_status_effects.remove(effect)
            effect.on_end(self, game_instance)
        
        # --- NEW: Tick down ability cooldowns every time this method is called ---
        # This method is now called specifically when the player's turn ends.
        for ability_name, ability_obj in self.abilities.items():
            ability_obj.tick_cooldown()





