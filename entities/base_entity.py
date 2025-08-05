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
        self.blocks_movement = True
        self.initiative = 0

    def roll_initiative(self):
        self.initiative = random.randint(1, 20)

    def get_dialogue(self):
        """Return random dialogue line"""
        if self.dialogue:
            return random.choice(self.dialogue)
        return f"{self.name} nods at you."

    def take_turn(self, player, game_map, game):
        """NPCs generally don't take active turns in the same way as monsters.
        This method is a placeholder to prevent AttributeError."""
        pass # Do nothing for most NPCs
