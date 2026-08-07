"""
story_failure_system.py

Phase 10 -- Story Failure & World Scars.

Provides a failure system for stories that don't end with the player
succeeding: stories the player never got to (Ignored), stories that ran
past a hard deadline (Expired), stories that hit an explicit failure
condition while active (Failed), and stories the world resolved without
the player at all (Resolved by NPCs). None of these are dead ends -- each
one is turned into a permanent, queryable change to the world (a
WorldScar) plus whatever mechanical consequences content wants (via the
existing consequence_system.py), and optionally spawns an aftermath
story so failure opens new content instead of closing a door.

This is framework only. It contains no narrative content -- it does not
decide *what* a burned village looks like or *which* NPC gets credit for
clearing the bandit camp; it only guarantees that failing is recorded,
that the right consequences run, that the change persists and is
queryable by future stories, and that content can branch on *which kind*
of failure happened. What that branch actually says is up to content.

Design summary
---------------
- FailureMode        : the vocabulary of ways a story ends without the
                        player completing it -- IGNORED, EXPIRED, FAILED,
                        RESOLVED_BY_NPC. Passed as the `reason` string to
                        StoryDirector.fail() (story_framework.py), so it
                        rides along on the existing STORY_FAILED hook
                        instead of inventing a parallel lifecycle.
- WorldScar           : a permanent, queryable record that the world
                        changed as a result of a failure -- a tag content
                        checks against, which story and FailureMode
                        produced it, when. It records the *fact*; it does
                        not itself mutate anything.
- WorldScarRegistry   : owns every WorldScar, indexed by tag and by story
                        so lookups never scan the full history.
- FailurePolicy       : a story's (or a whole chain's) data-driven
                        declaration of what should happen per FailureMode
                        -- which Consequences to run, what tag to scar the
                        world with, and which aftermath story to enqueue.
- FailureRecord       : bookkeeping for one story's failure -- when, how,
                        at what stage, and (for RESOLVED_BY_NPC) by whom.
- StoryFailureManager : glues it together. Subscribes to every registered
                        story's STORY_FAILED hook (however it fires --
                        a deadline, a trigger rule, a direct call) and
                        turns it into a FailureRecord, a scar, and
                        whatever the story's FailurePolicy declares.

Relationship to the rest of the framework
-------------------------------------------
- StoryDirector.fail(reason) (story_framework.py) is the single point of
  entry this system hooks into. story_framework.py's transition table now
  also allows UNINITIALIZED/PAUSED -> FAILED (see that file), so an
  ignored story -- one the player never even started -- can still be
  failed the same way an active one can, through the same method, firing
  the same STORY_FAILED hook.
- StoryFailureManager never decides *when* a story fails. Detection is
  content's job, wired through the framework's existing pieces:
    * mark_failed()/mark_resolved_by_npc() are typically called from a
      TriggerRule.effect (trigger_system.py) or a ScheduledEvent callback
      (world_time.py) that already knows the story in question failed.
    * arm_ignore_timer()/arm_expiry_timer() are convenience wrappers
      around WorldTimeManager.scheduler.schedule_in() (world_time.py):
      schedule a check for "still not started" / "still not finished" N
      hours out, exactly like world_time.py's own
      schedule_npc_missing()/schedule_camp_abandonment() examples.
- Consequences (destroy a landmark, shift reputation, spawn an NPC or a
  StoryObject ruin, lock/unlock a region, ...) run through the same
  shared ConsequenceExecutor/ExecutionContext (consequence_system.py)
  every other part of the framework already uses -- this system supplies
  no new mutation mechanism, only a new reason to trigger one.
- WorldScarCondition (added to condition_system.py alongside
  StoryCompletedCondition/StoryFailedCondition) is how *any* future
  story, ActivationRequirement (story_queue_manager.py), or ChainEdge
  (story_chain_system.py) gates on a scar existing -- e.g. a "refugee
  camp" story's ActivationRequirement.condition can be
  WorldScarCondition("village_burned:northfield"), becoming eligible
  only once that scar is recorded, without any direct link to the story
  that burned the village.
- StoryChainManager (story_chain_system.py) already listens to
  STORY_FAILED and maps it to ChainOutcome.FAILED via a node's
  outcome_resolver. Because this system stamps a "failure_mode" flag on
  the StoryInstance the moment it fails (before chain edges are
  followed, since both listeners are wired independently on the same
  hook), a ChainNode can supply its own outcome_resolver that reads
  `story.get_flag("failure_mode")` instead of just `story.state`, giving
  branches like "ignored" -> a rumor spreads, "resolved_by_npc" -> a
  rival takes the credit, in addition to the plain "completed"/"failed"/
  "aborted" outcomes ChainOutcome already provides -- no changes needed
  to story_chain_system.py itself, since ChainEdge.outcome is already
  just a string key.
- StoryQueueManager (story_queue_manager.py) is reused, not duplicated,
  for aftermath: FailurePolicy.follow_up_story_id names a story that
  must already be registered with StoryManager, and this system simply
  calls queue_manager.enqueue() on it -- the queue manager's existing
  priority/requirement/cooldown machinery decides when it actually
  starts, exactly as it does for chain nodes.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from story.story_framework import StoryEvent, StoryState

if TYPE_CHECKING:
    from story.story_framework import StoryDirector, StoryInstance, StoryManager
    from story.story_queue_manager import ActivationRequirement, StoryQueueManager
    from story.consequence_system import Consequence, ConsequenceExecutor
    from world.world_time import TimeUnit, WorldTimeManager


# ---------------------------------------------------------------------------
# FailureMode
# ---------------------------------------------------------------------------

class FailureMode(Enum):
    """
    The vocabulary of ways a story can end without the player completing
    it. Values double as the `reason` string passed to
    StoryDirector.fail() -- StoryFailureManager reads it back off the
    STORY_FAILED hook to decide what happened, so this is the one place
    that vocabulary is defined.

    Distinct from StoryState.FAILED: every one of these lands in that
    same coarse lifecycle bucket, but FailureMode is the finer-grained
    signal everything downstream (scars, policies, chain branching)
    actually keys off of.
    """
    IGNORED = "ignored"                    # never started -- the player never engaged it in time
    EXPIRED = "expired"                    # started, but a hard deadline passed before completion
    FAILED = "failed"                      # started, and an explicit failure condition was met
    RESOLVED_BY_NPC = "resolved_by_npc"    # the world resolved it without the player

    @classmethod
    def from_reason(cls, reason: Optional[str]) -> "FailureMode":
        """
        Best-effort parse of a StoryDirector.fail() `reason` back into a
        FailureMode. Falls back to FAILED for any reason this system
        didn't produce itself -- including None, or a plain "failed"
        passed by content that never heard of FailureMode -- since FAILED
        is the most conservative, least-presumptuous bucket.
        """
        try:
            return cls(reason)
        except ValueError:
            return cls.FAILED


# ---------------------------------------------------------------------------
# WorldScar
# ---------------------------------------------------------------------------

class WorldScar:
    """
    A permanent, queryable record that the world changed as a result of
    a story's failure.

    Deliberately thin: an id, the tag content checks against (e.g.
    "village_burned:northfield"), which story and FailureMode produced
    it, when, and a freeform data payload. A scar does not itself change
    anything -- the actual mutation already happened through
    FailurePolicy's `consequences`, applied via the same
    ConsequenceExecutor/ExecutionContext every other part of the
    framework uses. The scar is only the fact that persists afterward.
    """

    def __init__(
        self,
        tag: str,
        story_id: str,
        failure_mode: FailureMode,
        world_hour: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None,
        scar_id: Optional[str] = None,
    ):
        self.id: str = scar_id or f"scar:{tag}:{story_id}"
        self.tag: str = tag
        self.story_id: str = story_id
        self.failure_mode: FailureMode = failure_mode
        self.world_hour: Optional[int] = world_hour
        self.created_at: float = time.time()
        self.data: Dict[str, Any] = data if data is not None else {}

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tag": self.tag,
            "story_id": self.story_id,
            "failure_mode": self.failure_mode.value,
            "world_hour": self.world_hour,
            "created_at": self.created_at,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldScar":
        scar = cls(
            tag=data["tag"],
            story_id=data["story_id"],
            failure_mode=FailureMode(data["failure_mode"]),
            world_hour=data.get("world_hour"),
            data=dict(data.get("data", {})),
            scar_id=data.get("id"),
        )
        scar.created_at = data.get("created_at", scar.created_at)
        return scar

    def __repr__(self) -> str:
        return f"WorldScar(tag={self.tag!r}, story_id={self.story_id!r}, mode={self.failure_mode.value})"


# ---------------------------------------------------------------------------
# WorldScarRegistry
# ---------------------------------------------------------------------------

class WorldScarRegistry:
    """
    Owns every WorldScar ever recorded, indexed the two ways content
    actually asks about them: "does this specific tag exist" and "what
    happened to this story". Mirrors ConditionEvaluator's dependency-index
    approach (condition_system.py) -- indexed lookups rather than a
    linear scan, since a long-lived world can accumulate a great many
    scars over its lifetime.
    """

    def __init__(self):
        self._scars: Dict[str, WorldScar] = {}
        self._by_tag: Dict[str, set] = {}
        self._by_story: Dict[str, set] = {}

    def add(self, scar: WorldScar) -> WorldScar:
        self._scars[scar.id] = scar
        self._by_tag.setdefault(scar.tag, set()).add(scar.id)
        self._by_story.setdefault(scar.story_id, set()).add(scar.id)
        return scar

    def has_scar(self, tag: str) -> bool:
        return bool(self._by_tag.get(tag))

    def get_scars(self, tag: str) -> List[WorldScar]:
        return [self._scars[scar_id] for scar_id in self._by_tag.get(tag, ())]

    def get_scars_for_story(self, story_id: str) -> List[WorldScar]:
        return [self._scars[scar_id] for scar_id in self._by_story.get(story_id, ())]

    # -- bulk persistence -------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {"scars": [scar.to_dict() for scar in self._scars.values()]}

    def load(self, data: Dict[str, Any]) -> None:
        """Restore scars into this registry. Additive -- does not clear
        first, so it composes with a host's broader bulk-load sequence."""
        for scar_data in data.get("scars", []):
            self.add(WorldScar.from_dict(scar_data))

    def __len__(self) -> int:
        return len(self._scars)

    def __repr__(self) -> str:
        return f"WorldScarRegistry(scars={len(self._scars)}, tags={len(self._by_tag)})"


# ---------------------------------------------------------------------------
# FailurePolicy
# ---------------------------------------------------------------------------

class FailurePolicy:
    """
    A story's data-driven declaration of what should happen when it
    fails, per FailureMode. Mirrors TriggerRule/ActivationRequirement's
    approach elsewhere in the framework: plain data plus optional escape
    hatches, and the policy itself never applies anything --
    StoryFailureManager does, through the shared ConsequenceExecutor.

    One policy is typically registered per story archetype and reused
    across every instance/chain node of it (content usually wants "any
    bandit-camp story that fails burns the camp down", not a bespoke
    policy per procedurally-generated instance).
    """

    def __init__(
        self,
        scar_tag: Optional[str] = None,
        consequences: Optional[Dict["FailureMode", List["Consequence"]]] = None,
        follow_up_story_id: Optional[Dict["FailureMode", str]] = None,
        follow_up_requirement: Optional["ActivationRequirement"] = None,
        applies_to: Optional[List["FailureMode"]] = None,
    ):
        # Tag stamped onto every WorldScar this policy produces. "{mode}"
        # inside the string is substituted with the FailureMode value, so
        # one policy can still produce distinguishable scars per mode
        # (e.g. "bandits_northfield:{mode}" -> "...:ignored" vs
        # "...:resolved_by_npc") without content writing four policies.
        self.scar_tag: Optional[str] = scar_tag

        # Consequences to run per FailureMode -- e.g. IGNORED might only
        # nudge reputation, while FAILED destroys a landmark and
        # RESOLVED_BY_NPC hands the credit/loot to an NPC faction instead
        # of the player.
        self.consequences: Dict[FailureMode, List["Consequence"]] = consequences or {}

        # Optional aftermath story to enqueue per FailureMode, so failure
        # opens new content instead of ending it (a burned village spawns
        # a "refugees" story; ignored bandits spawn a "raid" story).
        self.follow_up_story_id: Dict[FailureMode, str] = follow_up_story_id or {}
        self.follow_up_requirement: Optional["ActivationRequirement"] = follow_up_requirement

        # Which FailureModes this policy actually reacts to. None
        # (default) means all of them; a policy can restrict itself so,
        # say, IGNORED produces no scar/consequences for a purely
        # ambient story that shouldn't mark the world just for being
        # skipped, while FAILED/RESOLVED_BY_NPC still do.
        self.applies_to: Optional[List[FailureMode]] = applies_to

    def applies(self, mode: "FailureMode") -> bool:
        return self.applies_to is None or mode in self.applies_to

    def scar_tag_for(self, mode: "FailureMode") -> Optional[str]:
        if self.scar_tag is None:
            return None
        return self.scar_tag.format(mode=mode.value)

    def consequences_for(self, mode: "FailureMode") -> List["Consequence"]:
        return list(self.consequences.get(mode, ()))

    def follow_up_for(self, mode: "FailureMode") -> Optional[str]:
        return self.follow_up_story_id.get(mode)

    def __repr__(self) -> str:
        return f"FailurePolicy(scar_tag={self.scar_tag!r}, modes={[m.value for m in (self.applies_to or list(FailureMode))]})"


# ---------------------------------------------------------------------------
# FailureRecord
# ---------------------------------------------------------------------------

class FailureRecord:
    """
    Bookkeeping for one story's failure -- when, how, at what stage, and
    (for RESOLVED_BY_NPC) who actually resolved it. A record always
    exists once a story fails, whether or not its FailurePolicy produced
    a scar (a policy can exclude a mode via `applies_to`); the scar is
    the world-facing consequence, the record is the audit trail.
    """

    def __init__(
        self,
        story_id: str,
        mode: "FailureMode",
        stage_at_failure: int,
        world_hour: Optional[int] = None,
        detail: Optional[Dict[str, Any]] = None,
    ):
        self.story_id: str = story_id
        self.mode: FailureMode = mode
        self.stage_at_failure: int = stage_at_failure
        self.world_hour: Optional[int] = world_hour
        self.recorded_at: float = time.time()
        # Freeform, e.g. {"resolver": "npc:rival_hunter"} for
        # RESOLVED_BY_NPC, or {"cause": "hostage_died"} for FAILED.
        self.detail: Dict[str, Any] = detail if detail is not None else {}

    def __repr__(self) -> str:
        return f"FailureRecord(story_id={self.story_id!r}, mode={self.mode.value}, stage={self.stage_at_failure})"


# ---------------------------------------------------------------------------
# StoryFailureManager
# ---------------------------------------------------------------------------

class StoryFailureManager:
    """
    Turns a StoryDirector's STORY_FAILED hook into permanent, queryable
    world consequences instead of a dead end.

    Wraps a StoryManager (required) and optionally a StoryQueueManager
    (to enqueue aftermath stories) and a WorldTimeManager (to arm ignore/
    expiry deadlines off the canonical world clock, and to timestamp
    scars/records with world_hour instead of wall-clock time). Subscribes
    to each registered story's STORY_FAILED hook the same way
    StoryChainManager subscribes to lifecycle hooks in
    story_chain_system.py -- purely reactive, never deciding *when* a
    story fails, only *what happens once it has*.
    """

    def __init__(
        self,
        story_manager: "StoryManager",
        queue_manager: Optional["StoryQueueManager"] = None,
        world_time: Optional["WorldTimeManager"] = None,
        consequence_executor: Optional["ConsequenceExecutor"] = None,
        registry: Optional["WorldScarRegistry"] = None,
    ):
        self.story_manager: "StoryManager" = story_manager
        self.queue_manager: Optional["StoryQueueManager"] = queue_manager
        self.world_time: Optional["WorldTimeManager"] = world_time
        # Reuse the manager's shared executor by default, same reasoning
        # as StoryChainManager reusing it in story_chain_system.py.
        self.consequence_executor: "ConsequenceExecutor" = (
            consequence_executor or story_manager.consequence_executor
        )
        self.registry: WorldScarRegistry = registry or WorldScarRegistry()

        self._policies: Dict[str, FailurePolicy] = {}
        self._records: Dict[str, FailureRecord] = {}
        # Detail stashed by mark_*() just before calling director.fail(),
        # consumed by _on_story_failed() when the hook actually fires --
        # lets richer per-call context (a resolver npc, a failure cause)
        # ride along without changing StoryDirector.fail()'s signature.
        self._pending_detail: Dict[str, Dict[str, Any]] = {}
        self._wired: set = set()

    # -- policy registration ------------------------------------------------

    def register_policy(self, story_id: str, policy: FailurePolicy) -> None:
        """
        Attach a FailurePolicy to a story and wire its director's
        STORY_FAILED hook, if not already wired. Safe to call before or
        after the story is started -- it only needs to already be loaded
        (create_story()/load_story() already ran), the same contract
        StoryChainManager.register_chain() documents for its nodes.
        """
        self._policies[story_id] = policy
        self._wire(story_id)

    def _wire(self, story_id: str) -> None:
        if story_id in self._wired:
            return
        director = self.story_manager.get_director(story_id)
        if director is None:
            return  # not loaded yet -- content re-registers after loading

        def on_failed(story: "StoryInstance", reason: Optional[str] = None, **_context: Any) -> None:
            self._on_story_failed(story, reason)

        director.on(StoryEvent.STORY_FAILED, on_failed)
        self._wired.add(story_id)

    # -- marking failure (convenience wrappers around director.fail()) -----

    def mark_ignored(self, story_id: str, **detail: Any) -> bool:
        """A queued/dormant/paused story the player never engaged with in
        time. Relies on story_framework.py's UNINITIALIZED/PAUSED ->
        FAILED transitions."""
        return self._mark(story_id, FailureMode.IGNORED, detail)

    def mark_expired(self, story_id: str, **detail: Any) -> bool:
        """An active story that hit a hard deadline before completion."""
        return self._mark(story_id, FailureMode.EXPIRED, detail)

    def mark_failed(self, story_id: str, **detail: Any) -> bool:
        """An active story where an explicit failure condition was met
        (a required NPC died, an escort was killed, a wrong choice was
        made, ...)."""
        return self._mark(story_id, FailureMode.FAILED, detail)

    def mark_resolved_by_npc(self, story_id: str, resolver: Any = None, **detail: Any) -> bool:
        """The world resolved the story's objective without the player --
        a rival adventurer looted the wagon first, town guards cleared
        the bandit camp on their own patrol."""
        detail["resolver"] = resolver
        return self._mark(story_id, FailureMode.RESOLVED_BY_NPC, detail)

    def _mark(self, story_id: str, mode: "FailureMode", detail: Dict[str, Any]) -> bool:
        director = self.story_manager.get_director(story_id)
        if director is None or director.is_finished():
            return False  # unloaded, or already completed/failed/aborted -- idempotent no-op
        self._wire(story_id)
        self._pending_detail[story_id] = detail
        return director.fail(reason=mode.value)

    # -- reacting to STORY_FAILED (however it was triggered) ---------------

    def _on_story_failed(self, story: "StoryInstance", reason: Optional[str]) -> None:
        """
        Runs for every STORY_FAILED this manager is wired to, whether it
        came from mark_*() above or from content calling director.fail()
        directly (e.g. a TriggerRule.effect). Records the failure, stamps
        a `failure_mode` flag any chain outcome_resolver or TriggerRule
        can branch on, and -- if a policy is registered and applies to
        this mode -- runs its consequences, scar, and aftermath story.
        """
        mode = FailureMode.from_reason(reason)
        detail = self._pending_detail.pop(story.id, {})

        record = FailureRecord(
            story_id=story.id,
            mode=mode,
            stage_at_failure=story.stage,
            world_hour=self.world_time.clock.total_hours if self.world_time else None,
            detail=detail,
        )
        self._records[story.id] = record

        # Stamped on the story itself (not just kept in this manager) so
        # any QuestFlagCondition, TriggerRule.required_flags, or a chain
        # node's custom outcome_resolver can branch on *which kind* of
        # failure this was -- not just the coarse "failed" StoryState
        # ChainOutcome.FAILED already exposes.
        director = self.story_manager.get_director(story.id)
        if director is not None:
            director.set_flag("failure_mode", mode.value)

        policy = self._policies.get(story.id)
        if policy is None or not policy.applies(mode):
            return

        self._apply_consequences(policy.consequences_for(mode))
        self._record_scar(policy.scar_tag_for(mode), story.id, mode, detail)
        self._enqueue_follow_up(policy.follow_up_for(mode), policy.follow_up_requirement)

    def _apply_consequences(self, consequences: List["Consequence"]) -> None:
        """Mirrors StoryManager._run_rule_consequences()/StoryChainManager
        ._apply(): a missing ExecutionContext or a failed consequence is
        swallowed here, since Consequence.execute() already guarantees
        it never raises."""
        context = self.story_manager.execution_context
        if not consequences or context is None:
            return
        for consequence in consequences:
            self.consequence_executor.execute(consequence, context)

    def _record_scar(
        self, tag: Optional[str], story_id: str, mode: "FailureMode", detail: Dict[str, Any]
    ) -> None:
        if tag is None:
            return
        scar = WorldScar(
            tag=tag,
            story_id=story_id,
            failure_mode=mode,
            world_hour=self.world_time.clock.total_hours if self.world_time else None,
            data=detail,
        )
        self.registry.add(scar)
        # Let any cached WorldScarCondition(tag) result (condition_system.py)
        # know a matching scar now exists -- the same targeted-invalidation
        # pattern FLAG_CHANGED/STORY_COMPLETED/STORY_FAILED already use in
        # story_framework.py's _wire_condition_invalidation().
        self.story_manager.condition_evaluator.invalidate(f"world_scar:{tag}")

    def _enqueue_follow_up(
        self, story_id: Optional[str], requirement: Optional["ActivationRequirement"]
    ) -> None:
        if story_id is None or self.queue_manager is None:
            return
        if self.story_manager.get_director(story_id) is None:
            return  # aftermath story must already be created/loaded, same contract as chain nodes
        self.queue_manager.enqueue(story_id, requirement=requirement)

    # -- deadline helpers (opt-in world_time.py integration) ---------------

    def arm_ignore_timer(self, story_id: str, amount: int, unit: "TimeUnit") -> Optional[Any]:
        """
        Schedule mark_ignored(story_id) to run `amount` of `unit` from
        now, but only if the story is still UNINITIALIZED at that point
        (the player never started it) -- if it's already active or
        finished by then, this is a no-op. Requires a WorldTimeManager;
        returns the ScheduledEvent, or None if none was supplied.
        """
        return self._arm_timer(story_id, amount, unit, StoryState.UNINITIALIZED, self.mark_ignored)

    def arm_expiry_timer(self, story_id: str, amount: int, unit: "TimeUnit") -> Optional[Any]:
        """
        Schedule mark_expired(story_id) to run `amount` of `unit` from
        now, but only if the story is still ACTIVE at that point (started
        but not yet finished) -- if it already completed, failed, or was
        aborted, this is a no-op.
        """
        return self._arm_timer(story_id, amount, unit, StoryState.ACTIVE, self.mark_expired)

    def _arm_timer(self, story_id: str, amount: int, unit: "TimeUnit", guard_state: StoryState, mark_fn: Any) -> Optional[Any]:
        if self.world_time is None:
            return None

        def _fire(mgr: "WorldTimeManager", event: Any) -> None:
            story = self.story_manager.get_story(story_id)
            if story is not None and story.state == guard_state:
                mark_fn(story_id)

        return self.world_time.scheduler.schedule_in(self.world_time.clock, amount, unit, _fire)

    # -- retrieval ------------------------------------------------------

    def get_record(self, story_id: str) -> Optional[FailureRecord]:
        return self._records.get(story_id)

    def has_scar(self, tag: str) -> bool:
        return self.registry.has_scar(tag)

    def __repr__(self) -> str:
        return (
            f"StoryFailureManager(policies={len(self._policies)}, "
            f"records={len(self._records)}, scars={len(self.registry)})"
        )