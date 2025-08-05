import pygame
import random
from core.fov import FOV
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from entities.player import Player
from entities.monster import Monster
from entities.tavern_npcs import create_tavern_npcs
from config import SCREEN_WIDTH, SCREEN_HEIGHT, TILE_SIZE, UI_PANEL_WIDTH, GAME_AREA_WIDTH
from core.message_log import MessageBox

class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"

class Camera:
    def __init__(self, screen_width, screen_height, tile_size):
        self.tile_size = tile_size
        self.viewport_width = GAME_AREA_WIDTH // tile_size
        self.viewport_height = screen_height // tile_size - 2
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
        self.tile_size = TILE_SIZE
        self.font = pygame.font.SysFont('consolas', self.tile_size)
        self.camera = Camera(GAME_AREA_WIDTH, SCREEN_HEIGHT, self.tile_size)
        self.game_state = GameState.TAVERN
        self.current_level = 1
        self.max_level_reached = 1
        
        self.message_log = MessageBox(
            GAME_AREA_WIDTH + 10,
            SCREEN_HEIGHT - 160,
            UI_PANEL_WIDTH - 20,
            150,
            font_size=16
        )

        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 100))
        self.generate_tavern()

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
        self.update_fov()
        
        self.message_log.add_message("=== WELCOME TO THE PRANCING PONY TAVERN ===", (255, 215, 0))
        self.message_log.add_message("Walk to the door (+) and press any movement key to enter the dungeon!", (150, 150, 255))

    def generate_level(self, level_number, spawn_on_stairs_up=False):
        self.game_state = GameState.DUNGEON
        self.current_level = level_number
        self.max_level_reached = max(self.max_level_reached, level_number)
        
        self.game_map = GameMap(80, 45)
        self.fov = FOV(self.game_map)
        rooms, self.stairs_positions = generate_dungeon(self.game_map, level_number)
        
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
                    monster = Monster(x, y, 'O', f'Orc{i+1}', (76, 153, 0))
                    monster.hp = 8 + level_number
                    monster.max_hp = 8 + level_number
                    monster.attack_power = 3 + (level_number - 1)
                    monster.base_xp = 10 + (level_number * 2)
                elif level_number <= 4:
                    monster = Monster(x, y, 'T', f'Troll{i+1}', (127, 63, 63))
                    monster.hp = 12 + level_number * 2
                    monster.max_hp = 12 + level_number * 2
                    monster.attack_power = 4 + level_number
                    monster.base_xp = 20 + (level_number * 3)
                else:
                    monster = Monster(x, y, 'D', f'Dragon{i+1}', (255, 63, 63))
                    monster.hp = 20 + level_number * 3
                    monster.max_hp = 20 + level_number * 3
                    monster.attack_power = 6 + level_number
                    monster.base_xp = 50 + (level_number * 5)
                
                self.entities.append(monster)
                self.message_log.add_message(f"A {monster.name} appears!", (255, 150, 0))
        
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
            self.fov.visible.clear()
            self.fov.explored.clear()
            for y in range(self.game_map.height):
                for x in range(self.game_map.width):
                    self.fov.visible.add((x, y))
                    self.fov.explored.add((x, y))
        else:
            self.fov.compute_fov(self.player.x, self.player.y, radius=8)

    def get_current_entity(self):
        if not self.turn_order or self.game_state == GameState.TAVERN:
            return self.player
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
            
        if not self.turn_order:
            return

        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        current = self.get_current_entity()

        if current == self.player:
            self.update_fov()
            if random.random() < 0.25:
                ambient_msgs = [
                    "The dungeon emits an eerie glow...",
                    "Something shuffles in the darkness..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (180, 180, 180))

        self.cleanup_entities()

    def cleanup_entities(self):
        alive_entities = [e for e in self.entities if e.alive]
        if len(alive_entities) != len(self.entities):
            self.entities = alive_entities
            self.turn_order = [e for e in self.turn_order if e.alive]
            if self.current_turn_index >= len(self.turn_order):
                self.current_turn_index = 0

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            if event.type == pygame.KEYDOWN:
                if self.get_current_entity() == self.player:
                    dx, dy = 0, 0

                    if event.key in (pygame.K_UP, pygame.K_k):
                        dy = -1
                    elif event.key in (pygame.K_DOWN, pygame.K_j):
                        dy = 1
                    elif event.key in (pygame.K_LEFT, pygame.K_h):
                        dx = -1
                    elif event.key in (pygame.K_RIGHT, pygame.K_l):
                        dx = 1
                    elif event.key == pygame.K_SPACE:
                        if self.game_state == GameState.TAVERN:
                            npc = self.check_npc_interaction()
                            if npc:
                                self.message_log.add_message(f"{npc.name}: {npc.get_dialogue()}", (200, 200, 255))
                        else:
                            target = self.get_adjacent_target()
                            if target:
                                self.handle_player_attack(target)
                                self.next_turn()
                    
                    if dx != 0 or dy != 0:
                        self.handle_player_action(dx, dy)
                        
        return True

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

        if self.game_state == GameState.TAVERN and (new_x, new_y) == self.door_position:
            self.message_log.add_message("You enter the dark dungeon...", (100, 255, 100))
            self.generate_level(1)
            return True

        target = self.get_target_at(new_x, new_y)
        if target:
            self.handle_player_attack(target)
            self.next_turn()
            return True
        elif self.game_map.is_walkable(new_x, new_y):
            self.player.x = new_x
            self.player.y = new_y
            self.update_fov()
            
            stairs_dir = self.check_stairs_interaction()
            if stairs_dir:
                self.handle_level_transition(stairs_dir)
            else:
                self.next_turn()
            return True
        
        return False

    def handle_player_attack(self, target):
        """Handle player attacking an enemy with full combat feedback"""
        if target.alive:
            # Calculate hit chance (d20 + attack bonus vs defense)
            attack_roll = random.randint(1, 20) + self.player.attack_bonus
            if attack_roll >= target.defense:
                damage = max(1, random.randint(1, 6) + self.player.attack_power)
                damage_dealt = target.take_damage(damage)
                
                self.message_log.add_message(
                    f"You hit the {target.name} for {damage_dealt} damage!",
                    (255, 100, 100)  # Red for damage
                )
                
                if not target.alive:
                    xp_gained = target.die()
                    self.player.gain_xp(xp_gained)
                    self.message_log.add_message(
                        f"The {target.name} dies! [+{xp_gained} XP]",
                        (100, 255, 100)  # Green for kill
                    )
                    # 70% chance for flavor text
                    if random.random() < 0.7:
                        self.add_ambient_combat_message()
                else:
                    self.message_log.add_message(
                        f"{target.name} has {target.hp}/{target.max_hp} HP",
                        (255, 255, 0)  # Yellow for HP display
                    )
            else:
                self.message_log.add_message(
                    f"Your attack misses the {target.name}!",
                    (200, 200, 200)  # Gray for miss
                )

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
        # Update camera to follow player first
        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)
        
        # In tavern, no automatic turns
        if self.game_state == GameState.TAVERN:
            return
            
        current = self.get_current_entity()
        if current and current != self.player and current.alive:
            # Monster's turn - they can now attack back!
            current.take_turn(self.player, self.game_map, self)
            self.next_turn()

    def render(self):
        """Main render method - draws everything"""
        # Clear screen
        self.screen.fill((0, 0, 0))
        
        # Draw game world
        self.render_map_with_fov()
        self.render_entities()
        
        # Draw UI elements
        self.draw_ui()
        self.message_log.render(self.screen)
        
        # Update display
        pygame.display.flip()

    def render_map_with_fov(self):
        for y in range(self.camera.y, min(self.camera.y + self.camera.viewport_height, self.game_map.height)):
            for x in range(self.camera.x, min(self.camera.x + self.camera.viewport_width, self.game_map.width)):
                screen_x, screen_y = self.camera.world_to_screen(x, y)
                draw_x = screen_x * self.tile_size
                draw_y = screen_y * self.tile_size

                if self.game_state == GameState.TAVERN:
                    tile = self.game_map.tiles[y][x]
                    char_surface = self.font.render(tile.char, True, tile.color)
                    self.screen.blit(char_surface, (draw_x, draw_y))
                else:
                    if self.fov.is_visible(x, y):
                        tile = self.game_map.tiles[y][x]
                        char_surface = self.font.render(tile.char, True, tile.color)
                        self.screen.blit(char_surface, (draw_x, draw_y))
                    elif self.fov.is_explored(x, y):
                        tile = self.game_map.tiles[y][x]
                        char_surface = self.font.render(tile.char, True, tile.dark_color)
                        self.screen.blit(char_surface, (draw_x, draw_y))

    def render_entities(self):
        for entity in self.entities:
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y):
                screen_x, screen_y = self.camera.world_to_screen(entity.x, entity.y)
                draw_x = screen_x * self.tile_size
                draw_y = screen_y * self.tile_size

                if self.game_state == GameState.TAVERN:
                    entity_surface = self.font.render(entity.char, True, entity.color)
                    self.screen.blit(entity_surface, (draw_x, draw_y))
                else:
                    if self.fov.is_visible(entity.x, entity.y):
                        entity_surface = self.font.render(entity.char, True, entity.color)
                        self.screen.blit(entity_surface, (draw_x, draw_y))

    def _draw_text(self, font, text, color, x, y):
        text_surface = font.render(text, True, color)
        self.screen.blit(text_surface, (x, y))

    def draw_ui(self):
        ui_panel_rect = pygame.Rect(GAME_AREA_WIDTH, 0, UI_PANEL_WIDTH, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, (20, 20, 20), ui_panel_rect)
        pygame.draw.line(self.screen, (50, 50, 50), (GAME_AREA_WIDTH, 0), (GAME_AREA_WIDTH, SCREEN_HEIGHT), 1)
        
        panel_offset_x = GAME_AREA_WIDTH + 10
        current_y = 10
        font_large = pygame.font.SysFont('consolas', 20)
        font_medium = pygame.font.SysFont('consolas', 18)
        font_small = pygame.font.SysFont('consolas', 16)
        
        # Player Info
        self._draw_text(font_large, "PLAYER", (124, 252, 0), panel_offset_x, current_y)
        current_y += 30
        self._draw_text(font_medium, f"Name: {self.player.name}", (255, 255, 255), panel_offset_x, current_y)
        current_y += 25
        self._draw_text(font_medium, f"Level: {self.player.level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += 25
        self._draw_text(font_medium, f"XP: {self.player.current_xp}/{self.player.xp_to_next_level}", (255, 255, 255), panel_offset_x, current_y)
        current_y += 35
        
        # Vitals
        self._draw_text(font_large, "VITALS", (124, 252, 0), panel_offset_x, current_y)
        current_y += 30
        hp_color = (255, 0, 0) if self.player.hp < self.player.max_hp // 3 else (255, 255, 0) if self.player.hp < self.player.max_hp * 2 // 3 else (0, 255, 0)
        self._draw_text(font_medium, f"HP: {self.player.hp}/{self.player.max_hp}", hp_color, panel_offset_x, current_y)
        current_y += 25
        
        # Health Bar
        bar_width = UI_PANEL_WIDTH - 40
        bar_height = 15
        hp_bar_rect = pygame.Rect(panel_offset_x, current_y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (50, 0, 0), hp_bar_rect)
        fill_width = int(bar_width * (self.player.hp / self.player.max_hp))
        pygame.draw.rect(self.screen, hp_color, (panel_offset_x, current_y, fill_width, bar_height))
        current_y += bar_height + 10

        # Location Info
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

        # Controls
        self._draw_text(font_large, "CONTROLS", (124, 252, 0), panel_offset_x, current_y)
        current_y += 30

        if self.game_state == GameState.TAVERN:
            if self.check_tavern_door_interaction():
                self._draw_text(font_small, "Move onto door (+) to enter dungeon", (255, 255, 0), panel_offset_x, current_y)
                current_y += 20
            npc = self.check_npc_interaction()
            if npc:
                self._draw_text(font_small, f"SPACE: Talk to {npc.name}", (0, 255, 255), panel_offset_x, current_y)
                current_y += 20
            controls = [
                "Arrow keys/hjkl: Move",
                "SPACE: Talk to NPCs",
                "+ = Door to dungeon"
            ]
        else:
            stairs_dir = self.check_stairs_interaction()
            if stairs_dir:
                if stairs_dir == 'down':
                    self._draw_text(font_small, "Move onto > to descend", (255, 255, 0), panel_offset_x, current_y)
                else:
                    self._draw_text(font_small, "Move onto < to ascend", (255, 255, 0), panel_offset_x, current_y)
                current_y += 20
            controls = [
                "Arrow keys/hjkl: Move",
                "SPACE: Attack adjacent",
                "> = Stairs down",
                "< = Stairs up"
            ]
        
        for control in controls:
            self._draw_text(font_small, control, (150, 150, 150), panel_offset_x, current_y)
            current_y += 20
