import random
from core.status_effects import Poisoned, Restrained, Burning # We'll add Restrained later if needed
from core.floating_text import FloatingText
from world.tile import TrapTile


class Trap:
    def __init__(self, name, char, color, description, detection_dc, disarm_dc, damage_dice, damage_modifier, damage_type='physical'):
        self.name = name
        self.char = char # Character to display when revealed
        self.color = color # Color when revealed
        self.description = description
        self.detection_dc = detection_dc # DC to notice the trap
        self.disarm_dc = disarm_dc     # DC to disarm the trap
        self.damage_dice = damage_dice # e.g., "1d6"
        self.damage_modifier = damage_modifier
        self.damage_type = damage_type
        self.is_hidden = True # Initial state
        self.is_triggered = False
        self.is_disarmed = False

    def reveal(self, game_instance, x, y):
        """Reveals the trap to the player."""
        if self.is_hidden:
            self.is_hidden = False
            game_instance.message_log.add_message(f"You notice a {self.name} at ({x},{y})!", self.color)
            # Add floating text for "TRAP!"
            game_instance.floating_texts.append(FloatingText(x, y, "TRAP!", (255, 100, 0)))
            # The tile itself will be updated in render_map_with_fov based on is_hidden state
            print(f"DEBUG: Trap '{self.name}' at ({x},{y}) (ID: {id(self)}) revealed.") # <--- ADD THIS DEBUG PRINT
            return True
        return False

    def trigger(self, player, game_instance, x, y):
        """Activates the trap's effect on the player."""
        if self.is_triggered or self.is_disarmed:
            print(f"DEBUG: Trap '{self.name}' at ({x},{y}) (ID: {id(self)}) already triggered or disarmed. Skipping.") 
            return False # Already triggered or disarmed

        self.is_triggered = True
        game_instance.message_log.add_message(f"You trigger a {self.name}!", (255, 0, 0))
        game_instance.floating_texts.append(FloatingText(x, y, "ZAP!", (255, 0, 0))) # Generic trigger text
        print(f"DEBUG: Trap '{self.name}' at ({x},{y}) (ID: {id(self)}) triggered.") 

        game_instance.game_map.tiles[y][x] = TrapTile(self, self.char, self.color, x, y, self.name)

        # Calculate damage
        dice_count_str, die_type_str = self.damage_dice.split('d')
        num_dice = int(dice_count_str)
        die_type = int(die_type_str)
        
        damage_roll = sum(random.randint(1, die_type) for _ in range(num_dice))
        total_damage = max(1, damage_roll + self.damage_modifier)

        damage_dealt = player.take_damage(total_damage, game_instance, damage_type=self.damage_type)
        game_instance.message_log.add_message(f"The {self.name} deals {damage_dealt} {self.damage_type} damage!", (255, 50, 50))
        game_instance.floating_texts.append(FloatingText(player.x, player.y - 0.5, str(damage_dealt), (255, 0, 0)))

        if not player.alive:
            game_instance.message_log.add_message("You fall victim to the trap!", (255, 0, 0))
        
        # Trap is now "spent"
        return True

    def attempt_disarm(self, player, game_instance, x, y):
        """Attempts to disarm the trap."""
        if self.is_disarmed:
            game_instance.message_log.add_message(f"The {self.name} is already disarmed.", (150, 150, 150))
            return False
        if self.is_triggered:
            game_instance.message_log.add_message(f"The {self.name} has already been triggered and cannot be disarmed.", (150, 150, 150))
            return False

        # For now, let's use Dexterity (Thieves' Tools) check
        # You'll need to ensure player has proficiency/tools later
        dex_modifier = player.get_ability_modifier(player.dexterity)
        proficiency_bonus = player.proficiency_bonus # Assuming proficiency in Thieves' Tools
        
        # For simplicity, let's assume Rogues are proficient with Thieves' Tools
        # You'll need to add a proper proficiency check in Player class or here later
        # For now, let's just add proficiency bonus if player is a Rogue
        if player.class_name == "Rogue":
            skill_bonus = dex_modifier + proficiency_bonus
            skill_name = "Dexterity (Thieves' Tools)"
        else:
            skill_bonus = dex_modifier # No proficiency bonus for others
            skill_name = "Dexterity"

        d20_roll = random.randint(1, 20)
        disarm_check_total = d20_roll + skill_bonus

        game_instance.message_log.add_message(
            f"You attempt to disarm the {self.name} ({skill_name} DC {self.disarm_dc}): {d20_roll} + {skill_bonus} = {disarm_check_total}",
            (200, 200, 255)
        )

        if disarm_check_total >= self.disarm_dc:
            self.is_disarmed = True
            game_instance.message_log.add_message(f"You successfully disarm the {self.name}!", (0, 255, 0))
            game_instance.floating_texts.append(FloatingText(x, y, "DISARMED!", (0, 255, 0)))
            print(f"DEBUG: Trap '{self.name}' at ({x},{y}) (ID: {id(self)}) disarmed.") # <--- ADD THIS DEBUG PRINT
            return True
        else:
            game_instance.message_log.add_message(f"You fail to disarm the {self.name}!", (255, 100, 100))
            # Optional: Trigger trap on failed disarm
            if random.random() < 0.5: # 50% chance to trigger on failure
                game_instance.message_log.add_message(f"The {self.name} springs!", (255, 0, 0))
                self.trigger(player, game_instance, x, y)
            print(f"DEBUG: Trap '{self.name}' at ({x},{y}) (ID: {id(self)}) disarm failed.") # <--- ADD THIS DEBUG PRINT
            return False

# --- Specific Trap Types ---

class DartTrap(Trap):
    def __init__(self):
        super().__init__(
            name="Dart Trap",
            char="^", # Revealed graphic
            color=(150, 150, 150),
            description="A pressure plate connected to hidden dart launchers.",
            detection_dc=12,
            disarm_dc=13,
            damage_dice="1d4",
            damage_modifier=0,
            damage_type='piercing'
        )
        self.can_poison = True # Specific to Dart Trap
        self.poison_dc = 10
        self.poison_duration = 3
        self.poison_damage_per_turn = 1

    def trigger(self, player, game_instance, x, y):
        if super().trigger(player, game_instance, x, y): # Call base trigger for damage
            if self.can_poison and player.alive:
                game_instance.message_log.add_message(f"Poisoned darts strike {player.name}!", (255, 150, 0))
                if not player.make_saving_throw("CON", self.poison_dc, game_instance):
                    player.add_status_effect("Poisoned", duration=self.poison_duration, game_instance=game_instance, source=self)
                else:
                    game_instance.message_log.add_message(f"{player.name} resists the poison!", (150, 255, 150))
            return True
        return False

class SpikeTrap(Trap):
    def __init__(self):
        super().__init__(
            name="Spike Trap",
            char="^", # Revealed graphic
            color=(180, 0, 0),
            description="A hidden pit or floor section that reveals sharp spikes.",
            detection_dc=14,
            disarm_dc=14,
            damage_dice="2d6",
            damage_modifier=0,
            damage_type='piercing'
        )

class FireTrap(Trap):
    def __init__(self):
        super().__init__(
            name="Fire Trap",
            char="^", # Revealed graphic
            color=(255, 100, 0),
            description="A magical glyph or mechanism that erupts in flames.",
            detection_dc=15,
            disarm_dc=16,
            damage_dice="1d4",
            damage_modifier=0,
            damage_type='fire'
        )
        self.can_burn = True
        self.burn_dc = 16
        self.burn_duration = 3
        self.damage_per_turn = 4

    def trigger(self, player, game_instance, x, y):
        if super().trigger(player, game_instance, x, y): # Call base trigger for damage
            if self.can_burn and player.alive:
                game_instance.message_log.add_message(f"FLames erupts on {player.name}!", (255, 150, 0))
                if not player.make_saving_throw("DEX", self.burn_dc, game_instance):
                    player.add_status_effect("Burning", duration=self.burn_duration, game_instance=game_instance, source=self)
                else:
                    game_instance.message_log.add_message(f"{player.name} resists the flames!", (150, 255, 150))
            return True
        return False

