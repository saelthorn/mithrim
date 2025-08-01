import pygame
import random
# from core.events import handle_input # REMOVE THIS IMPORT
from core.fov import FOV
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from entities.player import Player
from entities.monster import Monster
from entities.tavern_npcs import create_tavern_npcs
from world.tile import stairs_down, stairs_up, door # Import 'door' tile
from config import SCREEN_WIDTH, SCREEN_HEIGHT, TILE_SIZE, UI_PANEL_WIDTH, GAME_AREA_WIDTH
from core.message_log import MessageBox # Import the MessageBox class

class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"

class Camera:
    def __init__(self, screen_width, screen_height, tile_size):
        self.tile_size = tile_size
        # Adjust viewport width to account for the UI panel
        self.viewport_width = GAME_AREA_WIDTH // tile_size
        self.viewport_height = screen_height // tile_size - 2  # Leave room for UI at bottom of game area if needed, or adjust as desired
        self.x = 0
        self.y = 0
    
    def update(self, target_x, target_y, map_width, map_height):
        """Center camera on target position"""
        # Center the camera on the target
        self.x = target_x - self.viewport_width // 2
        self.y = target_y - self.viewport_height // 2
        
        # Clamp camera to map boundaries
        self.x = max(0, min(self.x, map_width - self.viewport_width))
        self.y = max(0, min(self.y, map_height - self.viewport_height))
    
    def world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates relative to game area"""
        screen_x = world_x - self.x
        screen_y = world_y - self.y
        return screen_x, screen_y
    
    def is_in_viewport(self, world_x, world_y):
        """Check if world coordinates are visible in the current viewport"""
        screen_x, screen_y = self.world_to_screen(world_x, world_y)
        return (0 <= screen_x < self.viewport_width and 
                0 <= screen_y < self.viewport_height)

class Game:
    def __init__(self, screen):
        self.screen = screen
        self.tile_size = TILE_SIZE # Use TILE_SIZE from config
        self.font = pygame.font.SysFont('consolas', self.tile_size)
        
        # Initialize camera with the new GAME_AREA_WIDTH
        self.camera = Camera(GAME_AREA_WIDTH, SCREEN_HEIGHT, self.tile_size)
        
        # Game state management
        self.game_state = GameState.TAVERN
        
        # Multi-level system
        self.current_level = 1
        self.max_level_reached = 1
        
        # --- FIX START ---
        # Create message log BEFORE calling generate_tavern()
        self.message_log = MessageBox(
            GAME_AREA_WIDTH + 10, # Start 10 pixels right of game area
            SCREEN_HEIGHT - 160,  # 160 pixels from bottom
            UI_PANEL_WIDTH - 20,  # Width of UI panel minus padding
            150,                  # Height of message box
            font_size=16          # Smaller font for messages
        )

        # Add initial messages (these will now work)
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 100))
        self.message_log.add_message("You hear strange noises in the distance...", (200, 200, 200))
        # --- FIX END ---

        # Generate tavern first (this will now find self.message_log)
        self.generate_tavern()


    def generate_tavern(self):
        """Generate the starting tavern"""
        self.game_state = GameState.TAVERN
        
        # Create tavern map (smaller than dungeon)
        self.game_map = GameMap(40, 24)
        self.fov = FOV(self.game_map)
        
        # Generate tavern layout
        self.door_position = generate_tavern(self.game_map)
        
        # Create player in tavern center
        start_x, start_y = self.game_map.width // 2, self.game_map.height // 2 + 2
        
        if hasattr(self, 'player'):
            # Move existing player
            self.player.x = start_x
            self.player.y = start_y
        else:
            # Create new player
            self.player = Player(start_x, start_y, '@', 'Hero', (255, 255, 255))
        
        # Calculate camera position to center the tavern map if it's smaller than the viewport
        if self.game_map.width < self.camera.viewport_width:
            self.camera.x = (self.game_map.width - self.camera.viewport_width) // 2
        else:
            self.camera.x = self.player.x - self.camera.viewport_width // 2
        
        if self.game_map.height < self.camera.viewport_height:
            self.camera.y = (self.game_map.height - self.camera.viewport_height) // 2
        else:
            self.camera.y = self.player.y - self.camera.viewport_height // 2
        
        # Ensure camera position is not negative (top-left corner of the map is 0,0)
        self.camera.x = max(0, self.camera.x)
        self.camera.y = max(0, self.camera.y)

        # Clamp camera to map boundaries (already handled by camera.update, but good to be explicit)
        self.camera.x = min(self.camera.x, self.game_map.width - self.camera.viewport_width)
        self.camera.y = min(self.camera.y, self.game_map.height - self.camera.viewport_height)

        # Update camera to follow player (this will re-clamp based on player, but our manual centering
        # for smaller maps will take precedence if the map fits entirely)
        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
        
        # Create tavern NPCs
        self.npcs = create_tavern_npcs(self.game_map, self.door_position)
        self.entities = [self.player] + self.npcs
        
        # NO TURN SYSTEM IN TAVERN - just set entities for rendering
        self.turn_order = []
        self.current_turn_index = 0
        
        # Compute initial FOV
        self.update_fov()
        
        # These message_log calls will now work
        self.message_log.add_message("=== WELCOME TO THE PRANCING PONY TAVERN ===", (255, 215, 0))
        self.message_log.add_message("Walk to the door (+) and press any movement key to enter the dungeon!", (150, 150, 255))

    def generate_level(self, level_number, spawn_on_stairs_up=False):
        """Generate a new dungeon level"""
        self.game_state = GameState.DUNGEON
        self.current_level = level_number
        self.max_level_reached = max(self.max_level_reached, level_number)
        
        # Create new map
        self.game_map = GameMap(80, 45)
        self.fov = FOV(self.game_map)
        
        # Generate dungeon
        rooms, self.stairs_positions = generate_dungeon(self.game_map, level_number)
        
        # Determine player spawn position
        if spawn_on_stairs_up and 'up' in self.stairs_positions:
            # Spawning from going up stairs - start near stairs up
            start_x, start_y = self.stairs_positions['up']
        else:
            # Normal spawn or going down stairs - start in first room
            start_x, start_y = rooms[0].center()
        
        # Move player
        self.player.x = start_x
        self.player.y = start_y
        
        # Update camera to follow player
        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
        
        self.entities = [self.player]
        
        # Create monsters (more monsters on deeper levels)
        monsters_per_level = min(2 + level_number, len(rooms) - 1)
        monster_rooms = rooms[1:monsters_per_level + 1]
        
        for i, room in enumerate(monster_rooms):
            x, y = room.center()
            
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y)):
                
                # Different monsters on different levels
                if level_number <= 2:
                    monster = Monster(x, y, 'o', f'Orc{i+1}', (63, 127, 63))
                    monster.hp = 8 + level_number
                    monster.max_hp = 8 + level_number
                    monster.attack_power = 3 + (level_number - 1)
                    monster.base_xp = 10 + (level_number * 2) # Assign base_xp
                elif level_number <= 4:
                    monster = Monster(x, y, 'T', f'Troll{i+1}', (127, 63, 63))
                    monster.hp = 12 + level_number * 2
                    monster.max_hp = 12 + level_number * 2
                    monster.attack_power = 4 + level_number
                    monster.base_xp = 20 + (level_number * 3) # Assign base_xp
                else:
                    monster = Monster(x, y, 'D', f'Dragon{i+1}', (255, 63, 63))
                    monster.hp = 20 + level_number * 3
                    monster.max_hp = 20 + level_number * 3
                    monster.attack_power = 6 + level_number
                    monster.base_xp = 50 + (level_number * 5) # Assign base_xp
                
                self.entities.append(monster)
                self.message_log.add_message(f"A {monster.name} appears!", (255, 150, 0))
        
        # Initialize turn system
        for entity in self.entities:
            entity.roll_initiative()
        
        self.turn_order = sorted(self.entities, key=lambda e: e.initiative, reverse=True)
        self.current_turn_index = 0
        
        # Compute initial FOV
        self.update_fov()
        
        self.message_log.add_message(f"=== ENTERED DUNGEON LEVEL {level_number} ===", (0, 255, 255))
        if hasattr(self, 'stairs_positions'):
            self.message_log.add_message(f"Stairs down at {self.stairs_positions.get('down')}, Stairs up at {self.stairs_positions.get('up')}", (150, 150, 255))

    def check_tavern_door_interaction(self):
        """Check if player is at tavern door"""
        if self.game_state == GameState.TAVERN:
            player_pos = (self.player.x, self.player.y)
            return player_pos == self.door_position
        return False

    def check_npc_interaction(self):
        """Check if player is adjacent to an NPC"""
        if self.game_state == GameState.TAVERN:
            for npc in self.npcs:
                if (abs(self.player.x - npc.x) <= 1 and 
                    abs(self.player.y - npc.y) <= 1 and
                    (abs(self.player.x - npc.x) + abs(self.player.y - npc.y)) == 1):
                    return npc
        return None

    def check_stairs_interaction(self):
        """Check if player is on stairs and handle level transition"""
        if self.game_state == GameState.DUNGEON:
            player_pos = (self.player.x, self.player.y)
            
            if hasattr(self, 'stairs_positions'):
                if 'down' in self.stairs_positions and player_pos == self.stairs_positions['down']:
                    return 'down'
                elif 'up' in self.stairs_positions and player_pos == self.stairs_positions['up']:
                    return 'up'
        return None

    def handle_level_transition(self, direction):
        """Handle moving between levels"""
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
        """Update field of view from player position"""
        if self.game_state == GameState.TAVERN:
            # In tavern, reveal everything - no fog of war
            self.fov.visible.clear()
            self.fov.explored.clear()
            for y in range(self.game_map.height):
                for x in range(self.game_map.width):
                    self.fov.visible.add((x, y))
                    self.fov.explored.add((x, y))
        else:
            # In dungeon, use normal FOV
            self.fov.compute_fov(self.player.x, self.player.y, radius=8)

    def get_current_entity(self):
        if not self.turn_order or self.game_state == GameState.TAVERN:
            return self.player  # In tavern, always player's turn
        return self.turn_order[self.current_turn_index]

    def next_turn(self): 
        """Advance to the next entity's turn with ambient messages""" 
        # In tavern, add ambient messages occasionally 
        if self.game_state == GameState.TAVERN: 
            if random.random() < 0.3: # 30% chance 
                ambient_msgs = [ "The torch flickers, casting long shadows...", "Distant drips echo through the stone halls...", "You hear the scuttling of tiny feet...", "A cold breeze chills the back of your neck..." ] 
                self.message_log.add_message(random.choice(ambient_msgs), (150, 150, 150)) 
                
                return            
        
        if not self.turn_order:
            return

        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        current = self.get_current_entity()

        # Update FOV if player's turn and add occasional ambient messages
        if current == self.player:
            self.update_fov()
            if random.random() < 0.25:  # 25% chance
                ambient_msgs = [
                    "The dungeon emits an eerie glow...",
                    "Something shuffles in the darkness...",
                    "Your footsteps echo hollowly...",
                    "The air feels heavy and stale..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (180, 180, 180))

        self.cleanup_entities()

    def cleanup_entities(self):
        """Remove dead entities from the game"""
        alive_entities = [e for e in self.entities if e.alive]
        if len(alive_entities) != len(self.entities):
            self.entities = alive_entities
            self.turn_order = [e for e in self.turn_order if e.alive]
            # Adjust turn index if necessary
            if self.current_turn_index >= len(self.turn_order):
                self.current_turn_index = 0

    def update(self, dt):
        """Handle non-player turns automatically"""
        # Update camera to follow player
        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
        
        # In tavern, no automatic turns - it's free movement
        if self.game_state == GameState.TAVERN:
            return
            
        current = self.get_current_entity()
        if (current and current != self.player and current.alive and 
            self.game_state == GameState.DUNGEON):
            current.take_turn(self.player, self.game_map, self.fov)
            self.next_turn()
            
    def check_for_target(self):
        """Check for a target (monster) in the player's vicinity."""
        for entity in self.entities:
            if entity != self.player and entity.alive:
                if (abs(self.player.x - entity.x) <= 1 and 
                    abs(self.player.y - entity.y) <= 1):
                    return entity
        return None


    def handle_events(self):
        """Handle all game events including player input"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.KEYDOWN:
                # Only process player input if it's the player's turn (or in tavern)
                if self.get_current_entity() == self.player:
                    dx, dy = 0, 0

                    # Movement keys
                    if event.key == pygame.K_UP or event.key == pygame.K_k:
                        dy = -1
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_j:
                        dy = 1
                    elif event.key == pygame.K_LEFT or event.key == pygame.K_h:
                        dx = -1
                    elif event.key == pygame.K_RIGHT or event.key == pygame.K_l:
                        dx = 1
                    elif event.key == pygame.K_y:  # Diagonal up-left
                        dx, dy = -1, -1
                    elif event.key == pygame.K_u:  # Diagonal up-right
                        dx, dy = 1, -1
                    elif event.key == pygame.K_b:  # Diagonal down-left
                        dx, dy = -1, 1
                    elif event.key == pygame.K_n:  # Diagonal down-right
                        dx, dy = 1, 1
                    
                    # Special interaction key (e.g., SPACE for talking/attacking)
                    elif event.key == pygame.K_SPACE:
                        if self.game_state == GameState.TAVERN:
                            npc = self.check_npc_interaction()
                            if npc:
                                self.message_log.add_message(f"{npc.name}: {npc.get_dialogue()}", (200, 200, 255))
                                # No turn advance for talking
                            else:
                                # If no NPC, maybe try to attack adjacent in tavern (though not typical)
                                target = self.get_adjacent_target()
                                if target:
                                    self.handle_player_attack(target)
                                    self.next_turn() # Advance turn after attack
                        elif self.game_state == GameState.DUNGEON:
                            target = self.get_adjacent_target()
                            if target:
                                self.handle_player_attack(target)
                                self.next_turn() # Advance turn after attack
                            # else: maybe a "wait" action or search?
                            
                    # If a movement key was pressed
                    if dx != 0 or dy != 0:
                        self.handle_player_action(dx, dy) # This method now handles all logic
                        # handle_player_action will return True if an action was taken
                        # and will call next_turn if in dungeon state
                        
        return True


    def handle_player_action(self, dx, dy):
        """Handle player movement, attack, or special interactions based on game state."""
        new_x = self.player.x + dx
        new_y = self.player.y + dy

        action_taken = False

        if self.game_state == GameState.TAVERN:
            # Check for tavern door interaction first
            if (new_x, new_y) == self.door_position:
                self.message_log.add_message("You step through the door into the darkness...", (100, 255, 100))
                self.generate_level(1) # Generate first dungeon level
                action_taken = True
            else:
                # In tavern, player can't attack, just move or be blocked by NPCs
                target_npc = None
                for npc in self.npcs:
                    if npc.x == new_x and npc.y == new_y and npc.alive:
                        target_npc = npc
                        break
                
                if target_npc:
                    self.message_log.add_message(f"You bump into {target_npc.name}.", (200, 200, 200))
                    action_taken = False # Cannot move through NPC
                elif self.game_map.is_walkable(new_x, new_y):
                    self.player.x = new_x
                    self.player.y = new_y
                    action_taken = True
                
            if action_taken:
                self.update_fov() # Update FOV after movement
                # No turn system in tavern, so no next_turn() call here
                
        elif self.game_state == GameState.DUNGEON:
            # Check for attack first
            target_entity = self.get_target_at(new_x, new_y)
            if target_entity:
                self.handle_player_attack(target_entity)
                action_taken = True
            elif self.game_map.is_walkable(new_x, new_y):
                self.player.x = new_x
                self.player.y = new_y
                action_taken = True
                self.update_fov() # Update FOV after movement
                
                # Check for stairs interaction after moving
                stairs_direction = self.check_stairs_interaction()
                if stairs_direction:
                    self.handle_level_transition(stairs_direction)
                else:
                    self.next_turn() # Advance turn after movement
            
        return action_taken


    def get_target_at(self, x, y):
        """Get entity at position if it exists"""
        for entity in self.entities:
            if entity.x == x and entity.y == y and entity != self.player and entity.alive:
                return entity
        return None
    
    def get_adjacent_target(self):
        """Check for adjacent target to attack"""
        for dx, dy in [(0,1), (1,0), (0,-1), (-1,0), (-1,-1), (1,-1), (-1,1), (1,1)]:  # All 8 directions
            target = self.get_target_at(self.player.x + dx, self.player.y + dy)
            if target:
                return target
        return None

    def handle_player_attack(self, target):
        """Handle player attack with damage calculation"""
        if target.alive:
            damage_dealt = self.player.attack(target)
            
            if damage_dealt > 0:
                self.message_log.add_message(
                    f"You hit {target.name} for {damage_dealt} damage!",
                    (255, 100, 100)
                )
                
                if not target.alive:
                    self.message_log.add_message(
                        f"{target.name} dies! [+{target.base_xp} XP]",
                        (100, 255, 100)
                    )
                else:
                    self.message_log.add_message(
                        f"{target.name} has {target.hp}/{target.max_hp} HP",
                        (255, 255, 0)
                    )
            else:
                self.message_log.add_message(
                    f"Your attack misses {target.name}!",
                    (200, 200, 200)
                )
            
            # next_turn() is called by handle_player_action after attack
            # or directly by handle_events if SPACE is pressed for attack
            # so we don't call it here to avoid double calls.


    def render(self):
        """Render the game"""
        self.screen.fill((0, 0, 0)) # Clear the entire screen
        
        # Draw the game map and entities on the left side (GAME_AREA)
        self.render_map_with_fov()
        self.render_entities()
        
        # Draw the UI panel on the right side
        self.draw_ui()
        
        # Render the message log
        self.message_log.render(self.screen)
        
        pygame.display.flip()

    def render_map_with_fov(self):
        """Render map tiles considering field of view and camera position"""
        # Iterate only over the visible portion of the map within the camera's viewport
        for y in range(self.camera.y, min(self.camera.y + self.camera.viewport_height, self.game_map.height)):
            for x in range(self.camera.x, min(self.camera.x + self.camera.viewport_width, self.game_map.width)):
                screen_x, screen_y = self.camera.world_to_screen(x, y)
                
                # Ensure drawing happens within the game area (left side)
                draw_x = screen_x * self.tile_size
                draw_y = screen_y * self.tile_size

                if self.game_state == GameState.TAVERN:
                    # In tavern, always show everything in full color
                    tile = self.game_map.tiles[y][x]
                    char_surface = self.font.render(tile.char, True, tile.color)
                    self.screen.blit(char_surface, (draw_x, draw_y))
                else:
                    # In dungeon, use fog of war
                    if self.fov.is_visible(x, y):
                        # Tile is visible - draw in full color
                        tile = self.game_map.tiles[y][x]
                        char_surface = self.font.render(tile.char, True, tile.color)
                        self.screen.blit(char_surface, (draw_x, draw_y))
                    elif self.fov.is_explored(x, y):
                        # Tile has been seen before - draw in dark color
                        tile = self.game_map.tiles[y][x]
                        char_surface = self.font.render(tile.char, True, tile.dark_color)
                        self.screen.blit(char_surface, (draw_x, draw_y))
                    # Unexplored tiles remain black

    def render_entities(self):
        """Render entities only if they're visible and in camera viewport"""
        for entity in self.entities:
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y):
                screen_x, screen_y = self.camera.world_to_screen(entity.x, entity.y)
                
                # Ensure drawing happens within the game area (left side)
                draw_x = screen_x * self.tile_size
                draw_y = screen_y * self.tile_size

                if self.game_state == GameState.TAVERN:
                    # In tavern, always show all entities
                    entity_surface = self.font.render(entity.char, True, entity.color)
                    self.screen.blit(entity_surface, (draw_x, draw_y))
                else:
                    # In dungeon, only show if visible
                    if self.fov.is_visible(entity.x, entity.y):
                        entity_surface = self.font.render(entity.char, True, entity.color)
                        self.screen.blit(entity_surface, (draw_x, draw_y))

    def _draw_text(self, font, text, color, x, y):
        """Helper to draw text on the screen"""
        text_surface = font.render(text, True, color)
        self.screen.blit(text_surface, (x, y))

    def draw_ui(self):
        """Draw user interface on the right-side panel"""
        # Define the UI panel's drawing area
        ui_panel_rect = pygame.Rect(GAME_AREA_WIDTH, 0, UI_PANEL_WIDTH, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, (20, 20, 20), ui_panel_rect)  # Dark background for UI panel
        pygame.draw.line(self.screen, (50, 50, 50), (GAME_AREA_WIDTH, 0), (GAME_AREA_WIDTH, SCREEN_HEIGHT), 1)  # Separator line
        
        # Offset for drawing UI elements within the panel
        panel_offset_x = GAME_AREA_WIDTH + 10  # 10 pixels padding from the left edge of the panel
        current_y = 10  # Starting Y position for UI elements
        font_large = pygame.font.SysFont('consolas', 20)
        font_medium = pygame.font.SysFont('consolas', 18)
        font_small = pygame.font.SysFont('consolas', 16)
        
        # --- Player Info ---
        self._draw_text(font_large, "PLAYER", (124, 252, 0), panel_offset_x, current_y)
        current_y += 30
        self._draw_text(font_medium, f"Name: {self.player.name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += 25
        self._draw_text(font_medium, f"Level: {self.player.level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += 25
        self._draw_text(font_medium, f"XP: {self.player.current_xp}/{self.player.xp_to_next_level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += 35
        
        # --- Vitals ---
        self._draw_text(font_large, "VITALS", (124, 252, 0), panel_offset_x, current_y)
        current_y += 30
        hp_color = (255, 0, 0) if self.player.hp < self.player.max_hp // 3 else (255, 255, 0) if self.player.hp < self.player.max_hp * 2 // 3 else (0, 255, 0)
        self._draw_text(font_medium, f"HP: {self.player.hp}/{self.player.max_hp}", hp_color, panel_offset_x, current_y)
        current_y += 25
        
        # Health Bar
        bar_width = UI_PANEL_WIDTH - 40  # Adjust for padding
        bar_height = 15
        hp_bar_rect = pygame.Rect(panel_offset_x, current_y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (50, 0, 0), hp_bar_rect)  # Background of health bar
        fill_width = int(bar_width * (self.player.hp / self.player.max_hp))
        pygame.draw.rect(self.screen, hp_color, (panel_offset_x, current_y, fill_width, bar_height)) # Health fill
        current_y += bar_height + 10 # Move past health bar

        # --- Location & Turn Indicator ---
        if self.game_state == GameState.TAVERN:
            self._draw_text(font_medium, "Location: The Prancing Pony Tavern", (255, 215, 0), panel_offset_x, current_y)
        else:
            self._draw_text(font_medium, f"Dungeon Level: {self.current_level}", (255, 255, 255), panel_offset_x, current_y)
            current_y += 25
            self._draw_text(font_medium, f"Position: ({self.player.x}, {self.player.y})", (150, 150, 150), panel_offset_x, current_y)
            current_y += 25
            current = self.get_current_entity()
            if current:
                turn_color = (255, 255, 255) if current == self.player else (255, 100, 100)
                self._draw_text(font_medium, f"Turn: {current.name}", turn_color, panel_offset_x, current_y)
        current_y += 35

        # --- Context-sensitive hints & Instructions ---
        self._draw_text(font_large, "HINTS & CONTROLS", (124, 252, 0), panel_offset_x, current_y)
        current_y += 30

        if self.game_state == GameState.TAVERN:
            if self.check_tavern_door_interaction():
                self._draw_text(font_small, "Stand on the door (+) and move to enter the dungeon!", (255, 255, 0), panel_offset_x, current_y)
                current_y += 20
            npc = self.check_npc_interaction()
            if npc:
                self._draw_text(font_small, f"Press SPACE to talk to {npc.name}", (0, 255, 255), panel_offset_x, current_y)
                current_y += 20
            instructions = [
                "Arrow keys / hjkl: Move",
                "SPACE: Talk to NPCs", 
                "+ = Door to dungeon",
                "B = Bartender, p = Patron"
            ]
        else:
            stairs_direction = self.check_stairs_interaction()
            if stairs_direction:
                stairs_color = (255, 255, 0)
                if stairs_direction == 'down':
                    self._draw_text(font_small, "Stand on stairs down - Move to descend", stairs_color, panel_offset_x, current_y)
                elif stairs_direction == 'up' and self.current_level > 1:
                    self._draw_text(font_small, "Stand on stairs up - Move to ascend", stairs_color, panel_offset_x, current_y)
                elif stairs_direction == 'up' and self.current_level == 1:
                    self._draw_text(font_small, "Stand on stairs up - Move to return to tavern", stairs_color, panel_offset_x, current_y)
                current_y += 20
            instructions = [
                "Arrow keys / hjkl: Move",
                "yubn: Diagonal movement", 
                "Walk into enemies to attack",
                "> = Stairs down, < = Stairs up"
            ]
        
        for instruction in instructions:
            self._draw_text(font_small, instruction, (150, 150, 150), panel_offset_x, current_y)
            current_y += 20
