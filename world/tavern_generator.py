from world.tile import tavern_floor, tavern_wall, bar_counter, table, chair, door, fireplace # Ensure 'door' is imported

def generate_tavern(game_map):
    """Generate a cozy tavern layout"""
    width = game_map.width
    height = game_map.height
    
    # Fill with walls first
    for y in range(height):
        for x in range(width):
            game_map.tiles[y][x] = tavern_wall
    
    # Create main tavern room (leave borders as walls)
    for y in range(2, height - 2):
        for x in range(2, width - 2):
            game_map.tiles[y][x] = tavern_floor
    
    # Add bar counter along the top wall
    bar_start_x = width // 4
    bar_end_x = width * 3 // 4
    bar_y = 3
    for x in range(bar_start_x, bar_end_x):
        game_map.tiles[bar_y][x] = bar_counter
    
    # Add tables and chairs scattered around
    tables_positions = [
        (width // 4, height // 2),
        (width * 3 // 4, height // 2),
        (width // 3, height * 2 // 3),
        (width * 2 // 3, height * 2 // 3),
    ]
    
    for table_x, table_y in tables_positions:
        if (2 < table_x < width - 2 and 2 < table_y < height - 2):
            game_map.tiles[table_y][table_x] = table
            
            # Add chairs around table
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                chair_x, chair_y = table_x + dx, table_y + dy
                if (2 < chair_x < width - 2 and 2 < chair_y < height - 2 and
                    game_map.tiles[chair_y][chair_x] == tavern_floor):
                    game_map.tiles[chair_y][chair_x] = chair
    
    # Add fireplace on the left wall
    fireplace_x = 1
    fireplace_y = height // 2
    if fireplace_y > 2 and fireplace_y < height - 2:
        game_map.tiles[fireplace_y][fireplace_x] = fireplace
    if fireplace_y > 2:
        game_map.tiles[fireplace_y - 1][fireplace_x] = fireplace         
    
    # Add exit door on the bottom wall
    door_x = width // 2
    door_y = height - 2
    game_map.tiles[door_y][door_x] = door # Use the imported 'door' tile
    
    # Return door position for player interaction
    return (door_x, door_y)
