from world.tile import tavern_floor, tavern_wall, bar_counter, table, chair, door, fireplace, wall, floor, torch # Ensure 'door' is imported
from entities.dungeon_npcs import DungeonHealer
from entities.tavern_npcs import Bartender, Patron
from core import game
from core.fov import FOV
import random

def generate_tavern(game_map, player):
    """Generate tavern layout based on ASCII blueprint."""
    ascii_map = [
        "###############",
        "#######+#######",
        "T              T",  # Torch placed here
        "#              #",
        "F              #",
        "#   c      c   #",
        "#  ctc    ctc  #",
        "#   c          #",
        "#              #",
        "#              #",
        "#              ##T##",
        "# c  c  c          #",
        "T========          T",
        "#                  T",
        "#                  #",
        "###################"
    ]

    height = len(ascii_map)
    width = len(ascii_map[0])
    start_x = (game_map.width - width) // 2 - 2
    start_y = (game_map.height - height) // 2
    door_position = (9, 0)

    char_to_tile = {
        '#': wall,
        ' ': floor,
        '+': door,
        '=': bar_counter,
        'c': chair,
        't': table,
        'F': fireplace,
        'T': torch,  # Map the torch character to the torch tile
    }

    for y, row in enumerate(ascii_map):
        for x, char in enumerate(row):
            gx, gy = start_x + x, start_y + y
            if char in char_to_tile:
                game_map.tiles[gy][gx] = char_to_tile[char]
            else:
                game_map.tiles[gy][gx] = floor  # Default floor

            # Place NPCs/entities
            if char == 'H':
                healer = DungeonHealer(gx, gy)
                game_map.items_on_ground.append(healer)
            elif char == 'p':
                patron = Patron(gx, gy, "Patron")
                game_map.items_on_ground.append(patron)
            elif char == 'A':
                bartender = Bartender(gx, gy)
                game_map.items_on_ground.append(bartender)

    # Place torches manually in the tavern
    for y in range(height):
        for x in range(width):
            if ascii_map[y][x] == 'T':  # Check for the torch character
                game_map.tiles[start_y + y][start_x + x] = torch  # Place the torch tile
                game_map.torch_light_sources.append((start_x + x, start_y + y))  # Add to light sources

    # Initialize FOV
    game_map.fov = FOV(game_map)
 
    # Set initial FoV
    game_map.fov.compute_fov(player.x, player.y, radius=8)  # Set the radius as needed
    
    # Return default door position
    return door_position







