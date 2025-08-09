# MultipleFiles/main.py
import pygame
import config
from core.game import Game
import graphics

def main():
    pygame.init()
    
    # --- MODIFIED: Removed pygame.SCALED flag ---
    screen = pygame.display.set_mode((config.BASE_SCREEN_WIDTH, config.BASE_SCREEN_HEIGHT), pygame.RESIZABLE)
    
    pygame.display.set_caption("Varethis")
    
    graphics.load_tileset('assets/Vector.png') 
    graphics.setup_tile_mapping() 
    clock = pygame.time.Clock()
    game = Game(screen) 
    
    running = True
    while running:
        dt = clock.tick(config.FPS) / 1000
        running = game.handle_events()
        game.update(dt)
        game.render()
    pygame.quit()

if __name__ == "__main__":
    main()
