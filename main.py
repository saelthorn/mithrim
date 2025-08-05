# MultipleFiles/main.py
import pygame
import config # Import config to get initial screen dimensions
from core.game import Game # Ensure Game class is imported

def main():
    pygame.init()
    
    # Set the display mode to the initial base resolution and make it RESIZABLE.
    # This will create a windowed screen that can be resized.
    # Do NOT include pygame.FULLSCREEN here.
    screen = pygame.display.set_mode((config.BASE_SCREEN_WIDTH, config.BASE_SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("D&D Roguelike")
    clock = pygame.time.Clock()

    game = Game(screen)

    running = True
    while running:
        dt = clock.tick(config.FPS) / 1000  # Delta time in seconds
        running = game.handle_events()
        game.update(dt)
        game.render()

    pygame.quit()

if __name__ == "__main__":
    main()
