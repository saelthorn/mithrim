import random
from entities.base_entity import NPC # Reuse base NPC class
from entities.base_entity import NPC

class DungeonHealer(NPC):
    def __init__(self, x, y):
        dialogue = [
            "Rest here, adventurer. The path ahead is perilous.",
            "I can mend your wounds, for a small favor...",
            "The dungeon's darkness drains even the strongest. Take a moment."
        ]
        super().__init__(x, y, 'H', 'Healer', (0, 255, 255), dialogue) # Cyan color
    
    def offer_rest(self, player, game):
        game.message_log.add_message(f"{self.name}: You feel your wounds mend.", (0, 255, 0))
        player.hp = player.max_hp # Full heal for simplicity
        # Or implement short rest with hit dice

class Bartender(NPC):
    def __init__(self, x, y):
        dialogue = [
            "Welcome to The Prancing Pony! What can I get you?",
            "The dungeon's been acting up lately. Strange sounds at night...",
            "You look like an adventurer. The dungeon entrance is just outside.",
            "Be careful out there. Many who enter don't return.",
            "Need a drink before you face the depths?",
        ]
        super().__init__(x, y, 'A', 'Bartender', (255, 215, 0), dialogue) # <--- CHANGED 'B' to 'A'        
