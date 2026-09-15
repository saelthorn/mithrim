
import math
import heapq
import random
from dataclasses import dataclass
from enum import Enum

from world.noise import HeightMap, _build_permutation_table, _fractal_noise

# ---------------------------------------------------------------------------
# Biome vocabulary and classification
# ---------------------------------------------------------------------------
# WorldMap owns what a biome *is* -- these constants, ChunkBiome, and the
# threshold classifiers below used to live in a separate world_generator.py; geography
# and biome classification now live here, at both world grain
# (_classify_world_biome) and tile grain (classify_local_terrain) and for a
# single arbitrary (height, moisture) sample (_biome, still used by chunk
# materialization for patch-naming flavor and dungeon-placement scoring --
# see chunk_materializer.py). Nothing outside this module decides what a
# biome is; it only asks WorldMap.

DEEP_WATER = 0.12
SHALLOW_WATER = 0.18
PLAINS = 0.55
HILLS = 0.75
FOREST = 0.50
SWAMP = 0.72

BIOME_OCEAN = "ocean"
BIOME_BEACH = "beach"
BIOME_PLAINS = "plains"
BIOME_FOREST = "forest"
BIOME_SWAMP = "swamp"
BIOME_HILLS = "hills"
BIOME_MOUNTAINS = "mountains"


@dataclass(frozen=True)
class BiomeThresholds:
    """
    Elevation/moisture cutoffs _biome() classifies against.

    Field names keep the (slightly confusing) meaning the old bare
    module constants had: `hills` is the elevation a tile must reach to
    stop being plains/forest/swamp and start being hills (was PLAINS),
    `mountains` is the elevation to stop being hills and become
    mountains (was HILLS).

    The defaults below assume a roughly uniform [0, 1] input
    distribution, which is true of the per-chunk local heightmap/
    moisture grids chunk_materializer.py generates but is NOT reliably
    true of raw fBm noise in general -- summing several octaves is a
    Central-Limit-Theorem setup, so the result clusters near its mean no
    matter how far the endpoints are stretched. compute_biome_thresholds()
    below derives a distribution-aware BiomeThresholds instead (percentile
    lookups against the actual world, not these fixed values) so
    world-scale biome area fractions stay close to what these defaults
    imply regardless of how a given world seed's noise happens to be
    shaped.
    """
    ocean: float = DEEP_WATER
    beach: float = SHALLOW_WATER
    hills: float = PLAINS
    mountains: float = HILLS
    forest_moisture: float = FOREST
    swamp_moisture: float = SWAMP


DEFAULT_BIOME_THRESHOLDS = BiomeThresholds()


class ChunkBiome(Enum):
    PLAINS = "plains"
    FOREST = "forest"
    SWAMP = "swamp"
    HILLS = "hills"
    MOUNTAINS = "mountains"
    DESERT = "desert"
    TUNDRA = "tundra"
    OCEAN = "ocean"


def _biome(height, moisture, thresholds=None):
    """
    Classify a single (height, moisture) sample into a BIOME_* constant.

    `thresholds` defaults to DEFAULT_BIOME_THRESHOLDS (the original fixed
    cutoffs), so every existing call site -- chunk_materializer.py's
    per-patch flavor naming and dungeon-placement scoring -- is
    unaffected. generate_world_map() below passes its own
    distribution-aware BiomeThresholds when classifying world-scale
    cells; see BiomeThresholds' docstring for why that matters.
    """
    if thresholds is None:
        thresholds = DEFAULT_BIOME_THRESHOLDS

    if height < thresholds.ocean:
        return BIOME_OCEAN
    if height < thresholds.beach:
        return BIOME_BEACH
    if height >= thresholds.mountains:
        return BIOME_MOUNTAINS
    if height >= thresholds.hills:
        return BIOME_HILLS
    if moisture > thresholds.swamp_moisture:
        return BIOME_SWAMP
    if moisture > thresholds.forest_moisture:
        return BIOME_FOREST

    return BIOME_PLAINS


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
# Coastal band just above the ocean cutoff -- cells here read as beach/
# shallows rather than solid land. Same 0.06 gap DEFAULT_BIOME_THRESHOLDS
# already uses between its own ocean/beach elevation percentiles, applied
# to continentalness instead so land/water shape stays the authority.
CONTINENTALNESS_BEACH_PERCENTILE = CONTINENTALNESS_OCEAN_PERCENTILE + 0.06

# -- chunk-local geography tuning ---------------------------------------
# How hard a chunk's local elevation/moisture noise is pulled toward this
# WorldMap's own continuous surface (see WorldMap._bias_grid_toward_surface).
# Elevation is biased harder than moisture -- mountain ranges and coastlines
# need to read as coherent multi-chunk shapes, moisture can stay noisier.
WORLD_ELEVATION_BIAS_STRENGTH = 0.35
WORLD_MOISTURE_BIAS_STRENGTH = 0.20
# How much of the continuous mountain_strength field gets floored into a
# chunk's local elevation (see WorldMap._apply_mountain_floor) -- keeps a
# world-scale range from disappearing at a chunk boundary.
WORLD_MOUNTAIN_FLOOR_STRENGTH = 0.78

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
# still handled by chunk_materializer.py.
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

# -- region growth cost -------------------------------------------------
# Base cost of extending a region by one cell on perfectly uniform terrain
# -- with everything else below at zero, this reduces to plain nearest-
# seed distance, so regions only diverge from that baseline where the
# terrain underneath actually changes.
REGION_GROWTH_STEP_COST = 1.0
# Elevation is the single strongest visual signal for a natural boundary
# (a ridge, a cliff, a valley wall), so it dominates the cost -- weighted
# well above moisture and biome below so a real elevation change reliably
# outweighs them.
REGION_GROWTH_ELEVATION_WEIGHT = 6.0
# Moisture/climate transitions (forest thinning into plains, plains
# drying into something sparser) are a real but gentler boundary cue than
# a wall of elevation, so this stays well under the elevation weight.
REGION_GROWTH_MOISTURE_WEIGHT = 3.0
# Flat penalty for stepping into a different (but still adjacency-legal --
# see _biomes_are_adjacent) biome, on top of whatever elevation/moisture
# gap caused it, so a biome edge is never entirely free to cross even when
# the underlying numbers are close.
REGION_GROWTH_BIOME_TRANSITION_COST = 1.5
# Soft, not hard: crossing a major river or a distinct mountain range
# (see _region_boundary_between) costs about six extra steps' worth of
# distance rather than being forbidden outright, so growth usually stops
# at one without it being a rule that every river/range must become a
# region edge -- a region can still cross one where growth pressure from
# every other direction is blocked and that's the only way to reach
# unclaimed ground.
REGION_GROWTH_BARRIER_COST = 6.0


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


# ---------------------------------------------------------------------------
# Chunk-local geography generation
# ---------------------------------------------------------------------------
# The elevation/moisture detail a single chunk carries on top of this
# WorldMap's own coarse fields -- moved here from the old world_generator.py so
# elevation/moisture generation lives in one place (WorldMap) rather than
# being split across files. chunk_materializer.py's standalone (no
# WorldMap) fallback still uses these directly; WorldMap.generate_chunk_geography()
# is the normal, WorldMap-driven path everything else goes through.

def _generate_mountain_ridges(width, height, rng=None):
    """
    Creates several long mountain ridges.

    These are NOT mountains yet.
    They're just polylines that later become elevation.
    """
    rng = rng or random
    ridges = []

    ridge_count = max(3, (width * height) // 20000)

    for _ in range(ridge_count):
        x = rng.randint(width // 5, width * 4 // 5)
        y = rng.randint(height // 5, height * 4 // 5)

        angle = rng.uniform(0, math.pi * 2)
        ridge = []

        length = rng.randint(
            min(width, height) // 3,
            min(width, height) // 2
        )

        for _ in range(length):
            ridge.append((int(x), int(y)))
            # slowly bend
            angle += rng.uniform(-0.25, 0.25)

            x += math.cos(angle)
            y += math.sin(angle)

            if x < 2 or x >= width - 2:
                break
            if y < 2 or y >= height - 2:
                break

        ridges.append(ridge)

    return ridges


def _generate_ridge_heightmap(width, height, rng=None):
    """
    Builds a heightmap from mountain ridges instead of Perlin noise.
    """
    ridges = _generate_mountain_ridges(width, height, rng=rng)
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

            value = (heightmap.get(x, y) - minimum) / scale
            value = value * 0.85 + 0.08

            heightmap.set(x, y, value)


def _generate_moisture_map(perm, chunk_x, chunk_y, width, height, scale, octaves=4, persistence=0.5, lacunarity=2.0):
    """
    Generates a normalized moisture map.
    Values range from 0.0 to 1.0.
    """
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


class WorldMap:
    """
    Coarse, persistent, world-scale terrain data: one elevation/moisture/
    biome value per chunk, plus which chunks carry a major river and which
    of their edges it crosses. Generated once per game (see
    generate_world_map) and consulted by chunk_materializer.materialize_overworld_chunk
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
        # re-derived by chunk generation -- chunk_materializer.py only reads
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
        # Same idea, one band further inland -- the continentalness value
        # below which a *tile* (not a whole world-map cell) reads as
        # coastal/beach rather than solid land. See classify_local_terrain().
        self.continentalness_beach_threshold = None

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

    def _bilinear_sample(self, grid, chunk_coord, fx, fy):
        """Sample `grid` (elevation/moisture/continentalness/mountain_strength
        -- any HeightMap this world map owns) continuously inside a chunk,
        where (fx, fy) in [0, 1] is a tile's position within it -- fx=fy=0
        is the chunk's own top-left corner, fx=fy=1 its bottom-right.

        Bilinearly blends this cell's value with its wrapped right/down/
        diagonal neighbors, the same trick the old per-chunk mountain-floor
        biasing used, generalized to any field: a chunk's edge (fx or fy at
        0 or 1) always lands exactly on the shared world-map cell value its
        neighboring chunk's opposite edge also lands on, so the sampled
        field is continuous across chunk boundaries with no seam.
        """
        grid_x, grid_y = self._to_grid(chunk_coord)
        x1 = (grid_x + 1) % self.width
        y1 = (grid_y + 1) % self.height
        return (
            grid.get(grid_x, grid_y) * (1 - fx) * (1 - fy)
            + grid.get(x1, grid_y) * fx * (1 - fy)
            + grid.get(grid_x, y1) * (1 - fx) * fy
            + grid.get(x1, y1) * fx * fy
        )

    def elevation_at_subtile(self, chunk_coord, fx, fy):
        return self._bilinear_sample(self.elevation, chunk_coord, fx, fy)

    def moisture_at_subtile(self, chunk_coord, fx, fy):
        return self._bilinear_sample(self.moisture, chunk_coord, fx, fy)

    def continentalness_at_subtile(self, chunk_coord, fx, fy):
        return self._bilinear_sample(self.continentalness, chunk_coord, fx, fy)

    def mountain_strength_at_subtile(self, chunk_coord, fx, fy):
        return self._bilinear_sample(self.mountain_strength, chunk_coord, fx, fy)

    def classify_local_terrain(self, elevation, moisture, continentalness, mountain_strength):
        """
        Tile-grained analog of _classify_world_biome(): the same
        elevation/mountain/moisture rules, evaluated against continuously
        sampled values (see the *_at_subtile() accessors above) instead of
        one flat value per world-map cell. Returns a ChunkBiome.

        Because the inputs are continuous, calling this once per tile
        across a chunk -- rather than once for the whole chunk -- makes a
        chunk's local terrain grade smoothly through ocean/beach/plains/
        forest/swamp/hills/mountains wherever the underlying fields do,
        instead of jumping between whichever two single biomes two
        neighboring chunks' own world-map cells happened to be classified
        as.
        """
        if continentalness < self.continentalness_ocean_threshold:
            return ChunkBiome.OCEAN
        if continentalness < self.continentalness_beach_threshold:
            return ChunkBiome.PLAINS

        thresholds = self.biome_thresholds
        if elevation >= thresholds.mountains or mountain_strength >= 0.40:
            return ChunkBiome.MOUNTAINS
        if elevation >= thresholds.hills or mountain_strength >= 0.12:
            return ChunkBiome.HILLS
        if moisture > thresholds.swamp_moisture:
            return ChunkBiome.SWAMP
        if moisture > thresholds.forest_moisture:
            return ChunkBiome.FOREST
        return ChunkBiome.PLAINS

    def local_terrain_mask(self, chunk_coord, heightmap, moisture, width, height):
        """
        Per-tile ChunkBiome classification for one chunk -- the geographic
        condition of every tile in it, not just one discrete biome for the
        whole chunk. `heightmap`/`moisture` are that chunk's own local
        grids (see generate_chunk_geography()), already continuous across
        chunk boundaries; continentalness/mountain_strength are sampled
        straight from this WorldMap per tile. Chunk materialization (see
        chunk_materializer.py's _paint_chunk_terrain()) only ever consumes
        this result -- it never decides biome placement itself.
        """
        mask = [[None for _ in range(width)] for _ in range(height)]
        for y in range(height):
            fy = (y + 0.5) / height
            for x in range(width):
                fx = (x + 0.5) / width
                continentalness = self.continentalness_at_subtile(chunk_coord, fx, fy)
                mountain_strength = self.mountain_strength_at_subtile(chunk_coord, fx, fy)
                mask[y][x] = self.classify_local_terrain(
                    heightmap.get(x, y), moisture.get(x, y), continentalness, mountain_strength,
                )
        return mask

    def _bias_grid_toward_surface(self, grid, chunk_coord, world_grid, strength):
        """
        Nudge a chunk-local tile grid (elevation or moisture) toward this
        WorldMap's continuous surface for that grid, so the broad
        geographic signal comes from WorldMap rather than from an
        independently-generated per-chunk decision. Local detail is only
        shifted, not replaced, so per-tile variation survives.
        """
        for y in range(grid.height):
            fy = (y + 0.5) / grid.height
            for x in range(grid.width):
                fx = (x + 0.5) / grid.width
                world_value = self._bilinear_sample(world_grid, chunk_coord, fx, fy)
                local_value = grid.get(x, y)
                biased = local_value + (world_value - 0.5) * strength
                grid.set(x, y, min(1.0, max(0.0, biased)))

    def _apply_mountain_floor(self, heightmap, chunk_coord):
        """
        Raise a chunk's local elevation to at least this WorldMap's
        continuous mountain envelope, so a persistent world-scale range
        doesn't disappear at a chunk boundary just because the local ridge
        noise happened to dip there.
        """
        width, height = heightmap.width, heightmap.height
        for y in range(height):
            fy = (y + 0.5) / height
            for x in range(width):
                fx = (x + 0.5) / width
                strength = self.mountain_strength_at_subtile(chunk_coord, fx, fy)
                floor = strength * WORLD_MOUNTAIN_FLOOR_STRENGTH
                heightmap.set(x, y, max(heightmap.get(x, y), floor))

    def generate_chunk_geography(self, chunk_coord, world_seed, width, height, rng=None):
        """
        The single entry point chunk materialization calls to find out
        what one chunk's geography actually is. Returns
        (heightmap, moisture, local_terrain):

          - heightmap/moisture: per-tile HeightMap grids -- local ridge/
            Perlin detail biased toward this WorldMap's continuous
            elevation/moisture fields, so they read as one continuous
            surface across chunk boundaries rather than independently
            decided per chunk.
          - local_terrain: a height x width grid of ChunkBiome, one per
            tile (see local_terrain_mask()).

        This is the WorldMap-data half of the
        "WorldMap data -> terrain materialization -> GameMap" pipeline --
        chunk_materializer.py's job starts only once this returns; it never
        generates or overrides geography of its own.

        `rng` is normally a chunk-scoped deterministic Random the caller
        already seeded from (world_seed, chunk_coord) -- see
        chunk_materializer.py's _chunk_materialization_rng(). If none is
        given, one is derived here from (world_seed, chunk_coord), the same
        integer-mixing scheme _chunk_materialization_rng() uses, rather
        than falling back to the shared global `random` module further
        down the call chain, so this method is deterministic on its own
        and safe to call directly, not only through chunk_materializer.py.
        """
        if rng is None:
            rng = random.Random(
                (world_seed * 1_000_003) ^ (chunk_coord[0] * 92_821) ^ (chunk_coord[1] * 68_917)
            )

        heightmap = _generate_ridge_heightmap(width, height, rng=rng)
        self._bias_grid_toward_surface(heightmap, chunk_coord, self.elevation, WORLD_ELEVATION_BIAS_STRENGTH)
        self._apply_mountain_floor(heightmap, chunk_coord)

        perm = _build_permutation_table(world_seed)
        moisture = _generate_moisture_map(
            perm, chunk_coord[0], chunk_coord[1], width, height, scale=max(width, height) / 10,
        )
        self._bias_grid_toward_surface(moisture, chunk_coord, self.moisture, WORLD_MOISTURE_BIAS_STRENGTH)

        local_terrain = self.local_terrain_mask(chunk_coord, heightmap, moisture, width, height)
        return heightmap, moisture, local_terrain

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
    directly (WorldMap._bias_grid_toward_surface(), for one).
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
# match the *intent* of DEFAULT_BIOME_THRESHOLDS' fixed
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
    Derive a BiomeThresholds from the *actual*
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


def _region_growth_cost(world_map, current, neighbor):
    """
    Cost of a region extending one step from `current` into `neighbor`.
    Built entirely from the elevation/moisture/biome/river/mountain-range
    data at those two cells -- on flat, uniform terrain this is just
    REGION_GROWTH_STEP_COST everywhere, so growth reduces to ordinary
    nearest-seed distance; it only rises where the terrain underneath
    actually changes, which is what lets a boundary settle along a real
    ridge, riverbank, or climate transition instead of an arbitrary line.
    """
    elevation_delta = abs(world_map.elevation.get(*current) - world_map.elevation.get(*neighbor))
    moisture_delta = abs(world_map.moisture.get(*current) - world_map.moisture.get(*neighbor))

    cost = REGION_GROWTH_STEP_COST
    cost += elevation_delta * REGION_GROWTH_ELEVATION_WEIGHT
    cost += moisture_delta * REGION_GROWTH_MOISTURE_WEIGHT

    if world_map.biomes.get(current) is not world_map.biomes.get(neighbor):
        cost += REGION_GROWTH_BIOME_TRANSITION_COST

    if _region_boundary_between(world_map, current, neighbor):
        cost += REGION_GROWTH_BARRIER_COST

    return cost


def _grow_regions_by_cost(world_map, selected_seeds, max_region_size):
    """
    Multi-source flood fill: every seed grows outward simultaneously and
    each cell is claimed by whichever seed can reach it most cheaply (see
    _region_growth_cost), not whichever seed is nearest in a straight
    line. The ocean/land split and biologically-implausible biome
    adjacency (see _biomes_are_adjacent) are still hard boundaries no
    region ever crosses; a river or a distinct mountain range is only a
    steep cost, so a region can still span one where growth pressure from
    every other direction leaves no cheaper path to unclaimed ground.

    `max_region_size` is an optional hard cap (None means uncapped) on
    how many cells one region may claim -- once reached, that region's
    frontier stops advancing and every other seed keeps growing to fill
    what's left.
    """
    width, height = world_map.width, world_map.height
    region_grid = [[None for _ in range(width)] for _ in range(height)]
    region_cost = [[math.inf for _ in range(width)] for _ in range(height)]
    region_seeds = {}
    region_labels = []
    claimed_count = {}

    frontier = []
    for region_id, (seed_x, seed_y, feature) in enumerate(selected_seeds, start=1):
        label = f"{feature}-{region_id}"
        region_seeds[label] = (seed_x, seed_y)
        region_labels.append(label)
        claimed_count[label] = 1
        region_grid[seed_y][seed_x] = label
        region_cost[seed_y][seed_x] = 0.0
        heapq.heappush(frontier, (0.0, seed_y, seed_x, label))

    while frontier:
        cost, cy, cx, label = heapq.heappop(frontier)
        if region_grid[cy][cx] != label or cost > region_cost[cy][cx]:
            continue  # a cheaper claim already won this cell
        if max_region_size is not None and claimed_count[label] >= max_region_size:
            continue  # this region has already claimed its full allowance

        seed_is_ocean = world_map.is_ocean[region_seeds[label]]
        current_biome = world_map.biomes[(cx, cy)]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if world_map.is_ocean[(nx, ny)] != seed_is_ocean:
                continue  # never grow a region across the coastline
            if not _biomes_are_adjacent(current_biome, world_map.biomes[(nx, ny)]):
                continue  # never grow a region across a biologically implausible seam

            new_cost = cost + _region_growth_cost(world_map, (cx, cy), (nx, ny))
            if new_cost < region_cost[ny][nx]:
                region_cost[ny][nx] = new_cost
                previous_owner = region_grid[ny][nx]
                if previous_owner is not None:
                    claimed_count[previous_owner] -= 1
                region_grid[ny][nx] = label
                claimed_count[label] += 1
                heapq.heappush(frontier, (new_cost, ny, nx, label))

    # Defensive fallback: a cell can only be left unreached if it's boxed
    # in entirely by the opposite ocean/land class or an implausible
    # biome seam with no seed of its own on its side -- assign any such
    # leftover cell to its nearest same-class seed by plain distance.
    for y in range(height):
        for x in range(width):
            if region_grid[y][x] is not None:
                continue
            is_ocean = world_map.is_ocean[(x, y)]
            candidates = [
                label for label in region_labels
                if world_map.is_ocean[region_seeds[label]] == is_ocean
            ] or region_labels
            region_grid[y][x] = min(
                candidates,
                key=lambda current_label: abs(x - region_seeds[current_label][0]) + abs(y - region_seeds[current_label][1]),
            )

    return region_grid, region_seeds, region_labels


def _region_cells_from_grid(region_grid, region_labels):
    region_cells = {label: [] for label in region_labels}
    for y, row in enumerate(region_grid):
        for x, label in enumerate(row):
            region_cells[label].append((x, y))
    return region_cells


def _merge_undersized_regions(world_map, region_grid, region_cells, region_labels, region_seeds, min_region_size):
    """
    Fold any region smaller than `min_region_size` cells into whichever
    neighboring region shares the most border with it -- a seed that got
    boxed in early by faster-growing (or more favorably placed) neighbors
    shouldn't linger as a degenerate sliver. Labels are always processed
    in sorted order, and ties on which neighbor to merge into are broken
    the same way, so the result never depends on dict/set iteration order.
    """
    width, height = world_map.width, world_map.height
    changed = True
    while changed:
        changed = False
        for label in sorted(region_labels):
            if label not in region_cells or len(region_labels) <= 1:
                continue
            cells = region_cells[label]
            if len(cells) >= min_region_size:
                continue

            border_counts = {}
            for x, y in cells:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    neighbor_label = region_grid[ny][nx]
                    if neighbor_label != label:
                        border_counts[neighbor_label] = border_counts.get(neighbor_label, 0) + 1

            if not border_counts:
                continue  # isolated with nothing to merge into -- leave it

            target = max(sorted(border_counts), key=border_counts.get)

            for x, y in cells:
                region_grid[y][x] = target
            region_cells[target].extend(cells)
            del region_cells[label]
            region_labels.remove(label)
            region_seeds.pop(label, None)
            changed = True

    return region_grid, region_cells, region_labels, region_seeds


def _generate_world_regions(world_map, rng, num_regions=None, min_region_size=4, max_region_size=None):
    """
    Generate a coarse region graph for the world map using geography-aware
    seeded growth. Seeds favor mountain ranges, river valleys, coasts, and
    broad climate/terrain masses before filling remaining slots from the
    strongest unclaimed geographic features. Every seed then grows
    simultaneously and competes for territory by cost (see
    _region_growth_cost) rather than straight-line distance, so a
    region's shape follows real elevation/moisture/biome continuity
    instead of settling on an arbitrary bisector between two seeds.
    Rivers and distinct mountain ranges are steep but not absolute costs
    to cross, and the ocean/land split is still never crossed. `rng` is
    unused now that growth is fully cost-driven, but is kept in the
    signature since callers already pass it.
    """
    width, height = world_map.width, world_map.height
    if num_regions is None:
        num_regions = max(8, (width * height) // 500)

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

    region_grid, region_seeds, region_labels = _grow_regions_by_cost(world_map, selected_seeds, max_region_size)
    region_cells = _region_cells_from_grid(region_grid, region_labels)
    region_grid, region_cells, region_labels, region_seeds = _merge_undersized_regions(
        world_map, region_grid, region_cells, region_labels, region_seeds, min_region_size,
    )

    for label, cells in region_cells.items():
        for x, y in cells:
            world_map.set_region((x, y), label)

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
    per-chunk flow field in chunk_materializer.py, just at chunk granularity and
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
    gradually as they walk, same shape of trick this module's own
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
    idea this module's own _generate_ridge_heightmap() already uses
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


# ---------------------------------------------------------------------------
# generate_world_map(): the WorldMap generation pipeline
# ---------------------------------------------------------------------------
# WorldMap is the single authoritative procedural world model. Everything
# below builds one WorldMap in clearly separated stages -- each stage is a
# small orchestrator function operating on fields the previous stage(s)
# already finalized, never on anything a later stage will still change.
# This is what keeps the pipeline generation-order independent *within a
# single world*: every stage is a pure function of the WorldMap state that
# already exists, computed once, up front, for the whole coarse grid --
# never per chunk and never re-derived on demand.
#
#   1. WORLD SEED               -- _init_world_seed
#   2. MACRO GEOGRAPHY          -- _generate_macro_geography
#        continentalness, elevation, mountain ranges, ocean/land
#   3. CLIMATE                  -- _generate_climate
#        moisture (temperature is not modeled in this game yet)
#   4. WORLD FEATURES: rivers   -- _generate_rivers
#   5. DERIVED TERRAIN CONDITIONS -- _generate_derived_terrain_conditions
#        biome thresholds + classification (coastal/mountain/wetland/
#        forest/plains conditions all fall out of the same elevation/
#        moisture/continentalness/mountain_strength fields -- see
#        classify_local_terrain() below for the chunk-grain version)
#   6. REGIONS                  -- _generate_world_regions (region identity,
#        names, flavor, transitions -- already its own well-scoped stage)
#   7. WORLD FEATURES: roads    -- _generate_world_roads
#
# Stage 4 (rivers) runs *before* stage 5 (biome classification) even though
# the suggested numbering above lists "world features" after "derived
# terrain conditions": rivers raise moisture along their banks, and biome
# classification has to see that raised moisture to classify a riverbank
# as swamp/forest rather than whatever it would've been without a river
# nearby. Stage 7 (roads) runs *after* regions, not alongside rivers in
# one "world features" stage, because roads connect region centers and
# don't exist as a concept until regions do. Both are genuine data
# dependencies in this codebase, not arbitrary choices -- see each stage
# function's docstring.
#
# Settlements, structures, and landmarks are deliberately NOT generated
# here. They're a chunk_materializer.py concern: rolled per chunk, on
# demand, the first time a chunk is visited (see _place_town()/_place_pois()
# there) rather than persisted as world-scale WorldMap data. WorldMap stays
# a coarse model of the world's *geography*; where a given player's game
# happens to place a town is fine detail, generated lazily, exactly like
# the rest of chunk materialization.


def _init_world_seed(world_seed):
    """
    Stage 1: WORLD SEED.

    Two different, unrelated seeds derived from world_seed: `perm` for
    Perlin detail noise (a different corner of the permutation table than
    per-chunk generation uses, so coarse world layout and fine per-chunk
    detail don't end up correlated), `rng` for everything that needs
    ordinary randomness (continent cores, mountain walks) -- kept as a
    local random.Random rather than the global `random` module so world
    generation stays reproducible for a given world_seed regardless of
    what else in the process has touched the global RNG.
    """
    perm = _build_permutation_table(world_seed ^ 0x5EED)
    rng = random.Random(world_seed ^ 0xC0FFEE)
    return perm, rng


def _generate_regional_relief(perm, width, height, elevation_scale):
    """
    An independent fBm layer feeding elevation (see _generate_elevation) --
    its own offset into the permutation table, so it doesn't just echo
    continent_shape or elevation's own local detail layer, normalized on
    its own so its highs/lows are spread naturally rather than clustered
    near the mean.
    """
    regional_relief = HeightMap(width, height)
    for y in range(height):
        for x in range(width):
            value = _fractal_noise(
                perm, (x + 3000) / elevation_scale, (y + 3000) / elevation_scale,
                REGIONAL_RELIEF_OCTAVES, REGIONAL_RELIEF_PERSISTENCE, REGIONAL_RELIEF_LACUNARITY,
            )
            regional_relief.set(x, y, (value + 1.0) / 2.0)
    _percentile_normalize(regional_relief)
    return regional_relief


def _generate_elevation(world_map, perm, regional_relief, width, height, elevation_scale, local_detail_weight):
    """Blend regional relief + mountain influence (macro) with a faster
    local fBm layer into world_map.elevation."""
    local_elevation_scale = elevation_scale / 5
    for y in range(height):
        for x in range(width):
            macro_elevation = (
                regional_relief.get(x, y) * _RELIEF_ELEVATION_SHARE
                + world_map.mountain_strength.get(x, y) * _MOUNTAIN_ELEVATION_SHARE
            )
            detail = (_fractal_noise(perm, x / local_elevation_scale, y / local_elevation_scale, 4, 0.5, 2.0) + 1.0) / 2.0
            world_map.elevation.set(x, y, macro_elevation * (1.0 - local_detail_weight) + detail * local_detail_weight)


def _classify_ocean_land(world_map, width, height):
    """
    Ocean/land distribution: a continentalness question, not an elevation
    one -- this is what keeps oceans and continents reading as a few
    large, coherent shapes instead of following every local elevation
    wobble. Also records the beach threshold one band further inland (see
    classify_local_terrain()'s tile-grain use of it).
    """
    ocean_threshold = _value_at_percentile(world_map.continentalness, CONTINENTALNESS_OCEAN_PERCENTILE)
    world_map.continentalness_ocean_threshold = ocean_threshold
    world_map.continentalness_beach_threshold = _value_at_percentile(world_map.continentalness, CONTINENTALNESS_BEACH_PERCENTILE)

    for y in range(height):
        for x in range(width):
            world_map.is_ocean[(x, y)] = world_map.continentalness.get(x, y) < ocean_threshold


def _generate_macro_geography(world_map, rng, perm, width, height, num_continents, num_mountain_ranges, elevation_curve, local_detail_weight):
    """
    Stage 2: MACRO GEOGRAPHY -- continentalness, elevation, mountain
    ranges, ocean/land distribution. Everything downstream (climate,
    rivers, biomes, regions) treats these fields as settled once this
    stage returns.
    """
    if num_continents is None:
        num_continents = max(3, (width * height) // 3500)
    continent_shape, continent_id = _generate_continents(rng, width, height, num_continents)
    world_map.continent_id = continent_id

    # continent_shape itself stays raw (unnormalized, can run negative
    # between continents) since mountain seeding and elevation blending
    # below rely on that raw falloff scale. continentalness is a separate,
    # percentile-normalized copy -- the actual [0, 1] field is_ocean and
    # chunk_materializer.py read.
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
    # The local layer varies ~5x faster than its macro counterpart --
    # frequent enough that neighboring chunks routinely diverge, not so
    # frequent that terrain reads as pure static instead of shaped land --
    # see _generate_elevation()'s local_elevation_scale.
    regional_relief = _generate_regional_relief(perm, width, height, elevation_scale)
    _generate_elevation(world_map, perm, regional_relief, width, height, elevation_scale, local_detail_weight)

    # Summing several octaves of noise (fBm) statistically pulls the result
    # toward the middle of its range -- it's rare for every octave to line up
    # near an extreme at once. A plain min/max stretch only fixes the
    # *endpoints*; the bulk of cells still cluster near the mean, so a fixed
    # cutoff like "elevation >= 0.75" barely ever fires. Percentile
    # normalization fixes the actual distribution instead of just its
    # extremes -- see _percentile_normalize()'s docstring.
    _percentile_normalize(world_map.elevation)
    # Optional art/tuning knob -- a no-op unless a curve is supplied. Applied
    # after percentile normalization so it's reshaping an already-uniform
    # distribution on purpose, not fighting the same clustering above fixes.
    _apply_curve(world_map.elevation, elevation_curve)

    _classify_ocean_land(world_map, width, height)

    return elevation_scale


def _generate_climate(world_map, perm, width, height, moisture_curve, local_detail_weight, prevailing_wind_dx):
    """
    Stage 3: CLIMATE -- moisture, shaped by mountain rain shadows.
    Temperature isn't modeled by this game yet; moisture is the only
    climate field WorldMap currently carries.
    """
    moisture_scale = max(width, height) / 4
    local_moisture_scale = moisture_scale / 5
    for y in range(height):
        for x in range(width):
            # Offset the sample point for moisture so it isn't just a
            # scaled copy of the elevation noise.
            macro_moisture = (_fractal_noise(perm, (x + 1000) / moisture_scale, (y + 1000) / moisture_scale, 4, 0.5, 2.0) + 1.0) / 2.0
            local_moisture = (_fractal_noise(perm, (x + 6000) / local_moisture_scale, (y + 6000) / local_moisture_scale, 2, 0.5, 2.0) + 1.0) / 2.0
            world_map.moisture.set(x, y, macro_moisture * (1.0 - local_detail_weight) + local_moisture * local_detail_weight)

    # Climate reacts to the shape macro geography already decided --
    # latitude and mountain rain shadows -- before percentile
    # normalization, so the nudge just shifts a cell's rank rather than
    # needing its own separate rescale.
    _apply_climate(world_map.moisture, world_map.mountain_strength, width, height, prevailing_wind_dx)
    _percentile_normalize(world_map.moisture)
    _apply_curve(world_map.moisture, moisture_curve)


def _generate_rivers(world_map, width, height, num_rivers):
    """
    Stage 4: WORLD FEATURES (rivers). Runs before stage 5's biome
    classification on purpose: a river raises moisture along its banks
    (see _apply_river_moisture), and that raised moisture has to be in
    place before biome thresholds/classification run, or a riverbank
    would classify as whatever it would've been with no river nearby.
    The ocean threshold used here to decide where a river "reaches the
    sea" is a preliminary one, computed from pre-river moisture; stage 5
    computes the real, final BiomeThresholds afterward.
    """
    if num_rivers is None:
        num_rivers = max(3, (width * height) // 1800)

    river_thresholds = compute_biome_thresholds(world_map.elevation, world_map.moisture)
    _generate_world_rivers(world_map, num_rivers, ocean_threshold=river_thresholds.ocean)
    _apply_river_moisture(world_map.moisture, world_map.river_edges, width, height)


def _generate_derived_terrain_conditions(world_map, width, height):
    """
    Stage 5: DERIVED TERRAIN CONDITIONS -- biome thresholds and
    classification. Coastal, mountain, wetland, forest, and plains
    conditions are not separate systems here: they all fall out of the
    same elevation/moisture/continentalness/mountain_strength fields
    through one distribution-aware BiomeThresholds and
    _classify_world_biome() (see classify_local_terrain() below for the
    tile-grain version chunk materialization samples).
    """
    thresholds = compute_biome_thresholds(world_map.elevation, world_map.moisture)
    world_map.biome_thresholds = thresholds

    for y in range(height):
        for x in range(width):
            world_biome = _classify_world_biome(world_map, x, y, thresholds)
            world_map.biomes[(x, y)] = _WORLD_BIOME_TO_CHUNK_BIOME[world_biome]

    _break_long_biome_runs(world_map)


def generate_world_map(
    world_seed,
    width=WORLD_MAP_WIDTH,
    height=WORLD_MAP_HEIGHT,
    num_rivers=None,
    num_regions=None,
    min_region_size=4,
    max_region_size=None,
    elevation_curve=None,
    moisture_curve=None,
    local_detail_weight=0.35,
    num_continents=None,
    num_mountain_ranges=None,
    prevailing_wind_dx=1,
):
    """
    Generate the coarse, persistent WorldMap for a game: the single
    authoritative procedural world model, built in clearly separated
    stages (see the module-level comment above this function). This is
    cheap (width * height cells, not width * height * chunk_size tiles)
    so it's generated once, up front, rather than lazily per chunk like
    the fine-grained terrain chunk_materializer.py produces on demand --
    WorldMap models the world; chunk_materializer.py materializes the
    playable area, one chunk at a time, only when a chunk is actually
    needed (see generate_chunk_geography() below).

    `num_continents`/`num_mountain_ranges` default to a handful scaled by
    grid area -- pass explicit values to make a seed feel more fragmented
    (more, smaller continents) or more monolithic.

    `prevailing_wind_dx` controls which side of a mountain range reads as
    its rain shadow (see _apply_climate()).

    `elevation_curve`/`moisture_curve` are optional shaping-curve
    callables (see power_curve()/smoothstep_curve() above) applied after
    percentile normalization, for controlling how mountainous/wet the
    world *feels* without touching biome area fractions -- those are
    always derived fresh from whatever distribution the grids end up
    with, via compute_biome_thresholds().

    `local_detail_weight` (0..1) controls how much fine per-cell noise is
    blended on top of the macro shape (continents + mountain ranges) --
    higher means neighboring chunks diverge in biome more readily, lower
    keeps terrain reading as large, geographically coherent masses.

    Every stage below is a pure function of WorldMap state the previous
    stage(s) already finalized -- nothing here depends on chunk
    generation order, and nothing in chunk generation feeds back into
    these fields once this function returns.
    """
    world_map = WorldMap(width, height)

    # Stage 1: WORLD SEED
    perm, rng = _init_world_seed(world_seed)

    # Stage 2: MACRO GEOGRAPHY
    _generate_macro_geography(
        world_map, rng, perm, width, height,
        num_continents, num_mountain_ranges, elevation_curve, local_detail_weight,
    )

    # Stage 3: CLIMATE
    _generate_climate(world_map, perm, width, height, moisture_curve, local_detail_weight, prevailing_wind_dx)

    # Stage 4: WORLD FEATURES -- rivers (before biome classification; see
    # _generate_rivers()'s docstring for why)
    _generate_rivers(world_map, width, height, num_rivers)

    # Stage 5: DERIVED TERRAIN CONDITIONS
    _generate_derived_terrain_conditions(world_map, width, height)

    # Stage 6: REGIONS
    _generate_world_regions(
        world_map, rng,
        num_regions=num_regions, min_region_size=min_region_size, max_region_size=max_region_size,
    )

    # Stage 7: WORLD FEATURES -- roads (after regions; connects region
    # centers, so roads aren't a meaningful concept until regions exist)
    _generate_world_roads(world_map)

    return world_map