import pygame
import random
import config


class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"
    INVENTORY = "inventory"
    INVENTORY_MENU = "inventory_menu"
    CHARACTER_MENU = "character_menu"
    TARGETING = "targeting"  
    CHARACTER_CREATION = "character_creation"
    CLASS_SELECTION = "class_selection"


from core.fov import FOV
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from entities.player import Player, Fighter, Rogue, Wizard

# NEW: Import all monster classes
from entities.monster import (
    Monster, Mimic, GiantRat, Ooze, Goblin, GoblinArcher, Skeleton,
    SkeletonArcher, Orc, Centaur, CentaurArcher, Troll, Lizardfolk, 
    LizardfolkArcher, GiantSpider, Beholder, LargeOoze, DragonWhelp
)

from entities.tavern_npcs import create_tavern_npcs
from entities.dungeon_npcs import DungeonHealer
from entities.tavern_npcs import NPC
from entities.races import Human, HillDwarf, DrowElf # NEW: Import DrowElf
from core.abilities import SecondWind, PowerAttack, CunningAction, Evasion, FireBolt, MistyStep
from core.message_log import MessageBox
from core.status_effects import PowerAttackBuff, CunningActionDashBuff, EvasionBuff
from items.items import Potion, Weapon, Armor, Chest
from core.pathfinding import astar
from world.tile import floor, MimicTile
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
        
        self.smoothing_factor = 0.2 # Adjust this value (e.g., 0.05 for very smooth, 0.3 for faster)

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
        
        self.internal_surface = None
        self.inventory_ui_surface = None
        self.camera = None
        self.message_log = None
        
        self._recalculate_dimensions() 
        
        self._init_fonts()


        # NEW: Start in character creation state
        self.game_state = GameState.CHARACTER_CREATION 
        self._previous_game_state = GameState.CHARACTER_CREATION # Or None, depending on desired flow
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
            
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 100))
        
        
        self.floating_texts = [] # <--- ADD THIS LINE


        # REMOVED: Player creation moved to character_creation_start
        self.player = None 
        
        self.selected_inventory_item = None


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


    MONSTER_SPAWN_TIERS = {
        # Level range: [List of monster classes that can spawn]
        (1, 3): [GiantSpider, Ooze],
        (4, 5): [Goblin, GoblinArcher, Ooze],
        (6, 7): [Skeleton, SkeletonArcher, Orc],
        (8, 9): [Lizardfolk,LizardfolkArcher],
        (10, 12): [Centaur, CentaurArcher, Troll],
        (13, 15): [Troll, Orc, GiantSpider, LargeOoze], 
        (16, 17): [LargeOoze, Beholder], 
        (18, 99): [DragonWhelp], # High level, adjust max level as needed
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
        
        # REMOVED: self.player.has_darkvision = self.player.race.has_darkvision (handled by apply_traits)
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
        self.game_map = GameMap(40, 24)
        self.fov = FOV(self.game_map)
        self.door_position = generate_tavern(self.game_map)
        
        start_x, start_y = self.game_map.width // 2, self.game_map.height // 2 + 2
        
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
        
        self.npcs = create_tavern_npcs(self.game_map, self.door_position)
        self.entities = [self.player] + self.npcs
        self.turn_order = []
        self.current_turn_index = 0
        self.update_fov()
        
        self.message_log.add_message("=== WELCOME TO THE PRANCING PONY TAVERN ===", (255, 215, 0))
        self.message_log.add_message("Walk to the door (+) and press any movement key to enter the dungeon!", (150, 150, 255))


    def generate_level(self, level_number, spawn_on_stairs_up=False):
        self.game_state = GameState.DUNGEON
        self._previous_game_state = GameState.DUNGEON
        self.current_level = level_number
        self.max_level_reached = max(self.max_level_reached, level_number)
        
        self.game_map = GameMap(80, 45)
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
        
        monsters_per_level = min(2 + level_number, len(rooms) - 1)
        monster_rooms = rooms[1:monsters_per_level + 1]

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
                self.message_log.add_message(f"A {monster.name} appears!", (255, 150, 0))

        if len(rooms) > 2 and random.random() < 0.6:
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
                    self.message_log.add_message(f"You sense a benevolent presence nearby...", (0, 255, 255))
                    self.message_log.add_message(f"A {dungeon_healer.name} is at ({healer_x}, {healer_y})", (0, 255, 255))
                    healer_spawned = True
                    break
            
            if not healer_spawned:
                self.message_log.add_message("DEBUG: Dungeon Healer could not find a suitable spawn spot.", (100, 100, 100))

        item_templates = [
            Potion(name="Healing Potion", char="!", color=(255, 0, 0), description="Restores a small amount of health.", effect_type="heal", effect_value=8),
            Weapon(name="Short Sword", char="/", color=(150, 150, 150), description="A basic short sword.", damage_dice="1d6", damage_modifier=0, attack_bonus=0),
            Armor(name="Leather Armor", char="[", color=(139, 69, 19), description="Light leather armor.", ac_bonus=1)
        ]

        item_spawn_chance = 0.9

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
                    self.message_log.add_message(f"You spot a {item_to_add.name} on the ground.", item_to_add.color)

        self.turn_order = [e for e in self.entities if not (isinstance(e, Mimic) and e.disguised)]
        for entity in self.turn_order:
            entity.roll_initiative()
        
        self.turn_order = sorted(self.turn_order, key=lambda e: e.initiative, reverse=True)
        self.current_turn_index = 0
        self.update_fov()
        
        self.message_log.add_message(f"=== ENTERED DUNGEON LEVEL {level_number} ===", (0, 255, 255))        
        if hasattr(self, 'stairs_positions'):
            self.message_log.add_message(f"Stairs down at {self.stairs_positions.get('down')}", (150, 150, 255))

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
                if isinstance(entity, DungeonHealer):
                    if (abs(self.player.x - entity.x) <= 1 and
                        abs(self.player.y - entity.y) <= 1 and
                        (abs(self.player.x - entity.x) + abs(self.player.y - entity.y)) == 1):
                        return entity
        return None

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
        if self.game_state == GameState.TAVERN:
            self.fov.visible_sources.clear()
            self.fov.explored.clear()
            for y in range(self.game_map.height):
                for x in range(self.game_map.width):
                    self.fov.visible_sources[(x, y)] = 'player'
                    self.fov.explored.add((x, y))
        else:
            self.fov.visible_sources.clear()
            # Pass player.darkvision_radius to compute_fov
            self.fov.compute_fov(self.player.x, self.player.y, radius=8, light_source_type='player', player_darkvision_radius=self.player.darkvision_radius)
            for tx, ty in self.torch_light_sources:
                self.fov.compute_fov(tx, ty, radius=5, light_source_type='torch')

    def get_current_entity(self):
        if not self.turn_order or self.game_state == GameState.TAVERN:
            return self.player
        if self.current_turn_index >= len(self.turn_order):
            self.current_turn_index = 0
        return self.turn_order[self.current_turn_index]

    def next_turn(self):
        if self.game_state == GameState.TAVERN:
            if random.random() < 0.3:
                ambient_msgs = [
                    "The torch flickers, casting long shadows...",
                    "Distant drips echo through the stone halls..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (150, 150, 150))
            return
        
        # Get the entity whose turn it *just was* or *is currently* before advancing the index
        current_acting_entity = self.get_current_entity()
        
        # Process status effects for the entity that just completed its turn (or was about to)
        # This ensures effects tick down AFTER their actions, but before the next entity's turn.
        if current_acting_entity:
            current_acting_entity.process_status_effects(self)

        self.cleanup_entities()

        # If after cleanup, there are no entities left (e.g., all monsters died)
        if not self.turn_order:
            if self.player.alive:
                self.turn_order = [self.player] # Ensure player is in turn order
                self.current_turn_index = 0
                self.player_has_acted = False # Reset for player's next turn
                self.update_fov()
            return # No more turns to process if no entities

        # Advance the turn index to the next entity
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        
        # Get the entity whose turn it is now (after advancing the index)
        current = self.get_current_entity() 

        # If it's the player's turn, reset their action flag and update FOV
        if current == self.player:
            self.update_fov()
            self.player_has_acted = False # This is correctly reset for player's turn
            if random.random() < 0.25:
                ambient_msgs = [
                    "The dungeon emits an eerie glow...",
                    "Something shuffles in the darkness..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (180, 180, 180))
        # If it's a monster's turn, it will be handled by the update loop in Game.update()


    def cleanup_entities(self):
        # Store the entity whose turn it *was* or *is about to be*
        entity_whose_turn_it_was = None
        if self.turn_order and 0 <= self.current_turn_index < len(self.turn_order):
            entity_whose_turn_it_was = self.turn_order[self.current_turn_index]
        # Filter out dead entities from the main entities list
        self.entities = [e for e in self.entities if e.alive]
        
        # Rebuild the turn_order list with only alive entities
        new_turn_order = []
        for entity in self.turn_order:
            if entity.alive:
                new_turn_order.append(entity)
        self.turn_order = new_turn_order
        
        # If the player is the only one left, ensure they are in turn_order
        if not self.turn_order and self.player.alive:
            self.turn_order = [self.player]
            self.current_turn_index = 0
            return # Nothing else to do if only player remains
        # Adjust current_turn_index based on who was supposed to act
        if entity_whose_turn_it_was and entity_whose_turn_it_was in self.turn_order:
            # If the entity whose turn it was is still alive, maintain its position
            self.current_turn_index = self.turn_order.index(entity_whose_turn_it_was)
        else:
            # If the entity whose turn it was died or was removed,
            # move the index back one to compensate for the next_turn increment,
            # or wrap around if it was the last entity.
            # This ensures the *next* entity in the sequence gets its turn.
            self.current_turn_index = (self.current_turn_index - 1 + len(self.turn_order)) % len(self.turn_order)
            # If the list became empty, this would cause an error, but we handle that above.
            # If the list is not empty, this will point to the entity that is now at the "previous" spot.
            # next_turn() will then increment it to the correct "next" entity.
        # Ensure index is within bounds after cleanup
        if self.current_turn_index >= len(self.turn_order):
            self.current_turn_index = 0 # Reset if somehow out of bounds (e.g., all entities died except player)


    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._recalculate_dimensions()
                self.render()            

            if event.type == pygame.KEYDOWN:
                print(f"  DEBUG KEYDOWN event: {pygame.key.name(event.key)} (value: {event.key})")
                
                # --- NEW: Handle Character Creation Input ---
                if self.game_state == GameState.CHARACTER_CREATION:
                   if self.game_state == GameState.CHARACTER_CREATION:
                       if event.key == pygame.K_UP:
                           self.selected_race_index = (self.selected_race_index - 1) % len(self.available_races)
                           self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
                           self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))
                       elif event.key == pygame.K_DOWN:
                           self.selected_race_index = (self.selected_race_index + 1) % len(self.available_races)
                           self.message_log.add_message(f"Current Race: {self.available_races[self.selected_race_index].name}", (255, 255, 255))
                           self.message_log.add_message(self.available_races[self.selected_race_index].description, (150, 150, 150))
                       elif event.key == pygame.K_RETURN:
                           self.finalize_race_selection() 
                       return True  # Consume event so no other input is processed

                if self.game_state == GameState.CLASS_SELECTION:
                    print(f"DEBUG: In CLASS_SELECTION state. Selected Class Index: {self.selected_class_index}")
                    if event.key == pygame.K_UP:
                        print("DEBUG: K_UP pressed in CLASS_SELECTION")
                        self.selected_class_index = (self.selected_class_index - 1) % len(self.available_classes)
                        self.message_log.add_message(f"Current Class: {self.available_classes[self.selected_class_index].__name__}", (255, 255, 255))
                        self.message_log.add_message("A brief description of the class will go here.", (150, 150, 150))
                    elif event.key == pygame.K_DOWN:
                        print("DEBUG: K_DOWN pressed in CLASS_SELECTION")
                        self.selected_class_index = (self.selected_class_index + 1) % len(self.available_classes)
                        self.message_log.add_message(f"Current Class: {self.available_classes[self.selected_class_index].__name__}", (255, 255, 255))
                        self.message_log.add_message("A brief description of the class will go here.", (150, 150, 150))
                    elif event.key == pygame.K_RETURN:
                        print("DEBUG: K_RETURN pressed in CLASS_SELECTION")
                        self.finalize_character_creation()
                    return True


                # --- Always accessible menus ---
                if event.key == pygame.K_i:
                    # Store the state *before* any menu or targeting was active
                    # This is crucial for returning to the correct game state after closing menus.
                    if self.game_state not in [GameState.INVENTORY, GameState.INVENTORY_MENU, GameState.CHARACTER_MENU, GameState.TARGETING]:
                        self._previous_game_state = self.game_state 
                    # If currently in TARGETING state, cancel it first
                    if self.game_state == GameState.TARGETING:
                        self.message_log.add_message("Targeting cancelled (Inventory opened).", (150, 150, 150))
                        self.ability_in_use = None # Clear the ability
                        self.player_has_acted = False # Player didn't act if cancelled
                        self.player.current_action_state = None # Clear any pending action state
                        # IMPORTANT: Do NOT set _previous_game_state here. It was already set above
                        # to the state *before* targeting. This ensures we return to DUNGEON/TAVERN.
                    
                    if self.game_state == GameState.INVENTORY: # If already in inventory, close it
                        self.game_state = self._previous_game_state
                        self.message_log.add_message("Closing Inventory.", (100, 200, 255))
                        self.selected_inventory_item = None
                    elif self.game_state == GameState.INVENTORY_MENU: # If in inventory menu, go back to main inventory
                        self.game_state = GameState.INVENTORY
                        self.selected_inventory_item = None
                        self.message_log.add_message("Returning to Inventory.", (100, 200, 255))
                    else: # If not in inventory, open it
                        self.game_state = GameState.INVENTORY
                        self.message_log.add_message("Opening Inventory...", (100, 200, 255))
                    return True # Consume event, don't process other game states                
                
                # Handle 'C' key for Character Menu
                if event.key == pygame.K_c:
                    # Store the state *before* any menu or targeting was active
                    # This is crucial for returning to the correct game state after closing menus.
                    if self.game_state not in [GameState.INVENTORY, GameState.INVENTORY_MENU, GameState.CHARACTER_MENU, GameState.TARGETING]:
                        self._previous_game_state = self.game_state 
                    # If currently in TARGETING state, cancel it first
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


                # --- Handle input based on game state ---
                # These blocks should only be entered if the game_state is specifically that menu
                # or if it's the main game (DUNGEON/TAVERN)
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
                    # handle_targeting_input will call execute_targeted_ability, which then calls next_turn.
                    # If targeting is cancelled, we want to fall through to normal movement.
                    # If targeting is confirmed, it will call next_turn and we can return True.
                    if self.game_state != GameState.TARGETING: # If state changed (i.e., targeting was cancelled or executed)
                        # Do NOT return True immediately. Let the rest of handle_events process the input
                        # if the state is now DUNGEON/TAVERN.
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
                    if event.key in (pygame.K_UP, pygame.K_w):
                        dy = -3
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        dy = 3
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        dx = -3
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        dx = 3
                    elif event.key == pygame.K_ESCAPE:
                        self.player.current_action_state = None
                        self.player.dash_active = False
                        self.message_log.add_message("Dash movement cancelled.", (150, 150, 150))
                        continue
                    else:
                        self.message_log.add_message("You are Dashing. Press a movement key or ESC to cancel.", (255, 150, 0))
                        continue

                    if dx != 0 or dy != 0:
                        target_x = self.player.x + dx 
                        target_y = self.player.y + dy 
                        
                        
                        if self.game_map.is_walkable(target_x, target_y):
                            self.player.x = target_x
                            self.player.y = target_y
                            self.message_log.add_message("You Dash forward!", (100, 255, 100))
                            action_taken = True
                        else:
                            target_x_1 = self.player.x + dx
                            target_y_1 = self.player.y + dy
                            if self.game_map.is_walkable(target_x_1, target_y_1):
                                self.player.x = target_x_1
                                self.player.y = target_y_1
                                self.message_log.add_message("You Dash forward but hit an obstacle!", (255, 150, 0))
                                action_taken = True
                            else:
                                self.message_log.add_message("You cannot Dash forward due to an obstacle!", (255, 150, 0))
                                action_taken = False
                        
                        self.player.dash_active = False
                        self.player.current_action_state = None
                        continue

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
                        if self.game_state == GameState.TAVERN:
                            npc = self.check_npc_interaction()
                            if npc:
                                self.message_log.add_message(f"{npc.name}: {npc.get_dialogue()}", (200, 200, 255))
                                action_taken = True
                        elif self.game_state == GameState.DUNGEON:
                            interactable_item = self.get_interactable_item_at(self.player.x, self.player.y)
                            if interactable_item:
                                if isinstance(interactable_item, Mimic):
                                    interactable_item.reveal(self)
                                    action_taken = True
                                elif isinstance(interactable_item, Chest):
                                    interactable_item.open(self.player, self)
                                    action_taken = True
                                else:
                                    self.message_log.add_message("You can't interact with that item.", (150, 150, 150))
                            else:
                                target = self.get_adjacent_target()
                                if target:
                                    if isinstance(target, Monster):
                                        self.handle_player_attack(target)
                                        action_taken = True
                                    elif isinstance(target, DungeonHealer):
                                        target.offer_rest(self.player, self)
                                        action_taken = True
                                    else:
                                        self.message_log.add_message(f"You can't interact with {target.name} that way.", (150, 150, 150))
                                else:
                                    action_taken = self.handle_item_pickup()

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
        """Handles input when in GameState.TARGETING (FireBolt, etc.)"""
        dx, dy = 0, 0  # Cursor movement directions
        # Handle cursor movement
        if key in (pygame.K_UP, pygame.K_w, pygame.K_k):  # Allow Vim-style 'k' for up
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

            # Keep cursor within map bounds
            if (0 <= new_x < self.game_map.width and 
                0 <= new_y < self.game_map.height):
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

        # Check Line of Sight (if applicable for the ability)
        # For simplicity, let's assume all targeted abilities require LOS for now.
        # You might want to add a flag to Ability class if some don't.
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
        Basic line of sight check using a simplified Bresenham-like approach.
        Checks if there are any sight-blocking tiles between (x1, y1) and (x2, y2).
        """
        # If start or end is blocked, no LOS
        if self.game_map.tiles[y1][x1].block_sight or self.game_map.tiles[y2][x2].block_sight:
            return False

        # Simple case: same tile
        if x1 == x2 and y1 == y2:
            return True

        # Use a simple step-by-step check
        points = []
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        current_x, current_y = x1, y1

        while True:
            points.append((current_x, current_y))
            if current_x == x2 and current_y == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                current_x += sx
            if e2 < dx:
                err += dx
                current_y += sy
        
        # Check all points along the line (excluding start and end)
        for px, py in points[1:-1]: # Exclude start and end points
            if self.game_map.tiles[py][px].block_sight:
                return False
        return True

    def get_interactable_item_at(self, x, y):
        """Checks if there's an interactable item (like a Chest or Mimic) at the given coordinates."""
        for item in self.game_map.items_on_ground:
            if (isinstance(item, Chest) or isinstance(item, Mimic)) and item.x == x and item.y == y:
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
            if item_to_pick_up.on_pickup(self.player, self):
                return True
            else:
                return False
        else:
            self.message_log.add_message("Nothing to pick up here.", (150, 150, 150))
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
            if entity.x == x and entity.y == y and entity != self.player and entity.alive:
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
                    self.handle_player_attack(target_at_new_pos)  # Player attacks monster
                    return True  # Action taken
                elif isinstance(target_at_new_pos, DungeonHealer):
                    target_at_new_pos.offer_rest(self.player, self)
                    return True
                else:
                    self.message_log.add_message(f"You can't attack {target_at_new_pos.name}.", (255, 150, 0))
                    return False

            # --- Step 4: Handle movement to an empty, walkable tile ---
            if self.game_map.is_walkable(new_x, new_y):
                original_player_x, original_player_y = self.player.x, self.player.y
                self.player.x = new_x
                self.player.y = new_y

                # --- NEW: Update camera target immediately after player moves ---
                self.camera.target_x = float(self.player.x)
                self.camera.target_y = float(self.player.y)
                
                # --- Opportunity Attack Check ---
                # Iterate through monsters that were adjacent before the move
                for monster in monsters_adjacent_before_move:
                    # Check if the monster is still adjacent to the player's *new* position
                    is_still_adjacent_to_monster = (abs(self.player.x - monster.x) <= 1 and abs(self.player.y - monster.y) <= 1)
                    
                    # If the monster was adjacent AND is no longer adjacent after the move,
                    # it gets an opportunity attack.
                    if not is_still_adjacent_to_monster:
                        self.message_log.add_message(f"The {monster.name} makes an Opportunity Attack!", (255, 100, 0))
                        monster.attack(self.player, self) # Monster attacks the player
                        # Important: If the player dies from an OA, the game state should reflect that.
                        if not self.player.alive:
                            return True # Player died, action taken, end turn.
                self.update_fov()
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
            return True
        else:
            self.message_log.add_message(f"You fail to smash the {target_tile.name}. It's tougher than it looks!", (255, 100, 100))
            return False
    

    def handle_player_attack(self, target, advantage=False, disadvantage=False):
        if not target.alive:
            return

        # Determine the actual d20 roll based on advantage/disadvantage
        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20) # Always roll a second for simplicity
        final_d20_roll = roll1
        roll_message_part = f"a d20: {roll1}"
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
            f"You roll {roll_message_part} + {attack_modifier} (Attack Bonus) = {attack_roll_total}",
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
                f"Your attack ({attack_roll_total}) hits the {target.name} (AC {target.armor_class})!",
                f"You connect with the {target.name}!",
                f"A solid blow lands on the {target.name}!",
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
                f"You roll {damage_message_dice_part} + {damage_modifier} (Attack Power) = {damage_total} damage!",
                (255, 200, 100)
            )

            damage_dealt = target.take_damage(damage_total, self, damage_type='physical') 

            self.message_log.add_message(
                f"You hit the {target.name} for {damage_dealt} damage!",
                (255, 100, 100)
            )

            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0), y_speed=0.6)
            self.floating_texts.append(damage_text)


            if not target.alive:
                xp_gained = target.die()
                self.player.gain_xp(xp_gained, self)
                self.message_log.add_message(
                    f"The {target.name} dies! [+{xp_gained} XP]",
                    (100, 255, 100)
                )
                if random.random() < 0.7:
                    self.add_ambient_combat_message()
            else:
                self.message_log.add_message(
                    f"{target.name} has {target.hp}/{target.max_hp} HP",
                    (255, 255, 0)
                )
        else:
            miss_messages = [
                f"Your attack ({attack_roll_total}) misses the {target.name} (AC {target.armor_class})!",
                f"You swing wildly and miss the {target.name}!",
                f"The {target.name} deftly dodges your attack!",
                f"Your weapon glances harmlessly off the {target.name}!"
            ]
            self.message_log.add_message(random.choice(miss_messages), (200, 200, 200))

            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            self.floating_texts.append(miss_text)



    def add_ambient_combat_message(self):
        messages = [
            "The smell of blood fills the air...",
            "Silence returns to the dungeon...",
            "Your weapon drips with monster blood..."
        ]
        self.message_log.add_message(random.choice(messages), (170, 170, 170))

    def update(self, dt):

        initial_floating_texts_count = len(self.floating_texts) # <--- ADD THIS
        self.floating_texts = [text for text in self.floating_texts if text.update()]        
        if len(self.floating_texts) != initial_floating_texts_count: # <--- ADD THIS
            print(f"DEBUG: FloatingTexts updated. Removed {initial_floating_texts_count - len(self.floating_texts)} expired texts. New list size: {len(self.floating_texts)}") # <--- ADD THIS

        # NEW: Only update camera and process turns if player exists and game is in an active state
        if self.player and (self.game_state == GameState.DUNGEON or self.game_state == GameState.TAVERN):
            self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
            
        
        if not self.player: # If player hasn't been created yet (e.g., in character creation)
            return # Do nothing else in update
        if not self.player.alive:
            if not hasattr(self, '_game_over_displayed'):
                death_messages = [
                    "Your journey ends here, adventurer. The dungeon claims another soul.",
                    "The light fades from your eyes. Darkness embraces you.",
                    "You fought bravely, but the dungeon proved too strong. Rest now.",
                    "The dungeon's embrace is cold and final. You have fallen."
                ]
                chosen_death_message = random.choice(death_messages)
                self.message_log.add_message(chosen_death_message, (255, 0, 0))
                self._game_over_displayed = True
            return
        
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
            print(f"DEBUG: It's {current.name}'s turn. Calling take_turn().") # <--- ADD THIS
            current.take_turn(self.player, self.game_map, self)
            print(f"DEBUG: {current.name}'s turn ended. Calling next_turn().") # <--- ADD THIS
            self.next_turn()
        else:
            pass # No active entity or entity is dead.
        

    def handle_window_resize(self):
        old_scale = self.scale
        
        self.scale_x = self.screen.get_width() / INTERNAL_WIDTH
        self.scale_y = self.screen.get_height() / INTERNAL_HEIGHT
        self.scale = min(self.scale_x, self.scale_y)
        
        if abs(old_scale - self.scale) > 0.1:
            self.internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
            self.font = pygame.font.SysFont('consolas', int(INTERNAL_HEIGHT/50))

    def render(self):
        """Main render method - draws everything"""
        self.screen.fill((0, 0, 0))
        self.internal_surface.fill((0, 0, 0))

        self.inventory_ui_surface.fill((0,0,0,0))
        if self.game_state == GameState.CHARACTER_CREATION: # NEW: Character Creation Render
            self.render_character_creation_screen()
            self.screen.blit(self.inventory_ui_surface, (0, 0)) # Use inventory_ui_surface for overlay
        elif self.game_state == GameState.CLASS_SELECTION: 
            self.render_class_selection_screen()
            self.screen.blit(self.inventory_ui_surface, (0, 0))
        elif self.game_state == GameState.INVENTORY:
            self.render_inventory_screen() 
            self.screen.blit(self.inventory_ui_surface, (0, 0))
        elif self.game_state == GameState.INVENTORY_MENU:
            self.render_inventory_screen() 
            self.screen.blit(self.inventory_ui_surface, (0, 0))
            self.render_inventory_menu_popup()
        elif self.game_state == GameState.CHARACTER_MENU:
            self.render_character_menu()
            self.screen.blit(self.inventory_ui_surface, (0, 0))
        else: # This block handles DUNGEON and TAVERN, and now TARGETING
            # --- NEW: Camera Update Logic for Targeting State ---
            if self.game_state == GameState.TARGETING:
                # In targeting mode, camera follows the targeting cursor
                self.camera.update(self.targeting_cursor_x, self.targeting_cursor_y, self.game_map.width, self.game_map.height)
            else:
                # Otherwise, camera follows the player (normal dungeon/tavern view)
                self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
            # --- END NEW CAMERA LOGIC ---

            self.render_map_with_fov()
            self.render_items_on_ground()
            self.render_entities()

            # <--- THIS IS THE CRITICAL LOOP ---
            for text_obj in self.floating_texts: # <--- ADD THIS LOOP
                text_obj.draw(self.internal_surface, self.camera) # Draw on internal surface                  


            if self.game_state == GameState.TARGETING:
                screen_x, screen_y = self.camera.world_to_screen(
                    self.targeting_cursor_x, 
                    self.targeting_cursor_y
                )

                # Check if we're targeting a monster or destructible
                target_type = None
                target_entity = self.get_target_at(self.targeting_cursor_x, self.targeting_cursor_y)
                if isinstance(target_entity, Monster):
                    target_type = "monster"
                elif (tile := self.game_map.tiles[self.targeting_cursor_y][self.targeting_cursor_x]) and tile.destructible:
                    target_type = "destructible"

                # Set cursor color based on target type
                cursor_color = (
                    (255, 100, 100) if target_type == "monster" else  # Red for monsters
                    (255, 200, 100) if target_type == "destructible" else  # Yellow for objects
                    (100, 100, 255)  # Blue for empty tiles
                )

                # Draw cursor rect (more visible than just an outline)
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
            
            available_width = config.GAME_AREA_WIDTH
            available_height = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
            
            internal_surface_aspect_ratio = config.INTERNAL_GAME_AREA_PIXEL_WIDTH / config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
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
        
        # Only draw UI if player exists (after character creation)
        if self.player: 
            self.draw_ui()
        self.message_log.render(self.screen)
        
        pygame.display.flip()


    def render_map_with_fov(self):
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
        
        # --- FIX: Cast camera.x and camera.y to int for range() loops ---
        camera_x_int = int(self.camera.x)
        camera_y_int = int(self.camera.y)

        for y in range(camera_y_int, min(camera_y_int + self.camera.viewport_height + 1, self.game_map.height)):
            for x in range(camera_x_int, min(camera_x_int + self.camera.viewport_width + 1, self.game_map.width)):
                screen_x_float, screen_y_float = self.camera.world_to_screen(x, y)
                
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE                
                
                #if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                #   0 <= draw_y < map_render_height):
                    
                visibility_type = self.fov.get_visibility_type(x, y)
                if visibility_type == 'unexplored':
                    continue
                
                tile = self.game_map.tiles[y][x]
                
                # --- NEW LOGIC HERE ---
                # Check if there's an item or entity at this exact spot
                item_at_pos = next((item for item in self.game_map.items_on_ground if item.x == x and item.y == y), None)
                entity_at_pos = next((entity for entity in self.entities if entity.x == x and entity.y == y), None)
                # If there's an item or entity (that's not disguised as a tile), draw the floor instead of the tile's char
                # Mimics are special: if disguised, they are handled as tiles, so we draw their disguise char.
                # If revealed, they are entities, and we draw floor + entity.
                draw_tile_char = tile.char
                if item_at_pos and not (isinstance(item_at_pos, Mimic) and item_at_pos.disguised):
                    draw_tile_char = floor.char # Draw floor under the item
                elif entity_at_pos and entity_at_pos != self.player and not (isinstance(entity_at_pos, Mimic) and entity_at_pos.disguised):
                    draw_tile_char = floor.char # Draw floor under the entity (excluding player, who is drawn later)
                elif entity_at_pos == self.player: # Always draw floor under player
                    draw_tile_char = floor.char
                
                render_color_tint = None
                if visibility_type == 'player':
                    render_color_tint = None
                elif visibility_type == 'torch':
                    render_color_tint = (128, 128, 128, 255)
                elif visibility_type == 'darkvision': # NEW: Darkvision tint
                    render_color_tint = (90, 90, 90, 255) # Slightly darker than torch, but still visible
                elif visibility_type == 'explored':
                    render_color_tint = (60, 60, 60, 255)

                graphics.draw_tile(self.internal_surface, draw_x, draw_y, draw_tile_char, color_tint=render_color_tint)                        
                    

    def render_entities(self):
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for entity in self.entities:
            if isinstance(entity, Mimic) and entity.disguised:
                continue 
            
            visibility_type = self.fov.get_visibility_type(entity.x, entity.y)
            
            # The is_in_viewport check is still useful for broad culling
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y) and \
               (visibility_type == 'player' or visibility_type == 'torch' or visibility_type == 'explored' or visibility_type == 'darkvision'):
                
                # --- MODIFIED: Get float screen coordinates ---
                screen_x_float, screen_y_float = self.camera.world_to_screen(entity.x, entity.y)
                
                # --- MODIFIED: Calculate pixel draw positions using floats ---
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE
                
                # The pixel bounds check is still good
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= draw_y < map_render_height):
                    
                    entity_color_tint = None
                    if visibility_type == 'player':
                        entity_color_tint = None
                    elif visibility_type == 'torch':
                        entity_color_tint = (128, 128, 128, 255)
                    elif visibility_type == 'darkvision':
                        entity_color_tint = (90, 90, 90, 255)
                    elif visibility_type == 'explored':
                        entity_color_tint = (60, 60, 60, 255)
                    
                    # Always draw floor under entities, as map rendering might have drawn a decorative tile
                    # --- MODIFIED: Pass float draw_x, draw_y to graphics.draw_tile ---
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, floor.char, color_tint=entity_color_tint)
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, entity.char, color_tint=entity_color_tint)


    def render_items_on_ground(self):
        """Render items lying on the dungeon floor."""
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
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, floor.char, color_tint=item_color_tint)
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, item.char, color_tint=item_color_tint)


    def render_character_creation_screen(self):
        target_surface = self.inventory_ui_surface # Use this surface for drawing
        target_surface.fill((0,0,0,0)) # Clear it
        
        # Draw a background box for the menu
        menu_width = int(target_surface.get_width() * 0.7)
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
        
        current_y = title_rect.bottom + 30
        item_start_x = menu_x + 40
        line_spacing = self.inventory_font_info.get_linesize() + 8
        
        for i, race in enumerate(self.available_races):
            race_text = f"{i+1}. {race.name}"
            color = (255, 255, 0) if i == self.selected_race_index else (200, 200, 200)
            race_surface = self.inventory_font_section.render(race_text, True, color)
            target_surface.blit(race_surface, (item_start_x, current_y))
            current_y += line_spacing
        
            if i == self.selected_race_index:
                wrapped_desc = self._wrap_text(race.description, self.inventory_font_small, menu_width - 80)
        
                for line in wrapped_desc:
                    desc_surface = self.inventory_font_small.render(line, True, (150, 150, 150))
                    target_surface.blit(desc_surface, (item_start_x + 20, current_y))
                    current_y += self.inventory_font_small.get_linesize() + 2
        
                current_y += 10 # Extra space after description
        
        instructions_y = menu_rect.bottom - (self.inventory_font_small.get_linesize() * 2) - 20
        self._draw_text(target_surface, self.inventory_font_small, "Use UP/DOWN arrows to select.", (150, 150, 150), item_start_x, instructions_y)
        self._draw_text(target_surface, self.inventory_font_small, "Press ENTER to confirm.", (150, 150, 150), item_start_x, instructions_y + self.inventory_font_small.get_linesize() + 5)    

    def render_class_selection_screen(self):
        target_surface = self.inventory_ui_surface
        target_surface.fill((0,0,0,0))
        
        menu_width = int(target_surface.get_width() * 0.7)
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
        
        current_y = title_rect.bottom + 30
        item_start_x = menu_x + 40
        line_spacing = self.inventory_font_info.get_linesize() + 8
        
        for i, class_constructor in enumerate(self.available_classes):
            class_name = class_constructor.__name__ # Get the class name string
            class_text = f"{i+1}. {class_name}"
            color = (255, 255, 0) if i == self.selected_class_index else (200, 200, 200)
            class_surface = self.inventory_font_section.render(class_text, True, color)
            target_surface.blit(class_surface, (item_start_x, current_y))
            current_y += line_spacing
            
            if i == self.selected_class_index:
                # You can add more detailed class descriptions here if you want to define them
                # For now, a generic one:
                class_description = "A brief description of this class's playstyle and abilities."
                wrapped_desc = self._wrap_text(class_description, self.inventory_font_small, menu_width - 80)
                for line in wrapped_desc:
                    desc_surface = self.inventory_font_small.render(line, True, (150, 150, 150))
                    target_surface.blit(desc_surface, (item_start_x + 20, current_y))
                    current_y += self.inventory_font_small.get_linesize() + 2
                current_y += 10 # Extra space after description
        
        instructions_y = menu_rect.bottom - (self.inventory_font_small.get_linesize() * 2) - 20
        self._draw_text(target_surface, self.inventory_font_small, "Use UP/DOWN arrows to select.", (150, 150, 150), item_start_x, instructions_y)
        self._draw_text(target_surface, self.inventory_font_small, "Press ENTER to confirm.", (150, 150, 150), item_start_x, instructions_y + self.inventory_font_small.get_linesize() + 5)
   

    def render_inventory_screen(self):
        """Renders the inventory screen."""
        target_surface = self.inventory_ui_surface
        target_surface.fill((0,0,0,0))
        inventory_width_ratio = 0.7
        inventory_height_ratio = 0.8
        inventory_rect_width = int(target_surface.get_width() * inventory_width_ratio)
        inventory_rect_height = int(target_surface.get_height() * inventory_height_ratio)
        
        inventory_x = (target_surface.get_width() - inventory_rect_width) // 2
        inventory_y = (target_surface.get_height() - inventory_rect_height) // 2
        
        inventory_rect = pygame.Rect(inventory_x, inventory_y, inventory_rect_width, inventory_rect_height)
        pygame.draw.rect(target_surface, (30, 30, 30), inventory_rect)
        pygame.draw.rect(target_surface, (100, 100, 100), inventory_rect, 2)
        
        title_text = "INVENTORY"
        title_surface = self.inventory_font_header.render(title_text, True, (255, 215, 0))
        title_rect = title_surface.get_rect(center=(inventory_rect.centerx, inventory_y + self.inventory_font_header.get_linesize() // 2 + 10))
        target_surface.blit(title_surface, title_rect)
        current_y = inventory_y + self.inventory_font_header.get_linesize() + 30
        
        item_start_x = inventory_x + 20
        line_spacing = self.inventory_font_info.get_linesize() + 8
        if not self.player.inventory.items:
            no_items_text = "Inventory is empty."
            no_items_surface = self.inventory_font_info.render(no_items_text, True, (150, 150, 150))
            no_items_rect = no_items_surface.get_rect(center=(inventory_rect.centerx, current_y + 20))
            target_surface.blit(no_items_surface, no_items_rect)
        else:
            for i, item in enumerate(self.player.inventory.items):
                item_text = f"{i+1}. {item.name}"
                if item == self.selected_inventory_item:
                    item_color = (255, 255, 0)
                else:
                    item_color = item.color
                item_surface = self.inventory_font_info.render(item_text, True, item_color)
                target_surface.blit(item_surface, (item_start_x, current_y))
                current_y += line_spacing
                
                if item == self.selected_inventory_item:
                    wrapped_desc = self._wrap_text(item.description, self.inventory_font_small, inventory_rect_width - 40)
                    for line in wrapped_desc:
                        desc_surface = self.inventory_font_small.render(line, True, (200, 200, 200))
                        target_surface.blit(desc_surface, (item_start_x + 10, current_y))
                        current_y += self.inventory_font_small.get_linesize() + 2
                    current_y += 5

        instructions_y_start = inventory_rect.bottom - (self.inventory_font_small.get_linesize() * 2) - 20
        
        if self.game_state == GameState.INVENTORY:
            self._draw_text(target_surface, self.inventory_font_small, "Press 1-9/0 to select an item.", (150, 150, 150), item_start_x, instructions_y_start)
            self._draw_text(target_surface, self.inventory_font_small, "Press 'I' to close inventory.", (150, 150, 150), item_start_x, instructions_y_start + self.inventory_font_small.get_linesize() + 5)
        elif self.game_state == GameState.INVENTORY_MENU and self.selected_inventory_item:
            menu_instructions_y = max(current_y + 10, instructions_y_start) 
            
            self._draw_text(target_surface, self.inventory_font_small, "U: Use", (150, 150, 150), item_start_x, menu_instructions_y)
            menu_instructions_y += self.inventory_font_small.get_linesize() + 5
            self._draw_text(target_surface, self.inventory_font_small, "E: Equip", (150, 150, 150), item_start_x, menu_instructions_y)
            menu_instructions_y += self.inventory_font_small.get_linesize() + 5
            self._draw_text(target_surface, self.inventory_font_small, "D: Drop", (150, 150, 150), item_start_x, menu_instructions_y)
            menu_instructions_y += self.inventory_font_small.get_linesize() + 5
            self._draw_text(target_surface, self.inventory_font_small, "C: Cancel", (150, 150, 150), item_start_x, menu_instructions_y)
            

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
            ("U: Use", pygame.K_u),
            ("E: Equip", pygame.K_e),
            ("D: Drop", pygame.K_d),
            ("C: Cancel", pygame.K_c)
        ]
        current_y = item_name_rect.bottom + 15
        for text, key_code in options:
            from items.items import Potion, Weapon, Armor
            is_valid_action = True
            if text == "U: Use" and not isinstance(self.selected_inventory_item, Potion):
                is_valid_action = False
            elif text == "E: Equip" and not (isinstance(self.selected_inventory_item, Weapon) or isinstance(self.selected_inventory_item, Armor)):
                is_valid_action = False
            
            color = (255, 255, 255) if is_valid_action else (100, 100, 100)
            
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
        self._draw_text(target_surface, self.inventory_font_info, f"Attack Bonus: +{self.player.attack_bonus}", (255, 255, 255), right_column_x, current_y_right)
        current_y_right += self.inventory_font_info.get_linesize() + 15

        self._draw_text(target_surface, self.inventory_font_section, "EQUIPMENT", (255, 215, 0), right_column_x, current_y_right)
        current_y_right += self.inventory_font_section.get_linesize() + 5
        
        equipped_weapon_name = self.player.equipped_weapon.name if self.player.equipped_weapon else "None"
        equipped_armor_name = self.player.equipped_armor.name if self.player.equipped_armor else "None"

        current_y_right = draw_wrapped_and_update_y_menu(target_surface, self.inventory_font_info, f"Weapon: {equipped_weapon_name}", (255, 255, 255), right_column_x, current_y_right, column_width)
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

        self._draw_text(target_surface, self.inventory_font_small, "Press 'C' to close Character Menu.", (150, 150, 150), left_column_x, instructions_y_start)
        self._draw_text(target_surface, self.inventory_font_small, "Press 'I' to open Inventory.", (150, 150, 150), left_column_x, instructions_y_start + self.inventory_font_small.get_linesize() + 5)


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
        self._draw_text(self.screen, font_info, f"Class: {self.player.class_name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5    
        self._draw_text(self.screen, font_info, f"Level: {self.player.level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        self._draw_text(self.screen, font_info, f"XP: {self.player.current_xp}/{self.player.xp_to_next_level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 15    
        pygame.draw.line(self.screen, separator_color, (panel_offset_x - 5, current_y), (panel_right_edge + 5, current_y), separator_thickness)
        current_y += 15

        draw_centered_header(self.screen, font_header, "VITALS", (255, 215, 0), current_y)
        current_y += font_header.get_linesize() + 10
        
        hp_color = (255, 0, 0) if self.player.hp < self.player.max_hp // 3 else (255, 255, 0) if self.player.hp < self.player.max_hp * 2 // 3 else (0, 255, 0)
        self._draw_text(self.screen, font_info, f"HP: {self.player.hp}/{self.player.max_hp}", hp_color, panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        
        bar_width = config.UI_PANEL_WIDTH - 40
        bar_height = 10
        hp_bar_rect = pygame.Rect(panel_offset_x, current_y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (50, 0, 0), hp_bar_rect)
        pygame.draw.rect(self.screen, (20, 20, 20), hp_bar_rect, 1)
        fill_width = int(bar_width * (self.player.hp / self.player.max_hp))
        pygame.draw.rect(self.screen, hp_color, (panel_offset_x, current_y, fill_width, bar_height))
        current_y += bar_height + 15
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
