import math
import random
from world.tile import grass, tall_grass, tree, dungeon_entrance, road, ground
from world.water_features import river, lake, is_water_tile


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


def _generate_noise_mask(width, height, scale, threshold, octaves=4, persistence=0.5, lacunarity=2.0):
    """
    Sample fractal Perlin noise across the whole map and threshold it into a
    boolean grid. `scale` controls feature size (bigger = larger, smoother
    blobs — use this for continents/lakes vs. forest patches), `threshold`
    controls roughly how much of the map ends up True.
    """
    perm = _build_permutation_table()
    return [
        [
            _fractal_noise(perm, x / scale, y / scale, octaves, persistence, lacunarity) < threshold
            for x in range(width)
        ]
        for y in range(height)
    ]


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


def _generate_landmass_and_forest_masks(width, height, water_threshold=-0.18, tree_threshold=0.0,
                                         water_iterations=4, tree_iterations=4):
    """
    Build the two terrain masks the overworld is made of:
      - water_mask: low-frequency noise -> a handful of large lakes/seas
      - tree_mask:  higher-frequency noise -> smaller, more numerous forest patches
    Both start as thresholded Perlin noise, then get smoothed by cellular
    automata so their edges read as coastlines/tree lines instead of static.
    """
    # Low-frequency noise (large scale divisor) -> big, smooth landmasses.
    water_scale = max(width, height) / 6
    water_mask = _generate_noise_mask(width, height, scale=water_scale, threshold=water_threshold)
    water_mask = _smooth_mask(water_mask, width, height, water_iterations)

    # Higher-frequency noise (small scale divisor) -> tighter forest clusters.
    tree_scale = max(width, height) / 14
    tree_mask = _generate_noise_mask(width, height, scale=tree_scale, threshold=tree_threshold)
    tree_mask = _smooth_mask(tree_mask, width, height, tree_iterations)

    return water_mask, tree_mask


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

def _generate_overworld_river(game_map, min_length=25):
    """Carve a wandering river across the map using a simple random walk."""
    river_tiles = []
    width, height = game_map.width, game_map.height

    # Start somewhere along one edge and generally walk toward the opposite edge.
    if random.random() < 0.5:
        x, y = random.randint(0, width - 1), 0
        dir_y = 1
    else:
        x, y = 0, random.randint(0, height - 1)
        dir_y = 0

    steps = 0
    max_steps = width + height  # generous upper bound so the walk always terminates
    while 0 <= x < width and 0 <= y < height and steps < max_steps:
        game_map.tiles[y][x] = river
        river_tiles.append((x, y))

        # Give the river some width so it doesn't read as a single-tile scratch.
        for wx, wy in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
            if 0 <= wx < width and 0 <= wy < height and random.random() < 0.3:
                game_map.tiles[wy][wx] = river
                river_tiles.append((wx, wy))

        # Wander toward the far edge with some horizontal drift.
        if dir_y:
            y += 1
            x += random.choice([-1, 0, 0, 1])
        else:
            x += 1
            y += random.choice([-1, 0, 0, 1])
        steps += 1

    if len(river_tiles) < min_length:
        return []  # too short to bother keeping — caller can retry
    return river_tiles


def _place_rivers(game_map, river_chance, max_rivers=None):
    """Scatter a few meandering rivers across the overworld map, on top of the
    noise-generated lakes/seas.

    max_rivers defaults to a count scaled off map area (roughly one river per
    24,000 tiles, minimum 1) — pass an explicit number to override this.
    """
    river_tiles = []
    width, height = game_map.width, game_map.height

    if max_rivers is None:
        max_rivers = max(1, (width * height) // 24000)

    for _ in range(max_rivers):
        if random.random() < river_chance:
            river_tiles.extend(_generate_overworld_river(game_map))

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


def _place_dungeon_entrances(game_map, num_entrances, min_spacing=15):
    """Scatter dungeon entrances across open ground, rejecting spots too close to
    an entrance already placed so they don't cluster together."""
    width, height = game_map.width, game_map.height
    placed = []

    attempts = num_entrances * 40  # generous retry budget for a sparse map
    for _ in range(attempts):
        if len(placed) >= num_entrances:
            break

        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        if not _is_valid_entrance_spot(game_map, x, y):
            continue

        too_close = any(
            abs(x - px) + abs(y - py) < min_spacing
            for px, py in placed
        )
        if too_close:
            continue

        game_map.tiles[y][x] = dungeon_entrance
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

def _nearest_edge_direction(x, y, width, height):
    """Return the cardinal direction ('N', 'S', 'E', or 'W') of the closest map edge."""
    distance_to_edge = {
        'N': y,
        'S': (height - 1) - y,
        'W': x,
        'E': (width - 1) - x,
    }
    return min(distance_to_edge, key=distance_to_edge.get)


def _generate_road(game_map, start_x, start_y, min_length=10):
    """Carve a single wandering road from (start_x, start_y) out toward the nearest
    map edge. Shaped like _generate_overworld_river's walk, but aimed at whichever
    edge is closest and left running until it actually reaches the border rather
    than stopping after a fixed number of steps."""
    width, height = game_map.width, game_map.height
    road_tiles = []

    direction = _nearest_edge_direction(start_x, start_y, width, height)
    dx, dy = {'N': (0, -1), 'S': (0, 1), 'E': (1, 0), 'W': (-1, 0)}[direction]

    # Step away from the entrance first so the road doesn't overwrite it.
    x, y = start_x + dx, start_y + dy

    steps = 0
    max_steps = width + height  # generous upper bound so the walk always terminates
    while 0 <= x < width and 0 <= y < height and steps < max_steps:
        if not is_water_tile(game_map.tiles[y][x]):
            game_map.tiles[y][x] = road
            road_tiles.append((x, y))

        # Mostly follow the chosen direction, with occasional sideways drift —
        # same feel as the river's wander, just aimed at an edge instead of a room.
        if dx:
            x += dx
            y += random.choice([-1, 0, 0, 1])
        else:
            y += dy
            x += random.choice([-1, 0, 0, 1])
        steps += 1

    if len(road_tiles) < min_length:
        return []  # too short to bother keeping
    return road_tiles


def _place_roads(game_map, entrance_positions, road_chance=0.8):
    """Grow a road out toward the map edge from some of the dungeon entrances."""
    road_tiles = []
    for x, y in entrance_positions:
        if random.random() < road_chance:
            road_tiles.extend(_generate_road(game_map, x, y))
    return road_tiles


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_overworld(game_map, num_dungeon_entrances=None, river_chance=0.8,
                        water_threshold=-0.12, tree_threshold=0.0):
    """
    Populate game_map with an overworld:
      1. Perlin noise lays out the base land/water layout and forest cover.
      2. Cellular automata smooths both into organic-looking coastlines/tree lines.
      3. A few meandering rivers are carved on top.
      4. Dungeon entrances are scattered across the open ground.

    num_dungeon_entrances defaults to a count scaled off map area (roughly one
    entrance per 6,000 tiles, minimum 5) — pass an explicit number to override this.

    Returns a dict describing what was placed, so game.py can wire up things like
    "walking onto a dungeon_entrance tile starts generate_dungeon()".
    """
    width, height = game_map.width, game_map.height

    if num_dungeon_entrances is None:
        num_dungeon_entrances = max(5, (width * height) // 6000)

    # 1 & 2. Noise-driven land/water and forest masks, cleaned up by cellular automata.
    water_mask, tree_mask = _generate_landmass_and_forest_masks(
        width, height, water_threshold=water_threshold, tree_threshold=tree_threshold
    )

    # 3. Paint the base terrain from those masks — water takes priority over trees
    #    (a tree can't grow in the middle of a lake), everything else is open ground.
    for y in range(height):
        for x in range(width):
            if water_mask[y][x]:
                game_map.tiles[y][x] = lake
            elif tree_mask[y][x]:
                game_map.tiles[y][x] = tree
            elif random.random() < 0.08:
                # Scatter some tall grass through the open areas for visual variety.
                game_map.tiles[y][x] = tall_grass
            # elif random.random() < 0.12:
            #     # Scatter a few small grass patches for visual variety.
            #     game_map.tiles[y][x] = grass
            else:
                game_map.tiles[y][x] = ground

    # 4. Rivers — meandering, carved on top of the noise-generated terrain.
    river_tiles = _place_rivers(game_map, river_chance)

    # 5. Dungeon entrances, spaced apart so they don't cluster.
    dungeon_entrances = _place_dungeon_entrances(game_map, num_dungeon_entrances)

    # 6. Roads leading out from some dungeon entrances toward the map edge —
    #    a visual hint (and future route) toward whatever lies past the border.
    road_tiles = _place_roads(game_map, dungeon_entrances)

    # Future hooks: towns and other points of interest get layered in here the
    # same way dungeon entrances and roads are — pick valid spots, place tiles,
    # record their positions for game.py to react to.

    return {
        "water_tiles": river_tiles,
        "dungeon_entrances": dungeon_entrances,
        "road_tiles": road_tiles,
    }