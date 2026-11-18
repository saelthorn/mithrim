import random

from world import tile
from world.encounters.church import _place_blocker, _place_decor

_BONE_HEAPS = (tile.bones, tile.bones, tile.rubble)


def generate_ossuary(game_map, room, stairs_positions):
    center_x = (room.x1 + room.x2) // 2
    half_width = min(center_x - (room.x1 + 1), (room.x2 - 1) - center_x)
    if half_width < 3:
        return False

    for y in range(room.y1 + 2, room.y2 - 1, 2):
        for side in (-2, 2):
            _place_blocker(game_map, room, center_x + side, y, tile.dungeon_pillar, stairs_positions)

    for y in range(room.y1 + 3, room.y2 - 1, 2):
        for offset in range(3, half_width + 1):
            for side in (-1, 1):
                if random.random() < 0.7:
                    _place_decor(game_map, center_x + side * offset, y, random.choice(_BONE_HEAPS), stairs_positions)

    for corner_x in (room.x1 + 1, room.x2 - 1):
        _place_blocker(game_map, room, corner_x, room.y1 + 1, tile.cob_web, stairs_positions)
    return True


def generate_lich_sanctum(game_map, room, stairs_positions):
    center_x, center_y = room.center()
    inner = set(room.inner_tiles())
    if (center_x, center_y) not in inner:
        return False

    placed = 0
    for dx, dy in ((3, 3), (-3, 3), (3, -3), (-3, -3)):
        if (center_x + dx, center_y + dy) in inner:
            placed += _place_blocker(game_map, room, center_x + dx, center_y + dy, tile.dungeon_pillar, stairs_positions)

    if (center_x, center_y - 4) in inner:
        _place_blocker(game_map, room, center_x, center_y - 4, tile.altar, stairs_positions)
    for dx in (-4, 4):
        if (center_x + dx, center_y) in inner:
            _place_blocker(game_map, room, center_x + dx, center_y, tile.torch, stairs_positions)

    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if (center_x + dx, center_y + dy) in inner and random.random() < 0.25:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_BONE_HEAPS), stairs_positions)
    return placed > 0