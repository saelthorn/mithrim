import random

from world import tile
from world.encounters.church import _place_blocker, _place_decor

_BONES = (tile.bones, tile.bones, tile.fresh_bones)
_TENT_SPOTS = ((-3, -2), (3, -2), (-3, 2), (3, 2), (0, -3), (0, 3))
_STASH_SPOTS = ((4, 0, tile.crate), (-4, 0, tile.barrel), (0, 4, tile.crate), (0, -4, tile.barrel))


def _inside(room, x, y):
    return room.x1 < x < room.x2 and room.y1 < y < room.y2


def _scatter_bones(game_map, room, center_x, center_y, radius, chance, stairs_positions):
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            x, y = center_x + dx, center_y + dy
            if _inside(room, x, y) and random.random() < chance:
                _place_decor(game_map, x, y, random.choice(_BONES), stairs_positions)


def generate_goblin_camp(game_map, room, stairs_positions):
    center_x, center_y = room.center()
    _place_decor(game_map, center_x, center_y, tile.campfire, stairs_positions)

    spots = list(_TENT_SPOTS)
    random.shuffle(spots)
    tents_placed = 0
    for dx, dy in spots[:3]:
        x, y = center_x + dx, center_y + dy
        if _inside(room, x, y) and _place_blocker(game_map, room, x, y, tile.tent, stairs_positions):
            tents_placed += 1

    if _inside(room, center_x + 2, center_y - 1):
        _place_blocker(game_map, room, center_x + 2, center_y - 1, tile.cauldron, stairs_positions)

    _scatter_bones(game_map, room, center_x, center_y, 3, 0.2, stairs_positions)
    return tents_placed > 0


def generate_goblin_hall(game_map, room, stairs_positions):
    center_x, center_y = room.center()
    inner = set(room.inner_tiles())
    if (center_x, center_y) not in inner:
        return False

    _place_decor(game_map, center_x, center_y, tile.campfire, stairs_positions)

    placed = 0
    for dx, dy in ((3, 3), (-3, 3), (3, -3), (-3, -3)):
        if (center_x + dx, center_y + dy) in inner:
            placed += _place_blocker(game_map, room, center_x + dx, center_y + dy, tile.banner, stairs_positions)

    for dx, dy, stash in _STASH_SPOTS:
        if (center_x + dx, center_y + dy) in inner:
            _place_blocker(game_map, room, center_x + dx, center_y + dy, stash, stairs_positions)

    _scatter_bones(game_map, room, center_x, center_y, 2, 0.25, stairs_positions)
    return placed > 0