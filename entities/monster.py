import random
from core.pathfinding import astar
from core.status_effects import Poisoned, AcidBurned, Burning, PowerAttackBuff, EvasionBuff
from core.floating_text import FloatingText 

from enum import Enum

class AI_State(Enum):
    CHASING = 1
    FLEEING = 2
    DESPERATE_FIGHT = 3

class Monster:
    def __init__(self, x, y, char, name, color):
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.alive = True
        self.hp = 10  # Base HP, will be overridden in subclasses
        self.max_hp = 10
        self.attack_bonus = 2  # Base attack bonus, will be overridden in subclasses
        self.armor_class = 11  # Base AC, will be overridden in subclasses
        self.base_xp = 10  # Base XP, will be overridden in subclasses
        self.monster_die_type = 4  # Base die type for damage rolls, will be overridden in subclasses
        self.num_damage_dice = 1  # Number of damage dice to roll, will be overridden in subclasses
        self.initiative = 0
        self.blocks_movement = True
        self.active_status_effects = []

        self.is_active = False # New attribute: True if monster is awake/active
        self.sleep_cooldown = 0 # New attribute: Timer for how long to stay asleep        

        # Rendering/footprint attributes
        # footprint_size represents how many tiles on a side this entity occupies (1 = 1x1)
        self.footprint_size = 1

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

        self.last_known_player_position = None  # New attribute to store last known player position
        self.detection_range = 5
       
        # Physical damage types
        self.damage_modifier = 2

        # Ranged attack attributes
        self.is_ranged = False
        self.ranged_attack_bonus = 0  # Base ranged attack bonus
        self.range = 0  # Max range for ranged attacks
        self.ranged_die_type = 4  # Base die type for ranged attacks
        self.ranged_num_dice = 1  # Number of damage dice for ranged attacks
       
        # Special attack attributes
        self.can_poison = False
        self.poison_dc = 10
        self.poison_duration = 3
        self.poison_damage_per_turn = 2
       
        self.can_acid_burn = False
        self.acid_burn_dc = 10
        self.acid_burn_duration = 3
        self.acid_burn_damage_per_turn = 3
       
        self.can_burn = False
        self.burn_dc = 14
        self.burn_duration = 3
        self.burn_damage_per_turn = random.randint(1, 4)

        # NEW: AI Behavior attributes
        self.is_intelligent = False  # Default to False. Set to True for intelligent monsters.
        self.flee_hp_threshold = 0.30  # Flee if monster HP < 25%
        self.player_safe_hp_threshold = 0.60  # Flee if player HP > 60%
        self.desperate_fight_hp_threshold = 0.50  # Fight if player HP < 40% (and monster HP is also low)
        self.ai_state = AI_State.CHASING  # Default state

        # Telegraph fields: when set by a monster, game will render highlights
        self.pending_telegraph_tiles = []  # list[(x,y)] tiles the monster intends to hit next turn
        self.telegraph_color = (255, 0, 0, 100)  # translucent red


    def take_turn(self, player, game_map, game):
        """Handle monster's combat and movement"""
        if not self.alive:
            return

        # If a telegraphed attack was set on previous turn, resolve it now
        if getattr(self, 'pending_telegraph_tiles', None):
            tiles = list(self.pending_telegraph_tiles)
            self.pending_telegraph_tiles = []
            # Apply damage to player if standing in any tile
            for tx, ty in tiles:
                if player.x == tx and player.y == ty and player.alive:
                    dmg = max(1, getattr(self, 'damage_modifier', 2) + random.randint(1, 6)) 
                    player.take_damage(dmg, game, damage_type='fire')
                    game.floating_texts.append(FloatingText(tx, ty, f"-{dmg}", (255, 80, 80)))
            # After resolving, monster's turn ends to give player counterplay
            return

        # Process status effects at the start of the monster's turn
        self.process_status_effects(game)
        if not self.alive:  # Check if monster died from status effect
            return

        # --- NEW: Sleep/Idle Logic ---
        if not self.is_active:
            # If not active, decrement sleep cooldown. If it reaches 0, it can potentially wake up.
            if self.sleep_cooldown > 0:
                self.sleep_cooldown -= 1
            return # Monster is sleeping, do nothing this turn


        player_detected = self.detect_player(player, game) # This updates last_known_player_position
        # --- Pathfinding only runs if player_detected or last_known_player_position is set ---
        if player_detected or self.last_known_player_position:
            pass
        else:
            self.patrol(game_map) # Or some other idle behavior

        # Determine AI state based on health
        monster_hp_low = self.hp_percentage() < self.flee_hp_threshold
        player_hp_high = game.get_player_hp_percentage() > self.player_safe_hp_threshold
        player_hp_low = game.get_player_hp_percentage() < self.desperate_fight_hp_threshold

        if self.is_intelligent:
            if monster_hp_low and player_hp_high:
                self.ai_state = AI_State.FLEEING
            elif monster_hp_low and player_hp_low:
                self.ai_state = AI_State.DESPERATE_FIGHT
            else:
                self.ai_state = AI_State.CHASING
        # Non-intelligent monsters always default to CHASING behavior (or whatever their default is)
        else:
            self.ai_state = AI_State.CHASING # Or a simpler AI state if they don't flee/desperate fight

        # Get distance to player for various checks
        distance_to_player = self.distance_to(player.x, player.y)
        player_detected = self.detect_player(player, game) # This updates last_known_player_position

        # --- AI State Behavior Execution ---
        if self.ai_state == AI_State.FLEEING:
            if self.flee(player, game_map, game):
                return  # Monster took action (fled)
            else:
                # game.message_log.add_message(f"The {self.name} tries to flee but is cornered!", (255, 100, 0))
                # If cannot flee, fall through to desperate fight or attack
                pass

        elif self.ai_state == AI_State.DESPERATE_FIGHT:
            game.message_log.add_message(f"The {self.name} is desperate and fights on!", (255, 100, 100))
            
            # Prioritize attacking if in range
            if self.is_ranged and distance_to_player <= self.range and game.check_line_of_sight(self.x, self.y, player.x, player.y):
                self.ranged_attack(player, game)
                return
            elif self.is_adjacent_to(player):
                self.attack(player, game)
                return
            
            # If not in attack range, chase the player
            else:
                # Use the same chasing logic as the CHASING state
                path = astar(game_map, (self.x, self.y), (player.x, player.y), entities=[e for e in game.entities if e != self and e != player and e.alive and e.blocks_movement], moving_entity=self)

                if path and len(path) > 1:
                    next_step = path[1]
                    new_x, new_y = next_step

                    moved = False
                    # For multi-tile entities, require full clearance at the new top-left anchor
                    if hasattr(self, 'can_occupy_position') and getattr(self, 'footprint_size', 1) > 1:
                        if self.can_occupy_position(new_x, new_y, game_map, game.entities, exclusions=[self]):
                            self.x, self.y = new_x, new_y
                            moved = True
                        else:
                            game.message_log.add_message(f"The {self.name} is too large to squeeze through.", (150, 100, 100))
                    else:
                        # Single-tile default movement
                        is_blocked = False
                        for entity in game.entities:
                            if entity != self and entity.alive and entity.blocks_movement:
                                if hasattr(entity, 'occupies_tile'):
                                    if entity.occupies_tile(new_x, new_y):
                                        is_blocked = True
                                        break
                                else:
                                    if entity.x == new_x and entity.y == new_y:
                                        is_blocked = True
                                        break

                        if not is_blocked:
                            self.x, self.y = new_x, new_y
                            moved = True

                    if not moved:
                        game.message_log.add_message(f"The {self.name} is blocked and cannot reach {player.name}!", (100, 100, 100))
                else:
                    game.message_log.add_message(f"The {self.name} cannot find a path to {player.name}!", (150, 150, 150))
                return # Action taken (attempted to move)

        # --- Default CHASING behavior (if not fleeing or desperate, or if fleeing failed) ---
        if player_detected: # Only chase if player is detected
            # If monster has ranged attack, check if player is in range and line of sight
            if self.is_ranged and distance_to_player <= self.range and game.check_line_of_sight(self.x, self.y, player.x, player.y):
                self.ranged_attack(player, game)
                return

            # Check if adjacent to player (including diagonals) - melee attack
            if self.is_adjacent_to(player):
                self.attack(player, game)  # Use base melee attack
                return

            # Otherwise, move toward the player's current position using A* pathfinding
            # Use last_known_player_position if player is not currently visible but was recently
            target_pos = (player.x, player.y) if game.check_line_of_sight(self.x, self.y, player.x, player.y) else self.last_known_player_position
            
            if target_pos: # Only pathfind if there's a target position
                path = astar(game_map, (self.x, self.y), target_pos, entities=[e for e in game.entities if e != self and e.alive and e.blocks_movement], moving_entity=self)

                if path and len(path) > 1:
                    next_step = path[1]
                    new_x, new_y = next_step

                    moved = False
                    # For multi-tile entities, require full clearance at the new top-left anchor
                    if getattr(self, 'footprint_size', 1) > 1 and hasattr(self, 'can_occupy_position'):
                        if self.can_occupy_position(new_x, new_y, game_map, game.entities, exclusions=[self]):
                            self.x, self.y = new_x, new_y
                            moved = True
                    else:
                        # Single-tile default movement with entity blocking check
                        is_blocked = False
                        for entity in game.entities:
                            if entity != self and entity.alive and entity.blocks_movement:
                                if hasattr(entity, 'occupies_tile'):
                                    if entity.occupies_tile(new_x, new_y):
                                        is_blocked = True
                                        break
                                else:
                                    if entity.x == new_x and entity.y == new_y:
                                        is_blocked = True
                                        break
                        if not is_blocked:
                            self.x, self.y = new_x, new_y
                            moved = True

                    if not moved:
                        game.message_log.add_message(f"The {self.name} is blocked and waits.", (100, 100, 100))
                else:
                    game.message_log.add_message(f"The {self.name} cannot find a path to the player.", (150, 150, 150))
        else:
            # If the player is not detected, patrol the area
            if self.patrol(game_map):
                pass # Monster patrolled

    def hp_percentage(self):
        """Returns the monster's current HP as a percentage."""
        if self.max_hp == 0:
            return 0.0
        return self.hp / self.max_hp

    def get_saving_throw_bonus(self, ability_name):
        """Calculate the saving throw bonus for the specified ability."""
        # Get the ability score based on the ability name
        ability_score = getattr(self, ability_name.lower(), 0)  # Default to 0 if not found
        modifier = (ability_score - 10) // 2  # Calculate the modifier
        # Check if the monster has proficiency in this saving throw
        if self.saving_throw_proficiencies.get(ability_name.upper(), False):
            return modifier + 2  # Assuming a base proficiency bonus of +2 for simplicity
        return modifier

    def roll_initiative(self):
        """Roll for turn order"""
        self.initiative = random.randint(1, 20)

    def distance_to(self, target_x, target_y):
        """Calculate the Chebyshev distance to another point."""
        dx = abs(self.x - target_x)
        dy = abs(self.y - target_y)
        return max(dx, dy) # Chebyshev distance (for grid-based movement)


    def detect_player(self, player, game_instance):
        """Check if the player is within detection range and line of sight."""
        distance_to_player = self.distance_to(player.x, player.y)
        is_visible_to_monster = game_instance.check_line_of_sight(self.x, self.y, player.x, player.y)
        
        if distance_to_player <= self.detection_range and is_visible_to_monster:
            self.last_known_player_position = (player.x, player.y)
            return True  # Player currently detected
        else:
            # If player is not currently visible, check if we still have a last known position
            if self.last_known_player_position:
                # If we lost sight, clear last known position and revert to patrolling
                # This is where the monster "forgets" the player
                if not game_instance.check_line_of_sight(self.x, self.y, self.last_known_player_position[0], self.last_known_player_position[1]):
                    self.last_known_player_position = None
                    self.ai_state = AI_State.CHASING # Revert to default chasing if intelligent
                    game_instance.message_log.add_message(f"The {self.name} loses track of you.", (150, 150, 150))
                return False # Player not currently detected, but might still be aggroed to last_known_position
            return False # Player not detected at all

 
    def patrol(self, game_map):
        """Move the monster along a patrol path or randomly within a defined area."""
        # Define a simple patrol path (for example, a square or a line)
        patrol_path = [(self.x + 1, self.y), (self.x, self.y + 1), (self.x - 1, self.y), (self.x, self.y - 1)]
        
        # Choose a random direction from the patrol path
        next_position = random.choice(patrol_path)

        # Check if the next position is within bounds and walkable
        if game_map.is_walkable(next_position[0], next_position[1]):
            self.x, self.y = next_position
            return True  # Successfully patrolled to the next position
        return False  # Could not move
            
    def flee(self, player, game_map, game):
        """
        Attempts to move the monster directly away from the player.
        Returns True if a move was made, False otherwise.
        """
        dx = self.x - player.x
        dy = self.y - player.y
    
        move_x = 0
        if dx > 0: move_x = 1
        elif dx < 0: move_x = -1
    
        move_y = 0
        if dy > 0: move_y = 1
        elif dy < 0: move_y = -1
    
        potential_moves = []
        if move_x != 0 and move_y != 0:
            potential_moves.append((move_x, move_y))  # Diagonal away
        if move_x != 0:
            potential_moves.append((move_x, 0))       # Horizontal away
        if move_y != 0:
            potential_moves.append((0, move_y))       # Vertical away
    
        for check_dx, check_dy in potential_moves:
            new_x, new_y = self.x + check_dx, self.y + check_dy
    
            # Check footprint clearance instead of just single tile
            if self.can_occupy_position(new_x, new_y, game_map, game.entities, exclusions=[self]):
                self.x, self.y = new_x, new_y
                return True  # Successfully fled one step
    
        return False  # Could not find a valid tile to flee to
    

    def is_adjacent_to(self, other):
        """Check if next to another entity (cardinal directions + diagonals)"""
        dx = abs(self.x - other.x)
        dy = abs(self.y - other.y)
        return dx <= 1 and dy <= 1 and (dx != 0 or dy != 0)

    def roll_damage(self, is_ranged=False):
        """
        Rolls damage based on monster's stats.
        If is_ranged=True, uses ranged attack dice.
        
        Returns total damage rolled and individual rolls for messaging.
        """
        if is_ranged:
            num_dice = self.ranged_num_dice
            die_type = self.ranged_die_type
        else:
            num_dice = self.num_damage_dice 
            die_type = self.monster_die_type
        rolls = [random.randint(1, die_type) for _ in range(num_dice)]
        return sum(rolls), rolls


    def attack(self, target, game, advantage=False, disadvantage=False):
        """Updated attack with optional telegraph phase for bosses."""
        if not target.alive:
            return

        # If monster is a boss (footprint_size > 1), telegraph an AoE instead of immediate hit
        if getattr(self, 'footprint_size', 1) > 1: 
            # Example: choose tiles around the player's current position (3x3) to telegraph
            telegraphed = []
            center_x, center_y = target.x, target.y
            for dy in (-1, 0, 1): 
                for dx in (-1, 0, 1):
                    tx, ty = center_x + dx, center_y + dy
                    if 0 <= tx < game.game_map.width and 0 <= ty < game.game_map.height:
                        telegraphed.append((tx, ty))
            self.pending_telegraph_tiles = telegraphed
            game.message_log.add_message(f"The {self.name} prepares a devastating attack!", (255, 80, 80))
            return  # Telegraph now; damage will apply at start of next turn cycle
      
        # Attack roll
        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20)
        final_d20_roll = roll1
        roll_message_part = f"a d20: {roll1}"
        attack_bonus = self.attack_bonus
        damage_modifier = self.damage_modifier

        if advantage and disadvantage:
            game.message_log.add_message(f"The {self.name} rolls with neither Advantage nor Disadvantage.", (150, 150, 150))
        elif advantage:
            final_d20_roll = max(roll1, roll2)
            roll_message_part = f"2d20 (Advantage): {roll1}, {roll2} -> {final_d20_roll}"
            game.message_log.add_message(f"The {self.name} rolls with Advantage!", (255, 200, 100))
        elif disadvantage:
            final_d20_roll = min(roll1, roll2)
            roll_message_part = f"2d20 (Disadvantage): {roll1}, {2} -> {final_d20_roll}"
            game.message_log.add_message(f"The {self.name} rolls with Disadvantage!", (150, 150, 255))
        attack_roll_total = final_d20_roll + attack_bonus
        
        # Check for critical hit/fumble
        is_critical_hit = (final_d20_roll == 20)
        is_critical_fumble = (final_d20_roll == 1)


        # Adjust target AC for evasion effects
        target_ac = target.armor_class
        if hasattr(target, 'active_status_effects'):
            for effect in target.active_status_effects:
                if isinstance(effect, EvasionBuff):
                    target_ac += effect.dodge_bonus
                    game.message_log.add_message(f"The {target.name} is evasive! Target AC: {target_ac}", (100, 255, 255))
        game.message_log.add_message(
            f"The {self.name} rolls {roll_message_part} + {attack_bonus} (Attack Bonus) = {attack_roll_total} vs AC {target_ac}",
            (255, 150, 150)
        )
        hit_successful = False
        if is_critical_hit:
            game.message_log.add_message("CRITICAL HIT!", (255, 100, 100))
            hit_successful = True
        elif is_critical_fumble:
            game.message_log.add_message("CRITICAL FUMBLE!", (150, 150, 150))
            hit_successful = False
        else:
            hit_successful = (attack_roll_total >= target_ac)


        if hit_successful:
            # Roll damage
            damage_rolls = []
            for _ in range(self.num_damage_dice * (2 if is_critical_hit else 1)):  # Roll twice for critical hits
                damage_rolls.append(random.randint(1, self.monster_die_type))

            damage_total = sum(damage_rolls) + self.damage_modifier  # Add damage modifier

            game.message_log.add_message(f"Rolls {damage_rolls} + {self.damage_modifier} (Damage Modifier) = {damage_total}", (230, 200, 150))

            # Apply damage
            damage_dealt = target.take_damage(damage_total, game)

            # Floating text
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game.floating_texts.extend([hit_text, damage_text])

            if not target.alive:
                game.message_log.add_message(f"{target.name} has been slain!", (200, 0, 0))
            else:
                hp_message = f"{target.name} has {target.hp}/{target.max_hp} HP"
                hp_color = (255, 200, 0) if target.hp > target.max_hp * 0.3 else (255, 100, 0)
                game.message_log.add_message(hp_message, hp_color)

            # --- NEW: Apply Status Effects ---
            if self.can_poison:
                if not target.make_saving_throw("CON", self.poison_dc, game):
                    target.add_status_effect("Poisoned", self.poison_duration, game, source=self)
            if self.can_acid_burn:
                if not target.make_saving_throw("DEX", self.acid_burn_dc, game): # Acid often uses Dex save
                    target.add_status_effect("AcidBurned", self.acid_burn_duration, game, source=self)
            if self.can_burn:
                if not target.make_saving_throw("DEX", self.burn_dc, game): # Fire often uses Dex save
                    target.add_status_effect("Burning", self.burn_duration, game, source=self)
            # Add more status effects here as needed (e.g., Restrained, Stunned, etc.)

        else:
            # Miss handling
            miss_messages = [
                f"The {self.name}'s attack misses!",
                f"{target.name} dodges the {self.name}'s strike!",
                f"The {self.name} swings wildly and misses!",
                f"{target.name} twists aside just in time!",
                f"The {self.name}'s blow smashes into stone instead!",
                f"{target.name} parries and deflects the strike!",
                f"The {self.name} lunges, but {target.name} slips away!",
                f"A sudden stumble throws the {self.name}'s aim wide!",
                f"{target.name} ducks beneath the attack with practiced ease!",
                f"The {self.name}'s weapon cuts only air!",
                f"With a deft step, {target.name} avoids certain harm!",
                f"The {self.name}'s strike glances harmlessly off armor!",
                f"A burst of sparks flies as the attack scrapes the wall!",
                f"{target.name} sidesteps smoothly, the attack wasted!"
            ]
            game.message_log.add_message(random.choice(miss_messages), (200, 200, 200))
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game.floating_texts.append(miss_text)


    def ranged_attack(self, target, game):
        """More powerful ranged attacks"""
        if not target.alive:
            return
       
        roll1 = random.randint(1, 20)
        final_d20_roll = roll1

        game.message_log.add_message(f"The {self.name} takes aim at {target.name}!", (255, 150, 0))
        
        # Attack roll 
        attack_roll_total = final_d20_roll + self.ranged_attack_bonus

        # Check for critical hit
        is_critical_hit = (final_d20_roll == 20)
        is_critical_fumble = (final_d20_roll == 1)


        target_ac = target.armor_class
        if hasattr(target, 'active_status_effects'):
            for effect in target.active_status_effects:
                if isinstance(effect, EvasionBuff):
                    target_ac += effect.dodge_bonus
        game.message_log.add_message(
            f"The {self.name} rolls {final_d20_roll} + {self.ranged_attack_bonus} (Attack Bonus) = {attack_roll_total} vs AC {target_ac}",
            (200, 200, 255)
        )


        hit_successful = False
        if is_critical_hit:
            crit_msgs = [
                "CRITICAL HIT! The strike lands with devastating force!",
                "A perfect blow! Critical Hit!",
                "The attack finds its mark — a Critical Hit!",
                "A savage strike! Critical damage dealt!"
            ]
            game.message_log.add_message(random.choice(crit_msgs), (255, 80, 80))
            hit_successful = True

        elif is_critical_fumble:
            fumble_msgs = [
                "CRITICAL FUMBLE! The attack goes horribly wrong!",
                "A misstep! Critical Fumble!",
                "Disaster! The strike falters into a Critical Fumble!",
                "A costly mistake — Critical Fumble!"
            ]
            game.message_log.add_message(random.choice(fumble_msgs), (150, 150, 150))
            hit_successful = False
        else:
            hit_successful = (attack_roll_total >= target_ac)

        
        if hit_successful:
            # Roll damage
            damage_rolls = []
            for _ in range(self.num_damage_dice * (2 if is_critical_hit else 1)):  # Roll twice for critical hits
                damage_rolls.append(random.randint(1, self.monster_die_type))

            damage_total = sum(damage_rolls) + self.damage_modifier  # Add damage modifier

            game.message_log.add_message(f"Rolls {damage_rolls} + {self.damage_modifier} (Damage Modifier) = {damage_total}", (230, 200, 150))

            # Apply damage
            damage_dealt = target.take_damage(damage_total, game)

            # Floating text
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game.floating_texts.extend([hit_text, damage_text])

            if not target.alive:
                game.message_log.add_message(f"{target.name} has been slain!", (200, 0, 0))
            else:
                hp_message = f"{target.name} has {target.hp}/{target.max_hp} HP"
                hp_color = (255, 200, 0) if target.hp > target.max_hp * 0.3 else (255, 100, 0)
                game.message_log.add_message(hp_message, hp_color)

            # --- NEW: Apply Status Effects (Ranged) ---
            if self.can_poison:
                if not target.make_saving_throw("CON", self.poison_dc, game):
                    target.add_status_effect("Poisoned", self.poison_duration, game, source=self)
            if self.can_acid_burn:
                if not target.make_saving_throw("DEX", self.acid_burn_dc, game):
                    target.add_status_effect("AcidBurned", self.acid_burn_duration, game, source=self)
            if self.can_burn:
                if not target.make_saving_throw("DEX", self.burn_dc, game):
                    target.add_status_effect("Burning", self.burn_duration, game, source=self)
            # Add more ranged status effects here as needed

        else:
            # Miss handling
            miss_messages = [
                f"The {self.name}'s attack misses!",
                f"{target.name} dodges the {self.name}'s attack!"
            ]
            game.message_log.add_message(random.choice(miss_messages), (200, 200, 200))
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game.floating_texts.append(miss_text)


    def take_damage(self, amount, game_instance=None, damage_type=None):
        """Handle taking damage and return actual damage taken"""
        damage_taken = amount 
        self.hp -= damage_taken
        
        # --- NEW: If monster takes damage, it knows where the player is ---
        if game_instance and game_instance.player:
            # Set last_known_player_position to player's current location
            self.last_known_player_position = (game_instance.player.x, game_instance.player.y)
            # Force AI state to chasing if it's an intelligent monster and not already fleeing/desperate
            if self.is_intelligent and self.ai_state not in [AI_State.FLEEING, AI_State.DESPERATE_FIGHT]:
                self.ai_state = AI_State.CHASING
                game_instance.message_log.add_message(f"The {self.name} is enraged and focuses on you!", (255, 100, 0))
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            
        return damage_taken

    def die(self, game_instance):
        """Handle death and return XP value"""
        return self.base_xp  # Return the XP gained

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        """Adds a status effect to the monster."""
        new_effect = None
        if effect_name == "Poisoned":
            new_effect = Poisoned(duration, source)
        # Add other status effects here if monsters can get them
        elif effect_name == "AcidBurned":
            new_effect = AcidBurned(duration, source)  
        
        elif effect_name == "Burning":
            new_effect == Burning(duration, source)      
        
        
        if new_effect:
            for existing_effect in self.active_status_effects:
                if type(existing_effect) is type(new_effect): # Check if it's the same class of effect
                    existing_effect.turns_left = new_effect.duration
                    game_instance.message_log.add_message(f"{self.name}'s {new_effect.name} effect is refreshed.", (200, 200, 255))
                    return
            
            self.active_status_effects.append(new_effect)
            new_effect.apply_effect(self, game_instance) # Call apply_effect immediately upon adding
        else:
            game_instance.message_log.add_message(f"Warning: Attempted to add unknown status effect to monster: {effect_name}", (255, 0, 0))
            print(f"Warning: Attempted to add unknown status effect to monster: {effect_name}")


    def process_status_effects(self, game_instance):
        """Processes all active status effects on the monster."""
        effects_to_remove = []
        for effect in self.active_status_effects:
            effect.apply_effect(self, game_instance) # Ensure apply_effect is called
            effect.tick_down()
            if effect.turns_left <= 0:
                effects_to_remove.append(effect)
        
        for effect in effects_to_remove:
            self.active_status_effects.remove(effect)
            effect.on_end(self, game_instance)


    def occupies_tile(self, x: int, y: int) -> bool:
        """Return True if this entity occupies the tile at (x, y).
        Supports multi-tile entities via self.footprint_size.
        Top-left anchor is at (self.x, self.y).
        """
        size = getattr(self, 'footprint_size', 1)
        return (self.x <= x < self.x + size) and (self.y <= y < self.y + size)

    def can_occupy_position(self, target_x: int, target_y: int, game_map, entities, exclusions=None) -> bool:
        """Check if this entity can occupy a top-left position with its full footprint.
        Excludes any entities in the exclusions iterable from blocking checks.
        """
        size = getattr(self, 'footprint_size', 1)
        if exclusions is None:
            exclusions = []
        # For single-tile, just defer to the normal checks
        if size <= 1:
            if not (0 <= target_x < game_map.width and 0 <= target_y < game_map.height):
                return False
            if not game_map.is_walkable(target_x, target_y):
                return False
            for entity in entities:
                if entity in exclusions or entity is self:
                    continue
                if getattr(entity, 'alive', True) and getattr(entity, 'blocks_movement', False):
                    if hasattr(entity, 'occupies_tile'):
                        if entity.occupies_tile(target_x, target_y):
                            return False
                    elif entity.x == target_x and entity.y == target_y:
                        return False
            return True

        # Multi-tile clearance
        for offset_y in range(size):
            for offset_x in range(size):
                tile_x = target_x + offset_x
                tile_y = target_y + offset_y
                if not (0 <= tile_x < game_map.width and 0 <= tile_y < game_map.height):
                    return False
                if not game_map.is_walkable(tile_x, tile_y):
                    return False
                for entity in entities:
                    if entity in exclusions or entity is self:
                        continue
                    if getattr(entity, 'alive', True) and getattr(entity, 'blocks_movement', False):
                        if hasattr(entity, 'occupies_tile'):
                            if entity.occupies_tile(tile_x, tile_y):
                                return False
                        elif getattr(entity, 'x', None) == tile_x and getattr(entity, 'y', None) == tile_y:
                            return False
        return True

class Mimic(Monster):
    def __init__(self, x, y, disguise_char, initial_color): 
        super().__init__(x, y, disguise_char, 'Mimic', initial_color) 
        
        self.disguised = True
        
        self._disguise_char = disguise_char 
        self._disguise_color = initial_color 
        if disguise_char == 'K': # Crate
            self.revealed_char = 'K' # Generic Mimic char
        elif disguise_char == 'B': # Barrel
            self.revealed_char = 'B' 
        elif disguise_char == 'C': # Chest
            self.revealed_char = 'M' 
        else:
            self.revealed_char = 'M' 
        self.revealed_color = (255, 0, 0) 
        
        self.hp = 58 # Mimic specific HP
        self.max_hp = 58
        self.attack_bonus = 5
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 8
        self.blocks_movement = True
        self.can_acid_burn = True
        self.acid_burn_dc = 12
        self.acid_burn_duration = 3
        self.acid_burn_damage_per_turn = 3
        self.damage_modifier = 3
        self.num_damage_dice = 1
        # Mimics are not "intelligent" in the sense of fleeing, they are ambush predators
        self.is_intelligent = False 

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        } 

    def take_damage(self, amount, game_instance, damage_type=None):
        """
        Mimic's take_damage method.
        If disguised and takes damage, it reveals itself.
        """
        if self.disguised:
            game_instance.message_log.add_message(f"You strike the {self.name}!", (255, 165, 0))
            self.reveal(game_instance) 
            
        damage_taken = super().take_damage(amount, game_instance, damage_type) # Pass game_instance here

        if not self.alive and not self.disguised: # Only if it died and was already revealed
            game_instance.message_log.add_message(f"The {self.name} shudders and collapses!", (255, 0, 0))

        return damage_taken

    def reveal(self, game_instance):
        """Mimic fully reveals its true form."""
        if self.disguised:
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealing. Current char (before change): {self.char}")
            self.disguised = False
            
            self.char = self.revealed_char 
            self.color = self.revealed_color 
            
            game_instance.message_log.add_message("The object suddenly sprouts teeth and eyes! It's a MIMIC!", (255, 0, 0))
            game_instance.message_log.add_message("Prepare for battle!", (255, 100, 100))
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealed. New char: {self.char}, color: {self.color}")
            # Mimic immediately attacks the player if adjacent after revealing
            if self.is_adjacent_to(game_instance.player):
                self.attack(game_instance.player, game_instance)
            
            if self not in game_instance.entities:
                game_instance.entities.append(self)
                print(f"DEBUG: Mimic added to game.entities.")
            if self not in game_instance.turn_order:
                self.roll_initiative()
                game_instance.turn_order.append(self)
                game_instance.turn_order = sorted(game_instance.turn_order, key=lambda e: e.initiative, reverse=True)
                print(f"DEBUG: Mimic added to game.turn_order.")
            
            if self in game_instance.game_map.items_on_ground:
                game_instance.game_map.items_on_ground.remove(self)
                print(f"DEBUG: Mimic removed from game_map.items_on_ground upon reveal.")
            
            from world.tile import floor # Import floor tile
            game_instance.game_map.tiles[self.y][self.x] = floor
            print(f"DEBUG: MimicTile at ({self.x},{self.y}) replaced with floor tile.")
            
            game_instance.update_fov()

    def take_turn(self, player, game_map, game):
        """Mimic's turn logic."""
        if not self.alive:
            return
        
        if self.disguised: # Should not happen if handle_player_action works
            return
        
        # If not disguised, behave like a normal monster (Stage 2 combat form)
        super().take_turn(player, game_map, game)


# --- MONSTER CLASSES ---

class GiantRat(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'R', 'Giant Rat', (0, 130, 8))
        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 12
        self.base_xp = 25
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 8
        self.num_damage_dice = 1
        # self.can_disease = True  # Filth Fever (homebrew disease effect)
        self.is_intelligent = False # Not intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Ooze(Monster):  
    def __init__(self, x, y):
        super().__init__(x, y, 'OZ', 'Ooze', (100, 100, 100))
        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 2
        self.armor_class = 8
        self.base_xp = 100
        self.monster_die_type = 6
        self.num_damage_dice = 2
        self.acid_burn_dc = 14
        self.acid_burn_duration = 4
        self.damage_modifier = 1
        self.detection_range = 4
        self.acid_burn_damage_per_turn = 3
        self.is_intelligent = False # Not intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Goblin(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GB', 'Goblin', (0, 255, 0))
        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 50
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class GoblinArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GA', 'Goblin Archer', (0, 200, 0))
        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 50
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2  # Base ranged attack bonus
        self.range = 4  # Max range for ranged attacks
        self.ranged_die_type = 6  # Base die type for ranged attacks
        self.ranged_num_dice = 1  # Number of damage dice for ranged attacks
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Skeleton(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'SK', 'Skeleton', (200, 200, 200))
        self.hp = 13
        self.max_hp = 13
        self.attack_bonus = 2
        self.armor_class = 13
        self.base_xp = 50
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 4
        self.num_damage_dice = 1
        self.is_intelligent = False # Not intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class SkeletonArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'SA', 'Skeleton Archer', (180, 180, 180))
        self.hp = 13
        self.max_hp = 13
        self.attack_bonus = 2
        self.armor_class = 13
        self.base_xp = 50
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2  # Base ranged attack bonus
        self.range = 5  # Max range for ranged attacks
        self.ranged_die_type = 6  # Base die type for ranged attacks
        self.ranged_num_dice = 1  # Number of damage dice for ranged attacks
        self.is_intelligent = False # Not intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class Orc(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'OR', 'Orc', (0, 128, 0))
        self.hp = 15
        self.max_hp = 15
        self.attack_bonus = 3
        self.armor_class = 13
        self.base_xp = 100
        self.monster_die_type = 12
        self.damage_modifier = 3
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class Centaur(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'CE', 'Centaur', (139, 69, 19))
        self.hp = 45
        self.max_hp = 45
        self.attack_bonus = 3
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 8
        self.damage_modifier = 4
        self.detection_range = 6
        self.num_damage_dice = 2
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class CentaurArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'CA', 'Centaur Archer', (160, 82, 45))
        self.hp = 45
        self.max_hp = 45
        self.attack_bonus = 3
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 6
        self.damage_modifier = 3
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2  # Base ranged attack bonus
        self.range = 5  # Max range for ranged attacks
        self.ranged_die_type = 8  # Base die type for ranged attacks
        self.ranged_num_dice = 1  # Number of damage dice for ranged attacks
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Troll(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'TR', 'Troll', (0, 100, 0))
        self.hp = 84
        self.max_hp = 84
        self.attack_bonus = 4
        self.armor_class = 15
        self.base_xp = 1800
        self.monster_die_type = 6
        self.damage_modifier = 4
        self.detection_range = 8
        self.num_damage_dice = 2
        # self.regeneration = True
        # self.regen_amount = 10  # per turn unless acid/fire damage
        self.is_intelligent = False # Not intelligent enough to flee (more brute force)

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Lizardfolk(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'LF', 'Lizardfolk', (46, 139, 87))
        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 100
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        self.can_poison = True
        self.poison_dc = 13
        self.poison_duration = 3
        self.poison_damage_per_turn = 2
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class LizardfolkArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'LA', 'Lizardfolk Archer', (60, 179, 113))
        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 100
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2  # Base ranged attack bonus
        self.range = 5  # Max range for ranged attacks
        self.ranged_die_type = 8  # Base die type for ranged attacks
        self.ranged_num_dice = 1  # Number of damage dice for ranged attacks
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class GiantSpider(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GS', 'Giant Spider', (50, 50, 50))
        self.hp = 26
        self.max_hp = 26
        self.attack_bonus = 3
        self.armor_class = 14
        self.base_xp = 200
        self.monster_die_type = 8
        self.damage_modifier = 3
        self.detection_range = 15
        self.num_damage_dice = 1
        self.can_poison = True
        self.poison_dc = 11
        self.poison_duration = 3
        self.poison_damage_per_turn = 4
        self.web_restrain = True
        self.is_intelligent = False # More instinct-driven

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Beholder(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'BH', 'Beholder', (150, 0, 150))
        self.hp = 180
        self.max_hp = 180
        self.attack_bonus = 7
        self.armor_class = 18
        self.base_xp = 10000
        self.monster_die_type = 8
        self.damage_modifier = 7
        self.detection_range = 8
        self.num_damage_dice = 4
        self.is_ranged = True
        self.ranged_attack_bonus = 2  # Base ranged attack bonus
        self.range = 6  # Max range for ranged attacks
        self.ranged_die_type = 8  # Base die type for ranged attacks
        self.ranged_num_dice = 4  # Number of damage dice for ranged attacks
        self.footprint_size = 2
        # self.eye_ray_effects = ["charm", "paralyze", "petrify", "fear", "disintegrate"]
        self.is_intelligent = True # Highly intelligent

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class LargeOoze(Monster):  # Gelatinous Cube
    def __init__(self, x, y):
        super().__init__(x, y, 'LO', 'Large Ooze', (34, 139, 34))
        self.hp = 85
        self.max_hp = 85
        self.attack_bonus = 4
        self.armor_class = 7
        self.base_xp = 1800
        self.monster_die_type = 8
        self.damage_modifier = 6
        self.detection_range = 4
        self.num_damage_dice = 2
        self.acid_burn_dc = 14
        self.acid_burn_duration = 4
        self.acid_burn_damage_per_turn = 4
        self.split_on_slash = True
        self.is_intelligent = False # Mindless

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class DragonWhelp(Monster):  # Wyrmling
    def __init__(self, x, y):
        super().__init__(x, y, 'DRA', 'Dragon Whelp', (255, 0, 0))
        self.hp = 32
        self.max_hp = 32
        self.attack_bonus = 4
        self.armor_class = 17
        self.base_xp = 700
        self.monster_die_type = 10
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        # self.breath_weapon = True
        # self.breath_dc = 13
        # self.breath_damage = "4d6 fire"
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Owlbear(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'OB', 'Owlbear', (139, 69, 19))
        self.hp = 59
        self.max_hp = 59
        self.attack_bonus = 5
        self.armor_class = 13
        self.base_xp = 700
        self.monster_die_type = 10
        self.damage_modifier = 5
        self.detection_range = 5
        self.num_damage_dice = 2
        self.is_intelligent = False # More beast-like

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Demogorgon(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'DG', 'Demogorgon', (72, 61, 139))
        self.hp = 496
        self.max_hp = 496
        self.attack_bonus = 12
        self.armor_class = 22
        self.base_xp = 155000
        self.monster_die_type = 12
        self.damage_modifier = 7
        self.detection_range = 8
        self.num_damage_dice = 3
        self.footprint_size = 2
        # self.legendary_resistance = 3
        # self.frightful_presence = True
        self.is_intelligent = True # Highly intelligent, but likely never flees (boss)

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Grick(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GK', 'Grick', (105, 105, 105))
        self.hp = 27
        self.max_hp = 27
        self.attack_bonus = 3
        self.armor_class = 14
        self.base_xp = 450
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 15
        self.num_damage_dice = 2
        # self.resist_nonmagical = True
        self.is_intelligent = False # Ambush predator, not intelligent

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class GibberingMouther(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GM', 'Gibbering Mouther', (200, 100, 100))
        self.hp = 67
        self.max_hp = 67
        self.attack_bonus = 2
        self.armor_class = 9
        self.base_xp = 450
        self.monster_die_type = 6
        self.damage_modifier = 1
        self.detection_range = 4
        self.num_damage_dice = 2
        # self.maddening_babble = True
        # self.prone_ground = True
        self.is_intelligent = False # Mindless aberration

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class MindFlayer(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MF', 'Mind Flayer', (75, 0, 130))
        self.hp = 71
        self.max_hp = 71
        self.attack_bonus = 7
        self.armor_class = 15
        self.base_xp = 2900
        self.monster_die_type = 10
        self.num_damage_dice = 2
        self.detection_range = 6
        self.damage_modifier = 4
        self.is_ranged = True
        self.ranged_attack_bonus = 7  # Base ranged attack bonus
        self.range = 5  # Max range for ranged attacks
        self.ranged_die_type = 10  # Base die type for ranged attacks
        self.ranged_num_dice = 2  # Number of damage dice for ranged attacks
        # self.psionic_blast_dc = 15
        # self.psionic_stun_duration = 1
        self.is_intelligent = True # Highly intelligent

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Minotaur(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MN', 'Minotaur', (139, 0, 0))
        self.hp = 76
        self.max_hp = 76
        self.attack_bonus = 4
        self.armor_class = 14
        self.base_xp = 700
        self.monster_die_type = 12
        self.damage_modifier = 4 
        self.detection_range = 6
        self.num_damage_dice = 2
        # self.charge_attack = True
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Wererat(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'WR', 'Wererat', (169, 169, 169))
        self.hp = 33
        self.max_hp = 33
        self.attack_bonus = 2
        self.armor_class = 12
        self.base_xp = 100
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 6
        self.num_damage_dice = 1
        # self.shapechanger = True
        # self.disease = True
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Wolf(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'WF', 'Wolf', (112, 128, 144))
        self.hp = 11
        self.max_hp = 11
        self.attack_bonus = 2
        self.armor_class = 13
        self.base_xp = 50
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 8
        self.num_damage_dice = 1
        # self.knock_prone_dc = 11
        self.is_intelligent = False # More beast-like

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Yochlol(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'YL', 'Yochlol', (112, 128, 144))
        self.hp = 136
        self.max_hp = 136
        self.attack_bonus = 3
        self.armor_class = 15
        self.base_xp = 5900
        self.monster_die_type = 8
        self.damage_modifier = 3
        self.detection_range = 12
        self.num_damage_dice = 1
        self.can_poison = True
        self.poison_dc = 10
        self.poison_duration = 3
        self.poison_damage_per_turn = 4
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class BlueSlaad(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'BS', 'BlueSlaad', (112, 128, 144))
        self.hp = 123
        self.max_hp = 123
        self.attack_bonus = 5
        self.armor_class = 15
        self.base_xp = 2900
        self.monster_die_type = 8
        self.damage_modifier = 5
        self.detection_range = 6
        self.num_damage_dice = 2
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Drider(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'DD', 'Drider', (112, 128, 144))
        self.hp = 123
        self.max_hp = 123
        self.attack_bonus = 3
        self.armor_class = 19
        self.base_xp = 2300
        self.monster_die_type = 6
        self.damage_modifier = 3
        self.detection_range = 12
        self.num_damage_dice = 3
        self.is_intelligent = True # Intelligent enough to flee

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        
