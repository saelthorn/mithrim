import random

from world import tile
from world.encounters.church import _place_blocker, _place_decor

_COCOONS = (tile.fresh_bones, tile.fresh_bones, tile.bones, tile.mushroom)
_LAIR_WEBS = ((3, 3), (-3, 3), (3, -3), (-3, -3), (4, 0), (-4, 0))


def generate_web_nest(game_map, room, stairs_positions):
    webs_placed = 0
    for corner_x, step_x in ((room.x1 + 1, 1), (room.x2 - 1, -1)):
        for corner_y, step_y in ((room.y1 + 1, 1), (room.y2 - 1, -1)):
            for dx, dy in ((0, 0), (1, 0), (0, 1)):
                webs_placed += _place_blocker(
                    game_map, room, corner_x + dx * step_x, corner_y + dy * step_y, tile.cob_web, stairs_positions
                )

    center_x, center_y = room.center()
    for dx in range(-2, 3):
        for dy in range(-1, 2):
            if random.random() < 0.35:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_COCOONS), stairs_positions)
    return webs_placed > 0


def generate_brood_lair(game_map, room, stairs_positions):
    center_x, center_y = room.center()
    inner = set(room.inner_tiles())
    if (center_x, center_y) not in inner:
        return False

    webs_placed = 0
    for dx, dy in _LAIR_WEBS:
        if (center_x + dx, center_y + dy) in inner:
            webs_placed += _place_blocker(game_map, room, center_x + dx, center_y + dy, tile.cob_web, stairs_positions)

    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if (center_x + dx, center_y + dy) in inner and random.random() < 0.3:
                _place_decor(game_map, center_x + dx, center_y + dy, random.choice(_COCOONS), stairs_positions)
    return webs_placed > 0