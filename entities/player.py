import random

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
        self.xp_to_next_level = 30
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
            "DEX": True,  # Example: Rogue/Monk/Ranger proficiency
            "CON": True,  # Example: Fighter/Sorcerer proficiency
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

        # --- Derived Stats ---
        self.proficiency_bonus = 2 
        self.max_hp = self._calculate_max_hp()
        self.hp = self.max_hp 
        
        self.attack_power = 8 
        self.attack_bonus = self.get_ability_modifier(self.dexterity) + self.proficiency_bonus 
        self.armor_class = self._calculate_ac() 

        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.initiative = 0 

    def get_ability_modifier(self, score):
        return (score - 10) // 2

    def get_saving_throw_bonus(self, ability_name):
        """Calculates the saving throw bonus for a given ability."""
        # Use the map to get the correct attribute name
        attribute_name = self._ability_name_map.get(ability_name.upper())
        if not attribute_name:
            raise ValueError(f"Invalid ability name for saving throw: {ability_name}")
        ability_score = getattr(self, attribute_name) # Get the actual score (e.g., self.strength)
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
            (150, 200, 255) # Light blue for save roll
        )

        if save_total >= dc:
            game_instance.message_log.add_message(
                f"Your {ability_name} save succeeds!",
                (100, 255, 100) # Green for success
            )
            return True
        else:
            game_instance.message_log.add_message(
                f"Your {ability_name} save fails!",
                (255, 100, 100) # Red for failure
            )
            return False

    def _calculate_max_hp(self):
        base_hp_at_level_1 = 10 
        con_modifier = self.get_ability_modifier(self.constitution)
        return base_hp_at_level_1 + (self.level - 1) * (6 + con_modifier)

    def _calculate_ac(self):
        return 10 + self.get_ability_modifier(self.dexterity)

    def attack(self, target):
        return 0 

    def gain_xp(self, amount, game_instance=None): # Added game_instance parameter
        self.current_xp += amount
        while self.current_xp >= self.xp_to_next_level:
            self.level_up(game_instance) # Pass game_instance to level_up

    def take_damage(self, amount):
        damage_taken = amount 
        self.hp -= damage_taken
        
        if self.hp <= 0:
            self.alive = False
        return damage_taken
    
    def level_up(self, game_instance=None): # Added game_instance parameter
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
