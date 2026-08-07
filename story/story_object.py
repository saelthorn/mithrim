"""
story_object.py

Phase 5 -- Story Objects.

Provides StoryObject: the base class for world objects that belong to a
story and drive its progression when the player interacts with them
(wagons, corpses, campfires, journals, tracks, shrines, ...).

This is framework only. Subclasses below exist to give each object type
a distinct, filterable class/tag -- they carry no narrative content,
dialogue, or clue text. What actually gets unlocked on interaction
(clues, dialogue, objectives, events) is decided by content systems built
on top of StoryDirector's hooks, not by this module.

Design summary
---------------
- StoryObject       : an AreaObject (so it plugs directly into SearchArea)
                       that additionally knows its owning story_id and its
                       own one-shot/repeatable interaction state.
- Subclasses         : Wagon, Corpse, Campfire, Tent, Tracks, Shrine, Cage,
                        Journal, Banner, Blood, Grave -- each just fixes
                        the object_type tag AreaObject already supports.
                        No added behavior; new types are added the same
                        way.
- StoryManager hook  : `on_story_object_inspected(story_id, obj)` is the
                        single entry point a StoryObject calls into. All
                        progression logic (finding the right director,
                        advancing the story, emitting hooks) lives there,
                        not on the object.

Relationship to the rest of the framework:
- StoryObject -> AreaObject -> lives inside a SearchArea (Phase 4).
- StoryObject.inspect() -> StoryManager.on_story_object_inspected()
  -> StoryDirector.advance() (Phase 3), firing StoryEvent.STAGE_ADVANCED
  and StoryEvent.OBJECT_INSPECTED for later content systems to subscribe to.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from story.search_area import AreaObject, Position

if TYPE_CHECKING:
    from story.story_framework import StoryManager


# ---------------------------------------------------------------------------
# StoryObject (base class)
# ---------------------------------------------------------------------------

class StoryObject(AreaObject):
    """
    Base class for any world object tied to a story's progression.

    A StoryObject only knows two things beyond a plain AreaObject: which
    story it belongs to (`story_id`), and whether it has already been
    interacted with. It does not know how to advance a story, what clue
    text to show, or what dialogue to trigger -- it just reports the
    interaction to the StoryManager and lets that layer decide.

    `object_type` defaults to the class name in lowercase (e.g. "wagon"
    for the Wagon subclass) so subclasses don't need to repeat it.
    """

    #: Override in subclasses to set a fixed type tag; falls back to the
    #: class name (lowercased) when left as None.
    default_object_type: Optional[str] = None

    def __init__(
        self,
        story_id: str,
        position: Position,
        object_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        repeatable: bool = False,
    ):
        object_type = self.default_object_type or self.__class__.__name__.lower()
        super().__init__(
            object_type=object_type,
            position=position,
            object_id=object_id,
            data=data,
        )
        self.story_id: str = story_id
        self.repeatable: bool = repeatable
        self.interacted: bool = False
        self.interaction_count: int = 0

    # -- interaction ------------------------------------------------------

    def can_interact(self) -> bool:
        """Whether inspecting this object right now would count as a new
        contribution to story progress."""
        return self.repeatable or not self.interacted

    def inspect(self, story_manager: "StoryManager") -> bool:
        """
        Handle the player inspecting/interacting with this object.

        Contributes to story progress only once unless `repeatable` is
        set. Returns True if the interaction was accepted and forwarded
        to the StoryManager, False if it was a no-op (already used and
        not repeatable, or the story couldn't be progressed).
        """
        if not self.can_interact():
            return False

        accepted = story_manager.on_story_object_inspected(self.story_id, self)
        if accepted:
            self.interacted = True
            self.interaction_count += 1
        return accepted

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload.update(
            {
                "story_id": self.story_id,
                "repeatable": self.repeatable,
                "interacted": self.interacted,
                "interaction_count": self.interaction_count,
            }
        )
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryObject":
        pos = data.get("position", [0, 0])
        obj = cls(
            story_id=data["story_id"],
            position=(pos[0], pos[1]),
            object_id=data.get("id"),
            data=dict(data.get("data", {})),
            repeatable=data.get("repeatable", False),
        )
        obj.interacted = data.get("interacted", False)
        obj.interaction_count = data.get("interaction_count", 0)
        return obj

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(id={self.id!r}, story_id={self.story_id!r}, "
            f"interacted={self.interacted})"
        )


# ---------------------------------------------------------------------------
# Concrete object types
# ---------------------------------------------------------------------------
# Each subclass exists purely to give the object a distinct, filterable
# type tag (via default_object_type / get_objects_by_type). None of them
# add behavior -- new object types are added the same way, by subclassing
# StoryObject and setting default_object_type.

class Wagon(StoryObject):
    default_object_type = "wagon"


class Corpse(StoryObject):
    default_object_type = "corpse"


class Campfire(StoryObject):
    default_object_type = "campfire"


class Tent(StoryObject):
    default_object_type = "tent"


class Tracks(StoryObject):
    default_object_type = "tracks"


class Shrine(StoryObject):
    default_object_type = "shrine"


class Cage(StoryObject):
    default_object_type = "cage"


class Journal(StoryObject):
    default_object_type = "journal"


class Banner(StoryObject):
    default_object_type = "banner"


class Blood(StoryObject):
    default_object_type = "blood"


class Grave(StoryObject):
    default_object_type = "grave"


class NPCSpawn(StoryObject):
    """
    A declared NPC waiting to be spawned as a real game entity once its
    story starts -- see story_content_loader.py's `npcs` schema and the
    host's own spawn step (e.g. game.py's _spawn_story_npcs()). Framework-
    only, same as every other StoryObject subclass here: carries no
    behavior of its own, only the type/role/hostile/group_id/dialogue_id
    the host needs, stashed in `.data` by the loader.
    """
    default_object_type = "npc_spawn"


# Registry mapping object_type tag -> class, so serialized data can be
# reconstructed as the correct subclass instead of the generic base.
STORY_OBJECT_TYPES: Dict[str, type] = {
    cls.default_object_type: cls
    for cls in (
        Wagon,
        Corpse,
        Campfire,
        Tent,
        Tracks,
        Shrine,
        Cage,
        Journal,
        Banner,
        Blood,
        Grave,
        NPCSpawn,
    )
}


def story_object_from_dict(data: Dict[str, Any]) -> StoryObject:
    """
    Reconstruct a StoryObject as its correct concrete subclass, based on
    the serialized `object_type` tag. Falls back to the base StoryObject
    class for unrecognized/future types instead of failing.
    """
    object_type = data.get("object_type")
    cls = STORY_OBJECT_TYPES.get(object_type, StoryObject)
    return cls.from_dict(data)