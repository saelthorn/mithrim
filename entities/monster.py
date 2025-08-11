import random
from core.pathfinding import astar
from core.status_effects import Poisoned, PowerAttackBuff, EvasionBuff

class Monster:
    def __init__(self, x, y, char, name, color):
        super().__init__()   
        
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.alive = True
        self.hp = 10
        self.max_hp = 10
        self.attack_power = 2
        self.armor_class = 11
        self.base_xp = 10
        self.initiative = 0
        self.blocks_movement = True
        self.active_status_effects = []
        
        self.can_poison = False
        self.poison_dc = 10
        self.poison_duration = 3
        self.poison_damage_per_turn = 2

    def roll_initiative(self):
        """Roll for turn order"""
        self.initiative = random.randint(1, 20)

    def take_turn(self, player, game_map, game):
        """Handle monster's combat and movement"""
        if not self.alive:
            return

        # Process status effects at the start of the monster's turn
        # self.process_status_effects(game)
        # if not self.alive: # Check if monster died from status effect
        #    return

        # Check if adjacent to player (including diagonals)
        if self.is_adjacent_to(player):
            self.attack(player, game)
            return

        # Otherwise move toward player using A* pathfinding
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
            else:
                game.message_log.add_message(f"The {self.name} is blocked and waits.", (100, 100, 100))


    def is_adjacent_to(self, other):
        """Check if next to another entity (cardinal directions + diagonals)"""
        dx = abs(self.x - other.x)
        dy = abs(self.y - other.y)
        return dx <= 1 and dy <= 1 and (dx != 0 or dy != 0)

    def attack(self, target, game):
        """Attack a target and show combat messages, including dice rolls, crits, and fumbles."""
        if not target.alive:
            return

        # --- Monster Attack Roll ---
        d20_roll = random.randint(1, 20)
        monster_attack_bonus = 2
        attack_roll_total = d20_roll + monster_attack_bonus

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
            f"The {self.name} rolls a d20: {d20_roll} + {monster_attack_bonus} (Attack Bonus) = {attack_roll_total}",
            (255, 150, 150)
        )

        is_critical_hit = (d20_roll == 20)
        is_critical_fumble = (d20_roll == 1)

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


            # --- Damage Calculation (already in place) ---
            damage_dice_roll_1 = random.randint(1, 4)
            damage_dice_roll_2 = 0

            if is_critical_hit:
                damage_dice_roll_2 = random.randint(1, 4)
                damage_dice_rolls_sum = damage_dice_roll_1 + damage_dice_roll_2
                damage_message_dice_part = f"2d4 ({damage_dice_roll_1} + {damage_dice_roll_2})"
            else:
                damage_dice_rolls_sum = damage_dice_roll_1
                damage_message_dice_part = f"1d4 ({damage_dice_roll_1})"

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

            # --- Apply Poison if applicable ---
            if self.can_poison and target.alive:
                game.message_log.add_message(f"The {self.name} attempts to poison {target.name}!", (255, 150, 0))
                if not target.make_saving_throw("CON", self.poison_dc, game):
                    # MODIFIED: Pass string name "Poisoned" instead of the object
                    target.add_status_effect("Poisoned", duration=self.poison_duration, game_instance=game, source=self) # <--- MODIFIED
                else:
                    game.message_log.add_message(f"{target.name} resists the poison!", (150, 255, 150))
            
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

    def add_status_effect(self, effect, game_instance):
        """Adds a status effect to the monster."""
        for existing_effect in self.active_status_effects:
            if type(existing_effect) is type(effect): # Check if it's the same class of effect
                existing_effect.turns_left = effect.duration
                game_instance.message_log.add_message(f"{self.name}'s {effect.name} effect is refreshed.", (200, 200, 255))
                return
        
        self.active_status_effects.append(effect)
        effect.apply_effect(self, game_instance) # Call apply_effect immediately upon adding

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
        if disguise_char == 'K':
            self.revealed_char = 'K' 
        elif disguise_char == 'B':
            self.revealed_char = 'B' 
        elif disguise_char == 'C':
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

    def take_damage(self, amount, game_instance, damage_type=None): # This method *does* take game_instance
        """
        Mimic's take_damage method.
        If disguised and takes damage, it reveals itself.
        """
        if self.disguised:
            game_instance.message_log.add_message(f"You strike the {self.name}!", (255, 165, 0))
            self.reveal(game_instance) 
            
        damage_taken = super().take_damage(amount, game_instance, damage_type) # <--- REMOVE game_instance FROM HERE

        # Add any Mimic-specific damage messages or effects here if needed
        if not self.alive and not self.disguised: # Only if it died and was already revealed
            game_instance.message_log.add_message(f"The {self.name} shudders and collapses!", (255, 0, 0))

        return damage_taken

    def reveal(self, game_instance):
        """Mimic fully reveals its true form."""
        if self.disguised:
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealing. Current char (before change): {self.char}")
            self.disguised = False
            
            # --- MODIFIED: Use self.revealed_char for the revealed form ---
            self.char = self.revealed_char 
            self.color = self.revealed_color 
            
            game_instance.message_log.add_message("The object suddenly sprouts teeth and eyes! It's a MIMIC!", (255, 0, 0))
            game_instance.message_log.add_message("Prepare for battle!", (255, 100, 100))
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealed. New char: {self.char}, color: {self.color}")
            # Mimic immediately attacks the player if adjacent after revealing
            if self.is_adjacent_to(game_instance.player):
                self.attack(game_instance.player, game_instance)
            
            # Ensure it's added to the turn order if it wasn't already (e.g., if it was just an item)
            if self not in game_instance.entities:
                game_instance.entities.append(self)
                print(f"DEBUG: Mimic added to game.entities.")
            if self not in game_instance.turn_order:
                self.roll_initiative()
                game_instance.turn_order.append(self)
                game_instance.turn_order = sorted(game_instance.turn_order, key=lambda e: e.initiative, reverse=True)
                print(f"DEBUG: Mimic added to game.turn_order.")
            
            # Remove revealed mimic from items_on_ground upon reveal
            # This is correct for the *item* aspect, but not the *tile* aspect.
            if self in game_instance.game_map.items_on_ground:
                game_instance.game_map.items_on_ground.remove(self)
                print(f"DEBUG: Mimic removed from game_map.items_on_ground upon reveal.")
            
            # --- NEW CRITICAL STEP: Replace the MimicTile with a floor tile ---
            # This removes the "static crate" visual from the map
            from world.tile import floor # Import floor tile
            game_instance.game_map.tiles[self.y][self.x] = floor
            print(f"DEBUG: MimicTile at ({self.x},{self.y}) replaced with floor tile.")
            
            # Update FOV to ensure the map redraws correctly
            game_instance.update_fov()

    def take_turn(self, player, game_map, game):
        """Mimic's turn logic."""
        if not self.alive:
            return
        
        if self.disguised: # Should not happen if handle_player_action works
            return
        
        # If not disguised, behave like a normal monster (Stage 2 combat form)
        super().take_turn(player, game_map, game)



