from random import randint
from world import tile
from world.tile import stairs_down, stairs_up, dungeon_door

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

    for _ in range(max_rooms):
        w = randint(room_min_size, room_max_size)
        h = randint(room_min_size, room_max_size)
        x = randint(0, game_map.width - w - 1)
        y = randint(0, game_map.height - h - 1)

        new_room = RectRoom(x, y, w, h)

        if any(new_room.intersects(other) for other in rooms):
            continue  # Skip overlapping

        dig_room(game_map, new_room)

        if rooms:
            # Connect to previous room
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
        # Door to next level in the last room (main progression method)
        last_room = rooms[-1]
        door_x, door_y = last_room.center()
        door_x += 1  # Offset slightly to avoid center
        if door_x < game_map.width and door_y < game_map.height:
            game_map.tiles[door_y][door_x] = dungeon_door
            stairs_positions['door'] = (door_x, door_y)
        
        # Optional stairs down in a different room (alternative path)
        if len(rooms) >= 3:
            stairs_room = rooms[-2]  # Second to last room
            stairs_down_x, stairs_down_y = stairs_room.center()
            stairs_down_x -= 1  # Offset in opposite direction
            if stairs_down_x >= 0 and stairs_down_y < game_map.height:
                game_map.tiles[stairs_down_y][stairs_down_x] = stairs_down
                stairs_positions['down'] = (stairs_down_x, stairs_down_y)
        
        # Stairs up in the first room (to return)
        if level_number > 1:
            first_room = rooms[0]
            stairs_up_x, stairs_up_y = first_room.center()
            if stairs_up_x < game_map.width and stairs_up_y < game_map.height:
                game_map.tiles[stairs_up_y][stairs_up_x] = stairs_up
                stairs_positions['up'] = (stairs_up_x, stairs_up_y)

    return rooms, stairs_positions