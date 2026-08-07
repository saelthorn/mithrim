"""
story_queue_manager.py

Phase 8 -- Story Queue Manager.

Provides StoryQueueManager: the system that decides, out of potentially
hundreds of registered stories, which ones are actually worth running
right now. StoryManager (Phase 3) knows how to run a story once it's
active; StoryQueueManager decides *when* a story gets to become active,
based on priority, player distance, player level, arbitrary requirement
Conditions, story chains (prerequisite stories), and cooldowns.

This is framework only. It contains no story content -- it does not know
why a story requires level 10 or what it unlocks when it completes, only
that a requirement was declared and either holds or doesn't.

Design summary
---------------
- QueueBucket        : the five buckets a story can live in --
                        QUEUED, DORMANT, ACTIVE, COMPLETED, FAILED.
- ActivationRequirement: data-driven gate a queued story must clear
                          before activating -- distance, player level,
                          prerequisite stories (chains), a richer
                          Condition (condition_system.py), and a cooldown.
- QueueEntry         : a story's membership record -- which bucket it's
                        in, its priority, its requirement, and timing.
- StoryQueueManager  : owns the buckets, the priority queue, the
                        chain/dependents index, and the dormant sweep.
                        `update()` is the single per-tick entry point.

Relationship to the rest of the framework:
- StoryQueueManager wraps a StoryManager (Phase 3) -- it never runs
  story logic itself, only decides when to call director.start() /
  .complete() / .fail() on the director StoryManager already owns.
- ActivationRequirement.condition is an optional condition_system.py
  Condition, evaluated through the same shared, caching
  ConditionEvaluator the trigger system uses, so a requirement shared
  across many queued stories is only actually computed once until
  something it depends on changes.
- Completing a story wakes only the stories chained to it (via a
  prerequisite -> dependents index), not a full scan of every dormant
  story -- the same "only touch what actually depends on this" idea
  condition_system.py's invalidate() uses.
- Optionally takes a WorldTimeManager (Phase 7, world_time.py). When
  supplied, cooldowns and sweep timing run off the canonical world
  clock (`WorldClock.total_hours`) instead of wall-clock time, and the
  manager subscribes to its TriggerType.TIME_PASSED so resting,
  traveling, or sleeping -- anything that calls
  WorldTimeManager.advance() -- automatically re-checks cooldowns and
  dormant requirements without gameplay code having to poll separately.
  Without a WorldTimeManager, everything falls back to wall-clock
  `time.time()`, so this integration is opt-in.

Performance & scalability notes
--------------------------------
- QUEUED stories are held in a binary heap (heapq), so picking the next
  highest-priority candidate is O(log n) rather than a linear scan.
  Priority changes use lazy deletion (push a new heap entry, mark the
  old one stale) rather than re-heapifying.
- Bucket membership is O(1) (dict keyed by story_id) for lookups, moves,
  and removals.
- DORMANT stories are not re-checked every tick. Only two things can
  make a dormant story worth re-checking: something explicitly marked
  it dirty (its chain prerequisite completed, its cooldown was set) or
  a throttled periodic sweep (`sweep_interval`) catches slow-changing
  gates like distance/level. This keeps update() cost proportional to
  "things that changed" plus a bounded sweep, not the total dormant count.
"""

from __future__ import annotations

import heapq
import itertools
import math
import time
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from story.trigger_system import TriggerEvent, TriggerType

if TYPE_CHECKING:
    from story.story_framework import StoryDirector, StoryManager
    from story.condition_system import Condition, ConditionContext, ConditionEvaluator
    from story.search_area import Position
    from world.world_time import WorldTimeManager


# ---------------------------------------------------------------------------
# QueueBucket
# ---------------------------------------------------------------------------

class QueueBucket(Enum):
    """Which of the five queue-level buckets a story currently lives in.

    This is distinct from (but kept in sync with) StoryInstance.state --
    a story can be QUEUED or DORMANT while its StoryState is still
    UNINITIALIZED; it only becomes ACTIVE here once StoryDirector.start()
    has actually run.
    """
    QUEUED = "queued"        # eligible to be picked up; waiting on priority order
    DORMANT = "dormant"      # not eligible yet; blocked on a requirement
    ACTIVE = "active"        # running, owned by StoryManager
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# ActivationRequirement
# ---------------------------------------------------------------------------

class ActivationRequirement:
    """
    Data-driven gate a queued story must clear before it can activate.

    Every field is optional; an unset field is simply not checked. This
    mirrors TriggerRule's approach in trigger_system.py -- most
    requirements need no Python logic at all, and a richer `condition`
    (player stats, factions, items, other stories) is available as an
    escape hatch for anything the built-in fields can't express.
    """

    def __init__(
        self,
        min_player_level: Optional[int] = None,
        location: Optional["Position"] = None,
        max_distance: Optional[float] = None,
        required_story_ids: Optional[List[str]] = None,
        condition: Optional["Condition"] = None,
        cooldown: float = 0.0,
    ):
        self.min_player_level: Optional[int] = min_player_level

        # Distance gating: the story only becomes eligible once the
        # player is within max_distance of `location`. Either both or
        # neither should be set; a missing location disables the check.
        self.location: Optional["Position"] = location
        self.max_distance: Optional[float] = max_distance

        # Story chains: this story cannot activate until every story in
        # required_story_ids has reached COMPLETED.
        self.required_story_ids: List[str] = list(required_story_ids or [])

        # Optional richer condition (see condition_system.py), evaluated
        # through the manager's shared ConditionEvaluator.
        self.condition: Optional["Condition"] = condition

        # Minimum time that must pass after this entry is marked
        # ready-for-cooldown (see StoryQueueManager.complete/fail/requeue)
        # before it can activate again. 0 means no cooldown. Expressed in
        # whatever unit StoryQueueManager._now() uses -- wall-clock
        # seconds by default, or world_time.py's WorldClock.total_hours
        # (i.e. hours) when the manager is given a WorldTimeManager. See
        # StoryQueueManager's docstring.
        self.cooldown: float = cooldown

    # -- individual checks (kept separate so callers/tests can probe why
    #    a requirement failed, instead of only getting one boolean back) --

    def level_satisfied(self, player_level: Optional[int]) -> bool:
        if self.min_player_level is None:
            return True
        return player_level is not None and player_level >= self.min_player_level

    def distance_satisfied(self, player_position: Optional["Position"]) -> bool:
        if self.location is None or self.max_distance is None:
            return True
        if player_position is None:
            return False
        dx = player_position[0] - self.location[0]
        dy = player_position[1] - self.location[1]
        return math.hypot(dx, dy) <= self.max_distance

    def chain_satisfied(self, story_manager: "StoryManager") -> bool:
        if not self.required_story_ids:
            return True
        for story_id in self.required_story_ids:
            story = story_manager.get_story(story_id)
            if story is None or story.state.value != "completed":
                return False
        return True

    def __repr__(self) -> str:
        return (
            f"ActivationRequirement(min_level={self.min_player_level}, "
            f"max_distance={self.max_distance}, chain={self.required_story_ids}, "
            f"cooldown={self.cooldown})"
        )


# ---------------------------------------------------------------------------
# QueueEntry
# ---------------------------------------------------------------------------

class QueueEntry:
    """
    A story's membership record within the queue manager.

    Holds everything the queue needs beyond what StoryInstance/StoryDirector
    already track: which bucket it's in, its priority, its activation
    requirement, and the timestamps that drive cooldowns and sweeps.
    """

    def __init__(
        self,
        story_id: str,
        priority: int = 0,
        requirement: Optional[ActivationRequirement] = None,
    ):
        self.story_id: str = story_id
        self.priority: int = priority
        self.requirement: ActivationRequirement = requirement or ActivationRequirement()

        self.bucket: QueueBucket = QueueBucket.QUEUED
        # Timestamps are stamped by StoryQueueManager via its own
        # _now(), so they stay in whatever clock the manager is
        # configured with (wall-clock seconds, or world-clock hours when
        # a WorldTimeManager is supplied) -- never mixed units.
        self.enqueued_at: Optional[float] = None
        self.activated_at: Optional[float] = None
        self.finished_at: Optional[float] = None

        # Set when a cooldown starts (complete/fail/requeue); the entry
        # is not eligible to activate again until elapsed time clears it.
        self.cooldown_ready_at: Optional[float] = None

        # Bumped every time this entry is pushed onto the priority heap,
        # so stale heap tuples (from a superseded priority change) can be
        # recognized and discarded lazily instead of re-heapifying.
        self._heap_token: int = 0

    def __repr__(self) -> str:
        return (
            f"QueueEntry(story_id={self.story_id!r}, bucket={self.bucket.value}, "
            f"priority={self.priority})"
        )


# ---------------------------------------------------------------------------
# StoryQueueManager
# ---------------------------------------------------------------------------

class StoryQueueManager:
    """
    Decides which registered stories get to run, and when.

    Wraps a StoryManager: this class owns no story content or lifecycle
    logic itself, only the scheduling policy layered on top of
    StoryDirector.start()/.complete()/.fail(). Gameplay/content code
    registers stories via `enqueue()` and calls `update()` once per tick
    (or on a slower cadence -- see `sweep_interval`) with the player's
    current position/level; StoryQueueManager activates whatever is
    ready, highest priority first, up to `max_active`.

    Pass a WorldTimeManager (world_time.py) via `world_time` to run
    cooldowns/sweeps off the canonical world clock instead of wall time,
    and to get automatic re-sweeps whenever world time advances (see
    `_on_time_passed`). This is optional -- omit it and everything works
    off `time.time()` exactly as before.
    """

    def __init__(
        self,
        story_manager: "StoryManager",
        max_active: int = 8,
        sweep_interval: float = 5.0,
        condition_evaluator: Optional["ConditionEvaluator"] = None,
        world_time: Optional["WorldTimeManager"] = None,
    ):
        self.story_manager: "StoryManager" = story_manager
        self.max_active: int = max_active
        # In whatever unit _now() returns -- wall-clock seconds by
        # default, or world-clock hours once `world_time` is set below.
        # A caller overriding this after construction should keep that
        # in mind (e.g. bump it to ~5 when switching to hourly ticks).
        self.sweep_interval: float = sweep_interval

        # Reuse the manager's shared ConditionEvaluator by default so a
        # requirement's Condition benefits from the same caching/
        # invalidation as TriggerRule conditions, instead of paying for
        # its own separate cache.
        self.condition_evaluator: "ConditionEvaluator" = (
            condition_evaluator or story_manager.condition_evaluator
        )

        # Optional world_time.py integration (see module docstring).
        # When set, _now() reads WorldClock.total_hours instead of
        # time.time(), and the manager re-sweeps automatically whenever
        # world time advances.
        self.world_time: Optional["WorldTimeManager"] = world_time
        if world_time is not None:
            world_time.trigger_system.subscribe(TriggerType.TIME_PASSED, self._on_time_passed)

        # Last known player context, cached so time-driven re-evaluation
        # (see _on_time_passed) has something to check requirements
        # against without gameplay code re-supplying it on every tick.
        self._player_position: Optional["Position"] = None
        self._player_level: Optional[int] = None
        self._condition_context: Optional["ConditionContext"] = None

        self._entries: Dict[str, QueueEntry] = {}
        self._buckets: Dict[QueueBucket, Dict[str, QueueEntry]] = {
            bucket: {} for bucket in QueueBucket
        }

        # Priority heap over QUEUED entries only. Tuples are
        # (-priority, sequence, story_id, heap_token) -- negated priority
        # so heapq's min-heap pops the *highest* priority first;
        # `sequence` breaks ties in FIFO (enqueue) order; `heap_token`
        # lets stale entries (superseded by set_priority) be dropped
        # lazily on pop instead of requiring a full re-heapify.
        self._heap: List[tuple] = []
        self._sequence = itertools.count()

        # prerequisite story_id -> ids of entries chained to it, so
        # completing a story only wakes the handful of dependents that
        # actually care, not every dormant entry.
        self._dependents: Dict[str, List[str]] = {}

        # Entries that need a requirement re-check on the next update(),
        # regardless of the sweep timer (e.g. a chain prerequisite just
        # completed, or a cooldown was just set).
        self._dirty: set = set()

        self._last_sweep: float = 0.0

    # -- clock ---------------------------------------------------------------

    def _now(self) -> float:
        """Current time in this manager's configured unit: world-clock
        hours when a WorldTimeManager is attached, wall-clock seconds
        otherwise. Every timestamp this manager stamps goes through
        here, so the two are never mixed."""
        if self.world_time is not None:
            return float(self.world_time.clock.total_hours)
        return time.time()

    # -- registration -----------------------------------------------------

    def enqueue(
        self,
        story_id: str,
        priority: int = 0,
        requirement: Optional[ActivationRequirement] = None,
    ) -> QueueEntry:
        """
        Register a story with the queue. The story must already exist in
        the wrapped StoryManager (create it there first). Starts in the
        QUEUED bucket and is immediately eligible for the next update()
        pass to evaluate.
        """
        entry = QueueEntry(story_id, priority=priority, requirement=requirement)
        entry.enqueued_at = self._now()
        self._entries[story_id] = entry
        self._index_chain(entry)
        self._set_bucket(entry, QueueBucket.QUEUED)
        self._push_heap(entry)
        return entry

    def _index_chain(self, entry: QueueEntry) -> None:
        for prerequisite_id in entry.requirement.required_story_ids:
            self._dependents.setdefault(prerequisite_id, []).append(entry.story_id)

    # -- priority -----------------------------------------------------------

    def set_priority(self, story_id: str, priority: int) -> bool:
        """Change a story's priority. Only affects ordering while it is
        QUEUED; takes effect on the next heap push."""
        entry = self._entries.get(story_id)
        if entry is None:
            return False
        entry.priority = priority
        if entry.bucket == QueueBucket.QUEUED:
            self._push_heap(entry)  # old heap tuple becomes stale, dropped lazily
        return True

    def _push_heap(self, entry: QueueEntry) -> None:
        entry._heap_token += 1
        heapq.heappush(
            self._heap,
            (-entry.priority, next(self._sequence), entry.story_id, entry._heap_token),
        )

    # -- bucket bookkeeping -------------------------------------------------

    def _set_bucket(self, entry: QueueEntry, bucket: QueueBucket) -> None:
        self._buckets[entry.bucket].pop(entry.story_id, None)
        entry.bucket = bucket
        self._buckets[bucket][entry.story_id] = entry

    def get_bucket(self, bucket: QueueBucket) -> List[QueueEntry]:
        return list(self._buckets[bucket].values())

    def get_entry(self, story_id: str) -> Optional[QueueEntry]:
        return self._entries.get(story_id)

    # -- requirement evaluation ---------------------------------------------

    def _requirement_met(
        self,
        entry: QueueEntry,
        player_position: Optional["Position"],
        player_level: Optional[int],
        condition_context: Optional["ConditionContext"],
        now: float,
    ) -> bool:
        requirement = entry.requirement

        if entry.cooldown_ready_at is not None and now < entry.cooldown_ready_at:
            return False
        if not requirement.level_satisfied(player_level):
            return False
        if not requirement.distance_satisfied(player_position):
            return False
        if not requirement.chain_satisfied(self.story_manager):
            return False
        if requirement.condition is not None:
            if condition_context is None:
                return False
            if not self.condition_evaluator.evaluate(requirement.condition, condition_context):
                return False

        return True

    # -- per-tick update ----------------------------------------------------

    def update(
        self,
        player_position: Optional["Position"] = None,
        player_level: Optional[int] = None,
        condition_context: Optional["ConditionContext"] = None,
        now: Optional[float] = None,
    ) -> List[str]:
        """
        Single per-tick entry point. Returns the ids of stories activated
        during this call.

        1. Re-check DORMANT entries that are either explicitly dirty or
           due for the throttled periodic sweep, moving newly-eligible
           ones back to QUEUED.
        2. Drain the priority heap, activating the highest-priority
           QUEUED entries that pass their requirement, until either the
           heap is empty or `max_active` active stories is reached.

        Any argument left as None falls back to the last known value
        (see `set_player_context`), so callers that only track one
        changing value (e.g. just distance every frame) don't have to
        keep re-supplying the others -- and so `_on_time_passed` can
        re-sweep on world-time advances using whatever was last seen.
        """
        self.set_player_context(player_position, player_level, condition_context)
        now = self._now() if now is None else now
        self._sweep_dormant(self._player_position, self._player_level, self._condition_context, now)
        return self._drain_queue(self._player_position, self._player_level, self._condition_context, now)

    def set_player_context(
        self,
        player_position: Optional["Position"] = None,
        player_level: Optional[int] = None,
        condition_context: Optional["ConditionContext"] = None,
    ) -> None:
        """Cache the latest known player context. Each argument only
        overwrites the cache when explicitly supplied (non-None), so
        partial updates don't clobber previously known values."""
        if player_position is not None:
            self._player_position = player_position
        if player_level is not None:
            self._player_level = player_level
        if condition_context is not None:
            self._condition_context = condition_context

    def _on_time_passed(self, event: TriggerEvent) -> None:
        """
        WorldTimeManager hook (subscribed in __init__ when `world_time`
        is supplied): whenever world time advances -- resting,
        traveling, sleeping, or a ScheduledEvent firing -- re-run the
        sweep/drain pass using the last known player context. This is
        what lets cooldowns and dormant requirements catch up the moment
        game time actually moves, instead of only when something happens
        to call update() on its own.
        """
        self.update()

    def _sweep_dormant(
        self,
        player_position: Optional["Position"],
        player_level: Optional[int],
        condition_context: Optional["ConditionContext"],
        now: float,
    ) -> None:
        due_for_sweep = (now - self._last_sweep) >= self.sweep_interval
        if not due_for_sweep and not self._dirty:
            return

        candidates = (
            self._buckets[QueueBucket.DORMANT].values()
            if due_for_sweep
            else [self._entries[sid] for sid in self._dirty if sid in self._entries]
        )
        # Snapshot before mutating buckets mid-iteration.
        for entry in list(candidates):
            if entry.bucket != QueueBucket.DORMANT:
                continue
            if self._requirement_met(entry, player_position, player_level, condition_context, now):
                self._set_bucket(entry, QueueBucket.QUEUED)
                self._push_heap(entry)

        self._dirty.clear()
        if due_for_sweep:
            self._last_sweep = now

    def _drain_queue(
        self,
        player_position: Optional["Position"],
        player_level: Optional[int],
        condition_context: Optional["ConditionContext"],
        now: float,
    ) -> List[str]:
        activated: List[str] = []
        deferred: List[QueueEntry] = []

        while self._heap and len(self._buckets[QueueBucket.ACTIVE]) < self.max_active:
            _, _, story_id, token = heapq.heappop(self._heap)
            entry = self._entries.get(story_id)
            if entry is None or entry.bucket != QueueBucket.QUEUED or entry._heap_token != token:
                continue  # stale (removed, re-bucketed, or superseded priority) -- discard

            if self._requirement_met(entry, player_position, player_level, condition_context, now):
                if self._activate(entry):
                    activated.append(story_id)
            else:
                deferred.append(entry)  # still queued, just not ready this pass

        for entry in deferred:
            self._set_bucket(entry, QueueBucket.DORMANT)

        return activated

    def _activate(self, entry: QueueEntry) -> bool:
        director = self.story_manager.get_director(entry.story_id)
        if director is None or not director.start():
            self._set_bucket(entry, QueueBucket.DORMANT)
            return False
        entry.activated_at = self._now()
        self._set_bucket(entry, QueueBucket.ACTIVE)
        return True

    # -- outcomes -------------------------------------------------------

    def complete(self, story_id: str) -> bool:
        """Mark a story completed, freeing an active slot and waking any
        stories chained to it."""
        return self._finish(story_id, QueueBucket.COMPLETED, lambda director: director.complete())

    def fail(self, story_id: str, reason: Optional[str] = None) -> bool:
        """Mark a story failed, freeing an active slot. Chained
        dependents stay dormant, since their prerequisite never completed."""
        return self._finish(story_id, QueueBucket.FAILED, lambda director: director.fail(reason))

    def _finish(self, story_id: str, bucket: QueueBucket, apply: Any) -> bool:
        entry = self._entries.get(story_id)
        director = self.story_manager.get_director(story_id)
        if entry is None or director is None:
            return False
        if not apply(director):
            return False

        entry.finished_at = self._now()
        self._set_bucket(entry, bucket)
        self.condition_evaluator.invalidate(f"story_state:{story_id}")

        if bucket == QueueBucket.COMPLETED:
            self._wake_dependents(story_id)
        return True

    def _wake_dependents(self, story_id: str) -> None:
        """Mark every entry chained to `story_id` dirty so the next
        update() re-checks it immediately, instead of waiting for the
        next periodic sweep."""
        for dependent_id in self._dependents.get(story_id, ()):
            self._dirty.add(dependent_id)

    def requeue(self, story_id: str, cooldown: Optional[float] = None) -> bool:
        """
        Return a finished (or dormant) story to circulation -- for
        repeatable/periodic stories (ambient encounters, recurring
        events). Applies `cooldown` seconds (falling back to the
        requirement's own configured cooldown) before it can activate
        again.
        """
        entry = self._entries.get(story_id)
        if entry is None:
            return False

        delay = entry.requirement.cooldown if cooldown is None else cooldown
        entry.cooldown_ready_at = self._now() + delay if delay > 0 else None
        self._set_bucket(entry, QueueBucket.DORMANT)
        self._dirty.add(story_id)
        return True

    # -- introspection ------------------------------------------------------

    def stats(self) -> Dict[str, int]:
        """Bucket sizes -- handy for HUD/debug display and for tuning
        `max_active`/`sweep_interval` against real story counts."""
        return {bucket.value: len(entries) for bucket, entries in self._buckets.items()}

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        counts = self.stats()
        return (
            f"StoryQueueManager(active={counts['active']}/{self.max_active}, "
            f"queued={counts['queued']}, dormant={counts['dormant']}, "
            f"completed={counts['completed']}, failed={counts['failed']})"
        )