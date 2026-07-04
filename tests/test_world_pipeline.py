import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "world" / "world_generator.py"

spec = importlib.util.spec_from_file_location("world_generator", MODULE_PATH)
world_generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world_generator)

from world import world_map as world_map_module


def test_generate_chunk_context_has_stage_data():
    class DummyGameMap:
        width = 8
        height = 8
        tiles = [[None for _ in range(8)] for _ in range(8)]

        def is_walkable(self, x, y):
            return True

    game_map = DummyGameMap()
    ctx = world_generator.generate_chunk_context(
        game_map,
        (0, 0),
        123,
        ChunkBiome=world_generator.ChunkBiome,
    )

    assert "heightmap" in ctx
    assert "moisture" in ctx
    assert "regions" in ctx
    assert "landmarks" in ctx
    assert "infrastructure" in ctx
    assert "population" in ctx
    assert "flavor" in ctx


def test_world_map_generates_region_graph_and_persistence():
    world_map = world_map_module.generate_world_map(123, width=20, height=20)

    sample_coord = (0, 0)
    assert world_map.region_at(sample_coord) is not None
    assert world_map.region_name_at(sample_coord) is not None

    region_id = world_map.region_at(sample_coord)
    assert region_id in world_map.region_graph
    assert world_map.region_graph[region_id]


def test_biome_generators_have_distinct_terrain_profiles():
    forest = world_generator.get_terrain_generator(world_generator.ChunkBiome.FOREST)()
    swamp = world_generator.get_terrain_generator(world_generator.ChunkBiome.SWAMP)()
    mountain = world_generator.get_terrain_generator(world_generator.ChunkBiome.MOUNTAINS)()
    plains = world_generator.get_terrain_generator(world_generator.ChunkBiome.PLAINS)()

    assert forest.terrain_tags() == ("forests", "rolling_hills", "streams")
    assert swamp.terrain_tags() == ("shallow_lakes", "mud_grass", "dead_trees")
    assert mountain.terrain_tags() == ("cliffs", "plateaus", "caves", "pine_forests")
    assert plains.terrain_tags() == ("open_grass", "scattered_trees", "gentle_hills")


def test_forest_generator_adds_nature_features():
    class DummyGameMap:
        width = 4
        height = 4
        tiles = [[world_generator.grass for _ in range(4)] for _ in range(4)]

    game_map = DummyGameMap()
    heightmap = world_generator.HeightMap(4, 4)
    moisture = world_generator.HeightMap(4, 4)

    for y in range(4):
        for x in range(4):
            heightmap.set(x, y, 0.2)
            moisture.set(x, y, 0.9)

    world_generator.ForestGenerator().apply(game_map, heightmap, moisture, set())

    assert any(tile is world_generator.pond for row in game_map.tiles for tile in row)
