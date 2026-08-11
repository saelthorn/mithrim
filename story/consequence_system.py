"""
consequence_system.py

Phase 8 -- Consequence System.

Provides a reusable framework for executing the *effects* of story and
gameplay events (reward XP/gold, spawn an NPC or merchant, destroy a
landmark, unlock a story or region, modify reputation, give an item,
change the weather, ...) safely, reversibly where appropriate,
serializably, and chainably.

This is framework only. Every Consequence is parameterized by plain data
(ids, amounts, types) -- none of them know *why* they're being executed
or what story they belong to. "Avoid story-specific implementations"
means exactly that: RewardXPConsequence has no idea if it's a quest
reward or a random event; it just asks an ExecutionContext to grant XP.

Design summary
---------------
- ExecutionContext : the mutating counterpart to condition_system.py's
                      ConditionContext -- a narrow interface the host
                      game implements once, giving consequences a place
                      to actually apply effects (grant XP, spawn an
                      entity, change weather, ...) without knowing any
                      concrete game classes.
- Consequence      : abstract base implementing the "execute safely"
                      guarantee as a template method: subclasses only
                      implement `_apply`/`_undo`; `execute()`/`undo()`
                      always catch exceptions and report a
                      ConsequenceResult rather than raising into caller
                      code (a bad consequence should never crash a
                      trigger response).
- Concrete types   : RewardXP, RewardGold, SpawnNPC, SpawnMerchant,
                      DestroyLandmark, UnlockStory, ModifyReputation,
                      GiveItem, RemoveItem, ChangeWeather, UnlockRegion.
- ConsequenceChain : a composite Consequence (so chains nest) that runs
                      its children in order and, on any failure, rolls
                      back every already-applied, reversible child in
                      reverse order -- all-or-nothing by default.
- ConsequenceExecutor : convenience runner that executes a single
                      Consequence or a chain against a context and keeps
                      a history of applied consequences for later,
                      independent undo (e.g. "undo the last 3 things that
                      happened").
- Registry         : `@register_consequence("type_name")` +
                      `consequence_from_dict` mirror condition_system.py's
                      data-driven construction.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable


# ---------------------------------------------------------------------------
# ExecutionContext
# ---------------------------------------------------------------------------

@runtime_checkable
class ExecutionContext(Protocol):
    """
    Everything a Consequence might need to mutate, as a narrow interface
    the host game implements once. Consequences depend only on this
    protocol, never on concrete game classes.

    Methods that create or change state return whatever is needed to
    undo that specific change (a spawned id, a previous value, a
    snapshot) -- Consequence subclasses store that as their undo_data
    rather than re-deriving it later.
    """
    story_manager: Any  # story_framework.StoryManager, kept as Any to avoid a circular import

    def reward_xp(self, amount: int) -> None: ...
    def reward_gold(self, amount: int) -> None: ...
    def spawn_npc(self, npc_type: str, position: Tuple[float, float], data: Optional[Dict[str, Any]] = None) -> str:
        """Spawn an NPC, returning its new entity id."""
        ...
    def spawn_merchant(self, merchant_type: str, position: Tuple[float, float], inventory: Optional[List[str]] = None) -> str:
        """Spawn a merchant, returning its new entity id."""
        ...
    def despawn_entity(self, entity_id: str) -> None:
        """Remove a previously spawned NPC/merchant."""
        ...
    def destroy_landmark(self, landmark_id: str) -> Dict[str, Any]:
        """Destroy a landmark, returning a snapshot sufficient to restore it."""
        ...
    def restore_landmark(self, landmark_id: str, snapshot: Dict[str, Any]) -> None: ...
    def modify_reputation(self, faction: str, delta: float) -> None: ...
    def give_item(self, item_id: str, count: int) -> None: ...
    def remove_item(self, item_id: str, count: int) -> None: ...
    def change_weather(self, weather_type: str) -> str:
        """Change the weather, returning the previous weather type."""
        ...
    def unlock_region(self, region_id: str) -> None: ...
    def lock_region(self, region_id: str) -> None: ...


# ---------------------------------------------------------------------------
# ConsequenceResult
# ---------------------------------------------------------------------------

class ConsequenceResult:
    """Outcome of executing (or undoing) a single Consequence."""

    def __init__(
        self,
        consequence: "Consequence",
        success: bool,
        undo_data: Any = None,
        error: Optional[str] = None,
    ):
        self.consequence = consequence
        self.success = success
        self.undo_data = undo_data
        self.error = error
        self.timestamp: float = time.time()

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        status = "ok" if self.success else f"failed ({self.error})"
        return f"ConsequenceResult({type(self.consequence).__name__}: {status})"


# ---------------------------------------------------------------------------
# Consequence (abstract base)
# ---------------------------------------------------------------------------

class Consequence(ABC):
    """
    Base class for every consequence.

    `execute()` and `undo()` are template methods: subclasses only
    implement `_apply`/`_undo`, and never need to write their own
    try/except -- every consequence executes and reverses safely by
    construction, not by discipline.
    """

    #: Set True by subclasses that implement a meaningful `_undo`.
    is_reversible: bool = False

    def __init__(self, consequence_id: Optional[str] = None):
        self.id: str = consequence_id or str(uuid.uuid4())

    # -- subclass hooks -------------------------------------------------------

    @abstractmethod
    def _apply(self, context: ExecutionContext) -> Any:
        """Apply the effect. Return whatever `_undo` will need later.
        May raise -- execute() catches it."""
        raise NotImplementedError

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        """Reverse the effect using the undo_data returned by `_apply`.
        Only called on consequences with is_reversible = True. May raise
        -- undo() catches it."""
        raise NotImplementedError(f"{type(self).__name__} is not reversible.")

    # -- safe execution ---------------------------------------------------------

    def execute(self, context: ExecutionContext) -> ConsequenceResult:
        """Apply this consequence. Never raises -- failures come back as
        a ConsequenceResult with success=False instead."""
        try:
            undo_data = self._apply(context)
            return ConsequenceResult(self, success=True, undo_data=undo_data)
        except Exception as exc:  # noqa: BLE001 -- consequences must never crash the caller
            return ConsequenceResult(self, success=False, error=str(exc))

    def undo(self, context: ExecutionContext, undo_data: Any) -> ConsequenceResult:
        """Reverse a previously successful execution. Never raises."""
        if not self.is_reversible:
            return ConsequenceResult(self, success=False, error="not reversible")
        try:
            self._undo(context, undo_data)
            return ConsequenceResult(self, success=True)
        except Exception as exc:  # noqa: BLE001
            return ConsequenceResult(self, success=False, error=str(exc))

    # -- chaining -----------------------------------------------------------

    def __add__(self, other: "Consequence") -> "ConsequenceChain":
        return ConsequenceChain([self, other])

    # -- serialization ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Override in subclasses that support serialization back to data."""
        raise NotImplementedError(f"{type(self).__name__} does not support to_dict().")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r})"


# ---------------------------------------------------------------------------
# ConsequenceChain (composite)
# ---------------------------------------------------------------------------

class ConsequenceChain(Consequence):
    """
    Runs child consequences in order. By default this is atomic: if any
    child fails, every already-applied, reversible child is rolled back
    in reverse order and the whole chain reports failure. Set
    `atomic=False` for best-effort execution (run everything regardless
    of individual failures).

    Chains nest -- a ConsequenceChain is itself a Consequence, so
    `chain_a + chain_b` or passing a chain as one element of another
    chain both work.
    """

    is_reversible = True

    def __init__(self, consequences: List[Consequence], atomic: bool = True, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.consequences: List[Consequence] = list(consequences)
        self.atomic = atomic

    def __add__(self, other: "Consequence") -> "ConsequenceChain":
        return ConsequenceChain(self.consequences + [other], atomic=self.atomic)

    def _apply(self, context: ExecutionContext) -> List[Tuple[Consequence, Any]]:
        applied: List[Tuple[Consequence, Any]] = []

        for consequence in self.consequences:
            result = consequence.execute(context)

            if result.success:
                applied.append((consequence, result.undo_data))
                continue

            if self.atomic:
                # Roll back everything applied so far, in reverse order,
                # then surface the original failure.
                for done_consequence, undo_data in reversed(applied):
                    if done_consequence.is_reversible:
                        done_consequence.undo(context, undo_data)
                raise RuntimeError(
                    f"Chain aborted at {type(consequence).__name__}: {result.error}"
                )
            # Non-atomic: log nothing here (framework stays content-agnostic),
            # just continue with the remaining consequences.

        return applied

    def _undo(self, context: ExecutionContext, undo_data: List[Tuple[Consequence, Any]]) -> None:
        for consequence, child_undo_data in reversed(undo_data):
            if consequence.is_reversible:
                consequence.undo(context, child_undo_data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "chain",
            "id": self.id,
            "atomic": self.atomic,
            "consequences": [c.to_dict() for c in self.consequences],
        }

    def __repr__(self) -> str:
        return f"ConsequenceChain({self.consequences!r}, atomic={self.atomic})"


# ---------------------------------------------------------------------------
# Registry for data-driven construction
# ---------------------------------------------------------------------------

_CONSEQUENCE_REGISTRY: Dict[str, type] = {}


def register_consequence(type_name: str) -> Callable[[type], type]:
    """Class decorator registering a Consequence subclass under
    `type_name` so it can be built from a dict via consequence_from_dict()."""

    def decorator(cls: type) -> type:
        _CONSEQUENCE_REGISTRY[type_name] = cls
        return cls

    return decorator


def consequence_from_dict(data: Dict[str, Any]) -> Consequence:
    """Build a Consequence (or ConsequenceChain) from plain data, mirroring
    condition_system.py's condition_from_dict()."""
    type_name = data["type"]

    if type_name == "chain":
        return ConsequenceChain(
            [consequence_from_dict(c) for c in data["consequences"]],
            atomic=data.get("atomic", True),
            consequence_id=data.get("id"),
        )

    cls = _CONSEQUENCE_REGISTRY.get(type_name)
    if cls is None:
        raise ValueError(f"Unknown consequence type: {type_name!r}")
    return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Concrete consequences
# ---------------------------------------------------------------------------

@register_consequence("reward_xp")
class RewardXPConsequence(Consequence):
    """Grants (or, on undo, revokes) a fixed amount of XP."""

    is_reversible = True

    def __init__(self, amount: int, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.amount = amount

    def _apply(self, context: ExecutionContext) -> None:
        context.reward_xp(self.amount)

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        context.reward_xp(-self.amount)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "reward_xp", "id": self.id, "amount": self.amount}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RewardXPConsequence":
        return cls(amount=data["amount"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"RewardXPConsequence({self.amount})"


@register_consequence("reward_gold")
class RewardGoldConsequence(Consequence):
    """Grants (or, on undo, revokes) a fixed amount of gold."""

    is_reversible = True

    def __init__(self, amount: int, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.amount = amount

    def _apply(self, context: ExecutionContext) -> None:
        context.reward_gold(self.amount)

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        context.reward_gold(-self.amount)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "reward_gold", "id": self.id, "amount": self.amount}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RewardGoldConsequence":
        return cls(amount=data["amount"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"RewardGoldConsequence({self.amount})"


@register_consequence("spawn_npc")
class SpawnNPCConsequence(Consequence):
    """Spawns an NPC; undo despawns the exact entity that was created."""

    is_reversible = True

    def __init__(
        self,
        npc_type: str,
        position: Tuple[float, float],
        data: Optional[Dict[str, Any]] = None,
        consequence_id: Optional[str] = None,
    ):
        super().__init__(consequence_id)
        self.npc_type = npc_type
        self.position = position
        self.data = data or {}

    def _apply(self, context: ExecutionContext) -> str:
        return context.spawn_npc(self.npc_type, self.position, self.data)

    def _undo(self, context: ExecutionContext, undo_data: str) -> None:
        context.despawn_entity(undo_data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "spawn_npc",
            "id": self.id,
            "npc_type": self.npc_type,
            "position": list(self.position),
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpawnNPCConsequence":
        pos = data.get("position", [0, 0])
        return cls(
            npc_type=data["npc_type"],
            position=(pos[0], pos[1]),
            data=dict(data.get("data", {})),
            consequence_id=data.get("id"),
        )

    def __repr__(self) -> str:
        return f"SpawnNPCConsequence({self.npc_type} @ {self.position})"


@register_consequence("spawn_merchant")
class SpawnMerchantConsequence(Consequence):
    """Spawns a merchant; undo despawns the exact entity that was created."""

    is_reversible = True

    def __init__(
        self,
        merchant_type: str,
        position: Tuple[float, float],
        inventory: Optional[List[str]] = None,
        consequence_id: Optional[str] = None,
    ):
        super().__init__(consequence_id)
        self.merchant_type = merchant_type
        self.position = position
        self.inventory = inventory or []

    def _apply(self, context: ExecutionContext) -> str:
        return context.spawn_merchant(self.merchant_type, self.position, self.inventory)

    def _undo(self, context: ExecutionContext, undo_data: str) -> None:
        context.despawn_entity(undo_data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "spawn_merchant",
            "id": self.id,
            "merchant_type": self.merchant_type,
            "position": list(self.position),
            "inventory": list(self.inventory),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpawnMerchantConsequence":
        pos = data.get("position", [0, 0])
        return cls(
            merchant_type=data["merchant_type"],
            position=(pos[0], pos[1]),
            inventory=list(data.get("inventory", [])),
            consequence_id=data.get("id"),
        )

    def __repr__(self) -> str:
        return f"SpawnMerchantConsequence({self.merchant_type} @ {self.position})"


@register_consequence("destroy_landmark")
class DestroyLandmarkConsequence(Consequence):
    """Destroys a landmark; undo restores it from the snapshot the host
    returned at destruction time."""

    is_reversible = True

    def __init__(self, landmark_id: str, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.landmark_id = landmark_id

    def _apply(self, context: ExecutionContext) -> Dict[str, Any]:
        return context.destroy_landmark(self.landmark_id)

    def _undo(self, context: ExecutionContext, undo_data: Dict[str, Any]) -> None:
        context.restore_landmark(self.landmark_id, undo_data)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "destroy_landmark", "id": self.id, "landmark_id": self.landmark_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DestroyLandmarkConsequence":
        return cls(landmark_id=data["landmark_id"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"DestroyLandmarkConsequence({self.landmark_id})"


@register_consequence("unlock_story")
class UnlockStoryConsequence(Consequence):
    """
    Starts a previously uninitialized/paused story via its StoryDirector.
    Framework-generic despite the name: it knows nothing about what the
    target story contains, only its id.
    """

    is_reversible = True

    def __init__(self, story_id: str, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.story_id = story_id

    def _apply(self, context: ExecutionContext) -> bool:
        director = context.story_manager.get_director(self.story_id)
        if director is None:
            raise RuntimeError(f"No loaded story director for {self.story_id!r}")
        was_active_before = director.is_active()
        if not was_active_before:
            director.start()
        return was_active_before

    def _undo(self, context: ExecutionContext, undo_data: bool) -> None:
        was_active_before = undo_data
        if not was_active_before:
            director = context.story_manager.get_director(self.story_id)
            if director is not None:
                director.pause()

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "unlock_story", "id": self.id, "story_id": self.story_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnlockStoryConsequence":
        return cls(story_id=data["story_id"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"UnlockStoryConsequence({self.story_id})"


@register_consequence("modify_reputation")
class ModifyReputationConsequence(Consequence):
    """Applies (or, on undo, reverses) a reputation delta with a faction."""

    is_reversible = True

    def __init__(self, faction: str, delta: float, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.faction = faction
        self.delta = delta

    def _apply(self, context: ExecutionContext) -> None:
        context.modify_reputation(self.faction, self.delta)

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        context.modify_reputation(self.faction, -self.delta)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "modify_reputation", "id": self.id, "faction": self.faction, "delta": self.delta}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModifyReputationConsequence":
        return cls(faction=data["faction"], delta=data["delta"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"ModifyReputationConsequence({self.faction} {self.delta:+})"


@register_consequence("give_item")
class GiveItemConsequence(Consequence):
    """Gives (or, on undo, removes) a fixed count of an item."""

    is_reversible = True

    def __init__(self, item_id: str, count: int = 1, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.item_id = item_id
        self.count = count

    def _apply(self, context: ExecutionContext) -> None:
        context.give_item(self.item_id, self.count)

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        context.remove_item(self.item_id, self.count)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "give_item", "id": self.id, "item_id": self.item_id, "count": self.count}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GiveItemConsequence":
        return cls(item_id=data["item_id"], count=data.get("count", 1), consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"GiveItemConsequence({self.item_id} x{self.count})"


@register_consequence("remove_item")
class RemoveItemConsequence(Consequence):
    """
    Removes a fixed count of an item (or, on undo, gives it back) -- the
    inverse of GiveItemConsequence, for content that spends an item as a
    cost rather than awards one (e.g. a choice that consumes a torch, or
    hands over rations as a kindness). ExecutionContext.remove_item()
    already existed as GiveItemConsequence's own undo path; this is that
    same effect exposed as a first-class forward consequence, so content
    JSON can declare {"type": "remove_item", ...} directly instead of
    only ever reaching it indirectly through undoing a give_item.
    """

    is_reversible = True

    def __init__(self, item_id: str, count: int = 1, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.item_id = item_id
        self.count = count

    def _apply(self, context: ExecutionContext) -> None:
        context.remove_item(self.item_id, self.count)

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        context.give_item(self.item_id, self.count)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "remove_item", "id": self.id, "item_id": self.item_id, "count": self.count}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RemoveItemConsequence":
        return cls(item_id=data["item_id"], count=data.get("count", 1), consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"RemoveItemConsequence({self.item_id} x{self.count})"


@register_consequence("change_weather")
class ChangeWeatherConsequence(Consequence):
    """Changes the weather; undo restores whatever weather preceded it."""

    is_reversible = True

    def __init__(self, weather_type: str, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.weather_type = weather_type

    def _apply(self, context: ExecutionContext) -> str:
        return context.change_weather(self.weather_type)

    def _undo(self, context: ExecutionContext, undo_data: str) -> None:
        context.change_weather(undo_data)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "change_weather", "id": self.id, "weather_type": self.weather_type}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeWeatherConsequence":
        return cls(weather_type=data["weather_type"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"ChangeWeatherConsequence({self.weather_type})"


@register_consequence("unlock_region")
class UnlockRegionConsequence(Consequence):
    """Unlocks a region; undo re-locks it."""

    is_reversible = True

    def __init__(self, region_id: str, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.region_id = region_id

    def _apply(self, context: ExecutionContext) -> None:
        context.unlock_region(self.region_id)

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        context.lock_region(self.region_id)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "unlock_region", "id": self.id, "region_id": self.region_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnlockRegionConsequence":
        return cls(region_id=data["region_id"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"UnlockRegionConsequence({self.region_id})"


@register_consequence("despawn_entity")
class DespawnEntityConsequence(Consequence):
    """
    Despawns a previously-spawned entity by id -- an NPC/merchant spawned
    via SpawnNPCConsequence/SpawnMerchantConsequence, or any other entity
    the host's ExecutionContext knows about (see game.py's npc_registry).
    Not reversible on its own: undoing a despawn would require re-spawning
    with the exact original type/position/data, which this consequence is
    never given. Pair it with that entity's own spawn Consequence in a
    ConsequenceChain if round-trip undo is needed.
    """

    def __init__(self, entity_id: str, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.entity_id = entity_id

    def _apply(self, context: ExecutionContext) -> None:
        context.despawn_entity(self.entity_id)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "despawn_entity", "id": self.id, "entity_id": self.entity_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DespawnEntityConsequence":
        return cls(entity_id=data["entity_id"], consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"DespawnEntityConsequence({self.entity_id})"


@register_consequence("set_flag")
class SetFlagConsequence(Consequence):
    """
    Sets a story flag through its StoryDirector -- e.g. a dialogue
    choice's `consequences` recording which branch the player picked
    (Hollow_Shrine.json's "chose_destroy"/"chose_spare"), for a later
    TriggerRule.required_flags or Condition to key off. Reaches through
    `context.story_manager` the same way UnlockStoryConsequence does,
    since flag state lives on the StoryInstance/StoryDirector, not on
    the host's own ExecutionContext.
    """

    is_reversible = True

    def __init__(self, story_id: str, key: str, value: Any = True, consequence_id: Optional[str] = None):
        super().__init__(consequence_id)
        self.story_id = story_id
        self.key = key
        self.value = value

    def _apply(self, context: ExecutionContext) -> Any:
        director = context.story_manager.get_director(self.story_id)
        if director is None:
            raise RuntimeError(f"No loaded story director for {self.story_id!r}")
        previous = director.story.get_flag(self.key)
        director.set_flag(self.key, self.value)
        return previous

    def _undo(self, context: ExecutionContext, undo_data: Any) -> None:
        director = context.story_manager.get_director(self.story_id)
        if director is not None:
            director.set_flag(self.key, undo_data)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "set_flag", "id": self.id, "story_id": self.story_id, "key": self.key, "value": self.value}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SetFlagConsequence":
        return cls(story_id=data["story_id"], key=data["key"], value=data.get("value", True), consequence_id=data.get("id"))

    def __repr__(self) -> str:
        return f"SetFlagConsequence({self.story_id}.{self.key} = {self.value!r})"


# ---------------------------------------------------------------------------
# ConsequenceExecutor
# ---------------------------------------------------------------------------

class ConsequenceExecutor:
    """
    Convenience runner: executes a Consequence (or ConsequenceChain)
    against a context and keeps a bounded history of applied
    consequences with their undo_data, so the host can undo the most
    recent N effects without having to track undo_data itself.
    """

    def __init__(self, history_limit: int = 200):
        self._history: List[Tuple[Consequence, Any]] = []
        self.history_limit = history_limit

    def execute(self, consequence: Consequence, context: ExecutionContext) -> ConsequenceResult:
        result = consequence.execute(context)
        if result.success and consequence.is_reversible:
            self._history.append((consequence, result.undo_data))
            if len(self._history) > self.history_limit:
                self._history.pop(0)
        return result

    def undo_last(self, context: ExecutionContext) -> Optional[ConsequenceResult]:
        """Undo the most recently applied, still-tracked consequence."""
        if not self._history:
            return None
        consequence, undo_data = self._history.pop()
        return consequence.undo(context, undo_data)

    def history(self) -> List[Consequence]:
        return [consequence for consequence, _ in self._history]

    def __repr__(self) -> str:
        return f"ConsequenceExecutor(history={len(self._history)}/{self.history_limit})"