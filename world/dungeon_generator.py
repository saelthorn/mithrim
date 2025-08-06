import random
from random import randint, choice
from world import tile
from world.tile import stairs_down, stairs_up, dungeon_door, rubble, bones, torch, crate, barrel, well, wall, floor # Import all necessary tiles
from items.items import Chest, generate_random_loot # <--- NEW IMPORTS
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
            self.y1 <= other.y2 and self.y2 >= other.y1
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
    
    floor_decoration_tiles = [rubble, bones, crate, barrel, well]
    floor_decoration_chance = 0.05

    torch_placement_chance = 0.1
    torch_light_sources = []

    # List to store chests (and later mimics)
    chests_and_mimics = [] # <--- NEW LIST

    for _ in range(max_rooms):
        w = randint(room_min_size, room_max_size)
        h = randint(room_min_size, room_max_size)
        x = randint(0, game_map.width - w - 1)
        y = randint(0, game_map.height - h - 1)

        new_room = RectRoom(x, y, w, h)

        if any(new_room.intersects(other) for other in rooms):
            continue

        dig_room(game_map, new_room)

        # --- Add Floor Decorations to the new room ---
        for ry in range(new_room.y1 + 1, new_room.y2):
            for rx in range(new_room.x1 + 1, new_room.x2):
                if game_map.tiles[ry][rx] == floor and random.random() < floor_decoration_chance:
                    game_map.tiles[ry][rx] = random.choice(floor_decoration_tiles)
        
        # --- Add Torches to the walls of the new room ---
        for rx in range(new_room.x1, new_room.x2 + 1):
            for ry in range(new_room.y1, new_room.y2 + 1):
                is_perimeter_wall = (
                    (rx == new_room.x1 or rx == new_room.x2) and (new_room.y1 < ry < new_room.y2) or
                    (ry == new_room.y1 or ry == new_room.y2) and (new_room.x1 < rx < new_room.x2)
                )
                
                if is_perimeter_wall and game_map.tiles[ry][rx] == wall:
                    adjacent_to_floor = False
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        nx, ny = rx + dx, ry + dy
                        if (new_room.x1 < nx < new_room.x2 and new_room.y1 < ny < new_room.y2 and
                            game_map.tiles[ny][nx] == floor):
                            adjacent_to_floor = True
                            break
                    
                    if adjacent_to_floor and random.random() < torch_placement_chance:
                        game_map.tiles[ry][rx] = torch
                        torch_light_sources.append((rx, ry))

        # --- Add Chests or Mimics to rooms (excluding the first room where player spawns) ---
        if rooms:
            if random.random() < 0.3: # 30% chance to spawn a chest/mimic in a room
                spawn_x, spawn_y = new_room.center()
                # Ensure spawn doesn't overlap with stairs
                if (spawn_x, spawn_y) not in stairs_positions.values():
                    if random.random() < 0.2: # 20% chance for a chest to be a mimic
                        new_mimic = Mimic(spawn_x, spawn_y)
                        chests_and_mimics.append(new_mimic)
                    else:
                        chest_contents = generate_random_loot(level_number)
                        new_chest = Chest(spawn_x, spawn_y, contents=chest_contents)
                        chests_and_mimics.append(new_chest)
        
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

    # Add doors and stairs
    if len(rooms) >= 2:
        last_room = rooms[-1]
        door_x, door_y = last_room.center()
        door_x += 1
        if door_x < game_map.width and door_y < game_map.height:
            game_map.tiles[door_y][door_x] = dungeon_door
            stairs_positions['door'] = (door_x, door_y)
        
        if len(rooms) >= 3:
            stairs_room = rooms[-2]
            stairs_down_x, stairs_down_y = stairs_room.center()
            stairs_down_x -= 1
            if stairs_down_x >= 0 and stairs_down_y < game_map.height:
                game_map.tiles[stairs_down_y][stairs_down_x] = stairs_down
                stairs_positions['down'] = (stairs_down_x, stairs_down_y)
        
        if level_number > 1:
            first_room = rooms[0]
            stairs_up_x, stairs_up_y = first_room.center()
            if stairs_up_x < game_map.width and stairs_up_y < game_map.height:
                game_map.tiles[stairs_up_y][stairs_up_x] = stairs_up
                stairs_positions['up'] = (stairs_up_x, stairs_up_y)
    
    # Add generated chests and mimics to items_on_ground
    # Mimics are initially treated as items on the ground for rendering and interaction
    game_map.items_on_ground.extend(chests_and_mimics)
    
    return rooms, stairs_positions, torch_light_sources
