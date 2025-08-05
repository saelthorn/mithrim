class Tile:
    def __init__(self, blocked=True, char="#", color=(255, 255, 255), block_sight=None):
        self.blocked = blocked
        self.block_sight = block_sight if block_sight is not None else blocked
        self.char = char
        self.color = color
        # Make dark_color significantly darker
        # Option 1: Divide by a larger number (e.g., 8 or 10)
        self.dark_color = tuple(c // 5 for c in color) # Or c // 10 for even darker
        # Option 2: Set a fixed dark color for all explored tiles (simpler, but less nuanced)
        # self.dark_color = (30, 30, 30) # A very dark gray
        # Option 3: Mix with black (more sophisticated dimming)
        # dark_factor = 0.2 # 20% of original color, 80% black
        # self.dark_color = tuple(int(c * dark_factor) for c in color)

# Dungeon tile templates
floor = Tile(blocked=False, char='.', color=(200, 180, 50))
wall  = Tile(blocked=True, char='#', color=(130, 110, 50)) # block_sight will default to True here, which is correct
stairs_down = Tile(blocked=False, char='>', color=(255, 255, 255))
stairs_up = Tile(blocked=False, char='<', color=(255, 255, 255))
dungeon_door = Tile(blocked=False, char='D', color=(139, 69, 19))

# Dungeon Decorations (add torch here)
rubble = Tile(blocked=False, char='%', color=(100, 100, 100))
bones = Tile(blocked=False, char='&', color=(200, 200, 180))
# IMPORTANT: Torch should be blocked=True, block_sight=False
torch = Tile(blocked=True, char='!', color=(255, 165, 0), block_sight=False)
altar = Tile(blocked=True, char='^', color=(150, 0, 150))
statue = Tile(blocked=True, char='S', color=(120, 120, 120))
crate = Tile(blocked=True, char='B', color=(139, 69, 19), block_sight=False)
barrel = Tile(blocked=True, char='O', color=(100, 50, 0), block_sight=False)
well = Tile(blocked=True, char='W', color=(0, 150, 255), block_sight=False)

# Tavern tile templates (defined here for easy import)
tavern_floor = Tile(blocked=False, char='.', color=(139, 69, 19))
tavern_wall = Tile(blocked=True, char='#', color=(101, 67, 33))
bar_counter = Tile(blocked=True, char='=', color=(160, 82, 45))
table = Tile(blocked=True, char='T', color=(139, 69, 19))
chair = Tile(blocked=False, char='c', color=(160, 82, 45))
door = Tile(blocked=False, char='+', color=(205, 133, 63))
fireplace = Tile(blocked=True, char='F', color=(255, 69, 0))