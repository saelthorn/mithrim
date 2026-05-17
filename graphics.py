import pygame
import config
import math  # For wave patterns in fallbacks

# Global variable to hold the loaded tileset image
TILESET_IMAGE = None
TILE_MAPPING = {}

ORIGINAL_TILE_DIM = 24 # Confirmed 24x24 in Figma
TILE_SPACING = 1     # 1 pixel space after each tile

# The effective dimension of each tile cell in the tileset, including spacing
CELL_DIM = ORIGINAL_TILE_DIM + TILE_SPACING

# --- Global X-axis offset for tile extraction ---
# These offsets should be 0 if your 24x24 sprites are perfectly at the top-left
# of their 25x25 grid cell. Adjust only if sprites are consistently shifted.
TILE_X_OFFSET = 0 
TILE_Y_OFFSET = 0 

def load_tileset(filepath):
    global TILESET_IMAGE
    try:
        TILESET_IMAGE = pygame.image.load(filepath).convert_alpha()
        print(f"Tileset loaded: {filepath}, size: {TILESET_IMAGE.get_size()}")
    except pygame.error as e:
        print(f"Error loading tileset: {e}")
        # Don't quit—fallback to generated tiles
        TILESET_IMAGE = None
        print("Using generated fallback tiles (no tileset image)")

def setup_tile_mapping():
    global TILE_MAPPING
        
    # FIXED: Distinct positions for '~' (river) and '≈' (lake)
    # Adjust these coordinates based on your tileset PNG (e.g., column 11, row 4 for river; try column 12 for lake if needed)
    # Use an image editor to verify the grid positions.
    TILE_MAPPING = {

        # Player Characters (based on race-class combinations)
        'HF': (0 * CELL_DIM, 0 * CELL_DIM),  # Human Fighter
        'HR': (1 * CELL_DIM, 0 * CELL_DIM),  # Human Rogue
        'HW': (2 * CELL_DIM, 0 * CELL_DIM),  # Human Wizard
        'HC': (3 * CELL_DIM, 0 * CELL_DIM),  # Human Cleric

        'DF': (0 * CELL_DIM, 1 * CELL_DIM),  # HillDwarf Fighter
        'DR': (1 * CELL_DIM, 1 * CELL_DIM),  # HillDwarf Rogue
        'DW': (2 * CELL_DIM, 1 * CELL_DIM),  # HillDwarf Wizard
        'DC': (3 * CELL_DIM, 1 * CELL_DIM),  # HillDwarf Cleric

        'EF': (0 * CELL_DIM, 2 * CELL_DIM),  # DrowElf Fighter
        'ER': (1 * CELL_DIM, 2 * CELL_DIM),  # DrowElf Rogue
        'EW': (2 * CELL_DIM, 2 * CELL_DIM),  # DrowElf Wizard
        'EC': (3 * CELL_DIM, 2 * CELL_DIM),  # DrowElf Cleric

        'TF': (0 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Fighter
        'TR': (1 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Rogue
        'TW': (2 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Wizard
        'TC': (3 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Cleric

        'DBF': (0 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Fighter
        'DBR': (1 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Rogue
        'DBW': (2 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Wizard
        'DBC': (3 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Cleric


        # Map Tiles
        'bl': (11 * CELL_DIM, 2 * CELL_DIM),# Bloodstain
        '{': (0 * CELL_DIM, 6 * CELL_DIM),  # Tavern Crate
        '}': (2 * CELL_DIM, 6 * CELL_DIM),  # Tavern Barrel
        ',': (2 * CELL_DIM, 16 * CELL_DIM), # Tavern Floor
        '?': (1 * CELL_DIM, 16 * CELL_DIM), # Kitchen Tavern Floor
        '.': (0 * CELL_DIM, 3 * CELL_DIM),  # Floor
        '#': (1 * CELL_DIM, 3 * CELL_DIM),  # Wall
        '>': (8 * CELL_DIM, 3 * CELL_DIM),  # Stairs Down
        '<': (9 * CELL_DIM, 3 * CELL_DIM),  # Stairs Up
        'alt': (10 * CELL_DIM, 3 * CELL_DIM), # Altar
        '+': (2 * CELL_DIM, 3 * CELL_DIM),  # Tavern Door
        ';': (1 * CELL_DIM, 4 * CELL_DIM),  # Bones
        '%': (2 * CELL_DIM, 4 * CELL_DIM),  # Rubble
        'x': (3 * CELL_DIM, 4 * CELL_DIM),  # Cobweb
        '*': (4 * CELL_DIM, 4 * CELL_DIM),  # Mushroom
        'fb': (5 * CELL_DIM, 4 * CELL_DIM), # Fresh Bones
        '`': (6 * CELL_DIM, 4 * CELL_DIM),  # Dungeon Grass
        'dp': (7 * CELL_DIM, 4 * CELL_DIM), # Dungeon Pillar
        '.2': (8 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Two
        '.3': (9 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Three
        '.5': (12 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Five 
        '.6': (13 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Six 
        '.4': (14 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Four
        '`2': (10 * CELL_DIM, 4 * CELL_DIM), # Dungeon Grass Two
        '~': (11 * CELL_DIM, 4 * CELL_DIM),  # River (Water) - FIXED: Keep this
        '≈': (11 * CELL_DIM, 4 * CELL_DIM),  # Lake (Water) - FIXED: Distinct position (adjust if your tileset has it elsewhere)
        
        # IMPORTANT: Ensure 'C' is your *closed* chest graphic
        'C': (4 * CELL_DIM, 5 * CELL_DIM),  # Chest (Closed)
        'O': (5 * CELL_DIM, 5 * CELL_DIM),  # Open Chest
        'c': (3 * CELL_DIM, 3 * CELL_DIM),  # Chair (Tavern)
        't': (4 * CELL_DIM, 3 * CELL_DIM),  # Table (Tavern)
        '=': (5 * CELL_DIM, 3 * CELL_DIM),  # Bar Counter
        'F': (6 * CELL_DIM, 3 * CELL_DIM),  # Fireplace
        'i': (7 * CELL_DIM, 3 * CELL_DIM),  # Torch Wall

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

        'R': (0 * CELL_DIM, 7 * CELL_DIM),   # Rat (Monster)
        'GB': (1 * CELL_DIM, 7 * CELL_DIM),  # Goblin
        'SK': (2 * CELL_DIM, 7 * CELL_DIM),  # Skeleton (Monster)
        'OR': (5 * CELL_DIM, 8 * CELL_DIM),  # Orc (Monster)
        'TL': (5 * CELL_DIM, 7 * CELL_DIM),  # Troll
        'RDR': (7 * CELL_DIM, 7 * CELL_DIM),  # Dragon (Monster)
        
        'OZ': (0 * CELL_DIM, 8 * CELL_DIM),  # Ooze (Monster)
        'GA': (1 * CELL_DIM, 8 * CELL_DIM),  # Goblin Archer
        'SA': (2 * CELL_DIM, 8 * CELL_DIM),  # Skeleton Archer
        'CE': (3 * CELL_DIM, 7 * CELL_DIM),  # Centaur
        'CA': (3 * CELL_DIM, 8 * CELL_DIM),  # Cebtaur Archer
        'LF': (4 * CELL_DIM, 7 * CELL_DIM),  # Lizardfolk
        'LA': (4 * CELL_DIM, 8 * CELL_DIM),  # Lizardfolk Archer
        'GS': (0 * CELL_DIM, 9 * CELL_DIM),  # Giant Spider
        'LO': (6 * CELL_DIM, 8 * CELL_DIM),  # Large Ooze
        'BH': (6 * CELL_DIM, 7 * CELL_DIM),  # Beholder

        'OB': (1 * CELL_DIM, 9 * CELL_DIM),  # Owlbear
        'DG': (2 * CELL_DIM, 9 * CELL_DIM),  # Demogorgon
        'GK': (3 * CELL_DIM, 9 * CELL_DIM),  # Grick
        'GM': (4 * CELL_DIM, 9 * CELL_DIM),  # Gibbering Mouther
        'MF': (5 * CELL_DIM, 9 * CELL_DIM),  # Mind Flayer
        'MN': (6 * CELL_DIM, 9 * CELL_DIM),  # Minotaur
        'WR': (7 * CELL_DIM, 9 * CELL_DIM),  # Wererat
        'WF': (7 * CELL_DIM, 8 * CELL_DIM),  # Wolf        

        'YL': (8 * CELL_DIM, 7 * CELL_DIM),  # Yochlol
        'DD': (8 * CELL_DIM, 8 * CELL_DIM),  # Drider
        'DS': (8 * CELL_DIM, 9 * CELL_DIM),  # Death Slaad
        'MS': (9 * CELL_DIM, 7 * CELL_DIM),  # Myconid Sprout
        'MA': (9 * CELL_DIM, 8 * CELL_DIM),  # Myconid Adult 
        'RS': (9 * CELL_DIM, 9 * CELL_DIM),  # Red Slaad
        'MZ': (10 * CELL_DIM, 7 * CELL_DIM),  # Mezzoloth 
        'GU': (10 * CELL_DIM, 8 * CELL_DIM),  # Gauth 
        'AR': (10 * CELL_DIM, 9 * CELL_DIM),  # Arasta 
        'ID': (11 * CELL_DIM, 7 * CELL_DIM), # Intellect Devourer
        'IM': (11 * CELL_DIM, 8 * CELL_DIM),  # Imp
        'AG': (11 * CELL_DIM, 9 * CELL_DIM),  # Alpha Grick 
        'WRT': (12 * CELL_DIM, 7 * CELL_DIM), # Wraith



        # Tavern Entities and Misc.
        'A': (9 * CELL_DIM, 0 * CELL_DIM),  # Bartender (NPC)
        'p': (8 * CELL_DIM, 0 * CELL_DIM),  # Patron (NPC)
        'H': (6 * CELL_DIM, 0 * CELL_DIM),  # Healer (NPC)
        'rc': (7 * CELL_DIM, 0 * CELL_DIM), # Merchant (NPC)
        'mh': (6 * CELL_DIM, 2 * CELL_DIM), # Mage Hand (Skill)
        'sw': (14 * CELL_DIM, 2 * CELL_DIM), # Spiritual Weapon (Skill)
        'CS': (12 * CELL_DIM, 8 * CELL_DIM), # Celestial Spirit (Skill)

        # Helmets
        'lc':  (0 * CELL_DIM, 17 * CELL_DIM),  # Leather Cap
        'ih':  (1 * CELL_DIM, 17 * CELL_DIM),  # Iron Helmet
        'sh':  (2 * CELL_DIM, 17 * CELL_DIM),  # Steel Helmet
        'gh':  (3 * CELL_DIM, 17 * CELL_DIM),  # Great Helm
        'mc':  (4 * CELL_DIM, 17 * CELL_DIM),  # Mage's Circlet
        'hs':  (5 * CELL_DIM, 17 * CELL_DIM),  # Hood of Shadows

        # Boots
        'lb':  (0 * CELL_DIM, 18 * CELL_DIM),  # Leather Boots
        'ig':  (1 * CELL_DIM, 18 * CELL_DIM),  # Iron Greaves
        'bs':  (2 * CELL_DIM, 18 * CELL_DIM),  # Boots of Speed
        'bst': (3 * CELL_DIM, 18 * CELL_DIM),  # Boots of Stealth
        'ds':  (4 * CELL_DIM, 18 * CELL_DIM),  # Dwarven Stompers

        # Focus Items
        'af':  (0 * CELL_DIM, 19 * CELL_DIM),  # Arcane Focus
        'df':  (1 * CELL_DIM, 19 * CELL_DIM),  # Divine Focus
        'rt':  (2 * CELL_DIM, 19 * CELL_DIM),  # Runed Tome

        # Item Characters
        'cf': (8 * CELL_DIM, 2 * CELL_DIM), # Campfire 
        'pn': (9 * CELL_DIM, 2 * CELL_DIM), # Wood Plank (Junk)
        'th': (10 * CELL_DIM,2 * CELL_DIM), # Torch (Item)
        'tt': (7 * CELL_DIM, 2 * CELL_DIM), # Thieves' Tools
        'spb': (13 * CELL_DIM, 2 * CELL_DIM), # Spellbook (Off-hand Item)
        'hsy': (12 * CELL_DIM, 2 * CELL_DIM), # Holy Symbol (Accessory)
        '!': (0 * CELL_DIM, 13 * CELL_DIM), # Potions

        # Food Characters
        'met': (11 * CELL_DIM, 1 * CELL_DIM), # Meat
        'gra': (12 * CELL_DIM, 1 * CELL_DIM), # Green Apple
        'frg': (13 * CELL_DIM, 1 * CELL_DIM), # Fromage
        'brd': (14 * CELL_DIM, 1 * CELL_DIM), # Bread
        'msm': (15 * CELL_DIM, 1 * CELL_DIM), # Mushroom
        'crt': (16 * CELL_DIM, 1 * CELL_DIM), # Carrot

        # Armors and Robes
        'pda': (1 * CELL_DIM, 13 * CELL_DIM),  # Leather Armor
        'sla': (1 * CELL_DIM, 14 * CELL_DIM),  # Studded Leather Armor
        'sma': (1 * CELL_DIM, 15 * CELL_DIM),  # Scale Mail Armor

        'cha': (2 * CELL_DIM, 13 * CELL_DIM),  # Chainmail Armor
        'hpa': (2 * CELL_DIM, 14 * CELL_DIM),  # Half Plate Armor
        'fpa': (2 * CELL_DIM, 15 * CELL_DIM),  # Full Plate Armor

        'rbs': (3 * CELL_DIM, 13 * CELL_DIM),  # Robes 
        'rop': (3 * CELL_DIM, 14 * CELL_DIM),  # Robes of Protection
        
        'rsh': (12 * CELL_DIM, 13 * CELL_DIM),  # Round Shield
        'ksh': (12 * CELL_DIM, 14 * CELL_DIM),  # Kite Shield
        'tsh': (12 * CELL_DIM, 15 * CELL_DIM),  # Tower Shield     

        # Weapons
        'dgr': (4 * CELL_DIM, 13 * CELL_DIM),  # Iron Dagger
        'sdr': (4 * CELL_DIM, 14 * CELL_DIM),  # SIlver Dagger
        'thr': (4 * CELL_DIM, 15 * CELL_DIM),  # Throwing Knife

        'shs': (5 * CELL_DIM, 13 * CELL_DIM),  # Shortsword
        'fhs': (5 * CELL_DIM, 14 * CELL_DIM),  # Flameheart Shortsword
        'bss': (5 * CELL_DIM, 15 * CELL_DIM),  # Shortsword

        'lns': (6 * CELL_DIM, 13 * CELL_DIM),  # Iron Longsword 
        'sls': (6 * CELL_DIM, 14 * CELL_DIM),  # Steel Longsword 
        'als': (6 * CELL_DIM, 15 * CELL_DIM),  # Adamantine Longsword 

        'sba': (8 * CELL_DIM, 13 * CELL_DIM),  # Steel Battleaxe
        'dba': (8 * CELL_DIM, 14 * CELL_DIM),  # Dwarven Battleaxe
        'pla': (8 * CELL_DIM, 15 * CELL_DIM),  # Polearm

        'oas': (7 * CELL_DIM, 13 * CELL_DIM),  # Oak Staff
        'aps': (7 * CELL_DIM, 14 * CELL_DIM),  # Apprentice's Staff
        'som': (7 * CELL_DIM, 15 * CELL_DIM),  # Staff of Magi
        'qts': (7 * CELL_DIM, 16 * CELL_DIM),  # Sturdy Quarterstaff

        'srp': (9 * CELL_DIM, 13 * CELL_DIM),  # Steel Rapier
        'dlr': (9 * CELL_DIM, 14 * CELL_DIM),  # Duelists Rapier

        'irh': (10 * CELL_DIM, 13 * CELL_DIM),  # Iron Hammer
        'dbw': (10 * CELL_DIM, 14 * CELL_DIM),  # Dragonsbane Warhammer
        'mul': (10 * CELL_DIM, 15 * CELL_DIM),  # Maul

        'stm': (11 * CELL_DIM, 13 * CELL_DIM),  # Steel Mace
        'dwf': (11 * CELL_DIM, 14 * CELL_DIM),  # Dwarven Flail
        'fhf': (11 * CELL_DIM, 15 * CELL_DIM),  # FLameheart Flail  

        'glo': (13 * CELL_DIM, 13 * CELL_DIM), # Glass Orb
        'ooc': (13 * CELL_DIM, 14 * CELL_DIM), # Orb of Chaos

       
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
    
    # The tile_rect now extracts the ORIGINAL_TILE_DIM (12x12) from the calculated position
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


def draw_tile(screen_surface, draw_x, draw_y, char, color_tint=None, tile_size=None, flip_x=False):
    # Support optional override size for special entities (e.g., bosses)
    if tile_size is None or tile_size == config.TILE_SIZE:
        tile_surface = get_tile_surface(char)
    else:
        # Extract base tile then rescale to requested size (int or tuple)
        base_surface = get_tile_surface(char)
        tile_surface = pygame.transform.scale(base_surface, (tile_size, tile_size))

    if flip_x:
        tile_surface = pygame.transform.flip(tile_surface, True, False)
    
    if color_tint:
        tinted_surface = tile_surface.copy()
        tinted_surface.fill(color_tint, special_flags=pygame.BLEND_RGBA_MULT)
        tile_surface = tinted_surface
    
    # Blit directly using draw_x, draw_y (int if floats)
    blit_x = int(draw_x) if hasattr(draw_x, '__float__') else draw_x
    blit_y = int(draw_y) if hasattr(draw_y, '__float__') else draw_y
    screen_surface.blit(tile_surface, (blit_x, blit_y))