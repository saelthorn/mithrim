import random
from dataclasses import dataclass, field

from world import tile

from entities.monster import (
    Cultist, CultAcolyte, CultFanatic, Imp, GiantRat, GiantSpider,
    Skeleton, SkeletonArcher, Ghoul, Wraith,
)


@dataclass(frozen=True, eq=False)
class DungeonFloorProfile:
    name: str
    room_props: tuple = None
    prop_chance: float = None
    nave_rooms: tuple = (0, 0)
    crypt_rooms: tuple = None
    sanctum: bool = False


@dataclass(frozen=True, eq=False)
class DungeonTheme:
    key: str
    name: str
    floor_range: tuple = None
    monster_tiers: dict = None
    boss_pools: dict = None
    monster_groups: dict = None
    floor_profiles: dict = None
    exterior_structure: str = None
    biome_weights: dict = field(default_factory=dict)

    @staticmethod
    def _lookup(depth, *tables):
        for table in tables:
            if table:
                pool = table.get(max(1, min(depth, max(table))))
                if pool:
                    return list(pool)
        return []

    def monster_pool(self, depth, default_tiers, fallback=()):
        return self._lookup(depth, self.monster_tiers, default_tiers) or list(fallback)

    def boss_pool(self, depth, default_pools):
        return self._lookup(depth, self.boss_pools, default_pools)

    def floor_profile(self, depth):
        if not self.floor_profiles:
            return None
        return self.floor_profiles.get(max(1, min(depth, max(self.floor_profiles))))

    def group_for(self, monster_name, default_groups):
        return (self.monster_groups or {}).get(monster_name) or default_groups.get(monster_name, [monster_name])

    def weight_for(self, biome):
        biome_key = getattr(biome, "value", biome)
        return self.biome_weights.get(biome_key, self.biome_weights.get("*", 0))


THEMES = {}


def register_theme(theme):
    THEMES[theme.key] = theme
    return theme


def get_theme(key):
    return THEMES[key]


CLASSIC_THEME = register_theme(DungeonTheme(
    key="classic",
    name="Dungeon",
    biome_weights={"*": 3},
))

CULT_CHURCH_THEME = register_theme(DungeonTheme(
    key="cult_church",
    name="Ruined Church",
    floor_range=(3, 3),
    exterior_structure="ruined_church",
    monster_tiers={
        1: [Cultist, CultAcolyte, Imp, GiantRat, GiantSpider],
        2: [Cultist, CultAcolyte, CultFanatic, Imp, Skeleton, SkeletonArcher, Ghoul],
        3: [Cultist, CultAcolyte, CultFanatic, Imp, Ghoul, SkeletonArcher, Wraith],
    },
    boss_pools={
        1: ["CultHierophant"],
        2: ["CultHierophant"],
        3: ["CultHierophant"],
    },
    monster_groups={
        "Cultist": ["Cultist", "Cultist", "CultAcolyte", "Imp"],
        "CultAcolyte": ["Cultist", "CultAcolyte"],
        "CultFanatic": ["CultFanatic", "Cultist", "CultAcolyte"],
        "Imp": ["Imp", "Cultist"],
    },
    floor_profiles={
        1: DungeonFloorProfile(
            "Desecrated Chapel",
            room_props=(
                tile.rubble, tile.rubble, tile.rubble, tile.bones, tile.cob_web,
                tile.cob_web, tile.dungeon_grass, tile.dungeon_grass_two, tile.crate,
            ),
            nave_rooms=(2, 0.7),
        ),
        2: DungeonFloorProfile(
            "Catacombs",
            room_props=(
                tile.bones, tile.bones, tile.fresh_bones, tile.rubble,
                tile.cob_web, tile.cob_web, tile.mushroom,
            ),
            prop_chance=0.2,
            crypt_rooms=(3, 0.85),
        ),
        3: DungeonFloorProfile(
            "Inner Sanctum",
            room_props=(tile.fresh_bones, tile.fresh_bones, tile.bones, tile.rubble, tile.cob_web),
            nave_rooms=(1, 0.5),
            sanctum=True,
        ),
    },
    biome_weights={"forest": 1, "plains": 1},
))


def theme_for_entrance(world_seed, entrance_position, biome):
    entrance_x, entrance_y = entrance_position
    seed = (
        world_seed * 2_654_435_761
        + entrance_x * 92_821
        + entrance_y * 68_927
        + 0x7E7
    ) & 0xFFFFFFFF

    candidates = [(theme, theme.weight_for(biome)) for theme in THEMES.values()]
    candidates = [(theme, weight) for theme, weight in candidates if weight > 0]
    if not candidates:
        return CLASSIC_THEME

    themes, weights = zip(*candidates)
    return random.Random(seed).choices(themes, weights=weights, k=1)[0]