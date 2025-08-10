import pygame
import random
import config

from core.fov import FOV
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from entities.player import Player, Fighter, Rogue, Wizard
from entities.monster import Monster
from entities.monster import Mimic
from entities.tavern_npcs import create_tavern_npcs
from entities.dungeon_npcs import DungeonHealer
from entities.tavern_npcs import NPC
from core.abilities import SecondWind, PowerAttack, CunningAction, Evasion
from core.message_log import MessageBox
from core.status_effects import PowerAttackBuff, CunningActionDashBuff, EvasionBuff
from items.items import Potion, Weapon, Armor, Chest
from core.pathfinding import astar
from world.tile import floor, MimicTile
import graphics


INTERNAL_WIDTH = 800
INTERNAL_HEIGHT = 600
ASPECT_RATIO = INTERNAL_WIDTH / INTERNAL_HEIGHT


class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"
    INVENTORY = "inventory"
    INVENTORY_MENU = "inventory_menu"
    CHARACTER_MENU = "character_menu"

class Camera:
    def __init__(self, screen_width, screen_height, tile_size, message_log_height):
        self.tile_size = tile_size
        self.viewport_width = screen_width // tile_size
        self.viewport_height = (screen_height - message_log_height) // tile_size - 2
        self.x = 0
        self.y = 0

    def update(self, target_x, target_y, map_width, map_height):
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
        
        self.internal_surface = None
        self.inventory_ui_surface = None
        self.camera = None
        self.message_log = None

        self._recalculate_dimensions() 
        print(f"After initial recalculation, TILE_SIZE: {config.TILE_SIZE}, SCREEN_WIDTH: {config.SCREEN_WIDTH}, SCREEN_HEIGHT: {config.SCREEN_HEIGHT}")
        print(f"Initialized internal_surface: {self.internal_surface.get_size()}")
        
        self._init_fonts()
        
        self.game_state = GameState.TAVERN
        self._previous_game_state = GameState.TAVERN
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
        
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 100))
        
        self.player = Rogue(0, 0, '@', 'Shadowblade', (255, 255, 255))

        self.generate_tavern() 
        self.selected_inventory_item = None

    def _recalculate_dimensions(self):
        """Recalculate all dynamic dimensions based on current screen size."""
        config.SCREEN_WIDTH, config.SCREEN_HEIGHT = self.screen.get_size()
        print(f"Recalculating dimensions. New screen size: {config.SCREEN_WIDTH}x{config.SCREEN_HEIGHT}")
        
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
        print(f"Re-initialized internal_surface in _recalculate_dimensions: {self.internal_surface.get_size()}")

        self.inventory_ui_surface = pygame.Surface((config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT)).convert_alpha()
        self.inventory_ui_surface.fill((0,0,0,0))

        if self.camera is None:
            self.camera = Camera(config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT, config.TILE_SIZE, config.MESSAGE_LOG_HEIGHT)
        
        self.camera.tile_size = config.TILE_SIZE 
        self.camera.viewport_width = config.INTERNAL_GAME_AREA_WIDTH_TILES
        self.camera.viewport_height = config.INTERNAL_GAME_AREA_HEIGHT_TILES
        print(f"Camera viewport (after recalculation): {self.camera.viewport_width}x{self.camera.viewport_height}")

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
        print(f"DEBUG: _init_fonts called. Current config.TILE_SIZE: {config.TILE_SIZE}")
        
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
        
        print("DEBUG: All fonts initialized successfully.")

    def generate_tavern(self):
        self.game_state = GameState.TAVERN
        self.game_map = GameMap(40, 24)
        self.fov = FOV(self.game_map)
        self.door_position = generate_tavern(self.game_map)
        
        start_x, start_y = self.game_map.width // 2, self.game_map.height // 2 + 2
        
        self.player.x = start_x
        self.player.y = start_y
        
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
        
        self.camera.update(start_x, start_y, self.game_map.width, self.game_map.height)
        
        self.entities = [self.player]
        
        monsters_per_level = min(2 + level_number, len(rooms) - 1)
        monster_rooms = rooms[1:monsters_per_level + 1]

        for i, room in enumerate(monster_rooms):
            x, y = room.center()
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y)):

                if level_number <= 2:
                    monster = Monster(x, y, 'r', f'Giant Rat{i+1}', (0, 130, 8))
                    monster.can_poison = True
                    monster.poison_dc = 12
                    monster.hp = 4 + level_number
                    monster.max_hp = 5 + level_number
                    monster.attack_power = 1 + (level_number - 1)
                    monster.armor_class = 10
                    monster.base_xp = 4 + (level_number * 2)
                elif level_number <= 4:
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
                    monster.can_poison = True
                    monster.poison_dc = 12
                    monster.hp = 11 + level_number
                    monster.max_hp = 12 + level_number
                    monster.attack_power = 4 + (level_number - 1)
                    monster.armor_class = 13
                    monster.base_xp = 10 + (level_number * 2)
                elif level_number <= 10:
                    monster = Monster(x, y, 'T', f'Troll{i+1}', (127, 63, 63))
                    monster.hp = 14 + level_number * 2
                    monster.max_hp = 15 + level_number * 2
                    monster.attack_power = 5 + level_number
                    monster.armor_class = 15
                    monster.base_xp = 20 + (level_number * 3)
                else:
                    monster = Monster(x, y, 'D', f'Dragon Whelp{i+1}', (255, 63, 63))
                    monster.hp = 20 + level_number * 3
                    monster.max_hp = 20 + level_number * 3
                    monster.attack_power = 6 + level_number
                    monster.armor_class = 17
                    monster.base_xp = 50 + (level_number * 5)

                if not isinstance(monster, Mimic):
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

                if (item_x, item_y) != (self.player.x, self.player.y) and \
                   (item_x, item_y) not in self.stairs_positions.values() and \
                   not is_blocked_by_non_item_entity and \
                   not is_occupied_by_another_item:

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
            self.fov.compute_fov(self.player.x, self.player.y, radius=8, light_source_type='player')
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

        self.cleanup_entities()

        previous_current_entity = self.get_current_entity()

        if not self.turn_order:
            self.current_turn_index = 0
            current = self.get_current_entity()
        else:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            current = self.get_current_entity()

        # MOVED: Process status effects for the player *only if it was their turn*
        # This ensures effects tick down AFTER their actions, but before the next entity's turn.
        if previous_current_entity == self.player:
            self.player.process_status_effects(self)

        if current == self.player:
            self.update_fov()
            self.player_has_acted = False
            if random.random() < 0.25:
                ambient_msgs = [
                    "The dungeon emits an eerie glow...",
                    "Something shuffles in the darkness..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (180, 180, 180))

    def cleanup_entities(self):
        current_entity_before_cleanup = None
        if self.turn_order and 0 <= self.current_turn_index < len(self.turn_order):
            current_entity_before_cleanup = self.turn_order[self.current_turn_index]

        alive_entities = [e for e in self.entities if e.alive]
        
        if len(alive_entities) != len(self.entities):
            self.entities = alive_entities
            
            new_turn_order = []
            for entity in self.turn_order:
                if entity.alive:
                    new_turn_order.append(entity)
            self.turn_order = new_turn_order
            
            if current_entity_before_cleanup and current_entity_before_cleanup in self.turn_order:
                self.current_turn_index = self.turn_order.index(current_entity_before_cleanup)
            else:
                self.current_turn_index = 0 
        
        if not self.turn_order and self.player.alive:
            self.turn_order = [self.player]
            self.current_turn_index = 0


    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._recalculate_dimensions()
                self.render()
            
            if event.type == pygame.KEYDOWN:
                
                # --- Always accessible menus ---
                if event.key == pygame.K_i:
                    if self.game_state == GameState.DUNGEON or self.game_state == GameState.TAVERN:
                        self._previous_game_state = self.game_state
                        self.game_state = GameState.INVENTORY
                        self.message_log.add_message("Opening Inventory...", (100, 200, 255))
                    elif self.game_state == GameState.INVENTORY:
                        self.game_state = self._previous_game_state
                        self.message_log.add_message("Closing Inventory.", (100, 200, 255))
                        self.selected_inventory_item = None
                    elif self.game_state == GameState.INVENTORY_MENU:
                        self.game_state = GameState.INVENTORY
                        self.selected_inventory_item = None
                        self.message_log.add_message("Returning to Inventory.", (100, 200, 255))
                    elif self.game_state == GameState.CHARACTER_MENU:
                        self.game_state = self._previous_game_state
                        self.message_log.add_message("Closing Character Menu.", (100, 200, 255))
                    continue
                
                if event.key == pygame.K_c:
                    if self.game_state == GameState.DUNGEON or self.game_state == GameState.TAVERN:
                        self._previous_game_state = self.game_state
                        self.game_state = GameState.CHARACTER_MENU
                        self.message_log.add_message("Opening Character Menu...", (100, 200, 255))
                    elif self.game_state == GameState.CHARACTER_MENU:
                        self.game_state = self._previous_game_state
                        self.message_log.add_message("Closing Character Menu.", (100, 200, 255))
                    elif self.game_state == GameState.INVENTORY:
                        self._previous_game_state = GameState.INVENTORY
                        self.game_state = GameState.CHARACTER_MENU
                        self.message_log.add_message("Switching to Character Menu.", (100, 200, 255))
                    elif self.game_state == GameState.INVENTORY_MENU:
                        self._previous_game_state = GameState.INVENTORY_MENU
                        self.game_state = GameState.CHARACTER_MENU
                        self.selected_inventory_item = None
                        self.message_log.add_message("Switching to Character Menu.", (100, 200, 255))
                    continue

                # --- Handle input based on game state ---
                if self.game_state == GameState.INVENTORY:
                    self.handle_inventory_input(event.key)
                    continue
                elif self.game_state == GameState.INVENTORY_MENU:
                    self.handle_inventory_menu_input(event.key)
                    continue
                elif self.game_state == GameState.CHARACTER_MENU:
                    continue

                # --- Player's turn logic (for Dungeon and Tavern) ---
                can_player_act_this_turn = (self.game_state == GameState.TAVERN) or \
                                           (self.get_current_entity() == self.player and not self.player_has_acted)
                
                if not can_player_act_this_turn:
                    continue

                dx, dy = 0, 0
                action_taken = False

                # --- Cunning Action State Handling ---
                if self.player.current_action_state == "cunning_action_choice":
                    if event.key == pygame.K_q: # Choose Dash
                        self.player.current_action_state = "cunning_action_dash"
                        self.player.add_status_effect("CunningActionDashBuff", duration=1, game_instance=self)
                        self.message_log.add_message(f"{self.player.name} is ready to Dash!", (100, 255, 100))
                        continue 
                    elif event.key == pygame.K_ESCAPE: # Cancel Cunning Action choice
                        self.player.current_action_state = None
                        self.message_log.add_message("Cunning Action cancelled.", (150, 150, 150))
                        continue
                    else:
                        self.message_log.add_message("Invalid choice. Choose Dash (Q) or Disengage (E), or ESC to cancel.", (255, 150, 0))
                        continue

                elif self.player.current_action_state == "cunning_action_dash":
                    if event.key in (pygame.K_UP, pygame.K_w):
                        dy = -1
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        dy = 1
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        dx = -1
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        dx = 1
                    elif event.key == pygame.K_ESCAPE:
                        self.player.current_action_state = None
                        self.player.dash_active = False
                        self.message_log.add_message("Dash movement cancelled.", (150, 150, 150))
                        continue
                    else:
                        self.message_log.add_message("You are Dashing. Press a movement key or ESC to cancel.", (255, 150, 0))
                        continue

                    if dx != 0 or dy != 0:
                        target_x = self.player.x + dx * 2
                        target_y = self.player.y + dy * 2
                        
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
                    
                    if pygame.K_1 <= event.key <= pygame.K_9:
                        ability_index = event.key - pygame.K_1
                        if 0 <= ability_index < len(sorted_abilities):
                            ability_to_use = sorted_abilities[ability_index]
                            if self.game_state == GameState.DUNGEON:
                                if ability_to_use.use(self.player, self):
                                    action_taken = True
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
                        continue
                
                # --- End of handle_events: Consume turn if action_taken ---
                if action_taken:
                    if self.game_state == GameState.DUNGEON:
                        self.player_has_acted = True
                    self.next_turn()
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
                return True
            self.message_log.add_message("You can't move there.", (255, 150, 0))
            return False

        elif self.game_state == GameState.DUNGEON:
            # --- Step 1: Identify potential targets at the new position ---
            target_at_new_pos = self.get_target_at(new_x, new_y)

            # --- Step 2: Identify monsters adjacent to player *before* moving ---
            monsters_adjacent_before_move = []
            for entity in self.entities:
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
                # --- Opportunity Attack Check ---
                for monster in monsters_adjacent_before_move:
                    is_still_adjacent_to_monster = (abs(new_x - monster.x) <= 1 and abs(new_y - monster.y) <= 1)

                    # Check if the player is disengaged
                    if not self.player.disengaged and not is_still_adjacent_to_monster:
                        self.message_log.add_message(f"The {monster.name} takes an Opportunity Attack!", (255, 100, 0))
                        monster.attack(self.player, self)  # Monster attacks player
                        if not self.player.alive:
                            return False  # Player died from opportunity attack

                # Now, actually move the player
                self.player.x = new_x
                self.player.y = new_y
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

    def handle_player_attack(self, target):
        if not target.alive:
            return

        d20_roll = random.randint(1, 20)
        attack_modifier = self.player.attack_bonus
        
        power_attack_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, PowerAttackBuff):
                power_attack_buff = effect
                break
        
        if power_attack_buff:
            attack_modifier += power_attack_buff.attack_modifier
            self.message_log.add_message(f"Power Attack: -{abs(power_attack_buff.attack_modifier)} to hit.", (255, 165, 0))
            
        attack_roll_total = d20_roll + attack_modifier

        self.message_log.add_message(
            f"You roll a d20: {d20_roll} + {attack_modifier} (Attack Bonus) = {attack_roll_total}",
            (200, 200, 255)
        )

        is_critical_hit = (d20_roll == 20)
        is_critical_fumble = (d20_roll == 1)

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
            
            if power_attack_buff:
                damage_modifier += power_attack_buff.damage_modifier
                self.message_log.add_message(f"Power Attack: +{power_attack_buff.damage_modifier} damage.", (255, 165, 0))

            damage_total = max(1, damage_dice_rolls_sum + damage_modifier)

            self.message_log.add_message(
                f"You roll {damage_message_dice_part} + {damage_modifier} (Attack Power) = {damage_total} damage!",
                (255, 200, 100)
            )

            damage_dealt = target.take_damage(damage_total, self)

            self.message_log.add_message(
                f"You hit the {target.name} for {damage_dealt} damage!",
                (255, 100, 100)
            )

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

    def add_ambient_combat_message(self):
        messages = [
            "The smell of blood fills the air...",
            "Silence returns to the dungeon...",
            "Your weapon drips with monster blood..."
        ]
        self.message_log.add_message(random.choice(messages), (170, 170, 170))

    def update(self, dt):
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
        
        if self.game_state == GameState.TAVERN or \
           self.game_state == GameState.INVENTORY or \
           self.game_state == GameState.INVENTORY_MENU or \
           self.game_state == GameState.CHARACTER_MENU:
            return

        current = self.get_current_entity()
        if current and current != self.player and current.alive:
            current.take_turn(self.player, self.game_map, self)
            self.next_turn()

    def handle_window_resize(self):
        old_scale = self.scale
        
        self.scale_x = self.screen.get_width() / INTERNAL_WIDTH
        self.scale_y = self.screen.get_height() / INTERNAL_HEIGHT
        self.scale = min(self.scale_x, self.scale_y)
        
        print(f"Resized to: {self.screen.get_size()}")
        print(f"New scale: {self.scale}")
        
        if abs(old_scale - self.scale) > 0.1:
            self.internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
            self.font = pygame.font.SysFont('consolas', int(INTERNAL_HEIGHT/50))

    def render(self):
        """Main render method - draws everything"""
        self.screen.fill((0, 0, 0))
        self.internal_surface.fill((0, 0, 0))
        
        self.inventory_ui_surface.fill((0,0,0,0))
        if self.game_state == GameState.INVENTORY:
            self.render_inventory_screen() 
            self.screen.blit(self.inventory_ui_surface, (0, 0))
        elif self.game_state == GameState.INVENTORY_MENU:
            self.render_inventory_screen() 
            self.screen.blit(self.inventory_ui_surface, (0, 0))
            
            self.render_inventory_menu_popup()
            
        elif self.game_state == GameState.CHARACTER_MENU:
            self.render_character_menu()
            self.screen.blit(self.inventory_ui_surface, (0, 0))
        else:
            self.render_map_with_fov()
            self.render_items_on_ground()
            self.render_entities()
            
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
        self.draw_ui()
        self.message_log.render(self.screen)
        
        pygame.display.flip()

    def render_map_with_fov(self):
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
        
        for y in range(self.camera.y, min(self.camera.y + self.camera.viewport_height, self.game_map.height)):
            for x in range(self.camera.x, min(self.camera.x + self.camera.viewport_width, self.game_map.width)):
                screen_x, screen_y = self.camera.world_to_screen(x, y)
                draw_x = screen_x * config.TILE_SIZE
                draw_y = screen_y * config.TILE_SIZE                
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
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
                    
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, tile.char, color_tint=render_color_tint)

    def render_entities(self):
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for entity in self.entities:
            if isinstance(entity, Mimic) and entity.disguised:
                continue 
            
            visibility_type = self.fov.get_visibility_type(entity.x, entity.y)
            
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y) and \
               (visibility_type == 'player' or visibility_type == 'torch' or visibility_type == 'explored'):
                
                screen_x, screen_y = self.camera.world_to_screen(entity.x, entity.y)
                
                if (0 <= screen_x * config.TILE_SIZE < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= screen_y * config.TILE_SIZE < map_render_height):
                    
                    entity_color_tint = None
                    if visibility_type == 'player':
                        entity_color_tint = None
                    elif visibility_type == 'torch':
                        entity_color_tint = (128, 128, 128, 255)
                    elif visibility_type == 'explored':
                        entity_color_tint = (60, 60, 60, 255)
                    
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, floor.char, color_tint=entity_color_tint)
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, entity.char, color_tint=entity_color_tint)

    def render_items_on_ground(self):
        """Render items lying on the dungeon floor."""
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for item in self.game_map.items_on_ground:
            if isinstance(item, Mimic) and item.disguised:
                continue 
            
            visibility_type = self.fov.get_visibility_type(item.x, item.y)
            
            if self.camera.is_in_viewport(item.x, item.y) and \
               (visibility_type == 'player' or visibility_type == 'torch' or visibility_type == 'explored'):
                
                screen_x, screen_y = self.camera.world_to_screen(item.x, item.y)
                
                if (0 <= screen_x * config.TILE_SIZE < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= screen_y * config.TILE_SIZE < map_render_height):
                    
                    item_color_tint = None
                    if visibility_type == 'player':
                        item_color_tint = None
                    elif visibility_type == 'torch':
                        item_color_tint = (128, 128, 128, 255)
                    elif visibility_type == 'explored':
                        item_color_tint = (60, 60, 60, 255)
                    
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, floor.char, color_tint=item_color_tint)
                    graphics.draw_tile(self.internal_surface, screen_x, screen_y, item.char, color_tint=item_color_tint)

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
            
            self._draw_text(target_surface, self.inventory_font_small, "U: Use Item", (150, 150, 150), item_start_x, menu_instructions_y)
            menu_instructions_y += self.inventory_font_small.get_linesize() + 5
            self._draw_text(target_surface, self.inventory_font_small, "E: Equip Item", (150, 150, 150), item_start_x, menu_instructions_y)
            menu_instructions_y += self.inventory_font_small.get_linesize() + 5
            self._draw_text(target_surface, self.inventory_font_small, "D: Drop Item", (150, 150, 150), item_start_x, menu_instructions_y)
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
        
        draw_centered_header(self.screen, self.font_header, "INVENTORY", (255, 215, 0), current_y)
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
