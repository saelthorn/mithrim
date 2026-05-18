import random
from random import randint, choice
from world import tile
from world.tile import (
    stairs_down, stairs_up, dungeon_door, bones, torch, crate, barrel,
    wall, floor, dungeon_grass, dungeon_grass_two,
    dungeon_floor_two, dungeon_floor_three, dungeon_floor_four,
    rubble, cob_web, mushroom, fresh_bones, dungeon_pillar, prison_bars,
    MimicTile, TrapTile, PrisonDoorTile, pressure_plate
)
from items.items import Chest, generate_random_loot
from entities.monster import Mimic
from world.altar import Altar
from traps import DartTrap, SpikeTrap, FireTrap, ExplosiveTrap, AcidSprayTrap
from world.water_features import generate_water_features, river, lake, sewer_water

from world.encounters.prison_cell import generate_prison_cell, PrisonDoorTile


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

class RectRoom:
    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h

    def center(self):
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    def inner_tiles(self):
        """Yield every (x, y) inside the room walls."""
        for ry in range(self.y1 + 1, self.y2):
            for rx in range(self.x1 + 1, self.x2):
                yield rx, ry

    def intersects(self, other, padding=1):
        """
        Returns True if the rooms overlap (with optional padding so rooms
        don't share a wall). Fixed: was comparing y1 <= other.y1 instead of
        y1 <= other.y2, which allowed rooms to overlap vertically.
        """
        return (
            self.x1 - padding <= other.x2 + padding and
            self.x2 + padding >= other.x1 - padding and
            self.y1 - padding <= other.y2 + padding and
            self.y2 + padding >= other.y1 - padding
        )


# ---------------------------------------------------------------------------
# Tile helpers
# ---------------------------------------------------------------------------

# Tiles that are purely visual floor variants — never block movement.
_FLOOR_VARIANTS = [
    tile.dungeon_floor_two, tile.dungeon_floor_three, tile.dungeon_floor_four, tile.dungeon_floor_five, tile.dungeon_floor_six
]

# Tiles placed as props inside rooms — these may be blocked.
_ROOM_PROPS = [
    crate, barrel, bones, rubble, mushroom, fresh_bones,
    dungeon_grass, dungeon_grass_two, cob_web,
]


def _plain_floor():
    """Return a plain floor tile with a small chance of a visual variant."""
    if random.random() < 0.12:
        return random.choice(_FLOOR_VARIANTS)
    return tile.floor


def _dig_room(game_map, room):
    for y in range(room.y1 + 1, room.y2):
        for x in range(room.x1 + 1, room.x2):
            game_map.tiles[y][x] = _plain_floor()


def _dig_tunnel_h(game_map, x1, x2, y):
    """Horizontal tunnel segment — always plain floor, no props."""
    for x in range(min(x1, x2), max(x1, x2) + 1):
        if game_map.tiles[y][x].blocked:   # don't overwrite existing floor
            game_map.tiles[y][x] = tile.floor


def _dig_tunnel_v(game_map, y1, y2, x):
    """Vertical tunnel segment — always plain floor, no props."""
    for y in range(min(y1, y2), max(y1, y2) + 1):
        if game_map.tiles[y][x].blocked:
            game_map.tiles[y][x] = tile.floor


def _connect_rooms(game_map, room_a, room_b):
    """
    Connect two rooms with an L-shaped tunnel.
    Randomly choose the bend direction.
    """
    ax, ay = room_a.center()
    bx, by = room_b.center()
    if randint(0, 1):
        _dig_tunnel_h(game_map, ax, bx, ay)
        _dig_tunnel_v(game_map, ay, by, bx)
        bend = (bx, ay)
    else:
        _dig_tunnel_v(game_map, ay, by, ax)
        _dig_tunnel_h(game_map, ax, bx, by)
        bend = (ax, by)
    return bend   # return the bend point so we can optionally place a door there


#def _place_door(game_map, x, y):
    """Place a door tile only if the spot is currently open floor."""
    if game_map.is_walkable(x, y):
        game_map.tiles[y][x] = dungeon_door


def _place_torch(game_map, x, y, torch_list):
    """Place a torch on a wall adjacent to (x, y) and register it."""
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    random.shuffle(offsets)
    for dx, dy in offsets:
        nx, ny = x + dx, y + dy
        if 0 <= nx < game_map.width and 0 <= ny < game_map.height:
            if game_map.tiles[ny][nx].blocked and not game_map.tiles[ny][nx].block_sight:
                # Wall tile that doesn't block sight — safe to put a torch on
                pass
            if game_map.tiles[ny][nx] == wall:
                game_map.tiles[ny][nx] = torch
                torch_list.append((nx, ny))
                return


def _place_pillars(game_map, room):
    """
    Place up to 4 pillars symmetrically near the room corners if the room
    is large enough and the tile hasn't been taken.
    """
    w = room.x2 - room.x1
    h = room.y2 - room.y1
    if w < 7 or h < 7:
        return
    offsets = [(2, 2), (w - 2, 2), (2, h - 2), (w - 2, h - 2)]
    for ox, oy in offsets:
        px, py = room.x1 + ox, room.y1 + oy
        if game_map.tiles[py][px] == tile.floor:
            game_map.tiles[py][px] = dungeon_pillar


def _is_protected(x, y, stairs_positions):
    return (x, y) == stairs_positions.get('down') or (x, y) == stairs_positions.get('up')


def _is_water(game_map, x, y):
    return game_map.tiles[y][x] in (lake, sewer_water, river)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_dungeon(game_map, level_number, max_rooms=14, room_min_size=5, room_max_size=12):
    rooms = []
    stairs_positions = {}
    torch_light_sources = []

    # Scale some things with dungeon depth
    trap_placement_chance = min(0.03 + level_number * 0.005, 0.12)
    possible_traps = [DartTrap, SpikeTrap, FireTrap, ExplosiveTrap, AcidSprayTrap]
    prop_chance = 0.16
    door_chance = 0.55   # probability of placing a door at a tunnel bend

    # ------------------------------------------------------------------
    # 1. Generate rooms
    # ------------------------------------------------------------------
    attempts = max_rooms * 4
    for _ in range(attempts):
        w = randint(room_min_size, room_max_size)
        h = randint(room_min_size, room_max_size)
        x = randint(1, game_map.width  - w - 2)
        y = randint(1, game_map.height - h - 2)
        new_room = RectRoom(x, y, w, h)

        if any(new_room.intersects(r) for r in rooms):
            continue

        _dig_room(game_map, new_room)
        rooms.append(new_room)
        if len(rooms) >= max_rooms:
            break

    # Fallback
    if not rooms:
        rooms.append(RectRoom(game_map.width // 2 - 3, game_map.height // 2 - 3, 6, 6))
        _dig_room(game_map, rooms[0])

    # ------------------------------------------------------------------
    # 2. Connect rooms
    #    Primary chain: rooms[0] → rooms[1] → … (guarantees connectivity)
    #    Extra edges:   randomly connect non-adjacent rooms to create loops
    # ------------------------------------------------------------------
    bends = []
    for i in range(1, len(rooms)):
        bend = _connect_rooms(game_map, rooms[i - 1], rooms[i])
        bends.append(bend)

    # Add ~30% of extra random connections for more interesting layouts
    extra_connections = max(1, len(rooms) // 3)
    room_indices = list(range(len(rooms)))
    for _ in range(extra_connections):
        a, b = random.sample(room_indices, 2)
        if abs(a - b) > 1:   # avoid re-connecting already-adjacent rooms
            bend = _connect_rooms(game_map, rooms[a], rooms[b])
            bends.append(bend)

    # Optionally place doors at tunnel bends
    # for bx, by in bends:
    #    if random.random() < door_chance:
    #        _place_door(game_map, bx, by)

    # ------------------------------------------------------------------
    # 3. Place stairs — up in the first room, down in the farthest room
    # ------------------------------------------------------------------
    def _room_distance(r1, r2):
        c1, c2 = r1.center(), r2.center()
        return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2) ** 0.5

    stairs_up_room   = rooms[0]
    stairs_down_room = max(rooms[1:], key=lambda r: _room_distance(rooms[0], r)) if len(rooms) > 1 else rooms[0]

    def _place_stair(game_map, room, stair_tile, avoid=None):
        cx, cy = room.center()
        candidates = [(cx, cy)]
        candidates += [(cx + dx, cy + dy) for dx in range(-2, 3) for dy in range(-2, 3) if (dx, dy) != (0, 0)]
        candidates += list(room.inner_tiles())
        for sx, sy in candidates:
            if not (0 <= sx < game_map.width and 0 <= sy < game_map.height):
                continue
            if not game_map.is_walkable(sx, sy):
                continue
            if avoid and (sx, sy) == avoid:
                continue
            game_map.tiles[sy][sx] = stair_tile
            game_map.items_on_ground = [i for i in game_map.items_on_ground if not (i.x == sx and i.y == sy)]
            return (sx, sy)
        # absolute fallback
        game_map.tiles[cy][cx] = stair_tile
        return (cx, cy)

    stairs_positions['down'] = _place_stair(game_map, stairs_down_room, stairs_down)
    stairs_positions['up']   = _place_stair(game_map, stairs_up_room,   stairs_up,   avoid=stairs_positions['down'])

    # ------------------------------------------------------------------
    # 4. Water features
    # ------------------------------------------------------------------
    water_spawn_chance = 0.4 + level_number * 0.05   # increases with depth
    water_tiles = generate_water_features(game_map, rooms, min(water_spawn_chance, 0.85))

    # Protect stairs from being overwritten by water
    for wx, wy in water_tiles:
        if (wx, wy) == stairs_positions.get('down'):
            game_map.tiles[wy][wx] = stairs_down
        elif (wx, wy) == stairs_positions.get('up'):
            game_map.tiles[wy][wx] = stairs_up

    # ------------------------------------------------------------------
    # 5. Choose which rooms get traps (never the stair rooms)
    # ------------------------------------------------------------------
    interior_rooms = [r for r in rooms if r is not stairs_up_room and r is not stairs_down_room]
    num_trap_rooms = max(1, len(interior_rooms) // 3)
    trap_rooms = set(id(r) for r in random.sample(interior_rooms, k=min(num_trap_rooms, len(interior_rooms))))

    # ------------------------------------------------------------------
    # 6. Populate rooms
    # ------------------------------------------------------------------
    for room in rooms:
        is_stair_room = (room is stairs_up_room or room is stairs_down_room)

        # --- Pillars in large rooms ---
        if not is_stair_room and random.random() < 0.4:
            _place_pillars(game_map, room)

        # --- Torches on room walls ---
        cx, cy = room.center()
        torch_count = randint(1, 3)
        # Place torches near corners for a more atmospheric look
        corner_offsets = [(1, 1), (room.x2 - room.x1 - 1, 1),
                          (1, room.y2 - room.y1 - 1), (room.x2 - room.x1 - 1, room.y2 - room.y1 - 1)]
        random.shuffle(corner_offsets)
        for i in range(min(torch_count, len(corner_offsets))):
            tx = room.x1 + corner_offsets[i][0]
            ty = room.y1 + corner_offsets[i][1]
            if 0 < tx < game_map.width - 1 and 0 < ty < game_map.height - 1:
                _place_torch(game_map, tx, ty, torch_light_sources)

        # --- Per-tile pass: props and traps ---
        if not is_stair_room:
            for rx, ry in room.inner_tiles():
                if _is_protected(rx, ry, stairs_positions):
                    continue
                if _is_water(game_map, rx, ry):
                    continue
                if game_map.tiles[ry][rx] != tile.floor:
                    continue   # already replaced by pillar, variant, etc.

                # Traps (only in designated trap rooms)
                if id(room) in trap_rooms and random.random() < trap_placement_chance:
                    trap_cls = random.choice(possible_traps)
                    trap_inst = trap_cls()
                    game_map.tiles[ry][rx] = TrapTile(trap_inst, floor.char, floor.color, rx, ry, trap_inst.name)
                    continue

                # Props
                if random.random() < prop_chance:
                    # Small chance for a mimic disguised as a crate/barrel (level 4+)
                    if level_number >= 4 and random.random() < 0.02:
                        base = random.choice([crate, barrel])
                        disguise_char = 'K' if base is crate else 'B'
                        display_char  = 'k' if base is crate else 'b'
                        mimic = Mimic(rx, ry, disguise_char, base.color)
                        mimic.name = f"Disguised {base.name} Mimic"
                        game_map.tiles[ry][rx] = MimicTile(mimic, display_char, base.color, base.name)
                        game_map.items_on_ground.append(mimic)
                    else:
                        game_map.tiles[ry][rx] = random.choice(_ROOM_PROPS)

        # --- Chest / chest mimic at room center ---
        if is_stair_room:
            continue

        # Find the best open floor tile near the center for a chest
        chest_placed = False
        cx, cy = room.center()
        candidates = [(cx, cy)] + [(cx + dx, cy + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
        for chx, chy in candidates:
            if not (0 <= chx < game_map.width and 0 <= chy < game_map.height):
                continue
            if _is_protected(chx, chy, stairs_positions):
                continue
            if _is_water(game_map, chx, chy):
                continue
            if not game_map.is_walkable(chx, chy):
                continue
            if any(i.x == chx and i.y == chy for i in game_map.items_on_ground):
                continue

            if random.random() < 0.22:
                if random.random() < 0.05:
                    mimic = Mimic(chx, chy, 'C', (139, 69, 19))
                    mimic.name = "Disguised Chest Mimic"
                    game_map.tiles[chy][chx] = MimicTile(mimic, 'C', (139, 69, 19), "Chest")
                    game_map.items_on_ground.append(mimic)
                else:
                    chest = Chest(chx, chy, contents=generate_random_loot(level_number))
                    game_map.items_on_ground.append(chest)
                    game_map.tiles[chy][chx] = tile.floor   # clear any prop that was here
                chest_placed = True
            break   # only attempt one chest per room regardless

    # ── Prison cell encounters (placed after monsters so entities list is stable) ──
    prison_prisoners = []   # list of PrisonerNPC to be added by game.py
    if random.random() < 0.60 and len(rooms) > 3:
        candidate_rooms = [
            r for r in rooms
            if r is not stairs_up_room
            and r is not stairs_down_room
            and (r.x2 - r.x1) >= 7
            and (r.y2 - r.y1) >= 5
        ]
        if candidate_rooms:
            prison_room = random.choice(candidate_rooms)
            result = generate_prison_cell(
                game_map, prison_room, prison_prisoners, stairs_positions
            )
            if result:
                prisoner, _ = result
                # prisoner is already in prison_prisoners list

    return rooms, stairs_positions, torch_light_sources, prison_prisoners