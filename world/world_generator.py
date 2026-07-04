import math
import heapq
import random
from core.game import ChunkBiome
from world.tile import grass, tall_grass, tree, dungeon_entrance, road, ground, mountain
from world.water_features import river, lake, is_water_tile



DEEP_WATER = 0.28
SHALLOW_WATER = 0.34
PLAINS = 0.60
HILLS = 0.78

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

}


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

def _build_permutation_table():
    """A shuffled 0-255 permutation table, doubled so lookups never need to wrap."""
    perm = list(range(256))
    random.shuffle(perm)
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


def _generate_heightmap(width, height, scale, octaves=5, persistence=0.5, lacunarity=2.0,):
    """
    Generates a normalized heightmap.
    Values range from 0.0 to 1.0.
    """
    perm = _build_permutation_table()
    heightmap = HeightMap(width, height)

    for y in range(height):
        for x in range(width):
            value = _fractal_noise(
                perm,
                x / scale,
                y / scale,
                octaves,
                persistence,
                lacunarity,
            )

            # convert from [-1,1] -> [0,1]
            value = (value + 1.0) / 2.0

            heightmap.set(x, y, value)

    return heightmap


def _generate_moisture_map(width, height, scale, octaves=4, persistence=0.5, lacunarity=2.0,):
    """
    Generates a normalized moisture map.
    Values range from 0.0 to 1.0.
    """
    perm = _build_permutation_table()
    moisture = HeightMap(width, height)

    for y in range(height):
        for x in range(width):
            value = _fractal_noise(
                perm,
                x / scale,
                y / scale,
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
# The noise+CA pass above handles broad lakes/seas; rivers are a separate,
# more linear feature so we keep the original meandering random-walk
# generator for them rather than trying to coax noise into thin lines.
# world/water_features.py was written with dungeons in mind (it replaces
# `floor`/`wall` tiles), so we don't reuse its generation functions directly
# — we borrow its river tile template and drop it onto open ground the same
# way, so both dungeons and the overworld render water the same way (and
# is_water_tile() keeps working everywhere).
# ---------------------------------------------------------------------------

def _find_river_sources(heightmap, count):
    """
    Choose random high-elevation tiles as river sources.
    """
    candidates = []

    for y in range(heightmap.height):
        for x in range(heightmap.width):
            if heightmap.get(x, y) >= HILLS:
                candidates.append((x, y))
    random.shuffle(candidates)

    return candidates[:count]


def _neighbors(x, y, width, height):
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx = x + dx
            ny = y + dy

            if 0 <= nx < width and 0 <= ny < height:
                yield nx, ny


def _lowest_neighbor(heightmap, x, y):
    current = heightmap.get(x, y)
    best = None
    best_height = current

    for nx, ny in _neighbors(x, y, heightmap.width, heightmap.height):
        h = heightmap.get(nx, ny)
        if h < best_height:
            best_height = h
            best = (nx, ny)

    return best                

def _generate_overworld_river(game_map, heightmap, source, min_length=20):
    x, y = source
    river_tiles = []
    visited = set()

    while True:
        if (x, y) in visited:
            break
        visited.add((x, y))
        river_tiles.append((x, y))
        game_map.tiles[y][x] = river

        # reached ocean/lake
        if heightmap.get(x, y) < SHALLOW_WATER:
            break

        nxt = _lowest_neighbor(heightmap, x, y)
        if nxt is None:
            break
        x, y = nxt

    if len(river_tiles) < min_length:
        return []

    return river_tiles

def _place_rivers(game_map, heightmap, river_count):
    river_tiles = []
    sources = _find_river_sources(heightmap, river_count)

    for source in sources:
        river_tiles.extend(
            _generate_overworld_river(
                game_map,
                heightmap,
                source
            )
        )

    return river_tiles


# ---------------------------------------------------------------------------
# Dungeon entrances
#
# For now these are the only "points of interest" the world generator drops
# onto the map. Towns, camps, and other structures can be added the same
# way later — pick valid open tiles, keep them spaced apart, mark them.
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
# Roads
#
# A handful of roads wander out from dungeon entrances toward the nearest
# map edge, using the same "mostly straight, occasionally nudged" walk as
# _generate_overworld_river. They're a visual and navigational cue that the
# world keeps going past the border — walking off the edge of the map is
# what actually generates/loads the next chunk over (see game.py).
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


def _nearest_edge_direction(x, y, width, height):
    """Return the cardinal direction ('N', 'S', 'E', or 'W') of the closest map edge."""
    distance_to_edge = {
        'N': y,
        'S': (height - 1) - y,
        'W': x,
        'E': (width - 1) - x,
    }
    return min(distance_to_edge, key=distance_to_edge.get)


def _generate_road(game_map, heightmap, start):
    goal = _nearest_edge_tile(
        start[0],
        start[1],
        game_map.width,
        game_map.height
    )

    path = _find_path(game_map, heightmap, start, goal)
    road_tiles = []
    for x, y in path:
        if not is_water_tile(game_map.tiles[y][x]):
            if game_map.tiles[y][x] is not dungeon_entrance:
                game_map.tiles[y][x] = road
            road_tiles.append((x, y))

    return road_tiles


def _place_roads(game_map, heightmap, entrances):
    roads = []
    for entrance in entrances:
        roads.extend(
            _generate_road(
                game_map,
                heightmap,
                entrance
            )
        )
    return roads


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_overworld(game_map, biome, num_dungeon_entrances=None):
    """
    Generate a new overworld map, filling in the game_map.tiles array with
    terrain tiles, and returning a dictionary of metadata about the generated
    world.
    """
    width, height = game_map.width, game_map.height

    if num_dungeon_entrances is None:
        num_dungeon_entrances = max(4, (width * height) // 6000) 

    # 1 & 2. Noise-driven land/water and forest masks, cleaned up by cellular automata.
    heightmap = _generate_heightmap(
        width,
        height,
        scale=max(width, height) / 6,
    )

    moisture = _generate_moisture_map(
        width,
        height,
        scale=max(width, height) / 10
    )    
    
    region_map, regions = _generate_regions(
        game_map,
        heightmap,
        moisture
    )    

    settings = BIOME_SETTINGS[biome]

    forest_chance = settings["forest_chance"]
    grass_chance = settings["grass_chance"]
    height_offset = settings["height_offset"]    

    # 3. Paint the base terrain from those masks — water takes priority over trees
    #    (a tree can't grow in the middle of a lake), everything else is open ground.

    for y in range(height):
        for x in range(width):
            elevation = min(
                1.0,
                max(
                    0.0,
                    heightmap.get(x, y) + height_offset
                )
            )

            # moisture_value = moisture.get(x, y) * moisture_scale
            biome = _biome(
                elevation,
                moisture.get(x, y)
            )

            if biome == BIOME_OCEAN:
                game_map.tiles[y][x] = lake
            elif biome == BIOME_BEACH:
                game_map.tiles[y][x] = ground
            elif biome == BIOME_MOUNTAINS:
                game_map.tiles[y][x] = mountain   # you'll need a mountain tile
            elif biome == BIOME_HILLS:
                if moisture.get(x, y) > 0.55:
                    game_map.tiles[y][x] = tree
                else:
                    game_map.tiles[y][x] = ground
            elif biome == BIOME_FOREST:
            
                if random.random() < forest_chance:
                    game_map.tiles[y][x] = tree
                else:
                    game_map.tiles[y][x] = ground
            elif biome == BIOME_SWAMP:
            
                if random.random() < grass_chance:
                    game_map.tiles[y][x] = tall_grass
                else:
                    game_map.tiles[y][x] = ground
            else:
                if random.random() < 0.08:
                    game_map.tiles[y][x] = tall_grass
                else:
                    game_map.tiles[y][x] = ground


    # 4. Rivers — meandering, carved on top of the noise-generated terrain.
    river_count = max(1, (width * height) // 25000)

    river_tiles = _place_rivers(
        game_map,
        heightmap,
        river_count
    )

    # 5. Dungeon entrances, spaced apart so they don't cluster.
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

    # 6. Roads leading out from some dungeon entrances toward the map edge —
    #    a visual hint (and future route) toward whatever lies past the border.
    road_tiles = _place_roads(
        game_map,
        heightmap,
        dungeon_entrances
    )

    # Future hooks: towns and other points of interest get layered in here the
    # same way dungeon entrances and roads are — pick valid spots, place tiles,
    # record their positions for game.py to react to.

    return {
        "heightmap": heightmap,
        "moisture": moisture,
        "water_tiles": river_tiles,
        "dungeon_entrances": dungeon_entrances,
        "road_tiles": road_tiles,
        "region_map": region_map,
        "regions": regions,        
    }