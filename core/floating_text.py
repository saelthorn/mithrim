import pygame
import config # Import config for TILE_SIZE and font scaling

# pygame.font.SysFont() asks the OS to match/load a font -- one of the
# slower calls in pygame, not a cheap lookup. FloatingText.font_size only
# ever takes a handful of distinct values (derived from config.TILE_SIZE,
# which only changes on zoom), so building a fresh SysFont for every
# single HIT!/MISS!/damage-number instance -- several of which get
# created per monster attack, for every monster, all within the same
# synchronous combat turn (see game.py's batch turn-processing loop) --
# turns a handful of monsters attacking at once into a dozen-plus
# from-scratch font loads before a single frame renders. Caching by
# (font_size, bold) means that cost is paid once per size, not once per
# floating text.
_FONT_CACHE = {}


def _get_cached_font(font_size, bold=True):
    cache_key = (font_size, bold)
    font = _FONT_CACHE.get(cache_key)
    if font is None:
        font = pygame.font.SysFont('consolas', font_size, bold=bold)
        _FONT_CACHE[cache_key] = font
    return font


class FloatingText:
    def __init__(self, x, y, text, color, duration=60, y_speed=-0.5, font_size=None):
        """
        Initializes a floating text object.

        Args:
            x (int): World X coordinate where the text appears.
            y (int): World Y coordinate where the text appears.
            text (str): The text to display (e.g., "HIT!", "12", "MISS!").
            color (tuple): RGB color of the text (e.g., (255, 255, 255)).
            duration (int): How many frames the text should remain visible.
            y_speed (float): How fast the text moves upwards (pixels per frame).
            font_size (int, optional): Specific font size. If None, uses a scaled default.
        """
        self.x = x # World X (tile coordinate)
        self.y = y # World Y (tile coordinate)
        self.text = text
        self.color = color
        self.duration = duration
        self.frames_left = duration
        self.y_speed = y_speed # Negative for upward movement
        self.expired = False

        # Determine font size dynamically based on TILE_SIZE if not specified
        if font_size is None:
            self.font_size = int(config.TILE_SIZE * 0.5) # Example: half the tile size
            if self.font_size < 10: # Ensure a minimum readable size
                self.font_size = 10
        else:
            self.font_size = font_size
            
        self.font = _get_cached_font(self.font_size, bold=True)
        self.surface = self.font.render(self.text, True, self.color)
        self.rect = self.surface.get_rect()

        self.last_draw_rect = None # Store the last rectangle it was drawn to

    def update(self):
        """Updates the text's position and remaining duration."""
        # The y_speed is applied to the *world* y coordinate, which is then converted by the camera.
        # This makes the text float up relative to its starting point.
        old_x, old_y = self.x, self.y        

        self.y += self.y_speed / config.FPS # Divide by FPS to make speed frame-rate independent
        self.frames_left -= 1
        self.duration -= 1

        if self.duration <= 0:
            self.expired = True

        if self.frames_left <= 0:
            if self.last_draw_rect:
                # This requires access to the game instance's dirty_rects list
                # A better pattern is to have the game loop iterate and collect dirty rects
                pass # Handled by Game.update's filtering and redraw

        return self.frames_left > 0


    def draw(self, screen_surface, camera):
        """
        Draws the floating text on the screen.
        Converts world coordinates to screen coordinates using the camera.
        """
        screen_x_tile, screen_y_tile = camera.world_to_screen(self.x, self.y)
        

        screen_x_pixel = screen_x_tile * config.TILE_SIZE
        screen_y_pixel = screen_y_tile * config.TILE_SIZE
        
        current_draw_rect = pygame.Rect(screen_x_pixel, screen_y_pixel, self.rect.width, self.rect.height)
        
        draw_x = screen_x_pixel + (config.TILE_SIZE - self.rect.width) // 2

        draw_y = screen_y_pixel - self.rect.height
        # print(f"DEBUG: Drawing FloatingText '{self.text}' at world ({self.x:.2f},{self.y:.2f}) -> screen_pixel ({draw_x},{draw_y})")
        screen_surface.blit(self.surface, (draw_x, draw_y))
