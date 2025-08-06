import pygame
from entities.player import Player
from config import TILE_SIZE
import graphics

# Lazy-loaded font and glyph cache
_font = None
_glyph_cache = {}

def get_font():
    global _font
    if _font is None:
        _font = pygame.font.SysFont('consolas', TILE_SIZE)
    return _font

def get_glyph(char, color):
    key = (char, color)
    if key not in _glyph_cache:
        font = get_font()
        _glyph_cache[key] = font.render(char, True, color)
    return _glyph_cache[key]

def draw_ascii_tile(screen, x, y, char, color):
    glyph = get_glyph(char, color)
    screen.blit(glyph, (x * TILE_SIZE, y * TILE_SIZE))

def draw_ui(screen, player):
    font = pygame.font.SysFont('consolas', 20)
    hp_text = font.render(f"HP: {player.hp}/{player.max_hp}", True, (255, 0, 0))
    screen.blit(hp_text, (10, 10))

def draw_game(screen, player, game_map):
    # Ensure tileset is loaded and mapping is set up
    if graphics.TILESET_IMAGE is None:
        graphics.load_tileset('assets/tile_set.png')
        graphics.setup_tile_mapping()
    
    for y in range(game_map.height):
        for x in range(game_map.width):
            tile = game_map.tiles[y][x]
            # Use tile graphics for ALL tiles that have mappings
            graphics.draw_tile(screen, x, y, tile.char)

    # Draw entities using ASCII for now (can be changed to tile graphics later)
    for entity in game_map.entities:
        draw_ascii_tile(screen, entity.x, entity.y, entity.char, entity.color)
