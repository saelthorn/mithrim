import random
from world.tile import Tile

# Water tile definitions
river = Tile(blocked=False, char='~', color=(0, 100, 200), block_sight=False, name="River")
lake = Tile(blocked=False, char='≈', color=(0, 80, 180), block_sight=False, name="Lake")

def generate_water_features(game_map, rooms, water_spawn_chance=0.4):
    """
    Generate rivers and lakes in the dungeon with a given spawn chance.
    Returns a list of water tiles created.
    """
    water_tiles = []
    
    if random.random() > water_spawn_chance:
        return water_tiles  # No water features this time
    
    # Determine water feature type (60% river, 30% lake)
    if random.random() < 0.6:
        water_tiles.extend(_generate_river(game_map, rooms))
    else:
        water_tiles.extend(_generate_lake(game_map, rooms))
    
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
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            new_x, new_y = x + dx, y + dy
            if (0 <= new_x < game_map.width and 
                0 <= new_y < game_map.height and
                (game_map.tiles[new_y][new_x] == floor or game_map.tiles[new_y][new_x] == wall) and
                random.random() < 0.3):
                game_map.tiles[new_y][new_x] = river
                river_tiles.append((new_x, new_y))
    

    # After placing tiles, debug the first one
    if river_tiles:
        first_tile = game_map.tiles[river_tiles[0][1]][river_tiles[0][0]]
        print(f"DEBUG: River tile placed at {river_tiles[0]}: char='{first_tile.char}', color={first_tile.color}")

    return river_tiles

def _generate_lake(game_map, rooms):
    """Generate a lake in one of the larger rooms."""
    from world.tile import floor, wall  # Local import to avoid circular import
    lake_tiles = []
    
    # Find the largest room (excluding the first room which is player start)
    if len(rooms) <= 1:
        return lake_tiles
    
    # Filter rooms to find suitable ones for lakes (minimum size)
    suitable_rooms = []
    for room in rooms[1:]:  # Skip player start room
        room_width = room.x2 - room.x1 - 1
        room_height = room.y2 - room.y1 - 1
        if room_width >= 8 and room_height >= 8:  # Minimum size for a lake
            suitable_rooms.append(room)
    
    if not suitable_rooms:
        return lake_tiles
    
    lake_room = random.choice(suitable_rooms)
    
    # Calculate lake center and size
    center_x, center_y = lake_room.center()
    # Ensure lake doesn't fill the entire room, leave a border
    max_lake_width = max(1, (lake_room.x2 - lake_room.x1 - 4) // 2) # -4 for 2-tile border on each side
    max_lake_height = max(1, (lake_room.y2 - lake_room.y1 - 4) // 2)
    
    if max_lake_width < 2 or max_lake_height < 2: # Ensure a minimum lake size
        return lake_tiles

    lake_width_radius = random.randint(2, max_lake_width)
    lake_height_radius = random.randint(2, max_lake_height)
    
    # Create elliptical lake
    for y in range(center_y - lake_height_radius, center_y + lake_height_radius + 1):
        for x in range(center_x - lake_width_radius, center_x + lake_width_radius + 1):
            if (((x - center_x) ** 2) / (lake_width_radius ** 2) + 
                ((y - center_y) ** 2) / (lake_height_radius ** 2)) <= 1:
                if (0 <= x < game_map.width and 
                    0 <= y < game_map.height and
                    (game_map.tiles[y][x] == floor or game_map.tiles[y][x] == wall)):
                    # Replace floor or wall with lake tile
                    game_map.tiles[y][x] = lake
                    lake_tiles.append((x, y))


    # After placing tiles, debug the first one
    if lake_tiles:
        first_tile = game_map.tiles[lake_tiles[0][1]][lake_tiles[0][0]]
        print(f"DEBUG: Lake tile placed at {lake_tiles[0]}: char='{first_tile.char}', color={first_tile.color}")

    return lake_tiles

def is_water_tile(tile):
    """Check if a tile is a water tile (more robust check)."""
    # Check by exact match first
    if tile == river or tile == lake:
        return True
    # Fallback: Check by name or char if the tile object might be different
    if hasattr(tile, 'name') and 'River' in tile.name:
        return True
    if hasattr(tile, 'name') and 'Lake' in tile.name:
        return True
    if hasattr(tile, 'char') and tile.char in ['~', '≈']:
        return True
    return False
