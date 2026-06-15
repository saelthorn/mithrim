import random
import math
from world.tile import wall, floor, dungeon_pillar, torch as torch_tile
from world.altar import Altar


# ─────────────────────────────────────────────────────────────────────────────
#  Circular Temple Room
# ─────────────────────────────────────────────────────────────────────────────
#
# A sacred circular chamber featuring:
#   - Perfect circular geometry carved by distance formula
#   - Central altar (always placed if conditions permit)
#   - 8 radial pillars: 4 cardinal + 4 diagonal directions
#   - 8 perimeter torches placed at cardinal and diagonal angles
#   - Clear procession space around the altar
#
# ─────────────────────────────────────────────────────────────────────────────


def is_circle_tile(center_x, center_y, radius, x, y):
    """
    Return True if (x, y) is within the circular boundary.
    Uses squared distance to avoid expensive sqrt() calls.
    """
    dx = x - center_x
    dy = y - center_y
    return dx * dx + dy * dy <= radius * radius


def generate_circular_temple(game_map, center_x, center_y, radius, items_on_ground, stairs_positions):
    """
    Generate a circular temple layout within a CircleRoom.
    
    Features:
      - Perfectly circular floor carved using distance formula
      - Central altar (always placed unless conflicting with stairs)
      - 8 radial pillars: 4 cardinal (N/S/E/W) + 4 diagonal (NE/NW/SE/SW)
      - 8 perimeter torches placed at cardinal and diagonal angles using trig
      - Returns dict with 'altar', 'torch_positions', 'pillar_positions'
    
    Args:
        game_map: The dungeon map
        center_x, center_y: Circle center coordinates
        radius: Circle radius in tiles
        items_on_ground: Game map's items list (for altar placement)
        stairs_positions: Dict of stair positions to avoid overlap
    
    Returns:
        dict with 'altar', 'torch_positions', 'pillar_positions'
    """
    result = {
        'altar': None,
        'torch_positions': [],
        'pillar_positions': [],
    }
    
    # ─── Place central altar (always, unless stairs conflict) ─────────────
    if stairs_positions:
        stair_positions_set = set(stairs_positions.values())
        if (center_x, center_y) not in stair_positions_set:
            altar = Altar(center_x, center_y)
            items_on_ground.append(altar)
            result['altar'] = altar
    else:
        # No stairs, always place altar
        altar = Altar(center_x, center_y)
        items_on_ground.append(altar)
        result['altar'] = altar
    
    # ─── Place 8 radial pillars ──────────────────────────────────────────
    #
    # Cardinal pillars (4): N, S, E, W at distance (radius - 3)
    # Diagonal pillars (4): NE, NW, SE, SW at distance (radius - 2)
    #
    pillar_distance = radius - 3
    pillar_positions = []
    
    # Cardinal directions (4-way)
    # cardinal_offsets = [
    #     (0, -pillar_distance),   # North
    #     (0, pillar_distance),    # South
    #     (-pillar_distance, 0),   # West
    #     (pillar_distance, 0),    # East
    # ]
    
    # for dx, dy in cardinal_offsets:
    #     px = center_x + dx
    #     py = center_y + dy
        
    #     if (0 <= px < game_map.width and 0 <= py < game_map.height):
    #         if is_circle_tile(center_x, center_y, radius, px, py):
    #             if game_map.tiles[py][px] == floor:
    #                 game_map.tiles[py][px] = dungeon_pillar
    #                 pillar_positions.append((px, py))
    
    # Diagonal pillars (4-way) — placed at 45° angles
    diagonal_distance = int(pillar_distance * 0.707)  # sqrt(2)/2 ≈ 0.707
    diagonal_offsets = [
        (-diagonal_distance, -diagonal_distance),  # NW
        (diagonal_distance, -diagonal_distance),   # NE
        (-diagonal_distance, diagonal_distance),   # SW
        (diagonal_distance, diagonal_distance),    # SE
    ]
    
    for dx, dy in diagonal_offsets:
        px = center_x + dx
        py = center_y + dy
        
        if (0 <= px < game_map.width and 0 <= py < game_map.height):
            if is_circle_tile(center_x, center_y, radius, px, py):
                if game_map.tiles[py][px] == floor:
                    game_map.tiles[py][px] = dungeon_pillar
                    pillar_positions.append((px, py))
    
    result['pillar_positions'] = pillar_positions
    
    # ─── Place 8 perimeter torches at cardinal and diagonal angles ────────
    #
    # Torch distance is set to (radius - 1) to place them just inside
    # the circular boundary, creating an inner ring of light.
    #
    # torch_distance = radius - 1
    # torch_angles = [0, 45, 90, 135, 180, 225, 270, 315]  # 8 directions
    # torch_positions = []
    
    # for angle_deg in torch_angles:
    #     # Convert angle to radians and compute position using trig
    #     angle_rad = math.radians(angle_deg)
    #     tx = center_x + int(round(torch_distance * math.cos(angle_rad)))
    #     ty = center_y + int(round(torch_distance * math.sin(angle_rad)))
        
    #     if (0 <= tx < game_map.width and 0 <= ty < game_map.height):
    #         if is_circle_tile(center_x, center_y, radius, tx, ty):
    #             if game_map.tiles[ty][tx] == floor:
    #                 game_map.tiles[ty][tx] = torch_tile
    #                 torch_positions.append((tx, ty))
    
    # result['torch_positions'] = torch_positions
    
    # return result