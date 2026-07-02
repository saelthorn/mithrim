import random


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
floor = Tile(blocked=False, char='.', color=(97, 95, 88), name="Floor")
wall  = Tile(blocked=True, char='#', color=(65, 61, 46), name="Wall")
stairs_down = Tile(blocked=False, char='>', color=(230, 192, 0), name="Stairs Down")
stairs_up = Tile(blocked=False, char='<', color=(230, 192, 0), name="Stairs Up")
dungeon_door = Tile(blocked=False, char='dd', color=(139, 69, 19), name="Dungeon Door")
dungeon_pillar = Tile(blocked=True, char='dp', color=(230, 230, 230), block_sight=True, name="Dungeon Pillar")
altar = Tile(blocked=True, char='alt', color=(255, 215, 0), block_sight=True, name="Altar")  

pressure_plate = Tile(blocked=False, char='_', color=(200, 180, 50), name="Pressure Plate")

# Dungeon Decorations
dungeon_floor_two = Tile(blocked=False, char='.2', color=(97, 95, 88), name="Dungeon Floor Two")
dungeon_floor_three = Tile(blocked=False, char='.3', color=(97, 95, 88), name="Dungeon Floor Three")
dungeon_floor_four = Tile(blocked=False, char='.4', color=(97, 95, 88), name="Dungeon Floor Four")
dungeon_floor_five = Tile(blocked=False, char='.5', color=(97, 95, 88), name="Dungeon Floor Five")
dungeon_floor_six = Tile(blocked=False, char='.6', color=(97, 95, 88), name="Dungeon Floor Six")
dungeon_grass = Tile(blocked=False, char='`', color=(0, 160, 20), name="Dungeon Grass")
dungeon_grass_two = Tile(blocked=False, char='`2', color=(0, 160, 20), name="Dungeon Grass Two")
rubble = Tile(blocked=False, char='%', color=(150, 150, 150), name="Rubble")
cob_web = Tile(blocked=True, char='x', color=(200, 200, 200), block_sight=False, destructible=True, name="Cobweb")   
mushroom = Tile(blocked=False, char='*', color=(255, 0, 255), name="Mushroom")
fresh_bones = Tile(blocked=False, char='fb', color=(200, 200, 180), name="Fresh Bones")
bones = Tile(blocked=False, char=';', color=(200, 200, 180), name="Bones")
torch = Tile(blocked=True, char='i', color=(153, 76, 0), block_sight=True, name="Torch")

prison_bars = Tile(blocked=True, char='pb', color=(160, 160, 180), block_sight=False, destructible=False, name="Prison Bars",)

# Static Crate and Barrel (using distinct chars)
crate = Tile(blocked=True, char='k', color=(74, 57, 0), block_sight=False, destructible=True, name="Crate")
barrel = Tile(blocked=True, char='b', color=(74, 57, 0), block_sight=False, destructible=True, name="Barrel")

# Tavern tile templates
tavern_floor = Tile(blocked=False, char=',', color=(139, 69, 19), name="Tavern Floor")
tavern_kitchen_floor = Tile(blocked=False, char='?', color=(139, 69, 19), name="Tavern Kitchen Floor")
tavern_wall = Tile(blocked=True, char='#', color=(101, 67, 33), name="Tavern Wall")
bar_counter = Tile(blocked=True, char='=', color=(160, 82, 45), block_sight=False, name="Bar Counter")
table = Tile(blocked=True, char='t', color=(139, 69, 19), name="Table")
chair = Tile(blocked=False, char='c', color=(160, 82, 45), block_sight=False, name="Chair")
door = Tile(blocked=False, char='+', color=(205, 133, 63), name="Door")
fireplace = Tile(blocked=True, char='F', color=(255, 69, 0), name="Fireplace")
tavern_crate = Tile(blocked=False, char='{', color=(139, 69, 19), name="Tavern Crate")
tavern_barrel = Tile(blocked=False, char='}', color=(139, 69, 19), name="Tavern Barrel")

# Overworld tile templates (used by world_generator.py)
grass = Tile(blocked=False, char='`', color=(60, 140, 40), name="Grass")
tall_grass = Tile(blocked=False, char='`2', color=(40, 110, 30), block_sight=True, name="Tall Grass")
tree = Tile(blocked=True, char='*', color=(25, 80, 35), block_sight=True, destructible=False, name="Tree")
dungeon_entrance = Tile(blocked=False, char='>', color=(230, 192, 0), name="Dungeon Entrance")

from world.water_features import river, lake


class MimicTile(Tile):
    def __init__(self, mimic_entity, char, color, name):
        super().__init__(blocked=True, char=char, color=color, block_sight=False, destructible=True, name=name)
        self.mimic_entity = mimic_entity


class TrapTile(Tile):
    def __init__(self, trap_instance, hidden_char, hidden_color, x, y, name="Hidden Trap"):
        super().__init__(blocked=False, char=hidden_char, color=hidden_color, block_sight=False, destructible=False, name=name)
        self.trap_instance = trap_instance
        self.original_char = hidden_char
        self.original_color = hidden_color
        self.x = x
        self.y = y
        self.highlighted = False

    def get_display_char(self):
        """Returns the character to display based on trap state."""
        if self.trap_instance.is_hidden:
            return self.original_char
        elif self.trap_instance.is_triggered:
            return self.trap_instance.char
        else:
            return self.trap_instance.char

    def get_display_color(self):
        """Returns the color to display based on trap state."""
        if self.highlighted:
            return (255, 255, 0)
        if self.trap_instance.is_hidden:
            return self.original_color
        elif self.trap_instance.is_disarmed:
            return (0, 200, 0)
        elif self.trap_instance.is_triggered:
            return (255, 0, 0)
        else:
            return self.trap_instance.color


class TombTile(Tile):
    """Ancient tomb that can be disturbed to spawn skeletons or drop loot."""
    def __init__(self):
        super().__init__(
            blocked=True,
            char='tm',
            color=(150, 130, 120),
            block_sight=False,
            destructible=False,
            name="Tomb",
        )
        self.is_disturbed = False
        self.is_not_disturbed = True


class DisturbedTombTile(Tile):
    """A tomb that has already been opened — uses the 'otm' (Open Tomb) sprite."""
    def __init__(self):
        super().__init__(
            blocked=False,
            char='otm',
            color=(110, 95, 85),
            block_sight=False,
            destructible=False,
            name="Disturbed Tomb",
        )
        self.is_disturbed = True


class PrisonDoorTile(Tile):
    """Locked prison door. Can be opened via a skill check."""
    def __init__(self):
        super().__init__(
            blocked=True,
            char='pd',
            color=(180, 140, 80),
            block_sight=False,
            destructible=False,
            name="Prison Door",
        )
        self.is_open   = False
        self.is_locked = True


class FireElementalTile:
    """
    A temporary hazard tile placed by Fireball (and future fire sources).

    The tile wraps the surface it lands on (`underlying_tile`) and restores
    it automatically when it expires.  Each turn the game calls tick(); any
    entity standing on a fire tile when that happens takes 1d6 fire damage.
    """

    def __init__(self, underlying_tile, duration=None):
        self.underlying_tile = underlying_tile
        self.turns_remaining  = duration if duration is not None else random.randint(3, 7)

        # Standard tile interface --------------------------------------------------
        self.char         = 'fire'  # Add a 'fire' entry to TILE_MAPPING in graphics.py
        self.name         = "Fire"
        self.blocked      = False   # Walkable but dangerous
        self.block_sight  = False
        self.destructible = False
        self.color        = (255, 100, 0, 0)
        self.dark_color   = (255, 50, 0, 0)

    def tick(self):
        """
        Decrement remaining duration.
        Returns True when the fire has fully burned out (caller restores underlying tile).
        """
        self.turns_remaining -= 1
        return self.turns_remaining <= 0