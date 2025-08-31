# MultipleFiles/game.py
import pygame
import random
import config
import math # Import math for distance calculations

class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"
    INVENTORY = "inventory"
    INVENTORY_MENU = "inventory_menu"
    CHARACTER_MENU = "character_menu"
    TARGETING = "targeting"  
    CHARACTER_CREATION = "character_creation"
    CLASS_SELECTION = "class_selection"
    TRADE = "trade"
    GAME_OVER = "game_over" # NEW: Add GAME_OVER state


from core.fov import FOV
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from entities.player import Player, Fighter, Rogue, Wizard

# NEW: Import all monster classes
from entities.monster import (
    Monster, Mimic, GiantRat, Ooze, Goblin, GoblinArcher, Skeleton,
    SkeletonArcher, Orc, Centaur, CentaurArcher, Troll, Lizardfolk, 
    LizardfolkArcher, GiantSpider, Beholder, LargeOoze, DragonWhelp,
    Owlbear, Demogorgon, Grick, GibberingMouther, MindFlayer, Minotaur,
    Wererat, Wolf, Yochlol, Drider, BlueSlaad
)

from entities.base_entity import NPC
from entities.tavern_npcs import create_tavern_npcs, NPC, Merchant
from entities.dungeon_npcs import DungeonHealer, DungeonMerchant
from entities.tavern_npcs import NPC
from entities.races import Human, HillDwarf, DrowElf # NEW: Import DrowElf
from entities.summons import MageHandEntity
from core.abilities import SecondWind, PowerAttack, CunningAction, Evasion, FireBolt, MistyStep, MageHand
from core.message_log import MessageBox
from core.status_effects import PowerAttackBuff, CunningActionDashBuff, EvasionBuff
from items.items import Potion, Weapon, Armor, Chest, lesser_healing_potion, greater_healing_potion, wood_plank, meat, green_apple, fromage, bread, mushroom, CampfireKit
from items.items import lesser_healing_potion, greater_healing_potion, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor, robes, iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail, round_shield, kite_shield, tower_shield
from core.pathfinding import astar
from world.tile import floor, MimicTile, TrapTile
from core.floating_text import FloatingText 
import graphics


INTERNAL_WIDTH = 800
INTERNAL_HEIGHT = 600
ASPECT_RATIO = INTERNAL_WIDTH / INTERNAL_HEIGHT


class Camera:
    def __init__(self, screen_width, screen_height, tile_size, message_log_height):
        self.tile_size = tile_size
        self.viewport_width = screen_width // tile_size
        self.viewport_height = (screen_height - message_log_height) // tile_size - 2
        
        # Initialize x and y as floats
        self.x = 0.0
        self.y = 0.0
        
        # Initialize target_x and target_y as floats
        self.target_x = 0.0
        self.target_y = 0.0
        
        self.smoothing_factor = 0.08 # Adjust this value (e.g., 0.05 for very smooth, 0.3 for faster)

    def update(self, desired_target_x, desired_target_y, map_width, map_height):
        # Ensure desired_target_x/y are treated as floats for calculations
        target_x_float = float(desired_target_x)
        target_y_float = float(desired_target_y)

        # Calculate the ideal camera position (center of viewport)
        # These should also be floats
        ideal_camera_center_x = target_x_float - (self.viewport_width / 2.0)
        ideal_camera_center_y = target_y_float - (self.viewport_height / 2.0)

        # Apply linear interpolation (LERP)
        self.x += (ideal_camera_center_x - self.x) * self.smoothing_factor
        self.y += (ideal_camera_center_y - self.y) * self.smoothing_factor

        # Clamp the camera's position to map boundaries
        # Ensure map_width/height are also treated as floats in the clamping
        self.x = max(0.0, min(self.x, float(map_width - self.viewport_width)))
        self.y = max(0.0, min(self.y, float(map_height - self.viewport_height)))

        # IMPORTANT: Do NOT convert self.x and self.y to int here.
        # They should remain floats for continuous smooth movement.
        # The conversion to int will happen in world_to_screen or when blitting.

    def world_to_screen(self, world_x, world_y):
        # This method now returns screen coordinates in *float tile units*
        # representing the precise offset from the camera's top-left.
        screen_x_float = world_x - self.x
        screen_y_float = world_y - self.y
        return screen_x_float, screen_y_float
    
    def is_in_viewport(self, world_x, world_y):
        # This method also needs to use the float camera position for accurate checks
        # but the result of world_to_screen is already int, so it's fine.
        screen_x, screen_y = self.world_to_screen(world_x, world_y)
        return (0 <= screen_x < self.viewport_width and
                0 <= screen_y < self.viewport_height)


class Game:
    def __init__(self, screen):
        self.screen = screen
        
        self.fps = 30
        self.fps_font = pygame.font.SysFont('consolas', 15)  # You can adjust the font size as needed
        self.clock = pygame.time.Clock()  # Initialize the clock for FPS tracking


        self.internal_surface = None
        self.inventory_ui_surface = None
        self.camera = None
        self.message_log = None

        self.merchant = None  # Initialize merchant attribute        
        
        self.entities = []  # Initialize the entities list here
        self.turn_order = []  # Initialize the turn order list
        self.current_turn_index = 0
        
        self._recalculate_dimensions() 
        self._init_fonts()

        # NEW: Start in character creation state
        self.game_state = GameState.CHARACTER_CREATION 
        self._previous_game_state = None
        self.current_level = 1
        self.max_level_reached = 1
        self.player_has_acted = False
        self.message_log = MessageBox(
            0,
            config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT,
            config.GAME_AREA_WIDTH,
            config.MESSAGE_LOG_HEIGHT
        )
        self._recalculate_dimensions()

        self.ability_in_use = None
        self.targeting_ability_range = 0
        self.targeting_cursor_x = 0
        self.targeting_cursor_y = 0
            
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 255))
        
        self.floating_texts = []  # Initialize floating texts list

        # REMOVED: Player creation moved to character_creation_start
        self.player = None 
        
        self.selected_inventory_item = None
        self.selected_inventory_index = 0  # Initialize the selected inventory index        

        # Tile highlights for telegraphed attacks or effects: list of (x, y, (r,g,b,a))
        self.tile_highlights = []

        # Character creation specific variables
        # UPDATED: Add DrowElf to available races
        self.available_races = [Human(), HillDwarf(), DrowElf()]
        self.selected_race_index = 0 
        self.character_name = "Shadowblade" # Default name, could be input later
        self.character_class = Wizard # Available classes: Fighter, Rogue, Wizard

        self.race_class_visuals = {
            # Human mappings
            ("Human", "Fighter"): ('HF', (255, 255, 255)), # 'HF' for Human Fighter
            ("Human", "Rogue"): ('HR', (255, 255, 0)),    # 'HR' for Human Rogue
            ("Human", "Wizard"): ('HW', (0, 200, 255)),   # 'HW' for Human Wizard
         
            # Hill Dwarf mappings
            ("HillDwarf", "Fighter"): ('DF', (180, 120, 60)), # 'DF' for Dwarf Fighter
            ("HillDwarf", "Rogue"): ('DR', (200, 150, 0)),   # 'DR' for Dwarf Rogue
            ("HillDwarf", "Wizard"): ('DW', (100, 150, 255)), # 'DW' for Dwarf Wizard

            # Drow Elf mappings (NEW)
            ("DrowElf", "Fighter"): ('EF', (100, 0, 100)), # Example: Purple for Drow Fighter
            ("DrowElf", "Rogue"): ('ER', (150, 0, 150)),   # Example: Darker Purple for Drow Rogue
            ("DrowElf", "Wizard"): ('EW', (200, 0, 200)),  # Example: Lighter Purple for Drow Wizard
        }

        # Class selection
        self.available_classes = [Fighter, Rogue, Wizard] # List of class objects
        self.selected_class_index = 0 

        # Call a method to start character creation
        self.start_character_creation()

        # Mini-map specific attributes
        self.minimap_surface = None
        self.minimap_rect = None
        self.minimap_needs_redraw = True # Flag to redraw minimap only when needed

        self.dirty_rects = [] # New list to store dirty rectangles

        self.menu_open = None

        self._recalculate_minimap_dimensions()

        # NEW: Flag to track if game over message has been displayed
        self._game_over_displayed = False

        self.death_screen_alpha = 0  # Alpha for "YOU DIED" text
        self.death_screen_bg_alpha = 0  # Alpha for background overlay
        self.death_screen_subtext_alpha = 0  # Alpha for subtext
        self.death_screen_animation_phase = 0  # 0=text fade-in, 1=bg fade-in, 2=subtext fade-in, 3=done
        self.death_screen_animation_speed = 2  # Alpha increment per frame (adjust for speed)

    # Boss schedule: every 5th floor, ordered list
    BOSS_FLOORS = [
        (1, 'Demogorgon'),
        (5, 'GoblinKing'),
        (10, 'GiantSpider'),
        (15, 'Beholder'),
        (20, 'RedDragon'),
        (25, 'Demogorgon'),
    ]

    MONSTER_SPAWN_TIERS = {
        # Level range: [List of monster classes that can spawn]

        # Early dungeon fodder
        (1, 1): [Goblin, Wolf, GiantRat],
        (2, 2): [Goblin, GoblinArcher, GiantRat, Wererat, Wolf],
        (2, 3): [Goblin, GoblinArcher, Ooze, GiantRat, Wererat, GiantSpider, Wolf],

        # Early-mid dangers
        (4, 5): [Skeleton, SkeletonArcher, Orc, Grick, Ooze],
        (6, 7): [Lizardfolk, LizardfolkArcher, GiantSpider, Wererat],

        # Mid-game threats
        (8, 9): [Centaur, CentaurArcher, Troll, Owlbear],
        (10, 11): [Troll, Orc, GiantSpider, LargeOoze, Minotaur],

        # Late-mid bosses and horrors
        (12, 13): [LargeOoze, DragonWhelp, GiantSpider, GibberingMouther],
        (14, 14): [Drider],

        # High level threats
        (15, 16): [Yochlol, BlueSlaad, LargeOoze],
        (17, 18): [Beholder, MindFlayer, LargeOoze],

        # Endgame / campaign boss
        (19, 99): [Demogorgon],
    }



    def start_character_creation(self):
        self.game_state = GameState.CHARACTER_CREATION
        self.message_log.add_message("--- CHARACTER CREATION ---", (255, 215, 0))
        self.message_log.add_message("Choose your Race (Arrow Keys to navigate, Enter to select):", (200, 200, 255))
        self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
        self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))

    def finalize_race_selection(self):
        chosen_race = self.available_races[self.selected_race_index]
        self.message_log.add_message(f"You have chosen the {chosen_race.name} race!", (0, 255, 0))
        
        # Transition to class selection
        self.game_state = GameState.CLASS_SELECTION
        self.message_log.add_message("--- CLASS SELECTION ---", (255, 215, 0))
        self.message_log.add_message("Choose your Class (Arrow Keys to navigate, Enter to select):", (200, 200, 255))
        self.message_log.add_message(f"Current Class: {self.available_classes[self.selected_class_index].__name__}", (255, 255, 255))
        # Display a generic description for now, or add descriptions to classes if you want
        self.message_log.add_message("A brief description of the class will go here.", (150, 150, 150))

    def finalize_character_creation(self):
        chosen_race = self.available_races[self.selected_race_index]
        chosen_class_constructor = self.available_classes[self.selected_class_index]
        
        race_name_str = chosen_race.name.replace(" ", "") # "HillDwarf" from "Hill Dwarf"
        class_name_str = chosen_class_constructor.__name__ # "Fighter", "Rogue", "Wizard"

        default_char = '@' # Fallback char
        default_color = (255, 255, 255) # Fallback color (white)      

        player_char, player_color = self.race_class_visuals.get(
            (race_name_str, class_name_str),
            (default_char, default_color) # Default if combination not found
        )

        self.player = chosen_class_constructor(0, 0, 
                                                player_char, # Use the char from the mapping
                                                self.character_name, 
                                                player_color) # Use the color from the mapping
        
        self.player.race = chosen_race
        self.player.race.apply_traits(self.player, self) 
        
        # REMOVED: self.player.darkvision_radius = self.player.race.darkvision_radius (handled by apply_traits)
        self.player.damage_resistances.extend(self.player.race.damage_resistances)
        self.player.skill_proficiencies.extend(self.player.race.skill_proficiencies)
        self.player.weapon_proficiencies.extend(self.player.race.weapon_proficiencies)
        self.player.armor_proficiencies.extend(self.player.race.armor_proficiencies)
        
        self.player.max_hp = self.player._calculate_max_hp()
        self.player.hp = self.player.max_hp
        self.player.armor_class = self.player._calculate_ac()
        
        self.player.attack_power = self.player.get_ability_modifier(self.player.dexterity) + self.player.equipped_weapon.damage_modifier
        self.player.attack_bonus = self.player.get_ability_modifier(self.player.dexterity) + self.player.proficiency_bonus + self.player.equipped_weapon.attack_bonus
        
        self.message_log.add_message(f"You have chosen to be a {chosen_race.name} {self.player.class_name} named {self.player.name}!", (0, 255, 0))
        
        # Transition to tavern
        self.generate_tavern()

        # Calculate the ideal snapped position
        ideal_x = self.player.x - self.camera.viewport_width // 2
        ideal_y = self.player.y - self.camera.viewport_height // 2
        # Clamp ideal position to map boundaries
        ideal_x = max(0, min(ideal_x, self.game_map.width - self.camera.viewport_width))
        ideal_y = max(0, min(ideal_y, self.game_map.height - self.camera.viewport_height))
        
        self.camera.x = ideal_x
        self.camera.y = ideal_y
        self.camera.target_x = self.player.x # Also set target_x/y so lerp starts correctly
        self.camera.target_y = self.player.y
        # No need to call self.camera.update here, as render will do it.


    def _recalculate_dimensions(self):
        """Recalculate all dynamic dimensions based on current screen size."""
        config.SCREEN_WIDTH, config.SCREEN_HEIGHT = self.screen.get_size()
        
        config.UI_PANEL_WIDTH = int(config.SCREEN_WIDTH * config.UI_PANEL_WIDTH_RATIO)
        config.GAME_AREA_WIDTH = config.SCREEN_WIDTH - config.UI_PANEL_WIDTH
        config.MESSAGE_LOG_HEIGHT = int(config.SCREEN_HEIGHT * config.MESSAGE_LOG_HEIGHT_RATIO)
        
        effective_tile_pixel_size = int(config.TILE_SIZE * config.TARGET_EFFECTIVE_TILE_SCALE)
        if effective_tile_pixel_size < 1:
            effective_tile_pixel_size = 1

        new_internal_width_tiles = max(config.MIN_GAME_AREA_TILES_WIDTH, config.GAME_AREA_WIDTH // effective_tile_pixel_size)
        new_internal_height_tiles = max(config.MIN_GAME_AREA_TILES_HEIGHT, (config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT) // effective_tile_pixel_size)
        
        config.INTERNAL_GAME_AREA_WIDTH_TILES = new_internal_width_tiles
        config.INTERNAL_GAME_AREA_HEIGHT_TILES = new_internal_height_tiles
        
        config.INTERNAL_GAME_AREA_PIXEL_WIDTH = config.INTERNAL_GAME_AREA_WIDTH_TILES * config.TILE_SIZE
        config.INTERNAL_GAME_AREA_PIXEL_HEIGHT = config.INTERNAL_GAME_AREA_HEIGHT_TILES * config.TILE_SIZE
        
        self.internal_surface = pygame.Surface((config.INTERNAL_GAME_AREA_PIXEL_WIDTH, config.INTERNAL_GAME_AREA_PIXEL_HEIGHT)).convert_alpha()
        
        self.inventory_ui_surface = pygame.Surface((config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT)).convert_alpha()
        self.inventory_ui_surface.fill((0,0,0,0))

        if self.camera is None:
            self.camera = Camera(config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT, config.TILE_SIZE, config.MESSAGE_LOG_HEIGHT)
        
        self.camera.tile_size = config.TILE_SIZE 
        self.camera.viewport_width = config.INTERNAL_GAME_AREA_WIDTH_TILES
        self.camera.viewport_height = config.INTERNAL_GAME_AREA_HEIGHT_TILES
        
        if self.message_log is not None: 
            self.message_log.rect.x = 0
            self.message_log.rect.y = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
            self.message_log.rect.width = config.GAME_AREA_WIDTH
            self.message_log.rect.height = config.MESSAGE_LOG_HEIGHT
            
            new_font_size = int(config.MESSAGE_LOG_FONT_BASE_SIZE * config.TARGET_EFFECTIVE_TILE_SCALE)
            if new_font_size < 8: new_font_size = 8 
            self.message_log.font = pygame.font.SysFont('consolas', new_font_size)
            
            self.message_log.line_height = self.message_log.font.get_linesize()
            self.message_log.max_lines = self.message_log.rect.height // self.message_log.line_height
        
        graphics.setup_tile_mapping() 
        self._init_fonts() 

        # Recalculate minimap dimensions and surface
        self._recalculate_minimap_dimensions()


    def _recalculate_minimap_dimensions(self):
        """Recalculates minimap surface and rect based on current screen size."""
        # Calculate minimap dimensions based on screen size ratios
        minimap_pixel_width = int(config.SCREEN_WIDTH * config.MINIMAP_WIDTH_RATIO)
        minimap_pixel_height = int(config.SCREEN_HEIGHT * config.MINIMAP_HEIGHT_RATIO)

        # Ensure minimap dimensions are at least 1x1
        minimap_pixel_width = max(1, minimap_pixel_width)
        minimap_pixel_height = max(1, minimap_pixel_height)

        self.minimap_surface = pygame.Surface((minimap_pixel_width, minimap_pixel_height), pygame.SRCALPHA)
        self.minimap_surface.set_alpha(config.MINIMAP_ALPHA)

        # Calculate margins based on screen dimensions
        minimap_margin_top = int(config.SCREEN_HEIGHT * config.MINIMAP_MARGIN_TOP_RATIO)
        minimap_margin_right = int(config.SCREEN_WIDTH * config.MINIMAP_MARGIN_RIGHT_RATIO)

        # Position the minimap in the top-right corner of the UI panel
        self.minimap_rect = pygame.Rect(
            config.GAME_AREA_WIDTH + config.UI_PANEL_WIDTH - minimap_pixel_width - minimap_margin_right,
            minimap_margin_top,
            minimap_pixel_width,
            minimap_pixel_height
        )
        self.minimap_needs_redraw = True  # Always redraw minimap after resize


    def _init_fonts(self):
        """Initializes or re-initializes fonts based on current TILE_SIZE and screen dimensions."""
        
        temp_tile_size = max(1, config.TILE_SIZE)
        self.font = pygame.font.SysFont('consolas', temp_tile_size)
        
        self.inventory_font_header = pygame.font.SysFont('consolas', 20, bold=True)
        self.inventory_font_section = pygame.font.SysFont('consolas', 16)
        self.inventory_font_info = pygame.font.SysFont('consolas', 14)
        self.inventory_font_small = pygame.font.SysFont('consolas', 14)

        self.font_header = pygame.font.SysFont('consolas', 18, bold=True)
        self.font_section = pygame.font.SysFont('consolas', 16)
        self.font_info = pygame.font.SysFont('consolas', 14)
        self.font_small = pygame.font.SysFont('consolas', 14)
        

    def generate_tavern(self):
        self.game_state = GameState.TAVERN
        self._previous_game_state = GameState.TAVERN
        self.game_map = GameMap(24, 15)
        self.fov = FOV(self.game_map)
        self.door_position = generate_tavern(self.game_map, self.player)              
        start_x, start_y = self.game_map.width // 2 - 3 , self.game_map.height // 2 + 3
        
        self.player.x = start_x
        self.player.y = start_y
        
        # --- MODIFIED: Initial camera snap for tavern generation ---
        # Calculate the ideal snapped position
        ideal_x = float(self.player.x) - (self.camera.viewport_width / 2.0)
        ideal_y = float(self.player.y) - (self.camera.viewport_height / 2.0)
        # Clamp ideal position to map boundaries (as floats)
        ideal_x = max(0.0, min(ideal_x, float(self.game_map.width - self.camera.viewport_width)))
        ideal_y = max(0.0, min(ideal_y, float(self.game_map.height - self.camera.viewport_height)))
        self.camera.x = ideal_x
        self.camera.y = ideal_y
        self.camera.target_x = float(self.player.x) # Set target_x/y as floats
        self.camera.target_y = float(self.player.y)        
        
        self.npcs = create_tavern_npcs(self.game_map, self.door_position, self)
        self.entities = [self.player] + self.npcs
        self.turn_order = []
        self.current_turn_index = 0
        self.update_fov()
        
        self.message_log.add_message("=== WELCOME TO THE PRANCING PONY TAVERN ===", (255, 215, 0))
        self.message_log.add_message("Walk to the door (+) and press any movement key to enter the dungeon!", (150, 150, 255))
        self.minimap_needs_redraw = True # New map, redraw minimap
    

    def generate_level(self, level_number, spawn_on_stairs_up=False):
        self.game_state = GameState.DUNGEON
        self._previous_game_state = GameState.DUNGEON
        self.current_level = level_number
        self.max_level_reached = max(self.max_level_reached, level_number)
        
        self.game_map = GameMap(70, 40)
        self.fov = FOV(self.game_map)
        
        rooms, self.stairs_positions, self.torch_light_sources = generate_dungeon(self.game_map, level_number)

        if spawn_on_stairs_up and 'up' in self.stairs_positions:
            start_x, start_y = self.stairs_positions['up']
        else:
            start_x, start_y = rooms[0].center()
        
        self.player.x = start_x
        self.player.y = start_y


        ideal_x = self.player.x - self.camera.viewport_width // 2
        ideal_y = self.player.y - self.camera.viewport_height // 2
        # Clamp ideal position to map boundaries
        ideal_x = max(0, min(ideal_x, self.game_map.width - self.camera.viewport_width))
        ideal_y = max(0, min(ideal_y, self.game_map.height - self.camera.viewport_height))
        self.camera.x = ideal_x
        self.camera.y = ideal_y
        self.camera.target_x = self.player.x # Also set target_x/y so lerp starts correctly
        self.camera.target_y = self.player.y
        # No need to call self.camera.update here, as render will do it.

        
        self.entities = [self.player]
        
        monsters_per_level = min(5 + level_number, len(rooms) - 1)
        monster_rooms = rooms[1:monsters_per_level + 2]

        # Boss floors: every 5th floor via schedule
        is_boss_floor = any(level_number == f for (f, _) in self.BOSS_FLOORS)
        boss_entity = None
        boss_room = None
        if rooms and is_boss_floor:
            # Choose the largest room by area, prefer not to use the player's start room
            candidate_rooms = rooms[1:] if len(rooms) > 1 else rooms
            if candidate_rooms:
                boss_room = max(
                    candidate_rooms,
                    key=lambda r: max(0, (r.x2 - r.x1 - 1)) * max(0, (r.y2 - r.y1 - 1))
                )
                # Find a spawn point inside the boss room that is walkable and not on stairs
                preferred_spots = []
                center_x, center_y = boss_room.center()
                # Require a 1-tile margin from room walls to avoid spawning overlapping walls visually
                margin = 2  # ensures a 2x2 footprint plus 1 tile buffer from walls
                min_x = boss_room.x1 + margin
                max_x = boss_room.x2 - margin  # exclusive upper bound in range()
                min_y = boss_room.y1 + margin
                max_y = boss_room.y2 - margin

                # Prefer center if it satisfies margin
                if min_x <= center_x < max_x and min_y <= center_y < max_y:
                    preferred_spots.append((center_x, center_y))

                # Add fallback points strictly inside the margin box
                for y_coord in range(min_y, max_y):
                    for x_coord in range(min_x, max_x):
                        preferred_spots.append((x_coord, y_coord))

                spawn_x, spawn_y = None, None
                for sx, sy in preferred_spots:
                    # Require 2x2 walkable area for boss spawn AND ensure all 4 tiles are floor-like (not walls/doors)
                    size_ok = True
                    for ox in (0, 1):
                        for oy in (0, 1):
                            tx, ty = sx + ox, sy + oy
                            if not (0 <= tx < self.game_map.width and 0 <= ty < self.game_map.height):
                                size_ok = False
                                break
                            if not self.game_map.is_walkable(tx, ty):
                                size_ok = False
                                break
                            # Avoid stairs positions
                            if ('down' in self.stairs_positions and (tx, ty) == self.stairs_positions.get('down')):
                                size_ok = False
                                break
                            if ('up' in self.stairs_positions and (tx, ty) == self.stairs_positions.get('up')):
                                size_ok = False
                                break
                            # Ensure tile type is floor-ish (avoid walls/doors overlap). Use tile char check.
                            tile_char = self.game_map.tiles[ty][tx].char if hasattr(self.game_map.tiles[ty][tx], 'char') else None
                            if tile_char in ['#', '+']:
                                size_ok = False
                                break
                        if not size_ok:
                            break
                    if size_ok:
                        spawn_x, spawn_y = sx, sy
                        break

                if spawn_x is not None:
                    # Pick boss by schedule
                    boss_name = next((name for (f, name) in self.BOSS_FLOORS if f == level_number), None)
                    # Map names to classes (fallback to Demogorgon if missing)
                    name_to_cls = {
                        'GoblinKing': Goblin,  # TODO: replace with GoblinKing class when available
                        'GiantSpider': GiantSpider,
                        'Beholder': Beholder,
                        'RedDragon': DragonWhelp,  # TODO: replace with Red Dragon class when available
                        'Demogorgon': Demogorgon,
                    }
                    boss_cls = name_to_cls.get(boss_name, Demogorgon)
                    boss_entity = boss_cls(spawn_x, spawn_y)
                    # Mark as boss for rendering/logic hooks
                    setattr(boss_entity, 'is_boss', True)
                    setattr(boss_entity, 'footprint_size', boss_entity.footprint_size)
                    self.entities.append(boss_entity)
                    # Don't spawn regular monsters in the boss room
                    monster_rooms = [r for r in monster_rooms if r is not boss_room]

        # Determine which monsters can spawn on this level based on MONSTER_SPAWN_TIERS
        possible_monsters = []
        for level_range, monster_list in self.MONSTER_SPAWN_TIERS.items():
            if level_range[0] <= level_number <= level_range[1]:
                possible_monsters.extend(monster_list)
        
        # Fallback: If no specific monsters are defined for a level, use a default
        if not possible_monsters:
            possible_monsters = [GiantRat] # Default to GiantRat if no tier matches

        for i, room in enumerate(monster_rooms):
            x, y = room.center()
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y)):

                # Randomly choose a monster class from the possible_monsters list
                chosen_monster_class = random.choice(possible_monsters)
                
                # Mimic is handled separately as a special case in dungeon_generator.py
                if chosen_monster_class == Mimic:
                    continue 

                monster = chosen_monster_class(x, y)

                # --- Monster Stat Scaling (Optional, implement later) ---
                # You can add logic here to scale monster HP, attack, etc. based on level_number
                # For example:
                # monster.hp = monster.base_hp + (level_number * 2)
                # monster.max_hp = monster.hp
                # monster.attack_power = monster.base_attack_power + (level_number // 2)
                # This would require adding 'base_hp', 'base_attack_power' attributes to your monster classes.
                # For now, their __init__ values are static.

                self.entities.append(monster)

        if len(rooms) > 2 and random.random() < 0.6: # Healer spawnrate
            shuffled_healer_rooms = list(rooms[1:-1])
            random.shuffle(shuffled_healer_rooms)
            healer_spawned = False
            for healer_room in shuffled_healer_rooms:
                possible_spawn_points = []
                for y_coord in range(healer_room.y1 + 2, healer_room.y2 - 1):
                    for x_coord in range(healer_room.x1 + 2, healer_room.x2 - 1):
                        if self.game_map.is_walkable(x_coord, y_coord) and \
                           not any(e.x == x_coord and e.y == y_coord for e in self.entities):
                            is_near_tunnel = False
                            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                                neighbor_x, neighbor_y = x_coord + dx, y_coord + dy
                                if self.game_map.tiles[neighbor_y][neighbor_x] == floor and \
                                   not (healer_room.x1 < neighbor_x < healer_room.x2 and healer_room.y1 < neighbor_y < healer_room.y2):
                                    is_near_tunnel = True
                                    break
                            if not is_near_tunnel:
                                possible_spawn_points.append((x_coord, y_coord))
                
                if possible_spawn_points:
                    healer_x, healer_y = random.choice(possible_spawn_points)
                    dungeon_healer = DungeonHealer(healer_x, healer_y)
                    self.entities.append(dungeon_healer)
                    healer_spawned = True
                    break
            
            if not healer_spawned:
                self.message_log.add_message("DEBUG: Dungeon Healer could not find a suitable spawn spot.", (100, 100, 100))

        elif len(rooms) > 2 and random.random() < 0.6: # Merchant spawnrate
            shuffled_merchant_rooms = list(rooms[1:-1])
            random.shuffle(shuffled_merchant_rooms)
            merchant_spawned = False
            for merchant_room in shuffled_merchant_rooms:
                possible_spawn_points = []
                for y_coord in range(merchant_room.y1 + 2, merchant_room.y2 - 1):
                    for x_coord in range(merchant_room.x1 + 2, merchant_room.x2 - 1):
                        if self.game_map.is_walkable(x_coord, y_coord) and \
                           not any(e.x == x_coord and e.y == y_coord for e in self.entities):
                            is_near_tunnel = False
                            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                                neighbor_x, neighbor_y = x_coord + dx, y_coord + dy
                                if self.game_map.tiles[neighbor_y][neighbor_x] == floor and \
                                   not (merchant_room.x1 < neighbor_x < merchant_room.x2 and merchant_room.y1 < neighbor_y < merchant_room.y2):
                                    is_near_tunnel = True
                                    break
                            if not is_near_tunnel:
                                possible_spawn_points.append((x_coord, y_coord))
                
                if possible_spawn_points:
                    merchat_x, merchant_y = random.choice(possible_spawn_points)
                    dungeon_merchant = DungeonMerchant(merchat_x, merchant_y)
                    self.entities.append(dungeon_merchant)
                    merchant_spawned = True
                    break
            
            if not merchant_spawned:
                self.message_log.add_message("DEBUG: Dungeon Healer could not find a suitable spawn spot.", (100, 100, 100))                

        item_templates = [
            lesser_healing_potion, greater_healing_potion, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor,
            robes, iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, 
            apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail,
            round_shield, kite_shield, tower_shield
        ]

        item_spawn_chance = 0.99

        for room in rooms:
            if random.random() < item_spawn_chance:
                item_x, item_y = room.center()
                
                is_blocked_by_non_item_entity = False
                for e in self.entities:
                    if e.x == item_x and e.y == item_y and \
                       (isinstance(e, Monster) and not isinstance(e, Mimic) or isinstance(e, NPC)):
                        is_blocked_by_non_item_entity = True
                        break

                is_occupied_by_another_item = False
                for existing_item in self.game_map.items_on_ground:
                    if existing_item.x == item_x and existing_item.y == item_y:
                        is_occupied_by_another_item = True
                        break


                is_decorative_tile = self.game_map.tiles[item_y][item_x] != floor                    

                if (item_x, item_y) != (self.player.x, self.player.y) and \
                   (item_x, item_y) not in self.stairs_positions.values() and \
                   not is_blocked_by_non_item_entity and \
                   not is_occupied_by_another_item and \
                    not is_decorative_tile:
                    

                    chosen_template = random.choice(item_templates)
                    item_to_add = chosen_template.__class__(
                        name=chosen_template.name,
                        char=chosen_template.char,
                        color=chosen_template.color,
                        description=chosen_template.description,
                        **{k: v for k, v in chosen_template.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                    )

                    item_to_add.x = item_x
                    item_to_add.y = item_y
                    self.game_map.items_on_ground.append(item_to_add)

        self.turn_order = [e for e in self.entities if not (isinstance(e, Mimic) and e.disguised)]
        for entity in self.turn_order:
            entity.roll_initiative()
        
        self.turn_order = sorted(self.turn_order, key=lambda e: e.initiative, reverse=True)
        self.current_turn_index = 0
        self.update_fov()
        
        self.message_log.add_message(f"=== ENTERED DUNGEON LEVEL {level_number} ===", (0, 255, 255))        
        if hasattr(self, 'stairs_positions'):
            self.message_log.add_message(f"Stairs down at {self.stairs_positions.get('down')}", (150, 150, 255))
        self.minimap_needs_redraw = True # New map, redraw minimap

    def get_player_hp_percentage(self):
        """Returns the player's current HP as a percentage."""
        if self.player.max_hp == 0:
            return 0.0
        return self.player.hp / self.player.max_hp


    def check_tavern_door_interaction(self):
        if self.game_state == GameState.TAVERN:
            player_pos = (self.player.x, self.player.y)
            return player_pos == self.door_position
        return False

    def check_npc_interaction(self):
        if self.game_state == GameState.TAVERN:
            for npc in self.npcs:
                if (abs(self.player.x - npc.x) <= 1 and
                    abs(self.player.y - npc.y) <= 1 and
                    (abs(self.player.x - npc.x) + abs(self.player.y - npc.y)) == 1):
                    return npc
        return None


    def check_dungeon_npc_interaction(self):
        """Check for NPC interaction in the dungeon."""
        if self.game_state == GameState.DUNGEON:
            for entity in self.entities:
                # Check if the entity is either a DungeonHealer or DungeonMerchant and is adjacent to the player
                if isinstance(entity, (DungeonHealer, DungeonMerchant)):
                    if (abs(self.player.x - entity.x) <= 1 and
                        abs(self.player.y - entity.y) <= 1 and
                        (abs(self.player.x - entity.x) + abs(self.player.y - entity.y)) == 1):
                        return entity  # Return the NPC if adjacent
        return None  # No NPC found

    def check_stairs_interaction(self):
        if self.game_state == GameState.DUNGEON:
            player_pos = (self.player.x, self.player.y)
            if hasattr(self, 'stairs_positions'):
                if 'down' in self.stairs_positions and player_pos == self.stairs_positions['down']:
                    return 'down'
                elif 'up' in self.stairs_positions and player_pos == self.stairs_positions['up']:
                    return 'up'
        return None

    def handle_level_transition(self, direction):
        if direction == 'down':
            new_level = self.current_level + 1
            self.message_log.add_message(f"Going down to level {new_level}...", (100, 200, 255))
            self.generate_level(new_level, spawn_on_stairs_up=False)
        elif direction == 'up' and self.current_level > 1:
            new_level = self.current_level - 1
            self.message_log.add_message(f"Going up to level {new_level}...", (100, 200, 255))
            self.generate_level(new_level, spawn_on_stairs_up=True)
        elif direction == 'up' and self.current_level == 1:
            self.message_log.add_message("Returning to tavern...", (100, 200, 255))
            self.generate_tavern()

    
    def update_fov(self):
        # Store previous explored tiles for minimap redraw check
        previous_explored = set(self.fov.explored)
        if self.game_state == GameState.TAVERN:
            self.fov.visible_sources.clear() 
            # Pass player.darkvision_radius to compute_fov
            self.fov.compute_fov(self.player.x, self.player.y, radius=4, light_source_type='player', player_darkvision_radius=self.player.darkvision_radius)
        else:
            # Clear only visible sources, keep explored for persistent map
            self.fov.visible_sources.clear() 
            # Pass player.darkvision_radius to compute_fov
            self.fov.compute_fov(self.player.x, self.player.y, radius=4, light_source_type='player', player_darkvision_radius=self.player.darkvision_radius)

        # Check if new tiles were explored for minimap redraw
        if self.fov.explored != previous_explored:
            self.minimap_needs_redraw = True


        for entity in self.entities:
            if isinstance(entity, Monster):
                visibility_type = self.fov.get_visibility_type(entity.x, entity.y)
                if visibility_type in ['player', 'torch', 'darkvision']:
                    if not entity.is_active:
                        entity.is_active = True
                        entity.sleep_cooldown = 2 # Wake up immediately
                        self.message_log.add_message(f"You spot a {entity.name}!", entity.color)
                else:
                    # If monster is not visible, put it to sleep after a short delay
                    if entity.is_active and entity.sleep_cooldown <= 12:
                        entity.is_active = False
                        entity.sleep_cooldown = random.randint(5, 15) # Sleep for 5-15 turns
                        self.message_log.add_message(f"The {entity.name} seems to have fallen asleep.", (100, 100, 100)) # Optional: for debugging            
    


    def get_current_entity(self):
        if not self.turn_order or self.game_state == GameState.TAVERN:
            return self.player
        if self.current_turn_index >= len(self.turn_order):
            self.current_turn_index = 0
        return self.turn_order[self.current_turn_index]

    def next_turn(self):
        if self.game_state == GameState.TAVERN:
            if random.random() < 0.1:
                ambient_msgs = [
                    "The fire crackles in the hearth, filling the tavern with warmth...",
                    "Laughter erupts from a table of rowdy adventurers...",
                    "The bard plucks a lazy tune on a worn lute...",
                    "Mugs clink together as patrons cheer a victorious tale...",
                    "The innkeeper wipes down the counter with a knowing smile...",
                    "The smell of roasted meat drifts from the kitchen...",
                    "A pair of dice clatter across a wooden table, followed by groans...",
                    "Someone hums a forgotten ballad in the corner...",
                    "The tavern cat weaves between the legs of travelers, tail high...",
                    "A weary adventurer sighs, staring long into his ale..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (200, 180, 140))
            return


        # Get the entity whose turn it *just was* or *is currently* before advancing the index
        current_acting_entity = self.get_current_entity()

        # Process status effects for the entity that just completed its turn (or was about to)
        if current_acting_entity:
            current_acting_entity.process_status_effects(self)
            if current_acting_entity == self.player:
                self.player.update_hunger(self)  # Decrease hunger each turn
                if self.player.hunger < self.player.hunger_threshold:
                    hunger_msgs = [
                        f"{self.player.name}'s stomach growls hungrily...",
                        f"{self.player.name} feels their strength waning from hunger.",
                        f"A hollow ache gnaws at {self.player.name}'s insides...",
                        f"Hunger claws at {self.player.name}, demanding to be fed.",
                        f"{self.player.name} feels faint — food is needed soon."
                    ]
                    self.message_log.add_message(random.choice(hunger_msgs), (255, 100, 0))
                
                if not self.player.alive:  # Check if the player has died from hunger
                    self.handle_game_over()
                    return  # End the turn if the player is dead
                                  
       
        self.cleanup_entities()

        # If after cleanup, there are no entities left (e.g., all monsters died)
        if not self.turn_order:
            if self.player and self.player.alive:
                self.turn_order = [self.player]  # Ensure player is in turn order
                self.current_turn_index = 0
                self.player_has_acted = False  # Reset for player's next turn
                self.update_fov()  # Update FOV for the player
            return  # No more turns to process if no entities

        # Advance the turn index to the next entity
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)

        # Get the entity whose turn it is now (after advancing the index)
        current = self.get_current_entity()

        # If it's the player's turn, reset their action flag and update FOV
        if current == self.player:
            self.update_fov()
            self.player_has_acted = False  # This is correctly reset for player's turn
            if random.random() < 0.1:
                ambient_msgs = [
                    "The dungeon emits an eerie glow...",
                    "Something shuffles in the darkness...",
                    "You hear distant dripping water echo through the halls...",
                    "A cold draft snakes across the floor, chilling your bones...",
                    "The walls seem to breathe for a moment, then fall silent...",
                    "Far off, chains rattle against stone...",
                    "A whisper brushes your ear, though no one is near...",
                    "Dust stirs as if unseen footsteps pass by...",
                    "A faint growl rumbles from somewhere deeper...",
                    "Your torch sputters, shadows twisting unnaturally...",
                    "The air tastes of iron and old blood...",
                    "You catch the fleeting scent of rot and damp earth...",
                    "The silence grows so heavy, it feels like pressure on your chest...",
                    "Something skitters just beyond the edge of your vision...",
                    "The stone beneath your feet groans as if alive..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (180, 180, 180))




    def cleanup_entities(self):
        """Remove dead monsters and clean up their references."""
        for entity in self.entities[:]:  # Copy list to safely modify
            if not entity.alive:
                if isinstance(entity, Monster):
                    self.entities.remove(entity)
                    self.message_log.add_message(f"{entity.name} has fallen.", (180, 0, 0))
                elif isinstance(entity, Player):
                    # Player death is handled separately
                    if self.game_state != GameState.GAME_OVER:
                        self.message_log.add_message("Your vision fades to black... you are no more.", (200, 0, 0))
                        self.game_state = GameState.GAME_OVER
                    # IMPORTANT: Don't remove the player object from self.entities
                    return  # Stop cleanup early if player is dead

    

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            # NEW: Handle input specifically for GAME_OVER state
            if self.game_state == GameState.GAME_OVER:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        # Restart the game: reset player, generate tavern or level 1
                        self._game_over_displayed = False # Reset flag for next death
                        self.game_state = GameState.CHARACTER_CREATION  # Or directly generate tavern/level 1
                        self.start_character_creation() # Re-initialize character creation process
                        return True # Consume event
                    elif event.key == pygame.K_q:
                        # Quit the game
                        return False # Signal to quit
                continue  # Skip other event processing when game over

            if event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._recalculate_dimensions()
                self.render()            

            # NEW: Handle mouse wheel scrolling for message log
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.message_log.rect.collidepoint(event.pos): # Check if mouse is over message log
                    if event.button == 4: # Scroll up
                        self.message_log.scroll_up()
                        return True # Consume event
                    elif event.button == 5: # Scroll down
                        self.message_log.scroll_down()
                        return True # Consume event

            if event.type == pygame.KEYDOWN:

                # --- Trade Interaction ---
                if self.game_state == GameState.TRADE:
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_RETURN:  # Enter key to submit input
                            input_text = self.message_log.current_input  # Capture the input
                            self.handle_text_input(input_text.lower())  # Convert to lowercase when processing
                            self.message_log.clear_last_input()  # Clear the input after processing
                            self.message_log.show_input_area = False  # Hide input area after submission
                        elif event.key == pygame.K_ESCAPE:  # Cancel trade
                            self.message_log.add_message("Trade cancelled.", (255, 0, 0))
                            self.game_state = self._previous_game_state  # Return to previous state
                        elif event.key == pygame.K_BACKSPACE:  # Handle backspace
                            self.message_log.current_input = self.message_log.current_input[:-1]  # Remove the last character
                        else:
                            # Capture the input character
                            if event.unicode:  # Check if the event has a unicode character
                                self.message_log.current_input += event.unicode  # Append the character to the current input


                else:
                    if event.key == pygame.K_SLASH:  # Enter key to submit input
                        if self.message_log.show_input_area:  # Check if input area is visible
                            input_text = self.message_log.current_input  # Capture the input
                            self.handle_text_input(input_text.lower())  # Process the input
                        else:
                            self.message_log.show_input_area = True  # Show input area if not already visible
                            self.message_log.current_input = ""  # Clear input when activating the input area
                    elif event.key == pygame.K_BACKSPACE:  # Handle backspace
                        if self.message_log.show_input_area:  # Only allow backspace if input area is visible
                            self.message_log.current_input = self.message_log.current_input[:-1]  # Remove the last character
                    elif event.key == pygame.K_RETURN:
                        self.message_log.clear_last_input()
                        self.message_log.show_input_area = False
                    else:
                        # Capture the input character only if the input area is visible
                        if self.message_log.show_input_area and event.unicode:  # Check if the event has a unicode character
                            self.message_log.current_input += event.unicode  # Append the character to the current input


                    # Handle other key events (like opening inventory) only if not in trade state
                    if event.key == pygame.K_i:
                        if self.game_state == GameState.TARGETING:
                            self.message_log.add_message("Targeting cancelled (Inventory opened).", (150, 150, 150))
                            self.ability_in_use = None # Clear the ability
                            self.player_has_acted = False # Player didn't act if cancelled
                            self.player.current_action_state = None # Clear any pending action state                        
                        
                        if self.game_state == GameState.INVENTORY:  # If already in inventory, close it
                            self.message_log.add_message("Closing Inventory.", (100, 200, 255))
                            self.selected_inventory_item = None
                            self.game_state = self._previous_game_state
                            print("Inventory closed.")  # Debugging statement
                        elif self.game_state == GameState.INVENTORY_MENU:  # If in inventory menu, go back to main inventory
                            self.game_state = GameState.INVENTORY
                            self.selected_inventory_item = None
                            self.message_log.add_message("Returning to Inventory.", (100, 200, 255))
                        else:  # If not in inventory, open it
                            self.game_state = GameState.INVENTORY  # Open inventory
                            self.message_log.add_message("Opening Inventory...", (100, 200, 255))
                        return True  # Consume event, don't process other game states          
 
                    # Handle the Campfire Kit usage
                    if self.game_state == GameState.INVENTORY_MENU:
                        self.handle_inventory_menu_input(event.key)
                        return True

                    # Handle resting
                    if event.key == pygame.K_r:
                        if self.player:
                            print("Attempting to rest...")  # Debugging statement
                            if self.player.rest(self):
                                self.next_turn()  # End the player's turn after resting
                        return True  # Consume event 
                    

                    # --- Always accessible menus ---
                    if event.key == pygame.K_c:
                        if self.game_state == GameState.TARGETING:
                            self.message_log.add_message("Targeting cancelled (Character Menu opened).", (150, 150, 150))
                            self.ability_in_use = None # Clear the ability
                            self.player_has_acted = False # Player didn't act if cancelled
                            self.player.current_action_state = None # Clear any pending action state
                            # IMPORTANT: Do NOT set _previous_game_state here. It was already set above
                            # to the state *before* targeting. This ensures we return to DUNGEON/TAVERN.
                        if self.game_state == GameState.CHARACTER_MENU: # If already in character menu, close it
                            self.game_state = self._previous_game_state
                            self.message_log.add_message("Closing Character Menu.", (100, 200, 255))
                        else: # If not in character menu, open it
                            self.game_state = GameState.CHARACTER_MENU
                            self.message_log.add_message("Opening Character Menu...", (100, 200, 255))
                        return True # Consume event, don't process other game states  


                    # --- Inventory Navigation ---
                    if self.game_state == GameState.INVENTORY:
                        if event.key in (pygame.K_UP, pygame.K_w):  # Up arrow or W key
                            if self.player.inventory.items:  # Check if there are items in inventory
                                self.selected_inventory_index = (self.selected_inventory_index - 1) % len(self.player.inventory.items)
                        elif event.key in (pygame.K_DOWN, pygame.K_s):  # Down arrow or S key
                            if self.player.inventory.items:  # Check if there are items in inventory
                                self.selected_inventory_index = (self.selected_inventory_index + 1) % len(self.player.inventory.items)
                        elif event.key == pygame.K_RETURN:  # Enter key to select item
                            if self.player.inventory.items:
                                # Ensure the index is within bounds
                                if 0 <= self.selected_inventory_index < len(self.player.inventory.items):
                                    self.selected_inventory_item = self.player.inventory.items[self.selected_inventory_index]
                                    self.game_state = GameState.INVENTORY_MENU
                                    self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
                                else:
                                    self.message_log.add_message("Invalid item selection.", (255, 0, 0))  # Log an error message
                        return True  # Consume event

                # --- Trade Interaction --- 
                if self.game_state in GameState.DUNGEON:
                    if event.key == pygame.K_f:  # Check if 'F' is pressed
                        # Check for adjacent Dungeon Merchant
                        merchant = self.check_dungeon_npc_interaction()  # Check for adjacent NPC
                        if isinstance(merchant, DungeonMerchant):
                            merchant.offer_trade(self.player, self)  # Call the trade method for the Merchant
                            return True  # Consume event

                if self.game_state in GameState.TAVERN:
                    if event.key == pygame.K_f:  # Check if 'F' is pressed
                        npc = self.check_npc_interaction()  # Check for adjacent NPC
                        if npc:
                            if isinstance(npc, Merchant):
                                npc.offer_trade(self.player, self)  # Call the trade method for the Merchant
                            else:
                                self.message_log.add_message(f"{npc.name}: {npc.get_dialogue()}", (200, 200, 255))
                            return True  # Consume event


                # --- Handle Character Creation Input ---
                if self.game_state == GameState.CHARACTER_CREATION:
                   if self.game_state == GameState.CHARACTER_CREATION:
                       if event.key in (pygame.K_UP, pygame.K_w):
                           self.selected_race_index = (self.selected_race_index - 1) % len(self.available_races)
                           self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
                           self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))
                       elif event.key in (pygame.K_DOWN, pygame.K_s):
                           self.selected_race_index = (self.selected_race_index + 1) % len(self.available_races)
                           self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
                           self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))
                       elif event.key == pygame.K_RETURN:
                           self.finalize_race_selection() 
                       return True  # Consume event so no other input is processed

                if self.game_state == GameState.CLASS_SELECTION:
                    print(f"DEBUG: In CLASS_SELECTION state. Selected Class Index: {self.selected_class_index}")
                    if event.key in (pygame.K_UP, pygame.K_w):
                        print("DEBUG: K_UP pressed in CLASS_SELECTION")
                        self.selected_class_index = (self.selected_class_index - 1) % len(self.available_classes)
                        self.message_log.add_message(f"Current Class: {self.available_classes[self.selected_class_index].__name__}", (255, 255, 255))
                        self.message_log.add_message("A brief description of the class will go here.", (150, 150, 150))
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        print("DEBUG: K_DOWN pressed in CLASS_SELECTION")
                        self.selected_class_index = (self.selected_class_index + 1) % len(self.available_classes)
                        self.message_log.add_message(f"Current Class: {self.available_classes[self.selected_class_index].__name__}", (255, 255, 255))
                        self.message_log.add_message("A brief description of the class will go here.", (150, 150, 150))
                    elif event.key == pygame.K_RETURN:
                        print("DEBUG: K_RETURN pressed in CLASS_SELECTION")
                        self.finalize_character_creation()
                    return True


              
                # --- Handle input based on game state ---
                if self.game_state == GameState.INVENTORY:
                    self.handle_inventory_input(event.key)
                    return True
                elif self.game_state == GameState.INVENTORY_MENU:
                    self.handle_inventory_menu_input(event.key)
                    return True
                elif self.game_state == GameState.CHARACTER_MENU:
                    return True

                elif self.game_state == GameState.TARGETING: 
                    self.handle_targeting_input(event.key)
                    if self.game_state != GameState.TARGETING: 
                        pass 
                    else: # Still in TARGETING state (e.g., invalid target chosen)
                        return True # Consume event, stay in targeting mode                
                    
                
                if self.game_state not in [GameState.DUNGEON, GameState.TAVERN]:
                    continue

                # --- Player's turn logic (for Dungeon and Tavern) ---
                # This block will now be reached if TARGETING was cancelled and game_state reverted.
                can_player_act_this_turn = (self.game_state == GameState.TAVERN) or \
                                           (self.get_current_entity() == self.player and not self.player_has_acted)

                if not can_player_act_this_turn:
                    continue
                
                dx, dy = 0, 0
                action_taken = False
              

                # --- Rogue Skill ---
                if self.player.current_action_state == "cunning_action_dash":
                    # Determine the full intended dash vector
                    full_dx, full_dy = 0, 0
                    if event.key in (pygame.K_UP, pygame.K_w):
                        full_dy = -3
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        full_dy = 3
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        full_dx = -3
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        full_dx = 3
                    elif event.key == pygame.K_ESCAPE:
                        self.player.current_action_state = None
                        self.player.dash_active = False
                        self.message_log.add_message("Dash movement cancelled.", (150, 150, 150))
                        continue
                    else:
                        self.message_log.add_message("You are Dashing. Press a movement key or ESC to cancel.", (255, 150, 0))
                        continue

                    if full_dx != 0 or full_dy != 0:
                        moved_successfully = False
                        
                        # Determine step direction (e.g., -1, 0, 1)
                        step_dx = 0 if full_dx == 0 else (full_dx // abs(full_dx))
                        step_dy = 0 if full_dy == 0 else (full_dy // abs(full_dy))
                        
                        # Iterate step by step
                        for i in range(1, 4): # Dash is 3 tiles, so check 1, 2, 3 steps
                            check_x = self.player.x + step_dx * i
                            check_y = self.player.y + step_dy * i
                           
                            # Check if the next tile is walkable and not blocked by an entity
                            is_blocked_by_entity = False
                            for entity in self.entities:
                                if entity != self.player and entity.alive and entity.blocks_movement:
                                    if hasattr(entity, 'occupies_tile'):
                                        if entity.occupies_tile(check_x, check_y):
                                            is_blocked_by_entity = True
                                            break
                                    else:
                                        if entity.x == check_x and entity.y == check_y:
                                            is_blocked_by_entity = True
                                            break

                            if not self.game_map.is_walkable(check_x, check_y) or is_blocked_by_entity:
                                # Obstacle found, stop one tile before it if possible
                                if i > 1: # If we moved at least one tile before hitting obstacle
                                    self.player.x = self.player.x + step_dx * (i - 1)
                                    self.player.y = self.player.y + step_dy * (i - 1)
                                    self.message_log.add_message("You Dash forward and stop before an obstacle!", (100, 255, 100))
                                    moved_successfully = True
                                else: # Obstacle right next to player, cannot dash
                                    self.message_log.add_message("You cannot Dash forward due to an immediate obstacle!", (255, 150, 0))
                                    moved_successfully = False # No movement occurred
                                break # Stop checking further steps
                            else:
                                # If this is the last step and it's clear, move fully
                                if i == 3:
                                    self.player.x = check_x
                                    self.player.y = check_y
                                    self.message_log.add_message("You Dash forward!", (100, 255, 100))
                                    moved_successfully = True
                                    break # Full dash completed
                        # If the loop finishes without breaking (meaning full dash was possible)
                        # This case is handled by the 'if i == 3' inside the loop.
                        # If no movement occurred (e.g., blocked immediately), moved_successfully will be False.
                        if moved_successfully:
                            action_taken = True
                        else:
                            action_taken = False # No action taken if couldn't move at all
                        self.player.dash_active = False
                        self.player.current_action_state = None
                        continue # Consume the event and proceed to next turn if action_taken is True                                
                
                current_entity = self.get_current_entity()
                if current_entity == self.player and not self.player_has_acted:
                    if event.key in (pygame.K_a, pygame.K_LEFT):
                        self.player.set_facing_direction(True)  # Look left
                    elif event.key in (pygame.K_d, pygame.K_RIGHT):
                        self.player.set_facing_direction(False)   # Look right  

                # --- Normal Turn Handling (if no special action state is active) ---
                if self.player.current_action_state is None:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        dy = -1
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        dy = 1
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        dx = -1
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        dx = 1
                    
                  

                    if dx != 0 or dy != 0:
                        action_taken = self.handle_player_action(dx, dy)
                    elif event.key == pygame.K_SPACE:
                        if self.game_state == GameState.DUNGEON:
                            # --- MODIFIED START ---
                            # Prioritize picking up items at player's feet
                            if self.handle_item_pickup():
                                action_taken = True
                            else:
                                # If no item at feet, check for adjacent interactables
                                target = self.get_adjacent_target()
                                if target:
                                    if isinstance(target, Mimic): # Mimics are entities, but also interactable
                                        target.reveal(self)
                                        action_taken = True
                                    elif isinstance(target, Monster): # If it's a monster, attack it
                                        self.handle_player_attack(target, self)
                                        action_taken = True
                                    else:
                                        self.message_log.add_message(f"You can't interact with {target.name} that way.", (150, 150, 150))
                                else:
                                    # If no adjacent entity, check for chests at player's position
                                    chest_at_pos = self.get_chest_at(self.player.x, self.player.y)
                                    if chest_at_pos:
                                        chest_at_pos.open(self.player, self)
                                        action_taken = True
                                    else:
                                        self.message_log.add_message("Nothing to interact with here.", (150, 150, 150))
                            # --- MODIFIED END ---

                    sorted_abilities = sorted(self.player.abilities.values(), key=lambda ab: ab.name)                    


                    # For abilities:
                    if pygame.K_1 <= event.key <= pygame.K_9:
                        ability_index = event.key - pygame.K_1
                        if 0 <= ability_index < len(sorted_abilities):
                            ability_to_use = sorted_abilities[ability_index]
                            if self.game_state == GameState.DUNGEON:    
                                if ability_to_use.use(self.player, self):
                                    if self.game_state != GameState.TARGETING:
                                        action_taken = True
                                else:
                                    pass # Debug print removed
                            else:
                                self.message_log.add_message("Abilities can only be used in the dungeon.", (150, 150, 150))
                        else:
                            self.message_log.add_message("No ability assigned to that hotkey.", (150, 150, 150)) 

                    elif event.key == pygame.K_F11:
                        flags = self.screen.get_flags()
                        if flags & pygame.FULLSCREEN:
                            info = pygame.display.Info()
                            self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
                        else:
                            self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.RESIZABLE)
                        self._recalculate_dimensions()
                        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height) 
                        self.render()
                        return True
                
                if action_taken:
                    if self.game_state == GameState.DUNGEON:
                        self.player_has_acted = True
                    self.next_turn()
                    return True
        return True 


    def handle_targeting_input(self, key):
        """Handles input when in GameState.TARGETING (Mage Hand, etc.)"""
        dx, dy = 0, 0  # Cursor movement directions

        # Handle cursor movement
        if key in (pygame.K_UP, pygame.K_w, pygame.K_k):
            dy = -1
        elif key in (pygame.K_DOWN, pygame.K_s, pygame.K_j):
            dy = 1
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_h):
            dx = -1
        elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_l):
            dx = 1

        # Apply movement if possible
        if dx != 0 or dy != 0:
            new_x = self.targeting_cursor_x + dx
            new_y = self.targeting_cursor_y + dy

            # Keep cursor within map bounds and within ability range
            if (0 <= new_x < self.game_map.width and
                0 <= new_y < self.game_map.height and
                self.player.distance_to(new_x, new_y) <= self.targeting_ability_range):  # Check against ability range
                self.targeting_cursor_x = new_x
                self.targeting_cursor_y = new_y
                return  # Done, next frame will render cursor

        # Confirm target selection
        elif key == pygame.K_RETURN:
            print("DEBUG: K_RETURN pressed in TARGETING. Calling execute_targeted_ability.") # <--- ADD THIS
            self.execute_targeted_ability()  # Handle the ability effect
            return  # Exit targeting mode

        # Cancel targeting
        if key == pygame.K_ESCAPE:
            self.message_log.add_message("Targeting cancelled.", (150, 150, 150))
            self.game_state = self._previous_game_state # Return to previous state (DUNGEON)
            self.ability_in_use = None # Clear the ability
            self.player_has_acted = False # Player didn't act if cancelled
            self.player.current_action_state = None # <--- THIS LINE MUST BE HERE
            return # Input handled 


    def handle_text_input(self, input_text):
        """Handles text input from the player."""
        input_text = input_text.lower()  # Convert input to lowercase
        if self.game_state == GameState.TRADE:
            if input_text.startswith("buy "):
                item_name = input_text[4:]  # Get the item name after "buy "
                result = self.merchant.buy_item(self.player, item_name)
                self.message_log.add_message(result, (255, 255, 255))
            elif input_text.startswith("sell "):
                item_name = input_text[5:]  # Get the item name after "sell "
                result = self.merchant.sell_item(self.player, item_name)
                self.message_log.add_message(result, (255, 255, 255))
            else:
                add_ambient_merchant_message = [
                    "The merchant squints at you: 'I only deal in proper trades. Say *buy <item>* or *sell <item>*.'",
                    "The trader frowns: 'That makes no sense to me, friend. Try *buy <item>* or *sell <item>* if you mean business.'",
                    "The merchant raises a brow: 'I’ll not play games. Speak plain: *buy <item>* or *sell <item>*.'",
                ]
                self.message_log.add_message(random.choice(add_ambient_merchant_message), (150, 150, 150))
            
            # Return to the previous game state after trading
            self.game_state = self._previous_game_state  # Revert to the previous state
            return  # Exit the method after handling trade input
    
        # Handle other game states (Tavern or Dungeon)
        if self.game_state == GameState.TAVERN:
            # Handle Tavern-specific input here
            pass
        elif self.game_state == GameState.DUNGEON:
            # Handle Dungeon-specific input here
            pass
        

    def execute_targeted_ability(self):
        """
        Confirms the target for the ability currently in use and executes its effect.
        """
        if not self.ability_in_use:
            self.message_log.add_message("Error: No ability in use for targeting.", (255, 0, 0))
            self._reset_targeting_state()
            return

        target_x = self.targeting_cursor_x
        target_y = self.targeting_cursor_y

        # Check range
        distance = self.player.distance_to(target_x, target_y)
        if distance > self.targeting_ability_range:
            self.message_log.add_message(f"{self.ability_in_use.name} target is out of range ({int(distance)} tiles away, max {self.targeting_ability_range}).", (255, 150, 0))
            return # Stay in targeting mode

        if not self.check_line_of_sight(self.player.x, self.player.y, target_x, target_y):
            self.message_log.add_message(f"Cannot target {self.ability_in_use.name}: No clear line of sight.", (255, 150, 0))
            return # Stay in targeting mode

        # Pass the confirmed target coordinates to the ability's execute_on_target method
        # This method will contain the specific logic for each ability.
        if self.ability_in_use.execute_on_target(self.player, self, target_x, target_y):
            print("DEBUG: ability_in_use.execute_on_target returned True. Resetting state.") # <--- ADD THIS
            # If the ability successfully executed its effect, then reset state and end turn
            self._reset_targeting_state()
        else:
            print("DEBUG: ability_in_use.execute_on_target returned False. Staying in targeting mode.") # <--- ADD THIS
            # If execute_on_target returns False, it means the target was invalid for that ability
            # (e.g., Fire Bolt on empty tile, Misty Step on blocked tile). Stay in targeting mode.
            pass # Message already handled by ability.execute_on_target

    def _reset_targeting_state(self):
        """Cleans up targeting-related state vars and ends the player's turn."""
        self.game_state = self._previous_game_state # Revert to previous game state (DUNGEON/TAVERN)
        self.ability_in_use = None # Clear the ability reference
        self.targeting_ability_range = 0
        self.targeting_cursor_x = 0 # Reset cursor position
        self.targeting_cursor_y = 0
        self.player.current_action_state = None # <--- THIS IS THE CRITICAL FIX FOR MISTY STEP

        # This is the critical part: End the player's turn.
        self.player_has_acted = True
        self.next_turn()


    def check_line_of_sight(self, x1, y1, x2, y2):
        """
        Bresenham's Line Algorithm for checking direct line of sight.
        Returns True if there are no sight-blocking tiles between (x1, y1) and (x2, y2) (exclusive of start, inclusive of end).
        """
        # If start or end is blocked, no LOS (unless it's the target itself)
        if self.game_map.tiles[y1][x1].block_sight:
            return False

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        current_x, current_y = x1, y1

        while True:
            # If we've reached the target, LOS is clear
            if current_x == x2 and current_y == y2:
                return True

            # Check if the current tile (excluding the start) blocks sight
            if (current_x != x1 or current_y != y1) and self.game_map.tiles[current_y][current_x].block_sight:
                return False

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                current_x += sx
            if e2 < dx:
                err += dx
                current_y += sy
        return False



    def get_interactable_item_at(self, x, y):
        """Checks if there's an interactable item (like a Potion or Chest) at the given coordinates."""
        for item in self.game_map.items_on_ground:
            # Check for any Item (including Potion, Weapon, Armor, Tools)
            # Exclude Mimic if it's disguised, as it's handled separately by MimicTile
            if item.x == x and item.y == y and not (isinstance(item, Mimic) and item.disguised):
                return item
        return None

    def get_chest_at(self, x, y):
        """Checks if there's a chest at the given coordinates."""
        for item in self.game_map.items_on_ground:
            if isinstance(item, Chest) and item.x == x and item.y == y:
                return item
        return None

    def handle_item_pickup(self):
        """Check for items at player's position and pick them up."""
        items_at_player_pos = [item for item in self.game_map.items_on_ground if item.x == self.player.x and item.y == self.player.y]
        if items_at_player_pos:
            item_to_pick_up = items_at_player_pos[0]
            # Ensure it's not a Chest, as Chests are handled by their own 'open' method
            if isinstance(item_to_pick_up, Chest):
                return False # Let the chest opening logic handle this
            
            if item_to_pick_up.on_pickup(self.player, self):
                # Remove the item from the ground after successful pickup
                self.game_map.items_on_ground.remove(item_to_pick_up)
                self.update_fov() # Update FOV to reflect item removal
                return True
            else:
                return False
        else:
            # Removed "Nothing to pick up here." message here, as it will be handled by the broader interaction logic.
            return False
        

    def handle_inventory_input(self, key):
        """Handles input when in the inventory screen."""
        if pygame.K_1 <= key <= pygame.K_9:
            item_index = key - pygame.K_1
            if 0 <= item_index < len(self.player.inventory.items):
                self.selected_inventory_item = self.player.inventory.items[item_index]
                self.game_state = GameState.INVENTORY_MENU
                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
            else:
                self.message_log.add_message("No item at that slot.", (150, 150, 150))
        elif key == pygame.K_0:
            if len(self.player.inventory.items) == 10:
                self.selected_inventory_item = self.player.inventory.items[9]
                self.game_state = GameState.INVENTORY_MENU
                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
            else:
                self.message_log.add_message("No item at that slot.", (150, 150, 150))
        elif key == pygame.K_ESCAPE or key == pygame.K_c:
            self.selected_inventory_item = None
            self.game_state = GameState.INVENTORY
            self.message_log.add_message("Selection cancelled.", (150, 150, 150))

    def handle_inventory_menu_input(self, key):
        """Handles input when an item is selected in the inventory menu (pop-up)."""
        if not self.selected_inventory_item:
            self.game_state = GameState.INVENTORY
            return

        action_taken_in_menu = False
        if key == pygame.K_u:
            # Check if the selected item is the Campfire Kit
            if isinstance(self.selected_inventory_item, CampfireKit):
                # Call the use method for the Campfire Kit
                if self.selected_inventory_item.use(self.player, self):
                    action_taken_in_menu = True
                    # Close the inventory menu
                    self.selected_inventory_item = None  # Reset selected item
                    # Optionally, you can log a message here if needed                         
            else:
                # Use the item normally
                if self.player.use_item(self.selected_inventory_item, self):
                    action_taken_in_menu = True
                else:
                    self.message_log.add_message(f"Cannot use {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_e:
            if self.player.equip_item(self.selected_inventory_item, self):
                action_taken_in_menu = True
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_d:
            self.player.inventory.remove_item(self.selected_inventory_item)
            self.selected_inventory_item.x = self.player.x
            self.selected_inventory_item.y = self.player.y
            self.game_map.items_on_ground.append(self.selected_inventory_item)
            self.message_log.add_message(f"You drop the {self.selected_inventory_item.name}.", self.selected_inventory_item.color)
            action_taken_in_menu = True
        elif key == pygame.K_ESCAPE or key == pygame.K_c:
            self.message_log.add_message("Action cancelled.", (150, 150, 150))
            action_taken_in_menu = False

        self.selected_inventory_item = None
        self.game_state = GameState.INVENTORY
        if action_taken_in_menu:
            self.player_has_acted = True
            self.next_turn()

    def get_target_at(self, x, y):
        for entity in self.entities:
            if entity != self.player and entity.alive:
                if hasattr(entity, 'occupies_tile'):
                    if entity.occupies_tile(x, y):
                        return entity
                elif entity.x == x and entity.y == y:
                    return entity
        return None

    def get_adjacent_target(self):
        for dx, dy in [(0,1),(1,0),(0,-1),(-1,0),(-1,-1),(1,-1),(-1,1),(1,1)]:
            target = self.get_target_at(self.player.x + dx, self.player.y + dy)
            if target:
                return target
        return None

    def handle_player_action(self, dx, dy):
        new_x = self.player.x + dx
        new_y = self.player.y + dy

        if self.game_state == GameState.TAVERN:
            if (new_x, new_y) == self.door_position:
                self.message_log.add_message("You enter the dark dungeon...", (100, 255, 100))
                self.generate_level(1)
                return True

            for npc in self.npcs:
                if npc.x == new_x and npc.y == new_y and npc.alive:
                    self.message_log.add_message(f"You can't move onto {npc.name}.", (255, 150, 0))
                    return False
            if self.game_map.is_walkable(new_x, new_y):
                self.player.x = new_x
                self.player.y = new_y
                self.update_fov()
                self.camera.target_x = float(self.player.x)
                self.camera.target_y = float(self.player.y)                
                return True
            self.message_log.add_message("You can't move there.", (255, 150, 0))
            return False

        elif self.game_state == GameState.DUNGEON:
            # --- Step 1: Identify potential targets at the new position ---
            target_at_new_pos = self.get_target_at(new_x, new_y)
            
            # --- Step 2: Identify monsters adjacent to player *before* moving ---
            monsters_adjacent_before_move = []
            for entity in self.entities:
                # Ensure it's a monster, alive, and adjacent to the player
                if isinstance(entity, Monster) and entity.alive and self.player.is_adjacent_to(entity):
                    monsters_adjacent_before_move.append(entity)
            
            # --- Step 3: Handle interaction with an entity at the new position ---
            if target_at_new_pos:
                if isinstance(target_at_new_pos, Monster):
                    self.handle_player_attack(target_at_new_pos, self)  # Player attacks monster
                    return True  # Action taken
                elif isinstance(target_at_new_pos, DungeonHealer):
                    target_at_new_pos.offer_rest(self.player, self)
                    return True
                else:
                    self.message_log.add_message(f"You can't attack {target_at_new_pos.name}.", (255, 150, 0))
                    return False

            # --- Step 4: Handle movement to an empty, walkable tile or TRAP ---
            if self.game_map.is_walkable(new_x, new_y):
                # Prevent moving into any tile occupied by a blocking entity (supports multi-tile)
                for entity in self.entities:
                    if entity is self.player or not getattr(entity, 'alive', True) or not getattr(entity, 'blocks_movement', False):
                        continue
                    if hasattr(entity, 'occupies_tile'):
                        if entity.occupies_tile(new_x, new_y):
                            self.message_log.add_message(f"You can't move onto {entity.name}.", (255, 150, 0))
                            return False
                    else:
                        if getattr(entity, 'x', None) == new_x and getattr(entity, 'y', None) == new_y:
                            self.message_log.add_message(f"You can't move onto {entity.name}.", (255, 150, 0))
                            return False
                # --- NEW: Trap Check BEFORE Movement ---
                target_tile_obj = self.game_map.tiles[new_y][new_x]
                if isinstance(target_tile_obj, TrapTile) and target_tile_obj.trap_instance.is_hidden:
                    # Attempt passive perception check
                    passive_perception_score = 10 + self.player.get_ability_modifier(self.player.wisdom)
                    if "perception" in self.player.skill_proficiencies:
                        passive_perception_score += self.player.proficiency_bonus
                    
                    if passive_perception_score >= target_tile_obj.trap_instance.detection_dc:
                        target_tile_obj.trap_instance.reveal(self, new_x, new_y)
                        self.message_log.add_message(f"You notice a hidden {target_tile_obj.trap_instance.name}!", (0, 255, 255))
                        return True # Action taken (noticed trap)
                    else:
                        self.message_log.add_message(f"You fail to notice anything unusual.", (150, 150, 150))
                        # Fall through to movement logic below, which will trigger the trap.
               
                original_player_x, original_player_y = self.player.x, self.player.y
                self.player.x = new_x
                self.player.y = new_y
                
                self.camera.target_x = float(self.player.x)
                self.camera.target_y = float(self.player.y)
                # --- NEW: Trigger Trap AFTER Movement (if not noticed/disarmed) ---
                if isinstance(target_tile_obj, TrapTile) and not target_tile_obj.trap_instance.is_disarmed and not target_tile_obj.trap_instance.is_triggered:
                    target_tile_obj.trap_instance.trigger(self.player, self, new_x, new_y)
                    return True # Action taken (triggered trap)
                                
                # --- Opportunity Attack Check ---
                # Iterate through monsters that were adjacent before the move
                for monster in monsters_adjacent_before_move:
                    # Check if the monster is still adjacent to the player's *new* position
                    is_still_adjacent_to_monster = (abs(self.player.x - monster.x) <= 1 and abs(self.player.y - monster.y) <= 1)
                    
                    if self.player.alive and not is_still_adjacent_to_monster:
                        oa_msgs = [
                            f"The {monster.name} lashes out as you flee!",
                            f"{monster.name}'s reflexes are quick — an opportunity strike!",
                            f"A sudden slash from the {monster.name} catches you off guard!",
                            f"As you turn away, the {monster.name} seizes its chance to attack!",
                            f"The {monster.name} strikes swiftly at your exposed flank!"
                        ]
                        self.message_log.add_message(random.choice(oa_msgs), (255, 100, 0))
                        
                        monster.attack(self.player, self)  # Monster attacks the player
                        
                        # Important: If the player dies from an OA, the game state should reflect that.
                        if not self.player.alive:
                            self.handle_game_over()
                            return  # Player died, action taken, end turn.
                    
                
                self.update_fov()
                self.minimap_needs_redraw = True # Player moved, minimap needs redraw
                stairs_dir = self.check_stairs_interaction()
                if stairs_dir:
                    self.handle_level_transition(stairs_dir)
                return True  # Action taken

            # --- Step 5: Handle interaction with special tiles (MimicTile, Destructible) ---
            target_tile = self.game_map.tiles[new_y][new_x]
            if isinstance(target_tile, MimicTile):
                mimic_entity = target_tile.mimic_entity
                if mimic_entity.disguised:
                    mimic_entity.reveal(self)
                    return True
                else:
                    self.message_log.add_message(f"The {mimic_entity.name} is already revealed.", (150, 150, 150))
                    return False
            elif target_tile.destructible:
                self.destroy_tile(new_x, new_y)
                return True
            else:
                self.message_log.add_message("You can't move there.", (255, 150, 0))
                return False
        return False


    def destroy_tile(self, x, y):
        """
        Attempts to destroy a destructible tile at (x, y) with a skill check.
        """
        target_tile = self.game_map.tiles[y][x]
        if not target_tile.destructible:
            self.message_log.add_message("That cannot be destroyed.", (150, 150, 150))
            return False
        destruction_dc = 12 
        
        str_modifier = self.player.get_ability_modifier(self.player.strength)
        athletics_bonus = str_modifier + self.player.proficiency_bonus
        d20_roll = random.randint(1, 20)
        skill_check_total = d20_roll + athletics_bonus
        self.message_log.add_message(
            f"You attempt to smash the {target_tile.name} (DC {destruction_dc}): {d20_roll} + {athletics_bonus} = {skill_check_total}",
            (200, 200, 255)
        )
        
        if skill_check_total >= destruction_dc:
            self.message_log.add_message(f"You successfully smash the {target_tile.name}!", (0, 255, 0))
            self.game_map.tiles[y][x] = floor
            self.minimap_needs_redraw = True # Map changed, redraw minimap
            
            # --- NEW: 10% chance to drop a Lesser Healing Potion ---
            if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel 
                if random.random() < 0.70:
                    new_junk = wood_plank.__class__(
                        name=wood_plank.name,
                        char=wood_plank.char,
                        color=wood_plank.color,
                        description=wood_plank.description
                    )
                    new_junk.x = x
                    new_junk.y = y
                    self.game_map.items_on_ground.append(new_junk)
                    self.message_log.add_message(f"A {new_junk.name} drops from the {target_tile.name}!", new_junk.color)
                elif random.random() < 0.2:
                    new_food = meat.__class__(
                        name=meat.name,
                        char=meat.char,
                        color=meat.color,
                        description=meat.description,
                        healing_value=meat.healing_value,
                        price=meat.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.35:
                    new_food = green_apple.__class__(
                        name=green_apple.name,
                        char=green_apple.char,
                        color=green_apple.color,
                        description=green_apple.description,
                        healing_value=green_apple.healing_value,
                        price=green_apple.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.25:
                    new_food = fromage.__class__(
                        name=fromage.name,
                        char=fromage.char,
                        color=fromage.color,
                        description=fromage.description,
                        healing_value=fromage.healing_value,
                        price=fromage.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.3:
                    new_food = bread.__class__(
                        name=bread.name,
                        char=bread.char,
                        color=bread.color,
                        description=bread.description,
                        healing_value=bread.healing_value,
                        price=bread.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.4:
                    new_food = mushroom.__class__(
                        name=mushroom.name,
                        char=mushroom.char,
                        color=mushroom.color,
                        description=mushroom.description,
                        healing_value=mushroom.healing_value,
                        price=mushroom.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
            # --- END NEW DROP LOGIC ---

            return True
        else:
            self.message_log.add_message(f"You fail to smash the {target_tile.name}. It's tougher than it looks!", (255, 100, 100))
            return False

    

    def handle_player_attack(self, target, game_instance, advantage=False, disadvantage=False):
        if not target.alive:
            return
        
        # Check if ANY tile of the target is in the player's FOV (supports multi-tile entities)
        visible_ok = False
        allowed_vis = ['player', 'torch', 'darkvision']
        footprint_size = getattr(target, 'footprint_size', 1)
        if footprint_size > 1:
            for oy in range(footprint_size):
                for ox in range(footprint_size):
                    tx, ty = target.x + ox, target.y + oy
                    if self.fov.get_visibility_type(tx, ty) in allowed_vis:
                        visible_ok = True
                        break
                if visible_ok:
                    break
        else:
            visible_ok = self.fov.get_visibility_type(target.x, target.y) in allowed_vis

        if not visible_ok:
            self.message_log.add_message(f"You cannot attack {target.name} because it is out of sight!", (255, 0, 0))
            return
    
        # Determine the actual d20 roll based on advantage/disadvantage
        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20) # Always roll a second for simplicity
        
        final_d20_roll = roll1
        roll_message_part = f"a d20: [{roll1}]"
        
        if advantage and disadvantage: # They cancel each other out
            self.message_log.add_message("Advantage and Disadvantage cancel out.", (150, 150, 150))
            # final_d20_roll remains roll1
        elif advantage:
            final_d20_roll = max(roll1, roll2)
            roll_message_part = f"2d20 (Advantage): {roll1}, {roll2} -> {final_d20_roll}"
            self.message_log.add_message("You roll with Advantage!", (100, 255, 100))
        elif disadvantage:
            final_d20_roll = min(roll1, roll2)
            roll_message_part = f"2d20 (Disadvantage): {roll1}, {roll2} -> {final_d20_roll}"
            self.message_log.add_message("You roll with Disadvantage!", (255, 100, 100))
    
        # Use final_d20_roll for the attack calculation
        attack_modifier = self.player.attack_bonus
    
        # --- Check for PowerAttackBuff ---
        power_attack_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, PowerAttackBuff):
                power_attack_buff = effect
                break
            
        if power_attack_buff:
            attack_modifier += power_attack_buff.attack_modifier # Apply accuracy penalty
            self.message_log.add_message(f"Power Attack: -{abs(power_attack_buff.attack_modifier)} to hit.", (255, 165, 0))
    
        attack_roll_total = final_d20_roll + attack_modifier # Use final_d20_roll here
        self.message_log.add_message(
            f"You roll {roll_message_part} + [{attack_modifier}] (Attack Bonus) = {attack_roll_total} vs AC {target.armor_class}",
            (200, 200, 255)
        )
    
        # Critical hit/fumble based on the final_d20_roll
        is_critical_hit = (final_d20_roll == 20)
        is_critical_fumble = (final_d20_roll == 1)
    
        if is_critical_hit:
            self.message_log.add_message(
                "CRITICAL HIT! You strike a vital spot!",
                (255, 255, 0)
            )
            hit_successful = True
        elif is_critical_fumble:
            self.message_log.add_message(
                "CRITICAL FUMBLE! You trip over your own feet!",
                (255, 0, 0)
            )
            hit_successful = False
        elif attack_roll_total >= target.armor_class:
            hit_successful = True
        else:
            hit_successful = False
    
        if hit_successful:
            hit_messages = [
                f"Your attack {attack_roll_total} hits the {target.name} (AC {target.armor_class})!",
                f"You connect with the {target.name} (AC {target.armor_class})!",
                f"A solid blow lands on the {target.name} (AC {target.armor_class})!",
                f"The {target.name} recoils from your strike!"
            ]
            self.message_log.add_message(random.choice(hit_messages), (100, 255, 100))
    
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0), y_speed=0.4)
            self.floating_texts.append(hit_text)
    
    
            # Parse weapon damage dice (e.g., "1d6")
            dice_count_str, die_type_str = self.player.equipped_weapon.damage_dice.split('d')
            num_dice = int(dice_count_str)
            die_type = int(die_type_str)
    
            damage_rolls = []
            total_dice_rolled = num_dice
    
            if is_critical_hit:
                total_dice_rolled *= 2 # Double the number of dice rolled for critical hits
                self.message_log.add_message(f"Critical Hit! Rolling {total_dice_rolled}d{die_type} for damage!", (255, 255, 0))
    
            for _ in range(total_dice_rolled):
                damage_rolls.append(random.randint(1, die_type))
    
            damage_dice_rolls_sum = sum(damage_rolls)
    
            # Construct the message part for dice rolls
            damage_message_dice_part = f"{total_dice_rolled}d{die_type} ({' + '.join(map(str, damage_rolls))})"
    
            damage_modifier = self.player.attack_power
    
            if power_attack_buff:
                damage_modifier += power_attack_buff.damage_modifier # Apply damage bonus
                self.message_log.add_message(f"Power Attack: +{power_attack_buff.damage_modifier} damage.", (255, 165, 0))
                # The buff should be consumed after one attack
                self.player.active_status_effects.remove(power_attack_buff) # Remove the buff
                self.message_log.add_message(f"Power Attack buff consumed.", (150, 150, 150))
    
            damage_total = max(1, damage_dice_rolls_sum + damage_modifier)
    
            self.message_log.add_message(
                f"You roll {damage_message_dice_part} + [{damage_modifier}] (Attack Power) = {damage_total} damage!",
                (255, 200, 100)
            )
    
            damage_dealt = target.take_damage(damage_total, game_instance, damage_type='physical') 
    
            self.message_log.add_message(
                f"You hit the {target.name} for {damage_dealt} damage!",
                (255, 100, 100)
            )
    
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0), y_speed=0.6)
            self.floating_texts.append(damage_text)
    
    
            if not target.alive:
                xp_gained = target.die(game_instance)
                self.player.gain_xp(xp_gained, game_instance)  # Use 'self' (player) here
                self.message_log.add_message(f"You gain {xp_gained} XP!", (100, 255, 100))  # Log the XP gained
                if random.random() < 0.7:
                    self.add_ambient_combat_message()
            else:
                self.message_log.add_message(
                    f"{target.name} has {target.hp}/{target.max_hp} HP",
                    (255, 255, 0)
                )
        else:
            miss_messages = [
                f"Your attack {attack_roll_total} misses the {target.name} (AC {target.armor_class})!",
                f"You swing wildly and miss the {target.name} (AC {target.armor_class})!",
                f"The {target.name} deftly dodges your attack!",
                f"Your weapon glances harmlessly off the {target.name} (AC {target.armor_class})!"
            ]
            self.message_log.add_message(random.choice(miss_messages), (200, 200, 200))
    
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            self.floating_texts.append(miss_text)
    

    def add_ambient_combat_message(self):
        common_msgs = [
            "The smell of blood fills the air...",
            "Silence returns to the dungeon...",
            "Your weapon drips with monster blood...",
            "A death cry echoes, then fades into silence...",
            "The ground is slick with gore and ichor...",
            "Your heartbeat pounds in your ears, then slows...",
            "The dungeon grows eerily quiet, as if holding its breath...",
            "A faint metallic tang of blood lingers on your tongue...",
            "Your boots leave red stains across the stone floor...",
            "The corpse twitches once before lying still...",
            "Shadows seem to crowd closer after the violence...",
            "A rat scurries out, drawn to the fresh kill...",
            "The clash of steel still rings faintly in your mind...",
            "You wipe the blade clean, though the stain remains..."
        ]

        rare_msgs = [
            "Somewhere deeper, a guttural roar answers the bloodshed...",
            "The clash of battle carries far — something stirs in the dark...",
            "Your victory echoes like a beacon — but not all ears are friendly...",
            "A distant screech pierces the silence, hungry and aware...",
            "The dungeon shifts uneasily, as if the stone itself resents your triumph..."
        ]

        # 90% chance for common aftermath, 10% chance for rare narrative escalation
        if random.random() < 0.1:
            msg = random.choice(rare_msgs)
            color = (200, 100, 100)  # darker red for danger
        else:
            msg = random.choice(common_msgs)
            color = (170, 170, 170)  # neutral gray

        self.message_log.add_message(msg, color)


    def update(self, dt):
        self.clock.tick(60)  # Limit to 60 FPS
        self.fps = self.clock.get_fps()  # Get the current FPS

        self.floating_texts = [text for text in self.floating_texts if text.update()]

        # NEW: If player is dead and game is not yet in GAME_OVER state, handle game over
        if self.player and not self.player.alive and self.game_state != GameState.GAME_OVER:
            self.handle_game_over()
            return # Stop further updates if game over is triggered

        # NEW: If game is already in GAME_OVER state, simply return
        if self.game_state == GameState.GAME_OVER:
            if self.death_screen_animation_phase == 0:
                self.death_screen_alpha += self.death_screen_animation_speed
                if self.death_screen_alpha >= 255:
                    self.death_screen_alpha = 255
                    self.death_screen_animation_phase = 1
            elif self.death_screen_animation_phase == 1:
                self.death_screen_bg_alpha += self.death_screen_animation_speed
                if self.death_screen_bg_alpha >= 120:  # Max alpha for background overlay
                    self.death_screen_bg_alpha = 120
                    self.death_screen_animation_phase = 2
            elif self.death_screen_animation_phase == 2:
                self.death_screen_subtext_alpha += self.death_screen_animation_speed
                if self.death_screen_subtext_alpha >= 255:
                    self.death_screen_subtext_alpha = 255
                    self.death_screen_animation_phase = 3
            return

        # --- NEW: Only process turns for active monsters ---
        current = self.get_current_entity()
        if current and current != self.player and current.alive:
            if isinstance(current, Monster) and not current.is_active:
                # Skip this monster's turn if it's not active
                self.next_turn()
            else:
                current.take_turn(self.player, self.game_map, self)
                self.next_turn()
        

        if not self.player: # If player hasn't been created yet (e.g., in character creation)
            return # Do nothing else in update
        

        # --- NEW: Batch Monster Turn Processing ---
        if self.game_state == GameState.DUNGEON and self.player.alive:
            # Loop to process turns until it's the player's turn or no more entities
            while True:
                self.cleanup_entities() # Always clean up before getting current entity
                if not self.turn_order: # If no entities left (e.g., all monsters died)
                    break # Exit turn processing loop
                current_entity = self.get_current_entity()
                if current_entity == self.player:
                    # It's the player's turn.
                    if not self.player_has_acted:
                        # Player's turn, waiting for input. Break the loop.
                        break
                    else:
                        # Player has acted, advance turn to next entity.
                        self.player_has_acted = False # Reset for player's next turn
                        self.next_turn() # This will call cleanup_entities again and advance index
                        # After next_turn, it might be a monster's turn or player's again.
                        # Continue the while loop to process the next entity.
                        continue # Go back to the start of the while loop
                elif isinstance(current_entity, Monster) and current_entity.alive:
                    # Process monster's turn
                    if current_entity.is_active: # Only process if monster is active
                        current_entity.take_turn(self.player, self.game_map, self)
                    # Monster has acted (or skipped if inactive), advance turn.
                    self.next_turn() # This will call cleanup_entities again and advance index
                    # Continue the while loop to process the next entity.
                    continue # Go back to the start of the while loop
                else:
                    # If current_entity is not player, not a monster, or dead (should be caught by cleanup),
                    # just advance turn. This is a safeguard.
                    self.next_turn()
                    continue # Go back to the start of the while loop

        self.floating_texts = [text for text in self.floating_texts if text.update()]        
        
        # This condition was already here, but now it's after the player check
        if self.game_state == GameState.TAVERN or \
           self.game_state == GameState.INVENTORY or \
           self.game_state == GameState.INVENTORY_MENU or \
           self.game_state == GameState.CHARACTER_MENU or \
           self.game_state == GameState.TARGETING or \
           self.game_state == GameState.CHARACTER_CREATION or \
           self.game_state == GameState.CLASS_SELECTION: # Added CLASS_SELECTION
            return # <--- Keep this line as is
        
        current = self.get_current_entity()
        
        # --- NEW: Explicitly reset player_has_acted at the start of player's turn ---
        if current == self.player and self.player_has_acted:
            self.player_has_acted = False
            self.message_log.add_message("Your turn begins!", (100, 255, 100))
            self.update_fov()
        elif current == self.player and not self.player_has_acted:
            # Player's turn, waiting for input. Do nothing here.
            pass
        elif current and current != self.player and current.alive: # <--- THIS IS THE MONSTER'S TURN
            # Only allow entities within 10 tiles (Chebyshev distance) to act
            dist_x = abs(current.x - self.player.x)
            dist_y = abs(current.y - self.player.y)
            if max(dist_x, dist_y) <= 10:
                current.take_turn(self.player, self.game_map, self)
            # Even if it skipped acting, advance the turn to avoid stalling
            self.next_turn()
        else:
            pass # No active entity or entity is dead.


        # NEW: Only update camera and process turns if player exists and game is in an active state
        if self.player and (self.game_state == GameState.DUNGEON or self.game_state == GameState.TAVERN or self.game_state == GameState.TARGETING): # Include TARGETING
            # If in targeting mode for Mage Hand, camera should follow the cursor
            if self.game_state == GameState.TARGETING and self.ability_in_use and isinstance(self.ability_in_use, MageHand):
                self.camera.update(self.targeting_cursor_x, self.targeting_cursor_y, self.game_map.width, self.game_map.height)
            else:
                self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)        


    def handle_game_over(self):
        if not self._game_over_displayed:
            death_messages = [
                "Your journey ends here, adventurer. The dungeon claims another soul.",
                "The light fades from your eyes. Darkness embraces you.",
                "You fought bravely, but the dungeon proved too strong. Rest now.",
                "The dungeon's embrace is cold and final. You have fallen."
            ]
            chosen_death_message = random.choice(death_messages)
            self.message_log.add_message(chosen_death_message, (255, 0, 0))
            self._game_over_displayed = True
            self.player.die()

            # Reset animation variables for death screen
            self.death_screen_alpha = 0  # Alpha for "YOU DIED" text
            self.death_screen_bg_alpha = 0  # Alpha for background overlay
            self.death_screen_subtext_alpha = 0  # Alpha for subtext
            self.death_screen_animation_phase = 0  # 0=text fade-in, 1=bg fade-in, 2=subtext fade-in, 3=done

        self.game_state = GameState.GAME_OVER



    def handle_window_resize(self):
        old_scale = self.scale
        
        self.scale_x = self.screen.get_width() / INTERNAL_WIDTH
        self.scale_y = self.screen.get_height() / INTERNAL_HEIGHT
        self.scale = min(self.scale_x, self.scale_y)
        
        if abs(old_scale - self.scale) > 0.1:
            self.internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
            self.font = pygame.font.SysFont('consolas', int(INTERNAL_HEIGHT/50))

        self._recalculate_minimap_dimensions()            


    def add_dirty_rect(self, x, y, width, height):
        """Adds a rectangle to the list of dirty rects, converting world to screen coords."""
        # This needs to be carefully managed. For now, let's assume it's in pixel coordinates
        # relative to the internal_surface.
        # The actual screen blit will handle scaling.
        self.dirty_rects.append(pygame.Rect(x, y, width, height))


    def render(self):
        """Main render method - draws everything"""
        # Clear the entire screen at the start of each frame
        self.screen.fill((0, 0, 0, 0))

        # --- Render the main game area (dungeon/tavern) to internal_surface ---
        self.internal_surface.fill((0, 0, 0, 0)) # Clear internal surface

        # Render map, items, entities, highlights, floating texts to internal_surface
        if self.game_state == GameState.CHARACTER_CREATION:
            self.render_character_creation_screen()
            # For character creation, we draw directly to screen, so no internal_surface blit here
            # The screen.fill((0,0,0)) at the top handles clearing.
        elif self.game_state == GameState.CLASS_SELECTION:
            self.render_class_selection_screen()
            # Same as character creation
        elif self.game_state == GameState.INVENTORY:
            self.render_inventory_screen()
            # Inventory also draws to inventory_ui_surface, which is then blitted to screen
            self.screen.blit(self.inventory_ui_surface, (0, 0)) # Blit inventory UI directly
        elif self.game_state == GameState.INVENTORY_MENU:
            self.render_inventory_screen()
            self.screen.blit(self.inventory_ui_surface, (0, 0))
            self.render_inventory_menu_popup() # Popup draws directly to screen
        elif self.game_state == GameState.CHARACTER_MENU:
            self.render_character_menu()
            self.screen.blit(self.inventory_ui_surface, (0, 0))
        else: # This block handles DUNGEON, TAVERN, and TARGETING (and will be drawn under GAME_OVER)
            # --- Camera Update Logic ---
            if self.game_state == GameState.TARGETING:
                self.camera.update(self.targeting_cursor_x, self.targeting_cursor_y, self.game_map.width, self.game_map.height)
            else:
                self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)

            self.render_map_with_fov()
            self.render_items_on_ground()
            self.render_tile_highlights()
            self.render_entities()

            for text_obj in self.floating_texts:
                text_obj.draw(self.internal_surface, self.camera)

            if self.game_state == GameState.TARGETING:
                screen_x, screen_y = self.camera.world_to_screen(
                    self.targeting_cursor_x,
                    self.targeting_cursor_y
                )
                target_type = None
                target_entity = self.get_target_at(self.targeting_cursor_x, self.targeting_cursor_y)
                if isinstance(target_entity, Monster):
                    target_type = "monster"
                elif (tile := self.game_map.tiles[self.targeting_cursor_y][self.targeting_cursor_x]) and tile.destructible:
                    target_type = "destructible"

                cursor_color = (
                    (255, 100, 100) if target_type == "monster" else
                    (255, 200, 100) if target_type == "destructible" else
                    (100, 100, 255)
                )

                if isinstance(self.ability_in_use, MageHand):
                    graphics.draw_tile(self.internal_surface, screen_x * config.TILE_SIZE, screen_y * config.TILE_SIZE, 'mh', color_tint=(150, 200, 255))
                else:
                    cursor_width = 3
                    pygame.draw.rect(
                        self.internal_surface,
                        cursor_color,
                        (screen_x * config.TILE_SIZE,
                         screen_y * config.TILE_SIZE,
                         config.TILE_SIZE,
                         config.TILE_SIZE),
                        cursor_width
                    )

            # Scale and blit the internal game area surface to the main screen
            available_width = config.GAME_AREA_WIDTH
            available_height = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT

            scale_to_fit_width = available_width / config.INTERNAL_GAME_AREA_PIXEL_WIDTH
            scale_to_fit_height = available_height / config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
            actual_display_scale = min(scale_to_fit_width, scale_to_fit_height)

            scaled_width = int(config.INTERNAL_GAME_AREA_PIXEL_WIDTH * actual_display_scale)
            scaled_height = int(config.INTERNAL_GAME_AREA_PIXEL_HEIGHT * actual_display_scale)

            offset_x = (available_width - scaled_width) // 2
            offset_y = (available_height - scaled_height) // 2

            target_rect = pygame.Rect(offset_x, offset_y, scaled_width, scaled_height)
            scaled_game_area = pygame.transform.scale(self.internal_surface, target_rect.size)
            self.screen.blit(scaled_game_area, target_rect.topleft)


        # --- Always draw UI, Minimap, and Message Log directly to the screen ---
        # This ensures they are always fully redrawn and prevents flickering.
        if self.player: # Only draw UI if player exists (after character creation)
            self.draw_ui() # This method now draws directly to self.screen
            # Draw minimap if in dungeon or tavern state
            if self.game_state in [GameState.DUNGEON, GameState.TAVERN]:
                self.draw_minimap() # This method now draws directly to self.screen

        # Message log is also drawn directly to screen
        if self.game_state not in [GameState.CHARACTER_CREATION, GameState.CLASS_SELECTION]:
            self.message_log.render(self.screen)

        # NEW: Render game over screen if in GAME_OVER state
        if self.game_state == GameState.GAME_OVER:
            self.render_game_over_screen()
            pygame.display.flip() # Ensure the screen updates
            return # Exit render function early to prevent further drawing

        fps_text = f"FPS: {int(self.fps)}"
        fps_surface = self.fps_font.render(fps_text, True, (255, 255, 255))  # White color
        self.screen.blit(fps_surface, (10, 10))  # Position at (10, 10) pixels from top-left

        # --- Final Display Update ---
        # Use flip for full screen update, or update a combined rect for game area + UI panel
        # For simplicity and to eliminate flickering, let's try flip first.
        pygame.display.flip()

        # Remove the old dirty_rects logic as it's no longer needed with flip()
        # self.dirty_rects = [] # This line can be removed or commented out
        # ... (remove all subsequent dirty_rects related code in render) ...

    def render_game_over_screen(self):
        # Render background overlay with fade-in alpha AFTER "YOU DIED" text
        if self.death_screen_animation_phase >= 1:
            overlay_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            overlay_surface.fill((0, 0, 0, self.death_screen_bg_alpha))
            self.screen.blit(overlay_surface, (0, 0))

        # Render "YOU DIED" text with fade-in alpha
        font = pygame.font.SysFont('consolas', 72, bold=True)
        text_surface = font.render("YOU DIED", True, (255, 0, 0))
        text_surface.set_alpha(self.death_screen_alpha)
        text_rect = text_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2))
        self.screen.blit(text_surface, text_rect)

        # Render subtext with fade-in alpha after background is visible
        if self.death_screen_animation_phase >= 2:
            font_small = pygame.font.SysFont('consolas', 24)
            subtext = font_small.render("Press R to Restart or Q to Quit", True, (255, 255, 255))
            subtext.set_alpha(self.death_screen_subtext_alpha)
            subtext_rect = subtext.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 60))
            self.screen.blit(subtext, subtext_rect)
            

    def render_map_with_fov(self, full_redraw=False):
        if not hasattr(self, 'game_map') or self.game_map is None:
            # No map to render yet, just return
            return
        
        camera_x_int = int(self.camera.x)
        camera_y_int = int(self.camera.y)

        for y in range(camera_y_int, min(camera_y_int + self.camera.viewport_height + 1, self.game_map.height)):
            for x in range(camera_x_int, min(camera_x_int + self.camera.viewport_width + 1, self.game_map.width)):

                screen_x_float, screen_y_float = self.camera.world_to_screen(x, y)

                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE

                visibility_type = self.fov.get_visibility_type(x, y)

                # Draw the tile based on visibility
                tile = self.game_map.tiles[y][x]

                
                # Draw the tile normally if explored or visible
                render_color_tint = None  # Initialize render_color_tint
                if visibility_type == 'player':
                    render_color_tint = None
                elif visibility_type == 'torch':
                    render_color_tint = (128, 128, 128, 255)
                elif visibility_type == 'darkvision':
                    render_color_tint = (120, 120, 120, 255)
                elif visibility_type == 'explored':
                    render_color_tint = (80 ,80, 80, 255)
                elif visibility_type == 'unexplored':
                    render_color_tint = (20, 20, 20, 255)

                graphics.draw_tile(self.internal_surface, draw_x, draw_y, tile.char, color_tint=render_color_tint)

                # Handle TrapTile display
                if isinstance(tile, TrapTile):
                    display_char = tile.get_display_char()
                    display_color = tile.get_display_color()
                    # Draw the base tile (floor, wall, or trap's hidden/revealed char)
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, display_char, color_tint=render_color_tint) 

                if full_redraw: # Only add to dirty rects if it's a full redraw or a specific tile changed
                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)   

                tile_rect = pygame.Rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)
                self.dirty_rects.append(tile_rect)                                                            


    def render_tile_highlights(self):
        # Draw per-entity telegraphs every frame to avoid stale global state
        for entity in self.entities:
            tiles = getattr(entity, 'pending_telegraph_tiles', None)          
            if not tiles:
                continue
            color = getattr(entity, 'telegraph_color', (255, 0, 0, 100))
            for hx, hy in tiles:
                if not (0 <= hx < self.game_map.width and 0 <= hy < self.game_map.height):
                    continue
                vis = self.fov.get_visibility_type(hx, hy)
                if vis not in ['player', 'torch', 'darkvision', 'explored']:
                    continue
                sx, sy = self.camera.world_to_screen(hx, hy)
                px = sx * config.TILE_SIZE
                py = sy * config.TILE_SIZE
                r, g, b, a = color
                overlay = pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA)
                overlay.fill((r, g, b, a))
                self.internal_surface.blit(overlay, (px, py))


    def render_entities(self, full_redraw=False):
        if not hasattr(self, 'game_map') or self.game_map is None:
            return        
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        for entity in self.entities:
            if isinstance(entity, Mimic) and entity.disguised:
                continue 
            visibility_type = self.fov.get_visibility_type(entity.x, entity.y)

            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y) and \
               (visibility_type == 'player' or visibility_type == 'torch' or visibility_type == 'explored' or visibility_type == 'darkvision'):

                screen_x_float, screen_y_float = self.camera.world_to_screen(entity.x, entity.y)
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE

                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= draw_y < map_render_height):

                    # Initialize entity_color_tint here
                    entity_color_tint = None
                    if visibility_type == 'player':
                        entity_color_tint = None
                    elif visibility_type == 'torch':
                        entity_color_tint = (128, 128, 128, 255)
                    elif visibility_type == 'darkvision':
                        entity_color_tint = (90, 90, 90, 255)
                    elif visibility_type == 'explored':
                        entity_color_tint = (60, 60, 60, 255)

                    footprint_size = getattr(entity, 'footprint_size', 1)
                    tile_size_override = config.TILE_SIZE * footprint_size if footprint_size > 1 else None

                    # Determine flip_x only for player
                    flip_x = False
                    if entity == self.player:
                        flip_x = not self.player.facing_right  # Flip if facing left

                    graphics.draw_tile(
                        self.internal_surface,
                        draw_x,
                        draw_y,
                        entity.char,
                        color_tint=entity_color_tint,
                        tile_size=tile_size_override,
                        flip_x=flip_x
                    )

                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)
                else:
                    pass
            else:
                pass



    def render_items_on_ground(self, full_redraw=False):
        """Render items lying on the dungeon floor."""
        if not hasattr(self, 'game_map') or self.game_map is None:
            return             
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for item in self.game_map.items_on_ground:
            if isinstance(item, Mimic) and item.disguised:
                continue 
            
            visibility_type = self.fov.get_visibility_type(item.x, item.y)
            
            if self.camera.is_in_viewport(item.x, item.y) and \
               (visibility_type == 'player' or visibility_type == 'torch' or visibility_type == 'explored' or visibility_type == 'darkvision'):
                
                # --- MODIFIED: Get float screen coordinates ---
                screen_x_float, screen_y_float = self.camera.world_to_screen(item.x, item.y)
                
                # --- MODIFIED: Calculate pixel draw positions using floats ---
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE
                
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= draw_y < map_render_height):
                    
                    item_color_tint = None
                    if visibility_type == 'player':
                        item_color_tint = None
                    elif visibility_type == 'torch':
                        item_color_tint = (128, 128, 128, 255)
                    elif visibility_type == 'darkvision':
                        item_color_tint = (90, 90, 90, 255)
                    elif visibility_type == 'explored':
                        item_color_tint = (60, 60, 60, 255)
                    
                    # Always draw floor under items, as map rendering might have drawn a decorative tile
                    # --- MODIFIED: Pass float draw_x, draw_y to graphics.draw_tile ---
                    # graphics.draw_tile(self.internal_surface, draw_x, draw_y, floor.char, color_tint=item_color_tint)
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, item.char, color_tint=item_color_tint)


                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)                    

   
    def render_character_creation_screen(self):
        # Use the main screen surface for drawing
        target_surface = self.screen  # Change to self.screen to cover the entire window
        target_surface.fill((0, 0, 0, 200))  # Fill with a semi-transparent black to create a modal effect

        # Draw a background box for the menu
        menu_width = int(target_surface.get_width() * 0.9)  # Make it wider to accommodate two columns
        menu_height = int(target_surface.get_height() * 0.8)
        menu_x = (target_surface.get_width() - menu_width) // 2
        menu_y = (target_surface.get_height() - menu_height) // 2
        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(target_surface, (30, 30, 30), menu_rect)
        pygame.draw.rect(target_surface, (100, 100, 100), menu_rect, 2)

        title_text = "CHOOSE YOUR RACE"
        title_surface = self.inventory_font_header.render(title_text, True, (255, 215, 0))
        title_rect = title_surface.get_rect(center=(menu_rect.centerx, menu_y + self.inventory_font_header.get_linesize() // 2 + 10))
        target_surface.blit(title_surface, title_rect)

        # Define column positions
        left_column_x = menu_x + 20
        right_column_x = menu_x + menu_width // 2 + 20  # Start right column after half width + padding
        column_width = menu_width // 2 - 40  # Adjust for padding on both sides

        current_y_left = title_rect.bottom + 30
        line_spacing = self.inventory_font_info.get_linesize() + 8

        # Left Column: Race Choices
        self._draw_text(target_surface, self.inventory_font_section, "Races:", (255, 255, 0), left_column_x, current_y_left)
        current_y_left += self.inventory_font_section.get_linesize() + 10

        for i, race in enumerate(self.available_races):
            race_text = f"{i + 1}. {race.name}"
            color = (255, 255, 0) if i == self.selected_race_index else (200, 200, 200)
            self._draw_text(target_surface, self.inventory_font_section, race_text, color, left_column_x, current_y_left)
            current_y_left += line_spacing

        # Right Column: Race Information
        current_y_right = title_rect.bottom + 30
        selected_race = self.available_races[self.selected_race_index]

        self._draw_text(target_surface, self.inventory_font_section, f"{selected_race.name} Details:", (255, 215, 0), right_column_x, current_y_right)
        current_y_right += self.inventory_font_section.get_linesize() + 10

        # Description
        current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, selected_race.description, (150, 150, 150), right_column_x, current_y_right, column_width)
        current_y_right += 10

        # Traits
        self._draw_text(target_surface, self.inventory_font_info, "Traits:", (200, 200, 255), right_column_x, current_y_right)
        current_y_right += self.inventory_font_info.get_linesize() + 5

        if selected_race.darkvision_radius > 0:
            self._draw_text(target_surface, self.inventory_font_small, f"- Darkvision: {selected_race.darkvision_radius} tiles.", (255, 255, 255), right_column_x + 10, current_y_right)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        if selected_race.damage_resistances:
            self._draw_text(target_surface, self.inventory_font_small, f"- Damage Resistances: {', '.join(selected_race.damage_resistances)}", (255, 255, 255), right_column_x + 10, current_y_right)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        if selected_race.skill_proficiencies:
            # Use the wrapped text method for skill proficiencies
            current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Skill Proficiencies: {', '.join(selected_race.skill_proficiencies)}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        if selected_race.weapon_proficiencies:
            # Use the wrapped text method for weapon proficiencies
            current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Weapon Proficiencies: {', '.join(selected_race.weapon_proficiencies)}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        if selected_race.armor_proficiencies:
            self._draw_text(target_surface, self.inventory_font_small, f"- Armor Proficiencies: {', '.join(selected_race.armor_proficiencies)}", (255, 255, 255), right_column_x + 10, current_y_right)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        # Instructions (at the bottom, centered)
        instructions_y = menu_rect.bottom - (self.inventory_font_small.get_linesize() * 2) - 20
        self._draw_text(target_surface, self.inventory_font_small, "Use UP/DOWN arrows to select.", (150, 150, 150), menu_rect.centerx - self.inventory_font_small.size("Use UP/DOWN arrows to select.")[0] // 2, instructions_y)
        self._draw_text(target_surface, self.inventory_font_small, "Press ENTER to confirm.", (150, 150, 150), menu_rect.centerx - self.inventory_font_small.size("Press ENTER to confirm.")[0] // 2, instructions_y + self.inventory_font_small.get_linesize() + 5)

    def _draw_wrapped_and_update_y_menu(self, surface, font, text, color, x, y_start, max_width):
        """Wraps text and draws it on the surface, updating the y position."""
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:  # Check if the line fits within the max width
                current_line.append(word)
            else:
                if current_line:  # If there's a current line, add it to lines
                    lines.append(' '.join(current_line))
                current_line = [word]  # Start a new line with the current word

        if current_line:  # Add the last line if it exists
            lines.append(' '.join(current_line))

        # Draw each line and update the y position
        y_offset = y_start
        for line in lines:
            self._draw_text(surface, font, line, color, x, y_offset)
            y_offset += font.get_linesize() + 2  # Add some spacing between lines

        return y_offset  # Return the new y position


    def render_class_selection_screen(self):
        # Use the main screen surface for drawing
        target_surface = self.screen  # Change to self.screen to cover the entire window
        target_surface.fill((0, 0, 0, 200))  # Fill with a semi-transparent black to create a modal effect

        # Draw a background box for the menu
        menu_width = int(target_surface.get_width() * 0.9)  # Make it wider
        menu_height = int(target_surface.get_height() * 0.8)
        menu_x = (target_surface.get_width() - menu_width) // 2
        menu_y = (target_surface.get_height() - menu_height) // 2
        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(target_surface, (30, 30, 30), menu_rect)
        pygame.draw.rect(target_surface, (100, 100, 100), menu_rect, 2)

        title_text = "CHOOSE YOUR CLASS"
        title_surface = self.inventory_font_header.render(title_text, True, (255, 215, 0))
        title_rect = title_surface.get_rect(center=(menu_rect.centerx, menu_y + self.inventory_font_header.get_linesize() // 2 + 10))
        target_surface.blit(title_surface, title_rect)

        # Define column positions
        left_column_x = menu_x + 20
        right_column_x = menu_x + menu_width // 2 + 20
        column_width = menu_width // 2 - 40

        current_y_left = title_rect.bottom + 30
        line_spacing = self.inventory_font_info.get_linesize() + 8

        # Left Column: Class Choices
        self._draw_text(target_surface, self.inventory_font_section, "Classes:", (255, 255, 0), left_column_x, current_y_left)
        current_y_left += self.inventory_font_section.get_linesize() + 10

        for i, class_constructor in enumerate(self.available_classes):
            class_name = class_constructor.__name__  # Get the class name string
            class_text = f"{i + 1}. {class_name}"
            color = (255, 255, 0) if i == self.selected_class_index else (200, 200, 200)
            self._draw_text(target_surface, self.inventory_font_section, class_text, color, left_column_x, current_y_left)
            current_y_left += line_spacing

        # Right Column: Class Information
        current_y_right = title_rect.bottom + 30
        selected_class_constructor = self.available_classes[self.selected_class_index]
        selected_class_name = selected_class_constructor.__name__

        self._draw_text(target_surface, self.inventory_font_section, f"{selected_class_name} Details:", (255, 215, 0), right_column_x, current_y_right)
        current_y_right += self.inventory_font_section.get_linesize() + 10

        # Get class-specific description and traits
        class_info = self._get_class_details(selected_class_constructor)

        # Description
        current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, class_info["description"], (150, 150, 150), right_column_x, current_y_right, column_width)
        current_y_right += 10

        # Key Features
        self._draw_text(target_surface, self.inventory_font_info, "Key Features:", (200, 200, 255), right_column_x, current_y_right)
        current_y_right += self.inventory_font_info.get_linesize() + 5

        # Hit Die
        current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Hit Die: {class_info['hit_die']}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
        current_y_right += self.inventory_font_small.get_linesize() + 2

        # Primary Ability
        current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Primary Ability: {class_info['primary_ability']}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
        current_y_right += self.inventory_font_small.get_linesize() + 2

        # Saving Throw Proficiencies
        if class_info['saving_throws']:
            current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Saving Throws: {', '.join(class_info['saving_throws'])}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        # Armor Proficiencies
        if class_info['armor_proficiencies']:
            current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Armor Proficiencies: {', '.join(class_info['armor_proficiencies'])}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        # Weapon Proficiencies
        if class_info['weapon_proficiencies']:
            current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Weapon Proficiencies: {', '.join(class_info['weapon_proficiencies'])}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        # Starting Equipment
        if class_info['starting_equipment']:
            current_y_right = self._draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_small, f"- Starting Equipment: {', '.join(class_info['starting_equipment'])}", (255, 255, 255), right_column_x + 10, current_y_right, column_width)
            current_y_right += self.inventory_font_small.get_linesize() + 2

        # Instructions (at the bottom, centered)
        instructions_y = menu_rect.bottom - (self.inventory_font_small.get_linesize() * 2) - 20
        self._draw_text(target_surface, self.inventory_font_small, "Use UP/DOWN arrows to select.", (150, 150, 150), menu_rect.centerx - self.inventory_font_small.size("Use UP/DOWN arrows to select.")[0] // 2, instructions_y)
        self._draw_text(target_surface, self.inventory_font_small, "Press ENTER to confirm.", (150, 150, 150), menu_rect.centerx - self.inventory_font_small.size("Press ENTER to confirm.")[0] // 2, instructions_y + self.inventory_font_small.get_linesize() + 5)


    def _get_class_details(self, class_constructor):
        """
        Returns a dictionary of details for a given class constructor.
        You will need to expand this with actual data for each class.
        """
        # Create a dummy instance to access class attributes
        dummy_instance = class_constructor(0, 0, '@', 'Dummy', (255, 255, 255))

        # Get the class name from the constructor
        selected_class_name = dummy_instance.class_name  # Assuming class_name is set in the class constructor

        details = {
            "Fighter": {
                "description": "A master of martial combat, skilled with a variety of weapons and armor. Fighters are versatile warriors who can specialize in offense or defense.",
                "hit_die": "1d10",
                "primary_ability": "Strength or Dexterity",
                "saving_throws": ["Strength", "Constitution"],
                "armor_proficiencies": ["Light", "Medium", "Heavy", "Shields"],
                "weapon_proficiencies": ["Simple", "Martial"],
                "starting_equipment": ["Chain mail", "A martial weapon and a shield", "A light crossbow and 20 bolts", "An explorer's pack"]
            },
            "Rogue": {
                "description": "A master of stealth, cunning, and trickery. Rogues excel at striking from the shadows and disarming traps.",
                "hit_die": "1d8",
                "primary_ability": "Dexterity",
                "saving_throws": ["Dexterity", "Intelligence"],
                "armor_proficiencies": ["Light"],
                "weapon_proficiencies": ["Simple", "Hand crossbows", "Longswords", "Rapiers", "Shortswords"],
                "starting_equipment": ["A rapier", "A shortbow and quiver of 20 arrows", "A burglar's pack", "Leather armor", "Two daggers", "Thieves' tools"]
            },
            "Wizard": {
                "description": "A scholarly magic-user capable of manipulating the fabric of reality. Wizards wield powerful spells learned from ancient tomes.",
                "hit_die": "1d6",
                "primary_ability": "Intelligence",
                "saving_throws": ["Intelligence", "Wisdom"],
                "armor_proficiencies": ["None"],
                "weapon_proficiencies": ["Daggers", "Darts", "Slings", "Quarterstaffs", "Light crossbows"],
                "starting_equipment": ["A quarterstaff", "A component pouch", "A scholar's pack", "A spellbook"]
            }
        }
        # Return specific details for the class, or a generic message if not found
        return details.get(selected_class_name, {
            "description": "No detailed description available for this class.",
            "hit_die": "N/A",
            "primary_ability": "N/A",
            "saving_throws": [],
            "armor_proficiencies": [],
            "weapon_proficiencies": [],
            "starting_equipment": []
        })
    

    def render_inventory_screen(self):
        """Renders the inventory screen with a two-column layout."""
        target_surface = self.inventory_ui_surface
        target_surface.fill((0, 0, 0, 0))  # Clear the surface

        # Define column widths
        left_column_width = target_surface.get_width() * 0.65  # 70% for inventory
        right_column_width = target_surface.get_width() * 0.32  # 30% for character info

        # Draw left column for inventory items
        left_column_rect = pygame.Rect(10, 10, left_column_width, target_surface.get_height() - 20)
        pygame.draw.rect(target_surface, (30, 30, 30), left_column_rect)
        pygame.draw.rect(target_surface, (100, 100, 100), left_column_rect, 2)

        # Draw right column for character info and equipped items
        right_column_rect = pygame.Rect(left_column_width + 20, 10, right_column_width, target_surface.get_height() - 20)
        pygame.draw.rect(target_surface, (30, 30, 30), right_column_rect)
        pygame.draw.rect(target_surface, (100, 100, 100), right_column_rect, 2)

        # Draw inventory items in the left column
        current_y = 20
        for i, item in enumerate(self.player.inventory.items):
            # Highlight the selected item
            if i == self.selected_inventory_index:
                item_color = (255, 255, 0)  # Yellow for selected item
                item_text = f"> {item.name} <"  # Add arrows to indicate selection
            else:
                item_color = (255, 255, 255)  # Default color for unselected items
                item_text = item.name  # Normal item name
            self._draw_text(target_surface, self.font_info, item_text, item_color, 20, current_y)
            current_y += self.font_info.get_linesize() + 5

        # Draw character graphic in the right column
        character_graphic = self.player.char  # Assuming this is the character's graphic representation
        character_surface = self.font_header.render(character_graphic, True, (255, 215, 0))  # Render character graphic
        target_surface.blit(character_surface, (left_column_width + 30, 20))  # Position it in the right column

        # Display equipped items as graphics
        equipped_weapon, equipped_armor, equipped_off_hand = self.player.get_equipped_items()
        weapon_name = equipped_weapon.name if equipped_weapon else "None"
        armor_name = equipped_armor.name if equipped_armor else "None"
        off_hand_name = equipped_off_hand.name if equipped_off_hand else "None"


        self._draw_text(target_surface, self.font_info, f"Name: {self.player.name}", (255, 255, 255), left_column_width + 30, 100)
        self._draw_text(target_surface, self.font_info, f"Gold: {self.player.gold}", (255, 255, 255), left_column_width + 30, 120)
        self._draw_text(target_surface, self.font_info, f"AC: {self.player.armor_class}", (255, 255, 255), left_column_width + 30, 160)
        self._draw_text(target_surface, self.font_info, f"Proficiency Bonus: +{self.player.proficiency_bonus}", (255, 255, 255), left_column_width + 30, 180)
        self._draw_text(target_surface, self.font_info, f"Attack Power: +{self.player.attack_power}", (255, 255, 255), left_column_width + 30, 200)
        self._draw_text(target_surface, self.font_info, f"Attack Bonus: +{self.player.attack_bonus}", (255, 255, 255), left_column_width + 30, 220)


        # Draw equipped weapon icon
        self._draw_text(target_surface, self.font_info, f"Equipped Weapon: {weapon_name}", (255, 255, 255), left_column_width + 30, 260)
        # Draw equipped armor icon
        self._draw_text(target_surface, self.font_info, f"Equipped Armor: {armor_name}", (255, 255, 255), left_column_width + 30, 280)
        # Draw equipped off-hand icon
        self._draw_text(target_surface, self.font_info, f"Equipped Off-Hand: {off_hand_name}", (255, 255, 255), left_column_width + 30, 300)
            



    def render_inventory_menu_popup(self):
        """Renders a small pop-up menu for selected inventory item actions."""
        if not self.selected_inventory_item:
            return
        popup_width = 200
        popup_height = 150

        popup_x = (self.inventory_ui_surface.get_width() - popup_width) // 2
        popup_y = (self.inventory_ui_surface.get_height() - popup_height) // 2

        popup_rect = pygame.Rect(popup_x, popup_y, popup_width, popup_height)

        popup_surface = pygame.Surface((popup_width, popup_height), pygame.SRCALPHA)
        popup_surface.fill((0, 0, 0, 200))
        pygame.draw.rect(popup_surface, (100, 100, 100), popup_surface.get_rect(), 2)
        item_name_surface = self.inventory_font_section.render(self.selected_inventory_item.name, True, self.selected_inventory_item.color)
        item_name_rect = item_name_surface.get_rect(centerx=popup_width // 2, y=10)
        popup_surface.blit(item_name_surface, item_name_rect)

        options = [
            ("U: Use", pygame.K_u),  # Ensure the Campfire Kit has a use option
            ("E: Equip", pygame.K_e),
            ("D: Drop", pygame.K_d),
            ("C: Cancel", pygame.K_c)
        ]

        current_y = item_name_rect.bottom + 15
        for text, key_code in options:
            color = (255, 255, 255)  # Default color for options
            if isinstance(self.selected_inventory_item, CampfireKit) and text == "U: Use":
                color = (100, 255, 100)  # Highlight the use option for Campfire Kit
            option_surface = self.inventory_font_info.render(text, True, color)
            option_rect = option_surface.get_rect(centerx=popup_width // 2, y=current_y)
            popup_surface.blit(option_surface, option_rect)
            current_y += self.inventory_font_info.get_linesize() + 5

        self.screen.blit(popup_surface, popup_rect.topleft)


    def render_character_menu(self):
        """Renders the character details screen with a two-column layout."""
        target_surface = self.inventory_ui_surface
        target_surface.fill((0,0,0,0))

        char_menu_width_ratio = 0.8
        char_menu_height_ratio = 0.9
        char_menu_rect_width = int(target_surface.get_width() * char_menu_width_ratio)
        char_menu_rect_height = int(target_surface.get_height() * char_menu_height_ratio)
        
        char_menu_x = (target_surface.get_width() - char_menu_rect_width) // 2
        char_menu_y = (target_surface.get_height() - char_menu_rect_height) // 2
        
        char_menu_rect = pygame.Rect(char_menu_x, char_menu_y, char_menu_rect_width, char_menu_rect_height)
        pygame.draw.rect(target_surface, (30, 30, 30), char_menu_rect)
        pygame.draw.rect(target_surface, (100, 100, 100), char_menu_rect, 2)

        title_text = "CHARACTER SHEET"
        title_surface = self.inventory_font_header.render(title_text, True, (255, 215, 0))
        title_rect = title_surface.get_rect(center=(char_menu_rect.centerx, char_menu_y + self.inventory_font_header.get_linesize() // 2 + 10))
        target_surface.blit(title_surface, title_rect)

        left_column_x = char_menu_x + 20
        right_column_x = char_menu_x + char_menu_rect_width // 2 + 10
        column_width = char_menu_rect_width // 2 - 30

        current_y_left = char_menu_y + self.inventory_font_header.get_linesize() + 50
        current_y_right = char_menu_y + self.inventory_font_header.get_linesize() + 50

        def format_ability_and_save(name, score, modifier, save_bonus, save_proficient):
            mod_str = f"+{modifier}" if modifier >= 0 else str(modifier)
            save_bonus_str = f"+{save_bonus}" if save_bonus >= 0 else str(save_bonus)
            prof_char = "*" if save_proficient else ""
            return f"{name}: {score} ({mod_str}) | Save: {save_bonus_str}{prof_char}"

        def draw_wrapped_and_update_y_menu(surface, font, text, color, x, y_start, max_width):
            wrapped_lines = self._wrap_text(text, font, max_width)
            y_offset = y_start
            for line in wrapped_lines:
                self._draw_text(surface, font, line, color, x, y_offset)
                y_offset += font.get_linesize() + 2
            return y_offset

        self._draw_text(target_surface, self.inventory_font_section, "BASIC INFO", (255, 215, 0), left_column_x, current_y_left)
        current_y_left += self.inventory_font_section.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"Name: {self.player.name}", (255, 255, 255), left_column_x, current_y_left)
        current_y_left += self.inventory_font_info.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"Gold: {self.player.gold}", (255, 255, 255), left_column_x, current_y_left)
        current_y_left += self.inventory_font_info.get_linesize() + 5        
        self._draw_text(target_surface, self.inventory_font_info, f"Level: {self.player.level}", (255, 255, 255), left_column_x, current_y_left)
        current_y_left += self.inventory_font_info.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"XP: {self.player.current_xp}/{self.player.xp_to_next_level}", (255, 255, 255), left_column_x, current_y_left)
        current_y_left += self.inventory_font_info.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"Class: {self.player.class_name}", (255, 255, 255), left_column_x, current_y_left)
        current_y_left += self.inventory_font_info.get_linesize() + 5
        hp_color = (255, 0, 0) if self.player.hp < self.player.max_hp // 3 else (255, 255, 0) if self.player.hp < self.player.max_hp * 2 // 3 else (0, 255, 0)
        self._draw_text(target_surface, self.inventory_font_info, f"HP: {self.player.hp}/{self.player.max_hp}", hp_color, left_column_x, current_y_left)
        current_y_left += self.inventory_font_info.get_linesize() + 15

        self._draw_text(target_surface, self.inventory_font_section, "ATTRIBUTES & SAVES", (255, 215, 0), left_column_x, current_y_left)
        current_y_left += self.inventory_font_section.get_linesize() + 5

        attributes_data = [
            ("STR", self.player.strength, self.player.get_ability_modifier(self.player.strength),
             self.player.get_saving_throw_bonus("STR"), self.player.saving_throw_proficiencies["STR"]),
            ("DEX", self.player.dexterity, self.player.get_ability_modifier(self.player.dexterity),
             self.player.get_saving_throw_bonus("DEX"), self.player.saving_throw_proficiencies["DEX"]),
            ("CON", self.player.constitution, self.player.get_ability_modifier(self.player.constitution),
             self.player.get_saving_throw_bonus("CON"), self.player.saving_throw_proficiencies["CON"]),
            ("INT", self.player.intelligence, self.player.get_ability_modifier(self.player.intelligence),
             self.player.get_saving_throw_bonus("INT"), self.player.saving_throw_proficiencies["INT"]),
            ("WIS", self.player.wisdom, self.player.get_ability_modifier(self.player.wisdom),
             self.player.get_saving_throw_bonus("WIS"), self.player.saving_throw_proficiencies["WIS"]),
            ("CHA", self.player.charisma, self.player.get_ability_modifier(self.player.charisma),
             self.player.get_saving_throw_bonus("CHA"), self.player.saving_throw_proficiencies["CHA"]),
        ]

        for attr_name, score, mod, save_bonus, save_prof in attributes_data:
            line_text = format_ability_and_save(attr_name, score, mod, save_bonus, save_prof)
            self._draw_text(target_surface, self.inventory_font_info, line_text, (255, 255, 255), left_column_x, current_y_left)
            current_y_left += self.inventory_font_info.get_linesize() + 5
        current_y_left += 15

        self._draw_text(target_surface, self.inventory_font_section, "COMBAT STATS", (255, 215, 0), right_column_x, current_y_right)
        current_y_right += self.inventory_font_section.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"AC: {self.player.armor_class}", (255, 255, 255), right_column_x, current_y_right)
        current_y_right += self.inventory_font_info.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"Proficiency Bonus: +{self.player.proficiency_bonus}", (255, 255, 255), right_column_x, current_y_right)
        current_y_right += self.inventory_font_info.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"Attack Power: +{self.player.attack_power}", (255, 255, 255), right_column_x, current_y_right)
        current_y_right += self.inventory_font_info.get_linesize() + 5
        self._draw_text(target_surface, self.inventory_font_info, f"Attack Bonus: +{self.player.attack_bonus}", (255, 255, 255), right_column_x, current_y_right)
        current_y_right += self.inventory_font_info.get_linesize() + 15

        self._draw_text(target_surface, self.inventory_font_section, "EQUIPMENT", (255, 215, 0), right_column_x, current_y_right)
        current_y_right += self.inventory_font_section.get_linesize() + 5
        
        equipped_weapon_name = self.player.equipped_weapon.name if self.player.equipped_weapon else "None"
        equipped_off_hand_name = self.player.equipped_off_hand.name if self.player.equipped_off_hand else "None"
        equipped_armor_name = self.player.equipped_armor.name if self.player.equipped_armor else "None"

        current_y_right = draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_info, f"Weapon: {equipped_weapon_name}", (255, 255, 255), right_column_x, current_y_right, column_width)
        current_y_right = draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_info, f"Offhand: {equipped_off_hand_name}", (255, 255, 255), right_column_x, current_y_right, column_width)
        current_y_right = draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_info, f"Armor: {equipped_armor_name}", (255, 255, 255), right_column_x, current_y_right, column_width)
        current_y_right += 15

        self._draw_text(target_surface, self.inventory_font_section, "STATUS EFFECTS", (255, 215, 0), right_column_x, current_y_right)
        current_y_right += self.inventory_font_section.get_linesize() + 5
        if not self.player.active_status_effects:
            self._draw_text(target_surface, self.inventory_font_info, "None", (150, 150, 150), right_column_x, current_y_right)
            current_y_right += self.inventory_font_info.get_linesize() + 5
        else:
            for effect in self.player.active_status_effects:
                current_y_right = draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_info, f"{effect.name} ({effect.turns_left})", (255, 100, 0), right_column_x, current_y_right, column_width)
                current_y_right += 2
        current_y_right += 15

        final_y = max(current_y_left, current_y_right)

        instructions_y_start = char_menu_rect.bottom - (self.inventory_font_small.get_linesize() * 2) - 20
        instructions_y_start = max(instructions_y_start, final_y + 10) 


    def _draw_text(self, target_surface, font, text, color, x, y):
        text_surface = font.render(text, True, color)
        target_surface.blit(text_surface, (x, y))

    def _wrap_text(self, text, font, max_width):
        words = text.split(' ')
        lines = []
        
        if not words or (len(words) == 1 and not words[0]):
            return [""]

        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        return lines

    def draw_ui(self):
        ui_panel_rect = pygame.Rect(config.GAME_AREA_WIDTH, 0, config.UI_PANEL_WIDTH, config.SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, (20, 20, 20), ui_panel_rect)
        
        pygame.draw.rect(self.screen, (50, 50, 50), ui_panel_rect, 2)

        panel_offset_x = config.GAME_AREA_WIDTH + 15
        panel_right_edge = config.SCREEN_WIDTH - 15
        available_text_width = panel_right_edge - panel_offset_x
        
        current_y = 15
        
        font_header = self.font_header
        font_section = self.font_section
        font_info = self.font_info
        font_small = self.font_small
                
        def draw_wrapped_and_update_y(surface, font, text, color, x, y_start):
            wrapped_lines = self._wrap_text(text, font, available_text_width)
            y_offset = y_start
            for line in wrapped_lines:
                self._draw_text(surface, font, line, color, x, y_offset)
                y_offset += font.get_linesize() + 2
            return y_offset

        def draw_centered_header(surface, font, text, color, y_pos):
            text_surface = font.render(text, True, color)
            text_rect = text_surface.get_rect(centerx=ui_panel_rect.centerx, y=y_pos)
            surface.blit(text_surface, text_rect)

        section_bg_color = (25, 25, 25)
        separator_color = (70, 70, 70)
        separator_thickness = 2

        draw_centered_header(self.screen, font_header, "PLAYER", (255, 215, 0), current_y)
        current_y += font_header.get_linesize() + 10
        self._draw_text(self.screen, font_info, f"Name: {self.player.name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5   
        self._draw_text(self.screen, font_info, f"Level: {self.player.level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        self._draw_text(self.screen, font_info, f"XP: {self.player.current_xp}/{self.player.xp_to_next_level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 15            
        self._draw_text(self.screen, font_info, f"Gold: {self.player.gold}", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        pygame.draw.line(self.screen, separator_color, (panel_offset_x - 5, current_y), (panel_right_edge + 5, current_y), separator_thickness)
        current_y += 15

        draw_centered_header(self.screen, font_header, "VITALS", (255, 215, 0), current_y)
        current_y += font_header.get_linesize() + 10
        
        hp_color = (255, 0, 0) if self.player.hp < self.player.max_hp // 3 else (255, 255, 0) if self.player.hp < self.player.max_hp * 2 // 3 else (0, 255, 0)
        self._draw_text(self.screen, font_info, f"HP: {self.player.hp}/{self.player.max_hp}", hp_color, panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5

        hunger_color = (0, 255, 0) if self.player.hunger > 50 else (255, 255, 0) if self.player.hunger > 20 else (255, 0, 0)
        self._draw_text(self.screen, self.font_info, f"Hunger: {self.player.hunger}/100", hunger_color, panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5 
        current_y += 15                      


        pygame.draw.line(self.screen, separator_color, (panel_offset_x - 5, current_y), (panel_right_edge + 5, current_y), separator_thickness)
        current_y += 15
        
        draw_centered_header(self.screen, font_header, "ABILITIES", (255, 215, 0), current_y)
        current_y += font_header.get_linesize() + 10
        
        if not self.player.abilities:
            self._draw_text(self.screen, font_info, "None", (150, 150, 150), panel_offset_x, current_y)
            current_y += font_info.get_linesize() + 5
        else:
            sorted_abilities = sorted(self.player.abilities.values(), key=lambda ab: ab.name)
            for i, ability in enumerate(sorted_abilities):
                cooldown_text = f" (CD: {ability.current_cooldown})" if ability.current_cooldown > 0 else ""
                ability_color = (100, 255, 255) if ability.current_cooldown == 0 else (255, 150, 0)
                
                ability_display_text = f"{i+1}. {ability.name}{cooldown_text}"
                current_y = draw_wrapped_and_update_y(self.screen, font_info, ability_display_text, ability_color, panel_offset_x, current_y)
                current_y += 5
        current_y += 10
        
        pygame.draw.line(self.screen, separator_color, (panel_offset_x - 5, current_y), (panel_right_edge + 5, current_y), separator_thickness)
        current_y += 15
        
        ''''
        draw_centered_header(self.screen, self.font_header, "ATTRIBUTES & SAVES", (255, 215, 0), current_y)
        current_y += self.font_header.get_linesize() + 10

        def format_ability_and_save(name, score, modifier, save_bonus, save_proficient):
            mod_str = f"+{modifier}" if modifier >= 0 else str(modifier)
            save_bonus_str = f"+{save_bonus}" if save_bonus >= 0 else str(save_bonus)
            prof_char = "*" if save_proficient else ""
            return f"{name}: {score} ({mod_str}) | Save: {save_bonus_str}{prof_char}"

        attributes_data = [
            ("STR", self.player.strength, self.player.get_ability_modifier(self.player.strength),
             self.player.get_saving_throw_bonus("STR"), self.player.saving_throw_proficiencies["STR"]),
            ("DEX", self.player.dexterity, self.player.get_ability_modifier(self.player.dexterity),
             self.player.get_saving_throw_bonus("DEX"), self.player.saving_throw_proficiencies["DEX"]),
            ("CON", self.player.constitution, self.player.get_ability_modifier(self.player.constitution),
             self.player.get_saving_throw_bonus("CON"), self.player.saving_throw_proficiencies["CON"]),
            ("INT", self.player.intelligence, self.player.get_ability_modifier(self.player.intelligence),
             self.player.get_saving_throw_bonus("INT"), self.player.saving_throw_proficiencies["INT"]),
            ("WIS", self.player.wisdom, self.player.get_ability_modifier(self.player.wisdom),
             self.player.get_saving_throw_bonus("WIS"), self.player.saving_throw_proficiencies["WIS"]),
            ("CHA", self.player.charisma, self.player.get_ability_modifier(self.player.charisma),
             self.player.get_saving_throw_bonus("CHA"), self.player.saving_throw_proficiencies["CHA"]),
        ]

        for attr_name, score, mod, save_bonus, save_prof in attributes_data:
            line_text = format_ability_and_save(attr_name, score, mod, save_bonus, save_prof)
            current_y = draw_wrapped_and_update_y(self.screen, self.font_info, line_text, (255, 255, 255), panel_offset_x, current_y)
            current_y += 2
        
        current_y += 10
        pygame.draw.line(self.screen, separator_color, (panel_offset_x - 5, current_y), (panel_right_edge + 5, current_y), separator_thickness)
        current_y += 15
        '''
        
        draw_centered_header(self.screen, font_header, "INVENTORY", (255, 215, 0), current_y)
        current_y += self.font_header.get_linesize() + 10
        inventory_count = len(self.player.inventory.items)
        inventory_capacity = self.player.inventory.capacity
        self._draw_text(self.screen, self.font_info, f"Items: {inventory_count}/{inventory_capacity}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        
        max_items_to_show = 3
        for i, item in enumerate(self.player.inventory.items[:max_items_to_show]):
            current_y = draw_wrapped_and_update_y(self.screen, font_small, f"- {item.name}", item.color, panel_offset_x + 10, current_y)
        if inventory_count > max_items_to_show:
            current_y = draw_wrapped_and_update_y(self.screen, font_small, f"...and {inventory_count - max_items_to_show} more", (150, 150, 150), panel_offset_x + 10, current_y)
        current_y += 10
        pygame.draw.line(self.screen, separator_color, (panel_offset_x - 5, current_y), (panel_right_edge + 5, current_y), separator_thickness)
        current_y += 15
        
        draw_centered_header(self.screen, font_header, "EFFECTS", (255, 215, 0), current_y)
        current_y += font_header.get_linesize() + 10
        if not self.player.active_status_effects:
            self._draw_text(self.screen, font_info, "None", (150, 150, 150), panel_offset_x, current_y)
            current_y += font_info.get_linesize() + 5
        else:
            for effect in self.player.active_status_effects:
                current_y = draw_wrapped_and_update_y(self.screen, font_info, f"{effect.name} ({effect.turns_left})", (255, 100, 0), panel_offset_x, current_y)
                current_y += 2
        current_y += 10
        pygame.draw.line(self.screen, separator_color, (panel_offset_x - 5, current_y), (panel_right_edge + 5, current_y), separator_thickness)
        current_y += 15
        
        draw_centered_header(self.screen, font_header, "STATUS", (255, 215, 0), current_y)
        current_y += font_header.get_linesize() + 10
        if self.game_state == GameState.TAVERN:
            current_y = draw_wrapped_and_update_y(self.screen, font_info, "Location: The Prancing Pony Tavern", (150, 200, 255), panel_offset_x, current_y)
        else:
            current_y = draw_wrapped_and_update_y(self.screen, font_info, f"Dungeon Level: {self.current_level}", (150, 200, 255), panel_offset_x, current_y)
            current_y = draw_wrapped_and_update_y(self.screen, font_info, f"Position: ({self.player.x}, {self.player.y})", (150, 150, 150), panel_offset_x, current_y)
            current = self.get_current_entity()
            if current:
                turn_color = (255, 255, 255) if current == self.player else (255, 100, 100)
                current_y = draw_wrapped_and_update_y(self.screen, font_info, f"Turn: {current.name}", turn_color, panel_offset_x, current_y)
        current_y += 10
        current_y += 15
       
        current_y += font_header.get_linesize() + 10
        max_controls_y = config.SCREEN_HEIGHT - 20
        controls_list = []
        if self.game_state == GameState.TAVERN:
            if self.check_tavern_door_interaction():
                controls_list.append("Move onto door (+) to enter dungeon")
            npc = self.check_npc_interaction()
            if npc:
                controls_list.append(f"SPACE: Talk to {npc.name}")
            controls_list.extend([
                "Arrow keys/hjkl: Move",
                "SPACE: Talk to NPCs",
                "+ = Door to dungeon",
                "I: Open Inventory",
                "C: Open Character Sheet"
            ])
        elif self.game_state == GameState.DUNGEON:
            stairs_dir = self.check_stairs_interaction()
            if stairs_dir:
                controls_list.append(f"Move onto {'<' if stairs_dir == 'up' else '>'} to {'ascend' if stairs_dir == 'up' else 'descend'}")
            dungeon_npc = self.check_dungeon_npc_interaction()
            if dungeon_npc:
                controls_list.append(f"SPACE: Talk to {dungeon_npc.name}")
            else:
                controls_list.append("SPACE: Attack/Pickup")
            controls_list.extend([
                "Arrow keys/hjkl: Move",
                "I: Open Inventory",
                "C: Open Character Sheet",
                "> = Stairs down",
                "< = Stairs up"
            ])
        elif self.game_state == GameState.INVENTORY:
            controls_list.extend([
                "I: Close Inventory",
                "C: Open Character Sheet",
                "1-9/0: Select Item",
            ])
        elif self.game_state == GameState.INVENTORY_MENU:
            controls_list.extend([
                "U: Use Item",
                "E: Equip Item",
                "D: Drop Item",
                "C: Cancel",
            ])
        elif self.game_state == GameState.CHARACTER_MENU:
            controls_list.extend([
                "C: Close Character Menu",
                "I: Open Inventory",
            ])
        for control in controls_list:
            if current_y + font_small.get_linesize() < max_controls_y:
                current_y = draw_wrapped_and_update_y(self.screen, font_small, control, (150, 150, 150), panel_offset_x, current_y)
            else:
                break


    def draw_minimap(self):
        # Always redraw minimap surface fully every frame

        # Fill with solid black background (opaque)
        self.minimap_surface.fill((0, 0, 0, 0))

        scale_x = self.minimap_surface.get_width() / self.game_map.width
        scale_y = self.minimap_surface.get_height() / self.game_map.height
        minimap_tile_scale = min(scale_x, scale_y)
        actual_minimap_tile_size = max(1, int(config.MINIMAP_TILE_SIZE * minimap_tile_scale))

        offset_x = (self.minimap_surface.get_width() - self.game_map.width * actual_minimap_tile_size) // 2
        offset_y = (self.minimap_surface.get_height() - self.game_map.height * actual_minimap_tile_size) // 2

        for y in range(self.game_map.height):
            for x in range(self.game_map.width):
                if (x, y) in self.fov.explored:
                    tile = self.game_map.tiles[y][x]
                    color = tile.color if self.fov.get_visibility_type(x, y) in ['player', 'torch', 'darkvision'] else tile.dark_color
                    pygame.draw.rect(
                        self.minimap_surface,
                        color,
                        (offset_x + x * actual_minimap_tile_size,
                         offset_y + y * actual_minimap_tile_size,
                         actual_minimap_tile_size,
                         actual_minimap_tile_size)
                    )

        if self.player:
            player_minimap_x = offset_x + self.player.x * actual_minimap_tile_size
            player_minimap_y = offset_y + self.player.y * actual_minimap_tile_size

            pygame.draw.rect(
                self.minimap_surface,
                (255, 255, 255),
                (player_minimap_x, player_minimap_y, actual_minimap_tile_size, actual_minimap_tile_size)
            )

        # Blit minimap surface directly to screen every frame
        self.screen.blit(self.minimap_surface, self.minimap_rect.topleft)

