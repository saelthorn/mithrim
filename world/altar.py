import random
from entities.player import Player
from core.status_effects import CurseOfWeakness, CurseOfBlindness, BlessingOfAgility, BlessingOfStrength

class Altar:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.char = 'alt'  # Greek Psi symbol for altar
        self.color = (255, 215, 0)  # Gold color
        self.name = "Mysterious Altar"
        self.description = "An ancient altar that bestows blessings or curses"
        self.activated = False
        self.effect = None
        
        # Randomly determine if this altar gives a blessing or curse
        self.is_blessing = random.random() < 0.7  # 70% chance for blessing
        
        if self.is_blessing:
            blessing_type = random.choice(["strength", "agility"])
            if blessing_type == "strength":
                self.effect = {
                    "type": "blessing", 
                    "name": "BlessingOfStrength",  # Changed to match add_status_effect
                    "display_name": "Blessing of Strength",
                    "description": "+5 Damage bonus for 150 turns",
                    "duration": 150
                }
            else:  # agility
                self.effect = {
                    "type": "blessing", 
                    "name": "BlessingOfAgility",  # Changed to match add_status_effect
                    "display_name": "Blessing of Agility",
                    "description": "+2 AC for 150 turns",
                    "duration": 150
                }
        else:
            curse_type = random.choice(["weakness", "blindness"])
            if curse_type == "weakness":
                self.effect = {
                    "type": "curse",
                    "name": "CurseOfWeakness",  # Changed to match add_status_effect
                    "display_name": "Curse of Weakness",
                    "description": "-5 Damage bonus for 150 turns",
                    "duration": 120
                }
            else:  # blindness
                self.effect = {
                    "type": "curse",
                    "name": "CurseOfBlindness",  # Changed to match add_status_effect
                    "display_name": "Curse of Blindness",
                    "description": "Vision radius reduced to 2 for 150 turns",
                    "duration": 50
                }

    def interact(self, player, game_instance):
        """Handle interaction with the altar"""
        if self.activated:
            game_instance.message_log.add_message("The altar's magic has already been spent.", (150, 150, 150))
            return 'already_used'
            
        self.activated = True
        self.color = (100, 100, 100)  # Gray out after use
        
        spent_altar_tile = game_instance.game_map.tiles [self.y][self.x]
        spent_altar_tile.destructible = True
        spent_altar_tile.name = "Spent Altar"
        spent_altar_tile.color = self.color

        if self.effect["type"] == "blessing":
            self._apply_blessing(player, game_instance)
        else:
            self._apply_curse(player, game_instance)
            
        return True

    def _apply_blessing(self, player, game_instance):
        """Apply a blessing effect to the player"""
        game_instance.message_log.add_message("You feel divine energy flow through you!", (0, 255, 0))

        if self.effect["name"] == "BlessingOfStrength":
            player.add_status_effect("BlessingOfStrength", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: +5 damage bonus for {self.effect['duration']} turns!", (0, 255, 0))

        elif self.effect["name"] == "BlessingOfAgility":
            player.add_status_effect("BlessingOfAgility", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: +2 AC for {self.effect['duration']} turns!", (0, 255, 0))

    def _apply_curse(self, player, game_instance):
        """Apply a curse effect to the player"""
        game_instance.message_log.add_message("A dark energy washes over you!", (255, 0, 0))

        if self.effect["name"] == "CurseOfWeakness":
            player.add_status_effect("CurseOfWeakness", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: -5 damage bonus for {self.effect['duration']} turns!", (255, 0, 0))

        elif self.effect["name"] == "CurseOfBlindness":
            player.add_status_effect("CurseOfBlindness", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: Vision reduced for {self.effect['duration']} turns!", (255, 0, 0))
