import pygame
import config # Import config for TILE_SIZE and font scaling

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

        # Determine font size dynamically based on TILE_SIZE if not specified
        if font_size is None:
            self.font_size = int(config.TILE_SIZE * 0.5) # Example: half the tile size
            if self.font_size < 10: # Ensure a minimum readable size
                self.font_size = 10
        else:
            self.font_size = font_size
            
        self.font = pygame.font.SysFont('consolas', self.font_size, bold=True)
        self.surface = self.font.render(self.text, True, self.color)
        self.rect = self.surface.get_rect()


    def update(self):
        """Updates the text's position and remaining duration."""
        # The y_speed is applied to the *world* y coordinate, which is then converted by the camera.
        # This makes the text float up relative to its starting point.
        self.y += self.y_speed / config.FPS # Divide by FPS to make speed frame-rate independent
        self.frames_left -= 1

        if self.frames_left <= 0:
            print(f"DEBUG: FloatingText '{self.text}' at ({self.x:.2f},{self.y:.2f}) expired.") # <--- ADD THIS

        return self.frames_left > 0


    def draw(self, screen_surface, camera):
        """
        Draws the floating text on the screen.
        Converts world coordinates to screen coordinates using the camera.
        """
        screen_x_tile, screen_y_tile = camera.world_to_screen(self.x, self.y)
        

        screen_x_pixel = screen_x_tile * config.TILE_SIZE
        screen_y_pixel = screen_y_tile * config.TILE_SIZE
        
        draw_x = screen_x_pixel + (config.TILE_SIZE - self.rect.width) // 2

        draw_y = screen_y_pixel - self.rect.height
        # print(f"DEBUG: Drawing FloatingText '{self.text}' at world ({self.x:.2f},{self.y:.2f}) -> screen_pixel ({draw_x},{draw_y})")
        screen_surface.blit(self.surface, (draw_x, draw_y))

