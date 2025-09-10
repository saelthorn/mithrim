import random
from core.status_effects import PowerAttackBuff, EvasionBuff, BlindnessCurse

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
                    "name": "BlessingOfStrength",
                    "description": "+5 to damage bonus for 200 turns",
                    "duration": 200
                }
            else:  # agility
                self.effect = {
                    "type": "blessing", 
                    "name": "BlessingOfAgility",
                    "description": "+2 AC for 150 turns",
                    "duration": 150
                }
        else:
            curse_type = random.choice(["weakness", "blindness"])
            if curse_type == "weakness":
                self.effect = {
                    "type": "curse",
                    "name": "CurseOfWeakness",
                    "description": "-5 Damage bonus for 150 turns",
                    "duration": 150
                }
            else:  # blindness
                self.effect = {
                    "type": "curse",
                    "name": "CurseOfBlindness",
                    "description": "Vision radius reduced to 2 for 150 turns",
                    "duration": 150
                }

    def interact(self, player, game_instance):
        """Handle interaction with the altar"""
        if self.activated:
            game_instance.message_log.add_message("The altar's magic has already been spent.", (150, 150, 150))
            return False
            
        self.activated = True
        self.color = (100, 100, 100)  # Gray out after use
        
        if self.effect["type"] == "blessing":
            self._apply_blessing(player, game_instance)
        else:
            self._apply_curse(player, game_instance)
            
        return True

    def _apply_blessing(self, player, game_instance):
        """Apply a blessing effect to the player"""
        game_instance.message_log.add_message(f"You feel divine energy flow through you!", (0, 255, 0))
        
        if self.effect["name"] == "Blessing Of Strength":
            # Create a custom status effect for strength blessing
            strength_buff = PowerAttackBuff(duration=self.effect["duration"])
            strength_buff.name = "BlessingOfStrength"
            strength_buff.damage_modifier = 5  # +5 damage bonus
            strength_buff.attack_modifier = 0  # No penalty to hit
            
            player.add_status_effect(strength_buff, duration=30, game_instance=game_instance)
            game_instance.message_log.add_message(f"Blessing of Strength: +5 damage bonus for {self.effect['duration']} turns!", (0, 255, 0))
            
        elif self.effect["name"] == "Blessing Of Agility":
            # Create a custom evasion buff for AC bonus
            agility_buff = EvasionBuff(duration=self.effect["duration"])
            agility_buff.name = "BlessingOfAgility"
            agility_buff.dodge_bonus = 2  # +2 AC
            
            player.add_status_effect(agility_buff, duration=30, game_instance=game_instance)
            game_instance.message_log.add_message(f"Blessing of Agility: +2 AC for {self.effect['duration']} turns!", (0, 255, 0))

    def _apply_curse(self, player, game_instance):
        """Apply a curse effect to the player"""
        game_instance.message_log.add_message(f"A dark energy washes over you!", (255, 0, 0))
        
        if self.effect["name"] == "Curse Of Weakness":
            # Create a negative strength effect
            weakness_curse = PowerAttackBuff(duration=self.effect["duration"])
            weakness_curse.name = "CurseOfWeakness"
            weakness_curse.damage_modifier = -5  # -5 damage penalty
            weakness_curse.attack_modifier = 0
            
            player.add_status_effect(weakness_curse, duration=30, game_instance=game_instance)
            game_instance.message_log.add_message(f"Curse of Weakness: -5 damage bonus for {self.effect['duration']} turns!", (255, 0, 0))
            
        elif self.effect["name"] == "Curse Of Blindness":
            # Store original darkvision and reduce it temporarily
            original_darkvision = player.darkvision_radius
            player.darkvision_radius = 2  # Reduce to 2 tiles
            
            blindness_curse = BlindnessCurse(self.effect["duration"], original_darkvision)
            player.active_status_effects.append(blindness_curse, duration=30, game_instance=game_instance)
            game_instance.message_log.add_message(f"Curse of Blindness: Vision reduced to 2 tiles for {self.effect['duration']} turns!", (255, 0, 0))

