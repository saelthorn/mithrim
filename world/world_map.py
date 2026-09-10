"""
World-scale map: a coarse, persistent grid laid over the *entire* game
world, one cell per overworld chunk.

Each individual chunk (world_generator.generate_overworld) is still
generated on demand, the first time the player steps into it, using its
own fine-grained Perlin noise. WorldMap decides what the world at large
*is*; the chunk generator decides what one chunk *looks like* given its
place in that world.

Generation is geography-first rather than biome-first:

    SEED -> CONTINENTS -> ELEVATION (+ MOUNTAIN RANGES) -> CLIMATE
          -> RIVERS -> BIOMES -> REGIONS

A handful of continent "cores" are seeded first and grown into cohesive
landmass shapes; mountain ranges are walked as ridge polylines across
those landmasses (the same ridge-polyline trick world_generator.py's own
_generate_ridge_heightmap() uses per-chunk, just at world scale) rather
than picked from raw noise, so mountains read as ranges instead of
scattered blobs. Climate (moisture) then reacts to that shape -- a
latitude band plus rain shadows cast by the mountain ranges -- before
biomes are classified off the result. Only after all of that is decided
do individual chunks get generated, each consulting this map for:
  - its biome (WorldMap.biome_at)
  - a coarse elevation bias (WorldMap.elevation_at), so mountain ranges
    and lowlands span multiple chunks instead of resetting every chunk
  - which of its edges a major river enters/exits on (WorldMap.river_edges_at)
"""
import math
import random
from collections import deque

from world.world_generator import (
    ChunkBiome,
    HeightMap,
    BiomeThresholds,
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

# -- continent shaping ------------------------------------------------------
# A continent is a Voronoi-style falloff blob around a seeded core; cells
# take the strongest falloff among all cores, so land forms as a few
# cohesive masses instead of a scatter of noise-driven islands.
CONTINENT_RADIUS_FRACTION = 0.14
# Minimum gap enforced between two continent cores, as a multiple of
# CONTINENT_RADIUS_FRACTION's radius -- without this, cores placed close
# together by chance blend into one shape far bigger than any individual
# continent should be (their falloff disks overlap almost entirely).
_CONTINENT_MIN_SPACING_FACTOR = 1.6
# How solidly "inland" (by raw continent shape, before percentile
# normalization) a cell must be to seed or continue a mountain range --
# keeps ranges off of open ocean.
MOUNTAIN_LAND_THRESHOLD = 0.40
# Half-width of a mountain range's elevation influence, as a fraction of
# the grid's larger dimension.
MOUNTAIN_BAND_FRACTION = 0.07
# How elevation's macro shape (i.e. everything but the per-cell detail
# layer) splits between continent shape and mountain-range influence.
_CONTINENT_ELEVATION_SHARE = 0.6
_MOUNTAIN_ELEVATION_SHARE = 0.4
# Continent shape is capped before it feeds elevation, at this fraction
# of its own [0, 1] range -- otherwise the smooth radial falloff toward
# a continent's own core would itself have enough spread to out-rank
# actual mountain-range influence, and every continent's interior would
# read as one giant highland instead of mostly flat land with a distinct
# range standing out on top of it. Coastlines/oceans still use the
# uncapped continent shape (see below), only the elevation contribution
# is flattened.
CONTINENT_INTERIOR_CAP = 0.4

# -- climate ------------------------------------------------------------
# How strongly a sine-wave latitude band (one full wrap per grid height,
# so it stays seamless on this toroidal map) nudges moisture wetter/drier.
LATITUDE_MOISTURE_STRENGTH = 0.35
# How strongly standing in the lee of a mountain range dries a cell out.
RAIN_SHADOW_STRENGTH = 0.6


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
        # Whether a cell classified as ocean during biome assignment --
        # ChunkBiome has no OCEAN member (ocean chunks still collapse onto
        # ChunkBiome.SWAMP for chunk generation, see _WORLD_BIOME_TO_CHUNK_BIOME),
        # so this is the only place "is this actually open water" survives.
        self.is_ocean = {}     # (grid_x, grid_y) -> bool
        # Which continent's core a cell is geographically closest to --
        # every cell gets one, however far out to sea it reads. Useful
        # for region growth and future flavor/road generation ("the sea
        # off the coast of continent 2").
        self.continent_id = {}  # (grid_x, grid_y) -> int
        # Every mountain range's spine, as the list of (x, y) points it was
        # walked through -- kept around for flavor text and future road
        # generation (routing around/through a named range).
        self.mountain_ranges = []
        # Set by generate_world_map() via compute_biome_thresholds() --
        # the actual elevation/moisture cutoffs this world's biomes were
        # classified against, kept around for debugging/introspection
        # (e.g. confirming a seed really did land ~12% ocean).
        self.biome_thresholds = None

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

    def is_ocean_at(self, chunk_coord):
        return self.is_ocean.get(self._to_grid(chunk_coord), False)

    def continent_at(self, chunk_coord):
        """Id of the continent core this chunk is geographically closest
        to, whether the chunk itself is land or open water off that
        continent's coast."""
        return self.continent_id.get(self._to_grid(chunk_coord))


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


def world_position_to_chunk_local(world_position):
    """
    Inverse of chunk_local_to_world_position(): given a global tile
    position (e.g. a story's search_area/StoryObject position, which
    story_content_loader.py places in the same global space as
    ActivationRequirement.location), return the (chunk_coord,
    local_position) pair needed to check it against whatever is
    currently rendered/adjacent in game.py -- game.entities, tile
    lookups, and adjacency checks like check_overworld_npc_interaction()
    all operate in chunk-local coordinates, not global ones.
    """
    world_x, world_y = world_position
    chunk_x, local_x = divmod(int(world_x), OVERWORLD_CHUNK_WIDTH)
    chunk_y, local_y = divmod(int(world_y), OVERWORLD_CHUNK_HEIGHT)
    return (chunk_x, chunk_y), (local_x, local_y)


def _percentile_normalize(grid):
    """
    Rescale `grid` (a HeightMap-like object) in place so its values are
    spread uniformly across [0, 1] by rank rather than by raw magnitude
    -- each cell ends up at its own percentile within the grid's actual
    distribution.

    This replaces the old approach of a plain linear min/max stretch,
    which only guaranteed the extremes touched 0.0/1.0. Summing several
    octaves of fBm noise is a Central-Limit-Theorem setup: the result
    clusters near its mean no matter how far the endpoints are
    stretched, so a threshold like "elevation >= 0.75" almost never
    fires even after stretching -- it sits deep in a tail that barely
    has any cells in it. Percentile normalization fixes that by
    construction: "the top 25% of cells by elevation" always *is* the
    top 25%, for any input distribution, which is what
    compute_biome_thresholds() below relies on. It's also what makes
    _apply_climate() below safe to leave un-clamped: shifting a value by
    a fixed amount doesn't need to stay inside [0, 1] before this re-ranks
    it, only stay correctly *ordered* relative to its neighbors.
    """
    width, height = grid.width, grid.height
    cells = [(x, y) for y in range(height) for x in range(width)]
    cells.sort(key=lambda cell: grid.get(*cell))

    denominator = max(1, len(cells) - 1)
    for rank, (x, y) in enumerate(cells):
        grid.set(x, y, rank / denominator)


def power_curve(exponent):
    """
    Shaping-curve factory: `value ** exponent`, meant to be applied
    *after* _percentile_normalize() so it's reshaping an already-uniform
    [0, 1] distribution on purpose, rather than fighting the same
    clustering _percentile_normalize() just fixed.

    exponent < 1 pulls values up (more of the map reads as high
    elevation/moisture -- a more mountainous or wetter-feeling world);
    exponent > 1 pulls values down (flatter, drier). exponent == 1.0 is
    a no-op. This is a pure art/tuning knob: it does not change biome
    *area fractions*, since compute_biome_thresholds() always measures
    percentiles off the grid's actual (possibly curved) distribution --
    it changes which specific elevation/moisture values correspond to
    those fractions, which matters anywhere the raw float is read
    directly (world_generator._bias_grid_toward_world_value(), for one).
    """
    return lambda value: value ** exponent


def smoothstep_curve(value):
    """
    Shaping-curve: classic smoothstep (3v^2 - 2v^3). Pushes mid-range
    values toward the extremes without moving 0.0/1.0 themselves,
    steepening the transition between low and high terrain (sharper
    coastlines/ridgelines, less gentle midground) — a different flavor
    of knob than power_curve(), usable the same way.
    """
    return value * value * (3.0 - 2.0 * value)


def _apply_curve(grid, curve):
    """Apply a shaping curve (a callable float -> float, e.g.
    power_curve(2.0) or smoothstep_curve) to every cell of `grid` in
    place. `curve=None` is a no-op, so callers can pass through an
    optional curve parameter without a branch of their own."""
    if curve is None:
        return
    for y in range(grid.height):
        for x in range(grid.width):
            grid.set(x, y, curve(grid.get(x, y)))


# Target area fractions each biome should occupy at world scale, chosen to
# match the *intent* of world_generator.DEFAULT_BIOME_THRESHOLDS' fixed
# cutoffs (DEEP_WATER=0.12, SHALLOW_WATER=0.18, PLAINS=0.55, HILLS=0.75,
# and the 0.50/0.72 moisture splits) -- "about 12% ocean", not "elevation
# below exactly 0.12". compute_biome_thresholds() below turns each of
# these into the actual elevation/moisture value that cutoff corresponds
# to for *this* world's generated grids, so the fraction holds regardless
# of seed or any shaping curve applied.
OCEAN_PERCENTILE = 0.12
BEACH_PERCENTILE = 0.18
HILLS_PERCENTILE = 0.55
MOUNTAINS_PERCENTILE = 0.75
FOREST_MOISTURE_PERCENTILE = 0.50
SWAMP_MOISTURE_PERCENTILE = 0.72


def _value_at_percentile(grid, percentile):
    """The actual value sitting at `percentile` (0..1) of `grid`'s
    sorted distribution -- e.g. percentile=0.75 returns the value with
    25% of cells above it, whatever that value happens to be."""
    values = sorted(grid.get(x, y) for y in range(grid.height) for x in range(grid.width))
    index = min(len(values) - 1, int(percentile * (len(values) - 1)))
    return values[index]


def compute_biome_thresholds(elevation, moisture):
    """
    Derive a world_generator.BiomeThresholds from the *actual*
    distribution of this world's elevation/moisture grids, instead of
    assuming DEFAULT_BIOME_THRESHOLDS' fixed values apply. See
    _percentile_normalize()'s docstring for why fixed values don't
    reliably work against fBm noise, even after a min/max stretch.
    """
    return BiomeThresholds(
        ocean=_value_at_percentile(elevation, OCEAN_PERCENTILE),
        beach=_value_at_percentile(elevation, BEACH_PERCENTILE),
        hills=_value_at_percentile(elevation, HILLS_PERCENTILE),
        mountains=_value_at_percentile(elevation, MOUNTAINS_PERCENTILE),
        forest_moisture=_value_at_percentile(moisture, FOREST_MOISTURE_PERCENTILE),
        swamp_moisture=_value_at_percentile(moisture, SWAMP_MOISTURE_PERCENTILE),
    )


def _biomes_are_adjacent(a, b):
    if a is None or b is None:
        return True
    adjacency = {
        ChunkBiome.FOREST: {ChunkBiome.FOREST, ChunkBiome.PLAINS, ChunkBiome.HILLS, ChunkBiome.SWAMP, ChunkBiome.MOUNTAINS},
        ChunkBiome.PLAINS: {ChunkBiome.PLAINS, ChunkBiome.FOREST, ChunkBiome.HILLS, ChunkBiome.SWAMP},
        ChunkBiome.SWAMP: {ChunkBiome.SWAMP, ChunkBiome.FOREST, ChunkBiome.PLAINS},
        ChunkBiome.HILLS: {ChunkBiome.HILLS, ChunkBiome.PLAINS, ChunkBiome.FOREST, ChunkBiome.MOUNTAINS},
        ChunkBiome.MOUNTAINS: {ChunkBiome.MOUNTAINS, ChunkBiome.HILLS, ChunkBiome.FOREST},
    }
    return b in adjacency.get(a, set()) or a in adjacency.get(b, set())


def _generate_world_regions(world_map, rng, num_regions=None, min_region_size=4, max_region_size=14):
    """
    Generate a coarse region graph for the world map using seeded growth,
    biome adjacency rules, and an ocean/land split -- a region never grows
    across that split, so "the Ashen Highlands" can no longer bleed into
    open sea just because ocean cells collapse onto ChunkBiome.SWAMP for
    chunk-generation purposes (see WorldMap.is_ocean). `rng` is a
    world-seed-derived random.Random, not the global `random` module, so
    region layout is reproducible for a given world_seed.
    """
    width, height = world_map.width, world_map.height
    if num_regions is None:
        num_regions = max(6, (width * height) // 250)

    region_grid = [[None for _ in range(width)] for _ in range(height)]
    region_seeds = {}
    region_labels = []

    for region_id in range(1, num_regions + 1):
        seed_x = rng.randrange(width)
        seed_y = rng.randrange(height)
        if region_grid[seed_y][seed_x] is not None:
            continue

        biome = world_map.biomes[(seed_x, seed_y)]
        is_ocean = world_map.is_ocean[(seed_x, seed_y)]
        region_name = _region_name_for_biome(biome, is_ocean)
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

                if world_map.is_ocean[(nx, ny)] != is_ocean:
                    continue  # never grow a region across the coastline

                neighbor_biome = world_map.biomes[(nx, ny)]
                if not _biomes_are_adjacent(biome, neighbor_biome):
                    continue

                if size < min_region_size or rng.random() < 0.75:
                    region_grid[ny][nx] = region_label
                    queue.append((nx, ny))

    for y in range(height):
        for x in range(width):
            if region_grid[y][x] is None:
                is_ocean = world_map.is_ocean[(x, y)]
                candidates = [
                    label for label in region_labels
                    if world_map.is_ocean[region_seeds[label]] == is_ocean
                ] or region_labels
                label = min(
                    candidates,
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


def _region_name_for_biome(biome, is_ocean=False):
    if is_ocean:
        return "Sea"
    if biome is None:
        return "Wilds"
    return {
        ChunkBiome.FOREST: "Forest",
        ChunkBiome.PLAINS: "Plains",
        ChunkBiome.SWAMP: "Swamp",
        ChunkBiome.HILLS: "Highlands",
        ChunkBiome.MOUNTAINS: "Mountains",
    }.get(biome, "Wilds")


def _generate_world_rivers(world_map, num_rivers, min_spacing=5, ocean_threshold=DEEP_WATER):
    """
    Trace `num_rivers` major rivers across the world grid: start from a
    high-elevation cell and walk to whichever unvisited neighbor is lowest,
    same steepest-descent idea as the per-chunk flow field in
    world_generator, just at chunk granularity and without the meander —
    a river spanning dozens of chunks doesn't need to wobble tile-by-tile
    to look natural. Each step records which edge of the source cell and
    entry edge of the destination cell the river crosses.

    Sourcing rivers from the highest cells naturally means they now start
    on the mountain ranges _apply_mountain_influence() raised, rather than
    an arbitrary noise peak, and flow down through foothills toward the
    coast -- geography drives this for free, nothing here changed.

    `ocean_threshold` decides when a river has "reached the ocean" and
    stops; generate_world_map() passes the world's own computed
    BiomeThresholds.ocean here so this agrees with actual biome
    classification instead of the fixed DEEP_WATER constant, which
    (pre-percentile-normalization) rarely matched what elevation values
    a given seed's ocean cells actually had.
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
            if current_elevation < ocean_threshold:
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


def _toroidal_delta(a, b, size):
    """Shortest signed-magnitude gap between two coordinates on a `size`-
    wide wrapping axis -- e.g. on a width-140 axis, positions 2 and 138
    are 4 apart, not 136. Used so continent falloff and climate sampling
    agree with WorldMap._to_grid()'s own wraparound instead of treating
    the grid edges as a hard seam."""
    delta = abs(a - b)
    return min(delta, size - delta)


def _generate_continents(rng, width, height, num_continents):
    """
    Seed `num_continents` landmass cores at random positions and build a
    continent shape field: every cell takes its value from whichever core
    pulls it least far into negative territory, so land forms as a few
    cohesive masses with organic-ish edges instead of scattered noise
    blobs. Deliberately left unclamped at the low end (a cell equidistant
    from every core, deep in a gap between continents, can read well
    below 0) rather than floored at 0 -- that's what gives the ocean
    between two continents one coherent low trough instead of scattered
    noise-driven ponds once this feeds into elevation below. Percentile
    normalization downstream doesn't care about the actual magnitude,
    only the ranking this produces, so leaving it unbounded costs nothing.

    Returns (continent_shape, continent_id): the HeightMap described
    above, and a dict of which core each cell is nearest to (every cell
    gets one, however far out to sea it reads).
    """
    radius = max(width, height) * CONTINENT_RADIUS_FRACTION
    min_spacing = radius * _CONTINENT_MIN_SPACING_FACTOR

    seeds = []
    attempts = 0
    while len(seeds) < num_continents and attempts < num_continents * 50:
        attempts += 1
        candidate_x, candidate_y = rng.uniform(0, width), rng.uniform(0, height)
        too_close = any(
            math.hypot(_toroidal_delta(candidate_x, sx, width), _toroidal_delta(candidate_y, sy, height)) < min_spacing
            for sx, sy, _ in seeds
        )
        if too_close:
            continue
        seeds.append((candidate_x, candidate_y, rng.uniform(0.85, 1.1)))

    shape = HeightMap(width, height)
    continent_id = {}

    for y in range(height):
        for x in range(width):
            best_value = None
            best_index = 0
            for index, (seed_x, seed_y, relative_size) in enumerate(seeds):
                dx = _toroidal_delta(x, seed_x, width)
                dy = _toroidal_delta(y, seed_y, height)
                distance = math.hypot(dx, dy)
                value = 1.0 - distance / (radius * relative_size)
                if best_value is None or value > best_value:
                    best_value = value
                    best_index = index
            shape.set(x, y, best_value if best_value is not None else -1.0)
            continent_id[(x, y)] = best_index

    return shape, continent_id


def _generate_mountain_spines(rng, continent_shape, width, height, num_ranges):
    """
    Walk `num_ranges` mountain ranges as ridge polylines, seeded on solid
    land (continent_shape >= MOUNTAIN_LAND_THRESHOLD) and bent gradually
    as they walk, same shape of trick world_generator.py's own
    _generate_mountain_ridges() uses per-chunk -- just seeded from this
    world's continents instead of a random point anywhere on the grid, so
    ranges land on the landmasses that exist rather than wherever.

    Returns a list of spines, each a list of (x, y) points (floats, not
    yet wrapped onto the grid -- _apply_mountain_influence() below handles
    that per-sample so a range can walk across the toroidal seam).
    """
    land_cells = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if continent_shape.get(x, y) >= MOUNTAIN_LAND_THRESHOLD
    ]
    if not land_cells:
        return []

    min_length = max(4, min(width, height) // 10)
    max_length = max(min_length + 4, min(width, height) // 4)

    spines = []
    for _ in range(num_ranges):
        x, y = rng.choice(land_cells)
        angle = rng.uniform(0, math.pi * 2)
        length = rng.randint(min_length, max_length)

        spine = []
        for _ in range(length):
            spine.append((x, y))
            angle += rng.uniform(-0.3, 0.3)
            x += math.cos(angle)
            y += math.sin(angle)

            sample = continent_shape.get(int(x) % width, int(y) % height)
            if sample < MOUNTAIN_LAND_THRESHOLD * 0.5:
                break  # walked off the landmass into open ocean

        if len(spine) >= 3:
            spines.append(spine)

    return spines


def _apply_mountain_influence(mountain_map, spines, width, height):
    """
    Raise elevation near each mountain range's spine with distance
    falloff -- the same "ridge polyline -> heightmap" idea world_generator
    .py's _generate_ridge_heightmap() already uses per-chunk, at world
    scale. Overlapping ranges take the strongest influence rather than
    summing, so `mountain_map` stays in a predictable [0, 1] range without
    needing its own separate normalization pass.
    """
    if not spines:
        return

    band_width = max(width, height) * MOUNTAIN_BAND_FRACTION

    for spine in spines:
        for ridge_x, ridge_y in spine:
            min_x, max_x = int(ridge_x - band_width), int(ridge_x + band_width)
            min_y, max_y = int(ridge_y - band_width), int(ridge_y + band_width)

            for grid_y in range(min_y, max_y + 1):
                dy = grid_y - ridge_y
                y = grid_y % height
                for grid_x in range(min_x, max_x + 1):
                    dx = grid_x - ridge_x
                    distance = math.hypot(dx, dy)
                    if distance >= band_width:
                        continue

                    influence = (1.0 - distance / band_width) ** 2
                    x = grid_x % width
                    if influence > mountain_map.get(x, y):
                        mountain_map.set(x, y, influence)


def _apply_climate(moisture, mountain_influence, width, height, prevailing_wind_dx):
    """
    Nudge raw moisture noise toward believable climate patterns before
    percentile normalization: a latitude band (one full sine wrap per
    grid height, so it wraps seamlessly rather than seaming at y=0/height)
    plus a rain shadow cast by mountain ranges on their leeward side.

    `prevailing_wind_dx` is the wind's direction of travel along x (+1 =
    blows toward +x, so the leeward/dry side of a range is to its east).
    For each cell, this looks upwind (the opposite direction) for nearby
    mountain influence and dries the cell out proportionally to the
    strongest peak found -- a cell downwind of a range reads drier than
    one upwind of the same range, without needing full wind simulation.
    """
    shadow_distance = max(4, min(width, height) // 12)
    wind_step = 1 if prevailing_wind_dx >= 0 else -1

    for y in range(height):
        latitude = (math.sin(2.0 * math.pi * y / height) + 1.0) / 2.0
        for x in range(width):
            value = moisture.get(x, y) + (latitude - 0.5) * LATITUDE_MOISTURE_STRENGTH

            upwind_peak = 0.0
            for step in range(1, shadow_distance + 1):
                upwind_x = (x - wind_step * step) % width
                upwind_peak = max(upwind_peak, mountain_influence.get(upwind_x, y))

            value -= upwind_peak * RAIN_SHADOW_STRENGTH
            moisture.set(x, y, value)


def generate_world_map(
    world_seed,
    width=WORLD_MAP_WIDTH,
    height=WORLD_MAP_HEIGHT,
    num_rivers=None,
    num_regions=None,
    min_region_size=4,
    max_region_size=14,
    elevation_curve=None,
    moisture_curve=None,
    local_detail_weight=0.35,
    num_continents=None,
    num_mountain_ranges=None,
    prevailing_wind_dx=1,
):
    """
    Generate the coarse, persistent world map for a game, geography-first:
    continents, then mountain ranges, then elevation, then climate, then
    rivers, then biomes, then regions. This is cheap (width * height
    cells, not width * height * chunk_size tiles) so it's generated once,
    up front, rather than lazily per chunk like the fine-grained terrain
    in generate_overworld.

    `num_continents`/`num_mountain_ranges` default to a handful scaled by
    grid area (see below) -- pass explicit values to make a seed feel more
    fragmented (more, smaller continents) or more monolithic.

    `prevailing_wind_dx` controls which side of a mountain range reads as
    its rain shadow (see _apply_climate()).

    `elevation_curve`/`moisture_curve` are optional shaping-curve
    callables (see power_curve()/smoothstep_curve() above) applied after
    percentile normalization, for controlling how mountainous/wet the
    world *feels* without touching biome area fractions -- those are
    always derived fresh from whatever distribution the grids end up
    with, via compute_biome_thresholds() below.

    `local_detail_weight` (0..1) controls how much fine per-cell noise is
    blended on top of the macro shape (continents + mountain ranges) --
    higher means neighboring chunks diverge in biome more readily, lower
    keeps terrain reading as large, geographically coherent masses.
    """
    # Two different, unrelated seeds derived from world_seed: `perm` for
    # Perlin detail noise (a different corner of the permutation table
    # than per-chunk generation uses, so coarse world layout and fine
    # per-chunk detail don't end up correlated), `rng` for everything
    # that needs ordinary randomness (continent cores, mountain walks,
    # region growth) -- kept as a local random.Random rather than the
    # global `random` module so world generation stays reproducible for
    # a given world_seed regardless of what else in the process has
    # touched the global RNG.
    perm = _build_permutation_table(world_seed ^ 0x5EED)
    rng = random.Random(world_seed ^ 0xC0FFEE)

    world_map = WorldMap(width, height)

    if num_continents is None:
        num_continents = max(3, (width * height) // 3500)
    continent_shape, continent_id = _generate_continents(rng, width, height, num_continents)
    world_map.continent_id = continent_id

    if num_mountain_ranges is None:
        num_mountain_ranges = max(3, (width * height) // 4000)
    mountain_spines = _generate_mountain_spines(rng, continent_shape, width, height, num_mountain_ranges)
    world_map.mountain_ranges = mountain_spines

    mountain_influence = HeightMap(width, height)
    _apply_mountain_influence(mountain_influence, mountain_spines, width, height)

    elevation_scale = max(width, height) / 6
    moisture_scale = max(width, height) / 4
    # The local layer varies ~5x faster than its macro counterpart --
    # frequent enough that neighboring chunks routinely diverge, not so
    # frequent that terrain reads as pure static instead of shaped land.
    local_elevation_scale = elevation_scale / 5
    local_moisture_scale = moisture_scale / 5

    for y in range(height):
        for x in range(width):
            capped_continent = min(continent_shape.get(x, y), CONTINENT_INTERIOR_CAP)
            macro_elevation = (
                capped_continent * _CONTINENT_ELEVATION_SHARE
                + mountain_influence.get(x, y) * _MOUNTAIN_ELEVATION_SHARE
            )
            detail = (_fractal_noise(perm, x / local_elevation_scale, y / local_elevation_scale, 4, 0.5, 2.0) + 1.0) / 2.0
            elevation = macro_elevation * (1.0 - local_detail_weight) + detail * local_detail_weight
            world_map.elevation.set(x, y, elevation)

            # Offset the sample point for moisture so it isn't just a scaled
            # copy of the elevation noise.
            macro_moisture = (_fractal_noise(perm, (x + 1000) / moisture_scale, (y + 1000) / moisture_scale, 4, 0.5, 2.0) + 1.0) / 2.0
            local_moisture = (_fractal_noise(perm, (x + 6000) / local_moisture_scale, (y + 6000) / local_moisture_scale, 2, 0.5, 2.0) + 1.0) / 2.0
            world_map.moisture.set(x, y, macro_moisture * (1.0 - local_detail_weight) + local_moisture * local_detail_weight)

    # Climate reacts to the shape already decided above -- latitude and
    # mountain rain shadows -- before percentile normalization, so both
    # nudges just shift a cell's rank rather than needing their own
    # separate rescale.
    _apply_climate(world_map.moisture, mountain_influence, width, height, prevailing_wind_dx)

    # Summing several octaves of noise (fBm) statistically pulls the result
    # toward the middle of its range -- it's rare for every octave to line up
    # near an extreme at once. A plain min/max stretch only fixes the
    # *endpoints*; the bulk of cells still cluster near the mean, so a fixed
    # cutoff like "elevation >= 0.75" barely ever fires. Percentile
    # normalization fixes the actual distribution instead of just its
    # extremes -- see _percentile_normalize()'s docstring.
    _percentile_normalize(world_map.elevation)
    _percentile_normalize(world_map.moisture)

    # Optional art/tuning knobs -- no-ops unless a curve is supplied. Applied
    # after percentile normalization so they're reshaping an already-uniform
    # distribution on purpose, not fighting the same clustering above fixes.
    _apply_curve(world_map.elevation, elevation_curve)
    _apply_curve(world_map.moisture, moisture_curve)

    # Distribution-aware cutoffs for *this* world's actual (possibly
    # curved) elevation/moisture grids, so biome area fractions stay close
    # to what DEFAULT_BIOME_THRESHOLDS' fixed values originally intended
    # ("about 12% ocean") regardless of seed or curve.
    thresholds = compute_biome_thresholds(world_map.elevation, world_map.moisture)
    world_map.biome_thresholds = thresholds

    for y in range(height):
        for x in range(width):
            elevation_moisture_biome = _elevation_moisture_biome(
                world_map.elevation.get(x, y),
                world_map.moisture.get(x, y),
                thresholds,
            )
            world_map.biomes[(x, y)] = _WORLD_BIOME_TO_CHUNK_BIOME[elevation_moisture_biome]
            world_map.is_ocean[(x, y)] = elevation_moisture_biome == BIOME_OCEAN

    _generate_world_regions(
        world_map,
        rng,
        num_regions=num_regions,
        min_region_size=min_region_size,
        max_region_size=max_region_size,
    )

    if num_rivers is None:
        num_rivers = max(4, (width * height) // 800)

    _generate_world_rivers(world_map, num_rivers, ocean_threshold=thresholds.ocean)

    return world_map