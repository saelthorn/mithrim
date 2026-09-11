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
import heapq
import random
from collections import deque

from world.world_generator import (
    ChunkBiome,
    HeightMap,
    BiomeThresholds,
    _build_permutation_table,
    _fractal_noise,
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
    BIOME_OCEAN: ChunkBiome.OCEAN,
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

# Target fraction of the world that reads as ocean by continentalness
# alone -- distinct from elevation's own OCEAN_PERCENTILE (see below),
# which is now secondary. Continentalness decides *whether a region is
# ocean or land* at the large scale; elevation decides terrain height
# within that region; mountain ranges below key off this same cutoff too,
# so all three stay in agreement about where land actually is.
CONTINENTALNESS_OCEAN_PERCENTILE = 0.35

# -- mountain ranges ---------------------------------------------------
# Ranges are walked as ridge polylines (see _generate_mountain_spines)
# seeded on, and confined to, solid land as read off *normalized*
# continentalness -- not raw continent_shape -- so "on land" here means
# exactly what WorldMap.is_ocean already means, keeping mountains
# consistent with the same field that decides ocean/land.
#
# How solidly on a continent (by normalized continentalness, 0..1) a
# cell must be to *seed* a new range -- comfortably above the ocean
# cutoff (CONTINENTALNESS_OCEAN_PERCENTILE) so ranges start well inland,
# never right at a coastline.
MOUNTAIN_LAND_THRESHOLD = 0.55
# How far continentalness may drop before an already-walking range stops
# -- lower than the seed threshold (so a range can cross a lower inland
# saddle without ending), but still kept a clear margin above
# CONTINENTALNESS_OCEAN_PERCENTILE so a range never actually reaches
# open water.
MOUNTAIN_RANGE_CONTINUE_THRESHOLD = CONTINENTALNESS_OCEAN_PERCENTILE + 0.05
# Half-width of a mountain range's elevation influence, as a fraction of
# the grid's larger dimension.
MOUNTAIN_BAND_FRACTION = 0.07

# -- elevation shaping --------------------------------------------------
# Elevation is deliberately generated without reference to continent
# shape/continentalness at all: continentalness already answered "land
# or ocean"; elevation only answers "how high is this land" (or "how
# deep is this water"), from its own independent regional-relief noise
# plus mountain-range influence. This is what keeps the two fields
# conceptually (and now numerically) separate.
#
# Regional relief is a mid-frequency fBm layer, percentile-normalized on
# its own before blending in below, so lowlands/hills/highlands are
# spread naturally across land instead of clustering near the mean the
# way raw fBm does (same reasoning as _percentile_normalize()'s
# docstring). Its wavelength sits between a whole continent and the fine
# per-cell detail layer, so highland/lowland swells span many chunks
# without tracking any single continent's own shape.
REGIONAL_RELIEF_OCTAVES = 4
REGIONAL_RELIEF_PERSISTENCE = 0.5
REGIONAL_RELIEF_LACUNARITY = 2.0
# How elevation's macro shape (i.e. everything but the per-cell detail
# layer) splits between regional relief and ridge-based mountain-range
# influence. Mountain ranges still read as a distinct, sharper feature
# rising out of gentler relief, not as one more noise octave -- away
# from a range mountain_influence is 0, so elevation there is pure
# relief; near a ridge this share pushes those cells reliably above
# everything else, without depending on relief happening to spike there.
_RELIEF_ELEVATION_SHARE = 0.6
_MOUNTAIN_ELEVATION_SHARE = 0.4

# -- climate ------------------------------------------------------------
# How strongly a sine-wave latitude band (one full wrap per grid height,
# so it stays seamless on this toroidal map) nudges moisture wetter/drier.
LATITUDE_MOISTURE_STRENGTH = 0.35
# How strongly standing in the lee of a mountain range dries a cell out.
RAIN_SHADOW_STRENGTH = 0.6
# World-map cells around a major river receive a smooth moisture increase.
RIVER_MOISTURE_RADIUS = 5
RIVER_MOISTURE_BOOST = 0.18
# Prevent one land biome from forming an unbroken corridor across dozens of
# world-map cells. This is a coarse-world constraint; local chunk detail is
# still handled by world_generator.py.
MAX_BIOME_RUN_LENGTH = 4

# -- region character -----------------------------------------------------
# Thresholds used to describe a region's *character* (elevation_character,
# moisture_character, near_mountains) from its member cells' averaged/peak
# values, rather than from a single feature label. Elevation/moisture are
# percentile-normalized to [0, 1] across the whole world grid by the time
# regions are built, so plain thirds are a reasonable, simple bucketing.
REGION_ELEVATION_LOWLAND_MAX = 0.35
REGION_ELEVATION_HIGHLAND_MIN = 0.65
REGION_MOISTURE_DRY_MAX = 0.35
REGION_MOISTURE_WET_MIN = 0.65
# Same cutoff _get_region_feature() already uses to call a cell
# "Highlands" -- reused here so "near_mountains" agrees with that feature
# detection instead of drifting from it.
REGION_NEAR_MOUNTAIN_STRENGTH = 0.12
# mountain_strength at/above which a cell's identity is "Mountain Range"
# rather than merely "Highlands" -- the same cutoff _classify_world_biome()
# already uses to call a cell BIOME_MOUNTAINS, kept in agreement here too.
REGION_MOUNTAIN_RANGE_STRENGTH = 0.40
# How much elevation is allowed to matter when ranking two "Mountain
# Range" candidates against each other. Small on purpose: mountain_strength
# is what identity is decided from, so elevation may only break ties
# between similarly-mountainous cells, never outrank a stronger range cell.
MOUNTAIN_ELEVATION_TIEBREAK_WEIGHT = 0.25

# -- region influence (graded, alongside the plain near_river/near_mountains
# booleans already on RegionInfo) -------------------------------------------
# A region's mountain_influence is bucketed from its cells' *average*
# mountain_strength (how mountainous the region is overall), reusing the
# same two cutoffs identity/near_mountains already use, so "Moderate"/
# "Strong" here agree with what a cell would itself be classified as.
REGION_MOUNTAIN_INFLUENCE_WEAK = 0.02
REGION_MOUNTAIN_INFLUENCE_MODERATE = REGION_NEAR_MOUNTAIN_STRENGTH
REGION_MOUNTAIN_INFLUENCE_STRONG = REGION_MOUNTAIN_RANGE_STRENGTH
# A region's river_influence is bucketed from the *fraction* of its cells
# that carry a river edge. Rivers are thin, linear features -- even a
# region genuinely shaped by a river rarely has it running through most of
# its cells -- so these fractions are deliberately much lower than the
# mountain thresholds above, which measure a broad area effect instead.
REGION_RIVER_INFLUENCE_WEAK = 0.05
REGION_RIVER_INFLUENCE_MODERATE = 0.15
REGION_RIVER_INFLUENCE_STRONG = 0.35

# -- region display naming --------------------------------------------------
# Purely descriptive vocabulary for turning a region's already-decided
# character (dominant_feature, moisture_character) into a two-word display
# name (e.g. "Ashen Highlands", "Emerald Vale") -- flavor only. The
# region's actual identity/lookup key stays RegionInfo.id (see
# _generate_world_regions), which this never touches.
REGION_NAME_NOUNS = {
    "Mountain Range": ["Peaks", "Range", "Crags"],
    "Highlands": ["Highlands", "Uplands", "Heights"],
    "Forest": ["Wood", "Grove", "Timberland"],
    "Marsh": ["Fen", "Mire", "Bog"],
    "Plains": ["Vale", "Reach", "Downs"],
    "Coastal": ["Shore", "Coast", "Strand"],
    "River Valley": ["Valley", "Vale", "Bend"],
    "Sea": ["Sea", "Deep", "Waters"],
}
REGION_NAME_ADJECTIVES = {
    "Dry": ["Ashen", "Parched", "Dusty"],
    "Moderate": ["Gray", "Quiet", "Still"],
    "Wet": ["Emerald", "Verdant", "Misty"],
}


class RegionInfo:
    """
    Authoritative, persistent identity and character of one world region.

    A region is a meaningful geographic area, not just a biome or a single
    terrain feature -- `dominant_biome` and `dominant_feature` are only two
    of several characteristics describing it, alongside elevation/moisture
    character and its neighboring terrain (river, mountains, coast, ocean).
    `id`/`name` are decided once by _generate_world_regions() and are what
    every other system (chunk generation, roads, flavor) should treat as
    the region's identity -- nothing downstream re-derives or overrides it.
    """

    def __init__(
        self,
        region_id,
        name,
        dominant_biome=None,
        dominant_feature=None,
        elevation_character="Midland",
        moisture_character="Moderate",
        near_river=False,
        near_mountains=False,
        river_influence="None",
        mountain_influence="None",
        coastal=False,
        is_ocean=False,
        size=0,
        center=None,
    ):
        self.id = region_id
        self.name = name
        self.dominant_biome = dominant_biome
        self.dominant_feature = dominant_feature
        self.elevation_character = elevation_character
        self.moisture_character = moisture_character
        self.near_river = near_river
        self.near_mountains = near_mountains
        # Graded ("None"/"Weak"/"Moderate"/"Strong") counterparts to the
        # plain booleans above -- how much of the region's *area* the
        # feature actually shapes, not just whether it's present anywhere.
        self.river_influence = river_influence
        self.mountain_influence = mountain_influence
        self.coastal = coastal
        self.is_ocean = is_ocean
        self.size = size
        self.center = center
        # Populated after every region's RegionInfo exists, from the same
        # region_graph WorldMap.region_transitions_at() already reads --
        # kept here too so a RegionInfo is a self-contained description of
        # the region without needing a second lookup against the WorldMap.
        self.neighbors = set()

    def __repr__(self):
        return f"RegionInfo(id={self.id!r}, name={self.name!r}, biome={self.dominant_biome})"


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
        # Low-frequency landmass signal, independent of elevation: how
        # solidly "on a continent" (high) vs "deep ocean" (low) a cell is.
        # This -- not elevation -- is what WorldMap.is_ocean is derived
        # from, so large-scale ocean/land shape stays coherent even where
        # elevation is locally noisy (mountain ranges, coastal detail).
        self.continentalness = HeightMap(width, height)
        self.biomes = {}       # (grid_x, grid_y) -> ChunkBiome
        self.coastal = {}      # (grid_x, grid_y) -> bool; land next to ocean
        self.river_edges = {}  # (grid_x, grid_y) -> set of "N"/"S"/"E"/"W"
        self.road_edges = {}   # (grid_x, grid_y) -> set of road crossings
        self.road_destinations = {}  # (grid_x, grid_y) -> strategic labels
        self.region_names = {} # (grid_x, grid_y) -> coarse region label
        self.flavor = {}       # (grid_x, grid_y) -> dict of stage metadata
        self.region_ids = {}    # (grid_x, grid_y) -> region id
        self.region_graph = {}  # region id -> set of neighboring region ids
        # Authoritative region identity: region id -> RegionInfo. A region's
        # name/id is decided once, by _generate_world_regions(), and never
        # re-derived by chunk generation -- world_generator.py only reads
        # this back through region_info_at() when it paints a chunk.
        self.regions = {}       # region id -> RegionInfo
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
        # How strongly a cell is shaped by the nearest mountain range's
        # ridge, in [0, 1] with 0 meaning "outside every range's band" --
        # this is the same field elevation blends in, kept here as its
        # own persistent grid so it's queryable independently of the
        # elevation value it fed into (e.g. "is this a mountain slope, or
        # just a naturally high patch of regional relief?").
        self.mountain_strength = HeightMap(width, height)
        # Which mountain_ranges[] index -- i.e. which range -- currently
        # dominates a cell's mountain_strength, or absent if the cell
        # isn't within any range's band at all. Lets content ask "which
        # range is this peak part of" instead of only "how mountainous".
        self.mountain_range_id = {}  # (grid_x, grid_y) -> int
        # Set by generate_world_map() via compute_biome_thresholds() --
        # the actual elevation/moisture cutoffs this world's biomes were
        # classified against, kept around for debugging/introspection
        # (e.g. confirming a seed really did land ~12% ocean).
        self.biome_thresholds = None
        # The continentalness value at/below which a cell is considered
        # ocean (see CONTINENTALNESS_OCEAN_PERCENTILE) -- kept around for
        # the same debugging/introspection reasons as biome_thresholds.
        self.continentalness_ocean_threshold = None

    def _to_grid(self, chunk_coord):
        """Wrap an unbounded (chunk_x, chunk_y) onto this fixed-size grid."""
        chunk_x, chunk_y = chunk_coord
        grid_x = (chunk_x + self.width // 2) % self.width
        grid_y = (chunk_y + self.height // 2) % self.height
        return grid_x, grid_y

    def elevation_at(self, chunk_coord):
        grid_x, grid_y = self._to_grid(chunk_coord)
        return self.elevation.get(grid_x, grid_y)

    def moisture_at(self, chunk_coord):
        grid_x, grid_y = self._to_grid(chunk_coord)
        return self.moisture.get(grid_x, grid_y)

    def continentalness_at(self, chunk_coord):
        grid_x, grid_y = self._to_grid(chunk_coord)
        return self.continentalness.get(grid_x, grid_y)

    def mountain_strength_at(self, chunk_coord):
        grid_x, grid_y = self._to_grid(chunk_coord)
        return self.mountain_strength.get(grid_x, grid_y)

    def mountain_range_id_at(self, chunk_coord):
        """Index into mountain_ranges for whichever range dominates this
        chunk's mountain_strength, or None if it's outside every range's
        band (mountain_strength is 0 there)."""
        return self.mountain_range_id.get(self._to_grid(chunk_coord))

    def biome_at(self, chunk_coord):
        return self.biomes[self._to_grid(chunk_coord)]

    def is_coastal_at(self, chunk_coord):
        """Whether this land cell borders an ocean cell at world scale."""
        return self.coastal.get(self._to_grid(chunk_coord), False)

    def river_edges_at(self, chunk_coord):
        """Which edges ('N'/'S'/'E'/'W') of this chunk a major river crosses,
        as an empty set if no major river passes through it."""
        return self.river_edges.get(self._to_grid(chunk_coord), set())

    def road_edges_at(self, chunk_coord):
        """Which edges of this chunk carry a world-scale strategic road."""
        return self.road_edges.get(self._to_grid(chunk_coord), set())

    def road_destinations_at(self, chunk_coord):
        """Strategic destination labels associated with this chunk."""
        return self.road_destinations.get(self._to_grid(chunk_coord), set())

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

    def region_info_at(self, chunk_coord):
        """The authoritative RegionInfo for this chunk, or None before
        region generation has run. This -- not a chunk's own local terrain
        sampling -- is the single source of truth for what world region a
        chunk belongs to and what that region's character is."""
        return self.regions.get(self.region_at(chunk_coord))

    def get_region(self, region_id):
        """Look up a RegionInfo directly by region id (see region_at())."""
        return self.regions.get(region_id)

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


def _is_coastal_cell(world_map, x, y):
    """Return whether a land cell directly borders ocean on the world grid."""
    if world_map.is_ocean.get((x, y), False):
        return False

    for dx, dy in _DIRECTION_OFFSETS.values():
        neighbor = ((x + dx) % world_map.width, (y + dy) % world_map.height)
        if world_map.is_ocean.get(neighbor, False):
            return True
    return False


def _classify_world_biome(world_map, x, y, thresholds):
    """Classify one coarse cell from persistent geography and climate."""
    if world_map.is_ocean.get((x, y), False):
        return BIOME_OCEAN

    if _is_coastal_cell(world_map, x, y):
        world_map.coastal[(x, y)] = True
        return BIOME_BEACH

    elevation = world_map.elevation.get(x, y)
    mountain_strength = world_map.mountain_strength.get(x, y)
    moisture = world_map.moisture.get(x, y)

    # Ridge influence makes ranges read as mountains even where independent
    # relief noise is modest; the lower band gives them a hills transition.
    if elevation >= thresholds.mountains or mountain_strength >= 0.40:
        return BIOME_MOUNTAINS
    if elevation >= thresholds.hills or mountain_strength >= 0.12:
        return BIOME_HILLS
    if moisture > thresholds.swamp_moisture:
        return BIOME_SWAMP
    if moisture > thresholds.forest_moisture:
        return BIOME_FOREST
    if elevation <= thresholds.ocean:
        return BIOME_OCEAN
    return BIOME_PLAINS


def _break_long_biome_runs(world_map, max_run=MAX_BIOME_RUN_LENGTH):
    """Break excessive cardinal biome streaks using nearby map geography."""
    if max_run < 2:
        return

    width, height = world_map.width, world_map.height
    original = dict(world_map.biomes)
    replacements = {}

    for y in range(height):
        for x in range(width):
            biome = original.get((x, y))
            if biome is None or world_map.is_ocean.get((x, y), False):
                continue

            for direction, (dx, dy) in (("E", (1, 0)), ("S", (0, 1))):
                run = []
                for offset in range(max_run + 1):
                    nx = (x + dx * offset) % width
                    ny = (y + dy * offset) % height
                    if world_map.is_ocean.get((nx, ny), False) or original.get((nx, ny)) != biome:
                        break
                    run.append((nx, ny))

                if len(run) <= max_run:
                    continue

                break_cell = run[max_run // 2]
                bx, by = break_cell
                nearby = []
                for radius in range(1, max_run + 1):
                    for ox, oy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
                        nx = (bx + ox) % width
                        ny = (by + oy) % height
                        candidate = original.get((nx, ny))
                        if candidate is None or candidate is biome or world_map.is_ocean.get((nx, ny), False):
                            continue
                        nearby.append((radius, candidate, nx, ny))
                    if nearby:
                        break

                if nearby:
                    _, replacement, _, _ = min(nearby, key=lambda item: (item[0], item[2], item[3], item[1].value))
                    replacements[break_cell] = replacement

    world_map.biomes.update(replacements)


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
    Generate a coarse region graph for the world map using geography-aware
    seeded growth. Seeds favor mountain ranges, river valleys, coasts, and
    broad climate/terrain masses before filling remaining slots from the
    strongest unclaimed geographic features. Rivers and distinct mountain
    ranges act as soft boundaries, while biome adjacency and the ocean/land
    split keep neighboring geography compatible. `rng` is retained for
    deterministic tie-breaking and region growth reproducibility.
    """
    width, height = world_map.width, world_map.height
    if num_regions is None:
        num_regions = max(8, (width * height) // 500)

    region_grid = [[None for _ in range(width)] for _ in range(height)]
    region_seeds = {}
    region_labels = []

    feature_order = (
        "Mountain Range",
        "River Valley",
        "Coastal",
        "Marsh",
        "Forest",
        "Highlands",
        "Plains",
        "Sea",
    )
    feature_candidates = {feature: [] for feature in feature_order}
    for y in range(height):
        for x in range(width):
            feature = _get_region_feature(world_map, x, y)
            score = _get_feature_strength(world_map, x, y, feature)
            feature_candidates[feature].append((score, x, y))

    seed_spacing = max(3, min(width, height) // 8)
    selected_seeds = []
    for feature in feature_order:
        feature_candidates[feature].sort(reverse=True)
        for _, seed_x, seed_y in feature_candidates[feature]:
            if len(selected_seeds) >= num_regions:
                break
            if any(abs(seed_x - sx) + abs(seed_y - sy) < seed_spacing for sx, sy, _ in selected_seeds):
                continue
            selected_seeds.append((seed_x, seed_y, feature))
            break
        if len(selected_seeds) >= num_regions:
            break

    remaining_candidates = sorted(
        [
            (
                _get_feature_strength(world_map, x, y, _get_region_feature(world_map, x, y)),
                x,
                y,
                _get_region_feature(world_map, x, y),
            )
        for y in range(height)
        for x in range(width)
        ],
        reverse=True,
    )
    for _, seed_x, seed_y, feature in remaining_candidates:
        if len(selected_seeds) >= num_regions:
            break
        if any(abs(seed_x - sx) + abs(seed_y - sy) < seed_spacing for sx, sy, _ in selected_seeds):
            continue
        selected_seeds.append((seed_x, seed_y, feature))

    for region_id, (seed_x, seed_y, feature) in enumerate(selected_seeds, start=1):
        region_label = f"{feature}-{region_id}"
        queue = deque([(seed_x, seed_y)])
        region_grid[seed_y][seed_x] = region_label
        region_seeds[region_label] = (seed_x, seed_y)
        region_labels.append(region_label)

        size = 0
        while queue and size < max_region_size:
            cx, cy = queue.popleft()
            size += 1
            biome = world_map.biomes[(seed_x, seed_y)]
            is_ocean = world_map.is_ocean[(seed_x, seed_y)]
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

                if _region_boundary_between(world_map, (cx, cy), (nx, ny)):
                    continue

                if size < min_region_size or rng.random() < 0.90:
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

    region_cells = {label: [] for label in region_labels}
    for y in range(height):
        for x in range(width):
            label = region_grid[y][x]
            world_map.set_region((x, y), label)
            region_cells[label].append((x, y))

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

    world_map.regions = _build_region_info(world_map, region_cells, region_seeds)
    for label, region in world_map.regions.items():
        region.neighbors = set(world_map.region_graph.get(label, set()))
        for x, y in region_cells[label]:
            world_map.set_region_name((x, y), region.name)

    return world_map


def _elevation_character(average_elevation):
    if average_elevation < REGION_ELEVATION_LOWLAND_MAX:
        return "Lowland"
    if average_elevation >= REGION_ELEVATION_HIGHLAND_MIN:
        return "Highland"
    return "Midland"


def _moisture_character(average_moisture):
    if average_moisture < REGION_MOISTURE_DRY_MAX:
        return "Dry"
    if average_moisture >= REGION_MOISTURE_WET_MIN:
        return "Wet"
    return "Moderate"


def _influence_level(value, weak_min, moderate_min, strong_min):
    """Bucket a 0..1 area measurement (e.g. average mountain_strength, or
    the fraction of a region's cells carrying a river edge) into a plain
    "None"/"Weak"/"Moderate"/"Strong" description."""
    if value >= strong_min:
        return "Strong"
    if value >= moderate_min:
        return "Moderate"
    if value >= weak_min:
        return "Weak"
    return "None"


def _stable_index(text, length, salt=0):
    """Deterministic index into a list of size `length`, derived from
    `text`. Used instead of the `random` module for descriptive-name
    variety, so the same world seed always produces the same names
    without threading an RNG through region metadata building."""
    if length <= 0:
        return 0
    total = salt
    for character in text:
        total = (total * 31 + ord(character)) & 0xFFFFFFFF
    return total % length


def _region_display_name(region_id, dominant_feature, moisture_character):
    """A two-word, human-facing name reflecting the region's own character
    (e.g. "Ashen Highlands", "Emerald Vale") -- flavor only, derived
    deterministically from data the region already has. Never used as a
    lookup key; see RegionInfo.id for that."""
    nouns = REGION_NAME_NOUNS.get(dominant_feature, ["Wilds"])
    adjectives = REGION_NAME_ADJECTIVES.get(moisture_character, ["Quiet"])
    adjective = adjectives[_stable_index(region_id, len(adjectives), salt=1)]
    noun = nouns[_stable_index(region_id, len(nouns), salt=2)]
    return f"{adjective} {noun}"


def _build_region_info(world_map, region_cells, region_seeds):
    """
    Derive one RegionInfo per region label from its actual member cells --
    this is what lets a region's identity (id/name) stay independent of any
    single characteristic like dominant_biome or dominant_feature, since
    those are computed *from* membership rather than defining it.
    """
    regions = {}
    for label, cells in region_cells.items():
        if not cells:
            continue

        biome_counts = {}
        river_cells = 0
        coastal_cells = 0
        ocean_cells = 0
        peak_mountain_strength = 0.0
        mountain_strength_total = 0.0
        elevation_total = 0.0
        moisture_total = 0.0

        for x, y in cells:
            biome_counts[world_map.biomes.get((x, y))] = biome_counts.get(world_map.biomes.get((x, y)), 0) + 1
            if world_map.river_edges.get((x, y)):
                river_cells += 1
            if world_map.coastal.get((x, y), False):
                coastal_cells += 1
            if world_map.is_ocean.get((x, y), False):
                ocean_cells += 1
            cell_mountain_strength = world_map.mountain_strength.get(x, y)
            peak_mountain_strength = max(peak_mountain_strength, cell_mountain_strength)
            mountain_strength_total += cell_mountain_strength
            elevation_total += world_map.elevation.get(x, y)
            moisture_total += world_map.moisture.get(x, y)

        cell_count = len(cells)
        dominant_biome = max(biome_counts, key=biome_counts.get)
        dominant_feature = label.split("-", 1)[0]
        moisture_character = _moisture_character(moisture_total / cell_count)

        regions[label] = RegionInfo(
            region_id=label,
            name=_region_display_name(label, dominant_feature, moisture_character),
            dominant_biome=dominant_biome,
            dominant_feature=dominant_feature,
            elevation_character=_elevation_character(elevation_total / cell_count),
            moisture_character=moisture_character,
            near_river=river_cells > 0,
            near_mountains=peak_mountain_strength >= REGION_NEAR_MOUNTAIN_STRENGTH,
            river_influence=_influence_level(
                river_cells / cell_count,
                REGION_RIVER_INFLUENCE_WEAK,
                REGION_RIVER_INFLUENCE_MODERATE,
                REGION_RIVER_INFLUENCE_STRONG,
            ),
            mountain_influence=_influence_level(
                mountain_strength_total / cell_count,
                REGION_MOUNTAIN_INFLUENCE_WEAK,
                REGION_MOUNTAIN_INFLUENCE_MODERATE,
                REGION_MOUNTAIN_INFLUENCE_STRONG,
            ),
            coastal=coastal_cells > 0,
            is_ocean=ocean_cells > cell_count / 2,
            size=cell_count,
            center=region_seeds.get(label),
        )

    return regions


def _world_road_cost(world_map, current, neighbor):
    """Return deterministic travel cost for one coarse road step."""
    if world_map.is_ocean.get(neighbor, False):
        return None

    cost = 1.0
    cost += world_map.elevation.get(*neighbor) * 0.5
    cost += world_map.mountain_strength.get(*neighbor) * 5.0

    current_range = world_map.mountain_range_id.get(current)
    neighbor_range = world_map.mountain_range_id.get(neighbor)
    if current_range != neighbor_range and current_range is not None and neighbor_range is not None:
        cost += 2.0

    current_x, current_y = current
    neighbor_x, neighbor_y = neighbor
    direction = next(
        direction
        for direction, (dx, dy) in _DIRECTION_OFFSETS.items()
        if (current_x + dx, current_y + dy) == (neighbor_x, neighbor_y)
    )
    if direction in world_map.river_edges.get(current, set()):
        cost += 3.0

    return cost


def _find_world_road_path(world_map, start, goal):
    """Find a low-cost cardinal route between two strategic destinations."""
    open_set = [(0.0, start)]
    costs = {start: 0.0}
    came_from = {}

    while open_set:
        cost, current = heapq.heappop(open_set)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        if cost != costs.get(current):
            continue

        current_x, current_y = current
        for _, (dx, dy) in _DIRECTION_OFFSETS.items():
            neighbor = (current_x + dx, current_y + dy)
            if not (0 <= neighbor[0] < world_map.width and 0 <= neighbor[1] < world_map.height):
                continue
            step_cost = _world_road_cost(world_map, current, neighbor)
            if step_cost is None:
                continue
            next_cost = cost + step_cost
            if next_cost < costs.get(neighbor, float("inf")):
                costs[neighbor] = next_cost
                came_from[neighbor] = current
                heapq.heappush(open_set, (next_cost, neighbor))

    return []


def _record_world_road_path(world_map, path, start_label, goal_label):
    """Record matching road edge crossings and endpoint destination labels."""
    if not path:
        return

    world_map.road_destinations.setdefault(path[0], set()).add(start_label)
    world_map.road_destinations.setdefault(path[-1], set()).add(goal_label)
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        direction = next(
            direction
            for direction, (dx, dy) in _DIRECTION_OFFSETS.items()
            if (ax + dx, ay + dy) == (bx, by)
        )
        opposite = _OPPOSITE_DIRECTION[direction]
        world_map.road_edges.setdefault((ax, ay), set()).add(direction)
        world_map.road_edges.setdefault((bx, by), set()).add(opposite)


def _generate_world_roads(world_map):
    """Connect neighboring land regions with a sparse strategic road network."""
    region_cells = {}
    for y in range(world_map.height):
        for x in range(world_map.width):
            region_id = world_map.region_at((x, y))
            if region_id is None or world_map.is_ocean.get((x, y), False):
                continue
            region_cells.setdefault(region_id, []).append((x, y))

    region_centers = {}
    for region_id, cells in region_cells.items():
        average_x = sum(x for x, _ in cells) / len(cells)
        average_y = sum(y for _, y in cells) / len(cells)
        region_centers[region_id] = min(
            cells,
            key=lambda cell: ((cell[0] - average_x) ** 2 + (cell[1] - average_y) ** 2, cell[1], cell[0]),
        )

    connected = set()
    for region_id in sorted(region_centers):
        neighbors = [
            neighbor_id
            for neighbor_id in world_map.region_graph.get(region_id, set())
            if neighbor_id in region_centers
        ]
        if not neighbors:
            continue
        neighbor_id = min(
            neighbors,
            key=lambda candidate: (
                abs(region_centers[region_id][0] - region_centers[candidate][0])
                + abs(region_centers[region_id][1] - region_centers[candidate][1]),
                candidate,
            ),
        )
        connection = frozenset((region_id, neighbor_id))
        if connection in connected:
            continue
        connected.add(connection)

        path = _find_world_road_path(
            world_map,
            region_centers[region_id],
            region_centers[neighbor_id],
        )
        _record_world_road_path(world_map, path, region_id, neighbor_id)

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


def _get_region_feature(world_map, x, y):
    """
    Identity: the single most specific geographic feature this cell
    represents. Every branch is decided by the same field that actually
    *is* that feature (ocean by is_ocean, mountains by mountain_strength,
    rivers by river_edges, coast by world_map.coastal, the rest by
    biome) -- checked in order of specificity so a cell that qualifies
    for more than one (a swampy river valley, say) gets the most
    distinguishing one. _get_feature_strength() below never changes this
    decision, only ranks candidates that already share it.
    """
    if world_map.is_ocean.get((x, y), False):
        return "Sea"
    if world_map.mountain_strength.get(x, y) >= REGION_MOUNTAIN_RANGE_STRENGTH:
        return "Mountain Range"
    if world_map.river_edges.get((x, y)):
        return "River Valley"
    if world_map.coastal.get((x, y), False):
        return "Coastal"

    biome = world_map.biomes.get((x, y))
    if biome is ChunkBiome.SWAMP:
        return "Marsh"
    if biome is ChunkBiome.FOREST:
        return "Forest"
    if biome is ChunkBiome.HILLS or world_map.mountain_strength.get(x, y) >= REGION_NEAR_MOUNTAIN_STRENGTH:
        return "Highlands"
    if biome is ChunkBiome.PLAINS:
        return "Plains"
    return "Plains"  # defensive default for any other/unclassified biome


def _band_centrality(value, low, high):
    """
    How centered `value` sits within [low, high) -- 1.0 at the band's
    midpoint, tapering to 0.0 at (or past) either edge. Used to score how
    representative a cell is of a band it was already classified into
    (e.g. a biome's moisture range), instead of treating the raw field
    value itself as the score, which rewards drifting toward a
    neighboring band's territory just as much as sitting solidly inside
    this one.
    """
    if high <= low:
        return 1.0
    midpoint = (low + high) / 2.0
    half_width = (high - low) / 2.0
    return max(0.0, 1.0 - abs(value - midpoint) / half_width)


def _ocean_neighbor_fraction(world_map, x, y):
    """Fraction (0..1) of this cell's four cardinal neighbors that are
    open ocean. Only used to rank how exposed a coastal candidate is;
    coastal identity itself is decided by world_map.coastal, not this."""
    ocean_neighbors = sum(
        1
        for dx, dy in _DIRECTION_OFFSETS.values()
        if world_map.is_ocean.get((x + dx, y + dy), False)
    )
    return ocean_neighbors / 4.0


def _get_feature_strength(world_map, x, y, feature):
    """
    Strength: how strongly this cell represents `feature`, for ranking
    candidate seeds against each other *within* one feature category --
    never used to decide `feature` itself (see _get_region_feature()).
    Every branch is built from the field(s) that actually back that
    feature's identity, so a "River Valley" candidate can only score
    higher by having more river evidence, a "Coastal" candidate only by
    being more exposed to the ocean, and so on -- never by an unrelated
    proxy like moisture standing in for a river, or raw continentalness
    standing in for coastal distance.
    """
    elevation = world_map.elevation.get(x, y)
    moisture = world_map.moisture.get(x, y)
    mountain_strength = world_map.mountain_strength.get(x, y)
    thresholds = world_map.biome_thresholds

    if feature == "Sea":
        ocean_threshold = world_map.continentalness_ocean_threshold
        if ocean_threshold is None:
            ocean_threshold = 0.0
        return ocean_threshold - world_map.continentalness.get(x, y)

    if feature == "Mountain Range":
        return mountain_strength + elevation * MOUNTAIN_ELEVATION_TIEBREAK_WEIGHT

    if feature == "River Valley":
        return len(world_map.river_edges.get((x, y), ())) / 4.0

    if feature == "Coastal":
        return _ocean_neighbor_fraction(world_map, x, y)

    if feature == "Marsh":
        if thresholds is not None:
            moisture_strength = _band_centrality(moisture, thresholds.swamp_moisture, 1.0)
        else:
            moisture_strength = moisture
        return moisture_strength * (1.0 - elevation)  # marshes are lowland by definition

    if feature == "Forest":
        if thresholds is not None:
            return _band_centrality(moisture, thresholds.forest_moisture, thresholds.swamp_moisture)
        return moisture

    if feature == "Highlands":
        return elevation + mountain_strength

    if feature == "Plains":
        if thresholds is not None:
            elevation_strength = _band_centrality(elevation, thresholds.beach, thresholds.hills)
        else:
            elevation_strength = 1.0 - abs(elevation - 0.5)
        return elevation_strength * (1.0 - mountain_strength)  # low relief, not just mid elevation

    raise ValueError(f"Unknown region feature: {feature!r}")


def _region_boundary_between(world_map, current, neighbor):
    """Return whether a major river or distinct range separates two cells."""
    current_x, current_y = current
    neighbor_x, neighbor_y = neighbor
    direction = next(
        direction
        for direction, (dx, dy) in _DIRECTION_OFFSETS.items()
        if (current_x + dx, current_y + dy) == (neighbor_x, neighbor_y)
    )
    if direction in world_map.river_edges.get(current, set()):
        return True
    if _OPPOSITE_DIRECTION[direction] in world_map.river_edges.get(neighbor, set()):
        return True

    current_range = world_map.mountain_range_id.get(current)
    neighbor_range = world_map.mountain_range_id.get(neighbor)
    return (
        current_range is not None
        and neighbor_range is not None
        and current_range != neighbor_range
        and world_map.mountain_strength.get(*current) >= 0.12
        and world_map.mountain_strength.get(*neighbor) >= 0.12
    )


def _generate_world_rivers(world_map, num_rivers, min_spacing=5, ocean_threshold=DEEP_WATER):
    """
    Trace `num_rivers` major rivers across the world grid. Sources are
    selected from spaced mountain/highland cells, then each river follows
    the lowest unvisited neighboring elevation until it reaches the ocean
    or a suitable low basin. This is the same steepest-descent idea as the
    per-chunk flow field in world_generator, just at chunk granularity and
    without the meander -- a river spanning dozens of chunks doesn't need
    to wobble tile-by-tile to look natural. Each step records which edge of
    the source cell and entry edge of the destination cell the river crosses.

    Sourcing rivers from mountain/highland cells means they begin in
    believable headwaters rather than in ocean cells or arbitrary lowland
    noise peaks. The source candidates and downhill choices are sorted and
    scanned deterministically, so the same world seed always produces the
    same systems.

    `world_map.is_ocean` is the primary coastline signal. `ocean_threshold`
    remains as a low-water compatibility fallback for callers that provide
    an elevation cutoff; generate_world_map() passes the world's own
    computed BiomeThresholds.ocean here instead of relying on the fixed
    DEEP_WATER constant.
    """
    width, height = world_map.width, world_map.height

    highest_first = sorted(
        ((world_map.elevation.get(x, y), x, y) for y in range(height) for x in range(width)),
        reverse=True,
    )

    # Headwaters need geographic context: a high cell in an ocean is not a
    # useful source, while mountain influence or highland elevation gives a
    # source a plausible reason to exist. The lower threshold allows ranges
    # that are represented by a broad highland rather than a sharp ridge.
    highland_threshold = _value_at_percentile(world_map.elevation, 0.70)
    source_candidates = [
        (elevation, x, y)
        for elevation, x, y in highest_first
        if not world_map.is_ocean.get((x, y), False)
        and (
            world_map.mountain_strength.get(x, y) >= 0.15
            or elevation >= highland_threshold
        )
    ]

    sources = []
    for _, x, y in source_candidates:
        if len(sources) >= num_rivers:
            break
        if any(abs(x - sx) + abs(y - sy) < min_spacing for sx, sy in sources):
            continue
        sources.append((x, y))

    lowland_threshold = _value_at_percentile(world_map.elevation, 0.20)
    for start_x, start_y in sources:
        path = [(start_x, start_y)]
        visited = {(start_x, start_y)}
        current_x, current_y = start_x, start_y

        for _ in range(width + height):  # generous upper bound on river length
            current_elevation = world_map.elevation.get(current_x, current_y)
            if (
                world_map.is_ocean.get((current_x, current_y), False)
                or current_elevation < ocean_threshold
            ):
                break  # reached the ocean or a low-water endpoint
            if len(path) > 1 and current_elevation <= lowland_threshold:
                break  # reached a suitable low basin

            best_neighbor = None
            best_elevation = current_elevation

            for direction, (dx, dy) in _DIRECTION_OFFSETS.items():
                nx = (current_x + dx) % width
                ny = (current_y + dy) % height
                if (nx, ny) in visited:
                    continue

                neighbor_elevation = world_map.elevation.get(nx, ny)
                if world_map.is_ocean.get((nx, ny), False):
                    best_neighbor = (direction, nx, ny)
                    break  # prefer recording the coastline crossing
                if neighbor_elevation < best_elevation:
                    best_elevation = neighbor_elevation
                    best_neighbor = (direction, nx, ny)

            if best_neighbor is None:
                break  # local minimum with nowhere lower to flow — river ends here

            _, next_x, next_y = best_neighbor
            path.append((next_x, next_y))
            visited.add((next_x, next_y))
            current_x, current_y = next_x, next_y

        if len(path) > 1:
            _record_river_path(world_map, path)


def _record_river_path(world_map, path):
    """Mark, on every cell the river passes through, which edges it crosses."""
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        exit_direction = next(
            direction
            for direction, (dx, dy) in _DIRECTION_OFFSETS.items()
            if ((ax + dx) % world_map.width, (ay + dy) % world_map.height) == (bx, by)
        )
        entry_direction = _OPPOSITE_DIRECTION[exit_direction]

        world_map.river_edges.setdefault((ax, ay), set()).add(exit_direction)
        world_map.river_edges.setdefault((bx, by), set()).add(entry_direction)


def _apply_river_moisture(moisture, river_edges, width, height, radius=RIVER_MOISTURE_RADIUS, boost=RIVER_MOISTURE_BOOST):
    """Add a gradual moisture bonus around the existing major-river cells.

    The base climate remains intact: this only adds a bounded, distance-
    weighted signal after the climate field has been shaped. Toroidal
    distance matches the world's wrapped coarse grid, so a river near an
    edge does not create an artificial dry seam on the opposite side.
    """
    if not river_edges or radius <= 0 or boost <= 0:
        return

    river_cells = river_edges.keys()
    for y in range(height):
        for x in range(width):
            nearest_distance = min(
                math.hypot(
                    _toroidal_delta(x, river_x, width),
                    _toroidal_delta(y, river_y, height),
                )
                for river_x, river_y in river_cells
            )
            if nearest_distance > radius:
                continue

            falloff = 1.0 - nearest_distance / radius
            moisture.set(x, y, min(1.0, moisture.get(x, y) + boost * falloff))


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


def _generate_mountain_spines(rng, continentalness, width, height, num_ranges):
    """
    Walk `num_ranges` mountain ranges as ridge polylines, seeded on
    cells solidly on land by normalized continentalness
    (>= MOUNTAIN_LAND_THRESHOLD, well clear of the coast) and bent
    gradually as they walk, same shape of trick world_generator.py's own
    _generate_mountain_ridges() uses per-chunk -- just seeded from this
    world's continentalness field instead of a random point anywhere on
    the grid, so ranges land on the landmasses that exist, well inland,
    rather than wherever.

    Returns a list of spines, each a list of (x, y) points (floats, not
    yet wrapped onto the grid -- _apply_mountain_influence() below handles
    that per-sample so a range can walk across the toroidal seam).
    """
    land_cells = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if continentalness.get(x, y) >= MOUNTAIN_LAND_THRESHOLD
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

            sample = continentalness.get(int(x) % width, int(y) % height)
            if sample < MOUNTAIN_RANGE_CONTINUE_THRESHOLD:
                break  # walked off solid land toward the coast/ocean

        if len(spine) >= 3:
            spines.append(spine)

    return spines


def _apply_mountain_influence(mountain_map, range_id_map, spines, width, height):
    """
    Raise elevation-contribution strength near each mountain range's
    spine with distance falloff -- the same "ridge polyline -> heightmap"
    idea world_generator.py's _generate_ridge_heightmap() already uses
    per-chunk, at world scale. Overlapping ranges take the strongest
    influence rather than summing, so `mountain_map` stays in a
    predictable [0, 1] range without needing its own separate
    normalization pass; `range_id_map` records which range "won" at each
    cell, so mountain range membership stays queryable even where ranges
    overlap.
    """
    if not spines:
        return

    band_width = max(width, height) * MOUNTAIN_BAND_FRACTION

    for range_id, spine in enumerate(spines):
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
                        range_id_map[(x, y)] = range_id


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

    # continent_shape itself stays raw (unnormalized, can run negative
    # between continents) since mountain seeding and elevation blending
    # below rely on that raw falloff scale. continentalness is a separate,
    # percentile-normalized copy -- the actual [0, 1] field is_ocean and
    # future world_generator.py logic should read.
    for y in range(height):
        for x in range(width):
            world_map.continentalness.set(x, y, continent_shape.get(x, y))
    _percentile_normalize(world_map.continentalness)

    if num_mountain_ranges is None:
        num_mountain_ranges = max(3, (width * height) // 4000)
    mountain_spines = _generate_mountain_spines(rng, world_map.continentalness, width, height, num_mountain_ranges)
    world_map.mountain_ranges = mountain_spines
    _apply_mountain_influence(world_map.mountain_strength, world_map.mountain_range_id, mountain_spines, width, height)

    elevation_scale = max(width, height) / 6
    moisture_scale = max(width, height) / 4
    # The local layer varies ~5x faster than its macro counterpart --
    # frequent enough that neighboring chunks routinely diverge, not so
    # frequent that terrain reads as pure static instead of shaped land.
    local_elevation_scale = elevation_scale / 5
    local_moisture_scale = moisture_scale / 5

    # Regional relief: an independent fBm layer (own offset into the
    # permutation table, so it doesn't just echo continent_shape or the
    # fine detail layer below), normalized on its own so its highs/lows
    # are spread naturally rather than clustered near the mean.
    regional_relief = HeightMap(width, height)
    for y in range(height):
        for x in range(width):
            value = _fractal_noise(
                perm, (x + 3000) / elevation_scale, (y + 3000) / elevation_scale,
                REGIONAL_RELIEF_OCTAVES, REGIONAL_RELIEF_PERSISTENCE, REGIONAL_RELIEF_LACUNARITY,
            )
            regional_relief.set(x, y, (value + 1.0) / 2.0)
    _percentile_normalize(regional_relief)

    for y in range(height):
        for x in range(width):
            macro_elevation = (
                regional_relief.get(x, y) * _RELIEF_ELEVATION_SHARE
                + world_map.mountain_strength.get(x, y) * _MOUNTAIN_ELEVATION_SHARE
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
    _apply_climate(world_map.moisture, world_map.mountain_strength, width, height, prevailing_wind_dx)

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

    # Ocean/land is now a continentalness question, not an elevation one --
    # this is what keeps oceans and continents reading as a few large,
    # coherent shapes instead of following every local elevation wobble.
    continentalness_ocean_threshold = _value_at_percentile(world_map.continentalness, CONTINENTALNESS_OCEAN_PERCENTILE)
    world_map.continentalness_ocean_threshold = continentalness_ocean_threshold

    for y in range(height):
        for x in range(width):
            world_map.is_ocean[(x, y)] = world_map.continentalness.get(x, y) < continentalness_ocean_threshold

    # Rivers need the coastline classification to know where to stop, but
    # their moisture influence must be applied before biome thresholds and
    # regions are finalized.
    if num_rivers is None:
        num_rivers = max(3, (width * height) // 1800)

    river_thresholds = compute_biome_thresholds(world_map.elevation, world_map.moisture)
    _generate_world_rivers(world_map, num_rivers, ocean_threshold=river_thresholds.ocean)
    _apply_river_moisture(world_map.moisture, world_map.river_edges, width, height)

    # Distribution-aware cutoffs for the final climate field, including the
    # river contribution, so moisture affects classification without
    # replacing the underlying climate signal.
    thresholds = compute_biome_thresholds(world_map.elevation, world_map.moisture)
    world_map.biome_thresholds = thresholds

    for y in range(height):
        for x in range(width):
            world_biome = _classify_world_biome(world_map, x, y, thresholds)
            world_map.biomes[(x, y)] = _WORLD_BIOME_TO_CHUNK_BIOME[world_biome]

    _break_long_biome_runs(world_map)

    _generate_world_regions(
        world_map,
        rng,
        num_regions=num_regions,
        min_region_size=min_region_size,
        max_region_size=max_region_size,
    )
    _generate_world_roads(world_map)

    return world_map