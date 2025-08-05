# MultipleFiles/config.py

# Base resolution for scaling (e.g., 1280x720 or 1920x1080)
# This is a reference, not a fixed screen size.
BASE_SCREEN_WIDTH = 1200
BASE_SCREEN_HEIGHT = 700

# UI panel width as a ratio of the total screen width
UI_PANEL_WIDTH_RATIO = 0.25 # UI panel takes 25% of screen width

# Message log height as a ratio of the total screen height
MESSAGE_LOG_HEIGHT_RATIO = 0.25 # Increased to 25% for a taller box

# Minimum tile size to prevent elements from becoming too small
MIN_TILE_SIZE = 12

# Initial FPS
FPS = 30

# These will be calculated dynamically in game.py
SCREEN_WIDTH = 0
SCREEN_HEIGHT = 0
TILE_SIZE = 0
UI_PANEL_WIDTH = 0
GAME_AREA_WIDTH = 0
MESSAGE_LOG_HEIGHT = 0
