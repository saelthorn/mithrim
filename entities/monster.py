import random
from core.pathfinding import astar
from core.status_effects import Poisoned, AcidBurned, Burning, PowerAttackBuff, EvasionBuff
from items.items import Potion, Weapon, Armor, Chest, lesser_healing_potion, greater_healing_potion, wood_plank, meat, green_apple, fromage, bread, mushroom, CampfireKit
from world.tile import floor
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
        if target is None or not target.alive:
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
        if target is None or not target.alive:
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


    def occupies_tile(self, x, y):
        """
        Returns True if the given (x, y) coordinate is within the monster's footprint.
        """
        size = getattr(self, 'footprint_size', 1)
        return (self.x <= x < self.x + size) and (self.y <= y < self.y + size)

    def is_adjacent_to(self, other_entity):
        """
        Checks if this monster is adjacent (including diagonals) to another entity,
        considering the footprint size of both.
        """
        size_self = getattr(self, 'footprint_size', 1)
        size_other = getattr(other_entity, 'footprint_size', 1)

        self_tiles = [(self.x + dx, self.y + dy) for dx in range(size_self) for dy in range(size_self)]
        other_tiles = [(other_entity.x + dx, other_entity.y + dy) for dx in range(size_other) for dy in range(size_other)]

        for (x1, y1) in self_tiles:
            for (x2, y2) in other_tiles:
                # Chebyshev distance == 1 means adjacent including diagonals
                if max(abs(x1 - x2), abs(y1 - y2)) == 1:
                    return True
        return False

    def get_footprint_tiles(self, x=None, y=None):
        """
        Returns a list of (x, y) tuples representing all tiles occupied by the monster's footprint.
        If x and y are None, uses current position.
        """
        base_x = x if x is not None else self.x
        base_y = y if y is not None else self.y
        size = getattr(self, 'footprint_size', 1)
        return [(base_x + dx, base_y + dy) for dx in range(size) for dy in range(size)]

    def get_adjacent_tiles_in_direction(self, dx, dy):
        """
        Returns a set of tiles (x, y) that are adjacent to the monster's footprint in the direction (dx, dy).
        This helps identify which tiles the monster would move into or need to destroy.
        """
        footprint_tiles = self.get_footprint_tiles()
        adjacent_tiles = set()

        # For each tile in footprint, check the tile in the movement direction
        for (x, y) in footprint_tiles:
            adj_x = x + dx
            adj_y = y + dy
            adjacent_tiles.add((adj_x, adj_y))

        return adjacent_tiles

    def can_move_to(self, new_x, new_y, game_map, game):
        """
        Checks if the monster can move to (new_x, new_y).
        Destroys destructible tiles adjacent to the footprint in the movement direction.
        Returns True if move is possible (after destroying obstacles), False otherwise.
        """
        size = getattr(self, 'footprint_size', 1)
        current_footprint = self.get_footprint_tiles()
        new_footprint = [(new_x + dx, new_y + dy) for dx in range(size) for dy in range(size)]

        # Calculate movement delta
        dx = new_x - self.x
        dy = new_y - self.y

        # Check map bounds for new footprint
        for (tx, ty) in new_footprint:
            if not (0 <= tx < game_map.width and 0 <= ty < game_map.height):
                return False

        # Check for blocking entities in new footprint
        for entity in game.entities:
            if entity != self and entity.alive and entity.blocks_movement:
                for (tx, ty) in new_footprint:
                    if hasattr(entity, 'occupies_tile'):
                        if entity.occupies_tile(tx, ty):
                            return False
                    else:
                        if entity.x == tx and entity.y == ty:
                            return False

        # Identify tiles adjacent to footprint in movement direction
        adjacent_tiles = self.get_adjacent_tiles_in_direction(dx, dy)

        # Destroy destructible tiles in adjacent tiles blocking the way
        for (ax, ay) in adjacent_tiles:
            if not (0 <= ax < game_map.width and 0 <= ay < game_map.height):
                continue
            tile = game_map.tiles[ay][ax]
            if not game_map.is_walkable(ax, ay):
                if tile.destructible:
                    # Destroy the tile
                    game.message_log.add_message(f"The massive {self.name} smashes the {tile.name}!", (255, 165, 0))
                    game_map.tiles[ay][ax] = floor
                    game.minimap_needs_redraw = True
                    game.floating_texts.append(FloatingText(ax, ay, "SMASH!", (255, 100, 0)))

                    if tile.name in ["Crate", "Barrel"]:
                        import random
                        if random.random() < 0.70:
                            new_junk = wood_plank.__class__(
                                name=wood_plank.name,
                                char=wood_plank.char,
                                color=wood_plank.color,
                                description=wood_plank.description
                            )
                            new_junk.x = ax
                            new_junk.y = ay
                            game_map.items_on_ground.append(new_junk)
                        elif random.random() < 0.20:
                            new_food = meat.__class__(
                                name=meat.name,
                                char=meat.char,
                                color=meat.color,
                                description=meat.description,
                                healing_value=meat.healing_value,
                                price=meat.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.35:
                            new_food = green_apple.__class__(
                                name=green_apple.name,
                                char=green_apple.char,
                                color=green_apple.color,
                                description=green_apple.description,
                                healing_value=green_apple.healing_value,
                                price=green_apple.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.25:
                            new_food = fromage.__class__(
                                name=fromage.name,
                                char=fromage.char,
                                color=fromage.color,
                                description=fromage.description,
                                healing_value=fromage.healing_value,
                                price=fromage.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.30:
                            new_food = bread.__class__(
                                name=bread.name,
                                char=bread.char,
                                color=bread.color,
                                description=bread.description,
                                healing_value=bread.healing_value,
                                price=bread.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.40:
                            new_food = mushroom.__class__(
                                name=mushroom.name,
                                char=mushroom.char,
                                color=mushroom.color,
                                description=mushroom.description,
                                healing_value=mushroom.healing_value,
                                price=mushroom.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)

                else:
                    # Tile is not walkable and not destructible
                    return False

        # Finally, check that all tiles in new footprint are walkable (after destruction)
        for (tx, ty) in new_footprint:
            if not game_map.is_walkable(tx, ty):
                return False

        return True

    def take_turn(self, player, game_map, game):
        """Handle monster's combat and movement"""
        if not self.alive:
            return

        # Resolve telegraphed attacks first
        if getattr(self, 'pending_telegraph_tiles', None):
            tiles = list(self.pending_telegraph_tiles)
            self.pending_telegraph_tiles = []
            for tx, ty in tiles:
                if player.x == tx and player.y == ty and player.alive:
                    dmg = max(1, getattr(self, 'damage_modifier', 2) + random.randint(1, 20))
                    player.take_damage(dmg, game, damage_type='fire')
                    game.floating_texts.append(FloatingText(tx, ty, f"-{dmg}", (255, 80, 80)))
            return

        self.process_status_effects(game)
        if not self.alive:
            return

        if not self.is_active:
            if self.sleep_cooldown > 0:
                self.sleep_cooldown -= 1
            return

        player_detected = self.detect_player(player, game)

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
        else:
            self.ai_state = AI_State.CHASING

        distance_to_player = self.distance_to(player.x, player.y)
        player_detected = self.detect_player(player, game)

        if self.ai_state == AI_State.FLEEING:
            if self.flee(player, game_map, game):
                return

        if self.ai_state == AI_State.DESPERATE_FIGHT:
            game.message_log.add_message(f"The {self.name} is desperate and fights on!", (255, 100, 100))

            if self.is_ranged and distance_to_player <= self.range and game.check_line_of_sight(self.x, self.y, player.x, player.y):
                self.ranged_attack(player, game)
                return
            elif self.is_adjacent_to(player):
                self.attack(player, game)
                return
            else:
                path = astar(
                    game_map,
                    (self.x, self.y),
                    (player.x, player.y),
                    entities=[e for e in game.entities if e != self and e != player and e.alive and e.blocks_movement],
                    moving_entity=self
                )
                if path and len(path) > 1:
                    next_step = path[1]
                    new_x, new_y = next_step

                    if self.can_move_to(new_x, new_y, game_map, game):
                        self.x = new_x
                        self.y = new_y
                    else:
                        game.message_log.add_message(f"The {self.name} is blocked and cannot reach {player.name}!", (100, 100, 100))
                else:
                    game.message_log.add_message(f"The {self.name} cannot find a path to {player.name}!", (150, 150, 150))
                return

        if player_detected:
            if self.is_ranged and distance_to_player <= self.range and game.check_line_of_sight(self.x, self.y, player.x, player.y):
                self.ranged_attack(player, game)
                return

            if self.is_adjacent_to(player):
                self.attack(player, game)
                return

            target_pos = (player.x, player.y) if game.check_line_of_sight(self.x, self.y, player.x, player.y) else self.last_known_player_position

            if target_pos:
                path = astar(
                    game_map,
                    (self.x, self.y),
                    target_pos,
                    entities=[e for e in game.entities if e != self and e.alive and e.blocks_movement],
                    moving_entity=self
                )
                if path and len(path) > 1:
                    next_step = path[1]
                    new_x, new_y = next_step

                    if self.can_move_to(new_x, new_y, game_map, game):
                        self.x = new_x
                        self.y = new_y
                    else:
                        game.message_log.add_message(f"The {self.name} is blocked and waits.", (100, 100, 100))
                else:
                    # Pathfinding failed: try greedy direct movement towards player
                    dx = player.x - self.x
                    dy = player.y - self.y

                    step_x = 0
                    step_y = 0

                    if dx != 0:
                        step_x = dx // abs(dx)
                    if dy != 0:
                        step_y = dy // abs(dy)

                    candidates = []
                    if step_x != 0 and step_y != 0:
                        candidates.append((self.x + step_x, self.y + step_y))  # diagonal
                    if step_x != 0:
                        candidates.append((self.x + step_x, self.y))
                    if step_y != 0:
                        candidates.append((self.x, self.y + step_y))

                    moved = False
                    for nx, ny in candidates:
                        if not (0 <= nx < game_map.width and 0 <= ny < game_map.height):
                            continue

                        if self.can_move_to(nx, ny, game_map, game):
                            self.x = nx
                            self.y = ny
                            moved = True
                            break

                    if not moved:
                        game.message_log.add_message(f"The {self.name} is blocked and waits.", (100, 100, 100))
            else:
                self.patrol(game_map)


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
        
        self.hp = 48 # Mimic specific HP
        self.max_hp = 48
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

class RedDragon(Monster):  
    def __init__(self, x, y):
        super().__init__(x, y, 'RDR', 'Red Dragon', (255, 0, 0))
        self.hp = 256
        self.max_hp = 256
        self.attack_bonus = 4
        self.armor_class = 19
        self.base_xp = 18000
        self.monster_die_type = 10
        self.damage_modifier = 6
        self.detection_range = 8
        self.num_damage_dice = 2
        self.is_intelligent = True # Intelligent enough to flee


        self.is_ranged = True
        self.ranged_attack_bonus = 5  # Base ranged attack bonus
        self.range = 6  # Max range for ranged attacks
        self.ranged_die_type = 6  # Base die type for ranged attacks
        self.ranged_num_dice = 1  # Number of damage dice for ranged attacks
        self.footprint_size = 3

        self.can_burn = True
        self.burn_dc = 17
        self.burn_damage_per_turn = 6
        self.burn_duration = 4
        self.burn

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": True,
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
        self.footprint_size = 3
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

class RedSlaad(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'RS', 'Red Slaad', (180, 30, 30))  # Deep red

        self.hp = 93
        self.max_hp = 93
        self.attack_bonus = 6
        self.armor_class = 14
        self.base_xp = 1800
        self.monster_die_type = 6   # Claw damage (1d6+4)
        self.num_damage_dice = 2    # Claw: 2d6+4 each
        self.damage_modifier = 4
        self.detection_range = 6
        self.is_intelligent = False  # Bestial cunning, not strategic

        # Claw carries a disease (Chaos Phage / Egg Implant)
        # self.disease = True
        # self.disease_dc = 14
        # self.disease_effect = "Implants egg → Spawns Blue Slaad on death"
        
        self.saving_throw_proficiencies = {
            "STR": True,   # +4 base
            "DEX": False,
            "CON": True,   # +3 base
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class DeathSlaad(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'DS', 'Death Slaad', (80, 0, 120))  # Black-purple skin

        self.hp = 170
        self.max_hp = 170
        self.attack_bonus = 8
        self.armor_class = 18
        self.base_xp = 5900
        self.monster_die_type = 8   # Claw/Bite with d8s
        self.num_damage_dice = 2    # 2d8+5 per claw
        self.damage_modifier = 5
        self.detection_range = 8
        self.is_intelligent = True  # Scheming and malicious

        # Shapechanger trait
        # self.shapechanger = True  # Can polymorph into humanoid

        # Spellcasting (innate)
        # self.spells = ["Fireball", "Fear", "Invisibility", "Detect Magic"]

        # Claw carries Chaos Phage (disease)
        # self.disease = True
        # self.disease_dc = 15
        # self.disease_effect = "Chaotic mutation → Transformation"

        self.saving_throw_proficiencies = {
            "STR": True,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": True,
        }

class MyconidSprout(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MS', 'Myconid Sprout', (120, 200, 120))  # Pale green mushroomy look

        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 10
        self.base_xp = 50
        self.monster_die_type = 4   # Fist attack (1d4)
        self.num_damage_dice = 1
        self.damage_modifier = 0
        self.detection_range = 4
        self.is_intelligent = False  # Instinctual, childlike

        # Status Effect: Pacifying Spores
        # self.can_pacify = True
        # self.pacify_dc = 11
        # self.pacify_duration = 1d4 rounds
        # Effect: Target becomes stunned

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }


class MyconidAdult(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MA', 'Myconid Adult', (80, 150, 80))  # Darker green/brown cap

        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 3
        self.armor_class = 12
        self.base_xp = 100
        self.monster_die_type = 6   # Fist attack (1d6+1)
        self.num_damage_dice = 1
        self.damage_modifier = 1
        self.detection_range = 5
        self.is_intelligent = True  # Can communicate telepathically (via spores)

        # Status Effect: Pacifying Spores
        # self.can_pacify = True
        # self.pacify_dc = 12
        # self.pacify_duration = 1d4 rounds
        # Effect: Target becomes stunned

        # Rapport Spores (telepathic network)
        # self.can_share_thoughts = True
        # Party-wide communication if close

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": True,
            "INT": False,
            "WIS": True,
            "CHA": False,
        }

class Mezzoloth(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MZ', 'Mezzoloth', (120, 60, 0))  # Dark brown/orange carapace

        self.hp = 75
        self.max_hp = 75
        self.attack_bonus = 6
        self.armor_class = 18
        self.base_xp = 1800
        self.monster_die_type = 6   # Claw attacks
        self.num_damage_dice = 2    # 2d6+3 per claw
        self.damage_modifier = 3
        self.detection_range = 8
        self.is_intelligent = True  # Tactical mercenary

        # Multiattack: two claw attacks per turn

        # Status Effects / Abilities:
        # self.can_poison_cloud = True
        # self.poison_cloud_dc = 14
        # self.poison_duration = 1 minute
        # self.poison_damage = "4d10 poison"
        # (Once per day — fills a 10 ft. radius with toxic gas)

        # Teleport (Innate ability, recharge 4–6)
        # self.can_teleport = True
        # Range: 60 ft.

        self.saving_throw_proficiencies = {
            "STR": True,   # Good Strength saves
            "DEX": False,
            "CON": True,   # Fiend toughness
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class Gauth(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GU', 'Gauth', (200, 150, 50))  # Gold/orange orb, distinct from beholder

        self.hp = 67
        self.max_hp = 67
        self.attack_bonus = 5
        self.armor_class = 15
        self.base_xp = 2300
        self.monster_die_type = 8   # Bite attack (1d8+2)
        self.num_damage_dice = 1
        self.damage_modifier = 2
        self.detection_range = 8
        self.is_intelligent = True  # Scheming, paranoid

        # Traits
        # Eye Rays (roll d6 each turn, fire 2 rays at random targets):
        # 1. Devour Magic Ray (suppresses magic item, DC 14)
        # 2. Enervation Ray (4d8 necrotic, DC 14 half)
        # 3. Paralyzing Ray (target paralyzed 1 min, DC 14 save)
        # 4. Fear Ray (frightened for 1 min, DC 14 save)
        # 5. Sleep Ray (unconscious 1 min, DC 14 save)
        # 6. Telekinetic Ray (move creature 30 ft, DC 14 resist)

        # Limited Anti-Magic Cone (like beholder, but only 150-degree arc)
        # self.anti_magic_cone = True
        # Range: 30 ft.

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": True,
            "CHA": True,
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

class Arasta(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'AR', 'Arasta', (40, 0, 40))  # Dark purple-black spider goddess

        self.hp = 300
        self.max_hp = 300
        self.attack_bonus = 10
        self.armor_class = 19
        self.base_xp = 33000
        self.monster_die_type = 12   # 2d12+6 bite or claw
        self.num_damage_dice = 2
        self.damage_modifier = 6
        self.detection_range = 10
        self.is_intelligent = True  # Scheming, divine hatred
        self.footprint_size = 4

        # Legendary Resistance (3/day) – auto succeed a failed saving throw
        # self.legendary_resistances = 3

        # Web of Hair (Recharge 5–6): restrains creatures in a 60 ft. cone
        # self.web_dc = 18
        # self.web_duration = 1 minute
        # self.web_damage = "restrained + poison"

        # Spider Swarm Spawn (lair action): summons 1d4 spider swarms each round

        # Bite attack: 2d12+6 piercing + 4d8 poison (poison DC 18)
        self.can_poison = True
        self.poison_dc = 18
        self.poison_duration = 4
        self.poison_damage_per_turn = 8

        # Mythic Trait (if reduced to 0 HP once, regain 200 HP and new abilities unlock)
        # Example: Aura of Webs – terrain becomes difficult terrain, enemies slowed.

        self.saving_throw_proficiencies = {
            "STR": True,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": True,
            "CHA": False,
        }
