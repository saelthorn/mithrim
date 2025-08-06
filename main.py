# MultipleFiles/main.py
import pygame
import config
from core.game import Game
import graphics # Import your new graphics module

def main():
    pygame.init()
    
    # 1. Set the display mode FIRST. This initializes the video system.
    screen = pygame.display.set_mode((config.BASE_SCREEN_WIDTH, config.BASE_SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Varethis") # Changed title as per README
    
    # 2. THEN load the tileset and set up mapping.
    #    Now that a video mode is set, convert_alpha() will work.
    graphics.load_tileset('assets/tile_set.png') 
    graphics.setup_tile_mapping() 

    clock = pygame.time.Clock()

    game = Game(screen) # Pass the initialized screen to your Game class

    running = True
    while running:
        dt = clock.tick(config.FPS) / 1000
        running = game.handle_events()
        game.update(dt)
        game.render()

    pygame.quit()

if __name__ == "__main__":
    main()
