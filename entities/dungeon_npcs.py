from entities.tavern_npcs import NPC # Reuse base NPC class

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
