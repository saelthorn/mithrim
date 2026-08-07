import random
from entities.base_entity import NPC # Reusing NPC as a base for simplicity
from entities.monster import Monster
from entities.dungeon_npcs import DungeonHealer, DungeonMerchant
from core.status_effects import Poisoned, AcidBurned, Burning
from core.pathfinding import astar
from core import game
from core.floating_text import FloatingText

# Cap on astar()'s per-call node-expansion budget for every summon's
# pathfinding below (EscortCompanion's fallback search, and Imp/
# Celestial/SpiritualWeaponEntity chasing the nearest enemy), matching
# the cap applied to monster AI in entities/monster.py for the same
# reason: every one of these calls targets something already within a
# handful of tiles (an owner to follow, an enemy within an 8-tile
# detection radius), so a map-spanning search is never actually needed.
# Every summon sits in turn_order and takes a turn on every single
# player action -- movement included, not just combat -- in the same
# synchronous batch pass before a frame renders (see game.py's turn-
# processing loop). Several summons/companions each left free to search
# toward astar()'s uncapped default of 4000 is exactly what turns "the
# player has an Imp, a Celestial, and two escort companions active at
# once" into a visible stutter/freeze.
SUMMON_PATHFINDING_MAX_EXPANSIONS = 400


def _chebyshev_distance(ax, ay, bx, by):
    """
    King-move distance between two tiles: how many steps it takes a piece
    that can move diagonally to close the gap. Every summon's "is this
    close enough" / "is this adjacent" check below uses this instead of
    Manhattan distance (abs(dx) + abs(dy)), which treats a diagonal
    neighbor as two tiles away and used to make a diagonally-adjacent
    summon think it wasn't close enough yet, or a diagonally-adjacent
    enemy think it wasn't in melee range yet.
    """
    return max(abs(ax - bx), abs(ay - by))


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

        # An escort can span an entire cross-chunk journey (see
        # game.py's recruit_companion()/generate_overworld_map()), and
        # _is_free() below already lets a companion step onto anything
        # game_map.is_walkable() allows -- including water, same as the
        # player. Without this, a companion wading into a river would
        # render as a normal (non-submerged) sprite instead of the
        # composited swimming sprite game.py's draw loop uses for the
        # player and other can_swim entities (see the is_submerged
        # check there).
        self.can_swim = True

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
        close the distance to the player.

        Performance note: this used to call astar() -- a full pathfinding
        search over the map -- on every single turn the companion wasn't
        already adjacent to the player, which is nearly every turn
        whenever the player is actively walking (the companion is
        perpetually catching up by one tile). That's cheap for a summon
        that only sticks around briefly, but an EscortCompanion now
        persists for an entire cross-chunk journey to an inn (see
        game.py's recruit_companion()/generate_overworld_map()), so it
        was paying a full search's cost on nearly every player action for
        the whole trip -- the actual cause of the slowdown reported after
        that persistence fix landed.

        The fix is the same "steer first, path-find only if that fails"
        split SpiritualWeapon already uses in this file for its own
        return-to-owner case: try a plain O(1) step directly toward the
        player first (covers the overwhelming majority of turns, since
        overworld terrain is mostly open), and only fall back to a full
        astar() search -- still available, so a companion never gets
        stuck behind an obstacle the way a pure greedy walker would --
        on the turns where that direct step is actually blocked.
        """
        if not self.alive:
            return

        distance_to_player = _chebyshev_distance(self.x, self.y, self.owner.x, self.owner.y)
        if distance_to_player <= self.FOLLOW_DISTANCE:
            return  # Close enough -- let the player lead

        if self._step_toward(game_map, game_instance, self.owner.x, self.owner.y):
            return

        self._pathfind_toward(game_map, game_instance, self.owner.x, self.owner.y)

    def _is_free(self, x, y, game_map, game_instance):
        """
        Whether (x, y) is walkable and not currently occupied -- by an
        ordinary blocking entity (a monster, a shopkeeper, ...), by the
        player, or by another escort companion. The single "can I step
        here" check both movement strategies below use before
        committing to a move.

        Companions themselves have blocks_movement=False (so they never
        block the *player's* own path -- see __init__), which means a
        plain blocks_movement check alone would happily let one
        companion step onto a tile the player or another companion is
        already standing on. Checking for the player and for
        EscortCompanion explicitly closes that gap without touching
        blocks_movement itself, which other code relies on staying
        False for companions.
        """
        if not game_map.is_walkable(x, y):
            return False
        for entity in game_instance.entities:
            if entity is self or entity.x != x or entity.y != y:
                continue
            if entity is self.owner or isinstance(entity, EscortCompanion):
                return False
            if getattr(entity, "blocks_movement", False):
                return False
        return True

    def _step_toward(self, game_map, game_instance, target_x, target_y):
        """
        Cheap, search-free steering step: move one tile toward
        (target_x, target_y), preferring a diagonal step (closes both
        axes' gap at once) and falling back to whichever single axis has
        the larger gap, then the other axis, if that tile isn't free. No
        grid search at all, so this is effectively free to call every
        turn -- it's what handles the common case of open terrain between
        the companion and the player. Returns True if it moved, False if
        none of the candidate tiles were free (an obstacle is in the way
        and the caller should fall back to _pathfind_toward()).
        """
        dx = target_x - self.x
        dy = target_y - self.y
        step_x = (dx > 0) - (dx < 0)  # -1, 0, or 1
        step_y = (dy > 0) - (dy < 0)

        cardinal_candidates = []
        if step_x != 0:
            cardinal_candidates.append((self.x + step_x, self.y))
        if step_y != 0:
            cardinal_candidates.append((self.x, self.y + step_y))
        if abs(dx) < abs(dy):
            cardinal_candidates.reverse()  # Lead with whichever axis has more ground to cover.

        candidates = []
        if step_x != 0 and step_y != 0:
            # A diagonal step closes both axes in one move, so it's
            # always the best option when the target isn't purely
            # horizontal/vertical from here -- try it before either
            # single-axis fallback above.
            candidates.append((self.x + step_x, self.y + step_y))
        candidates.extend(cardinal_candidates)

        for next_x, next_y in candidates:
            if self._is_free(next_x, next_y, game_map, game_instance):
                self.x, self.y = next_x, next_y
                return True
        return False

    def _pathfind_toward(self, game_map, game_instance, target_x, target_y):
        """
        Fallback for when the direct step is blocked -- the same A*
        helper other summons use for navigating around terrain (see
        Imp.take_turn()'s Priority 2), only actually invoked on the
        turns _step_toward() couldn't resolve on its own.
        """
        path = astar(game_map, (self.x, self.y), (target_x, target_y),
                     max_expansions=SUMMON_PATHFINDING_MAX_EXPANSIONS)
        if not path or len(path) < 2:
            return  # No route to the player right now (e.g. a closed door between them)

        next_x, next_y = path[1]
        if self._is_free(next_x, next_y, game_map, game_instance):
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
            # Combat summons only ever fight Monster instances -- never
            # NPCs (shopkeepers, questgivers, escort companions, DungeonHealer/
            # DungeonMerchant, ...), even if one happens to block movement.
            if not isinstance(entity, Monster):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = _chebyshev_distance(self.x, self.y, entity.x, entity.y)
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
            # Combat summons only ever fight Monster instances -- never
            # NPCs (shopkeepers, questgivers, escort companions, DungeonHealer/
            # DungeonMerchant, ...), even if one happens to block movement.
            if not isinstance(entity, Monster):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = _chebyshev_distance(self.x, self.y, entity.x, entity.y)
                if distance <= 8:  # Within 8 tiles
                    enemies_in_range.append(entity)

        if enemies_in_range:
            # Find the nearest enemy
            nearest_enemy = min(enemies_in_range, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))

            # Use A* pathfinding to find a path to the enemy
            path = astar(game_map, (self.x, self.y), (nearest_enemy.x, nearest_enemy.y),
                         max_expansions=SUMMON_PATHFINDING_MAX_EXPANSIONS)
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
        distance_to_player = _chebyshev_distance(self.x, self.y, self.owner.x, self.owner.y)
        
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
            # Combat summons only ever fight Monster instances -- never
            # NPCs (shopkeepers, questgivers, escort companions, DungeonHealer/
            # DungeonMerchant, ...), even if one happens to block movement.
            if not isinstance(entity, Monster):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = _chebyshev_distance(self.x, self.y, entity.x, entity.y)
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
            # Combat summons only ever fight Monster instances -- never
            # NPCs (shopkeepers, questgivers, escort companions, DungeonHealer/
            # DungeonMerchant, ...), even if one happens to block movement.
            if not isinstance(entity, Monster):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = _chebyshev_distance(self.x, self.y, entity.x, entity.y)
                if distance <= 8:  # Within 8 tiles
                    enemies_in_range.append(entity)

        if enemies_in_range:
            # Find the nearest enemy
            nearest_enemy = min(enemies_in_range, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))

            # Use A* pathfinding to find a path to the enemy
            path = astar(game_map, (self.x, self.y), (nearest_enemy.x, nearest_enemy.y),
                         max_expansions=SUMMON_PATHFINDING_MAX_EXPANSIONS)
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
        distance_to_player = _chebyshev_distance(self.x, self.y, self.owner.x, self.owner.y)

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
            # Combat summons only ever fight Monster instances -- never
            # NPCs (shopkeepers, questgivers, escort companions, DungeonHealer/
            # DungeonMerchant, ...), even if one happens to block movement.
            if not isinstance(entity, Monster):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = _chebyshev_distance(self.x, self.y, entity.x, entity.y)
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
            # Combat summons only ever fight Monster instances -- never
            # NPCs (shopkeepers, questgivers, escort companions, DungeonHealer/
            # DungeonMerchant, ...), even if one happens to block movement.
            if not isinstance(entity, Monster):
                continue
            if hasattr(entity, 'blocks_movement') and entity.blocks_movement:
                distance = _chebyshev_distance(self.x, self.y, entity.x, entity.y)
                if distance <= 8:  # Within 8 tiles
                    enemies_in_range.append(entity)

        if enemies_in_range:
            nearest_enemy = min(enemies_in_range, key=lambda e: abs(self.x - e.x) + abs(self.y - e.y))
            
            path = astar(game_map, (self.x, self.y), (nearest_enemy.x, nearest_enemy.y),
                         max_expansions=SUMMON_PATHFINDING_MAX_EXPANSIONS)
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

        distance_to_player = _chebyshev_distance(self.x, self.y, self.owner.x, self.owner.y)

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