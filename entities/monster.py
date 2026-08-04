import random
from core.pathfinding import astar
from core.status_effects import Poisoned, AcidBurned, Burning, PowerAttackBuff, EvasionBuff, BlessingOfAgility, GuardBuff, ParryBuff
from world.water_features import is_water_tile

from items.items import (
    Potion, Weapon, Armor, Chest, lesser_healing_potion, greater_healing_potion, wood_plank, meat, green_apple, fromage, 
    bread, mushroom, CampfireKit, torch, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor, robes, 
    iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, 
    apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail, 
    round_shield, kite_shield, tower_shield
    )

from world.tile import floor
from world.bloodstain import Bloodstain
from core.floating_text import FloatingText 

from enum import Enum

# Cap on astar()'s per-call node-expansion budget for every monster
# pathfinding call below (chasing, desperate-fight charges, kiting
# pursuit, and investigate/patrol via move_towards), much smaller than
# astar()'s own default of 4000. None of these ever legitimately need a
# map-spanning search -- a monster is always either engaged with a
# nearby target or investigating a position it saw the player at within
# its own detection_range. And since every active monster's turn runs
# synchronously, in the same batch pass, on every single player action
# -- including plain movement, not just combat -- before a single frame
# renders (see game.py's turn-processing loop), an uncapped budget is
# what turns "several monsters searching at once" (a crowded fight, or
# just a handful investigating after losing the player) into a visible
# stutter/freeze that gets worse as monster count grows.
MONSTER_PATHFINDING_MAX_EXPANSIONS = 400

class AI_State(Enum):
    CHASING = 1
    FLEEING = 2
    DESPERATE_FIGHT = 3
    INVESTIGATE = 4
    KITING = 5


class Disposition(Enum):
    """
    How a monster is inclined to treat the player before anything has
    happened between them yet -- distinct from AI_State, which governs
    *how* an already-hostile monster behaves turn to turn (chasing,
    fleeing, kiting, ...) once it's decided to fight. Disposition governs
    whether Monster.take_turn() ever runs that combat AI at all:

      - AGGRESSIVE: attacks/chases on sight, exactly like every monster
        behaved before this existed. The default for every Monster, so
        nothing changes for existing content unless it opts in below.
      - PASSIVE: ignores the player entirely -- no detection, no
        chasing, not even at melee range -- until the player actually
        lands a hit (see Monster.provoke(), called from take_damage()).
        A myconid grove or centaur band the player can walk straight
        past, or straight up to, without a fight starting on its own.
      - NEUTRAL: behaves identically to PASSIVE for now (ignores the
        player until struck). Kept as its own value, rather than
        reusing PASSIVE, so content can label "wary but not fleeing"
        wildlife distinctly from "doesn't even notice you" wildlife --
        and so a future refinement (e.g. neutral creatures backing away
        if the player lingers adjacent) has somewhere to hang that
        behavior without another new attribute.

    Set directly on an already-constructed monster (e.g.
    Game._spawn_world_encounter_passive_creatures() sets this right
    after spawning) rather than threaded through every subclass's
    __init__ -- a monster's *type* doesn't imply its disposition, since
    the same Centaur could be spawned hostile in one encounter and
    passive in another.
    """
    AGGRESSIVE = "aggressive"
    PASSIVE = "passive"
    NEUTRAL = "neutral"


# --- MONSTER GROUP DEFINITIONS ---
MONSTER_GROUPS = {
    # Paired/Pack Monsters
    'Goblin': ['Goblin', 'GoblinArcher'],
    'GoblinArcher': ['Goblin', 'GoblinArcher'],
    'Skeleton': ['Skeleton', 'SkeletonArcher'],
    'SkeletonArcher': ['Skeleton', 'SkeletonArcher'],
    'Lizardfolk': ['Lizardfolk', 'LizardfolkArcher'],
    'LizardfolkArcher': ['Lizardfolk', 'LizardfolkArcher'],
    'Centaur': ['Centaur', 'CentaurArcher'],
    'CentaurArcher': ['Centaur', 'CentaurArcher'],
    'Wolf': ['Wolf', 'Wolf', 'Goblin', 'GoblinArcher'],
    
    # Solo/Pack Monsters
    'GiantRat': ['GiantRat', 'GiantRat'],
    'Ooze': ['Ooze'],
    'Orc': ['Orc', 'Orc'],
    'Troll': ['Troll'],
    'GiantSpider': ['GiantSpider', 'GiantSpider'],
    'Wererat': ['Wererat', 'Wererat'],
    'MyconidSprout': ['MyconidSprout', 'MyconidSprout', 'MyconidAdult'],
    'MyconidAdult': ['MyconidAdult', 'MyconidSprout'],
    'Beholder': ['Beholder', 'Gauth'],
    'LargeOoze': ['LargeOoze', 'Ooze'],
    
    # Solo Monsters
    'RedDragon': ['RedDragon'],
    'Owlbear': ['Owlbear'],
    'Demogorgon': ['Demogorgon'],
    'AlphaGrick': ['AlphaGrick'],
    'Grick': ['Grick'],
    'GibberingMouther': ['GibberingMouther'],
    'MindFlayer': ['MindFlayer'],
    'Minotaur': ['Minotaur'],
    'Yochlol': ['Yochlol'],
    'RedSlaad': ['RedSlaad'],
    'DeathSlaad': ['DeathSlaad'],
    'Mezzoloth': ['Mezzoloth'],
    'Gauth': ['Gauth'],
    'Drider': ['Drider'],
    'Arasta': ['Arasta'],
    'IntellectDevourer': ['IntellectDevourer', 'IntellectDevourer'],
    'Imp': ['Imp', 'Imp'],
    'Wraith': ['Wraith'],
    'TombTapper': ['TombTapper']
}

class Monster:
    def __init__(self, x, y, char, name, color):
        self.x = x
        self.y = y
        self.char = char
        self.name = name
        self.color = color
        self.alive = True
        self.hp = 10  # Base HP, will be overridden in subclasses
        self.max_hp = 10
        self.attack_bonus = 2  # Base attack bonus, will be overridden in subclasses
        self.armor_class = 11  # Base AC, will be overridden in subclasses
        self.base_xp = 10  # Base XP, will be overridden in subclasses
        self.monster_die_type = 4  # Base die type for damage rolls, will be overridden in subclasses
        self.num_damage_dice = 1  # Number of damage dice to roll, will be overridden in subclasses
        self.initiative = 0
        self.blocks_movement = True
        self.active_status_effects = []

        self.can_swim = False

        self.is_active = False
        self.sleep_cooldown = 0        

        # How this monster is inclined to treat the player before anything
        # has happened between them yet -- see the Disposition docstring
        # near the top of this file. Defaults to AGGRESSIVE (every monster's
        # behavior before this existed); a spawn site (e.g. Game.spawn_
        # overworld_monster_groups()'s OVERWORLD_PASSIVE_MONSTER_TYPES) sets
        # this to PASSIVE/NEUTRAL directly on the instance afterward, since
        # a monster's *type* doesn't imply its disposition. See provoke().
        self.disposition = Disposition.AGGRESSIVE

        # Set by world encounters when the player successfully sneaks up on a
        # group (see Game._spawn_world_encounter_monsters): every monster in
        # the group shares this same list, so waking one (see take_damage
        # below) wakes the rest of the group at the same time.
        self.encounter_group = None

        # Shared id tagging every monster spawned together as one pack --
        # a world-encounter ambush (Game._spawn_world_encounter_monsters),
        # an overworld wildlife cluster (Game.spawn_overworld_monster_groups),
        # or a dungeon room's pack (Game.spawn_monster_group). None means
        # "not part of a tagged group" (a lone spawn). See provoke(): landing
        # a hit on one PASSIVE/NEUTRAL member of a group turns the whole
        # group AGGRESSIVE at once, not just the monster actually struck.
        self.group_id = None

        self.patrol_radius = 12
        self.investigate_turns_left = 4  # Turns left to investigate
        self.investigate_search_radius = 3  # Radius around last known position to search
        self.ai_state = AI_State.PATROLLING if hasattr(self, 'ai_state') else AI_State.CHASING  # Default state

        # Rendering/footprint attributes
        # footprint_size represents how many tiles on a side this entity occupies (1 = 1x1)
        self.footprint_size = 1

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

        self.last_known_player_position = None
        self.detection_range = 5
       
        self.damage_modifier = 2

        self.is_ranged = False
        self.ranged_attack_bonus = 0  # Base ranged attack bonus
        self.range = 0  # Max range for ranged attacks
        self.ranged_die_type = 4  # Base die type for ranged attacks
        self.ranged_num_dice = 1  # Number of damage dice for ranged attacks
       
        self.can_poison = False
        self.poison_dc = 10
        self.poison_duration = 3
        self.poison_damage_per_turn = 2
       
        self.can_acid_burn = False
        self.acid_burn_dc = 10
        self.acid_burn_duration = 3
        self.acid_burn_damage_per_turn = 3
       
        self.can_burn = False
        self.burn_dc = 14
        self.burn_duration = 3
        self.burn_damage_per_turn = random.randint(1, 4)

        # NEW: AI Behavior attributes
        self.is_intelligent = False  # Default to False. Set to True for intelligent monsters.
        self.flee_hp_threshold = 0.40  # Flee if monster HP < 40%
        self.player_safe_hp_threshold = 0.60  # Flee if player HP > 60%
        self.desperate_fight_hp_threshold = 0.50  # Fight if player HP < 50% (and monster HP is also low)
        self.ai_state = AI_State.CHASING  # Default state

        # Kiting behavior for ranged monsters
        self.can_kite = False  # Enable kiting for intelligent ranged monsters
        self.ideal_kiting_distance = 4  # Preferred distance to maintain
        self.kiting_attack_threshold = 2  # Min distance before retreating
        self.kiting_retreat_distance = 5  # Max distance before pursuing again
        self.last_kite_direction = (0, 0)  # Memory of last kiting direction
        self.kiting_turns_since_strafe = 0  # Track strafe attempts

        # Telegraph fields: when set by a monster, game will render highlights
        self.pending_telegraph_tiles = []  # list[(x,y)] tiles the monster intends to hit next turn
        self.telegraph_color = (255, 0, 0, 100)  # translucent red
        self.attack_cooldown = 0  # Cooldown for boss telegraphed attacks
        self.telegraph_timer = 0  # Timer for when telegraphed attack resolves (3 turns)

        self.loot_table = []  # List of (item_template, drop_chance) tuples
        
        self.consecutive_failed_flee_turns = 0

            

    def hp_percentage(self):
        """Returns the monster's current HP as a percentage."""
        if self.max_hp == 0:
            return 0.0
        return self.hp / self.max_hp

    def get_saving_throw_bonus(self, ability_name):
        """Calculate the saving throw bonus for the specified ability."""
        ability_score = getattr(self, ability_name.lower(), 0)
        modifier = (ability_score - 10) // 2
        if self.saving_throw_proficiencies.get(ability_name.upper(), False):
            return modifier + 2
        return modifier

    def roll_initiative(self):
        """Roll for turn order"""
        self.initiative = random.randint(1, 20)

    def distance_to(self, target_x, target_y):
        """Calculate the Chebyshev distance to another point."""
        dx = abs(self.x - target_x)
        dy = abs(self.y - target_y)
        return max(dx, dy)


    def detect_player(self, player, game_instance):
        """Check if the player is within detection range and line of sight."""
        distance_to_player = self.distance_to(player.x, player.y)
        is_visible_to_monster = game_instance.check_line_of_sight(self.x, self.y, player.x, player.y)

        if distance_to_player <= self.detection_range and is_visible_to_monster:
            self.last_known_player_position = (player.x, player.y)
            if self.ai_state != AI_State.CHASING and self.ai_state != AI_State.KITING:
                self.ai_state = AI_State.CHASING
                game_instance.message_log.add_message(f"The {self.name} spots you and starts chasing!", self.color)
            return True
        else:
            if self.last_known_player_position:
                can_see_last_known = game_instance.check_line_of_sight(
                    self.x, self.y,
                    self.last_known_player_position[0], self.last_known_player_position[1]
                )
                if not can_see_last_known:
                    self.last_known_player_position = None
                    if self.is_intelligent:
                        if self.ai_state != AI_State.INVESTIGATE:
                            self.ai_state = AI_State.INVESTIGATE
                            self.investigate_turns_left = 4
                            game_instance.message_log.add_message(f"The {self.name} loses track of you and starts investigating.", (150, 150, 150))
                    return False
                else:
                    return False
            return False


    def check_torchlight_in_range(self, game):
        """
        Checks if any torchlight tile is within detection range.
        If so, and player is not visible, triggers investigate state.
        """
        for (x, y), source in game.fov.visible_sources.items():
            if source == 'torch':
                dist = self.distance_to(x, y)
                if dist <= self.detection_range:
                    if game.fov.get_visibility_type(self.x, self.y) != 'player' and self.ai_state != AI_State.INVESTIGATE:
                        self.last_known_player_position = (x, y)
                        self.ai_state = AI_State.INVESTIGATE
                        self.investigate_turns_left = 10
                        game.message_log.add_message(f"The {self.name} notices a flickering light and starts investigating.", self.color)
                        break


    def patrol(self, game_map, game):
        possible_moves = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                new_x, new_y = self.x + dx, self.y + dy
                if self.can_occupy_position(new_x, new_y, game_map, game.entities, exclusions=[self]):
                    possible_moves.append((new_x, new_y))

        if possible_moves:
            target_x, target_y = random.choice(possible_moves)
            self.move_towards(target_x, target_y, game_map, game)

    def _approach_tile_near(self, target_entity, game_map, game):
        """
        Return an open tile adjacent to target_entity for astar to path
        toward, instead of target_entity's own tile.

        astar() itself is fine with an occupied goal (see pathfinding.py
        -- it explicitly excludes the destination from its blocked-tile
        check), but this monster could never actually finish that move
        anyway: can_move_to() refuses to step onto a tile occupied by
        another blocking entity, target included. Pathing straight at
        the target's own tile therefore wastes the search on a step
        that would just get rejected at the end -- this redirects to
        wherever the monster should actually end up standing, next to
        the target and in attack range.

        Prefers whichever open, adjacent tile is closest to self, so the
        monster still approaches from a sensible direction. Returns None
        if every adjacent tile is currently occupied (the target is
        fully surrounded) -- callers should fall back to waiting/greedy
        movement in that case rather than pathing at the occupied tile.
        """
        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                tx, ty = target_entity.x + dx, target_entity.y + dy
                if self.can_occupy_position(tx, ty, game_map, game.entities, exclusions=[self, target_entity]):
                    candidates.append((tx, ty))

        if not candidates:
            return None
        return min(candidates, key=lambda pos: self.distance_to(*pos))

    def move_towards(self, target_x, target_y, game_map, game):
        """
        Moves the monster one step towards the target using A* pathfinding.
        Handles footprint and destructible tiles.
        """
        other_entities = [e for e in game.entities if e != self]

        # If the destination is a live, blocking entity's own tile (e.g.
        # kite()'s pursuit branch chasing the target directly), retarget
        # to the nearest open tile next to it instead -- see
        # _approach_tile_near()'s docstring for why pathing straight at
        # an occupied tile is expensive, not just pointless.
        blocker = next(
            (
                e for e in other_entities
                if getattr(e, "alive", False) and getattr(e, "blocks_movement", False)
                and (e.x, e.y) == (target_x, target_y)
            ),
            None,
        )
        if blocker is not None:
            approach = self._approach_tile_near(blocker, game_map, game)
            if approach is None:
                return False  # blocker is fully surrounded -- nowhere useful to path to
            target_x, target_y = approach

        # Every caller of move_towards() -- patrol (always one adjacent
        # tile away), kiting pursuit, and AI_State.INVESTIGATE chasing a
        # last_known_player_position -- only ever needs a local search,
        # never astar()'s full default budget of 4000. That default was
        # still reachable here whenever the destination wasn't a live
        # blocking entity (the INVESTIGATE case in particular, since it's
        # chasing a remembered position, not an entity move_towards can
        # detect as a "blocker"). Every player action -- including plain
        # movement, not just combat -- advances a full turn for every
        # monster in turn_order in one synchronous pass before a frame
        # renders (see game.py's turn-processing loop), so several
        # investigating monsters each paying close to the full budget on
        # every single player step is exactly what shows up as the game
        # freezing during ordinary movement, not just combat.
        path = astar(game_map, (self.x, self.y), (target_x, target_y), 
                     entities=other_entities, 
                     moving_entity=self, 
                     ignore_destructible=True,
                     max_expansions=MONSTER_PATHFINDING_MAX_EXPANSIONS)
        if path and len(path) > 1:
            next_x, next_y = path[1]
            dx = next_x - self.x
            dy = next_y - self.y
            if self.can_move_to(next_x, next_y, game_map, game):
                self.x = next_x
                self.y = next_y
                game.refresh_monster_wake_state()
                return True
            else:
                return False
        else:
            return False
    
    def flee(self, player, game_map, game):
        """
        Attempts to move the monster directly away from the player.
        Returns tuple: (success: bool, is_cornered: bool)
        """
        dx = self.x - player.x
        dy = self.y - player.y
    
        move_x = 0
        if dx > 0: move_x = 1
        elif dx < 0: move_x = -1
    
        move_y = 0
        if dy > 0: move_y = 1
        elif dy < 0: move_y = -1
    
        potential_moves = []
        if move_x != 0 and move_y != 0:
            potential_moves.append((move_x, move_y))
        if move_x != 0:
            potential_moves.append((move_x, 0))
        if move_y != 0:
            potential_moves.append((0, move_y))
    
        # Track summons whose reach the monster is leaving
        adjacent_summons = []
        for entity in game.entities:
            if not hasattr(entity, 'owner') or entity.owner != player:
                continue
            if not getattr(entity, 'alive', False) or not getattr(entity, 'blocks_movement', False):
                continue
            if max(abs(self.x - entity.x), abs(self.y - entity.y)) == 1:
                adjacent_summons.append(entity)

        for check_dx, check_dy in potential_moves:
            new_x, new_y = self.x + check_dx, self.y + check_dy

            if self.can_occupy_position(new_x, new_y, game_map, game.entities, exclusions=[self]):
                self.x, self.y = new_x, new_y
                game.refresh_monster_wake_state()

                # Opportunity attacks from summons that lost adjacency
                for summon in adjacent_summons:
                    if not getattr(summon, 'alive', False):
                        continue
                    still_adjacent = max(abs(self.x - summon.x), abs(self.y - summon.y)) == 1
                    if not still_adjacent and hasattr(summon, 'opportunity_attack'):
                        summon.opportunity_attack(self, game)
                        if not self.alive:
                            return (True, False)
                
                self.consecutive_failed_flee_turns = 0
                return (True, False)
    
        # Could not flee - track failure
        self.consecutive_failed_flee_turns += 1
        is_cornered = self.consecutive_failed_flee_turns >= 3
        return (False, is_cornered)

    def kite(self, target, game_map, game):
        """
        Kiting behavior: maintain optimal ranged attack distance.
        Move away if target gets too close, pursue if target gets too far.
        This is the core tactic for intelligent ranged monsters.
        """
        distance = self.distance_to(target.x, target.y)
  
        if distance <= 1 and self.is_ranged:
            self.attack(target, game)
            return True
                
        if distance <= self.kiting_attack_threshold:
            self.flee(target, game_map, game)
            return True

        if distance <= self.range and game.check_line_of_sight(self.x, self.y, target.x, target.y):
            self.ranged_attack(target, game)
            return True
        
        if distance > self.kiting_retreat_distance:
            self.move_towards(target.x, target.y, game_map, game)
            return True
        

        # Maintain distance: strafe around target at ideal distance
        dx = target.x - self.x
        dy = target.y - self.y
        
        mag = max(abs(dx), abs(dy))
        if mag > 0:
            dx = dx // mag if dx != 0 else 0
            dy = dy // mag if dy != 0 else 0
        
        perpendicular_moves = [
            (-dy, dx),
            (dy, -dx),
        ]
        
        best_move = None
        best_distance_diff = float('inf')
        
        for move_dx, move_dy in perpendicular_moves:
            if move_dx == 0 and move_dy == 0:
                continue
            
            check_x = self.x + move_dx
            check_y = self.y + move_dy
            
            if not (0 <= check_x < game_map.width and 0 <= check_y < game_map.height):
                continue
            if not game_map.is_walkable(check_x, check_y):
                continue
            
            blocked = False
            for entity in game.entities:
                if entity != self and entity.alive and entity.blocks_movement:
                    if hasattr(entity, 'occupies_tile'):
                        if entity.occupies_tile(check_x, check_y):
                            blocked = True
                            break
                    elif entity.x == check_x and entity.y == check_y:
                        blocked = True
                        break
            if blocked:
                continue
            
            new_distance = self.distance_to(check_x, check_y)
            distance_diff = abs(new_distance - self.ideal_kiting_distance)
            
            if distance_diff < best_distance_diff:
                best_distance_diff = distance_diff
                best_move = (check_x, check_y)
        
        if best_move:
            self.x, self.y = best_move
            game.refresh_monster_wake_state()
            self.kiting_turns_since_strafe = 0
            return True
        
        self.kiting_turns_since_strafe += 1
        if self.kiting_turns_since_strafe > 2:
            for move_dx in [-1, 0, 1]:
                for move_dy in [-1, 0, 1]:
                    if move_dx == 0 and move_dy == 0:
                        continue
                    if (move_dx * dx + move_dy * dy) < 0:
                        check_x = self.x + move_dx
                        check_y = self.y + move_dy
                        if self.can_occupy_position(check_x, check_y, game_map, game.entities, exclusions=[self]):
                            self.x, self.y = check_x, check_y
                            game.refresh_monster_wake_state()
                            self.kiting_turns_since_strafe = 0
                            return True
        
        return False

    def roll_damage(self, is_ranged=False):
        """
        Rolls damage based on monster's stats.
        If is_ranged=True, uses ranged attack dice.
        
        Returns total damage rolled and individual rolls for messaging.
        """
        if is_ranged:
            num_dice = self.ranged_num_dice
            die_type = self.ranged_die_type
        else:
            num_dice = self.num_damage_dice 
            die_type = self.monster_die_type
        rolls = [random.randint(1, die_type) for _ in range(num_dice)]
        return sum(rolls), rolls


    def attack(self, target, game, advantage=False, disadvantage=False):
        """Updated attack with optional telegraph phase for bosses."""
        if target is None or not target.alive:
            return

        if getattr(self, 'footprint_size', 1) > 1:
            if self.attack_cooldown == 0:
                telegraphed = []
                center_x, center_y = target.x, target.y
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        tx, ty = center_x + dx, center_y + dy
                        if 0 <= tx < game.game_map.width and 0 <= ty < game.game_map.height:
                            telegraphed.append((tx, ty))
                self.pending_telegraph_tiles = telegraphed
                self.telegraph_timer = 3
                self.attack_cooldown = 5
                game.message_log.add_message(f"The {self.name} prepares a devastating attack!", (255, 80, 80))
                return
    
        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20)
        final_d20_roll = roll1
        roll_message_part = f"a d20: {roll1}"
        attack_bonus = self.attack_bonus
        damage_modifier = self.damage_modifier

        if advantage and disadvantage:
            game.message_log.add_message(f"The {self.name} rolls with neither Advantage nor Disadvantage.", (150, 150, 150))
        elif advantage:
            final_d20_roll = max(roll1, roll2)
            roll_message_part = f"2d20 (Advantage): {roll1}, {roll2} -> {final_d20_roll}"
            game.message_log.add_message(f"The {self.name} rolls with Advantage!", (255, 200, 100))
        elif disadvantage:
            final_d20_roll = min(roll1, roll2)
            roll_message_part = f"2d20 (Disadvantage): {roll1}, {roll2} -> {final_d20_roll}"
            game.message_log.add_message(f"The {self.name} rolls with Disadvantage!", (150, 150, 255))
        attack_roll_total = final_d20_roll + attack_bonus
        
        is_critical_hit = (final_d20_roll == 20)
        is_critical_fumble = (final_d20_roll == 1)

        target_ac = target.armor_class
        if hasattr(target, 'active_status_effects'):
            for effect in target.active_status_effects:
                if isinstance(effect, EvasionBuff):
                    target_ac += effect.dodge_bonus
                    game.message_log.add_message(f"The {target.name} is evasive! Target AC: {target_ac}", (100, 255, 255))
                if isinstance(effect, BlessingOfAgility):
                    target_ac += effect.ac_bonus
                    game.message_log.add_message(f"The {target.name} is agile! Target AC: {target_ac}", (100, 255, 255))
                if isinstance(effect, GuardBuff):
                    target_ac += effect.ac_bonus
                    game.message_log.add_message(f"The {target.name} is guarded! Target AC: {target_ac}", (100, 255, 255))
        game.message_log.add_message(
            f"The {self.name} rolls {roll_message_part} + {attack_bonus} (Attack Bonus) = {attack_roll_total} vs AC {target_ac}",
            (255, 150, 150)
        )
        hit_successful = False
        if is_critical_hit:
            game.message_log.add_message("CRITICAL HIT!", (255, 100, 100))
            hit_successful = True
        elif is_critical_fumble:
            game.message_log.add_message("CRITICAL FUMBLE!", (150, 150, 150))
            hit_successful = False
        else:
            hit_successful = (attack_roll_total >= target_ac)


        if hit_successful:
            damage_rolls = []
            for _ in range(self.num_damage_dice * (2 if is_critical_hit else 1)):
                damage_rolls.append(random.randint(1, self.monster_die_type))

            damage_total = sum(damage_rolls) + self.damage_modifier

            game.message_log.add_message(f"Rolls {damage_rolls} + {self.damage_modifier} (Damage Modifier) = {damage_total}", (230, 200, 150))

            damage_dealt = target.take_damage(damage_total, game)

            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game.floating_texts.extend([hit_text, damage_text])

            if not target.alive:
                game.message_log.add_message(f"{target.name} has been slain!", (200, 0, 0))
            else:
                hp_message = f"{target.name} has {target.hp}/{target.max_hp} HP"
                hp_color = (255, 200, 0) if target.hp > target.max_hp * 0.3 else (255, 100, 0)
                game.message_log.add_message(hp_message, hp_color)

            if self.can_poison:
                if not target.make_saving_throw("CON", self.poison_dc, game):
                    target.add_status_effect("Poisoned", self.poison_duration, game, source=self)
            if self.can_acid_burn:
                if not target.make_saving_throw("DEX", self.acid_burn_dc, game):
                    target.add_status_effect("AcidBurned", self.acid_burn_duration, game, source=self)
            if self.can_burn:
                if not target.make_saving_throw("DEX", self.burn_dc, game):
                    target.add_status_effect("Burning", self.burn_duration, game, source=self)

        else:
            miss_messages = [
                f"The {self.name}'s attack misses!",
                f"{target.name} dodges the {self.name}'s strike!",
                f"The {self.name} swings wildly and misses!",
                f"{target.name} twists aside just in time!",
                f"The {self.name}'s blow smashes into stone instead!",
                f"{target.name} parries and deflects the strike!",
                f"The {self.name} lunges, but {target.name} slips away!",
                f"A sudden stumble throws the {self.name}'s aim wide!",
                f"{target.name} ducks beneath the attack with practiced ease!",
                f"The {self.name}'s weapon cuts only air!",
                f"With a deft step, {target.name} avoids certain harm!",
                f"The {self.name}'s strike glances harmlessly off armor!",
                f"A burst of sparks flies as the attack scrapes the wall!",
                f"{target.name} sidesteps smoothly, the attack wasted!"
            ]
            game.message_log.add_message(random.choice(miss_messages), (200, 200, 200))
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game.floating_texts.append(miss_text)

            if hasattr(target, 'active_status_effects'):
                for effect in target.active_status_effects:
                    if isinstance(effect, ParryBuff):
                        game.message_log.add_message(f"{target.name} counters with a devastating riposte!", (255, 255, 0))
                        game.handle_player_attack(self, game)
                        break


    def ranged_attack(self, target, game):
        """More powerful ranged attacks"""
        if target is None or not target.alive:
            return
    
        roll1 = random.randint(1, 20)
        final_d20_roll = roll1

        game.message_log.add_message(f"The {self.name} takes aim at {target.name}!", (255, 150, 0))
        
        attack_roll_total = final_d20_roll + self.ranged_attack_bonus

        is_critical_hit = (final_d20_roll == 20)
        is_critical_fumble = (final_d20_roll == 1)

        target_ac = target.armor_class
        if hasattr(target, 'active_status_effects'):
            for effect in target.active_status_effects:
                if isinstance(effect, EvasionBuff):
                    target_ac += effect.dodge_bonus
                if isinstance(effect, BlessingOfAgility):
                    target_ac += effect.ac_bonus
        game.message_log.add_message(
            f"The {self.name} rolls {final_d20_roll} + {self.ranged_attack_bonus} (Attack Bonus) = {attack_roll_total} vs AC {target_ac}",
            (200, 200, 255)
        )

        hit_successful = False
        if is_critical_hit:
            crit_msgs = [
                "CRITICAL HIT! The strike lands with devastating force!",
                "A perfect blow! Critical Hit!",
                "The attack finds its mark — a Critical Hit!",
                "A savage strike! Critical damage dealt!"
            ]
            game.message_log.add_message(random.choice(crit_msgs), (255, 80, 80))
            hit_successful = True

        elif is_critical_fumble:
            fumble_msgs = [
                "CRITICAL FUMBLE! The attack goes horribly wrong!",
                "A misstep! Critical Fumble!",
                "Disaster! The strike falters into a Critical Fumble!",
                "A costly mistake — Critical Fumble!"
            ]
            game.message_log.add_message(random.choice(fumble_msgs), (150, 150, 150))
            hit_successful = False
        else:
            hit_successful = (attack_roll_total >= target_ac)

        
        if hit_successful:
            damage_rolls = []
            for _ in range(self.num_damage_dice * (2 if is_critical_hit else 1)):
                damage_rolls.append(random.randint(1, self.monster_die_type))

            damage_total = sum(damage_rolls) + self.damage_modifier

            game.message_log.add_message(f"Rolls {damage_rolls} + {self.damage_modifier} (Damage Modifier) = {damage_total}", (230, 200, 150))

            damage_dealt = target.take_damage(damage_total, game)

            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0))
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0))
            game.floating_texts.extend([hit_text, damage_text])

            if not target.alive:
                game.message_log.add_message(f"{target.name} has been slain!", (200, 0, 0))
            else:
                hp_message = f"{target.name} has {target.hp}/{target.max_hp} HP"
                hp_color = (255, 200, 0) if target.hp > target.max_hp * 0.3 else (255, 100, 0)
                game.message_log.add_message(hp_message, hp_color)

            if self.can_poison:
                if not target.make_saving_throw("CON", self.poison_dc, game):
                    target.add_status_effect("Poisoned", self.poison_duration, game, source=self)
            if self.can_acid_burn:
                if not target.make_saving_throw("DEX", self.acid_burn_dc, game):
                    target.add_status_effect("AcidBurned", self.acid_burn_duration, game, source=self)
            if self.can_burn:
                if not target.make_saving_throw("DEX", self.burn_dc, game):
                    target.add_status_effect("Burning", self.burn_duration, game, source=self)

        else:
            miss_messages = [
                f"The {self.name}'s attack misses!",
                f"{target.name} dodges the {self.name}'s attack!"
            ]
            game.message_log.add_message(random.choice(miss_messages), (200, 200, 200))
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            game.floating_texts.append(miss_text)


    def provoke(self, game_instance=None):
        """
        Force this monster into AGGRESSIVE disposition, permanently, and
        wake it if it wasn't already active. Called from take_damage() so
        a PASSIVE/NEUTRAL creature (see the Disposition docstring near the
        top of this file) that was ignoring the player starts fighting
        back the instant it takes a hit -- from the player or from
        anything else that can call take_damage() (a stray fire tile, a
        summoned ally), not just a deliberate melee attack -- exactly like
        Myconid_Grove.json/Centaur_Crossing.json's world-encounter
        versions of the same creatures never offer a way to fight after
        choosing to walk away peacefully. A no-op disposition-wise (aside
        from the wake-up) if the monster was already AGGRESSIVE.

        The first time this actually flips the disposition, it also
        alerts the rest of this monster's group (see `group_id`) -- a
        centaur band or myconid grove fights as one the instant any single
        member is struck, not just the one that got hit.
        """
        was_provoked = self.disposition != Disposition.AGGRESSIVE
        self.disposition = Disposition.AGGRESSIVE
        self.is_active = True
        if was_provoked and game_instance:
            game_instance.message_log.add_message(f"The {self.name} turns on you!", (255, 100, 100))
            self._alert_group(game_instance)

    def _alert_group(self, game_instance):
        """
        Turn every other living monster sharing this one's `group_id`
        AGGRESSIVE too, so attacking one member of a spawned pack (see
        `group_id`'s docstring in __init__) brings the whole group into
        the fight at once instead of picking its members off one at a
        time while the rest look on. Only reached from provoke() the
        instant *this* monster is the one flipping from non-aggressive,
        so a group alert only ever fires once per fight, not once per hit.
        """
        if not self.group_id:
            return

        alerted_any = False
        for entity in getattr(game_instance, "entities", ()):
            if entity is self or not isinstance(entity, Monster):
                continue
            if not entity.alive or entity.group_id != self.group_id:
                continue
            if entity.disposition == Disposition.AGGRESSIVE:
                continue

            entity.disposition = Disposition.AGGRESSIVE
            entity.is_active = True
            entity.last_known_player_position = self.last_known_player_position
            entity.ai_state = AI_State.CHASING
            alerted_any = True

        if alerted_any:
            game_instance.message_log.add_message(
                "The rest of the group turns hostile!", (255, 100, 100)
            )

    def take_damage(self, amount, game_instance=None, damage_type=None):
        """Handle taking damage and return actual damage taken"""
        # A sleeping monster that gets hit rouses its whole ambush group at
        # once - see Game._spawn_world_encounter_monsters() for how the group
        # is assembled and put to sleep in the first place.
        if not self.is_active and self.encounter_group:
            for member in self.encounter_group:
                if member.alive:
                    member.is_active = True
            if game_instance:
                game_instance.message_log.add_message(
                    "The rest spring awake at the commotion!", (255, 150, 100)
                )
        self.provoke(game_instance)

        damage_taken = amount 
        self.hp -= damage_taken
        
        if game_instance and game_instance.player:
            self.last_known_player_position = (game_instance.player.x, game_instance.player.y)
            if True:
                self.ai_state = AI_State.CHASING
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
            
        return damage_taken

    def die(self, game_instance, killer=None):
        """Handle death, drop loot, and return XP value"""
        bloodstain = Bloodstain(self.x, self.y, game_instance)
        game_instance.bloodstains.append(bloodstain)

        if killer and hasattr(killer, 'active_status_effects'):
            for effect in killer.active_status_effects:
                if effect.name == "Blessing of Bloodlust":
                    heal_amount = effect.hp_restore_on_kill
                    killer.heal(heal_amount)
                    game_instance.message_log.add_message(f"Bloodlust restores {heal_amount} HP!", (255, 0, 0))
                    floating_text = FloatingText(killer.x, killer.y, f"+{heal_amount}", (0, 255, 0))
                    game_instance.floating_texts.append(floating_text)
                    break

        for item_template, drop_chance in self.loot_table:
            if random.random() < drop_chance:
                item_vars = {k: v for k, v in vars(item_template).items() if not k.startswith('_')}
                
                item_vars.pop('owner', None)
                item_vars.pop('x', None)
                item_vars.pop('y', None)

                new_item = item_template.__class__(**item_vars)
                new_item.x = self.x
                new_item.y = self.y
                game_instance.game_map.items_on_ground.append(new_item)
                game_instance.message_log.add_message(f"The {self.name} dropped a {new_item.name}!", (0, 255, 255))

        return self.base_xp

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        """Adds a status effect to the monster."""
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
            new_effect.apply_effect(self, game_instance)
        else:
            game_instance.message_log.add_message(f"Warning: Attempted to add unknown status effect to monster: {effect_name}", (255, 0, 0))
            print(f"Warning: Attempted to add unknown status effect to monster: {effect_name}")


    def process_status_effects(self, game_instance):
        """Processes all active status effects on the monster."""
        effects_to_remove = []
        for effect in self.active_status_effects:
            effect.apply_effect(self, game_instance)
            effect.tick_down()
            if effect.turns_left <= 0:
                effects_to_remove.append(effect)
        
        for effect in effects_to_remove:
            self.active_status_effects.remove(effect)
            effect.on_end(self, game_instance)


    def occupies_tile(self, x, y):
        """
        Returns True if the given (x, y) coordinate is within the monster's footprint.
        """
        size = getattr(self, 'footprint_size', 1)
        return (self.x <= x < self.x + size) and (self.y <= y < self.y + size)

    def is_adjacent_to(self, other_entity):
        """
        Checks if this monster is adjacent (including diagonals) to another entity,
        considering the footprint size of both.
        """
        size_self = getattr(self, 'footprint_size', 1)
        size_other = getattr(other_entity, 'footprint_size', 1)

        self_tiles = [(self.x + dx, self.y + dy) for dx in range(size_self) for dy in range(size_self)]
        other_tiles = [(other_entity.x + dx, other_entity.y + dy) for dx in range(size_other) for dy in range(size_other)]

        for (x1, y1) in self_tiles:
            for (x2, y2) in other_tiles:
                if max(abs(x1 - x2), abs(y1 - y2)) == 1:
                    return True
        return False

    def get_footprint_tiles(self, x=None, y=None):
        """
        Returns a list of (x, y) tuples representing all tiles occupied by the monster's footprint.
        If x and y are None, uses current position.
        """
        base_x = x if x is not None else self.x
        base_y = y if y is not None else self.y
        size = getattr(self, 'footprint_size', 1)
        return [(base_x + dx, base_y + dy) for dx in range(size) for dy in range(size)]

    def get_adjacent_tiles_in_direction(self, dx, dy):
        """
        Returns a set of tiles (x, y) that are adjacent to the monster's footprint in the direction (dx, dy).
        This helps identify which tiles the monster would move into or need to destroy.
        """
        footprint_tiles = self.get_footprint_tiles()
        adjacent_tiles = set()

        for (x, y) in footprint_tiles:
            adj_x = x + dx
            adj_y = y + dy
            adjacent_tiles.add((adj_x, adj_y))

        return adjacent_tiles

    def can_move_to(self, new_x, new_y, game_map, game):
        """
        Checks if the monster can move to (new_x, new_y).
        Destroys destructible tiles adjacent to the footprint in the movement direction.
        Returns True if move is possible (after destroying obstacles), False otherwise.
        """
        size = getattr(self, 'footprint_size', 1)
        current_footprint = self.get_footprint_tiles()
        new_footprint = [(new_x + dx, new_y + dy) for dx in range(size) for dy in range(size)]

        dx = new_x - self.x
        dy = new_y - self.y

        for (tx, ty) in new_footprint:
            if not (0 <= tx < game_map.width and 0 <= ty < game_map.height):
                return False

        for entity in game.entities:
            if entity != self and entity.alive and entity.blocks_movement:
                for (tx, ty) in new_footprint:
                    if hasattr(entity, 'occupies_tile'):
                        if entity.occupies_tile(tx, ty):
                            return False
                    else:
                        if entity.x == tx and entity.y == ty:
                            return False

        adjacent_tiles = self.get_adjacent_tiles_in_direction(dx, dy)

        for (ax, ay) in adjacent_tiles:
            if not (0 <= ax < game_map.width and 0 <= ay < game_map.height):
                continue
            tile = game_map.tiles[ay][ax]
            if not game_map.is_walkable(ax, ay):
                if tile.destructible:
                    game.message_log.add_message(f"The massive {self.name} smashes the {tile.name}!", (255, 165, 0))
                    game_map.tiles[ay][ax] = floor
                    game.minimap_needs_redraw = True
                    game.floating_texts.append(FloatingText(ax, ay, "SMASH!", (255, 100, 0)))

                    if tile.name in ["Crate", "Barrel"]:
                        import random
                        if random.random() < 0.70:
                            new_junk = wood_plank.__class__(
                                name=wood_plank.name,
                                char=wood_plank.char,
                                color=wood_plank.color,
                                description=wood_plank.description
                            )
                            new_junk.x = ax
                            new_junk.y = ay
                            game_map.items_on_ground.append(new_junk)
                        elif random.random() < 0.20:
                            new_food = meat.__class__(
                                name=meat.name,
                                char=meat.char,
                                color=meat.color,
                                description=meat.description,
                                healing_value=meat.healing_value,
                                price=meat.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.35:
                            new_food = green_apple.__class__(
                                name=green_apple.name,
                                char=green_apple.char,
                                color=green_apple.color,
                                description=green_apple.description,
                                healing_value=green_apple.healing_value,
                                price=green_apple.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.25:
                            new_food = fromage.__class__(
                                name=fromage.name,
                                char=fromage.char,
                                color=fromage.color,
                                description=fromage.description,
                                healing_value=fromage.healing_value,
                                price=fromage.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.30:
                            new_food = bread.__class__(
                                name=bread.name,
                                char=bread.char,
                                color=bread.color,
                                description=bread.description,
                                healing_value=bread.healing_value,
                                price=bread.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)
                        elif random.random() < 0.40:
                            new_food = mushroom.__class__(
                                name=mushroom.name,
                                char=mushroom.char,
                                color=mushroom.color,
                                description=mushroom.description,
                                healing_value=mushroom.healing_value,
                                price=mushroom.price
                            )
                            new_food.x = ax
                            new_food.y = ay
                            game_map.items_on_ground.append(new_food)
                            game.message_log.add_message(f"A {new_food.name} drops from the {tile.name}!", new_food.color)

                else:
                    return False

        for (tx, ty) in new_footprint:
            tile = game_map.tiles[ty][tx]
            if self.footprint_size == 1 and is_water_tile(tile) and not self.can_swim:
                return False
            if not game_map.is_walkable(tx, ty):
                return False

        return True

    def take_turn(self, player, game_map, game):
        """Handle monster's combat and movement with improved AI"""
        if not self.alive:
            return

        self.process_status_effects(game)
        if not self.alive:
            return

        # PASSIVE/NEUTRAL monsters (see the Disposition docstring near the
        # top of this file) never detect, target, or chase anything on
        # their own -- they just stand/wander undisturbed until provoke()
        # (called from take_damage() the instant they're hit) permanently
        # flips them to AGGRESSIVE, at which point this check stops
        # short-circuiting and every turn from then on runs the normal AI
        # below exactly like any other monster. Status effects above still
        # process regardless (a passive creature that wandered onto a fire
        # tile still burns), since disposition only governs whether *this*
        # monster initiates anything against the player.
        if self.disposition != Disposition.AGGRESSIVE:
            return

        # Check for player's summoned entities and prioritize attacking them.
        # Candidates come from game._owned_blocking_entities, refreshed once
        # per player action (see Game._refresh_owned_blocking_entities_cache())
        # instead of every monster re-scanning the full entity list here --
        # this used to run unconditionally on every active monster's turn,
        # attack turns included, which made it the dominant per-turn cost in
        # a crowded fight even after movement-triggered FOV recomputes were
        # fixed. .alive is still re-checked per candidate below, so a summon
        # that died earlier in this same batch (to another monster's attack)
        # is simply skipped rather than trusted from the snapshot.
        target_entity = None
        target_distance = float('inf')

        for entity in getattr(game, '_owned_blocking_entities', None) or []:
            if entity.alive:
                dist = self.distance_to(entity.x, entity.y)
                if dist < target_distance:
                    target_distance = dist
                    target_entity = entity


        if target_entity is None:
            target_entity = player
            target_distance = self.distance_to(player.x, player.y)

        # No summons around - fighting-back guards (see GuardVictim in
        # entities/dungeon_npcs.py) are the next priority, ahead of the player.
        if target_entity is None:
            from entities.dungeon_npcs import GuardVictim
            for entity in game.entities:
                if isinstance(entity, GuardVictim) and entity.alive:
                    dist = self.distance_to(entity.x, entity.y)
                    if dist < target_distance:
                        target_distance = dist
                        target_entity = entity

        # Decrement timers
        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1
        if self.telegraph_timer > 0:
            self.telegraph_timer -= 1
            if self.telegraph_timer == 0 and self.pending_telegraph_tiles:
                for tx, ty in self.pending_telegraph_tiles:
                    if target_entity.x == tx and target_entity.y == ty and target_entity.alive:
                        dmg = max(1, getattr(self, 'damage_modifier', 2) + random.randint(1, 20))
                        target_entity.take_damage(dmg, game, damage_type='fire')
                        game.floating_texts.append(FloatingText(tx, ty, f"-{dmg}", (255, 80, 80)))
                self.pending_telegraph_tiles = []
        if not self.alive:
            return

        if not self.is_active:
            if self.sleep_cooldown > 0:
                self.sleep_cooldown -= 1
            return

        if self.sleep_cooldown == 0 and not self.is_active:
            self.is_active = True
            game.message_log.add_message(f"The {self.name} stirs awake!", self.color)

        dist_to_player = self.distance_to(player.x, player.y)
        player_detected = self.detect_player(player, game)

        if not player_detected and self.is_intelligent:
            self.check_torchlight_in_range(game)

        # --- IMPROVED: AI STATE MANAGEMENT FOR INTELLIGENT MONSTERS ---
        if self.is_intelligent and player_detected:
            self_hp_pct = self.hp_percentage()
            player_hp_pct = player.hp / player.max_hp if player.max_hp > 0 else 0
            
            # State transitions based on health conditions
            if self_hp_pct < self.flee_hp_threshold:
                # Monster is badly wounded
                if player_hp_pct > self.player_safe_hp_threshold:
                    # Player is relatively healthy - FLEE from combat
                    if self.ai_state != AI_State.FLEEING and self.ai_state != AI_State.CHASING:
                        self.ai_state = AI_State.FLEEING
                        self.consecutive_failed_flee_turns = 0
                        game.message_log.add_message(f"The {self.name} attempts to escape!", (255, 150, 0))
                elif (self_hp_pct < self.desperate_fight_hp_threshold and 
                      player_hp_pct < self.desperate_fight_hp_threshold):
                    # Both are critically low - DESPERATE_FIGHT
                    if self.ai_state != AI_State.DESPERATE_FIGHT:
                        self.ai_state = AI_State.DESPERATE_FIGHT
                        self.consecutive_failed_flee_turns = 0
                        game.message_log.add_message(f"The {self.name} fights desperately for survival!", (255, 100, 100))
                else:
                    # Default to chasing if conditions don't match
                    if self.ai_state not in [AI_State.CHASING, AI_State.KITING]:
                        self.ai_state = AI_State.CHASING
                        self.consecutive_failed_flee_turns = 0
            else:
                # Monster is healthy enough - reset fleeing if applicable
                if self.ai_state == AI_State.FLEEING:
                    self.ai_state = AI_State.CHASING
                    self.consecutive_failed_flee_turns = 0

        # Handle AI states for intelligent monsters
        if self.is_intelligent:
            if self.ai_state == AI_State.INVESTIGATE:
                if player_detected:
                    self.ai_state = AI_State.CHASING
                    self.investigate_turns_left = 0
                    game.message_log.add_message(f"The {self.name} re-acquires your scent and resumes chasing!", self.color)
                else:
                    if self.investigate_turns_left > 0:
                        self.investigate_turns_left -= 1
                        if self.last_known_player_position:
                            target_x, target_y = self.last_known_player_position
                            if (self.x, self.y) == (target_x, target_y):
                                if self.investigate_turns_left == 0:
                                    game.message_log.add_message(f"The {self.name} finds nothing and gives up investigating.", (150, 150, 150))
                                    self.patrol(game_map, game)
                                    self.last_known_player_position = None
                            else:
                                self.move_towards(target_x, target_y, game_map, game)
                        else:
                            self.patrol(game_map, game)
                    else:
                        self.patrol(game_map, game)
                        self.last_known_player_position = None
                return

            # KITING STATE
            if self.ai_state == AI_State.KITING:
                if player_detected:
                    if self.kite(target_entity, game_map, game):
                        return
                else:
                    self.ai_state = AI_State.INVESTIGATE
                    self.investigate_turns_left = 4
                    self.last_known_player_position = self.last_known_player_position or (player.x, player.y)
                    game.message_log.add_message(f"The {self.name} loses track of you.", (150, 150, 150))
                return

            # --- IMPROVED: FLEEING STATE WITH CORNERING DETECTION ---
            if self.ai_state == AI_State.FLEEING:
                fled_success, is_cornered = self.flee(player, game_map, game)
                
                if is_cornered:
                    # Monster is trapped - switch to desperate fight
                    game.message_log.add_message(
                        f"The {self.name} is cornered and fights back viciously!",
                        (255, 100, 100)
                    )
                    self.ai_state = AI_State.DESPERATE_FIGHT
                    # Fall through to desperate fight logic
                elif fled_success:
                    return  # Successfully fled, end turn
                else:
                    # Still trying to flee but movement blocked
                    return

            # --- IMPROVED: DESPERATE_FIGHT STATE ---
            if self.ai_state == AI_State.DESPERATE_FIGHT:
                if self.is_ranged and target_distance <= self.range and \
                   game.check_line_of_sight(self.x, self.y, target_entity.x, target_entity.y):
                    self.ranged_attack(target_entity, game)
                    return
                elif self.is_adjacent_to(target_entity):
                    self.attack(target_entity, game)
                    return
                else:
                    # Charge toward target aggressively. A capped
                    # max_expansions here (rather than astar()'s default
                    # 4000) matters specifically in crowded fights: this
                    # runs once per non-adjacent monster's turn, all
                    # within the same synchronous batch pass before a
                    # frame renders (see game.py's turn-processing loop),
                    # so several monsters each climbing toward the full
                    # budget while routing around each other in the same
                    # frame is what shows up as a stutter/freeze as
                    # monster count grows. The target is always nearby by
                    # definition here, so a small local search radius is
                    # all this ever legitimately needs.
                    approach_pos = self._approach_tile_near(target_entity, game_map, game)
                    if approach_pos is None:
                        game.message_log.add_message(f"The {self.name} is blocked and cannot reach {target_entity.name}!", (100, 100, 100))
                        return
                    path = astar(
                        game_map,
                        (self.x, self.y),
                        approach_pos,
                        entities=[e for e in game.entities if e != self and e.alive and e.blocks_movement],
                        moving_entity=self,
                        max_expansions=MONSTER_PATHFINDING_MAX_EXPANSIONS
                    )
                    if path and len(path) > 1:
                        next_step = path[1]
                        new_x, new_y = next_step

                        if self.can_move_to(new_x, new_y, game_map, game):
                            self.x = new_x
                            self.y = new_y
                            game.refresh_monster_wake_state()
                        else:
                            game.message_log.add_message(f"The {self.name} is blocked and cannot reach {target_entity.name}!", (100, 100, 100))
                    else:
                        game.message_log.add_message(f"The {self.name} cannot find a path to {target_entity.name}!", (150, 150, 150))
                    return

            if self.ai_state == AI_State.CHASING:
                # Decision: should intelligent ranged monsters use kiting?
                if self.is_ranged and self.can_kite and player_detected:
                    self.ai_state = AI_State.KITING
                    if self.kite(target_entity, game_map, game):
                        return

                if self.is_ranged and target_distance <= self.range and game.check_line_of_sight(self.x, self.y, target_entity.x, target_entity.y):
                    self.ranged_attack(target_entity, game)
                    return

                if self.is_adjacent_to(target_entity):
                    self.attack(target_entity, game)
                    return

                target_pos = (target_entity.x, target_entity.y) if game.check_line_of_sight(self.x, self.y, target_entity.x, target_entity.y) else self.last_known_player_position

                if target_pos:
                    # Retarget from the target's own tile to an open tile
                    # next to it -- not because astar can't path there
                    # (it explicitly allows an occupied goal, see
                    # pathfinding.py), but because can_move_to() would
                    # refuse to actually step onto it anyway, so pathing
                    # there directly would just waste the search. A
                    # remembered last-known position isn't necessarily
                    # occupied by anyone right now, so only retarget when
                    # target_pos is the target's live tile. If the target
                    # is fully surrounded (no approach tile available at
                    # all), skip astar entirely and go straight to the
                    # greedy-movement fallback below, same as "no path
                    # found".
                    path = None
                    astar_goal = target_pos
                    if target_pos == (target_entity.x, target_entity.y):
                        astar_goal = self._approach_tile_near(target_entity, game_map, game)

                    if astar_goal is not None:
                        path = astar(
                            game_map,
                            (self.x, self.y),
                            astar_goal,
                            entities=[e for e in game.entities if e != self and e.alive and e.blocks_movement],
                            moving_entity=self,
                            # Capped rather than astar()'s default 4000 --
                            # this runs once per non-adjacent monster's
                            # turn, all within the same synchronous batch
                            # pass before a frame renders (see game.py's
                            # turn-processing loop). A crowded fight is
                            # exactly the case where several monsters each
                            # climb toward the full budget routing around
                            # each other in the same frame, which is what
                            # shows up as a stutter/freeze as monster
                            # count grows -- and the target is always
                            # nearby here, so a small local search is all
                            # this legitimately needs.
                            max_expansions=MONSTER_PATHFINDING_MAX_EXPANSIONS
                        )
                    if path and len(path) > 1:
                        next_step = path[1]
                        new_x, new_y = next_step

                        if self.can_move_to(new_x, new_y, game_map, game):
                            self.x = new_x
                            self.y = new_y
                            game.refresh_monster_wake_state()
                        else:
                            game.message_log.add_message(f"The {self.name} is blocked and waits.", (100, 100, 100))
                    else:
                        # Pathfinding failed: try greedy direct movement towards target
                        dx = target_entity.x - self.x
                        dy = target_entity.y - self.y

                        step_x = 0
                        step_y = 0

                        if dx != 0:
                            step_x = dx // abs(dx)
                        if dy != 0:
                            step_y = dy // abs(dy)

                        candidates = []
                        if step_x != 0 and step_y != 0:
                            candidates.append((self.x + step_x, self.y + step_y))
                        if step_x != 0:
                            candidates.append((self.x + step_x, self.y))
                        if step_y != 0:
                            candidates.append((self.x, self.y + step_y))

                        moved = False
                        for nx, ny in candidates:
                            if not (0 <= nx < game_map.width and 0 <= ny < game_map.height):
                                continue

                            if self.can_move_to(nx, ny, game_map, game):
                                self.x = nx
                                self.y = ny
                                game.refresh_monster_wake_state()
                                moved = True
                                break

                        if not moved:
                            game.message_log.add_message(f"The {self.name} is blocked and waits.", (100, 100, 100))
                else:
                    self.patrol(game_map, game)
                return
        else:
            # Non-intelligent monsters chase target if detected, else patrol
            if player_detected:
                if self.is_ranged and target_distance <= self.range:
                    self.ranged_attack(target_entity, game)
                    return
                elif self.is_adjacent_to(target_entity):
                    self.attack(target_entity, game)
                    return
                else:
                    self.move_towards(target_entity.x, target_entity.y, game_map, game)
                    return
            else:
                self.patrol(game_map, game)
                return



    def can_occupy_position(self, target_x: int, target_y: int, game_map, entities, exclusions=None) -> bool:
        """Check if this entity can occupy a top-left position with its full footprint.
        Excludes any entities in the exclusions iterable from blocking checks.
        """
        size = getattr(self, 'footprint_size', 1)
        if exclusions is None:
            exclusions = []
        if size <= 1:
            if not (0 <= target_x < game_map.width and 0 <= target_y < game_map.height):
                return False
            tile = game_map.tiles[target_y][target_x]
            if self.footprint_size == 1 and is_water_tile(tile) and not self.can_swim:
                return False
            if not game_map.is_walkable(target_x, target_y):
                return False
            for entity in entities:
                if entity in exclusions or entity is self:
                    continue
                if getattr(entity, 'alive', True) and getattr(entity, 'blocks_movement', False):
                    if hasattr(entity, 'occupies_tile'):
                        if entity.occupies_tile(target_x, target_y):
                            return False
                    elif entity.x == target_x and entity.y == target_y:
                        return False
            return True

        for offset_y in range(size):
            for offset_x in range(size):
                tile_x = target_x + offset_x
                tile_y = target_y + offset_y
                if not (0 <= tile_x < game_map.width and 0 <= tile_y < game_map.height):
                    return False
                tile = game_map.tiles[tile_y][tile_x]
                if self.footprint_size == 1 and is_water_tile(tile) and not self.can_swim:
                    return False
                if not game_map.is_walkable(tile_x, tile_y):
                    return False
                for entity in entities:
                    if entity in exclusions or entity is self:
                        continue
                    if getattr(entity, 'alive', True) and getattr(entity, 'blocks_movement', False):
                        if hasattr(entity, 'occupies_tile'):
                            if entity.occupies_tile(tile_x, tile_y):
                                return False
                        elif getattr(entity, 'x', None) == tile_x and getattr(entity, 'y', None) == tile_y:
                            return False
        return True
    
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
        
        self.hp = 48
        self.max_hp = 48
        self.attack_bonus = 5
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 8
        self.blocks_movement = True
        self.can_acid_burn = True
        self.acid_burn_dc = 12
        self.acid_burn_duration = 3
        self.acid_burn_damage_per_turn = 3
        self.damage_modifier = 3
        self.num_damage_dice = 1
        self.is_intelligent = False 

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        } 

    def take_damage(self, amount, game_instance, damage_type=None):
        """
        Mimic's take_damage method.
        If disguised and takes damage, it reveals itself.
        """
        if self.disguised:
            game_instance.message_log.add_message(f"You strike the {self.name}!", (255, 165, 0))
            self.reveal(game_instance) 
            
        damage_taken = super().take_damage(amount, game_instance, damage_type)

        if not self.alive and not self.disguised:
            game_instance.message_log.add_message(f"The {self.name} shudders and collapses!", (255, 0, 0))

        return damage_taken

    def reveal(self, game_instance):
        """Mimic fully reveals its true form."""
        if self.disguised:
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealing. Current char (before change): {self.char}")
            self.disguised = False
            
            self.char = self.revealed_char 
            self.color = self.revealed_color 
            
            game_instance.message_log.add_message("The object suddenly sprouts teeth and eyes! It's a MIMIC!", (255, 0, 0))
            game_instance.message_log.add_message("Prepare for battle!", (255, 100, 100))
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealed. New char: {self.char}, color: {self.color}")
            self.is_active = True
            self.ai_state = AI_State.CHASING
            if self.is_adjacent_to(game_instance.player):
                self.attack(game_instance.player, game_instance)
            
            if self not in game_instance.entities:
                game_instance.entities.append(self)
                print(f"DEBUG: Mimic added to game.entities.")
            if self not in game_instance.turn_order:
                self.roll_initiative()
                game_instance.turn_order.append(self)
                game_instance.turn_order = sorted(game_instance.turn_order, key=lambda e: e.initiative, reverse=True)
                print(f"DEBUG: Mimic added to game.turn_order.")
            
            if self in game_instance.game_map.items_on_ground:
                game_instance.game_map.items_on_ground.remove(self)
                print(f"DEBUG: Mimic removed from game_map.items_on_ground upon reveal.")
            
            from world.tile import floor
            game_instance.game_map.tiles[self.y][self.x] = floor
            print(f"DEBUG: MimicTile at ({self.x},{self.y}) replaced with floor tile.")
            
            game_instance.update_fov()

    def take_turn(self, player, game_map, game):
        """Mimic's turn logic."""
        if not self.alive:
            return
        
        if self.disguised:
            return
        
        super().take_turn(player, game_map, game)

class Mimic(Monster):
    def __init__(self, x, y, disguise_char, initial_color): 
        super().__init__(x, y, disguise_char, 'Mimic', initial_color) 
    
        self.disguised = True
        
        self._disguise_char = disguise_char 
        self._disguise_color = initial_color 
        if disguise_char == 'K': # Crate
            self.revealed_char = 'K' # Generic Mimic char
        elif disguise_char == 'B': # Barrel
            self.revealed_char = 'B' 
        elif disguise_char == 'C': # Chest
            self.revealed_char = 'M' 
        else:
            self.revealed_char = 'M' 
        self.revealed_color = (255, 0, 0) 
        
        self.hp = 48 # Mimic specific HP
        self.max_hp = 48
        self.attack_bonus = 5
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 8
        self.blocks_movement = True
        self.can_acid_burn = True
        self.acid_burn_dc = 12
        self.acid_burn_duration = 3
        self.acid_burn_damage_per_turn = 3
        self.damage_modifier = 3
        self.num_damage_dice = 1
        # Mimics are not "intelligent" in the sense of fleeing, they are ambush predators
        self.is_intelligent = False 

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,  # Proficient in Dexterity saves
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        } 

    def take_damage(self, amount, game_instance, damage_type=None):
        """
        Mimic's take_damage method.
        If disguised and takes damage, it reveals itself.
        """
        if self.disguised:
            game_instance.message_log.add_message(f"You strike the {self.name}!", (255, 165, 0))
            self.reveal(game_instance) 
            
        damage_taken = super().take_damage(amount, game_instance, damage_type)

        if not self.alive and not self.disguised:
            game_instance.message_log.add_message(f"The {self.name} shudders and collapses!", (255, 0, 0))

        return damage_taken

    def reveal(self, game_instance):
        """Mimic fully reveals its true form."""
        if self.disguised:
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealing. Current char (before change): {self.char}")
            self.disguised = False
            
            self.char = self.revealed_char 
            self.color = self.revealed_color 
            
            game_instance.message_log.add_message("The object suddenly sprouts teeth and eyes! It's a MIMIC!", (255, 0, 0))
            game_instance.message_log.add_message("Prepare for battle!", (255, 100, 100))

            floatingtext = FloatingText(self.x, self.y, "MIMIC!", (255, 0, 0))
            game_instance.floating_texts.append(floatingtext)
            print(f"DEBUG: Mimic at ({self.x},{self.y}) revealed. New char: {self.char}, color: {self.color}")
            # Activate the mimic so it can take turns immediately after reveal
            self.is_active = True
            self.ai_state = AI_State.CHASING
            # Mimic immediately attacks the player if adjacent after revealing
            if self.is_adjacent_to(game_instance.player):
                self.attack(game_instance.player, game_instance)
            
            if self not in game_instance.entities:
                game_instance.entities.append(self)
                print(f"DEBUG: Mimic added to game.entities.")
            if self not in game_instance.turn_order:
                self.roll_initiative()
                game_instance.turn_order.append(self)
                game_instance.turn_order = sorted(game_instance.turn_order, key=lambda e: e.initiative, reverse=True)
                print(f"DEBUG: Mimic added to game.turn_order.")
            
            if self in game_instance.game_map.items_on_ground:
                game_instance.game_map.items_on_ground.remove(self)
                print(f"DEBUG: Mimic removed from game_map.items_on_ground upon reveal.")
            
            from world.tile import floor
            game_instance.game_map.tiles[self.y][self.x] = floor
            print(f"DEBUG: MimicTile at ({self.x},{self.y}) replaced with floor tile.")
            
            game_instance.update_fov()

    def take_turn(self, player, game_map, game):
        """Mimic's turn logic."""
        if not self.alive:
            return
        
        if self.disguised:
            return
        
        # If not disguised, behave like a normal monster (Stage 2 combat form)
        super().take_turn(player, game_map, game)


# --- MONSTER CLASSES ---

class GiantRat(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'R', 'Giant Rat', (0, 130, 8))
        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 12
        self.base_xp = 50
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 8
        self.num_damage_dice = 1
        self.is_intelligent = False

        self.loot_table = [
            (meat, 0.25)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Ooze(Monster):  
    def __init__(self, x, y):
        super().__init__(x, y, 'OZ', 'Ooze', (100, 100, 100))
        self.can_swim = True
        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 2
        self.armor_class = 8
        self.base_xp = 100
        self.monster_die_type = 6
        self.num_damage_dice = 2
        self.acid_burn_dc = 14
        self.acid_burn_duration = 4
        self.damage_modifier = 1
        self.detection_range = 4
        self.acid_burn_damage_per_turn = 3
        self.is_intelligent = False

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Goblin(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GB', 'Goblin', (0, 255, 0))
        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 50
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_intelligent = True
        self.can_poison = True

        self.loot_table = [
            (iron_dagger, 0.8)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class GoblinArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GA', 'Goblin Archer', (0, 200, 0))
        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 50
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2
        self.range = 4
        self.ranged_die_type = 6
        self.ranged_num_dice = 1
        self.is_intelligent = True
        self.can_poison = True
        
        # Enable kiting for this ranged monster
        self.can_kite = True
        self.ideal_kiting_distance = self.range - 1
        self.kiting_attack_threshold = 2

        self.loot_table = [
            (bread, 0.25)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Skeleton(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'SK', 'Skeleton', (200, 200, 200))
        self.hp = 13
        self.max_hp = 13
        self.attack_bonus = 2
        self.armor_class = 13
        self.base_xp = 50
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 4
        self.num_damage_dice = 1
        self.is_intelligent = False
        
        self.loot_table = [
            (bronze_short_sword, 0.85)
        ]
        
        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class SkeletonArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'SA', 'Skeleton Archer', (180, 180, 180))
        self.hp = 13
        self.max_hp = 13
        self.attack_bonus = 2
        self.armor_class = 13
        self.base_xp = 50
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2
        self.range = 4
        self.ranged_die_type = 6
        self.ranged_num_dice = 1
        self.is_intelligent = False

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class Orc(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'OR', 'Orc', (0, 128, 0))
        self.hp = 15
        self.max_hp = 15
        self.attack_bonus = 3
        self.armor_class = 13
        self.base_xp = 100
        self.monster_die_type = 12
        self.damage_modifier = 3
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_intelligent = True

        self.loot_table = [
            (steel_battle_axe, 0.75)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class Centaur(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'CE', 'Centaur', (139, 69, 19))
        self.hp = 45
        self.max_hp = 45
        self.attack_bonus = 3
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 8
        self.damage_modifier = 4
        self.detection_range = 6
        self.num_damage_dice = 2
        self.is_intelligent = True

        self.loot_table = [
            (pole_arm, 0.75),
            (studded_leather_armor, 0.50),
            (meat, 0.25)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

        # Territorial, not hostile on sight -- see the Disposition docstring
        # near the top of this file and Monster.provoke(). The player can
        # walk right up to a centaur band without a fight starting; landing
        # a hit on one (from the player or anything else) permanently flips
        # it, and every centaur it shares an encounter_group/pack with, to
        # AGGRESSIVE from then on.
        self.disposition = Disposition.PASSIVE

class CentaurArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'CA', 'Centaur Archer', (160, 82, 45))
        self.hp = 45
        self.max_hp = 45
        self.attack_bonus = 3
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 6
        self.damage_modifier = 3
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2
        self.range = 5
        self.ranged_die_type = 8
        self.ranged_num_dice = 1
        self.is_intelligent = True
        
        # Enable kiting for this ranged monster
        self.can_kite = True
        self.ideal_kiting_distance = self.range - 1
        self.kiting_attack_threshold = 2

        self.loot_table = [
            (iron_short_sword, 0.20),
            (meat, 0.25)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

        # See Centaur.__init__ above -- same territorial-not-hostile default.
        self.disposition = Disposition.PASSIVE

class Troll(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'TL', 'Troll', (0, 100, 0))
        self.hp = 84
        self.max_hp = 84
        self.attack_bonus = 4
        self.armor_class = 15
        self.base_xp = 1800
        self.monster_die_type = 6
        self.damage_modifier = 4
        self.detection_range = 8
        self.num_damage_dice = 2
        self.is_intelligent = False
        
        self.footprint_size = 2

        self.loot_table = [
            (steel_maul, 0.85),
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Lizardfolk(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'LF', 'Lizardfolk', (46, 139, 87))
        self.can_swim = True
        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 100
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        self.can_poison = True
        self.poison_dc = 13
        self.poison_duration = 3
        self.poison_damage_per_turn = 2
        self.is_intelligent = True

        self.loot_table = [
            (pole_arm, 0.75)
        ]        

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

        self.disposition = Disposition.PASSIVE

class LizardfolkArcher(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'LA', 'Lizardfolk Archer', (60, 179, 113))
        self.can_swim = True
        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 2
        self.armor_class = 15
        self.base_xp = 100
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 5
        self.num_damage_dice = 1
        self.is_ranged = True
        self.ranged_attack_bonus = 2
        self.range = 4
        self.ranged_die_type = 8
        self.ranged_num_dice = 1
        self.is_intelligent = True
        
        # Enable kiting for this ranged monster
        self.can_kite = True
        self.ideal_kiting_distance = self.range - 1
        self.kiting_attack_threshold = 2

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

        self.disposition = Disposition.PASSIVE
                

class GiantSpider(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GS', 'Giant Spider', (50, 50, 50))
        self.hp = 26
        self.max_hp = 26
        self.attack_bonus = 3
        self.armor_class = 14
        self.base_xp = 200
        self.monster_die_type = 8
        self.damage_modifier = 3
        self.detection_range = 15
        self.num_damage_dice = 1
        self.can_poison = True
        self.poison_dc = 11
        self.poison_duration = 3
        self.poison_damage_per_turn = 4
        self.web_restrain = True
        self.is_intelligent = False

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Beholder(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'BH', 'Beholder', (150, 0, 150))
        self.hp = 180
        self.max_hp = 180
        self.attack_bonus = 7
        self.armor_class = 18
        self.base_xp = 10000
        self.monster_die_type = 8
        self.damage_modifier = 7
        self.detection_range = 8
        self.num_damage_dice = 4
        self.is_ranged = True
        self.ranged_attack_bonus = 2
        self.range = 5
        self.ranged_die_type = 8
        self.ranged_num_dice = 4
        self.footprint_size = 2
        self.is_intelligent = True
        
        # Beholder can kite at very long range
        self.can_kite = True
        self.ideal_kiting_distance = 5
        self.kiting_attack_threshold = 3

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class LargeOoze(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'LO', 'Large Ooze', (34, 139, 34))
        self.can_swim = True
        self.hp = 85
        self.max_hp = 85
        self.attack_bonus = 4
        self.armor_class = 7
        self.base_xp = 1800
        self.monster_die_type = 8
        self.damage_modifier = 6
        self.detection_range = 4
        self.num_damage_dice = 2
        self.acid_burn_dc = 14
        self.acid_burn_duration = 4
        self.acid_burn_damage_per_turn = 4
        self.split_on_slash = True
        self.is_intelligent = False

        self.loot_table = [
            (bronze_short_sword, 0.30),
            (round_shield, 0.25)
        ]    

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }               

class RedDragon(Monster):  
    def __init__(self, x, y):
        super().__init__(x, y, 'RDR', 'Red Dragon', (255, 0, 0))
        self.can_swim = True
        self.hp = 256
        self.max_hp = 256
        self.attack_bonus = 4
        self.armor_class = 19
        self.base_xp = 18000
        self.monster_die_type = 10
        self.damage_modifier = 6
        self.detection_range = 8
        self.num_damage_dice = 2
        self.is_intelligent = True
        self.is_ranged = True
        self.ranged_attack_bonus = 5
        self.range = 4
        self.ranged_die_type = 6
        self.ranged_num_dice = 1
        self.footprint_size = 3
        self.can_burn = True
        self.burn_dc = 17
        self.burn_damage_per_turn = 6
        self.burn_duration = 4

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": True,
        } 

class Owlbear(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'OB', 'Owlbear', (139, 69, 19))
        self.hp = 59
        self.max_hp = 59
        self.attack_bonus = 5
        self.armor_class = 13
        self.base_xp = 700
        self.monster_die_type = 10
        self.damage_modifier = 5
        self.detection_range = 5
        self.num_damage_dice = 2
        self.is_intelligent = False

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Demogorgon(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'DG', 'Demogorgon', (72, 61, 139))
        self.hp = 496
        self.max_hp = 496
        self.attack_bonus = 12
        self.armor_class = 22
        self.base_xp = 155000
        self.monster_die_type = 12
        self.damage_modifier = 7
        self.detection_range = 15
        self.num_damage_dice = 3
        self.footprint_size = 3
        self.is_intelligent = True

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class AlphaGrick(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'AG', 'Alpha Grick', (169, 169, 169))
        self.hp = 153
        self.max_hp = 153
        self.attack_bonus = 7
        self.armor_class = 18
        self.base_xp = 2900
        self.monster_die_type = 8
        self.damage_modifier = 4
        self.detection_range = 10
        self.num_damage_dice = 2
        self.is_intelligent = False

        self.loot_table = [
            (meat, 0.25)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }


class Grick(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GK', 'Grick', (105, 105, 105))
        self.can_swim = True
        self.hp = 27
        self.max_hp = 27
        self.attack_bonus = 3
        self.armor_class = 14
        self.base_xp = 450
        self.monster_die_type = 6
        self.damage_modifier = 2
        self.detection_range = 8
        self.num_damage_dice = 2
        self.is_intelligent = False

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class GibberingMouther(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GM', 'Gibbering Mouther', (200, 100, 100))
        self.hp = 67
        self.max_hp = 67
        self.attack_bonus = 2
        self.armor_class = 9
        self.base_xp = 450
        self.monster_die_type = 6
        self.damage_modifier = 1
        self.detection_range = 4
        self.num_damage_dice = 2
        self.is_intelligent = False

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class MindFlayer(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MF', 'Mind Flayer', (75, 0, 130))
        self.hp = 71
        self.max_hp = 71
        self.attack_bonus = 7
        self.armor_class = 15
        self.base_xp = 2900
        self.monster_die_type = 10
        self.num_damage_dice = 2
        self.detection_range = 6
        self.damage_modifier = 4
        self.is_ranged = True
        self.ranged_attack_bonus = 7
        self.range = 4
        self.ranged_die_type = 10
        self.ranged_num_dice = 2
        self.is_intelligent = True
        
        # Mind Flayer uses kiting at medium range
        self.can_kite = True
        self.ideal_kiting_distance = 4
        self.kiting_attack_threshold = 2

        self.loot_table = [
            (chainmail_armor, 0.75)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Minotaur(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MN', 'Minotaur', (139, 0, 0))
        self.hp = 76
        self.max_hp = 76
        self.attack_bonus = 4
        self.armor_class = 14
        self.base_xp = 700
        self.monster_die_type = 12
        self.damage_modifier = 4 
        self.detection_range = 6
        self.num_damage_dice = 2
        self.is_intelligent = True

        self.loot_table = [
            (steel_battle_axe, 0.75),
            (meat, 0.25)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Wererat(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'WR', 'Wererat', (169, 169, 169))
        self.hp = 33
        self.max_hp = 33
        self.attack_bonus = 2
        self.armor_class = 12
        self.base_xp = 100
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 6
        self.num_damage_dice = 1
        self.is_intelligent = True

        self.loot_table = [
            (iron_dagger, 0.85),
            (meat, 0.25),
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Wolf(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'WF', 'Wolf', (112, 128, 144))
        self.can_swim = False
        self.hp = 11
        self.max_hp = 11
        self.attack_bonus = 2
        self.armor_class = 13
        self.base_xp = 50
        self.monster_die_type = 4
        self.damage_modifier = 2
        self.detection_range = 8
        self.num_damage_dice = 1
        self.is_intelligent = False
        
        self.loot_table = [
            (meat, 0.60)
        ]        

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Yochlol(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'YL', 'Yochlol', (112, 128, 144))
        self.hp = 136
        self.max_hp = 136
        self.attack_bonus = 3
        self.armor_class = 15
        self.base_xp = 5900
        self.monster_die_type = 8
        self.damage_modifier = 3
        self.detection_range = 12
        self.num_damage_dice = 1
        self.can_poison = True
        self.poison_dc = 10
        self.poison_duration = 3
        self.poison_damage_per_turn = 4
        self.is_intelligent = True

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class RedSlaad(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'RS', 'Red Slaad', (180, 30, 30))

        self.hp = 93
        self.max_hp = 93
        self.attack_bonus = 6
        self.armor_class = 14
        self.base_xp = 1800
        self.monster_die_type = 6
        self.num_damage_dice = 2
        self.damage_modifier = 4
        self.detection_range = 6
        self.is_intelligent = False
        
        self.saving_throw_proficiencies = {
            "STR": True,
            "DEX": False,
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class DeathSlaad(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'DS', 'Death Slaad', (80, 0, 120))

        self.hp = 170
        self.max_hp = 170
        self.attack_bonus = 8
        self.armor_class = 18
        self.base_xp = 5900
        self.monster_die_type = 8
        self.num_damage_dice = 2
        self.damage_modifier = 5
        self.detection_range = 8
        self.is_intelligent = True

        self.saving_throw_proficiencies = {
            "STR": True,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": True,
        }

class MyconidSprout(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MS', 'Myconid Sprout', (120, 200, 120))

        self.hp = 7
        self.max_hp = 7
        self.attack_bonus = 2
        self.armor_class = 10
        self.base_xp = 50
        self.monster_die_type = 4
        self.num_damage_dice = 1
        self.damage_modifier = 0
        self.detection_range = 4
        self.is_intelligent = False

        self.loot_table = [
            (mushroom, 0.99)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

        # A grove of myconid sprouts sways and watches, but doesn't attack
        # on sight -- see the Disposition docstring near the top of this
        # file and Monster.provoke(). Landing a hit on one (from the player
        # or anything else) permanently flips it, and the rest of its
        # encounter_group/pack, to AGGRESSIVE from then on.
        self.disposition = Disposition.PASSIVE


class MyconidAdult(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MA', 'Myconid Adult', (80, 150, 80))

        self.hp = 22
        self.max_hp = 22
        self.attack_bonus = 3
        self.armor_class = 12
        self.base_xp = 100
        self.monster_die_type = 6
        self.num_damage_dice = 1
        self.damage_modifier = 1
        self.detection_range = 5
        self.is_intelligent = True
      
        self.loot_table = [
            (mushroom, 0.99)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": True,
            "INT": False,
            "WIS": True,
            "CHA": False,
        }

        # See MyconidSprout.__init__ above -- same not-hostile-on-sight
        # default, so a grove mixing sprouts and adults is uniformly
        # peaceful until something provokes it.
        self.disposition = Disposition.PASSIVE

class Mezzoloth(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'MZ', 'Mezzoloth', (120, 60, 0))

        self.hp = 75
        self.max_hp = 75
        self.attack_bonus = 6
        self.armor_class = 18
        self.base_xp = 1800
        self.monster_die_type = 6
        self.num_damage_dice = 2
        self.damage_modifier = 3
        self.detection_range = 8
        self.is_intelligent = True

        self.saving_throw_proficiencies = {
            "STR": True,
            "DEX": False,
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }

class Gauth(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'GU', 'Gauth', (200, 150, 50))

        self.hp = 67
        self.max_hp = 67
        self.attack_bonus = 5
        self.armor_class = 15
        self.base_xp = 2300
        self.monster_die_type = 8
        self.num_damage_dice = 1
        self.damage_modifier = 2
        self.detection_range = 8
        self.is_intelligent = True
        self.range = 3
        self.is_ranged = True
        self.ranged_attack_bonus = 5
        self.ranged_die_type = 8
        self.ranged_num_dice = 1
        
        # Gauth uses medium-range kiting
        self.can_kite = True
        self.ideal_kiting_distance = 3
        self.kiting_attack_threshold = 1

        self.loot_table = [
            (meat, 0.1)
        ]        

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": True,
            "CHA": True,
        }


class Drider(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'DD', 'Drider', (112, 128, 144))
        self.can_swim = True
        self.hp = 123
        self.max_hp = 123
        self.attack_bonus = 3
        self.armor_class = 19
        self.base_xp = 2300
        self.monster_die_type = 6
        self.damage_modifier = 3
        self.detection_range = 12
        self.num_damage_dice = 3
        self.is_intelligent = True

        self.loot_table = [
            (steel_rapier, 0.80)
        ]

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }        

class Arasta(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'AR', 'Arasta', (40, 0, 40))

        self.hp = 300
        self.max_hp = 300
        self.attack_bonus = 10
        self.armor_class = 19
        self.base_xp = 33000
        self.monster_die_type = 12
        self.num_damage_dice = 2
        self.damage_modifier = 6
        self.detection_range = 10
        self.is_intelligent = True
        self.footprint_size = 3
        self.can_swim = True

        self.can_poison = True
        self.poison_dc = 18
        self.poison_duration = 4
        self.poison_damage_per_turn = 8

        self.saving_throw_proficiencies = {
            "STR": True,
            "DEX": True,
            "CON": True,
            "INT": False,
            "WIS": True,
            "CHA": False,
        }

class IntellectDevourer(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'ID', 'Intellect Devourer', (255, 0, 255))

        self.hp = 21
        self.max_hp = 21
        self.attack_bonus = 4
        self.armor_class = 12
        self.base_xp = 450
        self.monster_die_type = 4
        self.num_damage_dice = 2
        self.damage_modifier = 2
        self.detection_range = 4
        self.is_intelligent = True

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": True,
            "WIS": False,
            "CHA": False,
        }

class Imp(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'IM', 'Imp', (255, 0, 255))

        self.hp = 10
        self.max_hp = 10
        self.attack_bonus = 2
        self.armor_class = 13
        self.base_xp = 50
        self.monster_die_type = 4
        self.num_damage_dice = 1
        self.damage_modifier = 1
        self.detection_range = 6
        self.is_intelligent = True

        self.can_poison = True
        self.poison_dc = 11
        self.poison_duration = 4  
        self.poison_damage_per_turn = 6

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": True,
            "WIS": False,
            "CHA": False,
        }


class Wraith(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'WRT', 'Wraith', (0, 0, 0))

        self.hp = 67
        self.max_hp = 67
        self.attack_bonus = 5
        self.armor_class = 13
        self.base_xp = 1800
        self.monster_die_type = 8
        self.num_damage_dice = 1
        self.damage_modifier = 2
        self.detection_range = 8
        self.is_intelligent = False
        self.can_fly = True

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }


class TombTapper(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'TTP', 'Tomb Tapper', (128, 0, 128))

        self.hp = 180
        self.max_hp = 180
        self.attack_bonus = 3
        self.armor_class = 12
        self.base_xp = 700
        self.monster_die_type = 6
        self.num_damage_dice = 2
        self.damage_modifier = 2
        self.detection_range = 6
        self.is_intelligent = True

        self.loot_table = [
            (meat, 0.25)
        ]

        self.saving_throw_proficiencies = {
            "STR": True,
            "DEX": False,
            "CON": True,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }


class Cultist(Monster):
    def __init__(self, x, y):
        super().__init__(x, y, 'CUL', 'Cultist', (128, 0, 128))

        self.hp = 9
        self.max_hp = 9
        self.attack_bonus = 2
        self.armor_class = 12
        self.base_xp = 50
        self.monster_die_type = 4
        self.num_damage_dice = 1
        self.damage_modifier = 1
        self.detection_range = 4
        self.is_intelligent = True

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": False,
            "CON": False,
            "INT": True,
            "WIS": False,
            "CHA": False,
        }