
class Race:
    def __init__(self, name, description, darkvision_radius=0, damage_resistances=None,
                 skill_proficiencies=None, weapon_proficiencies=None, armor_proficiencies=None):
        self.name = name
        self.description = description
        self.darkvision_radius = darkvision_radius
        self.damage_resistances = damage_resistances if damage_resistances is not None else [] 

        # NEW: Initialize proficiency lists
        self.skill_proficiencies = skill_proficiencies if skill_proficiencies is not None else []
        self.weapon_proficiencies = weapon_proficiencies if weapon_proficiencies is not None else []
        self.armor_proficiencies = armor_proficiencies if armor_proficiencies is not None else []

    def apply_traits(self, player_instance, game_instance):
        """
        Applies the racial traits to the player_instance.
        This method should be overridden by specific race implementations.
        """
        game_instance.message_log.add_message(
            f"Applying base traits for {self.name} to {player_instance.name}.",
            (150, 150, 255)
        )

        player_instance.darkvision_radius = self.darkvision_radius



class Human(Race):
    def __init__(self):
        super().__init__("Human", "A versatile and adaptable people, gaining +1 to all ability scores.",
                         darkvision_radius=8)

    def apply_traits(self, player_instance, game_instance):
        super().apply_traits(player_instance, game_instance) # Call base method for logging
        
        player_instance.strength += 1
        player_instance.dexterity += 1
        player_instance.constitution += 1
        player_instance.intelligence += 1
        player_instance.wisdom += 1
        player_instance.charisma += 1
        
        game_instance.message_log.add_message(
            f"{player_instance.name} gains +1 to all abilities from being Human.",
            (200, 200, 255)
        )

      
class HillDwarf(Race):
    def __init__(self):
        # NEW: Add weapon_proficiencies for HillDwarf
        super().__init__("Hill Dwarf", "Stout and hardy, with a keen intuition. +2 CON, +1 WIS, and +1 HP per level. Has Darkvision and Poison Resistance. Proficient with axes and hammers.",
                         darkvision_radius=10, damage_resistances=['poison'],
                         weapon_proficiencies=["battleaxe", "handaxe", "light hammer", "warhammer"]) # Example proficiencies

    def apply_traits(self, player_instance, game_instance):
        super().apply_traits(player_instance, game_instance)
        
        player_instance.constitution += 2
        player_instance.wisdom += 1
        player_instance.max_hp += player_instance.level
        player_instance.hp += player_instance.level
        
        game_instance.message_log.add_message(
            f"{player_instance.name} gains +2 CON, +1 WIS, and extra HP from being a Hill Dwarf.",
            (200, 200, 255)
        )
        # MODIFIED: Message for darkvision
        if self.darkvision_radius > 0:
            game_instance.message_log.add_message(
                f"{player_instance.name} gains Darkvision (range {self.darkvision_radius} tiles), allowing sight in darkness.",
                (150, 200, 255)
            )
        game_instance.message_log.add_message(
            f"{player_instance.name} gains resistance to Poison damage.",
            (150, 200, 255)
        )
        if self.weapon_proficiencies:
            game_instance.message_log.add_message(
                f"{player_instance.name} is proficient with: {', '.join(self.weapon_proficiencies)}.",
                (150, 200, 255)
            )


class DrowElf(Race):
    def __init__(self):
        super().__init__(
            "Drow Elf",
            "A dark-skinned elf with keen senses and a natural affinity for magic, often dwelling in the Underdark. Gains +2 Dexterity, +1 Charisma, and Superior Darkvision.",
            darkvision_radius=14, # Superior Darkvision (e.g., 12 tiles)
            damage_resistances=[], 
            skill_proficiencies=[], 
            weapon_proficiencies=["rapier", "shortsword", "hand crossbow"], 
            armor_proficiencies=["light"] 
        )
    def apply_traits(self, player_instance, game_instance):
        super().apply_traits(player_instance, game_instance) # Call base method for logging and applying darkvision_radius
        player_instance.dexterity += 2
        player_instance.charisma += 1
        
        game_instance.message_log.add_message(
            f"{player_instance.name} gains +2 Dexterity and +1 Charisma from being a Drow Elf.",
            (200, 200, 255)
        )
        # MODIFIED: Message for darkvision
        if self.darkvision_radius > 0:
            game_instance.message_log.add_message(
                f"{player_instance.name} gains Superior Darkvision (range {self.darkvision_radius} tiles), allowing sight in deep darkness.",
                (150, 200, 255)
            )
        if self.weapon_proficiencies:
            game_instance.message_log.add_message(
                f"{player_instance.name} is proficient with: {', '.join(self.weapon_proficiencies)}.",
                (150, 200, 255)
            )
        if self.armor_proficiencies:
            game_instance.message_log.add_message(
                f"{player_instance.name} is proficient with {', '.join(self.armor_proficiencies)} armor.",
                (150, 200, 255)
            )

