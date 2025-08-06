import pygame
import config

# Global variable to hold the loaded tileset image
TILESET_IMAGE = None  # Will be loaded as actual image
# Dictionary to map game characters to their (x, y) pixel coordinates in the tileset
TILE_MAPPING = {}

def load_tileset(filepath):
    global TILESET_IMAGE
    try:
        TILESET_IMAGE = pygame.image.load(filepath).convert_alpha()
        # No scaling needed here if config.TILE_SIZE matches the PNG's tile size
        # If you later decide to render at a larger size (e.g., 24x24 pixels on screen
        # for a 12x12 source tile), you would scale the individual tile surfaces
        # when you get them, or scale the entire tileset here if all tiles are scaled uniformly.
        # For now, assume 1:1 rendering of 12x12 tiles.
    except pygame.error as e:
        print(f"Error loading tileset: {e}")
        pygame.quit()
        exit()

def setup_tile_mapping():
    """
    Define the mapping from your game's character representation to
    the (x, y) pixel coordinates of the top-left corner of the tile
    within the TILESET_IMAGE.

    YOU MUST ADJUST THESE BASED ON YOUR ACTUAL 12x12 tile_set.png layout.
    (char): (column_index * config.TILE_SIZE, row_index * config.TILE_SIZE)
    """
    global TILE_MAPPING

    # Example mapping (THESE ARE PLACEHOLDERS - YOU NEED TO FIND THE CORRECT INDICES FOR YOUR TILESET)
    # For a 12x12 tileset, config.TILE_SIZE will be 12.
    # So, (0 * 12, 0 * 12) = (0, 0)
    # (1 * 12, 0 * 12) = (12, 0)
    # (0 * 12, 1 * 12) = (0, 12)
    TILE_MAPPING = {
        '.': (1 * config.TILE_SIZE, 1 * config.TILE_SIZE),  # Floor - top-left corner
        '#': (1 * config.TILE_SIZE, 1 * config.TILE_SIZE),  # Wall - next to floor
        '@': (2 * config.TILE_SIZE, 1 * config.TILE_SIZE),  # Player
        'o': (3 * config.TILE_SIZE, 0 * config.TILE_SIZE),  # Orc
        'T': (4 * config.TILE_SIZE, 0 * config.TILE_SIZE),  # Troll
        'D': (5 * config.TILE_SIZE, 0 * config.TILE_SIZE),  # Dragon
        '!': (6 * config.TILE_SIZE, 0 * config.TILE_SIZE),  # Potion
        '/': (7 * config.TILE_SIZE, 0 * config.TILE_SIZE),  # Weapon
        '[': (8 * config.TILE_SIZE, 0 * config.TILE_SIZE),  # Armor
        '>': (9 * config.TILE_SIZE, 0 * config.TILE_SIZE),  # Stairs Down
        '<': (10 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Stairs Up
        '+': (11 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Door
        'C': (12 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Chest
        'M': (13 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Mimic
        'B': (14 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Bartender
        'p': (15 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Patron
        'H': (16 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Healer
        '=': (17 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Bar Counter
        't': (18 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Table
        'c': (19 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Chair
        'F': (20 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Fireplace
        '%': (21 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Rubble
        '&': (22 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Bones
        'O': (23 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Barrel
        'W': (24 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Well
        'D': (25 * config.TILE_SIZE, 0 * config.TILE_SIZE), # Dungeon Door
        # Add more mappings for other tiles/entities as needed
    }

def get_tile_surface(char):
    """
    Returns a pygame.Surface object representing the tile for the given character.
    """
    if TILESET_IMAGE is None:
        raise RuntimeError("Tileset not loaded. Call load_tileset() first.")

    tile_coords = TILE_MAPPING.get(char)
    if tile_coords is None:
        print(f"Warning: No tile mapping for character '{char}'. Using default blank tile.")
        # Return a blank surface or a specific error tile
        return pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA)

    x, y = tile_coords
    tile_rect = pygame.Rect(x, y, config.TILE_SIZE, config.TILE_SIZE)
    return TILESET_IMAGE.subsurface(tile_rect)

def draw_tile(screen, screen_x, screen_y, char, color_tint=None):
    """
    Draws a tile from the tileset at the given screen coordinates (in tile units).
    Optionally applies a color tint (e.g., for explored areas or light sources).
    """
    tile_surface = get_tile_surface(char)

    # Apply color tint if provided (e.g., for dimming explored areas)
    if color_tint:
        tinted_surface = tile_surface.copy()
        tinted_surface.fill(color_tint, special_flags=pygame.BLEND_RGBA_MULT)
        tile_surface = tinted_surface

    screen.blit(tile_surface, (screen_x * config.TILE_SIZE, screen_y * config.TILE_SIZE))

