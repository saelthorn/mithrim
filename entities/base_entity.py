import random

from core.status_effects import AcidBurned, Burning, Frightened, Poisoned, Restrained

class NPC:
    def __init__(self, x, y, char, name, color, dialogue=None):
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.dialogue = dialogue or []
        self.alive = True
        self.hp = 10  # Set a base HP for NPCs
        self.max_hp = 10
        self.attack_bonus = 2  # Base attack bonus for NPCs
        self.blocks_movement = True
        self.initiative = 0
        self.active_status_effects = [] 

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

    def roll_initiative(self):
        self.initiative = random.randint(1, 20)

    def get_ability_modifier(self, score):
        return (score - 10) // 2

    def get_saving_throw_bonus(self, ability_name):
        ability_name = ability_name.upper()
        ability_score = getattr(self, ability_name.lower(), 10)
        modifier = self.get_ability_modifier(ability_score)
        if self.saving_throw_proficiencies.get(ability_name, False):
            modifier += getattr(self, "proficiency_bonus", 0)
        return modifier

    def make_saving_throw(self, ability_name, dc, game_instance):
        d20_roll = random.randint(1, 20)
        save_bonus = self.get_saving_throw_bonus(ability_name)
        save_total = d20_roll + save_bonus
        game_instance.message_log.add_message(
            f"The {self.name} rolls a {ability_name} saving throw: "
            f"[{d20_roll}] + [{save_bonus}] = {save_total} vs DC {dc}",
            (255, 150, 150),
        )
        return save_total >= dc

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        effect_types = {
            "Poisoned": Poisoned,
            "AcidBurned": AcidBurned,
            "Burning": Burning,
            "Frightened": Frightened,
            "Restrained": Restrained,
        }
        effect_type = effect_types.get(effect_name)
        if effect_type is None:
            return

        effect_kwargs = {"source": source}
        if effect_name == "Restrained":
            effect_kwargs["escape_dc"] = getattr(source, "dc", 12)
        new_effect = effect_type(duration, **effect_kwargs)
        for existing_effect in self.active_status_effects:
            if type(existing_effect) is type(new_effect):
                existing_effect.turns_left = new_effect.duration
                return
        self.active_status_effects.append(new_effect)



    def take_damage(self, amount, game_instance, damage_type=None): # Added damage_type for consistency
        """Handle taking damage and return actual damage taken"""
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            game_instance.message_log.add_message(f"{self.name} has been slain!", (200, 0, 0))
            return self.die(game_instance)  # Call die method to handle XP awarding
        return amount
    
    def die(self, game_instance):
        """Handle death and return XP value"""
        xp_gained = 10  # Set a base XP for NPCs, adjust as needed
        game_instance.message_log.add_message(f"{self.name} has been defeated! You gain {xp_gained} XP.", (200, 0, 0))
        return xp_gained  # Return the XP gained

    def get_dialogue(self):
        """Return random dialogue line"""
        if self.dialogue:
            return random.choice(self.dialogue)
        return f"{self.name} nods at you."

    def take_turn(self, player, game_map, game):
        """NPCs generally don't take active turns in the same way as monsters.
        This method is a placeholder to prevent AttributeError."""
        pass # Do nothing for most NPCs

    def process_status_effects(self, game_instance):
        """Placeholder for NPCs who don't have status effects."""
        # If you ever add status effects to NPCs, this method would be implemented.
        pass 
