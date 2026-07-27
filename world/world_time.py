"""
world_time.py

Phase 7 -- World Time & Scheduling.

Provides a single canonical world clock plus a priority-queue scheduler
that lets stories evolve while the player isn't looking: missing NPCs,
decaying corpses, abandoned camps, relocating bandits, burned buildings,
growing crops.

This is framework only. It contains no narrative content -- it does not
decide *what* a decayed corpse looks like or *where* bandits relocate to;
it only guarantees that the right callback runs at the right game-time
and that the rest of the framework hears about it. What the callback
actually does is supplied by content systems (see the example scheduling
helpers near the bottom of this file, which stand in for that content
layer).

Design summary
---------------
- TimeUnit        : HOUR / DAY / WEEK / MONTH, each expressed as a fixed
                     number of hours so conversions never drift.
- WorldClock       : the single source of truth for "what time is it".
                     Stores one integer (total hours elapsed); day, week,
                     and month are computed properties, never stored
                     redundantly. `advance()` is the only way time moves.
- ScheduledEvent   : one queued piece of story evolution -- a callback
                     plus the absolute hour it's due, and (for recurring
                     events like crop growth stages) an interval to
                     re-schedule itself with after running.
- TimeScheduler    : a heapq-backed priority queue of ScheduledEvents.
                     Only events that are actually due get touched on any
                     given advance -- no per-tick scanning of every world
                     object.
- WorldTimeManager : glues WorldClock + TimeScheduler + TriggerSystem
                     together. Gameplay code calls one method
                     (`advance`); everything else -- running due events,
                     firing TIME_PASSED, letting stories react -- follows
                     from that.

Relationship to the rest of the framework:
- Gameplay code -> WorldTimeManager.advance(amount, unit)
    -> WorldClock.advance()               (moves the canonical clock)
    -> TimeScheduler.run_due(new_hour)    (pops + runs due ScheduledEvents)
    -> TriggerSystem.fire(TIME_PASSED, ...)  (generic "time moved" signal)
- Each ScheduledEvent's callback is free to call
  `TriggerSystem.fire(SPECIFIC_TYPE, ...)` itself (see the example
  systems below) so StoryManager's existing TriggerRule matching (Phase
  6) picks it up exactly like any other gameplay trigger -- no changes
  needed to story_framework.py or trigger_system.py's dispatch logic.
"""

from __future__ import annotations

import heapq
import itertools
from enum import Enum
from typing import Any, Callable, Dict, Optional

from story.trigger_system import TriggerSystem, TriggerType


# ---------------------------------------------------------------------------
# TimeUnit
# ---------------------------------------------------------------------------

class TimeUnit(Enum):
    """
    Supported units of world time, each defined as a fixed number of
    hours. HOURS_PER_MONTH uses a flat 30-day month for predictable
    scheduling math (no calendar-specific leap/short-month handling) --
    change here if Mithrim later wants a real calendar.
    """
    MINUTE = 1 / 60
    HOUR = 1
    DAY = 24
    WEEK = 24 * 7
    MONTH = 24 * 30

    @property
    def hours(self) -> int:
        return self.value


# ---------------------------------------------------------------------------
# WorldClock
# ---------------------------------------------------------------------------

class WorldClock:
    """
    The single source of truth for world time.

    Time is stored as one integer: total whole *minutes* elapsed since
    world start. Hour/day/week/month are computed properties derived
    from that integer, so they can never drift out of sync with each
    other -- there is exactly one number to advance.

    Minutes, not hours, are the canonical unit specifically so that
    per-minute advances (see story_integration.py's advance_turn(),
    which ticks the clock forward one minute at a time as the player
    takes turns) always land on a whole number. Storing whole hours
    instead used to mean minute-sized advances either got silently
    dropped or produced a fractional value that broke the ":02d" time
    readout in game.py's render() -- the clock only ever "safely" moved
    in hour-sized jumps as a result.
    """

    _MINUTES_PER_HOUR = 60

    def __init__(self, start_hour: int = 0):
        self._total_minutes: int = start_hour * self._MINUTES_PER_HOUR

    # -- getters (computed, never stored) ----------------------------------

    @property
    def total_minutes(self) -> int:
        return self._total_minutes

    @property
    def total_hours(self) -> int:
        return self._total_minutes // self._MINUTES_PER_HOUR

    @property
    def minute_of_hour(self) -> int:
        return self._total_minutes % self._MINUTES_PER_HOUR

    @property
    def hour_of_day(self) -> int:
        return self.total_hours % TimeUnit.DAY.hours

    @property
    def day(self) -> int:
        return self.total_hours // TimeUnit.DAY.hours

    @property
    def week(self) -> int:
        return self.total_hours // TimeUnit.WEEK.hours

    @property
    def month(self) -> int:
        return self.total_hours // TimeUnit.MONTH.hours

    # -- advancing ------------------------------------------------------------

    def advance(self, amount: int, unit: TimeUnit = TimeUnit.HOUR) -> int:
        """
        Move the clock forward by `amount` of `unit`. Returns the new
        total_hours (whole hours -- so TimeScheduler and the TIME_PASSED
        trigger, which both key off hours, never see a fractional value
        even when `unit` is TimeUnit.MINUTE). This is the only method
        that changes world time -- everything else on this class is
        read-only.
        """
        if amount < 0:
            raise ValueError("WorldClock cannot advance by a negative amount")
        # round() absorbs the tiny float error from unit.hours (e.g.
        # TimeUnit.MINUTE is 1/60) so total_minutes always stays a
        # clean integer instead of drifting by fractions of a minute.
        self._total_minutes += round(amount * unit.hours * self._MINUTES_PER_HOUR)
        return self.total_hours

    def __repr__(self) -> str:
        return (
            f"WorldClock(day={self.day}, hour={self.hour_of_day}, minute={self.minute_of_hour}, "
            f"total_hours={self.total_hours})"
        )


# ---------------------------------------------------------------------------
# ScheduledEvent
# ---------------------------------------------------------------------------

class ScheduledEvent:
    """
    One queued piece of story evolution: a callback due to run at a
    specific absolute world hour.

    Set `recurring_hours` for events that should keep happening (e.g. a
    crop advancing a growth stage every 48 hours) -- after the callback
    runs, TimeScheduler re-inserts the event with a new `fire_at` rather
    than dropping it. One-shot events (a corpse finally decaying away)
    leave `recurring_hours` as None and are discarded after running.
    """

    #: Tie-breaker counter so events with an identical fire_at hour still
    #: compare deterministically in the heap (heapq needs a total order).
    _id_counter = itertools.count()

    def __init__(
        self,
        fire_at: int,
        callback: Callable[["WorldTimeManager"], None],
        recurring_hours: Optional[int] = None,
        event_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.fire_at: int = fire_at
        self.callback = callback
        self.recurring_hours: Optional[int] = recurring_hours
        self.id: str = event_id or f"event:{next(self._id_counter)}"
        self.data: Dict[str, Any] = data if data is not None else {}
        self._tiebreak: int = next(self._id_counter)

    @property
    def is_recurring(self) -> bool:
        return self.recurring_hours is not None

    def rescheduled(self) -> "ScheduledEvent":
        """Return a copy of this event moved forward by its recurrence
        interval, for re-insertion after firing."""
        return ScheduledEvent(
            fire_at=self.fire_at + self.recurring_hours,
            callback=self.callback,
            recurring_hours=self.recurring_hours,
            event_id=self.id,
            data=self.data,
        )

    def __lt__(self, other: "ScheduledEvent") -> bool:
        return (self.fire_at, self._tiebreak) < (other.fire_at, other._tiebreak)

    def __repr__(self) -> str:
        return f"ScheduledEvent(id={self.id!r}, fire_at={self.fire_at}, recurring={self.is_recurring})"


# ---------------------------------------------------------------------------
# TimeScheduler
# ---------------------------------------------------------------------------

class TimeScheduler:
    """
    Priority queue of ScheduledEvents, ordered by absolute fire hour.

    Only events that are actually due get popped and run on any given
    advance -- world evolution cost scales with "how many things are
    about to happen", not with "how many things exist in the world".
    """

    def __init__(self):
        self._heap: list = []
        self._cancelled: set = set()

    # -- scheduling -----------------------------------------------------------

    def schedule_at(self, fire_at: int, callback, recurring_hours: Optional[int] = None,
                     event_id: Optional[str] = None, **data: Any) -> ScheduledEvent:
        """Schedule `callback` to run at absolute hour `fire_at`."""
        event = ScheduledEvent(fire_at, callback, recurring_hours, event_id, data)
        heapq.heappush(self._heap, event)
        return event

    def schedule_in(self, clock: WorldClock, amount: int, unit: TimeUnit, callback,
                     recurring: Optional[int] = None, recurring_unit: TimeUnit = TimeUnit.HOUR,
                     event_id: Optional[str] = None, **data: Any) -> ScheduledEvent:
        """
        Schedule `callback` to run `amount` of `unit` from the clock's
        current time. Convenience wrapper around `schedule_at` for the
        common "N hours/days/weeks/months from now" case.
        """
        fire_at = clock.total_hours + amount * unit.hours
        recurring_hours = recurring * recurring_unit.hours if recurring is not None else None
        return self.schedule_at(fire_at, callback, recurring_hours, event_id, **data)

    def cancel(self, event_id: str) -> None:
        """Prevent a still-pending event from running. Cheap tombstone
        approach -- the event is skipped when popped rather than
        searched for and removed from the heap immediately."""
        self._cancelled.add(event_id)

    # -- running due events -----------------------------------------------------

    def run_due(self, current_hour: int, manager: "WorldTimeManager") -> int:
        """
        Pop and run every event with `fire_at <= current_hour`, in
        chronological order. Recurring events are re-inserted with their
        next fire time. Returns how many events actually ran.
        """
        ran = 0
        while self._heap and self._heap[0].fire_at <= current_hour:
            event = heapq.heappop(self._heap)
            if event.id in self._cancelled:
                self._cancelled.discard(event.id)
                continue

            event.callback(manager, event)
            ran += 1

            if event.is_recurring:
                heapq.heappush(self._heap, event.rescheduled())

        return ran

    def __len__(self) -> int:
        return len(self._heap)

    def __repr__(self) -> str:
        return f"TimeScheduler(pending={len(self._heap)})"


# ---------------------------------------------------------------------------
# WorldTimeManager
# ---------------------------------------------------------------------------

class WorldTimeManager:
    """
    Glues WorldClock + TimeScheduler + TriggerSystem together behind a
    single entry point: `advance()`.

    Gameplay code (resting at a campfire, traveling, sleeping at an inn)
    never touches WorldClock or TimeScheduler directly -- it calls
    `WorldTimeManager.advance(amount, unit)` and everything downstream
    (running due story-evolution events, notifying stories) happens
    automatically.
    """

    def __init__(self, trigger_system: Optional[TriggerSystem] = None, start_hour: int = 7):
        self.clock: WorldClock = WorldClock(start_hour)
        self.scheduler: TimeScheduler = TimeScheduler()
        # Shared with StoryManager when one is available, so scheduled
        # events (corpse decay, bandit relocation, ...) reach the same
        # TriggerRules that gameplay-driven events do. Falls back to an
        # owned TriggerSystem so this module works standalone.
        self.trigger_system: TriggerSystem = trigger_system or TriggerSystem()

    def advance(self, amount: int, unit: TimeUnit = TimeUnit.HOUR) -> int:
        """
        Advance world time and let it evolve the world.

        1. Moves the clock forward.
        2. Runs every ScheduledEvent now due, in order.
        3. Fires a generic TIME_PASSED trigger so stage-gated TriggerRules
           (Phase 6) can react without needing a bespoke trigger type.

        Returns the new total_hours.
        """
        previous_hour = self.clock.total_hours
        new_hour = self.clock.advance(amount, unit)

        self.scheduler.run_due(new_hour, self)

        self.trigger_system.fire(
            TriggerType.TIME_PASSED,
            hours_elapsed=new_hour - previous_hour,
            total_hours=new_hour,
            day=self.clock.day,
            unit=unit.name,
        )
        return new_hour

    def __repr__(self) -> str:
        return f"WorldTimeManager(clock={self.clock!r}, {self.scheduler!r})"


# ---------------------------------------------------------------------------
# Example story-evolution systems
# ---------------------------------------------------------------------------
# These are *examples* of the content layer this framework enables -- thin
# registration functions that schedule a callback and fire a specific
# trigger when it runs. They carry no dialogue/clue text, mirroring how
# story_object.py's subclasses carry no narrative content either. Real
# content systems would live in their own module(s); they're inlined here
# just to demonstrate the intended usage pattern end to end.

def schedule_npc_missing(manager: WorldTimeManager, npc: Any, hours: int) -> ScheduledEvent:
    """An NPC who hasn't checked in becomes "missing" after `hours`."""
    def _fire(mgr: WorldTimeManager, event: ScheduledEvent) -> None:
        mgr.trigger_system.fire(TriggerType.NPC_WENT_MISSING, target=npc)

    return manager.scheduler.schedule_in(manager.clock, hours, TimeUnit.HOUR, _fire)


def schedule_corpse_decay(manager: WorldTimeManager, corpse: Any, days: int = 3) -> ScheduledEvent:
    """A corpse fully decays (and can be despawned/replaced with a
    bones/blood marker by whoever handles the trigger) after `days`."""
    def _fire(mgr: WorldTimeManager, event: ScheduledEvent) -> None:
        mgr.trigger_system.fire(TriggerType.CORPSE_DECAYED, target=corpse)

    return manager.scheduler.schedule_in(manager.clock, days, TimeUnit.DAY, _fire)


def schedule_camp_abandonment(manager: WorldTimeManager, camp: Any, weeks: int = 1) -> ScheduledEvent:
    """An unvisited camp is abandoned/cleared after `weeks` of inactivity."""
    def _fire(mgr: WorldTimeManager, event: ScheduledEvent) -> None:
        mgr.trigger_system.fire(TriggerType.CAMP_ABANDONED, target=camp)

    return manager.scheduler.schedule_in(manager.clock, weeks, TimeUnit.WEEK, _fire)


def schedule_bandit_relocation(manager: WorldTimeManager, bandit_group: Any,
                                recheck_days: int = 2) -> ScheduledEvent:
    """
    Bandits periodically reconsider their camp (e.g. after being raided,
    or on a patrol cycle). Recurring: fires every `recheck_days` for as
    long as the group exists. Whoever handles CAMP relocation decides
    the new position; this only decides *when* to ask the question.
    """
    def _fire(mgr: WorldTimeManager, event: ScheduledEvent) -> None:
        mgr.trigger_system.fire(TriggerType.BANDITS_RELOCATED, target=bandit_group)

    return manager.scheduler.schedule_in(
        manager.clock, recheck_days, TimeUnit.DAY, _fire,
        recurring=recheck_days, recurring_unit=TimeUnit.DAY,
        event_id=f"bandit_relocate:{getattr(bandit_group, 'id', id(bandit_group))}",
    )


def schedule_building_burn(manager: WorldTimeManager, building: Any, hours_to_collapse: int = 6) -> ScheduledEvent:
    """A building set ablaze finishes burning down after `hours_to_collapse`."""
    def _fire(mgr: WorldTimeManager, event: ScheduledEvent) -> None:
        mgr.trigger_system.fire(TriggerType.BUILDING_BURNED, target=building)

    return manager.scheduler.schedule_in(manager.clock, hours_to_collapse, TimeUnit.HOUR, _fire)


def schedule_crop_growth(manager: WorldTimeManager, field: Any, stage_interval_days: int = 5,
                          total_stages: int = 4) -> ScheduledEvent:
    """
    Crops advance one growth stage every `stage_interval_days`, for
    `total_stages` total (e.g. sprout -> growing -> ripe -> harvestable).
    Recurring, but self-cancels once the final stage is reached.
    """
    field_id = f"crop_growth:{getattr(field, 'id', id(field))}"

    def _fire(mgr: WorldTimeManager, event: ScheduledEvent) -> None:
        current_stage = event.data.get("stage", 0) + 1
        event.data["stage"] = current_stage
        mgr.trigger_system.fire(TriggerType.CROP_GROWTH_STAGE, target=field, stage=current_stage)
        if current_stage >= total_stages:
            mgr.scheduler.cancel(field_id)

    return manager.scheduler.schedule_in(
        manager.clock, stage_interval_days, TimeUnit.DAY, _fire,
        recurring=stage_interval_days, recurring_unit=TimeUnit.DAY,
        event_id=field_id, stage=0,
    )