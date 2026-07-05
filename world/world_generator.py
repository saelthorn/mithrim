import math
import heapq
import random
import struct
import zlib
from core.game import ChunkBiome
from world.tile import (
    grass,
    tall_grass,
    tree,
    dungeon_entrance,
    road,
    ground,
    mountain,
    clearing,
    giant_tree,
    pond,
    flower_field,
    cliff,
    valley,
    waterfall,
    scree,
    ridge,
    meadow,
    rock_formation,
    marsh_pool,
    reeds,
    dead_forest,
)
from world.water_features import river, lake, is_water_tile
from world.structures import place_structure_at_anchor, get_structure_blueprint


DEEP_WATER = 0.12
SHALLOW_WATER = 0.18
PLAINS = 0.55
HILLS = 0.75

# How strongly a chunk's local elevation/moisture noise is pulled toward the
# coarse, world-scale value WorldMap recorded for that chunk (see
# _bias_grid_toward_world_value). Elevation is biased harder than moisture —
# mountain ranges and coastlines reading as continuous across chunks matters
# more than moisture doing the same.
WORLD_ELEVATION_BIAS_STRENGTH = 0.35
WORLD_MOISTURE_BIAS_STRENGTH = 0.20

BIOME_OCEAN = "ocean"
BIOME_BEACH = "beach"
BIOME_PLAINS = "plains"
BIOME_FOREST = "forest"
BIOME_SWAMP = "swamp"
BIOME_HILLS = "hills"
BIOME_MOUNTAINS = "mountains"

REGION_PREFIXES = [
    "Ashen",
    "Golden",
    "Frozen",
    "Whispering",
    "Emerald",
    "Broken",
    "Ancient",
    "Black",
    "Silent",
    "Storm",
    "Iron",
    "Scarlet",
]

REGION_SUFFIX = {
    BIOME_FOREST: [
        "Forest",
        "Woods",
        "Grove"
    ],

    BIOME_PLAINS: [
        "Plains",
        "Fields",
        "Lowlands"
    ],

    BIOME_HILLS: [
        "Hills",
        "Highlands"
    ],

    BIOME_MOUNTAINS: [
        "Peaks",
        "Mountains",
        "Range"
    ],

    BIOME_SWAMP: [
        "Marsh",
        "Bog",
        "Fen"
    ],

    BIOME_OCEAN: [
        "Sea"
    ]
}


BIOME_SETTINGS = {

    ChunkBiome.PLAINS: {
        "forest_chance": 0.10,
        "grass_chance": 0.08,
        "height_offset": 0.00,
    },

    ChunkBiome.FOREST: {
        "forest_chance": 0.85,
        "grass_chance": 0.05,
        "height_offset": 0.00,
    },

    ChunkBiome.SWAMP: {
        "forest_chance": 0.40,
        "grass_chance": 0.60,
        "height_offset": -0.03,
    },

    ChunkBiome.HILLS: {
        "forest_chance": 0.35,
        "grass_chance": 0.08,
        "height_offset": 0.08,
    },

    ChunkBiome.MOUNTAINS: {
        "forest_chance": 0.15,
        "grass_chance": 0.02,
        "height_offset": 0.18,
    },

    ChunkBiome.DESERT: {
        "forest_chance": 0.02,
        "grass_chance": 0.01,
        "height_offset": -0.05,
    },

    ChunkBiome.TUNDRA: {
        "forest_chance": 0.05,
        "grass_chance": 0.05,
        "height_offset": 0.12,
    },

}


def _decoration_hash(x, y, salt):
    """
    Deterministic pseudo-random value in [0, 1) for a tile, used to scatter
    decorations. Unlike a linear check such as `(x * a + y * b) % n == 0`,
    which always produces evenly-spaced parallel diagonal lines (an artifact
    of the congruence, not real randomness), this mixes the bits of x, y,
    and a salt so results look organically scattered while still being
    fully deterministic for a given tile/salt pair (no shared RNG state,
    safe to call in any order).
    """
    h = (x * 0x1F1F1F1F) ^ (y * 0x2545F491) ^ (salt * 0x9E3779B1)
    h = (h ^ (h >> 15)) * 0x85EBCA6B
    h = (h ^ (h >> 13)) * 0xC2B2AE35
    h ^= h >> 16
    return (h & 0xFFFFFFFF) / 0xFFFFFFFF


def _chance(x, y, salt, probability):
    """Returns True with roughly `probability` odds, scattered (not aligned)."""
    return _decoration_hash(x, y, salt) < probability


class HeightMap:
    """
    Stores the elevation of every tile.
    Values are normalized between 0.0 and 1.0.
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.values = [
            [0.0 for _ in range(width)]
            for _ in range(height)
        ]

    def get(self, x, y):
        return self.values[y][x]

    def set(self, x, y, value):
        self.values[y][x] = value


class FlowField:
    """
    Stores, for every tile, which single downhill neighbor water flows to
    (`direction`) and how much flow has accumulated there from all its
    upstream tiles (`volume`). Both are computed once in _generate_flow_field()
    and then just read everywhere else, so river accumulation and river
    painting always agree on the exact same path.
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.direction = [[None for _ in range(width)] for _ in range(height)]
        self.volume = [[1 for _ in range(width)] for _ in range(height)]

    def get_direction(self, x, y):
        return self.direction[y][x]

    def set_direction(self, x, y, target):
        self.direction[y][x] = target

    def get_volume(self, x, y):
        return self.volume[y][x]

    def add_volume(self, x, y, amount):
        self.volume[y][x] += amount


class RegionMap:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.values = [
            [-1 for _ in range(width)]
            for _ in range(height)
        ]

    def get(self, x, y):
        return self.values[y][x]

    def set(self, x, y, region):
        self.values[y][x] = region


class PointOfInterest:

    def __init__(
        self,
        name,
        tile,
        min_spacing,
        score_function
    ):
        self.name = name
        self.tile = tile
        self.min_spacing = min_spacing
        self.score_function = score_function

class Region:
    def __init__(self, id, name, biome):
        self.id = id
        self.name = name
        self.biome = biome

        self.tiles = []
        self.center = None
        self.points_of_interest = []


class TerrainGenerator:
    def terrain_tags(self):
        return ()

    def decorate(self, game_map, heightmap, moisture, river_positions):
        return

    def place_landmarks(self, game_map, heightmap, moisture, river_positions):
        return []

    def apply(self, game_map, heightmap, moisture, river_positions):
        raise NotImplementedError


class PlainsGenerator(TerrainGenerator):
    def terrain_tags(self):
        return ("open_grass", "scattered_trees", "gentle_hills")

    def apply(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if (x, y) in river_tiles:
                    game_map.tiles[y][x] = ground
                elif h > 0.78:
                    game_map.tiles[y][x] = tall_grass
                elif h > 0.60:
                    game_map.tiles[y][x] = clearing
                elif m > 0.72 and _chance(x, y, 3, 1 / 19):
                    game_map.tiles[y][x] = tree
                else:
                    game_map.tiles[y][x] = ground

        self.decorate(game_map, heightmap, moisture, river_positions)
        return self.place_landmarks(game_map, heightmap, moisture, river_positions)

    def decorate(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                if (x, y) in river_tiles:
                    continue
                tile = game_map.tiles[y][x]
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if tile not in {ground, grass, tall_grass}:
                    continue

                if h > 0.22 and _chance(x, y, 1, 1 / 11):
                    game_map.tiles[y][x] = ridge
                elif m > 0.32 and _chance(x, y, 2, 1 / 15):
                    game_map.tiles[y][x] = meadow
                elif h > 0.50 and _chance(x, y, 3, 1 / 19):
                    game_map.tiles[y][x] = rock_formation

    def place_landmarks(self, game_map, heightmap, moisture, river_positions):
        candidates = []
        width, height = game_map.width, game_map.height
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                if (x, y) in set(river_positions or ()):
                    continue
                tile = game_map.tiles[y][x]
                if tile not in {grass, tall_grass, ground}:
                    continue
                if (x + y) % 17 == 0:
                    candidates.append((x, y))

        if not candidates:
            return []

        x, y = random.choice(candidates)
        landmark = random.choice(["Ruined Farm", "Caravan Camp", "Standing Stones", "Windmill"])
        game_map.tiles[y][x] = ground
        return [(x, y, landmark)]


class ForestGenerator(TerrainGenerator):
    def terrain_tags(self):
        return ("forests", "rolling_hills", "streams")

    def apply(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if (x, y) in river_tiles:
                    game_map.tiles[y][x] = ground
                elif h > 0.80:
                    game_map.tiles[y][x] = tree
                elif h > 0.66:
                    game_map.tiles[y][x] = tall_grass
                elif m > 0.62 and _chance(x, y, 3, 1 / 19):
                    game_map.tiles[y][x] = tree
                else:
                    game_map.tiles[y][x] = clearing

        self.decorate(game_map, heightmap, moisture, river_positions)
        return self.place_landmarks(game_map, heightmap, moisture, river_positions)

    def decorate(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                if (x, y) in river_tiles:
                    continue
                tile = game_map.tiles[y][x]
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if tile not in {grass, tall_grass, ground, tree}:
                    continue

                if m > 0.44 and h < 0.40 and _chance(x, y, 1, 1 / 13):
                    game_map.tiles[y][x] = pond
                elif tile is tree and _chance(x, y, 2, 1 / 17):
                    game_map.tiles[y][x] = giant_tree
                elif m > 0.52 and _chance(x, y, 3, 1 / 19):
                    game_map.tiles[y][x] = flower_field
                elif h < 0.65 and _chance(x, y, 4, 1 / 23):
                    game_map.tiles[y][x] = clearing

    def place_landmarks(self, game_map, heightmap, moisture, river_positions):
        candidates = []
        width, height = game_map.width, game_map.height
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                if (x, y) in set(river_positions or ()):
                    continue
                tile = game_map.tiles[y][x]
                if tile not in {grass, tall_grass, ground, tree}:
                    continue
                if (x * 3 + y * 5 + 1) % 19 == 0:
                    candidates.append((x, y))

        if not candidates:
            return []

        x, y = random.choice(candidates)
        landmark = random.choice(["Ancient Oak", "Fairy Pond", "Stone Circle", "Bandit Camp"])
        game_map.tiles[y][x] = ground
        return [(x, y, landmark)]


class SwampGenerator(TerrainGenerator):
    def terrain_tags(self):
        return ("shallow_lakes", "mud_grass", "dead_trees")

    def apply(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if (x, y) in river_tiles:
                    game_map.tiles[y][x] = ground
                elif m > 0.82 and h < 0.50:
                    game_map.tiles[y][x] = lake
                elif m > 0.65:
                    game_map.tiles[y][x] = clearing
                elif h > 0.72:
                    game_map.tiles[y][x] = tree
                else:
                    game_map.tiles[y][x] = ground

        self.decorate(game_map, heightmap, moisture, river_positions)
        return self.place_landmarks(game_map, heightmap, moisture, river_positions)

    def decorate(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                if (x, y) in river_tiles:
                    continue
                tile = game_map.tiles[y][x]
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if tile not in {ground, grass, tree, lake}:
                    continue

                if m > 0.64 and h < 0.45 and _chance(x, y, 1, 1 / 11):
                    game_map.tiles[y][x] = marsh_pool
                elif tile is tree and _chance(x, y, 2, 1 / 13):
                    game_map.tiles[y][x] = dead_forest
                elif m > 0.72 and _chance(x, y, 3, 1 / 19):
                    game_map.tiles[y][x] = reeds

    def place_landmarks(self, game_map, heightmap, moisture, river_positions):
        candidates = []
        width, height = game_map.width, game_map.height
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                if (x, y) in set(river_positions or ()):
                    continue
                tile = game_map.tiles[y][x]
                if tile not in {grass, ground, tree, lake}:
                    continue
                if (x * 7 + y * 3 + 2) % 23 == 0:
                    candidates.append((x, y))

        if not candidates:
            return []

        x, y = random.choice(candidates)
        landmark = random.choice(["Witch Hut", "Bog Cemetery", "Sunken Chapel", "Giant Lily Marsh"])
        structure_id = {"Witch Hut": "witch_hut"}.get(landmark)
        if structure_id is not None:
            return [(x, y, landmark, structure_id)]
        game_map.tiles[y][x] = ground
        return [(x, y, landmark)]


class MountainGenerator(TerrainGenerator):
    def terrain_tags(self):
        return ("cliffs", "plateaus", "caves", "pine_forests")

    def apply(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if (x, y) in river_tiles:
                    game_map.tiles[y][x] = ground
                elif h > 0.90:
                    game_map.tiles[y][x] = mountain
                elif h > 0.78:
                    game_map.tiles[y][x] = ground
                elif h > 0.65 and m > 0.50:
                    game_map.tiles[y][x] = tree
                else:
                    game_map.tiles[y][x] = clearing

        self.decorate(game_map, heightmap, moisture, river_positions)
        return self.place_landmarks(game_map, heightmap, moisture, river_positions)

    def decorate(self, game_map, heightmap, moisture, river_positions):
        river_tiles = set(river_positions or ())
        width, height = game_map.width, game_map.height

        for y in range(height):
            for x in range(width):
                if (x, y) in river_tiles:
                    continue
                tile = game_map.tiles[y][x]
                h = heightmap.get(x, y)
                m = moisture.get(x, y)

                if tile not in {ground, grass, tree, mountain}:
                    continue

                if h > 0.60 and _chance(x, y, 1, 1 / 13):
                    game_map.tiles[y][x] = mountain
                elif h > 0.30 and _chance(x, y, 2, 1 / 17):
                    game_map.tiles[y][x] = scree
                elif h < 0.45 and _chance(x, y, 3, 1 / 19):
                    game_map.tiles[y][x] = valley
                elif h > 0.52 and m > 0.40 and _chance(x, y, 4, 1 / 23):
                    game_map.tiles[y][x] = waterfall
                elif tile is tree and _chance(x, y, 5, 1 / 29):
                    game_map.tiles[y][x] = ridge

    def place_landmarks(self, game_map, heightmap, moisture, river_positions):
        candidates = []
        width, height = game_map.width, game_map.height
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                if (x, y) in set(river_positions or ()):
                    continue
                tile = game_map.tiles[y][x]
                if tile not in {ground, grass, tree, mountain}:
                    continue
                if (x * 5 + y * 7 + 1) % 29 == 0:
                    candidates.append((x, y))

        if not candidates:
            return []

        x, y = random.choice(candidates)
        landmark = random.choice(["Dwarven Mine", "Giant Skeleton", "Watchtower", "Shrine", "Dragon Bones"])
        structure_id = {"Watchtower": "watch_tower", "Shrine": "shrine"}.get(landmark)
        if structure_id is not None:
            return [(x, y, landmark, structure_id)]
        game_map.tiles[y][x] = ground
        return [(x, y, landmark)]


def get_terrain_generator(biome):
    if biome is None:
        return PlainsGenerator

    if biome in {ChunkBiome.FOREST, ChunkBiome.FOREST.value}:
        return ForestGenerator
    if biome in {ChunkBiome.SWAMP, ChunkBiome.SWAMP.value}:
        return SwampGenerator
    if biome in {ChunkBiome.MOUNTAINS, ChunkBiome.MOUNTAINS.value}:
        return MountainGenerator
    if biome in {ChunkBiome.PLAINS, ChunkBiome.PLAINS.value}:
        return PlainsGenerator

    return PlainsGenerator


def _biome(height, moisture):
    if height < DEEP_WATER:
        return BIOME_OCEAN
    if height < SHALLOW_WATER:
        return BIOME_BEACH
    if height >= HILLS:
        return BIOME_MOUNTAINS
    if height >= PLAINS:
        return BIOME_HILLS
    if moisture > 0.72:
        return BIOME_SWAMP
    if moisture > 0.50:
        return BIOME_FOREST

    return BIOME_PLAINS


def _random_region_name(biome):
    prefix = random.choice(REGION_PREFIXES)

    suffix = random.choice(
        REGION_SUFFIX.get(
            biome,
            ["Wilds"]
        )
    )

    return f"{prefix} {suffix}"


def _generate_region_seeds(width, height, count):
    seeds = []

    for i in range(count):
        x = random.randrange(width)
        y = random.randrange(height)

        seeds.append((i, x, y))

    return seeds


def _generate_regions(game_map, heightmap, moisture):
    width = game_map.width
    height = game_map.height

    region_count = max(6, width * height // 12000)

    seeds = _generate_region_seeds(
        width,
        height,
        region_count
    )

    region_map = RegionMap(width, height)
    regions = {}

    for region_id, sx, sy in seeds:
        biome = _biome(
            heightmap.get(sx, sy),
            moisture.get(sx, sy)
        )
        region = Region(
            region_id,
            _random_region_name(biome),
            biome
        )
        region.center = (sx, sy)
        regions[region_id] = region


    for y in range(height):
        for x in range(width):
            nearest = min(
                seeds,
                key=lambda s:
                (x-s[1])**2 + (y-s[2])**2
            )
            region_id = nearest[0]
            region_map.set(x, y, region_id)
            regions[region_id].tiles.append((x, y))


    return region_map, list(regions.values())


# ---------------------------------------------------------------------------
# Perlin noise
#
# A small, dependency-free 2D Perlin noise implementation (Ken Perlin's
# "improved" fade curve), layered into fractal Brownian motion (fBm) for
# multi-frequency detail. This is the *base layer* the overworld is built
# from — low-frequency noise lays out where the land and water go, and
# higher-frequency noise lays out where the forests go. Cellular automata
# (below) is then used purely as a post-processing pass on top of it, to
# smooth the raw noise into organic-looking coastlines and tree lines
# instead of leaving it as speckled noise.
# ---------------------------------------------------------------------------

def _build_permutation_table(seed):
    rng = random.Random(seed)

    perm = list(range(256))
    rng.shuffle(perm)

    return perm + perm


def _distance(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])


def _heuristic(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])


def _nearest_edge_tile(x, y, width, height):

    distances = {
        (x, 0): y,
        (x, height-1): height-1-y,
        (0, y): x,
        (width-1, y): width-1-x
    }

    return min(distances, key=distances.get)


def _nearest_tile(game_map, start, predicate, max_radius=20):

    sx, sy = start

    best = None
    best_dist = float("inf")

    for y in range(max(0, sy-max_radius), min(game_map.height, sy+max_radius+1)):
        for x in range(max(0, sx-max_radius), min(game_map.width, sx+max_radius+1)):

            if predicate(game_map.tiles[y][x]):

                d = abs(x-sx)+abs(y-sy)

                if d < best_dist:
                    best_dist = d
                    best = (x, y)

    return best

def _find_path(game_map, heightmap, start, goal):
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = {start: 0}

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path
        cx, cy = current

        for nx, ny in _neighbors(cx, cy, heightmap.width, heightmap.height):
            cost = _movement_cost(game_map, nx, ny)

            if cost is None:
                continue

            tentative = g_score[current] + cost

            if tentative < g_score.get((nx, ny), float("inf")):
                came_from[(nx, ny)] = current
                g_score[(nx, ny)] = tentative
                f = tentative + _heuristic((nx, ny), goal)
                heapq.heappush(open_set, (f, (nx, ny)))

    return []


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(t, a, b):
    return a + t * (b - a)


def _gradient(hash_value, x, y):
    """Pick one of 8 gradient directions based on the low bits of the hash."""
    h = hash_value & 7
    u = x if h < 4 else y
    v = y if h < 4 else x
    return (u if h & 1 == 0 else -u) + (v if h & 2 == 0 else -v)


def _perlin(perm, x, y):
    """Sample 2D Perlin noise at (x, y). Returns a value roughly in [-1, 1]."""
    xi, yi = int(math.floor(x)) & 255, int(math.floor(y)) & 255
    xf, yf = x - math.floor(x), y - math.floor(y)
    u, v = _fade(xf), _fade(yf)

    aa = perm[perm[xi] + yi]
    ab = perm[perm[xi] + yi + 1]
    ba = perm[perm[xi + 1] + yi]
    bb = perm[perm[xi + 1] + yi + 1]

    top = _lerp(u, _gradient(aa, xf, yf), _gradient(ba, xf - 1, yf))
    bottom = _lerp(u, _gradient(ab, xf, yf - 1), _gradient(bb, xf - 1, yf - 1))
    return _lerp(v, top, bottom)


def _fractal_noise(perm, x, y, octaves, persistence, lacunarity):
    """Layer several octaves of Perlin noise (fBm) for more natural-looking detail."""
    total, amplitude, frequency, max_amplitude = 0.0, 1.0, 1.0, 0.0
    for _ in range(octaves):
        total += _perlin(perm, x * frequency, y * frequency) * amplitude
        max_amplitude += amplitude
        amplitude *= persistence
        frequency *= lacunarity
    return total / max_amplitude  # normalized back to roughly [-1, 1]


def _generate_mountain_ridges(width, height):
    """
    Creates several long mountain ridges.

    These are NOT mountains yet.
    They're just polylines that later become elevation.
    """
    ridges = []

    ridge_count = max(3, (width * height) // 20000)

    for _ in range(ridge_count):
        x = random.randint(width // 5, width * 4 // 5)
        y = random.randint(height // 5, height * 4 // 5)

        angle = random.uniform(0, math.pi * 2)
        ridge = []

        length = random.randint(
            min(width, height) // 3,
            min(width, height) // 2
        )

        for _ in range(length):
            ridge.append((int(x), int(y)))
            # slowly bend
            angle += random.uniform(-0.25, 0.25)

            x += math.cos(angle)
            y += math.sin(angle)

            if x < 2 or x >= width - 2:
                break
            if y < 2 or y >= height - 2:
                break

        ridges.append(ridge)

    return ridges


def _generate_ridge_heightmap(width, height):
    """
    Builds a heightmap from mountain ridges instead of Perlin noise.
    """
    ridges = _generate_mountain_ridges(width, height)
    heightmap = HeightMap(width, height)
    max_radius = max(width, height) * 0.30

    for y in range(height):
        for x in range(width):
            elevation = 0.0

            for ridge in ridges:
                nearest = float("inf")
                for rx, ry in ridge:
                    d = math.hypot(rx - x, ry - y)

                    if d < nearest:
                        nearest = d

                if nearest < max_radius:
                    influence = 1.0 - (nearest / max_radius)
                    elevation += influence ** 2

            heightmap.set(x, y, elevation)

    _normalize_heightmap(heightmap)

    return heightmap


def _normalize_heightmap(heightmap):

    minimum = float("inf")
    maximum = float("-inf")

    for row in heightmap.values:
        for value in row:
            minimum = min(minimum, value)
            maximum = max(maximum, value)

    scale = maximum - minimum

    if scale == 0:
        return

    for y in range(heightmap.height):
        for x in range(heightmap.width):

            value = heightmap.get(x, y)

            value = value * 0.85 + 0.08

            heightmap.set(x, y, value)


def _bias_grid_toward_world_value(grid, world_value, strength):
    """
    Nudge every tile in a HeightMap-like grid (elevation or moisture) toward
    a single coarse, world-scale value for this chunk, so a chunk sampled
    from a world-map mountain range trends mountainous locally too, and a
    chunk sampled from a wet region trends moister — instead of every
    chunk's terrain being decided independently of its neighbors.
    `strength` controls how hard the world value pulls; the local Perlin
    detail is only shifted, not replaced, so per-chunk variation survives.
    """
    for y in range(grid.height):
        for x in range(grid.width):
            local_value = grid.get(x, y)
            biased = local_value + (world_value - 0.5) * strength
            grid.set(x, y, min(1.0, max(0.0, biased)))


def _generate_moisture_map(perm, chunk_x, chunk_y, width, height, scale, octaves=4, persistence=0.5, lacunarity=2.0,):
    """
    Generates a normalized moisture map.
    Values range from 0.0 to 1.0.
    """
    #perm = _build_permutation_table()
    moisture = HeightMap(width, height)

    for y in range(height):
        for x in range(width):
            world_x = chunk_x * width + x
            world_y = chunk_y * height + y
            value = _fractal_noise(
                perm,
                world_x / scale,
                world_y / scale,
                octaves,
                persistence,
                lacunarity
            )

            value = (value + 1) / 2
            moisture.set(x, y, value)

    return moisture


def _score_dungeon_location(game_map, heightmap, moisture, x, y):
    score = 0
    biome = _biome(
        heightmap.get(x, y),
        moisture.get(x, y)
    )

    if biome == BIOME_SWAMP:
        score -= 25
    elif biome == BIOME_MOUNTAINS:
        score += 40
    elif biome == BIOME_FOREST:
        score += 15

    # Forest nearby
    forest = _nearest_tile(
        game_map,
        (x, y),
        lambda t: t == tree,
        max_radius=8
    )

    if forest:
        score += 15

    # River nearby
    river_pos = _nearest_tile(
        game_map,
        (x, y),
        is_water_tile,
        max_radius=10
    )

    if river_pos:
        score += 10

    # Road nearby — an entrance that already sits close to the trunk road
    # network needs a shorter (cheaper, less land-scarring) spur to reach it.
    road_pos = _nearest_tile(
        game_map,
        (x, y),
        lambda t: t is road,
        max_radius=12
    )

    if road_pos:
        score += 10

    return score

# ---------------------------------------------------------------------------
# Cellular automata post-processing
#
# Same broad idea as the room/tunnel carving in dungeon_generator.py, but
# instead of hand-placed rectangles we clean up a boolean grid by repeatedly
# smoothing it — here that grid comes from thresholded Perlin noise (above)
# rather than raw random fill, so the smoothing turns noisy blob edges into
# organic-looking coastlines and tree lines.
# ---------------------------------------------------------------------------

def _count_solid_neighbors(grid, x, y, width, height):
    """Count solid cells in the 8 tiles surrounding (x, y). Out-of-bounds counts as solid
    so that terrain naturally thickens toward the edge of the map instead of fraying out."""
    count = 0
    for ny in range(y - 1, y + 2):
        for nx in range(x - 1, x + 2):
            if nx == x and ny == y:
                continue
            if 0 <= nx < width and 0 <= ny < height:
                if grid[ny][nx]:
                    count += 1
            else:
                count += 1
    return count


def _smooth(grid, width, height, birth_limit, death_limit):
    """Run a single cellular automata smoothing pass over the grid."""
    new_grid = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            neighbors = _count_solid_neighbors(grid, x, y, width, height)
            if grid[y][x]:
                # Already solid — stays solid unless it's too isolated.
                new_grid[y][x] = neighbors >= death_limit
            else:
                # Currently open — becomes solid if enough solid neighbors crowd in.
                new_grid[y][x] = neighbors > birth_limit
    return new_grid


def _smooth_mask(grid, width, height, iterations, birth_limit=4, death_limit=3):
    """Repeatedly apply the CA smoothing pass to an existing boolean grid (post-processing)."""
    for _ in range(iterations):
        grid = _smooth(grid, width, height, birth_limit, death_limit)
    return grid


# ---------------------------------------------------------------------------
# Rivers
#
# Rivers are derived from a flow field: every tile picks a single downhill
# neighbor to drain into, and flow volume accumulates from high ground down
# to low ground. Wherever enough volume piles up, that's a river.
#
# The key fix here vs. the old approach: a tile's downhill neighbor involves
# a random choice (to make rivers meander instead of running bone-straight),
# so it must be rolled exactly ONCE per tile and then reused everywhere.
# The previous code called that random pick separately during accumulation
# and again during painting, so the two steps frequently disagreed about
# which way a tile's water was flowing — volume would accumulate along one
# path while the painted river wandered off along another, producing rivers
# that broke, forked randomly, or didn't line up with their own source of
# flow at all. FlowField.direction fixes that by caching the choice.
#
# world/water_features.py was written with dungeons in mind (it replaces
# `floor`/`wall` tiles), so we don't reuse its generation functions directly
# — we borrow its river tile template and drop it onto open ground the same
# way, so both dungeons and the overworld render water the same way (and
# is_water_tile() keeps working everywhere).
# ---------------------------------------------------------------------------

def _neighbors(x, y, width, height):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx = x + dx
            ny = y + dy

            if 0 <= nx < width and 0 <= ny < height:
                yield nx, ny


def _pick_downhill_neighbor(heightmap, x, y):
    """
    Pick the neighbor this tile's water flows toward.

    Instead of always taking the single lowest neighbor, we randomly choose
    between several near-steepest candidates so rivers meander naturally
    rather than cutting a perfectly straight line downhill. This is called
    exactly once per tile (from _generate_flow_field) and the result is
    cached, so every later step agrees on the answer.
    """
    current = heightmap.get(x, y)
    candidates = []

    for nx, ny in _neighbors(x, y, heightmap.width, heightmap.height):
        drop = current - heightmap.get(nx, ny)

        if drop > 0:
            candidates.append((drop, nx, ny))

    if not candidates:
        return None

    best_drop = max(candidates)[0]
    good = [
        (nx, ny)
        for drop, nx, ny in candidates
        if drop >= best_drop * 0.75
    ]

    return random.choice(good)


def _generate_flow_field(heightmap):
    """
    Build the flow field in two passes:

      1. Give every tile its (single, cached) downhill direction. This can be
         done in any order — one tile's choice doesn't depend on any other.
      2. Walk tiles from highest to lowest, adding each tile's accumulated
         volume onto whatever it flows toward. Processing high-to-low
         guarantees that by the time we reach a tile, every one of its
         upstream neighbors has already contributed its volume.
    """
    flow = FlowField(heightmap.width, heightmap.height)
    tiles_by_height = []

    for y in range(heightmap.height):
        for x in range(heightmap.width):
            flow.set_direction(x, y, _pick_downhill_neighbor(heightmap, x, y))
            tiles_by_height.append((heightmap.get(x, y), x, y))

    tiles_by_height.sort(reverse=True)

    for _, x, y in tiles_by_height:
        target = flow.get_direction(x, y)
        if target is None:
            continue

        tx, ty = target
        flow.add_volume(tx, ty, flow.get_volume(x, y))

    return flow


def _river_width(volume):
    """Returns the radius of the river based on accumulated flow volume."""
    if volume < 25:
        return 0      # not a river
    if volume < 60:
        return 1      # narrow stream
    if volume < 120:
        return 2      # medium river
    if volume < 250:
        return 3      # large river

    return 4          # huge river


def _river_tile_positions(flow_field):
    """
    Work out every tile covered by river geometry, purely from the flow
    field — no game_map involved yet. Splitting this out from the actual
    tile-painting lets the caller fold river positions into the moisture map
    (rivers make nearby land wetter) before biomes are painted, while the
    actual carving of `river` tiles onto the map still happens afterward
    (see _carve_rivers), since biome painting would otherwise overwrite it.
    """
    width, height = flow_field.width, flow_field.height
    positions = set()

    for y in range(height):
        for x in range(width):
            radius = _river_width(flow_field.get_volume(x, y))
            if radius == 0:
                continue

            direction = flow_field.get_direction(x, y)
            if direction is None:
                continue

            dx, dy = direction[0] - x, direction[1] - y
            perp_x, perp_y = -dy, dx  # perpendicular to flow, gives the river its width

            for i in range(-radius, radius + 1):
                rx, ry = x + perp_x * i, y + perp_y * i
                if 0 <= rx < width and 0 <= ry < height:
                    positions.add((rx, ry))

    return positions


def _carve_rivers(game_map, river_positions):
    """
    Paint river tiles onto the map on top of whatever biome was already
    painted there. Lakes take precedence — a river runs into a lake rather
    than replacing it.
    """
    river_tiles = []

    for x, y in river_positions:
        if game_map.tiles[y][x] is lake:
            continue
        game_map.tiles[y][x] = river
        river_tiles.append((x, y))

    return river_tiles


def _edge_midpoint(width, height, direction):
    """The tile at the midpoint of one edge of the chunk, used as the fixed
    point a major river connects to so it lines up with the matching edge
    of whichever neighboring chunk it continues into."""
    if direction == "N":
        return (width // 2, 0)
    if direction == "S":
        return (width // 2, height - 1)
    if direction == "W":
        return (0, height // 2)
    return (width - 1, height // 2)  # "E"


def _carve_major_river(game_map, heightmap, edges, radius=2):
    """
    Force a wide river connecting the given edge(s) of this chunk.

    The flow-field river generated above (_river_tile_positions/_carve_rivers)
    is purely local to a single chunk's heightmap, so it has no way to know
    that a river should continue into the next chunk over. This carves a
    guaranteed river between the WorldMap-provided edge crossings instead,
    so a world-scale river reliably lines up on both sides of a chunk
    boundary. It's routed with the same A* pathfinder as roads, so it still
    bends around whatever terrain the local heightmap produced.
    """
    width, height = game_map.width, game_map.height
    waypoints = [_edge_midpoint(width, height, direction) for direction in edges]

    if len(waypoints) == 1:
        # A source or a mouth — only one edge is fixed, so run the river to
        # this chunk's lowest point rather than to a second edge.
        lowest_point = min(
            ((x, y) for y in range(height) for x in range(width)),
            key=lambda point: heightmap.get(*point),
        )
        waypoints.append(lowest_point)

    river_tiles = []

    for start, goal in zip(waypoints, waypoints[1:]):
        path = _find_path(game_map, heightmap, start, goal)

        for x, y in path:
            for nx in range(max(0, x - radius), min(width, x + radius + 1)):
                for ny in range(max(0, y - radius), min(height, y + radius + 1)):
                    if _distance((x, y), (nx, ny)) > radius:
                        continue
                    if game_map.tiles[ny][nx] is lake:
                        continue
                    game_map.tiles[ny][nx] = river
                    river_tiles.append((nx, ny))

    return river_tiles


def _apply_river_moisture(moisture, river_positions, radius=6, boost=0.4):
    """Rivers make nearby land moister, encouraging forest/swamp instead of plains."""
    width, height = moisture.width, moisture.height

    for rx, ry in river_positions:
        for y in range(max(0, ry - radius), min(height, ry + radius + 1)):
            for x in range(max(0, rx - radius), min(width, rx + radius + 1)):
                dist = _distance((x, y), (rx, ry))
                if dist > radius:
                    continue

                falloff = 1 - (dist / radius)
                moisture.set(x, y, min(1.0, moisture.get(x, y) + boost * falloff))


# ---------------------------------------------------------------------------
# Roads
#
# Roads are laid down as a backbone network connecting each region to its
# nearest neighboring region, using A* pathfinding (replacing the old biased
# random walk) so they take sensible routes around water and rough terrain.
# This runs *before* points of interest are placed so that POI placement can
# take "is this near a road?" into account, and so newly-placed POIs have
# something to connect a short spur road to (see _connect_to_road_network).
# ---------------------------------------------------------------------------
def _movement_cost(game_map, x, y):

    tile = game_map.tiles[y][x]

    if tile == lake:
        return None

    if tile == river:
        return None

    if tile == tree:
        return 6

    if tile == tall_grass:
        return 2

    if tile == road:
        return 1

    return 1


def _paint_road_path(game_map, heightmap, start, goal):
    """Pathfind from start to goal and paint the route as road, skipping water
    and dungeon entrances (an entrance tile stays an entrance, not a road)."""
    path = _find_path(game_map, heightmap, start, goal)
    road_tiles = []

    for x, y in path:
        if is_water_tile(game_map.tiles[y][x]):
            continue
        if game_map.tiles[y][x] is not dungeon_entrance:
            game_map.tiles[y][x] = road
        road_tiles.append((x, y))

    return road_tiles


def _generate_trunk_roads(game_map, heightmap, regions):
    """
    Lay down a backbone road network by connecting each region's center to
    its nearest neighboring region's center. Runs before POIs are placed —
    see the module-level comment above — so it only has region centers to
    work from, not dungeon entrances.
    """
    centers = [region.center for region in regions if region.center is not None]
    connected_pairs = set()
    road_tiles = []

    for center in centers:
        nearest = min(
            (other for other in centers if other != center),
            key=lambda other: _distance(center, other),
            default=None
        )
        if nearest is None:
            continue

        pair = frozenset({center, nearest})
        if pair in connected_pairs:
            continue
        connected_pairs.add(pair)

        road_tiles.extend(_paint_road_path(game_map, heightmap, center, nearest))

    return road_tiles


def _connect_to_road_network(game_map, heightmap, start, road_tiles):
    """
    Connect a point to the nearest existing road tile with a short spur,
    falling back to the map edge if no road exists yet (e.g. a region-sparse
    or very small map).
    """
    goal = min(road_tiles, key=lambda tile: _distance(start, tile)) if road_tiles else None

    if goal is None:
        goal = _nearest_edge_tile(start[0], start[1], game_map.width, game_map.height)

    return _paint_road_path(game_map, heightmap, start, goal)


# ---------------------------------------------------------------------------
# Points of interest
#
# Dungeon entrances are, for now, the only points of interest the world
# generator drops onto the map. Towns, camps, and other structures can be
# added the same way later — pick valid open tiles, keep them spaced apart,
# mark them. POIs are placed after roads exist, so each one can be scored on
# (and afterward spurred onto) the existing road network.
# ---------------------------------------------------------------------------

def _is_valid_entrance_spot(game_map, x, y):
    """A dungeon entrance needs open, dry, walkable ground to sit on."""
    if not game_map.is_walkable(x, y):
        return False
    tile = game_map.tiles[y][x]
    if is_water_tile(tile):
        return False
    return tile is ground  # keep entrances off tall grass/tree tiles for visibility


def _place_pois(game_map, heightmap, moisture, poi, count):
    candidates = []

    for y in range(game_map.height):
        for x in range(game_map.width):
            if not game_map.is_walkable(x, y):
                continue
            score = poi.score_function(
                game_map,
                heightmap,
                moisture,
                x,
                y
            )
            candidates.append((score, x, y))

    candidates.sort(reverse=True)
    placed = []

    for score, x, y in candidates:
        if len(placed) >= count:
            break

        too_close = False

        for px, py in placed:
            if _distance((x, y), (px, py)) < poi.min_spacing:
                too_close = True
                break

        if too_close:
            continue

        game_map.tiles[y][x] = poi.tile
        placed.append((x, y))

    return placed


# ---------------------------------------------------------------------------
# Heightmap PNG export
#
# A small debug/visualization helper: dumps a HeightMap out as a single PNG
# so the raw noise can be eyeballed without running the full game. Written
# by hand with `struct` + `zlib` (both stdlib) instead of adding an image
# library dependency — same "no new dependencies" approach as the Perlin
# noise implementation above.
# ---------------------------------------------------------------------------

# Elevation -> color stops, reusing the same thresholds as _biome() so the
# preview image lines up with what actually gets painted onto the map.
# _HEIGHTMAP_COLOR_STOPS = [
#     (0.00,          (20, 40, 120)),    # deep water
#     (DEEP_WATER,    (40, 90, 200)),    # shallow water
#     (SHALLOW_WATER, (194, 178, 128)),  # beach
#     (PLAINS * 0.6,  (90, 160, 60)),    # plains / lowlands
#     (PLAINS,        (60, 110, 40)),    # forest-ish green
#     (HILLS,         (120, 100, 70)),   # hills
#     (1.00,          (235, 235, 240)),  # mountain peaks
# ]


# def _lerp_color(t, color_a, color_b):
#     return tuple(
#         round(_lerp(t, a, b))
#         for a, b in zip(color_a, color_b)
#     )


# def _elevation_to_color(value):
#     """Map a normalized elevation value in [0.0, 1.0] to an (r, g, b) color."""
#     value = min(1.0, max(0.0, value))

#     for (low, low_color), (high, high_color) in zip(_HEIGHTMAP_COLOR_STOPS, _HEIGHTMAP_COLOR_STOPS[1:]):
#         if value <= high:
#             span = high - low
#             t = 0.0 if span == 0 else (value - low) / span
#             return _lerp_color(t, low_color, high_color)

#     return _HEIGHTMAP_COLOR_STOPS[-1][1]


# def _write_png(path, width, height, pixel_rows):
#     """
#     Write an uncompressed-filter RGB PNG from raw pixel data.
#     pixel_rows: list of `height` rows, each a flat list of `width * 3` ints (0-255).
#     """

#     def chunk(chunk_type, data):
#         return (
#             struct.pack(">I", len(data))
#             + chunk_type
#             + data
#             + struct.pack(">I", zlib.crc32(chunk_type + data))
#         )

#     signature = b"\x89PNG\r\n\x1a\n"

#     header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB, no filter/interlace

#     # Each scanline is prefixed with a filter-type byte (0 = "none").
#     raw = bytearray()
#     for row in pixel_rows:
#         raw.append(0)
#         raw.extend(row)

#     compressed = zlib.compress(bytes(raw), level=9)

#     png = (
#         signature
#         + chunk(b"IHDR", header)
#         + chunk(b"IDAT", compressed)
#         + chunk(b"IEND", b"")
#     )

#     with open(path, "wb") as f:
#         f.write(png)


# def save_heightmap_png(heightmap, path="heightmap.png"):
#     """
#     Render a HeightMap (values in [0.0, 1.0]) out to a color-coded PNG at
#     `path`, using the same elevation bands as the biome logic so it reads
#     like a preview of the generated terrain. Handy for eyeballing the noise
#     without needing to run the game.
#     """
#     pixel_rows = []

#     for y in range(heightmap.height):
#         row = []
#         for x in range(heightmap.width):
#             r, g, b = _elevation_to_color(heightmap.get(x, y))
#             row.extend((r, g, b))
#         pixel_rows.append(row)

#     _write_png(path, heightmap.width, heightmap.height, pixel_rows)

#     return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Minimum number of empty tiles kept between two town buildings' footprints.
TOWN_BUILDING_GAP = 2


def _anchor_offset(size_a, size_b, gap):
    """
    Distance to add to one building's anchor coordinate to get the anchor
    coordinate of a second building placed directly after it (to the right,
    or below, depending on whether this is used for x or y), leaving at
    least `gap` empty tiles between their two footprints.

    place_structure_at_anchor centers a building on its anchor using
    `origin = anchor - size // 2`, so this mirrors that math rather than
    guessing at spacing with hand-picked offsets.
    """
    return (size_a - size_a // 2) + gap + (size_b // 2)


def _place_town(game_map, chunk_coord, biome):
    """
    Attempt to place a small town — one tavern, one shop, and a handful of
    houses, clustered together — in this chunk.

    Not every chunk gets a town: like the single biome_structure fallback
    below, this is a cheap deterministic "roll" based on the chunk's
    coordinates so towns show up now and then rather than on every screen.
    Mountain chunks are skipped since cliffs/ridges break up the terrain
    too much for a clean town layout.

    The tavern is placed first and anchors the rest of the layout; if it
    doesn't fit anywhere nearby, we give up on the town entirely rather
    than scattering a shop or houses with nothing around them. The shop
    and houses are positioned using each building's actual footprint size
    (from its blueprint) plus TOWN_BUILDING_GAP, so buildings stay at
    least a tile apart instead of relying on hand-picked offsets. Note
    place_structure_at_anchor may still nudge a building a tile or two to
    find clear ground, so this spacing is a target, not an absolute
    guarantee.
    """
    width, height = game_map.width, game_map.height

    if biome == ChunkBiome.MOUNTAINS:
        return []
    if (chunk_coord[0] * 13 + chunk_coord[1] * 7) % 5 != 0:
        return []

    anchor_x = width // 2 + (chunk_coord[0] % 5) - 2
    anchor_y = height // 2 + (chunk_coord[1] % 5) - 2

    tavern_bp = get_structure_blueprint("tavern")
    shop_bp = get_structure_blueprint("shop")
    house_bp = get_structure_blueprint("house")

    tavern_w, tavern_h = len(tavern_bp.tile_map[0]), len(tavern_bp.tile_map)
    shop_w, shop_h = len(shop_bp.tile_map[0]), len(shop_bp.tile_map)
    house_w, house_h = len(house_bp.tile_map[0]), len(house_bp.tile_map)

    town_buildings = []

    tavern = place_structure_at_anchor(game_map, "tavern", anchor_x, anchor_y)
    if not tavern:
        return []
    town_buildings.append(("tavern", tavern))

    # Shop sits to the right of the tavern, on the same row.
    shop_anchor_x = anchor_x + _anchor_offset(tavern_w, shop_w, TOWN_BUILDING_GAP)
    shop = place_structure_at_anchor(game_map, "shop", shop_anchor_x, anchor_y)
    if shop:
        town_buildings.append(("shop", shop))

    # Houses form a row below the tavern/shop row, spaced the same way.
    houses_row_y = anchor_y + _anchor_offset(max(tavern_h, shop_h), house_h, TOWN_BUILDING_GAP)
    house_spacing = _anchor_offset(house_w, house_w, TOWN_BUILDING_GAP)
    house_anchors_x = [anchor_x - house_spacing, anchor_x, anchor_x + house_spacing]

    for house_anchor_x in house_anchors_x:
        house = place_structure_at_anchor(game_map, "house", house_anchor_x, houses_row_y)
        if house:
            town_buildings.append(("house", house))

    return town_buildings


def generate_chunk_context(game_map, chunk_coord, world_seed, biome=None, world_map=None, num_dungeon_entrances=None, debug_heightmap_path=None, ChunkBiome=None):
    """Build a staged context for one overworld chunk, exposing the pipeline
    phases clearly while preserving the existing terrain-generation behavior."""
    if ChunkBiome is None:
        from core.game import ChunkBiome as _ChunkBiome
        ChunkBiome = _ChunkBiome

    if biome is None:
        biome = ChunkBiome.PLAINS

    perm = _build_permutation_table(world_seed)
    width, height = game_map.width, game_map.height

    if num_dungeon_entrances is None:
        num_dungeon_entrances = max(1, (width * height) // 12000)

    # 1. Region generator: coarse regional identity and region boundaries.
    heightmap = _generate_ridge_heightmap(width, height)
    if world_map is not None:
        _bias_grid_toward_world_value(
            heightmap,
            world_map.elevation_at(chunk_coord),
            WORLD_ELEVATION_BIAS_STRENGTH,
        )

    flow_field = _generate_flow_field(heightmap)
    river_positions = _river_tile_positions(flow_field)

    moisture = _generate_moisture_map(
        perm,
        chunk_coord[0],
        chunk_coord[1],
        width,
        height,
        scale=max(width, height) / 10
    )

    if world_map is not None:
        _bias_grid_toward_world_value(
            moisture,
            world_map.moisture_at(chunk_coord),
            WORLD_MOISTURE_BIAS_STRENGTH,
        )

    _apply_river_moisture(moisture, river_positions)
    region_map, regions = _generate_regions(game_map, heightmap, moisture)

    # 2. Chunk generator: paint terrain with biome-specific terrain rules.
    terrain_generator = get_terrain_generator(biome)()
    landmarks = terrain_generator.apply(game_map, heightmap, moisture, river_positions)

    river_tiles = _carve_rivers(game_map, river_positions)

    if world_map is not None:
        major_river_edges = world_map.river_edges_at(chunk_coord)
        if major_river_edges:
            river_tiles.extend(_carve_major_river(game_map, heightmap, major_river_edges))

    # 3. Landmark generator: dungeon entrances and future POIs.
    dungeon_poi = PointOfInterest(
        name="Dungeon",
        tile=dungeon_entrance,
        min_spacing=18,
        score_function=_score_dungeon_location
    )
    dungeon_entrances = _place_pois(
        game_map,
        heightmap,
        moisture,
        dungeon_poi,
        num_dungeon_entrances
    )

    # 4. Infrastructure: roads and trails.
    road_tiles = _generate_trunk_roads(game_map, heightmap, regions)
    for entrance in dungeon_entrances:
        road_tiles.extend(_connect_to_road_network(game_map, heightmap, entrance, road_tiles))

    # 5. Population: reserved for creatures, NPC travelers, and encounters.
    population = []

    # 6. Flavor: biome, region name, and scene-level tags.
    region_name = None
    if world_map is not None:
        region_name = world_map.region_name_at(chunk_coord)
    if region_name is None:
        region_name = f"{getattr(biome, 'value', str(biome)).title()} Region"

    flavor = {
        "biome": getattr(biome, "value", str(biome)),
        "region_name": region_name,
        "terrain_tags": list(terrain_generator.terrain_tags()),
        "landmarks": landmarks,
        "has_major_river": bool(world_map and world_map.river_edges_at(chunk_coord)),
        "river_edges": list(world_map.river_edges_at(chunk_coord)) if world_map else [],
    }

    if world_map is not None:
        world_map.set_region_name(chunk_coord, region_name)
        world_map.set_flavor(chunk_coord, flavor)

    ridges = _generate_mountain_ridges(width, height)
    for ridge in ridges:
        for x, y in ridge:
            game_map.tiles[y][x] = mountain

    for landmark in landmarks:
        if len(landmark) < 4:
            continue
        anchor_x, anchor_y, _, structure_id = landmark
        if structure_id is None:
            continue
        place_structure_at_anchor(game_map, structure_id, anchor_x, anchor_y)

    # Towns are placed after the landmark structures above (and after the
    # mountain ridges) so ridges can't carve through a building, and so a
    # town has first pick of the map's central area before the single
    # biome_structure fallback below claims it.
    town_buildings = _place_town(game_map, chunk_coord, biome)
    flavor["has_town"] = bool(town_buildings)

    structure_names = {"Witch Hut", "Watchtower", "Shrine", "Cabin", "Tavern", "Shop", "House"}
    has_any_structure = any(
        tile is not None and getattr(tile, "name", "") in structure_names
        for row in game_map.tiles for tile in row
    )
    if not has_any_structure:
        biome_structure = {
            ChunkBiome.SWAMP: "witch_hut",
            ChunkBiome.MOUNTAINS: "watch_tower",
            ChunkBiome.FOREST: "small_cabin",
            ChunkBiome.PLAINS: "small_cabin",
        }.get(biome, "shrine")
        anchor_x = width // 2 + (chunk_coord[0] % 3) - 1
        anchor_y = height // 2 + (chunk_coord[1] % 3) - 1
        place_structure_at_anchor(game_map, biome_structure, anchor_x, anchor_y)

    return {
        "heightmap": heightmap,
        "flow_field": flow_field,
        "moisture": moisture,
        "water_tiles": river_tiles,
        "dungeon_entrances": dungeon_entrances,
        "road_tiles": road_tiles,
        "region_map": region_map,
        "regions": regions,
        "landmarks": dungeon_entrances,
        "terrain_landmarks": landmarks,
        "infrastructure": road_tiles,
        "population": population,
        "flavor": flavor,
        "town_buildings": town_buildings,
    }


def generate_overworld(game_map, chunk_coord, world_seed, biome, world_map=None, num_dungeon_entrances=None, debug_heightmap_path=None):
    """
    Generate a new overworld map, filling in the game_map.tiles array with
    terrain tiles, and returning a dictionary of metadata about the generated
    world.

    This now delegates to generate_chunk_context() so the generation pipeline
    is organized into explicit stages while preserving the existing game
    behavior and return values.
    """
    context = generate_chunk_context(
        game_map,
        chunk_coord,
        world_seed,
        biome=biome,
        world_map=world_map,
        num_dungeon_entrances=num_dungeon_entrances,
        debug_heightmap_path=debug_heightmap_path,
    )

    return {
        "heightmap": context["heightmap"],
        "flow_field": context["flow_field"],
        "moisture": context["moisture"],
        "water_tiles": context["water_tiles"],
        "dungeon_entrances": context["dungeon_entrances"],
        "road_tiles": context["road_tiles"],
        "region_map": context["region_map"],
        "regions": context["regions"],
        "landmarks": context["landmarks"],
        "infrastructure": context["infrastructure"],
        "population": context["population"],
        "flavor": context["flavor"],
        "town_buildings": context["town_buildings"],
    }