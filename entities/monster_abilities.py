
from core.pathfinding import astar
from core.floating_text import FloatingText
from core.status_effects import is_restrained



# Mirrors entities.monster.MONSTER_PATHFINDING_MAX_EXPANSIONS. Kept as
# its own constant instead of imported, to avoid the circular import
# described above. Abilities only ever path a short, local distance (a
# charge at an already-nearby target), so this doesn't need to match
# the much larger budget monster.py tunes for its own, far more
# frequent per-turn chase pathing.
ABILITY_PATHFINDING_MAX_EXPANSIONS = 200


# ---------------------------------------------------------------------------
# MonsterAbility (base class)
# ---------------------------------------------------------------------------

class MonsterAbility:
    """
    Base class for autonomous monster abilities. See module docstring
    for the three hook types (passive / turn-level / on-hit); a given
    ability only ever overrides the one(s) that fit it.
    """

    def __init__(self, name, description, cooldown=0, passive=False):
        self.name = name
        self.description = description
        self.cooldown = cooldown
        self.current_cooldown = 0
        self.passive = passive

    def tick_cooldown(self):
        """Call once per monster turn (see Monster.take_turn())."""
        if self.current_cooldown > 0:
            self.current_cooldown -= 1

    def is_ready(self):
        return self.current_cooldown == 0

    def should_trigger(self, monster, target, distance, game):
        """
        Whether a turn-level ability wants to act *instead of* the
        monster's normal move-or-attack decision this turn. Passive and
        on-hit abilities can leave this at the default False -- they're
        never asked.
        """
        return False

    def execute(self, monster, target, game):
        """
        Perform a passive or turn-level ability's effect. Return False
        to indicate the ability declined to act after all (e.g. a
        charge that found no path, or Regeneration at full HP) -- the
        cooldown is not spent in that case. Any other return value
        (including None) counts as a successful use.
        """
        raise NotImplementedError

    def on_hit(self, monster, target, game):
        """
        Called from Monster._perform_attack() immediately after a
        normal melee attack() lands. Default no-op; on-hit abilities
        (Multiattack, Sweep, Knockback, Webbed) override this instead
        of should_trigger()/execute(). Each on-hit ability is
        responsible for its own is_ready()/cooldown bookkeeping, since
        several may fire off the same hit.
        """
        pass

    def use(self, monster, target, game):
        """Entry point for passive/turn-level abilities."""
        if not self.is_ready():
            return False
        if self.execute(monster, target, game) is False:
            return False
        self.current_cooldown = self.cooldown
        return True

    def __repr__(self):
        return f"{type(self).__name__}(cooldown={self.current_cooldown}/{self.cooldown})"


# ---------------------------------------------------------------------------
# Turn-level abilities
# ---------------------------------------------------------------------------

class Charge(MonsterAbility):
    """
    Closes a large gap in a single turn and immediately attacks with
    bonus damage, instead of the usual one-tile-per-turn approach. Only
    worth using while still relatively far from the target -- once
    adjacent there's nothing left to charge, so should_trigger() steps
    aside and lets the normal attack happen instead.
    """

    def __init__(self, min_range=3, max_tiles=5, bonus_damage=4, cooldown=6):
        super().__init__(
            "Charge",
            "Rushes the target across open ground and strikes with extra force.",
            cooldown=cooldown,
        )
        self.min_range = min_range
        self.max_tiles = max_tiles
        self.bonus_damage = bonus_damage

    def should_trigger(self, monster, target, distance, game):
        # Speed 0 while restrained (see core/status_effects.py's
        # Restrained) -- there's no gap left to close, so step aside and
        # let the normal attack-if-adjacent decision handle it instead.
        return self.is_ready() and distance >= self.min_range and not is_restrained(monster)

    def execute(self, monster, target, game):
        game_map = game.game_map
        approach = monster._approach_tile_near(target, game_map, game)
        if approach is None:
            return False

        path = astar(
            game_map,
            (monster.x, monster.y),
            approach,
            entities=[e for e in game.entities if e != monster and e.alive and e.blocks_movement],
            moving_entity=monster,
            max_expansions=ABILITY_PATHFINDING_MAX_EXPANSIONS,
        )
        if not path or len(path) < 2:
            return False

        game.message_log.add_message(f"The {monster.name} charges at {target.name}!", (255, 150, 0))

        # Cover up to max_tiles steps of the path this single turn,
        # stopping early if something blocks the way partway through.
        for next_x, next_y in path[1:1 + self.max_tiles]:
            if not monster.can_move_to(next_x, next_y, game_map, game):
                break
            monster.x, monster.y = next_x, next_y
            game.refresh_monster_wake_state()

        if monster.is_adjacent_to(target):
            original_modifier = monster.damage_modifier
            monster.damage_modifier += self.bonus_damage
            try:
                monster._perform_attack(target, game)
            finally:
                monster.damage_modifier = original_modifier
        return True


class Roar(MonsterAbility):
    """
    A fear-inducing bellow: forces a WIS save or the target becomes
    Frightened (disadvantage on its own attacks -- see
    core/status_effects.py's Frightened). Ranged rather than melee, so
    it doesn't need to compete with reaching an adjacent attack.
    """

    def __init__(self, dc=14, duration=3, use_range=6, cooldown=10):
        super().__init__(
            "Roar",
            "Lets out a terrifying roar, frightening anything nearby.",
            cooldown=cooldown,
        )
        self.dc = dc
        self.duration = duration
        self.use_range = use_range

    def should_trigger(self, monster, target, distance, game):
        return self.is_ready() and distance <= self.use_range

    def execute(self, monster, target, game):
        game.message_log.add_message(f"The {monster.name} lets out a terrifying roar!", (255, 80, 0))

        saved = hasattr(target, "make_saving_throw") and target.make_saving_throw("WIS", self.dc, game)
        if saved:
            game.message_log.add_message(f"{target.name} resists the fear!", (150, 150, 150))
        else:
            target.add_status_effect("Frightened", self.duration, game, source=monster)
        return True


class CallToArms(MonsterAbility):
    """
    Rallies every living monster within radius, not just this monster's
    own encounter group (see Monster.provoke()/_alert_group(), which
    only wakes a shared group_id) -- a dungeon room's assorted guards
    converging on a sentry's alarm, rather than only its own patrol.
    """

    def __init__(self, radius=10, cooldown=30):
        super().__init__(
            "Call to Arms",
            "Rallies nearby allies to converge on the target.",
            cooldown=cooldown,
        )
        self.radius = radius

    def should_trigger(self, monster, target, distance, game):
        return self.is_ready()

    def execute(self, monster, target, game):
        from entities.monster import Monster, AI_State, Disposition

        rallied = 0
        for entity in game.entities:
            if entity is monster or not isinstance(entity, Monster) or not entity.alive:
                continue
            if monster.distance_to(entity.x, entity.y) > self.radius:
                continue
            if entity.disposition == Disposition.AGGRESSIVE and entity.is_active:
                continue  # already in the fight -- nothing to rally

            entity.disposition = Disposition.AGGRESSIVE
            entity.is_active = True
            entity.last_known_player_position = (target.x, target.y)
            entity.ai_state = AI_State.CHASING
            rallied += 1

        if rallied:
            game.message_log.add_message(
                f"The {monster.name}'s call rallies {rallied} nearby creatures!", (255, 100, 0)
            )
        return rallied > 0


# ---------------------------------------------------------------------------
# On-hit abilities
# ---------------------------------------------------------------------------

class Multiattack(MonsterAbility):
    """Follows up a normal attack with one or more additional attacks
    against the same target, the same turn. The extra swings are plain
    attack() calls (not routed back through _perform_attack()), so they
    don't re-trigger on-hit abilities themselves -- a Multiattack troll
    with Sweep gets one sweep per turn, not one per swing."""

    def __init__(self, extra_attacks=1):
        super().__init__(
            "Multiattack",
            "Strikes again immediately after its first attack.",
            cooldown=0,
        )
        self.extra_attacks = extra_attacks

    def on_hit(self, monster, target, game):
        for _ in range(self.extra_attacks):
            if not target.alive:
                break
            monster.attack(target, game)


class Sweep(MonsterAbility):
    """On a hit, also swings at every other living, non-monster entity
    (the player, or any of the player's summons) adjacent to the
    monster -- a wide weapon or tail catching whoever else is standing
    too close."""

    def __init__(self, damage_penalty=0, cooldown=3):
        super().__init__(
            "Sweep",
            "Follows a hit with a wide swing catching everyone nearby.",
            cooldown=cooldown,
        )
        self.damage_penalty = damage_penalty

    def on_hit(self, monster, target, game):
        if not self.is_ready():
            return

        from entities.monster import Monster

        others = [
            entity for entity in game.entities
            if entity is not monster and entity is not target
            and getattr(entity, "alive", False)
            and not isinstance(entity, Monster)
            and monster.is_adjacent_to(entity)
        ]
        if not others:
            return

        game.message_log.add_message(f"The {monster.name} sweeps at everything nearby!", (255, 150, 0))
        original_modifier = monster.damage_modifier
        monster.damage_modifier += self.damage_penalty
        try:
            for entity in others:
                monster.attack(entity, game)
        finally:
            monster.damage_modifier = original_modifier

        self.current_cooldown = self.cooldown


class Knockback(MonsterAbility):
    """On a hit, shoves the target back along the strike's direction,
    tile by tile, stopping at the first blocked/occupied/out-of-bounds
    tile."""

    def __init__(self, distance=2, cooldown=2):
        super().__init__(
            "Knockback",
            "A powerful blow sends the target reeling backwards.",
            cooldown=cooldown,
        )
        self.distance = distance

    def on_hit(self, monster, target, game):
        if not self.is_ready():
            return

        dx = target.x - monster.x
        dy = target.y - monster.y
        step_x = (dx > 0) - (dx < 0)
        step_y = (dy > 0) - (dy < 0)
        if step_x == 0 and step_y == 0:
            return  # same tile (shouldn't happen) -- nowhere to push

        game_map = game.game_map
        pushed = 0
        for _ in range(self.distance):
            new_x, new_y = target.x + step_x, target.y + step_y
            if not (0 <= new_x < game_map.width and 0 <= new_y < game_map.height):
                break
            if not game_map.is_walkable(new_x, new_y):
                break
            occupied = any(
                e is not target and getattr(e, "alive", False) and getattr(e, "blocks_movement", False)
                and e.x == new_x and e.y == new_y
                for e in game.entities
            )
            if occupied:
                break
            target.x, target.y = new_x, new_y
            pushed += 1

        if pushed:
            game.message_log.add_message(f"{target.name} is knocked back!", (255, 200, 0))
            game.floating_texts.append(FloatingText(target.x, target.y, "KNOCKED BACK!", (255, 200, 0)))

        self.current_cooldown = self.cooldown


class Webbed(MonsterAbility):
    """On a hit, forces a DEX save or restrains the target in sticky
    webbing (see core/status_effects.py's Restrained). No cooldown by
    default -- a spider's web is a property of every strike, not a
    once-in-a-while trick -- but the parameter is there for a monster
    that should only web occasionally."""

    def __init__(self, dc=12, duration=3, cooldown=0):
        super().__init__(
            "Webbed",
            "A sticky strand of web threatens to bind the target in place.",
            cooldown=cooldown,
        )
        self.dc = dc
        self.duration = duration

    def on_hit(self, monster, target, game):
        if not self.is_ready():
            return

        saved = hasattr(target, "make_saving_throw") and target.make_saving_throw("DEX", self.dc, game)
        if saved:
            game.message_log.add_message(f"{target.name} slips free of the webbing!", (150, 150, 150))
        else:
            target.add_status_effect("Restrained", self.duration, game, source=self)

        self.current_cooldown = self.cooldown


# ---------------------------------------------------------------------------
# Passive abilities
# ---------------------------------------------------------------------------

class Regeneration(MonsterAbility):
    """
    Passive per-turn healing, same idea as a 5e Troll's Regeneration --
    heals automatically at the start of each turn unless the monster
    took fire or acid damage since its last turn (see
    Monster.took_fire_or_acid_damage, set in take_damage() and read/
    cleared once per turn in take_turn()).
    """

    def __init__(self, heal_amount=10):
        super().__init__(
            "Regeneration",
            "Rapidly knits wounds shut each turn unless recently burned.",
            cooldown=0,
            passive=True,
        )
        self.heal_amount = heal_amount

    def execute(self, monster, target, game):
        if not monster.alive or monster.hp >= monster.max_hp:
            return False
        if monster.took_fire_or_acid_damage:
            return False

        healed = monster.heal(self.heal_amount)
        if healed > 0:
            game.message_log.add_message(f"The {monster.name}'s wounds knit back together!", (0, 255, 100))
            game.floating_texts.append(FloatingText(monster.x, monster.y, f"+{healed}", (0, 255, 0)))
        return healed > 0