"""
trigger_system.py

Phase 6 -- Trigger System.

Provides a centralized, generic dispatcher for gameplay events (the
player inspecting something, talking to an NPC, entering an area, time
passing, ...) plus a data-driven way for stories to declare which
triggers they care about, without hardcoding response logic per story.

This is framework only. It contains no story content -- it does not know
what "inspecting the wagon" means narratively, only that an InspectObject
trigger fired with that wagon as its target, and that some story declared
it cares about InspectObject events matching certain conditions.

Design summary
---------------
- TriggerType   : the vocabulary of gameplay events (InspectObject,
                  TalkNPC, KillNPC, EnterArea, LeaveArea, LootObject,
                  Wait, Sleep, TimePassed, ReadJournal, ...). Adding a new
                  trigger type never requires touching existing stories.
- TriggerEvent  : the payload passed around when a trigger fires --
                  type, target, instigator, location, freeform data.
- TriggerSystem : centralized fire/subscribe dispatcher. Gameplay code
                  only ever calls `TriggerSystem.fire(...)`; it has no
                  idea which stories, if any, are listening.
- TriggerRule   : a story's data-driven declaration of "when trigger X
                  happens, and these conditions hold, respond". Rules are
                  attached to a StoryInstance (see story_framework.py's
                  `add_trigger_rule`) and evaluated by StoryManager.

Relationship to the rest of the framework:
- Gameplay code -> TriggerSystem.fire(...) -> TriggerEvent
- StoryManager subscribes to TriggerSystem (via its own trigger_system,
  created by default) and, on each event, checks every active story's
  TriggerRules for a match.
- A matching rule's default response is StoryDirector.advance(); a rule
  may instead supply its own `effect` callback for custom, content-layer
  behavior (unlocking a specific flag, starting a follow-up event, etc.)
  -- the trigger system itself never decides what that behavior is.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from story.story_framework import StoryInstance, StoryDirector
    from story.condition_system import Condition
    from story.consequence_system import Consequence


# ---------------------------------------------------------------------------
# TriggerType
# ---------------------------------------------------------------------------

class TriggerType(Enum):
    """
    The vocabulary of gameplay events stories can react to. This list is
    illustrative, not exhaustive -- add new members here as new gameplay
    events are introduced; existing TriggerRules on existing stories are
    unaffected by additions.
    """
    INSPECT_OBJECT = "inspect_object"
    TALK_NPC = "talk_npc"
    KILL_NPC = "kill_npc"
    ENTER_AREA = "enter_area"
    LEAVE_AREA = "leave_area"
    LOOT_OBJECT = "loot_object"
    WAIT = "wait"
    SLEEP = "sleep"
    TIME_PASSED = "time_passed"
    READ_JOURNAL = "read_journal"

    # World-time driven events (see world_time.py). Fired by ScheduledEvents
    # in addition to the generic TIME_PASSED trigger, so content systems can
    # subscribe to the specific thing that happened rather than filtering
    # TIME_PASSED data themselves.
    NPC_WENT_MISSING = "npc_went_missing"
    CORPSE_DECAYED = "corpse_decayed"
    CAMP_ABANDONED = "camp_abandoned"
    BANDITS_RELOCATED = "bandits_relocated"
    BUILDING_BURNED = "building_burned"
    CROP_GROWTH_STAGE = "crop_growth_stage"


# ---------------------------------------------------------------------------
# TriggerEvent
# ---------------------------------------------------------------------------

class TriggerEvent:
    """
    A single fired gameplay event.

    `target`, `instigator`, and `location` are intentionally untyped from
    the framework's point of view -- they might be a StoryObject, a
    player entity, a SearchArea id, or None, depending on the trigger
    type. `data` carries anything else relevant (e.g. how many turns were
    waited, which journal page was read).
    """

    def __init__(
        self,
        trigger_type: TriggerType,
        target: Any = None,
        instigator: Any = None,
        location: Any = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.type: TriggerType = trigger_type
        self.target: Any = target
        self.instigator: Any = instigator
        self.location: Any = location
        self.data: Dict[str, Any] = data if data is not None else {}
        self.timestamp: float = time.time()

    def __repr__(self) -> str:
        return (
            f"TriggerEvent(type={self.type.value}, target={self.target!r}, "
            f"instigator={self.instigator!r}, location={self.location!r})"
        )


# ---------------------------------------------------------------------------
# TriggerSystem
# ---------------------------------------------------------------------------

class TriggerSystem:
    """
    Centralized dispatcher for gameplay events.

    Gameplay code only ever calls `fire()`. It has no knowledge of who is
    listening -- StoryManager is the primary listener, but any number of
    other systems (achievements, analytics, ambient reactions) can
    subscribe independently without stories or gameplay code changing.
    """

    def __init__(self):
        self._listeners: Dict[TriggerType, List[Callable[[TriggerEvent], None]]] = {
            trigger_type: [] for trigger_type in TriggerType
        }
        self._global_listeners: List[Callable[[TriggerEvent], None]] = []

    # -- subscription -------------------------------------------------------

    def subscribe(self, trigger_type: TriggerType, callback: Callable[[TriggerEvent], None]) -> None:
        """Listen for a single trigger type."""
        self._listeners[trigger_type].append(callback)

    def subscribe_all(self, callback: Callable[[TriggerEvent], None]) -> None:
        """Listen for every trigger type, regardless of TriggerType additions."""
        self._global_listeners.append(callback)

    def unsubscribe(self, trigger_type: TriggerType, callback: Callable[[TriggerEvent], None]) -> None:
        if callback in self._listeners[trigger_type]:
            self._listeners[trigger_type].remove(callback)

    def unsubscribe_all(self, callback: Callable[[TriggerEvent], None]) -> None:
        if callback in self._global_listeners:
            self._global_listeners.remove(callback)

    # -- firing ---------------------------------------------------------------

    def fire(
        self,
        trigger_type: TriggerType,
        target: Any = None,
        instigator: Any = None,
        location: Any = None,
        **data: Any,
    ) -> TriggerEvent:
        """
        Fire a trigger event. Builds the TriggerEvent, notifies every
        listener subscribed to this trigger type plus every global
        listener, and returns the event (useful for tests/logging).
        """
        event = TriggerEvent(
            trigger_type=trigger_type,
            target=target,
            instigator=instigator,
            location=location,
            data=data,
        )

        for callback in self._listeners[trigger_type]:
            callback(event)
        for callback in self._global_listeners:
            callback(event)

        return event

    def __repr__(self) -> str:
        subscriber_count = sum(len(cbs) for cbs in self._listeners.values())
        subscriber_count += len(self._global_listeners)
        return f"TriggerSystem(subscribers={subscriber_count})"


# ---------------------------------------------------------------------------
# TriggerRule
# ---------------------------------------------------------------------------

class TriggerRule:
    """
    A story's data-driven declaration of which trigger it cares about and
    under what conditions.

    Conditions are plain data (ids, stage bounds, required flags, and
    freeform data-field filters) so most rules need no Python logic at
    all. For richer requirements (player level, faction reputation, NPC
    alive/dead, inventory, story completion, ...) a rule may additionally
    carry a `condition` from condition_system.py -- evaluated through
    StoryManager's shared ConditionEvaluator, so it benefits from the
    same dependency-indexed caching regardless of how many stories use
    it. A rule may also carry `consequences` -- Consequence objects from
    consequence_system.py -- executed safely through StoryManager's
    shared ConsequenceExecutor whenever the rule matches, independent of
    (and in addition to) `effect`. `effect` remains the escape hatch for
    custom Python behavior beyond "advance one stage" plus whatever
    consequences ran; the trigger system itself never contains that
    behavior.
    """

    def __init__(
        self,
        trigger_type: TriggerType,
        target_id: Optional[str] = None,
        instigator_id: Optional[str] = None,
        location_id: Optional[str] = None,
        min_stage: Optional[int] = None,
        max_stage: Optional[int] = None,
        required_flags: Optional[Dict[str, Any]] = None,
        data_filters: Optional[Dict[str, Any]] = None,
        condition: Optional["Condition"] = None,
        consequences: Optional[List["Consequence"]] = None,
        repeatable: bool = False,
        effect: Optional[Callable[["StoryInstance", "StoryDirector", TriggerEvent], None]] = None,
        rule_id: Optional[str] = None,
    ):
        self.id: str = rule_id or f"{trigger_type.value}:{id(self):x}"
        self.trigger_type: TriggerType = trigger_type

        # Conditions -- all optional; unset ones are ignored during matching.
        self.target_id: Optional[str] = target_id
        self.instigator_id: Optional[str] = instigator_id
        self.location_id: Optional[str] = location_id
        self.min_stage: Optional[int] = min_stage
        self.max_stage: Optional[int] = max_stage
        self.required_flags: Dict[str, Any] = required_flags or {}
        self.data_filters: Dict[str, Any] = data_filters or {}
        # Optional richer condition tree (see condition_system.py). Checked
        # separately by StoryManager, since evaluating it needs a
        # ConditionContext that TriggerRule itself has no business knowing about.
        self.condition: Optional["Condition"] = condition
        # Optional effects to execute on match (see consequence_system.py).
        # Run through StoryManager's shared ConsequenceExecutor, same
        # reasoning as `condition` above.
        self.consequences: List["Consequence"] = consequences or []

        self.repeatable: bool = repeatable
        self.effect = effect

        self.fired_count: int = 0

    # -- matching -------------------------------------------------------------

    def matches(self, event: TriggerEvent, story: "StoryInstance") -> bool:
        """Whether this rule should respond to `event` given the current
        state of `story`. Pure condition evaluation -- no side effects."""
        if event.type != self.trigger_type:
            return False
        if self.fired_count > 0 and not self.repeatable:
            return False

        if self.target_id is not None and _identifier_of(event.target) != self.target_id:
            return False
        if self.instigator_id is not None and _identifier_of(event.instigator) != self.instigator_id:
            return False
        if self.location_id is not None and _identifier_of(event.location) != self.location_id:
            return False

        if self.min_stage is not None and story.stage < self.min_stage:
            return False
        if self.max_stage is not None and story.stage > self.max_stage:
            return False

        for flag_key, expected_value in self.required_flags.items():
            if story.get_flag(flag_key) != expected_value:
                return False

        for data_key, expected_value in self.data_filters.items():
            if event.data.get(data_key) != expected_value:
                return False

        return True

    def mark_fired(self) -> None:
        self.fired_count += 1

    def __repr__(self) -> str:
        return f"TriggerRule(id={self.id!r}, type={self.trigger_type.value}, fired={self.fired_count})"


def _identifier_of(value: Any) -> Any:
    """
    Best-effort identifier extraction for condition matching: prefer an
    `.id` attribute (StoryObject, SearchArea, ...), otherwise fall back
    to the raw value itself (e.g. a plain string id passed directly).
    """
    return getattr(value, "id", value)