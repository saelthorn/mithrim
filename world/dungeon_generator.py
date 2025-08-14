import random
from random import randint, choice
from world import tile
from world.tile import stairs_down, stairs_up, dungeon_door, bones, torch, crate, barrel, wall, floor, dungeon_grass, rubble, cob_web, mushroom, fresh_bones, MimicTile
from items.items import Chest, generate_random_loot
from entities.monster import Mimic

class RectRoom:
    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h

    def center(self):
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    def intersects(self, other):
        return (
            self.x1 <= other.x2 and self.x2 >= other.x1 and
            self.y1 <= other.y1 and self.y2 >= other.y1
        )

def dig_room(game_map, room):
    for y in range(room.y1 + 1, room.y2):
        for x in range(room.x1 + 1, room.x2):
            game_map.tiles[y][x] = tile.floor

def dig_tunnel_x(game_map, x1, x2, y):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        game_map.tiles[y][x] = tile.floor

def dig_tunnel_y(game_map, y1, y2, x):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        game_map.tiles[y][x] = tile.floor

def generate_dungeon(game_map, level_number, max_rooms=5, room_min_size=5, room_max_size=10):
    rooms = []
    stairs_positions = {}
    
    floor_decoration_tiles = [crate, barrel, bones, dungeon_grass, cob_web, rubble, mushroom, fresh_bones] 
    floor_decoration_chance = 0.2  # Ensure this is defined
    torch_placement_chance = 0.1
    torch_light_sources = []
    
    # Attempt to generate rooms
    for _ in range(max_rooms * 2): # Try more times than max_rooms to ensure we get enough
        w = randint(room_min_size, room_max_size)
        h = randint(room_min_size, room_max_size)
        x = randint(0, game_map.width - w - 1)
        y = randint(0, game_map.height - h - 1)
        new_room = RectRoom(x, y, w, h)
        
        # Check for intersection with existing rooms
        intersects_existing = False
        for existing_room in rooms:
            if new_room.intersects(existing_room):
                intersects_existing = True
                break
        
        if not intersects_existing:
            dig_room(game_map, new_room)
            
            # Connect to previous room if not the first room
            if rooms:
                prev_x, prev_y = rooms[-1].center()
                new_x, new_y = new_room.center()
                if randint(0, 1):
                    dig_tunnel_x(game_map, prev_x, new_x, prev_y)
                    dig_tunnel_y(game_map, prev_y, new_y, new_x)
                else:
                    dig_tunnel_y(game_map, prev_y, new_y, prev_x)
                    dig_tunnel_x(game_map, prev_x, new_x, new_y)
            
            rooms.append(new_room)
            if len(rooms) >= max_rooms: # Stop if we have enough rooms
                break

    # If we didn't manage to create enough rooms, use what we have
    if not rooms: # Should not happen if max_rooms > 0
        # Fallback for extremely rare cases or small maps
        rooms.append(RectRoom(game_map.width // 2 - 2, game_map.height // 2 - 2, 5, 5))
        dig_room(game_map, rooms[0])

    # --- Place Stairs (Guaranteed Placement) ---
    # Place stairs_down in the last room generated
    if rooms:
        stairs_down_room = rooms[-1]
        stairs_x, stairs_y = stairs_down_room.center()
        
        found_stairs_down_spot = False
        possible_stairs_spots = [(stairs_x, stairs_y)] + \
                                [(stairs_x + dx, stairs_y + dy) for dx in [-1, 0, 1] for dy in [-1, 0, 1] if (dx, dy) != (0,0)] + \
                                [(x, y) for y in range(stairs_down_room.y1 + 1, stairs_down_room.y2) for x in range(stairs_down_room.x1 + 1, stairs_down_room.x2)]
        
        for sx, sy in possible_stairs_spots:
            if game_map.is_walkable(sx, sy):
                game_map.tiles[sy][sx] = stairs_down
                stairs_positions['down'] = (sx, sy)
                found_stairs_down_spot = True
                # Remove any item that might have been at this spot to guarantee stairs visibility
                game_map.items_on_ground = [item for item in game_map.items_on_ground if not (item.x == sx and item.y == sy)]
                break
        
        if not found_stairs_down_spot:
            # Emergency fallback for stairs_down
            player_start_x, player_start_y = rooms[0].center()
            game_map.tiles[player_start_y][player_start_x] = stairs_down
            stairs_positions['down'] = (player_start_x, player_start_y)
            game_map.items_on_ground = [item for item in game_map.items_on_ground if not (item.x == player_start_x and item.y == player_start_y)]

    # Place stairs_up in the first room generated (player's spawn room)
    if rooms:
        stairs_up_room = rooms[0]
        stairs_x, stairs_y = stairs_up_room.center()

        found_stairs_up_spot = False
        # Prioritize center, then adjacent, then random within room
        possible_stairs_spots = [(stairs_x, stairs_y)] + \
                                [(stairs_x + dx, stairs_y + dy) for dx in [-1, 0, 1] for dy in [-1, 0, 1] if (dx, dy) != (0,0)] + \
                                [(x, y) for y in range(stairs_up_room.y1 + 1, stairs_up_room.y2) for x in range(stairs_up_room.x1 + 1, stairs_up_room.x2)]
        
        for sx, sy in possible_stairs_spots:
            # Ensure it's walkable AND not the same spot as stairs_down (if only one room)
            if game_map.is_walkable(sx, sy) and (sx, sy) != stairs_positions.get('down'):
                game_map.tiles[sy][sx] = stairs_up
                stairs_positions['up'] = (sx, sy)
                found_stairs_up_spot = True
                game_map.items_on_ground = [item for item in game_map.items_on_ground if not (item.x == sx and item.y == sy)]
                break
        
        if not found_stairs_up_spot:
            # Emergency fallback for stairs_up (should be rare)
            game_map.tiles[stairs_x][stairs_y] = stairs_up # Try center again
            stairs_positions['up'] = (stairs_x, stairs_y)
            game_map.items_on_ground = [item for item in game_map.items_on_ground if not (item.x == stairs_x and item.y == stairs_y)]

    # --- Populate Rooms with Decorations, Torches, Chests/Mimics ---
    for room in rooms:
        # Skip the room where stairs are placed for item/decoration spawning
        # to avoid overwriting stairs, unless it's the only room.
        # This logic needs to be careful not to skip the first room entirely if it's the only one.
        if len(rooms) > 1: # Only skip if there's more than one room
            if 'down' in stairs_positions and room.center() == stairs_positions['down']:
                continue 
            if 'up' in stairs_positions and room.center() == stairs_positions['up']:
                continue

        # First pass: Place floor decorations
        for ry in range(room.y1 + 1, room.y2):
            for rx in range(room.x1 + 1, room.x2):
                # Skip if this spot is where stairs are
                if 'down' in stairs_positions and (rx, ry) == stairs_positions['down']:
                    continue
                if 'up' in stairs_positions and (rx, ry) == stairs_positions['up']:
                    continue

                if game_map.tiles[ry][rx] == floor: # Only place on floor tiles
                    # --- Floor Decorations ---
                    if random.random() < floor_decoration_chance:
                        if random.random() < 0.1: # 15% chance for a decoration to be a Mimic
                            mimic_type_tile_obj = random.choice([crate, barrel])
                            mimic_entity_disguise_char = 'K' if mimic_type_tile_obj == crate else 'B'
                            mimic_tile_initial_display_char = 'k' if mimic_type_tile_obj == crate else 'b'
                            
                            mimic_entity = Mimic(rx, ry, mimic_entity_disguise_char, mimic_type_tile_obj.color)
                            mimic_entity.name = f"Disguised {mimic_type_tile_obj.name} Mimic"
                            
                            game_map.tiles[ry][rx] = MimicTile(mimic_entity, mimic_tile_initial_display_char, mimic_type_tile_obj.color, mimic_type_tile_obj.name)
                            game_map.items_on_ground.append(mimic_entity) 
                        else:
                            chosen_decoration = random.choice(floor_decoration_tiles)
                            game_map.tiles[ry][rx] = chosen_decoration

        # --- Chests (and Chest Mimics) ---
        # Place chests/mimics at room center, but only if not already occupied by stairs
        chest_spawn_x, chest_spawn_y = room.center()
        if 'down' in stairs_positions and (chest_spawn_x, chest_spawn_y) == stairs_positions['down']:
            continue # Skip if stairs_down are at the center of this room
        if 'up' in stairs_positions and (chest_spawn_x, chest_spawn_y) == stairs_positions['up']:
            continue # Skip if stairs_up are at the center of this room

        if random.random() < 0.6: # Increased overall chest spawn chance to 60%
            # Check if the spot is already occupied by an item (Mimic or Chest)
            is_occupied_by_item = False
            for existing_item in game_map.items_on_ground:
                if existing_item.x == chest_spawn_x and existing_item.y == chest_spawn_y:
                    is_occupied_by_item = True
                    break
            
            # If the spot is already occupied by an item, skip placing another chest/mimic here.
            if is_occupied_by_item:
                continue # Skip placing a chest/mimic if an item is already here.

            # If the spot is not occupied by an item, proceed with placing the chest/mimic.
            # IMPORTANT: If a decorative tile (like crate/barrel) was placed here,
            # it will be overwritten by the MimicTile or remain a floor tile for the Chest.
            # This is the correct behavior.
            if random.random() < 0.2: # 75% chance for a chest to be a mimic
                new_mimic = Mimic(chest_spawn_x, chest_spawn_y, 'C', (139, 69, 19))
                new_mimic.name = "Disguised Chest Mimic"
                game_map.tiles[chest_spawn_y][chest_spawn_x] = MimicTile(new_mimic, 'C', (139, 69, 19), "Chest")
                game_map.items_on_ground.append(new_mimic) 
            else:
                chest_contents = generate_random_loot(level_number)
                new_chest = Chest(chest_spawn_x, chest_spawn_y, contents=chest_contents)
                game_map.items_on_ground.append(new_chest)
                # Ensure the tile under the chest is a floor tile, not a decoration.
                game_map.tiles[chest_spawn_y][chest_spawn_x] = floor # <--- ADD THIS LINE

    return rooms, stairs_positions, torch_light_sources





