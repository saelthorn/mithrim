import random

from world import tile
from world.water_features import lake, sewer_water, river

_BROKEN_PEWS = (tile.rubble, tile.rubble, tile.bones, tile.fresh_bones)


def _is_open_floor(game_map, x, y, stairs_positions):
    if not (0 < x < game_map.width - 1 and 0 < y < game_map.height - 1):
        return False
    current = game_map.tiles[y][x]
    return (
        not current.blocked
        and current not in (lake, sewer_water, river)
        and (x, y) not in stairs_positions.values()
    )


def _touches_opening(game_map, room, x, y):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nx, ny = x + dx, y + dy
            inside = room.x1 < nx < room.x2 and room.y1 < ny < room.y2
            if not inside and not game_map.tiles[ny][nx].blocked:
                return True
    return False


def _place_blocker(game_map, room, x, y, blocker, stairs_positions):
    if not _is_open_floor(game_map, x, y, stairs_positions) or _touches_opening(game_map, room, x, y):
        return False
    game_map.tiles[y][x] = blocker
    return True


def _place_decor(game_map, x, y, decor, stairs_positions):
    if _is_open_floor(game_map, x, y, stairs_positions):
        game_map.tiles[y][x] = decor


def generate_church_nave(game_map, room, stairs_positions):
    center_x = (room.x1 + room.x2) // 2
    half_width = min(center_x - (room.x1 + 1), (room.x2 - 1) - center_x)
    if half_width < 3:
        return False

    altar_y = room.y1 + 1
    _place_blocker(game_map, room, center_x, altar_y, tile.altar, stairs_positions)
    for side in (-2, 2):
        _place_blocker(game_map, room, center_x + side, altar_y, tile.banner, stairs_positions)

    for y in range(room.y1 + 3, room.y2 - 1, 2):
        for side in (-2, 2):
            _place_blocker(game_map, room, center_x + side, y, tile.dungeon_pillar, stairs_positions)

    for y in range(room.y1 + 4, room.y2 - 1, 2):
        for offset in range(3, half_width + 1):
            for side in (-1, 1):
                if random.random() < 0.85:
                    _place_decor(game_map, center_x + side * offset, y, random.choice(_BROKEN_PEWS), stairs_positions)
    return True


def generate_church_sanctum(game_map, room, stairs_positions):
    center_x, center_y = room.center()
    inner = set(room.inner_tiles())
    if (center_x, center_y) not in inner:
        return False

    placed_circles = 0
    for dx, dy in ((3, 0), (-3, 0), (0, 3), (0, -3)):
        if (center_x + dx, center_y + dy) in inner:
            if _place_blocker(game_map, room, center_x + dx, center_y + dy, tile.ritual_circle, stairs_positions):
                placed_circles += 1

    for dx, dy in ((3, 3), (-3, 3), (3, -3), (-3, -3)):
        if (center_x + dx, center_y + dy) in inner:
            _place_blocker(game_map, room, center_x + dx, center_y + dy, tile.banner, stairs_positions)

    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if (center_x + dx, center_y + dy) in inner and random.random() < 0.25:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_BROKEN_PEWS[2:]), stairs_positions)
    return placed_circles > 0