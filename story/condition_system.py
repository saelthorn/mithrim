"""
condition_system.py

Phase 7 -- Condition System.

Provides a reusable, chainable, data-driven condition evaluation system
(player level, faction reputation, quest flags, NPC alive/dead, has item,
visited area, time passed, story completed/failed, ...) plus a caching
evaluator designed for large numbers of simultaneously active stories.

This is framework only. Conditions ask questions about game state -- they
never contain narrative content, and they never mutate state; evaluation
is always read-only.

Design summary
---------------
- ConditionContext : a thin adapter the host game implements once, giving
                      conditions read access to whatever state they need
                      (player stats, factions, inventory, NPC registry,
                      areas, elapsed time) plus the StoryManager for
                      quest-flag / story-completion questions. Conditions
                      never touch game systems directly -- only through
                      this context -- so they stay portable and testable.
- Condition        : abstract base. Every condition can report which
                      pieces of state it depends on (`dependency_keys`),
                      which is what makes the evaluator's caching cheap
                      to invalidate correctly instead of blindly.
- Leaf conditions  : PlayerLevel, FactionReputation, QuestFlag, NPCAlive,
                      NPCDead, HasItem, VisitedArea, TimePassed,
                      StoryCompleted, StoryFailed, WorldScar.
- Composites       : And / Or / Not, built either explicitly or via the
                      `&`, `|`, `~` operators on any Condition, so trees
                      read like `has_sword & (npc_alive | quest_flag)`.
- Registry         : `@register_condition("type_name")` + `condition_from_dict`
                      let entire condition trees be built from plain
                      dicts/JSON -- no Python required to define new
                      story requirements.
- ConditionEvaluator: caches each condition's last result and only
                      recomputes it when something it actually depends on
                      has changed (via `invalidate(dependency_key)`),
                      rather than re-evaluating every condition of every
                      active story on every tick.

Evaluation pipeline (why this scales to many active stories)
--------------------------------------------------------------
1. Composite conditions short-circuit (And stops at the first False, Or
   stops at the first True), so a story's full condition tree is rarely
   evaluated in full.
2. Every condition declares its dependency_keys() (e.g. "flag:<story_id>:
   met_hermit", "npc_alive:goblin_1", "item:sword"). The evaluator
   indexes conditions by these keys the first time they're seen.
3. When game state changes, the host calls
   `evaluator.invalidate("npc_alive:goblin_1")` (or story_framework.py's
   FLAG_CHANGED/STORY_COMPLETED/... hooks do this automatically for
   quest-flag and story-state conditions). Only conditions that actually
   depend on that key are dropped from cache -- everything else across
   every other active story stays cached and free to re-read.
4. Conditions with no meaningful state key (e.g. a pure function of
   something that changes every tick) simply declare no dependencies and
   are treated as always-dirty, so correctness never depends on the host
   remembering to invalidate them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Protocol, Tuple, runtime_checkable


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------

class Comparator(Enum):
    """Numeric comparison used by threshold-style conditions (level,
    reputation, time passed, item count)."""
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"

    def apply(self, actual: Any, expected: Any) -> bool:
        if self is Comparator.EQ:
            return actual == expected
        if self is Comparator.NE:
            return actual != expected
        if self is Comparator.GT:
            return actual > expected
        if self is Comparator.GTE:
            return actual >= expected
        if self is Comparator.LT:
            return actual < expected
        if self is Comparator.LTE:
            return actual <= expected
        raise ValueError(f"Unknown comparator: {self}")


# ---------------------------------------------------------------------------
# ConditionContext
# ---------------------------------------------------------------------------

@runtime_checkable
class ConditionContext(Protocol):
    """
    Everything a Condition might need to read, as a narrow interface the
    host game implements once. Conditions depend only on this protocol,
    never on concrete game classes, so new condition types never need to
    know how the player, inventory, or NPC registry are actually built.

    `story_manager` is the one concrete framework object exposed directly,
    since quest-flag / story-completion questions are answered by
    story_framework.py's own StoryManager/StoryInstance rather than
    needing yet another indirection layer.
    """
    story_manager: Any  # story_framework.StoryManager, kept as Any to avoid a circular import

    def get_player_level(self) -> int: ...
    def get_faction_reputation(self, faction: str) -> float: ...
    def is_npc_alive(self, npc_id: str) -> bool: ...
    def has_item(self, item_id: str) -> int:
        """Return how many of `item_id` the player currently holds."""
        ...
    def has_visited_area(self, area_id: str) -> bool: ...
    def get_elapsed_time(self) -> float:
        """Elapsed game time (seconds, turns -- whatever unit the host uses,
        as long as it's used consistently by TimePassedCondition callers)."""
        ...
    def has_world_scar(self, tag: str) -> bool:
        """Whether a WorldScar with this tag has been recorded (see
        story_failure_system.py) -- i.e. some story's failure has
        permanently altered the world in a way content tagged `tag`."""
        ...


# ---------------------------------------------------------------------------
# Condition (abstract base)
# ---------------------------------------------------------------------------

class Condition(ABC):
    """
    Base class for every condition. Subclasses implement `_evaluate` and
    `dependency_keys`; chaining (`&`, `|`, `~`) and caching integration
    are handled here so every condition gets them for free.
    """

    @abstractmethod
    def _evaluate(self, context: ConditionContext) -> bool:
        """Actual condition logic. Called by evaluate()/the evaluator --
        prefer going through those rather than calling this directly so
        caching is respected."""
        raise NotImplementedError

    def evaluate(self, context: ConditionContext) -> bool:
        """Evaluate uncached. For cached, indexed evaluation across many
        stories, use ConditionEvaluator.evaluate(condition, context) instead."""
        return self._evaluate(context)

    def dependency_keys(self) -> FrozenSet[str]:
        """
        State keys this condition's result depends on, for cache
        invalidation. An empty set means "no known dependency" -- the
        evaluator treats such conditions as always-dirty rather than
        risking a stale cached result.
        """
        return frozenset()

    # -- chaining -----------------------------------------------------------

    def __and__(self, other: "Condition") -> "AndCondition":
        return AndCondition([self, other])

    def __or__(self, other: "Condition") -> "OrCondition":
        return OrCondition([self, other])

    def __invert__(self) -> "NotCondition":
        return NotCondition(self)

    # -- data-driven construction -------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Override in subclasses that support serialization back to data."""
        raise NotImplementedError(f"{type(self).__name__} does not support to_dict().")


# ---------------------------------------------------------------------------
# Composite conditions
# ---------------------------------------------------------------------------

class AndCondition(Condition):
    """True only if every child condition is true. Short-circuits on the
    first False child."""

    def __init__(self, conditions: List[Condition]):
        self.conditions: List[Condition] = list(conditions)

    def _evaluate(self, context: ConditionContext) -> bool:
        return all(condition.evaluate(context) for condition in self.conditions)

    def dependency_keys(self) -> FrozenSet[str]:
        keys: set = set()
        for condition in self.conditions:
            keys |= condition.dependency_keys()
        return frozenset(keys)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "and", "conditions": [c.to_dict() for c in self.conditions]}

    def __repr__(self) -> str:
        return f"AndCondition({self.conditions!r})"


class OrCondition(Condition):
    """True if any child condition is true. Short-circuits on the first
    True child."""

    def __init__(self, conditions: List[Condition]):
        self.conditions: List[Condition] = list(conditions)

    def _evaluate(self, context: ConditionContext) -> bool:
        return any(condition.evaluate(context) for condition in self.conditions)

    def dependency_keys(self) -> FrozenSet[str]:
        keys: set = set()
        for condition in self.conditions:
            keys |= condition.dependency_keys()
        return frozenset(keys)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "or", "conditions": [c.to_dict() for c in self.conditions]}

    def __repr__(self) -> str:
        return f"OrCondition({self.conditions!r})"


class NotCondition(Condition):
    """Inverts a single child condition."""

    def __init__(self, condition: Condition):
        self.condition: Condition = condition

    def _evaluate(self, context: ConditionContext) -> bool:
        return not self.condition.evaluate(context)

    def dependency_keys(self) -> FrozenSet[str]:
        return self.condition.dependency_keys()

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "not", "condition": self.condition.to_dict()}

    def __repr__(self) -> str:
        return f"NotCondition({self.condition!r})"


# ---------------------------------------------------------------------------
# Registry for data-driven construction
# ---------------------------------------------------------------------------

_CONDITION_REGISTRY: Dict[str, type] = {}


def register_condition(type_name: str) -> Callable[[type], type]:
    """Class decorator registering a Condition subclass under `type_name`
    so it can be built from a dict via condition_from_dict()."""

    def decorator(cls: type) -> type:
        _CONDITION_REGISTRY[type_name] = cls
        return cls

    return decorator


def condition_from_dict(data: Dict[str, Any]) -> Condition:
    """
    Build a Condition tree from plain data, e.g.:

        {"type": "and", "conditions": [
            {"type": "has_item", "item_id": "sword", "count": 1},
            {"type": "npc_alive", "npc_id": "hermit"},
        ]}

    Composite types ("and", "or", "not") are handled here directly; leaf
    types are looked up in the registry and must implement `from_dict`.
    """
    type_name = data["type"]

    if type_name == "and":
        return AndCondition([condition_from_dict(c) for c in data["conditions"]])
    if type_name == "or":
        return OrCondition([condition_from_dict(c) for c in data["conditions"]])
    if type_name == "not":
        return NotCondition(condition_from_dict(data["condition"]))

    cls = _CONDITION_REGISTRY.get(type_name)
    if cls is None:
        raise ValueError(f"Unknown condition type: {type_name!r}")
    return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Leaf conditions
# ---------------------------------------------------------------------------

@register_condition("player_level")
class PlayerLevelCondition(Condition):
    """True if the player's level compares as specified against `level`."""

    def __init__(self, level: int, comparator: Comparator = Comparator.GTE):
        self.level = level
        self.comparator = comparator

    def _evaluate(self, context: ConditionContext) -> bool:
        return self.comparator.apply(context.get_player_level(), self.level)

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({"player_level"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "player_level", "level": self.level, "comparator": self.comparator.value}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerLevelCondition":
        return cls(level=data["level"], comparator=Comparator(data.get("comparator", "gte")))

    def __repr__(self) -> str:
        return f"PlayerLevelCondition({self.comparator.value} {self.level})"


@register_condition("faction_reputation")
class FactionReputationCondition(Condition):
    """True if reputation with `faction` compares as specified against `value`."""

    def __init__(self, faction: str, value: float, comparator: Comparator = Comparator.GTE):
        self.faction = faction
        self.value = value
        self.comparator = comparator

    def _evaluate(self, context: ConditionContext) -> bool:
        return self.comparator.apply(context.get_faction_reputation(self.faction), self.value)

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"faction_reputation:{self.faction}"})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "faction_reputation",
            "faction": self.faction,
            "value": self.value,
            "comparator": self.comparator.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FactionReputationCondition":
        return cls(
            faction=data["faction"],
            value=data["value"],
            comparator=Comparator(data.get("comparator", "gte")),
        )

    def __repr__(self) -> str:
        return f"FactionReputationCondition({self.faction} {self.comparator.value} {self.value})"


@register_condition("quest_flag")
class QuestFlagCondition(Condition):
    """True if `story_id`'s flag `flag_name` equals `expected` (defaults
    to truthiness-style equality against True)."""

    def __init__(self, story_id: str, flag_name: str, expected: Any = True):
        self.story_id = story_id
        self.flag_name = flag_name
        self.expected = expected

    def _evaluate(self, context: ConditionContext) -> bool:
        story = context.story_manager.get_story(self.story_id)
        if story is None:
            return False
        return story.get_flag(self.flag_name) == self.expected

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"flag:{self.story_id}:{self.flag_name}"})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "quest_flag",
            "story_id": self.story_id,
            "flag_name": self.flag_name,
            "expected": self.expected,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuestFlagCondition":
        return cls(story_id=data["story_id"], flag_name=data["flag_name"], expected=data.get("expected", True))

    def __repr__(self) -> str:
        return f"QuestFlagCondition({self.story_id}.{self.flag_name} == {self.expected!r})"


@register_condition("npc_alive")
class NPCAliveCondition(Condition):
    """True if the given NPC is currently alive."""

    def __init__(self, npc_id: str):
        self.npc_id = npc_id

    def _evaluate(self, context: ConditionContext) -> bool:
        return context.is_npc_alive(self.npc_id)

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"npc_alive:{self.npc_id}"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "npc_alive", "npc_id": self.npc_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NPCAliveCondition":
        return cls(npc_id=data["npc_id"])

    def __repr__(self) -> str:
        return f"NPCAliveCondition({self.npc_id})"


@register_condition("npc_dead")
class NPCDeadCondition(Condition):
    """True if the given NPC is currently dead. Kept as its own condition
    (rather than always requiring `~NPCAlive(...)`) so data-driven rules
    can express it directly without composite syntax."""

    def __init__(self, npc_id: str):
        self.npc_id = npc_id

    def _evaluate(self, context: ConditionContext) -> bool:
        return not context.is_npc_alive(self.npc_id)

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"npc_alive:{self.npc_id}"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "npc_dead", "npc_id": self.npc_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NPCDeadCondition":
        return cls(npc_id=data["npc_id"])

    def __repr__(self) -> str:
        return f"NPCDeadCondition({self.npc_id})"


@register_condition("has_item")
class HasItemCondition(Condition):
    """True if the player holds at least `count` of `item_id`."""

    def __init__(self, item_id: str, count: int = 1):
        self.item_id = item_id
        self.count = count

    def _evaluate(self, context: ConditionContext) -> bool:
        return context.has_item(self.item_id) >= self.count

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"item:{self.item_id}"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "has_item", "item_id": self.item_id, "count": self.count}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HasItemCondition":
        return cls(item_id=data["item_id"], count=data.get("count", 1))

    def __repr__(self) -> str:
        return f"HasItemCondition({self.item_id} x{self.count})"


@register_condition("visited_area")
class VisitedAreaCondition(Condition):
    """True if the player has visited/discovered the given area."""

    def __init__(self, area_id: str):
        self.area_id = area_id

    def _evaluate(self, context: ConditionContext) -> bool:
        return context.has_visited_area(self.area_id)

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"visited_area:{self.area_id}"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "visited_area", "area_id": self.area_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisitedAreaCondition":
        return cls(area_id=data["area_id"])

    def __repr__(self) -> str:
        return f"VisitedAreaCondition({self.area_id})"


@register_condition("time_passed")
class TimePassedCondition(Condition):
    """
    True once at least `duration` game-time units have elapsed since
    `since`. `since` is an absolute timestamp in the same unit as
    context.get_elapsed_time() (e.g. captured via that same method when
    the relevant clock started).

    Deliberately declares no dependency_keys(): elapsed time changes
    continuously rather than on a discrete event, so it is always
    re-evaluated rather than cached (see ConditionEvaluator).
    """

    def __init__(self, duration: float, since: float = 0.0):
        self.duration = duration
        self.since = since

    def _evaluate(self, context: ConditionContext) -> bool:
        return (context.get_elapsed_time() - self.since) >= self.duration

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "time_passed", "duration": self.duration, "since": self.since}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimePassedCondition":
        return cls(duration=data["duration"], since=data.get("since", 0.0))

    def __repr__(self) -> str:
        return f"TimePassedCondition({self.duration} since {self.since})"


@register_condition("story_completed")
class StoryCompletedCondition(Condition):
    """True if the given story has reached the COMPLETED state."""

    def __init__(self, story_id: str):
        self.story_id = story_id

    def _evaluate(self, context: ConditionContext) -> bool:
        story = context.story_manager.get_story(self.story_id)
        if story is None:
            return False
        return story.state.value == "completed"

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"story_state:{self.story_id}"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "story_completed", "story_id": self.story_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryCompletedCondition":
        return cls(story_id=data["story_id"])

    def __repr__(self) -> str:
        return f"StoryCompletedCondition({self.story_id})"


@register_condition("story_failed")
class StoryFailedCondition(Condition):
    """True if the given story has reached the FAILED state."""

    def __init__(self, story_id: str):
        self.story_id = story_id

    def _evaluate(self, context: ConditionContext) -> bool:
        story = context.story_manager.get_story(self.story_id)
        if story is None:
            return False
        return story.state.value == "failed"

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"story_state:{self.story_id}"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "story_failed", "story_id": self.story_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryFailedCondition":
        return cls(story_id=data["story_id"])

    def __repr__(self) -> str:
        return f"StoryFailedCondition({self.story_id})"


@register_condition("world_scar")
class WorldScarCondition(Condition):
    """
    True if a WorldScar tagged `tag` has been recorded (see
    story_failure_system.py) -- i.e. some story's failure permanently
    altered the world in a way content tagged that string (e.g.
    "village_burned:northfield"). This is the general-purpose way
    *any* story, ActivationRequirement, or ChainEdge gates on world
    state that persists independently of any single story's own flags,
    not just stories chained directly to the one that failed.
    """

    def __init__(self, tag: str):
        self.tag = tag

    def _evaluate(self, context: ConditionContext) -> bool:
        return context.has_world_scar(self.tag)

    def dependency_keys(self) -> FrozenSet[str]:
        return frozenset({f"world_scar:{self.tag}"})

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "world_scar", "tag": self.tag}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldScarCondition":
        return cls(tag=data["tag"])

    def __repr__(self) -> str:
        return f"WorldScarCondition({self.tag})"


# ---------------------------------------------------------------------------
# ConditionEvaluator
# ---------------------------------------------------------------------------

class ConditionEvaluator:
    """
    Caches condition results and only recomputes them when something
    they depend on has actually changed -- the piece that makes this
    pipeline scale to many simultaneously active stories.

    Each condition is cached independently by its identity (`id(condition)`),
    so sharing a single condition instance across many rules/stories (e.g.
    a common PlayerLevelCondition gating several unrelated stories) means
    it is evaluated once and reused everywhere, until something relevant
    changes.
    """

    def __init__(self):
        self._cache: Dict[int, bool] = {}
        # Conditions that declared no dependency_keys() -- always re-evaluated,
        # since there's no safe key to invalidate them on.
        self._always_dirty: Dict[int, Condition] = {}
        # dependency_key -> set of condition ids that depend on it, so a
        # single invalidate() call only drops the conditions that actually
        # care, not the whole cache.
        self._index: Dict[str, set] = {}
        self._conditions: Dict[int, Condition] = {}

    def _register(self, condition: Condition) -> None:
        condition_id = id(condition)
        if condition_id in self._conditions:
            return
        self._conditions[condition_id] = condition

        keys = condition.dependency_keys()
        if not keys:
            self._always_dirty[condition_id] = condition
            return
        for key in keys:
            self._index.setdefault(key, set()).add(condition_id)

    def evaluate(self, condition: Condition, context: ConditionContext) -> bool:
        """Evaluate `condition`, using the cache when possible."""
        condition_id = id(condition)
        self._register(condition)

        if condition_id in self._always_dirty:
            return condition.evaluate(context)

        if condition_id in self._cache:
            return self._cache[condition_id]

        result = condition.evaluate(context)
        self._cache[condition_id] = result
        return result

    def invalidate(self, dependency_key: str) -> None:
        """Drop cached results for every condition that depends on
        `dependency_key`. Call this whenever the underlying state changes
        (an NPC dies, an item is picked up, a flag is set, ...)."""
        for condition_id in self._index.get(dependency_key, ()):
            self._cache.pop(condition_id, None)

    def invalidate_all(self) -> None:
        """Blunt fallback: drop every cached result. Prefer targeted
        invalidate() calls; this exists as a safety net."""
        self._cache.clear()

    def __repr__(self) -> str:
        return f"ConditionEvaluator(tracked={len(self._conditions)}, cached={len(self._cache)})"