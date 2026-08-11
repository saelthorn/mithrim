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
altar = Tile(blocked=True, char='&', color=(255, 215, 0), block_sight=True, name="Altar")  

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
table = Tile(blocked=True, char='t', color=(139, 69, 19), block_sight=False, name="Table")
chair = Tile(blocked=False, char='c', color=(160, 82, 45), block_sight=False, name="Chair")
door = Tile(blocked=False, char='+', color=(205, 133, 63), name="Door")
fireplace = Tile(blocked=True, char='F', color=(255, 69, 0), name="Fireplace")
tavern_crate = Tile(blocked=False, char='{', color=(139, 69, 19), name="Tavern Crate")
tavern_barrel = Tile(blocked=False, char='}', color=(139, 69, 19), name="Tavern Barrel")
tavern_barrel_two = Tile(blocked=True, char='}2', color=(139, 69, 19), block_sight="False", name="Tavern Barrel Two")

bar_counter_two = Tile(blocked=True, char='I', color=(160, 82, 45), block_sight=False, name="Bar Counter Two")
bar_counter_three = Tile(blocked=True, char='7', color=(160, 82, 45), block_sight=False, name="Bar Counter Three")
bar_counter_four = Tile(blocked=True, char='|', color=(160, 82, 45), block_sight=False, name="Bar Counter Four")

bar_counter_five = Tile(blocked=True, char='|2', color=(160, 82, 45), block_sight=False, name="Bar Counter Five")
bar_counter_six = Tile(blocked=True, char='|3', color=(160, 82, 45), block_sight=False, name="Bar Counter Six")

forge = Tile(blocked=True, char='fg', color=(128, 128, 128), block_sight=False, name="Forge")
anvil = Tile(blocked=True, char='av', color=(128, 128, 128), block_sight=False, name="Anvil")
shelf = Tile(blocked=True, char='5', color=(139, 69, 19), block_sight=False, name="Shelf")
shelf_two = Tile(blocked=True, char='52', color=(139, 69, 19), block_sight=False, name="Shelf Two")
shelf_three = Tile(blocked=True, char='53', color=(139, 69, 19), block_sight=False, name="Shelf Three")
bed = Tile(blocked=True, char='--', color=(139, 69, 19), block_sight=False, name="Bed")
hay = Tile(blocked=True, char='hy', color=(139, 69, 19), name="Hay")

# Overworld tile templates (used by world_generator.py)
road = Tile(blocked=False, char='rd', color=(128, 128, 128), name="Road")
ground = Tile(blocked=False, char='grd', color=(20, 100, 20), name="Ground")
grass = Tile(blocked=False, char='`2', color=(60, 140, 40), name="Grass")
tall_grass = Tile(blocked=False, char='`3', color=(20, 100, 20), name="Tall Grass")
tree = Tile(blocked=False, char='tre', color=(25, 80, 35), block_sight=True, destructible=False, name="Tree")
dungeon_entrance = Tile(blocked=False, char='>', color=(230, 192, 0), name="Dungeon Entrance")
mountain = Tile(blocked=True, char='mnt', color=(100, 100, 100), block_sight=True, destructible=False, name="Mountain")

# World-encounter landmark props (see game.py's WORLD_ENCOUNTER_TILE_TYPES) --
# placed directly on the overworld map near the player when a scenario
# declares a "landmark_tile" (e.g. Bandit_Ambush.json's ransacked cart).
caravan = Tile(blocked=True, char='crv', color=(139, 90, 43), block_sight=False, destructible=False, name="Caravan")
ritual_circle = Tile(blocked=True, char='rtc', color=(130, 30, 150), block_sight=False, destructible=False, name="Ritual Circle")
barricade = Tile(blocked=True, char='brc', color=(101, 67, 33), block_sight=True, destructible=True, name="Barricade")
ambush_tree = Tile(blocked=False, char='amt', color=(35, 90, 40), block_sight=True, destructible=False, name="Lone Tree")
overworld_cobweb = Tile(blocked=True, char='ocw', color=(200, 200, 200), block_sight=False, destructible=True, name="Cobweb")
tent = Tile(blocked=True, char='ten', color=(180, 40, 40), block_sight=True, destructible=True, name="Tent")
gravestone = Tile(blocked=True, char='gvs1', color=(120, 120, 120), block_sight=False, destructible=True, name="Gravestone One")
gravestone_two = Tile(blocked=True, char='gvs2', color=(120, 120, 120), block_sight=False, destructible=True, name="Gravestone Two")
gravestone_three = Tile(blocked=True, char='gvs3', color=(120, 120, 120), block_sight=False, destructible=True, name="Gravestone Three")

campfire = Tile(blocked=False, char='cf', color=(255, 140, 0), block_sight=False, destructible=False, name="Campfire")
cauldron = Tile(blocked=True, char='cau', color=(80, 80, 80), block_sight=False, destructible=False, name="Cauldron")
ladder = Tile(blocked=False, char='lad', color=(139, 69, 19), block_sight=False, destructible=False, name="Ladder")
wood_plank = Tile(blocked=False, char='tpn', color=(139, 69, 19), block_sight=False, destructible=True, name="Wood Plank")
tavern_cobweb = Tile(blocked=True, char='tcw', color=(200, 200, 200), block_sight=False, destructible=True, name="Tavern Cobweb")

dragon_skull = Tile(blocked=True, char='dsk', color=(200, 200, 200), block_sight=False, destructible=False, name="Dragon Skull")
dragon_skeleton = Tile(blocked=True, char='dskl', color=(200, 200, 200), block_sight=False, destructible=False, name="Dragon Skeleton")
dragon_tail = Tile(blocked=True, char='dtl', color=(200, 200, 200), block_sight=False, destructible=False, name="Dragon Tail")

# Overworld terrain decoration (non-POI nature features)
clearing = Tile(blocked=False, char='cl', color=(20, 100, 20), name="Clearing")
giant_tree = Tile(blocked=False, char='GT', color=(15, 50, 20), block_sight=True, name="Giant Tree")
pond = Tile(blocked=False, char='pnd', color=(80, 140, 180), name="Pond")
flower_field = Tile(blocked=False, char='ff', color=(180, 90, 170), name="Flower Field")
cliff = Tile(blocked=False, char='clf', color=(150, 140, 140), name="Cliff")
valley = Tile(blocked=False, char='vy', color=(120, 150, 100), name="Valley")
waterfall = Tile(blocked=False, char='wtf', color=(90, 140, 220), name="Waterfall")
scree = Tile(blocked=False, char='sc', color=(140, 130, 115), name="Scree")
ridge = Tile(blocked=False, char='rg', color=(140, 110, 90), name="Ridge")
meadow = Tile(blocked=False, char='md', color=(120, 180, 80), name="Meadow")
rock_formation = Tile(blocked=False, char='rk', color=(160, 160, 160), name="Rock Formation")
marsh_pool = Tile(blocked=False, char='mp', color=(80, 150, 110), name="Marsh Pool")
reeds = Tile(blocked=False, char='rds', color=(70, 140, 80), name="Reeds")
dead_forest = Tile(blocked=False, char='ddf', color=(90, 100, 70), name="Dead Forest")


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