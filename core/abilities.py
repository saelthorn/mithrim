from core.status_effects import PowerAttackBuff, EvasionBuff
from core.game import GameState


class Ability:
    def __init__(self, name, description, cost=0, cooldown=0):
        self.name = name
        self.description = description
        self.cost = cost # e.g., mana, stamina, uses per rest
        self.cooldown = cooldown # turns until usable again
        self.current_cooldown = 0

    def can_use(self, user, game_instance):
        """Checks if the user can currently use this ability."""
        if self.current_cooldown > 0:
            game_instance.message_log.add_message(f"{self.name} is on cooldown ({self.current_cooldown} turns left).", (255, 150, 0))
            return False
        # Add checks for cost (e.g., if user has enough mana/stamina) later
        return True

    def use(self, user, game_instance):
        """Abstract method to be implemented by specific abilities."""
        if not self.can_use(user, game_instance): # <--- THIS IS THE CRITICAL CHECK
            return False # <--- If cannot use, immediately return False and do nothing else
        
        # Apply cost and set cooldown (common to all abilities)
        # user.spend_resource(self.cost) # Implement this in Player class later
        self.current_cooldown = self.cooldown
        
        game_instance.message_log.add_message(f"{user.name} uses {self.name}!", (100, 255, 255))
        return True # Indicate successful use

    def tick_cooldown(self):
        """Decrements the cooldown each turn."""
        if self.current_cooldown > 0:
            self.current_cooldown -= 1

# --- Specific Abilities ---

class SecondWind(Ability):
    def __init__(self):
        super().__init__("Second Wind", "Heal yourself for a small amount of HP.", cooldown=15) # 15 turns cooldown

    def use(self, user, game_instance):
        # Call base class use to handle cooldown and initial checks.
        # If base.use returns False (because can_use failed), then this method should also return False.
        if not super().use(user, game_instance):
            return False
        
        heal_amount = user.level * 2 + 5 # Example: Heals based on level
        amount_healed = user.heal(heal_amount)
        game_instance.message_log.add_message(f"{user.name} regains {amount_healed} HP!", (0, 255, 0))
        return True # Indicate successful use


class PowerAttack(Ability):
    def __init__(self):
        super().__init__("Power Attack", "Sacrifice accuracy for increased damage on your next attack.", cooldown=3)
    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Apply the PowerAttackBuff to the user
        # Apply the PowerAttackBuff to the user using its string name
        user.add_status_effect("PowerAttackBuff", duration=3, game_instance=game_instance) # <--- MODIFIED
        game_instance.message_log.add_message(f"{user.name} prepares a powerful strike!", (255, 165, 0))
        return True

class CunningAction(Ability):
    def __init__(self):
        super().__init__("Cunning Action", "Use a bonus action to Dash.", cooldown=1)  # Removed Disengage option

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Set the player's action state to indicate a choice is pending
        user.current_action_state = "cunning_action_dash"  # Changed to only allow Dash
        game_instance.message_log.add_message(f"{user.name} prepares a Cunning Action: Dash!", (100, 255, 255))
        return True  # Indicate successful use of the ability (bonus action consumed)
    

class Evasion(Ability):
    def __init__(self):
        super().__init__("Evasion", "Become incredibly agile, greatly increasing dodge chance and taking half damage if hit. Lasts 3 turns.", cooldown=50)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        user.add_status_effect("EvasionBuff", duration=3, game_instance=game_instance)
        game_instance.message_log.add_message(f"{user.name} activates Evasion!", (100, 255, 255))
        return True


class FireBolt(Ability):
    def __init__(self):
        # Cantrips have no cost and no cooldown (they are "at-will")
        super().__init__("Fire Bolt", "Hurl a searing bolt of fire at a foe.", cost=0, cooldown=0)
        self.range = 8 # Example range in tiles

    def use(self, user, game_instance):
        # Cantrips don't have cooldowns, but we'll still call super().use for consistency
        # and to potentially handle future cost mechanics if we add them to cantrips.
        if not super().use(user, game_instance):
            return False
        
        # Set the game state to targeting mode
        game_instance.game_state = GameState.TARGETING
        game_instance.ability_in_use = self # Store which ability is being used
        game_instance.targeting_ability_range = self.range
        
        # Initialize targeting cursor at player's position
        game_instance.targeting_cursor_x = user.x
        game_instance.targeting_cursor_y = user.y
        
        game_instance.message_log.add_message(f"{user.name} prepares Fire Bolt! Select a target (Arrow Keys, Enter to confirm, Esc to cancel).", (255, 100, 0))
        return True # Indicate successful initiation of targeting


