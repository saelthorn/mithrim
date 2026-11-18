import random
from dataclasses import dataclass, field

from world import tile

from entities.monster import (
    Cultist, CultAcolyte, CultFanatic, Imp, GiantRat, GiantSpider,
    Skeleton, SkeletonArcher, Ghoul, Wraith,
    Goblin, GoblinArcher, Hobgoblin, GoblinBoss, Wolf, Mummy,
    Spiderling, GiantScorpion, Orc, OrcShaman, Troll, Owlbear,
    Lizardfolk, LizardfolkArcher, LizardfolkShaman, Crocodile,
)


@dataclass(frozen=True, eq=False)
class DungeonFloorProfile:
    name: str
    room_props: tuple = None
    prop_chance: float = None
    room_dressers: tuple = ()
    boss_dresser: str = None
    crypt_rooms: tuple = None
    water_chance: float = None


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

FORCED_THEME_KEY = None


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
            room_dressers=(("church_nave", 2, 0.7),),
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
            room_dressers=(("church_nave", 1, 0.5),),
            boss_dresser="church_sanctum",
        ),
    },
    biome_weights={"forest": 1, "plains": 1},
))


GOBLIN_HIDEOUT_THEME = register_theme(DungeonTheme(
    key="goblin_hideout",
    name="Goblin Hideout",
    floor_range=(2, 2),
    exterior_structure="goblin_hideout",
    monster_tiers={
        1: [Goblin, GoblinArcher, Hobgoblin, Wolf, GiantRat],
        2: [Goblin, GoblinArcher, Hobgoblin, GoblinBoss, Wolf],
    },
    boss_pools={
        1: ["GoblinWarchief"],
        2: ["GoblinWarchief"],
    },
    monster_groups={
        "Goblin": ["Goblin", "Goblin", "GoblinArcher", "Hobgoblin"],
        "Hobgoblin": ["Hobgoblin", "Goblin", "GoblinArcher"],
        "GoblinBoss": ["GoblinBoss", "Goblin", "GoblinArcher", "Wolf"],
    },
    floor_profiles={
        1: DungeonFloorProfile(
            "Goblin Warrens",
            room_props=(
                tile.crate, tile.barrel, tile.hay, tile.bones,
                tile.rubble, tile.rubble, tile.cob_web,
            ),
            prop_chance=0.2,
            room_dressers=(("goblin_camp", 2, 0.7),),
        ),
        2: DungeonFloorProfile(
            "Chieftain's Den",
            room_props=(tile.crate, tile.barrel, tile.bones, tile.fresh_bones, tile.rubble, tile.hay),
            prop_chance=0.2,
            room_dressers=(("goblin_camp", 1, 0.5),),
            boss_dresser="goblin_hall",
        ),
    },
    biome_weights={"hills": 2, "forest": 1, "mountains": 1},
))

ANCIENT_TOMB_THEME = register_theme(DungeonTheme(
    key="ancient_tomb",
    name="Ancient Tomb",
    floor_range=(3, 3),
    exterior_structure="ancient_tomb",
    monster_tiers={
        1: [Skeleton, SkeletonArcher, Ghoul, GiantRat],
        2: [Skeleton, SkeletonArcher, Ghoul, Mummy],
        3: [Skeleton, SkeletonArcher, Ghoul, Mummy, Wraith],
    },
    boss_pools={
        1: ["Lich"],
        2: ["Lich"],
        3: ["Lich"],
    },
    monster_groups={
        "Skeleton": ["Skeleton", "Skeleton", "SkeletonArcher", "Ghoul"],
        "Ghoul": ["Ghoul", "Ghoul", "Skeleton"],
        "Mummy": ["Mummy", "Skeleton"],
    },
    floor_profiles={
        1: DungeonFloorProfile(
            "Burial Halls",
            room_props=(tile.bones, tile.bones, tile.rubble, tile.cob_web, tile.cob_web),
            prop_chance=0.18,
            room_dressers=(("ossuary", 1, 0.6),),
            crypt_rooms=(2, 0.7),
        ),
        2: DungeonFloorProfile(
            "Ossuary Depths",
            room_props=(tile.bones, tile.bones, tile.rubble, tile.cob_web, tile.mushroom),
            prop_chance=0.22,
            room_dressers=(("ossuary", 2, 0.7),),
            crypt_rooms=(3, 0.9),
        ),
        3: DungeonFloorProfile(
            "Lich's Sanctum",
            room_props=(tile.bones, tile.rubble, tile.cob_web, tile.cob_web),
            prop_chance=0.15,
            room_dressers=(("ossuary", 1, 0.5),),
            boss_dresser="lich_sanctum",
            crypt_rooms=(2, 0.6),
        ),
    },
    biome_weights={"swamp": 1, "plains": 1, "hills": 1, "mountains": 1},
))

SPIDER_NEST_THEME = register_theme(DungeonTheme(
    key="spider_nest",
    name="Spider Nest",
    floor_range=(2, 3),
    exterior_structure="spider_nest",
    monster_tiers={
        1: [Spiderling, GiantRat, GiantSpider],
        2: [Spiderling, GiantSpider, GiantScorpion, GiantRat],
        3: [Spiderling, GiantSpider, GiantScorpion],
    },
    boss_pools={
        1: ["BroodMother"],
        2: ["BroodMother"],
        3: ["BroodMother"],
    },
    monster_groups={
        "Spiderling": ["Spiderling", "Spiderling", "Spiderling", "GiantSpider"],
        "GiantSpider": ["GiantSpider", "Spiderling", "Spiderling"],
    },
    floor_profiles={
        1: DungeonFloorProfile(
            "Webbed Burrows",
            room_props=(
                tile.cob_web, tile.cob_web, tile.cob_web, tile.bones,
                tile.fresh_bones, tile.rubble, tile.mushroom,
            ),
            prop_chance=0.18,
            room_dressers=(("web_nest", 2, 0.7),),
        ),
        2: DungeonFloorProfile(
            "Brood Chambers",
            room_props=(
                tile.cob_web, tile.cob_web, tile.cob_web, tile.fresh_bones,
                tile.mushroom, tile.bones,
            ),
            prop_chance=0.18,
            room_dressers=(("web_nest", 2, 0.6),),
            boss_dresser="brood_lair",
        ),
        3: DungeonFloorProfile(
            "Brood Mother's Lair",
            room_props=(tile.cob_web, tile.cob_web, tile.fresh_bones, tile.mushroom, tile.bones),
            prop_chance=0.18,
            room_dressers=(("web_nest", 1, 0.5),),
            boss_dresser="brood_lair",
        ),
    },
    biome_weights={"forest": 2, "swamp": 1, "hills": 1},
))

ORC_STRONGHOLD_THEME = register_theme(DungeonTheme(
    key="orc_stronghold",
    name="Orc Stronghold",
    floor_range=(3, 3),
    exterior_structure="orc_stronghold",
    monster_tiers={
        1: [Orc, Wolf, Goblin, GoblinArcher],
        2: [Orc, OrcShaman, Wolf, Owlbear, GoblinArcher],
        3: [Orc, OrcShaman, Troll, Owlbear, Wolf],
    },
    boss_pools={
        1: ["OrcWarlord"],
        2: ["OrcWarlord"],
        3: ["OrcWarlord"],
    },
    monster_groups={
        "Orc": ["Orc", "Orc", "OrcShaman", "Wolf"],
        "OrcShaman": ["OrcShaman", "Orc", "Orc"],
        "Wolf": ["Wolf", "Wolf", "Orc"],
    },
    floor_profiles={
        1: DungeonFloorProfile(
            "Gatehouse",
            room_props=(tile.crate, tile.barrel, tile.bones, tile.rubble, tile.hay, tile.rubble),
            prop_chance=0.18,
            room_dressers=(("war_barracks", 2, 0.7),),
        ),
        2: DungeonFloorProfile(
            "Barracks",
            room_props=(tile.crate, tile.barrel, tile.bones, tile.hay, tile.rubble),
            prop_chance=0.2,
            room_dressers=(("war_barracks", 2, 0.8),),
        ),
        3: DungeonFloorProfile(
            "War Hall",
            room_props=(tile.bones, tile.fresh_bones, tile.rubble, tile.crate, tile.barrel),
            prop_chance=0.18,
            room_dressers=(("war_barracks", 1, 0.5),),
            boss_dresser="war_hall",
        ),
    },
    biome_weights={"mountains": 2, "hills": 1},
))

SUNKEN_TEMPLE_THEME = register_theme(DungeonTheme(
    key="sunken_temple",
    name="Sunken Temple",
    floor_range=(2, 3),
    exterior_structure="sunken_temple",
    monster_tiers={
        1: [Lizardfolk, LizardfolkArcher, GiantRat],
        2: [Lizardfolk, LizardfolkArcher, LizardfolkShaman, Crocodile],
        3: [Lizardfolk, LizardfolkArcher, LizardfolkShaman, Crocodile],
    },
    boss_pools={
        1: ["LizardfolkChieftain"],
        2: ["LizardfolkChieftain"],
        3: ["LizardfolkChieftain"],
    },
    monster_groups={
        "Lizardfolk": ["Lizardfolk", "Lizardfolk", "LizardfolkArcher", "LizardfolkShaman"],
        "LizardfolkShaman": ["LizardfolkShaman", "Lizardfolk", "Crocodile"],
        "Crocodile": ["Crocodile", "Crocodile", "Lizardfolk"],
    },
    floor_profiles={
        1: DungeonFloorProfile(
            "Flooded Approach",
            room_props=(tile.dungeon_grass, tile.dungeon_grass_two, tile.rubble, tile.mushroom, tile.cob_web, tile.bones),
            prop_chance=0.18,
            room_dressers=(("flooded_hall", 2, 0.6),),
            water_chance=0.65,
        ),
        2: DungeonFloorProfile(
            "Sunken Halls",
            room_props=(tile.dungeon_grass, tile.rubble, tile.mushroom, tile.bones, tile.fresh_bones),
            prop_chance=0.18,
            room_dressers=(("flooded_hall", 2, 0.7),),
            boss_dresser="temple_sanctum",
            water_chance=0.8,
        ),
        3: DungeonFloorProfile(
            "Drowned Sanctum",
            room_props=(tile.dungeon_grass, tile.rubble, tile.mushroom, tile.bones, tile.cob_web),
            prop_chance=0.16,
            room_dressers=(("flooded_hall", 1, 0.5),),
            boss_dresser="temple_sanctum",
            water_chance=0.85,
        ),
    },
    biome_weights={"swamp": 2, "plains": 1},
))

def theme_for_entrance(world_seed, location, biome):
    if FORCED_THEME_KEY:
        return THEMES[FORCED_THEME_KEY]

    entrance_x, entrance_y = location
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