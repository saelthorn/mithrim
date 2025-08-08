# MultipleFiles/graphics.py

import pygame
import config

# Global variable to hold the loaded tileset image
TILESET_IMAGE = None
TILE_MAPPING = {}

ORIGINAL_TILE_DIM = 12 # Confirmed 12x12 in Figma
TILE_SPACING = 1     # 1 pixel space after each tile

# The effective dimension of each tile cell in the tileset, including spacing
CELL_DIM = ORIGINAL_TILE_DIM + TILE_SPACING

# --- Global X-axis offset for tile extraction ---
# These offsets should be 0 if your 12x12 sprites are perfectly at the top-left
# of their 13x13 grid cell. Adjust only if sprites are consistently shifted.
TILE_X_OFFSET = 1 
TILE_Y_OFFSET = 0 

def load_tileset(filepath):
    global TILESET_IMAGE
    try:
        TILESET_IMAGE = pygame.image.load(filepath).convert_alpha()
        print(f"Tileset loaded: {filepath}, size: {TILESET_IMAGE.get_size()}")
    except pygame.error as e:
        print(f"Error loading tileset: {e}")
        pygame.quit()
        exit()

def setup_tile_mapping():
    global TILE_MAPPING
        
    # The coordinates in TILE_MAPPING now need to reflect the *actual pixel start*
    # of each tile's 13x13 cell.
    # So, we multiply the grid column/row by CELL_DIM (13).

    TILE_MAPPING = {
        # Map Tiles (assuming first row)
        '.': (12 * CELL_DIM, 5 * CELL_DIM),  # Floor
        '#': (22 * CELL_DIM, 3 * CELL_DIM),  # Wall
        '>': (23 * CELL_DIM, 0 * CELL_DIM),  # Stairs Down
        '<': (24 * CELL_DIM, 0 * CELL_DIM),  # Stairs Up
        '+': (14 * CELL_DIM, 1 * CELL_DIM),  # Tavern Door
        '`': (15 * CELL_DIM, 5 * CELL_DIM),  # Dungeon Grass
        'C': (26 * CELL_DIM, 19 * CELL_DIM),  # Chest (Closed) - This was the issue!
        'O': (27 * CELL_DIM, 19 * CELL_DIM),  # Open Chest (Placeholder, adjust if needed)
        'c': (5 * CELL_DIM, 36 * CELL_DIM),  # Chair
        't': (15 * CELL_DIM, 35 * CELL_DIM),  # Table
        '=': (1 * CELL_DIM, 35 * CELL_DIM),  # Bar Counter
        'F': (1 * CELL_DIM, 42 * CELL_DIM), # Fireplace
        '%': (10 * CELL_DIM, 5 * CELL_DIM), # Rubble
        ';': (0 * CELL_DIM, 7 * CELL_DIM), # Bones
        'b': (7 * CELL_DIM, 36 * CELL_DIM), # Crate
        'o': (11 * CELL_DIM, 36 * CELL_DIM), # Barrel
        'W': (20 * CELL_DIM, 40 * CELL_DIM), # Well
        'i': (3 * CELL_DIM, 42 * CELL_DIM), # Torch

        # Entity Characters
        '@': (153 * CELL_DIM, 0 * CELL_DIM),  # Player
        'g': (149 * CELL_DIM, 8 * CELL_DIM),  # Goblin
        '&': (104 * CELL_DIM, 10 * CELL_DIM),  # Skeleton (Monster)
        'R': (168 * CELL_DIM, 27 * CELL_DIM),  # Orc (Monster) - Changed from 'O' to 'R'
        'T': (150 * CELL_DIM, 5 * CELL_DIM),  # Troll
        'D': (112 * CELL_DIM, 42 * CELL_DIM),  # Dragon (Monster)
        'M': (107 * CELL_DIM, 41 * CELL_DIM),  # Mimic
        'B': (117 * CELL_DIM, 0 * CELL_DIM),  # Bartender (NPC)
        'p': (104 * CELL_DIM, 0 * CELL_DIM),  # Patron (NPC)
        'H': (148 * CELL_DIM, 28 * CELL_DIM),  # Healer (NPC)
        
        # Item Characters
        '!': (30 * CELL_DIM, 4 * CELL_DIM),  # Potion
        '/': (40 * CELL_DIM, 6 * CELL_DIM),  # Weapon
        '[': (27 * CELL_DIM, 11 * CELL_DIM),  # Armor
    }
    print("Tile mapping setup complete.")

def get_tile_surface(char):
    """
    Returns a pygame.Surface object representing the tile for the given character,
    scaled to the current config.TILE_SIZE.
    """
    if TILESET_IMAGE is None:
        raise RuntimeError("Tileset not loaded. Call load_tileset() first.")

    tile_coords = TILE_MAPPING.get(char)
    if tile_coords is None:
        print(f"Warning: No tile mapping for character '{char}'. Using default blank tile.")
        return pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA)

    x, y = tile_coords
    
    # The tile_rect now extracts the ORIGINAL_TILE_DIM (12x12) from the calculated
    # position, plus any fine-tuning offsets.
    # This is the crucial part: x and y are already calculated using CELL_DIM.
    # We then add TILE_X_OFFSET/TILE_Y_OFFSET to get to the top-left of the *actual sprite*.
    tile_rect = pygame.Rect(x + TILE_X_OFFSET, y + TILE_Y_OFFSET, ORIGINAL_TILE_DIM, ORIGINAL_TILE_DIM)
    
    # Add a check to ensure the rect is within the tileset image bounds
    if not TILESET_IMAGE.get_rect().contains(tile_rect):
        print(f"Error: Extracted tile rect {tile_rect} for char '{char}' is out of bounds of tileset image {TILESET_IMAGE.get_size()}.")
        return pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA) # Return blank tile

    subsurface = TILESET_IMAGE.subsurface(tile_rect)

    # The scaling here should now be crisp if the source subsurface is correct.
    if config.TILE_SIZE != ORIGINAL_TILE_DIM:
        scaled_surface = pygame.transform.scale(subsurface, (config.TILE_SIZE, config.TILE_SIZE))
        return scaled_surface
    else:
        return subsurface

def draw_tile(screen_surface, screen_x, screen_y, char, color_tint=None):
    tile_surface = get_tile_surface(char)
    
    if color_tint:
        tinted_surface = tile_surface.copy()
        tinted_surface.fill(color_tint, special_flags=pygame.BLEND_RGBA_MULT)
        tile_surface = tinted_surface
    
    screen_surface.blit(tile_surface, (screen_x * config.TILE_SIZE, screen_y * config.TILE_SIZE))

