"""
story_framework.py

Phase 3 -- Story Framework.

This module provides the architectural skeleton for Mithrim's narrative
engine: StoryInstance, StoryDirector, and StoryManager.

This is framework only. It contains no story content, dialogue, quests,
or events -- those belong to later phases and to data/content modules
that plug into this framework.

Design summary
---------------
- StoryInstance   : the data + lifecycle of a single story (state machine).
- StoryDirector    : controls progression of ONE story instance at a time
                      (start/pause/resume/advance/end) and exposes hooks
                      that future systems (quests, dialogue, cutscenes,
                      scripting) can subscribe to. Contains no content.
- StoryManager     : owns and orchestrates MANY StoryInstances (create,
                      load, unload, delete, update, save/load-all).

Determinism: every StoryInstance carries a `seed`. Any procedural
narrative logic added in later phases should derive its randomness from
that seed (e.g. via `random.Random(seed)`) so stories are reproducible.
"""

from __future__ import annotations

import random
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional

from search_area import SearchArea
from trigger_system import TriggerEvent, TriggerRule, TriggerSystem, TriggerType
from condition_system import Condition, ConditionContext, ConditionEvaluator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StoryState(Enum):
    """Lifecycle state of a StoryInstance."""
    UNINITIALIZED = "uninitialized"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class StoryEvent(Enum):
    """
    Hook events fired by StoryDirector. Future systems (quests, dialogue,
    cutscenes, scripting) subscribe to these instead of the director
    knowing about them directly.
    """
    STORY_STARTED = "story_started"
    STORY_PAUSED = "story_paused"
    STORY_RESUMED = "story_resumed"
    STAGE_ADVANCED = "stage_advanced"
    STORY_COMPLETED = "story_completed"
    STORY_FAILED = "story_failed"
    STORY_ABORTED = "story_aborted"
    FLAG_CHANGED = "flag_changed"
    OBJECT_INSPECTED = "object_inspected"
    TRIGGER_MATCHED = "trigger_matched"


# ---------------------------------------------------------------------------
# StoryInstance
# ---------------------------------------------------------------------------

class StoryInstance:
    """
    Represents a single active (or inactive) story.

    A StoryInstance is a pure data + lifecycle container. It knows how to
    initialize itself, move between stages, hold arbitrary flags/objects,
    validate its own consistency, and (de)serialize -- but it does not
    know *why* it advances or *what* content lives at each stage. That
    orchestration belongs to StoryDirector; the content itself belongs to
    later phases.
    """

    def __init__(
        self,
        story_id: Optional[str] = None,
        seed: Optional[int] = None,
        stage_count: int = 1,
    ):
        self.id: str = story_id or str(uuid.uuid4())
        self.seed: int = seed if seed is not None else random.randrange(2 ** 32)
        self.rng: random.Random = random.Random(self.seed)

        self.state: StoryState = StoryState.UNINITIALIZED
        self.stage: int = 0
        self.stage_count: int = max(1, stage_count)

        # Arbitrary story-scoped data. Flags are simple key/value truths
        # ("met_the_hermit": True); objects hold richer data structures
        # ("captured_npc_ids": [...], "reputation": {...}) without the
        # framework needing to know their shape.
        self.flags: Dict[str, Any] = {}
        self.objects: Dict[str, Any] = {}

        # Every story owns exactly one SearchArea -- the physical zone
        # where it takes place. It is not created automatically (a story
        # may be uninitialized before its area's size/location is known);
        # use set_search_area() or create_search_area() once that's decided.
        self.search_area: Optional[SearchArea] = None

        # Data-driven trigger declarations: "when TriggerType X fires and
        # these conditions hold, respond". Evaluated by StoryManager
        # against every TriggerEvent it receives. Not included in
        # to_dict()/from_dict() -- like StoryDirector's hooks, rules may
        # carry Python callables (`effect`) and are expected to be
        # re-registered by content-layer code after a story is loaded.
        self.trigger_rules: List[TriggerRule] = []

        self.created_at: float = time.time()
        self.updated_at: float = self.created_at

    # -- lifecycle -----------------------------------------------------

    def initialize(self) -> None:
        """
        Reset runtime data and mark the story ready to be started.
        Safe to call again later via reset().
        """
        self.rng = random.Random(self.seed)
        self.state = StoryState.UNINITIALIZED
        self.stage = 0
        self.flags = {}
        self.objects = {}
        self._touch()

    def reset(self, new_seed: Optional[int] = None) -> None:
        """Fully reset the story, optionally re-seeding it."""
        if new_seed is not None:
            self.seed = new_seed
        self.initialize()

    def _touch(self) -> None:
        self.updated_at = time.time()

    # -- flags -----------------------------------------------------------

    def get_flag(self, key: str, default: Any = None) -> Any:
        return self.flags.get(key, default)

    def set_flag(self, key: str, value: Any) -> None:
        self.flags[key] = value
        self._touch()

    def has_flag(self, key: str) -> bool:
        return key in self.flags

    def clear_flag(self, key: str) -> None:
        self.flags.pop(key, None)
        self._touch()

    # -- objects -----------------------------------------------------------

    def get_object(self, key: str, default: Any = None) -> Any:
        return self.objects.get(key, default)

    def set_object(self, key: str, value: Any) -> None:
        self.objects[key] = value
        self._touch()

    def remove_object(self, key: str) -> None:
        self.objects.pop(key, None)
        self._touch()

    # -- search area --------------------------------------------------------

    def create_search_area(
        self,
        center: Any = (0.0, 0.0),
        size: Any = (50, 50),
        seed: Optional[int] = None,
    ) -> SearchArea:
        """
        Create and attach this story's SearchArea, seeded from the story's
        own seed by default so the area is reproducible from the story
        seed alone unless a distinct seed is explicitly supplied.
        """
        area_seed = seed if seed is not None else self.seed
        self.search_area = SearchArea(
            story_id=self.id,
            center=center,
            size=size,
            seed=area_seed,
        )
        self._touch()
        return self.search_area

    def set_search_area(self, area: SearchArea) -> None:
        """Attach an already-constructed SearchArea to this story."""
        self.search_area = area
        self._touch()

    # -- trigger rules --------------------------------------------------------

    def add_trigger_rule(self, rule: TriggerRule) -> None:
        """Register a data-driven TriggerRule this story should evaluate
        against incoming TriggerEvents."""
        self.trigger_rules.append(rule)
        self._touch()

    def remove_trigger_rule(self, rule_id: str) -> bool:
        for rule in self.trigger_rules:
            if rule.id == rule_id:
                self.trigger_rules.remove(rule)
                self._touch()
                return True
        return False

    def get_trigger_rules(self, trigger_type: Optional[TriggerType] = None) -> List[TriggerRule]:
        if trigger_type is None:
            return list(self.trigger_rules)
        return [rule for rule in self.trigger_rules if rule.trigger_type == trigger_type]

    # -- stage progression ------------------------------------------------

    def can_advance(self) -> bool:
        """Whether there is a next stage to advance into."""
        return self.stage + 1 < self.stage_count

    def advance_stage(self) -> bool:
        """
        Move to the next stage. Returns True if advanced, False if already
        at (or beyond) the final stage. Does not change `state` -- that is
        StoryDirector's responsibility.
        """
        if not self.can_advance():
            return False
        self.stage += 1
        self._touch()
        return True

    def is_final_stage(self) -> bool:
        return self.stage >= self.stage_count - 1

    # -- validation ---------------------------------------------------------

    def validate(self) -> List[str]:
        """
        Check internal consistency. Returns a list of human-readable
        problems; an empty list means the instance is valid.
        """
        problems: List[str] = []

        if not self.id:
            problems.append("Story has no id.")
        if self.stage_count < 1:
            problems.append("stage_count must be >= 1.")
        if not (0 <= self.stage < self.stage_count):
            problems.append(
                f"stage {self.stage} out of range for stage_count {self.stage_count}."
            )
        if not isinstance(self.flags, dict):
            problems.append("flags must be a dict.")
        if not isinstance(self.objects, dict):
            problems.append("objects must be a dict.")
        if not isinstance(self.state, StoryState):
            problems.append("state must be a StoryState.")
        if self.search_area is not None and self.search_area.story_id != self.id:
            problems.append("search_area.story_id does not match this story's id.")

        return problems

    def is_valid(self) -> bool:
        return not self.validate()

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding."""
        return {
            "id": self.id,
            "seed": self.seed,
            "state": self.state.value,
            "stage": self.stage,
            "stage_count": self.stage_count,
            "flags": dict(self.flags),
            "objects": dict(self.objects),
            "search_area": self.search_area.to_dict() if self.search_area else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryInstance":
        """Reconstruct a StoryInstance from a dict produced by to_dict()."""
        instance = cls(
            story_id=data["id"],
            seed=data.get("seed"),
            stage_count=data.get("stage_count", 1),
        )
        instance.state = StoryState(data.get("state", StoryState.UNINITIALIZED.value))
        instance.stage = data.get("stage", 0)
        instance.flags = dict(data.get("flags", {}))
        instance.objects = dict(data.get("objects", {}))
        area_data = data.get("search_area")
        instance.search_area = SearchArea.from_dict(area_data) if area_data else None
        instance.created_at = data.get("created_at", time.time())
        instance.updated_at = data.get("updated_at", instance.created_at)
        # Restore rng state deterministically from the seed. Replaying the
        # exact rng cursor position is a later-phase concern (would require
        # persisting rng.getstate() too, if bit-exact resume is needed).
        instance.rng = random.Random(instance.seed)
        return instance

    def __repr__(self) -> str:
        return (
            f"StoryInstance(id={self.id!r}, state={self.state.value}, "
            f"stage={self.stage}/{self.stage_count - 1})"
        )


# ---------------------------------------------------------------------------
# StoryDirector
# ---------------------------------------------------------------------------

class StoryDirector:
    """
    Controls the progression of a single StoryInstance.

    The director owns transition rules (what states can move to what
    states) and fires hook events so other systems can react to
    progression without the director needing to know about them. It
    holds no story content itself.

    One StoryDirector is bound to one StoryInstance at a time. StoryManager
    is responsible for creating/owning directors per active story.
    """

    # Legal state transitions. Keys are the current state; values are the
    # set of states that may be entered directly from it.
    _TRANSITIONS: Dict[StoryState, set] = {
        StoryState.UNINITIALIZED: {StoryState.ACTIVE},
        StoryState.ACTIVE: {
            StoryState.PAUSED,
            StoryState.COMPLETED,
            StoryState.FAILED,
            StoryState.ABORTED,
        },
        StoryState.PAUSED: {StoryState.ACTIVE, StoryState.ABORTED},
        StoryState.COMPLETED: set(),
        StoryState.FAILED: set(),
        StoryState.ABORTED: set(),
    }

    def __init__(self, story: StoryInstance):
        self.story: StoryInstance = story
        # event -> list of callback(story, **context)
        self._hooks: Dict[StoryEvent, List[Callable[..., None]]] = {
            event: [] for event in StoryEvent
        }

    # -- hooks ---------------------------------------------------------

    def on(self, event: StoryEvent, callback: Callable[..., None]) -> None:
        """Subscribe a callback to a director event."""
        self._hooks[event].append(callback)

    def off(self, event: StoryEvent, callback: Callable[..., None]) -> None:
        """Unsubscribe a callback from a director event, if present."""
        if callback in self._hooks[event]:
            self._hooks[event].remove(callback)

    def _emit(self, event: StoryEvent, **context: Any) -> None:
        for callback in self._hooks[event]:
            callback(self.story, **context)

    # -- transition validation ------------------------------------------

    def can_transition(self, target: StoryState) -> bool:
        allowed = self._TRANSITIONS.get(self.story.state, set())
        return target in allowed

    def _transition(self, target: StoryState) -> bool:
        if not self.can_transition(target):
            return False
        self.story.state = target
        self.story._touch()
        return True

    # -- lifecycle control ------------------------------------------------

    def start(self) -> bool:
        """Move an uninitialized story into the active state."""
        if self.story.state == StoryState.UNINITIALIZED:
            self.story.initialize()
        if self._transition(StoryState.ACTIVE):
            self._emit(StoryEvent.STORY_STARTED)
            return True
        return False

    def pause(self) -> bool:
        if self._transition(StoryState.PAUSED):
            self._emit(StoryEvent.STORY_PAUSED)
            return True
        return False

    def resume(self) -> bool:
        if self._transition(StoryState.ACTIVE):
            self._emit(StoryEvent.STORY_RESUMED)
            return True
        return False

    def advance(self) -> bool:
        """
        Advance the story to its next stage. If the story is already on
        its final stage, this completes the story instead.
        """
        if self.story.state != StoryState.ACTIVE:
            return False

        if self.story.is_final_stage():
            return self.complete()

        if self.story.advance_stage():
            self._emit(StoryEvent.STAGE_ADVANCED, stage=self.story.stage)
            return True
        return False

    def complete(self) -> bool:
        if self._transition(StoryState.COMPLETED):
            self._emit(StoryEvent.STORY_COMPLETED)
            return True
        return False

    def fail(self, reason: Optional[str] = None) -> bool:
        if self._transition(StoryState.FAILED):
            self._emit(StoryEvent.STORY_FAILED, reason=reason)
            return True
        return False

    def abort(self, reason: Optional[str] = None) -> bool:
        if self._transition(StoryState.ABORTED):
            self._emit(StoryEvent.STORY_ABORTED, reason=reason)
            return True
        return False

    # -- flag convenience (routes through the story, emits a hook) --------

    def set_flag(self, key: str, value: Any) -> None:
        old_value = self.story.get_flag(key)
        self.story.set_flag(key, value)
        self._emit(StoryEvent.FLAG_CHANGED, key=key, old_value=old_value, new_value=value)

    # -- story object interaction ------------------------------------------

    def notify_object_inspected(self, story_object: Any) -> bool:
        """
        Handle a StoryObject reporting that it was interacted with.

        Generic progression policy: an active story advances one stage
        per accepted interaction. Whatever that stage actually unlocks
        (clues, dialogue, objectives, events) is entirely up to content
        systems subscribed to STAGE_ADVANCED / OBJECT_INSPECTED -- this
        method only decides *whether* progress happens, never *what* it
        contains.
        """
        if not self.is_active():
            return False

        advanced = self.advance()
        self._emit(StoryEvent.OBJECT_INSPECTED, story_object=story_object, advanced=advanced)
        return True

    def notify_trigger_matched(self, rule: TriggerRule, event: TriggerEvent) -> bool:
        """
        Handle a TriggerRule matching an incoming TriggerEvent for this
        director's story.

        If the rule supplies its own `effect`, that callback is
        responsible for whatever progression/response it wants (it
        receives the story, this director, and the event). Otherwise the
        generic default -- same as object inspection -- is to advance one
        stage. Either way TRIGGER_MATCHED fires afterward so other
        systems can react.
        """
        if not self.is_active():
            return False

        if rule.effect is not None:
            rule.effect(self.story, self, event)
        else:
            self.advance()

        rule.mark_fired()
        self._emit(StoryEvent.TRIGGER_MATCHED, rule=rule, trigger_event=event)
        return True

    def is_active(self) -> bool:
        return self.story.state == StoryState.ACTIVE

    def is_finished(self) -> bool:
        return self.story.state in (
            StoryState.COMPLETED,
            StoryState.FAILED,
            StoryState.ABORTED,
        )

    def __repr__(self) -> str:
        return f"StoryDirector(story={self.story.id!r}, state={self.story.state.value})"


# ---------------------------------------------------------------------------
# StoryManager
# ---------------------------------------------------------------------------

class StoryManager:
    """
    Owns and orchestrates every StoryInstance in the game.

    Responsible for creation, loading/unloading, deletion, lookup,
    per-tick updates of active stories, and bulk save/load of all story
    state. It delegates all per-story lifecycle logic to StoryDirector;
    StoryManager itself only manages the collection.

    It also listens to a TriggerSystem (created by default, or supplied
    externally to share dispatch with other systems) and evaluates every
    active story's TriggerRules against each incoming TriggerEvent.
    """

    def __init__(self, trigger_system: Optional[TriggerSystem] = None):
        # All known stories, keyed by id -- includes loaded and unloaded.
        self._stories: Dict[str, StoryInstance] = {}
        # Directors only exist for stories currently loaded into memory.
        self._directors: Dict[str, StoryDirector] = {}
        # Ids of stories that are loaded but not currently active/updating.
        self._unloaded: set = set()

        self.trigger_system: TriggerSystem = trigger_system or TriggerSystem()
        self.trigger_system.subscribe_all(self._on_trigger_event)

        # Shared caching evaluator for any TriggerRule.condition (see
        # condition_system.py). One evaluator for the whole manager means
        # a condition reused across many stories/rules is only actually
        # computed once until something it depends on changes.
        self.condition_evaluator: ConditionEvaluator = ConditionEvaluator()
        # Host-supplied read access to player/world state (level, items,
        # NPCs, ...). Story-only condition types (quest_flag, story_completed,
        # story_failed) work without this being set; anything else does not.
        self.condition_context: Optional[ConditionContext] = None

    def set_condition_context(self, context: ConditionContext) -> None:
        """Attach the host's ConditionContext so TriggerRule.condition
        checks involving player/world state (not just story flags) can
        be evaluated."""
        self.condition_context = context

    # -- creation -----------------------------------------------------------

    def create_story(
        self,
        story_id: Optional[str] = None,
        seed: Optional[int] = None,
        stage_count: int = 1,
        auto_start: bool = False,
    ) -> StoryDirector:
        """
        Create a new StoryInstance and its StoryDirector, register both,
        and optionally start the story immediately.
        """
        story = StoryInstance(story_id=story_id, seed=seed, stage_count=stage_count)
        director = StoryDirector(story)

        self._stories[story.id] = story
        self._directors[story.id] = director
        self._wire_condition_invalidation(director)

        if auto_start:
            director.start()

        return director

    # -- load / unload / delete ---------------------------------------------

    def load_story(self, data: Dict[str, Any]) -> StoryDirector:
        """
        Reconstruct a StoryInstance from serialized data, wrap it in a
        fresh StoryDirector, and register both as loaded.
        """
        story = StoryInstance.from_dict(data)
        director = StoryDirector(story)

        self._stories[story.id] = story
        self._directors[story.id] = director
        self._unloaded.discard(story.id)
        self._wire_condition_invalidation(director)

        return director

    def _wire_condition_invalidation(self, director: StoryDirector) -> None:
        """
        Keep the shared ConditionEvaluator's cache correct automatically:
        whenever this story's flags or terminal state change, drop only
        the cached conditions that actually depend on that specific key
        (see QuestFlagCondition/StoryCompletedCondition/StoryFailedCondition
        in condition_system.py), leaving every other story's cached
        results untouched.
        """
        story_id = director.story.id

        def invalidate_flag(story: StoryInstance, key: str, **_: Any) -> None:
            self.condition_evaluator.invalidate(f"flag:{story_id}:{key}")

        def invalidate_state(*_args: Any, **_kwargs: Any) -> None:
            self.condition_evaluator.invalidate(f"story_state:{story_id}")

        director.on(StoryEvent.FLAG_CHANGED, invalidate_flag)
        director.on(StoryEvent.STORY_COMPLETED, invalidate_state)
        director.on(StoryEvent.STORY_FAILED, invalidate_state)
        director.on(StoryEvent.STORY_ABORTED, invalidate_state)

    def unload_story(self, story_id: str) -> bool:
        """
        Drop the in-memory director for a story while keeping its data
        registered, so it stops being updated but can be reloaded later
        via reload_story(). Returns False if the story is unknown.
        """
        if story_id not in self._stories:
            return False
        self._directors.pop(story_id, None)
        self._unloaded.add(story_id)
        return True

    def reload_story(self, story_id: str) -> Optional[StoryDirector]:
        """Recreate a director for a previously unloaded story."""
        story = self._stories.get(story_id)
        if story is None:
            return None
        director = StoryDirector(story)
        self._directors[story_id] = director
        self._unloaded.discard(story_id)
        self._wire_condition_invalidation(director)
        return director

    def delete_story(self, story_id: str) -> bool:
        """Permanently remove a story and its director."""
        existed = story_id in self._stories
        self._stories.pop(story_id, None)
        self._directors.pop(story_id, None)
        self._unloaded.discard(story_id)
        return existed

    # -- retrieval ------------------------------------------------------

    def get_story(self, story_id: str) -> Optional[StoryInstance]:
        return self._stories.get(story_id)

    def get_director(self, story_id: str) -> Optional[StoryDirector]:
        return self._directors.get(story_id)

    # -- story object interaction ------------------------------------------

    def on_story_object_inspected(self, story_id: str, story_object: Any) -> bool:
        """
        Single entry point for any StoryObject reporting an interaction.

        Looks up the loaded, active director for `story_id` and forwards
        the interaction to it. Returns False (no-op) if the story isn't
        loaded or isn't active -- e.g. objects belonging to a paused,
        completed, or not-yet-started story simply don't contribute.
        All progression logic itself lives on StoryDirector, not here.
        """
        director = self._directors.get(story_id)
        if director is None:
            return False
        return director.notify_object_inspected(story_object)

    def _on_trigger_event(self, event: TriggerEvent) -> None:
        """
        TriggerSystem callback: check every active story's TriggerRules
        for this event and notify the matching ones' directors.

        A single event can match rules across multiple stories (or
        multiple rules within one story) -- each match is handled
        independently via StoryDirector.notify_trigger_matched().
        """
        for story in self.list_stories(only_active=True):
            director = self._directors[story.id]
            for rule in story.get_trigger_rules(event.type):
                if not rule.matches(event, story):
                    continue
                if rule.condition is not None and not self._check_rule_condition(rule.condition):
                    continue
                director.notify_trigger_matched(rule, event)

    def _check_rule_condition(self, condition: Condition) -> bool:
        """Evaluate a TriggerRule's optional richer Condition through the
        shared, caching ConditionEvaluator. Fails closed (does not match)
        if no ConditionContext has been supplied by the host yet."""
        if self.condition_context is None:
            return False
        return self.condition_evaluator.evaluate(condition, self.condition_context)

    def list_stories(self, only_active: bool = False) -> List[StoryInstance]:
        """
        List known stories. With only_active=True, restrict to stories
        currently loaded and in the ACTIVE state.
        """
        if not only_active:
            return list(self._stories.values())
        return [
            story
            for story_id, story in self._stories.items()
            if story_id in self._directors and story.state == StoryState.ACTIVE
        ]

    def is_loaded(self, story_id: str) -> bool:
        return story_id in self._directors

    # -- update loop ------------------------------------------------------

    def update(self, *args: Any, **kwargs: Any) -> None:
        """
        Per-tick hook for all loaded, active stories. Framework-level:
        it does not decide *when* to advance a story, only gives every
        active director a chance to react. Later phases (quests,
        scripting, timers) can override or extend director.advance()
        logic to decide progression conditions.
        """
        for director in self._directors.values():
            if director.is_active():
                # Intentionally a no-op at framework level -- content
                # systems built on top of StoryDirector decide when to
                # call advance()/complete()/fail() themselves.
                pass

    # -- bulk persistence -------------------------------------------------

    def save_all(self) -> Dict[str, Any]:
        """Serialize every known story (loaded or unloaded)."""
        return {
            "stories": [story.to_dict() for story in self._stories.values()],
        }

    def load_all(self, data: Dict[str, Any]) -> None:
        """
        Replace current state with stories deserialized from save_all()
        output. All loaded stories get fresh directors.
        """
        self._stories.clear()
        self._directors.clear()
        self._unloaded.clear()

        for story_data in data.get("stories", []):
            self.load_story(story_data)

    # -- validation -------------------------------------------------------

    def validate_all(self) -> Dict[str, List[str]]:
        """
        Validate every known story. Returns a dict of story_id -> list of
        problems, only including stories that failed validation.
        """
        results: Dict[str, List[str]] = {}
        for story_id, story in self._stories.items():
            problems = story.validate()
            if problems:
                results[story_id] = problems
        return results

    def __len__(self) -> int:
        return len(self._stories)

    def __iter__(self) -> Iterable[StoryInstance]:
        return iter(self._stories.values())

    def __repr__(self) -> str:
        return (
            f"StoryManager(stories={len(self._stories)}, "
            f"loaded={len(self._directors)})"
        )