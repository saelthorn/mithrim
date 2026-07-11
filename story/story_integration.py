"""
story_integration.py

Game-layer glue between Mithrim's narrative engine (story_framework,
trigger_system, condition_system, consequence_system, story_queue_manager,
story_failure_system, story_chain_system, world_time, story_content_loader)
and the existing Game class in game.py.

Nothing in the engine itself is modified. This module only:
  1. Implements ConditionContext / ExecutionContext as thin adapters over
     an existing Game instance (the "host" interface both systems expect).
  2. Boots every manager and loads all story JSON from content/stories/.
  3. Exposes a few fire_* helpers so game.py's existing event handlers
     (combat resolution, object interaction, dialogue, resting) can each
     add ONE line to notify the story engine, instead of the story engine
     needing to know anything about pygame/Game internals.

Usage from game.py (see integration notes at the bottom of this file):

    from story_integration import StorySystems

    # in Game.__init__, after self.player and self.message_log exist:
    self.stories = StorySystems(self)

    # in Game.update(dt):
    self.stories.update(dt)

    # wherever the player inspects a StoryObject:
    self.stories.fire_inspect(story_object, instigator=self.player)

    # wherever an NPC/monster dies:
    self.stories.fire_kill(npc, instigator=self.player)

    # wherever the player talks to an NPC:
    self.stories.fire_talk(npc, instigator=self.player)

    # wherever the player enters/leaves a named area or town:
    self.stories.fire_enter_area(area_id, instigator=self.player)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from story.story_framework import StoryManager
from story.trigger_system import TriggerSystem, TriggerType
from story.story_queue_manager import StoryQueueManager
from story.story_failure_system import StoryFailureManager, WorldScarRegistry
from story.story_chain_system import StoryChainManager
from world.world_time import WorldTimeManager, TimeUnit
from story.story_content_loader import StoryContentLoader, DialogueLibrary


# ---------------------------------------------------------------------------
# GameConditionContext -- read-only adapter (condition_system.ConditionContext)
# ---------------------------------------------------------------------------

class GameConditionContext:
    """
    Satisfies condition_system.ConditionContext by reading off an
    existing Game instance. Every method here is a thin lookup -- no
    story logic lives in this class, only "where does Game keep this".

    Falls back to conservative defaults (0 / False / empty) if a piece
    of state doesn't exist yet (e.g. before character creation), so
    condition evaluation never raises during menu/setup screens.
    """

    def __init__(self, game: Any, story_manager: StoryManager, scar_registry: WorldScarRegistry):
        self.game = game
        self.story_manager = story_manager
        self._scar_registry = scar_registry

    def get_player_level(self) -> int:
        player = getattr(self.game, "player", None)
        return getattr(player, "level", 1) if player else 1

    def get_faction_reputation(self, faction: str) -> float:
        reputations = getattr(self.game, "faction_reputations", {})
        return float(reputations.get(faction, 0.0))

    def is_npc_alive(self, npc_id: str) -> bool:
        registry = getattr(self.game, "npc_registry", {})
        npc = registry.get(npc_id)
        if npc is None:
            return False
        return getattr(npc, "hp", 1) > 0

    def has_item(self, item_id: str) -> int:
        player = getattr(self.game, "player", None)
        if player is None or not hasattr(player, "inventory"):
            return 0
        return sum(1 for item in player.inventory if getattr(item, "id", None) == item_id)

    def has_visited_area(self, area_id: str) -> bool:
        visited = getattr(self.game, "visited_areas", set())
        return area_id in visited

    def get_elapsed_time(self) -> float:
        world_time = getattr(self.game, "world_time", None)
        return float(world_time.clock.total_hours) if world_time else 0.0

    def has_world_scar(self, tag: str) -> bool:
        return self._scar_registry.has_scar(tag)


# ---------------------------------------------------------------------------
# GameExecutionContext -- mutating adapter (consequence_system.ExecutionContext)
# ---------------------------------------------------------------------------

class GameExecutionContext:
    """
    Satisfies consequence_system.ExecutionContext by mutating an existing
    Game instance. Same rule as GameConditionContext: pure plumbing, no
    story-specific behavior. Every method degrades gracefully (logs to
    the message log if present) rather than raising, since Consequence.
    execute() already wraps calls in try/except -- but a clean no-op is
    still better than an AttributeError bubbling up as a "failed" result.
    """

    def __init__(self, game: Any, story_manager: StoryManager):
        self.game = game
        self.story_manager = story_manager

    def _log(self, text: str, color: Tuple[int, int, int] = (200, 200, 255)) -> None:
        if getattr(self.game, "message_log", None) is not None:
            self.game.message_log.add_message(text, color)

    def reward_xp(self, amount: int) -> None:
        player = getattr(self.game, "player", None)
        if player is not None and hasattr(player, "gain_xp"):
            player.gain_xp(amount)
        self._log(f"You gain {amount} XP.", (150, 255, 180))

    def reward_gold(self, amount: int) -> None:
        player = getattr(self.game, "player", None)
        if player is not None:
            player.gold = getattr(player, "gold", 0) + amount
        self._log(f"You receive {amount} gold.", (255, 215, 0))

    def spawn_npc(self, npc_type: str, position: Tuple[float, float], data: Optional[Dict[str, Any]] = None) -> str:
        spawner = getattr(self.game, "spawn_story_npc", None)
        if spawner is None:
            return f"unspawned:{npc_type}"
        return spawner(npc_type, position, data or {})

    def spawn_merchant(self, merchant_type: str, position: Tuple[float, float], inventory: Optional[List[str]] = None) -> str:
        spawner = getattr(self.game, "spawn_story_merchant", None)
        if spawner is None:
            return f"unspawned:{merchant_type}"
        return spawner(merchant_type, position, inventory or [])

    def despawn_entity(self, entity_id: str) -> None:
        registry = getattr(self.game, "npc_registry", {})
        npc = registry.pop(entity_id, None)
        if npc is not None and hasattr(self.game, "npcs") and npc in self.game.npcs:
            self.game.npcs.remove(npc)

    def destroy_landmark(self, landmark_id: str) -> Dict[str, Any]:
        landmarks = getattr(self.game, "landmark_registry", {})
        landmark = landmarks.get(landmark_id)
        snapshot = {"existed": landmark is not None}
        if landmark is not None:
            landmarks.pop(landmark_id, None)
            self._log(f"{landmark_id} is destroyed.", (255, 120, 100))
        return snapshot

    def restore_landmark(self, landmark_id: str, snapshot: Dict[str, Any]) -> None:
        pass  # Landmark restoration is content-specific; no-op by default.

    def modify_reputation(self, faction: str, delta: float) -> None:
        reputations = self.game.__dict__.setdefault("faction_reputations", {})
        reputations[faction] = reputations.get(faction, 0.0) + delta
        sign = "+" if delta >= 0 else ""
        self._log(f"Reputation with {faction} {sign}{delta:g}.", (180, 180, 255))

    def give_item(self, item_id: str, count: int) -> None:
        giver = getattr(self.game, "give_item_to_player", None)
        if giver is not None:
            giver(item_id, count)
        self._log(f"You receive {item_id} x{count}.", (255, 255, 150))

    def remove_item(self, item_id: str, count: int) -> None:
        remover = getattr(self.game, "remove_item_from_player", None)
        if remover is not None:
            remover(item_id, count)

    def change_weather(self, weather_type: str) -> str:
        previous = getattr(self.game, "weather", "clear")
        self.game.weather = weather_type
        return previous

    def unlock_region(self, region_id: str) -> None:
        unlocked = self.game.__dict__.setdefault("unlocked_regions", set())
        unlocked.add(region_id)

    def lock_region(self, region_id: str) -> None:
        unlocked = getattr(self.game, "unlocked_regions", set())
        unlocked.discard(region_id)


# ---------------------------------------------------------------------------
# StorySystems -- the single object game.py talks to
# ---------------------------------------------------------------------------

class StorySystems:
    """
    Boots and owns every narrative-engine manager for one running game,
    loads all story content from content/stories/, and exposes small
    fire_* helpers so game.py's existing event handlers can notify the
    engine with a single call each.

    Construct once, in Game.__init__, after self.player exists (the
    condition/execution contexts read from self.game lazily, so player
    creation order relative to this constructor doesn't actually matter
    -- but keeping it after is clearer to read).
    """

    CONTENT_ROOT = "content/stories"

    def __init__(self, game: Any, content_root: Optional[str] = None):
        self.game = game

        self.trigger_system = TriggerSystem()
        self.story_manager = StoryManager(trigger_system=self.trigger_system)
        self.world_time = WorldTimeManager(trigger_system=self.trigger_system)
        self.queue_manager = StoryQueueManager(self.story_manager, world_time=self.world_time)
        self.scar_registry = WorldScarRegistry()
        self.failure_manager = StoryFailureManager(
            self.story_manager,
            queue_manager=self.queue_manager,
            world_time=self.world_time,
            registry=self.scar_registry,
        )
        self.chain_manager = StoryChainManager(self.story_manager, self.queue_manager)

        self.condition_context = GameConditionContext(game, self.story_manager, self.scar_registry)
        self.execution_context = GameExecutionContext(game, self.story_manager)
        self.story_manager.set_condition_context(self.condition_context)
        self.story_manager.set_execution_context(self.execution_context)

        self.loader = StoryContentLoader(
            self.story_manager, queue_manager=self.queue_manager, failure_manager=self.failure_manager
        )
        self.dialogue: DialogueLibrary = self.loader.dialogue

        self.load_report = self.loader.load_directory(content_root or self.CONTENT_ROOT)
        self._log_load_report()
        self.loader.build_chains(self.chain_manager)

    # -- loading feedback ---------------------------------------------------

    def _log_load_report(self) -> None:
        log = getattr(self.game, "message_log", None)
        if log is None:
            return
        log.add_message(f"Loaded {len(self.load_report.loaded)} stories.", (150, 200, 255))
        for error in self.load_report.errors:
            log.add_message(f"Story load error: {error}", (255, 100, 100))

    # -- per-frame tick -------------------------------------------------------

    def update(self, dt: float) -> None:
        """Call once per frame/turn from Game.update(). Advances world
        time by whole in-game hours as they accumulate in dt, and lets
        the queue manager sweep dormant stories for newly-met requirements."""
        hours = getattr(self.game, "hours_per_tick", 0)
        if hours:
            self.world_time.advance(hours, TimeUnit.HOUR)
        self.queue_manager.update(
            player_level=self.condition_context.get_player_level(),
            player_position=self._player_position(),
        )

    def _player_position(self) -> Optional[Tuple[float, float]]:
        player = getattr(self.game, "player", None)
        if player is None:
            return None
        return (getattr(player, "x", 0.0), getattr(player, "y", 0.0))

    # -- fire_* helpers, one per gameplay event game.py already handles -----

    def fire_inspect(self, story_object: Any, instigator: Any = None, **data: Any) -> None:
        self.trigger_system.fire(TriggerType.INSPECT_OBJECT, target=story_object, instigator=instigator, **data)

    def fire_talk(self, npc: Any, instigator: Any = None, **data: Any) -> None:
        self.trigger_system.fire(TriggerType.TALK_NPC, target=npc, instigator=instigator, **data)

    def fire_kill(self, npc: Any, instigator: Any = None, **data: Any) -> None:
        self.trigger_system.fire(TriggerType.KILL_NPC, target=npc, instigator=instigator, **data)

    def fire_loot(self, story_object: Any, instigator: Any = None, **data: Any) -> None:
        self.trigger_system.fire(TriggerType.LOOT_OBJECT, target=story_object, instigator=instigator, **data)

    def fire_enter_area(self, area_id: str, instigator: Any = None, **data: Any) -> None:
        self.trigger_system.fire(TriggerType.ENTER_AREA, location=area_id, instigator=instigator, **data)
        visited = self.game.__dict__.setdefault("visited_areas", set())
        visited.add(area_id)

    def fire_leave_area(self, area_id: str, instigator: Any = None, **data: Any) -> None:
        self.trigger_system.fire(TriggerType.LEAVE_AREA, location=area_id, instigator=instigator, **data)

    def fire_read_journal(self, story_object: Any, instigator: Any = None, **data: Any) -> None:
        self.trigger_system.fire(TriggerType.READ_JOURNAL, target=story_object, instigator=instigator, **data)

    def fire_rest(self, hours: int, instigator: Any = None) -> None:
        """Convenience for inn/camp resting: advances world time directly
        (rather than through the per-frame hours_per_tick accumulator)
        and fires SLEEP so any story reacting to "the player slept" sees it."""
        self.world_time.advance(hours, TimeUnit.HOUR)
        self.trigger_system.fire(TriggerType.SLEEP, instigator=instigator, hours=hours)

    def get_dialogue(self, story_id: str, node_id: str):
        return self.dialogue.get(story_id, node_id)


# ---------------------------------------------------------------------------
# Integration notes for game.py (apply by hand -- nothing here is auto-patched)
# ---------------------------------------------------------------------------
#
# 1. Import, near the other top-level imports:
#
#       from story_integration import StorySystems
#
# 2. In Game.__init__, after self.player / self.message_log are set up:
#
#       self.stories = StorySystems(self)
#
# 3. In Game.update(self, dt), anywhere after the world-state is settled
#    for the frame:
#
#       self.stories.update(dt)
#
# 4. Wherever the player currently interacts with a world object that
#    should be story-aware (e.g. the existing "inspect"/"E to interact"
#    handler), after resolving whichever StoryObject was targeted:
#
#       if isinstance(target, StoryObject):
#           target.inspect(self.stories.story_manager)   # advances the story itself
#           self.stories.fire_inspect(target, instigator=self.player)  # notifies TriggerRules
#
# 5. Wherever a monster/NPC's death is finalized (hp <= 0 resolution):
#
#       self.stories.fire_kill(monster, instigator=self.player, group_id=getattr(monster, "group_id", None))
#
# 6. Wherever dialogue with an NPC starts:
#
#       self.stories.fire_talk(npc, instigator=self.player)
#
# 7. Optional -- if/when a `game.hours_per_tick` attribute exists (an
#    accumulator that turns real playtime or turn-count into whole game
#    hours), StorySystems.update() will advance world_time automatically.
#    Until then, call self.stories.fire_rest(hours) explicitly at
#    inn/camp rest points, which is the only place most stories care
#    about elapsed time anyway (missed deadlines, decay, relocation).
#
# None of these calls require game.py to import anything from the story
# engine directly -- only story_integration.StorySystems and, at call
# site 4, the StoryObject base class from story.story_object if isinstance
# checks are wanted (a plain getattr(target, "story_id", None) check
# works too, and avoids that import entirely).