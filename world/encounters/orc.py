import random

from world import tile
from world.encounters.church import _place_blocker, _place_decor

_SPOILS = (tile.bones, tile.bones, tile.fresh_bones, tile.rubble)
_STORES = (tile.crate, tile.barrel)
_HALL_BANNERS = ((3, 3), (-3, 3), (3, -3), (-3, -3))


def generate_war_barracks(game_map, room, stairs_positions):
    bedrolls_placed = 0
    for y in range(room.y1 + 2, room.y2 - 1, 3):
        for x in (room.x1 + 2, room.x2 - 2):
            bedrolls_placed += _place_blocker(game_map, room, x, y, tile.hay, stairs_positions)

    for corner_x in (room.x1 + 1, room.x2 - 1):
        for corner_y in (room.y1 + 1, room.y2 - 1):
            _place_blocker(game_map, room, corner_x, corner_y, random.choice(_STORES), stairs_positions)

    center_x, center_y = room.center()
    for dx in range(-2, 3):
        for dy in range(-1, 2):
            if random.random() < 0.25:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_SPOILS), stairs_positions)
    return bedrolls_placed > 0


def generate_war_hall(game_map, room, stairs_positions):
    center_x, center_y = room.center()
    inner = set(room.inner_tiles())
    if (center_x, center_y) not in inner:
        return False

    banners_placed = 0
    for dx, dy in _HALL_BANNERS:
        if (center_x + dx, center_y + dy) in inner:
            banners_placed += _place_blocker(game_map, room, center_x + dx, center_y + dy, tile.banner, stairs_positions)

    for dx, station in ((-4, tile.forge), (4, tile.anvil)):
        if (center_x + dx, center_y) in inner:
            _place_blocker(game_map, room, center_x + dx, center_y, station, stairs_positions)

    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if (center_x + dx, center_y + dy) in inner and random.random() < 0.25:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_SPOILS), stairs_positions)
    return banners_placed > 0