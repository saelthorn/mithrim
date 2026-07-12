"""
World-scale map: a coarse, persistent grid laid over the *entire* game
world, one cell per overworld chunk.

Each individual chunk (world_generator.generate_overworld) is still
generated on demand, the first time the player steps into it, using its
own fine-grained Perlin noise. What was missing is any notion of the
world beyond a single chunk: biomes were chosen chunk-by-chunk with a
random walk (see BIOME_CONNECTIONS in game.py) and rivers never made it
past the edge of the chunk they started in.

WorldMap fixes that by generating one coarse heightmap/moisture map/biome
grid up front, sized WORLD_MAP_WIDTH x WORLD_MAP_HEIGHT chunks, along with
a handful of major rivers that flow across many chunks. Individual chunk
generation then consults this map for:
  - its biome (WorldMap.biome_at), replacing the old neighbor-based walk
  - a coarse elevation bias (WorldMap.elevation_at), so mountain ranges
    and lowlands span multiple chunks instead of resetting every chunk
  - which of its edges a major river enters/exits on (WorldMap.river_edges_at),
    so a river that crosses a chunk boundary lines up on both sides
"""
import random
from collections import deque

from world.world_generator import (
    ChunkBiome,
    HeightMap,
    _build_permutation_table,
    _fractal_noise,
    _biome as _elevation_moisture_biome,
    BIOME_OCEAN,
    BIOME_BEACH,
    BIOME_PLAINS,
    BIOME_FOREST,
    BIOME_SWAMP,
    BIOME_HILLS,
    BIOME_MOUNTAINS,
    DEEP_WATER,
)

# The world map is a fixed-size grid of chunk-sized cells. Chunk coordinates
# in game.py are unbounded and can go negative (the player can walk in any
# direction from the starting chunk), so WorldMap wraps them onto this grid
# rather than requiring the world to have a hard edge.
WORLD_MAP_WIDTH = 140
WORLD_MAP_HEIGHT = 100

# Chunk (0, 0) — where the player starts — maps to the center of the grid,
# so there's roughly as much generated world in every direction.
_WORLD_MAP_ORIGIN_X = WORLD_MAP_WIDTH // 2
_WORLD_MAP_ORIGIN_Y = WORLD_MAP_HEIGHT // 2

# Tile dimensions of a single overworld chunk's own GameMap (see game.py's
# GameMap(OVERWORLD_CHUNK_WIDTH, OVERWORLD_CHUNK_HEIGHT)). Distinct from
# WORLD_MAP_WIDTH/HEIGHT above, which is the size of the coarse *chunk*
# grid, not the tile grid inside one chunk -- the two happen to share
# values right now but measure different things (chunks vs. tiles-per-
# chunk) and are free to diverge. Defined here, not in game.py, so this
# module can also own the chunk-local <-> global tile conversion below;
# game.py imports these rather than keeping its own copy.
OVERWORLD_CHUNK_WIDTH = 140
OVERWORLD_CHUNK_HEIGHT = 100

# The fine-grained _biome() thresholds classify individual tiles; at world
# scale we only need one ChunkBiome per cell, so ocean/beach collapse onto
# their nearest land biome (a chunk is generated with local water regardless
# of ChunkBiome, so this only affects flavor, not walkability).
_WORLD_BIOME_TO_CHUNK_BIOME = {
    BIOME_OCEAN: ChunkBiome.SWAMP,
    BIOME_BEACH: ChunkBiome.PLAINS,
    BIOME_PLAINS: ChunkBiome.PLAINS,
    BIOME_FOREST: ChunkBiome.FOREST,
    BIOME_SWAMP: ChunkBiome.SWAMP,
    BIOME_HILLS: ChunkBiome.HILLS,
    BIOME_MOUNTAINS: ChunkBiome.MOUNTAINS,
}

# Four-neighbor directions used when walking rivers across chunks, and their
# opposites — used to record which edge of a chunk a river enters/exits on.
_DIRECTION_OFFSETS = {
    "N": (0, -1),
    "S": (0, 1),
    "W": (-1, 0),
    "E": (1, 0),
}
_OPPOSITE_DIRECTION = {"N": "S", "S": "N", "W": "E", "E": "W"}


class WorldMap:
    """
    Coarse, persistent, world-scale terrain data: one elevation/moisture/
    biome value per chunk, plus which chunks carry a major river and which
    of their edges it crosses. Generated once per game (see
    generate_world_map) and consulted by world_generator.generate_overworld
    whenever a chunk is generated.
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.elevation = HeightMap(width, height)
        self.moisture = HeightMap(width, height)
        self.biomes = {}       # (grid_x, grid_y) -> ChunkBiome
        self.river_edges = {}  # (grid_x, grid_y) -> set of "N"/"S"/"E"/"W"
        self.region_names = {} # (grid_x, grid_y) -> coarse region label
        self.flavor = {}       # (grid_x, grid_y) -> dict of stage metadata
        self.region_ids = {}    # (grid_x, grid_y) -> region id
        self.region_graph = {}  # region id -> set of neighboring region ids

    def _to_grid(self, chunk_coord):
        """Wrap an unbounded (chunk_x, chunk_y) onto this fixed-size grid."""
        chunk_x, chunk_y = chunk_coord
        grid_x = (chunk_x + _WORLD_MAP_ORIGIN_X) % self.width
        grid_y = (chunk_y + _WORLD_MAP_ORIGIN_Y) % self.height
        return grid_x, grid_y

    def elevation_at(self, chunk_coord):
        grid_x, grid_y = self._to_grid(chunk_coord)
        return self.elevation.get(grid_x, grid_y)

    def moisture_at(self, chunk_coord):
        grid_x, grid_y = self._to_grid(chunk_coord)
        return self.moisture.get(grid_x, grid_y)

    def biome_at(self, chunk_coord):
        return self.biomes[self._to_grid(chunk_coord)]

    def river_edges_at(self, chunk_coord):
        """Which edges ('N'/'S'/'E'/'W') of this chunk a major river crosses,
        as an empty set if no major river passes through it."""
        return self.river_edges.get(self._to_grid(chunk_coord), set())

    def region_name_at(self, chunk_coord):
        """Return the coarse region label for a chunk, if one has been assigned."""
        return self.region_names.get(self._to_grid(chunk_coord))

    def set_region_name(self, chunk_coord, name):
        self.region_names[self._to_grid(chunk_coord)] = name

    def flavor_at(self, chunk_coord):
        return self.flavor.get(self._to_grid(chunk_coord), {})

    def set_flavor(self, chunk_coord, metadata):
        self.flavor[self._to_grid(chunk_coord)] = metadata

    def region_at(self, chunk_coord):
        return self.region_ids.get(self._to_grid(chunk_coord))

    def set_region(self, chunk_coord, region_id):
        self.region_ids[self._to_grid(chunk_coord)] = region_id

    def region_transitions_at(self, chunk_coord):
        region_id = self.region_at(chunk_coord)
        return self.region_graph.get(region_id, set())


def chunk_local_to_world_position(chunk_coord, local_position):
    """
    Convert a chunk-local tile position into a single stable global tile
    coordinate for the whole unbounded overworld.

    game.py's `self.player.x`/`self.player.y` are local to whichever
    chunk the player is currently standing in -- both reset to a small
    range (0..OVERWORLD_CHUNK_WIDTH/HEIGHT) every time the player crosses
    a chunk boundary via `self.overworld_chunk_coord`. That's fine for
    rendering and collision within a chunk, but it is *not* directly
    comparable to any coordinate meant to describe "a place in the
    world" -- e.g. a story's `requirements.location` in
    story_content_loader.py/story_queue_manager.py's
    ActivationRequirement, which is written in global terms (a shrine at
    (340, 210) several chunks from the start, not "(340, 210) within
    whichever chunk you happen to be in").

    This is the one place that conversion happens, so every caller
    (story_integration.py's StorySystems._player_position(), or anything
    else that needs to compare a chunk-local position against
    world-scale content) gets the same answer.
    """
    chunk_x, chunk_y = chunk_coord
    local_x, local_y = local_position
    world_x = chunk_x * OVERWORLD_CHUNK_WIDTH + local_x
    world_y = chunk_y * OVERWORLD_CHUNK_HEIGHT + local_y
    return (world_x, world_y)


def _normalize_elevation_range(world_map):
    """
    Rescale world_map.elevation in place so its actual minimum and maximum
    land exactly on 0.0 and 1.0, instead of the compressed band the raw
    fBm noise tends to occupy. This is a plain linear stretch — relative
    shape of the terrain (where the peaks and valleys are) is unchanged,
    only how far those peaks and valleys sit from the middle of the range.
    """
    width, height = world_map.width, world_map.height
    values = [world_map.elevation.get(x, y) for y in range(height) for x in range(width)]
    lowest, highest = min(values), max(values)

    elevation_range = highest - lowest
    if elevation_range == 0:
        return  # perfectly flat noise (shouldn't happen); nothing to stretch

    for y in range(height):
        for x in range(width):
            raw = world_map.elevation.get(x, y)
            world_map.elevation.set(x, y, (raw - lowest) / elevation_range)


def _biomes_are_adjacent(a, b):
    if a is None or b is None:
        return True
    adjacency = {
        ChunkBiome.FOREST: {ChunkBiome.FOREST, ChunkBiome.PLAINS, ChunkBiome.HILLS, ChunkBiome.SWAMP, ChunkBiome.MOUNTAINS},
        ChunkBiome.PLAINS: {ChunkBiome.PLAINS, ChunkBiome.FOREST, ChunkBiome.HILLS, ChunkBiome.SWAMP},
        ChunkBiome.SWAMP: {ChunkBiome.SWAMP, ChunkBiome.FOREST, ChunkBiome.PLAINS},
        ChunkBiome.HILLS: {ChunkBiome.HILLS, ChunkBiome.PLAINS, ChunkBiome.FOREST, ChunkBiome.MOUNTAINS},
        ChunkBiome.MOUNTAINS: {ChunkBiome.MOUNTAINS, ChunkBiome.HILLS},
    }
    return b in adjacency.get(a, set()) or a in adjacency.get(b, set())


def _generate_world_regions(world_map, num_regions=None, min_region_size=4, max_region_size=14):
    """Generate a coarse region graph for the world map using seeded growth and biome adjacency rules."""
    width, height = world_map.width, world_map.height
    if num_regions is None:
        num_regions = max(6, (width * height) // 250)

    region_grid = [[None for _ in range(width)] for _ in range(height)]
    region_seeds = {}
    region_labels = []

    for region_id in range(1, num_regions + 1):
        seed_x = random.randrange(width)
        seed_y = random.randrange(height)
        if region_grid[seed_y][seed_x] is not None:
            continue

        biome = world_map.biomes[(seed_x, seed_y)]
        region_name = _region_name_for_biome(biome)
        region_label = f"{region_name}-{region_id}"
        queue = deque([(seed_x, seed_y)])
        region_grid[seed_y][seed_x] = region_label
        region_seeds[region_label] = (seed_x, seed_y)
        region_labels.append(region_label)

        size = 0
        while queue and size < max_region_size:
            cx, cy = queue.popleft()
            size += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                if region_grid[ny][nx] is not None:
                    continue

                neighbor_biome = world_map.biomes[(nx, ny)]
                if not _biomes_are_adjacent(biome, neighbor_biome):
                    continue

                if size < min_region_size or random.random() < 0.75:
                    region_grid[ny][nx] = region_label
                    queue.append((nx, ny))

    for y in range(height):
        for x in range(width):
            if region_grid[y][x] is None:
                label = min(
                    region_labels,
                    key=lambda current_label: abs(x - region_seeds[current_label][0]) + abs(y - region_seeds[current_label][1]),
                )
                region_grid[y][x] = label

    for y in range(height):
        for x in range(width):
            label = region_grid[y][x]
            world_map.set_region((x, y), label)
            region_name = label.split("-", 1)[0]
            world_map.set_region_name((x, y), region_name)

    world_map.region_graph = {label: set() for label in region_labels}
    for y in range(height):
        for x in range(width):
            region_label = world_map.region_at((x, y))
            if region_label is None:
                continue
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                neighbor_region = world_map.region_at((nx, ny))
                if neighbor_region and neighbor_region != region_label:
                    world_map.region_graph.setdefault(region_label, set()).add(neighbor_region)
                    world_map.region_graph.setdefault(neighbor_region, set()).add(region_label)

    return world_map


def _region_name_for_biome(biome):
    if biome is None:
        return "Wilds"
    return {
        ChunkBiome.FOREST: "Forest",
        ChunkBiome.PLAINS: "Plains",
        ChunkBiome.SWAMP: "Swamp",
        ChunkBiome.HILLS: "Highlands",
        ChunkBiome.MOUNTAINS: "Mountains",
    }.get(biome, "Wilds")


def _generate_world_rivers(world_map, num_rivers, min_spacing=5):
    """
    Trace `num_rivers` major rivers across the world grid: start from a
    high-elevation cell and walk to whichever unvisited neighbor is lowest,
    same steepest-descent idea as the per-chunk flow field in
    world_generator, just at chunk granularity and without the meander —
    a river spanning dozens of chunks doesn't need to wobble tile-by-tile
    to look natural. Each step records which edge of the source cell and
    entry edge of the destination cell the river crosses.
    """
    width, height = world_map.width, world_map.height

    highest_first = sorted(
        ((world_map.elevation.get(x, y), x, y) for y in range(height) for x in range(width)),
        reverse=True,
    )

    sources = []
    for _, x, y in highest_first:
        if len(sources) >= num_rivers:
            break
        if any(abs(x - sx) + abs(y - sy) < min_spacing for sx, sy in sources):
            continue
        sources.append((x, y))

    for start_x, start_y in sources:
        path = [(start_x, start_y)]
        visited = {(start_x, start_y)}
        current_x, current_y = start_x, start_y

        for _ in range(width + height):  # generous upper bound on river length
            current_elevation = world_map.elevation.get(current_x, current_y)
            if current_elevation < DEEP_WATER:
                break  # reached the ocean

            best_neighbor = None
            best_elevation = current_elevation

            for direction, (dx, dy) in _DIRECTION_OFFSETS.items():
                nx, ny = current_x + dx, current_y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                if (nx, ny) in visited:
                    continue

                neighbor_elevation = world_map.elevation.get(nx, ny)
                if neighbor_elevation < best_elevation:
                    best_elevation = neighbor_elevation
                    best_neighbor = (direction, nx, ny)

            if best_neighbor is None:
                break  # local minimum with nowhere lower to flow — river ends here

            _, next_x, next_y = best_neighbor
            path.append((next_x, next_y))
            visited.add((next_x, next_y))
            current_x, current_y = next_x, next_y

        _record_river_path(world_map, path)


def _record_river_path(world_map, path):
    """Mark, on every cell the river passes through, which edges it crosses."""
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        exit_direction = next(
            direction
            for direction, (dx, dy) in _DIRECTION_OFFSETS.items()
            if (ax + dx, ay + dy) == (bx, by)
        )
        entry_direction = _OPPOSITE_DIRECTION[exit_direction]

        world_map.river_edges.setdefault((ax, ay), set()).add(exit_direction)
        world_map.river_edges.setdefault((bx, by), set()).add(entry_direction)


def generate_world_map(world_seed, width=WORLD_MAP_WIDTH, height=WORLD_MAP_HEIGHT, num_rivers=None, num_regions=None, min_region_size=4, max_region_size=14):
    """
    Generate the coarse, persistent world map for a game: one elevation/
    moisture/biome value per chunk, plus a handful of major rivers crossing
    many chunks. This is cheap (width * height cells, not width * height *
    chunk_size tiles) so it's generated once, up front, rather than lazily
    per chunk like the fine-grained terrain in generate_overworld.
    """
    # A different corner of the permutation table than per-chunk noise uses
    # (world_generator seeds its own permutation table from the same
    # world_seed), so the coarse world layout and the fine per-chunk detail
    # don't end up correlated with each other.
    perm = _build_permutation_table(world_seed ^ 0x5EED)

    world_map = WorldMap(width, height)
    elevation_scale = max(width, height) / 6
    moisture_scale = max(width, height) / 4

    for y in range(height):
        for x in range(width):
            elevation = (_fractal_noise(perm, x / elevation_scale, y / elevation_scale, 5, 0.5, 2.0) + 1.0) / 2.0
            world_map.elevation.set(x, y, elevation)

            # Offset the sample point for moisture so it isn't just a scaled
            # copy of the elevation noise (same trick generate_overworld uses).
            moisture = (_fractal_noise(perm, (x + 1000) / moisture_scale, (y + 1000) / moisture_scale, 4, 0.5, 2.0) + 1.0) / 2.0
            world_map.moisture.set(x, y, moisture)

    # Summing several octaves of noise (fBm) statistically pulls the result
    # toward the middle of its range — it's rare for every octave to line up
    # near an extreme at once — so the raw elevation above rarely gets
    # anywhere near 1.0. Left alone, that means it almost never clears the
    # HILLS threshold used below, and mountains (which need an even higher
    # elevation than hills) become vanishingly rare. Stretching the grid's
    # actual min/max out to fill the full 0..1 range fixes that without
    # changing the HILLS/PLAINS thresholds themselves or touching how
    # per-chunk elevation is generated.
    _normalize_elevation_range(world_map)

    for y in range(height):
        for x in range(width):
            elevation_moisture_biome = _elevation_moisture_biome(
                world_map.elevation.get(x, y),
                world_map.moisture.get(x, y),
            )
            world_map.biomes[(x, y)] = _WORLD_BIOME_TO_CHUNK_BIOME[elevation_moisture_biome]

    _generate_world_regions(
        world_map,
        num_regions=num_regions,
        min_region_size=min_region_size,
        max_region_size=max_region_size,
    )

    if num_rivers is None:
        num_rivers = max(4, (width * height) // 800)

    _generate_world_rivers(world_map, num_rivers)

    return world_map