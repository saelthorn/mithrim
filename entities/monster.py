import random
from core.pathfinding import astar
from core.status_effects import Poisoned # <--- NEW IMPORT

class Monster:
    def __init__(self, x, y, char, name, color):
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
        self.active_status_effects = [] # <--- NEW: List to hold active status effects

        # --- Poison specific attributes (for testing) ---
        self.can_poison = False # Default
        self.poison_dc = 10 # DC for player's CON save
        self.poison_duration = 3 # Turns
        self.poison_damage_per_turn = 2 # Damage

    def roll_initiative(self):
        """Roll for turn order"""
        self.initiative = random.randint(1, 20)

    def take_turn(self, player, game_map, game):
        """Handle monster's combat and movement"""
        if not self.alive:
            return

        # Process status effects at the start of the monster's turn
        self.process_status_effects(game)
        if not self.alive: # Check if monster died from status effect
            return

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
        else:
            game.message_log.add_message(f"The {self.name} has no clear path and waits.", (100, 100, 100))


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
        elif attack_roll_total >= target.armor_class:
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

            damage_dealt = target.take_damage(damage_total)
            
            game.message_log.add_message(
                f"The {self.name} attacks {target.name} for {damage_dealt} damage!", 
                (255, 50, 50)
            )

            # --- Apply Poison if applicable ---
            if self.can_poison and target.alive:
                game.message_log.add_message(f"The {self.name} attempts to poison {target.name}!", (255, 150, 0))
                if not target.make_saving_throw("CON", self.poison_dc, game):
                    poison_effect = Poisoned(duration=self.poison_duration, source=self, damage_per_turn=self.poison_damage_per_turn)
                    target.add_status_effect(poison_effect, game)
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


    def take_damage(self, amount):
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

    # --- Status Effect Management Methods (similar to Player) ---
    def add_status_effect(self, effect, game_instance):
        """Adds a status effect to the monster."""
        for existing_effect in self.active_status_effects:
            if existing_effect == effect:
                existing_effect.turns_left = effect.duration
                game_instance.message_log.add_message(f"{self.name}'s {effect.name} effect is refreshed.", (200, 200, 255))
                return

        self.active_status_effects.append(effect)
        effect.apply(self, game_instance)

    def process_status_effects(self, game_instance):
        """Processes all active status effects on the monster."""
        effects_to_remove = []
        for effect in self.active_status_effects:
            effect.tick(self, game_instance)
            if effect.turns_left <= 0:
                effects_to_remove.append(effect)

        for effect in effects_to_remove:
            self.active_status_effects.remove(effect)
            effect.remove(self, game_instance)



class Mimic(Monster):
    def __init__(self, x, y):
        # Mimics start disguised as a chest
        super().__init__(x, y, 'C', 'Chest', (139, 69, 19)) # Same char and color as Chest
        self.name = "Mimic" # Actual name
        self.disguised = True
        self.hp = 20
        self.max_hp = 20
        self.attack_power = 5
        self.armor_class = 14
        self.base_xp = 30 # More XP for a trickier monster
        self.blocks_movement = True # Mimics block movement even when disguised
    
    def reveal(self, game_instance):
        """Mimic reveals its true form."""
        if self.disguised:
            self.disguised = False
            self.char = 'M' # Change character to 'M' for Mimic
            self.color = (255, 0, 0) # Change color to red
            game_instance.message_log.add_message("The chest suddenly sprouts teeth and eyes! It's a MIMIC!", (255, 0, 0))
            game_instance.message_log.add_message("Prepare for battle!", (255, 100, 100))
            # Mimic immediately attacks the player if adjacent after revealing
            if self.is_adjacent_to(game_instance.player):
                self.attack(game_instance.player, game_instance)
            # Ensure it's added to the turn order if it wasn't already (e.g., if it was just an item)
            if self not in game_instance.turn_order:
                game_instance.entities.append(self)
                self.roll_initiative()
                game_instance.turn_order.append(self)
                game_instance.turn_order = sorted(game_instance.turn_order, key=lambda e: e.initiative, reverse=True)

    def take_turn(self, player, game_map, game):
        """Mimic's turn logic."""
        if not self.alive:
            return
        if self.disguised:
            # Disguised mimics don't move or attack on their own turn
            return
        # If not disguised, behave like a normal monster
        super().take_turn(player, game_map, game)
