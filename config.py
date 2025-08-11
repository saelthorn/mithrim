# MultipleFiles/config.py

# Base resolution for scaling (e.g., 1280x720 or 1920x1080)
# This is a reference, not a fixed screen size.
BASE_SCREEN_WIDTH = 1200
BASE_SCREEN_HEIGHT = 700

# UI panel width as a ratio of the total screen width
UI_PANEL_WIDTH_RATIO = 0.20 # UI panel takes 25% of screen width

# Message log height as a ratio of the total screen height
MESSAGE_LOG_HEIGHT_RATIO = 0.25 # Increased to 25% for a taller box

# Set TILE_SIZE to match your tileset's individual tile size (e.g., 12x12)
TILE_SIZE = 53
MIN_TILE_SIZE = 53 

# Initial FPS
FPS = 30

# --- NEW: Message Log Font Scaling ---
# This factor will be multiplied by the actual_scale_factor of the game area
# to determine the message log's font size.
MESSAGE_LOG_FONT_BASE_SIZE = 5 # Base size for the font (e.g., 12px)
MESSAGE_LOG_FONT_SCALE_FACTOR = 1.5 # Multiplier for the base size, relative to game scale

# --- NEW: Internal Game Area Resolution ---
# These values will now be dynamically calculated, but we keep them here as initial
# values or as a reference for the *maximum* zoom-out level if you want to cap it.
# For dynamic sizing, these specific values (40, 36) will be overwritten.
# However, the pixel dimensions derived from them are still used for initial surface creation.
INTERNAL_GAME_AREA_WIDTH_TILES = 60 # This will be dynamically calculated
INTERNAL_GAME_AREA_HEIGHT_TILES = 36 # This will be dynamically calculated
INTERNAL_GAME_AREA_PIXEL_WIDTH = INTERNAL_GAME_AREA_WIDTH_TILES * TILE_SIZE
INTERNAL_GAME_AREA_PIXEL_HEIGHT = INTERNAL_GAME_AREA_HEIGHT_TILES * TILE_SIZE

# --- NEW: Minimum number of tiles to display (for dynamic scaling) ---
MIN_GAME_AREA_TILES_WIDTH = 33  # Ensure at least 20 tiles wide are always shown
MIN_GAME_AREA_TILES_HEIGHT = 18 # Ensure at least 18 tiles high are always shown

# --- NEW: Target effective tile scale for dynamic scaling ---
# This determines the "base" zoom level. E.g., 2 means each 12px tile will try to be 24px.
# A value of 1 means each 12px tile will try to be 12px (most zoomed out, smallest tiles).
# A value of 3 means each 12px tile will try to be 36px (more zoomed in, larger tiles).
TARGET_EFFECTIVE_TILE_SCALE = 3 # <--- ADD THIS LINE

# These will be calculated dynamically in game.py
SCREEN_WIDTH = 0
SCREEN_HEIGHT = 0
UI_PANEL_WIDTH = 0
GAME_AREA_WIDTH = 0 # This will now be the *actual* pixel width of the game area on the screen
MESSAGE_LOG_HEIGHT = 0
