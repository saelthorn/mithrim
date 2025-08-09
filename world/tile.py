class Tile:
    def __init__(self, blocked=True, char="#", color=(255, 255, 255), block_sight=None, destructible=False, name="Tile"): # <--- ADD name="Tile"
        self.blocked = blocked
        self.block_sight = block_sight if block_sight is not None else blocked
        self.char = char
        self.color = color
        self.dark_color = tuple(c // 5 for c in color)
        self.destructible = destructible
        self.name = name # <--- ADD THIS LINE

# Dungeon tile templates
floor = Tile(blocked=False, char='.', color=(200, 180, 50), name="Floor") # <--- ADD name
wall  = Tile(blocked=True, char='#', color=(130, 110, 50), name="Wall") # <--- ADD name
stairs_down = Tile(blocked=False, char='>', color=(255, 255, 255), name="Stairs Down") # <--- ADD name
stairs_up = Tile(blocked=False, char='<', color=(255, 255, 255), name="Stairs Up") # <--- ADD name
dungeon_door = Tile(blocked=False, char='`', color=(139, 69, 19), name="Dungeon Door") # <--- ADD name

# Dungeon Decorations
bones = Tile(blocked=False, char=';', color=(200, 200, 180), name="Bones") # <--- ADD name
torch = Tile(blocked=True, char='i', color=(255, 165, 0), block_sight=False, name="Torch") # <--- ADD name
altar = Tile(blocked=True, char='^', color=(150, 0, 150), name="Altar") # <--- ADD name
statue = Tile(blocked=True, char='S', color=(120, 120, 120), name="Statue") # <--- ADD name
crate = Tile(blocked=True, char='b', color=(139, 69, 19), block_sight=False, destructible=True, name="Crate") # <--- ADD name
barrel = Tile(blocked=True, char='o', color=(100, 50, 0), block_sight=False, destructible=True, name="Barrel") # <--- ADD name

# Tavern tile templates (add names for consistency, though not strictly needed for this bug fix)
tavern_floor = Tile(blocked=False, char='.', color=(139, 69, 19), name="Tavern Floor")
tavern_wall = Tile(blocked=True, char='#', color=(101, 67, 33), name="Tavern Wall")
bar_counter = Tile(blocked=True, char='=', color=(160, 82, 45), name="Bar Counter")
table = Tile(blocked=True, char='t', color=(139, 69, 19), name="Table")
chair = Tile(blocked=False, char='c', color=(160, 82, 45), name="Chair")
door = Tile(blocked=False, char='+', color=(205, 133, 63), name="Door")
fireplace = Tile(blocked=True, char='F', color=(255, 69, 0), name="Fireplace")
