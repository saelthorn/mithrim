import pygame
import random
import config
import math 
import tracemalloc      # Lifesaver


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
from core.ui_sidebar import draw_sidebar
from core.ui_screens import render_inventory_screen, render_inventory_menu_popup, render_character_menu
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from world.encounters.prison_cell import (
    handle_prison_door_interaction, PrisonDoorTile
)
from entities.player import Player, Fighter, Rogue, Wizard, Cleric

# NEW: Import all monster classes
from entities.monster import (
    Monster, Mimic, GiantRat, Ooze, Goblin, GoblinArcher, Skeleton,
    SkeletonArcher, Orc, Centaur, CentaurArcher, Troll, Lizardfolk, 
    LizardfolkArcher, GiantSpider, Beholder, LargeOoze, RedDragon,
    Owlbear, Demogorgon, Grick, GibberingMouther, MindFlayer, Minotaur,
    Wererat, Wolf, Yochlol, Drider, RedSlaad, DeathSlaad, MyconidSprout,
    MyconidAdult, Mezzoloth, Gauth, Arasta, AlphaGrick, IntellectDevourer, 
    Imp, Wraith

)

from entities.base_entity import NPC
from entities.tavern_npcs import create_tavern_npcs, NPC, Merchant
from entities.dungeon_npcs import DungeonHealer, DungeonMerchant, PrisonerNPC
from entities.races import Human, HillDwarf, DrowElf, Tiefling, Dragonborn
from entities.summons import MageHandEntity, SummonedEntity
from core.abilities import SecondWind, PowerAttack, CunningActionDash, Evasion, FireBolt, MistyStep, MageHand, ActionSurge
from core.message_log import MessageBox
from core.status_effects import ParryBuff, PowerAttackBuff, DivineStrikeBuff, CunningActionDashBuff, EvasionBuff, Hidden, BlessingOfStrength, CurseOfWeakness, PreciseStrikeBuff, Prepared, FleetFooted, AppliedToxins

from items.items import (
    Potion, Weapon, Armor, Chest, lesser_healing_potion, greater_healing_potion, wood_plank, meat, green_apple, fromage, 
    bread, mushroom, CampfireKit, torch, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor, robes, 
    iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, 
    apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail, 
    round_shield, kite_shield, tower_shield,
    Helmet, Boots, FocusItem,
    leather_cap, iron_helmet, steel_helmet, great_helm, mages_circlet, hood_of_shadows,
    leather_boots, iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers,
)

from core.pathfinding import astar
from world.tile import floor, dungeon_floor_two, dungeon_floor_three, dungeon_floor_four, MimicTile, TrapTile
from world.bloodstain import Bloodstain
from world.altar import Altar
from world.water_features import river, lake, is_water_tile # NEW: Import water tiles and helper
from core.floating_text import FloatingText 
import graphics


INTERNAL_WIDTH = 800
INTERNAL_HEIGHT = 600
ASPECT_RATIO = INTERNAL_WIDTH / INTERNAL_HEIGHT


class Camera:
    def __init__(self, screen_width, screen_height, tile_size, message_log_height):
        self.tile_size = tile_size
        self.viewport_width = screen_width // tile_size
        self.viewport_height = screen_height // tile_size - 2
        
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

        # Calculate the ideal camera position.
        # Player is centered horizontally, but shifted up by 30% of the viewport
        # so the message log overlay at the bottom doesn't obscure the action.
        ideal_camera_center_x = target_x_float - (self.viewport_width / 2.0)
        ideal_camera_center_y = target_y_float - (self.viewport_height * 0.38)

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
        
        self.fps = 60
        self.fps_font = pygame.font.SysFont('consolas', 15)  # You can adjust the font size as needed
        self.clock = pygame.time.Clock()  # Initialize the clock for FPS tracking


        self.internal_surface = None
        self.inventory_ui_surface = None
        self.camera = None
        self.message_log = None

        self.merchant = None  # Initialize merchant attribute        
        self.dungeon_merchant = None # Create a persistent instance
        
        self.entities = []  # Initialize the entities list here
        self.turn_order = []  # Initialize the turn order list
        self.current_turn_index = 0
        self.bloodstains = []
        
        self._recalculate_dimensions() 
        self._init_fonts()

        # NEW: Start in character creation state
        self.game_state = GameState.CHARACTER_CREATION 
        self._previous_game_state = None
        self.current_level = 1  
        self.max_level_reached = 1
        self.player_has_acted = False
        self.player_bonus_action_used = False
        self.message_log = MessageBox(
            0,
            config.SCREEN_HEIGHT - int(config.SCREEN_HEIGHT * 0.26),
            config.GAME_AREA_WIDTH,
            int(config.SCREEN_HEIGHT * 0.26)
        )
        self._recalculate_dimensions()

        self.ability_in_use = None
        self.targeting_ability_range = 0
        self.targeting_cursor_x = 0
        self.targeting_cursor_y = 0
            
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 255))
        
        self.floating_texts = []  # Initialize floating texts list
        self.lit_wall_torches = set()  # (x, y) positions of wall torches the player has lit

        # REMOVED: Player creation moved to character_creation_start
        self.player = None 
        
        self.selected_inventory_item = None
        self.selected_inventory_index = 0  # Initialize the selected inventory index        

        # Tile highlights for telegraphed attacks or effects: list of (x, y, (r,g,b,a))
        self.tile_highlights = []

        # Torch Flicker
        self._torch_flicker_frame = 0
        self._torch_flicker_tint = (235, 185, 95, 255)

        # Character creation specific variables
        # UPDATED: Add DrowElf to available races
        self.available_races = [Human(), HillDwarf(), DrowElf(), Tiefling(), Dragonborn()]
        self.selected_race_index = 0 
        self.character_name = "Shadowblade" # Default name, could be input later
        self.character_class = Rogue # Available classes: Fighter, Rogue, Wizard, Cleric

        self.race_class_visuals = {
            # Human mappings
            ("Human", "Fighter"): ('HF', (255, 255, 255)), # 'HF' for Human Fighter
            ("Human", "Rogue"): ('HR', (255, 255, 0)),    # 'HR' for Human Rogue
            ("Human", "Wizard"): ('HW', (0, 200, 255)),   # 'HW' for Human Wizard
            ("Human", "Cleric"): ('HC', (255, 255, 0)),    # 'HC' for Human Cleric
         
            # Hill Dwarf mappings
            ("HillDwarf", "Fighter"): ('DF', (180, 120, 60)), # 'DF' for Dwarf Fighter
            ("HillDwarf", "Rogue"): ('DR', (200, 150, 0)),   # 'DR' for Dwarf Rogue
            ("HillDwarf", "Wizard"): ('DW', (100, 150, 255)), # 'DW' for Dwarf Wizard
            ("HillDwarf", "Cleric"): ('DC', (255, 255, 0)),   # 'DC' for Dwarf Cleric

            # Drow Elf mappings 
            ("DrowElf", "Fighter"): ('EF', (100, 0, 100)), # Purple for Drow Fighter
            ("DrowElf", "Rogue"): ('ER', (150, 0, 150)),   # Darker Purple for Drow Rogue
            ("DrowElf", "Wizard"): ('EW', (200, 0, 200)),  # Lighter Purple for Drow Wizard
            ("DrowElf", "Cleric"): ('EC', (255, 255, 0)),   # Yellow for Drow Cleric

            # Tiefling mappings (NEW)
            ("Tiefling", "Fighter"): ('TF', (150, 0, 0)), # Red for Tiefling Fighter
            ("Tiefling", "Rogue"): ('TR', (200, 0, 0)),   # Dark Red for Tiefling Rogue
            ("Tiefling", "Wizard"): ('TW', (255, 0, 0)),  # Bright Red for Tiefling Wizard
            ("Tiefling", "Cleric"): ('TC', (255, 255, 0)),   # Yellow for Tiefling Cleric

            # Dragonborn mappings (NEW)
            ("Dragonborn", "Fighter"): ('DBF', (100, 0, 0)), # Red for Dragonborn Fighter
            ("Dragonborn", "Rogue"): ('DBR', (0, 150, 0)),   # Dark Red for Dragonborn Rogue
            ("Dragonborn", "Wizard"): ('DBW', (0, 255, 0)),  # Bright Red for Dragonborn Wizard
            ("Dragonborn", "Cleric"): ('DBC', (255, 255, 0)),   # Yellow for Dragonborn Cleric
        }

        # Class selection
        self.available_classes = [Fighter, Rogue, Wizard, Cleric] # List of class objects
        self.selected_class_index = 0 

        # Call a method to start character creation
        self.start_character_creation()

        # Mini-map specific attributes
        self.minimap_surface = None
        self.minimap_rect = None
        self.minimap_needs_redraw = True # Flag to redraw minimap only when needed

        self.dirty_rects = [] # New list to store dirty rectangles
        self._equip_slot_rects = {}     # Set by render_inventory_screen each frame
        self._inventory_slot_rects = {}  # Set by render_inventory_screen each frame

        self.menu_open = None

        self._recalculate_minimap_dimensions()

        # NEW: Flag to track if game over message has been displayed
        self._game_over_displayed = False

        self.death_screen_alpha = 0  # Alpha for game over title text
        self.death_screen_bg_alpha = 0  # Alpha for background overlay
        self.death_screen_subtext_alpha = 0  # Alpha for subtext
        self.death_screen_animation_phase = 0  # 0=text fade-in, 1=bg fade-in, 2=subtext fade-in, 3=done
        self.death_screen_animation_speed = 5  # Alpha increment per frame (adjust for speed)
        self.fade_out_alpha = 0 # NEW: Alpha for the full screen fade-out
        self.fade_out_speed = 15 # NEW: Speed of the fade-out
        self.fade_in_alpha = 255
        self.fade_in_speed = 15

        self.game_over_victory = False
        self.game_over_title = "YOU DIED"
        self.game_over_story_lines = []
        self.game_over_subtext = "Press R to Restart or Q to Quit"

        self.ignore_next_input = False  # Flag to ignore input after restart

    # Boss schedule: every 5th floor, ordered list
    BOSS_FLOORS = [
        (1, 'Ooze'),
        (2, 'MyconidAdult'),
        (3, 'LizardfolkArcher'),
        (5, 'Gauth'),
        (7, 'AlphaGrick'),
        (10, 'DeathSlaad'),
        (12, 'MindFlayer'),
        (15, 'Beholder'),
        (18, 'RedDragon'),
        (19, 'Demogorgon'),
        (20, 'Arasta'),
    ]

    MONSTER_SPAWN_TIERS = {
        # 🌱 Early dungeon fodder (CR 1/8 – CR 1/4)
        (1, 2): [Goblin, Wolf, Imp, GiantRat, MyconidSprout],
        (3, 4): [Goblin, GoblinArcher, GiantRat, GiantSpider, Wererat, Wolf, MyconidSprout, IntellectDevourer, Imp],
        (5, 5): [Goblin, GoblinArcher, Ooze, GiantRat, Wererat, GiantSpider, Wolf, MyconidAdult, IntellectDevourer],

        # ⚔️ Early-mid dangers (CR 1/2 – CR 2)
        (6, 7): [Skeleton, SkeletonArcher, Orc, Grick, Ooze],
        (8, 9): [Lizardfolk, LizardfolkArcher, GiantSpider, Wererat, MyconidAdult],

        # 🛡️ Mid-game threats (CR 3 – CR 6)
        (10, 11): [Centaur, CentaurArcher, Troll, Owlbear, Minotaur, RedSlaad, GibberingMouther],
        (12, 13): [Troll, Orc, GiantSpider, LargeOoze, Minotaur, GibberingMouther],

        # 👁️ Late-mid bosses and horrors (CR 7 – CR 10)
        (14, 15): [LargeOoze, GiantSpider, GibberingMouther, Gauth, Wraith],
        (16, 16): [Drider, Mezzoloth, Wraith],

        # 🔥 High level threats (CR 11 – CR 15)
        (17, 17): [Yochlol, RedSlaad, LargeOoze, AlphaGrick, Wraith],
        (18, 18): [Beholder, MindFlayer, LargeOoze, DeathSlaad, Gauth],

        # 🕷️ Endgame / campaign bosses (CR 20+)
        (19, 19): [],
        (20, 99): [GiantSpider],
    }




    def start_character_creation(self):
        self.game_state = GameState.CHARACTER_CREATION
        self.message_log.add_message("--- CHARACTER CREATION ---", (240, 240, 240))
        self.message_log.add_message("Choose your Race (Arrow Keys to navigate, Enter to select):", (200, 200, 255))
        self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
        self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))

    def finalize_race_selection(self):
        chosen_race = self.available_races[self.selected_race_index]
        self.message_log.add_message(f"You have chosen the {chosen_race.name} race!", (0, 255, 0))
        
        # Transition to class selection
        self.game_state = GameState.CLASS_SELECTION
        self.message_log.add_message("--- CLASS SELECTION ---", (240, 240, 240))
        self.message_log.add_message("Choose your Class (Arrow Keys to navigate, Enter to select):", (200, 200, 255))
        self.message_log.add_message(f"Current Class: {self.available_classes[self.selected_class_index].__name__}", (255, 255, 255))
        # Display a generic description for now, or add descriptions to classes if you want
        self.message_log.add_message("A brief description of the class will go here.", (150, 150, 150))

        pygame.event.clear()
        self.ignore_next_input = True  # Ignore next keydown event


    def finalize_character_creation(self):
        chosen_race = self.available_races[self.selected_race_index]
        chosen_class_constructor = self.available_classes[self.selected_class_index]
        
        race_name_str = chosen_race.name.replace(" ", "") # "HillDwarf" from "Hill Dwarf"
        class_name_str = chosen_class_constructor.__name__ # "Fighter", "Rogue", "Wizard", "Cleric"

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

        self.player.spell_bonus = self.player.get_spell_modifier() + self.player.proficiency_bonus
        self.player.attack_power = self.player.get_ability_modifier(self.player.dexterity) + self.player.equipped_weapon.damage_modifier
        self.player.attack_bonus = self.player.get_ability_modifier(self.player.dexterity) + self.player.proficiency_bonus + self.player.equipped_weapon.attack_bonus
        
        self.message_log.add_message(f"You have chosen to be a {chosen_race.name} {self.player.class_name} named {self.player.name}!", (0, 255, 0))
        
        # Transition to tavern
        pygame.event.clear()  
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


    def _recalculate_dimensions(self, is_zoom_only=False):
        """Recalculate all dynamic dimensions based on current screen size."""
        config.SCREEN_WIDTH, config.SCREEN_HEIGHT = self.screen.get_size()
        
        config.UI_PANEL_WIDTH = int(config.SCREEN_WIDTH * config.UI_PANEL_WIDTH_RATIO)
        config.GAME_AREA_WIDTH = config.SCREEN_WIDTH - config.UI_PANEL_WIDTH
        config.MESSAGE_LOG_HEIGHT = int(config.SCREEN_HEIGHT * config.MESSAGE_LOG_HEIGHT_RATIO)
        
        effective_tile_pixel_size = int(config.TILE_SIZE * config.TARGET_EFFECTIVE_TILE_SCALE)
        if effective_tile_pixel_size < 1:
            effective_tile_pixel_size = 1

        new_internal_width_tiles = max(config.MIN_GAME_AREA_TILES_WIDTH, config.GAME_AREA_WIDTH // effective_tile_pixel_size)
        # Game area uses full screen height — message log overlays on top as transparent
        new_internal_height_tiles = max(config.MIN_GAME_AREA_TILES_HEIGHT, config.SCREEN_HEIGHT // effective_tile_pixel_size)
        
        config.INTERNAL_GAME_AREA_WIDTH_TILES = new_internal_width_tiles
        config.INTERNAL_GAME_AREA_HEIGHT_TILES = new_internal_height_tiles
        
        config.INTERNAL_GAME_AREA_PIXEL_WIDTH = config.INTERNAL_GAME_AREA_WIDTH_TILES * config.TILE_SIZE
        config.INTERNAL_GAME_AREA_PIXEL_HEIGHT = config.INTERNAL_GAME_AREA_HEIGHT_TILES * config.TILE_SIZE
        
        self.internal_surface = pygame.Surface((config.INTERNAL_GAME_AREA_PIXEL_WIDTH, config.INTERNAL_GAME_AREA_PIXEL_HEIGHT)).convert_alpha()
        
        self.inventory_ui_surface = pygame.Surface((config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT)).convert_alpha()
        self.inventory_ui_surface.fill((0,0,0,0))

        if self.camera is None:
            self.camera = Camera(config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT, config.TILE_SIZE, 0)
        
        self.camera.tile_size = config.TILE_SIZE 
        self.camera.viewport_width = config.INTERNAL_GAME_AREA_WIDTH_TILES
        self.camera.viewport_height = config.INTERNAL_GAME_AREA_HEIGHT_TILES
        
        if self.message_log is not None: 
            self.message_log.rect.x = 0
            self.message_log.rect.y = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
            self.message_log.rect.width = config.GAME_AREA_WIDTH
            self.message_log.rect.height = config.MESSAGE_LOG_HEIGHT
            
            # Only recalculate message log font on window resize, not on game zoom
            if not is_zoom_only:
                new_font_size = int(config.MESSAGE_LOG_FONT_BASE_SIZE * config.MESSAGE_LOG_FONT_SCALE_FACTOR)
                if new_font_size < 8: new_font_size = 8 
                self.message_log.font = pygame.font.SysFont('consolas', new_font_size)
                
                self.message_log.line_height = self.message_log.font.get_linesize()
                self.message_log.max_lines = self.message_log.rect.height // self.message_log.line_height
        
        graphics.setup_tile_mapping() 
        self._init_fonts() 

        # Recalculate minimap dimensions and surface
        self._recalculate_minimap_dimensions()

    def change_zoom(self, zoom_delta):
        """Adjust zoom level while keeping the game camera within bounds."""
        new_zoom = config.TARGET_EFFECTIVE_TILE_SCALE + zoom_delta
        new_zoom = max(config.MIN_ZOOM_SCALE, min(config.MAX_ZOOM_SCALE, new_zoom))
        if new_zoom == config.TARGET_EFFECTIVE_TILE_SCALE:
            return

        config.TARGET_EFFECTIVE_TILE_SCALE = new_zoom
        self._recalculate_dimensions(is_zoom_only=True)

        if self.camera is not None and hasattr(self, "game_map") and self.game_map is not None:
            self.camera.x = max(0.0, min(self.camera.x, float(self.game_map.width - self.camera.viewport_width)))
            self.camera.y = max(0.0, min(self.camera.y, float(self.game_map.height - self.camera.viewport_height)))
            self.camera.target_x = max(0.0, min(self.camera.target_x, float(self.game_map.width - self.camera.viewport_width)))
            self.camera.target_y = max(0.0, min(self.camera.target_y, float(self.game_map.height - self.camera.viewport_height)))

        if hasattr(self, "message_log") and self.message_log is not None:
            self.message_log.add_message(f"Zoom {'in' if zoom_delta > 0 else 'out'}: {new_zoom:.1f}x", (200, 200, 255))


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
        
        self.message_log.add_message("=== WELCOME TO THE PRANCING PONY TAVERN ===", (240, 240, 240))
        self.message_log.add_message("Walk to the door (+) and press any movement key to enter the dungeon!", (150, 150, 255))
        self.minimap_needs_redraw = True # New map, redraw minimap
    

    def generate_level(self, level_number, spawn_on_stairs_up=False):
        self.game_state = GameState.DUNGEON
        self._previous_game_state = GameState.DUNGEON
        self.current_level = level_number
        self.max_level_reached = max(self.max_level_reached, level_number)
        if hasattr(self, "game_map") and hasattr(self.game_map, "items_on_ground"):
            self.game_map.items_on_ground.clear()
        self.lit_wall_torches = set()  # Reset lit torches for the new level 

        self.game_map = GameMap(60, 40)
        self.fov = FOV(self.game_map)
        
        rooms, self.stairs_positions, self.torch_light_sources, prison_prisoners = generate_dungeon(self.game_map, level_number)
        # Add any prison prisoners to the entity list
        for prisoner in prison_prisoners:
            self.entities.append(prisoner)

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

        # Altar generation (this is correct placement)
        altars_to_place = min(1 + level_number // 1, 1)
        for _ in range(altars_to_place):
            # Find a suitable room for the altar (preferably not the starting room)
            if len(rooms) > 1:
                # Select a room, excluding the first one (player spawn)
                altar_room = random.choice(rooms[1:])

                # Try to find an unoccupied spot within the room for the altar
                possible_altar_spots = []
                # Iterate over all tiles within the room (excluding walls)
                for y_coord in range(altar_room.y1 + 1, altar_room.y2):
                    for x_coord in range(altar_room.x1 + 1, altar_room.x2):
                        # Check if the tile is walkable (floor)
                        if self.game_map.is_walkable(x_coord, y_coord):
                            # Check if it's not a stairs position
                            is_stairs = False
                            for _, pos in self.stairs_positions.items():
                                if (x_coord, y_coord) == pos:
                                    is_stairs = True
                                    break
                                
                            # Check if it's not already occupied by another altar
                            is_occupied_by_altar = False
                            for existing_altar in self.game_map.altars:
                                if existing_altar.x == x_coord and existing_altar.y == y_coord:
                                    is_occupied_by_altar = True
                                    break
                            # Check if it's not occupied by any existing items on the ground
                            is_occupied_by_item = False
                            for existing_item in self.game_map.items_on_ground:
                                if existing_item.x == x_coord and existing_item.y == y_coord:
                                    is_occupied_by_item = True
                                    break
                            # NEW: Check if it's not a water tile
                            is_water = is_water_tile(self.game_map.tiles[y_coord][x_coord])

                            # Add to possible spots if all checks pass
                            if not is_stairs and not is_occupied_by_altar and not is_occupied_by_item and not is_water:
                                possible_altar_spots.append((x_coord, y_coord))

                if possible_altar_spots:
                    # Choose a random spot from the valid ones
                    altar_x, altar_y = random.choice(possible_altar_spots)
                    altar = Altar(altar_x, altar_y)
                    self.game_map.altars.append(altar)

        self.entities = [self.player]
        
        monsters_per_level = min(5 + level_number, len(rooms) - 2)
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
                # Find a spawn point inside the boss room that is walkable and not on stairs or water
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
                    # Require 2x2 walkable area for boss spawn AND ensure all 4 tiles are floor-like (not walls/doors/water)
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
                            # Ensure tile type is floor-ish (avoid walls/doors/water overlap). Use tile char check.
                            tile_obj = self.game_map.tiles[ty][tx]
                            if tile_obj.char in ['#', '+'] or is_water_tile(tile_obj): # NEW: Check for water tiles
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
                        'Ooze': Ooze,
                        'LizardfolkArcher': LizardfolkArcher,  # Example of a non-boss that could be added to the schedule
                        'MyconidAdult': MyconidAdult,
                        'Troll': Troll,  # TODO: replace with GoblinKing class when available
                        'Owlbear': Owlbear,
                        'Beholder': Beholder,
                        'DeathSlaad': DeathSlaad,
                        'Gauth': Gauth,
                        'AlphaGrick': AlphaGrick,
                        'MindFlayer': MindFlayer,
                        'RedDragon': RedDragon,  # TODO: replace with Red Dragon class when available
                        'Demogorgon': Demogorgon,
                        'Arasta': Arasta
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
            # NEW: Ensure monster doesn't spawn on water
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y) and not is_water_tile(self.game_map.tiles[y][x])):
                # Randomly choose a monster class from the possible_monsters list
                chosen_monster_class = random.choice(possible_monsters)

                # Mimic is handled separately as a special case in dungeon_generator.py
                if chosen_monster_class == Mimic:
                    continue 

                monster = chosen_monster_class(x, y)
                # --- Monster Stat Scaling (Optional, implement later) ---
                # You can add logic here to scale monster HP, attack, etc. based on level_number
                self.entities.append(monster)

        if len(rooms) > 2 and random.random() < 0.2: # Healer spawnrate
            shuffled_healer_rooms = list(rooms[1:-1])
            random.shuffle(shuffled_healer_rooms)
            healer_spawned = False
            for healer_room in shuffled_healer_rooms:
                possible_spawn_points = []
                for y_coord in range(healer_room.y1 + 2, healer_room.y2 - 1):
                    for x_coord in range(healer_room.x1 + 2, healer_room.x2 - 1):
                        # NEW: Check for water tiles
                        if self.game_map.is_walkable(x_coord, y_coord) and \
                           not any(e.x == x_coord and e.y == y_coord for e in self.entities) and \
                           not is_water_tile(self.game_map.tiles[y_coord][x_coord]):
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

        elif len(rooms) > 2 and random.random() < 0.9: # Merchant spawnrate
            shuffled_merchant_rooms = list(rooms[1:-1])
            random.shuffle(shuffled_merchant_rooms)
            merchant_spawned = False
            for merchant_room in shuffled_merchant_rooms:
                possible_spawn_points = []
                for y_coord in range(merchant_room.y1 + 2, merchant_room.y2 - 1):
                    for x_coord in range(merchant_room.x1 + 2, merchant_room.x2 - 1):
                        # NEW: Check for water tiles
                        if self.game_map.is_walkable(x_coord, y_coord) and \
                           not any(e.x == x_coord and e.y == y_coord for e in self.entities) and \
                           not is_water_tile(self.game_map.tiles[y_coord][x_coord]):
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
                    merchant_x, merchant_y = random.choice(possible_spawn_points)
                    self.dungeon_merchant = DungeonMerchant(merchant_x, merchant_y) # Assign to game instance
                    self.entities.append(self.dungeon_merchant)
                    merchant_spawned = True
                    break
            
            if not merchant_spawned:
                self.message_log.add_message("DEBUG: Dungeon Healer could not find a suitable spawn spot.", (100, 100, 100))                

        item_templates = [
            lesser_healing_potion, greater_healing_potion, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor,
            robes, iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, 
            apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail,
            round_shield, kite_shield, tower_shield, torch,
            leather_cap, iron_helmet, steel_helmet, great_helm, mages_circlet, hood_of_shadows,
            leather_boots, iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers,
        ]

        item_spawn_chance = 0.5 + min(0.5, level_number * 0.02) # Scales from 30% to max 50% at level 10+

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


                # is_decorative_tile = self.game_map.tiles[item_y][item_x] != floor                    
                # NEW: Check if the spot is a water tile
                is_water = is_water_tile(self.game_map.tiles[item_y][item_x])

                if (item_x, item_y) != (self.player.x, self.player.y) and \
                   (item_x, item_y) not in self.stairs_positions.values() and \
                   not is_blocked_by_non_item_entity and \
                   not is_occupied_by_another_item and \
                   not is_water: # NEW: Don't spawn items on water
                    

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
        
        self.bloodstains.clear()
        self.floating_texts.clear()  

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
        if self.game_state == GameState.DUNGEON:
            for entity in self.entities:
                if isinstance(entity, (DungeonHealer, DungeonMerchant, PrisonerNPC)):
                    if (abs(self.player.x - entity.x) <= 1 and
                        abs(self.player.y - entity.y) <= 1 and
                        (abs(self.player.x - entity.x) + abs(self.player.y - entity.y)) == 1):
                        if isinstance(entity, DungeonMerchant):
                            self.dungeon_merchant = entity
                        elif isinstance(entity, PrisonerNPC) and entity.has_been_freed:
                            # Show freed dialogue via message log
                            self.message_log.add_message(
                                f'{entity.name}: "{entity.get_dialogue()}"', (220, 200, 140)
                            )
                            return None  # handled inline, no trade UI
                        return entity
        return None

    def try_light_wall_torch(self):
        """
        If the player is adjacent to a wall torch tile and has the 'Torchlight'
        (has_torchlight) status effect, light that torch so it emits light.
        Returns True if a torch was successfully lit, False otherwise.
        """
        from world.tile import torch as torch_tile

        has_torchlight = any(
            effect.name == "Torchlight" for effect in self.player.active_status_effects
        )
        if not has_torchlight:
            self.message_log.add_message(
                "You need a light source (Torchlight effect) to ignite the torch.",
                (150, 150, 150)
            )
            return False

        adjacents = [
            (self.player.x + dx, self.player.y + dy)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
        ]

        for tx, ty in adjacents:
            if not (0 <= tx < self.game_map.width and 0 <= ty < self.game_map.height):
                continue
            tile_at = self.game_map.tiles[ty][tx]
            # Match torch tile by char and name (avoids importing the singleton object)
            if tile_at.char == 'i' and tile_at.name == "Torch":
                if (tx, ty) in self.lit_wall_torches:
                    self.message_log.add_message("That torch is already burning.", (255, 165, 0))
                    return False
                # Light it up
                self.lit_wall_torches.add((tx, ty))
                self.update_fov()
                self.message_log.add_message(
                    "You touch your flame to the wall torch — it roars to life!",
                    (255, 165, 0)
                )
                return True

        self.message_log.add_message("No torch to light nearby.", (150, 150, 150))
        return False

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
        # Clear entities, items, bloodstains, floating texts, and map tile references before level change
        self.entities.clear()
        if hasattr(self, "game_map") and hasattr(self.game_map, "items_on_ground"):
            self.game_map.items_on_ground.clear()
        if hasattr(self, "floating_texts"):
            self.floating_texts.clear()
        if hasattr(self, "bloodstains"):
            self.bloodstains.clear()
        if hasattr(self, "game_map") and hasattr(self.game_map, "tiles"):
            for row in self.game_map.tiles:
                for tile in row:
                    if hasattr(tile, "entity"):
                        tile.entity = None
                    if hasattr(tile, "item"):
                        tile.item = None

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
        base_radius = getattr(self.player, 'vision_radius', 4)  # base vision radius
        torch_bonus = 0
        has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)    
        
        if has_torchlight:
            torch_bonus = 1

        LIGHT_PRIORITY = {
            'torch': 3,
            'player': 2,
            'darkvision': 1
        }

        # Clear previous visibility sources but keep explored tiles
        previous_explored = set(self.fov.explored)
        self.fov.visible_sources.clear()

        # Compute base FOV with 'player' light source and darkvision radius
        self.fov.compute_fov(
            self.player.x,
            self.player.y,
            radius=base_radius,
            light_source_type='player',
            player_darkvision_radius=max(getattr(self.player, 'darkvision_radius', 0), base_radius)
        )

        # If torchlight active, compute extended FOV with 'torch' light source
        if torch_bonus > 0:
            torch_fov = FOV(self.game_map)          

            torch_fov.compute_fov(
                self.player.x,
                self.player.y,
                radius=base_radius + torch_bonus,
                light_source_type='torch'
            )

            # Merge torchlight FOV into main FOV with priority
            for (x, y), source in torch_fov.visible_sources.items():
                existing_source = self.fov.visible_sources.get((x, y))
                if existing_source is None:
                    self.fov.visible_sources[(x, y)] = source
                    self.fov.explored.add((x, y))
                else:
                    # Replace only if torchlight has higher priority
                    if LIGHT_PRIORITY[source] > LIGHT_PRIORITY.get(existing_source, 0):
                        self.fov.visible_sources[(x, y)] = source
                        self.fov.explored.add((x, y))

        # Emit light from each lit wall torch (player-activated via 'F' key).
        # Torches sit on wall tiles, so casting FOV from the torch position itself
        # traps the light inside the wall.  Instead, find every open floor tile
        # adjacent to the torch and cast from there — the union of those passes
        # is the light that fans out into the room.
        WALL_TORCH_RADIUS = 3  # how far a lit wall torch illuminates
        for (wx, wy) in getattr(self, 'lit_wall_torches', set()):
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ox, oy = wx + dx, wy + dy
                if not (0 <= ox < self.game_map.width and 0 <= oy < self.game_map.height):
                    continue
                if self.game_map.tiles[oy][ox].blocked:
                    continue  # skip neighbours that are also walls
                wall_torch_fov = FOV(self.game_map)
                wall_torch_fov.compute_fov(
                    ox, oy,
                    radius=WALL_TORCH_RADIUS,
                    light_source_type='torch'
                )
                for (x, y), source in wall_torch_fov.visible_sources.items():
                    existing = self.fov.visible_sources.get((x, y))
                    if existing is None:
                        self.fov.visible_sources[(x, y)] = source
                        self.fov.explored.add((x, y))
                    elif LIGHT_PRIORITY[source] > LIGHT_PRIORITY.get(existing, 0):
                        self.fov.visible_sources[(x, y)] = source
                        self.fov.explored.add((x, y))

        # Check if new tiles were explored for minimap redraw
        if self.fov.explored != previous_explored:
            self.minimap_needs_redraw = True

        # Existing monster activation logic...
        WAKE_RADIUS = 10  # Tiles within which monsters wake up regardless of visibility

        for entity in self.entities:
            if isinstance(entity, Monster):
                visibility_type = self.fov.get_visibility_type(entity.x, entity.y)
                distance_to_player = entity.distance_to(self.player.x, self.player.y)

                # Wake if visible OR within wake radius
                if visibility_type in ['player', 'torch', 'darkvision'] and distance_to_player <= WAKE_RADIUS:
                    if not entity.is_active:
                        entity.is_active = True
                        entity.sleep_cooldown = 0
                        self.message_log.add_message(f"You spot a {entity.name}!", entity.color)
                elif distance_to_player <= WAKE_RADIUS:
                    entity.is_active = True
                    entity.sleep_cooldown = 0
                elif visibility_type in ['player', 'torch', 'darkvision'] and distance_to_player >= WAKE_RADIUS:
                    if entity.is_active:
                        entity.is_active = False
                        entity.sleep_cooldown = random.randint(5, 15)
                        self.message_log.add_message(f"The {entity.name} seems to have fallen asleep.", (100, 100, 100))
                else:
                    if entity.is_active and entity.sleep_cooldown <= 10:
                        entity.is_active = False
                        entity.sleep_cooldown = random.randint(5, 15)




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

        if current_acting_entity == self.player and self.player.extra_turns > 0:
            self.player.extra_turns -= 1
            self.message_log.add_message("You take an extra action!", (255, 255, 0))
            self.player_has_acted = False # Reset for the next action
            return # IMPORTANT: Exit before advancing to the next entity

        if current_acting_entity == self.player and self.player.hidden_turns > 0:
            self.player.hidden_turns -= 1
            self.player_has_acted = False # Reset for the next action
            
            return # IMPORTANT: Exit before advancing to the next entity   

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
            self.player_bonus_action_used = False  # Reset bonus action availability on a new player turn
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
        """Remove dead or expired entities/items from the game world."""

        # Remove dead monsters/NPCs
        self.entities = [e for e in self.entities if getattr(e, "alive", True)]

        # Handle items (depends on your structure: game.items_on_ground or game.map.items_on_ground)
        if hasattr(self, "items_on_ground"):
            self.items_on_ground = [i for i in self.items_on_ground if getattr(i, "alive", True)]
        elif hasattr(self, "map") and hasattr(self.map, "items_on_ground"):
            self.map.items_on_ground = [i for i in self.map.items_on_ground if getattr(i, "alive", True)]

        # Clean up any dead entities left in tiles
        if hasattr(self, "map") and hasattr(self.map, "tiles"):
            for row in self.map.tiles:
                for tile in row:
                    if hasattr(tile, "entity") and tile.entity is not None:
                        if not getattr(tile.entity, "alive", True):
                            tile.entity = None

        # Clean up floating texts (remove expired ones)
        if hasattr(self, "floating_texts"):
            self.floating_texts = [t for t in self.floating_texts if not getattr(t, "expired", False)]

        # Cap message log size (prevents memory bloat)
        if hasattr(self, "message_log") and hasattr(self.message_log, "messages"):
            MAX_LOG_MESSAGES = 50
            if len(self.message_log.messages) > MAX_LOG_MESSAGES:
                self.message_log.messages = self.message_log.messages[-MAX_LOG_MESSAGES:]
    
    

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if self.ignore_next_input:
                # Ignore all keydown events once, then reset flag
                if event.type == pygame.KEYDOWN:
                    self.ignore_next_input = False
                    return True  # Consume this event and ignore it
                else:
                    continue  # Ignore other events until keydown resets flag

            # NEW: Handle input specifically for GAME_OVER state
            if self.game_state == GameState.GAME_OVER:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        # Restart the game: reset player, generate tavern or level 1
                        if self.death_screen_animation_phase == 3: # Only if initial animation is done
                            self.death_screen_animation_phase = 4 # NEW: Start fade-out phase
                            self.fade_out_alpha = 0 # Start fade-out from transparent
                            self.message_log.add_message("Initiating restart sequence...", (100, 200, 255))

                            pygame.event.clear()
                            self.ignore_next_input = True  # Set flag to ignore next input
                        return True
                    elif event.key == pygame.K_q:
                        # Quit the game
                        return False # Signal to quit
                continue  # Skip other event processing when game over

            if event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._recalculate_dimensions()
                self.render()            

            # NEW: Handle mouse wheel scrolling for message log and game zoom
            if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.MOUSEWHEEL:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = event.pos
                    wheel_delta = 0
                    if event.button == 4:
                        wheel_delta = 1
                    elif event.button == 5:
                        wheel_delta = -1
                else:
                    pos = pygame.mouse.get_pos()
                    wheel_delta = event.y

                message_log_hit = self.message_log.rect.collidepoint(pos)
                game_area_hit = (0 <= pos[0] < config.GAME_AREA_WIDTH and
                                 0 <= pos[1] < config.SCREEN_HEIGHT)

                if message_log_hit:
                    if wheel_delta > 0:
                        self.message_log.scroll_up()
                        return True
                    elif wheel_delta < 0:
                        self.message_log.scroll_down()
                        return True

                if game_area_hit and self.game_state in (GameState.DUNGEON, GameState.TAVERN, GameState.TARGETING):
                    if wheel_delta > 0:
                        self.change_zoom(config.ZOOM_STEP)
                        return True
                    elif wheel_delta < 0:
                        self.change_zoom(-config.ZOOM_STEP)
                        return True

                # Inventory mouse handling
                if (event.type == pygame.MOUSEBUTTONDOWN
                        and self.game_state == GameState.INVENTORY):

                    # Left-click on equipment slot → unequip to inventory
                    if event.button == 1 and hasattr(self, '_equip_slot_rects'):
                        for slot_key, rect in self._equip_slot_rects.items():
                            if rect.collidepoint(pos):
                                self._unequip_slot(slot_key)
                                return True

                    # Left-click on inventory grid slot → equip item immediately
                    # Right-click on inventory grid slot → open action popup
                    if event.button in (1, 3) and hasattr(self, '_inventory_slot_rects'):
                        for idx, rect in self._inventory_slot_rects.items():
                            if rect.collidepoint(pos):
                                items = self.player.inventory.items
                                if idx < len(items):
                                    self.selected_inventory_index = idx
                                    clicked_item = items[idx]
                                    if event.button == 1:  # left-click → equip
                                        self.player.equip_item(clicked_item, self)
                                    else:  # right-click → action popup
                                        self.selected_inventory_item = clicked_item
                                        self.game_state = GameState.INVENTORY_MENU
                                return True

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
                        GRID_COLS = 5  # Must match COLS in ui_screens.py
                        n = len(self.player.inventory.items)
                        if n > 0:
                            idx = self.selected_inventory_index
                            if event.key in (pygame.K_LEFT, pygame.K_a):
                                self.selected_inventory_index = (idx - 1) % n
                            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                                self.selected_inventory_index = (idx + 1) % n
                            elif event.key in (pygame.K_UP, pygame.K_w):
                                new_idx = idx - GRID_COLS
                                self.selected_inventory_index = new_idx if new_idx >= 0 else idx
                            elif event.key in (pygame.K_DOWN, pygame.K_s):
                                new_idx = idx + GRID_COLS
                                self.selected_inventory_index = new_idx if new_idx < n else idx
                        if event.key == pygame.K_RETURN:
                            if 0 <= self.selected_inventory_index < n:
                                self.selected_inventory_item = self.player.inventory.items[self.selected_inventory_index]
                                self.game_state = GameState.INVENTORY_MENU
                                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
                        return True  # Consume event

                # --- Trade Interaction --- 
                if self.game_state in GameState.DUNGEON:
                    if event.key == pygame.K_f:
                        # --- Wall torch lighting (takes priority over NPC / quick-bar) ---
                        adjacent_has_torch = any(
                            (0 <= self.player.x + dx < self.game_map.width and
                             0 <= self.player.y + dy < self.game_map.height and
                             self.game_map.tiles[self.player.y + dy][self.player.x + dx].char == 'i' and
                             self.game_map.tiles[self.player.y + dy][self.player.x + dx].name == "Torch")
                            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                        )
                        if adjacent_has_torch:
                            self.try_light_wall_torch()
                            return True  # Consume event regardless (don't fall to quick-bar)
                        
                        # --- Prison door interaction ---
                        if handle_prison_door_interaction(self.player, self):
                            return True                        

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

                # --- Quick Bar Key Presses ---
                if self.game_state not in [GameState.CHARACTER_CREATION, GameState.CLASS_SELECTION, GameState.GAME_OVER, GameState.TRADE]:
                    if event.key == pygame.K_q:
                        if self.player.use_quick_bar_item('q', self):
                            action_taken = True
                        else:
                            # If use_quick_bar_item returns False, it means it couldn't be used,
                            # but it doesn't necessarily mean the player's turn is consumed.
                            # The message is already logged by use_quick_bar_item.
                            pass
                    elif event.key == pygame.K_f:
                        if self.player.use_quick_bar_item('f', self):
                            action_taken = True
                        else:
                            pass

                # --- Handle Character Creation Input ---
                if self.game_state == GameState.CHARACTER_CREATION:
                    print(f"DEBUG: In CHARACTER_CREATION state. Selected Race Index: {self.selected_class_index}")
                    if event.key in (pygame.K_UP, pygame.K_w):
                        self.selected_race_index = (self.selected_race_index - 1) % len(self.available_races)
                        self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
                        self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.selected_race_index = (self.selected_race_index + 1) % len(self.available_races)
                        self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
                        self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))
                    elif event.key == pygame.K_RETURN:
                        print("DEBUG: K_RETURN pressed in CHARACTER_CREATION")
                        self.finalize_race_selection() 
                        return True

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

                    abilities_list = list(self.player.abilities.values())


                    # For abilities:
                    if pygame.K_1 <= event.key <= pygame.K_9:
                        ability_index = event.key - pygame.K_1
                        if 0 <= ability_index < len(abilities_list):
                            ability_to_use = abilities_list[ability_index]
                            if self.game_state == GameState.DUNGEON:
                                if getattr(ability_to_use, "is_bonus_action", False) and self.player_bonus_action_used:
                                    self.message_log.add_message(
                                        f"{ability_to_use.name} is a bonus action and you have already used your bonus action this turn.",
                                        (255, 150, 0)
                                    )
                                elif ability_to_use.use(self.player, self):
                                    if self.game_state != GameState.TARGETING:
                                        if getattr(ability_to_use, "is_bonus_action", False):
                                            self.player_bonus_action_used = True
                                        else:
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
        input_text = input_text.lower()

        if self.game_state == GameState.TRADE:
            # Determine which merchant is active
            active_merchant = None
            if self._previous_game_state == GameState.TAVERN and self.merchant:
                active_merchant = self.merchant
            elif self._previous_game_state == GameState.DUNGEON and self.dungeon_merchant:
                active_merchant = self.dungeon_merchant

            if active_merchant:
                if input_text.startswith("buy "):
                    item_name = input_text[4:]
                    result = active_merchant.buy_item(self.player, item_name)
                    self.message_log.add_message(result, (255, 255, 255))
                elif input_text.startswith("sell "):
                    item_name = input_text[5:]
                    result = active_merchant.sell_item(self.player, item_name)
                    self.message_log.add_message(result, (255, 255, 255))
                else:
                    add_ambient_merchant_message = [
                        "The merchant squints at you: 'I only deal in proper trades. Say *buy <item>* or *sell <item>*.'",
                        "The trader frowns: 'That makes no sense to me, friend. Try *buy <item>* or *sell <item>* if you mean business.'",
                        "The merchant raises a brow: 'I’ll not play games. Speak plain: *buy <item>* or *sell <item>*.'",
                    ]
                    self.message_log.add_message(random.choice(add_ambient_merchant_message), (150, 150, 150))
            
            # After any trade attempt, revert state and hide input
            self.game_state = self._previous_game_state
            self.message_log.show_input_area = False
            self.message_log.current_input = ""
            return

        # Fallback for other states if needed
        self.message_log.show_input_area = False
        self.message_log.current_input = ""
        

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
            print("DEBUG: ability_in_use.execute_on_target returned True. Resetting state.")
            # If the ability successfully executed its effect, then reset targeting state.
            should_end_turn = not getattr(self.ability_in_use, "is_bonus_action", False)
            if not should_end_turn:
                self.player_bonus_action_used = True
            self._reset_targeting_state(end_turn=should_end_turn)
        else:
            print("DEBUG: ability_in_use.execute_on_target returned False. Staying in targeting mode.") # <--- ADD THIS
            # If execute_on_target returns False, it means the target was invalid for that ability
            # (e.g., Fire Bolt on empty tile, Misty Step on blocked tile). Stay in targeting mode.
            pass # Message already handled by ability.execute_on_target

    def _reset_targeting_state(self, end_turn=True):
        """Cleans up targeting-related state vars and optionally ends the player's turn."""
        self.game_state = self._previous_game_state # Revert to previous game state (DUNGEON/TAVERN)
        self.ability_in_use = None # Clear the ability reference
        self.targeting_ability_range = 0
        self.targeting_cursor_x = 0 # Reset cursor position
        self.targeting_cursor_y = 0
        self.player.current_action_state = None # <--- THIS IS THE CRITICAL FIX FOR MISTY STEP

        if end_turn:
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



    def get_interactable_item_at(self, x, y):
        """Checks if there's an interactable item (like a Potion or Chest) at the given coordinates."""
        for item in self.game_map.items_on_ground:
            # Check for any Item (including Potion, Weapon, Armor, Tools)
            # Exclude monsters, as they are not items
            if item.x == x and item.y == y and not isinstance(item, Monster):
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
        items_at_player_pos = [item for item in self.game_map.items_on_ground if item.x == self.player.x and item.y == self.player.y and not isinstance(item, Monster)]
        if items_at_player_pos:
            item_to_pick_up = items_at_player_pos[0]
            # Ensure it's not a Chest, as Chests are handled by their own 'open' method
            if isinstance(item_to_pick_up, Chest):
                return False # Let the chest opening logic handle this
            
            if item_to_pick_up.on_pickup(self.player, self):
                # Remove the item from the ground after successful pickup
                self.game_map.items_on_ground.remove(item_to_pick_up)
                self.player.update_throw_knife_ability()
                self.player.update_spellbook_abilities()
                self.player.update_thieves_tools_ability()
                self.player.update_guard_ability()
                self.player.update_holy_symbol_abilities()
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
            self.player.update_throw_knife_ability()
            self.player.update_spellbook_abilities()
            self.player.update_thieves_tools_ability()
            self.player.update_guard_ability()
            self.player.update_holy_symbol_abilities()
            self.selected_inventory_item.x = self.player.x
            self.selected_inventory_item.y = self.player.y
            self.game_map.items_on_ground.append(self.selected_inventory_item)
            self.message_log.add_message(f"You drop the {self.selected_inventory_item.name}.", self.selected_inventory_item.color)
            action_taken_in_menu = True
        elif key == pygame.K_ESCAPE or key == pygame.K_c:
            self.message_log.add_message("Action cancelled.", (150, 150, 150))
            action_taken_in_menu = False
        elif key == pygame.K_q: # New key for quick bar slot 'q'
            if self.player.equip_to_quick_bar(self.selected_inventory_item, 'q', self):
                self.player.update_throw_knife_ability()
                self.player.update_spellbook_abilities()
                self.player.update_thieves_tools_ability()
                self.player.update_guard_ability()
                self.player.update_holy_symbol_abilities()
                action_taken_in_menu = False
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name} to Quick Bar (Q).", (255, 100, 100))
        elif key == pygame.K_f: # New key for quick bar slot 'f'
            if self.player.equip_to_quick_bar(self.selected_inventory_item, 'f', self):
                self.player.update_throw_knife_ability()
                self.player.update_spellbook_abilities()
                self.player.update_thieves_tools_ability()
                self.player.update_guard_ability()
                self.player.update_holy_symbol_abilities()
                action_taken_in_menu = False
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name} to Quick Bar (F).", (255, 100, 100))



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

        # Add altar interaction check
        altar_at_pos = None
        for altar in self.game_map.altars:
            if altar.x == new_x and altar.y == new_y:
                altar_at_pos = altar
                break
            
        if altar_at_pos:
            interaction_result = altar_at_pos.interact(self.player, self)
            if interaction_result is True:
                self.player_has_acted = True
                return True
            elif interaction_result == 'already_used':
                pass
            else:
                return False

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
            # Prevent out-of-bounds movement before accessing the tile grid.
            if not (0 <= new_x < self.game_map.width and 0 <= new_y < self.game_map.height):
                self.message_log.add_message("You can't move there.", (255, 150, 0))
                return False

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
                elif isinstance(target_at_new_pos, SummonedEntity) and target_at_new_pos.owner == self.player:
                    # Swap positions with player's own summoned entity
                    target_at_new_pos.x, self.player.x = self.player.x, target_at_new_pos.x
                    target_at_new_pos.y, self.player.y = self.player.y, target_at_new_pos.y
                    self.message_log.add_message(f"You swap places with the {target_at_new_pos.name}!", (100, 255, 200))
                    self.update_fov()
                    self.camera.target_x = float(self.player.x)
                    self.camera.target_y = float(self.player.y)
                    self.player_has_acted = True
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
                            # Check if it's a summoned entity - if so, swap positions
                            if isinstance(entity, SummonedEntity):
                                entity.x, self.player.x = self.player.x, entity.x
                                entity.y, self.player.y = self.player.y, entity.y
                                self.message_log.add_message(f"You swap places with the {entity.name}!", (100, 255, 200))
                                self.player_has_acted = True
                                self.update_fov()
                                self.camera.target_x = float(self.player.x)
                                self.camera.target_y = float(self.player.y)
                                return True
                            else:
                                self.message_log.add_message(f"You can't move onto {entity.name}.", (255, 150, 0))
                                return False
                    else:
                        if getattr(entity, 'x', None) == new_x and getattr(entity, 'y', None) == new_y:
                            # Check if it's a summoned entity - if so, swap positions
                            if isinstance(entity, SummonedEntity):
                                entity.x, self.player.x = self.player.x, entity.x
                                entity.y, self.player.y = self.player.y, entity.y
                                self.message_log.add_message(f"You swap places with the {entity.name}!", (100, 255, 200))
                                self.player_has_acted = True
                                self.update_fov()
                                self.camera.target_x = float(self.player.x)
                                self.camera.target_y = float(self.player.y)
                                return True
                            else:
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
                        self.message_log.add_message(f"Perception Check: You notice a hidden {target_tile_obj.trap_instance.name}!", (0, 255, 255))
                        return True # Action taken (noticed trap)
                    else:
                        self.message_log.add_message(f"Perception Check: You fail to notice anything unusual.", (150, 150, 150))
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
                if mimic_entity.disguised or mimic_entity not in self.entities:
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
            f"Athletics Check: Rolled {d20_roll} + {athletics_bonus} = {skill_check_total} against DC {destruction_dc}.",
            (200, 200, 255)
        )
        
        if skill_check_total >= destruction_dc:
            self.message_log.add_message(f"You successfully smash the {target_tile.name}!", (0, 255, 0))
            self.game_map.tiles[y][x] = floor
            self.minimap_needs_redraw = True # Map changed, redraw minimap
            
            # --- NEW: 10% chance to drop a Lesser Healing Potion ---
            if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel 
                if random.random() < 0.75:
                    new_junk = wood_plank.__class__(
                        name=wood_plank.name,
                        char=wood_plank.char,
                        color=wood_plank.color,
                        description=wood_plank.description
                    )
                    new_junk.x = x
                    new_junk.y = y
                    self.game_map.items_on_ground.append(new_junk)
                elif random.random() < 0.21:
                    new_potion = lesser_healing_potion.__class__(
                        name=lesser_healing_potion.name,
                        char=lesser_healing_potion.char,
                        color=lesser_healing_potion.color,
                        effect_type=lesser_healing_potion.effect_type,
                        effect_value=lesser_healing_potion.effect_value,
                        description=lesser_healing_potion.description,
                        price=lesser_healing_potion.price
                    )
                    new_potion.x = x
                    new_potion.y = y
                    self.game_map.items_on_ground.append(new_potion)
                    self.message_log.add_message(f"A {new_potion.name} drops from the {target_tile.name}!", new_potion.color)
                elif random.random() < 0.3:
                    new_torch = torch.__class__(
                        name=torch.name,
                        char=torch.char,
                        color=torch.color,
                        description=torch.description,
                        price=torch.price
                    )
                    new_torch.x = x
                    new_torch.y = y
                    self.game_map.items_on_ground.append(new_torch)
                    self.message_log.add_message(f"A {new_torch.name} drops from the {target_tile.name}!", new_torch.color)
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
                elif random.random() < 0.27:
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
                elif random.random() < 0.5:
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
        
        # Use final_d20_roll for the attack calculation
        attack_modifier = self.player.attack_bonus
    
        # --- Altar Blessings and Curses ---
        blessing_of_strength = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, BlessingOfStrength):
                blessing_of_strength = effect
                break

        curse_of_weakness = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, CurseOfWeakness):
                curse_of_weakness = effect
                break


        # --- Check for PowerAttackBuff ---
        power_attack_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, PowerAttackBuff):
                power_attack_buff = effect
                break
            
        if power_attack_buff:
            attack_modifier += power_attack_buff.attack_modifier # Apply accuracy penalty
            self.message_log.add_message(f"Power Attack: -{abs(power_attack_buff.attack_modifier)} to hit.", (255, 165, 0))



        # --- Check for DivineStrikeBuff ---
        divine_strike_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, DivineStrikeBuff):
                divine_strike_buff = effect
                break

        if divine_strike_buff:
            attack_modifier += divine_strike_buff.base_attack_bonus_modifier # Apply attack bonus
            self.message_log.add_message(f"Divine Strike: +{divine_strike_buff.base_attack_bonus_modifier} to hit.", (255, 255, 0))

        # --- Check for PreciseStrikeBuff ---
        precise_strike_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, PreciseStrikeBuff):
                precise_strike_buff = effect
                break
            
        if precise_strike_buff:
            attack_modifier += precise_strike_buff.attack_bonus_modifier # Apply attack bonus
            self.message_log.add_message(f"Precise Strike: +{precise_strike_buff.attack_bonus_modifier} to hit.", (0, 255, 255))

        prepared_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, Prepared):
                prepared_buff = effect
                break

        if prepared_buff:
            self.message_log.add_message(f"Prepared: +{prepared_buff.attack_power_modifier} attack power.", (0, 255, 255))

        applied_toxins_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, AppliedToxins):
                applied_toxins_buff = effect
                break

        # --- Check for Hidden Status Effect ---
        hidden_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, Hidden):
                hidden_buff = effect
                break

        if hidden_buff:
            self.message_log.add_message("Your attack from hiding deals extra damage!", (255, 215, 0))         

            sneak_dice_count = 0

            if self.player.level >= 1:
                # Sneak Attack always starts at 1d6
                sneak_dice_count = 1 + ((self.player.level - 1) // 2)
                # Cap at 10d6 (level 19+)
                sneak_dice_count = min(sneak_dice_count, 10)
              
            advantage = True       


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
    
            for _ in range(total_dice_rolled):
                damage_rolls.append(random.randint(1, die_type))
    
            damage_dice_rolls_sum = sum(damage_rolls)
    
            # Construct the message part for dice rolls
            damage_message_dice_part = f"{total_dice_rolled}d{die_type} [{' + '.join(map(str, damage_rolls))}]"
    
            damage_modifier = self.player.attack_power
    
            if blessing_of_strength:
                damage_modifier += blessing_of_strength.damage_modifier
                self.message_log.add_message(f"Blessing of Strength: +{blessing_of_strength.damage_modifier} damage.", (0, 255, 255))

            if curse_of_weakness:
                damage_modifier += curse_of_weakness.damage_modifier # Note: This is negative
                self.message_log.add_message(f"Curse of Weakness: {curse_of_weakness.damage_modifier} damage.", (255, 0, 255))

            if power_attack_buff:
                damage_modifier += power_attack_buff.damage_modifier # Apply flat damage bonus
                self.message_log.add_message(f"Power Attack: +{power_attack_buff.damage_modifier} damage.", (255, 165, 0))
                if getattr(power_attack_buff, "extra_damage_dice", 0) > 0:
                    extra_dice_count = power_attack_buff.extra_damage_dice * (2 if is_critical_hit else 1)
                    extra_rolls = [random.randint(1, die_type) for _ in range(extra_dice_count)]
                    extra_sum = sum(extra_rolls)
                    damage_dice_rolls_sum += extra_sum
                    damage_message_dice_part += f" + {extra_dice_count}d{die_type} [{' + '.join(map(str, extra_rolls))}] (Power Attack)"
                    self.message_log.add_message(f"Power Attack adds {extra_dice_count}d{die_type} damage.", (255, 165, 0))
                # The buff should be consumed after one attack
                self.player.active_status_effects.remove(power_attack_buff) # Remove the buff
                self.message_log.add_message(f"Power Attack buff consumed.", (150, 150, 150))

            if divine_strike_buff:
                damage_modifier += divine_strike_buff.damage_modifier # Apply flat damage bonus
                self.message_log.add_message(f"Divine Strike: +{divine_strike_buff.damage_modifier} damage.", (255, 255, 0))
                if getattr(divine_strike_buff, "extra_damage_dice", 0) > 0:
                    extra_dice_count = divine_strike_buff.extra_damage_dice * (2 if is_critical_hit else 1)
                    extra_rolls = [random.randint(1, die_type) for _ in range(extra_dice_count)]
                    extra_sum = sum(extra_rolls)
                    damage_dice_rolls_sum += extra_sum
                    damage_message_dice_part += f" + {extra_dice_count}d{die_type} [{' + '.join(map(str, extra_rolls))}] (Divine Strike)"
                    self.message_log.add_message(f"Divine Strike adds {extra_dice_count}d{die_type} damage.", (255, 255, 0))
                # The buff should be consumed after one attack
                self.player.active_status_effects.remove(divine_strike_buff) # Remove the buff
                self.message_log.add_message(f"Divine Strike buff consumed.", (150, 150, 150))

            if prepared_buff:
                damage_modifier += prepared_buff.attack_power_modifier

            if applied_toxins_buff and hit_successful:
                poison_dice_count = applied_toxins_buff.poison_damage_dice * (2 if is_critical_hit else 1)
                poison_rolls = [random.randint(1, applied_toxins_buff.poison_die_type) for _ in range(poison_dice_count)]
                poison_sum = sum(poison_rolls)
                damage_dice_rolls_sum += poison_sum
                damage_message_dice_part += f" + {poison_dice_count}d{applied_toxins_buff.poison_die_type} [{' + '.join(map(str, poison_rolls))}] (Applied Toxins)"
                self.message_log.add_message(f"Applied Toxins deals +{poison_sum} poison damage.", (0, 255, 100))

            if hidden_buff:
                sneak_attack_rolls = []
                
                for _ in range(sneak_dice_count):
                    sneak_attack_rolls.append(random.randint(1, 6))
                sneak_attack_sum = sum(sneak_attack_rolls)
                damage_dice_rolls_sum += sneak_attack_sum
                damage_message_dice_part += f" + {sneak_dice_count}d6 [{' + '.join(map(str, sneak_attack_rolls))}] (Sneak Attack)"

                self.player.active_status_effects.remove(hidden_buff) # Remove the buff after one attack
                self.message_log.add_message(f"You are no longer hidden.", (150, 150, 150))


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
                xp_gained = target.die(game_instance, killer=self.player)
                self.player.gain_xp(xp_gained, game_instance)  # Use 'self' (player) here
                self.message_log.add_message(f"You gain {xp_gained} XP!", (100, 255, 100))  # Log the XP gained
                if target.name == 'Arasta' and self.current_level == 20:
                    self.handle_victory()
                    return
                if random.random() < 0.7:
                    self.add_ambient_combat_message()
            else:
                self.message_log.add_message(
                    f"{target.name} has {target.hp}/{target.max_hp} HP",
                    (255, 255, 0)
                )

        # Reveal if hidden
        if self.player.hidden_turns > 0:
            self.player.hidden_turns = 0
            hidden_buff = next((e for e in self.player.active_status_effects if isinstance(e, Hidden)), None)
            if hidden_buff:
                self.player.active_status_effects.remove(hidden_buff)
                hidden_buff.on_end(self.player, self)

        if not hit_successful:
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

        # self._torch_flicker_frame += 1
        # if self._torch_flicker_frame % 12 == 0:
        #     import random as _r
        #     # ember / candlelit tones
        #     r = 235 + _r.randint(-16, 10)
        #     g = 168 + _r.randint(-20, 8)
        #     b = 92  + _r.randint(-12, 6)

        #     # subtle brightness fluctuation
        #     a = 235 + _r.randint(-18, 0)

        #     self._torch_flicker_tint = (
        #         max(80, min(255, r)),
        #         max(80, min(255, g)),
        #         max(80, min(255, b)),
        #         max(180, min(255, a)),
        #     )     

        self.floating_texts = [text for text in self.floating_texts if text.update()]

        # NEW: If player is dead and game is not yet in GAME_OVER state, handle game over
        if self.player and not self.player.alive and self.game_state != GameState.GAME_OVER:
            self.handle_game_over()
            return # Stop further updates if game over is triggered


        if self.game_state == GameState.CHARACTER_CREATION:
            if self.fade_in_alpha > 0:
                self.fade_in_alpha -= self.fade_in_speed
                if self.fade_in_alpha < 0:
                    self.fade_in_alpha = 0
        if self.game_state == GameState.CLASS_SELECTION:
            if self.fade_in_alpha > 0:
                self.fade_in_alpha -= self.fade_in_speed
                if self.fade_in_alpha < 0:
                    self.fade_in_alpha = 0                                    

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
            elif self.death_screen_animation_phase == 4: # Fade-out initiated by 'R' press
                self.fade_out_alpha += self.fade_out_speed
                if self.fade_out_alpha >= 255:
                    self.fade_out_alpha = 255
                    # Fade-out complete, now transition to character creation
                    self.entities.clear()
                    self.player = None
                    self._game_over_displayed = False
                    self.death_screen_animation_phase = 0 # Reset for next death
                    self.death_screen_alpha = 0 # Reset for next death
                    self.death_screen_bg_alpha = 0 # Reset for next death
                    self.death_screen_subtext_alpha = 0 # Reset for next death
                    
                    self.game_state = GameState.CHARACTER_CREATION
                    self.start_character_creation()
                    
                    self.fade_in_alpha = 255
                    self.message_log.add_message("Welcome, new adventurer!", (0, 255, 0))                    
            return

        # --- NEW: Only process turns for active entities ---
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
                elif current_entity.alive and hasattr(current_entity, 'take_turn'):
                    # Process entity's turn (Monster, SummonedEntity, NPC, etc.)
                    if isinstance(current_entity, Monster) and hasattr(current_entity, 'is_active'):
                        if not current_entity.is_active:
                            # Skip inactive monsters
                            self.next_turn()
                            continue
                    # Call take_turn for any entity that has it
                    current_entity.take_turn(self.player, self.game_map, self)
                    # Entity has acted, advance turn.
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
            self.game_over_victory = False
            self.game_over_title = "YOU DIED"
            self.game_over_story_lines = []
            self.game_over_subtext = "Press R to Restart or Q to Quit"
            if self.player:
                self.player.die()

            self.death_screen_alpha = 0
            self.death_screen_bg_alpha = 0
            self.death_screen_subtext_alpha = 0
            self.death_screen_animation_phase = 0

        self.game_state = GameState.GAME_OVER

    def handle_victory(self):
        if not self._game_over_displayed:
            self._game_over_displayed = True
            self.game_over_victory = True
            self.game_over_title = "VICTORY"
            self.game_over_story_lines = [
                "Arasta collapses beneath your final strike, her webs unraveling into the cold air.",
                "You leave the dungeon as more than a desperate stranger — you leave as its breaker.",
                "The tavern's dim warmth was once a shelter from debt and curse; now it becomes a place of legend.",
                "Your name will be whispered by weary travelers as the one who toppled the spider queen."
            ]
            self.game_over_subtext = "Press R to Restart or Q to Quit"

            self.death_screen_alpha = 0
            self.death_screen_bg_alpha = 0
            self.death_screen_subtext_alpha = 0
            self.death_screen_animation_phase = 0

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
        screen_x_float, screen_y_float = self.camera.world_to_screen(x, y)
        draw_x = int(screen_x_float * config.TILE_SIZE)
        draw_y = int(screen_y_float * config.TILE_SIZE)
        rect = pygame.Rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)
        self.dirty_rects.append(rect)


    def render(self):
        """Main render method - draws everything"""
        # Clear the entire screen at the start of each frame
        self.screen.fill((0, 0, 0, 0))

        # --- Render the main game area (dungeon/tavern) to internal_surface ---
        self.internal_surface.fill((0, 0, 0, 0)) # Clear internal surface

        # Render map, items, entities, highlights, floating texts to internal_surface
        if self.game_state == GameState.CHARACTER_CREATION:
            self.render_character_creation_screen()
            if self.fade_in_alpha > 0:
                fade_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                fade_surface.fill((0, 0, 0, self.fade_in_alpha))
                self.screen.blit(fade_surface, (0, 0))
        elif self.game_state == GameState.CLASS_SELECTION:
            self.render_class_selection_screen() 
            if self.fade_in_alpha > 0:
                fade_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                fade_surface.fill((0, 0, 0, self.fade_in_alpha))
                self.screen.blit(fade_surface, (0, 0))                                 
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
            
            # Render altars
            if hasattr(self.game_map, 'altars'):
                for altar in self.game_map.altars:
                    if self.camera.is_in_viewport(altar.x, altar.y):
                        visibility_type = self.fov.get_visibility_type(altar.x, altar.y)

                        # Only render if visible or explored
                        if visibility_type in ['player', 'torch', 'darkvision', 'explored']:
                            screen_x_float, screen_y_float = self.camera.world_to_screen(altar.x, altar.y)
                            draw_x = screen_x_float * config.TILE_SIZE
                            draw_y = screen_y_float * config.TILE_SIZE

                            # Set color tint based on visibility
                            if visibility_type == 'player':
                                altar_color_tint = (115, 102, 92, 255)
                            elif visibility_type == 'torch':
                                altar_color_tint = (255, 170, 82, 255)
                            elif visibility_type == 'darkvision':
                                altar_color_tint = (72, 78, 86, 255)
                            elif visibility_type == 'explored':
                                altar_color_tint = (36, 30, 34, 255)
                            else:
                                continue  # Don't render if not visible
                            
                            graphics.draw_tile(self.internal_surface, draw_x, draw_y, altar.char, color_tint=altar_color_tint)            

            self.render_items_on_ground()
            self.render_tile_highlights()
            self.render_bloodstains()
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
            available_height = config.SCREEN_HEIGHT  # log is a transparent overlay

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

        if self.game_state == GameState.GAME_OVER and self.death_screen_animation_phase == 4:
            fade_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            fade_surface.fill((0, 0, 0, self.fade_out_alpha)) # Black overlay, increasing alpha
            self.screen.blit(fade_surface, (0, 0))
            pygame.display.flip() # Ensure this is drawn over everything
            return # Exit render function early during fade-out to prevent drawing underlying game

        # NEW: Render game over screen if in GAME_OVER state
        if self.game_state == GameState.GAME_OVER:
            self.render_game_over_screen()
            pygame.display.flip() # Ensure the screen updates
            return # Exit render function early to prevent further drawing

        fps_text = f"FPS: {int(self.fps)}"
        fps_surface = self.fps_font.render(fps_text, True, (255, 255, 255))  # White color
        self.screen.blit(fps_surface, (10, 10))  # Position at (10, 10) pixels from top-left

        
        pygame.display.update(self.dirty_rects)

        # --- Final Display Update ---
        # Use flip for full screen update, or update a combined rect for game area + UI panel
        # For simplicity and to eliminate flickering, let's try flip first.
        pygame.display.flip()

        self.dirty_rects.clear()


    def render_game_over_screen(self):
        # Render background overlay with fade-in alpha after the title text
        if self.death_screen_animation_phase >= 1:
            overlay_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            overlay_surface.fill((0, 0, 0, self.death_screen_bg_alpha))
            self.screen.blit(overlay_surface, (0, 0))

        # Render title text with fade-in alpha
        font = pygame.font.SysFont('consolas', 72, bold=True)
        title_color = (0, 255, 0) if self.game_over_victory else (255, 0, 0)
        text_surface = font.render(self.game_over_title, True, title_color)
        text_surface.set_alpha(self.death_screen_alpha)
        text_rect = text_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 40))
        self.screen.blit(text_surface, text_rect)

        # Render story lines for victory after background is visible
        if self.death_screen_animation_phase >= 2 and self.game_over_victory:
            font_small = pygame.font.SysFont('consolas', 24)
            y_offset = text_rect.bottom + 20
            for line in self.game_over_story_lines:
                story_surface = font_small.render(line, True, (220, 220, 220))
                story_surface.set_alpha(self.death_screen_subtext_alpha)
                story_rect = story_surface.get_rect(center=(self.screen.get_width() // 2, y_offset))
                self.screen.blit(story_surface, story_rect)
                y_offset += story_surface.get_height() + 8

        # Render subtext with fade-in alpha after background is visible
        if self.death_screen_animation_phase >= 2:
            font_small = pygame.font.SysFont('consolas', 24)
            subtext = font_small.render(self.game_over_subtext, True, (255, 255, 255))
            subtext.set_alpha(self.death_screen_subtext_alpha)
            subtext_rect = subtext.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() - 80))
            self.screen.blit(subtext, subtext_rect)
            

    def render_map_with_fov(self, full_redraw=False):
        if not hasattr(self, 'game_map') or self.game_map is None:
            return

        camera_x_int = int(self.camera.x)
        camera_y_int = int(self.camera.y)

        has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)          

        for y in range(camera_y_int, min(camera_y_int + self.camera.viewport_height + 1, self.game_map.height)):
            for x in range(camera_x_int, min(camera_x_int + self.camera.viewport_width + 1, self.game_map.width)):

                screen_x_float, screen_y_float = self.camera.world_to_screen(x, y)

                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE

                visibility_type = self.fov.get_visibility_type(x, y)

                tile = self.game_map.tiles[y][x]      

                # Set color tint based on visibility (applies to all tiles, including water) change FOV
                render_color_tint = None
                if visibility_type == 'player':
                    if has_torchlight:
                        render_color_tint = self._torch_flicker_tint
                    else:
                        render_color_tint = (115, 102, 92, 255)
                elif visibility_type == 'torch':
                    render_color_tint = self._torch_flicker_tint
                elif visibility_type == 'darkvision':
                    render_color_tint = (72, 78, 86, 255)
                elif visibility_type == 'explored':
                    render_color_tint = (36, 30, 34, 255)
                elif visibility_type == 'unexplored':
                    render_color_tint = (8, 6, 8, 255)  # Very dark tint for unexplored, but still render the tile
                    continue
                else:
                    continue  # Don't render if truly invisible

                # Draw the tile using the restored sprite-based draw_tile
                graphics.draw_tile(self.internal_surface, draw_x, draw_y, tile.char, color_tint=render_color_tint)

                # Handle special tiles (e.g., TrapTile, MimicTile - your existing logic)
                if isinstance(tile, TrapTile):
                    display_char = tile.get_display_char()
                    display_color = tile.get_display_color()
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, display_char, color_tint=render_color_tint) 

                if full_redraw:
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
    
                    has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)
    
                    # KEPT: Visibility-based tinting (dimming for FOV effects)
                    entity_color_tint = None
                    if visibility_type == 'player':
                        if has_torchlight:
                            entity_color_tint = self._torch_flicker_tint  # Dimmer tint when torchlight active
                        else:
                            entity_color_tint = (115, 102, 92, 255)
                    elif visibility_type == 'torch':
                        entity_color_tint = self._torch_flicker_tint
                    elif visibility_type == 'darkvision':
                        entity_color_tint = (72, 78, 86, 255)
                    elif visibility_type == 'explored':
                        entity_color_tint = (36, 30, 34, 255)
                    elif visibility_type == 'unexplored':
                        entity_color_tint = (8, 6, 8, 255)
    
                    footprint_size = getattr(entity, 'footprint_size', 1)
                    tile_size_override = config.TILE_SIZE * footprint_size if footprint_size > 1 else None
    
                    # Determine flip_x only for player
                    flip_x = False
                    if entity == self.player:
                        flip_x = not self.player.facing_right
    
                    # Check for submersion (player or swimming monsters on water)
                    entity_tile = self.game_map.tiles[entity.y][entity.x]
                    is_submerged = (entity == self.player or (hasattr(entity, 'can_swim') and entity.can_swim)) and is_water_tile(entity_tile)
    
                    if is_submerged:
                        # Get the base sprite for the entity char
                        base_sprite = graphics.get_tile_surface(entity.char)
                        if base_sprite is None:
                            print(f"ERROR: No sprite for entity char '{entity.char}'")
                            continue  # Skip rendering this frame
                        
                        base_sprite = base_sprite.convert_alpha()
                        
                        # Apply flip if needed (only for player)
                        sprite_surface = base_sprite.copy()
                        if flip_x:
                            sprite_surface = pygame.transform.flip(sprite_surface, True, False)
                        
                        # Apply visibility tint directly to the sprite
                        if entity_color_tint:
                            tinted_sprite = sprite_surface.copy()
                            tinted_sprite.fill(entity_color_tint, special_flags=pygame.BLEND_RGBA_MULT)
                            sprite_surface = tinted_sprite
    
                        # Create top-half clip rect (source rect for blit)
                        half_height = config.TILE_SIZE // 2
                        clip_rect = pygame.Rect(0, 0, config.TILE_SIZE, half_height)
                        
                        # Blit only the top half of the tinted sprite
                        self.internal_surface.blit(sprite_surface, (draw_x, draw_y), clip_rect)
                        
                        # Add ripple sprite in bottom half
                        ripple_sprite = graphics.get_tile_surface('~')  # Use '~' sprite for ripple
                        if ripple_sprite:
                            ripple_sprite = ripple_sprite.convert_alpha()
                            ripple_sprite = pygame.transform.scale(ripple_sprite, (config.TILE_SIZE, half_height))
                            # Apply visibility tint to ripple
                            if entity_color_tint:
                                ripple_tinted = ripple_sprite.copy()
                                ripple_tinted.fill(entity_color_tint, special_flags=pygame.BLEND_RGBA_MULT)
                                ripple_sprite = ripple_tinted
                            self.internal_surface.blit(ripple_sprite, (draw_x, draw_y + half_height))
                    else:
                        # Normal rendering for non-submerged entities
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
        

    def render_bloodstains(self):
        """Renders bloodstains on the map."""
        if not hasattr(self, 'game_map') or self.game_map is None:
            return
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
        for bloodstain in self.bloodstains:
            # Only render if within camera viewport
            if self.camera.is_in_viewport(bloodstain.x, bloodstain.y):
                screen_x_float, screen_y_float = self.camera.world_to_screen(bloodstain.x, bloodstain.y)
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= draw_y < map_render_height):
                    # Bloodstains should appear dimmer in explored areas
                    visibility_type = self.fov.get_visibility_type(bloodstain.x, bloodstain.y)
                    color_tint = None
                    if visibility_type == 'player':
                        color_tint = (235, 0, 0, 150) # Slightly transparent red
                    elif visibility_type == 'torch':
                        color_tint = (185, 0, 0, 120)
                    elif visibility_type == 'darkvision':
                        color_tint = (72, 0, 0, 100)
                    elif visibility_type == 'explored':
                        color_tint = (36, 0, 0, 80) # Very dim in explored areas
                    else: # Unexplored, don't draw
                        continue
                    # Draw a semi-transparent red square or a specific bloodstain character
                    # You can use a custom character like '.' or ',' for bloodstains
                    # Or draw a semi-transparent rectangle over the tile
                    graphics.draw_tile(
                        self.internal_surface,
                        draw_x,
                        draw_y,
                        bloodstain.char, # Use the bloodstain's character
                        color_tint=color_tint
                    )
                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)

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
                    

                    has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)

                    item_color_tint = None
                    if visibility_type == 'player':
                        if has_torchlight:
                            item_color_tint = self._torch_flicker_tint # Dimmer tint when torchlight active
                        else:
                            item_color_tint = (115, 102, 92, 255)  
                    elif visibility_type == 'torch':
                        item_color_tint = self._torch_flicker_tint
                    elif visibility_type == 'darkvision':
                        item_color_tint = (72, 78, 86, 255)
                    elif visibility_type == 'explored':
                        item_color_tint = (36, 30, 34, 255)
                    elif visibility_type == 'unexplored':
                        item_color_tint = (8, 6, 8, 255) 
                    
                    # Always draw floor under items, as map rendering might have drawn a decorative tile
                    # --- MODIFIED: Pass float draw_x, draw_y to graphics.draw_tile ---
                    # graphics.draw_tile(self.internal_surface, draw_x, draw_y, floor.char, color_tint=item_color_tint)
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, item.char, color_tint=item_color_tint)


                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)                    

   
    def render_character_creation_screen(self):
        surf = self.screen
        SW, SH = surf.get_width(), surf.get_height()

        _BG     = (10,   8,  10)   # abyss black
        _PANEL  = (18,  14,  18)   # obsidian stone

        _BORDER = (52,  42,  46)   # dark iron border

        _GOLD   = (164, 124,  52)  # tarnished relic gold
        _ACCENT = (96,  38,  38)   # dried blood crimson

        _DIM    = (112, 102,  96)  # dusty parchment
        _NORMAL = (188, 178, 168)  # aged bone
        _BRIGHT = (232, 224, 210)  # candlelit ivory

        _GREEN  = (74, 122,  76)   # swamp herb green
        _CYAN   = (72, 132, 136)   # spectral teal
        _RED    = (148,  42,  42)  # coagulated blood

        def _ff(sz, bold=False):
            try:    return pygame.font.SysFont("consolas", sz, bold=bold)
            except: return pygame.font.Font(None, sz + 2)

        fTitle = _ff(22, bold=True)
        fSec   = _ff(18, bold=True)
        fN     = _ff(16)
        fSm    = _ff(14)

        surf.fill(_BG)

        PAD = 20
        panel = pygame.Rect(PAD, PAD, SW - PAD*2, SH - PAD*2)
        pygame.draw.rect(surf, _PANEL, panel, border_radius=8)
        pygame.draw.rect(surf, _BORDER, panel, 1, border_radius=8)

        title_bar = pygame.Rect(PAD, PAD, SW - PAD*2, 42)
        pygame.draw.rect(surf, (22, 18, 28), title_bar, border_radius=8)
        pygame.draw.rect(surf, _ACCENT, title_bar, 1, border_radius=8)
        ts = fTitle.render("CHOOSE YOUR RACE", True, _GOLD)
        surf.blit(ts, (SW // 2 - ts.get_width() // 2, PAD + 10))

        content_y = PAD + 52
        content_h = SH - content_y - PAD - 36

        COL_PAD = 10
        col_w   = (SW - PAD*2 - COL_PAD*4) // 3
        col1_x  = PAD + COL_PAD
        col2_x  = col1_x + col_w + COL_PAD
        col3_x  = col2_x + col_w + COL_PAD

        for cx in (col1_x, col2_x, col3_x):
            r = pygame.Rect(cx - 4, content_y, col_w + 8, content_h)
            pygame.draw.rect(surf, (20, 18, 26), r, border_radius=6)
            pygame.draw.rect(surf, _BORDER, r, 1, border_radius=6)

        selected_race      = self.available_races[self.selected_race_index]
        selected_class_cls = self.available_classes[self.selected_class_index]
        race_str   = selected_race.name.replace(" ", "")
        class_str  = selected_class_cls.__name__
        player_char, player_color = self.race_class_visuals.get(
            (race_str, class_str), ('@', (200, 200, 200))
        )

        # ── COLUMN 1: Race list ──────────────────────────────────────────────
        y1 = content_y + 10
        pygame.draw.rect(surf, _ACCENT, (col1_x, y1 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render("RACES", True, _BRIGHT), (col1_x + 8, y1))
        pygame.draw.line(surf, _BORDER, (col1_x, y1 + fSec.get_linesize() + 3),
                         (col1_x + col_w, y1 + fSec.get_linesize() + 3), 1)
        y1 += fSec.get_linesize() + 10

        for i, race in enumerate(self.available_races):
            sel    = (i == self.selected_race_index)
            row_h  = fN.get_linesize() + 10
            row_r  = pygame.Rect(col1_x - 2, y1, col_w + 4, row_h)
            if sel:
                pygame.draw.rect(surf, (28, 38, 55), row_r, border_radius=4)
                pygame.draw.rect(surf, _ACCENT, row_r, 1, border_radius=4)
                pygame.draw.rect(surf, _GOLD, (col1_x - 2, y1 + 4, 3, row_h - 8))
            rs  = fN.render(race.name, True, _GOLD if sel else _NORMAL)
            surf.blit(rs, (col1_x + 10, y1 + row_h // 2 - rs.get_height() // 2))
            if race.darkvision_radius > 0:
                dv = fSm.render(f"Darkvision {race.darkvision_radius}", True, _CYAN)
                surf.blit(dv, (col1_x + col_w - dv.get_width() - 6,
                               y1 + row_h // 2 - dv.get_height() // 2))
            y1 += row_h + 4

        # ── COLUMN 2: Character doll ─────────────────────────────────────────
        cx2 = col2_x + col_w // 2
        y2  = content_y + 18

        pygame.draw.rect(surf, _ACCENT, (col2_x, y2 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render("PREVIEW", True, _BRIGHT), (col2_x + 8, y2))
        pygame.draw.line(surf, _BORDER, (col2_x, y2 + fSec.get_linesize() + 3),
                         (col2_x + col_w, y2 + fSec.get_linesize() + 3), 1)
        y2 += fSec.get_linesize() + 14

        AVATAR = 96
        try:
            base   = graphics.get_tile_surface(player_char)
            avatar = pygame.transform.scale(base, (AVATAR, AVATAR)) if base else None
        except Exception:
            avatar = None

        av_x = cx2 - AVATAR // 2
        av_y = y2
        r2, g2, b2 = player_color

        glow_s = pygame.Surface((AVATAR + 16, AVATAR + 16), pygame.SRCALPHA)
        pygame.draw.rect(glow_s, (r2, g2, b2, 40), (0, 0, AVATAR+16, AVATAR+16), border_radius=10)
        pygame.draw.rect(glow_s, (r2, g2, b2, 100), (0, 0, AVATAR+16, AVATAR+16), 2, border_radius=10)
        surf.blit(glow_s, (av_x - 8, av_y - 8))

        if avatar:
            tinted = avatar.copy()
            surf.blit(tinted, (av_x, av_y))
        else:
            pygame.draw.rect(surf, player_color, (av_x, av_y, AVATAR, AVATAR), border_radius=6)

        pygame.draw.rect(surf, _BORDER, (av_x - 3, av_y - 3, AVATAR + 6, AVATAR + 6), 1, border_radius=7)
        y2 += AVATAR + 12

        lbl = fN.render(f"{selected_race.name}  ·  {class_str}", True, player_color)
        surf.blit(lbl, (cx2 - lbl.get_width() // 2, y2))
        y2 += fN.get_linesize() + 14

        hit_die_map  = {"Fighter": 10, "Rogue": 8, "Wizard": 6, "Cleric": 8}
        hit_die      = hit_die_map.get(class_str, 8)
        est_hp       = hit_die + 2
        BAR_W = col_w - 20
        BAR_H = 10
        bx    = col2_x + 10

        def _mini_bar(label, val, max_val, fc, yy):
            ls3 = fSm.render(label, True, _DIM)
            surf.blit(ls3, (bx, yy))
            yy += ls3.get_height() + 3
            pygame.draw.rect(surf, (30, 30, 40), (bx, yy, BAR_W, BAR_H), border_radius=3)
            fw = max(0, int(BAR_W * min(val / max_val, 1.0)))
            if fw: pygame.draw.rect(surf, fc, (bx, yy, fw, BAR_H), border_radius=3)
            pygame.draw.rect(surf, _BORDER, (bx, yy, BAR_W, BAR_H), 1, border_radius=3)
            vs3 = fSm.render(str(val), True, _BRIGHT)
            surf.blit(vs3, (bx + BAR_W//2 - vs3.get_width()//2, yy + BAR_H//2 - vs3.get_height()//2))
            return yy + BAR_H + 8

        hp_col = _RED if est_hp < 7 else (_GOLD if est_hp < 10 else _GREEN)
        y2 = _mini_bar(f"Est. HP  (d{hit_die})", est_hp, 14, hp_col, y2)
        y2 = _mini_bar("Base AC", 10, 20, _CYAN, y2)

        if selected_race.damage_resistances:
            rs3 = fSm.render("Resist: " + ", ".join(selected_race.damage_resistances), True, _GREEN)
            surf.blit(rs3, (cx2 - rs3.get_width()//2, y2))
            y2 += rs3.get_height() + 4
        if selected_race.darkvision_radius > 0:
            dv2 = fSm.render(f"Darkvision  {selected_race.darkvision_radius} tiles", True, _CYAN)
            surf.blit(dv2, (cx2 - dv2.get_width()//2, y2))

        # ── COLUMN 3: Race details ────────────────────────────────────────────
        y3 = content_y + 10

        def _hdr3(label, yy):
            pygame.draw.rect(surf, _ACCENT, (col3_x, yy + 2, 3, fSec.get_linesize() - 2))
            surf.blit(fSec.render(label, True, _BRIGHT), (col3_x + 8, yy))
            pygame.draw.line(surf, _BORDER, (col3_x, yy + fSec.get_linesize() + 3),
                             (col3_x + col_w, yy + fSec.get_linesize() + 3), 1)
            return yy + fSec.get_linesize() + 10

        def _wrap3(text, color, yy):
            words = text.split()
            lines2, cur = [], []
            for w in words:
                test = " ".join(cur + [w])
                if fSm.size(test)[0] <= col_w - 8:
                    cur.append(w)
                else:
                    if cur: lines2.append(" ".join(cur))
                    cur = [w]
            if cur: lines2.append(" ".join(cur))
            for line in lines2:
                surf.blit(fSm.render(line, True, color), (col3_x + 4, yy))
                yy += fSm.get_linesize() + 2
            return yy + 4

        def _trait(label, value, color, yy):
            surf.blit(fSm.render(label, True, _DIM), (col3_x + 4, yy))
            vs4 = fSm.render(str(value), True, color)
            surf.blit(vs4, (col3_x + col_w - vs4.get_width() - 4, yy))
            pygame.draw.line(surf, _BORDER,
                             (col3_x + 4, yy + fSm.get_linesize() + 2),
                             (col3_x + col_w - 4, yy + fSm.get_linesize() + 2), 1)
            return yy + fSm.get_linesize() + 6

        y3 = _hdr3(f"{selected_race.name.upper()}  DETAILS", y3)
        y3 = _wrap3(selected_race.description, _NORMAL, y3)
        y3 += 6
        y3 = _hdr3("TRAITS", y3)
        if selected_race.darkvision_radius > 0:
            y3 = _trait("Darkvision", f"{selected_race.darkvision_radius} tiles", _CYAN, y3)
        if selected_race.damage_resistances:
            y3 = _trait("Resistances", ", ".join(selected_race.damage_resistances), _GREEN, y3)
        if selected_race.skill_proficiencies:
            y3 = _trait("Skill Prof.", ", ".join(selected_race.skill_proficiencies), _NORMAL, y3)
        if selected_race.weapon_proficiencies:
            y3 = _trait("Weapon Prof.", ", ".join(selected_race.weapon_proficiencies), _NORMAL, y3)
        if selected_race.armor_proficiencies:
            y3 = _trait("Armor Prof.", ", ".join(selected_race.armor_proficiencies), _NORMAL, y3)
        if not any([selected_race.darkvision_radius, selected_race.damage_resistances,
                    selected_race.skill_proficiencies, selected_race.weapon_proficiencies,
                    selected_race.armor_proficiencies]):
            surf.blit(fSm.render("No special traits.", True, _DIM), (col3_x + 4, y3))

        # ── Instructions ─────────────────────────────────────────────────────
        iy = SH - PAD - fSm.get_linesize() - 8
        inst = fSm.render("W / S  or  UP / DOWN  navigate      Enter  confirm", True, _DIM)
        surf.blit(inst, (SW // 2 - inst.get_width() // 2, iy))

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
        surf = self.screen
        SW, SH = surf.get_width(), surf.get_height()

        _BG     = (10,   8,  10)   # abyss black
        _PANEL  = (18,  14,  18)   # obsidian stone

        _BORDER = (52,  42,  46)   # dark iron

        _GOLD   = (164, 124,  52)  # tarnished relic gold
        _ACCENT = (96,  38,  38)   # dried blood crimson

        _DIM    = (112, 102,  96)  # dusty parchment
        _NORMAL = (188, 178, 168)  # aged bone
        _BRIGHT = (232, 224, 210)  # candlelit ivory

        _GREEN  = (74, 122,  76)   # swamp herb green
        _CYAN   = (72, 132, 136)   # spectral teal
        _RED    = (148,  42,  42)  # coagulated blood

        _ORANGE = (176,  96,  42)  # ember flame

        def _ff(sz, bold=False):
            try:    return pygame.font.SysFont("consolas", sz, bold=bold)
            except: return pygame.font.Font(None, sz + 2)

        fTitle = _ff(22, bold=True)
        fSec   = _ff(18, bold=True)
        fN     = _ff(16)
        fSm    = _ff(14)

        surf.fill(_BG)

        PAD = 20
        panel = pygame.Rect(PAD, PAD, SW - PAD*2, SH - PAD*2)
        pygame.draw.rect(surf, _PANEL, panel, border_radius=8)
        pygame.draw.rect(surf, _BORDER, panel, 1, border_radius=8)

        title_bar = pygame.Rect(PAD, PAD, SW - PAD*2, 42)
        pygame.draw.rect(surf, (22, 18, 28), title_bar, border_radius=8)
        pygame.draw.rect(surf, _ACCENT, title_bar, 1, border_radius=8)
        ts = fTitle.render("CHOOSE YOUR CLASS", True, _GOLD)
        surf.blit(ts, (SW // 2 - ts.get_width() // 2, PAD + 10))

        content_y = PAD + 52
        content_h = SH - content_y - PAD - 36

        COL_PAD = 10
        col_w   = (SW - PAD*2 - COL_PAD*4) // 3
        col1_x  = PAD + COL_PAD
        col2_x  = col1_x + col_w + COL_PAD
        col3_x  = col2_x + col_w + COL_PAD

        for cx in (col1_x, col2_x, col3_x):
            r = pygame.Rect(cx - 4, content_y, col_w + 8, content_h)
            pygame.draw.rect(surf, (20, 18, 26), r, border_radius=6)
            pygame.draw.rect(surf, _BORDER, r, 1, border_radius=6)

        selected_race      = self.available_races[self.selected_race_index]
        selected_class_cls = self.available_classes[self.selected_class_index]
        race_str   = selected_race.name.replace(" ", "")
        class_str  = selected_class_cls.__name__
        player_char, player_color = self.race_class_visuals.get(
            (race_str, class_str), ('@', (200, 200, 200))
        )
        class_info = self._get_class_details(selected_class_cls)

        # class colour theme per class
        class_color_map = {
            "Fighter": (180,  80,  80),
            "Rogue":   ( 80, 160,  80),
            "Wizard":  ( 80, 130, 220),
            "Cleric":  (220, 200,  60),
        }
        class_color = class_color_map.get(class_str, _GOLD)

        # ── COLUMN 1: Class list ─────────────────────────────────────────────
        y1 = content_y + 10
        pygame.draw.rect(surf, _ACCENT, (col1_x, y1 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render("CLASSES", True, _BRIGHT), (col1_x + 8, y1))
        pygame.draw.line(surf, _BORDER, (col1_x, y1 + fSec.get_linesize() + 3),
                         (col1_x + col_w, y1 + fSec.get_linesize() + 3), 1)
        y1 += fSec.get_linesize() + 10

        hit_die_map  = {"Fighter": 10, "Rogue": 8, "Wizard": 6, "Cleric": 8}
        for i, cls in enumerate(self.available_classes):
            sel   = (i == self.selected_class_index)
            cname = cls.__name__
            row_h = fN.get_linesize() + 10
            row_r = pygame.Rect(col1_x - 2, y1, col_w + 4, row_h)
            ccol  = class_color_map.get(cname, _GOLD)
            if sel:
                pygame.draw.rect(surf, (28, 38, 55), row_r, border_radius=4)
                pygame.draw.rect(surf, _ACCENT, row_r, 1, border_radius=4)
                pygame.draw.rect(surf, ccol, (col1_x - 2, y1 + 4, 3, row_h - 8))
            ns = fN.render(cname, True, ccol if sel else _NORMAL)
            surf.blit(ns, (col1_x + 10, y1 + row_h // 2 - ns.get_height() // 2))
            hd = fSm.render(f"d{hit_die_map.get(cname, 8)}", True, _DIM)
            surf.blit(hd, (col1_x + col_w - hd.get_width() - 6,
                           y1 + row_h // 2 - hd.get_height() // 2))
            y1 += row_h + 4

        # ── COLUMN 2: Character doll ─────────────────────────────────────────
        cx2 = col2_x + col_w // 2
        y2  = content_y + 18

        pygame.draw.rect(surf, _ACCENT, (col2_x, y2 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render("PREVIEW", True, _BRIGHT), (col2_x + 8, y2))
        pygame.draw.line(surf, _BORDER, (col2_x, y2 + fSec.get_linesize() + 3),
                         (col2_x + col_w, y2 + fSec.get_linesize() + 3), 1)
        y2 += fSec.get_linesize() + 14

        AVATAR = 96
        try:
            base   = graphics.get_tile_surface(player_char)
            avatar = pygame.transform.scale(base, (AVATAR, AVATAR)) if base else None
        except Exception:
            avatar = None

        av_x = cx2 - AVATAR // 2
        av_y = y2
        r2, g2, b2 = player_color

        glow_s = pygame.Surface((AVATAR + 16, AVATAR + 16), pygame.SRCALPHA)
        pygame.draw.rect(glow_s, (r2, g2, b2, 40), (0, 0, AVATAR+16, AVATAR+16), border_radius=10)
        pygame.draw.rect(glow_s, (r2, g2, b2, 100), (0, 0, AVATAR+16, AVATAR+16), 2, border_radius=10)
        surf.blit(glow_s, (av_x - 8, av_y - 8))

        if avatar:
            tinted = avatar.copy()
            surf.blit(tinted, (av_x, av_y))
        else:
            pygame.draw.rect(surf, player_color, (av_x, av_y, AVATAR, AVATAR), border_radius=6)

        pygame.draw.rect(surf, _BORDER, (av_x - 3, av_y - 3, AVATAR + 6, AVATAR + 6), 1, border_radius=7)
        y2 += AVATAR + 10

        # race · class label in class colour
        lbl = fN.render(f"{selected_race.name}  ·  {class_str}", True, class_color)
        surf.blit(lbl, (cx2 - lbl.get_width() // 2, y2))
        y2 += fN.get_linesize() + 12

        # starting weapon/armor icons
        icon_chars = {
            "Fighter": ["shs", "rsh"],
            "Rogue":   ["dgr", "pda"],
            "Wizard":  ["spb", "!"],
            "Cleric":  ["shs", "cha"],
        }
        icons = icon_chars.get(class_str, [])
        ICON  = 36
        ix    = cx2 - (len(icons) * (ICON + 6)) // 2
        for ic in icons:
            try:
                base2 = graphics.get_tile_surface(ic)
                if base2:
                    s2 = pygame.transform.scale(base2, (ICON, ICON))
                    surf.blit(s2, (ix, y2))
            except Exception:
                pass
            pygame.draw.rect(surf, _BORDER, (ix - 2, y2 - 2, ICON + 4, ICON + 4), 1, border_radius=3)
            ix += ICON + 8
        y2 += ICON + 10

        # stat bars
        est_hp = hit_die_map.get(class_str, 8) + 2
        BAR_W  = col_w - 20
        BAR_H  = 10
        bx     = col2_x + 10

        def _mini_bar(label, val, max_val, fc, yy):
            surf.blit(fSm.render(label, True, _DIM), (bx, yy))
            yy += fSm.get_linesize() + 3
            pygame.draw.rect(surf, (30, 30, 40), (bx, yy, BAR_W, BAR_H), border_radius=3)
            fw = max(0, int(BAR_W * min(val / max_val, 1.0)))
            if fw: pygame.draw.rect(surf, fc, (bx, yy, fw, BAR_H), border_radius=3)
            pygame.draw.rect(surf, _BORDER, (bx, yy, BAR_W, BAR_H), 1, border_radius=3)
            vs3 = fSm.render(str(val), True, _BRIGHT)
            surf.blit(vs3, (bx + BAR_W//2 - vs3.get_width()//2, yy + BAR_H//2 - vs3.get_height()//2))
            return yy + BAR_H + 8

        hp_col = _RED if est_hp < 7 else (_GOLD if est_hp < 10 else _GREEN)
        y2 = _mini_bar(f"Est. HP  ({class_info['hit_die']})", est_hp, 14, hp_col, y2)
        y2 = _mini_bar("Primary Ability", 1, 1, class_color, y2)
        # primary ability label
        pa = fSm.render(class_info["primary_ability"], True, class_color)
        surf.blit(pa, (cx2 - pa.get_width() // 2, y2))

        # ── COLUMN 3: Class details ───────────────────────────────────────────
        y3 = content_y + 10

        def _hdr3(label, yy):
            pygame.draw.rect(surf, _ACCENT, (col3_x, yy + 2, 3, fSec.get_linesize() - 2))
            surf.blit(fSec.render(label, True, _BRIGHT), (col3_x + 8, yy))
            pygame.draw.line(surf, _BORDER, (col3_x, yy + fSec.get_linesize() + 3),
                             (col3_x + col_w, yy + fSec.get_linesize() + 3), 1)
            return yy + fSec.get_linesize() + 10

        def _wrap3(text, color, yy):
            words = text.split()
            lines2, cur = [], []
            for w in words:
                test = " ".join(cur + [w])
                if fSm.size(test)[0] <= col_w - 8:
                    cur.append(w)
                else:
                    if cur: lines2.append(" ".join(cur))
                    cur = [w]
            if cur: lines2.append(" ".join(cur))
            for line in lines2:
                surf.blit(fSm.render(line, True, color), (col3_x + 4, yy))
                yy += fSm.get_linesize() + 2
            return yy + 4

        def _row3(label, value, color, yy):
            surf.blit(fSm.render(label, True, _DIM), (col3_x + 4, yy))
            vs4 = fSm.render(str(value), True, color)
            surf.blit(vs4, (col3_x + col_w - vs4.get_width() - 4, yy))
            pygame.draw.line(surf, _BORDER,
                             (col3_x + 4, yy + fSm.get_linesize() + 2),
                             (col3_x + col_w - 4, yy + fSm.get_linesize() + 2), 1)
            return yy + fSm.get_linesize() + 6

        y3 = _hdr3(f"{class_str.upper()}  DETAILS", y3)
        y3 = _wrap3(class_info["description"], _NORMAL, y3)
        y3 += 6
        y3 = _hdr3("KEY FEATURES", y3)
        y3 = _row3("Hit Die",          class_info["hit_die"],          class_color, y3)
        y3 = _row3("Primary Ability",  class_info["primary_ability"],  class_color, y3)
        if class_info["saving_throws"]:
            y3 = _row3("Saving Throws", ", ".join(class_info["saving_throws"]), _NORMAL, y3)
        if class_info["armor_proficiencies"]:
            y3 = _row3("Armor Prof.",   ", ".join(class_info["armor_proficiencies"]), _NORMAL, y3)
        if class_info["weapon_proficiencies"]:
            y3 = _row3("Weapon Prof.",  ", ".join(class_info["weapon_proficiencies"]), _NORMAL, y3)

        if class_info.get("starting_equipment"):
            y3 += 4
            y3 = _hdr3("STARTING GEAR", y3)
            for eq_item in class_info["starting_equipment"]:
                y3 = _wrap3(f"· {eq_item}", _DIM, y3)

        # ── Instructions ─────────────────────────────────────────────────────
        iy = SH - PAD - fSm.get_linesize() - 8
        inst = fSm.render("W / S  or  UP / DOWN  navigate      Enter  confirm", True, _DIM)
        surf.blit(inst, (SW // 2 - inst.get_width() // 2, iy))

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
            },
            "Cleric": {
                "description": "A priestly champion who wields divine magic in service of a higher power. Clerics can heal wounds, turn undead, and call down divine wrath.",
                "hit_die": "1d8",
                "primary_ability": "Wisdom",
                "saving_throws": ["Wisdom", "Charisma"],
                "armor_proficiencies": ["Light", "Medium", "Shields"],
                "weapon_proficiencies": ["Simple"],
                "starting_equipment": ["A mace", "Scale mail", "A light crossbow and 20 bolts", "A priest's pack", "A shield emblazoned with the symbol of their deity"]
            },
            "Sorcerer": {
                "description": "A spellcaster who draws on inherent magic from a powerful bloodline. Sorcerers have a limited number of spells but can cast them with great flexibility.",
                "hit_die": "1d6",
                "primary_ability": "Charisma",
                "saving_throws": ["Constitution", "Charisma"],
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
        render_inventory_screen(self)
            
    def render_inventory_menu_popup(self):
        render_inventory_menu_popup(self)

    def render_character_menu(self):
        render_character_menu(self)


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

    def _unequip_slot(self, slot_key):
        """Unequip item from the given slot key using the player's own unequip_item method."""
        slot_map = {
            "weapon":   "equipped_weapon",
            "armor":    "equipped_armor",
            "off_hand": "equipped_off_hand",
            "acc1":     "equipped_accessory1",
            "acc2":     "equipped_accessory2",
            "helmet":   "equipped_helmet",
            "boots":    "equipped_boots",
            "focus":    "equipped_focus",
        }
        attr = slot_map.get(slot_key)
        if not attr:
            return
        item = getattr(self.player, attr, None)
        if item is None:
            self.message_log.add_message("Nothing equipped in that slot.", (150, 150, 150))
            return
        self.player.unequip_item(item, self)




    def draw_ui(self):
        draw_sidebar(self)

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

        for bloodstain in self.bloodstains:
            if (bloodstain.x, bloodstain.y) in self.fov.explored: # Only show on minimap if explored
                bloodstain_minimap_x = offset_x + bloodstain.x * actual_minimap_tile_size
                bloodstain_minimap_y = offset_y + bloodstain.y * actual_minimap_tile_size
                pygame.draw.rect(
                    self.minimap_surface,
                    (100, 0, 0), # Dark red for minimap bloodstains
                    (bloodstain_minimap_x, bloodstain_minimap_y, actual_minimap_tile_size, actual_minimap_tile_size)
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