import random
from entities.player import Player
from core.status_effects import CurseOfWeakness, CurseOfBlindness, BlessingOfAgility, BlessingOfStrength, BlessingOfBloodlust, CurseOfRot, BlessingOfFortitude

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
        self.alive = True  # Treat as a ground item
        
        # Blessing/curse determination moved to interact() method
        # where we can check the player's class

    def interact(self, player, game_instance):
        """Handle interaction with the altar"""
        if self.activated:
            game_instance.message_log.add_message("The altar's magic has already been spent.", (150, 150, 150))
            return 'already_used'
            
        self.activated = True
        
        spent_altar_tile = game_instance.game_map.tiles [self.y][self.x]
        #spent_altar_tile.destructible = True
        spent_altar_tile.name = "Spent Altar"
        spent_altar_tile.color = self.color

        # Determine blessing/curse based on die roll
        is_cleric = hasattr(player, 'class_name') and player.class_name == "Cleric"
        
        if is_cleric:
            # Clerics roll with advantage (2d20, take higher)
            roll1 = random.randint(1, 20)
            roll2 = random.randint(1, 20)
            final_roll = max(roll1, roll2)
            game_instance.message_log.add_message(f"You roll 2d20 with divine favor: {roll1}, {roll2} -> {final_roll}", (255, 255, 0))
        else:
            # Other classes roll normally (1d20)
            final_roll = random.randint(1, 20)
            game_instance.message_log.add_message(f"You roll a d20: {final_roll}", (255, 255, 0))
        
        # Determine blessing/curse: 11+ = blessing, 10 or less = curse
        self.is_blessing = final_roll >= 11
        
        if self.is_blessing:
            blessing_type = random.choice(["strength", "agility", "fortitude", "bloodlust"])
            if blessing_type == "strength":
                self.effect = {
                    "type": "blessing", 
                    "name": "BlessingOfStrength",
                    "display_name": "Blessing of Strength",
                    "description": "+5 Damage bonus for 150 turns",
                    "duration": 150
                }
            elif blessing_type == "fortitude":
                self.effect = {
                    "type": "blessing", 
                    "name": "BlessingOfFortitude",
                    "display_name": "Blessing of Fortitude",
                    "description": "+20 max HP for 150 turns",
                    "duration": 150
                }
            elif blessing_type == "bloodlust":
                self.effect = {
                    "type": "blessing", 
                    "name": "BlessingOfBloodlust",
                    "display_name": "Blessing of Bloodlust",
                    "description": "Killing an enemy restores small HP for 200 turns",
                    "duration": 200
                }
            else:  # agility
                self.effect = {
                    "type": "blessing", 
                    "name": "BlessingOfAgility",
                    "display_name": "Blessing of Agility",
                    "description": "+2 AC for 150 turns",
                    "duration": 150
                }
        else:
            curse_type = random.choice(["weakness", "blindness", "rot"])
            if curse_type == "weakness":
                self.effect = {
                    "type": "curse",
                    "name": "CurseOfWeakness",
                    "display_name": "Curse of Weakness",
                    "description": "-5 Damage bonus for 120 turns",
                    "duration": 120
                }
            elif curse_type == "rot":
                self.effect = {
                    "type": "curse",
                    "name": "CurseOfRot",
                    "display_name": "Curse of Rot",
                    "description": "Take damage over time for 40 turns",
                    "duration": 40
                }
            else:  # blindness
                self.effect = {
                    "type": "curse",
                    "name": "CurseOfBlindness",
                    "display_name": "Curse of Blindness",
                    "description": "Vision radius reduced to 2 for 120 turns",
                    "duration": 120
                }

        # Check for critical rolls (natural 20 or 1) - double duration
        if final_roll == 20:
            self.effect["duration"] *= 2
            game_instance.message_log.add_message("CRITICAL SUCCESS! The divine power surges, doubling the blessing's duration!", (0, 255, 0))
        elif final_roll == 1:
            self.effect["duration"] *= 2
            game_instance.message_log.add_message("CRITICAL FAILURE! The dark energy intensifies, doubling the curse's duration!", (255, 0, 0))

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

        elif self.effect["name"] == "BlessingOfFortitude":
            player.add_status_effect("BlessingOfFortitude", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: +20 max HP for {self.effect['duration']} turns!", (0, 255, 0))

        elif self.effect["name"] == "BlessingOfBloodlust":
            player.add_status_effect("BlessingOfBloodlust", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: Killing enemy restores small HP for {self.effect['duration']} turns!", (0, 255, 0))

    def _apply_curse(self, player, game_instance):
        """Apply a curse effect to the player"""
        game_instance.message_log.add_message("A dark energy washes over you!", (255, 0, 0))

        if self.effect["name"] == "CurseOfWeakness":
            player.add_status_effect("CurseOfWeakness", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: -5 damage bonus for {self.effect['duration']} turns!", (255, 0, 0))

        elif self.effect["name"] == "CurseOfRot":
            player.add_status_effect("CurseOfRot", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: Take damage over time for {self.effect['duration']} turns!", (255, 0, 0))

        elif self.effect["name"] == "CurseOfBlindness":
            player.add_status_effect("CurseOfBlindness", self.effect["duration"], game_instance=game_instance)
            game_instance.message_log.add_message(f"{self.effect['display_name']}: Vision reduced for {self.effect['duration']} turns!", (255, 0, 0))