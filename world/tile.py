class Tile:
    def __init__(self, blocked=True, char="#", color=(255, 255, 255), block_sight=None):
        self.blocked = blocked
        self.block_sight = block_sight if block_sight is not None else blocked
        self.char = char
        self.color = color
        self.dark_color = tuple(c // 3 for c in color)  # Darker version for explored but not visible

# Dungeon tile templates
floor = Tile(blocked=False, char='.', color=(200, 180, 50))   # Brighter floor
wall  = Tile(blocked=True, char='#', color=(130, 110, 50))    # Wall color
stairs_down = Tile(blocked=False, char='>', color=(255, 255, 255))  # Stairs down
stairs_up = Tile(blocked=False, char='<', color=(255, 255, 255))    # Stairs up
dungeon_door = Tile(blocked=False, char='D', color=(139, 69, 19))   # Dungeon door to next level

# Tavern tile templates (defined here for easy import)
tavern_floor = Tile(blocked=False, char='.', color=(139, 69, 19))  # Brown floor
tavern_wall = Tile(blocked=True, char='#', color=(101, 67, 33))    # Dark brown walls
bar_counter = Tile(blocked=True, char='=', color=(160, 82, 45))    # Bar counter
table = Tile(blocked=True, char='T', color=(139, 69, 19))          # Table
chair = Tile(blocked=False, char='c', color=(160, 82, 45))         # Chair
door = Tile(blocked=False, char='+', color=(205, 133, 63))         # Door  <-- ENSURE THIS IS PRESENT
fireplace = Tile(blocked=True, char='F', color=(255, 69, 0))       # Fireplace
