import pygame
import config
import math  # For wave patterns in fallbacks

# Global variable to hold the loaded tileset image
TILESET_IMAGE = None
TILE_MAPPING = {}
_SURFACE_CACHE = {}
_DRAW_CACHE = {}
_SUBMERGED_CACHE = {}

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
    _SURFACE_CACHE.clear()
    _DRAW_CACHE.clear()
    _SUBMERGED_CACHE.clear()
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
    _SURFACE_CACHE.clear()
    _DRAW_CACHE.clear()
    _SUBMERGED_CACHE.clear()
    
    # FIXED: Distinct positions for '~' (river) and '≈' (lake)
    # Adjust these coordinates based on your tileset PNG (e.g., column 11, row 4 for river; try column 12 for lake if needed)
    # Use an image editor to verify the grid positions.
    TILE_MAPPING = {

        # ── Player Characters ─────────────────────────────────────────────
        # Row 0 — Human
        'HF':  (0 * CELL_DIM,  0 * CELL_DIM),  # Human Fighter
        'HR':  (1 * CELL_DIM,  0 * CELL_DIM),  # Human Rogue
        'HW':  (2 * CELL_DIM,  0 * CELL_DIM),  # Human Wizard
        'HC':  (3 * CELL_DIM,  0 * CELL_DIM),  # Human Cleric
        'HG':  (0 * CELL_DIM,  21 * CELL_DIM),  # Human Ranger

        # Row 1 — Dwarf (Hill Dwarf uses the base dwarf row)
        'DF':  (0 * CELL_DIM,  1 * CELL_DIM),  # Hill Dwarf Fighter
        'DR':  (1 * CELL_DIM,  1 * CELL_DIM),  # Hill Dwarf Rogue
        'DW':  (2 * CELL_DIM,  1 * CELL_DIM),  # Hill Dwarf Wizard
        'DC':  (3 * CELL_DIM,  1 * CELL_DIM),  # Hill Dwarf Cleric
        'DG':  (0 * CELL_DIM, 22 * CELL_DIM),  # Hill Dwarf Ranger
        # Mountain Dwarf — shares the Hill Dwarf row (same sprite set)
        'MDF': (4 * CELL_DIM,  1 * CELL_DIM),  # Mountain Dwarf Fighter
        'MDR': (5 * CELL_DIM,  1 * CELL_DIM),  # Mountain Dwarf Rogue
        'MDW': (6 * CELL_DIM,  1 * CELL_DIM),  # Mountain Dwarf Wizard
        'MDC': (7 * CELL_DIM,  1 * CELL_DIM),  # Mountain Dwarf Cleric
        'MDG': (4 * CELL_DIM, 22 * CELL_DIM),  # Mountain Dwarf Ranger
        # Duergar — shares the Hill Dwarf row until a dedicated row exists
        'DGF': (8 * CELL_DIM,  1 * CELL_DIM),   # Duergar Fighter
        'DGR': (9 * CELL_DIM,  1 * CELL_DIM),   # Duergar Rogue
        'DGW': (10 * CELL_DIM,  1 * CELL_DIM),  # Duergar Wizard
        'DGC': (11 * CELL_DIM,  1 * CELL_DIM),  # Duergar Cleric
        'DGG': (8 * CELL_DIM, 22 * CELL_DIM),  # Duergar Ranger

        # Row 2 — Elf (Drow uses the base elf row)
        'EF':  (0 * CELL_DIM,  2 * CELL_DIM),  # Drow Fighter
        'ER':  (1 * CELL_DIM,  2 * CELL_DIM),  # Drow Rogue
        'EW':  (2 * CELL_DIM,  2 * CELL_DIM),  # Drow Wizard
        'EC':  (3 * CELL_DIM,  2 * CELL_DIM),  # Drow Cleric
        'EG':  (0 * CELL_DIM, 23 * CELL_DIM),  # Drow Cleric
        # High Elf — shares the Drow elf row until a dedicated row exists
        'HEF': (4 * CELL_DIM,  2 * CELL_DIM),  # High Elf Fighter
        'HER': (5 * CELL_DIM,  2 * CELL_DIM),  # High Elf Rogue
        'HEW': (6 * CELL_DIM,  2 * CELL_DIM),  # High Elf Wizard
        'HEC': (7 * CELL_DIM,  2 * CELL_DIM),  # High Elf Cleric
        'HEG': (4 * CELL_DIM, 23 * CELL_DIM),  # High Elf Cleric
        # Wood Elf — shares the Drow elf row until a dedicated row exists
        'WEF': (8 * CELL_DIM,  2 * CELL_DIM),   # Wood Elf Fighter
        'WER': (9 * CELL_DIM,  2 * CELL_DIM),   # Wood Elf Rogue
        'WEW': (10 * CELL_DIM,  2 * CELL_DIM),  # Wood Elf Wizard
        'WEC': (11 * CELL_DIM,  2 * CELL_DIM),  # Wood Elf Cleric
        'WEG': (8 * CELL_DIM,  23 * CELL_DIM),  # Wood Elf Cleric

        # Row 10 — Tiefling (all patron lineages share the base tiefling row)
        'TF':  (0 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Fighter   (legacy key, kept for safety)
        'TR':  (1 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Rogue     (legacy key)
        'TW':  (2 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Wizard    (legacy key)
        'TC':  (3 * CELL_DIM, 10 * CELL_DIM),  # Tiefling Cleric    (legacy key)
        # Zariel
        'ZTF': (0 * CELL_DIM, 10 * CELL_DIM),  # Zariel Tiefling Fighter
        'ZTR': (1 * CELL_DIM, 10 * CELL_DIM),  # Zariel Tiefling Rogue
        'ZTW': (2 * CELL_DIM, 10 * CELL_DIM),  # Zariel Tiefling Wizard
        'ZTC': (3 * CELL_DIM, 10 * CELL_DIM),  # Zariel Tiefling Cleric
        # Levistus
        'LTF': (4 * CELL_DIM, 10 * CELL_DIM),  # Levistus Tiefling Fighter
        'LTR': (5 * CELL_DIM, 10 * CELL_DIM),  # Levistus Tiefling Rogue
        'LTW': (6 * CELL_DIM, 10 * CELL_DIM),  # Levistus Tiefling Wizard
        'LTC': (7 * CELL_DIM, 10 * CELL_DIM),  # Levistus Tiefling Cleric
        # Dispater
        'DTF': (8 * CELL_DIM, 10 * CELL_DIM),  # Dispater Tiefling Fighter
        'DTR': (9 * CELL_DIM, 10 * CELL_DIM),  # Dispater Tiefling Rogue
        'DTW': (10 * CELL_DIM, 10 * CELL_DIM),  # Dispater Tiefling Wizard
        'DTC': (11 * CELL_DIM, 10 * CELL_DIM),  # Dispater Tiefling Cleric
        # Mephistopheles
        'MTF': (12 * CELL_DIM, 10 * CELL_DIM),  # Mephistopheles Tiefling Fighter
        'MTR': (13 * CELL_DIM, 10 * CELL_DIM),  # Mephistopheles Tiefling Rogue
        'MTW': (14 * CELL_DIM, 10 * CELL_DIM),  # Mephistopheles Tiefling Wizard
        'MTC': (15 * CELL_DIM, 10 * CELL_DIM),  # Mephistopheles Tiefling Cleric

        # Row 11 — Dragonborn (all colour lineages share the base dragonborn row)
        'DBF': (0 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Fighter (legacy key)
        'DBR': (1 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Rogue   (legacy key)
        'DBW': (2 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Wizard  (legacy key)
        'DBC': (3 * CELL_DIM, 11 * CELL_DIM),  # Dragonborn Cleric  (legacy key)
        # Red
        'RDF': (0 * CELL_DIM, 11 * CELL_DIM),  # Red Dragonborn Fighter
        'RDR': (1 * CELL_DIM, 11 * CELL_DIM),  # Red Dragonborn Rogue
        'RDW': (2 * CELL_DIM, 11 * CELL_DIM),  # Red Dragonborn Wizard
        'RDC': (3 * CELL_DIM, 11 * CELL_DIM),  # Red Dragonborn Cleric        
        # Gold
        'GDF': (4 * CELL_DIM, 11 * CELL_DIM),  # Gold Dragonborn Fighter
        'GDR': (5 * CELL_DIM, 11 * CELL_DIM),  # Gold Dragonborn Rogue
        'GDW': (6 * CELL_DIM, 11 * CELL_DIM),  # Gold Dragonborn Wizard
        'GDC': (7 * CELL_DIM, 11 * CELL_DIM),  # Gold Dragonborn Cleric
        # Green
        'GNF': (8 * CELL_DIM, 11 * CELL_DIM),   # Green Dragonborn Fighter
        'GNR': (9 * CELL_DIM, 11 * CELL_DIM),   # Green Dragonborn Rogue
        'GNW': (10 * CELL_DIM, 11 * CELL_DIM),  # Green Dragonborn Wizard
        'GNC': (11 * CELL_DIM, 11 * CELL_DIM),  # Green Dragonborn Cleric
        # Blue
        'BDF': (12 * CELL_DIM, 11 * CELL_DIM),  # Blue Dragonborn Fighter
        'BDR': (13 * CELL_DIM, 11 * CELL_DIM),  # Blue Dragonborn Rogue
        'BDW': (14 * CELL_DIM, 11 * CELL_DIM),  # Blue Dragonborn Wizard
        'BDC': (15 * CELL_DIM, 11 * CELL_DIM),  # Blue Dragonborn Cleric



        # Map Tiles
        'bl': (16 * CELL_DIM, 6 * CELL_DIM), # Bloodstain
        '{': (0 * CELL_DIM, 6 * CELL_DIM),   # Tavern Crate
        '}': (2 * CELL_DIM, 6 * CELL_DIM),   # Tavern Barrel
        ',': (2 * CELL_DIM, 17 * CELL_DIM),  # Tavern Floor
        '?': (1 * CELL_DIM, 17 * CELL_DIM),  # Kitchen Tavern Floor
        '.': (0 * CELL_DIM, 3 * CELL_DIM),   # Floor
        '#': (1 * CELL_DIM, 3 * CELL_DIM),   # Wall
        '>': (8 * CELL_DIM, 3 * CELL_DIM),   # Stairs Down
        '<': (9 * CELL_DIM, 3 * CELL_DIM),   # Stairs Up
        '&': (10 * CELL_DIM, 3 * CELL_DIM),  # Altar
        '+': (2 * CELL_DIM, 3 * CELL_DIM),   # Tavern Door
        ';': (1 * CELL_DIM, 4 * CELL_DIM),   # Bones
        '%': (2 * CELL_DIM, 4 * CELL_DIM),   # Rubble
        'x': (3 * CELL_DIM, 4 * CELL_DIM),   # Cobweb
        '*': (4 * CELL_DIM, 4 * CELL_DIM),   # Mushroom
        'fb': (5 * CELL_DIM, 4 * CELL_DIM),  # Fresh Bones
        '`': (6 * CELL_DIM, 4 * CELL_DIM),   # Dungeon Grass
        'dp': (7 * CELL_DIM, 4 * CELL_DIM),  # Dungeon Pillar
        '.2': (8 * CELL_DIM, 4 * CELL_DIM),  # Dungeon Floor Two
        '.3': (9 * CELL_DIM, 4 * CELL_DIM),  # Dungeon Floor Three
        '.5': (12 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Five 
        '.6': (13 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Six 
        '.4': (14 * CELL_DIM, 4 * CELL_DIM), # Dungeon Floor Four
        'w': (15 * CELL_DIM, 4 * CELL_DIM),  # Window
        '`2': (10 * CELL_DIM, 4 * CELL_DIM), # Dungeon Grass Two
        'tm': (7 * CELL_DIM, 5 * CELL_DIM),  # Tomb 
        'otm': (8 * CELL_DIM, 5 * CELL_DIM), # Open Tomb

        'pd':  (11 * CELL_DIM, 3 * CELL_DIM),   # Prison Door (closed)
        'pdo': (12 * CELL_DIM, 3 * CELL_DIM),   # Prison Door (open)
        'pb':  (13 * CELL_DIM, 3 * CELL_DIM),   # Prison Bars  – pick a free cell

        '~': (11 * CELL_DIM, 4 * CELL_DIM),  # River (Water) - FIXED: Keep this
        '≈': (11 * CELL_DIM, 4 * CELL_DIM),  # Lake (Water) - FIXED: Distinct position (adjust if your tileset has it elsewhere)


        # Overworld Tiles
        'rd': (0 * CELL_DIM, 3 * CELL_DIM),    # Road
        'tre': (0 * CELL_DIM, 18 * CELL_DIM),  # Tree
        'grd': (1 * CELL_DIM, 18 * CELL_DIM),  # Ground
        '`3': (2 * CELL_DIM, 18 * CELL_DIM),   # Tall Grass
        'mnt': (3 * CELL_DIM, 18 * CELL_DIM),  # Mountain

        'cl': (4 * CELL_DIM, 18 * CELL_DIM),   # Clearing
        'GT': (5 * CELL_DIM, 18 * CELL_DIM),   # Giant Tree
        'pnd': (6 * CELL_DIM, 18 * CELL_DIM),  # Pond
        'ff': (7 * CELL_DIM, 18 * CELL_DIM),   # Flower Field
        'clf': (1 * CELL_DIM, 18 * CELL_DIM),  # Cliff
        'vy': (1 * CELL_DIM, 18 * CELL_DIM),   # Valley 
        'wtf': (1 * CELL_DIM, 18 * CELL_DIM),  # Waterfall
        'sc': (8 * CELL_DIM, 18 * CELL_DIM),   # Scree
        'rg': (1 * CELL_DIM, 18 * CELL_DIM),   # Ridge
        'md': (9 * CELL_DIM, 18 * CELL_DIM),   # Meadow
        'rk': (10 * CELL_DIM, 18 * CELL_DIM),  # Rock Formation
        'mp': (11 * CELL_DIM, 18 * CELL_DIM),  # Marsh Pool
        'rds': (12 * CELL_DIM, 18 * CELL_DIM), # Reeds
        'ddf': (13 * CELL_DIM, 18 * CELL_DIM), # Dead Forest


        'amt': (13 * CELL_DIM, 18 * CELL_DIM),  # Ambush Tree (Landmark)
        'ocw': (14 * CELL_DIM, 18 * CELL_DIM),  # Overworld Cobweb (Landmark)
        'bt':  (15 * CELL_DIM, 18 * CELL_DIM),  # Boat (Washed Ashore)
        '`4':  (16 * CELL_DIM, 18 * CELL_DIM),  # Grass
        'fnc': (17 * CELL_DIM, 18 * CELL_DIM),  # Fence
        'fng': (18 * CELL_DIM, 18 * CELL_DIM),  # Fence Gate
        'bnr': (19 * CELL_DIM, 18 * CELL_DIM),  # Banner

        'gvs1':(0 * CELL_DIM,  19 * CELL_DIM),  # Gravestone One (Landmark)
        'gvs2':(1 * CELL_DIM,  19 * CELL_DIM),  # Gravestone Two (Landmark)
        'gvs3':(2 * CELL_DIM,  19 * CELL_DIM),  # Gravestone Three (Landmark)
        'crv': (3 * CELL_DIM,  19 * CELL_DIM),  # Caravan (Landmark)
        'ten': (4 * CELL_DIM,  19 * CELL_DIM),  # Tent (Landmark)
        'rtc': (6 * CELL_DIM,  19 * CELL_DIM),  # Ritual Circle (Landmark)
        'brc': (7 * CELL_DIM,  19 * CELL_DIM),  # Barricade (Landmark)

        'sll': (0 * CELL_DIM,  20 * CELL_DIM),  # Sail Left
        'slm': (1 * CELL_DIM,  20 * CELL_DIM),  # Sail Middle
        'slr': (2 * CELL_DIM,  20 * CELL_DIM),  # Sail Right


        # Elemental Tiles
        'fire': (12 * CELL_DIM, 5 * CELL_DIM),  # Fire
        

        # IMPORTANT: Ensure 'C' is your *closed* chest graphic
        'C':  (4 * CELL_DIM, 5 * CELL_DIM),   # Chest (Closed)
        'O':  (5 * CELL_DIM, 5 * CELL_DIM),   # Open Chest
        # Locked chest variants — adjust all three coords to match your tileset
        'LC':  (4 * CELL_DIM, 5 * CELL_DIM),  # Locked Chest (closed)
        'olc': (5 * CELL_DIM, 5 * CELL_DIM),  # Locked Chest (opened)
        'LM':  (5 * CELL_DIM, 6 * CELL_DIM),  # Locked Chest Mimic (revealed)

        'IC': (4 * CELL_DIM, 6 * CELL_DIM),   # Indoor Chest Overworld (closed)
        'ICO': (5 * CELL_DIM, 6 * CELL_DIM),   # Indoor Chest Overworld (opened)
        'OC': (7 * CELL_DIM, 6 * CELL_DIM),   # Outdoor Chest Overworld (closed)
        'OCO': (8 * CELL_DIM, 6 * CELL_DIM),   # Outdoor Chest Overworld (opened)
        
        
        'c': (3 * CELL_DIM, 3 * CELL_DIM),    # Chair (Tavern)
        't': (4 * CELL_DIM, 3 * CELL_DIM),    # Table (Tavern)
        '=': (5 * CELL_DIM, 3 * CELL_DIM),    # Bar Counter
        'I': (3 * CELL_DIM, 17 * CELL_DIM),   # Bar Counter Two
        '7': (4 * CELL_DIM, 17 * CELL_DIM),   # Bar Counter Three
        '|': (5 * CELL_DIM, 17 * CELL_DIM),   # Bar Counter Four
        'F': (6 * CELL_DIM, 3 * CELL_DIM),    # Fireplace
        'i': (7 * CELL_DIM, 3 * CELL_DIM),    # Torch Wall
        '}2': (6 * CELL_DIM, 17 * CELL_DIM),  # Tavern Barrel Two
        '5':  (7 * CELL_DIM, 17 * CELL_DIM),  # Shelf
        '52': (8 * CELL_DIM, 17 * CELL_DIM),  # Shelf Two
        '--': (9 * CELL_DIM, 17 * CELL_DIM),  # Bed
        'fg': (10 * CELL_DIM, 17 * CELL_DIM),  # Forge
        'av': (11 * CELL_DIM, 17 * CELL_DIM),  # Anvil
        '53': (12 * CELL_DIM, 17 * CELL_DIM),  # Shelf Three
        '|2': (13 * CELL_DIM, 17 * CELL_DIM),  # Bar Counter Five
        '|3': (14 * CELL_DIM, 17 * CELL_DIM),  # Bar Counter Six
        'cau': (15 * CELL_DIM, 17 * CELL_DIM), # Cauldron
        'lad': (16 * CELL_DIM, 17 * CELL_DIM), # Ladder
        'tcw': (17 * CELL_DIM, 17 * CELL_DIM), # Tavern Cobweb
        'tpn': (18 * CELL_DIM, 17 * CELL_DIM), # Wood Plank
        'hy': (15 * CELL_DIM, 17 * CELL_DIM),  # Hay

        # Dragon Bones
        'dsk': (16 * CELL_DIM, 17 * CELL_DIM),  # Dragon Skull
        'dskl': (17 * CELL_DIM, 17 * CELL_DIM), # Dragon Skeleton
        'dtl': (18 * CELL_DIM, 17 * CELL_DIM),  # Dragon Tail

        # Static Decorations (using distinct chars)
        'b': (2 * CELL_DIM, 5 * CELL_DIM), # Static Barrel (original graphic)
        'k': (0 * CELL_DIM, 5 * CELL_DIM), # Static Crate (original graphic)             

        # Mimic disguised as Crate/Barrel (using distinct chars)
        # These should point to your *disguised* mimic graphics (e.g., barrel with eyes)
        'K': (1 * CELL_DIM, 5 * CELL_DIM),  # Mimic Crate
        'B': (3 * CELL_DIM, 5 * CELL_DIM),  # Mimic Barrel
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
        'CA': (3 * CELL_DIM, 8 * CELL_DIM),  # Centaur Archer
        'LF': (4 * CELL_DIM, 7 * CELL_DIM),  # Lizardfolk
        'LA': (4 * CELL_DIM, 8 * CELL_DIM),  # Lizardfolk Archer
        'GS': (0 * CELL_DIM, 9 * CELL_DIM),  # Giant Spider
        'LO': (6 * CELL_DIM, 8 * CELL_DIM),  # Large Ooze
        'BH': (6 * CELL_DIM, 7 * CELL_DIM),  # Beholder

        'OB': (1 * CELL_DIM, 9 * CELL_DIM),  # Owlbear
        'DMG': (2 * CELL_DIM, 9 * CELL_DIM),  # Demogorgon
        'GK': (3 * CELL_DIM, 9 * CELL_DIM),  # Grick
        'GM': (4 * CELL_DIM, 9 * CELL_DIM),  # Gibbering Mouther
        'MF': (5 * CELL_DIM, 9 * CELL_DIM),  # Mind Flayer
        'MN': (6 * CELL_DIM, 9 * CELL_DIM),  # Minotaur
        'WR': (7 * CELL_DIM, 9 * CELL_DIM),  # Wererat
        'WF': (7 * CELL_DIM, 8 * CELL_DIM),  # Wolf        

        'YL': (8 * CELL_DIM, 7 * CELL_DIM),    # Yochlol
        'DD': (8 * CELL_DIM, 8 * CELL_DIM),    # Drider
        'DS': (8 * CELL_DIM, 9 * CELL_DIM),    # Death Slaad
        'MS': (9 * CELL_DIM, 7 * CELL_DIM),    # Myconid Sprout
        'MA': (9 * CELL_DIM, 8 * CELL_DIM),    # Myconid Adult 
        'RS': (9 * CELL_DIM, 9 * CELL_DIM),    # Red Slaad
        'MZ': (10 * CELL_DIM, 7 * CELL_DIM),   # Mezzoloth 
        'GU': (10 * CELL_DIM, 8 * CELL_DIM),   # Gauth 
        'AR': (10 * CELL_DIM, 9 * CELL_DIM),   # Arasta 
        'ID': (11 * CELL_DIM, 7 * CELL_DIM),   # Intellect Devourer
        'IM': (11 * CELL_DIM, 8 * CELL_DIM),   # Imp
        'AG': (11 * CELL_DIM, 9 * CELL_DIM),   # Alpha Grick 
        'WRT': (12 * CELL_DIM, 7 * CELL_DIM),  # Wraith
        'TTP': (12 * CELL_DIM, 9 * CELL_DIM),  # Tomb Tapper
        'g':   (13 * CELL_DIM,  7 * CELL_DIM), # Guard (NPC)
        'CUL': (13 * CELL_DIM, 8 * CELL_DIM),  # Cultist
        'pnp': (13 * CELL_DIM, 9 * CELL_DIM),  # Prisoner (NPC) 
        'tv':  (14 * CELL_DIM, 7 * CELL_DIM),  # Cocooned Traveler (NPC)
        'pg':  (14 * CELL_DIM, 8 * CELL_DIM),  # Pilgrim (NPC)
        'fm':  (14 * CELL_DIM, 9 * CELL_DIM),  # Fisherman (NPC)


        # Tavern Entities and Misc.
        'bls': (5 * CELL_DIM, 0 * CELL_DIM),  # Blacksmith (NPC)
        'H': (6 * CELL_DIM,   0 * CELL_DIM),  # Healer (NPC)        
        'rc': (7 * CELL_DIM,  0 * CELL_DIM),  # Merchant (NPC)
        'p': (8 * CELL_DIM,   0 * CELL_DIM),  # Patron (NPC)
        'A': (9 * CELL_DIM,   0 * CELL_DIM),  # Bartender (NPC)
        'td': (10 * CELL_DIM,  0 * CELL_DIM), # Trader (NPC)
        'ch': (11 * CELL_DIM,  0 * CELL_DIM), # Child (NPC)
        'cr': (12 * CELL_DIM,  0 * CELL_DIM), # Courier (NPC)
        'mh': (11 * CELL_DIM,  6 * CELL_DIM), # Mage Hand (Skill)
        'sw': (19 * CELL_DIM,  6 * CELL_DIM), # Spiritual Weapon (Skill)
        'CS': (12 * CELL_DIM,  8 * CELL_DIM), # Celestial Spirit (Skill)

        # Item Characters
        'tt': (12 * CELL_DIM,   6 * CELL_DIM), # Thieves' Tools
        'cf': (13 * CELL_DIM,   6 * CELL_DIM), # Campfire 
        'pn': (14 * CELL_DIM,   6 * CELL_DIM), # Wood Plank (Junk)
        'th': (15 * CELL_DIM,  6 * CELL_DIM),  # Torch (Item)
        'hsy': (17 * CELL_DIM, 6 * CELL_DIM),  # Holy Symbol (Accessory)
        'spb': (18 * CELL_DIM, 6 * CELL_DIM),  # Spellbook (Off-hand Item)
        '!': (0 * CELL_DIM,    13 * CELL_DIM), # Potions

        # Food Characters
        'met': (20 * CELL_DIM, 0 * CELL_DIM), # Meat
        'gra': (21 * CELL_DIM, 0 * CELL_DIM), # Green Apple
        'frg': (22 * CELL_DIM, 0 * CELL_DIM), # Fromage
        'brd': (23 * CELL_DIM, 0 * CELL_DIM), # Bread
        'msm': (24 * CELL_DIM, 0 * CELL_DIM), # Mushroom
        'crt': (25 * CELL_DIM, 0 * CELL_DIM), # Carrot

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

        # Helmets
        'lc':  (16 * CELL_DIM, 13 * CELL_DIM),  # Leather Cap
        'ih':  (16 * CELL_DIM, 14 * CELL_DIM),  # Iron Helmet
        'sh':  (16 * CELL_DIM, 15 * CELL_DIM),  # Steel Helmet
        'hs':  (16 * CELL_DIM, 16 * CELL_DIM),  # Hood of Shadows
        'gh':  (17 * CELL_DIM, 13 * CELL_DIM),  # Great Helm
        'mc':  (17 * CELL_DIM, 14 * CELL_DIM),  # Mage's Circlet

        # Boots
        'lb':  (14 * CELL_DIM, 13 * CELL_DIM),  # Leather Boots
        'ig':  (14 * CELL_DIM, 14 * CELL_DIM),  # Iron Greaves
        'bst': (14 * CELL_DIM, 15 * CELL_DIM),  # Boots of Stealth
        'bs':  (15 * CELL_DIM, 13 * CELL_DIM),  # Boots of Speed
        'ds':  (15 * CELL_DIM, 14 * CELL_DIM),  # Dwarven Stompers

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

        'arr': (19 * CELL_DIM, 13 * CELL_DIM), # Arrow

        'hbo': (18 * CELL_DIM, 13 * CELL_DIM), # Hand Crossbow
        'crb': (18 * CELL_DIM, 13 * CELL_DIM), # Crossbow
        'sbo': (18 * CELL_DIM, 14 * CELL_DIM), # Shortbow
        'lbo': (18 * CELL_DIM, 15 * CELL_DIM), # Longbow

       
    }
    print("Tile mapping setup complete.")

def get_tile_surface(char, tile_size=None):
    """
    Returns a pygame.Surface object representing the tile for the given character,
    scaled to the requested size and cached for reuse.
    """
    if TILESET_IMAGE is None:
        raise RuntimeError("Tileset not loaded. Call load_tileset() first.")

    effective_tile_size = config.TILE_SIZE if tile_size is None else int(tile_size)
    cache_key = (char, effective_tile_size)
    cached_surface = _SURFACE_CACHE.get(cache_key)
    if cached_surface is not None:
        return cached_surface

    tile_coords = TILE_MAPPING.get(char)
    if tile_coords is None:
        print(f"Warning: No tile mapping for character '{char}'. Using default blank tile.")
        blank_surface = pygame.Surface((effective_tile_size, effective_tile_size), pygame.SRCALPHA)
        _SURFACE_CACHE[cache_key] = blank_surface
        return blank_surface

    x, y = tile_coords

    tile_rect = pygame.Rect(x + TILE_X_OFFSET, y + TILE_Y_OFFSET, ORIGINAL_TILE_DIM, ORIGINAL_TILE_DIM)

    if not TILESET_IMAGE.get_rect().contains(tile_rect):
        print(f"Error: Extracted tile rect {tile_rect} for char '{char}' is out of bounds of tileset image {TILESET_IMAGE.get_size()}.")
        blank_surface = pygame.Surface((effective_tile_size, effective_tile_size), pygame.SRCALPHA)
        _SURFACE_CACHE[cache_key] = blank_surface
        return blank_surface

    subsurface = TILESET_IMAGE.subsurface(tile_rect)

    if effective_tile_size != ORIGINAL_TILE_DIM:
        scaled_surface = pygame.transform.scale(subsurface, (effective_tile_size, effective_tile_size))
        _SURFACE_CACHE[cache_key] = scaled_surface
        return scaled_surface

    _SURFACE_CACHE[cache_key] = subsurface
    return subsurface


def draw_tile(screen_surface, draw_x, draw_y, char, color_tint=None, tile_size=None, flip_x=False):
    effective_tile_size = config.TILE_SIZE if tile_size is None else int(tile_size)

    if color_tint:
        cache_key = (char, effective_tile_size, tuple(color_tint), flip_x)
        cached_surface = _DRAW_CACHE.get(cache_key)
        if cached_surface is not None:
            tile_surface = cached_surface
        else:
            tile_surface = get_tile_surface(char, tile_size=effective_tile_size)
            if flip_x:
                tile_surface = pygame.transform.flip(tile_surface, True, False)
            tinted_surface = tile_surface.copy()
            tinted_surface.fill(color_tint, special_flags=pygame.BLEND_RGBA_MULT)
            _DRAW_CACHE[cache_key] = tinted_surface
            tile_surface = tinted_surface
    elif flip_x:
        # No tint, but still flipped: cache the flipped surface so it isn't
        # regenerated with pygame.transform.flip() on every call.
        cache_key = (char, effective_tile_size, None, flip_x)
        cached_surface = _DRAW_CACHE.get(cache_key)
        if cached_surface is not None:
            tile_surface = cached_surface
        else:
            tile_surface = pygame.transform.flip(get_tile_surface(char, tile_size=effective_tile_size), True, False)
            _DRAW_CACHE[cache_key] = tile_surface
    else:
        tile_surface = get_tile_surface(char, tile_size=effective_tile_size)

    blit_x = int(draw_x) if hasattr(draw_x, '__float__') else draw_x
    blit_y = int(draw_y) if hasattr(draw_y, '__float__') else draw_y
    screen_surface.blit(tile_surface, (blit_x, blit_y))


def draw_submerged_tile(screen_surface, draw_x, draw_y, char, color_tint=None, tile_size=None, flip_x=False):
    """
    Draws an entity that is half-submerged in water: the top half shows the
    entity's own sprite and the bottom half shows a ripple sprite ('~').

    The composited (flip + tint + top/bottom merge) result is cached per
    (char, tile_size, color_tint, flip_x), so the surface is only built once
    per combination instead of being reassembled with copy()/transform.flip()/
    transform.scale()/fill() calls on every frame an entity is in water.
    """
    effective_tile_size = config.TILE_SIZE if tile_size is None else int(tile_size)
    cache_key = (char, effective_tile_size, tuple(color_tint) if color_tint else None, flip_x)

    composed_surface = _SUBMERGED_CACHE.get(cache_key)
    if composed_surface is None:
        half_height = effective_tile_size // 2

        # Top half: the entity's own sprite, flipped/tinted as needed.
        top_sprite = get_tile_surface(char, tile_size=effective_tile_size)
        if flip_x:
            top_sprite = pygame.transform.flip(top_sprite, True, False)
        if color_tint:
            tinted_top = top_sprite.copy()
            tinted_top.fill(color_tint, special_flags=pygame.BLEND_RGBA_MULT)
            top_sprite = tinted_top

        # Bottom half: the ripple sprite, stretched to fill the lower half.
        ripple_sprite = get_tile_surface('~', tile_size=effective_tile_size)
        ripple_sprite = pygame.transform.scale(ripple_sprite, (effective_tile_size, half_height))
        if color_tint:
            tinted_ripple = ripple_sprite.copy()
            tinted_ripple.fill(color_tint, special_flags=pygame.BLEND_RGBA_MULT)
            ripple_sprite = tinted_ripple

        composed_surface = pygame.Surface((effective_tile_size, effective_tile_size), pygame.SRCALPHA)
        top_clip_rect = pygame.Rect(0, 0, effective_tile_size, half_height)
        composed_surface.blit(top_sprite, (0, 0), top_clip_rect)
        composed_surface.blit(ripple_sprite, (0, half_height))

        _SUBMERGED_CACHE[cache_key] = composed_surface

    blit_x = int(draw_x) if hasattr(draw_x, '__float__') else draw_x
    blit_y = int(draw_y) if hasattr(draw_y, '__float__') else draw_y
    screen_surface.blit(composed_surface, (blit_x, blit_y))