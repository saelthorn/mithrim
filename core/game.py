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
from core.abilities import SecondWind
from core.message_log import MessageBox
from items.items import Potion, Weapon, Armor, Chest
from core.pathfinding import astar # Keep this import

class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"
    INVENTORY = "inventory" # New game state for inventory screen
    INVENTORY_MENU = "inventory_menu" # New state for item interaction menu

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

        self._recalculate_dimensions()
        self._init_fonts()

        self.camera = Camera(config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT, config.TILE_SIZE, config.MESSAGE_LOG_HEIGHT)

        self.game_state = GameState.TAVERN
        self.current_level = 1
        self.max_level_reached = 1
        self.player_has_acted = False # Flag to prevent spamming actions in dungeon

        self.message_log = MessageBox(
            0,
            config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT,
            config.GAME_AREA_WIDTH,
            config.MESSAGE_LOG_HEIGHT,
            font_size=int(config.TILE_SIZE * 0.8)
        )
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 100))
        self.generate_tavern()

        self.selected_inventory_item = None # To hold the item selected in inventory

    def _recalculate_dimensions(self):
        """Recalculate all dynamic dimensions based on current screen size."""
        config.SCREEN_WIDTH, config.SCREEN_HEIGHT = self.screen.get_size()

        current_game_area_height = config.SCREEN_HEIGHT * (1 - config.MESSAGE_LOG_HEIGHT_RATIO)

        TARGET_VERTICAL_TILES = 35

        if current_game_area_height <= 0:
            config.TILE_SIZE = config.MIN_TILE_SIZE
        else:
            config.TILE_SIZE = max(config.MIN_TILE_SIZE, int(current_game_area_height / TARGET_VERTICAL_TILES))

        config.UI_PANEL_WIDTH = int(config.SCREEN_WIDTH * config.UI_PANEL_WIDTH_RATIO)
        config.GAME_AREA_WIDTH = config.SCREEN_WIDTH - config.UI_PANEL_WIDTH

        config.MESSAGE_LOG_HEIGHT = int(config.SCREEN_HEIGHT * config.MESSAGE_LOG_HEIGHT_RATIO)

        if config.GAME_AREA_WIDTH < config.TILE_SIZE * 20:
            config.GAME_AREA_WIDTH = config.TILE_SIZE * 20
            config.UI_PANEL_WIDTH = config.SCREEN_WIDTH - config.GAME_AREA_WIDTH

        if config.MESSAGE_LOG_HEIGHT < config.TILE_SIZE * 3:
            config.MESSAGE_LOG_HEIGHT = config.TILE_SIZE * 3

        if hasattr(self, 'camera'):
            self.camera.tile_size = config.TILE_SIZE
            self.camera.viewport_width = config.GAME_AREA_WIDTH // config.TILE_SIZE
            self.camera.viewport_height = (config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT) // config.TILE_SIZE - 2

        if hasattr(self, 'message_log'):
            self.message_log.rect.x = 0
            self.message_log.rect.y = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
            self.message_log.rect.width = config.GAME_AREA_WIDTH
            self.message_log.rect.height = config.MESSAGE_LOG_HEIGHT
            self.message_log.font = pygame.font.SysFont('consolas', int(config.TILE_SIZE * 1))
            self.message_log.line_height = self.message_log.font.get_linesize()
            self.message_log.max_lines = self.message_log.rect.height // self.message_log.line_height

        self._init_fonts()

    def _init_fonts(self):
        """Initializes or re-initializes fonts based on current TILE_SIZE."""
        temp_tile_size = max(1, config.TILE_SIZE)

        self.font = pygame.font.SysFont('consolas', temp_tile_size)
        self.font_header = pygame.font.SysFont('consolas', int(temp_tile_size * 1), bold=True)
        self.font_section = pygame.font.SysFont('consolas', int(temp_tile_size * 1))
        self.font_info = pygame.font.SysFont('consolas', int(temp_tile_size * 0.9))
        self.font_small = pygame.font.SysFont('consolas', int(temp_tile_size * 0.8))


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
        
        self.camera.update(start_x, start_y, self.game_map.width, self.game_map.height)
        self.npcs = create_tavern_npcs(self.game_map, self.door_position)
        self.entities = [self.player] + self.npcs
        self.turn_order = []
        self.current_turn_index = 0
        self.update_fov() # Call update_fov after entities are set up
        
        self.message_log.add_message("=== WELCOME TO THE PRANCING PONY TAVERN ===", (255, 215, 0))
        self.message_log.add_message("Walk to the door (+) and press any movement key to enter the dungeon!", (150, 150, 255))

    def generate_level(self, level_number, spawn_on_stairs_up=False):
        self.game_state = GameState.DUNGEON
        self.current_level = level_number
        self.max_level_reached = max(self.max_level_reached, level_number)
        
        self.game_map = GameMap(80, 45)
        self.fov = FOV(self.game_map)
        # IMPORTANT: Clear explored only when generating a *new* level
        # self.fov.explored.clear() # This is handled by FOV.__init__ for new FOV object
        
        rooms, self.stairs_positions, self.torch_light_sources = generate_dungeon(self.game_map, level_number)
        
        if spawn_on_stairs_up and 'up' in self.stairs_positions:
            start_x, start_y = self.stairs_positions['up']
        else:
            start_x, start_y = rooms[0].center()
        
        self.player.x = start_x
        self.player.y = start_y
        self.camera.update(start_x, start_y, self.game_map.width, self.game_map.height)
        self.entities = [self.player]

        # Monster generation
        monsters_per_level = min(2 + level_number, len(rooms) - 1)
        monster_rooms = rooms[1:monsters_per_level + 1]

        for i, room in enumerate(monster_rooms):
            x, y = room.center()
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y)):

                if level_number <= 2:
                    monster = Monster(x, y, 'o', f'Orc{i+1}', (63, 127, 63))
                    # Make Orcs capable of poisoning for testing
                    monster.can_poison = True
                    monster.poison_dc = 12
                    monster.hp = 8 + level_number
                    monster.max_hp = 8 + level_number
                    monster.attack_power = 3 + (level_number - 1)
                    monster.armor_class = 13
                    monster.base_xp = 10 + (level_number * 2)
                elif level_number <= 4:
                    monster = Monster(x, y, 'T', f'Troll{i+1}', (127, 63, 63))
                    monster.hp = 12 + level_number * 2
                    monster.max_hp = 12 + level_number * 2
                    monster.attack_power = 4 + level_number
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
        self.update_fov() # Call update_fov after entities are set up
        
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
            self.fov.visible_sources.clear() # Clear current visible sources
            self.fov.explored.clear() # Clear explored for tavern
            for y in range(self.game_map.height):
                for x in range(self.game_map.width):
                    self.fov.visible_sources[(x, y)] = 'player' # Treat all as player light
                    self.fov.explored.add((x, y))
        else:
            # For dungeon levels, clear only the 'visible_sources' each turn
            # 'explored' should persist across turns
            self.fov.visible_sources.clear() # <--- Clear current visible sources
            
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
            self.current_turn_index = 0 # Wrap around if somehow out of bounds
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
            current = self.get_current_entity() # This will be the player
        else:
            # Advance to the next entity in the turn order
            self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
            current = self.get_current_entity()

        # --- NEW: Process player's status effects and cooldowns when player's turn ends ---
        # This ensures cooldowns tick down only after the player has acted.
        # This is called *after* the turn has advanced, so it applies to the entity
        # whose turn just finished.
        if previous_current_entity == self.player:
            self.player.process_status_effects(self) # This will now tick down cooldowns

        if current == self.player:
            self.update_fov()
            self.player_has_acted = False # Reset flag at start of player's turn in dungeon
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
            for entity in self.turn_order: # Iterate over the *old* turn_order
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
            self.current_turn_index = 0 # Player's turn


    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._recalculate_dimensions()
                self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
                self.render()
            
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
                    action_taken = False # Flag for successful action that consumes a turn

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
                                action_taken = True # Talking takes an action
                        elif self.game_state == GameState.DUNGEON:
                            interactable_item = self.get_interactable_item_at(self.player.x, self.player.y)
                            if interactable_item:
                                if isinstance(interactable_item, Mimic):
                                    interactable_item.reveal(self)
                                    self.game_map.items_on_ground.remove(interactable_item)
                                    action_taken = True # Interacting with a mimic takes a turn
                                elif isinstance(interactable_item, Chest):
                                    interactable_item.open(self.player, self)
                                    action_taken = True # Opening a chest takes a turn
                                else:
                                    self.message_log.add_message("You can't interact with that item.", (150, 150, 150))
                            else:
                                target = self.get_adjacent_target()
                                if target:
                                    self.handle_player_attack(target)
                                    action_taken = True # Attacking takes a turn
                                else:
                                    action_taken = self.handle_item_pickup() # Pickup returns True if successful
                    elif event.key == pygame.K_1: # Example: Use '1' for Second Wind
                        if self.game_state == GameState.DUNGEON:
                            second_wind_ability = self.player.abilities.get("second_wind")
                            if second_wind_ability:
                                if second_wind_ability.use(self.player, self):
                                    action_taken = True # Ability use takes a turn
                            else:
                                self.message_log.add_message("You don't have Second Wind.", (150, 150, 150))
                    # Add more elif blocks for other abilities (e.g., K_2, K_3)                    

                    # If an action was successfully taken, set player_has_acted and advance turn
                    if action_taken:
                        if self.game_state == GameState.DUNGEON: # Only set player_has_acted in dungeon
                            self.player_has_acted = True
                        self.next_turn() # Advance turn (this will handle dungeon turn order or tavern ambient)

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
            item_to_pick_up = items_at_player_pos[0] # Pick up the first item found
            if self.player.inventory.add_item(item_to_pick_up):
                item_to_pick_up.on_pickup(self.player, self) # Item's on_pickup handles removal from map
                return True # Picking up an item takes a turn
            else:
                self.message_log.add_message("Your inventory is full!", (255, 0, 0))
        else:
            self.message_log.add_message("Nothing to pick up here.", (150, 150, 150))
        return False # No item picked up, no turn consumed

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
        elif key == pygame.K_0: # For 10th item if capacity is 10
            if len(self.player.inventory.items) == 10:
                self.selected_inventory_item = self.player.inventory.items[9]
                self.game_state = GameState.INVENTORY_MENU
                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
            else:
                self.message_log.add_message("No item at that slot.", (150, 150, 150))

    def handle_inventory_menu_input(self, key):
        """Handles input when an item is selected in the inventory menu."""
        if not self.selected_inventory_item:
            self.game_state = GameState.INVENTORY # Should not happen, but as a safeguard
            return

        action_taken_in_menu = False # Flag for actions that consume a turn
        if key == pygame.K_u: # Use item
            if self.player.use_item(self.selected_inventory_item, self):
                self.selected_inventory_item = None
                self.game_state = GameState.DUNGEON # Exit inventory after use
                action_taken_in_menu = True # Using an item takes a turn
            else:
                self.message_log.add_message(f"Cannot use {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_e: # Equip item
            if self.player.equip_item(self.selected_inventory_item, self):
                self.selected_inventory_item = None
                self.game_state = GameState.DUNGEON # Exit inventory after equip
                action_taken_in_menu = True # Equipping an item takes a turn
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_d: # Drop item
            self.player.inventory.remove_item(self.selected_inventory_item) # Remove from player's inventory
            self.selected_inventory_item.x = self.player.x # Set item's position to player's
            self.selected_inventory_item.y = self.player.y
            self.game_map.items_on_ground.append(self.selected_inventory_item) # Add to map
            self.message_log.add_message(f"You drop the {self.selected_inventory_item.name}.", self.selected_inventory_item.color)
            self.selected_inventory_item = None
            self.game_state = GameState.DUNGEON # Exit inventory after drop
            action_taken_in_menu = True # Dropping an item takes a turn
        elif key == pygame.K_c: # Cancel
            self.selected_inventory_item = None
            self.game_state = GameState.INVENTORY # Go back to inventory list
        
        if action_taken_in_menu:
            self.player_has_acted = True # Set flag if action consumed turn
            self.next_turn() # Advance turn

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
                return True # Player successfully moved to door and transitioned
            
            # Check if new position is blocked by an NPC in tavern
            for npc in self.npcs:
                if npc.x == new_x and npc.y == new_y and npc.alive:
                    self.message_log.add_message(f"You can't move onto {npc.name}.", (255, 150, 0))
                    return False # Blocked by NPC

            # Check if new position is walkable in tavern
            if self.game_map.is_walkable(new_x, new_y):
                self.player.x = new_x
                self.player.y = new_y
                self.update_fov() # Update FOV even in tavern for consistency
                return True # Player successfully moved in tavern

            # If not door, not blocked by NPC, and not walkable
            self.message_log.add_message("You can't move there.", (255, 150, 0))
            return False # Cannot move

        # --- Dungeon-specific movement logic (original) ---
        elif self.game_state == GameState.DUNGEON:
            target = self.get_target_at(new_x, new_y)
            if target:
                self.handle_player_attack(target)
                return True # Return True for successful action (attack)
            elif self.game_map.is_walkable(new_x, new_y):
                self.player.x = new_x
                self.player.y = new_y
                self.update_fov()

                stairs_dir = self.check_stairs_interaction()
                if stairs_dir:
                    self.handle_level_transition(stairs_dir)
                # No else here, as handle_level_transition will call generate_level which resets game state
                return True # Return True for successful action (movement)
            else:
                self.message_log.add_message("You can't move there.", (255, 150, 0))
                return False # Cannot move (blocked by wall/obstacle)

        return False # Default return if game_state is not handled (shouldn't happen)

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
            (200, 200, 255) # Light blue for attack roll info
        )

        is_critical_hit = (d20_roll == 20)
        is_critical_fumble = (d20_roll == 1)

        if is_critical_hit:
            self.message_log.add_message(
                "CRITICAL HIT! You strike a vital spot!",
                (255, 255, 0) # Yellow for critical hit
            )
            hit_successful = True
        elif is_critical_fumble:
            self.message_log.add_message(
                "CRITICAL FUMBLE! You trip over your own feet!",
                (255, 0, 0) # Red for critical fumble
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


            # --- Damage Calculation (already in place) ---
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
                self.player.gain_xp(xp_gained, self) # Assuming game_instance is passed
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
            # In tavern, player doesn't have status effects or abilities with cooldowns
            # that tick down per game turn. So we can return here.
            return

        current = self.get_current_entity()
        if current and current != self.player and current.alive:
            current.take_turn(self.player, self.game_map, self)
            self.next_turn()
        # The 'elif current == self.player:' block is no longer needed here
        # because player.process_status_effects is now called unconditionally above.
        # The player's turn is handled by input in handle_events.
            
    def render(self):
        """Main render method - draws everything"""
        self.screen.fill((0, 0, 0))
        
        if self.game_state == GameState.INVENTORY:
            self.render_inventory_screen()
        elif self.game_state == GameState.INVENTORY_MENU:
            self.render_inventory_screen()
            self.render_inventory_menu()
        else:
            self.render_map_with_fov()
            self.render_items_on_ground() # Render items before entities so entities are on top
            self.render_entities() # Render entities last so they are on top
        
        self.draw_ui()
        self.message_log.render(self.screen)
        
        pygame.display.flip()

    def render_map_with_fov(self):
        map_render_height = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
        
        for y in range(self.camera.y, min(self.camera.y + self.camera.viewport_height, self.game_map.height)):
            for x in range(self.camera.x, min(self.camera.x + self.camera.viewport_width, self.game_map.width)):
                screen_x, screen_y = self.camera.world_to_screen(x, y)
                draw_x = screen_x * config.TILE_SIZE
                draw_y = screen_y * config.TILE_SIZE
                if draw_y < map_render_height:
                    visibility_type = self.fov.get_visibility_type(x, y) # NEW: Get visibility type
                    if visibility_type == 'unexplored':
                        continue # Don't render unexplored areas
                    tile = self.game_map.tiles[y][x]
                    render_color = tile.color # Default to full color
                    if visibility_type == 'player':
                        render_color = tile.color # Full brightness
                    elif visibility_type == 'torch':
                        # Darken torch FOV compared to player FOV
                        render_color = tuple(c // 2 for c in tile.color) # Example: Half brightness
                    elif visibility_type == 'explored':
                        render_color = tile.dark_color # Dimmed color
                    
                    char_surface = self.font.render(tile.char, True, render_color)
                    self.screen.blit(char_surface, (draw_x, draw_y))

    def render_entities(self):
        map_render_height = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
        
        for entity in self.entities:
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y):
                screen_x, screen_y = self.camera.world_to_screen(entity.x, entity.y)
                draw_x = screen_x * config.TILE_SIZE
                draw_y = screen_y * config.TILE_SIZE
                
                if draw_y < map_render_height:
                    visibility_type = self.fov.get_visibility_type(entity.x, entity.y) # NEW: Get visibility type
                    if visibility_type == 'unexplored' or visibility_type == 'explored':
                        continue # Don't render entities if not currently visible
                    render_color = entity.color # Default to full color
                    
                    if visibility_type == 'player':
                        render_color = entity.color # Full brightness
                    elif visibility_type == 'torch':
                        # Darken torch FOV for entities too
                        render_color = tuple(c // 2 for c in entity.color) # Example: Half brightness
                    
                    entity_surface = self.font.render(entity.char, True, render_color)
                    self.screen.blit(entity_surface, (draw_x, draw_y))

    def render_items_on_ground(self):
        """Render items lying on the dungeon floor."""
        map_render_height = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
        
        for item in self.game_map.items_on_ground:
            if self.camera.is_in_viewport(item.x, item.y):
                screen_x, screen_y = self.camera.world_to_screen(item.x, item.y)
                draw_x = screen_x * config.TILE_SIZE
                draw_y = screen_y * config.TILE_SIZE
                if draw_y < map_render_height:
                    visibility_type = self.fov.get_visibility_type(item.x, item.y) # NEW: Get visibility type
                    if visibility_type == 'unexplored':
                        continue # Don't render unexplored items
                    
                    render_color = item.color # Default to full color
                    
                    if visibility_type == 'player':
                        render_color = item.color # Full brightness
                    elif visibility_type == 'torch':
                        # Darken torch FOV for items too
                        render_color = tuple(c // 2 for c in item.color) # Example: Half brightness
                    elif visibility_type == 'explored':
                        # Render a darker version of the item if explored but not visible
                        render_color = tuple(c // 3 for c in item.color) # Use a slightly darker version for explored items
                    
                    item_surface = self.font.render(item.char, True, render_color)
                    self.screen.blit(item_surface, (draw_x, draw_y))

    def render_inventory_screen(self):
        """Renders the inventory screen."""
        # Clear game area
        game_area_rect = pygame.Rect(0, 0, config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT)
        pygame.draw.rect(self.screen, (0, 0, 0), game_area_rect)

        # Draw inventory title
        title_text = self.font_header.render("INVENTORY", True, (255, 215, 0))
        self.screen.blit(title_text, (config.GAME_AREA_WIDTH // 2 - title_text.get_width() // 2, 20))

        current_y = 20 + title_text.get_height() + 20

        if not self.player.inventory.items:
            empty_text = self.font_info.render("Your inventory is empty.", True, (150, 150, 150))
            self.screen.blit(empty_text, (config.GAME_AREA_WIDTH // 2 - empty_text.get_width() // 2, current_y))
        else:
            for i, item in enumerate(self.player.inventory.items):
                item_text_color = item.color
                if self.selected_inventory_item == item:
                    item_text_color = (255, 255, 0) # Highlight selected item

                display_index = i + 1 if i < 9 else 0 # Display 1-9, then 0 for 10th item
                item_text = self.font_info.render(f"{display_index}. {item.name}", True, item_text_color)
                self.screen.blit(item_text, (50, current_y))
                current_y += item_text.get_height() + 5
                if current_y > config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT - 20:
                    break # Prevent drawing off screen

        # Add instructions
        instructions_text = self.font_small.render("Press 'i' to close inventory.", True, (100, 100, 100))
        self.screen.blit(instructions_text, (50, config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT - instructions_text.get_height() - 10))

    def render_inventory_menu(self):
        """Renders the menu for interacting with a selected inventory item."""
        if not self.selected_inventory_item:
            return

        # Draw a semi-transparent overlay or a small box for the menu
        menu_width = 200
        menu_height = 150
        menu_x = config.GAME_AREA_WIDTH // 2 - menu_width // 2
        menu_y = config.SCREEN_HEIGHT // 2 - menu_height // 2 - config.MESSAGE_LOG_HEIGHT // 2

        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, (50, 50, 50, 200), menu_rect) # Dark gray, semi-transparent
        pygame.draw.rect(self.screen, (200, 200, 200), menu_rect, 2) # White border

        # Item name at the top of the menu
        item_name_text = self.font_section.render(self.selected_inventory_item.name, True, self.selected_inventory_item.color)
        self.screen.blit(item_name_text, (menu_x + menu_width // 2 - item_name_text.get_width() // 2, menu_y + 10))

        # Options
        options_y = menu_y + 10 + item_name_text.get_height() + 10
        options = []
        if isinstance(self.selected_inventory_item, Potion):
            options.append(("U: Use", (0, 255, 0)))
        if isinstance(self.selected_inventory_item, (Weapon, Armor)):
            options.append(("E: Equip", (0, 255, 255)))
        options.append(("D: Drop", (255, 150, 0)))
        options.append(("C: Cancel", (150, 150, 150)))

        for option_text, option_color in options:
            option_surface = self.font_info.render(option_text, True, option_color)
            self.screen.blit(option_surface, (menu_x + 20, options_y))
            options_y += option_surface.get_height() + 5


    def _draw_text(self, font, text, color, x, y):
        text_surface = font.render(text, True, color)
        self.screen.blit(text_surface, (x, y))

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
        self._draw_text(font_header, "PLAYER", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        self._draw_text(font_info, f"Name: {self.player.name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        self._draw_text(font_info, f"Level: {self.player.level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        self._draw_text(font_info, f"XP: {self.player.current_xp}/{self.player.xp_to_next_level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 15

        # --- VITALS SECTION ---
        self._draw_text(font_header, "VITALS", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        
        hp_color = (255, 0, 0) if self.player.hp < self.player.max_hp // 3 else (255, 255, 0) if self.player.hp < self.player.max_hp * 2 // 3 else (0, 255, 0)
        self._draw_text(font_info, f"HP: {self.player.hp}/{self.player.max_hp}", hp_color, panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 5
        
        bar_width = config.UI_PANEL_WIDTH - 40
        bar_height = int(config.TILE_SIZE * 1.25)
        hp_bar_rect = pygame.Rect(panel_offset_x, current_y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (50, 0, 0), hp_bar_rect)
        pygame.draw.rect(self.screen, (20, 20, 20), hp_bar_rect, 1)
        fill_width = int(bar_width * (self.player.hp / self.player.max_hp))
        pygame.draw.rect(self.screen, hp_color, (panel_offset_x, current_y, fill_width, bar_height))
        current_y += bar_height + 15
        
        # --- NEW: Abilities Section in UI ---
        self._draw_text(self.font_header, "ABILITIES", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        
        for ab_key, ability in self.player.abilities.items():
            cooldown_str = f" (CD: {ability.current_cooldown})" if ability.current_cooldown > 0 else ""
            self._draw_text(self.font_info, f"{ability.name}{cooldown_str}", (255, 255, 255), panel_offset_x, current_y)
            current_y += self.font_info.get_linesize() + 5
        current_y += self.font_info.get_linesize() + 15 # Add some space

        # --- ABILITY SCORES SECTION ---
        self._draw_text(self.font_header, "ABILITIES", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        def format_ability(name, score, modifier):
            mod_str = f"+{modifier}" if modifier >= 0 else str(modifier)
            return f"{name}: {score} ({mod_str})"
        
        self._draw_text(self.font_info, format_ability("STR", self.player.strength, self.player.get_ability_modifier(self.player.strength)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_ability("DEX", self.player.dexterity, self.player.get_ability_modifier(self.player.dexterity)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_ability("CON", self.player.constitution, self.player.get_ability_modifier(self.player.constitution)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_ability("INT", self.player.intelligence, self.player.get_ability_modifier(self.player.intelligence)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_ability("WIS", self.player.wisdom, self.player.get_ability_modifier(self.player.wisdom)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_ability("CHA", self.player.charisma, self.player.get_ability_modifier(self.player.charisma)), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15
        
        # --- SAVING THROWS SECTION ---
        self._draw_text(self.font_header, "SAVING THROWS", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        def format_save(name, bonus, proficient):
            bonus_str = f"+{bonus}" if bonus >= 0 else str(bonus)
            prof_char = "*" if proficient else "" # Asterisk for proficiency
            return f"{name}: {bonus_str}{prof_char}"
        self._draw_text(self.font_info, format_save("STR", self.player.get_saving_throw_bonus("STR"), self.player.saving_throw_proficiencies["STR"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_save("DEX", self.player.get_saving_throw_bonus("DEX"), self.player.saving_throw_proficiencies["DEX"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_save("CON", self.player.get_saving_throw_bonus("CON"), self.player.saving_throw_proficiencies["CON"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_save("INT", self.player.get_saving_throw_bonus("INT"), self.player.saving_throw_proficiencies["INT"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_save("WIS", self.player.get_saving_throw_bonus("WIS"), self.player.saving_throw_proficiencies["WIS"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, format_save("CHA", self.player.get_saving_throw_bonus("CHA"), self.player.saving_throw_proficiencies["CHA"]), (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15
        
        # --- COMBAT STATS ---
        self._draw_text(self.font_header, "COMBAT", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        
        self._draw_text(self.font_info, f"AC: {self.player.armor_class}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, f"Proficiency Bonus: +{self.player.proficiency_bonus}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, f"Attack Bonus: +{self.player.attack_bonus}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15

        # --- EQUIPPED ITEMS SECTION ---
        self._draw_text(self.font_header, "EQUIPMENT", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        
        equipped_weapon_name = self.player.equipped_weapon.name if self.player.equipped_weapon else "None"
        equipped_armor_name = self.player.equipped_armor.name if self.player.equipped_armor else "None"
        self._draw_text(self.font_info, f"Weapon: {equipped_weapon_name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        self._draw_text(self.font_info, f"Armor: {equipped_armor_name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 15
        
        # --- INVENTORY SUMMARY SECTION ---
        self._draw_text(self.font_header, "INVENTORY", (255, 215, 0), panel_offset_x, current_y)
        current_y += self.font_header.get_linesize() + 10
        inventory_count = len(self.player.inventory.items)
        inventory_capacity = self.player.inventory.capacity
        self._draw_text(self.font_info, f"Items: {inventory_count}/{inventory_capacity}", (255, 255, 255), panel_offset_x, current_y)
        current_y += self.font_info.get_linesize() + 5
        
        # Display a few items from inventory if space allows
        max_items_to_show = 3
        for i, item in enumerate(self.player.inventory.items[:max_items_to_show]):
            self._draw_text(self.font_small, f"- {item.name}", item.color, panel_offset_x + 10, current_y)
            current_y += self.font_small.get_linesize() + 2
        if inventory_count > max_items_to_show:
            self._draw_text(self.font_small, f"...and {inventory_count - max_items_to_show} more", (150, 150, 150), panel_offset_x + 10, current_y)
        current_y += self.font_info.get_linesize() + 15

        # --- STATUS EFFECTS SECTION ---
        self._draw_text(font_header, "EFFECTS", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        if not self.player.active_status_effects:
            self._draw_text(font_info, "None", (150, 150, 150), panel_offset_x, current_y)
        else:
            for effect in self.player.active_status_effects:
                self._draw_text(font_info, f"{effect.name} ({effect.turns_left})", (255, 100, 0), panel_offset_x, current_y)
                current_y += font_info.get_linesize() + 5
        current_y += self.font_info.get_linesize() + 15 # Add some space after effects

        # --- LOCATION & TURN SECTION ---
        self._draw_text(font_header, "STATUS", (255, 215, 0), panel_offset_x, current_y)
        current_y += font_header.get_linesize() + 10
        if self.game_state == GameState.TAVERN:
            self._draw_text(font_info, "Location: The Prancing Pony Tavern", (150, 200, 255), panel_offset_x, current_y)
        else:
            self._draw_text(font_info, f"Dungeon Level: {self.current_level}", (150, 200, 255), panel_offset_x, current_y)
            current_y += font_info.get_linesize() + 5
            self._draw_text(font_info, f"Position: ({self.player.x}, {self.player.y})", (150, 150, 150), panel_offset_x, current_y)
            current_y += font_info.get_linesize() + 5
            current = self.get_current_entity()
            if current:
                turn_color = (255, 255, 255) if current == self.player else (255, 100, 100)
                self._draw_text(font_info, f"Turn: {current.name}", turn_color, panel_offset_x, current_y)
        current_y += font_info.get_linesize() + 15

        # --- CONTROLS / HINTS SECTION ---
        self._draw_text(font_header, "CONTROLS", (255, 215, 0), panel_offset_x, current_y)
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
                controls_list.append("SPACE: Attack/Pickup") # Combined action
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
                self._draw_text(font_small, control, (150, 150, 150), panel_offset_x, current_y)
                current_y += font_small.get_linesize() + 5
            else:
                break
