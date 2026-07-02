import random
from world.tile import grass, tall_grass, tree, dungeon_entrance
from world.water_features import river, lake, is_water_tile


# ---------------------------------------------------------------------------
# Cellular automata terrain generation
#
# Same broad idea as the room/tunnel carving in dungeon_generator.py, but
# instead of hand-placed rectangles we grow organic terrain by repeatedly
# smoothing a random noise grid. `True` in these grids means "solid"
# (a tree, for our purposes) and `False` means "open" (walkable grass).
# ---------------------------------------------------------------------------

def _seed_noise(width, height, fill_prob):
    """Return a boolean grid seeded with random noise at the given fill probability."""
    return [[random.random() < fill_prob for _ in range(width)] for _ in range(height)]


def _count_solid_neighbors(grid, x, y, width, height):
    """Count solid cells in the 8 tiles surrounding (x, y). Out-of-bounds counts as solid
    so that forests naturally thicken toward the edge of the map instead of fraying out."""
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


def _run_cellular_automata(width, height, fill_prob, iterations, birth_limit=4, death_limit=3):
    """Seed a noise grid and smooth it repeatedly to produce organic terrain clusters."""
    grid = _seed_noise(width, height, fill_prob)
    for _ in range(iterations):
        grid = _smooth(grid, width, height, birth_limit, death_limit)
    return grid


# ---------------------------------------------------------------------------
# Water features
#
# world/water_features.py was written with dungeons in mind (it replaces
# `floor`/`wall` tiles), so we don't reuse its generation functions directly.
# Instead we borrow its river/lake tile templates and drop them onto open
# ground the same way, so both dungeons and the overworld render water the
# same way (and is_water_tile() keeps working everywhere).
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


def _generate_overworld_lake(game_map, center_x, center_y):
    """Grow an irregular lake around a chosen center point, mirroring _generate_lake()
    from water_features.py but operating on open overworld ground instead of floor/wall."""
    lake_tiles = []
    width, height = game_map.width, game_map.height

    width_radius = random.randint(4, 9)
    height_radius = random.randint(4, 8)

    for y in range(center_y - height_radius - 2, center_y + height_radius + 3):
        for x in range(center_x - width_radius - 2, center_x + width_radius + 3):
            if not (0 <= x < width and 0 <= y < height):
                continue
            dx = x - center_x
            dy = y - center_y
            noise = random.uniform(-0.6, 0.3)
            distance_squared = (dx ** 2) / (width_radius ** 2) + (dy ** 2) / (height_radius ** 2) + noise
            if distance_squared <= 1.0:
                game_map.tiles[y][x] = lake
                lake_tiles.append((x, y))

    return lake_tiles


def _place_water_features(game_map, water_feature_chance, max_features=None):
    """Scatter rivers/lakes across the overworld map.

    max_features defaults to a count scaled off map area (roughly one feature
    per 12,000 tiles, minimum 2) so a bigger overworld doesn't end up looking
    sparser than a small one — pass an explicit number to override this.
    """
    water_tiles = []
    width, height = game_map.width, game_map.height

    if max_features is None:
        max_features = max(2, (width * height) // 12000)

    for _ in range(max_features):
        if random.random() > water_feature_chance:
            continue
        if random.random() < 0.5:
            water_tiles.extend(_generate_overworld_river(game_map))
        else:
            cx = random.randint(width // 4, (width * 3) // 4)
            cy = random.randint(height // 4, (height * 3) // 4)
            water_tiles.extend(_generate_overworld_lake(game_map, cx, cy))

    return water_tiles


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
    return tile is grass  # keep entrances off tall grass/tree tiles for visibility


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
# Entry point
# ---------------------------------------------------------------------------

def generate_overworld(game_map, num_dungeon_entrances=None, water_feature_chance=0.8,
                        tree_fill_prob=0.45, tree_iterations=5):
    """
    Populate game_map with an overworld: open ground dotted with cellular-automata
    forest clusters, a handful of water features, and dungeon entrances scattered
    across it.

    num_dungeon_entrances defaults to a count scaled off map area (roughly one
    entrance per 6,000 tiles, minimum 5) — pass an explicit number to override this.

    Returns a dict describing what was placed, so game.py can wire up things like
    "walking onto a dungeon_entrance tile starts generate_dungeon()".
    """
    width, height = game_map.width, game_map.height

    if num_dungeon_entrances is None:
        num_dungeon_entrances = max(5, (width * height) // 6000)

    # 1. Base ground layer — everything starts as walkable grass.
    for y in range(height):
        for x in range(width):
            game_map.tiles[y][x] = grass

    # 2. Cellular automata pass for tree clusters/forests.
    tree_grid = _run_cellular_automata(width, height, fill_prob=tree_fill_prob,
                                        iterations=tree_iterations)
    for y in range(height):
        for x in range(width):
            if tree_grid[y][x]:
                game_map.tiles[y][x] = tree
            elif random.random() < 0.08:
                # Scatter some tall grass through the open areas for visual variety.
                game_map.tiles[y][x] = tall_grass

    # 3. Water features — rivers and lakes carved into the open ground.
    water_tiles = _place_water_features(game_map, water_feature_chance)

    # 4. Dungeon entrances, spaced apart so they don't cluster.
    dungeon_entrances = _place_dungeon_entrances(game_map, num_dungeon_entrances)

    # Future hooks: towns, roads, and other points of interest get layered in
    # here the same way dungeon entrances are — pick valid spots, place tiles,
    # record their positions for game.py to react to.

    return {
        "water_tiles": water_tiles,
        "dungeon_entrances": dungeon_entrances,
    }