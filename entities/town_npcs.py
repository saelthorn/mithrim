import math
import random

import config
from core.pathfinding import astar
from world.water_features import is_water_tile
from core.floating_text import FloatingText



from core.game import GameState
from entities.base_entity import NPC
from core.game import GameState
from items.items import (
    torch, throwing_knife, lesser_healing_potion, greater_healing_potion, meat, green_apple, fromage, bread, mushroom, 
    carrot, spell_book, holy_symbol, full_plate_armor, robes_of_protection, adamantine_long_sword, staff_of_magi, 
    duelists_rapier, dwarven_battle_axe, dragonsbane_warhammer, flameheart_flail, flameheart_short_sword, scale_mail_armor, 
    sturdy_quarterstaff, leather_cap, iron_helmet, steel_helmet, hood_of_shadows, great_helm, mages_circlet, leather_boots, 
    iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers, silver_dagger, round_shield, iron_short_sword,
    CampfireKit, Food, Weapon, Helmet, Armor, Boots, OffHand, FocusItem, format_price
)



#: Cap on astar()'s per-call node-expansion budget when a TownNPC needs
#: to route around an obstacle to reach home/post. Deliberately NOT
#: copied from summons.py's SUMMON_PATHFINDING_MAX_EXPANSIONS (400) --
#: that value is sized for combat-radius pathing (short hops, called
#: every frame for potentially many summons at once, so it has to stay
#: cheap). A TownNPC's wander_bounds spans the *whole* town footprint
#: (padded by only a few tiles -- see bounding_box_for_footprints()), so
#: an NPC that wandered to the far side of a sprawling town can easily
#: be 40-80+ tiles from home once walls and buildings are accounted
#: for -- well beyond what 400 expansions reliably covers. astar()
#: silently returns None when it runs out of budget rather than raising
#: (see pathfinding.py's max_expansions comment), so a cap that's too
#: tight here doesn't error, it just leaves the NPC stuck retrying the
#: same failed search forever -- exactly the "some NPCs never make it
#: home" symptom. There are only ever a handful of town NPCs actually
#: TRAVELING at once (not one per frame like summons in combat), so
#: there's no real cost to matching astar()'s own default headroom.
TOWN_NPC_PATHFINDING_MAX_EXPANSIONS = 400


class NPCBehavior:
    """
    Behavior states for TownNPC.take_turn()'s daily schedule. Plain
    string constants rather than an Enum -- they're only ever compared
    and stored on the instance, matching the lightweight style
    structures.py already uses elsewhere (tile chars, structure keys).
    """
    SLEEPING = "sleeping"       # idle at home
    AT_POST = "at_post"         # idle at their workplace tile (bar, shop counter, altar, forge)
    WANDERING = "wandering"     # puttering around town, one step every WANDER_INTERVAL turns
    TRAVELING = "traveling"     # walking toward a specific target tile (home, post, or a chat partner)
    SOCIALIZING = "socializing" # paused with another NPC for a short conversation -- see TownNPC's socializing section


def _behavior_for_hour(schedule, hour):
    """
    Look up which NPCBehavior a schedule says covers `hour` (0-23).
    Entries are (start_hour, end_hour, behavior); a range where
    start > end wraps past midnight (e.g. (22, 6, SLEEPING) covers
    22:00 through 05:59). Falls back to WANDERING if no entry matches,
    so a malformed/incomplete schedule never leaves an NPC stuck.
    """
    for start, end, behavior in schedule:
        if start <= end:
            if start <= hour < end:
                return behavior
        elif hour >= start or hour < end:
            return behavior
    return NPCBehavior.WANDERING


#: Default schedule for NPCs with no fixed workplace (Townsfolk) --
#: wander town by day, sleep at night.
DEFAULT_SCHEDULE = [
    (22, 6, NPCBehavior.SLEEPING),
    (6, 7, NPCBehavior.AT_POST),
    (7, 12, NPCBehavior.WANDERING),
    (12, 13, NPCBehavior.AT_POST),  # lunch break
    (13, 22, NPCBehavior.WANDERING),
]

#: Schedule for NPCs who mind a post (Innkeeper, Shopkeeper, Blacksmith,
#: Priest) -- stay put during open hours instead of wandering off.
AT_POST_SCHEDULE = [
    (22, 6, NPCBehavior.SLEEPING),
    (10, 20, NPCBehavior.AT_POST),
]


class ChatBubbleText(FloatingText):
    """
    A FloatingText that sways side to side as it drifts upward, instead
    of rising in a dead-straight line -- used for TownNPC's "..."
    conversation indicator (see _spawn_chat_bubble()) so it reads as
    idle chatter rather than a damage number or a "MISS!" callout.

    Only `draw()` differs from FloatingText: fade timing, upward drift,
    and font caching are all inherited unchanged. The sway itself is a
    simple sine wave driven by how far through its lifetime the bubble
    currently is, so it always completes a whole number of swings and
    never "jumps" partway through one if `duration` is changed later.
    """

    #: How far the bubble sways from its tile's center, in tiles.
    WAVE_AMPLITUDE = 0.18
    #: How many full left-right swings it completes over its lifetime.
    WAVE_CYCLES = 1.5

    def __init__(self, x, y, text, color, duration=60, y_speed=-0.5, font_size=None):
        super().__init__(x, y, text, color, duration=duration, y_speed=y_speed, font_size=font_size)
        # frames_left counts down toward 0 across the bubble's life, but
        # duration itself doesn't change after __init__ -- capturing it
        # here (rather than re-reading self.duration, which *does* count
        # down alongside frames_left) gives draw() a fixed denominator to
        # compute "how far through its life" against.
        self._wave_total_frames = max(duration, 1)

    def draw(self, screen_surface, camera):
        """
        Identical to FloatingText.draw(), except the world x position is
        offset by a sine wave before the camera converts it to screen
        space -- everything downstream (centering, pixel snapping) stays
        the same math FloatingText already uses.
        """
        elapsed_frames = self._wave_total_frames - self.frames_left
        progress = elapsed_frames / self._wave_total_frames
        wave_offset = math.sin(progress * self.WAVE_CYCLES * 2 * math.pi) * self.WAVE_AMPLITUDE

        screen_x_tile, screen_y_tile = camera.world_to_screen(self.x + wave_offset, self.y)

        screen_x_pixel = screen_x_tile * config.TILE_SIZE
        screen_y_pixel = screen_y_tile * config.TILE_SIZE

        draw_x = screen_x_pixel + (config.TILE_SIZE - self.rect.width) // 2
        draw_y = screen_y_pixel - self.rect.height
        screen_surface.blit(self.surface, (draw_x, draw_y))


class TownNPC(NPC):
    """
    Base class for the population of overworld towns and buildings.

    Every TownNPC knows three places: `post` (where their blueprint
    spawned them -- bar counter, shop counter, altar, forge), `home`
    (also their spawn tile by default -- the anchor SLEEPING returns
    them to), and `wander_bounds` (the town's rough footprint, so
    wandering never drifts off toward the horizon). `wander_bounds`
    starts unrestricted and is filled in afterward by
    assign_npc_schedule_anchors() once the surrounding structure(s) are
    known -- see create_town_npcs() and game.py's
    _spawn_player_in_starting_tavern(). This keeps every existing NPC
    factory's `(x, y) -> NPC` signature untouched. Doors are never a
    destination in their own right -- astar() just routes through them
    naturally on the way to home/post (see _pathfind_toward()).

    `schedule` maps hour_of_day to an NPCBehavior; take_turn() reads
    the world clock each turn and moves one step at a time toward
    wherever that behavior currently wants them.

    While WANDERING, an NPC may also notice another WANDERING NPC nearby
    and wander over for a chat -- see the "-- socializing --" section
    below for the full WANDERING -> TRAVELING -> SOCIALIZING -> WANDERING
    flow. This never interrupts AT_POST/SLEEPING and never survives past
    bedtime.
    """

    #: Hour ranges -> NPCBehavior. Subclasses with a fixed workplace
    #: override this with AT_POST_SCHEDULE.
    schedule = DEFAULT_SCHEDULE

    #: Turns to idle between wander steps -- a step every single turn
    #: reads as twitchy for someone just puttering around town.
    WANDER_INTERVAL = 4

    #: Per-wander-step odds that an idle, WANDERING NPC notices someone
    #: to talk to and sets off toward them (see _try_start_socializing()).
    SOCIALIZE_CHANCE = 0.15
    #: How far away (Chebyshev tiles) a WANDERING NPC can notice another
    #: WANDERING NPC worth approaching.
    SOCIALIZE_RADIUS = 6
    #: (min, max) turns a conversation lasts once both NPCs are together --
    #: see _start_conversation().
    SOCIALIZE_DURATION = (6, 14)
    #: (min, max) turns an NPC waits after a conversation ends before it
    #: will consider starting (or being invited into) another one, so the
    #: same pair doesn't immediately re-chat the moment they part ways.
    SOCIALIZE_COOLDOWN = (25, 50)
    #: Give up on an unreachable/blocked chat partner after this many
    #: turns of travel rather than chasing them forever -- see
    #: _advance_social_travel().
    SOCIALIZE_TRAVEL_TIMEOUT = 40
    #: Purely cosmetic: how often (in turns) an ongoing conversation
    #: re-spawns its "..." floating text so a long chat doesn't go
    #: visually silent after the opening bubble fades -- see
    #: _spawn_chat_bubble()/_advance_socializing().
    CHAT_BUBBLE_INTERVAL = 5
    CHAT_BUBBLE_TEXT = "..."
    CHAT_BUBBLE_COLOR = (190, 190, 230)

    def __init__(self, x, y, char, name, color, dialogue=None):
        super().__init__(x, y, char, name, color, dialogue)
        self.post = (x, y)
        self.home = (x, y)
        self.wander_bounds = None  # (min_x, min_y, max_x, max_y), or None = unrestricted
        self.behavior_state = NPCBehavior.AT_POST
        self._travel_target = None
        self._wander_cooldown = 0
        # Cached astar() route currently being followed toward home/post
        # (see _advance_along_path()) plus the target it was computed
        # for, so a schedule change or a nudge off the route is detected
        # and replanned rather than silently followed anyway.
        self._travel_path = None
        self._travel_path_target = None
        # Same list, purely for the F9 debug overlay (see game.py's
        # render_tile_highlights()) -- not read by any movement logic
        # itself. Kept as its own attribute (rather than reading
        # _travel_path directly at render time) so it can be explicitly
        # cleared on turns with nothing to show (sleeping, wandering).
        self._debug_path = None

        # -- socializing (see the "-- socializing --" section below) --
        # What TRAVELING is currently *for*: None (the ordinary home/post
        # trip _reconcile_behavior() sets up) or "social" (walking toward
        # a chat partner instead -- see _begin_social_travel()). Read by
        # take_turn() to decide which advance method drives a TRAVELING
        # step, since the two need different arrival logic.
        self._travel_purpose = None
        # The other TownNPC we're currently approaching or talking with,
        # or None if we're not involved in a conversation right now.
        self._social_partner = None
        # "initiator" (the one who noticed the partner and set off) or
        # "partner" (the one who got approached). Only the initiator
        # drives the shared countdown in _advance_socializing() -- see
        # its docstring for why.
        self._social_role = None
        # Turns left in the current conversation. Stays 0 for a "partner"
        # who has been reserved but not yet joined by their initiator --
        # see _accept_social_invite().
        self._social_turns_remaining = 0
        # Turns spent TRAVELING toward a partner so far, for
        # SOCIALIZE_TRAVEL_TIMEOUT below.
        self._social_travel_turns = 0
        # Turns left before this NPC will start or accept another
        # conversation -- ticked down once per take_turn() regardless of
        # behavior_state, same as _wander_cooldown.
        self._social_cooldown = 0

    # -- schedule ------------------------------------------------------

    def take_turn(self, player, game_map, game):
        """
        Called once per turn cycle (see game.py's turn_order batch
        processing, which already calls take_turn() on every entity
        that has one -- no game.py changes needed for TownNPCs to
        participate). Reads the world clock, reconciles the current
        behavior_state toward whatever the schedule wants right now,
        and takes at most one step in that direction.
        """
        hour = self._current_hour(game)
        if hour is None:
            return  # world clock not available yet (e.g. character creation)

        desired = _behavior_for_hour(self.schedule, hour)

        if self._social_cooldown > 0:
            self._social_cooldown -= 1

        # A conversation (or the walk toward one) never gets to override
        # bedtime -- if the schedule now wants us SLEEPING, drop whatever
        # social plans we had immediately rather than making the partner
        # (or the sweep for a partner) wait for a natural end.
        if desired == NPCBehavior.SLEEPING and self._social_partner is not None:
            self._cancel_social()

        if self.behavior_state == NPCBehavior.SOCIALIZING:
            self._advance_socializing(game)
            return

        self._reconcile_behavior(desired)

        if self.behavior_state == NPCBehavior.TRAVELING:
            if self._travel_purpose == "social":
                self._advance_social_travel(game_map, game)
            else:
                self._advance_along_path(game_map, game, self._travel_target)
                if (self.x, self.y) == self._travel_target:
                    self.behavior_state = desired
        elif self.behavior_state == NPCBehavior.WANDERING:
            self._travel_path = None
            self._debug_path = None
            if not self._try_start_socializing(game_map, game):
                self._wander(game_map, game)
        elif self.behavior_state == NPCBehavior.AT_POST:
            self._advance_along_path(game_map, game, self.post)
        else:
            # SLEEPING: idle at home, nothing to do.
            self._travel_path = None
            self._debug_path = None

    def _current_hour(self, game):
        stories = getattr(game, "stories", None)
        world_time = getattr(stories, "world_time", None) if stories else None
        return world_time.clock.hour_of_day if world_time else None

    def _reconcile_behavior(self, desired):
        """
        Move behavior_state toward `desired`, routing through TRAVELING
        whenever the destination needs the NPC somewhere they aren't
        already standing -- so a schedule change never teleports an
        NPC across town, it just starts them walking there.
        """
        if self.behavior_state == NPCBehavior.TRAVELING:
            return  # already en route; take_turn() checks arrival itself

        if desired == self.behavior_state:
            return

        if desired == NPCBehavior.WANDERING:
            self.behavior_state = NPCBehavior.WANDERING
            return

        target = self.home if desired == NPCBehavior.SLEEPING else self.post
        if (self.x, self.y) == target:
            self.behavior_state = desired
        else:
            self.behavior_state = NPCBehavior.TRAVELING
            self._travel_target = target

    # -- socializing -------------------------------------------------------
    #
    #   WANDERING -> notice nearby NPC -> decide to socialize
    #       -> TRAVELING (purpose="social") -> target NPC
    #       -> SOCIALIZING -> conversation ends
    #       -> WANDERING / TRAVELING / AT_POST (whatever the schedule wants next)
    #
    # Only WANDERING NPCs ever start or accept a conversation -- someone
    # AT_POST is working and someone SLEEPING is, well, asleep. The
    # initiator drives the whole thing (finds a partner, walks to them,
    # starts and ends the shared countdown); the partner is a passive
    # participant that simply stops wandering and waits once invited, then
    # goes back to normal schedule reconciliation the instant the
    # initiator ends the conversation. This keeps the two NPCs' clocks
    # from ever drifting apart by a turn without needing any shared state
    # beyond the direct object references they already hold in
    # `_social_partner`.

    def _try_start_socializing(self, game_map, game):
        """
        Called on a WANDERING NPC's turn, before it takes its usual
        wander step. Occasionally notices a nearby, equally free NPC and
        sets off toward them instead. Returns True if a conversation was
        just kicked off (behavior_state is now TRAVELING), so take_turn()
        knows to skip this turn's wander step.
        """
        if self._social_cooldown > 0:
            return False
        if random.random() > self.SOCIALIZE_CHANCE:
            return False

        partner = self._find_social_partner(game)
        if partner is None:
            return False

        self._begin_social_travel(partner)
        partner._accept_social_invite(self)
        return True

    def _find_social_partner(self, game):
        """
        Nearest other TownNPC currently WANDERING and not already tied up
        in a conversation of their own, within SOCIALIZE_RADIUS tiles.
        Returns None if nobody nearby qualifies.
        """
        best, best_distance = None, self.SOCIALIZE_RADIUS + 1
        for entity in getattr(game, "entities", ()):
            if entity is self or not isinstance(entity, TownNPC):
                continue
            if (
                not entity.alive
                or entity.behavior_state != NPCBehavior.WANDERING
                or entity._social_partner is not None
                or entity._social_cooldown > 0
            ):
                continue
            distance = self._chebyshev_distance(entity)
            if distance <= self.SOCIALIZE_RADIUS and distance < best_distance:
                best, best_distance = entity, distance
        return best

    def _chebyshev_distance(self, other):
        return max(abs(other.x - self.x), abs(other.y - self.y))

    def _begin_social_travel(self, partner):
        """Commit to approaching `partner` for a chat. Mirrors
        _reconcile_behavior()'s TRAVELING setup, but targets a moving
        NPC instead of a fixed home/post tile -- see _travel_purpose."""
        self._social_partner = partner
        self._social_role = "initiator"
        self._social_travel_turns = 0
        self.behavior_state = NPCBehavior.TRAVELING
        self._travel_purpose = "social"
        self._travel_path = None
        self._debug_path = None

    def _accept_social_invite(self, initiator):
        """
        Called directly by the initiator (not from our own take_turn())
        the moment they set off toward us, so we stop wandering away
        from underneath them immediately rather than one turn late.
        `_social_turns_remaining` stays 0 -- the actual conversation
        clock only starts once the initiator physically arrives, in
        _start_conversation().
        """
        self._social_partner = initiator
        self._social_role = "partner"
        self.behavior_state = NPCBehavior.SOCIALIZING
        self._social_turns_remaining = 0
        self._travel_path = None
        self._debug_path = None

    def _advance_social_travel(self, game_map, game):
        """
        TRAVELING with _travel_purpose == "social": walk toward wherever
        our partner currently stands. Unlike home/post, the target isn't
        fixed -- _advance_along_path() naturally replans if they haven't
        settled at the spot we last aimed for -- so this checks adjacency
        itself every turn instead of waiting to land exactly on their tile
        (which _advance_along_path() would never let us do anyway, since
        their tile is occupied).
        """
        partner = self._social_partner
        if partner is None or not partner.alive or partner._social_partner is not self:
            self._cancel_social()
            return

        self._social_travel_turns += 1
        if self._social_travel_turns > self.SOCIALIZE_TRAVEL_TIMEOUT:
            self._cancel_social()
            return

        if self._chebyshev_distance(partner) <= 1:
            self._start_conversation(partner, game)
            return

        self._advance_along_path(game_map, game, (partner.x, partner.y))

    def _start_conversation(self, partner, game):
        """We've arrived next to our partner -- both of us settle into
        SOCIALIZING for the same randomly-rolled duration."""
        low, high = self.SOCIALIZE_DURATION
        duration = random.randint(low, high)

        self.behavior_state = NPCBehavior.SOCIALIZING
        self._travel_purpose = None
        self._travel_path = None
        self._debug_path = None
        self._social_turns_remaining = duration

        partner.behavior_state = NPCBehavior.SOCIALIZING
        partner._social_turns_remaining = duration

        self._spawn_chat_bubble(game, partner)

    def _advance_socializing(self, game):
        """
        One turn of an ongoing conversation. Only the initiator counts
        down and ends it -- if the partner also decremented its own
        copy independently, the two could end up one turn apart (e.g.
        if either of them got skipped a turn for being too far from the
        player -- see game.py's 10-tile turn-processing radius check)
        and try to clear each other's already-cleared state. The partner
        just waits for the initiator to call `_end_social()` on it directly.
        """
        if self._social_role != "initiator":
            return

        self._social_turns_remaining -= 1
        if self._social_turns_remaining <= 0:
            partner = self._social_partner
            self._end_social()
            if partner is not None:
                partner._end_social()
            return

        # Still talking -- keep the "..." bubble showing up every so
        # often so a long conversation doesn't go visually silent once
        # the opening bubble fades. Purely cosmetic (see
        # _spawn_chat_bubble()); the countdown above already ended the
        # conversation on schedule regardless of this.
        if self._social_turns_remaining % self.CHAT_BUBBLE_INTERVAL == 0:
            self._spawn_chat_bubble(game, self._social_partner)

    def _spawn_chat_bubble(self, game, partner):
        """
        Drop a small ambient, waving "..." over both participants so
        the player can tell at a glance that two NPCs are mid-
        conversation rather than just standing around. Purely cosmetic --
        never touches behavior_state or any other gameplay-relevant
        field, and silently does nothing if `game` has no floating_texts
        list (e.g. very early during setup) or `partner` is already gone.
        """
        floating_texts = getattr(game, "floating_texts", None)
        if floating_texts is None:
            return
        for participant in (self, partner):
            if participant is None:
                continue
            floating_texts.append(
                ChatBubbleText(
                    participant.x, participant.y - 0.5,
                    self.CHAT_BUBBLE_TEXT, self.CHAT_BUBBLE_COLOR,
                )
            )

    def _end_social(self):
        """
        A conversation ran its full course. Land back on WANDERING and
        start our post-chat cooldown; the very next take_turn() reads
        the world clock fresh and reconciles normally from there, exactly
        like any other schedule transition -- so a partner who's now due
        AT_POST or SLEEPING sorts itself out on its own next turn without
        this method needing to know anything about schedules.
        """
        self._social_partner = None
        self._social_role = None
        self._social_turns_remaining = 0
        self._social_travel_turns = 0
        self._social_cooldown = random.randint(*self.SOCIALIZE_COOLDOWN)
        self._travel_purpose = None
        self.behavior_state = NPCBehavior.WANDERING
        self._travel_path = None
        self._debug_path = None

    def _cancel_social(self):
        """
        Abandon an in-progress invite/approach -- our partner died, wandered
        out of reach, got claimed by someone else, or our own schedule
        needs us elsewhere (see the SLEEPING check in take_turn()). Unlike
        _end_social(), this skips SOCIALIZE_COOLDOWN: we never actually
        talked, so there's no reason to make either of us wait before
        trying again. Also unwinds the other side of the invite, if they
        still think they're paired with us.
        """
        partner = self._social_partner
        self._social_partner = None
        self._social_role = None
        self._social_turns_remaining = 0
        self._social_travel_turns = 0
        self._travel_purpose = None
        self.behavior_state = NPCBehavior.WANDERING
        self._travel_path = None
        self._debug_path = None

        if partner is not None and partner._social_partner is self:
            partner._cancel_social()

    # -- movement --------------------------------------------------------

    def _wander(self, game_map, game):
        if self._wander_cooldown > 0:
            self._wander_cooldown -= 1
            return
        self._wander_cooldown = self.WANDER_INTERVAL

        candidates = self._adjacent_walkable(game_map, game)
        if self.wander_bounds is not None:
            min_x, min_y, max_x, max_y = self.wander_bounds
            candidates = [
                (x, y) for x, y in candidates
                if min_x <= x <= max_x and min_y <= y <= max_y
            ]
        if candidates:
            self.x, self.y = random.choice(candidates)

    def _step_toward(self, game_map, game, tx, ty):
        """
        Cheap, search-free steering step: move one tile toward (tx, ty),
        diagonal-first, falling back to a single axis if the diagonal is
        blocked -- same Chebyshev-adjacency convention as summons.py's
        EscortCompanion._step_toward(). Returns True if it moved (or was
        already there), False if every candidate tile was blocked.

        Not used by TRAVELING/AT_POST movement (see
        _advance_along_path()'s docstring for why -- this heuristic and
        a real astar() route can disagree about which direction is
        actually correct near a corridor bend, and since this succeeds
        by its own limited judgment far more often than it fails, the
        astar() fallback almost never got a chance to correct course,
        which is what made NPCs visibly oscillate between two tiles).
        Kept only as a building block other callers may still want for
        a single unplanned nudge.
        """
        if (self.x, self.y) == (tx, ty):
            return True
        dx = (tx > self.x) - (tx < self.x)
        dy = (ty > self.y) - (ty < self.y)
        for step_x, step_y in ((dx, dy), (dx, 0), (0, dy)):
            if step_x == 0 and step_y == 0:
                continue
            nx, ny = self.x + step_x, self.y + step_y
            if self._can_occupy(game_map, game, nx, ny):
                self.x, self.y = nx, ny
                return True
        return False

    def _advance_along_path(self, game_map, game, target):
        """
        Move one step toward `target` by following a cached astar()
        route to completion, rather than re-deciding fresh every turn
        from a mix of a cheap greedy guess and an occasional real
        search. That "greedy first, search only as a fallback" design
        is what caused NPCs to visibly walk back and forth: the greedy
        step's sign(dx)/sign(dy) heuristic and astar()'s actual
        shortest path can disagree about which direction is correct
        near an L-shaped corridor or an offset doorway, and because the
        greedy step almost always finds *some* legal tile to move to,
        astar() rarely got consulted to correct course -- so the F9
        overlay could show a perfectly good route that the NPC was
        never actually following.

        Committing to one real path and only replanning when it's
        actually invalid (target changed, exhausted, or we're no longer
        where it expects) removes that disagreement: the NPC now always
        walks the exact route the debug overlay shows.
        """
        if (self.x, self.y) == target:
            self._travel_path = None
            self._debug_path = None
            return

        # Recompute only when the cached path isn't usable as-is: none
        # yet, aimed at a different target (a schedule change mid-route),
        # or our position no longer matches where the path expects us
        # (nudged aside, or this is the very first step).
        if (
            not self._travel_path
            or self._travel_path_target != target
            or self._travel_path[0] != (self.x, self.y)
        ):
            self._travel_path = astar(
                game_map, (self.x, self.y), target,
                max_expansions=TOWN_NPC_PATHFINDING_MAX_EXPANSIONS,
            )
            self._travel_path_target = target
            self._debug_path = self._travel_path

        if not self._travel_path or len(self._travel_path) < 2:
            self._travel_path = None
            return  # No route right now (e.g. the door is blocked by someone else)

        next_x, next_y = self._travel_path[1]
        if self._is_free_of_entities(game, next_x, next_y):
            self.x, self.y = next_x, next_y
            self._travel_path = self._travel_path[1:]
            self._debug_path = self._travel_path
        # Otherwise another entity is standing on the next tile right
        # now -- wait rather than discarding a perfectly good path. If
        # they're still there next turn we keep waiting (cheap); if our
        # position ever stops matching path[0] the staleness check
        # above replans automatically.

    def _can_occupy(self, game_map, game, x, y):
        """
        Full "can I step here right now" check for _wander()'s blind,
        unvalidated adjacent-tile scan: terrain-walkable, not a wall-
        corner clip, and not occupied by another blocking entity.
        _advance_along_path() deliberately does NOT route through this
        -- a step that already came out of a real astar() search needs
        a different (and, for a step astar() itself proposed, more
        trustworthy) admissibility check than a blind guess does; see
        that method's docstring and _is_free_of_entities() below.
        """
        if not self._tile_walkable(game_map, x, y):
            return False

        # Forbid slipping diagonally through a solid wall corner: a
        # diagonal move is only legal if at least one of the two tiles
        # it would "cut past" is itself open. This guards _wander()'s
        # blind adjacent-tile guess, which has no path-search behind it
        # and so has no other way to know it's about to clip a corner.
        dx, dy = x - self.x, y - self.y
        if dx != 0 and dy != 0:
            flank_a = self._tile_walkable(game_map, x, self.y)
            flank_b = self._tile_walkable(game_map, self.x, y)
            if not (flank_a or flank_b):
                return False

        return self._is_free_of_entities(game, x, y)

    def _is_free_of_entities(self, game, x, y):
        """Whether (x, y) is unoccupied by another blocking entity."""
        for entity in getattr(game, "entities", ()):
            if (
                entity is not self
                and getattr(entity, "alive", True)
                and getattr(entity, "blocks_movement", False)
                and getattr(entity, "x", None) == x
                and getattr(entity, "y", None) == y
            ):
                return False
        return True

    def _tile_walkable(self, game_map, x, y):
        """
        Terrain-only walkability check (no entity occupancy). Used both
        by _can_occupy()'s corner-cutting guard (the two flanking tiles
        of a diagonal move) and directly by _wander()'s adjacent scan.

        Also rejects water tiles (rivers, lakes, ponds) outright:
        TownNPCs have no can_swim flag (see base_entity.py's NPC),
        matching the same default astar() itself already applies for
        _advance_along_path()'s route searches -- pathfinding.py's
        can_swim defaults to False whenever no moving_entity is passed,
        which TownNPC's astar() calls never do, so a TRAVELING NPC is
        already routed around water automatically. is_walkable() alone
        doesn't know the difference between open ground and open water
        (both are blocked=False), so without this check here too,
        _wander() could still send a wandering NPC straight into a
        river that TRAVELING would never cross.
        """
        if x < 0 or y < 0 or x >= game_map.width or y >= game_map.height:
            return False
        if hasattr(game_map, "is_walkable"):
            if not game_map.is_walkable(x, y):
                return False
        elif getattr(game_map.tiles[y][x], "blocked", True):
            return False
        return not is_water_tile(game_map.tiles[y][x])

    def _adjacent_walkable(self, game_map, game):
        offsets = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
        return [
            (self.x + dx, self.y + dy) for dx, dy in offsets
            if self._can_occupy(game_map, game, self.x + dx, self.y + dy)
        ]


def _clone_item(item):
    """
    Return a fresh instance of `item`, matching the clone pattern
    merchants already use when handing out one of their own template
    items, so the player never ends up aliasing the template object
    itself. Shared by Shopkeeper's stocking/bulk-buy and Innkeeper's
    food menu below.
    """
    if isinstance(item, CampfireKit):
        return CampfireKit()
    return item.__class__(
        name=item.name,
        char=item.char,
        color=item.color,
        description=item.description,
        **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
    )


def _buy_from_stock(seller, player, item_name):
    """
    Shared "buy an item (or every food item at once) from a merchant's
    items_for_sale list" logic, used by both Shopkeeper.buy_item() and
    Innkeeper.buy_item() so the purchase rules (afford-check, inventory-
    full refund, bulk "all food" buy) only live in one place. `seller`
    only needs an `items_for_sale` list -- it doesn't need to be a
    Shopkeeper itself, which is what lets Innkeeper reuse this too.
    """
    if item_name == "all food":
        food_items = [item for item in seller.items_for_sale if isinstance(item, Food)]
        if not food_items:
            return "No food items are available for sale."

        purchased_items = []
        total_cost = 0
        for item in list(food_items):
            if player.money < item.price:
                continue

            new_item = _clone_item(item)
            if player.inventory.add_item(new_item):
                player.money -= item.price
                total_cost += item.price
                purchased_items.append(item.name)
                seller.items_for_sale.remove(item)
            else:
                break

        if not purchased_items:
            return "You couldn't buy any food. Check your gold or inventory space."
        item_list = ", ".join(purchased_items)
        player.update_throw_knife_ability()
        player.update_spellbook_abilities()
        player.update_guard_ability()
        return f"You bought {len(purchased_items)} food items for {format_price(total_cost)}: {item_list}."

    for item in seller.items_for_sale:
        if item.name.lower() == item_name.lower():
            if player.money >= item.price:
                player.money -= item.price

                # Give the actual item instance to the player
                if player.inventory.add_item(item):
                    seller.items_for_sale.remove(item)  # Remove the item from the seller
                    player.update_throw_knife_ability()
                    player.update_spellbook_abilities()
                    player.update_guard_ability()
                    return f"You bought {item.name}!"
                else:
                    # If adding failed, refund the player
                    player.money += item.price
                    return "Your inventory is full!"
            else:
                return "Scram! you don't have enough gold!"
    return "We don't sell that kind of item here!"


class Townsfolk(TownNPC):
    def __init__(self, x, y, name=None):
        dialogue = [
            "Roads have been busier since the old entrances opened again.",
            "Mind the wilds after dusk. The grass gets quiet before trouble.",
            "If you are heading below, make sure you have food and light.",
            "Every town around here has a story about someone who went missing.",
        ]
        super().__init__(x, y, 'p', name or random.choice(TOWNSFOLK_NAMES), (205, 205, 185), dialogue)


class Blacksmith(TownNPC):
    #: Minds the forge during open hours instead of wandering.
    schedule = AT_POST_SCHEDULE

    def __init__(self, x, y, name=None):
        dialogue = [
            "I am still unpacking the shelves, but I know a good buyer when I see one.",
            "Bring back anything odd from the ruins. Odd things sell.",
            "A careful blade and a dry torch are worth more than bravado.",            
        ]
        super().__init__(x, y, 'p', name or random.choice(TOWNSFOLK_NAMES), (205, 205, 185), dialogue)


class Priest(TownNPC):
    #: Tends the altar during open hours instead of wandering.
    schedule = AT_POST_SCHEDULE

    def __init__(self, x, y, name=None):
        dialogue = [
            "Roads have been busier since the old entrances opened again.",
            "Mind the wilds after dusk. The grass gets quiet before trouble.",
            "If you are heading below, make sure you have food and light.",
            "Every town around here has a story about someone who went missing.",
        ]
        super().__init__(x, y, 'p', name or random.choice(TOWNSFOLK_NAMES), (205, 205, 185), dialogue)



class Innkeeper(TownNPC):
    #: Gold charged for a night's stay -- see rest_player().
    rest_cost = 5
    #: Hours the world clock advances per rest -- see rest_player().
    rest_hours = 8
    #: Minds the bar during open hours instead of wandering.
    schedule = AT_POST_SCHEDULE

    def __init__(self, x, y):
        dialogue = [
            "Welcome in, traveler. Warm floorboards beat cold roads.",
            "Most adventurers ask about dungeons. The wise ones ask about supper.",
            "You can learn plenty by listening before you descend.",
        ]
        super().__init__(x, y, 'A', 'Innkeeper', (255, 215, 120), dialogue)

        # A small, fixed food menu -- unlike Shopkeeper, the innkeeper
        # doesn't restock randomly or carry equipment, only supper and a
        # bed. See structures.STRUCTURE_BLUEPRINTS' "tavern" blueprint.
        food_menu = [bread, meat, fromage, green_apple, carrot, mushroom]
        self.items_for_sale = [_clone_item(item) for item in food_menu]

    def offer_trade(self, player, game):
        """
        Open the same shop overlay Shopkeeper.offer_trade() uses (see
        game.py's render_shop_menu()/handle_shop_menu_input()) scoped to
        the innkeeper's food menu -- that overlay only needs an object
        with .name/.items_for_sale/.buy_item()/.sell_item(), so it works
        unmodified for any merchant-shaped NPC, not just Shopkeeper.
        """
        game._previous_game_state = game.game_state
        game._shop_menu_merchant  = self
        game._shop_selected_index = 0
        game._shop_mode           = "buy"
        game.game_state           = GameState.SHOP_MENU

    def buy_item(self, player, item_name):
        return _buy_from_stock(self, player, item_name)

    def sell_item(self, player, item_name):
        """The innkeeper doesn't buy anything back -- kept so the shared
        shop overlay's SELL tab has something safe to call rather than
        crashing if a player tabs over to it out of habit."""
        return f'{self.name} shakes their head. "I only deal in food and lodging here."'

    def rest_player(self, player, game):
        """
        Handle the player paying for a night's stay: charges rest_cost
        gold, fully restores HP, and advances the world clock by a full
        night through StorySystems.fire_rest() -- the canonical inn/camp
        rest path story_integration.py's docstring already earmarks for
        this, so any story timer (deadlines, decay, scheduled events)
        sees it exactly like any other rest.

        Returns a message string for the caller to log, matching
        buy_item()/sell_item()'s "return a string, let the caller log
        it" convention.
        """
        if player.gold < self.rest_cost:
            return f"You can't afford a room tonight. A bed costs {self.rest_cost} gold."

        player.gold -= self.rest_cost
        player.hp = player.max_hp

        # Some classes track further per-rest resources (spell slots,
        # ability charges, ...) behind their own long_rest() hook; restore
        # those too if present, without this needing to know their shape.
        long_rest = getattr(player, "long_rest", None)
        if callable(long_rest):
            long_rest()

        game.stories.fire_rest(self.rest_hours)
        return f"You rest through the night and wake up refreshed. (-{self.rest_cost} gold)"


class Shopkeeper(TownNPC):
    #: Minds the shop during open hours instead of wandering.
    schedule = AT_POST_SCHEDULE

    def __init__(self, x, y):
        dialogue = [
            "I am still unpacking the shelves, but I know a good buyer when I see one.",
            "Bring back anything odd from the ruins. Odd things sell.",
            "A careful blade and a dry torch are worth more than bravado.",
        ]
        super().__init__(x, y, 'rc', 'Shopkeeper', (230, 200, 120), dialogue)

        self.saving_throw_proficiencies = {
            "STR": False,
            "DEX": True,
            "CON": False,
            "INT": False,
            "WIS": False,
            "CHA": False,
        }
        # Default items always sold
        default_items = [
            CampfireKit(),
            lesser_healing_potion,
            greater_healing_potion,
            meat,
            bread,
            carrot,
            fromage,
            torch,
            throwing_knife,
        ]
        # Chance-based items with their spawn probabilities (fewer and simpler than dungeon merchant)
        chance_items_with_chance = [
            (duelists_rapier, 0.3),
            (staff_of_magi, 0.3),
            (full_plate_armor, 0.35),
            (scale_mail_armor, 0.4),
            (sturdy_quarterstaff, 0.6),
            (iron_helmet, 0.7),
            (leather_cap, 0.8),
            (steel_helmet, 0.6),
            (hood_of_shadows, 0.4),
            (great_helm, 0.3),
            (mages_circlet, 0.4),
            (leather_boots, 0.8),
            (iron_greaves, 0.8),
            (boots_of_speed, 0.4),
            (boots_of_stealth, 0.4),
            (dwarven_stompers, 0.3),
            (adamantine_long_sword, 0.5),
            (flameheart_flail, 0.5),
            (flameheart_short_sword, 0.4),
            (robes_of_protection, 0.35),
            (dwarven_battle_axe, 0.45),
            (dragonsbane_warhammer, 0.3),
            (spell_book, 0.25),
            (holy_symbol, 0.25),
            (carrot, 0.3),
            (mushroom, 0.3),
            (green_apple, 0.3),
            (bread, 0.3),
            (meat, 0.3),
        ]

        self.items_for_sale = []
       
        # Add default items
        for item in default_items:
            if isinstance(item, CampfireKit):
                self.items_for_sale.append(CampfireKit()) # Create a new instance directly
            else:
                # Create a new instance for other items
                new_item = item.__class__(
                    name=item.name,
                    char=item.char,
                    color=item.color,
                    description=item.description,
                    **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                )
                self.items_for_sale.append(new_item)
    
        # Add chance-based items
        for item, chance in chance_items_with_chance:
            if random.random() < chance:
                new_item = item.__class__(
                    name=item.name,
                    char=item.char,
                    color=item.color,
                    description=item.description,
                    **{k: v for k, v in item.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                )
                self.items_for_sale.append(new_item)

    def offer_trade(self, player, game):
        """Open the shop menu overlay instead of the legacy text-input trade flow."""
        game._previous_game_state  = game.game_state
        game._shop_menu_merchant   = self
        game._shop_selected_index  = 0
        game._shop_mode            = "buy"
        game.game_state            = GameState.SHOP_MENU



    def buy_item(self, player, item_name):
        return _buy_from_stock(self, player, item_name)
    


    def sell_item(self, player, item_name):
        """Logic to sell an item or multiple items."""
        # Handle bulk selling
        if item_name == "all equipments":
            equipments = [item for item in player.inventory.items if isinstance(item, (Weapon, OffHand, Armor, Helmet, Boots, FocusItem))]
            if not equipments:
                return "You don't have any equipments to sell."
            total_price = 0
            for item in equipments:
                player.inventory.remove_item(item)
                total_price += item.price // 2
                self.items_for_sale.append(item)
            player.money += total_price
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_holy_symbol_abilities()
            player.update_guard_ability()
            return f"You sold {len(equipments)} equipment(s) for {format_price(total_price)}!"

        if item_name == "all weapons":
            weapons = [item for item in player.inventory.items if isinstance(item, (Weapon, OffHand))]
            if not weapons:
                return "You don't have any weapons to sell."
            total_price = 0
            for item in weapons:
                player.inventory.remove_item(item)
                total_price += item.price // 2
                self.items_for_sale.append(item)
            player.money += total_price
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_guard_ability()
            return f"You sold {len(weapons)} weapon(s) for {format_price(total_price)}!"

        if item_name == "all armors":
            armor_items = [item for item in player.inventory.items if isinstance(item, (Helmet, Armor, Boots))]
            if not armor_items:
                return "You don't have any armor to sell."
            total_price = 0
            for item in armor_items:
                player.inventory.remove_item(item)
                total_price += item.price // 2
                self.items_for_sale.append(item)
            player.money += total_price
            player.update_throw_knife_ability()
            player.update_spellbook_abilities()
            player.update_holy_symbol_abilities()
            player.update_guard_ability()
            return f"You sold {len(armor_items)} armor item(s) for {format_price(total_price)}!"
        
        # Handle single item selling
        for item in player.inventory.items:  # Access the player's inventory items
            if item.name.lower() == item_name.lower():  # Case insensitive comparison
                player.inventory.remove_item(item)  # Remove the item from the player's inventory
                player.money += item.price // 2  # Assuming the merchant pays half the price
                self.items_for_sale.append(item)  # Add the item back to the merchant's inventory
                player.update_throw_knife_ability()
                player.update_spellbook_abilities()
                player.update_holy_symbol_abilities()
                player.update_guard_ability()
                return f"You sold {item.name}!"
        return "Item not found in your inventory."


TOWNSFOLK_NAMES = [
    "Mara", "Edrin", "Tess", "Borin", "Lysa", "Corren", "Nessa", "Tobin"
]