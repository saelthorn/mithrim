# MultipleFiles/monster.py
import random
from core.pathfinding import astar
from core.status_effects import Poisoned, AcidBurned, PowerAttackBuff, EvasionBuff
from core.floating_text import FloatingText 

class Monster:
    def __init__(self, x, y, char, name, color):
        # super().__init__() # This line is not needed if Monster does not inherit from another class
        
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.alive = True
        self.hp = 10
        self.max_hp = 10
        self.attack_power = 2 # Melee attack power
        self.armor_class = 11
        self.base_xp = 10
        self.initiative = 0
        self.blocks_movement = True
        self.active_status_effects = []
        
        # Ranged attack specific attributes (default to 0/False)
        self.is_ranged = False
        self.ranged_attack_power = 0
        self.range = 0 # Max range for ranged attacks

        # Poison specific attributes
        self.can_poison = False
        self.poison_dc = 10
        self.poison_duration = 3
        self.poison_damage_per_turn = 2

        # Acid burn specific attributes
        self.can_acid_burn = False
        self.acid_burn_dc = 10
        self.acid_burn_duration = 3
        self.acid_burn_damage_per_turn = 3

    def roll_initiative(self):
        """Roll for turn order"""
        self.initiative = random.randint(1, 20)

    def distance_to(self, target_x, target_y):
        """Calculate the Chebyshev distance to another point."""
        dx = abs(self.x - target_x)
        dy = abs(self.y - target_y)
        return max(dx, dy) # Chebyshev distance (for grid-based movement)

    def take_turn(self, player, game_map, game):
        """Handle monster's combat and movement"""
        if not self.alive:
            print(f"DEBUG: {self.name} is dead, skipping turn.") # <--- ADD THIS
            return

        # Process status effects at the start of the monster's turn
        self.process_status_effects(game)
        if not self.alive: # Check if monster died from status effect
           print(f"DEBUG: {self.name} died from status effect, skipping turn.") # <--- ADD THIS
           return

        # Check if adjacent to player (including diagonals)
        if self.is_adjacent_to(player):
            print(f"DEBUG: {self.name} is adjacent to player. Calling attack().") # <--- ADD THIS
            self.attack(player, game) # Use base melee attack
            return

        # If monster has ranged attack, check if player is in range and line of sight
        if self.is_ranged:
            distance_to_player = self.distance_to(player.x, player.y)
            if distance_to_player <= self.range and game.check_line_of_sight(self.x, self.y, player.x, player.y):
                print(f"DEBUG: {self.name} is ranged and player in LOS. Calling ranged_attack().") # <--- ADD THIS
                self.ranged_attack(player, game)
                return

        # Otherwise, move toward player using A* pathfinding
        print(f"DEBUG: {self.name} is moving towards player.") # <--- ADD THIS
        other_entities = [e for e in game.entities if e != self and e != player and e.alive and e.blocks_movement]

        path = astar(game_map, (self.x, self.y), (player.x, player.y), entities=other_entities)

        if path and len(path) > 1:
            next_step = path[1]
            new_x, new_y = next_step

            is_blocked = False
            for entity in game.entities:
                if entity != self and entity.x == new_x and entity.y == new_y and entity.alive and entity.blocks_movement:
                    is_blocked = True
                    break

            if not is_blocked:
                self.x, self.y = new_x, new_y
                print(f"DEBUG: {self.name} moved to ({self.x},{self.y}).") # <--- ADD THIS
            else:
                game.message_log.add_message(f"The {self.name} is blocked and waits.", (100, 100, 100))
                print(f"DEBUG: {self.name} is blocked.") # <--- ADD THIS
        else:
            print(f"DEBUG: {self.name} found no path or no next step.") # <--- ADD THIS


    def is_adjacent_to(self, other):
        """Check if next to another entity (cardinal directions + diagonals)"""
        dx = abs(self.x - other.x)
        dy = abs(self.y - other.y)
        return dx <= 1 and dy <= 1 and (dx != 0 or dy != 0)

    def attack(self, target, game, advantage=False, disadvantage=False):
        """Attack a target and show combat messages, including dice rolls, crits, and fumbles."""
        if not target.alive:
            return

        # --- Monster Attack Roll ---
        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20) 

        final_d20_roll = roll1
        roll_message_part = f"a d20: {roll1}"

        if advantage and disadvantage:
            game.message_log.add_message(f"The {self.name} rolls with neither Advantage nor Disadvantage.", (150, 150, 150))
        elif advantage:
            final_d20_roll = max(roll1, roll2)
            roll_message_part = f"2d20 (Advantage): {roll1}, {roll2} -> {final_d20_roll}"
            game.message_log.add_message(f"The {self.name} rolls with Advantage!", (255, 200, 100))
        elif disadvantage:
            final_d20_roll = min(roll1, roll2)
            roll_message_part = f"2d20 (Disadvantage): {roll1}, {roll2} -> {final_d20_roll}"
            game.message_log.add_message(f"The {self.name} rolls with Disadvantage!", (150, 150, 255))
        
        monster_attack_bonus = 2 # Keep this as is for now
        attack_roll_total = final_d20_roll + monster_attack_bonus # Use final_d20_roll

        # --- Apply EvasionBuff to target's AC if present ---
        target_ac = target.armor_class
        evasion_buff = None
        if hasattr(target, 'active_status_effects'): # Ensure target is a Player or similar
            for effect in target.active_status_effects:
                if isinstance(effect, EvasionBuff):
                    evasion_buff = effect
                    break

        if evasion_buff:
            target_ac += evasion_buff.dodge_bonus
            game.message_log.add_message(f"The {target.name} is evasive! Target AC: {target_ac}", (100, 255, 255))

        game.message_log.add_message(
            f"The {self.name} rolls {roll_message_part} + {monster_attack_bonus} (Attack Bonus) = {attack_roll_total}",
            (255, 150, 150)
        )

        is_critical_hit = (final_d20_roll == 20) # Use final_d20_roll
        is_critical_fumble = (final_d20_roll == 1) # Use final_d20_roll


        if is_critical_hit:
            game.message_log.add_message(
                f"CRITICAL HIT! The {self.name} lands a devastating blow!",
                (255, 100, 100)
            )
            hit_successful = True
        elif is_critical_fumble:
            game.message_log.add_message(
                f"CRITICAL FUMBLE! The {self.name} stumbles!",
                (150, 150, 150)
            )
            hit_successful = False
        elif attack_roll_total >= target_ac:
            hit_successful = True
        else:
            hit_successful = False

        if hit_successful:
            # --- AMBIENT TEXT FOR MONSTER HIT ---
            monster_hit_messages = [
                f"The {self.name}'s attack ({attack_roll_total}) hits {target.name} (AC {target.armor_class})!",
                f"The {self.name} strikes {target.name}!",
                f"A claw rakes across {target.name}'s arm!",
                f"The {self.name} connects with a brutal blow!"
            ]
            game.message_log.add_message(random.choice(monster_hit_messages), (255, 100, 100))

            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            game.floating_texts.append(hit_text)
            # print(f"DEBUG: Monster added HIT! FloatingText for {target.name} at ({target.x},{target.y}). Initial frames_left: {hit_text.frames_left}. List size: {len(game.floating_texts)}") # <--- MODIFIED PRINT


            # --- Damage Calculation ---
            monster_die_type = 4 # Assuming 1d4 for monsters
            damage_rolls = []
            total_dice_rolled = 1 # Default to 1 die

            if is_critical_hit:
                total_dice_rolled *= 2 # Double the number of dice rolled for critical hits
                game.message_log.add_message(f"Critical Hit! The {self.name} rolls {total_dice_rolled}d{monster_die_type} for damage!", (255, 100, 100))

            for _ in range(total_dice_rolled):
                damage_rolls.append(random.randint(1, monster_die_type))
            
            damage_dice_rolls_sum = sum(damage_rolls)
            
            # Construct the message part for dice rolls
            damage_message_dice_part = f"{total_dice_rolled}d{monster_die_type} ({' + '.join(map(str, damage_rolls))})"

            damage_modifier = self.attack_power
            damage_total = max(1, damage_dice_rolls_sum + damage_modifier)

            game.message_log.add_message(
                f"The {self.name} rolls {damage_message_dice_part} + {damage_modifier} (Attack Power) = {damage_total} damage!",
                (255, 170, 100)
            )

            damage_dealt = target.take_damage(damage_total, game, damage_type='physical') 
            
            game.message_log.add_message(
                f"The {self.name} attacks {target.name} for {damage_dealt} damage!", 
                (255, 50, 50)
            )

            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game.floating_texts.append(damage_text)
            print(f"DEBUG: Monster added DAMAGE FloatingText for {target.name} at ({target.x},{target.y}). Initial frames_left: {damage_text.frames_left}. List size: {len(game.floating_texts)}") # <--- MODIFIED PRINT

            # --- Apply Poison if applicable ---
            if self.can_poison and target.alive:
                game.message_log.add_message(f"The {self.name} attempts to poison {target.name}!", (255, 150, 0))
                if not target.make_saving_throw("CON", self.poison_dc, game):
                    target.add_status_effect("Poisoned", duration=self.poison_duration, game_instance=game, source=self)
                else:
                    game.message_log.add_message(f"{target.name} resists the poison!", (150, 255, 150))

            # --- Apply Acid Burn if applicable ---
            if self.can_acid_burn and target.alive:
                game.message_log.add_message(f"The {self.name} attempts to burn {target.name} with acid!", (255, 150, 0))
                if not target.make_saving_throw("CON", self.acid_burn_dc, game):
                    target.add_status_effect("AcidBurned", duration=self.acid_burn_duration, game_instance=game, source=self)
                else:
                    game.message_log.add_message(f"{target.name} resists the acid burn!", (150, 255, 150))

            if not target.alive:
                game.message_log.add_message(
                    f"{target.name} has been slain!",
                    (200, 0, 0)
                )
            else:
                game.message_log.add_message(
                    f"{target.name} has {target.hp}/{target.max_hp} HP remaining.",
                    (255, 200, 0)
                )
        else:
            # --- AMBIENT TEXT FOR MONSTER MISS ---
            monster_miss_messages = [
                f"The {self.name}'s attack ({attack_roll_total}) misses {target.name} (AC {target.armor_class})!",
                f"The {self.name} lunges, but misses {target.name}!",
                f"{target.name} deftly avoids the {self.name}'s attack!",
                f"The {self.name}'s attack whiffs past {target.name}!"
            ]
            game.message_log.add_message(random.choice(monster_miss_messages), (200, 200, 200))

            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game.floating_texts.append(miss_text)
            print(f"DEBUG: Monster added MISS! FloatingText for {target.name} at ({target.x},{target.y}). Initial frames_left: {miss_text.frames_left}. List size: {len(game.floating_texts)}") # <--- MODIFIED PRINT


    def ranged_attack(self, target, game):
        """Performs a ranged attack. Override for specific ranged monsters."""
        if not target.alive:
            return
        
        game.message_log.add_message(f"The {self.name} makes a ranged attack at {target.name}!", (255, 150, 0))
        
        # Simplified ranged attack roll (you can make this more complex later)
        attack_roll = random.randint(1, 20) + 2 # Example: +2 to hit for ranged
        
        if attack_roll >= target.armor_class:
            damage = random.randint(1, 6) + self.ranged_attack_power # Example: 1d6 + ranged_attack_power
            damage_dealt = target.take_damage(damage, game, damage_type='piercing')
            game.message_log.add_message(f"The projectile hits {target.name} for {damage_dealt} damage!", (255, 50, 50))
            
            # --- ADDED: Floating Text for HIT! ---
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            game.floating_texts.append(hit_text)
            # --- ADDED: Floating Text for Damage Dealt ---
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game.floating_texts.append(damage_text)
            if not target.alive:
                game.message_log.add_message(f"{target.name} has been slain by a ranged attack!", (200, 0, 0))
        else:
            game.message_log.add_message(f"The {self.name}'s projectile misses {target.name}.", (200, 200, 200))
            
            # --- ADDED: Floating Text for MISS! ---
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game.floating_texts.append(miss_text)
            

    def take_damage(self, amount, game_instance=None, damage_type=None): 
        """Handle taking damage and return actual damage taken"""
        damage_taken = amount 
        self.hp -= damage_taken
        
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            
        return damage_taken

    def die(self):
        """Handle death and return XP value"""
        return self.base_xp

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        """Adds a status effect to the monster."""
        new_effect = None
        if effect_name == "Poisoned":
            new_effect = Poisoned(duration, source)
        # Add other status effects here if monsters can get them
        elif effect_name == "AcidBurned":
            new_effect = AcidBurned(duration, source)        
        
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
        
        self.hp = 20 # Mimic specific HP
        self.max_hp = 20
        self.attack_power = 5
        self.armor_class = 14
        self.base_xp = 30
        self.blocks_movement = True

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


# --- NEW MONSTER CLASSES ---

class GiantRat(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'r', 'Giant Rat', (0, 130, 8))
        self.hp = 5
        self.max_hp = 5
        self.attack_power = 1
        self.armor_class = 10
        self.base_xp = 4
        self.can_poison = True
        self.poison_dc = 11
        self.poison_duration = 2
        self.poison_damage_per_turn = 1

class Ooze(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 's', 'Ooze', (0, 200, 0)) # 's' for slime, bright green
        self.hp = 8
        self.max_hp = 8
        self.attack_power = 2
        self.armor_class = 8 # Slimes are squishy
        self.base_xp = 6
        self.can_poison = False # Or make it acid damage later

class Goblin(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'g', 'Goblin', (0, 130, 8))
        self.hp = 7
        self.max_hp = 7
        self.attack_power = 2
        self.armor_class = 12
        self.base_xp = 6

class GoblinArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'ga', 'Goblin Archer', (0, 100, 0)) # 'a' for archer, darker green
        self.hp = 8
        self.max_hp = 8
        self.attack_power = 1 # Melee attack if adjacent
        self.is_ranged = True
        self.ranged_attack_power = 1 # Ranged attack damage
        self.range = 6 # How far it can shoot
        self.armor_class = 13
        self.base_xp = 15

class Skeleton(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'S', 'Skeleton', (215, 152, 152))
        self.hp = 9
        self.max_hp = 9
        self.attack_power = 3
        self.armor_class = 12
        self.base_xp = 8

class SkeletonArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'SA', 'Skeleton Archer', (180, 180, 180)) # 'S' for Skeleton Archer, lighter gray
        self.hp = 10
        self.max_hp = 10
        self.attack_power = 2
        self.is_ranged = True
        self.ranged_attack_power = 1
        self.range = 6
        self.armor_class = 14
        self.base_xp = 20

class Orc(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'OR', 'Orc', (63, 127, 63)) # 'OR' for Orc, dark green
        self.hp = 12
        self.max_hp = 12
        self.attack_power = 4
        self.armor_class = 13
        self.base_xp = 10

class Centaur(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'CT', 'Centaur', (139, 69, 19)) # 'C' for Centaur, brown
        self.hp = 15
        self.max_hp = 15
        self.attack_power = 5 # Melee attack (hooves/spear)
        self.range = 8
        self.armor_class = 14
        self.base_xp = 25

class CentaurArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'CA', 'Centaur Archer', (139, 69, 19)) # 'CA' for Centaur Archer, brown
        self.hp = 14
        self.max_hp = 14
        self.attack_power = 3 # Melee attack if adjacent
        self.is_ranged = True
        self.ranged_attack_power = 4 # Ranged attack damage
        self.range = 6 # How far it can shoot
        self.armor_class = 15
        self.base_xp = 20        

class Troll(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'T', 'Troll', (127, 63, 63))
        self.hp = 20
        self.max_hp = 20
        self.attack_power = 6
        self.armor_class = 15
        self.base_xp = 30
        # Trolls often have regeneration, which would be a status effect or a special method

class Lizardfolk(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'L', 'Lizardfolk', (0, 100, 100)) # 'L' for Lizardfolk, teal
        self.hp = 18
        self.max_hp = 18
        self.attack_power = 5
        self.armor_class = 16
        self.base_xp = 28
        self.can_poison = True # Some Lizardfolk have poisonous bites
        self.poison_dc = 13
        self.poison_duration = 3
        self.poison_damage_per_turn = 2

class LizardfolkArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'LA', 'Lizardfolk Archer', (0, 80, 80)) # 'LA' for Lizardfolk Archer, darker teal
        self.hp = 16
        self.max_hp = 16
        self.attack_power = 3 # Melee attack if adjacent
        self.is_ranged = True
        self.ranged_attack_power = 4 # Ranged attack damage
        self.range = 6 # How far it can shoot
        self.armor_class = 15
        self.base_xp = 22        

class GiantSpider(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GS', 'Giant Spider', (50, 50, 50)) # 'P' for Spider, dark gray
        self.hp = 15
        self.max_hp = 15
        self.attack_power = 4
        self.armor_class = 14
        self.base_xp = 25
        self.can_poison = True
        self.poison_dc = 12
        self.poison_duration = 4
        self.poison_damage_per_turn = 3

class LargeOoze(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'LO', 'Large Ooze', (0, 150, 0)) # 'O' for Large Ooze, bright green
        self.hp = 20
        self.max_hp = 20
        self.attack_power = 3
        self.armor_class = 10 # Still squishy but larger
        self.base_xp = 15
        self.can_acid_burn = True # Or make it acid damage later
        self.acid_burn_dc = 12
        self.acid_burn_duration = 3
        self.acid_burn_damage_per_turn = 4        

class Beholder(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'BH', 'Beholder', (150, 0, 150)) # 'B' for Beholder, purple
        self.hp = 50
        self.max_hp = 50
        self.attack_power = 8 # Bite attack
        self.is_ranged = True
        self.ranged_attack_power = 5 # Eye ray damage (example)
        self.range = 7 # Long range eye rays
        self.armor_class = 18
        self.base_xp = 100
        # Beholders would typically have multiple eye ray types, anti-magic cone, etc.
        # This is a very simplified version.

class DragonWhelp(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'D', 'Dragon Whelp', (255, 63, 63))
        self.hp = 30
        self.max_hp = 30
        self.attack_power = 7
        self.armor_class = 17
        self.base_xp = 50
        # Dragon Whelps might have a breath weapon (area effect)
