
class StatusEffect:
    def __init__(self, name, duration, source=None):
        self.name = name
        self.duration = duration
        self.turns_left = duration
        self.source = source # Who applied the effect (e.g., a monster)

    def apply_effect(self, target, game_instance):
        """Applies the effect to the target each turn."""
        pass # To be overridden by specific effects

    def tick_down(self):
        """Decrements the duration of the effect."""
        self.turns_left -= 1

    def on_end(self, target, game_instance):
        """Called when the effect ends."""
        game_instance.message_log.add_message(f"{target.name} is no longer {self.name.lower()}.", (150, 150, 150))


class Poisoned(StatusEffect):
    def __init__(self, duration, source=None, damage_per_turn=2):
        super().__init__("Poisoned", duration, source)
        self.damage_per_turn = damage_per_turn
    
    def apply_effect(self, target, game_instance):
        if self.turns_left > 0:
            game_instance.message_log.add_message(f"{target.name} is poisoned! Takes {self.damage_per_turn} damage.", (255, 0, 0))
            # NEW: Pass damage_type='poison'
            target.take_damage(self.damage_per_turn, game_instance, damage_type='poison') 
            
            if not target.alive:
                game_instance.message_log.add_message(f"{target.name} succumbed to poison!", (200, 0, 0))
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
    

class PowerAttackBuff(StatusEffect):
    def __init__(self, duration=1): # Typically lasts for 1 turn (the next attack)
        super().__init__("Power Attack Buff", duration)
        self.attack_modifier = -5 # Example: -5 to hit
        self.damage_modifier = 10 # Example: +10 to damage

    def apply_effect(self, target, game_instance):
        """This effect modifies the player's stats directly when active."""
        # The actual modification will happen in the player's attack calculation
        # This method is mostly for logging or continuous effects.
        if self.turns_left == self.duration: # Only log when first applied
            game_instance.message_log.add_message(f"{target.name} is imbued with Power Attack!", (255, 165, 0))

    def on_end(self, target, game_instance):
        """Called when the buff expires."""
        super().on_end(target, game_instance)
        # No need to revert stats here, as they are applied dynamically during attack.


class CunningActionDashBuff(StatusEffect):
    def __init__(self, duration=1): # Lasts for 1 turn (until next movement)
        super().__init__("Cunning Action (Dash)", duration)
    
    def apply_effect(self, target, game_instance):
        # Message is now handled in game.py when choice is made
        target.dash_active = True # Set player flag
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s Dash readiness fades.", (150, 150, 150))
        # Flag is cleared in player.process_status_effects


class EvasionBuff(StatusEffect):
    def __init__(self, duration=5): # Lasts for 3 turns
        super().__init__("Evasion", duration)
        self.dodge_bonus = 100 # A large number to simulate high dodge chance
                               # This will be added to the player's AC for attack rolls
        self.damage_reduction_multiplier = 0.5 # Take half damage if hit
   
    def apply_effect(self, target, game_instance):
        if self.turns_left == self.duration: # Only log when first applied
            game_instance.message_log.add_message(f"{target.name} becomes incredibly agile, ready to evade!", (100, 255, 255))
   
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s Evasion fades.", (150, 150, 150))