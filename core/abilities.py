import random
from world.tile import floor, MimicTile, TrapTile

from core.status_effects import PowerAttackBuff, EvasionBuff
from core.game import GameState
from entities.monster import Monster, Mimic
from entities.summons import MageHandEntity
from entities.base_entity import NPC
from core.floating_text import FloatingText
from items.items import Potion, Food, lesser_healing_potion, greater_healing_potion, meat, green_apple, fromage, bread, mushroom, torch, wood_plank # NEW: Import for potion drop


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
        Performs the Mage Hand effect on the selected target.
        """
        target_tile = game_instance.game_map.tiles[target_y][target_x]

        # Check if the target is a TrapTile
        if isinstance(target_tile, TrapTile) and not target_tile.trap_instance.is_triggered:
            game_instance.message_log.add_message(f"The Mage Hand triggers the {target_tile.trap_instance.name}!", (255, 255, 0))

            # Pass the actual player object instead of "Mage Hand"
            target_tile.trap_instance.trigger(user, game_instance, target_x, target_y)  # Pass the player object
            return True  # Action successful, end turn

        game_instance.message_log.add_message("Mage Hand cannot interact with that target.", (255, 150, 0))
        return False  # Invalid target, stay in targeting mode

# --- Innate Abilities ---

class SpotTrapsAbility(Ability):
    def __init__(self):
        # Cooldown: e.g., 10 turns. Cost: 0 for now, could be stamina later.
        super().__init__("Spot Traps", "Actively search for hidden traps in adjacent tiles.", cost=0, cooldown=3)

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
        super().__init__("Disarm Traps", "Attempt to disarm a revealed trap in an adjacent tile.", cost=0, cooldown=3)

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
        super().__init__("Second Wind", "Heal yourself for a small amount of HP.", cooldown=75) # 75 turns cooldown

    def use(self, user, game_instance):
        # Call base class use to handle cooldown and initial checks.
        # If base.use returns False (because can_use failed), then this method should also return False.
        if not super().use(user, game_instance):
            return False
        
        heal_amount = user.level * 2 + 8 # Example: Heals based on level
        amount_healed = user.heal(heal_amount)
        game_instance.message_log.add_message(f"{user.name} regains {amount_healed} HP!", (0, 255, 0))
        return True # Indicate successful use


class PowerAttack(Ability):
    def __init__(self):
        super().__init__("Power Attack", "Sacrifice accuracy for increased damage on your next attack.", cooldown=15)
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
        super().__init__("Cunning Action", "Use a bonus action to Dash.", cooldown=5)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Set the player's action state to indicate a choice is pending
        user.current_action_state = "cunning_action_dash"  # Changed to only allow Dash
        game_instance.message_log.add_message(f"{user.name} prepares a Cunning Action: Dash!", (100, 255, 255))
        return True  # Indicate successful use of the ability (bonus action consumed)
  

class Evasion(Ability):
    def __init__(self):
        super().__init__("Evasion", "Become incredibly agile, greatly increasing dodge chance and taking half damage if hit. Lasts 3 turns.", cooldown=40)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        user.add_status_effect("EvasionBuff", duration=10, game_instance=game_instance)
        game_instance.message_log.add_message(f"{user.name} activates Evasion!", (100, 255, 255))
        return True


class FireBolt(Ability):
    def __init__(self):
        super().__init__("Fire Bolt", "Hurl a searing bolt of fire at a foe.", cost=0, cooldown=1)
        self.range = 6  # Example range in tiles

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False

        # Helper: footprint-aware visibility
        def is_entity_visible(ent):
            allowed = ['player', 'torch', 'darkvision']
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                for oy in range(size):
                    for ox in range(size):
                        if game_instance.fov.get_visibility_type(ent.x + ox, ent.y + oy) in allowed:
                            return True
                return False
            return game_instance.fov.get_visibility_type(ent.x, ent.y) in allowed

        # Helper: footprint-aware distance (min distance to any occupied tile)
        def distance_to_entity(ent):
            size = getattr(ent, 'footprint_size', 1)
            if size > 1:
                best = None
                for oy in range(size):
                    for ox in range(size):
                        d = user.distance_to(ent.x + ox, ent.y + oy)
                        if best is None or d < best:
                            best = d
                return best if best is not None else 9999
            return user.distance_to(ent.x, ent.y)

        # Find only monster targets within range (footprint-aware)
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = distance_to_entity(entity)
                if distance <= self.range:  # Check against ability range
                    if is_entity_visible(entity):  # Footprint-aware FOV
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
            game_instance.message_log.add_message(f"{user.name} prepares Fire Bolt! No enemies in range. Select a target (Arrow Keys, Enter to confirm, Esc to cancel).", (255, 100, 0))
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at player's position
            game_instance.targeting_cursor_x = user.x
            game_instance.targeting_cursor_y = user.y
            
            return True  # Indicate successful initiation of targeting

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Fire Bolt effect on the selected target.
        """
        target_monster = game_instance.get_target_at(target_x, target_y)
        target_tile = game_instance.game_map.tiles[target_y][target_x]  # Get the tile object at target

        # Check if the target is within the player's FOV (tile or any tile of monster footprint)
        if not game_instance.fov.get_visibility_type(target_x, target_y) in ['player', 'torch', 'darkvision']:
            game_instance.message_log.add_message(f"You cannot attack {target_x}, {target_y} because it is out of sight!", (255, 0, 0))
            return False  # Do not consume a turn

        if not game_instance.check_line_of_sight(user.x, user.y, target_x, target_y):
            game_instance.message_log.add_message(f"A wall blocks your shot to {target_x}, {target_y}!", (255, 0, 0))
            return False # Do not consume a turn

        target_monster = game_instance.get_target_at(target_x, target_y)
        target_tile = game_instance.game_map.tiles[target_y][target_x]  # Get the tile object at target        


        # Check if the target is a valid monster or destructible object
        if not (target_monster or target_tile.destructible):
            game_instance.message_log.add_message("Fire Bolt requires a monster target or a destructible object.", (255, 150, 0))
            return False  # Invalid target, do not consume a turn

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
                damage_dealt = target_monster.take_damage(damage_roll, game_instance) 
            else:
                damage_dealt = target_monster.take_damage(damage_roll, game_instance)  # Pass game_instance here

            game_instance.message_log.add_message(f"A bolt of fire strikes {target_monster.name} for {damage_dealt} damage!", (255, 165, 0))
            game_instance.message_log.add_message(f"{target_monster.name} has {target_monster.hp}/{target_monster.max_hp} HP", (255, 165, 0))

            # Add FloatingText for "HIT!" and damage dealt
            hit_text = FloatingText(target_monster.x, target_monster.y, "HIT!", (255, 255, 0))
            game_instance.floating_texts.append(hit_text)

            damage_text = FloatingText(target_monster.x, target_monster.y - 0.5, str(damage_dealt), (255, 0, 0))  # <--- ADJUSTED Y
            game_instance.floating_texts.append(damage_text)

            if not target_monster.alive:
                xp_gained = target_monster.die(game_instance)
                user.gain_xp(xp_gained, game_instance)  # Use 'user' (player) here
            return True  # Successfully used ability

        elif target_tile.destructible:  # <--- NEW: Check if the tile is destructible
            destructible_messages = [
                f"Your Fire Bolt incinerates the {target_tile.name}!",
                f"A magical inferno consumes the {target_tile.name}!",
            ]
            game_instance.message_log.add_message(random.choice(destructible_messages), (255, 165, 0))                

            # For simplicity, we'll assume Fire Bolt instantly destroys destructible tiles
            # In a more complex system, destructible tiles might have HP.
            game_instance.message_log.add_message(f"Your Fire Bolt smashes the {target_tile.name}!", (255, 165, 0))
            game_instance.game_map.tiles[target_y][target_x] = floor  # Replace with floor tile
            self.minimap_needs_redraw = True # Map changed, redraw minimap
            
            # --- 10% chance to drop a healing potion ---            
            if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel 
                if random.random() < 0.70:
                    new_junk = wood_plank.__class__(
                        name=wood_plank.name,
                        char=wood_plank.char,
                        color=wood_plank.color,
                        description=wood_plank.description
                    )
                    new_junk.x = target_x
                    new_junk.y = target_y
                    game_instance.game_map.items_on_ground.append(new_junk)
                elif random.random() < 0.3:
                    new_torch = torch.__class__(
                        name=torch.name,
                        char=torch.char,
                        color=torch.color,
                        description=torch.description,
                        price=torch.price
                    )
                    new_torch.x = target_x
                    new_torch.y = target_y
                    game_instance.game_map.items_on_ground.append(new_torch)
                    game_instance.message_log.add_message(f"A {new_torch.name} drops from the {target_tile.name}!", new_torch.color)
                elif random.random() < 0.2:
                    new_food = meat.__class__(
                        name=meat.name,
                        char=meat.char,
                        color=meat.color,
                        description=meat.description,
                        healing_value=meat.healing_value,
                        price=meat.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.35:
                    new_food = green_apple.__class__(
                        name=green_apple.name,
                        char=green_apple.char,
                        color=green_apple.color,
                        description=green_apple.description,
                        healing_value=green_apple.healing_value,
                        price=green_apple.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.25:
                    new_food = fromage.__class__(
                        name=fromage.name,
                        char=fromage.char,
                        color=fromage.color,
                        description=fromage.description,
                        healing_value=fromage.healing_value,
                        price=fromage.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.3:
                    new_food = bread.__class__(
                        name=bread.name,
                        char=bread.char,
                        color=bread.color,
                        description=bread.description,
                        healing_value=bread.healing_value,
                        price=bread.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.4:
                    new_food = mushroom.__class__(
                        name=mushroom.name,
                        char=mushroom.char,
                        color=mushroom.color,
                        description=mushroom.description,
                        healing_value=mushroom.healing_value,
                        price=mushroom.price
                    )
                    new_food.x = target_x
                    new_food.y = target_y
                    game_instance.game_map.items_on_ground.append(new_food)
                    game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)                 


            # --- MISSING FLOATING TEXT CREATION HERE FOR DESTRUCTIBLE ---
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "SMASH!", (255, 100, 0)))
            print(f"DEBUG: FireBolt added SMASH! FloatingText for {target_tile.name} at ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}")  # <--- ADD THIS DEBUG

            # If it was a MimicTile, ensure the Mimic entity is also handled
            if isinstance(target_tile, MimicTile):
                mimic_entity = target_tile.mimic_entity
                if mimic_entity.disguised:
                    mimic_entity.reveal(game_instance)  # Reveal the mimic
                else:
                    game_instance.message_log.add_message(f"The {mimic_entity.name} is already revealed and takes no further damage from smashing its disguise.", (150, 150, 150))
            return True  # Successfully used ability
        else:
            game_instance.message_log.add_message("Fire Bolt requires a monster target or a destructible object.", (255, 150, 0))
            # --- MISSING FLOATING TEXT FOR MISS/INVALID TARGET ---
            game_instance.floating_texts.append(FloatingText(target_x, target_y, "INVALID!", (255, 0, 0)))
            print(f"DEBUG: FireBolt added INVALID! FloatingText for ({target_x},{target_y}). List size: {len(game_instance.floating_texts)}")  # <--- ADD THIS DEBUG
            return False  # Invalid target, stay in targeting mode

class Fireball(Ability):
    def __init__(self):
        super().__init__("Fireball", "A bright streak flashes and explodes in a fiery blast.", cost=0, cooldown=100)
        self.radius = 4  # Radius of the fireball effect
        self.range = 8
        self.damage_dice = 8  # Number of damage dice

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False
        
        # Find only monster targets within range
        monster_targets = []
        for entity in game_instance.entities:
            if isinstance(entity, Monster) and entity.alive:
                distance = user.distance_to(entity.x, entity.y)
                if distance <= self.range:  # Check against ability range
                    # Check if the target is within the player's FOV
                    if game_instance.fov.get_visibility_type(entity.x, entity.y) in ['player', 'torch', 'darkvision']:
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
            
            game_instance.message_log.add_message(f"{user.name} conjures Fireball! Auto-targeting {target.name}.", (255, 100, 0))
            game_instance.message_log.add_message("Use Arrow Keys to change target, Enter to confirm, Esc to cancel.", (255, 100, 0))
            return True  # Indicate successful initiation of targeting
        
        # If no monster targets are found, revert to manual targeting starting at player
        else:
            game_instance.message_log.add_message(f"{user.name} conjures Fireball! No enemies in range. Select a target (Arrow Keys, Enter to confirm, Esc to cancel).", (255, 100, 0))
            game_instance.game_state = GameState.TARGETING
            game_instance.ability_in_use = self  # Store which ability is being used
            game_instance.targeting_ability_range = self.range
            
            # Initialize targeting cursor at player's position
            game_instance.targeting_cursor_x = user.x
            game_instance.targeting_cursor_y = user.y
            
            return True  # Indicate successful initiation of targeting

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Executes the Fireball effect on the selected target.
        """
        from entities.player import Player
        # Check if the target is within the player's FOV
        if not game_instance.fov.get_visibility_type(target_x, target_y) in ['player', 'torch', 'darkvision']:
            game_instance.message_log.add_message(f"You cannot cast Fireball at {target_x}, {target_y} because it is out of sight!", (255, 0, 0))
            return False  # Do not consume a turn

        # Calculate the damage
        damage_rolls = [random.randint(1, 6) for _ in range(self.damage_dice)]  # Roll 8d6
        total_damage = sum(damage_rolls)

        # Notify the player of the damage
        game_instance.message_log.add_message(f"{user.name} casts Fireball and rolls 8d6 {damage_rolls}.", (255, 165, 0))
        game_instance.message_log.add_message(f"Fireball deals {total_damage} fire damage!", (255, 165, 0))

        # Apply damage to all entities in the area of effect
        for entity in game_instance.entities:
            if entity.alive and self.is_within_radius(entity.x, entity.y, target_x, target_y, self.radius):
                if isinstance(entity, (Monster, Player)):
                    # Each entity makes a Dexterity saving throw
                    dexterity_save = entity.get_saving_throw_bonus("DEX")
                    d20_roll = random.randint(1, 20)
                    save_total = d20_roll + dexterity_save

                    game_instance.message_log.add_message(f"{entity.name} rolls a d20: {d20_roll} + {dexterity_save} = {save_total} (DC 15)", (200, 200, 255))

                    if save_total >= 15:  # Assuming a DC of 15 for Fireball
                        damage_dealt = total_damage // 2  # Half damage on success
                        game_instance.message_log.add_message(f"{entity.name} succeeds on the saving throw and takes {damage_dealt} fire damage!", (100, 255, 100))
                    else:
                        damage_dealt = total_damage  # Full damage on failure
                        game_instance.message_log.add_message(f"{entity.name} fails the saving throw and takes {damage_dealt} fire damage!", (255, 100, 100))

                    damage_dealt = entity.take_damage(damage_dealt, game_instance, damage_type='fire')  # Apply damage

                    # Create floating text for damage dealt
                    damage_text = FloatingText(entity.x, entity.y - 0.5, str(damage_dealt), (255, 0, 0))  # Adjust Y for visibility
                    game_instance.floating_texts.append(damage_text)  # Add to floating texts

                    # Check if the entity is dead and award XP
                    if not entity.alive:
                        if isinstance(entity, Monster):
                            xp_gained = entity.die(game_instance)  # Pass game_instance to the die method
                            user.gain_xp(xp_gained, game_instance)  # Award XP to the player
                            game_instance.message_log.add_message(f"You gain {xp_gained} XP!", (100, 255, 100))  # Log the XP gained

        # Destroy destructible tiles in the area of effect
        for x in range(target_x - self.radius, target_x + self.radius + 1):
            for y in range(target_y - self.radius, target_y + self.radius + 1):
                if self.is_within_radius(x, y, target_x, target_y, self.radius):
                    # Ensure coordinates are within map bounds
                    if not (0 <= x < game_instance.game_map.width and 0 <= y < game_instance.game_map.height):
                        continue

                    target_tile = game_instance.game_map.tiles[y][x]

                    # --- NEW MIMIC REVEAL LOGIC ---
                    if isinstance(target_tile, MimicTile):
                        mimic_entity = target_tile.mimic_entity
                        if mimic_entity.disguised:
                            game_instance.message_log.add_message(f"The Fireball strikes the disguised {mimic_entity.name}!", (255, 165, 0))
                            # Mimics take damage from the fireball, which will trigger their reveal
                            # We pass the full damage of the fireball to the mimic
                            mimic_entity.take_damage(total_damage, game_instance, damage_type='fire')
                            # If the mimic is still disguised after taking damage (meaning it didn't die from the hit)
                            if mimic_entity.disguised: # Check again if it's still disguised
                                mimic_entity.reveal(game_instance) # Force reveal if it didn't die
                            # No need to replace the tile with floor here, as the mimic's reveal handles it.
                            game_instance.floating_texts.append(FloatingText(x, y, "REVEAL!", (255, 255, 0)))
                            game_instance.minimap_needs_redraw = True
                            continue # Move to the next tile in the radius

                    # --- EXISTING DESTRUCTIBLE TILE LOGIC (only if not a MimicTile) ---
                    if target_tile.destructible:
                        game_instance.message_log.add_message(f"The {target_tile.name} is destroyed by the Fireball!", (255, 0, 0))
                        game_instance.game_map.tiles[y][x] = floor  # Replace with floor tile
                        game_instance.minimap_needs_redraw = True  # Mark minimap for redraw

                        # Create floating text for the destruction of the tile
                        destruction_text = FloatingText(x, y - 0.5, f"SMASH!", (255, 0, 0))  # Adjust Y for visibility
                        game_instance.floating_texts.append(destruction_text)  # Add to floating texts

                        # --- Existing potion drop logic for crates/barrels ---
                        if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel 
                            if random.random() < 0.70:
                                new_junk = wood_plank.__class__(
                                    name=wood_plank.name,
                                    char=wood_plank.char,
                                    color=wood_plank.color,
                                    description=wood_plank.description
                                )
                                new_junk.x = x
                                new_junk.y = y
                                game_instance.game_map.items_on_ground.append(new_junk)
                            elif random.random() < 0.3:
                                new_torch = torch.__class__(
                                    name=torch.name,
                                    char=torch.char,
                                    color=torch.color,
                                    description=torch.description,
                                    price=torch.price
                                )
                                new_torch.x = x
                                new_torch.y = y
                                game_instance.game_map.items_on_ground.append(new_torch)
                                game_instance.message_log.add_message(f"A {new_torch.name} drops from the {target_tile.name}!", new_torch.color)
                            elif random.random() < 0.2:
                                new_food = meat.__class__(
                                    name=meat.name,
                                    char=meat.char,
                                    color=meat.color,
                                    description=meat.description,
                                    healing_value=meat.healing_value,
                                    price=meat.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                            elif random.random() < 0.35:
                                new_food = green_apple.__class__(
                                    name=green_apple.name,
                                    char=green_apple.char,
                                    color=green_apple.color,
                                    description=green_apple.description,
                                    healing_value=green_apple.healing_value,
                                    price=green_apple.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                            elif random.random() < 0.25:
                                new_food = fromage.__class__(
                                    name=fromage.name,
                                    char=fromage.char,
                                    color=fromage.color,
                                    description=fromage.description,
                                    healing_value=fromage.healing_value,
                                    price=fromage.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                            elif random.random() < 0.3:
                                new_food = bread.__class__(
                                    name=bread.name,
                                    char=bread.char,
                                    color=bread.color,
                                    description=bread.description,
                                    healing_value=bread.healing_value,
                                    price=bread.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                            elif random.random() < 0.4:
                                new_food = mushroom.__class__(
                                    name=mushroom.name,
                                    char=mushroom.char,
                                    color=mushroom.color,
                                    description=mushroom.description,
                                    healing_value=mushroom.healing_value,
                                    price=mushroom.price
                                )
                                new_food.x = x
                                new_food.y = y
                                game_instance.game_map.items_on_ground.append(new_food)
                                game_instance.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 

        return True  # Successfully used ability

    def is_within_radius(self, x, y, center_x, center_y, radius):
        """Check if the (x, y) coordinates are within the radius of the center point."""
        return (x - center_x) ** 2 + (y - center_y) ** 2 <= radius ** 2


class MistyStep(Ability):
    def __init__(self):
        super().__init__("Misty Step", "The caster is briefly surrounded by silvery mist then vanishes, reappearing in an unoccupied space up to 6 tiles away.", cooldown=7)
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


class DetectMagic(Ability):
    def __init__(self):
        super().__init__("Detect Magic", "Detects magical traps (specifically Fire Traps) within a certain range.", cost=0, cooldown=3)

    def use(self, user, game_instance):
        if not super().use(user, game_instance):  # Handles cooldown check
            return False
        
        game_instance.message_log.add_message(f"{user.name} casts Detect Magic...", (100, 255, 255))
        
        # Check for Fire Traps in adjacent tiles
        detected_traps = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue  # Skip self
                check_x = user.x + dx
                check_y = user.y + dy
                if 0 <= check_x < game_instance.game_map.width and 0 <= check_y < game_instance.game_map.height:
                    tile = game_instance.game_map.tiles[check_y][check_x]
                    if isinstance(tile, TrapTile) and tile.trap_instance.name == "Fire Trap" and tile.trap_instance.is_hidden:
                        detected_traps.append(tile)

        if detected_traps:
            for trap_tile in detected_traps:
                trap_tile.trap_instance.reveal(game_instance, trap_tile.x, trap_tile.y)
                game_instance.message_log.add_message(f"You detect a hidden {trap_tile.trap_instance.name}!", (0, 255, 255))
        else:
            game_instance.message_log.add_message("No magical traps detected nearby.", (150, 150, 150))
        
        return True  # Indicate successful use and end turn


class MageHand(Ability):
    def __init__(self):
        super().__init__("Mage Hand", "Summon a spectral hand to trigger traps or pick up items from a distance.", cost=0, cooldown=2)
        self.range = 6  # Max distance the Mage Hand can be controlled

    def use(self, user, game_instance):
        if not super().use(user, game_instance):
            return False

        game_instance.message_log.add_message("Select a target to trigger a trap or pick up an item (Arrow Keys, Enter to confirm, Esc to cancel).", (255, 100, 0))
        
        game_instance.game_state = GameState.TARGETING
        game_instance.ability_in_use = self
        game_instance.targeting_ability_range = self.range
        game_instance.targeting_cursor_x = user.x  # Start at player's position
        game_instance.targeting_cursor_y = user.y

        return True

    def execute_on_target(self, user, game_instance, target_x, target_y):
        """
        Performs the Mage Hand effect on the selected target.
        """
        target_tile = game_instance.game_map.tiles[target_y][target_x]
    
        # Create a temporary MageHandEntity instance to act as the 'player' for the trap trigger
        mage_hand_actor = MageHandEntity(user.x, user.y, user)  # Pass user as owner
    
        # Check if the target is a TrapTile
        if isinstance(target_tile, TrapTile) and not target_tile.trap_instance.is_triggered:
            game_instance.message_log.add_message(f"The Mage Hand triggers the {target_tile.trap_instance.name}!", (255, 255, 0))
            target_tile.trap_instance.trigger(mage_hand_actor, game_instance, target_x, target_y)  # Pass the mage_hand_actor
            return True  # Action successful, end turn
    
        # Check if the target is an item (specifically a potion)
        item_at_target = game_instance.get_interactable_item_at(target_x, target_y)
        if item_at_target and isinstance(item_at_target, Potion or Food):
            # Instead of using mage_hand_actor, add the potion directly to the user's inventory
            if item_at_target.on_pickup(user, game_instance):  # Use the actual user as the picker
                game_instance.message_log.add_message(f"The Mage Hand picks up the {item_at_target.name}!", (0, 255, 0))
                # Remove the item from the ground after successful pickup
                game_instance.game_map.items_on_ground.remove(item_at_target)  # <-- Remove from ground
                return True  # Action successful, end turn
            else:
                game_instance.message_log.add_message(f"The Mage Hand cannot pick up the {item_at_target.name}.", (255, 150, 0))
                return False  # Failed to pick up the item
    
        game_instance.message_log.add_message("Mage Hand cannot interact with that target.", (255, 150, 0))
        return False  # Invalid target, stay in targeting mode



