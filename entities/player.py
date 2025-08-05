import random
from core.inventory import Inventory
from items.items import Weapon, Armor, Potion

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
        self.xp_to_next_level = 30
        self.alive = True

        # --- D&D 5e Ability Scores ---
        self.strength = 10
        self.dexterity = 14
        self.constitution = 13
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

        # --- Derived Stats (now safe to calculate) ---
        self.proficiency_bonus = 2
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp

        # Call update_derived_stats to set initial combat stats correctly
        # This will use the newly initialized equipped_weapon/armor (which are None)
        self.update_derived_stats()

        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.initiative = 0

        self.inventory = Inventory(capacity=10)
        self.inventory.owner = self # Set the owner of the inventory

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
        # Base AC is 10 + DEX modifier
        base_ac = 10 + self.get_ability_modifier(self.dexterity)
        if self.equipped_armor:
            base_ac += self.equipped_armor.ac_bonus
        return base_ac

    def _calculate_attack_bonus(self):
        # Base attack bonus is DEX modifier + proficiency bonus
        bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus
        if self.equipped_weapon:
            bonus += self.equipped_weapon.attack_bonus
        return bonus

    def _calculate_attack_power(self):
        # Base attack power is 8, modified by equipped weapon
        power = 8 # Base value
        if self.equipped_weapon:
            # For simplicity, let's say weapon damage_modifier adds to attack_power
            # In a full D&D system, this would be more complex (damage dice, etc.)
            power += self.equipped_weapon.damage_modifier
        return power

    def update_derived_stats(self):
        """Recalculate stats that depend on equipped items or abilities."""
        self.max_hp = self._calculate_max_hp() # Max HP can change with CON
        self.armor_class = self._calculate_ac()
        self.attack_bonus = self._calculate_attack_bonus()
        self.attack_power = self._calculate_attack_power() # Update attack power based on weapon

    def attack(self, target):
        # This method seems to be a placeholder, returning 0.
        # Actual attack logic is in Game.handle_player_attack.
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
        self.attack_power += 1 # Base attack power increase
        self.update_derived_stats() # Recalculate all derived stats

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

    # --- NEW METHODS FOR ITEM MANAGEMENT ---
    def equip_item(self, item, game_instance):
        if isinstance(item, Weapon):
            if self.equipped_weapon:
                self.unequip_item(self.equipped_weapon, game_instance)
            self.equipped_weapon = item
            game_instance.message_log.add_message(f"You equip the {item.name}.", (100, 255, 100))
        elif isinstance(item, Armor):
            if self.equipped_armor:
                self.unequip_item(self.equipped_armor, game_instance)
            self.equipped_armor = item
            game_instance.message_log.add_message(f"You equip the {item.name}.", (100, 255, 100))
        else:
            game_instance.message_log.add_message(f"You cannot equip {item.name}.", (255, 100, 100))
            return False

        self.update_derived_stats() # Recalculate stats after equipping
        return True

    def unequip_item(self, item, game_instance):
        if item == self.equipped_weapon:
            self.equipped_weapon = None
            game_instance.message_log.add_message(f"You unequip the {item.name}.", (150, 150, 150))
        elif item == self.equipped_armor:
            self.equipped_armor = None
            game_instance.message_log.add_message(f"You unequip the {item.name}.", (150, 150, 150))
        else:
            game_instance.message_log.add_message(f"You don't have {item.name} equipped.", (255, 100, 100))
            return False

        self.update_derived_stats() # Recalculate stats after unequipping
        return True

    def use_item(self, item, game_instance):
        if isinstance(item, Potion):
            item.use(self, game_instance) # Potion's use method handles healing and removal
            return True
        else:
            game_instance.message_log.add_message(f"You cannot use {item.name} this way.", (255, 100, 100))
            return False
