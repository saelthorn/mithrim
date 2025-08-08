# MultipleFiles/game.py
import pygame
import random
import config

from core.fov import FOV
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from entities.player import Player
from entities.monster import Monster
from entities.monster import Mimic
from entities.tavern_npcs import create_tavern_npcs
from entities.dungeon_npcs import DungeonHealer
from entities.tavern_npcs import NPC # Keep this import for NPC type checking
from core.abilities import SecondWind, PowerAttack
from core.message_log import MessageBox
from items.items import Potion, Weapon, Armor, Chest
from core.pathfinding import astar # Keep this import
from world.tile import floor
import graphics # Import the graphics module


INTERNAL_WIDTH = 800
INTERNAL_HEIGHT = 600
ASPECT_RATIO = INTERNAL_WIDTH / INTERNAL_HEIGHT


class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"
    INVENTORY = "inventory" # New game state for inventory screen
    INVENTORY_MENU = "inventory_menu" # New state for item interaction menu

class Camera:
    def __init__(self, screen_width, screen_height, tile_size, message_log_height):
        self.tile_size = tile_size
        # Initial viewport calculation based on the *actual* game area on screen
        # These will be updated by _recalculate_dimensions
        self.viewport_width = screen_width // tile_size
        self.viewport_height = (screen_height - message_log_height) // tile_size - 2
        self.x = 0
        self.y = 0

    def update(self, target_x, target_y, map_width, map_height):
        # The viewport dimensions should be set externally by _recalculate_dimensions
        # or passed directly if they change.
        # For now, let's assume they are correctly set before this call.
        # The lines below are redundant if _recalculate_dimensions already sets them.
        # self.viewport_width = config.GAME_AREA_WIDTH // config.TILE_SIZE
        # self.viewport_height = (config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT) // config.TILE_SIZE - 2

        self.x = target_x - self.viewport_width // 2
        self.y = target_y - self.viewport_height // 2
        self.x = max(0, min(self.x, map_width - self.viewport_width))
        self.y = max(0, min(self.y, map_height - self.viewport_height))

    def world_to_screen(self, world_x, world_y):
        screen_x = world_x - self.x
        screen_y = world_y - self.y
        return screen_x, screen_y

    def is_in_viewport(self, world_x, world_y):
        screen_x, screen_y = self.world_to_screen(world_x, world_y)
        return (0 <= screen_x < self.viewport_width and
                0 <= screen_y < self.viewport_height)


class Game:
    def __init__(self, screen):
        self.screen = screen
        print(f"Initializing game with screen size: {screen.get_size()}")
        
        self._recalculate_dimensions() 
        print(f"After initial recalculation, TILE_SIZE: {config.TILE_SIZE}, SCREEN_WIDTH: {config.SCREEN_WIDTH}, SCREEN_HEIGHT: {config.SCREEN_HEIGHT}")
        
        self.internal_surface = pygame.Surface((config.INTERNAL_GAME_AREA_PIXEL_WIDTH, config.INTERNAL_GAME_AREA_PIXEL_HEIGHT)).convert_alpha()
        print(f"Initialized internal_surface: {self.internal_surface.get_size()}")
        
        # --- NEW: Surface for Inventory/Menu UI (unscaled) ---
        # This surface will be sized to the actual game area on the screen,
        # not the internal pixel dimensions.
        self.inventory_ui_surface = pygame.Surface((config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT)).convert_alpha()
        self.inventory_ui_surface.fill((0,0,0,0)) # Start transparent
        
        self._init_fonts() # This will now initialize fonts for both game world and UI panel
        
        self.camera = Camera(config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT, config.TILE_SIZE, config.MESSAGE_LOG_HEIGHT)
        self.camera.viewport_width = config.INTERNAL_GAME_AREA_PIXEL_WIDTH // config.TILE_SIZE
        self.camera.viewport_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT // config.TILE_SIZE
        print(f"Camera viewport (after init): {self.camera.viewport_width}x{self.camera.viewport_height}")
        
        self.game_state = GameState.TAVERN
        self.current_level = 1
        self.max_level_reached = 1
        self.player_has_acted = False
        self.message_log = MessageBox(
            0,
            config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT,
            config.GAME_AREA_WIDTH,
            config.MESSAGE_LOG_HEIGHT
        )
        self._recalculate_dimensions() # Call again to update message_log font and rect
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 100))
        
        self.generate_tavern() 
        self.selected_inventory_item = None

    def _recalculate_dimensions(self):
        """Recalculate all dynamic dimensions based on current screen size."""
        config.SCREEN_WIDTH, config.SCREEN_HEIGHT = self.screen.get_size()
        print(f"Recalculating dimensions. New screen size: {config.SCREEN_WIDTH}x{config.SCREEN_HEIGHT}")
        
        config.UI_PANEL_WIDTH = int(config.SCREEN_WIDTH * config.UI_PANEL_WIDTH_RATIO)
        config.GAME_AREA_WIDTH = config.SCREEN_WIDTH - config.UI_PANEL_WIDTH
        config.MESSAGE_LOG_HEIGHT = int(config.SCREEN_HEIGHT * config.MESSAGE_LOG_HEIGHT_RATIO)
        target_effective_tile_pixel_size = config.TILE_SIZE * config.TARGET_EFFECTIVE_TILE_SCALE
        
        new_internal_width_tiles = max(config.MIN_GAME_AREA_TILES_WIDTH, config.GAME_AREA_WIDTH // target_effective_tile_pixel_size)
        new_internal_height_tiles = max(config.MIN_GAME_AREA_TILES_HEIGHT, (config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT) // target_effective_tile_pixel_size)
        config.INTERNAL_GAME_AREA_WIDTH_TILES = new_internal_width_tiles
        config.INTERNAL_GAME_AREA_HEIGHT_TILES = new_internal_height_tiles
        
        config.INTERNAL_GAME_AREA_PIXEL_WIDTH = config.INTERNAL_GAME_AREA_WIDTH_TILES * config.TILE_SIZE
        config.INTERNAL_GAME_AREA_PIXEL_HEIGHT = config.INTERNAL_GAME_AREA_HEIGHT_TILES * config.TILE_SIZE
        
        if hasattr(self, 'internal_surface'):
            self.internal_surface = pygame.Surface((config.INTERNAL_GAME_AREA_PIXEL_WIDTH, config.INTERNAL_GAME_AREA_PIXEL_HEIGHT)).convert_alpha()
            print(f"Re-initialized internal_surface in _recalculate_dimensions: {self.internal_surface.get_size()}")

        # --- NEW: Re-initialize inventory_ui_surface on resize ---
        if hasattr(self, 'inventory_ui_surface'):
            self.inventory_ui_surface = pygame.Surface((config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT)).convert_alpha()
            self.inventory_ui_surface.fill((0,0,0,0)) # Keep transparent
        if hasattr(self, 'camera'):
            self.camera.tile_size = config.TILE_SIZE 
            self.camera.viewport_width = config.INTERNAL_GAME_AREA_PIXEL_WIDTH // config.TILE_SIZE
            self.camera.viewport_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT // config.TILE_SIZE
        if hasattr(self, 'message_log'):
            self.message_log.rect.x = 0
            self.message_log.rect.y = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
            self.message_log.rect.width = config.GAME_AREA_WIDTH
            self.message_log.rect.height = config.MESSAGE_LOG_HEIGHT
            
            new_font_size = int(config.MESSAGE_LOG_FONT_BASE_SIZE * config.TARGET_EFFECTIVE_TILE_SCALE * config.MESSAGE_LOG_FONT_SCALE_FACTOR)
            self.message_log.font = pygame.font.SysFont('consolas', new_font_size)
            
            self.message_log.line_height = self.message_log.font.get_linesize()
            self.message_log.max_lines = self.message_log.rect.height // self.message_log.line_height
        graphics.setup_tile_mapping()
        self._init_fonts() # Re-initialize other UI fonts (including inventory fonts)

    def _init_fonts(self):
        """Initializes or re-initializes fonts based on current TILE_SIZE and screen dimensions."""
        print(f"DEBUG: _init_fonts called. Current config.TILE_SIZE: {config.TILE_SIZE}")
        
        # Fonts for the main game area (scaled) - these will be small on internal_surface
        # but will scale up with the game area.
        # We can keep these relative to TILE_SIZE if we want them to scale with the game world.
        temp_tile_size = max(1, config.TILE_SIZE)
        self.font = pygame.font.SysFont('consolas', temp_tile_size) # For game world text if any
        
        # --- NEW: Fonts for Inventory/Menu UI (unscaled, absolute pixel sizes) ---
        # These fonts will be drawn directly to inventory_ui_surface, which is then blitted
        # to the screen without further scaling. So, their sizes should be absolute.
        self.inventory_font_header = pygame.font.SysFont('consolas', 24, bold=True) # Example absolute size
        self.inventory_font_section = pygame.font.SysFont('consolas', 20)
        self.inventory_font_info = pygame.font.SysFont('consolas', 16)
        self.inventory_font_small = pygame.font.SysFont('consolas', 14)
        # Fonts for the UI panel (drawn directly to screen, absolute pixel sizes)
        # These should also be absolute pixel sizes, as they are not scaled by internal_surface.
        self.font_header = pygame.font.SysFont('consolas', 20, bold=True) # Absolute size for UI panel
        self.font_section = pygame.font.SysFont('consolas', 18)
        self.font_info = pygame.font.SysFont('consolas', 16)
        self.font_small = pygame.font.SysFont('consolas', 14)
        
        print("DEBUG: All fonts initialized successfully.")

    def generate_tavern(self):
        self.game_state = GameState.TAVERN
        self.game_map = GameMap(40, 24)
        self.fov = FOV(self.game_map)
        self.door_position = generate_tavern(self.game_map)
        
        start_x, start_y = self.game_map.width // 2, self.game_map.height // 2 + 2
        
        if hasattr(self, 'player'):
            self.player.x = start_x
            self.player.y = start_y
        else:
            self.player = Player(start_x, start_y, '@', 'Hero', (255, 255, 255))
        
        # This call is correct here, as player and map are now set
        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
        
        self.npcs = create_tavern_npcs(self.game_map, self.door_position)
        self.entities = [self.player] + self.npcs
        self.turn_order = []
        self.current_turn_index = 0
        self.update_fov()
        
        self.message_log.add_message("=== WELCOME TO THE PRANCING PONY TAVERN ===", (255, 215, 0))
        self.message_log.add_message("Walk to the door (+) and press any movement key to enter the dungeon!", (150, 150, 255))

    def generate_level(self, level_number, spawn_on_stairs_up=False):
        self.game_state = GameState.DUNGEON
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
        
        # This call is correct here
        self.camera.update(start_x, start_y, self.game_map.width, self.game_map.height)
        
        self.entities = [self.player]
        
        # Monster generation
        monsters_per_level = min(2 + level_number, len(rooms) - 1)
        monster_rooms = rooms[1:monsters_per_level + 1]

        for i, room in enumerate(monster_rooms):
            x, y = room.center()
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y)):

                if level_number <= 3:
                    monster = Monster(x, y, 'g', f'Goblin{i+1}', (0, 130, 8))
                    monster.can_poison = True
                    monster.poison_dc = 12
                    monster.hp = 7 + level_number
                    monster.max_hp = 8 + level_number
                    monster.attack_power = 2 + (level_number - 1)
                    monster.armor_class = 12
                    monster.base_xp = 6 + (level_number * 2)
                elif level_number <= 6:
                    monster = Monster(x, y, '&', f'Skeleton{i+1}', (215, 152, 152))
                    monster.hp = 9 + level_number
                    monster.max_hp = 10 + level_number
                    monster.attack_power = 3 + (level_number - 1)
                    monster.armor_class = 12
                    monster.base_xp = 8 + (level_number * 2)
                elif level_number <= 8:
                    monster = Monster(x, y, 'R', f'Orc{i+1}', (63, 127, 63))
                    # Make Orcs capable of poisoning for testing
                    monster.can_poison = True
                    monster.poison_dc = 12
                    monster.hp = 11 + level_number
                    monster.max_hp = 12 + level_number
                    monster.attack_power = 4 + (level_number - 1)
                    monster.armor_class = 13
                    monster.base_xp = 10 + (level_number * 2)
                elif level_number <= 12:
                    monster = Monster(x, y, 'T', f'Troll{i+1}', (127, 63, 63))
                    monster.hp = 14 + level_number * 2
                    monster.max_hp = 15 + level_number * 2
                    monster.attack_power = 5 + level_number
                    monster.armor_class = 15
                    monster.base_xp = 20 + (level_number * 3)
                else:
                    monster = Monster(x, y, 'D', f'Dragon{i+1}', (255, 63, 63))
                    monster.hp = 20 + level_number * 3
                    monster.max_hp = 20 + level_number * 3
                    monster.attack_power = 6 + level_number
                    monster.armor_class = 17
                    monster.base_xp = 50 + (level_number * 5)

                self.entities.append(monster)
                self.message_log.add_message(f"A {monster.name} appears!", (255, 150, 0))

        # Dungeon Healer Spawning Logic
        if len(rooms) > 2 and random.random() < 0.9: # 25% chance to spawn a healer
            healer_room = random.choice(rooms[1:-1]) # Pick a room that's not the first or last
            healer_x, healer_y = healer_room.center()

            if self.game_map.is_walkable(healer_x, healer_y) and \
               not any(e.x == healer_x and e.y == healer_y for e in self.entities):

                dungeon_healer = DungeonHealer(healer_x, healer_y)
                self.entities.append(dungeon_healer)
                self.message_log.add_message(f"You sense a benevolent presence nearby...", (0, 255, 255))
                self.message_log.add_message(f"A {dungeon_healer.name} is at ({healer_x}, {healer_y})", (0, 255, 255))

        # Item Spawning Logic
        # Define the item templates here, using the imported classes
        item_templates = [
            Potion(name="Healing Potion", char="!", color=(255, 0, 0), description="Restores a small amount of health.", effect_type="heal", effect_value=8),
            Weapon(name="Short Sword", char="/", color=(150, 150, 150), description="A basic short sword.", damage_dice="1d6", damage_modifier=0, attack_bonus=0),
            Armor(name="Leather Armor", char="[", color=(139, 69, 19), description="Light leather armor.", ac_bonus=1)
        ]

        item_spawn_chance = 0.9 # 30% chance for a room to have an item

        for room in rooms:
            if random.random() < item_spawn_chance:
                item_x, item_y = room.center()
                # Ensure item doesn't spawn on player, stairs, or other entities
                if (item_x, item_y) != (self.player.x, self.player.y) and \
                   (item_x, item_y) not in self.stairs_positions.values() and \
                   not any(e.x == item_x and e.y == item_y for e in self.entities):

                    # Pick a random template and create a NEW instance from it
                    chosen_template = random.choice(item_templates)
                    # This creates a new object with the same properties as the template
                    # This is a generic way to copy attributes for simple items.
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

        # Initialize turn system
        for entity in self.entities:
            entity.roll_initiative()
        
        self.turn_order = sorted(self.entities, key=lambda e: e.initiative, reverse=True)
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

    def check_dungeon_npc_interaction(self): # New method for dungeon NPCs
        if self.game_state == GameState.DUNGEON:
            for entity in self.entities:
                if isinstance(entity, DungeonHealer): # Check if it's a DungeonHealer
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
            # In tavern, everything is always visible and explored
            self.fov.visible_sources.clear()  # Clear current visible sources
            self.fov.explored.clear()  # Clear explored for tavern
            for y in range(self.game_map.height):
                for x in range(self.game_map.width):
                    self.fov.visible_sources[(x, y)] = 'player'  # Treat all as player light
                    self.fov.explored.add((x, y))
        else:
            # For dungeon levels, clear only the 'visible_sources' each turn
            # 'explored' should persist across turns
            self.fov.visible_sources.clear()  # Clear current visible sources
            
            # Compute FOV from player (strongest light source)
            self.fov.compute_fov(self.player.x, self.player.y, radius=8, light_source_type='player')
            
            # Additionally, compute FOV from each torch (weaker light source)
            for tx, ty in self.torch_light_sources:
                self.fov.compute_fov(tx, ty, radius=5, light_source_type='torch')

    def get_current_entity(self):
        if not self.turn_order or self.game_state == GameState.TAVERN:
            return self.player
        # Ensure current_turn_index is always valid
        if self.current_turn_index >= len(self.turn_order):
            self.current_turn_index = 0  # Wrap around if somehow out of bounds
        return self.turn_order[self.current_turn_index]

    def next_turn(self):
        if self.game_state == GameState.TAVERN:
            # In tavern, next_turn just handles ambient messages, no turn order advancement
            if random.random() < 0.3:
                ambient_msgs = [
                    "The torch flickers, casting long shadows...",
                    "Distant drips echo through the stone halls..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (150, 150, 150))
            # In tavern, player actions don't consume a "turn" in the combat sense,
            # so no cooldowns tick down here.
            return

        # --- Dungeon turn logic below ---
        # IMPORTANT: Cleanup entities BEFORE advancing the turn index
        self.cleanup_entities()

        # Get the entity whose turn it *was* before advancing
        previous_current_entity = self.get_current_entity()

        if not self.turn_order:
            # If no entities left (e.g., all monsters dead), ensure player's turn
            self.current_turn_index = 0
            current = self.get_current_entity()  # This will be the player
        else:
            # Advance to the next entity in the turn order
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            current = self.get_current_entity()

        # --- NEW: Process player's status effects and cooldowns when player's turn ends ---
        # This ensures cooldowns tick down only after the player has acted.
        # This is called *after* the turn has advanced, so it applies to the entity
        # whose turn just finished.
        if previous_current_entity == self.player:
            self.player.process_status_effects(self)  # This will now tick down cooldowns

        if current == self.player:
            self.update_fov()
            self.player_has_acted = False  # Reset flag at start of player's turn in dungeon
            if random.random() < 0.25:
                ambient_msgs = [
                    "The dungeon emits an eerie glow...",
                    "Something shuffles in the darkness..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (180, 180, 180))

    def cleanup_entities(self):
        """Removes dead entities from the game's entity list and turn order,
        and adjusts the current_turn_index if necessary."""
        
        # Store the entity whose turn it currently is (before cleanup)
        current_entity_before_cleanup = None
        if self.turn_order and 0 <= self.current_turn_index < len(self.turn_order):
            current_entity_before_cleanup = self.turn_order[self.current_turn_index]

        # Filter out dead entities from the main list
        alive_entities = [e for e in self.entities if e.alive]
        
        # If the list of entities has changed (i.e., something died)
        if len(alive_entities) != len(self.entities):
            self.entities = alive_entities
            
            # Rebuild the turn_order list, ensuring only alive entities are present
            # and maintaining the original relative order as much as possible.
            new_turn_order = []
            for entity in self.turn_order:  # Iterate over the *old* turn_order
                if entity.alive:
                    new_turn_order.append(entity)
            self.turn_order = new_turn_order
            
            # Now, adjust current_turn_index based on the new turn_order.
            # If the entity whose turn it was is still in the new list,
            # we try to keep the index pointing to it.
            if current_entity_before_cleanup and current_entity_before_cleanup in self.turn_order:
                self.current_turn_index = self.turn_order.index(current_entity_before_cleanup)
            else:
                # If the entity whose turn it was died or is no longer in the list,
                # we need to reset the index. The next_turn() logic will then
                # correctly advance it.
                # If the turn_order is now empty, current_turn_index will be 0,
                # and get_current_entity() will correctly return the player.
                self.current_turn_index = 0 
        
        # If turn_order becomes empty (all monsters dead), ensure player is the only one
        if not self.turn_order and self.player.alive:
            self.turn_order = [self.player]
            self.current_turn_index = 0  # Player's turn


    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.VIDEORESIZE:
                # When window is resized (or toggled fullscreen), recalculate dimensions
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._recalculate_dimensions()
                # After recalculating dimensions, update camera and re-render
                self.render()  # Force a re-render immediately
            
            if event.type == pygame.KEYDOWN:
                # --- Handle 'i' key for Inventory/Inventory Menu (always accessible) ---
                if event.key == pygame.K_i:
                    if self.game_state == GameState.DUNGEON:
                        self.game_state = GameState.INVENTORY
                        self.message_log.add_message("Opening Inventory...", (100, 200, 255))
                    elif self.game_state == GameState.INVENTORY:
                        self.game_state = GameState.DUNGEON
                        self.message_log.add_message("Closing Inventory.", (100, 200, 255))
                        self.selected_inventory_item = None
                    elif self.game_state == GameState.INVENTORY_MENU:
                        self.game_state = GameState.INVENTORY
                        self.selected_inventory_item = None
                        self.message_log.add_message("Returning to Inventory.", (100, 200, 255))
                    continue

                # --- Handle input based on game state ---
                if self.game_state == GameState.INVENTORY:
                    self.handle_inventory_input(event.key)
                    continue
                elif self.game_state == GameState.INVENTORY_MENU:
                    self.handle_inventory_menu_input(event.key)
                    continue

                # --- Player's turn logic (for Dungeon and Tavern) ---
                # In Tavern, player can always act. In Dungeon, only if it's player's turn and they haven't acted.
                can_player_act_this_turn = (self.game_state == GameState.TAVERN) or \
                                           (self.get_current_entity() == self.player and not self.player_has_acted)

                if can_player_act_this_turn:
                    dx, dy = 0, 0
                    action_taken = False  # Flag for successful action that consumes a turn

                    if event.key in (pygame.K_UP, pygame.K_k):
                        dy = -1
                        action_taken = self.handle_player_action(dx, dy)
                    elif event.key in (pygame.K_DOWN, pygame.K_j):
                        dy = 1
                        action_taken = self.handle_player_action(dx, dy)
                    elif event.key in (pygame.K_LEFT, pygame.K_h):
                        dx = -1
                        action_taken = self.handle_player_action(dx, dy)
                    elif event.key in (pygame.K_RIGHT, pygame.K_l):
                        dx = 1
                        action_taken = self.handle_player_action(dx, dy)
                    elif event.key == pygame.K_SPACE:
                        if self.game_state == GameState.TAVERN:
                            npc = self.check_npc_interaction()
                            if npc:
                                self.message_log.add_message(f"{npc.name}: {npc.get_dialogue()}", (200, 200, 255))
                                action_taken = True  # Talking takes an action
                        elif self.game_state == GameState.DUNGEON:
                            interactable_item = self.get_interactable_item_at(self.player.x, self.player.y)
                            if interactable_item:
                                if isinstance(interactable_item, Mimic):
                                    interactable_item.reveal(self)
                                    self.game_map.items_on_ground.remove(interactable_item)
                                    action_taken = True  # Interacting with a mimic takes a turn
                                elif isinstance(interactable_item, Chest):
                                    interactable_item.open(self.player, self)
                                    action_taken = True  # Opening a chest takes a turn
                                else:
                                    self.message_log.add_message("You can't interact with that item.", (150, 150, 150))
                            else:
                                target = self.get_adjacent_target()
                                if target:
                                    self.handle_player_attack(target)
                                    action_taken = True  # Attacking takes a turn
                                else:
                                    action_taken = self.handle_item_pickup()  # Pickup returns True if successful
                                

                    # --- Ability Hotkeys ---
                    # Get a list of abilities in the same order as displayed in UI
                    sorted_abilities = sorted(self.player.abilities.values(), key=lambda ab: ab.name)
                    
                    # Check for number keys 1-9 (and potentially 0 for 10th ability)
                    if pygame.K_1 <= event.key <= pygame.K_9:
                        ability_index = event.key - pygame.K_1
                        if 0 <= ability_index < len(sorted_abilities):
                            ability_to_use = sorted_abilities[ability_index]
                            if self.game_state == GameState.DUNGEON: # Abilities only usable in dungeon
                                if ability_to_use.use(self.player, self):
                                    action_taken = True  # Ability use takes a turn
                            else:
                                self.message_log.add_message("Abilities can only be used in the dungeon.", (150, 150, 150))
                        else:
                            self.message_log.add_message("No ability assigned to that hotkey.", (150, 150, 150))                   

                    
                    elif event.key == pygame.K_F11:
                        flags = self.screen.get_flags()
                        if flags & pygame.FULLSCREEN:
                            self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.RESIZABLE)
                        else:
                            info = pygame.display.Info()
                            self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
                        self._recalculate_dimensions()
                        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height) 
                        self.render()  # Force a re-render after resizing
                        continue


                    # If an action was successfully taken, set player_has_acted and advance turn
                    if action_taken:
                        if self.game_state == GameState.DUNGEON:  # Only set player_has_acted in dungeon
                            self.player_has_acted = True
                        self.next_turn()  # Advance turn (this will handle dungeon turn order or tavern ambient)

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
            item_to_pick_up = items_at_player_pos[0]  # Pick up the first item found
            if self.player.inventory.add_item(item_to_pick_up):
                item_to_pick_up.on_pickup(self.player, self)  # Item's on_pickup handles removal from map
                return True  # Picking up an item takes a turn
            else:
                self.message_log.add_message("Your inventory is full!", (255, 0, 0))
        else:
            self.message_log.add_message("Nothing to pick up here.", (150, 150, 150))
        return False  # No item picked up, no turn consumed

    def handle_inventory_input(self, key):
        """Handles input when in the inventory screen."""
        # Allow closing with 'i' (handled in handle_events)
        # Handle number keys for item selection
        if pygame.K_1 <= key <= pygame.K_9:
            item_index = key - pygame.K_1
            if 0 <= item_index < len(self.player.inventory.items):
                self.selected_inventory_item = self.player.inventory.items[item_index]
                self.game_state = GameState.INVENTORY_MENU
                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
            else:
                self.message_log.add_message("No item at that slot.", (150, 150, 150))
        elif key == pygame.K_0:  # For 10th item if capacity is 10
            if len(self.player.inventory.items) == 10:
                self.selected_inventory_item = self.player.inventory.items[9]
                self.game_state = GameState.INVENTORY_MENU
                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
            else:
                self.message_log.add_message("No item at that slot.", (150, 150, 150))

    def handle_inventory_menu_input(self, key):
        """Handles input when an item is selected in the inventory menu."""
        if not self.selected_inventory_item:
            self.game_state = GameState.INVENTORY  # Should not happen, but as a safeguard
            return

        action_taken_in_menu = False  # Flag for actions that consume a turn
        if key == pygame.K_u:  # Use item
            if self.player.use_item(self.selected_inventory_item, self):
                self.selected_inventory_item = None
                self.game_state = GameState.DUNGEON  # Exit inventory after use
                action_taken_in_menu = True  # Using an item takes a turn
            else:
                self.message_log.add_message(f"Cannot use {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_e:  # Equip item
            if self.player.equip_item(self.selected_inventory_item, self):
                self.selected_inventory_item = None
                self.game_state = GameState.DUNGEON  # Exit inventory after equip
                action_taken_in_menu = True  # Equipping an item takes a turn
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_d:  # Drop item
            self.player.inventory.remove_item(self.selected_inventory_item)  # Remove from player's inventory
            self.selected_inventory_item.x = self.player.x  # Set item's position to player's
            self.selected_inventory_item.y = self.player.y
            self.game_map.items_on_ground.append(self.selected_inventory_item)  # Add to map
            self.message_log.add_message(f"You drop the {self.selected_inventory_item.name}.", self.selected_inventory_item.color)
            self.selected_inventory_item = None
            self.game_state = GameState.DUNGEON  # Exit inventory after drop
            action_taken_in_menu = True  # Dropping an item takes a turn
        elif key == pygame.K_c:  # Cancel
            self.selected_inventory_item = None
            self.game_state = GameState.INVENTORY  # Go back to inventory list
        
        if action_taken_in_menu:
            self.player_has_acted = True  # Set flag if action consumed turn
            self.next_turn()  # Advance turn

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

        # --- Tavern-specific movement logic ---
        if self.game_state == GameState.TAVERN:
            # Check for door interaction first
            if (new_x, new_y) == self.door_position:
                self.message_log.add_message("You enter the dark dungeon...", (100, 255, 100))
                self.generate_level(1)
                return True  # Player successfully moved to door and transitioned
            
            # Check if new position is blocked by an NPC in tavern
            for npc in self.npcs:
                if npc.x == new_x and npc.y == new_y and npc.alive:
                    self.message_log.add_message(f"You can't move onto {npc.name}.", (255, 150, 0))
                    return False  # Blocked by NPC

            # Check if new position is walkable in tavern
            if self.game_map.is_walkable(new_x, new_y):
                self.player.x = new_x
                self.player.y = new_y
                self.update_fov()  # Update FOV even in tavern for consistency
                return True  # Player successfully moved in tavern

            # If not door, not blocked by NPC, and not walkable
            self.message_log.add_message("You can't move there.", (255, 150, 0))
            return False  # Cannot move

        # --- Dungeon-specific movement logic (original) ---
        elif self.game_state == GameState.DUNGEON:
            target = self.get_target_at(new_x, new_y)
            if target:
                self.handle_player_attack(target)
                return True  # Return True for successful action (attack)
            elif self.game_map.is_walkable(new_x, new_y):
                self.player.x = new_x
                self.player.y = new_y

                self.update_fov()

                stairs_dir = self.check_stairs_interaction()
                if stairs_dir:
                    self.handle_level_transition(stairs_dir)
                # No else here, as handle_level_transition will call generate_level which resets game state
                return True  # Return True for successful action (movement)
            else:
                self.message_log.add_message("You can't move there.", (255, 150, 0))
                return False  # Cannot move (blocked by wall/obstacle)

        return False  # Default return if game_state is not handled (shouldn't happen)

    def handle_player_attack(self, target):
        """Handle player attacking an enemy with full combat feedback, including dice rolls, crits, and fumbles."""
        if not target.alive:
            return

        # --- Player Attack Roll ---
        d20_roll = random.randint(1, 20)
        attack_modifier = self.player.attack_bonus
        attack_roll_total = d20_roll + attack_modifier

        self.message_log.add_message(
            f"You roll a d20: {d20_roll} + {attack_modifier} (Attack Bonus) = {attack_roll_total}",
            (200, 200, 255)  # Light blue for attack roll info
        )

        is_critical_hit = (d20_roll == 20)
        is_critical_fumble = (d20_roll == 1)

        if is_critical_hit:
            self.message_log.add_message(
                "CRITICAL HIT! You strike a vital spot!",
                (255, 255, 0)  # Yellow for critical hit
            )
            hit_successful = True
        elif is_critical_fumble:
            self.message_log.add_message(
                "CRITICAL FUMBLE! You trip over your own feet!",
                (255, 0, 0)  # Red for critical fumble
            )
            hit_successful = False
        elif attack_roll_total >= target.armor_class:
            hit_successful = True
        else:
            hit_successful = False

        if hit_successful:
            # --- AMBIENT TEXT FOR PLAYER HIT ---
            hit_messages = [
                f"Your attack ({attack_roll_total}) hits the {target.name} (AC {target.armor_class})!",
                f"You connect with the {target.name}!",
                f"A solid blow lands on the {target.name}!",
                f"The {target.name} recoils from your strike!"
            ]
            self.message_log.add_message(random.choice(hit_messages), (100, 255, 100))

            # --- Damage Calculation ---
            damage_dice_roll_1 = random.randint(1, 6)
            damage_dice_roll_2 = 0

            if is_critical_hit:
                damage_dice_roll_2 = random.randint(1, 6)
                damage_dice_rolls_sum = damage_dice_roll_1 + damage_dice_roll_2
                damage_message_dice_part = f"2d6 ({damage_dice_roll_1} + {damage_dice_roll_2})"
            else:
                damage_dice_rolls_sum = damage_dice_roll_1
                damage_message_dice_part = f"1d6 ({damage_dice_roll_1})"

            damage_modifier = self.player.attack_power
            damage_total = max(1, damage_dice_rolls_sum + damage_modifier)

            self.message_log.add_message(
                f"You roll {damage_message_dice_part} + {damage_modifier} (Attack Power) = {damage_total} damage!",
                (255, 200, 100)
            )

            damage_dealt = target.take_damage(damage_total)

            self.message_log.add_message(
                f"You hit the {target.name} for {damage_dealt} damage!",
                (255, 100, 100)
            )

            if not target.alive:
                xp_gained = target.die()
                self.player.gain_xp(xp_gained, self)  # Assuming game_instance is passed
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
            # --- AMBIENT TEXT FOR PLAYER MISS ---
            miss_messages = [
                f"Your attack ({attack_roll_total}) misses the {target.name} (AC {target.armor_class})!",
                f"You swing wildly and miss the {target.name}!",
                f"The {target.name} deftly dodges your attack!",
                f"Your weapon glances harmlessly off the {target.name}!"
            ]
            self.message_log.add_message(random.choice(miss_messages), (200, 200, 200))

    def add_ambient_combat_message(self):
        """Add random post-combat ambient message"""
        messages = [
            "The smell of blood fills the air...",
            "Silence returns to the dungeon...",
            "Your weapon drips with monster blood..."
        ]
        self.message_log.add_message(random.choice(messages), (170, 170, 170))

    def update(self, dt):
        """Handle non-player turns and game updates"""
        # This update is fine here, as it's called every frame after initial setup
        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
        
        if not self.player.alive:
            if not hasattr(self, '_game_over_displayed'):
                death_messages = [
                    "Your journey ends here, adventurer. The dungeon claims another soul.",
                    "The light fades from your eyes. Darkness embraces you.",
                    "You fought bravely, but the dungeon proved too strong. Rest now.",
                    "Your spirit departs this mortal coil. Game Over.",
                    "The dungeon's embrace is cold and final. You have fallen."
                ]
                chosen_death_message = random.choice(death_messages)
                self.message_log.add_message(chosen_death_message, (255, 0, 0))
                self._game_over_displayed = True
            return
        
        if self.game_state == GameState.TAVERN:
            return
        current = self.get_current_entity()
        if current and current != self.player and current.alive:
            current.take_turn(self.player, self.game_map, self)
            self.next_turn()

    def handle_window_resize(self):
        """Reinitialize display when window size changes"""
        old_scale = self.scale
        
        # Calculate new scaling factors
        self.scale_x = self.screen.get_width() / INTERNAL_WIDTH
        self.scale_y = self.screen.get_height() / INTERNAL_HEIGHT
        self.scale = min(self.scale_x, self.scale_y)
        
        print(f"Resized to: {self.screen.get_size()}")
        print(f"New scale: {self.scale}")
        
        # Only recreate internal surface if scale changed significantly
        if abs(old_scale - self.scale) > 0.1:
            self.internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
            self.font = pygame.font.SysFont('consolas', int(INTERNAL_HEIGHT/50))

    def render(self):
        """Main render method - draws everything"""
        self.screen.fill((0, 0, 0)) # Clear the actual display screen
        self.internal_surface.fill((0, 0, 0)) # Clear the internal game world surface
        
        # --- NEW: Clear inventory_ui_surface at the start of render ---
        self.inventory_ui_surface.fill((0,0,0,0)) # Clear with transparency
        if self.game_state == GameState.INVENTORY:
            self.render_inventory_screen() 
            # --- NEW: Blit inventory_ui_surface to screen ---
            self.screen.blit(self.inventory_ui_surface, (0, 0)) # Blit at top-left of game area
        elif self.game_state == GameState.INVENTORY_MENU:
            self.render_inventory_screen() # Draws background
            self.render_inventory_menu() # Draws menu on top
            # --- NEW: Blit inventory_ui_surface to screen ---
            self.screen.blit(self.inventory_ui_surface, (0, 0)) # Blit at top-left of game area
        else:
            self.render_map_with_fov()
            self.render_items_on_ground()
            self.render_entities()
            
            # Existing scaling logic for the game world
            internal_aspect_ratio = config.INTERNAL_GAME_AREA_PIXEL_WIDTH / config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
            available_width = config.GAME_AREA_WIDTH
            available_height = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
            
            scale_factor_x = available_width // config.INTERNAL_GAME_AREA_PIXEL_WIDTH
            scale_factor_y = available_height // config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
            
            actual_scale_factor = min(scale_factor_x, scale_factor_y)
            
            if actual_scale_factor < 1:
                actual_scale_factor = 1 
            scaled_width = config.INTERNAL_GAME_AREA_PIXEL_WIDTH * actual_scale_factor
            scaled_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT * actual_scale_factor
            
            offset_x = (available_width - scaled_width) // 2
            offset_y = (available_height - scaled_height) // 2
            target_rect = pygame.Rect(offset_x, offset_y, scaled_width, scaled_height)
            
            scaled_game_area = pygame.transform.scale(self.internal_surface, target_rect.size)
            self.screen.blit(scaled_game_area, target_rect.topleft)
        self.draw_ui() # This draws directly to self.screen (side panel)
        self.message_log.render(self.screen) # Draws directly to self.screen
        
        pygame.display.flip()

    def render_map_with_fov(self):
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT # Use internal height for drawing
        
        for y in range(self.camera.y, min(self.camera.y + self.camera.viewport_height, self.game_map.height)):
            for x in range(self.camera.x, min(self.camera.x + self.camera.viewport_width, self.game_map.width)):
                screen_x, screen_y = self.camera.world_to_screen(x, y)
                draw_x = screen_x * config.TILE_SIZE
                draw_y = screen_y * config.TILE_SIZE                

                # Only draw if within the actual pixel bounds of the INTERNAL game area
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and # Check against internal surface dimensions
                    0 <= draw_y < map_render_height):
                    
                    visibility_type = self.fov.get_visibility_type(x, y)
                    if visibility_type == 'unexplored':
                        continue
                    tile = self.game_map.tiles[y][x]
                    
                    render_color_tint = None
                    if visibility_type == 'player':
                        render_color_tint = None
                    elif visibility_type == 'torch':
                        render_color_tint = (128, 128, 128, 255)
                    elif visibility_type == 'explored':
                        render_color_tint = (60, 60, 60, 255)
                    
                    # Pass self.internal_surface to graphics.draw_tile
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, tile.char, color_tint=render_color_tint)



    def render_entities(self):
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for entity in self.entities:
            visibility_type = self.fov.get_visibility_type(entity.x, entity.y)
            
            # Only draw if in viewport AND currently visible (player or torch light)
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y) and \
               (visibility_type == 'player' or visibility_type == 'torch'):
                
                screen_x, screen_y = self.camera.world_to_screen(entity.x, entity.y)
                
                if (0 <= screen_x * config.TILE_SIZE < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= screen_y * config.TILE_SIZE < map_render_height):
                    
                    # --- NEW: Draw a non-dimmed floor tile underneath the entity ---
                    # This ensures the background behind the entity is always bright, not dimmed.
                    # You might need to adjust 'floor' to be the specific floor tile type for the current map.
                    # For simplicity, assuming 'floor' is universally applicable.
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, floor.char, color_tint=None)
                    
                    # Then draw the entity on top
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, entity.char, color_tint=None)

    def render_items_on_ground(self):
        """Render items lying on the dungeon floor."""
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for item in self.game_map.items_on_ground:
            visibility_type = self.fov.get_visibility_type(item.x, item.y)
            
            # Only draw if in viewport AND currently visible (player or torch light)
            if self.camera.is_in_viewport(item.x, item.y) and \
               (visibility_type == 'player' or visibility_type == 'torch'):
                
                screen_x, screen_y = self.camera.world_to_screen(item.x, item.y)
                
                if (0 <= screen_x * config.TILE_SIZE < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= screen_y * config.TILE_SIZE < map_render_height):
                    
                    # --- NEW: Draw a non-dimmed floor tile underneath the item ---
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, floor.char, color_tint=None)
                    # Then draw the item on top
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, item.char, color_tint=None)


    def render_inventory_screen(self):
        """Renders the inventory screen."""
        # Draw to inventory_ui_surface instead of internal_surface
        target_surface = self.inventory_ui_surface
        target_surface.fill((0,0,0,0)) # Clear with transparency for background
        # Define the area for the inventory display on the inventory_ui_surface
        # These dimensions are now absolute pixel values relative to inventory_ui_surface
        inventory_width_ratio = 0.7 # Make it 70% of the inventory_ui_surface width
        inventory_height_ratio = 0.8 # Make it 80% of the inventory_ui_surface height
        inventory_rect_width = int(target_surface.get_width() * inventory_width_ratio)
        inventory_rect_height = int(target_surface.get_height() * inventory_height_ratio)
        
        inventory_x = (target_surface.get_width() - inventory_rect_width) // 2
        inventory_y = (target_surface.get_height() - inventory_rect_height) // 2
        
        inventory_rect = pygame.Rect(inventory_x, inventory_y, inventory_rect_width, inventory_rect_height)
        pygame.draw.rect(target_surface, (30, 30, 30), inventory_rect) # Dark gray background
        pygame.draw.rect(target_surface, (100, 100, 100), inventory_rect, 2) # Border
        # Title
        title_text = "INVENTORY"
        title_surface = self.inventory_font_header.render(title_text, True, (255, 215, 0))
        title_rect = title_surface.get_rect(center=(inventory_rect.centerx, inventory_y + self.inventory_font_header.get_linesize() // 2 + 10))
        target_surface.blit(title_surface, title_rect)
        current_y = inventory_y + self.inventory_font_header.get_linesize() + 30
        # List items
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

        # Instructions
        instructions_y_start = inventory_rect.bottom - (self.inventory_font_small.get_linesize() * 2) - 20
        self._draw_text(target_surface, self.inventory_font_small, "Press 1-9/0 to select an item.", (150, 150, 150), item_start_x, instructions_y_start)
        self._draw_text(target_surface, self.inventory_font_small, "Press 'I' to close inventory.", (150, 150, 150), item_start_x, instructions_y_start + self.inventory_font_small.get_linesize() + 5)                    

    def render_inventory_menu(self):
        """Renders the menu for a selected inventory item."""
        if not self.selected_inventory_item:
            return
        target_surface = self.inventory_ui_surface # Draw to the unscaled UI surface
        menu_width = int(target_surface.get_width() * 0.3)
        menu_height = int(self.inventory_font_section.get_linesize() + (self.inventory_font_info.get_linesize() + 5) * 4 + 30)
        
        menu_x = (target_surface.get_width() - menu_width) // 2 # Center horizontally on target_surface
        menu_y = (target_surface.get_height() - menu_height) // 2 # Center vertically on target_surface
        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(target_surface, (40, 40, 40), menu_rect)
        pygame.draw.rect(target_surface, (150, 150, 150), menu_rect, 2)
        current_y = menu_y + 10
        
        item_name_surface = self.inventory_font_section.render(self.selected_inventory_item.name, True, self.selected_inventory_item.color)
        item_name_rect = item_name_surface.get_rect(centerx=menu_rect.centerx)
        target_surface.blit(item_name_surface, (item_name_rect.x, current_y))
        current_y += self.inventory_font_section.get_linesize() + 10
        options = [
            ("U: Use", pygame.K_u),
            ("E: Equip", pygame.K_e),
            ("D: Drop", pygame.K_d),
            ("C: Cancel", pygame.K_c)
        ]
        option_start_x = menu_x + 20
        option_line_spacing = self.inventory_font_info.get_linesize() + 5
        for text, key_code in options:
            is_valid_option = True
            from items.items import Potion, Weapon, Armor # Ensure these are imported if not already
            if text == "U: Use":
                if not isinstance(self.selected_inventory_item, Potion):
                    is_valid_option = False
            elif text == "E: Equip":
                if not (isinstance(self.selected_inventory_item, Weapon) or isinstance(self.selected_inventory_item, Armor)):
                    is_valid_option = False
            
            color = (255, 255, 255) if is_valid_option else (100, 100, 100)
            
            option_surface = self.inventory_font_info.render(text, True, color)
            target_surface.blit(option_surface, (option_start_x, current_y))
            current_y += option_line_spacing

    def _draw_text(self, target_surface, font, text, color, x, y):
        text_surface = font.render(text, True, color)
        target_surface.blit(text_surface, (x, y))

    def _wrap_text(self, text, font, max_width):
        """Wraps text to fit within a maximum width."""
        words = text.split(' ')
        lines = []
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
        pygame.draw.line(self.screen, (50, 50, 50), (config.GAME_AREA_WIDTH, 0), (config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT), 1)
        
        panel_offset_x = config.GAME_AREA_WIDTH + 10
        current_y = 10
        
        font_header = self.font_header
        font_section = self.font_section
        font_info = self.font_info
        font_small = self.font_small
        
        # --- PLAYER SECTION ---
        self._draw_text(self.screen, font_header, "PLAYER", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        self._draw_text(self.screen, font_info, f"Name: {self.player.name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        self._draw_text(self.screen, font_info, f"Level: {self.player.level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        self._draw_text(self.screen, font_info, f"XP: {self.player.current_xp}/{self.player.xp_to_next_level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 15
        
        # --- VITALS SECTION ---
        self._draw_text(self.screen, font_header, "VITALS", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        
        hp_color = (255, 0, 0) if self.player.hp < self.player.max_hp // 3 else (255, 255, 0) if self.player.hp < self.player.max_hp * 2 // 3 else (0, 255, 0)
        self._draw_text(self.screen, font_info, f"HP: {self.player.hp}/{self.player.max_hp}", hp_color, panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        
        bar_width = config.UI_PANEL_WIDTH - 40
        bar_height = int(config.TILE_SIZE * 1.25)
        hp_bar_rect = pygame.Rect(panel_offset_x, current_y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (50, 0, 0), hp_bar_rect)
        pygame.draw.rect(self.screen, (20, 20, 20), hp_bar_rect, 1)
        fill_width = int(bar_width * (self.player.hp / self.player.max_hp))
        pygame.draw.rect(self.screen, hp_color, (panel_offset_x, current_y, fill_width, bar_height))
        current_y += bar_height + 15
        
        # --- ABILITIES (PLAYER SKILLS) SECTION ---
        self._draw_text(self.screen, font_header, "ABILITIES", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        
        if not self.player.abilities:
            self._draw_text(self.screen, font_info, "None", (150, 150, 150), panel_offset_x, current_y)
            current_y += font_info.get_linesize() + 5
        else:
            # Sort abilities by name for consistent display
            sorted_abilities = sorted(self.player.abilities.values(), key=lambda ab: ab.name)
            for i, ability in enumerate(sorted_abilities):
                # Display ability name and cooldown
                cooldown_text = f" (CD: {ability.current_cooldown})" if ability.current_cooldown > 0 else ""
                ability_color = (100, 255, 255) if ability.current_cooldown == 0 else (255, 150, 0) # Cyan when ready, orange when on cooldown
                
                # Add a number for quick access (e.g., 1. Second Wind)
                ability_display_text = f"{i+1}. {ability.name}{cooldown_text}"
                self._draw_text(self.screen, font_info, ability_display_text, ability_color, panel_offset_x, current_y)
                current_y += font_info.get_linesize() + 5
        current_y += 10 # Add some space after abilities
        
        # --- ABILITY SCORES SECTION (Keep this, it's D&D stats) ---
        self._draw_text(self.screen, self.font_header, "ATTRIBUTES", (255, 215, 0), panel_offset_x, current_y) # Renamed header to avoid confusion
        current_y += self.font_header.get_linesize() + 10
        def format_ability(name, score, modifier):
            mod_str = f"+{modifier}" if modifier >= 0 else str(modifier)
            return f"{name}: {score} ({mod_str})"
        
        self._draw_text(self.screen, self.font_info, format_ability("STR", self.player.strength, self.player.get_ability_modifier(self.player.strength)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_ability("DEX", self.player.dexterity, self.player.get_ability_modifier(self.player.dexterity)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_ability("CON", self.player.constitution, self.player.get_ability_modifier(self.player.constitution)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_ability("INT", self.player.intelligence, self.player.get_ability_modifier(self.player.intelligence)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_ability("WIS", self.player.wisdom, self.player.get_ability_modifier(self.player.wisdom)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_ability("CHA", self.player.charisma, self.player.get_ability_modifier(self.player.charisma)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15
                
        # --- SAVING THROWS SECTION ---
        self._draw_text(self.screen, self.font_header, "SAVING THROWS", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        def format_save(name, bonus, proficient):
            bonus_str = f"+{bonus}" if bonus >= 0 else str(bonus)
            prof_char = "*" if proficient else "" # Asterisk for proficiency
            return f"{name}: {bonus_str}{prof_char}"
        self._draw_text(self.screen, self.font_info, format_save("STR", self.player.get_saving_throw_bonus("STR"), self.player.saving_throw_proficiencies["STR"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_save("DEX", self.player.get_saving_throw_bonus("DEX"), self.player.saving_throw_proficiencies["DEX"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_save("CON", self.player.get_saving_throw_bonus("CON"), self.player.saving_throw_proficiencies["CON"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_save("INT", self.player.get_saving_throw_bonus("INT"), self.player.saving_throw_proficiencies["INT"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_save("WIS", self.player.get_saving_throw_bonus("WIS"), self.player.saving_throw_proficiencies["WIS"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, format_save("CHA", self.player.get_saving_throw_bonus("CHA"), self.player.saving_throw_proficiencies["CHA"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15
        
        # --- COMBAT STATS ---
        self._draw_text(self.screen, self.font_header, "COMBAT", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        
        self._draw_text(self.screen, self.font_info, f"AC: {self.player.armor_class}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, f"Proficiency Bonus: +{self.player.proficiency_bonus}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, f"Attack Bonus: +{self.player.attack_bonus}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15
        
        # --- EQUIPPED ITEMS SECTION ---
        self._draw_text(self.screen, self.font_header, "EQUIPMENT", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        
        equipped_weapon_name = self.player.equipped_weapon.name if self.player.equipped_weapon else "None"
        equipped_armor_name = self.player.equipped_armor.name if self.player.equipped_armor else "None"
        self._draw_text(self.screen, self.font_info, f"Weapon: {equipped_weapon_name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.screen, self.font_info, f"Armor: {equipped_armor_name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15
        
        # --- INVENTORY SUMMARY SECTION ---
        self._draw_text(self.screen, self.font_header, "INVENTORY", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        inventory_count = len(self.player.inventory.items)
        inventory_capacity = self.player.inventory.capacity
        self._draw_text(self.screen, self.font_info, f"Items: {inventory_count}/{inventory_capacity}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        
        # Display a few items from inventory if space allows
        max_items_to_show = 3
        for i, item in enumerate(self.player.inventory.items[:max_items_to_show]):
            self._draw_text(self.screen, self.font_small, f"- {item.name}", item.color, panel_offset_x + 10, current_y)
            current_y += self.font_small.get_linesize() + 2
        if inventory_count > max_items_to_show:
            self._draw_text(self.screen, self.font_small, f"...and {inventory_count - max_items_to_show} more", (150, 150, 150), panel_offset_x + 10, current_y)
        current_y += self.font_info.get_linesize() + 15
        
        # --- STATUS EFFECTS SECTION ---
        self._draw_text(self.screen, font_header, "EFFECTS", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        if not self.player.active_status_effects:
            self._draw_text(self.screen, font_info, "None", (150, 150, 150), panel_offset_x, current_y)
        else:
            for effect in self.player.active_status_effects:
                self._draw_text(self.screen, font_info, f"{effect.name} ({effect.turns_left})", (255, 100, 0), panel_offset_x, current_y)
                current_y += font_info.get_linesize() + 5
        current_y += self.font_info.get_linesize() + 15  # Add some space after effects
        
        # --- LOCATION & TURN SECTION ---
        self._draw_text(self.screen, font_header, "STATUS", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        if self.game_state == GameState.TAVERN:
            self._draw_text(self.screen, font_info, "Location: The Prancing Pony Tavern", (150, 200, 255), panel_offset_x, current_y)
        else:
            self._draw_text(self.screen, font_info, f"Dungeon Level: {self.current_level}", (150, 200, 255), panel_offset_x, current_y)
            current_y += font_info.get_linesize() + 5
            self._draw_text(self.screen, font_info, f"Position: ({self.player.x}, {self.player.y})", (150, 150, 150), panel_offset_x, current_y)
            current_y += font_info.get_linesize() + 5
            current = self.get_current_entity()
            if current:
                turn_color = (255, 255, 255) if current == self.player else (255, 100, 100)
                self._draw_text(self.screen, font_info, f"Turn: {current.name}", turn_color, panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 15
       
        # --- CONTROLS / HINTS SECTION ---
        self._draw_text(self.screen, font_header, "CONTROLS", (255, 215, 0), panel_offset_x, current_y)
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
                "+ = Door to dungeon"
            ])
        elif self.game_state == GameState.DUNGEON:
            stairs_dir = self.check_stairs_interaction()
            if stairs_dir:
                controls_list.append(f"Move onto {'<' if stairs_dir == 'up' else '>'} to {'ascend' if stairs_dir == 'up' else 'descend'}")
            dungeon_npc = self.check_dungeon_npc_interaction()
            if dungeon_npc:
                controls_list.append(f"SPACE: Talk to {dungeon_npc.name}")
            else:
                controls_list.append("SPACE: Attack/Pickup")  # Combined action
            controls_list.extend([
                "Arrow keys/hjkl: Move",
                "I: Open Inventory",
                "> = Stairs down",
                "< = Stairs up"
            ])
        elif self.game_state == GameState.INVENTORY:
            controls_list.extend([
                "I: Close Inventory",
                "1-9/0: Select Item",
            ])
        elif self.game_state == GameState.INVENTORY_MENU:
            controls_list.extend([
                "U: Use Item",
                "E: Equip Item",
                "D: Drop Item",
                "C: Cancel",
            ])
        for control in controls_list:
            if current_y + font_small.get_linesize() < max_controls_y:
                self._draw_text(self.screen, font_small, control, (150, 150, 150), panel_offset_x, current_y)
                current_y += font_small.get_linesize() + 5
            else:
                break
