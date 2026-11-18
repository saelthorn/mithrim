import random

from world import tile
from world.encounters.church import _place_blocker, _place_decor
from world.water_features import lake

_OVERGROWTH = (tile.dungeon_grass, tile.dungeon_grass_two, tile.rubble, tile.mushroom)


def _flood(game_map, x, y, stairs_positions):
    if (x, y) not in stairs_positions.values() and not game_map.tiles[y][x].blocked:
        game_map.tiles[y][x] = lake


def generate_flooded_hall(game_map, room, stairs_positions):
    center_x, center_y = room.center()
    half_width = min(center_x - (room.x1 + 1), (room.x2 - 1) - center_x)
    if half_width < 3:
        return False

    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            _flood(game_map, center_x + dx, center_y + dy, stairs_positions)

    pillars_placed = 0
    for y in range(room.y1 + 2, room.y2 - 1, 2):
        for side in (-3, 3):
            if abs(y - center_y) > 1:
                pillars_placed += _place_blocker(game_map, room, center_x + side, y, tile.dungeon_pillar, stairs_positions)

    for dx in range(-half_width, half_width + 1):
        for dy in range(room.y1 + 1 - center_y, room.y2 - center_y):
            if random.random() < 0.12:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_OVERGROWTH), stairs_positions)
    return pillars_placed > 0


def generate_temple_sanctum(game_map, room, stairs_positions):
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
            _flood(game_map, center_x + dx, center_y, stairs_positions)

    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if (center_x + dx, center_y + dy) in inner and random.random() < 0.2:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_OVERGROWTH), stairs_positions)
    return placed > 0