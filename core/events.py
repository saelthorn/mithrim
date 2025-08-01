import pygame

# The handle_input function is no longer needed as input is handled directly in Game.handle_events
# def handle_input(event, player, game_map, game):
#     """Handle player input"""
#     if event.type == pygame.KEYDOWN:
#         if game.get_current_entity() != player:
#             return False  # Not player's turn

#         dx, dy = 0, 0

#         # Movement keys
#         if event.key == pygame.K_UP or event.key == pygame.K_k:
#             dy = -1
#         elif event.key == pygame.K_DOWN or event.key == pygame.K_j:
#             dy = 1
#         elif event.key == pygame.K_LEFT or event.key == pygame.K_h:
#             dx = -1
#         elif event.key == pygame.K_RIGHT or event.key == pygame.K_l:
#             dx = 1
#         elif event.key == pygame.K_y:  # Diagonal up-left
#             dx, dy = -1, -1
#         elif event.key == pygame.K_u:  # Diagonal up-right
#             dx, dy = 1, -1
#         elif event.key == pygame.K_b:  # Diagonal down-left
#             dx, dy = -1, 1
#         elif event.key == pygame.K_n:  # Diagonal down-right
#             dx, dy = 1, 1

#         if dx != 0 or dy != 0:
#             # In tavern, NPCs don't fight, so just move or be blocked
#             if hasattr(game, 'game_state') and game.game_state == "tavern":
#                 return player.move_in_tavern(dx, dy, game_map, game.npcs)
#             else:
#                 # In dungeon, use normal move or attack
#                 return player.move_or_attack(dx, dy, game_map, game.entities)

#     return False
