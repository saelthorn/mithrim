import random

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


    def take_damage(self, amount, game_instance):
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
