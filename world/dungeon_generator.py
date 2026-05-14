import random
from random import randint, choice
from world import tile
from world.tile import stairs_down, stairs_up, dungeon_door, bones, torch, crate, barrel, wall, floor, dungeon_grass, dungeon_grass_two, dungeon_floor_two, dungeon_floor_three, dungeon_floor_four, dungeon_floor_five, dungeon_floor_six, rubble, cob_web, mushroom, fresh_bones, dungeon_pillar, MimicTile, TrapTile
from items.items import Chest, generate_random_loot
from entities.monster import Mimic
from world.altar import Altar
from traps import DartTrap, SpikeTrap, FireTrap, ExplosiveTrap, AcidSprayTrap
from world.water_features import generate_water_features, river, lake, sewer_water # NEW: Import water features generator and tile types

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
    
def get_floor_tile(x, y):
    if random.random() < 0.2:  # 20% chance for a variant
        return random.choice([tile.dungeon_floor_two, tile.dungeon_floor_three, tile.dungeon_floor_four, tile.dungeon_floor_five, tile.dungeon_floor_six, tile.bones, tile.mushroom, tile.cob_web])
    return tile.floor

def dig_room(game_map, room):
    for y in range(room.y1 + 1, room.y2):
        for x in range(room.x1 + 1, room.x2):
            game_map.tiles[y][x] = get_floor_tile(x, y)

def dig_tunnel_x(game_map, x1, x2, y):
    for x in range(min(x1, x2), max(x1, x2) + 1):
        game_map.tiles[y][x] = get_floor_tile(x, y)

def dig_tunnel_y(game_map, y1, y2, x):
    for y in range(min(y1, y2), max(y1, y2) + 1):
        game_map.tiles[y][x] = get_floor_tile(x, y)
def generate_dungeon(game_map, level_number, max_rooms=14, room_min_size=5, room_max_size=12):
    rooms = []
    stairs_positions = {}
    
    floor_decoration_tiles = [crate, barrel, bones, dungeon_grass, cob_web, rubble, mushroom, fresh_bones, dungeon_grass_two, dungeon_floor_two, dungeon_floor_three, dungeon_floor_four, dungeon_floor_five, dungeon_floor_six ] 
    floor_decoration_chance = 0.12  # Ensure this is defined
    torch_light_sources = []

    # Trap Definitions and Chance
    possible_traps = [DartTrap, SpikeTrap, FireTrap, ExplosiveTrap, AcidSprayTrap] # List of trap instances
    trap_placement_chance = 0.05 # 5% chance for a floor tile to become a trap    
    
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

    # Determine stairs rooms: stairs_up in first room, stairs_down in farthest room
    stairs_up_room = rooms[0]
    if len(rooms) > 1:
        def distance(r1, r2):
            c1 = r1.center()
            c2 = r2.center()
            return ((c1[0] - c2[0])**2 + (c1[1] - c2[1])**2)**0.5
        stairs_down_room = max(rooms[1:], key=lambda r: distance(stairs_up_room, r))
    else:
        stairs_down_room = rooms[0]

    # --- Place Stairs (Guaranteed Placement) ---
    # Place stairs_down in the farthest room
    if rooms:
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
            stairs_down_fallback_x, stairs_down_fallback_y = stairs_down_room.center()
            game_map.tiles[stairs_down_fallback_y][stairs_down_fallback_x] = stairs_down
            stairs_positions['down'] = (stairs_down_fallback_x, stairs_down_fallback_y)
            game_map.items_on_ground = [item for item in game_map.items_on_ground if not (item.x == stairs_down_fallback_x and item.y == stairs_down_fallback_y)]

    # Place stairs_up in the first room generated (player's spawn room)
    if rooms:

            
        stairs_up_room = rooms[0]
        stairs_x, stairs_y = stairs_up_room.center()

        found_stairs_up_spot = False
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

    # NEW: Generate water features after rooms and stairs are placed
    # Pass the water_spawn_chance based on level_number if desired, e.g., 0.4 for level 1
    water_spawn_chance = 1.0  # TEMP: Force 100% chance for testing (set back to 0.4 later)
    water_tiles = generate_water_features(game_map, rooms, water_spawn_chance)
    
    # DEBUG: Print water generation info (remove after testing)
    print(f"DEBUG: Generated {len(water_tiles)} water tiles on level {level_number}")
    if water_tiles:
        sample_tile = game_map.tiles[water_tiles[0][1]][water_tiles[0][0]]  # First water tile
        print(f"DEBUG: Sample water tile at {water_tiles[0]}: char='{sample_tile.char}', name='{sample_tile.name}', blocked={sample_tile.blocked}")
    else:
        print("DEBUG: No water tiles generated - check room count or spawn chance")

    # Ensure water doesn't overwrite stairs
    for wx, wy in water_tiles:
        if (wx, wy) == stairs_positions.get('down'):
            game_map.tiles[wy][wx] = stairs_down
        elif (wx, wy) == stairs_positions.get('up'):
            game_map.tiles[wy][wx] = stairs_up

    trap_rooms = random.sample(range(len(rooms)), k=min(2, len(rooms)))  # Randomly select 1 or 2 rooms for traps

    # --- Populate Rooms with Decorations, Torches, Chests/Mimics AND TRAPS ---
    for room_index, room in enumerate(rooms):
        # Skip the rooms where stairs are placed for item/decoration spawning
        if room == stairs_up_room or room == stairs_down_room:
            continue
        
        # First pass: Place floor decorations and TRAPS
        for ry in range(room.y1 + 1, room.y2):
            for rx in range(room.x1 + 1, room.x2):
                # Skip if this spot is where stairs are
                if 'down' in stairs_positions and (rx, ry) == stairs_positions['down']:
                    continue
                if 'up' in stairs_positions and (rx, ry) == stairs_positions['up']:
                    continue
                # Skip if this spot is a water tile
                if game_map.tiles[ry][rx] in [lake, sewer_water]:
                    continue
                
                if game_map.tiles[ry][rx] == floor: # Only place on floor tiles
                    # --- NEW: Trap Placement Logic ---
                    if room_index in trap_rooms and random.random() < trap_placement_chance:
                        chosen_trap_instance = random.choice(possible_traps)
                        new_trap_instance = chosen_trap_instance()

                        # Create a TrapTile, disguised as a floor tile
                        game_map.tiles[ry][rx] = TrapTile(new_trap_instance, floor.char, floor.color, rx, ry, new_trap_instance.name)
                        continue

                    # --- Floor Decorations ---                    
                    if random.random() < floor_decoration_chance:
                        if level_number > 3 and random.random() < 0.02: # 1% chance for a decoration to be a Mimic
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
        # Place chests/mimics at room center, but only if not already occupied by stairs or water
        chest_spawn_x, chest_spawn_y = room.center()
        if 'down' in stairs_positions and (chest_spawn_x, chest_spawn_y) == stairs_positions['down']:
            continue # Skip if stairs_down are at the center of this room
        if 'up' in stairs_positions and (chest_spawn_x, chest_spawn_y) == stairs_positions['up']:
            continue # Skip if stairs_up are at the center of this room
        if game_map.tiles[chest_spawn_y][chest_spawn_x] in [lake, sewer_water]: # Skip if water tile
            continue

        if random.random() < 0.2: # Increased overall chest spawn chance to 50%
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
            if random.random() < 0.05: # 5% chance for a chest to be a mimic
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

