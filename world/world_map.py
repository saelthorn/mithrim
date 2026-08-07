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
    compute_biome_thresholds() below relies on.

    Applied to both world_map.elevation and world_map.moisture --
    moisture previously wasn't normalized at all, which is the more
    direct bug: BIOME_SWAMP's raw moisture > 0.72 cutoff was checked
    against noise that rarely left a narrow band around 0.5.
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


def _generate_world_rivers(world_map, num_rivers, min_spacing=5, ocean_threshold=DEEP_WATER):
    """
    Trace `num_rivers` major rivers across the world grid: start from a
    high-elevation cell and walk to whichever unvisited neighbor is lowest,
    same steepest-descent idea as the per-chunk flow field in
    world_generator, just at chunk granularity and without the meander —
    a river spanning dozens of chunks doesn't need to wobble tile-by-tile
    to look natural. Each step records which edge of the source cell and
    entry edge of the destination cell the river crosses.

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


def _world_noise(perm, x, y, macro_scale, local_scale, local_weight, octaves, offset):
    """
    Sample one elevation/moisture value at world-map cell (x, y) as a
    blend of two fBm layers: a broad, slow-varying "macro" layer (the
    one this module always had -- continents, mountain ranges, climate
    zones spanning many chunks) and a faster-varying "local" layer laid
    on top of it.

    Without the local layer, two chunks have to be `macro_scale` cells
    apart (~23 chunks, at this module's default scales) before the
    macro noise moves enough to plausibly change biome -- so a player
    spawning in a mountain chunk could walk a dozen chunks in any
    direction and still be in mountains, since every neighboring cell
    was reading almost the same macro value. Blending in `local_weight`
    of a layer that varies `local_scale` (a fraction of macro_scale)
    gives each chunk its own texture on top of the broad shape, so
    neighboring chunks routinely differ in elevation/moisture (and
    therefore biome) while the macro layer still keeps mountain ranges,
    oceans, etc. reading as coherent multi-chunk regions rather than
    dissolving into pure noise.

    `offset` shifts the sample point the same way the original moisture
    sampling did, so elevation and moisture (and each one's macro/local
    components) never sample the exact same noise field.
    """
    macro = (_fractal_noise(perm, (x + offset) / macro_scale, (y + offset) / macro_scale, octaves, 0.5, 2.0) + 1.0) / 2.0
    local = (_fractal_noise(perm, (x + offset + 5000) / local_scale, (y + offset + 5000) / local_scale, max(2, octaves - 2), 0.5, 2.0) + 1.0) / 2.0
    return macro * (1.0 - local_weight) + local * local_weight


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
):
    """
    Generate the coarse, persistent world map for a game: one elevation/
    moisture/biome value per chunk, plus a handful of major rivers crossing
    many chunks. This is cheap (width * height cells, not width * height *
    chunk_size tiles) so it's generated once, up front, rather than lazily
    per chunk like the fine-grained terrain in generate_overworld.

    `elevation_curve`/`moisture_curve` are optional shaping-curve
    callables (see power_curve()/smoothstep_curve() above) applied after
    percentile normalization, for controlling how mountainous/wet the
    world *feels* without touching biome area fractions -- those are
    always derived fresh from whatever distribution the grids end up
    with, via compute_biome_thresholds() below.

    `local_detail_weight` (0..1) controls how much of the faster-varying
    "local" noise layer (see _world_noise()) is blended into the classic
    macro layer -- higher means neighboring chunks diverge in biome more
    readily, lower keeps the old behavior of very large, uniform biome
    regions. 0.0 reproduces the original macro-only noise exactly.
    """
    # A different corner of the permutation table than per-chunk noise uses
    # (world_generator seeds its own permutation table from the same
    # world_seed), so the coarse world layout and the fine per-chunk detail
    # don't end up correlated with each other.
    perm = _build_permutation_table(world_seed ^ 0x5EED)

    world_map = WorldMap(width, height)
    elevation_scale = max(width, height) / 6
    moisture_scale = max(width, height) / 4
    # The local layer varies ~5x faster than its macro counterpart --
    # frequent enough that neighboring chunks routinely diverge, not so
    # frequent that terrain reads as pure static instead of shaped land.
    local_elevation_scale = elevation_scale / 5
    local_moisture_scale = moisture_scale / 5

    for y in range(height):
        for x in range(width):
            elevation = _world_noise(
                perm, x, y, elevation_scale, local_elevation_scale, local_detail_weight,
                octaves=5, offset=0,
            )
            world_map.elevation.set(x, y, elevation)

            # Offset the sample point for moisture so it isn't just a scaled
            # copy of the elevation noise (same trick generate_overworld uses).
            moisture = _world_noise(
                perm, x, y, moisture_scale, local_moisture_scale, local_detail_weight,
                octaves=4, offset=1000,
            )
            world_map.moisture.set(x, y, moisture)

    # Summing several octaves of noise (fBm) statistically pulls the result
    # toward the middle of its range -- it's rare for every octave to line up
    # near an extreme at once. A plain min/max stretch only fixes the
    # *endpoints*; the bulk of cells still cluster near the mean, so a fixed
    # cutoff like "elevation >= 0.75" barely ever fires. Percentile
    # normalization fixes the actual distribution instead of just its
    # extremes -- see _percentile_normalize()'s docstring -- and is applied
    # to moisture too, which previously wasn't normalized at all (moisture
    # > 0.72 for BIOME_SWAMP was checked against raw, uncorrected noise).
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

    _generate_world_regions(
        world_map,
        num_regions=num_regions,
        min_region_size=min_region_size,
        max_region_size=max_region_size,
    )

    if num_rivers is None:
        num_rivers = max(4, (width * height) // 800)

    _generate_world_rivers(world_map, num_rivers, ocean_threshold=thresholds.ocean)

    return world_map