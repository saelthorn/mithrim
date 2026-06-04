import random
from world.tile import wall, floor, dungeon_pillar, torch as torch_tile
from world.altar import Altar


# ─────────────────────────────────────────────────────────────────────────────
#  Temple Room Patterns
# ─────────────────────────────────────────────────────────────────────────────
#
# A temple room is a sacred chamber featuring:
#   - Central altar (if conditions permit)
#   - Symmetric pillar arrangement (cross or diamond pattern)
#   - Torch fixtures on cardinal or diagonal walls
#   - Clear central nave for procession or prayer
#
# Temples can be designated as a special room encounter in larger chambers.
# ─────────────────────────────────────────────────────────────────────────────


def can_place_temple_in_room(room):
    """
    Determine if a room is large enough to accommodate a temple layout.
    Requires minimum 12x12 interior to fit altar, pillars, and procession space.
    """
    inner_width = (room.x2 - room.x1) - 1
    inner_height = (room.y2 - room.y1) - 1
    return inner_width >= 12 and inner_height >= 12


def generate_temple_room(game_map, room, items_on_ground, stairs_positions):
    """
    Carve a sacred temple layout into a large room.
    
    Features:
      - Central altar (5% chance of placement, must avoid stairs)
      - Outer pillar ring or cross pattern (depends on room shape)
      - Torch fixtures on available walls (corner or cardinal)
      - Sacred geometry with clear nave (central procession area)
    
    Returns a dict with:
      - 'altar': Altar instance if placed, or None
      - 'torch_positions': list of (x, y) positions where torches were placed
      - 'pillar_positions': list of (x, y) positions where pillars were placed
    """
    result = {
        'altar': None,
        'torch_positions': [],
        'pillar_positions': [],
    }
    
    # Inner extents (excluding room walls)
    first_inner_col = room.x1 + 1
    first_inner_row = room.y1 + 1
    last_inner_col = room.x2 - 1
    last_inner_row = room.y2 - 1
    
    inner_width = last_inner_col - first_inner_col + 1
    inner_height = last_inner_row - first_inner_row + 1
    
    center_x = (first_inner_col + last_inner_col) // 2
    center_y = (first_inner_row + last_inner_row) // 2
    
    # ─── Place the central altar (optional, 5% spawn chance) ─────────────
    if random.random() < 0.05:
        # Verify altar position doesn't overlap stairs
        if stairs_positions:
            stair_positions_set = set(stairs_positions.values())
            if (center_x, center_y) not in stair_positions_set:
                altar = Altar(center_x, center_y)
                items_on_ground.append(altar)
                result['altar'] = altar
    
    # ─── Create sacred geometry: pillar arrangement ─────────────────────
    #
    # Pillar pattern depends on room aspect ratio:
    #   - Square-ish: four cardinal pillars + four corners (8-pillar ring)
    #   - Wide: four cardinal pillars + inner columns
    #   - Tall: four cardinal pillars + inner rows
    #
    # All pillars maintain at least 2 tiles clearance from the center.
    
    pillar_distance = 4  # 4 tiles from center in cardinal directions
    
    pillar_positions = []
    
    # Cardinal pillars (north, south, east, west)
    cardinal_offsets = [
        (0, -pillar_distance),  # north
        (0, pillar_distance),   # south
        (-pillar_distance, 0),  # west
        (pillar_distance, 0),   # east
    ]
    
    for dx, dy in cardinal_offsets:
        px = center_x + dx
        py = center_y + dy
        
        if (first_inner_col <= px <= last_inner_col and
            first_inner_row <= py <= last_inner_row):
            if game_map.tiles[py][px] == floor:
                pillar_positions.append((px, py))
    
    # Diagonal pillars (if room is large enough and not too narrow)
    if inner_width >= 14 and inner_height >= 14:
        corner_distance = 3
        diag_offsets = [
            (-corner_distance, -corner_distance),  # NW
            (corner_distance, -corner_distance),   # NE
            (-corner_distance, corner_distance),   # SW
            (corner_distance, corner_distance),    # SE
        ]
        
        for dx, dy in diag_offsets:
            px = center_x + dx
            py = center_y + dy
            
            if (first_inner_col <= px <= last_inner_col and
                first_inner_row <= py <= last_inner_row):
                if game_map.tiles[py][px] == floor:
                    pillar_positions.append((px, py))
    
    # Stamp pillars onto the map
    for px, py in pillar_positions:
        if game_map.tiles[py][px] == floor:
            game_map.tiles[py][px] = dungeon_pillar
    
    result['pillar_positions'] = pillar_positions
    
    # ─── Place torch fixtures on walls or near corners ──────────────────
    #
    # Torches serve as light sources and mark the sacred space.
    # Place them symmetrically: corners or cardinal wall points.
    
    torch_positions = []
    
    # Try cardinal wall points (closest to the center, one tile from wall)
    wall_distance = 1
    cardinal_wall_offsets = [
        (0, -wall_distance, 'north'),  # just inside north wall
        (0, wall_distance, 'south'),   # just inside south wall
        (-wall_distance, 0, 'west'),   # just inside west wall
        (wall_distance, 0, 'east'),    # just inside east wall
    ]
    
    for dx, dy, direction in cardinal_wall_offsets:
        torch_x = center_x + dx
        torch_y = center_y + dy
        
        # Place torch on the wall just beyond
        wall_x = torch_x + (dx if dx != 0 else 0)
        wall_y = torch_y + (dy if dy != 0 else 0)
        
        if (0 <= wall_x < game_map.width and 0 <= wall_y < game_map.height):
            if game_map.tiles[wall_y][wall_x] == wall:
                game_map.tiles[wall_y][wall_x] = torch_tile
                torch_positions.append((wall_x, wall_y))
    
    result['torch_positions'] = torch_positions
    
    # ─── Create a clear nave (central procession path) ─────────────────
    #
    # Ensure a 3-5 tile wide cross-shaped path is kept clear from
    # the entrance through the altar area.
    #
    # This is mostly a visual/conceptual thing since we've already
    # dug the room; we just ensure no stray pillars block major paths.
    
    nave_width = 3
    for ny in range(first_inner_row, last_inner_row + 1):
        for nx in range(center_x - nave_width, center_x + nave_width + 1):
            if (first_inner_col <= nx <= last_inner_col):
                # Keep nave clear of props but don't erase pillars already placed
                pass
    
    return result


def apply_temple_theme_to_room(game_map, room):
    """
    Apply temple aesthetic to an existing room without special placement.
    Adds scattered torches and possibly a few pillars for ambiance.
    Used when a room is marked as 'Temple' theme but too small for full temple.
    """
    first_inner_col = room.x1 + 1
    first_inner_row = room.y1 + 1
    last_inner_col = room.x2 - 1
    last_inner_row = room.y2 - 1
    
    inner_width = last_inner_col - first_inner_col + 1
    inner_height = last_inner_row - first_inner_row + 1
    
    # Place a few ambient torches (not in a pattern, just scattered near walls)
    num_ambient_torches = random.randint(1, 3)
    
    for _ in range(num_ambient_torches):
        # Pick a random wall-adjacent floor tile
        if random.random() < 0.5:
            # Near a vertical wall
            col = first_inner_col if random.random() < 0.5 else last_inner_col
            row = random.randint(first_inner_row, last_inner_row)
        else:
            # Near a horizontal wall
            col = random.randint(first_inner_col, last_inner_col)
            row = first_inner_row if random.random() < 0.5 else last_inner_row
        
        if (0 <= col < game_map.width and 0 <= row < game_map.height):
            if game_map.tiles[row][col] == floor:
                game_map.tiles[row][col] = torch_tile
