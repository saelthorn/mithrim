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
        self.attack_power = 3  # Base damage
        self.defense = 1       # Damage reduction
        self.base_xp = 10      # XP awarded when killed
        self.initiative = 0    # For turn order

    def roll_initiative(self):
        """Roll for turn order"""
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
        """Attack a target and show combat messages"""
        if not target.alive:
            return

        # Damage calculation
        damage = max(1, random.randint(1, 4) + self.attack_power)  # 1d4 + attack power
        damage_dealt = target.take_damage(damage)
        
        # Combat messages
        game.message_log.add_message(
            f"The {self.name} attacks {target.name} for {damage_dealt} damage!", 
            (255, 50, 50)  # Red color for damage
        )
        
        if not target.alive:
            game.message_log.add_message(
                f"{target.name} has been slain!",
                (200, 0, 0)  # Dark red for kill
            )
        else:
            game.message_log.add_message(
                f"{target.name} has {target.hp}/{target.max_hp} HP remaining.",
                (255, 200, 0)  # Yellow for HP display
            )

    def take_damage(self, amount):
        """Handle taking damage and return actual damage taken"""
        damage_taken = max(1, amount - self.defense)  # Minimum 1 damage
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
