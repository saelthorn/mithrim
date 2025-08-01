import random

class Player:
    def __init__(self, x, y, char, name, color):
        self.level = 1
        self.current_xp = 0
        self.xp_to_next_level = 100
        self.alive = True
        self.hp = 40
        self.max_hp = 40
        self.attack_power = 8    
        self.attack_bonus = 2 # Added for combat calculations
        self.defense = 1      # Added for combat calculations
        
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.initiative = 0

    def attack(self, target):
        """Attack a target and return damage dealt"""
        # Calculate attack roll (d20 + bonuses)
        attack_roll = random.randint(1, 20) + self.attack_bonus
        
        # Check if attack hits (vs target's defense)
        if attack_roll >= target.defense:
            # Calculate damage (1d6 + attack_power)
            damage = max(1, random.randint(1, 6) + self.attack_power)
            damage_dealt = target.take_damage(damage)
            
            # Handle death and XP
            if not target.alive:
                xp = target.die()
                if xp > 0:
                    self.gain_xp(xp)
            return damage_dealt
        return 0  # Missed attack


    def gain_xp(self, amount):
        """Add XP to the player and handle leveling up."""
        self.current_xp += amount
        print(f"{self.name} gained {amount} XP! Total XP: {self.current_xp}/{self.xp_to_next_level}")

        # Check for level up
        while self.current_xp >= self.xp_to_next_level:
            self.level_up()

    def take_damage(self, amount):
        """Take damage and return actual damage taken"""
        # Apply defense (minimum 1 damage always gets through)
        damage_taken = max(1, amount - self.defense)
        self.hp -= damage_taken
        
        if self.hp <= 0:
            self.alive = False
        return damage_taken
    
    def level_up(self):
        """Handle leveling up the player."""
        self.level += 1
        self.current_xp -= self.xp_to_next_level
        self.xp_to_next_level = int(self.xp_to_next_level * 1.5)  # Increase threshold for next level
        # Increase player stats on level up
        self.max_hp += 5
        self.hp = self.max_hp # Heal to full HP on level up
        self.attack_power += 1
        self.attack_bonus += 1
        self.defense += 1
        print(f"{self.name} leveled up! Now level {self.level}. Next level at {self.xp_to_next_level} XP.")  # Debug statement


    def roll_initiative(self):
        self.initiative = random.randint(1, 20) + 2  # Player gets +2 DEX bonus

    def move_in_tavern(self, dx, dy, game_map, npcs):
        """Move in tavern - can't attack NPCs, just move or be blocked"""
        new_x = self.x + dx
        new_y = self.y + dy

        # Check for NPC at target location
        for npc in npcs:
            if npc.x == new_x and npc.y == new_y and npc.alive:
                print(f"You bump into {npc.name}. Press SPACE to talk!")
                return False  # Can't move through NPCs

        # Check if position is walkable
        if game_map.is_walkable(new_x, new_y):
            self.x = new_x
            self.y = new_y
            print(f"Player moved to ({self.x}, {self.y})")
            return True
        
        return False

    def move_or_attack(self, dx, dy, game_map, entities):
        """Move or attack - returns True if action was taken"""
        new_x = self.x + dx
        new_y = self.y + dy

        target = None
        # Check for entity at target location
        for entity in entities:
            if entity.x == new_x and entity.y == new_y and entity != self and entity.alive:
                target = entity
                break

        if target:
            # Attack the target
            # The handle_player_attack in game.py will call player.attack()
            # and handle the message logging.
            # We just need to return True to indicate an action was taken.
            return True # Action taken (attack)
        elif game_map.is_walkable(new_x, new_y):
            # Move to the location
            self.x = new_x
            self.y = new_y
            print(f"Player moved to ({self.x}, {self.y})")
            return True # Action taken (move)
        
        return False # No action taken
