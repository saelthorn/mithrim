# MultipleFiles/graphics.py

import pygame
import config

# Global variable to hold the loaded tileset image
TILESET_IMAGE = None
TILE_MAPPING = {}

ORIGINAL_TILE_DIM = 24 # Confirmed 12x12 in Figma
TILE_SPACING = 1     # 1 pixel space after each tile

# The effective dimension of each tile cell in the tileset, including spacing
CELL_DIM = ORIGINAL_TILE_DIM + TILE_SPACING

# --- Global X-axis offset for tile extraction ---
# These offsets should be 0 if your 12x12 sprites are perfectly at the top-left
# of their 13x13 grid cell. Adjust only if sprites are consistently shifted.
TILE_X_OFFSET = 0 
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

        # Player Characters (based on race-class combinations)
        'HF': (0 * CELL_DIM, 0 * CELL_DIM),  # Human Fighter
        'HR': (1 * CELL_DIM, 0 * CELL_DIM),  # Human Rogue
        'HW': (2 * CELL_DIM, 0 * CELL_DIM),  # Human Wizard

        'DF': (0 * CELL_DIM, 1 * CELL_DIM),  # HillDwarf Fighter
        'DR': (1 * CELL_DIM, 1 * CELL_DIM),  # HillDwarf Rogue
        'DW': (2 * CELL_DIM, 1 * CELL_DIM),  # HillDwarf Wizard

        'EF': (0 * CELL_DIM, 2 * CELL_DIM),  # DrowElf Fighter
        'ER': (1 * CELL_DIM, 2 * CELL_DIM),  # DrowElf Rogue
        'EW': (2 * CELL_DIM, 2 * CELL_DIM),  # DrowElf Wizard


        # Map Tiles
        '.': (0 * CELL_DIM, 3 * CELL_DIM),  # Floor
        '#': (1 * CELL_DIM, 3 * CELL_DIM),  # Wall
        '>': (8 * CELL_DIM, 3 * CELL_DIM),  # Stairs Down
        '<': (9 * CELL_DIM, 3 * CELL_DIM),  # Stairs Up
        '+': (2 * CELL_DIM, 3 * CELL_DIM),  # Tavern Door
        ';': (1 * CELL_DIM, 4 * CELL_DIM),  # Bones
        '%': (2 * CELL_DIM, 4 * CELL_DIM),  # Rubble
        '~': (3 * CELL_DIM, 4 * CELL_DIM),  # Cobweb
        '*': (4 * CELL_DIM, 4 * CELL_DIM),  # Mushroom
        'fb': (5 * CELL_DIM, 4 * CELL_DIM), # Fresh Bones
        '`': (6 * CELL_DIM, 4 * CELL_DIM),  # Dungeon Grass
        
        # IMPORTANT: Ensure 'C' is your *closed* chest graphic
        'C': (4 * CELL_DIM, 5 * CELL_DIM),  # Chest (Closed)
        'O': (5 * CELL_DIM, 5 * CELL_DIM),  # Open Chest
        'c': (3 * CELL_DIM, 3 * CELL_DIM),  # Chair (Tavern)
        't': (4 * CELL_DIM, 3 * CELL_DIM),  # Table (Tavern)
        '=': (5 * CELL_DIM, 3 * CELL_DIM),  # Bar Counter
        'F': (6 * CELL_DIM, 3 * CELL_DIM),  # Fireplace
        'i': (7 * CELL_DIM, 3 * CELL_DIM),  # Torch

        # Static Decorations (using distinct chars)
        'b': (2 * CELL_DIM, 5 * CELL_DIM), # Static Barrel (original graphic)
        'k': (0 * CELL_DIM, 5 * CELL_DIM), # Static Crate (original graphic)             

        # Mimic disguised as Crate/Barrel (using distinct chars)
        # These should point to your *disguised* mimic graphics (e.g., barrel with eyes)
        'B': (3 * CELL_DIM, 5 * CELL_DIM),  # Mimic Barrel
        'K': (1 * CELL_DIM, 5 * CELL_DIM),  # Mimic Crate
        'M': (6 * CELL_DIM, 5 * CELL_DIM),  # Mimic (Generic Revealed Form)

        # Pressure Plate / Trap Graphics
        '^': (0 * CELL_DIM, 4 * CELL_DIM), # Example: A simple triangle or pressure plate graphic
        '_': (0 * CELL_DIM, 4 * CELL_DIM), # Use floor graphic for hidden pressure plate (or a specific hidden trap graphic)   

        # Entity Characters
        '@': (0 * CELL_DIM, 0 * CELL_DIM),  # Player
        'r': (0 * CELL_DIM, 7 * CELL_DIM),  # Rat (Monster)
        'g': (1 * CELL_DIM, 7 * CELL_DIM),  # Goblin
        'S': (2 * CELL_DIM, 7 * CELL_DIM),  # Skeleton (Monster)
        'OR': (5 * CELL_DIM, 8 * CELL_DIM),  # Orc (Monster)
        'T': (5 * CELL_DIM, 7 * CELL_DIM),  # Troll
        'D': (7 * CELL_DIM, 7 * CELL_DIM),  # Dragon (Monster)
        
        's': (0 * CELL_DIM, 8 * CELL_DIM),  # Ooze (Monster)
        'ga': (1 * CELL_DIM, 8 * CELL_DIM),  # Goblin Archer
        'SA': (2 * CELL_DIM, 8 * CELL_DIM),  # Skeleton Archer
        'CT': (3 * CELL_DIM, 7 * CELL_DIM),  # Centaur
        'CA': (3 * CELL_DIM, 8 * CELL_DIM),  # Cebtaur Archer
        'L': (4 * CELL_DIM, 7 * CELL_DIM),  # Lizardfolk
        'LA': (4 * CELL_DIM, 8 * CELL_DIM),  # Lizardfolk Archer
        'GS': (0 * CELL_DIM, 9 * CELL_DIM),  # Giant Spider
        'LO': (6 * CELL_DIM, 8 * CELL_DIM),  # Large Ooze
        'BH': (6 * CELL_DIM, 7 * CELL_DIM),  # Beholder

        # IMPORTANT: Ensure 'M' is your *generic revealed mimic* graphic
        'A': (7 * CELL_DIM, 0 * CELL_DIM),  # Bartender (NPC)
        'p': (8 * CELL_DIM, 0 * CELL_DIM),  # Patron (NPC)
        'H': (6 * CELL_DIM, 0 * CELL_DIM),  # Healer (NPC)
        'mh': (6 * CELL_DIM, 2 * CELL_DIM), # Mage Hand
        
        # Item Characters
        '!': (0 * CELL_DIM, 6 * CELL_DIM),  # Potion
        '/': (4 * CELL_DIM, 6 * CELL_DIM),  # Weapon
        '[': (1 * CELL_DIM, 6 * CELL_DIM),  # Armor
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


def draw_tile(screen_surface, draw_x, draw_y, char, color_tint=None):
    tile_surface = get_tile_surface(char)
    
    if color_tint:
        tinted_surface = tile_surface.copy()
        tinted_surface.fill(color_tint, special_flags=pygame.BLEND_RGBA_MULT)
        tile_surface = tinted_surface
    
    # --- MODIFIED: Blit directly using draw_x, draw_y ---
    screen_surface.blit(tile_surface, (draw_x, draw_y))    
