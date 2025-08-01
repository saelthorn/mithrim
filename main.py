# MultipleFiles/main.py
import pygame
from config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS
from core.game import Game

def main():
    pygame.init()
    # Set the display mode to the full screen width and height
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("D&D Roguelike")
    clock = pygame.time.Clock()

    game = Game(screen)

    running = True
    while running:
        dt = clock.tick(FPS) / 1000  # Delta time in seconds
        running = game.handle_events()
        game.update(dt)
        game.render()

    pygame.quit()

if __name__ == "__main__":
    main()
