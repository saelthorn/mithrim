import random
from random import randint, choice
from world import tile
from world.tile import (
    stairs_down, stairs_up, dungeon_door, bones, torch, crate, barrel,
    wall, floor, dungeon_grass, dungeon_grass_two,
    dungeon_floor_two, dungeon_floor_three, dungeon_floor_four,
    rubble, cob_web, mushroom, fresh_bones, dungeon_pillar, prison_bars,
    MimicTile, TrapTile, PrisonDoorTile, pressure_plate, TombTile
)
from items.items import Chest, LockedChest, generate_random_loot, generate_locked_loot
from entities.monster import Mimic
from world.altar import Altar
from traps import DartTrap, SpikeTrap, FireTrap, ExplosiveTrap, AcidSprayTrap
from world.water_features import generate_water_features, river, lake, sewer_water

from world.encounters.prison_cell import generate_prison_cell, is_prison_cell_position, PrisonDoorTile
from world.encounters.temple_room import generate_circular_temple
from world.encounters.crypt import generate_crypt, is_crypt_position


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


class LShapedRoom:
    """
    L-shaped room composed of a horizontal and vertical rectangular section.
    The two sections overlap to form an L.
    """
    def __init__(self, h_x1, h_x2, h_y1, h_y2, v_x1, v_x2, v_y1, v_y2):
        # Horizontal section (the wide bar of the L)
        self.h_x1 = h_x1
        self.h_x2 = h_x2
        self.h_y1 = h_y1
        self.h_y2 = h_y2
        
        # Vertical section (the tall bar of the L)
        self.v_x1 = v_x1
        self.v_x2 = v_x2
        self.v_y1 = v_y1
        self.v_y2 = v_y2
        
        # Bounding box for intersection checks and general properties
        self.x1 = min(h_x1, v_x1)
        self.x2 = max(h_x2, v_x2)
        self.y1 = min(h_y1, v_y1)
        self.y2 = max(h_y2, v_y2)

    def center(self):
        """Return the center of the bounding box."""
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def inner_tiles(self):
        """Yield all interior tiles of the L-shaped room (union of both sections)."""
        seen = set()
        
        # Interior of horizontal section
        for y in range(self.h_y1 + 1, self.h_y2):
            for x in range(self.h_x1 + 1, self.h_x2):
                if (x, y) not in seen:
                    seen.add((x, y))
                    yield x, y
        
        # Interior of vertical section (excluding already-covered overlap)
        for y in range(self.v_y1 + 1, self.v_y2):
            for x in range(self.v_x1 + 1, self.v_x2):
                if (x, y) not in seen:
                    seen.add((x, y))
                    yield x, y

    def intersects(self, other, padding=1):
        """Check if this L-room's bounding box intersects with another room."""
        return (
            self.x1 - padding <= other.x2 + padding and
            self.x2 + padding >= other.x1 - padding and
            self.y1 - padding <= other.y2 + padding and
            self.y2 + padding >= other.y1 - padding
        )


class CircleRoom:
    """
    Circular room defined by center coordinates and radius.
    Used for sacred temple chambers with perfect circular geometry.
    """
    def __init__(self, center_x, center_y, radius):
        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        # Bounding box for intersection checks
        self.x1 = center_x - radius
        self.y1 = center_y - radius
        self.x2 = center_x + radius + 1
        self.y2 = center_y + radius + 1

    def center(self):
        """Return the center coordinates."""
        return (self.center_x, self.center_y)

    def inner_tiles(self):
        """Yield all (x, y) coordinates within the circular boundary."""
        for y in range(self.y1, self.y2):
            for x in range(self.x1, self.x2):
                dx = x - self.center_x
                dy = y - self.center_y
                if dx * dx + dy * dy <= self.radius * self.radius:
                    yield x, y

    def intersects(self, other, padding=1):
        """Check if this circle's bounding box intersects with another room."""
        return (
            self.x1 - padding <= other.x2 + padding and
            self.x2 + padding >= other.x1 - padding and
            self.y1 - padding <= other.y2 + padding and
            self.y2 + padding >= other.y1 - padding
        )


class PlusShapedRoom:
    """
    Plus-shaped (cross/'+') room composed of a horizontal and vertical rectangular section.
    The two sections overlap in the center to form a plus sign.
    """
    def __init__(self, h_x1, h_x2, h_y1, h_y2, v_x1, v_x2, v_y1, v_y2):
        # Horizontal section (the wide bar of the plus)
        self.h_x1 = h_x1
        self.h_x2 = h_x2
        self.h_y1 = h_y1
        self.h_y2 = h_y2
        
        # Vertical section (the tall bar of the plus)
        self.v_x1 = v_x1
        self.v_x2 = v_x2
        self.v_y1 = v_y1
        self.v_y2 = v_y2
        
        # Bounding box for intersection checks and general properties
        self.x1 = min(h_x1, v_x1)
        self.x2 = max(h_x2, v_x2)
        self.y1 = min(h_y1, v_y1)
        self.y2 = max(h_y2, v_y2)

    def center(self):
        """Return the center of the bounding box."""
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def inner_tiles(self):
        """Yield all interior tiles of the plus-shaped room (union of both sections)."""
        seen = set()
        
        # Interior of horizontal section
        for y in range(self.h_y1 + 1, self.h_y2):
            for x in range(self.h_x1 + 1, self.h_x2):
                if (x, y) not in seen:
                    seen.add((x, y))
                    yield x, y
        
        # Interior of vertical section (excluding already-covered overlap)
        for y in range(self.v_y1 + 1, self.v_y2):
            for x in range(self.v_x1 + 1, self.v_x2):
                if (x, y) not in seen:
                    seen.add((x, y))
                    yield x, y

    def intersects(self, other, padding=1):
        """Check if this plus-room's bounding box intersects with another room."""
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
    """Dig a room (rectangular or L-shaped)."""
    if isinstance(room, LShapedRoom):
        # Dig the horizontal section
        for y in range(room.h_y1 + 1, room.h_y2): 
            for x in range(room.h_x1 + 1, room.h_x2):
                game_map.tiles[y][x] = _plain_floor()
        
        # Dig the vertical section
        for y in range(room.v_y1 + 1, room.v_y2):
            for x in range(room.v_x1 + 1, room.v_x2):
                game_map.tiles[y][x] = _plain_floor()
    else:
        # Regular rectangular room
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


def _tunnel_length(x1, y1, x2, y2):
    """Calculate the Manhattan distance for a tunnel (L-shaped)."""
    return abs(x2 - x1) + abs(y2 - y1)


def _create_hub_room(game_map, cx, cy, rooms):
    """
    Create a 3x3 hub room centered at (cx, cy).
    Returns a RectRoom if successful, None if it intersects with existing rooms.
    """
    # 3x3 room, so x1/x2 are 2 units apart (same with y)
    hub = RectRoom(cx - 1, cy - 1, 3, 3)
    
    # Check if it intersects with any existing room
    if any(hub.intersects(r) for r in rooms):
        return None
    
    # Carve out the hub room
    _dig_room(game_map, hub)
    return hub


def _connect_rooms(game_map, room_a, room_b, prison_blocked_sides=None, max_tunnel_length=None):
    """
    Connect two rooms with an L-shaped tunnel.

    If a room has a prison cell on one side (east/west), tunnels must never
    enter that room from that cardinal direction.  We control this by choosing
    which bend variant to use:

      Variant A  (horizontal first):
        - enters room_a from the EAST or WEST (horizontal segment leaves ax)
        - enters room_b from the NORTH or SOUTH (vertical segment arrives at by)

      Variant B  (vertical first):
        - enters room_a from the NORTH or SOUTH (vertical segment leaves ay)
        - enters room_b from the EAST or WEST (horizontal segment arrives at bx)

    So if room_a has prison on the east/west we prefer Variant B (enters room_a
    vertically).  If room_b has prison on east/west we prefer Variant A (enters
    room_b vertically).  If both are constrained the same way we still pick the
    best option — the constraint is a preference, not a hard block, since some
    layouts may have no perfect choice.
    
    If max_tunnel_length is set and the tunnel would exceed it (Manhattan distance),
    returns None instead of creating the tunnel.
    """
    ax, ay = room_a.center()
    bx, by = room_b.center()

    # Check tunnel length if constrained
    if max_tunnel_length is not None:
        tunnel_len = _tunnel_length(ax, ay, bx, by)
        if tunnel_len > max_tunnel_length:
            return None  # Tunnel too long, reject connection

    blocked_sides = prison_blocked_sides or {}
    a_blocked = blocked_sides.get(id(room_a))  # 'east', 'west', or None
    b_blocked = blocked_sides.get(id(room_b))

    # Variant A: horizontal first (room_a entered east/west, room_b north/south)
    # Variant B: vertical first  (room_a entered north/south, room_b east/west)
    #
    # a_blocked east/west  → avoid variant A for room_a  → prefer B
    # b_blocked east/west  → avoid variant B for room_b  → prefer A
    a_needs_vertical_entry = a_blocked in ('east', 'west')
    b_needs_vertical_entry = b_blocked in ('east', 'west')

    if a_needs_vertical_entry and not b_needs_vertical_entry:
        use_variant_b = True   # room_a must be entered vertically
    elif b_needs_vertical_entry and not a_needs_vertical_entry:
        use_variant_b = False  # room_b must be entered vertically → use A
    else:
        use_variant_b = bool(randint(0, 1))  # no constraint or both constrained

    if not use_variant_b:
        # Variant A: horizontal ax→bx at ay, then vertical ay→by at bx
        _dig_tunnel_h(game_map, ax, bx, ay)
        _dig_tunnel_v(game_map, ay, by, bx)
        bend = (bx, ay)
    else:
        # Variant B: vertical ay→by at ax, then horizontal ax→bx at by
        _dig_tunnel_v(game_map, ay, by, ax)
        _dig_tunnel_h(game_map, ax, bx, by)
        bend = (ax, by)

    return bend

def _place_door(game_map, x, y):
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


def _generate_l_shaped_room(game_map, room_min_size, room_max_size, region_x1=None, region_x2=None, region_y1=None, region_y2=None):
    """
    Generate a random L-shaped room that fits on the map, optionally within a center-biased region.
    Returns an LShapedRoom or None if generation fails.
    More lenient sizing and positioning to ensure success rate.
    """
    # Use full map if region not specified
    if region_x1 is None:
        region_x1 = 1
        region_x2 = game_map.width - 1
        region_y1 = 1
        region_y2 = game_map.height - 1
    
    # Make sections more reasonably sized
    h_w = randint(max(6, room_min_size), room_max_size + 2)      # horizontal section width
    h_h = randint(4, 5)                                           # horizontal section height (thinner)
    v_w = randint(4, 5)                                           # vertical section width (narrower)
    v_h = randint(max(6, room_min_size), room_max_size + 2)      # vertical section height
    
    # Randomly position the L in one of 4 orientations
    orientation = randint(0, 3)
    
    try:
        if orientation == 0:
            # Horizontal at top-left, vertical extending down-right
            max_h_x = min(region_x2 - h_w - v_w - 3, game_map.width - h_w - v_w - 3)
            if max_h_x < region_x1:
                return None
            h_x = randint(region_x1, max_h_x)
            max_h_y = min(region_y2 - max(h_h, v_h) - 3, game_map.height - max(h_h, v_h) - 3)
            if max_h_y < region_y1:
                return None
            h_y = randint(region_y1, max_h_y)
            v_x = h_x + h_w - v_w
            v_y = h_y + h_h - 1  # Overlap to create seamless L-shape
            
            if not (0 <= v_x and v_x + v_w <= game_map.width and
                    0 <= v_y and v_y + v_h <= game_map.height):
                return None
                
            return LShapedRoom(h_x, h_x + h_w, h_y, h_y + h_h,
                              v_x, v_x + v_w, v_y, v_y + v_h)
        
        elif orientation == 1:
            # Horizontal at top-right, vertical extending down-left
            max_h_x = min(region_x2 - h_w - 3, game_map.width - h_w - 3)
            if max_h_x < region_x1 + v_w + 2:
                return None
            h_x = randint(region_x1 + v_w + 2, max_h_x)
            max_h_y = min(region_y2 - max(h_h, v_h) - 3, game_map.height - max(h_h, v_h) - 3)
            if max_h_y < region_y1:
                return None
            h_y = randint(region_y1, max_h_y)
            v_x = h_x
            v_y = h_y + h_h - 1  # Overlap to create seamless L-shape
            
            if not (0 <= v_x and v_x + v_w <= game_map.width and
                    0 <= v_y and v_y + v_h <= game_map.height):
                return None
                
            return LShapedRoom(h_x, h_x + h_w, h_y, h_y + h_h,
                              max(0, v_x - v_w), v_x, v_y, v_y + v_h)
        
        elif orientation == 2:
            # Vertical at top-left, horizontal extending right-down
            max_v_x = min(region_x2 - max(h_w, v_w) - 3, game_map.width - max(h_w, v_w) - 3)
            if max_v_x < region_x1:
                return None
            v_x = randint(region_x1, max_v_x)
            max_v_y = min(region_y2 - v_h - h_h - 3, game_map.height - v_h - h_h - 3)
            if max_v_y < region_y1:
                return None
            v_y = randint(region_y1, max_v_y)
            h_x = v_x + v_w - 1  # Overlap to create seamless L-shape
            h_y = v_y + v_h - h_h
            
            if not (0 <= h_x and h_x + h_w <= game_map.width and
                    0 <= h_y and h_y + h_h <= game_map.height):
                return None
                
            return LShapedRoom(h_x, h_x + h_w, h_y, h_y + h_h,
                              v_x, v_x + v_w, v_y, v_y + v_h)
        
        else:  # orientation == 3
            # Vertical at top-right, horizontal extending left-down
            max_v_x = min(region_x2 - v_w - 3, game_map.width - v_w - 3)
            if max_v_x < region_x1 + h_w + 2:
                return None
            v_x = randint(region_x1 + h_w + 2, max_v_x)
            max_v_y = min(region_y2 - v_h - h_h - 3, game_map.height - v_h - h_h - 3)
            if max_v_y < region_y1:
                return None
            v_y = randint(region_y1, max_v_y)
            h_x = v_x - h_w + 1  # Overlap to create seamless L-shape
            h_y = v_y + v_h - h_h
            
            if not (0 <= h_x and h_x + h_w <= game_map.width and
                    0 <= h_y and h_y + h_h <= game_map.height):
                return None
                
            return LShapedRoom(h_x, h_x + h_w, h_y, h_y + h_h,
                              v_x, v_x + v_w, v_y, v_y + v_h)
    
    except (ValueError, IndexError):
        return None


def _generate_circular_room(game_map, radius, region_x1, region_x2, region_y1, region_y2):
    """
    Generate a circular temple room at a random position within the region.
    
    Args:
        game_map: The dungeon map
        radius: Radius of the circular room
        region_x1, region_x2, region_y1, region_y2: Placement region bounds
    
    Returns:
        CircleRoom or None if no valid placement found
    """
    # Ensure the circle fits completely within the map and region
    min_x = max(region_x1, radius + 1)
    max_x = min(region_x2 - radius - 1, game_map.width - radius - 2)
    min_y = max(region_y1, radius + 1)
    max_y = min(region_y2 - radius - 1, game_map.height - radius - 2)
    
    if min_x >= max_x or min_y >= max_y:
        return None
    
    center_x = randint(min_x, max_x)
    center_y = randint(min_y, max_y)
    
    return CircleRoom(center_x, center_y, radius)


def _dig_circular_room(game_map, circle_room):
    """
    Carve a circular room into the dungeon map using distance formula.
    
    Args:
        game_map: The dungeon map
        circle_room: CircleRoom instance to carve
    """
    center_x = circle_room.center_x
    center_y = circle_room.center_y
    radius = circle_room.radius
    
    # Carve all tiles within the circular boundary
    for y in range(circle_room.y1, circle_room.y2):
        for x in range(circle_room.x1, circle_room.x2):
            if 0 <= x < game_map.width and 0 <= y < game_map.height:
                dx = x - center_x
                dy = y - center_y
                # Use distance squared to avoid sqrt()
                if dx * dx + dy * dy <= radius * radius:
                    game_map.tiles[y][x] = _plain_floor()


def _generate_plus_shaped_room(game_map, room_min_size, room_max_size, region_x1=None, region_x2=None, region_y1=None, region_y2=None):
    """
    Generate a random plus-shaped (cross) room that fits on the map, optionally within a center-biased region.
    Returns a PlusShapedRoom or None if generation fails.
    
    The plus shape consists of:
    - A horizontal bar (wide, thin)
    - A vertical bar (tall, thin)
    - Both centered on the same point, creating a symmetric plus/cross shape
    """
    # Use full map if region not specified
    if region_x1 is None:
        region_x1 = 1
        region_x2 = game_map.width - 1
        region_y1 = 1
        region_y2 = game_map.height - 1
    
    # Dimensions for plus-shaped room
    h_w = randint(max(8, room_min_size), room_max_size + 2)      # horizontal bar width (full extent)
    h_h = randint(3, 5)                                           # horizontal bar height (thin)
    v_w = randint(3, 5)                                           # vertical bar width (thin)
    v_h = randint(max(8, room_min_size), room_max_size + 2)      # vertical bar height (full extent)
    
    try:
        # Choose a center point for the plus
        min_x = max(region_x1, (h_w // 2) + 2)
        max_x = min(region_x2 - (h_w // 2) - 2, game_map.width - (h_w // 2) - 3)
        min_y = max(region_y1, (v_h // 2) + 2)
        max_y = min(region_y2 - (v_h // 2) - 2, game_map.height - (v_h // 2) - 3)
        
        if min_x >= max_x or min_y >= max_y:
            return None
        
        center_x = randint(min_x, max_x)
        center_y = randint(min_y, max_y)
        
        # Calculate the four positions of the bars
        # Horizontal bar: centered on center_y, extends left-right from center_x
        h_x1 = center_x - (h_w // 2)
        h_x2 = h_x1 + h_w
        h_y1 = center_y - (h_h // 2)
        h_y2 = h_y1 + h_h
        
        # Vertical bar: centered on center_x, extends up-down from center_y
        v_x1 = center_x - (v_w // 2)
        v_x2 = v_x1 + v_w
        v_y1 = center_y - (v_h // 2)
        v_y2 = v_y1 + v_h
        
        # Validate all boundaries
        if not (0 <= h_x1 and h_x2 <= game_map.width and
                0 <= h_y1 and h_y2 <= game_map.height and
                0 <= v_x1 and v_x2 <= game_map.width and
                0 <= v_y1 and v_y2 <= game_map.height):
            return None
        
        return PlusShapedRoom(h_x1, h_x2, h_y1, h_y2, v_x1, v_x2, v_y1, v_y2)
    
    except (ValueError, IndexError):
        return None


def _dig_plus_shaped_room(game_map, plus_room):
    """
    Carve a plus-shaped room into the dungeon map.
    
    Args:
        game_map: The dungeon map
        plus_room: PlusShapedRoom instance to carve
    """
    # Dig the horizontal section
    for y in range(plus_room.h_y1 + 1, plus_room.h_y2):
        for x in range(plus_room.h_x1 + 1, plus_room.h_x2):
            if 0 <= x < game_map.width and 0 <= y < game_map.height:
                game_map.tiles[y][x] = _plain_floor()
    
    # Dig the vertical section
    for y in range(plus_room.v_y1 + 1, plus_room.v_y2):
        for x in range(plus_room.v_x1 + 1, plus_room.v_x2):
            if 0 <= x < game_map.width and 0 <= y < game_map.height:
                game_map.tiles[y][x] = _plain_floor()


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_dungeon(game_map, level_number, max_rooms=32, room_min_size=8, room_max_size=10):
    rooms = []
    stairs_positions = {}
    torch_light_sources = []

    # Scale some things with dungeon depth
    trap_placement_chance = min(0.03 + level_number * 0.005, 0.12)
    possible_traps = [DartTrap, SpikeTrap, FireTrap, ExplosiveTrap, AcidSprayTrap]
    prop_chance = 0.16
    door_chance = 0.55   # probability of placing a door at a tunnel bend
    
    # Calculate center-biased placement region to keep rooms clustered
    # and avoid long winding tunnels
    center_x = game_map.width // 2
    center_y = game_map.height // 2
    region_width = max(50, int(game_map.width * 0.6))    # 60% of map width
    region_height = max(40, int(game_map.height * 0.6))  # 60% of map height
    region_x1 = max(1, center_x - region_width // 2)
    region_x2 = min(game_map.width - 1, center_x + region_width // 2)
    region_y1 = max(1, center_y - region_height // 2)
    region_y2 = min(game_map.height - 1, center_y + region_height // 2)
    
    # Maximum tunnel length to prevent long winding corridors (in Manhattan distance)
    # This is roughly 40% of the region's diagonal
    max_tunnel_length = int(((region_width ** 2 + region_height ** 2) ** 0.5) * 0.4)

    # ------------------------------------------------------------------
    # 1. Generate rooms
    # ------------------------------------------------------------------
    # Room type distribution: 15% circular temples, 15% plus-shaped, 20% L-shaped, 50% rectangular
    attempts = max_rooms * 4
    for _ in range(attempts):
        rand_val = random.random()
        
        if rand_val < 0.15:
            # Generate a circular temple room
            temple_radius = randint(5, 8)
            new_room = _generate_circular_room(game_map, temple_radius, 
                                               region_x1, region_x2, region_y1, region_y2)
            if new_room is None:
                continue  # Failed to generate circle, try again
        
        elif rand_val < 0.30:
            # Generate a plus-shaped room
            new_room = _generate_plus_shaped_room(game_map, room_min_size, room_max_size,
                                                  region_x1, region_x2, region_y1, region_y2)
            if new_room is None:
                continue  # Failed to generate plus-room, try again
                
        elif rand_val < 0.50:
            # Generate an L-shaped room
            new_room = _generate_l_shaped_room(game_map, room_min_size, room_max_size,
                                               region_x1, region_x2, region_y1, region_y2)
            if new_room is None:
                continue  # Failed to generate L-room, try again
        else:
            # Generate a rectangular room
            w = randint(room_min_size, room_max_size)
            h = randint(room_min_size, room_max_size)
            # Place room within center-biased region
            x = randint(region_x1, max(region_x1 + 1, region_x2 - w - 1))
            y = randint(region_y1, max(region_y1 + 1, region_y2 - h - 1))
            new_room = RectRoom(x, y, w, h)

        if any(new_room.intersects(r) for r in rooms):
            continue

        # Dig the room (different handling for each type)
        if isinstance(new_room, CircleRoom):
            _dig_circular_room(game_map, new_room)
            # Decorate with altar and pillars (80% of circles)
            if random.random() < 0.8:
                generate_circular_temple(game_map, new_room.center_x, new_room.center_y,
                                        new_room.radius, game_map.items_on_ground, stairs_positions)
        elif isinstance(new_room, PlusShapedRoom):
            _dig_plus_shaped_room(game_map, new_room)
        else:
            _dig_room(game_map, new_room)
            
        rooms.append(new_room)
        if len(rooms) >= max_rooms:
            break

    # Fallback
    if not rooms:
        rooms.append(RectRoom(game_map.width // 2 - 3, game_map.height // 2 - 3, 6, 6))
        _dig_room(game_map, rooms[0])

    # ------------------------------------------------------------------
    # 2. Connect rooms using a tree/graph structure
    #    - Room 0 is the root
    #    - Each room connects to its 2-3 nearest unconnected rooms
    #    - This creates natural branching instead of a linear chain
    #    - Ensures full connectivity while preferring short distances
    # ------------------------------------------------------------------
    bends = []
    connected = set()  # Track which rooms have been processed
    connected.add(0)   # Start with room 0 as root
    queue = [0]       # Breadth-first queue
    
    def _distance_between_rooms(room_a, room_b):
        """Calculate Euclidean distance between room centers."""
        ax, ay = room_a.center()
        bx, by = room_b.center()
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    
    def _connect_rooms_safe(room_a, room_b):
        """Connect two rooms with hub fallback. Returns True if successful."""
        # Try direct connection first
        bend = _connect_rooms(game_map, room_a, room_b, max_tunnel_length=max_tunnel_length)
        if bend is not None:
            bends.append(bend)
            return True
        
        # Tunnel too long; try to create a hub room at midpoint
        ax, ay = room_a.center()
        bx, by = room_b.center()
        hub_x = (ax + bx) // 2
        hub_y = (ay + by) // 2
        
        # Try to create a hub room at the midpoint
        hub = _create_hub_room(game_map, hub_x, hub_y, rooms)
        if hub is None:
            # Try a few offset positions if the center doesn't work
            for offset_x in [-3, 3]:
                for offset_y in [-3, 3]:
                    hub = _create_hub_room(game_map, hub_x + offset_x, hub_y + offset_y, rooms)
                    if hub is not None:
                        break
                if hub is not None:
                    break
        
        if hub is None:
            return False  # Couldn't create hub
        
        rooms.append(hub)  # Add hub to rooms list
        
        # Connect room_a → hub and hub → room_b
        bend1 = _connect_rooms(game_map, room_a, hub, max_tunnel_length=None)
        bend2 = _connect_rooms(game_map, hub, room_b, max_tunnel_length=None)
        
        if bend1 is not None:
            bends.append(bend1)
        if bend2 is not None:
            bends.append(bend2)
        
        return True
    
    # Process rooms in breadth-first order, building a tree structure
    while queue:
        current_idx = queue.pop(0)
        current_room = rooms[current_idx]
        
        # Find unconnected rooms, sorted by distance (nearest first)
        unconnected = [
            (i, _distance_between_rooms(current_room, rooms[i]))
            for i in range(len(rooms))
            if i not in connected
        ]
        unconnected.sort(key=lambda x: x[1])
        
        # Connect to 2-3 nearest unconnected rooms (branching factor)
        branches = min(3, len(unconnected))
        for i in range(branches):
            if i >= len(unconnected):
                break
            next_idx, distance = unconnected[i]
            next_room = rooms[next_idx]
            
            # Try to connect
            if _connect_rooms_safe(current_room, next_room):
                connected.add(next_idx)
                queue.append(next_idx)
    
    # Attempt to connect any remaining unconnected rooms
    # (in case the tree structure didn't reach them)
    for i in range(len(rooms)):
        if i not in connected:
            # Find nearest connected room and connect to it
            connected_distances = [
                (j, _distance_between_rooms(rooms[i], rooms[j]))
                for j in connected
            ]
            if connected_distances:
                nearest_idx, _ = min(connected_distances, key=lambda x: x[1])
                if _connect_rooms_safe(rooms[nearest_idx], rooms[i]):
                    connected.add(i)

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
    # 6. Prison cell encounters
    #    Carved after tunnels are already dug. We then repair any tunnel
    #    that punched through the prison's blocked side by walling it off
    #    and digging a new vertical entry from the top or bottom instead.
    # ------------------------------------------------------------------
    MAX_PRISON_ROOMS    = 3
    PRISON_ROOM_CHANCE  = 0.60
    PRISONER_SPAWN_CHANCE = 0.40  # chance each individual prisoner actually appears
    prison_prisoners    = []
    prison_blocked_sides = {}  # id(room) -> 'east' or 'west'

    prison_candidates = [
        room for room in rooms
        if room is not stairs_up_room
        and room is not stairs_down_room
        and not isinstance(room, LShapedRoom)
        and not isinstance(room, CircleRoom)  # Exclude circular temples
        and not isinstance(room, PlusShapedRoom)  # Exclude plus-shaped rooms
        and (room.x2 - room.x1) >= 8
        and (room.y2 - room.y1) >= 9
    ]
    random.shuffle(prison_candidates)

    prison_rooms_placed = 0
    for candidate in prison_candidates:
        if prison_rooms_placed >= MAX_PRISON_ROOMS:
            break
        if random.random() > PRISON_ROOM_CHANCE:
            continue

        # Snapshot list length so we can identify newly added prisoners
        prisoners_before = len(prison_prisoners)

        orientation, result = generate_prison_cell(
            game_map, candidate, prison_prisoners, stairs_positions
        )
        if result is not None:
            prison_blocked_sides[id(candidate)] = orientation
            prison_rooms_placed += 1

            # Cull newly added prisoners based on spawn chance.
            # Iterate in reverse so removing by index is safe.
            for i in range(len(prison_prisoners) - 1, prisoners_before - 1, -1):
                if random.random() > PRISONER_SPAWN_CHANCE:
                    prison_prisoners.pop(i)

    # ------------------------------------------------------------------
    # 6b. Crypt encounters
    #     Similar to prison cells but with tombs that spawn skeletons
    #     or drop treasure when disturbed.
    # ------------------------------------------------------------------
    MAX_CRYPT_ROOMS    = 2
    CRYPT_ROOM_CHANCE  = 0.50

    crypt_candidates = [
        room for room in rooms
        if room is not stairs_up_room
        and room is not stairs_down_room
        and id(room) not in prison_blocked_sides
        and (room.x2 - room.x1) >= 8
        and (room.y2 - room.y1) >= 9
    ]
    random.shuffle(crypt_candidates)

    crypt_rooms_placed = 0
    for candidate in crypt_candidates:
        if crypt_rooms_placed >= MAX_CRYPT_ROOMS:
            break
        if random.random() > CRYPT_ROOM_CHANCE:
            continue

        tomb_positions = generate_crypt(game_map, candidate, stairs_positions)
        if tomb_positions is not None:
            crypt_rooms_placed += 1

    # ------------------------------------------------------------------
    # 7. Repair tunnels that cut through prison-blocked walls
    #
    #    For each prison room, find the column of its outer wall on the
    #    blocked side (east wall col = room.x2, west wall col = room.x1).
    #    Any floor tile on that wall column was dug by a horizontal tunnel
    #    — wall it back up.  Then ensure the room is still reachable by
    #    digging a vertical entry through the top or bottom wall instead.
    # ------------------------------------------------------------------
    for room, side in [(r, prison_blocked_sides[id(r)]) for r in rooms if id(r) in prison_blocked_sides]:

        if side == 'east':
            blocked_wall_col = room.x2   # the east outer wall column
        else:
            blocked_wall_col = room.x1   # the west outer wall column

        # Seal any horizontal tunnel breaches on the blocked wall column.
        for row in range(room.y1, room.y2 + 1):
            if 0 <= blocked_wall_col < game_map.width and 0 <= row < game_map.height:
                t = game_map.tiles[row][blocked_wall_col]
                # A floor (or variant) on the outer wall means a tunnel dug through here.
                if not t.blocked:
                    game_map.tiles[row][blocked_wall_col] = wall

        # Also seal one column inside the room on the blocked side, because
        # _dig_tunnel_h may have run a few tiles into the room interior before
        # hitting the bars column.
        inner_col = (room.x2 - 1) if side == 'east' else (room.x1 + 1)
        for row in range(room.y1, room.y2 + 1):
            if 0 <= inner_col < game_map.width and 0 <= row < game_map.height:
                if is_prison_cell_position(game_map, inner_col, row):
                    # This column is bars/floor — leave it alone.
                    continue
                t = game_map.tiles[row][inner_col]
                if not t.blocked:
                    game_map.tiles[row][inner_col] = wall

        # Now ensure the room is still connected by checking that at least
        # one floor tile exists on the top or bottom outer wall (a vertical
        # tunnel already enters there, or we dig one now).
        top_wall_row    = room.y1
        bottom_wall_row = room.y2
        cx = (room.x1 + room.x2) // 2

        def _has_floor_on_wall(wall_row, x1, x2):
            for col in range(x1 + 1, x2):
                if 0 <= col < game_map.width and 0 <= wall_row < game_map.height:
                    if not game_map.tiles[wall_row][col].blocked:
                        return True
            return False

        top_open    = _has_floor_on_wall(top_wall_row,    room.x1, room.x2)
        bottom_open = _has_floor_on_wall(bottom_wall_row, room.x1, room.x2)

        if not top_open and not bottom_open:
            # Room is now sealed — punch a new entry through the top wall at center.
            if 0 <= cx < game_map.width and 0 <= top_wall_row < game_map.height:
                game_map.tiles[top_wall_row][cx] = tile.floor
            # And connect it upward to the nearest open corridor tile above.
            connect_row = top_wall_row - 1
            while connect_row >= 0:
                if not game_map.tiles[connect_row][cx].blocked:
                    break
                game_map.tiles[connect_row][cx] = tile.floor
                connect_row -= 1

    # ------------------------------------------------------------------
    # 7b. Carve a 1-tile floor border just outside each prison room
    #
    #     The prison room's own walls are left intact.  We carve floor
    #     into the ring of tiles immediately outside those walls so the
    #     player has a walkable corridor all the way around the room:

    for room in [r for r in rooms if id(r) in prison_blocked_sides]:

        # One tile beyond each edge of the room boundary
        surround_x1 = room.x1 - 1
        surround_x2 = room.x2 + 1
        surround_y1 = room.y1 - 1
        surround_y2 = room.y2 + 1

        # Top row  (y == room.y1 - 1)
        for col in range(surround_x1, surround_x2 + 1):
            if 0 <= col < game_map.width and 0 <= surround_y1 < game_map.height:
                if game_map.tiles[surround_y1][col].blocked:
                    game_map.tiles[surround_y1][col] = tile.floor

        # Bottom row  (y == room.y2 + 1)
        for col in range(surround_x1, surround_x2 + 1):
            if 0 <= col < game_map.width and 0 <= surround_y2 < game_map.height:
                if game_map.tiles[surround_y2][col].blocked:
                    game_map.tiles[surround_y2][col] = tile.floor

        # Left column  (x == room.x1 - 1)
        for row in range(surround_y1, surround_y2 + 1):
            if 0 <= surround_x1 < game_map.width and 0 <= row < game_map.height:
                if game_map.tiles[row][surround_x1].blocked:
                    game_map.tiles[row][surround_x1] = tile.floor

        # Right column  (x == room.x2 + 1)
        for row in range(surround_y1, surround_y2 + 1):
            if 0 <= surround_x2 < game_map.width and 0 <= row < game_map.height:
                if game_map.tiles[row][surround_x2].blocked:
                    game_map.tiles[row][surround_x2] = tile.floor

    # ------------------------------------------------------------------
    # 8. Populate rooms
    # ------------------------------------------------------------------
    for room in rooms:
        # Skip circular temple and plus-shaped rooms — they have their own special handling
        if isinstance(room, CircleRoom) or isinstance(room, PlusShapedRoom):
            continue
            
        is_stair_room = (room is stairs_up_room or room is stairs_down_room)

        # Check if this room has any prison cell tiles — if so, skip pillars
        # to avoid blocking cell interiors and corridors.
        room_has_prison_tiles = any(
            is_prison_cell_position(game_map, x, y)
            for x, y in room.inner_tiles()
        )

        # --- Pillars in large rooms (not stair rooms, not prison rooms, not special shapes) ---
        if (not is_stair_room and not room_has_prison_tiles and 
            not isinstance(room, LShapedRoom) and not isinstance(room, PlusShapedRoom) and 
            random.random() < 0.4):
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
                if is_prison_cell_position(game_map, rx, ry):
                    continue   # never overwrite prison bars/door/cell floor
                if is_crypt_position(game_map, rx, ry):
                    continue   # never overwrite crypt tombs
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
            if is_prison_cell_position(game_map, chx, chy):
                continue   # don't place chests inside or on prison tiles
            if is_crypt_position(game_map, chx, chy):
                continue   # don't place chests on tomb tiles
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
                elif random.random() < 0.30:
                    if random.random() < 0.15:
                        # Locked chest mimic — rarer and more dangerous than a regular chest mimic
                        mimic = Mimic(chx, chy, 'LC', (100, 110, 130))
                        mimic.name = "Disguised Locked Chest Mimic"
                        mimic.char = 'LM'  # Revealed form gets its own graphic
                        game_map.tiles[chy][chx] = MimicTile(mimic, 'LC', (100, 110, 130), "Locked Chest")
                        game_map.items_on_ground.append(mimic)
                    else:
                        # Locked chest — better loot, requires Thieves' Tools to open
                        locked_chest = LockedChest(chx, chy, contents=generate_locked_loot(level_number))
                        game_map.items_on_ground.append(locked_chest)
                        game_map.tiles[chy][chx] = tile.floor   # clear any prop that was here
                else:
                    chest = Chest(chx, chy, contents=generate_random_loot(level_number))
                    game_map.items_on_ground.append(chest)
                    game_map.tiles[chy][chx] = tile.floor   # clear any prop that was here
                chest_placed = True
            break   # only attempt one chest per room regardless



    return rooms, stairs_positions, torch_light_sources, prison_prisoners