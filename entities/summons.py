import random
from entities.base_entity import NPC # Reusing NPC as a base for simplicity
from entities.dungeon_npcs import DungeonHealer, DungeonMerchant
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

    def opportunity_attack(self, target, game_instance):
        """Perform an opportunity attack when a target leaves melee reach."""
        if not self.alive:
            return False
        if hasattr(self, 'attack_enemy'):
            game_instance.message_log.add_message(f"{self.name} strikes as {target.name} tries to flee!", self.color)
            self.attack_enemy(target, game_instance)
            return True
        return False


class EscortCompanion(SummonedEntity):
    """
    A rescued/recruited NPC who follows the player during an escort
    quest -- e.g. a world encounter's aftermath choice to walk a
    victim home, or an authored story handing off an NPC to be led
    somewhere. Not summoned by a player ability, but it reuses
    SummonedEntity's owner/turn-order plumbing anyway (die()'s
    entities/turn_order cleanup, tick_duration()'s no-op when
    duration=0) since a companion sits on the turn order exactly the
    same way a combat summon does -- it just never fights, never
    expires on its own, and only leaves the party when it's delivered
    (see complete_escort()) or killed (see die()).

    Created via Game.recruit_companion() (game.py), which is also
    where escort_id/reward_consequences/escort_hours get their values --
    this class only carries them, it doesn't decide what an escort is
    worth or how it's paid out.
    """

    #: How close a companion tries to stay to the player before it
    #: bothers pathfinding closer -- 1 keeps them adjacent without the
    #: two of them fighting over the exact same tile.
    FOLLOW_DISTANCE = 1

    def __init__(
        self, x, y, char, name, color, owner,
        hp=8, armor_class=10, escort_id=None,
        reward_consequences=None, escort_hours=0, dialogue=None,
    ):
        super().__init__(x, y, char, name, color, owner, duration=0)  # duration=0 -> permanent until delivered/killed
        self.hp = hp
        self.max_hp = hp
        self.armor_class = armor_class
        self.blocks_movement = False  # Never blocks the player's own path
        self.attack_power = 0         # Companions never fight
        self.initiative = 0
        self.active_status_effects = []

        # Which escort quest this companion belongs to, and what
        # delivering them safely pays out -- read by game.py's
        # Game.try_deliver_companions()/_grant_escort_reward().
        #
        # reward_consequences is a list of consequence_system.py
        # Consequence objects (RewardXPConsequence, RewardGoldConsequence,
        # ModifyReputationConsequence, ...) rather than a couple of
        # hardcoded numeric fields, so a scenario's aftermath
        # "consequences" -- already parsed into real Consequence
        # instances by game.py's _normalize_world_encounter_aftermath()
        # -- can be handed straight through here and replayed on
        # delivery through the same shared ConsequenceExecutor every
        # other reward path in the game uses. This class deliberately
        # never executes them itself (that needs an ExecutionContext,
        # which lives on game.py's StorySystems, not here) -- it only
        # carries the list until _grant_escort_reward() runs it. That
        # keeps this module ignorant of consequence_system.py entirely,
        # the same way it's ignorant of the story engine as a whole.
        self.escort_id = escort_id
        self.reward_consequences = list(reward_consequences) if reward_consequences else []
        # Hours the journey is deemed to take once delivered -- applied
        # to the world clock by _grant_escort_reward(), not here (this
        # class has no reference to WorldTimeManager).
        self.escort_hours = escort_hours
        self._dialogue = dialogue or "Please, just get me somewhere safe."

    def get_dialogue(self):
        """Matches every other NPC's get_dialogue() interface (see
        game.py's 'F to talk' handler) so a companion can be talked to
        like any other NPC while it's following."""
        return self._dialogue

    def take_turn(self, player, game_map, game_instance):
        """
        Escort companions never fight -- every turn they simply try to
        close the distance to the player, pathfinding around obstacles
        with the same A* helper combat summons use for chasing enemies
        (see Imp.take_turn()'s Priority 2 above).
        """
        if not self.alive:
            return

        distance_to_player = abs(self.x - self.owner.x) + abs(self.y - self.owner.y)
        if distance_to_player <= self.FOLLOW_DISTANCE:
            return  # Close enough -- let the player lead

        path = astar(game_map, (self.x, self.y), (self.owner.x, self.owner.y))
        if not path or len(path) < 2:
            return  # No route to the player right now (e.g. a closed door between them)

        next_x, next_y = path[1]
        if not game_map.is_walkable(next_x, next_y):
            return

        blocked = any(
            entity.x == next_x and entity.y == next_y
            and getattr(entity, "blocks_movement", False) and entity is not self
            for entity in game_instance.entities
        )
        if not blocked:
            self.x, self.y = next_x, next_y

    def complete_escort(self, game_instance):
        """
        Called once this companion has been safely delivered (see
        Game.try_deliver_companions()). Leaves the party with escort-
        appropriate flavor text instead of SummonedEntity.die()'s
        combat-summon "vanishes" message -- reward granting is the
        caller's job, not this method's.
        """
        self.alive = False
        game_instance.message_log.add_message(
            f"{self.name} thanks you and settles in at the inn.", self.color
        )
        self._leave_party(game_instance)

    def die(self, game_instance):
        """A companion killed mid-escort fails the quest instead of
        just 'vanishing' like a spent combat summon."""
        self.alive = False
        game_instance.message_log.add_message(
            f"{self.name} has fallen! The escort has failed.", (255, 80, 80)
        )
        self._leave_party(game_instance)

    def _leave_party(self, game_instance):
        """Shared entities/turn_order/companions cleanup for both ways
        an escort can end -- delivered or killed."""
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        if self in game_instance.companions:
            game_instance.companions.remove(self)
        game_instance.update_fov()


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
    def __init__(self, x, y, owner, hp=10, attack_power=2, proficiency_bonus=2):
        super().__init__(x, y, 'IM', 'Imp', (180, 50, 50), owner, duration=60)  # Lasts 60 turns (1 hour)
        self.hp = hp
        self.max_hp = hp
        self.armor_class = 12
        self.blocks_movement = True
        self.attack_power = attack_power  # +2 modifier for d4 sting attack
        self.initiative = 0
        self.active_status_effects = []
        self.proficiency_bonus = proficiency_bonus

        self.strength = 6
        self.dexterity = 17
        self.constitution = 13
        self.intelligence = 11
        self.wisdom = 12
        self.charisma = 14

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


    def make_saving_throw(self, save_type, dc, game_instance, source=None):
        """Imps can make saving throws to avoid certain effects."""
        ability_score = getattr(self, save_type, 10)
        save_bonus = (ability_score - 10) // 2 + self.proficiency_bonus
        d20_roll = random.randint(1, 20)
        total_save = d20_roll + save_bonus

        game_instance.message_log.add_message(f"The {self.name} rolls a {save_type} saving throw: [{d20_roll}] + [{save_bonus}] (Save Bonus) = {total_save} vs DC {dc}", (255, 150, 150))

        return total_save >= dc
    
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
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive or isinstance(entity, SummonedEntity):
                continue
            if isinstance(entity, (DungeonHealer, DungeonMerchant)):
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
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive or isinstance(entity, SummonedEntity):
                continue
            if isinstance(entity, (DungeonHealer, DungeonMerchant)):
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
        attack_bonus = self.attack_power + self.proficiency_bonus
        attack_total = d20_roll + attack_bonus
        target_ac = getattr(target, 'armor_class', 10)

        # Show the attack roll
        game_instance.message_log.add_message(f"The imp rolls a d20: [{d20_roll}] + [{attack_bonus}] (Attack Bonus) = {attack_total} vs AC {target_ac}!", (255, 120, 120))

        if attack_total >= target_ac:
            game_instance.message_log.add_message(f"The imp's sting hits {target.name}!", (220, 100, 100))

            damage_roll = random.randint(1, 4) 
            damage_dealt = target.take_damage(damage_roll, game_instance, damage_type="piercing") + self.attack_power
            game_instance.message_log.add_message(f"The imp rolls a 1d4: [{damage_roll}] + [{self.attack_power}] (Attack Power) = {damage_dealt} damage!", (255, 120, 120))
            game_instance.message_log.add_message(f"The imp stings {target.name} for {damage_dealt} damage!", (255, 100, 100))
            game_instance.message_log.add_message(f"{target.name} has {getattr(target, 'hp', 'unknown')}/{getattr(target, 'max_hp', 'unknown')} HP.", (255, 120, 120))
            
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
        if self.owner and hasattr(self.owner, 'abilities'):
            game_instance.message_log.add_message(f"{self.owner.name}'s summon_imp ability is now on cooldown.", (255, 150, 150))
            summon_ability = self.owner.abilities.get("Summon Imp")
            if summon_ability:
                summon_ability.current_cooldown = summon_ability.cooldown
        game_instance.update_fov()


class Celestial(SummonedEntity):
    """
    A celestial spirit summoned by the Cleric's Summon Celestial ability.
    It can heal allies and smite enemies with radiant energy.
    """
    def __init__(self, x, y, owner, hp=20, proficiency_bonus=2, attack_power=4,):
        super().__init__(x, y, 'CS', 'Celestial Spirit', (255, 255, 200), owner, duration=160)  # Lasts 160 turns (16 minutes)
        self.hp = hp
        self.max_hp = hp
        self.armor_class = 15
        self.blocks_movement = True
        self.attack_power = attack_power  # +4 modifier for radiant smite attack
        self.initiative = 0
        self.active_status_effects = []
        self.proficiency_bonus = proficiency_bonus

        self.strength = 16
        self.dexterity = 14
        self.constitution = 16
        self.intelligence = 10
        self.wisdom = 14
        self.charisma = 16

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

    def make_saving_throw(self, save_type, dc, game_instance, source=None):
        """Celestial Spirits can make saving throws to avoid certain effects."""
        ability_score = getattr(self, save_type, 10)
        save_bonus = (ability_score - 10) // 2 + self.proficiency_bonus
        d20_roll = random.randint(1, 20)
        total_save = d20_roll + save_bonus

        game_instance.message_log.add_message(f"The {self.name} rolls a {save_type} saving throw: [{d20_roll}] + [{save_bonus}] (Save Bonus) = {total_save} vs DC {dc}", (255, 255, 150))

        return total_save >= dc
    
    def take_turn(self, player, game_map, game_instance):
        """
        Celestial Spirits takes its turn. It only attacks in melee range, pathfinds to enemies within 8 tiles, 
        or follows the player if no enemies are nearby.
        """
        self.tick_duration(game_instance)
        if not self.alive:
            return
        
        # Find all adjacent enemies (melee range - distance of 1)
        adjacent_enemies = []
        for entity in game_instance.entities:
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive or isinstance(entity, SummonedEntity):
                continue
            if isinstance(entity, (DungeonHealer, DungeonMerchant)):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = abs(self.x - entity.x) + abs(self.y - entity.y)
                if distance == 1:  # Adjacent (melee range)
                    adjacent_enemies.append(entity)

        # Priority 1: Attack adjacent enemies
        if adjacent_enemies:
            # Attack the closest adjacent enemy
            target = min(adjacent_enemies, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))
            self.attack_enemy(target, game_instance)
            return             

        # Priority 2: Find enemies within 8 tiles and pathfind toward the nearest one
        enemies_in_range = []
        for entity in game_instance.entities:
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive or isinstance(entity, SummonedEntity):
                continue
            if isinstance(entity, (DungeonHealer, DungeonMerchant)):
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
        """Celestial Spirit attacks an adjacent enemy."""
        import random
        d20_roll = random.randint(1, 20)
        attack_bonus = self.attack_power + self.proficiency_bonus
        attack_total = d20_roll + attack_bonus
        target_ac = getattr(target, 'armor_class', 10)

        # Show the attack roll
        game_instance.message_log.add_message(f"The celestial spirit rolls a d20: [{d20_roll}] + [{attack_bonus}] (Attack Bonus) = {attack_total} vs AC {target_ac}!", (255, 255, 150))

        if attack_total >= target_ac:
            game_instance.message_log.add_message(f"The celestial spirit's radiant smite hits {target.name}!", (255, 200, 150))

            damage_roll = random.randint(1, 8) 
            damage_dealt = target.take_damage(damage_roll, game_instance, damage_type="radiant") + self.attack_power
            game_instance.message_log.add_message(f"The celestial spirit rolls a 1d8: [{damage_roll}] + [{self.attack_power}] (Attack Power) = {damage_dealt} damage!", (255, 255, 150))
            game_instance.message_log.add_message(f"The celestial spirit smites {target.name} for {damage_dealt} radiant damage!", (255, 200, 150))
            game_instance.message_log.add_message(f"{target.name} has {getattr(target, 'hp', 'unknown')}/{getattr(target, 'max_hp', 'unknown')} HP.", (255, 180, 150))
            
            # Add floating text for successful hit
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game_instance.floating_texts.append(hit_text)
            game_instance.floating_texts.append(damage_text)
        else:
            game_instance.message_log.add_message(f"The celestial spirit's radiant smite misses {target.name}!", (150, 150, 150))
            
            # Add floating text for miss
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game_instance.floating_texts.append(miss_text)  

    def die(self, game_instance):  
        """Handles the Celestial Spirit vanishing."""
        self.alive = False
        game_instance.message_log.add_message(f"The {self.name} fades away in a burst of radiant light!", self.color)
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        if self.owner and hasattr(self.owner, 'abilities'):
            summon_ability = self.owner.abilities.get("Summons Celestial")
            if summon_ability:
                summon_ability.current_cooldown = summon_ability.cooldown
        game_instance.update_fov()                  

class SpiritualWeaponEntity(SummonedEntity):
    """
    A spectral weapon summoned by the Cleric's Spiritual Weapon ability.
    It can attack enemies with force damage.
    """
    def __init__(self, x, y, owner, hp=1, proficiency_bonus=2, attack_power=5):
        super().__init__(x, y, 'sw', 'Spiritual Weapon', (200, 200, 255), owner, duration=50)  # Lasts 50 turns (5 minutes)
        self.hp = hp
        self.max_hp = hp
        self.armor_class = 0
        self.blocks_movement = False
        self.attack_power = attack_power  # +5 modifier for force damage attack
        self.initiative = 0
        self.active_status_effects = []
        self.proficiency_bonus = proficiency_bonus

        self.strength = 0
        self.dexterity = 0
        self.constitution = 0
        self.intelligence = 0
        self.wisdom = 0
        self.charisma = 0

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

    def make_saving_throw(self, save_type, dc, game_instance, source=None):
        """Spiritual Weapon can make saving throws to avoid certain effects, though it typically doesn't."""
        ability_score = getattr(self, save_type, 10)
        save_bonus = (ability_score - 10) // 2 + self.proficiency_bonus
        d20_roll = random.randint(1, 20)
        total_save = d20_roll + save_bonus

        game_instance.message_log.add_message(f"The {self.name} rolls a {save_type} saving throw: [{d20_roll}] + [{save_bonus}] (Save Bonus) = {total_save} vs DC {dc}", (200, 200, 255))

        return total_save >= dc        

    def take_turn(self, player, game_map, game_instance):
        """
        Spiritual Weapon doesn't move or take actions on its own turn.
        Its attacks are controlled directly by the player's ability use.
        However, its duration still ticks down.
        """
        self.tick_duration(game_instance)
        if not self.alive:
            return
        
        adjacent_enemies = []
        for entity in game_instance.entities:
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive or isinstance(entity, SummonedEntity):
                continue
            if isinstance(entity, (DungeonHealer, DungeonMerchant)):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = abs(self.x - entity.x) + abs(self.y - entity.y)
                if distance == 1:  # Adjacent (melee range)
                    adjacent_enemies.append(entity)

        if adjacent_enemies:
            target = min(adjacent_enemies, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))
            self.attack_enemy(target, game_instance)
            return

        enemies_in_range = []
        for entity in game_instance.entities:
            if entity == self or entity == self.owner or not hasattr(entity, 'alive') or not entity.alive or isinstance(entity, SummonedEntity):
                continue
            if isinstance(entity, (DungeonHealer, DungeonMerchant)):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = abs(self.x - entity.x) + abs(self.y - entity.y)
                if distance <= 8:  # Within 8 tiles
                    enemies_in_range.append(entity)

        if enemies_in_range:
            nearest_enemy = min(enemies_in_range, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))
            
            path = astar(game_map, (self.x, self.y), (nearest_enemy.x, nearest_enemy.y))
            if path and len(path) > 1:
                next_x, next_y = path[1]
                if game_map.is_walkable(next_x, next_y):
                    blocked = False
                    for entity in game_instance.entities:
                        if entity.x == next_x and entity.y == next_y and entity.blocks_movement and entity != self:
                            blocked = True
                            break
                    if not blocked:
                        self.x = next_x
                        self.y = next_y       
                        return

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
        """Spiritual Weapon attacks an adjacent enemy."""
        import random
        d20_roll = random.randint(1, 20)
        attack_bonus = self.attack_power + self.proficiency_bonus
        attack_total = d20_roll + attack_bonus
        target_ac = getattr(target, 'armor_class', 10)

        game_instance.message_log.add_message(f"The spiritual weapon rolls a d20: [{d20_roll}] + [{attack_bonus}] (Attack Bonus) = {attack_total} vs AC {target_ac}!", (255, 255, 150))

        if attack_total >= target_ac:
            game_instance.message_log.add_message(f"The spiritual weapon's force strike hits {target.name}!", (255, 200, 150))

            damage_roll = random.randint(1, 8) 
            damage_dealt = target.take_damage(damage_roll, game_instance, damage_type="force") + self.attack_power
            game_instance.message_log.add_message(f"The spiritual weapon rolls a 1d8: [{damage_roll}] + [{self.attack_power}] (Attack Power) = {damage_dealt} damage!", (255, 255, 150))
            game_instance.message_log.add_message(f"The spiritual weapon strikes {target.name} for {damage_dealt} force damage!", (255, 200, 150))
            game_instance.message_log.add_message(f"{target.name} has {getattr(target, 'hp', 'unknown')}/{getattr(target, 'max_hp', 'unknown')} HP.", (255, 180, 150))
            
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game_instance.floating_texts.append(hit_text)
            game_instance.floating_texts.append(damage_text)
        else:
            game_instance.message_log.add_message(f"The spiritual weapon's force strike misses {target.name}!", (150, 150, 150))
            
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game_instance.floating_texts.append(miss_text)                                 

    def die(self, game_instance):
        """Handles the Spiritual Weapon vanishing."""
        self.alive = False
        game_instance.message_log.add_message(f"The {self.name} dissipates after its strike.", self.color)
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        if self.owner and hasattr(self.owner, 'abilities'):
            summon_ability = self.owner.abilities.get("Spiritual Weapon")
            if summon_ability:
                summon_ability.current_cooldown = summon_ability.cooldown
        game_instance.update_fov()