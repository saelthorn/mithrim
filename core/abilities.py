
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
        
        # Apply a temporary buff to the player
        user.add_status_effect("PowerAttackBuff", duration=1) # Needs a status effect system
        game_instance.message_log.add_message(f"{user.name} prepares a powerful strike!", (255, 165, 0))
        return True
