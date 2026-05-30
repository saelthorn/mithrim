import random
from items.items import torch # Ensure torch item is imported here if not already
from world.tile import MimicTile


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
    base_attack_modifier = -5
    base_damage_modifier = 10
    base_extra_damage_dice = 1

    def __init__(self, duration=2): # Typically lasts for 2 turn (the next attack)
        super().__init__("Power Attack Buff", duration)
        self.attack_modifier = self.base_attack_modifier
        self.damage_modifier = self.base_damage_modifier
        self.extra_damage_dice = self.base_extra_damage_dice

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

class DivineStrikeBuff(StatusEffect):
    base_attack_bonus_modifier = 5
    base_extra_damage_dice = 1
    base_damage_modifier = 10 

    def __init__(self, duration=2): # Typically lasts for 2 turns (the next attack)
        super().__init__("Divine Strike Buff", duration)
        self.damage_modifier = self.base_attack_bonus_modifier
        self.base_extra_damage_dice = self.base_extra_damage_dice
        self.extra_damage_dice = self.base_extra_damage_dice

    def apply_effect(self, target, game_instance):
        """This effect modifies the player's damage directly when active."""
        if self.turns_left == self.duration: # Only log when first applied
            game_instance.message_log.add_message(f"{target.name} is imbued with Divine Strike!", (255, 215, 0))

    def on_end(self, target, game_instance):
        """Called when the buff expires."""
        super().on_end(target, game_instance)
        # No need to revert stats here, as they are applied dynamically during attack.

class PreciseStrikeBuff(StatusEffect):
    base_attack_bonus_modifier = 5

    def __init__(self, duration=10): # Lasts for 10 turns
        super().__init__("Precise Strike", duration)
        self.attack_bonus_modifier = self.base_attack_bonus_modifier

    def apply_effect(self, target, game_instance):
        """This effect modifies the player's attack bonus."""
        if self.turns_left == self.duration: # Only log when first applied
            game_instance.message_log.add_message(f"{target.name} gains precise strike!", (0, 255, 255))

    def on_end(self, target, game_instance):
        """Called when the buff expires."""
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s precise strike fades.", (150, 150, 150))


class Prepared(StatusEffect):
    base_attack_power_modifier = 2

    def __init__(self, duration=10):
        super().__init__("Prepared", duration)
        self.attack_power_modifier = self.base_attack_power_modifier

    def apply_effect(self, target, game_instance):
        if self.turns_left == self.duration:
            game_instance.message_log.add_message(f"{target.name} feels prepared, their strikes are sharper!", (0, 255, 255))

    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s prepared focus fades.", (150, 150, 150))


class FleetFooted(StatusEffect):
    base_ac_bonus = 2

    def __init__(self, duration=10):
        super().__init__("FleetFooted", duration)
        self.ac_bonus = self.base_ac_bonus

    def apply_effect(self, target, game_instance):
        if self.turns_left == self.duration:
            game_instance.message_log.add_message(f"{target.name} moves with FleetFooted grace, gaining better defense!", (0, 255, 255))

    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s FleetFooted defense fades.", (150, 150, 150))


class AppliedToxins(StatusEffect):
    base_poison_die_type = 4
    base_poison_damage_dice = 1

    def __init__(self, duration=10):
        super().__init__("Applied Toxins", duration)
        self.poison_die_type = self.base_poison_die_type
        self.poison_damage_dice = self.base_poison_damage_dice

    def apply_effect(self, target, game_instance):
        if self.turns_left == self.duration:
            game_instance.message_log.add_message(f"{target.name}'s weapons are coated with applied toxins!", (0, 255, 100))

    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s toxins wear off.", (150, 150, 150))


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


class ParryBuff(StatusEffect):
    def __init__(self, duration=10, ac_bonus=3, source=None): # Lasts for 10 turns
        super().__init__("Parry", duration, source)
        self.ac_bonus = ac_bonus

    def apply_effect(self, target, game_instance):
        """This effect modifies the player's AC directly when active."""
        if self.turns_left == self.duration: # Only log when first applied
            game_instance.message_log.add_message(f"{target.name} is ready to parry incoming attacks!", (0, 255, 255))

    def on_end(self, target, game_instance):
        """Called when the buff expires."""
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s parry readiness fades.", (150, 150, 150))


class Torchlight(StatusEffect):
    def __init__(self, duration=350):
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
        target.hidden_turns = 0  # Reset hidden_turns to ensure hidden state is cleared        

class SummonedImpEffect(StatusEffect):
    def __init__(self, duration=60): # Lasts for 60 turns (1 hour)
        super().__init__("Summoned Imp", duration)
    
    def apply_effect(self, target, game_instance):
        pass
    
    def on_end(self, target, game_instance):
        game_instance.message_log.add_message(f"The summoned imp vanishes back to its plane.", (150, 150, 150))

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

class BlessingOfFortitude(StatusEffect):
    def __init__(self, duration=50):
        super().__init__("Blessing of Fortitude", duration)
        self.hp_bonus = 20
    
    def apply_effect(self, target, game_instance):
        # The HP bonus is applied dynamically during max HP calculations
        pass
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message("The fortitude blessing fades away.", (150, 150, 150))

class BlessingOfBloodlust(StatusEffect):
    def __init__(self, duration=50):
        super().__init__("Blessing of Bloodlust", duration)
        self.hp_restore_on_kill = 10 # Restores 10 HP on kill
    
    def apply_effect(self, target, game_instance):
        # The HP restoration is handled in the player's attack logic when an enemy is killed
        pass
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message("The bloodlust blessing fades away.", (150, 150, 150))

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

class CurseOfRot(StatusEffect):
    def __init__(self, duration=50):
        super().__init__("Curse of Rot", duration)
        self.damage_per_turn = 1 # Take 1 damage per turn
    
    def apply_effect(self, target, game_instance):
        if self.turns_left > 0:
            damage = self.damage_per_turn
            target.take_damage(damage, game_instance, damage_type='rot')
            game_instance.message_log.add_message(f"{target.name} takes {damage} rot damage!", (139, 69, 19))
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"The rot curse fades away.", (150, 150, 150))

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


class SpotTrapsEffect(StatusEffect):
    def __init__(self, duration=10):
        super().__init__("Spot Traps", duration)
        self.detection_radius = 4

    def apply_effect(self, target, game_instance):
        """Automatically spot traps in a 4-tile radius each turn."""
        from world.tile import TrapTile
        import random

        adjacent_traps = []
        radius = self.detection_radius
        
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue  # Skip self
                check_x = target.x + dx
                check_y = target.y + dy
                if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                    tile = game_instance.game_map.tiles[check_y][check_x]
                    if isinstance(tile, TrapTile) and tile.trap_instance.is_hidden:
                        adjacent_traps.append(tile)
        
        if adjacent_traps:
            # Perform an Intelligence (Investigation) check
            investigation_bonus = target.get_ability_modifier(target.intelligence)
            if "investigation" in target.skill_proficiencies:
                investigation_bonus += target.proficiency_bonus
            d20_roll = random.randint(1, 20)
            investigation_check_total = d20_roll + investigation_bonus
            
            found_any = False
            for trap_tile in adjacent_traps:
                if investigation_check_total >= trap_tile.trap_instance.detection_dc:
                    trap_tile.trap_instance.reveal(game_instance, trap_tile.x, trap_tile.y)

                    game_instance.message_log.add_message(f"Perception Check: Rolled {d20_roll} against {trap_tile.trap_instance.detection_dc}.", (0, 255, 255))

                    game_instance.message_log.add_message(f"You spot a hidden {trap_tile.trap_instance.name}!", (0, 255, 255))
                    found_any = True
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s trap detection fades.", (150, 150, 150))


class DetectMagicEffect(StatusEffect):
    def __init__(self, duration=10):
        super().__init__("Detect Magic", duration)
        self.detection_radius = 6

    def apply_effect(self, target, game_instance):
        """Automatically detect magical things in a 6-tile radius each turn."""
        from world.tile import TrapTile, MimicTile
        import random

        detected_items = []
        radius = self.detection_radius
        
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue  # Skip self
                check_x = target.x + dx
                check_y = target.y + dy
                if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                    tile = game_instance.game_map.tiles[check_y][check_x]
                    if isinstance(tile, TrapTile) and tile.trap_instance.is_hidden:
                        detected_items.append(tile)
                    elif isinstance(tile, MimicTile) and tile.mimic_entity.disguised:
                        detected_items.append(tile)
        
        if detected_items:
            # Perform an Intelligence (Arcana) check
            arcana_bonus = target.get_ability_modifier(target.intelligence)
            if "arcana" in target.skill_proficiencies:
                arcana_bonus += target.proficiency_bonus
            d20_roll = random.randint(1, 20)
            arcana_check_total = d20_roll + arcana_bonus

            found_any = False
            for item in detected_items:
                if isinstance(item, TrapTile):
                    detection_dc = item.trap_instance.detection_dc
                    if arcana_check_total >= detection_dc:
                        item.trap_instance.reveal(game_instance, item.x, item.y)
                        
                        game_instance.message_log.add_message(f"Arcana Check: Rolled {d20_roll} + {arcana_bonus} = {arcana_check_total} against {item.trap_instance.detection_dc} DC.", (160, 40, 160))
            
                        game_instance.message_log.add_message(f"You detect a hidden {item.trap_instance.name}!", (0, 255, 255))
                        found_any = True
                elif isinstance(item, MimicTile):
                    # Assume a fixed DC for mimics, or get from mimic_entity
                    detection_dc = 15  # Or getattr(item.mimic_entity, 'detection_dc', 15)
                    if arcana_check_total >= detection_dc:
                        item.mimic_entity.reveal(game_instance)

                        game_instance.message_log.add_message(f"Arcana Check: Rolled {d20_roll} + {arcana_bonus} = {arcana_check_total} against {item.trap_instance.detection_dc} DC.", (160, 40, 160))
                                                
                        game_instance.message_log.add_message(f"You detect a hidden mimic!", (0, 255, 255))
                        found_any = True
    
    def on_end(self, target, game_instance):
        super().on_end(target, game_instance)
        game_instance.message_log.add_message(f"{target.name}'s magical detection fades.", (150, 150, 150))

