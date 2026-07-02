import random
from world.tile import Tile

# Water tile definitions
river = Tile(blocked=False, char='~', color=(0, 100, 200), block_sight=False, name="River")
lake = Tile(blocked=False, char='≈', color=(0, 80, 180), block_sight=False, name="Lake")
sewer_water = Tile(blocked=False, char='~', color=(25, 75, 150), block_sight=False, name="Sewer Water")  # Slightly different color for sewers

def generate_water_features(game_map, rooms, water_spawn_chance=0.6):
    """
    Generate rivers, lakes, or sewer hallways in the dungeon with a given spawn chance.
    Returns a list of water tiles created.
    """
    water_tiles = []
    
    if random.random() > water_spawn_chance:
        return water_tiles  # No water features this time
    
    # Determine water feature type (40% river, 30% lake, 30% sewer hallway)
    rand = random.random()
    if rand < 0.05:
        water_tiles.extend(_generate_river(game_map, rooms))
    elif rand < 0.3:
        water_tiles.extend(_generate_lake(game_map, rooms))
    else:
        water_tiles.extend(_generate_sewer_hallway(game_map, rooms))
    
    # DEBUG: Print total water tiles (remove after testing)
    print(f"DEBUG: Water features generated {len(water_tiles)} tiles")    
    return water_tiles

def _generate_river(game_map, rooms):
    """Generate a river flowing through the dungeon."""
    from world.tile import floor, wall  # Local import to avoid circular import
    river_tiles = []
    
    if len(rooms) < 2:
        return river_tiles  # Need at least 2 rooms for a river
    
    # Choose two distant rooms to connect with a river
    # Ensure chosen rooms are not the player's start or stairs rooms
    candidate_rooms = [r for r in rooms if r != rooms[0] and r != rooms[-1]]
    if len(candidate_rooms) < 2:
        candidate_rooms = rooms # Fallback to all rooms if not enough non-start/end rooms
    
    if len(candidate_rooms) < 2:
        return river_tiles # Still not enough rooms

    room1, room2 = random.sample(candidate_rooms, 2)
    start_x, start_y = room1.center()
    end_x, end_y = room2.center()
    
    # Create river using Bresenham's line algorithm
    dx = abs(end_x - start_x)
    dy = abs(end_y - start_y)
    sx = 1 if start_x < end_x else -1
    sy = 1 if start_y < end_y else -1
    err = dx - dy
    
    current_x, current_y = start_x, start_y
    
    while True:
        if (0 <= current_x < game_map.width and 
            0 <= current_y < game_map.height and
            (game_map.tiles[current_y][current_x] == floor or game_map.tiles[current_y][current_x] == wall)):
            # Replace floor or wall with river tile
            game_map.tiles[current_y][current_x] = river
            river_tiles.append((current_x, current_y))
        
        if current_x == end_x and current_y == end_y:
            break
            
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            current_x += sx
        if e2 < dx:
            err += dx
            current_y += sy
    
    # Add some river width variations
    for x, y in list(river_tiles):
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0), (0, -2), (0, 2)]:
            new_x, new_y = x + dx, y + dy
            if (0 <= new_x < game_map.width and 
                0 <= new_y < game_map.height and
                (game_map.tiles[new_y][new_x] == floor or game_map.tiles[new_y][new_x] == wall) and
                random.random() < 0.45):
                game_map.tiles[new_y][new_x] = river
                river_tiles.append((new_x, new_y))
    

    # After placing tiles, debug the first one
    if river_tiles:
        first_tile = game_map.tiles[river_tiles[0][1]][river_tiles[0][0]]
        print(f"DEBUG: River tile placed at {river_tiles[0]}: char='{first_tile.char}', color={first_tile.color}")

    return river_tiles

def _generate_lake(game_map, rooms):
    """Generate an irregular lake in one of the larger rooms."""
    from world.tile import floor, wall  # Local import to avoid circular import
    lake_tiles = []
    
    # Find the largest room (excluding the first room which is player start)
    if len(rooms) <= 1:
        return lake_tiles
    
    # Choose any room except the player's starting room, ignoring room size.
    candidate_rooms = [room for room in rooms[1:]]
    if not candidate_rooms:
        return lake_tiles

    lake_room = random.choice(candidate_rooms)

    # Calculate lake center and size independently from room dimensions.
    center_x, center_y = lake_room.center()
    min_lake_width = 5
    min_lake_height = 4
    max_lake_width = min(max(6, game_map.width // 6), 12)
    max_lake_height = min(max(5, game_map.height // 8), 10)

    lake_width_radius = random.randint(min_lake_width, max_lake_width)
    lake_height_radius = random.randint(min_lake_height, max_lake_height)
    
    # Create irregular lake with noise for organic edges
    for y in range(center_y - lake_height_radius - 3, center_y + lake_height_radius + 4):
        for x in range(center_x - lake_width_radius - 3, center_x + lake_width_radius + 4):
            # Calculate distance from center with noise
            dx = x - center_x
            dy = y - center_y
            
            # Add random noise to create irregular edges (-0.7 to +0.3)
            noise = random.uniform(-0.7, 0.3)
            distance_squared = (dx ** 2) / (lake_width_radius ** 2) + (dy ** 2) / (lake_height_radius ** 2) + noise
            
            if distance_squared <= 1.0:  # Within the irregular ellipse
                if (0 <= x < game_map.width and 
                    0 <= y < game_map.height and
                    (game_map.tiles[y][x] == floor or game_map.tiles[y][x] == wall)):
                    # Replace floor or wall with lake tile
                    game_map.tiles[y][x] = lake
                    lake_tiles.append((x, y))
    
    # Add small islands (remove some tiles from the center)
    if lake_tiles:
        num_islands = random.randint(1, min(3, max(1, len(lake_tiles) // 8)))  # At least some potential islands
        for _ in range(num_islands):
            # Pick a random lake tile near the center
            center_tiles = [tile for tile in lake_tiles if 
                          abs(tile[0] - center_x) <= lake_width_radius // 2 and 
                          abs(tile[1] - center_y) <= lake_height_radius // 2]
            if center_tiles:
                island_x, island_y = random.choice(center_tiles)
                # Remove a small cluster of tiles for the island
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        ix, iy = island_x + dx, island_y + dy
                        if (ix, iy) in lake_tiles:
                            lake_tiles.remove((ix, iy))
                            # Restore to floor tile
                            game_map.tiles[iy][ix] = floor
    
    # Add some shallow water edges (optional: vary appearance, but for now just ensure edges are clean)
    # You could add different water tiles here if you have them
    
    # After placing tiles, debug the first one
    if lake_tiles:
        first_tile = game_map.tiles[lake_tiles[0][1]][lake_tiles[0][0]]
        print(f"DEBUG: Lake tile placed at {lake_tiles[0]}: char='{first_tile.char}', color={first_tile.color}")

    return lake_tiles

def _generate_sewer_hallway(game_map, rooms):
    """Generate a sewer hallway connecting rooms with drain-like water channels."""
    from world.tile import floor, wall  # Local import to avoid circular import
    sewer_tiles = []

    if len(rooms) < 3:
        return sewer_tiles  # Need at least 3 rooms for a sewer hallway

    room1, room2 = random.sample(rooms, 2)

    def _room_edge_point(room):
        """Get a random edge point of a room, safely handling small rooms."""
        # Ensure room has minimum dimensions (handles 3x3 hub rooms)
        room_width = room.x2 - room.x1
        room_height = room.y2 - room.y1
        
        # Safe offsets based on room size
        x_offset = min(1, max(0, room_width // 3))
        y_offset = min(1, max(0, room_height // 3))
        
        if random.random() < 0.5:
            # Horizontal: pick random x, fixed y (top or bottom)
            x_min = room.x1 + x_offset
            x_max = room.x2 - x_offset
            if x_min < x_max:
                x = random.randint(x_min, x_max - 1)
            else:
                x = (room.x1 + room.x2) // 2
            y = room.y1 + y_offset if random.random() < 0.5 else room.y2 - y_offset - 1
            return x, y
        else:
            # Vertical: fixed x, pick random y
            y_min = room.y1 + y_offset
            y_max = room.y2 - y_offset
            if y_min < y_max:
                y = random.randint(y_min, y_max - 1)
            else:
                y = (room.y1 + room.y2) // 2
            x = room.x1 + x_offset if random.random() < 0.5 else room.x2 - x_offset - 1
            return x, y

    start_x, start_y = _room_edge_point(room1)
    end_x, end_y = _room_edge_point(room2)

    def _carve_tile(cx, cy, horizontal=True):
        if not (0 <= cx < game_map.width and 0 <= cy < game_map.height):
            return

        if game_map.tiles[cy][cx] in (floor, wall):
            game_map.tiles[cy][cx] = sewer_water
            sewer_tiles.append((cx, cy))

        if horizontal:
            for dy in (-1, 1):
                if 0 <= cy + dy < game_map.height and game_map.tiles[cy + dy][cx] == wall:
                    game_map.tiles[cy + dy][cx] = floor
        else:
            for dx in (-1, 1):
                if 0 <= cx + dx < game_map.width and game_map.tiles[cy][cx + dx] == wall:
                    game_map.tiles[cy][cx + dx] = floor

    def _carve_segment(x1, y1, x2, y2):
        if x1 == x2:
            step = 1 if y2 > y1 else -1
            for y in range(y1, y2 + step, step):
                _carve_tile(x1, y, horizontal=False)
        elif y1 == y2:
            step = 1 if x2 > x1 else -1
            for x in range(x1, x2 + step, step):
                _carve_tile(x, y1, horizontal=True)

    def _carve_chamber(cx, cy):
        for ox in range(-1, 2):
            for oy in range(-1, 2):
                tx, ty = cx + ox, cy + oy
                if 0 <= tx < game_map.width and 0 <= ty < game_map.height:
                    if abs(ox) + abs(oy) <= 1:
                        if game_map.tiles[ty][tx] in (floor, wall):
                            game_map.tiles[ty][tx] = sewer_water
                            sewer_tiles.append((tx, ty))
                    elif game_map.tiles[ty][tx] == wall:
                        game_map.tiles[ty][tx] = floor

    if random.random() < 0.5:
        mid_x, mid_y = end_x, start_y
    else:
        mid_x, mid_y = start_x, end_y

    _carve_chamber(start_x, start_y)
    _carve_segment(start_x, start_y, mid_x, mid_y)
    _carve_segment(mid_x, mid_y, end_x, end_y)
    _carve_chamber(end_x, end_y)

    for _ in range(random.randint(4, 8)):
        if not sewer_tiles:
            break
        wx, wy = random.choice(sewer_tiles)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = wx + dx, wy + dy
            if (0 <= nx < game_map.width and 0 <= ny < game_map.height and
                game_map.tiles[ny][nx] == floor and random.random() < 0.35):
                game_map.tiles[ny][nx] = sewer_water
                sewer_tiles.append((nx, ny))

    if sewer_tiles:
        first_tile = game_map.tiles[sewer_tiles[0][1]][sewer_tiles[0][0]]
        print(f"DEBUG: Sewer tile placed at {sewer_tiles[0]}: char='{first_tile.char}', color={first_tile.color}")

    return sewer_tiles

def is_water_tile(tile):
    """Check if a tile is a water tile (more robust check)."""
    # Check by exact match first
    if tile == river or tile == lake or tile == sewer_water:
        return True
    # Fallback: Check by name or char if the tile object might be different
    if hasattr(tile, 'name') and ('River' in tile.name or 'Lake' in tile.name or 'Sewer' in tile.name):
        return True
    if hasattr(tile, 'char') and tile.char in ['~', '≈']:
        return True
    return False