from entities.base_entity import NPC # Reusing NPC as a base for simplicity
from core.status_effects import Poisoned, AcidBurned, Burning
from core.pathfinding import astar
from core import game
from core.floating_text import FloatingText

class SummonedEntity(NPC):
    """
    Base class for any entity summoned by a player ability.
    """
    def __init__(self, x, y, char, name, color, owner, duration=0):
        super().__init__(x, y, char, name, color)
        self.owner = owner  # The player or entity that summoned this
        self.duration = duration # How many turns the summon lasts (0 for permanent until destroyed)
        self.turns_left = duration
        self.blocks_movement = True # Most summons block movement
        self.alive = True # Summons start alive
        self.hp = 1 # Summons might have very low HP or be invulnerable
        self.max_hp = 1
        self.attack_power = 0 # Most summons don't attack by default
        self.armor_class = 0 # Most summons don't have AC by default

    def take_turn(self, player, game_map, game):
        """
        Summoned entities might have their own AI or simply expire.
        This method should be overridden by specific summons.
        """
        self.tick_duration(game)
        if not self.alive:
            return

        # Default behavior: do nothing or move randomly
        # Specific summons (like a combat pet) would have their own logic here.
        pass

    def tick_duration(self, game_instance):
        """Decrements the summon's duration each turn."""
        if self.duration > 0:
            self.turns_left -= 1
            if self.turns_left <= 0:
                self.die(game_instance)

    def die(self, game_instance):
        """Handles the summon's despawn or death."""
        self.alive = False
        game_instance.message_log.add_message(f"The {self.name} vanishes!", self.color)
        # Remove from entities list and turn order
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        game_instance.update_fov() # Update FOV if it was a light source or blocking sight


class MageHandEntity(SummonedEntity):
    """
    A spectral hand summoned by the Mage Hand ability.
    It's primarily for interaction, not combat.
    """
    def __init__(self, x, y, owner):
        # Mage Hand is typically invisible or translucent, but for display, use a char.
        # It doesn't have HP or take damage in D&D 5e, so HP is set to 1 as a placeholder.
        super().__init__(x, y, 'mh', 'Mage Hand', (150, 200, 255), owner, duration=10) # Lasts 1 minute (10 turns)
        self.blocks_movement = False # Mage Hand typically doesn't block movement
        self.hp = 1 # It's not a combatant, so effectively invulnerable to damage
        self.max_hp = 1
        self.armor_class = 0 # No AC, as it's not directly targetable by attacks

    def take_damage(self, amount, game_instance=None, damage_type=None):
        """
        Mage Hand does not take damage. Override to prevent HP reduction.
        """
        # Log that it was "hit" but took no damage
        if game_instance:
            game_instance.message_log.add_message(f"The {self.name} shimmers but is unaffected.", self.color)
        return 0 # No damage taken

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        """Adds a status effect to the player."""
        new_effect = None
        
        if effect_name == "Poisoned":
            new_effect = Poisoned(duration, source)
        elif effect_name == "AcidBurned":
            new_effect = AcidBurned(duration, source)
        elif effect_name == "Burning":
            new_effect = Burning(duration, source) 
        
        if new_effect:
            for existing_effect in self.active_status_effects:
                if type(existing_effect) is type(new_effect):
                    existing_effect.turns_left = new_effect.duration
                    game_instance.message_log.add_message(f"{self.name}'s {new_effect.name} effect is refreshed.", (200, 200, 255))
                    return
            self.active_status_effects.append(new_effect)
            game_instance.message_log.add_message(f"{self.name} triggers the trap and dissipates!", (255, 100, 0))         
        else:
            game_instance.message_log.add_message(f"Warning: Attempted to add unknown status effect: {effect_name}", (255, 0, 0))
            print(f"Warning: Attempted to add unknown status effect: {effect_name}")

    def take_turn(self, player, game_map, game):
        """
        Mage Hand doesn't have an active turn in the initiative order.
        Its actions are controlled directly by the player's ability use.
        However, its duration still ticks down.
        """
        self.tick_duration(game)
        # No other actions for Mage Hand on its "turn"
        pass

    def die(self, game_instance):
        """Handles the Mage Hand vanishing."""
        self.alive = False
        game_instance.message_log.add_message(f"The {self.name} dissipates.", self.color)
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        # No FOV update needed as it's not a light source and doesn't block sight.


class Imp(SummonedEntity):
    """
    A small devil imp summoned by the Wizard's Summon Imp ability.
    It can attack enemies and defend its summoner.
    """
    def __init__(self, x, y, owner):
        super().__init__(x, y, 'IM', 'Imp', (180, 50, 50), owner, duration=60)  # Lasts 60 turns (1 hour)
        self.hp = 10
        self.max_hp = 10
        self.armor_class = 12
        self.blocks_movement = True
        self.attack_power = 2  # +2 modifier for d4 sting attack
        self.initiative = 0
        self.active_status_effects = []

    def take_turn(self, player, game_map, game_instance):
        """
        Imp takes its turn. It attacks enemies in melee range, pathfinds to enemies within 8 tiles,
        or follows the player if no enemies are nearby.
        """
        self.tick_duration(game_instance)
        if not self.alive:
            return

        # Find all adjacent enemies (melee range - distance of 1)
        adjacent_enemies = []
        for entity in game_instance.entities:
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive:
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = abs(self.x - entity.x) + abs(self.y - entity.y)
                if distance == 1:  # Adjacent (melee range)
                    adjacent_enemies.append(entity)
                    print(f"[DEBUG] Found adjacent enemy: {entity.name} at distance {distance}")

        # Priority 1: Attack adjacent enemies
        if adjacent_enemies:
            # Attack the closest adjacent enemy
            target = min(adjacent_enemies, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))
            print(f"[DEBUG] Imp attacking {target.name}")
            self.attack_enemy(target, game_instance)
            return

        # Priority 2: Find enemies within 8 tiles and pathfind toward the nearest one
        enemies_in_range = []
        for entity in game_instance.entities:
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive:
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = abs(self.x - entity.x) + abs(self.y - entity.y)
                if distance <= 8:  # Within 8 tiles
                    enemies_in_range.append(entity)

        if enemies_in_range:
            # Find the nearest enemy
            nearest_enemy = min(enemies_in_range, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))

            # Use A* pathfinding to find a path to the enemy
            path = astar(game_map, (self.x, self.y), (nearest_enemy.x, nearest_enemy.y))
            if path and len(path) > 1:  # path[0] is current position, path[1] is next step
                next_x, next_y = path[1]

                # Check if the next tile is walkable and not blocked
                if game_map.is_walkable(next_x, next_y):
                    blocked = False
                    for entity in game_instance.entities:
                        if entity.x == next_x and entity.y == next_y and entity.blocks_movement and entity != self:
                            blocked = True
                            break
                    if not blocked:
                        self.x = next_x
                        self.y = next_y
                        print(f"[DEBUG] Imp moved to ({self.x}, {self.y}) toward enemy")
                        return

        # Priority 3: If not adjacent to player, move towards the player
        distance_to_player = abs(self.x - self.owner.x) + abs(self.y - self.owner.y)
        
        if distance_to_player > 1:
            dx = 0
            dy = 0
            if self.owner.x < self.x:
                dx = -1
            elif self.owner.x > self.x:
                dx = 1
            if self.owner.y < self.y:
                dy = -1
            elif self.owner.y > self.y:
                dy = 1
            
            new_x = self.x + dx
            new_y = self.y + dy
            
            
            if game_map.is_walkable(new_x, new_y):
                # Check if blocked by another entity
                blocked = False
                for entity in game_instance.entities:
                    if entity.x == new_x and entity.y == new_y and entity.blocks_movement:
                        blocked = True
                        break
                if not blocked:
                    self.x = new_x
                    self.y = new_y
            else:
                print(f"[DEBUG] Target tile ({new_x}, {new_y}) not walkable")

    def attack_enemy(self, target, game_instance):
        """Imp attacks an adjacent enemy."""
        import random
        d20_roll = random.randint(1, 20)
        attack_bonus = self.attack_power + 2  # +2 proficiency bonus
        attack_total = d20_roll + attack_bonus
        target_ac = getattr(target, 'armor_class', 10)

        # Show the attack roll
        game_instance.message_log.add_message(f"The imp attacks {target.name} with a {attack_total} (d20: {d20_roll} + {attack_bonus}) vs AC {target_ac}!", (255, 255, 255))

        if attack_total >= target_ac:
            damage_roll = random.randint(1, 4) + self.attack_power
            damage_dealt = target.take_damage(damage_roll, game_instance, damage_type="piercing")
            game_instance.message_log.add_message(f"The imp stings {target.name} for {damage_dealt} damage!", (255, 100, 100))
            
            # Add floating text for successful hit
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game_instance.floating_texts.append(hit_text)
            game_instance.floating_texts.append(damage_text)
        else:
            game_instance.message_log.add_message(f"The imp's sting misses {target.name}!", (150, 150, 150))
            
            # Add floating text for miss
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game_instance.floating_texts.append(miss_text)

    def die(self, game_instance):
        """Handles the Imp vanishing."""
        self.alive = False
        game_instance.message_log.add_message(f"The {self.name} shrieks and dissipates in a puff of sulfurous smoke!", self.color)
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        game_instance.update_fov()

