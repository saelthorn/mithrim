"""
faction_system.py

Phase 8 -- Faction & Reputation System.

Provides a scalable, data-driven faction and reputation system: a
registry of FactionDefinitions (Kingdom, Church, Merchants, Bandits,
Mages, Cultists, Orcs, Goblins, Necromancers, ...), a FactionManager
that tracks the player's standing with each of them, and the derived
NPC-reaction and trading behavior that standing should produce.

This is framework only. It contains no dialogue or quest content --
factions declare thresholds and relations as plain data, and the
manager only ever answers "what reputation is this", "what level does
that correspond to", "how should an NPC react", and "what should this
cost". What an NPC actually *says*, or which quest a reputation change
unlocks, is decided by content systems and stories built on top of it.

Design summary
---------------
- ReputationLevel    : the shared vocabulary of standing tiers (Hated
                        through Exalted) every faction is measured in,
                        so gameplay code never has to special-case a
                        faction's own scale.
- FactionDefinition  : a faction's static data -- reputation range,
                        level thresholds, relations to other factions,
                        and optional trading/reaction overrides. Purely
                        data; no logic beyond small lookups.
- FACTION_REGISTRY   : `register_faction(...)` adds a new faction with
                        no changes to this module or FactionManager --
                        new factions are additive, not edits.
- NPCReaction        : the derived reaction (attitude, will it trade,
                        will it attack on sight, greeting tag) for an
                        NPC of a given faction given the player's
                        current standing.
- FactionManager     : owns the player's live reputation with every
                        faction, applies deltas (with clamping and
                        relation propagation), computes NPCReaction and
                        trade price multipliers, and fires reputation-
                        change events other systems can subscribe to.
- faction_level_condition(...): a convenience builder that produces a
                        condition_system.py FactionReputationCondition
                        pre-filled from a faction's own threshold table,
                        so story requirements read as "friendly with
                        the Church" rather than a bare numeric compare.

Relationship to the rest of the framework:
- FactionManager.get_faction_reputation(faction_id) is the method a
  host's ConditionContext (condition_system.py) delegates to, so
  FactionReputationCondition -- and therefore TriggerRule and story
  requirements -- work against this system without any changes there.
- Gameplay code (talking to an NPC, opening a shop, a story stage
  granting/costing reputation) calls FactionManager.adjust_reputation(...);
  everything else (thresholds, relations, reactions, prices) follows
  from that one call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from story.condition_system import Comparator, Condition, FactionReputationCondition


# ---------------------------------------------------------------------------
# ReputationLevel
# ---------------------------------------------------------------------------

class ReputationLevel(Enum):
    """
    The shared standing tiers every faction is measured in. Individual
    factions map their own numeric range onto these via
    FactionDefinition.thresholds, so "Friendly" always means the same
    thing to gameplay code regardless of which faction it's asking about.
    """
    HATED = "hated"
    HOSTILE = "hostile"
    UNFRIENDLY = "unfriendly"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    HONORED = "honored"
    EXALTED = "exalted"


#: Low -> high ordering, used for comparisons ("is at least Friendly") and
#: for resolving which threshold a raw value currently satisfies.
REPUTATION_LEVEL_ORDER: List[ReputationLevel] = [
    ReputationLevel.HATED,
    ReputationLevel.HOSTILE,
    ReputationLevel.UNFRIENDLY,
    ReputationLevel.NEUTRAL,
    ReputationLevel.FRIENDLY,
    ReputationLevel.HONORED,
    ReputationLevel.EXALTED,
]


def _level_rank(level: ReputationLevel) -> int:
    return REPUTATION_LEVEL_ORDER.index(level)


#: Standard symmetric threshold curve most factions can just reuse.
#: A faction only needs its own `thresholds` when it should feel
#: different by default (e.g. Cultists starting distrustful of
#: outsiders, or Bandits being unusually easy to win over).
DEFAULT_THRESHOLDS: Dict[ReputationLevel, float] = {
    ReputationLevel.HATED: -100.0,
    ReputationLevel.HOSTILE: -70.0,
    ReputationLevel.UNFRIENDLY: -30.0,
    ReputationLevel.NEUTRAL: 0.0,
    ReputationLevel.FRIENDLY: 30.0,
    ReputationLevel.HONORED: 70.0,
    ReputationLevel.EXALTED: 90.0,
}

#: Standard price multiplier curve (applied to buy prices; sell prices
#: can use the inverse). 1.0 is a neutral, undiscounted price.
DEFAULT_PRICE_MODIFIERS: Dict[ReputationLevel, float] = {
    ReputationLevel.HATED: 2.0,
    ReputationLevel.HOSTILE: 1.5,
    ReputationLevel.UNFRIENDLY: 1.2,
    ReputationLevel.NEUTRAL: 1.0,
    ReputationLevel.FRIENDLY: 0.9,
    ReputationLevel.HONORED: 0.8,
    ReputationLevel.EXALTED: 0.65,
}


# ---------------------------------------------------------------------------
# NPCReaction
# ---------------------------------------------------------------------------

@dataclass
class NPCReaction:
    """
    The derived reaction an NPC of a given faction should have towards
    the player right now. Content systems (dialogue, AI) read this
    rather than reputation numbers directly, so tuning what "Hostile"
    means (attacks on sight vs. just refuses to trade) happens here,
    once, instead of being re-decided at every call site.
    """
    faction_id: str
    level: ReputationLevel
    reputation: float
    will_trade: bool
    will_offer_quests: bool
    attacks_on_sight: bool
    guards_alerted: bool
    price_multiplier: float
    greeting_tag: str

    def __repr__(self) -> str:
        return f"NPCReaction(faction={self.faction_id!r}, level={self.level.value})"


# ---------------------------------------------------------------------------
# FactionDefinition
# ---------------------------------------------------------------------------

@dataclass
class FactionDefinition:
    """
    Static description of one faction. Everything here is plain data --
    adding a faction never requires touching FactionManager or any
    other faction's definition.

    `relations` lets standing with one faction ripple into another
    (helping the Bandits costs you favor with the Kingdom, aiding the
    Church helps the Mages a little, ...). A positive value means the
    related faction's reputation moves the *same* direction as this
    one's delta (allied); negative means it moves the *opposite*
    direction (opposed). The magnitude is a fraction of the original
    delta applied to the related faction.
    """
    id: str
    display_name: str
    min_reputation: float = -100.0
    max_reputation: float = 100.0
    default_reputation: float = 0.0
    thresholds: Dict[ReputationLevel, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    price_modifiers: Dict[ReputationLevel, float] = field(default_factory=lambda: dict(DEFAULT_PRICE_MODIFIERS))
    # faction_id -> propagation weight, see class docstring.
    relations: Dict[str, float] = field(default_factory=dict)
    # Whether NPCs of this faction attack on sight while Hostile/Hated.
    hostile_is_violent: bool = True

    def clamp(self, value: float) -> float:
        return max(self.min_reputation, min(self.max_reputation, value))

    def level_for(self, value: float) -> ReputationLevel:
        """Highest ReputationLevel whose threshold `value` meets or exceeds."""
        current = ReputationLevel.NEUTRAL
        for level in REPUTATION_LEVEL_ORDER:
            threshold = self.thresholds.get(level)
            if threshold is not None and value >= threshold:
                current = level
        return current

    def threshold_for(self, level: ReputationLevel) -> Optional[float]:
        return self.thresholds.get(level)

    def price_multiplier_for(self, value: float) -> float:
        level = self.level_for(value)
        return self.price_modifiers.get(level, DEFAULT_PRICE_MODIFIERS[level])

    def is_at_least(self, value: float, level: ReputationLevel) -> bool:
        return _level_rank(self.level_for(value)) >= _level_rank(level)

    def is_friendly(self, value: float) -> bool:
        return self.is_at_least(value, ReputationLevel.FRIENDLY)

    def is_hostile(self, value: float) -> bool:
        return _level_rank(self.level_for(value)) <= _level_rank(ReputationLevel.HOSTILE)

    def __repr__(self) -> str:
        return f"FactionDefinition(id={self.id!r}, display_name={self.display_name!r})"


# ---------------------------------------------------------------------------
# Registry -- new factions register here, nowhere else needs to change
# ---------------------------------------------------------------------------

FACTION_REGISTRY: Dict[str, FactionDefinition] = {}


def register_faction(definition: FactionDefinition) -> FactionDefinition:
    """
    Add (or replace) a faction definition in the shared registry. This
    is the only step required to introduce a new faction -- FactionManager,
    NPCReaction, and story requirements all work from this registry, so
    none of them need editing when a faction is added later.
    """
    FACTION_REGISTRY[definition.id] = definition
    return definition


def get_faction_definition(faction_id: str) -> FactionDefinition:
    definition = FACTION_REGISTRY.get(faction_id)
    if definition is None:
        raise KeyError(f"Unknown faction: {faction_id!r}")
    return definition


def define_faction(
    faction_id: str,
    display_name: str,
    *,
    default_reputation: float = 0.0,
    thresholds: Optional[Dict[ReputationLevel, float]] = None,
    price_modifiers: Optional[Dict[ReputationLevel, float]] = None,
    relations: Optional[Dict[str, float]] = None,
    hostile_is_violent: bool = True,
    min_reputation: float = -100.0,
    max_reputation: float = 100.0,
) -> FactionDefinition:
    """
    Convenience wrapper around FactionDefinition + register_faction for
    the common case of "mostly default curve, a few overrides". This is
    how every faction below is declared, and how future ones should be
    declared too.
    """
    definition = FactionDefinition(
        id=faction_id,
        display_name=display_name,
        min_reputation=min_reputation,
        max_reputation=max_reputation,
        default_reputation=default_reputation,
        thresholds=dict(thresholds) if thresholds else dict(DEFAULT_THRESHOLDS),
        price_modifiers=dict(price_modifiers) if price_modifiers else dict(DEFAULT_PRICE_MODIFIERS),
        relations=dict(relations) if relations else {},
        hostile_is_violent=hostile_is_violent,
    )
    return register_faction(definition)


# ---------------------------------------------------------------------------
# Default factions
# ---------------------------------------------------------------------------
# Each entry is additive: removing or editing one does not require
# touching any other, and adding an entirely new faction later (e.g. a
# Sea Raiders or Fey Court faction) is done the exact same way.

define_faction(
    "kingdom", "The Kingdom",
    relations={"bandits": -0.5, "orcs": -0.3, "necromancers": -0.5},
)

define_faction(
    "church", "The Church",
    relations={"cultists": -0.6, "necromancers": -0.6, "mages": -0.2},
)

define_faction(
    "merchants", "The Merchant Guilds",
    relations={"bandits": -0.4},
)

define_faction(
    "bandits", "The Bandits",
    # Bandits distrust everyone by default and are quicker to turn violent.
    default_reputation=-10.0,
    relations={"kingdom": -0.3, "merchants": -0.2},
)

define_faction(
    "mages", "The Mage Circle",
    relations={"church": -0.1, "necromancers": -0.4},
)

define_faction(
    "cultists", "The Cult",
    # Outsiders start distrusted; standard curve is too forgiving for them.
    default_reputation=-20.0,
    thresholds={
        ReputationLevel.HATED: -100.0,
        ReputationLevel.HOSTILE: -60.0,
        ReputationLevel.UNFRIENDLY: -20.0,
        ReputationLevel.NEUTRAL: -10.0,
        ReputationLevel.FRIENDLY: 20.0,
        ReputationLevel.HONORED: 60.0,
        ReputationLevel.EXALTED: 85.0,
    },
    relations={"church": -0.6, "necromancers": 0.3},
)

define_faction(
    "orcs", "The Orc Clans",
    relations={"goblins": 0.3, "kingdom": -0.2},
)

define_faction(
    "goblins", "The Goblin Warrens",
    relations={"orcs": 0.3},
)

define_faction(
    "necromancers", "The Necromancers",
    default_reputation=-15.0,
    relations={"church": -0.6, "kingdom": -0.4, "cultists": 0.3},
)


# ---------------------------------------------------------------------------
# FactionReputationChangedEvent
# ---------------------------------------------------------------------------

class FactionReputationChangedEvent:
    """Payload passed to FactionManager listeners whenever a faction's
    reputation actually changes (including changes from propagation)."""

    def __init__(
        self,
        faction_id: str,
        old_value: float,
        new_value: float,
        old_level: ReputationLevel,
        new_level: ReputationLevel,
        source: Any = None,
    ):
        self.faction_id = faction_id
        self.old_value = old_value
        self.new_value = new_value
        self.old_level = old_level
        self.new_level = new_level
        self.source = source
        self.timestamp: float = time.time()

    @property
    def level_changed(self) -> bool:
        return self.old_level != self.new_level

    def __repr__(self) -> str:
        return (
            f"FactionReputationChangedEvent(faction={self.faction_id!r}, "
            f"{self.old_value:.1f}->{self.new_value:.1f}, "
            f"level={self.old_level.value}->{self.new_level.value})"
        )


# ---------------------------------------------------------------------------
# FactionManager
# ---------------------------------------------------------------------------

class FactionManager:
    """
    Owns the player's live reputation with every registered faction.

    Unknown factions are lazily initialized from FACTION_REGISTRY the
    first time they're touched, so a save file created before a new
    faction existed still works -- the new faction simply starts at its
    definition's default_reputation the first time it's queried.
    """

    def __init__(self):
        self._reputation: Dict[str, float] = {}
        self._listeners: List[Callable[[FactionReputationChangedEvent], None]] = []

    # -- subscription ---------------------------------------------------------

    def subscribe(self, callback: Callable[[FactionReputationChangedEvent], None]) -> None:
        """Listen for every reputation change, across every faction."""
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[FactionReputationChangedEvent], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    # -- reading ----------------------------------------------------------------

    def get_faction_reputation(self, faction_id: str) -> float:
        """
        Current reputation with `faction_id`. Named to match
        condition_system.py's ConditionContext protocol directly -- a
        host's ConditionContext can simply delegate this method to a
        FactionManager instance.
        """
        if faction_id not in self._reputation:
            definition = get_faction_definition(faction_id)
            self._reputation[faction_id] = definition.default_reputation
        return self._reputation[faction_id]

    def get_level(self, faction_id: str) -> ReputationLevel:
        definition = get_faction_definition(faction_id)
        return definition.level_for(self.get_faction_reputation(faction_id))

    def is_friendly(self, faction_id: str) -> bool:
        definition = get_faction_definition(faction_id)
        return definition.is_friendly(self.get_faction_reputation(faction_id))

    def is_hostile(self, faction_id: str) -> bool:
        definition = get_faction_definition(faction_id)
        return definition.is_hostile(self.get_faction_reputation(faction_id))

    def meets_requirement(self, faction_id: str, min_level: ReputationLevel) -> bool:
        """Whether the player is at least `min_level` with `faction_id` --
        the check most story requirements and dialogue gates actually want."""
        definition = get_faction_definition(faction_id)
        return definition.is_at_least(self.get_faction_reputation(faction_id), min_level)

    # -- reactions & trading ------------------------------------------------------

    def get_npc_reaction(self, faction_id: str) -> NPCReaction:
        """Derive how an NPC belonging to `faction_id` should currently
        treat the player."""
        definition = get_faction_definition(faction_id)
        reputation = self.get_faction_reputation(faction_id)
        level = definition.level_for(reputation)
        rank = _level_rank(level)

        is_hostile = rank <= _level_rank(ReputationLevel.HOSTILE)
        is_unfriendly_or_worse = rank <= _level_rank(ReputationLevel.UNFRIENDLY)

        return NPCReaction(
            faction_id=faction_id,
            level=level,
            reputation=reputation,
            will_trade=not is_hostile,
            will_offer_quests=rank >= _level_rank(ReputationLevel.NEUTRAL),
            attacks_on_sight=is_hostile and definition.hostile_is_violent,
            guards_alerted=is_unfriendly_or_worse,
            price_multiplier=definition.price_multiplier_for(reputation),
            greeting_tag=level.value,
        )

    def get_trade_modifier(self, faction_id: str) -> float:
        """Buy-price multiplier for a merchant of this faction. A sell
        price can use `1.0 / max(modifier, epsilon)` to stay symmetric."""
        definition = get_faction_definition(faction_id)
        return definition.price_multiplier_for(self.get_faction_reputation(faction_id))

    # -- writing ----------------------------------------------------------------

    def set_reputation(self, faction_id: str, value: float, source: Any = None) -> None:
        """Set reputation directly (e.g. loading a save, a scripted
        story event forcing a specific standing). Still clamps and
        fires change events; does not propagate to related factions."""
        definition = get_faction_definition(faction_id)
        self._apply(faction_id, definition.clamp(value), source)

    def adjust_reputation(
        self,
        faction_id: str,
        delta: float,
        source: Any = None,
        propagate: bool = True,
    ) -> Dict[str, float]:
        """
        Apply `delta` to `faction_id`'s reputation, then, if `propagate`
        is set, ripple a fraction of that delta into every faction it
        has a relation with (allies move with it, rivals move against
        it). Returns a dict of every faction_id -> new reputation that
        actually changed, including the primary one.

        Propagation is single-hop by design: an ally-of-an-ally does not
        automatically move too. Chained relationships are something a
        content system can layer on top (e.g. via its own listener) if
        a specific story wants that -- this stays simple and predictable.
        """
        definition = get_faction_definition(faction_id)
        old_value = self.get_faction_reputation(faction_id)
        new_value = definition.clamp(old_value + delta)
        changed: Dict[str, float] = {}

        if new_value != old_value:
            self._apply(faction_id, new_value, source)
            changed[faction_id] = new_value

        if propagate:
            for related_id, weight in definition.relations.items():
                if related_id not in FACTION_REGISTRY:
                    continue
                related_delta = delta * weight
                if related_delta == 0:
                    continue
                related_definition = get_faction_definition(related_id)
                related_old = self.get_faction_reputation(related_id)
                related_new = related_definition.clamp(related_old + related_delta)
                if related_new != related_old:
                    self._apply(related_id, related_new, source)
                    changed[related_id] = related_new

        return changed

    def _apply(self, faction_id: str, new_value: float, source: Any) -> None:
        definition = get_faction_definition(faction_id)
        old_value = self.get_faction_reputation(faction_id)
        old_level = definition.level_for(old_value)
        new_level = definition.level_for(new_value)

        self._reputation[faction_id] = new_value

        event = FactionReputationChangedEvent(
            faction_id=faction_id,
            old_value=old_value,
            new_value=new_value,
            old_level=old_level,
            new_level=new_level,
            source=source,
        )
        for callback in self._listeners:
            callback(event)

    # -- serialization ------------------------------------------------------------

    def to_dict(self) -> Dict[str, float]:
        return dict(self._reputation)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "FactionManager":
        manager = cls()
        for faction_id, value in data.items():
            if faction_id in FACTION_REGISTRY:
                manager._reputation[faction_id] = get_faction_definition(faction_id).clamp(value)
        return manager

    def __repr__(self) -> str:
        return f"FactionManager(tracked={len(self._reputation)})"


# ---------------------------------------------------------------------------
# Story requirement helper
# ---------------------------------------------------------------------------

def faction_level_condition(
    faction_id: str,
    min_level: ReputationLevel,
    comparator: Comparator = Comparator.GTE,
) -> Condition:
    """
    Build a condition_system.py FactionReputationCondition pre-filled
    with `faction_id`'s own threshold for `min_level`, so a story's
    requirement can read as "at least Friendly with the Church" instead
    of a bare, faction-agnostic numeric compare. Works unmodified with
    TriggerRule.condition and every other Condition consumer, since the
    result is a plain Condition.
    """
    definition = get_faction_definition(faction_id)
    threshold = definition.threshold_for(min_level)
    if threshold is None:
        raise ValueError(f"Faction {faction_id!r} has no threshold defined for {min_level!r}")
    return FactionReputationCondition(faction=faction_id, value=threshold, comparator=comparator)