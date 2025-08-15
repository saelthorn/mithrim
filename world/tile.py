# MultipleFiles/tile.py

class Tile:
    def __init__(self, blocked=True, char="#", color=(255, 255, 255), block_sight=None, destructible=False, name="Tile"):
        self.blocked = blocked
        self.block_sight = block_sight if block_sight is not None else blocked
        self.char = char
        self.color = color
        self.dark_color = tuple(c // 5 for c in color)
        self.destructible = destructible
        self.name = name

# Dungeon tile templates
floor = Tile(blocked=False, char='.', color=(200, 180, 50), name="Floor")
wall  = Tile(blocked=True, char='#', color=(130, 110, 50), name="Wall")
stairs_down = Tile(blocked=False, char='>', color=(255, 255, 255), name="Stairs Down")
stairs_up = Tile(blocked=False, char='<', color=(255, 255, 255), name="Stairs Up")
dungeon_door = Tile(blocked=False, char='dd', color=(139, 69, 19), name="Dungeon Door")

pressure_plate = Tile(blocked=False, char='_', color=(200, 180, 50), name="Pressure Plate")

# Dungeon Decorations
dungeon_grass = Tile(blocked=False, char='`', color=(0, 160, 20), name="Dungeon Grass")
rubble = Tile(blocked=False, char='%', color=(150, 150, 150), name="Rubble")
cob_web = Tile(blocked=True, char='~', color=(200, 200, 200), block_sight=False, destructible=True, name="Cobweb")   
mushroom = Tile(blocked=False, char='*', color=(255, 0, 255), name="Mushroom")
fresh_bones = Tile(blocked=False, char='fb', color=(200, 200, 180), name="Fresh Bones")
bones = Tile(blocked=False, char=';', color=(200, 200, 180), name="Bones")
torch = Tile(blocked=True, char='i', color=(255, 165, 0), block_sight=False, name="Torch")
altar = Tile(blocked=True, char='^', color=(150, 0, 150), name="Altar")
statue = Tile(blocked=True, char='S', color=(120, 120, 120), name="Statue")

# Static Crate and Barrel (using distinct chars)
crate = Tile(blocked=True, char='k', color=(139, 69, 19), block_sight=False, destructible=True, name="Crate") # <--- CHANGED char to 'k'
barrel = Tile(blocked=True, char='b', color=(100, 50, 0), block_sight=False, destructible=True, name="Barrel") # <--- char 'b' is fine

# Tavern tile templates
tavern_floor = Tile(blocked=False, char='.', color=(139, 69, 19), name="Tavern Floor")
tavern_wall = Tile(blocked=True, char='#', color=(101, 67, 33), name="Tavern Wall")
bar_counter = Tile(blocked=True, char='=', color=(160, 82, 45), name="Bar Counter")
table = Tile(blocked=True, char='t', color=(139, 69, 19), name="Table")
chair = Tile(blocked=False, char='c', color=(160, 82, 45), name="Chair")
door = Tile(blocked=False, char='+', color=(205, 133, 63), name="Door")
fireplace = Tile(blocked=True, char='F', color=(255, 69, 0), name="Fireplace")


class MimicTile(Tile):
    def __init__(self, mimic_entity, char, color, name): # 'char' here will be 'K' or 'B'
        super().__init__(blocked=True, char=char, color=color, block_sight=False, destructible=True, name=name)
        self.mimic_entity = mimic_entity # Reference to the actual Mimic monster


class TrapTile(Tile):
    def __init__(self, trap_instance, hidden_char, hidden_color, x, y, name="Hidden Trap"):
        super().__init__(blocked=False, char=hidden_char, color=hidden_color, block_sight=False, destructible=False, name=name)
        self.trap_instance = trap_instance  # Reference to the actual Trap object (e.g., DartTrap)
        self.original_char = hidden_char  # Store original char for when it's hidden
        self.original_color = hidden_color  # Store original color
        self.x = x  # Store x coordinate
        self.y = y  # Store y coordinate
        self.highlighted = False

    def get_display_char(self):
        """Returns the character to display based on trap state."""
        if self.trap_instance.is_hidden:
            return self.original_char  # Show as floor or whatever it's disguised as
        elif self.trap_instance.is_triggered:
            return self.trap_instance.char  # Show revealed graphic (e.g., '^')
        else:  # Revealed but not triggered/disarmed
            return self.trap_instance.char  # Show revealed graphic (e.g., '^')

    def get_display_color(self):
        """Returns the color to display based on trap state."""
        if self.highlighted:
            return (255, 255, 0)  # Yellow for highlighted traps
        if self.trap_instance.is_hidden:
            return self.original_color
        elif self.trap_instance.is_disarmed:
            return (0, 200, 0)  # Green for disarmed
        elif self.trap_instance.is_triggered:
            return (255, 0, 0)  # Red for triggered
        else:
            return self.trap_instance.color  # Trap's own color




