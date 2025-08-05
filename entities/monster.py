import random  

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
        self.attack_power = 2  # Base damage
        self.armor_class = 11  # D&D 5e equivalent of AC for monsters (e.g., Orc AC is 13, but let's start lower for early monsters)
        self.base_xp = 10      # XP awarded when killed
        self.initiative = 0    # For turn order

    def roll_initiative(self):
        """Roll for turn order"""
        # Monsters can have a DEX modifier for initiative, for simplicity just d20 for now
        self.initiative = random.randint(1, 20)

    def take_turn(self, player, game_map, game):
        """Handle monster's combat and movement"""
        if not self.alive:
            return

        # Check if adjacent to player (including diagonals)
        if self.is_adjacent_to(player):
            self.attack(player, game)
            return

        # Otherwise move toward player
        self.move_toward_player(player, game_map)

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
        # In D&D 5e, damage is applied directly after hitting AC.
        # Monsters don't have a 'defense' attribute for damage reduction.
        damage_taken = amount 
        self.hp -= damage_taken
        
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            
        return damage_taken

    def die(self):
        """Handle death and return XP value"""
        return self.base_xp

    def move_toward_player(self, player, game_map):
        """Simple pathfinding - move toward player"""
        # Calculate direction
        dx = 1 if player.x > self.x else -1 if player.x < self.x else 0
        dy = 1 if player.y > self.y else -1 if player.y < self.y else 0
        
        # Try primary direction first
        new_x, new_y = self.x + dx, self.y + dy
        if game_map.is_walkable(new_x, new_y):
            self.x, self.y = new_x, new_y
            return
            
        # If primary direction blocked, try secondary
        if dx != 0:
            new_x, new_y = self.x, self.y + dy
            if game_map.is_walkable(new_x, new_y):
                self.x, self.y = new_x, new_y
                return
                
        if dy != 0:
            new_x, new_y = self.x + dx, self.y
            if game_map.is_walkable(new_x, new_y):
                self.x, self.y = new_x, new_y
                return
