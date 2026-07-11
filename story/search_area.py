"""
search_area.py

Phase 4 -- Story Areas.

Provides SearchArea: the bounded, deterministically-generated investigation
zone that every StoryInstance owns exactly one of.

This is framework only. It contains no story content, quests, dialogue,
NPC personalities, or procedural writing -- those belong to content
modules built on top of this framework in later phases. This module only
answers "where is the story physically happening, what bounds does it
have, and what generic objects live inside it."

Design summary
---------------
- AreaObject   : a lightweight, content-agnostic container for anything
                 placed inside an area (a wagon, a corpse, an NPC, a clue,
                 ...). It carries a type tag and a freeform data dict, but
                 no behavior -- what an "NPC" or "clue" actually *does* is
                 entirely up to systems built on top of this framework.
- SearchArea   : the bounded zone itself. Owns object storage, a spatial
                 grid index for fast proximity queries, containment
                 checks, and deterministic generation/reset/clear.

Determinism: SearchArea is seeded (defaulting to derived from the owning
story's seed if not given explicitly). All procedural placement added in
later phases should draw from `SearchArea.rng` so the same seed always
reproduces the same area.
"""

from __future__ import annotations

import random
import time
import uuid
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple


Position = Tuple[float, float]


# ---------------------------------------------------------------------------
# Enums / presets
# ---------------------------------------------------------------------------

class AreaState(Enum):
    """Lifecycle state of a SearchArea."""
    UNGENERATED = "ungenerated"
    GENERATED = "generated"
    ACTIVE = "active"
    INACTIVE = "inactive"


# Named size presets requested by design. `custom` sizes are supported by
# simply passing any (width, height) directly to SearchArea's constructor
# or generate() -- this dict is a convenience, not a restriction.
AREA_SIZE_PRESETS: Dict[str, Tuple[int, int]] = {
    "small": (35, 35),
    "medium": (50, 50),
    "large": (75, 75),
}

# Spatial grid cell size used for the proximity index. Objects are bucketed
# into cells of this size so `query_nearby` only has to scan nearby cells
# instead of every object in the area.
DEFAULT_GRID_CELL_SIZE: float = 10.0


# ---------------------------------------------------------------------------
# AreaObject
# ---------------------------------------------------------------------------

class AreaObject:
    """
    A generic, content-agnostic object placed inside a SearchArea.

    Examples of `object_type` tags future systems might use: "wagon",
    "camp", "corpse", "blood", "clue", "npc", "tracks", "container",
    "prop". This class does not care which tags exist or what they mean --
    it only stores identity, type, position, and freeform data.
    """

    def __init__(
        self,
        object_type: str,
        position: Position,
        object_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.id: str = object_id or str(uuid.uuid4())
        self.object_type: str = object_type
        self.position: Position = position
        self.data: Dict[str, Any] = data if data is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "object_type": self.object_type,
            "position": list(self.position),
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AreaObject":
        pos = data.get("position", [0, 0])
        return cls(
            object_type=data["object_type"],
            position=(pos[0], pos[1]),
            object_id=data.get("id"),
            data=dict(data.get("data", {})),
        )

    def __repr__(self) -> str:
        return f"AreaObject(id={self.id!r}, type={self.object_type!r}, pos={self.position})"


# ---------------------------------------------------------------------------
# SearchArea
# ---------------------------------------------------------------------------

class SearchArea:
    """
    A bounded investigation zone owned by exactly one StoryInstance.

    Responsibilities:
    - Own a deterministic seed and derived RNG for procedural placement.
    - Define bounds (center + width/height) and answer containment checks.
    - Store AreaObjects, tagged by type, with a spatial index for fast
      proximity queries.
    - Track its own lifecycle (ungenerated / generated / active / inactive)
      independently of story progression logic, which lives in
      StoryDirector.

    Anything outside `bounds` is considered inactive space -- the
    framework never places or tracks objects outside the area.
    """

    def __init__(
        self,
        story_id: str,
        center: Position = (0.0, 0.0),
        size: Tuple[int, int] = AREA_SIZE_PRESETS["medium"],
        seed: Optional[int] = None,
        area_id: Optional[str] = None,
        grid_cell_size: float = DEFAULT_GRID_CELL_SIZE,
    ):
        self.id: str = area_id or str(uuid.uuid4())
        self.story_id: str = story_id
        self.seed: int = seed if seed is not None else random.randrange(2 ** 32)
        self.rng: random.Random = random.Random(self.seed)

        self.center: Position = center
        self.width: int
        self.height: int
        self.width, self.height = size
        self.radius: float = max(self.width, self.height) / 2.0
        self.bounds: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self._recompute_bounds()

        self.state: AreaState = AreaState.UNGENERATED
        self.active: bool = False
        self.discovered: bool = False
        self.generated: bool = False

        # Objects keyed by their own id, plus a secondary index by type so
        # `get_objects_by_type` doesn't need a linear scan.
        self._objects: Dict[str, AreaObject] = {}
        self._by_type: Dict[str, set] = {}

        # Spatial grid: (cell_x, cell_y) -> set of object ids. Used for
        # fast nearby-object queries instead of scanning every object.
        self._grid_cell_size: float = grid_cell_size
        self._grid: Dict[Tuple[int, int], set] = {}

        self.created_at: float = time.time()
        self.updated_at: float = self.created_at

    def _touch(self) -> None:
        self.updated_at = time.time()

    # -- bounds / sizing --------------------------------------------------

    def _recompute_bounds(self) -> None:
        cx, cy = self.center
        half_w, half_h = self.width / 2.0, self.height / 2.0
        self.bounds = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    def resize(self, size: Tuple[int, int]) -> None:
        """Change the area's width/height (e.g. switch between presets)."""
        self.width, self.height = size
        self.radius = max(self.width, self.height) / 2.0
        self._recompute_bounds()
        self._touch()

    def recenter(self, center: Position) -> None:
        """Move the area to a new center point, keeping its size."""
        self.center = center
        self._recompute_bounds()
        self._touch()

    # -- generation / clearing / reset -------------------------------------

    def generate(self, seed: Optional[int] = None) -> None:
        """
        Deterministically (re)generate the area from its seed. This
        framework method only establishes the RNG and marks the area as
        generated -- actual procedural placement (camps, clues, wildlife,
        terrain, ...) is performed by content systems built on top of
        this class, which should draw from `self.rng`.
        """
        if seed is not None:
            self.seed = seed
        self.rng = random.Random(self.seed)
        self.clear()
        self.generated = True
        self.state = AreaState.GENERATED
        self._touch()

    def clear(self) -> None:
        """Remove all objects from the area without changing its bounds,
        seed, or generated/active flags."""
        self._objects.clear()
        self._by_type.clear()
        self._grid.clear()
        self._touch()

    def reset(self, new_seed: Optional[int] = None) -> None:
        """
        Fully reset the area back to an ungenerated state, optionally
        re-seeding it. Equivalent to a fresh area at the same location
        and size.
        """
        if new_seed is not None:
            self.seed = new_seed
        self.rng = random.Random(self.seed)
        self.clear()
        self.generated = False
        self.discovered = False
        self.active = False
        self.state = AreaState.UNGENERATED
        self._touch()

    # -- containment --------------------------------------------------------

    def contains_point(self, position: Position) -> bool:
        """Whether `position` falls within this area's bounds (inclusive)."""
        x, y = position
        min_x, min_y, max_x, max_y = self.bounds
        return min_x <= x <= max_x and min_y <= y <= max_y

    def is_outside(self, position: Position) -> bool:
        """Convenience inverse of contains_point -- anything outside the
        area's bounds is considered inactive space."""
        return not self.contains_point(position)

    def clamp_to_bounds(self, position: Position) -> Position:
        """Clamp an arbitrary position to the nearest point inside bounds."""
        x, y = position
        min_x, min_y, max_x, max_y = self.bounds
        return (max(min_x, min(x, max_x)), max(min_y, min(y, max_y)))

    # -- spatial grid (internal) --------------------------------------------

    def _cell_of(self, position: Position) -> Tuple[int, int]:
        x, y = position
        size = self._grid_cell_size
        return (int(x // size), int(y // size))

    def _grid_add(self, obj: AreaObject) -> None:
        cell = self._cell_of(obj.position)
        self._grid.setdefault(cell, set()).add(obj.id)

    def _grid_remove(self, obj: AreaObject) -> None:
        cell = self._cell_of(obj.position)
        bucket = self._grid.get(cell)
        if bucket:
            bucket.discard(obj.id)
            if not bucket:
                del self._grid[cell]

    # -- object management ---------------------------------------------------

    def add_object(self, obj: AreaObject, clamp: bool = True) -> bool:
        """
        Add an AreaObject to the area. Returns False (and does not add
        the object) if its position falls outside the area's bounds and
        `clamp` is False -- the framework guarantees no story object
        exists outside its area.
        """
        if not self.contains_point(obj.position):
            if not clamp:
                return False
            obj.position = self.clamp_to_bounds(obj.position)

        self._objects[obj.id] = obj
        self._by_type.setdefault(obj.object_type, set()).add(obj.id)
        self._grid_add(obj)
        self._touch()
        return True

    def remove_object(self, object_id: str) -> bool:
        obj = self._objects.pop(object_id, None)
        if obj is None:
            return False

        type_bucket = self._by_type.get(obj.object_type)
        if type_bucket:
            type_bucket.discard(object_id)
            if not type_bucket:
                del self._by_type[obj.object_type]

        self._grid_remove(obj)
        self._touch()
        return True

    def move_object(self, object_id: str, new_position: Position, clamp: bool = True) -> bool:
        """Reposition an existing object, keeping the spatial index consistent."""
        obj = self._objects.get(object_id)
        if obj is None:
            return False

        if not self.contains_point(new_position):
            if not clamp:
                return False
            new_position = self.clamp_to_bounds(new_position)

        self._grid_remove(obj)
        obj.position = new_position
        self._grid_add(obj)
        self._touch()
        return True

    def get_object(self, object_id: str) -> Optional[AreaObject]:
        return self._objects.get(object_id)

    def get_objects_by_type(self, object_type: str) -> List[AreaObject]:
        ids = self._by_type.get(object_type, set())
        return [self._objects[object_id] for object_id in ids]

    def get_all_objects(self) -> List[AreaObject]:
        return list(self._objects.values())

    def object_types(self) -> List[str]:
        return list(self._by_type.keys())

    def object_count(self, object_type: Optional[str] = None) -> int:
        if object_type is None:
            return len(self._objects)
        return len(self._by_type.get(object_type, ()))

    # -- spatial queries ------------------------------------------------------

    def query_nearby(
        self,
        position: Position,
        radius: float,
        object_type: Optional[str] = None,
    ) -> List[AreaObject]:
        """
        Return every object within `radius` of `position`, optionally
        filtered to a single object_type. Uses the spatial grid to only
        scan candidate cells rather than every object in the area.
        """
        size = self._grid_cell_size
        cell_radius = int(radius // size) + 1
        cx, cy = self._cell_of(position)

        candidate_ids: set = set()
        for dx in range(-cell_radius, cell_radius + 1):
            for dy in range(-cell_radius, cell_radius + 1):
                bucket = self._grid.get((cx + dx, cy + dy))
                if bucket:
                    candidate_ids.update(bucket)

        results: List[AreaObject] = []
        radius_sq = radius * radius
        px, py = position
        for object_id in candidate_ids:
            obj = self._objects.get(object_id)
            if obj is None:
                continue
            if object_type is not None and obj.object_type != object_type:
                continue
            ox, oy = obj.position
            if (ox - px) ** 2 + (oy - py) ** 2 <= radius_sq:
                results.append(obj)

        return results

    # -- activation / discovery --------------------------------------------

    def activate(self) -> None:
        self.active = True
        self.state = AreaState.ACTIVE
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self.state = AreaState.INACTIVE
        self._touch()

    def discover(self) -> None:
        """Mark the area as found/known by the player, independent of
        whether it is currently active."""
        self.discovered = True
        self._touch()

    # -- validation ----------------------------------------------------------

    def validate(self) -> List[str]:
        """Check internal consistency. Empty list means valid."""
        problems: List[str] = []

        if not self.id:
            problems.append("SearchArea has no id.")
        if not self.story_id:
            problems.append("SearchArea has no story_id.")
        if self.width <= 0 or self.height <= 0:
            problems.append("width/height must be positive.")
        if not isinstance(self.state, AreaState):
            problems.append("state must be an AreaState.")

        for object_id, obj in self._objects.items():
            if object_id != obj.id:
                problems.append(f"Object key {object_id} does not match object.id {obj.id}.")
            if not self.contains_point(obj.position):
                problems.append(f"Object {object_id} lies outside area bounds.")

        return problems

    def is_valid(self) -> bool:
        return not self.validate()

    # -- serialization ---------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "story_id": self.story_id,
            "seed": self.seed,
            "center": list(self.center),
            "width": self.width,
            "height": self.height,
            "state": self.state.value,
            "active": self.active,
            "discovered": self.discovered,
            "generated": self.generated,
            "grid_cell_size": self._grid_cell_size,
            "objects": [obj.to_dict() for obj in self._objects.values()],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchArea":
        center = data.get("center", [0.0, 0.0])
        area = cls(
            story_id=data["story_id"],
            center=(center[0], center[1]),
            size=(data.get("width", 50), data.get("height", 50)),
            seed=data.get("seed"),
            area_id=data.get("id"),
            grid_cell_size=data.get("grid_cell_size", DEFAULT_GRID_CELL_SIZE),
        )
        area.state = AreaState(data.get("state", AreaState.UNGENERATED.value))
        area.active = data.get("active", False)
        area.discovered = data.get("discovered", False)
        area.generated = data.get("generated", False)
        area.created_at = data.get("created_at", time.time())
        area.updated_at = data.get("updated_at", area.created_at)

        for object_data in data.get("objects", []):
            area.add_object(AreaObject.from_dict(object_data), clamp=False)

        return area

    def __repr__(self) -> str:
        return (
            f"SearchArea(id={self.id!r}, story_id={self.story_id!r}, "
            f"size={self.width}x{self.height}, state={self.state.value}, "
            f"objects={len(self._objects)})"
        )