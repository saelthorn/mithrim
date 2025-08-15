import random
from world.tile import floor, MimicTile, TrapTile

from core.status_effects import PowerAttackBuff, EvasionBuff
from core.game import GameState
from entities.monster import Monster, Mimic
from core.floating_text import FloatingText


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

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Abstract method: Performs the ability's effect on the given target coordinates.
        Returns True if the effect was successfully applied and the turn should end.
        Returns False if the target was invalid or the ability couldn't be used on it,
        and targeting mode should persist.
        """
        raise NotImplementedError("Subclasses must implement execute_on_target method.")            

# --- Innate Abilities ---

class SpotTrapsAbility(Ability):
    def __init__(self):
        # Cooldown: e.g., 10 turns. Cost: 0 for now, could be stamina later.
        super().__init__("Spot Traps", "Actively search for hidden traps in adjacent tiles.", cost=0, cooldown=5)

    def use(self, user, game_instance):
        if not super().use(user, game_instance): # Handles cooldown check
            return False
        
        game_instance.message_log.add_message(f"{user.name} actively searches for traps...", (100, 255, 255))
        
        # Check for traps in adjacent tiles
        adjacent_traps = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue  # Skip self
                check_x = user.x + dx
                check_y = user.y + dy
                if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                    tile = game_instance.game_map.tiles[check_y][check_x]
                    if isinstance(tile, TrapTile) and tile.trap_instance.is_hidden:
                        adjacent_traps.append(tile)
        
        if adjacent_traps:
            # Perform an Intelligence (Investigation) check
            investigation_bonus = user.get_ability_modifier(user.intelligence)
            if "investigation" in user.skill_proficiencies:
                investigation_bonus += user.proficiency_bonus
            d20_roll = random.randint(1, 20)
            investigation_check_total = d20_roll + investigation_bonus
            
            found_any = False
            for trap_tile in adjacent_traps:
                if investigation_check_total >= trap_tile.trap_instance.detection_dc:
                    trap_tile.trap_instance.reveal(game_instance, trap_tile.x, trap_tile.y)
                    game_instance.message_log.add_message(f"You successfully find a hidden {trap_tile.trap_instance.name}!", (0, 255, 255))
                    found_any = True
                # Else: The message for failing to find *any* traps is handled below.
            
            if not found_any:
                game_instance.message_log.add_message(f"You fail to find any traps nearby.", (150, 150, 150))
        else:
            game_instance.message_log.add_message("You don't see any traps nearby.", (150, 150, 150))
        
        return True # Indicate successful use and end turn


class DisarmTrapsAbility(Ability):
    def __init__(self):
        # Cooldown: e.g., 15 turns. Cost: 0 for now.
        super().__init__("Disarm Traps", "Attempt to disarm a revealed trap in an adjacent tile.", cost=0, cooldown=10)

    def use(self, user, game_instance):
        if not super().use(user, game_instance): # Handles cooldown check
            return False
        
        game_instance.message_log.add_message(f"{user.name} prepares to disarm a trap...", (100, 255, 255))
        
        # Check all adjacent tiles for revealed traps
        disarmable_traps = []
        for dx in [0, -1, 1]:  # Check adjacent tiles
            for dy in [0, -1, 1]:
                if abs(dx) + abs(dy) == 1:  # Only cardinal directions for disarming
                    check_x = user.x + dx
                    check_y = user.y + dy
                    if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                        tile = game_instance.game_map.tiles[check_y][check_x]
                        if isinstance(tile, TrapTile) and not tile.trap_instance.is_hidden and not tile.trap_instance.is_disarmed:
                            disarmable_traps.append(tile)
        
        if disarmable_traps:
            # For simplicity, we'll auto-target the first disarmable trap found.
            # You could implement a targeting mode similar to FireBolt if you want the player to choose.
            target_tile = disarmable_traps[0]

            # Check if the player has Thieves' Tools in their inventory
            has_tools = any(item.name == "Thieves' Tools" for item in user.inventory.items)
            
            if has_tools:
                if target_tile.trap_instance.attempt_disarm(user, game_instance, target_tile.x, target_tile.y):
                    game_instance.message_log.add_message(f"Disarmed the {target_tile.trap_instance.name}!", (0, 255, 0))
                else:
                    game_instance.message_log.add_message(f"Failed to disarm the {target_tile.trap_instance.name}!", (255, 100, 100))
            else:
                game_instance.message_log.add_message("You need Thieves' Tools to disarm traps.", (255, 0, 0))
        else:
            game_instance.message_log.add_message("No disarmable traps adjacent to you.", (150, 150, 150))
        
        return True # Indicate successful use and end turn




# --- Specific Abilities ---

class SecondWind(Ability):
    def __init__(self):
        super().__init__("Second Wind", "Heal yourself for a small amount of HP.", cooldown=30) # 15 turns cooldown

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
        super().__init__("Power Attack", "Sacrifice accuracy for increased damage on your next attack.", cooldown=10)
        # PowerAttack doesn't need a 'range' attribute here because it's not a direct targeted ability.
        # It modifies the *next* melee attack.
    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Apply the PowerAttackBuff to the user
        user.add_status_effect("PowerAttackBuff", duration=2, game_instance=game_instance) # Duration 1 means it lasts for the next turn/attack
        
        game_instance.message_log.add_message(f"{user.name} prepares a Power Attack!", (255, 165, 0))
        
        # Power Attack does NOT enter targeting mode. It just applies a buff.
        # The player's turn should end after using this ability.
        return True # Indicate successful use and end turn


class CunningAction(Ability):
    def __init__(self):
        super().__init__("Cunning Action", "Use a bonus action to Dash.", cooldown=5)  # Removed Disengage option

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
        
        user.add_status_effect("EvasionBuff", duration=5, game_instance=game_instance)
        game_instance.message_log.add_message(f"{user.name} activates Evasion!", (100, 255, 255))
        return True


class FireBolt(Ability):
    def __init__(self):
        super().__init__("Fire Bolt", "Hurl a searing bolt of fire at a foe.", cost=0, cooldown=0)
        self.range = 8  # Example range in tiles

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Find only monster targets within range
        # Each element in 'targets' will be a Monster object
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = user.distance_to(entity.x, entity.y)
                if distance <= self.range * 1:  # Auto-targeting range is multiplied by 2
                    monster_targets.append(entity)

        # If there are monster targets, auto-target the closest one
        if monster_targets:
            target = min(monster_targets, key=lambda m: user.distance_to(m.x, m.y))
            
            # Set the game state to targeting mode
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at the auto-selected monster's position
            game_instance.targeting_cursor_x = target.x
            game_instance.targeting_cursor_y = target.y
            
            game_instance.message_log.add_message(f"{user.name} prepares Fire Bolt! Auto-targeting {target.name}.", (255, 100, 0))
            game_instance.message_log.add_message("Use Arrow Keys to change target, Enter to confirm, Esc to cancel.", (255, 100, 0))
            return True  # Indicate successful initiation of targeting
        
        # If no monster targets are found, revert to manual targeting starting at player
        else:
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at player's position
            game_instance.targeting_cursor_x = user.x
            game_instance.targeting_cursor_y = user.y
            
            game_instance.message_log.add_message(f"{user.name} prepares Fire Bolt! No enemies in range. Select a target (Arrow Keys, Enter to confirm, Esc to cancel).", (255, 100, 0))
            return True # Indicate successful initiation of targeting

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Fire Bolt effect on the selected target.
        """
        target_monster = game_instance.get_target_at(target_x, target_y)
        target_tile = game_instance.game_map.tiles[target_y][target_x] # Get the tile object at target

        # Fire Bolt damage calculation (example: 1d10)
        damage_roll = random.randint(1, 10)
        if target_monster and isinstance(target_monster, Monster):
            # Check if the target is specifically a Mimic
            hit_messages = [
                f"A searing bolt of fire streaks towards the {target_monster.name}!",
                f"Flames erupt as your spell connects with the {target_monster.name}!",
                f"The {target_monster.name} is engulfed in magical fire!",
            ]
            game_instance.message_log.add_message(random.choice(hit_messages), (255, 165, 0))

            if isinstance(target_monster, Mimic):
                # Mimic.take_damage expects 'amount' and 'game_instance'
                damage_dealt = target_monster.take_damage(damage_roll, game_instance) 
            else:
                # Monster.take_damage (for generic monsters) only expects 'amount'
                damage_dealt = target_monster.take_damage(damage_roll, game_instance) # Pass game_instance here

            game_instance.message_log.add_message(f"A bolt of fire strikes {target_monster.name} for {damage_dealt} damage!", (255, 165, 0))
            # Add the HP message here
            game_instance.message_log.add_message(f"{target_monster.name} has {target_monster.hp}/{target_monster.max_hp} HP", (255, 165, 0))

            # Add FloatingText for "HIT!" and damage dealt
            hit_text = FloatingText(target_monster.x, target_monster.y, "HIT!", (255, 255, 0))
            game_instance.floating_texts.append(hit_text)

            damage_text = FloatingText(target_monster.x, target_monster.y - 0.5, str(damage_dealt), (255, 0, 0)) # <--- ADJUSTED Y
            game_instance.floating_texts.append(damage_text)

            if not target_monster.alive:
                xp_gained = target_monster.die()
                user.gain_xp(xp_gained, game_instance) # Use 'user' (player) here
                game_instance.message_log.add_message(f"The {target_monster.name} dies! [+{xp_gained} XP]", (100, 255, 100))
            return True # Successfully used ability

        
        elif target_tile.destructible: # <--- NEW: Check if the tile is destructible
            destructible_messages = [
                f"Your Fire Bolt incinerates the {target_tile.name}!",
                f"The {target_tile.name} explodes in a burst of flame!",
                f"A magical inferno consumes the {target_tile.name}!",
            ]
            game_instance.message_log.add_message(random.choice(destructible_messages), (255, 165, 0))                
            
            # For simplicity, we'll assume Fire Bolt instantly destroys destructible tiles
            # In a more complex system, destructible tiles might have HP.
            game_instance.message_log.add_message(f"Your Fire Bolt smashes the {target_tile.name}!", (255, 165, 0))
            game_instance.game_map.tiles[target_y][target_x] = floor # Replace with floor tile
            
            # --- MISSING FLOATING TEXT CREATION HERE FOR DESTRUCTIBLE ---
            # You might want a different message for destructibles, e.g., "SMASH!"
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "SMASH!", (255, 100, 0)))
            print(f"DEBUG: FireBolt added SMASH! FloatingText for {target_tile.name} at ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}") # <--- ADD THIS DEBUG

            # If it was a MimicTile, ensure the Mimic entity is also handled
            if isinstance(target_tile, MimicTile):
                mimic_entity = target_tile.mimic_entity
                if mimic_entity.disguised:
                    mimic_entity.reveal(game_instance) # Reveal the mimic
                else:
                    game_instance.message_log.add_message(f"The {mimic_entity.name} is already revealed and takes no further damage from smashing its disguise.", (150, 150, 150))
            return True # Successfully used ability
        else:
            game_instance.message_log.add_message("Fire Bolt requires a monster target or a destructible object.", (255, 150, 0))
            # --- MISSING FLOATING TEXT FOR MISS/INVALID TARGET ---
            # You might want a "MISS!" or "INVALID!" floating text here
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "INVALID!", (255, 0, 0)))
            print(f"DEBUG: FireBolt added INVALID! FloatingText for ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}") # <--- ADD THIS DEBUG
            return False # Invalid target, stay in targeting mode            


class MistyStep(Ability):
    def __init__(self):
        super().__init__("Misty Step", "The caster is briefly surrounded by silvery mist then vanishes, reappearing in an unoccupied space up to 6 tiles away.", cooldown=10)
        self.range = 6 # Max teleport distance in tiles

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Set the player's action state to indicate a choice is pending
        user.current_action_state = "misty_step_teleport" # A new state for Misty Step
        game_instance.message_log.add_message(f"{user.name} prepares to Misty Step! Select a destination (Arrow Keys, Enter to confirm, Esc to cancel).", (100, 255, 255))
        
        # Initialize targeting cursor at player's position for selection
        game_instance.targeting_cursor_x = user.x
        game_instance.targeting_cursor_y = user.y
        game_instance.targeting_ability_range = self.range # Set the range for the cursor
        game_instance.ability_in_use = self # Store the ability for targeting context
        game_instance.game_state = GameState.TARGETING # Enter targeting mode

        return True # Indicate successful initiation of the ability
    
    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Misty Step teleport effect.
        """
        # Check if the target tile is walkable and not blocked by an entity
        if not game_instance.game_map.is_walkable(target_x, target_y):
            game_instance.message_log.add_message("Cannot Misty Step to an unwalkable space.", (255, 150, 0))
            return False # Invalid target, stay in targeting mode
        
        # Check if the target tile is occupied by another entity
        entity_at_target = game_instance.get_target_at(target_x, target_y) # Re-using get_target_at
        if entity_at_target:
            game_instance.message_log.add_message("Cannot Misty Step to an occupied space.", (255, 150, 0))
            return False # Invalid target, stay in targeting mode
        
        # Perform the teleport
        user.x = target_x
        user.y = target_y
        game_instance.message_log.add_message(f"{user.name} vanishes in a silvery mist and reappears!", (100, 255, 255))
        game_instance.update_fov() # Update FOV after teleporting
        return True # Successfully used ability    



