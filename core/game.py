import pygame
import random

from core.fov import FOV
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.tavern_generator import generate_tavern
from entities.player import Player
from entities.monster import Monster
from entities.tavern_npcs import create_tavern_npcs
from entities.dungeon_npcs import DungeonHealer
import config 
from core.message_log import MessageBox 

class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"

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
        
        self.message_log = MessageBox(
            0, 
            config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT, 
            config.GAME_AREA_WIDTH, 
            config.MESSAGE_LOG_HEIGHT, 
            font_size=int(config.TILE_SIZE * 0.8) 
        )
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 100))
        self.generate_tavern()

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
        
        # Monster generation
        monsters_per_level = min(2 + level_number, len(rooms) - 1)
        monster_rooms = rooms[1:monsters_per_level + 1]
        
        for i, room in enumerate(monster_rooms):
            x, y = room.center()
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y)):
                
                if level_number <= 2:
                    monster = Monster(x, y, 'o', f'Orc{i+1}', (63, 127, 63))
                    monster.hp = 8 + level_number
                    monster.max_hp = 8 + level_number
                    monster.attack_power = 3 + (level_number - 1)
                    monster.armor_class = 13 # Example AC for Orc
                    monster.base_xp = 10 + (level_number * 2)
                elif level_number <= 4:
                    monster = Monster(x, y, 'T', f'Troll{i+1}', (127, 63, 63))
                    monster.hp = 12 + level_number * 2
                    monster.max_hp = 12 + level_number * 2
                    monster.attack_power = 4 + level_number
                    monster.armor_class = 15 # Example AC for Troll
                    monster.base_xp = 20 + (level_number * 3)
                else:
                    monster = Monster(x, y, 'D', f'Dragon{i+1}', (255, 63, 63))
                    monster.hp = 20 + level_number * 3
                    monster.max_hp = 20 + level_number * 3
                    monster.attack_power = 6 + level_number
                    monster.armor_class = 17 # Example AC for Dragon
                    monster.base_xp = 50 + (level_number * 5)
                
                self.entities.append(monster)
                self.message_log.add_message(f"A {monster.name} appears!", (255, 150, 0))

        # --- Dungeon Healer Spawning Logic ---
        # Only spawn if there are enough rooms and a random chance passes
        if len(rooms) > 2 and random.random() < 0.25: # 25% chance to spawn a healer
            healer_room = random.choice(rooms[1:-1]) # Pick a room that's not the first or last
            healer_x, healer_y = healer_room.center()
            
            # Ensure the spot is walkable and not occupied by another entity
            if self.game_map.is_walkable(healer_x, healer_y) and \
               not any(e.x == healer_x and e.y == healer_y for e in self.entities):
                
                dungeon_healer = DungeonHealer(healer_x, healer_y)
                self.entities.append(dungeon_healer)
                self.message_log.add_message(f"You sense a benevolent presence nearby...", (0, 255, 255))
                self.message_log.add_message(f"A {dungeon_healer.name} is at ({healer_x}, {healer_y})", (0, 255, 255))

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
            # Clear visible tiles for the new FOV calculation
            self.fov.visible.clear() # <--- ADD THIS LINE HERE
            # Compute FOV from player
            self.fov.compute_fov(self.player.x, self.player.y, radius=8)
            
            # Additionally, compute FOV from each torch
            if hasattr(self, 'torch_light_sources'): # Ensure torch_light_sources exists
                for tx, ty in self.torch_light_sources:
                    self.fov.compute_fov(tx, ty, radius=3) # Torches have a smaller light radius

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

    def check_dungeon_npc_interaction(self):
        """Check if player is adjacent to a Dungeon NPC and return it."""
        if self.game_state == GameState.DUNGEON:
            for entity in self.entities:
                if isinstance(entity, DungeonHealer): # Check if it's a DungeonHealer
                    if (abs(self.player.x - entity.x) <= 1 and
                        abs(self.player.y - entity.y) <= 1 and
                        (abs(self.player.x - entity.x) + abs(self.player.y - entity.y)) == 1):
                        return entity
        return None

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
                            npc = self.check_npc_interaction() # This is for Tavern NPCs
                            if npc:
                                self.message_log.add_message(f"{npc.name}: {npc.get_dialogue()}", (200, 200, 255))
                        else: # In Dungeon State
                            dungeon_npc = self.check_dungeon_npc_interaction() # <--- NEW CHECK
                            if dungeon_npc:
                                if isinstance(dungeon_npc, DungeonHealer):
                                    dungeon_npc.offer_rest(self.player, self) # Call healer's specific method
                                else:
                                    self.message_log.add_message(f"{dungeon_npc.name}: {dungeon_npc.get_dialogue()}", (200, 200, 255))
                            else: # No dungeon NPC, check for attack
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

        # --- NEW: Check if player is alive before processing turns ---
        if not self.player.alive:
            # Player is dead, stop turn processing.
            if not hasattr(self, '_game_over_displayed'): # Prevent spamming message
                death_messages = [
                    "Your journey ends here, adventurer. The dungeon claims another soul.",
                    "The light fades from your eyes. Darkness embraces you.",
                    "You fought bravely, but the dungeon proved too strong. Rest now.",
                    "Your spirit departs this mortal coil. Game Over.",
                    "The dungeon's embrace is cold and final. You have fallen."
                ]
                # Choose a random death message
                chosen_death_message = random.choice(death_messages)
                self.message_log.add_message(chosen_death_message, (255, 0, 0))
                self._game_over_displayed = True
            return # <--- IMPORTANT: Exit the update method
        if self.game_state == GameState.TAVERN:
            return

        current = self.get_current_entity()
        if current and current != self.player and current.alive:
            # Monster's turn - they can now attack back!
            current.take_turn(self.player, self.game_map, self) # Pass 'self' (game object) to monster's turn
            self.next_turn()
            # Example: Monster might try to poison player (requires CON save)
            if isinstance(current, Monster) and random.random() < 0.1: # 10% chance for a special ability
                if current.is_adjacent_to(self.player):
                    self.message_log.add_message(f"The {current.name} attempts to poison you!", (255, 150, 0))
                    poison_dc = 10 + current.attack_power # Example DC
                    if not self.player.make_saving_throw("CON", poison_dc, self):
                        self.message_log.add_message("You are poisoned! Take 2 damage.", (255, 0, 0))
                        self.player.take_damage(2) # Apply damage for failed save


    def render(self):
        """Main render method - draws everything"""
        self.screen.fill((0, 0, 0))
        
        self.render_map_with_fov()
        self.render_entities()
        
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
        map_render_height = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
        for entity in self.entities:
            # Always render the player if they are alive and in viewport
            if entity == self.player:
                if entity.alive and self.camera.is_in_viewport(entity.x, entity.y):
                    screen_x, screen_y = self.camera.world_to_screen(entity.x, entity.y)
                    draw_x = screen_x * config.TILE_SIZE
                    draw_y = screen_y * config.TILE_SIZE
                    if draw_y < map_render_height:
                        entity_surface = self.font.render(entity.char, True, entity.color)
                        self.screen.blit(entity_surface, (draw_x, draw_y))
                continue # Skip to next entity after rendering player
            # For other entities (monsters, NPCs), apply FOV rules
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y):
                screen_x, screen_y = self.camera.world_to_screen(entity.x, entity.y)
                
                draw_x = screen_x * config.TILE_SIZE
                draw_y = screen_y * config.TILE_SIZE
                if draw_y < map_render_height:
                    if self.game_state == GameState.TAVERN:
                        # In tavern, all NPCs are visible
                        entity_surface = self.font.render(entity.char, True, entity.color)
                        self.screen.blit(entity_surface, (draw_x, draw_y))
                    else:
                        # In dungeon, only render if visible by FOV
                        if self.fov.is_visible(entity.x, entity.y):
                            entity_surface = self.font.render(entity.char, True, entity.color)
                            self.screen.blit(entity_surface, (draw_x, draw_y))

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
        else:
            stairs_dir = self.check_stairs_interaction()
            if stairs_dir:
                controls_list.append(f"Move onto {'<' if stairs_dir == 'up' else '>'} to {'ascend' if stairs_dir == 'up' else 'descend'}")
            controls_list.extend([
                "Arrow keys/hjkl: Move",
                "SPACE: Attack adjacent",
                "> = Stairs down",
                "< = Stairs up"
            ])
        
        for control in controls_list:
            if current_y + font_small.get_linesize() < max_controls_y:
                self._draw_text(font_small, control, (150, 150, 150), panel_offset_x, current_y)
                current_y += font_small.get_linesize() + 5
            else:
                break
