import random

class Monster:
    def __init__(self, x, y, char, name, color, blocks_movement=True):
        self.base_xp = 50
        self.alive = True
        self.hp = 5
        self.max_hp = 5
        self.attack_power = 3
        self.defense = 0 # Added for combat calculations

        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.blocks_movement = blocks_movement
        self.initiative = 0
        
        # AI state
        self.last_seen_player_x = None
        self.last_seen_player_y = None
        self.turns_since_seen_player = 0

    def roll_initiative(self):
        self.initiative = random.randint(1, 20)

    def is_adjacent_to(self, other):
        """Check if adjacent to another entity"""
        return abs(self.x - other.x) <= 1 and abs(self.y - other.y) <= 1 and (abs(self.x - other.x) + abs(self.y - other.y)) == 1

    def can_see_player(self, player, fov):
        """Check if this monster can see the player (simple line of sight)"""
        # For simplicity, monsters can see the player if the player can see them
        return fov.is_visible(self.x, self.y) and fov.is_visible(player.x, player.y)

    def take_turn(self, player, game_map, fov=None):
        """Take this monster's turn with smarter AI"""
        if not self.alive:
            return

        # Check if we can see the player
        can_see = fov is None or self.can_see_player(player, fov)
        
        if can_see:
            # Update last known player position
            self.last_seen_player_x = player.x
            self.last_seen_player_y = player.y
            self.turns_since_seen_player = 0
            
            # If adjacent, attack
            if self.is_adjacent_to(player):
                self.attack(player)
                return
            else:
                # Move toward player
                self.move_toward(player.x, player.y, game_map, [player])
        else:
            # Can't see player - check if we remember where they were
            self.turns_since_seen_player += 1
            
            if (self.last_seen_player_x is not None and 
                self.turns_since_seen_player < 5):  # Remember for 5 turns
                # Move toward last known position
                if (self.x != self.last_seen_player_x or 
                    self.y != self.last_seen_player_y):
                    self.move_toward(self.last_seen_player_x, self.last_seen_player_y, 
                                   game_map, [player])
                else:
                    # Reached last known position - forget it
                    self.last_seen_player_x = None
                    self.last_seen_player_y = None
            else:
                # Wander randomly or stand still
                if random.randint(1, 3) == 1:  # 33% chance to move randomly
                    dx = random.randint(-1, 1)
                    dy = random.randint(-1, 1)
                    if dx != 0 or dy != 0:
                        self.move_toward(self.x + dx, self.y + dy, game_map, [player])

    def attack(self, target):
        """Attack target and return damage dealt"""
        # Simple attack - no dice roll for monsters (or add if you want)
        damage = random.randint(1, 4) + self.attack_power // 2
   
        damage_dealt = target.take_damage(damage)
        return damage_dealt

    def take_damage(self, amount):
        """Take damage and return actual damage taken"""
        damage_taken = max(1, amount - self.defense)
        self.hp -= damage_taken
        
        if self.hp <= 0:
            self.alive = False
            return self.base_xp  # Return XP when killed
        return damage_taken
        
    def die(self):
        """Handle monster death and return XP to be awarded."""
        # This method should only be called when the monster is already dead (hp <= 0, alive = False)
        # It simply returns the XP value for this monster.
        return self.base_xp

    def move_toward(self, target_x, target_y, game_map, entities):
        """Move toward target position"""
        dx = target_x - self.x
        dy = target_y - self.y
        
        # Determine step direction
        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)

        new_x = self.x + step_x
        new_y = self.y + step_y

        # Check if position is valid and not occupied
        if (game_map.is_walkable(new_x, new_y) and 
            not any(e.x == new_x and e.y == new_y and e != self and e.alive for e in entities)):
            self.x = new_x
            self.y = new_y
