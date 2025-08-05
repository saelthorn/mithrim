import random
from core.inventory import Inventory
from core.status_effects import Poisoned # <--- NEW IMPORT

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
        # --- Initialize equipped item slots FIRST ---
        self.equipped_weapon = None
        self.equipped_armor = None

        self.level = 1
        self.current_xp = 0
        self.xp_to_next_level = 20
        self.alive = True

        # --- D&D 5e Ability Scores ---
        self.strength = 10
        self.dexterity = 14
        self.constitution = 130
        self.intelligence = 10
        self.wisdom = 12
        self.charisma = 8

        # --- Saving Throw Proficiencies ---
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
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp

        self.update_derived_stats() # This will calculate attack_power, attack_bonus, armor_class

        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.initiative = 0
        self.blocks_movement = True # Player blocks movement

        self.inventory = Inventory(capacity=10)
        self.inventory.owner = self

        self.active_status_effects = [] # <--- NEW: List to hold active status effects

    def get_ability_modifier(self, score):
        """Calculates the D&D 5e ability modifier from a score."""
        return (score - 10) // 2

    def get_saving_throw_bonus(self, ability_name):
        """Calculates the saving throw bonus for a given ability."""
        attribute_name = self._ability_name_map.get(ability_name.upper())
        if not attribute_name:
            raise ValueError(f"Invalid ability name for saving throw: {ability_name}")
        ability_score = getattr(self, attribute_name)
        modifier = self.get_ability_modifier(ability_score)

        if self.saving_throw_proficiencies.get(ability_name.upper(), False):
            return modifier + self.proficiency_bonus
        return modifier

    def make_saving_throw(self, ability_name, dc, game_instance):
        """
        Performs a saving throw.
        :param ability_name: The name of the ability (e.g., "DEX", "CON").
        :param dc: The Difficulty Class to beat.
        :param game_instance: The game object for message logging.
        :return: True if the save succeeds, False otherwise.
        """
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
        base_hp_at_level_1 = 10
        con_modifier = self.get_ability_modifier(self.constitution)
        return base_hp_at_level_1 + (self.level - 1) * (6 + con_modifier)

    def _calculate_ac(self):
        base_ac = 10 + self.get_ability_modifier(self.dexterity)
        if self.equipped_armor:
            base_ac += self.equipped_armor.ac_bonus
        return base_ac

    def update_derived_stats(self):
        """Recalculates combat stats based on current abilities and equipment."""
        # For now, attack_power is fixed, but could be based on STR/DEX + weapon
        self.attack_power = 8 # Base attack power
        if self.equipped_weapon:
            # Assuming weapon damage_dice is handled in Game.handle_player_attack
            # This attack_power could be a flat bonus from the weapon
            self.attack_power += self.equipped_weapon.damage_modifier

        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus
        if self.equipped_weapon:
            self.attack_bonus += self.equipped_weapon.attack_bonus

        self.armor_class = self._calculate_ac()

    def gain_xp(self, amount, game_instance=None):
        self.current_xp += amount
        while self.current_xp >= self.xp_to_next_level:
            self.level_up(game_instance)

    def take_damage(self, amount):
        damage_taken = amount
        self.hp -= damage_taken

        if self.hp <= 0:
            self.hp = 0 # Ensure HP doesn't go negative
            self.alive = False
        return damage_taken

    def heal(self, amount):
        """Heal the player for a given amount, not exceeding max_hp."""
        old_hp = self.hp
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp
        return self.hp - old_hp # Return actual amount healed

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
        self.update_derived_stats() # Recalculate stats after level up

        if game_instance:
            game_instance.message_log.add_message(f"You reached Level {self.level}!", (0, 255, 0))

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
        # This method is largely deprecated now that Game.handle_player_action handles movement/attack
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

    def use_item(self, item, game_instance):
        """Attempts to use an item from inventory."""
        if hasattr(item, 'use'):
            item.use(self, game_instance)
            self.update_derived_stats() # Update stats if item affects them (e.g., potion)
            return True
        else:
            game_instance.message_log.add_message(f"You cannot use the {item.name}.", (255, 100, 100))
            return False

    def equip_item(self, item, game_instance):
        """Attempts to equip an item from inventory."""
        from items.items import Weapon, Armor # Import locally to avoid circular dependency

        if isinstance(item, Weapon):
            if self.equipped_weapon:
                # Unequip current weapon first
                self.inventory.add_item(self.equipped_weapon)
                game_instance.message_log.add_message(f"You unequip {self.equipped_weapon.name}.", (150, 150, 150))
            self.equipped_weapon = item
            self.inventory.remove_item(item) # Remove from inventory after equipping
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            self.update_derived_stats()
            return True
        elif isinstance(item, Armor):
            if self.equipped_armor:
                # Unequip current armor first
                self.inventory.add_item(self.equipped_armor)
                game_instance.message_log.add_message(f"You unequip {self.equipped_armor.name}.", (150, 150, 150))
            self.equipped_armor = item
            self.inventory.remove_item(item) # Remove from inventory after equipping
            game_instance.message_log.add_message(f"You equip {item.name}.", (0, 255, 0))
            self.update_derived_stats()
            return True
        else:
            game_instance.message_log.add_message(f"You cannot equip the {item.name}.", (255, 100, 100))
            return False

    # --- Status Effect Management Methods ---
    def add_status_effect(self, effect, game_instance):
        """Adds a status effect to the player."""
        # Check if an effect of the same type is already active
        for existing_effect in self.active_status_effects:
            if existing_effect == effect: # Uses the __eq__ method of StatusEffect
                # If it's the same type, refresh duration or stack (for now, just refresh)
                existing_effect.turns_left = effect.duration
                game_instance.message_log.add_message(f"{self.name}'s {effect.name} effect is refreshed.", (200, 200, 255))
                return

        self.active_status_effects.append(effect)
        effect.apply(self, game_instance)

    def process_status_effects(self, game_instance):
        """Processes all active status effects on the player."""
        effects_to_remove = []
        for effect in self.active_status_effects:
            effect.tick(self, game_instance)
            if effect.turns_left <= 0:
                effects_to_remove.append(effect)

        for effect in effects_to_remove:
            self.active_status_effects.remove(effect)
            effect.remove(self, game_instance)

