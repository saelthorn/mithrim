import random
from items.items import torch # Ensure torch item is imported here if not already


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
        game_instance.message_log.add_message(f"{target.name}'s poison wears off.", (150, 150, 150))


class Restrained(StatusEffect):
    def __init__(self, duration, source=None):
        super().__init__("Restrained", duration, source)            


class Burning(StatusEffect):
    def __init__(self, duration, source=None, damage_per_turn=3):
        super().__init__("Burning", duration, source)
        self.damage_per_turn = damage_per_turn

    def apply_effect(self, target, game_instance):
        if self.turns_left > 0:
            game_instance.message_log.add_message(f"{target.name} is burning! Takes {self.damage_per_turn} damage.", (255, 50, 50))
            target.take_damage(self.damage_per_turn, game_instance, damage_type='fire')

            if not target.alive:
                game_instance.message_log.add_message(f"{target.name} succumed to burning to crisp!", (200, 0, 0))    

    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s burning fades away.", (150, 150, 150))
                        

class AcidBurned(StatusEffect):
    def __init__(self, duration, source=None, damage_per_turn=3):
        super().__init__("Acid Burned", duration, source)
        self.damage_per_turn = damage_per_turn
    
    def apply_effect(self, target, game_instance):
        if self.turns_left > 0:
            game_instance.message_log.add_message(f"{target.name} is burned by acid! Takes {self.damage_per_turn} damage.", (255, 165, 0))
            # NEW: Pass damage_type    
            target.take_damage(self.damage_per_turn, game_instance, damage_type='acid')
            
            if not target.alive:
                game_instance.message_log.add_message(f"{target.name} succumbed to acid burns!", (200, 0, 0))

    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s acid burns fade away.", (150, 150, 150))


class PowerAttackBuff(StatusEffect):
    def __init__(self, duration=2): # Typically lasts for 2 turn (the next attack)
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


class GuardBuff(StatusEffect):
    def __init__(self, duration=3, ac_bonus=5, source=None):
        super().__init__("Guard", duration, source)
        self.ac_bonus = ac_bonus

    def apply_effect(self, target, game_instance):
        if self.turns_left == self.duration:
            game_instance.message_log.add_message(f"{target.name} holds the shield steady, increasing AC by {self.ac_bonus}.", (100, 255, 100))

    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s guard falters.", (150, 150, 150))


class Torchlight(StatusEffect):
    def __init__(self, duration=250):
        super().__init__("Torchlight", duration)

    def apply_effect(self, target, game_instance):
        # Only log when first applied
        if self.turns_left == self.duration:
            game_instance.message_log.add_message(f"{target.name} is surrounded by the warm glow of a torch!", (255, 165, 0))

    # Torchlight status effect
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"The torchlight flickers and goes out.", (255, 100, 0))
    
        off_hand_item = target.equipped_off_hand
        if off_hand_item and off_hand_item.name.lower() == "torch":
            success = target.unequip_item(off_hand_item, game_instance, remove_from_inventory=True)
            if success:
                game_instance.message_log.add_message(f"{target.name} unequips and discards the burnt-out {off_hand_item.name}.", (150, 150, 150))
            else:
                game_instance.message_log.add_message(f"Failed to unequip and remove {off_hand_item.name}.", (255, 0, 0))
        else:
            game_instance.message_log.add_message(f"No torch equipped in off-hand to remove.", (150, 150, 150))


class ActionSurgeEffect(StatusEffect):
    def __init__(self, duration):
        super().__init__("Action Surge", duration)

    def apply_effect(self, target, game_instance):
        # This effect is purely for visual feedback.
        # The name is updated dynamically in process_status_effects.
        pass

    def on_end(self, target, game_instance):
        # The message for the end of the surge.
        game_instance.message_log.add_message("Your surge of action ends.", (255, 200, 0))


class Hidden(StatusEffect):
    def __init__(self, duration=3): # Lasts for 3 turns
        super().__init__("Cunning Action (Hide)", duration)
    
    def apply_effect(self, target, game_instance):
        pass
    
    def on_end(self, target, game_instance):
        game_instance.message_log.add_message(f"{target.name} steps out of the shadow.", (150, 150, 150))        



class BlessingOfStrength(StatusEffect):
    def __init__(self, duration=50):
        super().__init__("Blessing of Strength", duration)
        self.damage_modifier = 5
    
    def apply_effect(self, target, game_instance):
        # The damage bonus is applied dynamically during attack calculations
        pass
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message("The strength blessing fades away.", (150, 150, 150))

class BlessingOfAgility(StatusEffect):
    def __init__(self, duration=50):
        super().__init__("Blessing of Agility", duration)
        self.ac_bonus = 2

        self.damage_reduction_multiplier = 0.5 # Take half damage if hit        
    
    def apply_effect(self, target, game_instance):
        # The AC bonus is applied dynamically during attack calculations
        pass
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message("The agility blessing fades away.", (150, 150, 150))

class CurseOfWeakness(StatusEffect):
    def __init__(self, duration=50):
        super().__init__("Curse of Weakness", duration)
        self.damage_modifier = -5
    
    def apply_effect(self, target, game_instance):
        # The damage penalty is applied dynamically during attack calculations
        pass
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message("The weakness curse lifts.", (150, 150, 150))

class CurseOfBlindness(StatusEffect):
    def __init__(self, duration=50):
        super().__init__("Curse of Blindness", duration)
        self.original_vision = None
        self.original_darkvision = None
    
    def apply_effect(self, target, game_instance):
        if self.original_vision is None:  # First application
            self.original_vision = getattr(target, 'vision_radius', 4)
            self.original_darkvision = getattr(target, 'darkvision_radius', 0)
            target.vision_radius = 2
            target.darkvision_radius = 0
            game_instance.message_log.add_message("Your vision becomes blurry and dark!", (255, 0, 0))
    
    def on_end(self, target, game_instance):
        if self.original_vision is not None:
            target.vision_radius = self.original_vision
        if self.original_darkvision is not None:
            target.darkvision_radius = self.original_darkvision
        super().on_end(target, game_instance)
        game_instance.message_log.add_message("Your vision returns to normal.", (150, 150, 150))  