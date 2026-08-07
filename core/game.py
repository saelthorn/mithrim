import pygame
import random
import config
import math 
import json
import uuid
import copy
import tracemalloc      # Lifesaver
from pathlib import Path
from enum import Enum


class GameState:
    TAVERN = "tavern"
    DUNGEON = "dungeon"
    INVENTORY = "inventory"
    INVENTORY_MENU = "inventory_menu"
    CHARACTER_MENU = "character_menu"
    TARGETING = "targeting"  
    CHARACTER_CREATION = "character_creation"
    LINEAGE_SELECTION = "lineage_selection"
    CLASS_SELECTION = "class_selection"
    TRADE = "trade"
    CHEST_MENU = "chest_menu"  # Locked chest interaction menu
    SHOP_MENU  = "shop_menu"   # Merchant shop overlay
    INNKEEPER_MENU = "innkeeper_menu"  # Innkeeper's Buy Food / Rest for the Night choice menu
    REST_MENU = "rest_menu"  # Player short rest / long rest choice menu
    GAME_OVER = "game_over" # NEW: Add GAME_OVER state
    OVERWORLD = "overworld"  # Cellular-automata overworld map (dungeon_generator's sibling)
    WORLD_ENCOUNTER_MENU = "world_encounter_menu"  # Narrative overworld encounter choice menu
    WORLD_ENCOUNTER_AFTERMATH_MENU = "world_encounter_aftermath_menu"  # Post-combat branching choice, see scenario "aftermath"
    WORLD_ENCOUNTER_DISCOVERY = "world_encounter_discovery"  # A stage's/aftermath's "discovery" text, shown alone with a "Continue" prompt before its choice menu opens
    DEATH_SAVE_MENU = "death_save_menu"  # Player unconscious at 0 hp, rolling death saving throws (see Player.roll_death_save())


class InteractionMode:
    """
    Which behavior the player's interact key (F, see check_overworld_npc_interaction()
    et al.) currently performs. Toggled with F1-F4 (see the always-accessible hotkey
    handling in Game's event loop) -- exactly one mode is active at a time, stored on
    Game.interaction_mode.

    NORMAL, STEAL, INTERACT, and INFO are all wired up: F1 talks to NPCs/uses
    landmarks (the original default), F2 attempts a pickpocket
    (_attempt_pickpocket()), F3 picks up ground loot at the player's feet
    (handle_item_pickup()) instead of talking to whatever NPC is adjacent,
    and F4 reports the current time/location instead of interacting with
    anything (_describe_surroundings()).
    """
    DIALOGUE = "dialogue"  # Talk to NPCs, use landmarks/torches -- today's default behavior
    STEAL = "steal"    # Attempt to pickpocket an adjacent NPC instead of talking to them
    INTERACT = "interact"      # Pick up items/loot from the ground instead of talking to NPCs
    INFO = "info"      # No world interaction -- reports ambient info about surroundings instead

    # Human-readable label shown in the mode-switch message and any future HUD indicator.
    LABELS = {
        DIALOGUE: "Dialogue",
        STEAL: "Steal",
        INTERACT: "Interact",
        INFO: "Info",
    }


# Ambient flavor text shown at random on the player's turn (see Game.next_turn()).
# Keyed first by which "place" the player is in (OVERWORLD vs. DUNGEON), then by
# a coarse time-of-day period derived from the world clock (see
# _ambient_time_period() below) -- so a message pool is picked for both *where*
# and *when* the player currently is, rather than one flat pool per place.
# Purely content/data: next_turn() only ever looks this table up, it never
# hardcodes any message text itself, matching the framework-first,
# data-driven approach used everywhere else in the narrative systems.
AMBIENT_MESSAGES_BY_PERIOD = {
    GameState.OVERWORLD: {
        "dawn": [
            "The morning mist curls between the trees like wandering spirits...",
            "The faint scent of damp earth rises as the night releases its grip...",
            "A lone raven cries somewhere beyond the fog...",
            "Fresh tracks disappear into the dew before you can follow them...",
            "The breeze carries the distant ringing of a temple bell...",
            "A fox darts through the underbrush before vanishing from sight...",
            "The world slowly stirs, though something still refuses to sleep...",
            "A lonely crow watches from a dead branch before taking flight...",
            "The chill of the night lingers stubbornly beneath the trees...",
            "You catch the scent of wildflowers hidden somewhere nearby...",
            "The horizon glows softly, promising warmth that has yet to arrive...",
            "A distant rooster calls from lands far beyond the wilderness...",
        ],
        "morning": [
            "The forest awakens with birdsong and rustling leaves...",
            "A squirrel scampers across a fallen log before disappearing into the brush...",
            "The wind carries the fresh scent of pine and moss...",
            "You hear water flowing somewhere nearby...",
            "Bees drift lazily between patches of wildflowers...",
            "The sunlight dances across the leaves overhead...",
            "A butterfly drifts lazily past before disappearing into the trees...",
            "The warmth of the morning sun eases the night's lingering chill...",
            "Somewhere in the distance, wood is being chopped rhythmically...",
            "The grass bends beneath an unseen creature moving away...",
            "The world feels peaceful—for now...",
            "A faint trail of smoke rises somewhere beyond the hills...",
        ],
        "noon": [
            "Cicadas sing relentlessly beneath the blazing sun...",
            "The warmth draws the scent of grass and earth into the air...",
            "The forest seems quieter beneath the oppressive heat...",
            "A dragonfly darts across your path in a flash of iridescent color...",
            "The wind has all but disappeared...",
            "The stillness is broken only by the occasional bird overhead...",
            "Even the insects seem sluggish beneath the midday heat...",
            "A distant river sparkles beneath the relentless sun...",
            "The shade beneath the trees offers welcome relief...",
            "The air feels strangely heavy, as though a storm waits beyond the horizon...",
            "The silence feels unnatural for this time of day...",
            "A lone buzzard circles high overhead...",
        ],
        "afternoon": [
            "The golden light softens the edges of the landscape...",
            "The wind shifts, carrying unfamiliar scents...",
            "The forest grows quieter as daylight begins to fade...",
            "A deer watches from the edge of the woods before slipping away...",
            "The distant call of a hunting horn echoes faintly...",
            "Leaves tumble lazily across the old road...",
            "The warmth of the day begins to fade from the stones beneath your feet...",
            "You notice broken branches where something recently passed...",
            "The shadows beneath the trees deepen with each passing hour...",
            "A flock of birds suddenly erupts into the sky in the distance...",
            "The breeze carries the faint scent of rain-soaked earth...",
            "The wilderness grows restless as evening approaches...",
        ],
        "dusk": [
            "The forest seems to hold its breath as daylight fades...",
            "A murder of crows takes flight with harsh cries...",
            "The fading light paints long shadows between the trees...",
            "An owl calls from somewhere hidden in the darkness...",
            "The air grows noticeably colder...",
            "You hear movement nearby, but find nothing when you look...",
            "The last rays of sunlight vanish behind the hills...",
            "The insects grow louder as darkness settles over the land...",
            "Something splashes in distant water...",
            "The smell of damp leaves fills the cooling air...",
            "A strange silence falls before the first sounds of the night emerge...",
            "The world slowly gives itself over to darkness...",
        ],
        "night": [
            "The darkness swallows the road behind you...",
            "The wind whispers through the trees in voices almost human...",
            "You hear slow footsteps... then nothing...",
            "A raven's cry cuts through the stillness before fading away...",
            "The moonlight turns every shadow into something unfamiliar...",
            "The forest seems far larger after sunset...",
            "The scent of smoke lingers, though no fire can be seen...",
            "A twig snaps somewhere nearby...",
            "You briefly glimpse glowing eyes watching from the darkness...",
            "The night air bites with unexpected cold...",
            "A distant scream echoes before abruptly falling silent...",
            "The stars seem strangely dim tonight...",
        ],
        "late_night": [
            "The darkness feels almost tangible...",
            "Every sound seems louder in the stillness...",
            "You catch yourself glancing over your shoulder...",
            "The wind dies completely, leaving an eerie silence...",
            "The moon disappears behind heavy clouds...",
            "A distant howl lingers far longer than it should...",
            "The hairs on the back of your neck stand on end...",
            "You cannot shake the feeling that someone is following you...",
            "The trees creak softly as though shifting in their sleep...",
            "Something breathes just beyond the reach of your torchlight...",
            "The silence is broken by a single, hollow knock in the distance...",
            "You suddenly realize you haven't heard a single insect for several minutes...",
        ],
    },
    GameState.DUNGEON: {
        "dawn": [
            "You imagine sunlight filtering through the world far above...",
            "The stale air remains unchanged despite the new day...",
            "A pebble tumbles somewhere deep within the darkness...",
            "The silence is broken by the slow drip of water...",
            "You feel strangely disconnected from the passage of time...",
            "The dungeon greets the morning with only silence...",
            "Something shifts within the walls before falling still...",
        ],
        "morning": [
            "A faint breeze brushes past before disappearing...",
            "The smell of mildew clings stubbornly to the stone...",
            "Your footsteps echo farther than before...",
            "The shadows seem thinner, though no light reaches them...",
            "You hear distant scraping against ancient stone...",
            "The walls glisten faintly with moisture...",
            "The darkness seems almost patient...",
        ],
        "noon": [
            "A low rumble echoes through the depths...",
            "Water drips steadily somewhere unseen...",
            "You hear what almost sounds like whispering...",
            "The stale air feels heavier than before...",
            "The silence grows uncomfortable...",
            "The torchlight dances across old carvings worn by time...",
            "Dust falls from the ceiling without warning...",
        ],
        "afternoon": [
            "A cold draft slips through the corridor before vanishing...",
            "The stones beneath your boots feel unnaturally cold...",
            "Something knocks softly beyond the wall...",
            "The shadows twist as your torch flickers...",
            "You hear chains dragging somewhere deeper within...",
            "The smell of ancient decay lingers in the air...",
            "The dungeon feels as though it is watching...",
        ],
        "dusk": [
            "The darkness beyond your torchlight seems deeper than before...",
            "A faint laugh echoes from somewhere impossible to place...",
            "Your flame sputters without warning...",
            "You feel an inexplicable sense of unease...",
            "A distant metallic clang reverberates through the halls...",
            "The air suddenly turns icy cold...",
            "The silence is interrupted by something scratching stone...",
        ],
        "night": [
            "The darkness presses close around your torch...",
            "You hear slow breathing that isn't your own...",
            "A foul smell of rot drifts through the corridor...",
            "The walls seem damp with something thicker than water...",
            "Something moves just outside your field of view...",
            "The dungeon groans softly beneath your feet...",
            "A whisper brushes past your ear before disappearing...",
        ],
        "late_night": [
            "The silence becomes almost unbearable...",
            "The darkness feels alive...",
            "You hear a single footstep echo behind you...",
            "The torchlight seems weaker than before...",
            "The air grows colder with every passing moment...",
            "A distant scream reverberates briefly before being swallowed by silence...",
            "The shadows linger just a little too long as your torch flickers...",
        ],
    },
}


# Flavor text pool for GameState.DEATH_SAVE_MENU (see Game._enter_death_save_menu()
# / Game._pick_death_save_ambient_message()). Purely atmospheric, no mechanical
# effect -- one line is picked fresh each turn the player spends unconscious,
# alongside a line naming whatever last struck them down, if that's known.
DEATH_SAVE_AMBIENT_MESSAGES = [
    "The world is a dim, ringing blur...",
    "Somewhere close, footsteps circle nearer...",
    "Your own heartbeat is the loudest sound left in the world...",
    "Cold seeps up from the ground beneath you...",
    "Shapes move at the edge of your vision, too faint to name...",
    "A weight presses on your chest, heavier with every breath...",
    "Voices drift past, muffled as if through water...",
    "You can't feel your hands anymore...",
]

# Templates filled in with Player.last_attacker_name/last_damage_taken when
# those are known, so the menu can name whoever struck the player down.
DEATH_SAVE_ATTACKER_MESSAGE_TEMPLATES = [
    "The last thing you remember is {attacker}'s blow landing...",
    "{attacker} looms somewhere above you, waiting to see if you rise...",
    "You can still feel where {attacker} struck you...",
]
DEATH_SAVE_ATTACKER_DAMAGE_TEMPLATE = (
    "{attacker} hit you for {damage} {damage_type} before everything went dark..."
)


def _ambient_time_period(hour_of_day):
    """
    Bucket a world-clock hour (0-23, see world_time.py's WorldClock.hour_of_day)
    into one of the coarse periods AMBIENT_MESSAGES_BY_PERIOD is keyed by.

    Kept separate from world/lighting.py's period_for_hour() (used for the
    on-screen clock readout) so ambient flavor text can use its own set of
    named buckets without being coupled to however many/which periods that
    module's own day/night-cycle lighting logic happens to define.
    """
    if 5 <= hour_of_day < 7:
        return "dawn"
    if 7 <= hour_of_day < 11:
        return "morning"
    if 11 <= hour_of_day < 14:
        return "noon"
    if 14 <= hour_of_day < 17:
        return "afternoon"
    if 17 <= hour_of_day < 20:
        return "dusk"
    if 20 <= hour_of_day < 24:
        return "night"
    return "late_night"  # 0-4





from world.world_generator import ChunkBiome

BIOME_CONNECTIONS = {

    ChunkBiome.PLAINS: [
        ChunkBiome.PLAINS,
        ChunkBiome.FOREST,
        ChunkBiome.HILLS,
        ChunkBiome.SWAMP,
        ChunkBiome.MOUNTAINS,
    ],

    ChunkBiome.FOREST: [
        ChunkBiome.FOREST,
        ChunkBiome.PLAINS,
        ChunkBiome.HILLS,
        ChunkBiome.SWAMP,
    ],

    ChunkBiome.SWAMP: [
        ChunkBiome.SWAMP,
        ChunkBiome.FOREST,
        ChunkBiome.PLAINS,
    ],

    ChunkBiome.HILLS: [
        ChunkBiome.HILLS,
        ChunkBiome.PLAINS,
        ChunkBiome.FOREST,
        ChunkBiome.MOUNTAINS,
    ],

    ChunkBiome.MOUNTAINS: [
        ChunkBiome.MOUNTAINS,
        ChunkBiome.HILLS,
        ChunkBiome.TUNDRA,
    ],

    ChunkBiome.TUNDRA: [
        ChunkBiome.TUNDRA,
        ChunkBiome.MOUNTAINS,
    ],

    ChunkBiome.DESERT: [
        ChunkBiome.DESERT,
        ChunkBiome.PLAINS,
    ],
}


from core.fov import FOV
from core.ui_sidebar import draw_sidebar
from core.ui_screens import render_inventory_screen, render_inventory_menu_popup, render_character_menu
from world.map import GameMap
from world.dungeon_generator import generate_dungeon
from world.world_generator import generate_overworld
from world.world_map import (
    generate_world_map,
    OVERWORLD_CHUNK_WIDTH,
    OVERWORLD_CHUNK_HEIGHT,
    world_position_to_chunk_local,
    chunk_local_to_world_position,
)
from world.world_time import TimeUnit
from world.lighting import ambient_tint_for_time, combine_tints, period_for_hour
from world.encounters.prison_cell import (
    handle_prison_door_interaction, PrisonDoorTile, is_prison_cell_position
)
from world.encounters.crypt import handle_tomb_interaction, is_crypt_position

from story.story_integration import StorySystems
from story.story_framework import StoryEvent
from story.trigger_system import TriggerRule, TriggerType
from story.consequence_system import RewardXPConsequence, RewardGoldConsequence, ModifyReputationConsequence, consequence_from_dict
from story.story_failure_system import FailureMode, FailurePolicy

from entities.player import Player, Fighter, Rogue, Wizard, Cleric

# NEW: Import all monster classes
from entities.monster import (
    Monster, Mimic, GiantRat, Ooze, Goblin, GoblinArcher, Skeleton,
    SkeletonArcher, Orc, Centaur, CentaurArcher, Troll, Lizardfolk, 
    LizardfolkArcher, GiantSpider, Beholder, LargeOoze, RedDragon,
    Owlbear, Demogorgon, Grick, GibberingMouther, MindFlayer, Minotaur,
    Wererat, Wolf, Yochlol, Drider, RedSlaad, DeathSlaad, MyconidSprout,
    MyconidAdult, Mezzoloth, Gauth, Arasta, AlphaGrick, IntellectDevourer, 
    Imp, Wraith, TombTapper, Cultist, Disposition

)

from entities.base_entity import NPC
from entities.tavern_npcs import NPC, Merchant
from entities.dungeon_npcs import DungeonHealer, DungeonMerchant, PrisonerNPC, make_encounter_victims, GuardVictim, Trader, EncounterVictim
from world.structures import TownNPC, Townsfolk, Innkeeper, Shopkeeper

from entities.races import (
    Human,
    DrowElf, HighElf, WoodElf,
    HillDwarf, MountainDwarf, Duergar,
    ZarielTiefling, LevistusTiefling, DispaterTiefling, MephistophelesTiefling,
    RedDragonborn, BlueDragonborn, GoldDragonborn, GreenDragonborn,
    RACE_GROUPS,          # lineage catalogue used by the creation screen
)
from entities.summons import MageHandEntity, SummonedEntity, EscortCompanion
from core.abilities import SecondWind, PowerAttack, CunningActionDash, Evasion, FireBolt, MistyStep, MageHand, ActionSurge
from core.message_log import MessageBox
from core.status_effects import (
    ParryBuff, PowerAttackBuff, DivineStrikeBuff, CunningActionDashBuff, EvasionBuff, Hidden, BlessingOfStrength, CurseOfWeakness, 
    PreciseStrikeBuff, Prepared, FleetFooted, AppliedToxins
)
from items.items import (
    Potion, Weapon, Armor, OffHand, Chest, LockedChest, lesser_healing_potion, greater_healing_potion, wood_plank, meat, green_apple, fromage, 
    bread, mushroom, CampfireKit, torch, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor, robes, 
    iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, 
    apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail, 
    round_shield, kite_shield, tower_shield,
    Helmet, Boots, FocusItem,
    leather_cap, iron_helmet, steel_helmet, great_helm, mages_circlet, hood_of_shadows,
    leather_boots, iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers,
)

from core.pathfinding import astar
from world.tile import floor, dungeon_floor_two, dungeon_floor_three, dungeon_floor_four, MimicTile, TrapTile, FireElementalTile, caravan, ritual_circle, barricade, ambush_tree, ground, overworld_cobweb, gravestone, gravestone_two, gravestone_three, tent 
from world.bloodstain import Bloodstain
from world.altar import Altar
from world.water_features import river, lake, is_water_tile # NEW: Import water tiles and helper
from core.floating_text import FloatingText 
import graphics


INTERNAL_WIDTH = 800
INTERNAL_HEIGHT = 600
ASPECT_RATIO = INTERNAL_WIDTH / INTERNAL_HEIGHT

# Every overworld chunk is generated at this fixed size (bigger than a
# generate_level() dungeon map, which is 120x100) so it feels expansive.
# Walking off the edge of one chunk generates/restores its neighbor at the
# same size, so the "grid of chunks" tiles together seamlessly.
# (OVERWORLD_CHUNK_WIDTH/HEIGHT now live in world.world_map, imported
# above, since that module also owns the chunk-local <-> global tile
# coordinate conversion that depends on them -- see
# world_map.chunk_local_to_world_position().)


class Camera:
    def __init__(self, screen_width, screen_height, tile_size, message_log_height):
        self.tile_size = tile_size
        self.viewport_width = screen_width // tile_size
        self.viewport_height = screen_height // tile_size - 2
        
        # Initialize x and y as floats
        self.x = 0.0
        self.y = 0.0
        
        # Initialize target_x and target_y as floats
        self.target_x = 0.0
        self.target_y = 0.0
        
        self.smoothing_factor = 0.08 # Adjust this value (e.g., 0.05 for very smooth, 0.3 for faster)

    def update(self, desired_target_x, desired_target_y, map_width, map_height):
        # Ensure desired_target_x/y are treated as floats for calculations
        target_x_float = float(desired_target_x)
        target_y_float = float(desired_target_y)

        # Calculate the ideal camera position.
        # Player is centered horizontally, but shifted up by 30% of the viewport
        # so the message log overlay at the bottom doesn't obscure the action.
        ideal_camera_center_x = target_x_float - (self.viewport_width / 2.0)
        ideal_camera_center_y = target_y_float - (self.viewport_height * 0.38)

        # Apply linear interpolation (LERP)
        self.x += (ideal_camera_center_x - self.x) * self.smoothing_factor
        self.y += (ideal_camera_center_y - self.y) * self.smoothing_factor

        # Clamp the camera's position to map boundaries
        # Ensure map_width/height are also treated as floats in the clamping
        self.x = max(0.0, min(self.x, float(map_width - self.viewport_width)))
        self.y = max(0.0, min(self.y, float(map_height - self.viewport_height)))

        # IMPORTANT: Do NOT convert self.x and self.y to int here.
        # They should remain floats for continuous smooth movement.
        # The conversion to int will happen in world_to_screen or when blitting.

    def world_to_screen(self, world_x, world_y):
        # This method now returns screen coordinates in *float tile units*
        # representing the precise offset from the camera's top-left.
        screen_x_float = world_x - self.x
        screen_y_float = world_y - self.y
        return screen_x_float, screen_y_float
    
    def is_in_viewport(self, world_x, world_y):
        # This method also needs to use the float camera position for accurate checks
        # but the result of world_to_screen is already int, so it's fine.
        screen_x, screen_y = self.world_to_screen(world_x, world_y)
        return (0 <= screen_x < self.viewport_width and
                0 <= screen_y < self.viewport_height)


class Game:
    def __init__(self, screen):
        self.screen = screen
        
        self.fps = 60
        self.fps_font = pygame.font.SysFont('consolas', 15)  # You can adjust the font size as needed
        self.clock = pygame.time.Clock()  # Initialize the clock for FPS tracking


        self.internal_surface = None
        self.inventory_ui_surface = None
        self.camera = None
        self.message_log = None

        self.merchant = None  # Initialize merchant attribute        
        self.dungeon_merchant = None # Create a persistent instance
        self.shopkeeper = None
        self.trader = None
        
        self.entities = []  # Initialize the entities list here
        # Cache consumed by Monster.take_turn()'s target-priority check --
        # see _refresh_owned_blocking_entities_cache(), (re)computed once
        # per player action rather than once per monster.
        self._owned_blocking_entities = []
        self.turn_order = []  # Initialize the turn order list
        self.current_turn_index = 0
        # NPCs currently being escorted -- a subset of self.entities/
        # self.turn_order (see entities/summons.py's EscortCompanion).
        # Populated by recruit_companion(), drained by
        # try_deliver_companions() once the player talks to an
        # Innkeeper, or by a companion's own die() if they're killed
        # along the way.
        self.companions = []
        self.bloodstains = []
        self.active_fire_tiles = []  # Tracks (x, y) positions of active FireElementalTiles
        # Marks (by id(npc)) which NPCs have already been successfully
        # pickpocketed this session -- see _attempt_pickpocket(), used by
        # F2/InteractionMode.STEAL -- so a mark can't be robbed repeatedly.
        # A failed attempt does NOT get added here; the player can try again.
        self._pickpocketed_npc_ids = set()
        
        self._recalculate_dimensions() 
        self._init_fonts()

        # NEW: Start in character creation state
        self.game_state = GameState.CHARACTER_CREATION 
        self._previous_game_state = None
        # Which behavior the interact key currently performs -- see
        # InteractionMode. Switched with F1-F4; only NORMAL (the default)
        # does anything today, the others are switched into ahead of their
        # own interaction logic being added.
        self.interaction_mode = InteractionMode.DIALOGUE
        # The last "place" the player actually stood in -- OVERWORLD or
        # DUNGEON -- independent of whatever menu (shop, chest, world
        # encounter, ...) is currently drawn on top of it. Menus overlay
        # the scene without moving the player anywhere, so anything that
        # depends on where the player physically is (right now just
        # _ambient_light_tint()'s sky-vs-underground check) should read
        # this instead of self.game_state directly -- otherwise the sky's
        # time-of-day tint would flatten out the instant a menu opened and
        # snap back the instant it closed. Only updated at the handful of
        # spots that actually move the player between places (see
        # generate_overworld_map()/enter_dungeon_level() and friends);
        # every menu-open/close path leaves it alone.
        self._environment_state = GameState.OVERWORLD
        self.current_level = 1  
        self.max_level_reached = 1

        # Overworld: an unbounded grid of chunks. Each chunk is generated once and
        # cached (rather than regenerated) so terrain, water, and dungeon entrance
        # placement stay put whether you're returning from a dungeon delve or
        # walking back into a chunk you've already explored.
        self.world_seed = random.randint(0, 999999999)
        #self.world_seed = 12345
        # Coarse, persistent world-scale terrain (elevation/biome/major rivers),
        # one cell per chunk. Cheap to generate up front, and consulted by
        # generate_overworld() whenever an individual chunk is generated so
        # neighboring chunks agree on biome and rivers cross chunk boundaries
        # cleanly instead of stopping dead at the edge. See world/world_map.py.
        self.world_map = generate_world_map(self.world_seed)
        self.overworld_chunks = {}  # (chunk_x, chunk_y) -> {"map": GameMap, "dungeon_entrances": [...]}
        self.overworld_chunk_coord = (0, 0)
        # Dungeon levels: the same "generate once, cache forever" idea as
        # overworld_chunks above, but keyed by (dungeon_id, level_number)
        # instead of chunk coordinate. Populated by _snapshot_dungeon_level()
        # right before the player leaves a level (stairs, or climbing back
        # out to the overworld) and consulted by generate_level(), so
        # descending/ascending stairs -- or leaving the dungeon and diving
        # back in -- restores the level exactly as it was left instead of
        # rerolling a brand new layout, monster spawns, and loot every time.
        #
        # `dungeon_id` identifies *which* dungeon entrance the player used --
        # see current_dungeon_id below -- so two different entrances that
        # both happen to be on "level 1" are two entirely separate dungeons,
        # each cached (and generated) independently, instead of sharing one
        # global "level 1" that every entrance on the map funnels into.
        self.dungeon_levels = {}  # (dungeon_id, level_number) -> {"map", "stairs_positions", "torch_light_sources", "lit_wall_torches", "fov", "entities"}
        # Which dungeon the player is currently inside (or last entered),
        # set the moment they step onto a dungeon_entrance tile -- see
        # handle_player_action()'s dungeon_entrance_positions check -- and
        # left unchanged while climbing stairs up/down within it. Combined
        # with self.current_level to form a dungeon_levels key, and folded
        # into the seed handed to generate_dungeon() so every entrance grows
        # its own distinct layout instead of reusing another entrance's.
        # Defaults to (0, 0) rather than None purely so _dungeon_seed()
        # never has to guard against an unset id (e.g. via the legacy,
        # currently-unreachable GameState.TAVERN doorway further down).
        self.current_dungeon_id = (0, 0)
        self.overworld_player_pos = None
        self.chunk_biomes = {}
        self.dungeon_entrance_positions = []
        self.entered_dungeon_from_overworld = False
        self.player_has_acted = False
        self.player_bonus_action_used = False
        self.message_log = MessageBox(
            0,
            config.SCREEN_HEIGHT - int(config.SCREEN_HEIGHT * 0.26),
            config.GAME_AREA_WIDTH,
            int(config.SCREEN_HEIGHT * 0.26)
        )
        self._recalculate_dimensions()

        self.ability_in_use = None
        self._chest_menu_target = None  # Locked chest awaiting player's choice
        self._innkeeper_menu_target = None  # Innkeeper awaiting player's Buy Food / Rest / Leave choice
        self._innkeeper_menu_return_state = GameState.OVERWORLD  # Where INNKEEPER_MENU itself returns to (see open_innkeeper_menu())
        self._rest_menu_target = None  # Player rest choice menu target
        self._world_encounter_target = None    # Scenario dict awaiting the player's choice
        self._world_encounter_story_id = None  # StoryInstance id backing the currently-offered/active encounter
        self._world_encounter_cooldown = 0     # Steps left before another encounter can roll
        self._world_encounter_aftermath = None # Scenario's "aftermath" block awaiting a post-combat choice
        self._world_encounter_target_victims = []  # Victims spawned for the current encounter, see recruit_companion()
        self._world_encounter_last_id = None   # scenario["id"] last rolled, see _maybe_trigger_world_encounter()
        self._world_encounter_stage_index = 0  # Index into scenario["stages"] currently on screen, see _enter_world_encounter_stage()
        self._world_encounter_stage_spawn_candidates = []  # Open tiles left after the current stage's landmark, see _spawn_world_encounter_monsters()
        self._world_encounter_pending_stage_index = None  # Next stage index queued by an "advance" choice, awaiting enough walking -- see _maybe_advance_world_encounter_stage()
        self._world_encounter_discovery_text = ""      # "discovery" text currently on screen, see _show_world_encounter_discovery()
        self._world_encounter_discovery_next_state = None  # GameState to enter once the player continues past the discovery prompt
        self._world_encounter_advance_steps = 0  # Steps walked since that "advance" choice was picked, see _maybe_advance_world_encounter_stage()
        self._shop_menu_merchant = None   # Active merchant for shop overlay
        self._shop_selected_index = 0     # Highlighted item index in shop
        self._shop_mode = "buy"           # "buy" or "sell"
        self.targeting_ability_range = 0
        self.targeting_cursor_x = 0
        self.targeting_cursor_y = 0
        self.missile_darts_remaining = 0  # Per-cast dart counter for Magic Missile
            
        self.message_log.add_message("Welcome to the dungeon!", (100, 255, 255))
        
        self.floating_texts = []  # Initialize floating texts list
        self.lit_wall_torches = set()  # (x, y) positions of wall torches the player has lit

        # REMOVED: Player creation moved to character_creation_start
        self.player = None 
        
        self.selected_inventory_item = None
        self.selected_inventory_index = 0  # Initialize the selected inventory index        

        # Tile highlights for telegraphed attacks or effects: list of (x, y, (r,g,b,a))
        self.tile_highlights = []

        # Torch Flicker
        self._torch_flicker_frame = 0
        self._torch_flicker_tint = (235, 185, 95, 255)

        # Character creation specific variables
        # UPDATED: Add DrowElf to available races
        self.available_races = [
            Human(), 
            HillDwarf(), MountainDwarf(), Duergar(), 
            DrowElf(), HighElf(), WoodElf(), 
            ZarielTiefling(), LevistusTiefling(), DispaterTiefling(), MephistophelesTiefling(), 
            RedDragonborn(), BlueDragonborn(), GoldDragonborn(), GreenDragonborn()
        ]
        self.selected_race_index = 0 

        # ── Character creation state ───────────────────────────────────────
        # RACE_GROUPS from races.py:  [(group_label, color, [lineage, ...]), ...]
        self.race_groups          = RACE_GROUPS
        self.selected_group_index   = 0      # which race group (Human / Elf / …)
        self.selected_lineage_index = 0      # which lineage within that group
 
        # Flat list rebuilt whenever the group changes; used by finalize.
        self._current_lineages = [r for _, _, rs in self.race_groups for r in rs]

        self.character_name = "Shadowblade" # Default name, could be input later
        self.character_class = Rogue # Available classes: Fighter, Rogue, Wizard, Cleric
        
        # Convenience property so the rest of the codebase can still read
        # self.available_races and self.selected_race_index unchanged.
        self.available_races      = self._current_lineages
        self.selected_race_index  = 0

        # id -> live entity, for every NPC the story engine knows about --
        # read by GameConditionContext.is_npc_alive() and written by
        # _spawn_story_npcs()/spawn_story_npc()/spawn_story_merchant() below.
        self.npc_registry = {}
        # id -> the StoryObject it was destroyed from, for
        # GameExecutionContext.destroy_landmark()/restore_landmark() (see
        # story_integration.py) -- populated by _register_story_landmarks().
        self.landmark_registry = {}
        # chunk_coord -> list of story-spawned entities waiting for that
        # chunk to actually be generated (see _place_story_entity_in_chunk()),
        # for the edge case where a story activates near a chunk boundary
        # and one of its npc_spawns falls just across it into a chunk the
        # player hasn't stepped into yet.
        self._pending_story_npc_spawns = {}

        # How many player turns pass before world_time.py's WorldClock
        # ticks forward by one minute (see story_integration.py's
        # StorySystems.advance_turn(), called from next_turn() below).
        # This is a turn-based game, so the clock advances with player
        # actions, not real wall-clock time -- resting still advances it
        # separately and explicitly via self.stories.fire_rest().
        #
        # Without this ticking forward somehow, WorldClock never moves,
        # which freezes more than just corpse-decay/camp-abandonment timers:
        # StoryQueueManager's periodic dormant-story sweep is timed off this
        # same clock, so a story that fails its ActivationRequirement once
        # (e.g. the player isn't at its location yet) would never be
        # re-checked again, no matter how close the player later walks.
        #
        # 10 moves/minute is a starting point, not a design decision --
        # tune to taste once you can see it moving alongside actual play.
        self.moves_per_minute = 10

        self.stories = StorySystems(self)
        self.world_encounter_scenarios = self._load_world_encounter_scenarios()

        # Each world-encounter scenario carries its own bystander preset as
        # "victim_data" (see Bandit_Ambush.json/Cultist_Ritual.json/
        # Undead_Siege.json/Wolf_Pack.json) -- dungeon_npcs.py no longer
        # keeps a hardcoded copy of these keyed by role/type string. Generic
        # story NPCs (content/stories/*.json "npcs" blocks) still want to
        # look one up by an arbitrary "role"/"type" string though (see
        # _build_story_npc_entity below), so this collects every scenario's
        # preset into one shared lookup, keyed the same way the scenario
        # itself is keyed (its "victim" field) -- e.g. "merchant" here still
        # means whatever Bandit_Ambush.json's "victim_data" says it means.
        self._victim_presets = {
            scenario["victim"]: scenario["victim_data"]
            for scenario in self.world_encounter_scenarios
            if scenario.get("victim") and scenario.get("victim_data")
        }

        self._wire_story_npc_spawning()

        self.race_class_visuals = {
            # ── Human ─────────────────────────────────────────────────────
            ("Human",           "Fighter"): ("HF",  (255, 255, 255)),
            ("Human",           "Rogue"):   ("HR",  (255, 255,   0)),
            ("Human",           "Wizard"):  ("HW",  (  0, 200, 255)),
            ("Human",           "Cleric"):  ("HC",  (255, 215,   0)),
 
            # ── Elf lineages ───────────────────────────────────────────────
            ("Drow Elf",        "Fighter"): ("EF",  (100,   0, 130)),
            ("Drow Elf",        "Rogue"):   ("ER",  (150,   0, 180)),
            ("Drow Elf",        "Wizard"):  ("EW",  (200,   0, 220)),
            ("Drow Elf",        "Cleric"):  ("EC",  (255, 255,   0)),
            ("High Elf",        "Fighter"): ("HEF", (180, 220, 180)),
            ("High Elf",        "Rogue"):   ("HER", (130, 190, 130)),
            ("High Elf",        "Wizard"):  ("HEW", ( 80, 150, 255)),
            ("High Elf",        "Cleric"):  ("HEC", (255, 255, 180)),
            ("Wood Elf",        "Fighter"): ("WEF", ( 80, 140,  60)),
            ("Wood Elf",        "Rogue"):   ("WER", ( 60, 120,  40)),
            ("Wood Elf",        "Wizard"):  ("WEW", ( 40, 160,  80)),
            ("Wood Elf",        "Cleric"):  ("WEC", (200, 220, 120)),
 
            # ── Dwarf lineages ─────────────────────────────────────────────
            ("Hill Dwarf",      "Fighter"): ("DF",  (180, 120,  60)),
            ("Hill Dwarf",      "Rogue"):   ("DR",  (200, 150,   0)),
            ("Hill Dwarf",      "Wizard"):  ("DW",  (100, 150, 255)),
            ("Hill Dwarf",      "Cleric"):  ("DC",  (255, 215,   0)),
            ("Mountain Dwarf",  "Fighter"): ("MDF", (160, 100,  50)),
            ("Mountain Dwarf",  "Rogue"):   ("MDR", (130,  80,  40)),
            ("Mountain Dwarf",  "Wizard"):  ("MDW", ( 90, 110, 200)),
            ("Mountain Dwarf",  "Cleric"):  ("MDC", (220, 190,  80)),
            ("Duergar",         "Fighter"): ("DGF", (100,  90,  90)),
            ("Duergar",         "Rogue"):   ("DGR", ( 80,  70,  70)),
            ("Duergar",         "Wizard"):  ("DGW", ( 70,  80, 130)),
            ("Duergar",         "Cleric"):  ("DGC", (180, 170, 140)),
 
            # ── Tiefling lineages ──────────────────────────────────────────
            # Zariel — ember orange (martial fury)
            ("Zariel Tiefling",       "Fighter"): ("ZTF", (210,  80,  20)),
            ("Zariel Tiefling",       "Rogue"):   ("ZTR", (190,  60,  10)),
            ("Zariel Tiefling",       "Wizard"):  ("ZTW", (240, 110,  40)),
            ("Zariel Tiefling",       "Cleric"):  ("ZTC", (255, 180,  60)),
            # Levistus — ice blue (cold cunning)
            ("Levistus Tiefling",     "Fighter"): ("LTF", ( 60, 120, 200)),
            ("Levistus Tiefling",     "Rogue"):   ("LTR", ( 40, 100, 180)),
            ("Levistus Tiefling",     "Wizard"):  ("LTW", ( 80, 160, 240)),
            ("Levistus Tiefling",     "Cleric"):  ("LTC", (160, 210, 255)),
            # Dispater — iron violet (infiltrator)
            ("Dispater Tiefling",     "Fighter"): ("DTF", (110,  70, 140)),
            ("Dispater Tiefling",     "Rogue"):   ("DTR", ( 90,  50, 120)),
            ("Dispater Tiefling",     "Wizard"):  ("DTW", (140,  90, 180)),
            ("Dispater Tiefling",     "Cleric"):  ("DTC", (200, 160, 255)),
            # Mephistopheles — arcane teal (arcanist)
            ("Mephistopheles Tiefling", "Fighter"): ("MTF", ( 20, 160, 140)),
            ("Mephistopheles Tiefling", "Rogue"):   ("MTR", ( 10, 130, 110)),
            ("Mephistopheles Tiefling", "Wizard"):  ("MTW", ( 40, 200, 180)),
            ("Mephistopheles Tiefling", "Cleric"):  ("MTC", (160, 240, 220)),
 
            # ── Dragonborn lineages ────────────────────────────────────────
            ("Red Dragonborn",   "Fighter"): ("RDF", (180,  40,  20)),
            ("Red Dragonborn",   "Rogue"):   ("DBR", (160,  30,  10)),
            ("Red Dragonborn",   "Wizard"):  ("RDW", (220,  60,  30)),
            ("Red Dragonborn",   "Cleric"):  ("RDC", (255, 200,  60)),
            ("Blue Dragonborn",  "Fighter"): ("BDF", ( 40,  80, 200)),
            ("Blue Dragonborn",  "Rogue"):   ("BDR", ( 30,  60, 170)),
            ("Blue Dragonborn",  "Wizard"):  ("BDW", ( 60, 120, 255)),
            ("Blue Dragonborn",  "Cleric"):  ("BDC", (200, 220, 255)),
            ("Gold Dragonborn",  "Fighter"): ("GDF", (200, 160,  20)),
            ("Gold Dragonborn",  "Rogue"):   ("GDR", (180, 140,  10)),
            ("Gold Dragonborn",  "Wizard"):  ("GDW", (240, 200,  60)),
            ("Gold Dragonborn",  "Cleric"):  ("GDC", (255, 230, 120)),
            ("Green Dragonborn", "Fighter"): ("GNF", ( 30, 130,  50)),
            ("Green Dragonborn", "Rogue"):   ("GNR", ( 20, 110,  40)),
            ("Green Dragonborn", "Wizard"):  ("GNW", ( 40, 160,  70)),
            ("Green Dragonborn", "Cleric"):  ("GNC", (160, 220, 100)),
        }

        # Class selection
        self.available_classes = [Fighter, Rogue, Wizard, Cleric] # List of class objects
        self.selected_class_index = 0 

        # Call a method to start character creation
        self.start_character_creation()

        # Mini-map specific attributes
        self.minimap_surface = None
        self.minimap_rect = None
        self.minimap_needs_redraw = True # Flag to redraw minimap only when needed

        self.dirty_rects = [] # New list to store dirty rectangles
        self._equip_slot_rects = {}     # Set by render_inventory_screen each frame
        self._inventory_slot_rects = {}  # Set by render_inventory_screen each frame

        self.menu_open = None

        self._recalculate_minimap_dimensions()

        # NEW: Flag to track if game over message has been displayed
        self._game_over_displayed = False

        self.death_screen_alpha = 0  # Alpha for game over title text
        self.death_screen_bg_alpha = 0  # Alpha for background overlay
        self.death_screen_subtext_alpha = 0  # Alpha for subtext
        self.death_screen_animation_phase = 0  # 0=text fade-in, 1=bg fade-in, 2=subtext fade-in, 3=done
        self.death_screen_animation_speed = 5  # Alpha increment per frame (adjust for speed)
        self.fade_out_alpha = 0 # NEW: Alpha for the full screen fade-out
        self.fade_out_speed = 15 # NEW: Speed of the fade-out
        self.fade_in_alpha = 255
        self.fade_in_speed = 15

        # --- Death saving throw menu (GameState.DEATH_SAVE_MENU) ---
        # Which game_state to return to once the current death save is
        # resolved, and the ambient flavor line currently on display -- see
        # _enter_death_save_menu()/_pick_death_save_ambient_message().
        self._death_save_return_state = GameState.OVERWORLD
        self.death_save_ambient_message = ""

        # Overworld chunk transition — a quick black fade-out/fade-in played whenever
        # the player walks into a new chunk, so the (potentially slow) chunk generation
        # happens hidden behind a full black screen instead of causing a visible stutter.
        self.chunk_transition_phase = None  # None, "out" (fading to black), or "in" (fading back in)
        self.chunk_transition_alpha = 0
        self.chunk_transition_speed = 25
        self.pending_chunk_transition = None  # (chunk_coord, spawn_pos) queued for when fade-out completes

        self.game_over_victory = False
        self.game_over_title = "YOU DIED"
        self.game_over_story_lines = []
        self.game_over_subtext = "Press R to Restart or Q to Quit"

        self.ignore_next_input = False  # Flag to ignore input after restart

    # Every dungeon (one per entrance) is generated with its own total
    # floor count, randomly but deterministically chosen in this range --
    # see _dungeon_floor_count(). There is no longer a single "the dungeon
    # goes to level 20" ladder; each dungeon is its own short, self-
    # contained descent.
    DUNGEON_MIN_FLOORS = 2
    DUNGEON_MAX_FLOORS = 5

    # Boss pool keyed by *depth within a dungeon* (1 .. DUNGEON_MAX_FLOORS),
    # not by an absolute floor number -- every dungeon is only 2-5 floors
    # deep, and whichever floor turns out to be the last one for a given
    # dungeon (see generate_level()'s is_final_floor) always gets a boss
    # room, with the boss rolled from that depth's pool. A dungeon that
    # happens to only be 2 floors deep pulls its boss from depth 2's pool;
    # a dungeon that goes the full 5 pulls from depth 5's, and so on.
    BOSS_FLOORS = {
        1: ['Ooze', 'MyconidAdult', 'LizardfolkArcher'],
        2: ['LizardfolkArcher', 'Gauth', 'AlphaGrick'],
        3: ['AlphaGrick', 'DeathSlaad', 'TombTapper'],
        4: ['MindFlayer', 'Beholder', 'DeathSlaad'],
        5: ['Beholder', 'RedDragon', 'Demogorgon', 'Arasta'],
    }

    # Regular (non-boss) monster pool, also keyed by depth within a
    # dungeon rather than an absolute floor number, so the same tiers
    # apply consistently no matter which entrance the player is in --
    # depth 1 is always "dungeon fodder", depth 5 is always as dangerous
    # as a dungeon gets, regardless of how many total floors that
    # particular dungeon has.
    MONSTER_SPAWN_TIERS = {
        # 🌱 Early dungeon fodder (CR 1/8 – CR 1/4)
        1: [Goblin, GoblinArcher, Wolf, Imp, GiantRat, MyconidSprout],

        # ⚔️ Early-mid dangers (CR 1/2 – CR 2)
        2: [Goblin, GoblinArcher, GiantRat, GiantSpider, Wererat, Wolf,
            MyconidSprout, IntellectDevourer, Imp, Cultist, Ooze],

        # 🛡️ Mid-game threats (CR 2 – CR 4)
        3: [Skeleton, SkeletonArcher, Orc, Grick, Ooze, Cultist,
            Lizardfolk, LizardfolkArcher, GiantSpider, Wererat, MyconidAdult],

        # 👁️ Late-mid bosses and horrors (CR 4 – CR 8)
        4: [Centaur, CentaurArcher, Troll, Owlbear, Minotaur, RedSlaad,
            GibberingMouther, LargeOoze, Gauth, Wraith],

        # 🔥 Endgame threats (CR 9+)
        5: [Drider, Mezzoloth, Wraith, Yochlol, RedSlaad, LargeOoze,
            AlphaGrick, GibberingMouther, TombTapper],
    }

    # Flavor-appropriate, low-tier monster pool for each overworld biome.
    # spawn_overworld_monster_groups() rolls a primary type from here, then
    # expands it into a full pack via MONSTER_GROUPS (the same lookup
    # spawn_monster_group() uses for dungeon rooms).
    OVERWORLD_MONSTER_TABLE = {
        ChunkBiome.PLAINS: [Goblin, GoblinArcher, Wolf, GiantRat],
        ChunkBiome.FOREST: [Wolf, Goblin, GoblinArcher, GiantSpider, MyconidSprout],
        ChunkBiome.SWAMP: [Lizardfolk, LizardfolkArcher, Ooze, GiantSpider],
        ChunkBiome.HILLS: [Orc, Centaur, CentaurArcher, Goblin],
        ChunkBiome.MOUNTAINS: [Orc, Troll, Centaur, CentaurArcher],
        ChunkBiome.DESERT: [GiantSpider, Skeleton, SkeletonArcher],
        ChunkBiome.TUNDRA: [Wolf, Skeleton, SkeletonArcher],
    }

    OVERWORLD_MONSTER_GROUP_COUNT = (2, 4)   # (min, max) groups per chunk
    OVERWORLD_GROUP_SEARCH_RADIUS = 6        # tiles around each anchor to consider
    OVERWORLD_VISION_RADIUS = 12             # open-sky sight range, vs. cramped dungeon corridors

    def spawn_overworld_monster_groups(self, game_map, biome, dungeon_entrances):
        """
        Populate a freshly generated overworld chunk with monster groups.

        Mirrors spawn_monster_group()'s use of MONSTER_GROUPS to expand a
        primary monster roll into a compatible pack, but instead of a single
        dungeon room, each group clusters around its own randomly chosen
        anchor point scattered across the open chunk.
        """
        from entities.monster import MONSTER_GROUPS

        possible_monsters = self.OVERWORLD_MONSTER_TABLE.get(biome, [GiantRat])
        structure_names = {"Witch Hut", "Watchtower", "Shrine", "Cabin", "Tavern", "Shop", "House"}
        spawned = []

        def is_free_tile(x, y):
            if not (0 <= x < game_map.width and 0 <= y < game_map.height):
                return False
            if not game_map.is_walkable(x, y) or is_water_tile(game_map.tiles[y][x]):
                return False
            if getattr(game_map.tiles[y][x], "name", "") in structure_names:
                return False
            if (x, y) in dungeon_entrances:
                return False
            if any(m.x == x and m.y == y for m in spawned):
                return False
            return True

        num_groups = random.randint(*self.OVERWORLD_MONSTER_GROUP_COUNT)
        for _ in range(num_groups):
            anchor_x = random.randint(0, game_map.width - 1)
            anchor_y = random.randint(0, game_map.height - 1)
            radius = self.OVERWORLD_GROUP_SEARCH_RADIUS

            valid_positions = [
                (x, y)
                for y in range(anchor_y - radius, anchor_y + radius + 1)
                for x in range(anchor_x - radius, anchor_x + radius + 1)
                if is_free_tile(x, y)
            ]
            if not valid_positions:
                continue  # Anchor landed somewhere too cramped (water, town, etc.) - skip this group

            primary_monster_class = random.choice(possible_monsters)
            compatible_types = MONSTER_GROUPS.get(primary_monster_class.__name__, [primary_monster_class.__name__])
            min_spawn, max_spawn = (1, 4) if len(compatible_types) > 1 else (1, 2)
            num_to_spawn = random.randint(min_spawn, max_spawn)

            # Shared by every monster spawned around this anchor -- see
            # Monster.group_id/provoke(): attacking one PASSIVE/NEUTRAL
            # member of the cluster (a centaur band, a myconid grove, ...)
            # alerts the rest of it at the same time.
            group_id = f"overworld_pack:{uuid.uuid4().hex[:8]}"

            for _ in range(num_to_spawn):
                if not valid_positions:
                    break
                # Compatible pack members are looked up by name against the classes
                # already imported into this module (globals()), the same way
                # MONSTER_GROUPS names are resolved for dungeon packs.
                monster_type_name = random.choice(compatible_types)
                monster_class = globals().get(monster_type_name, primary_monster_class)
                spawn_x, spawn_y = random.choice(valid_positions)
                valid_positions.remove((spawn_x, spawn_y))
                monster = monster_class(spawn_x, spawn_y)
                monster.group_id = group_id
                spawned.append(monster)

        return spawned

    # --- World Encounters -------------------------------------------------
    # Narrative interrupts while walking the overworld: instead of every tile
    # silently hiding a monster group, occasionally the player hears a hook
    # ("You hear screams ahead.") and gets a WORLD_ENCOUNTER_MENU offering
    # whichever choices the triggered scenario's own JSON declares (see
    # "choices" in Bandit_Ambush.json and _normalize_world_encounter_
    # choices()) before finding out what's actually going on.
    WORLD_ENCOUNTER_CHANCE = 0.02           # Rolled once per step taken in the overworld
    WORLD_ENCOUNTER_COOLDOWN_STEPS = 60     # Minimum steps before another can trigger
    WORLD_ENCOUNTER_STRUCTURE_TILES = {"Witch Hut", "Watchtower", "Shrine", "Cabin", "Tavern", "Shop", "House"}
    WORLD_ENCOUNTER_MIN_ENTITY_DISTANCE = 8  # Skip the roll if another live entity is already this close

    # Default player-level band for a scenario that declares neither
    # "min_level" nor "max_level" -- wide open, so every encounter authored
    # before level-gating existed (or any scenario that's genuinely meant
    # to stay relevant at any level, like Roadside_Shrine.json) keeps
    # rolling exactly as it always has. See
    # _normalize_world_encounter_level_range()/_roll_world_encounter_scenario().
    WORLD_ENCOUNTER_DEFAULT_MIN_LEVEL = 1
    WORLD_ENCOUNTER_DEFAULT_MAX_LEVEL = None

    # Minimum empty tiles kept between two structures' footprints when a
    # stage's "landmark_structure" names more than one (see
    # _place_world_encounter_structure_cluster()), plus extra random slack
    # layered on top purely for visual variety -- same "guaranteed floor,
    # jittered on top" shape world_generator.py's _place_town() uses for
    # TOWN_BUILDING_GAP/TOWN_LAYOUT_JITTER.
    WORLD_ENCOUNTER_STRUCTURE_GAP = 2
    WORLD_ENCOUNTER_STRUCTURE_JITTER = 3

    # How far off the player a landmark_structure gets anchored (see
    # _world_encounter_structure_anchor()) -- Chebyshev distance, matching
    # this project's diagonal-adjacency convention (max(|dx|, |dy|), not
    # Manhattan). A single building only needs to clear
    # WORLD_ENCOUNTER_STRUCTURE_MIN_DISTANCE; a multi-building cluster
    # (e.g. Undead_Siege.json's tavern-plus-houses) anchors further out
    # still, since _world_encounter_next_cluster_anchor() spreads later
    # buildings outward from the first one in a random direction and
    # could otherwise drift a house back toward the player.
    WORLD_ENCOUNTER_STRUCTURE_MIN_DISTANCE = 6
    WORLD_ENCOUNTER_STRUCTURE_CLUSTER_MIN_DISTANCE = 8
    WORLD_ENCOUNTER_STRUCTURE_SEARCH_RADIUS = 6

    # An "advance" choice (see WORLD_ENCOUNTER_ACTIONS/_resolve_world_encounter_
    # advance()) doesn't reveal a staged scenario's next beat instantly -- the
    # player has to actually walk there. WORLD_ENCOUNTER_STAGE_ADVANCE_MIN_STEPS
    # is a hard floor (the next stage can never trigger before this many steps
    # have passed); once cleared, WORLD_ENCOUNTER_STAGE_ADVANCE_CHANCE is
    # rolled once per additional step, same "small per-step chance" shape as
    # WORLD_ENCOUNTER_CHANCE above, so the reveal lands a handful of steps
    # past the floor rather than on the exact same step every time. See
    # _maybe_advance_world_encounter_stage().
    WORLD_ENCOUNTER_STAGE_ADVANCE_MIN_STEPS = 5
    WORLD_ENCOUNTER_STAGE_ADVANCE_CHANCE = 0.20

    WORLD_ENCOUNTER_HOOKS = [
        "You hear screams ahead.",
        "Raised voices and the clash of steel drift through the trees.",
        "A plume of smoke rises over the next rise.",
        "Something is snarling and thrashing just out of sight.",
    ]

    # Content root for world-encounter JSON, one file per scenario -- see
    # content/encounters/*.json and _load_world_encounter_scenarios().
    # Mirrors StoryContentLoader.CONTENT_ROOT ("content/stories") for
    # authored quests, just with a lighter schema: no fixed location or
    # search_area, since a world encounter can trigger anywhere the player
    # happens to be walking.
    WORLD_ENCOUNTER_CONTENT_ROOT = "content/encounters"
    WORLD_CAMPAIGN_CONTENT_ROOT = "content/stories"

    # A world encounter's JSON declares its monster_pool as plain class
    # names (e.g. "Goblin") rather than importing Python classes itself --
    # this is the lookup _load_world_encounter_scenarios() resolves them
    # through. Add an entry here whenever a new monster type is used in an
    # encounter file.
    WORLD_ENCOUNTER_MONSTER_CLASSES = {
        "Goblin": Goblin,
        "GoblinArcher": GoblinArcher,
        "Orc": Orc,
        "Wolf": Wolf,
        "Skeleton": Skeleton,
        "SkeletonArcher": SkeletonArcher,
        "Imp": Imp,
        "Cultist": Cultist,
        "GiantRat": GiantRat,
        "GiantSpider": GiantSpider,
        "Lizardfolk": Lizardfolk,
        "LizardfolkArcher": LizardfolkArcher,
        "Wererat": Wererat,
        "Troll": Troll,
        "Centaur": Centaur,
        "CentaurArcher": CentaurArcher,
        "MyconidSprout": MyconidSprout,
        "MyconidAdult": MyconidAdult,
    }

    # A stage's (or wave's) optional "disposition" string, resolved to
    # entities/monster.py's Disposition enum -- see _normalize_world_
    # encounter_stage() and Disposition's own docstring. Lets a scenario
    # like Centaur_Crossing.json spawn its monster_pool PASSIVE/NEUTRAL
    # (territorial, not hostile on sight) instead of every world-encounter
    # monster defaulting to AGGRESSIVE. A PASSIVE/NEUTRAL monster does
    # nothing at all -- no chasing, no Opportunity Attack -- until the
    # player actually attacks one, at which point Monster.provoke() makes
    # that monster (and, via _alert_group(), every other living monster
    # sharing its group_id) AGGRESSIVE, and the "Opportunity Attack Check"
    # in try_move_player() starts applying to them from then on.
    WORLD_ENCOUNTER_DISPOSITIONS = {
        "aggressive": Disposition.AGGRESSIVE,
        "passive": Disposition.PASSIVE,
        "neutral": Disposition.NEUTRAL,
    }

    # A world encounter's (or authored quest's) "give_item"/"remove_item"
    # Consequence (see consequence_system.py's GiveItemConsequence/
    # GameExecutionContext.give_item() in story_integration.py) names its
    # item as a short string key rather than importing items.py itself --
    # this is the lookup give_item_to_player()/remove_item_from_player()
    # resolve those keys through, the same division of labor
    # WORLD_ENCOUNTER_MONSTER_CLASSES above already uses for monster_pool
    # names. Add an entry here whenever a new item is referenced from
    # content. Values are items.py's own shared module-level instances --
    # give_item_to_player() copy.copy()s one per unit granted rather than
    # handing out that literal shared object, so two different rewards
    # (or two grants of the same reward) never alias the same instance.
    WORLD_ENCOUNTER_ITEM_TEMPLATES = {
        "torch": torch,
        "wood_plank": wood_plank,
        "meat": meat,
        "green_apple": green_apple,
        "fromage": fromage,
        "bread": bread,
        "mushroom": mushroom,
        "lesser_healing_potion": lesser_healing_potion,
        "greater_healing_potion": greater_healing_potion,
        "iron_dagger": iron_dagger,
        "silver_dagger": silver_dagger,
        "bronze_short_sword": bronze_short_sword,
        "iron_short_sword": iron_short_sword,
        "iron_long_sword": iron_long_sword,
        "steel_long_sword": steel_long_sword,
        "oak_staff": oak_staff,
        "apprentices_staff": apprentices_staff,
        "pole_arm": pole_arm,
        "steel_battle_axe": steel_battle_axe,
        "steel_rapier": steel_rapier,
        "iron_hammer": iron_hammer,
        "steel_maul": steel_maul,
        "steel_mace": steel_mace,
        "dwarven_flail": dwarven_flail,
        "round_shield": round_shield,
        "kite_shield": kite_shield,
        "tower_shield": tower_shield,
        "padded_armor": padded_armor,
        "studded_leather_armor": studded_leather_armor,
        "chainmail_armor": chainmail_armor,
        "half_plate_armor": half_plate_armor,
        "robes": robes,
        "leather_cap": leather_cap,
        "iron_helmet": iron_helmet,
        "steel_helmet": steel_helmet,
        "great_helm": great_helm,
        "mages_circlet": mages_circlet,
        "hood_of_shadows": hood_of_shadows,
        "leather_boots": leather_boots,
        "iron_greaves": iron_greaves,
        "boots_of_speed": boots_of_speed,
        "boots_of_stealth": boots_of_stealth,
        "dwarven_stompers": dwarven_stompers,
    }

    # A world encounter's JSON may declare a "landmark_tile" (e.g.
    # Bandit_Ambush.json's ransacked "caravan") -- a static map tile
    # dropped near the player alongside the monsters/victims, giving the
    # scene a physical prop instead of only narration. Resolved by name
    # at spawn time via _spawn_world_encounter_landmark_tile(); scenarios
    # that omit "landmark_tile" simply skip that step. "landmark_tile_
    # amount" (a fixed int, or a [min, max] range like "monster_count")
    # controls how many copies get placed -- defaults to exactly one.
    #
    # "landmark_tile" itself may be a single key (e.g. "ambush_tree") or
    # a list of keys (e.g. Bandit_Ambush.json's ["caravan", "barricade"])
    # -- see _normalize_world_encounter_tile_pool(). When a scenario
    # supplies more than one key, each individual placement independently
    # rolls a random tile from that pool, so a multi-tile scene reads as
    # a believable, varied clutter of wreckage instead of copies of the
    # exact same prop.
    WORLD_ENCOUNTER_TILE_TYPES = {
        "caravan": caravan,
        "ritual_circle": ritual_circle,
        "barricade": barricade,
        "ambush_tree": ambush_tree,
        "overworld_cobweb": overworld_cobweb,
        "gravestone": gravestone,
        "gravestone_two": gravestone_two,
        "gravestone_three": gravestone_three,
        "tent": tent
    }

    # A world encounter's JSON may instead (or additionally) declare a
    # "landmark_structure" (e.g. Roadside_Shrine.json's "shrine") -- a
    # whole multi-tile building from structures.py's STRUCTURE_BLUEPRINTS,
    # rather than a single decorative tile. Unlike "landmark_tile", which
    # only gets placed once combat actually spawns (see
    # _spawn_world_encounter_landmark_tile(), called from
    # _spawn_world_encounter_monsters()), a landmark_structure is placed
    # the moment the encounter triggers -- see
    # _spawn_world_encounter_landmark_structure(), called from
    # _maybe_trigger_world_encounter() -- since non-combat scenarios built
    # entirely from "resolve" choices (see WORLD_ENCOUNTER_ACTIONS) never
    # go through monster spawning at all, and the shrine/cabin/watchtower
    # the discovery text describes should already be standing there the
    # moment the player is offered the menu. No lookup table is needed
    # here the way WORLD_ENCOUNTER_TILE_TYPES needs one -- structure keys
    # are resolved directly against structures.py's own registry via
    # get_structure_blueprint()/place_structure_at_anchor().
    #
    # "landmark_structure" may be a single key (e.g. Roadside_Shrine.json's
    # "shrine") or a list of keys (e.g. Undead_Siege.json's
    # ["tavern", "house", "house"] for a small roadside hamlet) -- see
    # _normalize_world_encounter_structure_list(). A multi-key value places
    # every named structure at once as one loose cluster (see
    # _place_world_encounter_structure_cluster()), the same "single key or
    # list of keys" shape "landmark_tile" already uses, just placing every
    # entry instead of drawing one at random per placement.

    # The vocabulary of built-in *behaviors* a scenario's "choices" block
    # can pick from via each choice's "action" field (see
    # _resolve_world_encounter_choice() and _normalize_world_encounter_
    # choices() below). Adding a genuinely new behavior -- not just new
    # flavor text on an existing one -- means implementing a
    # `_resolve_world_encounter_<action>()` method and adding its name
    # here. Everything about *how* a behavior is offered to the player
    # (its label, description, color, key binding, and whether it cancels
    # the encounter like Ignore/ESC does) is entirely up to each
    # scenario's own JSON from this point on -- game.py no longer
    # hardcodes "there are exactly three options."
    #
    # "resolve" is the odd one out: investigate/sneak/ignore/advance are
    # fully scripted in Python, while a "resolve" choice is entirely
    # data-driven -- its own "outcome"/"consequences" (see
    # _normalize_world_encounter_choices()) decide what happens, the
    # same way a post-combat "aftermath" choice already works. This is
    # what a non-combat encounter (one with no "monster_pool" at all --
    # see Lost_Pilgrim.json) uses instead of investigate/sneak, since
    # there's no fight to start.
    #
    # "advance" is how a *staged* scenario (see "stages" below) walks the
    # player past the beat currently on screen without investigating,
    # sneaking, or ignoring it outright -- e.g. passing the broken wagon
    # to press on toward the campfire beyond it. Like "resolve", its own
    # "outcome"/"consequences" describe whatever happens along the way
    # (a moment of unease, a scrap of loot), but "outcome" isn't required
    # the way "resolve"'s is, since walking past a beat needn't say
    # anything at all. See _resolve_world_encounter_advance().
    WORLD_ENCOUNTER_ACTIONS = ("investigate", "sneak", "ignore", "resolve", "advance")

    # A world encounter's JSON can either describe a single beat with its
    # flat "discovery"/"landmark_tile"/"monster_pool"/"choices" fields
    # (unchanged since before staging existed -- see Wolf_Pack.json and
    # Spider_Nest.json) or an ordered "stages" list of several such
    # beats, each revealed one at a time as the player presses forward:
    #
    #     "stages": [
    #       {"discovery": "...", "landmark_tile": "wagon", "choices": [...advance/investigate/ignore...]},
    #       {"discovery": "...", "landmark_tile": "campfire", "choices": [...advance/investigate/ignore...]},
    #       {"discovery": "...", "monster_pool": [...], "monster_count": [3, 4], "choices": [...investigate/sneak/ignore...]}
    #     ]
    #
    # Only the *final* stage typically declares "monster_pool" -- see
    # Bandit_Ambush.json's wagon -> campfire -> goblin camp progression --
    # but any stage may, and any stage's choices may offer "investigate"/
    # "sneak" to start a fight right there instead of walking further in.
    # A scenario with no "stages" block at all is treated as a single
    # implicit stage built from its own top-level fields (see
    # _load_world_encounter_scenarios()), so every scenario written before
    # staging existed keeps working completely unchanged.
    WORLD_ENCOUNTER_STAGE_FIELDS = (
        "discovery", "landmark_tile", "landmark_tile_amount", "landmark_structure",
        "monster_pool", "monster_count", "disposition", "choices", "sneak_dc",
        "sneak_success", "sneak_fail", "ignore", "investigate_message",
    )

    # Fallback menu for any world-encounter JSON that doesn't declare its
    # own "choices" block, so existing/older content files keep working
    # unchanged. New or updated scenarios (see Bandit_Ambush.json) declare
    # "choices" directly and can offer as many, or as few, options as
    # they like, in whatever order and with whatever wording they want.
    DEFAULT_WORLD_ENCOUNTER_CHOICES = [
        {
            "key": 1,
            "action": "investigate",
            "label": "Investigate",
            "description": "Walk in and see what's happening",
            "color": (255, 160, 100),
        },
        {
            "key": 2,
            "action": "sneak",
            "label": "Sneak Around",
            "description": "Stealth check to glimpse it unseen",
            "color": (160, 200, 255),
        },
        {
            "key": 3,
            "action": "ignore",
            "label": "Ignore",
            "description": "ESC also cancels - just keep walking",
            "color": (150, 150, 150),
            "is_cancel": True,
        },
    ]

    def _normalize_world_encounter_choices(self, choices, source_name):
        """
        Validates a scenario's "choices" block (see Bandit_Ambush.json)
        and fills in display defaults, called once per file by
        _load_world_encounter_scenarios(). Falls back to
        DEFAULT_WORLD_ENCOUNTER_CHOICES entirely if the scenario didn't
        declare "choices" at all, or if every declared choice turned out
        to be invalid, so a missing/malformed block never leaves an
        encounter with an empty menu.

        Each choice needs a "key" (the number key that selects it -- see
        _world_encounter_choice_for_key()) and an "action" naming one of
        WORLD_ENCOUNTER_ACTIONS; anything else (label/description/color/
        is_cancel) is optional and defaulted here. A choice naming an
        unknown action is dropped, with a load-error message, rather
        than failing the whole file over one bad entry.

        Every choice also picks up the same "outcome"/"consequences"/
        "hours"/"escort" fields _normalize_world_encounter_aftermath()'s
        choices carry (defaulted to empty/false when a scenario doesn't
        set them). investigate/sneak/ignore ignore all four -- their
        behavior is fully scripted in Python -- but "resolve" and
        "advance" choices (see WORLD_ENCOUNTER_ACTIONS) read them
        exactly like an aftermath choice does, so one schema covers all
        three instead of several. A "resolve" choice missing "outcome"
        is dropped the same way a choice with an unknown action is;
        "advance" has no such requirement, since walking past a beat
        needn't say anything at all.

        An "advance" choice may also declare "next_stage": the "id" of
        whichever stage (see _normalize_world_encounter_stage()) it
        should reveal next. This is what lets a scenario's choices
        actually branch -- e.g. Spider_Nest.json's "Push Through the
        Webbing" and "Look for a Way Around" naming two different
        next_stage ids -- instead of every "advance" choice on a stage
        silently funneling back to the same next entry in "stages"
        regardless of which one the player picked. Left unset, an
        "advance" choice falls back to that old linear "next entry in
        the list" behavior (see _resolve_world_encounter_advance()), so
        a scenario that never sets it keeps working exactly as before.
        Only meaningful on "advance" -- every other action already ends
        or fully resolves the encounter without revealing another stage.
        """
        if not choices:
            return [dict(default) for default in self.DEFAULT_WORLD_ENCOUNTER_CHOICES]

        normalized = []
        for choice in choices:
            action = choice.get("action")
            if action not in self.WORLD_ENCOUNTER_ACTIONS or "key" not in choice:
                self.message_log.add_message(
                    f"Encounter load error ({source_name}): invalid choice {choice!r}", (255, 100, 100)
                )
                continue
            if action == "resolve" and "outcome" not in choice:
                self.message_log.add_message(
                    f"Encounter load error ({source_name}): 'resolve' choice needs an 'outcome' {choice!r}",
                    (255, 100, 100),
                )
                continue
            normalized.append({
                "key": choice["key"],
                "action": action,
                "label": choice.get("label", action.title()),
                "description": choice.get("description", ""),
                "color": tuple(choice.get("color", (200, 200, 200))),
                "is_cancel": choice.get("is_cancel", False),
                "outcome": choice.get("outcome", ""),
                "hours": choice.get("hours", 0),
                "consequences": [consequence_from_dict(c) for c in choice.get("consequences", [])],
                "escort": choice.get("escort", False),
                "next_stage": choice.get("next_stage"),
            })

        return normalized or [dict(default) for default in self.DEFAULT_WORLD_ENCOUNTER_CHOICES]

    def _normalize_world_encounter_range(self, value):
        """
        Accepts either a single int (a fixed amount, e.g. Wolf_Pack.json's
        "landmark_tile_amount": 1) or a [min, max] list (a random range,
        inclusive -- same shape "monster_count"/"victim_count" already
        use, e.g. Undead_Siege.json's "landmark_tile_amount": [2, 4]) and
        returns a (min, max) tuple either way, so callers always unpack
        the same way regardless of which form a scenario's JSON used.
        """
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return (value, value)

    def _normalize_world_encounter_tile_pool(self, value):
        """
        Accepts a scenario's "landmark_tile" field in either of two
        shapes -- a single key (e.g. Wolf_Pack.json's "ambush_tree") or a
        list of keys (e.g. Bandit_Ambush.json's ["caravan", "barricade"])
        -- and always returns a list, so _spawn_world_encounter_landmark_
        tile() can treat every scenario as "a pool of one or more tile
        types to draw from" without caring which form the JSON used.
        Returns an empty list for a missing/None field (no landmark at
        all), unchanged prior behavior for scenarios that never had one.
        """
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _normalize_world_encounter_structure_list(self, value):
        """
        Accepts a scenario's "landmark_structure" field in either of two
        shapes -- a single key (e.g. Roadside_Shrine.json's "shrine") or a
        list of keys (e.g. Undead_Siege.json's ["tavern", "house", "house"])
        -- and always returns a list, so _spawn_world_encounter_landmark_
        structure() can treat every scenario as "one or more structures to
        place together" without caring which form the JSON used.

        Same normalization shape as _normalize_world_encounter_tile_pool()
        just above, but kept as its own method rather than reused directly:
        a landmark_tile pool is drawn from at random per placement, while
        every key here gets placed, as a single cluster (see
        _place_world_encounter_structure_cluster()) -- different enough
        semantics that sharing one method would be misleading to read at
        the call site.
        """
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _resolve_world_encounter_disposition(self, value, source):
        """
        Resolves a stage's (or wave's) optional "disposition" string
        (see WORLD_ENCOUNTER_DISPOSITIONS) to a Disposition enum member.
        Returns None for a stage that doesn't declare one at all, so the
        spawned monster keeps whatever its class's __init__ already sets
        (AGGRESSIVE for most, PASSIVE for Centaur/MyconidSprout/etc. --
        see monster.py) rather than this method silently overriding it.
        An unrecognized string logs a load error and falls back to that
        same None/"leave it alone" behavior, rather than crashing the
        whole file over one typo.
        """
        if value is None:
            return None
        disposition = self.WORLD_ENCOUNTER_DISPOSITIONS.get(value)
        if disposition is None:
            self.message_log.add_message(
                f"Encounter load error ({source}): unknown disposition {value!r}", (255, 100, 100)
            )
        return disposition

    def _normalize_world_encounter_stage(self, stage_data, source_name, stage_index):
        """
        Normalizes one entry of a scenario's "stages" list (see
        WORLD_ENCOUNTER_STAGE_FIELDS) into the shape the rest of the
        world-encounter pipeline expects -- resolved monster classes,
        a (min, max) tile amount, normalized choices, and so on. Also
        used by _load_world_encounter_scenarios() to build the single
        implicit stage of a legacy, non-staged scenario, so both paths
        -- an authored "stages" list and an old flat scenario file --
        produce identical stage dicts and every other method in this
        pipeline only ever has to think in terms of "the current stage".

        Not every stage needs every field: a narrative-only beat (e.g.
        a broken wagon the player can only investigate/ignore/advance
        past) simply omits "monster_pool"/"sneak_dc"/etc. and gets empty/
        None defaults for them, exactly like a non-combat scenario's
        single implicit stage already did before staging existed.
        """
        source = f"{source_name} stage {stage_index}"

        monster_pool = [
            self.WORLD_ENCOUNTER_MONSTER_CLASSES[name] for name in stage_data.get("monster_pool", [])
        ]
        return {
            # Defaults to the stage's own position in "stages" (as a
            # string) so a scenario that never names its stages keeps
            # behaving exactly as before -- only content that wants a
            # choice to jump somewhere other than "the next entry in the
            # list" (see "next_stage" in _normalize_world_encounter_
            # choices()) needs to give a stage an explicit "id".
            "id": str(stage_data.get("id", stage_index)),
            "discovery": stage_data.get("discovery", ""),
            "landmark_tile": self._normalize_world_encounter_tile_pool(stage_data.get("landmark_tile")),
            "landmark_tile_amount": self._normalize_world_encounter_range(
                stage_data.get("landmark_tile_amount", 1)
            ),
            # Always a list, even for a scenario declaring a single key
            # (e.g. "shrine") rather than ["tavern", "house"] -- see
            # _normalize_world_encounter_structure_list() and
            # _spawn_world_encounter_landmark_structure(). An empty list
            # means the stage declares no landmark_structure at all.
            "landmark_structure": self._normalize_world_encounter_structure_list(
                stage_data.get("landmark_structure")
            ),
            "monster_pool": monster_pool,
            "monster_count": tuple(stage_data.get("monster_count", (0, 0))),
            # None (the default) leaves each spawned monster's own class
            # default disposition alone -- see WORLD_ENCOUNTER_DISPOSITIONS
            # and _spawn_world_encounter_monsters().
            "disposition": self._resolve_world_encounter_disposition(
                stage_data.get("disposition"), source
            ),
            "combat": bool(monster_pool),
            "sneak_dc": stage_data.get("sneak_dc"),
            "sneak_success": stage_data.get("sneak_success", ""),
            "sneak_fail": stage_data.get("sneak_fail", ""),
            "ignore": stage_data.get("ignore", ""),
            # Logged by _resolve_world_encounter_investigate() once its
            # monster_pool is spawned. Defaults to the line every combat
            # stage used unconditionally before this field existed, so
            # only a stage that actually wants different flavor (e.g. one
            # spawning PASSIVE wildlife -- see Disposition in entities/
            # monster.py -- that the player is walking up to, not attacking)
            # needs to set it.
            "investigate_message": stage_data.get("investigate_message", "You step in to help, weapon drawn!"),
            "choices": self._normalize_world_encounter_choices(stage_data.get("choices"), source),
        }

    def _normalize_world_encounter_aftermath(self, aftermath, source_name):
        """
        Validates a scenario's optional "aftermath" block (see
        Wolf_Pack.json) -- a second, post-combat branching choice offered
        once the encounter's fight is won (see _wire_world_encounter_
        rewards()'s STORY_COMPLETED hook), e.g. deciding what becomes of
        a rescued victim. Unlike _normalize_world_encounter_choices()'s
        "choices", an aftermath choice never dispatches to a
        `_resolve_world_encounter_<action>()` method -- "action" here is
        just a label for logging/debugging, and resolution is entirely
        data-driven: an "outcome" line for the message log plus a list of
        Consequences (consequence_system.py's consequence_from_dict) run
        through the shared ConsequenceExecutor, exactly like an authored
        JSON quest's `rewards.on_complete`.

        Returns None if the scenario declares no "aftermath" at all (most
        won't need one) or if every declared choice turned out to be
        invalid -- there is no generic fallback menu here the way there
        is for the discovery "choices", since a bad aftermath block
        should just be skipped rather than forcing an unrelated decision
        on the player.
        """
        if not aftermath:
            return None

        choices = []
        for choice in aftermath.get("choices", []):
            if "key" not in choice or "outcome" not in choice:
                self.message_log.add_message(
                    f"Encounter load error ({source_name}): invalid aftermath choice {choice!r}", (255, 100, 100)
                )
                continue
            action = choice.get("action", "choose")
            choices.append({
                "key": choice["key"],
                "action": action,
                "label": choice.get("label", action.title()),
                "description": choice.get("description", ""),
                "color": tuple(choice.get("color", (200, 200, 200))),
                "is_cancel": choice.get("is_cancel", False),
                "outcome": choice["outcome"],
                "hours": choice.get("hours", 0),
                "consequences": [consequence_from_dict(c) for c in choice.get("consequences", [])],
                # Opt-in flag (not a Consequence, since it doesn't mutate
                # game/execution state the way consequence_system.py's
                # types do -- it recruits one of *this* encounter's own
                # victim entities, which only game.py knows about) --
                # see recruit_companion()/_resolve_world_encounter_
                # aftermath_choice() below.
                "escort": choice.get("escort", False),
            })

        if not choices:
            return None
        return {"discovery": aftermath.get("discovery", ""), "choices": choices}

    def _normalize_world_encounter_waves(self, waves, source_name):
        """
        Validates a scenario's optional "waves" block -- extra surges of
        monsters that spawn once the previous wave (the scenario's own
        top-level monster_pool/monster_count, or a prior wave in this
        same list) is entirely defeated, before the encounter's rewards/
        aftermath fire (see _advance_world_encounter_wave()). Undead_
        Siege.json uses this for a second surge of undead once the first
        is cleared, but any scenario can declare one the same way.

        Each wave needs its own "monster_pool" (resolved to Python
        classes the same way the top-level one is, see
        _load_world_encounter_scenarios()) and "monster_count"
        ([min, max], same shape as the top-level field). "discovery" is
        an optional message logged when the wave arrives, so the player
        gets a beat of warning instead of monsters just appearing.
        Returns an empty list for a scenario with no "waves" at all
        (every encounter before this stayed a single fight, unchanged).
        A malformed wave is dropped, with a load-error message, rather
        than failing the whole file over one bad entry.
        """
        if not waves:
            return []

        normalized = []
        for wave in waves:
            try:
                monster_pool = [self.WORLD_ENCOUNTER_MONSTER_CLASSES[name] for name in wave["monster_pool"]]
                monster_count = tuple(wave["monster_count"])
            except (KeyError, TypeError, ValueError) as exc:
                self.message_log.add_message(
                    f"Encounter load error ({source_name}): invalid wave {wave!r} ({exc})", (255, 100, 100)
                )
                continue
            normalized.append({
                "discovery": wave.get("discovery", ""),
                "monster_pool": monster_pool,
                "monster_count": monster_count,
                # Same optional override as a stage's own "disposition" --
                # see WORLD_ENCOUNTER_DISPOSITIONS and _resolve_world_
                # encounter_disposition(). None leaves each wave monster's
                # class default alone.
                "disposition": self._resolve_world_encounter_disposition(
                    wave.get("disposition"), f"{source_name} wave"
                ),
            })
        return normalized

    def _normalize_world_encounter_level_range(self, data, source_name):
        """
        Validates a scenario's optional top-level "min_level"/"max_level"
        fields -- the band of player levels this encounter is written
        for (a level 1 character shouldn't stumble into Troll_Toll.json,
        and a high-level veteran shouldn't keep tripping Rat_Infested_
        Cabin.json). Consulted by _roll_world_encounter_scenario() when
        picking which scenario to offer next.

        Both fields are optional and independent: a missing "min_level"
        falls back to WORLD_ENCOUNTER_DEFAULT_MIN_LEVEL, a missing
        "max_level" to WORLD_ENCOUNTER_DEFAULT_MAX_LEVEL (None, meaning
        no ceiling) -- so a scenario can set a floor without a ceiling
        (Undead_Siege.json staying relevant at any high level) or omit
        both entirely (Roadside_Shrine.json, always in the pool). An
        unparseable value logs a load error and falls back to the wide-
        open default band rather than dropping the scenario; a min above
        max is corrected by swapping, also with a load error, so a typo
        shrinks the band to nothing instead of silently excluding the
        scenario forever.
        """
        min_level = data.get("min_level", self.WORLD_ENCOUNTER_DEFAULT_MIN_LEVEL)
        max_level = data.get("max_level", self.WORLD_ENCOUNTER_DEFAULT_MAX_LEVEL)

        try:
            min_level = int(min_level)
            max_level = int(max_level) if max_level is not None else None
        except (TypeError, ValueError):
            self.message_log.add_message(
                f"Encounter load error ({source_name}): invalid min_level/max_level "
                f"({min_level!r}/{max_level!r}), defaulting to unrestricted",
                (255, 100, 100),
            )
            return self.WORLD_ENCOUNTER_DEFAULT_MIN_LEVEL, self.WORLD_ENCOUNTER_DEFAULT_MAX_LEVEL

        min_level = max(1, min_level)
        if max_level is not None and max_level < min_level:
            self.message_log.add_message(
                f"Encounter load error ({source_name}): min_level {min_level} "
                f"exceeds max_level {max_level}, swapping",
                (255, 100, 100),
            )
            min_level, max_level = max_level, min_level

        return min_level, max_level

    def _load_world_encounter_scenarios(self):
        """
        Loads every *.json file under WORLD_ENCOUNTER_CONTENT_ROOT into a
        scenario dict -- the same "flavor text plus story-engine metadata"
        shape the scenarios used to have as a hardcoded Python list, just
        authored in JSON now (see content/encounters/*.json, and compare
        to how Missing_Trader.json/Hollow_Shrine.json author full quests
        for story_content_loader.py). Deliberately not routed through
        StoryContentLoader itself: a world encounter has no fixed
        location/search_area and needs its monster_pool resolved to
        Python classes, neither of which that quest-oriented schema covers.
        Non-recursive, like StoryContentLoader.load_directory().
        """
        scenarios = []
        root = Path(self.WORLD_ENCOUNTER_CONTENT_ROOT)
        for path in sorted(root.glob("*.json")):
            try:
                data = json.loads(path.read_text())

                # A scenario either authors an ordered "stages" list
                # directly (see WORLD_ENCOUNTER_STAGE_FIELDS/Bandit_
                # Ambush.json's wagon -> campfire -> goblin camp) or
                # stays a single flat beat the old way (Wolf_Pack.json,
                # Spider_Nest.json) -- normalized here into a one-entry
                # "stages" list built from its own top-level fields, so
                # every other method in the pipeline only ever deals
                # with "the scenario's list of stages", never which
                # shape the source file used.
                if "stages" in data:
                    stages = [
                        self._normalize_world_encounter_stage(stage, path.name, index)
                        for index, stage in enumerate(data["stages"])
                    ]
                else:
                    legacy_stage = {field: data[field] for field in self.WORLD_ENCOUNTER_STAGE_FIELDS if field in data}
                    stages = [self._normalize_world_encounter_stage(legacy_stage, path.name, 0)]

                if not stages:
                    raise ValueError("scenario declares no stages")
                data["stages"] = stages

                # stage id -> index into "stages", so an "advance"
                # choice's "next_stage" (see _normalize_world_encounter_
                # choices()) can name where it branches to without the
                # rest of the pipeline needing to know ids exist at all
                # -- _resolve_world_encounter_advance() still only ever
                # deals in plain list indices. A choice naming an id this
                # scenario doesn't have is a content bug (a typo, or a
                # stage renamed without updating what points to it); it's
                # dropped back to the default "next entry in the list"
                # behavior with a load-error message, rather than either
                # crashing the whole file or silently going nowhere.
                stage_index_by_id = {stage["id"]: index for index, stage in enumerate(stages)}
                for stage in stages:
                    for choice in stage["choices"]:
                        next_stage_id = choice.get("next_stage")
                        if next_stage_id is not None and next_stage_id not in stage_index_by_id:
                            self.message_log.add_message(
                                f"Encounter load error ({path.name}): 'advance' choice "
                                f"{choice['label']!r} targets unknown next_stage {next_stage_id!r}",
                                (255, 100, 100),
                            )
                            choice["next_stage"] = None
                data["stage_index_by_id"] = stage_index_by_id

                data["victim_count"] = tuple(data.get("victim_count", (1, 1)))
                data["aftermath"] = self._normalize_world_encounter_aftermath(data.get("aftermath"), path.name)
                data["waves"] = self._normalize_world_encounter_waves(data.get("waves"), path.name)
                data["min_level"], data["max_level"] = self._normalize_world_encounter_level_range(data, path.name)
            except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
                self.message_log.add_message(f"Encounter load error ({path.name}): {exc}", (255, 100, 100))
                continue
            scenarios.append(data)
        return scenarios

    # --- Authored-story NPCs & landmarks -----------------------------------
    # Full quests (content/stories/*.json, loaded by StorySystems at startup
    # -- see story_content_loader.py) can declare their own cast up front via
    # an "npcs" block, e.g. Hollow_Shrine.json's cultist guards or
    # Missing_Trader.json's raiders and captive. StoryContentLoader stores
    # those declarations as content-only "npc_spawn" StoryObjects inside
    # each story's SearchArea; the methods below are the game-specific half
    # that turns them into real entities once a story actually starts, the
    # same division of labor WORLD_ENCOUNTER_MONSTER_CLASSES/
    # _spawn_world_encounter_monsters() already use for world encounters.

    STORY_NPC_MONSTER_CLASSES = {
        "cultist": Cultist,
        "goblin": Goblin,
        "goblin_archer": GoblinArcher,
        "orc": Orc,
        "wolf": Wolf,
        "skeleton": Skeleton,
        "skeleton_archer": SkeletonArcher,
        "imp": Imp,
        "bandit": Goblin,  # no dedicated Bandit class yet -- reuses Goblin's stats/AI
    }

    def _wire_story_npc_spawning(self):
        """
        Subscribes every story already loaded by StorySystems (see
        StorySystems.__init__ -> StoryContentLoader.load_directory()) to
        spawn its declared NPCs and register its landmarks the moment it
        starts (STORY_STARTED). Called once from Game.__init__, right
        after self.stories is constructed.
        """
        for story in self.stories.story_manager.list_stories():
            director = self.stories.story_manager.get_director(story.id)
            if director is not None:
                director.on(StoryEvent.STORY_STARTED, self._spawn_story_npcs)
                director.on(StoryEvent.STORY_STARTED, self._register_story_landmarks)

    def _spawn_story_npcs(self, story, **_context):
        """
        STORY_STARTED hook: spawns every "npc_spawn" StoryObject in this
        story's SearchArea as a real world entity, tagged so kill_npc/
        talk_npc triggers and GameConditionContext.is_npc_alive() all
        resolve against it using the id the story JSON gave it. Safe to
        call again if a story is resumed after a pause -- already-spawned
        NPCs are skipped.

        Story content (search_area/objects/npcs positions) is authored in
        the same global overworld tile space as `requirements.location`
        (see world_map.chunk_local_to_world_position/
        world_to_chunk_local_position) -- NOT the chunk-local x/y that
        self.entities and self.game_map actually use. Each spawn is
        converted to its (chunk_coord, local_position) here before it
        touches anything chunk-shaped:
          - if that chunk is already generated, the entity is appended to
            its persistent chunk["population"] list (surviving the
            player leaving and re-entering, the same as any other
            overworld monster group), and to self.entities immediately
            if that chunk happens to be the one currently loaded;
          - if the chunk hasn't been generated yet, the spawn is queued
            in self._pending_story_npc_spawns and drained into
            chunk["population"] the moment generate_overworld_map()
            actually creates that chunk.
        """
        if story.search_area is None:
            return
        for spawn in story.search_area.get_objects_by_type("npc_spawn"):
            if spawn.id in self.npc_registry:
                continue

            chunk_coord, local_position = world_position_to_chunk_local(spawn.position)
            entity = self._build_story_npc_entity(spawn, local_position)
            if entity is None:
                continue

            self.npc_registry[spawn.id] = entity
            self._place_story_entity_in_chunk(entity, chunk_coord)

    def _place_story_entity_in_chunk(self, entity, chunk_coord):
        """
        Adds a story-spawned entity to whichever chunk it belongs to,
        persistently (chunk["population"]) if that chunk already exists,
        or queued for the moment it's generated otherwise. Also drops it
        into self.entities right away when that chunk is the one
        currently loaded, so it's visible/interactable without requiring
        a chunk reload. Shared by _spawn_story_npcs() above and
        spawn_story_npc() below (the `spawn_npc` Consequence hook), so
        both paths place entities consistently.
        """
        chunk = self.overworld_chunks.get(chunk_coord)
        if chunk is not None:
            chunk.setdefault("population", []).append(entity)
        else:
            self._pending_story_npc_spawns.setdefault(chunk_coord, []).append(entity)

        if (
            self.game_state == GameState.OVERWORLD
            and chunk_coord == self.overworld_chunk_coord
            and entity not in self.entities
        ):
            self.entities.append(entity)

    def _build_story_npc_entity(self, spawn, local_position):
        """
        Builds the actual entity for one "npc_spawn" StoryObject, placed
        at `local_position` (already converted to chunk-local tile
        coordinates by the caller -- see _spawn_story_npcs()). Hostile
        entries (`data["hostile"]`) become real Monsters looked up via
        STORY_NPC_MONSTER_CLASSES by `data["type"]`, tagged with the
        story's own group_id so kill_npc triggers can match them (see
        story_integration.py's fire_kill). Everything else becomes an
        EncounterVictim-style NPC through the same make_encounter_victims()
        factory the world-encounter victims use (dungeon_npcs.py), with its
        preset looked up in self._victim_presets (built at startup from
        every world-encounter scenario's own "victim_data" -- see
        __init__) keyed off `role` and falling back to `type`, then
        "merchant", for any role that lookup doesn't recognize.
        """
        data = spawn.data
        x, y = local_position

        if data.get("hostile"):
            monster_cls = self.STORY_NPC_MONSTER_CLASSES.get(data.get("type"))
            if monster_cls is None:
                return None
            entity = monster_cls(x, y)
            entity.group_id = data.get("group_id")
        else:
            preset = (
                self._victim_presets.get(data.get("role"))
                or self._victim_presets.get(data.get("type"))
                or self._victim_presets.get("merchant")
            )
            victims = make_encounter_victims(preset, 1, [(x, y)])
            if not victims:
                return None
            entity = victims[0]

        entity.id = spawn.id
        return entity

    def _register_story_landmarks(self, story, **_context):
        """
        STORY_STARTED hook: registers every non-NPC StoryObject in this
        story's SearchArea (shrines, wagons, journals, ...) into
        self.landmark_registry, so GameExecutionContext.destroy_landmark()
        (story_integration.py) has something real to find and remove when
        a trigger's `destroy_landmark` consequence fires.
        """
        if story.search_area is None:
            return
        for obj in story.search_area.get_all_objects():
            if obj.object_type != "npc_spawn":
                self.landmark_registry[obj.id] = obj

    def spawn_story_npc(self, npc_type, position, data=None):
        """
        ExecutionContext.spawn_npc hook (story_integration.py): fires
        whenever a story's `spawn_npc` Consequence runs, e.g. a stage's
        on_enter reward such as Missing_Trader.json's "wolf_pack_marker".
        Reuses STORY_NPC_MONSTER_CLASSES; falls back to an inert
        "unspawned:" id (matching story_integration.py's own default) for
        marker types with no monster class, since those exist to advance
        the story rather than to be fought.
        """
        monster_cls = self.STORY_NPC_MONSTER_CLASSES.get(npc_type)
        if monster_cls is None:
            return f"unspawned:{npc_type}"
        x, y = int(position[0]), int(position[1])
        entity = monster_cls(x, y)
        entity.id = (data or {}).get("id", f"{npc_type}:{id(entity):x}")
        entity.group_id = (data or {}).get("group_id")
        self.entities.append(entity)
        self.npc_registry[entity.id] = entity
        return entity.id

    def spawn_story_merchant(self, merchant_type, position, inventory=None):
        """ExecutionContext.spawn_merchant hook (story_integration.py):
        spawns a generic DungeonMerchant for a story's `spawn_merchant`
        Consequence. `inventory`/`merchant_type` are accepted for schema
        compatibility but not yet used to customize wares."""
        x, y = int(position[0]), int(position[1])
        entity = DungeonMerchant(x, y)
        entity.id = f"{merchant_type}:{id(entity):x}"
        self.entities.append(entity)
        self.npc_registry[entity.id] = entity
        return entity.id

    def give_item_to_player(self, item_id, count=1):
        """
        ExecutionContext.give_item hook (story_integration.py's
        GameExecutionContext.give_item()): what a "give_item" Consequence
        actually does to self.player.inventory -- e.g. a rescued victim
        handing over a keepsake, or a non-combat encounter's "resolve"
        choice rewarding a specific item instead of (or alongside) raw
        gold/xp. `item_id` is looked up in WORLD_ENCOUNTER_ITEM_TEMPLATES
        the same way monster_pool names are resolved through
        WORLD_ENCOUNTER_MONSTER_CLASSES -- content references items by a
        short string key rather than importing items.py itself.

        Grants a fresh copy.copy() of the template per unit of `count`
        rather than handing out the same shared module-level item object
        more than once: items.py's instances (torch, iron_dagger, ...)
        are reused as read-only templates throughout this file (e.g.
        chest loot tables), and self.player.inventory.add_item() expects
        each stacked/equipped item to be its own object, not the literal
        same instance appearing twice over.

        An unknown item_id is a content mistake, not a player-facing
        failure -- logged once and otherwise a no-op, rather than raising
        out of whatever ConsequenceExecutor.execute() call this ran
        inside of (Consequence.execute() already swallows exceptions from
        _apply(), but a swallowed KeyError here would look identical to a
        silently-empty reward with no indication why).
        """
        template = self.WORLD_ENCOUNTER_ITEM_TEMPLATES.get(item_id)
        if template is None:
            self.message_log.add_message(f"(unknown reward item {item_id!r} -- nothing given)", (255, 100, 100))
            return

        for _ in range(max(1, count)):
            new_item = copy.copy(template)
            if not self.player.inventory.add_item(new_item):
                self.message_log.add_message(
                    f"Your inventory is full! You couldn't take the {new_item.name}.", (255, 0, 0)
                )
                break

    def remove_item_from_player(self, item_id, count=1):
        """
        ExecutionContext.remove_item hook: the other half of
        give_item_to_player() above -- what a "remove_item" Consequence
        (e.g. a non-combat encounter's choice where the player hands over
        supplies to someone in need) actually does. items.py items carry
        no string id of their own to match against directly, so this
        matches inventory items back to `item_id`'s template by name,
        removing up to `count` of them -- fewer than `count`, silently,
        if the player is carrying less than that, rather than raising.

        Unlike give_item_to_player(), an unknown item_id logs nothing:
        GameExecutionContext.remove_item() has no generic message of its
        own either, and a scenario giving away an item the player was
        never guaranteed to be carrying (e.g. an optional "if you still
        have one" supply donation) shouldn't read as an error.
        """
        template = self.WORLD_ENCOUNTER_ITEM_TEMPLATES.get(item_id)
        if template is None:
            return

        removed = 0
        for item in list(self.player.inventory.items):
            if removed >= count:
                break
            if item.name == template.name:
                self.player.inventory.remove_item(item)
                removed += 1

        if removed:
            label = template.name if removed == 1 else f"{template.name} x{removed}"
            self.message_log.add_message(f"You hand over {label}.", (200, 200, 255))

    def _entity_within_range(self, radius):
        """
        Whether any other live entity (a monster, NPC, or companion
        already in self.entities) currently sits within `radius` tiles
        of the player, using Chebyshev distance to match the square
        search patterns the rest of this file already uses (e.g.
        OVERWORLD_GROUP_SEARCH_RADIUS). Used to keep a fresh world
        encounter from spawning its own monster group right on top of
        something the player can already see -- see
        WORLD_ENCOUNTER_MIN_ENTITY_DISTANCE.
        """
        px, py = self.player.x, self.player.y
        for entity in self.entities:
            if entity is self.player or not getattr(entity, "alive", True):
                continue
            if max(abs(entity.x - px), abs(entity.y - py)) <= radius:
                return True
        return False

    def _maybe_trigger_world_encounter(self):
        """
        Rolls a small chance, once per overworld step, to interrupt travel with
        a WORLD_ENCOUNTER_MENU instead of silently letting the player walk on.
        Guarded by a cooldown so encounters don't stack back-to-back, and
        skipped entirely while standing on a structure tile (towns/shrines
        shouldn't ambush the player at their own doorstep) or while escorting
        a companion (self.companions -- see recruit_companion()/
        try_deliver_companions()): a fresh encounter piling onto an existing
        escort makes the escort itself untrackable (linked_monsters/
        escort_id assume one encounter's aftermath at a time) and undercuts
        the "get them somewhere safe" tension the escort is going for.

        Also skipped while a staged scenario's own next beat is queued (see
        _maybe_advance_world_encounter_stage()) -- an unrelated ambush
        shouldn't interrupt the walk toward a beat the player already
        committed to advancing into.
        """
        if self.companions:
            return False

        if self._world_encounter_pending_stage_index is not None:
            return False

        if self._world_encounter_cooldown > 0:
            self._world_encounter_cooldown -= 1
            return False

        tile_name = getattr(self.game_map.tiles[self.player.y][self.player.x], "name", "")
        if tile_name in self.WORLD_ENCOUNTER_STRUCTURE_TILES:
            return False

        if self._entity_within_range(self.WORLD_ENCOUNTER_MIN_ENTITY_DISTANCE):
            return False

        if random.random() > self.WORLD_ENCOUNTER_CHANCE:
            return False

        scenario = self._roll_world_encounter_scenario()
        self._world_encounter_target_victims = []
        self._world_encounter_story_id = self._create_world_encounter_story(scenario)
        self._world_encounter_cooldown = self.WORLD_ENCOUNTER_COOLDOWN_STEPS
        self.message_log.add_message(random.choice(self.WORLD_ENCOUNTER_HOOKS), (200, 200, 255))
        self._enter_world_encounter_stage(scenario, 0)
        return True

    def _maybe_advance_world_encounter_stage(self):
        """
        Rolls, once per overworld step, whether a staged scenario's queued
        next beat (see _resolve_world_encounter_advance()) finally reveals
        itself. A no-op returning False whenever nothing is queued
        (self._world_encounter_pending_stage_index is None) -- the common
        case, since most steps aren't taken mid-advance.

        Counts steps in self._world_encounter_advance_steps rather than
        rolling from the moment "advance" was picked, so the next beat
        can never trigger before WORLD_ENCOUNTER_STAGE_ADVANCE_MIN_STEPS
        have actually been walked -- "10 steps, then it's possible" reads
        as a real stretch of travel instead of an instant reveal that
        merely got delayed by a frame. Past that floor,
        WORLD_ENCOUNTER_STAGE_ADVANCE_CHANCE is rolled every further step
        (same "small per-step chance" shape as _maybe_trigger_world_
        encounter()'s WORLD_ENCOUNTER_CHANCE) until it lands, so the
        reveal doesn't fire on the exact same step every single time.

        Called from the same movement site as _maybe_trigger_world_
        encounter() (see that method's docstring for why a pending
        advance also suppresses a brand new, unrelated encounter from
        rolling in the meantime).
        """
        if self._world_encounter_pending_stage_index is None:
            return False

        self._world_encounter_advance_steps += 1
        if self._world_encounter_advance_steps < self.WORLD_ENCOUNTER_STAGE_ADVANCE_MIN_STEPS:
            return False

        if random.random() > self.WORLD_ENCOUNTER_STAGE_ADVANCE_CHANCE:
            return False

        scenario = self._world_encounter_target
        stage_index = self._world_encounter_pending_stage_index
        self._world_encounter_pending_stage_index = None
        self._world_encounter_advance_steps = 0
        self._enter_world_encounter_stage(scenario, stage_index)
        return True

    def _world_encounter_matches_player_level(self, scenario):
        """
        Whether `scenario`'s ["min_level", "max_level"] band (see
        _normalize_world_encounter_level_range()) covers the player's
        current level. A missing player (shouldn't happen once the
        overworld is reachable, but see the "before character creation"
        caution elsewhere in this file) is treated as level 1, so the
        check fails closed toward the earliest-game content rather than
        raising.
        """
        player_level = getattr(self.player, "level", 1)
        if player_level < scenario["min_level"]:
            return False
        if scenario["max_level"] is not None and player_level > scenario["max_level"]:
            return False
        return True

    def _roll_world_encounter_scenario(self):
        """
        Picks the scenario for a freshly-triggered world encounter.

        First narrows to scenarios whose level band covers the player
        right now (_world_encounter_matches_player_level()), so a fresh
        level 1 character doesn't stumble into Troll_Toll.json and a
        high-level veteran doesn't keep tripping Rat_Infested_Cabin.json.
        Within that level-appropriate pool, excludes whichever scenario
        was last rolled (self._world_encounter_last_id) so two ambushes
        in a row never repeat the exact same flavor.

        Both narrowing steps fall back gracefully rather than ever
        raising: if nothing in the full scenario list matches the
        player's level (a sparse content set, or a level outside
        anything authored), the level filter is dropped and every
        scenario is back in the running; if the level-appropriate pool
        turns out to be exactly the one just rolled, the last-id
        exclusion is dropped instead of leaving an empty pool.
        """
        level_appropriate = [
            scenario for scenario in self.world_encounter_scenarios
            if self._world_encounter_matches_player_level(scenario)
        ]
        pool = level_appropriate or self.world_encounter_scenarios

        pool = [scenario for scenario in pool if scenario["id"] != self._world_encounter_last_id] or pool

        scenario = random.choice(pool)
        self._world_encounter_last_id = scenario["id"]
        return scenario

    def _create_world_encounter_story(self, scenario):
        """
        Registers this ambush as a real (if tiny and unnamed) StoryInstance
        with the story engine the moment it's offered, rather than only
        after the player commits to a fight. This is what lets "ignore"
        route through StoryFailureManager's IGNORED failure mode -- a scar
        and a reputation hit exactly like an authored quest the player
        walked past -- instead of being a bespoke inline penalty.

        Stage 0 = "in progress"; stage 1 (the final stage) = "resolved",
        reached once every monster tagged with this encounter's own
        group_id has been killed (see _wire_world_encounter_combat()), or
        -- for a non-combat scenario (see WORLD_ENCOUNTER_ACTIONS'
        "resolve") -- the moment the player picks a resolving choice.
        The story stays UNINITIALIZED until the player actually commits
        (investigate/sneak/resolve) -- see StoryDirector.start().

        This StoryInstance's own two-stage lifecycle is deliberately kept
        separate from a *staged* scenario's narrative progress through
        its "stages" list (see WORLD_ENCOUNTER_STAGE_FIELDS and
        self._world_encounter_stage_index) -- walking from the broken
        wagon to the campfire to the goblin camp never touches this
        story at all, since the KILL_NPC TriggerRule wired in
        _start_world_encounter_combat() is gated to `min_stage=0,
        max_stage=0` and must stay valid throughout. The story only
        starts once the player actually commits to a stage's fight or
        resolution.

        The IGNORED FailurePolicy below only gets registered when the
        scenario actually declares "reputation_faction"/"ignored_
        reputation_delta" -- i.e. it offers a bare "ignore" choice at
        all. A non-combat scenario built entirely from "resolve" choices
        (each of which fully describes its own consequences, including
        any walk-away option) doesn't need this and can leave both
        fields out.
        """
        director = self.stories.story_manager.create_story(stage_count=2)
        director.story.set_flag("group_id", f"world_encounter:{director.story.id}")

        if "reputation_faction" in scenario:
            policy = FailurePolicy(
                scar_tag=scenario["scar_tag"] + ":{mode}",
                consequences={
                    FailureMode.IGNORED: [
                        ModifyReputationConsequence(
                            scenario["reputation_faction"], scenario["ignored_reputation_delta"]
                        )
                    ]
                },
                applies_to=[FailureMode.IGNORED],
            )
            self.stories.failure_manager.register_policy(director.story.id, policy)
        return director.story.id

    def _spawn_world_encounter_landmark_tile(self, stage, spawn_candidates):
        """
        Places the current stage's "landmark_tile" (see
        WORLD_ENCOUNTER_TILE_TYPES, e.g. Bandit_Ambush.json's ransacked
        "caravan") directly on the overworld map, at the open spawn
        candidates closest to the player -- giving the scene a physical
        prop matching its discovery text ("rifling through their cart")
        instead of only narration. A no-op for a stage that doesn't
        declare one.

        Called once per stage, from _enter_world_encounter_stage(), so a
        staged scenario's landmark changes as the player walks deeper in
        (the wagon gives way to a campfire, which gives way to the camp
        itself) -- not just once at the moment combat starts, the way a
        single-stage scenario's landmark always has.

        "landmark_tile" is normalized to a *pool* of one or more tile keys
        by _normalize_world_encounter_tile_pool() at load time. Each
        individual placement below independently rolls a random key from
        that pool, so a stage like Bandit_Ambush.json's
        ["caravan", "barricade"] scatters a believable mix of wrecked
        cart and hasty barricade instead of several copies of the same
        prop; a single-key pool (e.g. Wolf_Pack.json's "ambush_tree")
        behaves exactly as before, since every roll trivially picks the
        one key available. Unknown keys are skipped individually (with
        the spawn candidate given back rather than consumed) instead of
        failing the whole placement pass.

        How many copies get placed is randomized between "landmark_tile_
        amount"'s min/max (see _normalize_world_encounter_range(), which
        defaults a missing/int value to exactly one tile -- unchanged
        prior behavior), capped to however many open positions actually
        exist. Placed nearest-to-player first, so a multi-tile stage
        reads as one cluster of wreckage/barricade/stones rather than
        scattering randomly across the whole spawn radius.

        Pops each chosen position out of `spawn_candidates` in place, so
        anything spawned from the same pool right after this (a later
        stage's own landmark, or this stage's monsters/victims once the
        player investigates/sneaks) never lands on top of one -- see
        _enter_world_encounter_stage()'s self._world_encounter_stage_
        spawn_candidates, which is exactly the list this mutates.
        """
        tile_pool = stage.get("landmark_tile")
        if not tile_pool or not spawn_candidates:
            return

        min_amount, max_amount = stage["landmark_tile_amount"]
        amount = min(random.randint(min_amount, max_amount), len(spawn_candidates))

        anchor_x, anchor_y = self.player.x, self.player.y
        spawn_candidates.sort(key=lambda pos: (pos[0] - anchor_x) ** 2 + (pos[1] - anchor_y) ** 2)

        for _ in range(amount):
            tile_template = self.WORLD_ENCOUNTER_TILE_TYPES.get(random.choice(tile_pool))
            if tile_template is None:
                continue  # unknown key in the pool -- skip this placement, leave the candidate open
            x, y = spawn_candidates.pop(0)
            self.game_map.tiles[y][x] = tile_template

    def _spawn_world_encounter_landmark_structure(self, stage):
        """
        Places the current stage's "landmark_structure" list (see
        WORLD_ENCOUNTER_TILE_TYPES's docstring above it, e.g.
        Roadside_Shrine.json's single "shrine", or Undead_Siege.json's
        multi-building ["tavern", "house", "house"]) as one or more
        full multi-tile buildings from structures.py, anchored well off
        the player's current position -- see
        _world_encounter_structure_anchor(), which picks that distant
        point (further still for a multi-building cluster) so the
        footprint search reads as something discovered nearby rather
        than dropped on top of the player.

        Called once per stage, from _enter_world_encounter_stage(), not
        from _spawn_world_encounter_monsters() like the monsters/victims
        themselves -- a non-combat stage (see WORLD_ENCOUNTER_ACTIONS'
        "resolve"/"advance") never spawns monsters at all, so the
        structure(s) have to appear independently of that path. A no-op
        for a stage that doesn't declare any.
        """
        structure_ids = stage.get("landmark_structure")
        if not structure_ids:
            return

        anchor_x, anchor_y = self._world_encounter_structure_anchor(cluster_size=len(structure_ids))
        self._place_world_encounter_structure_cluster(structure_ids, anchor_x, anchor_y)

    def _place_world_encounter_structure_cluster(self, structure_ids, anchor_x, anchor_y):
        """
        Places every structure in `structure_ids` (see
        _normalize_world_encounter_structure_list()) as a single loose
        cluster anchored near (anchor_x, anchor_y) -- e.g. a "small town"
        of a tavern plus a couple of houses, all appearing together,
        rather than landmark_structure being limited to exactly one
        building.

        Mirrors world_generator.py's _place_town(): the first structure
        anchors the cluster; each later one is offset from the *previous*
        one by their combined footprint half-widths plus a gap (see
        _world_encounter_structure_offset(), the same math as that
        module's _anchor_offset()), in a randomly rolled direction with a
        little perpendicular drift for visual variety -- a guaranteed
        minimum spacing with extra jitter layered on top, generalized to
        however many structures a stage names instead of a fixed
        tavern/shop/house layout. place_structure_at_anchor() may still
        nudge an individual building a tile or two to find clear ground,
        so like _place_town, this spacing is a target, not an absolute
        guarantee.

        Unknown structure ids, or ones that can't find any clear
        footprint nearby, are skipped individually (place_structure_at_
        anchor returns None) rather than aborting the whole cluster --
        the same "don't fail the whole placement over one bad entry"
        approach _spawn_world_encounter_landmark_tile() takes with
        unknown tile keys.

        Every successfully placed structure also spawns its own NPC
        population (structures.py's blueprint.npc_map), exactly like
        _spawn_player_in_starting_tavern() already does when placing a
        tavern directly rather than through _place_town() -- otherwise a
        multi-building "town" landmark would read as an empty film set.
        """
        from world.structures import get_structure_blueprint, npcs_for_placement, place_structure_at_anchor

        previous_anchor = None  # (x, y, width, height) of the last structure actually placed
        for structure_id in structure_ids:
            blueprint = get_structure_blueprint(structure_id)
            if blueprint is None:
                continue
            width, height = len(blueprint.tile_map[0]), len(blueprint.tile_map)

            if previous_anchor is None:
                structure_anchor_x, structure_anchor_y = anchor_x, anchor_y
            else:
                structure_anchor_x, structure_anchor_y = self._world_encounter_next_cluster_anchor(
                    previous_anchor, width, height
                )

            placed_tiles = place_structure_at_anchor(self.game_map, structure_id, structure_anchor_x, structure_anchor_y)
            if not placed_tiles:
                continue  # no clear footprint nearby -- leave the rest of the cluster unaffected

            previous_anchor = (structure_anchor_x, structure_anchor_y, width, height)
            self.entities.extend(npcs_for_placement(structure_id, placed_tiles))

    def _world_encounter_next_cluster_anchor(self, previous_anchor, width, height):
        """
        Given the (x, y, width, height) of the previously placed structure
        in a cluster, roll an anchor point for the next one: a random side
        (right/left/below/above), offset by their combined footprint
        half-widths plus WORLD_ENCOUNTER_STRUCTURE_GAP (never less, since
        every jitter roll below only adds slack on top of that floor), and
        a small perpendicular drift so a longer cluster reads as a
        scattered hamlet rather than a rigid line of buildings. See
        _place_world_encounter_structure_cluster()'s docstring for how
        this mirrors world_generator.py's _place_town().
        """
        previous_x, previous_y, previous_width, previous_height = previous_anchor
        gap = self.WORLD_ENCOUNTER_STRUCTURE_GAP + random.randint(0, self.WORLD_ENCOUNTER_STRUCTURE_JITTER)
        drift = random.randint(-self.WORLD_ENCOUNTER_STRUCTURE_JITTER, self.WORLD_ENCOUNTER_STRUCTURE_JITTER)
        side = random.choice(("right", "left", "below", "above"))

        if side == "right":
            return previous_x + self._world_encounter_structure_offset(previous_width, width, gap), previous_y + drift
        if side == "left":
            return previous_x - self._world_encounter_structure_offset(previous_width, width, gap), previous_y + drift
        if side == "below":
            return previous_x + drift, previous_y + self._world_encounter_structure_offset(previous_height, height, gap)
        return previous_x + drift, previous_y - self._world_encounter_structure_offset(previous_height, height, gap)

    @staticmethod
    def _world_encounter_structure_offset(size_a, size_b, gap):
        """
        Distance to add to one structure's anchor coordinate to get the
        anchor coordinate of a second structure placed directly after it,
        leaving at least `gap` empty tiles between their two footprints.
        Identical math to world_generator.py's module-level
        _anchor_offset() (place_structure_at_anchor() centers a building
        on its anchor using `origin = anchor - size // 2`, so this mirrors
        that rather than guessing at spacing with hand-picked offsets) --
        duplicated here as a small static method instead of importing a
        private helper across modules.
        """
        return (size_a - size_a // 2) + gap + (size_b // 2)

    def _enter_world_encounter_stage(self, scenario, stage_index):
        """
        Reveals one narrative beat of a (possibly staged) world
        encounter: logs the stage's own "discovery" text, places its
        landmark_tile/landmark_structure (if any), and opens its
        WORLD_ENCOUNTER_MENU with that stage's own "choices".

        Called once when the encounter first triggers (stage 0, from
        _maybe_trigger_world_encounter()) and again each time an
        "advance" choice walks the player past the current beat (see
        _resolve_world_encounter_advance()) -- e.g. a broken wagon
        giving way to a campfire, which gives way to the goblin camp
        itself. A single-stage (non-staged) scenario simply calls this
        once, exactly as before staging existed.

        Caches the spawn candidates left over after this stage's own
        landmark tile is placed (self._world_encounter_stage_spawn_
        candidates) so that, if this turns out to be the stage the
        player investigates/sneaks into, _spawn_world_encounter_monsters()
        reuses the exact same open positions instead of risking a
        monster/victim landing on the landmark tile just placed.
        """
        self._world_encounter_stage_index = stage_index
        stage = scenario["stages"][stage_index]

        if stage["discovery"]:
            self.message_log.add_message(stage["discovery"], (255, 200, 120))

        self._spawn_world_encounter_landmark_structure(stage)
        self._world_encounter_stage_spawn_candidates = self._world_encounter_spawn_candidates()
        self._spawn_world_encounter_landmark_tile(stage, self._world_encounter_stage_spawn_candidates)

        self._world_encounter_target = scenario
        self._show_world_encounter_discovery(stage["discovery"], GameState.WORLD_ENCOUNTER_MENU)

    def _show_world_encounter_discovery(self, text, next_state):
        """
        Puts a beat's "discovery" text on screen by itself, with a single
        "Continue" prompt, before handing off to `next_state` (whichever
        choice menu -- WORLD_ENCOUNTER_MENU or WORLD_ENCOUNTER_AFTERMATH_
        MENU -- actually offers the player something to decide). The text
        itself was already written to the message log by the caller
        (_enter_world_encounter_stage()/_offer_world_encounter_aftermath())
        so it stays in the scrollback either way; this only controls what
        the modal popup shows before the real choices appear.

        A stage/aftermath with no discovery text at all (rare, but not
        disallowed by the schema) skips the prompt and goes straight to
        `next_state`, since there'd be nothing to show but "Continue".
        """
        if not text:
            self.game_state = next_state
            return
        self._world_encounter_discovery_text = text
        self._world_encounter_discovery_next_state = next_state
        self.game_state = GameState.WORLD_ENCOUNTER_DISCOVERY

    def _continue_past_world_encounter_discovery(self):
        """Dismiss the discovery prompt and open whichever choice menu it
        was standing in front of. Doesn't cost the player a turn -- same
        as opening any other menu."""
        next_state = self._world_encounter_discovery_next_state or GameState.OVERWORLD
        self._world_encounter_discovery_text = ""
        self._world_encounter_discovery_next_state = None
        self.game_state = next_state

    def _current_world_encounter_stage(self):
        """The stage dict currently on screen -- see
        _enter_world_encounter_stage()/self._world_encounter_stage_index."""
        return self._world_encounter_target["stages"][self._world_encounter_stage_index]

    def _world_encounter_structure_anchor(self, cluster_size=1):
        """
        Pick a point well off the player's own position to anchor a
        landmark_structure's footprint search from -- at least
        WORLD_ENCOUNTER_STRUCTURE_MIN_DISTANCE tiles away, or
        WORLD_ENCOUNTER_STRUCTURE_CLUSTER_MIN_DISTANCE when `cluster_size`
        names more than one structure (e.g. Undead_Siege.json's
        tavern-plus-houses -- see _spawn_world_encounter_landmark_structure()).

        place_structure_at_anchor() only avoids blocked/unwalkable
        terrain when it searches outward for "the closest clear
        footprint" -- it has no idea where the player is standing, so a
        nearby anchor risked the building (or, for a cluster, one of the
        later buildings _world_encounter_next_cluster_anchor() spreads
        outward from the first) reading as though it materialized right
        on top of the player instead of being discovered a short walk
        away. This is deliberately a wider, further-out search than
        _world_encounter_spawn_candidates() (which keeps monster/victim
        spawns close, radius 5, so the opening fight is immediately at
        hand) -- structures and monsters want opposite distances from
        the player.

        Falls back to the player's own position if nothing that far out
        is walkable/clear (e.g. hemmed in by water/impassable terrain)
        rather than failing to anchor the structure at all.
        """
        min_distance = (
            self.WORLD_ENCOUNTER_STRUCTURE_CLUSTER_MIN_DISTANCE
            if cluster_size > 1
            else self.WORLD_ENCOUNTER_STRUCTURE_MIN_DISTANCE
        )
        candidates = self._world_encounter_structure_anchor_candidates(min_distance)
        if not candidates:
            return self.player.x, self.player.y
        return random.choice(candidates)

    def _world_encounter_structure_anchor_candidates(self, min_distance):
        """
        Walkable, unoccupied, non-water overworld tiles at least
        `min_distance` tiles (Chebyshev -- max(|dx|, |dy|), matching this
        project's diagonal-adjacency convention rather than Manhattan)
        from the player, out to WORLD_ENCOUNTER_STRUCTURE_SEARCH_RADIUS.
        This is the ring _world_encounter_structure_anchor() draws its
        anchor from -- kept separate from _world_encounter_spawn_
        candidates() since that pool has no minimum distance and only
        reaches out to radius 5, too close for a structure that should
        read as discovered rather than conjured underfoot.
        """
        anchor_x, anchor_y = self.player.x, self.player.y
        radius = self.WORLD_ENCOUNTER_STRUCTURE_SEARCH_RADIUS

        candidates = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) < min_distance:
                    continue  # too close -- keep the structure a walk away from the player
                x, y = anchor_x + dx, anchor_y + dy
                if not (0 <= x < self.game_map.width and 0 <= y < self.game_map.height):
                    continue
                if not self.game_map.is_walkable(x, y) or is_water_tile(self.game_map.tiles[y][x]):
                    continue
                if any(e.x == x and e.y == y and getattr(e, "alive", True) for e in self.entities):
                    continue
                candidates.append((x, y))
        return candidates

    def _world_encounter_spawn_candidates(self):
        """
        Open, walkable, unoccupied overworld tiles near the player --
        the shared candidate pool _spawn_world_encounter_monsters() draws
        the opening wave's (and any landmark tile's) positions from, and
        _spawn_world_encounter_wave_monsters() reuses for every
        follow-up wave after it (see WORLD_ENCOUNTER's optional "waves"
        block, e.g. Undead_Siege.json's second surge of undead). Pulled
        out on its own so both call sites stay in sync instead of
        keeping two copies of the same radius/walkability/occupancy scan.
        """
        anchor_x, anchor_y = self.player.x, self.player.y
        radius = 5

        spawn_candidates = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) <= 1 and abs(dy) <= 1:
                    continue  # Give the player a little breathing room
                x, y = anchor_x + dx, anchor_y + dy
                if not (0 <= x < self.game_map.width and 0 <= y < self.game_map.height):
                    continue
                if not self.game_map.is_walkable(x, y) or is_water_tile(self.game_map.tiles[y][x]):
                    continue
                if any(e.x == x and e.y == y and getattr(e, "alive", True) for e in self.entities):
                    continue
                spawn_candidates.append((x, y))
        return spawn_candidates

    def _spawn_world_encounter_wave_monsters(self, wave, group_id):
        """
        Spawns one follow-up wave's monsters (see _normalize_world_
        encounter_waves()) near the player, once the previous wave/the
        opening fight is entirely cleared -- see
        _advance_world_encounter_wave(). Reuses the same spawn-candidate
        search the opening wave draws from, but doesn't re-place a
        landmark tile or re-roll victims: both already belong to the
        scene from the initial spawn, and shouldn't be duplicated just
        because more monsters arrived.

        Tagged with the same group_id as the rest of the encounter, so
        the existing KILL_NPC TriggerRule wired in
        _start_world_encounter_combat() counts wave monsters exactly
        like the opening ones -- no separate tracking needed.
        """
        spawn_candidates = self._world_encounter_spawn_candidates()
        if not spawn_candidates:
            return []

        min_count, max_count = wave["monster_count"]
        num_to_spawn = min(random.randint(min_count, max_count), len(spawn_candidates))

        spawned = []
        for _ in range(num_to_spawn):
            monster_class = random.choice(wave["monster_pool"])
            spawn_x, spawn_y = random.choice(spawn_candidates)
            spawn_candidates.remove((spawn_x, spawn_y))
            monster = monster_class(spawn_x, spawn_y)
            monster.group_id = group_id
            if wave["disposition"] is not None:
                monster.disposition = wave["disposition"]
            monster.roll_initiative()
            self.entities.append(monster)
            self.turn_order.append(monster)
            spawned.append(monster)

        self._resort_turn_order_preserving_current()
        return spawned

    def _spawn_world_encounter_monsters(self, scenario, stage, surprised=False, asleep=False):
        """
        Drops `stage`'s hostile monsters near the player once the
        encounter turns to combat (investigated, or spotted while sneaking
        at whichever stage the player committed at). Mirrors
        spawn_monsters_near_prison_alert()'s search-radius approach, but
        anchored on the player instead of a prison door.

        Reuses self._world_encounter_stage_spawn_candidates -- the open
        positions _enter_world_encounter_stage() computed when this stage
        was first revealed, already reduced by that stage's own landmark
        tile -- rather than recomputing and re-placing the landmark here,
        so a stage's wagon/campfire/camp prop is placed exactly once, the
        moment it's revealed, and monsters/victims never land on top of it.

        If asleep is True (a successful sneak), the monsters are spawned
        inactive and sharing one encounter_group list - attacking any one of
        them wakes the whole group at once (see Monster.take_damage).

        Every spawned monster is tagged with this encounter's story-scoped
        group_id (see _create_world_encounter_story()) so the KILL_NPC
        TriggerRule wired in _wire_world_encounter_combat() can tell which
        kills belong to this ambush versus any other monster on the map.

        If `stage` declares a "disposition" (see WORLD_ENCOUNTER_
        DISPOSITIONS), every monster spawned here gets it -- e.g.
        Centaur_Crossing.json spawning its band PASSIVE so "Approach the
        Band" doesn't start a fight on its own. Left as each class's own
        default disposition otherwise.
        """
        spawn_candidates = self._world_encounter_stage_spawn_candidates
        if not spawn_candidates:
            return []

        min_count, max_count = stage["monster_count"]
        num_to_spawn = min(random.randint(min_count, max_count), len(spawn_candidates))

        group_id = self._start_world_encounter_combat(scenario, num_to_spawn)

        spawned = []
        encounter_group = [] if asleep else None
        for _ in range(num_to_spawn):
            monster_class = random.choice(stage["monster_pool"])
            spawn_x, spawn_y = random.choice(spawn_candidates)
            spawn_candidates.remove((spawn_x, spawn_y))
            monster = monster_class(spawn_x, spawn_y)
            monster.group_id = group_id
            if stage["disposition"] is not None:
                monster.disposition = stage["disposition"]
            monster.roll_initiative()
            if surprised:
                # Spotted while sneaking - the monsters get the jump on the player.
                monster.initiative += 20
            if asleep:
                monster.is_active = False
                monster.encounter_group = encounter_group
                encounter_group.append(monster)
            self.entities.append(monster)
            self.turn_order.append(monster)
            spawned.append(monster)

        self._resort_turn_order_preserving_current()

        self._world_encounter_target_victims = self._spawn_world_encounter_victims(scenario, spawn_candidates, spawned)

        return spawned

    def _start_world_encounter_combat(self, scenario, monster_count):
        """
        Starts this encounter's StoryInstance (created back in
        _create_world_encounter_story()) and wires the TriggerRule that
        watches for its group's monsters dying. Returns the group_id every
        spawned monster should be tagged with.

        The story's "remaining" flag is how the wired TriggerRule below
        knows when the last group member has fallen -- decremented once
        per matching KILL_NPC trigger (already fired for every monster
        death via StorySystems.fire_kill, see game.py's combat resolution)
        until it reaches zero, at which point the story completes and runs
        its reward Consequences (see _wire_world_encounter_rewards()).
        """
        director = self.stories.story_manager.get_director(self._world_encounter_story_id)
        group_id = director.story.get_flag("group_id")

        director.start()
        director.story.set_flag("remaining", monster_count)
        director.story.set_flag("wave_index", 0)
        self._wire_world_encounter_rewards(director, scenario)

        def _on_group_member_killed(story, story_director, event):
            remaining = story.get_flag("remaining", 1) - 1
            story_director.set_flag("remaining", remaining)
            if remaining > 0:
                return
            if self._advance_world_encounter_wave(story, story_director, scenario, group_id):
                return  # another wave just spawned -- stay ACTIVE until it's cleared too
            story_director.complete()

        director.story.add_trigger_rule(TriggerRule(
            trigger_type=TriggerType.KILL_NPC,
            data_filters={"group_id": group_id},
            min_stage=0,
            max_stage=0,
            repeatable=True,
            effect=_on_group_member_killed,
        ))

        return group_id

    def _advance_world_encounter_wave(self, story, director, scenario, group_id):
        """
        Called once a wave's last tagged monster falls (see the KILL_NPC
        TriggerRule wired just above in _start_world_encounter_combat()).
        If the scenario declares more "waves" (see _normalize_world_
        encounter_waves(), e.g. Undead_Siege.json's second, larger surge
        of undead once the barricade's first attackers are cleared) than
        have been spawned so far, spawns the next one and keeps the
        story ACTIVE instead of completing it -- rewards and any
        post-combat "aftermath" menu (_wire_world_encounter_rewards())
        only fire once every wave is down, not after the opening one.

        Returns True if a new wave was spawned (the caller should leave
        the story running), or False once "waves" is exhausted -- or
        there was nowhere left to spawn one -- signaling the caller to
        complete the story as usual.
        """
        waves = scenario.get("waves") or []
        wave_index = story.get_flag("wave_index", 0)
        if wave_index >= len(waves):
            return False

        wave = waves[wave_index]
        spawned = self._spawn_world_encounter_wave_monsters(wave, group_id)
        if not spawned:
            return False  # no room left to spawn one -- treat the encounter as resolved

        director.set_flag("wave_index", wave_index + 1)
        director.set_flag("remaining", len(spawned))
        if wave["discovery"]:
            self.message_log.add_message(wave["discovery"], (255, 200, 120))
        return True

    def _wire_world_encounter_rewards(self, director, scenario):
        """
        Runs this encounter's reward Consequences through the shared
        ConsequenceExecutor/ExecutionContext once its story completes --
        the same reward path an authored JSON quest's `rewards.on_complete`
        uses (see story_content_loader.py), just wired directly instead of
        parsed from a file.
        """
        consequences = [RewardXPConsequence(scenario["reward_xp"])]
        if scenario.get("reward_gold"):
            consequences.append(RewardGoldConsequence(scenario["reward_gold"]))
        if scenario.get("reputation_faction"):
            consequences.append(
                ModifyReputationConsequence(scenario["reputation_faction"], scenario["reputation_delta"])
            )

        def _on_completed(story, **_context):
            context = self.stories.execution_context
            executor = self.stories.story_manager.consequence_executor
            for consequence in consequences:
                executor.execute(consequence, context)
            self.message_log.add_message("The fight is over. You take a moment to catch your breath.", (150, 255, 180))
            self._offer_world_encounter_aftermath(scenario)

        director.on(StoryEvent.STORY_COMPLETED, _on_completed)

    def _offer_world_encounter_aftermath(self, scenario):
        """
        Opens the post-combat branching menu for scenarios that declare
        an "aftermath" block (see Wolf_Pack.json) -- what becomes of a
        rescued victim once the fight that put them in danger is over.
        A no-op for scenarios without one, so most encounters end exactly
        as before: the "fight is over" message and nothing else.
        """
        aftermath = scenario.get("aftermath")
        if aftermath is None:
            return
        if aftermath["discovery"]:
            self.message_log.add_message(aftermath["discovery"], (255, 200, 120))
        self._world_encounter_aftermath = aftermath
        self._show_world_encounter_discovery(aftermath["discovery"], GameState.WORLD_ENCOUNTER_AFTERMATH_MENU)

    def _spawn_world_encounter_victims(self, scenario, spawn_candidates, linked_monsters):
        """
        Places the scenario's bystanders (the merchants being robbed, the
        guards making their stand, etc.) among the leftover spawn candidates
        from _spawn_world_encounter_monsters, so the scene reads as the
        discovery text describes it. Most are flavour-only (EncounterVictim),
        but combat-capable ones (GuardVictim) also join the turn order so
        they actually fight alongside the player - see dungeon_npcs.py.

        Every victim is linked to the same `linked_monsters` group so
        EncounterVictim.combat_resolved() can tell once they're all dead,
        which is what unlocks freeing/rewarding the victim (F key).
        """
        preset = scenario.get("victim_data")
        if preset is None or not spawn_candidates:
            return []

        min_count, max_count = scenario.get("victim_count", (1, 1))
        num_to_spawn = min(random.randint(min_count, max_count), len(spawn_candidates))

        positions = random.sample(spawn_candidates, num_to_spawn)
        victims = make_encounter_victims(preset, num_to_spawn, positions)
        for victim in victims:
            victim.linked_monsters = linked_monsters
        self.entities.extend(victims)

        fighters = [v for v in victims if isinstance(v, GuardVictim)]
        if fighters:
            for guard in fighters:
                guard.roll_initiative()
                self.turn_order.append(guard)
            self._resort_turn_order_preserving_current()

        return victims

    def _resolve_world_encounter_choice(self, choice):
        """
        Dispatches a selected WORLD_ENCOUNTER_MENU choice to its built-in
        behavior -- one of the WORLD_ENCOUNTER_ACTIONS handlers just
        below (_resolve_world_encounter_investigate/_sneak/_ignore/
        _resolve/_advance), acting on whichever stage is currently on
        screen (see _current_world_encounter_stage()). Everything about
        *how* a choice was offered (label, description, color, key,
        is_cancel) already did its job in the menu; the resolver gets the
        full choice dict anyway (not just its action name) since
        "resolve"/"advance" need their own "outcome"/"consequences" --
        investigate/sneak/ignore mostly ignore the argument, being fully
        scripted in Python.
        """
        resolver = getattr(self, f"_resolve_world_encounter_{choice['action']}")
        resolver(choice)

    def _world_encounter_choice_for_key(self, key, choices):
        """
        Resolves a raw pygame key event to one of `choices` -- either the
        currently-offered scenario's normalized "choices" (see
        _normalize_world_encounter_choices()) or its "aftermath" choices
        (see _normalize_world_encounter_aftermath()), whichever menu is
        currently open. Digit keys (pygame.K_0 + n == pygame.K_<n> for
        0 <= n <= 9) match a choice by its own "key" number, however many
        choices a scenario declares. ESC always matches whichever choice
        (if any) is flagged "is_cancel" -- e.g. Bandit_Ambush.json's
        "Ignore" -- regardless of which number key it's also bound to.
        Returns None if nothing matches (e.g. an unbound digit was pressed).
        """
        if key == pygame.K_ESCAPE:
            return next((choice for choice in choices if choice.get("is_cancel")), None)
        return next((choice for choice in choices if pygame.K_0 + choice["key"] == key), None)

    def _resolve_world_encounter_investigate(self, choice):
        """
        "investigate" action: walk straight in - reveals the scenario and
        starts the fight. _spawn_world_encounter_monsters() starts this
        encounter's StoryInstance and wires its combat-completion reward;
        the reward itself only fires later, once the last tagged monster
        dies. `choice` is unused -- this action is fully scripted and
        doesn't vary by which choice offered it (accepted only so
        _resolve_world_encounter_choice() can call every resolver the
        same way; see _resolve_world_encounter_resolve() for a resolver
        that actually reads it).

        Acts on the *current* stage (_current_world_encounter_stage()),
        not the scenario as a whole -- a staged scenario has no top-level
        "discovery"/"monster_pool" of its own, only per-stage ones (see
        WORLD_ENCOUNTER_STAGE_FIELDS). The stage's discovery text was
        already logged the moment it was revealed
        (_enter_world_encounter_stage()), so it isn't repeated here.
        """
        scenario = self._world_encounter_target
        stage = self._current_world_encounter_stage()
        spawned = self._spawn_world_encounter_monsters(scenario, stage)
        if spawned:
            self.message_log.add_message(stage["investigate_message"], (255, 150, 100))
        self.game_state = GameState.OVERWORLD
        self._world_encounter_target = None
        self._world_encounter_story_id = None

    def _resolve_world_encounter_sneak(self, choice):
        """
        "sneak" action: DEX (Stealth) check.
        Success - the enemies are spawned asleep, giving the player a choice:
        slip past, or strike one down before the rest ever wake up.
        Failure - spotted; the enemies spawn awake and alerted.
        `choice` is unused -- see _resolve_world_encounter_investigate().

        Acts on the current stage (_current_world_encounter_stage()) --
        "sneak_dc"/"sneak_success"/"sneak_fail" live per-stage, same
        reasoning as _resolve_world_encounter_investigate(). The stage's
        discovery text was already logged when it was revealed, so only
        the stealth-roll line and the success/fail line (genuinely new
        information the sneak check itself reveals) are logged here.
        The success/fail line is also shown as its own discovery prompt
        (see _show_world_encounter_discovery()) so the player reads it
        before combat actually resumes.
        """
        scenario = self._world_encounter_target
        stage = self._current_world_encounter_stage()
        dex_roll  = random.randint(1, 20)
        dex_mod   = self.player.get_ability_modifier(self.player.dexterity)
        if "stealth" in self.player.skill_proficiencies:
            dex_mod += self.player.proficiency_bonus
        dex_total = dex_roll + dex_mod
        sneak_dc  = stage["sneak_dc"]

        self.message_log.add_message(
            f"You creep closer to see what's happening. "
            f"(Stealth {dex_roll}{dex_mod:+d} = {dex_total} vs DC {sneak_dc})",
            (150, 200, 220)
        )

        if dex_total >= sneak_dc:
            outcome_text = stage["sneak_success"]
            self.message_log.add_message(outcome_text, (150, 255, 180))
            self._spawn_world_encounter_monsters(scenario, stage, asleep=True)
        else:
            outcome_text = stage["sneak_fail"]
            self.message_log.add_message(outcome_text, (255, 120, 100))
            self._spawn_world_encounter_monsters(scenario, stage, surprised=True)

        self._world_encounter_target = None
        self._world_encounter_story_id = None
        self._show_world_encounter_discovery(outcome_text, GameState.OVERWORLD)

    def _resolve_world_encounter_ignore(self, choice):
        """
        "ignore" action (usually also bound to ESC via a scenario's
        "is_cancel" choice -- see Bandit_Ambush.json): walk on - no fight,
        no reward. Routed through StoryFailureManager.mark_ignored() so
        this plays by the same rules as an authored quest the player
        never engaged: it stamps a FailureMode.IGNORED world scar (see
        _create_world_encounter_story()'s FailurePolicy) and applies the
        scenario's reputation penalty via the shared consequence
        machinery, instead of a one-off inline hit. `choice` is unused --
        see _resolve_world_encounter_investigate().

        Reads "ignore" flavor text off the *current* stage -- walking
        away from the wagon reads differently than walking away from the
        goblin camp itself -- but always marks the *whole encounter* as
        ignored via the scenario-level story id, since the reputation/
        scar consequences apply regardless of which stage the player
        turned back at. Shown as its own discovery prompt (see
        _show_world_encounter_discovery()) before control returns to the
        overworld, same as the sneak success/fail lines.
        """
        stage = self._current_world_encounter_stage()
        self.message_log.add_message(stage["ignore"], (150, 150, 150))
        self.stories.failure_manager.mark_ignored(self._world_encounter_story_id)
        self._world_encounter_target = None
        self._world_encounter_story_id = None
        self._show_world_encounter_discovery(stage["ignore"], GameState.OVERWORLD)

    def _resolve_world_encounter_advance(self, choice):
        """
        "advance" action: walk past the current stage's beat without
        investigating, sneaking, or ignoring it outright -- e.g. passing
        a broken wagon to press on toward the campfire beyond it (see
        WORLD_ENCOUNTER_STAGE_FIELDS's docstring for the full wagon ->
        campfire -> goblin camp example this exists for).

        Applies the choice's own optional "outcome"/"consequences"/
        "hours" (a moment of unease, a scrap of loot picked up along the
        way) through the same _apply_world_encounter_outcome_choice()
        path a "resolve" choice uses -- unlike "resolve", "outcome" isn't
        required here (see _normalize_world_encounter_choices()), so
        advancing past a beat with nothing to say about it is fine.

        Rather than revealing the scenario's next stage immediately, this
        hands the menu back to the overworld and queues that stage for
        _maybe_advance_world_encounter_stage() -- the player has to
        actually cover ground (WORLD_ENCOUNTER_STAGE_ADVANCE_MIN_STEPS,
        plus a per-step roll after that) before the next beat's discovery
        text fires, so pressing on toward the campfire reads as a walk,
        not a menu click. Content is expected to only offer "advance" on
        a non-final stage; if a scenario's JSON mistakenly offers it on
        the last one, this falls back to walking away (the same outcome
        "ignore" produces) instead of indexing past the end of "stages".

        Which stage comes next is the choice's own "next_stage" (see
        _normalize_world_encounter_choices()) when it names one -- this
        is what lets different "advance" choices on the same stage lead
        somewhere different, a real branch rather than every option
        funneling back to the same next beat. A choice that leaves
        "next_stage" unset keeps the old behavior of simply walking on
        to the next entry in "stages", so linear, unbranched scenarios
        (or every stage before a scenario's first fork) need no changes.

        A choice's own "outcome" line (e.g. Wolf_Pack.json's "Track
        Carefully") is shown as its own discovery prompt (see
        _show_world_encounter_discovery()) before the overworld actually
        takes back control -- empty for most "advance" choices, in which
        case the prompt is skipped and the handoff is immediate.
        """
        scenario = self._world_encounter_target
        self._apply_world_encounter_outcome_choice(choice)

        next_stage_id = choice.get("next_stage")
        if next_stage_id is not None:
            next_index = scenario["stage_index_by_id"][next_stage_id]
        else:
            next_index = self._world_encounter_stage_index + 1

        if next_index >= len(scenario["stages"]):
            self._world_encounter_target = None
            self._world_encounter_story_id = None
            self._world_encounter_pending_stage_index = None
            self._world_encounter_advance_steps = 0
        else:
            self._world_encounter_pending_stage_index = next_index
            self._world_encounter_advance_steps = 0

        self._show_world_encounter_discovery(choice["outcome"], GameState.OVERWORLD)

    def _resolve_world_encounter_resolve(self, choice):
        """
        "resolve" action: for a non-combat scenario (one with no
        "monster_pool" at all, e.g. Lost_Pilgrim.json -- see
        _load_world_encounter_scenarios()'s "combat" flag), a choice
        settles the whole encounter immediately, with no fight and no
        separate post-combat "aftermath" menu after it. The choice's own
        "outcome"/"consequences" (parsed by _normalize_world_encounter_
        choices() exactly like an aftermath choice's -- see
        _apply_world_encounter_outcome_choice()) are the entire payoff,
        so a non-combat scenario's choices fully describe every branch
        themselves, including any walk-away option, rather than relying
        on a bare scenario-level reward.

        Completes this encounter's StoryInstance the same way a won
        fight does (director.complete()), so a non-combat encounter
        still plays by the same StoryEvent/FailureManager rules as a
        combat one -- chains, scars, and condition tracking all see it
        as a normal resolved story instead of one left UNINITIALIZED.

        The choice's "outcome" line (always present -- see
        _normalize_world_encounter_choices()) is shown as its own
        discovery prompt (see _show_world_encounter_discovery()) before
        the overworld takes back control.
        """
        director = self.stories.story_manager.get_director(self._world_encounter_story_id)
        director.start()
        director.complete()

        self._apply_world_encounter_outcome_choice(choice)

        self._world_encounter_target = None
        self._world_encounter_story_id = None
        self._show_world_encounter_discovery(choice["outcome"], GameState.OVERWORLD)

    def _apply_world_encounter_outcome_choice(self, choice):
        """
        Shared resolution for any menu choice that fully describes its
        own result via "outcome"/"consequences"/"hours"/"escort" (see
        _normalize_world_encounter_choices()/_normalize_world_encounter_
        aftermath()) -- a non-combat scenario's "resolve" choice (see
        _resolve_world_encounter_resolve()) and a post-combat
        "aftermath" choice (see _resolve_world_encounter_aftermath_
        choice()) are the exact same shape of data, so both route
        through here instead of duplicating the escort-vs-consequences
        branch twice.

        Logs the choice's own "outcome" line, then either recruits this
        encounter's victim(s) as escorted companions (see
        recruit_companion()) if the choice is flagged "escort" and
        victims exist to escort, or runs its "consequences"/"hours"
        immediately through the shared ConsequenceExecutor otherwise.
        Leaves game_state and every _world_encounter_* menu field alone
        -- callers close those out themselves, since "resolve" and
        "aftermath" choices leave the encounter in different states.

        Logging the "outcome" line is skipped entirely if it's empty --
        "resolve"/"aftermath" choices always require one (see
        _normalize_world_encounter_choices()/_normalize_world_encounter_
        aftermath()), but an "advance" choice doesn't, and an empty line
        in the message log helps no one.
        """
        if choice["outcome"]:
            self.message_log.add_message(
                choice["outcome"], (150, 255, 180) if not choice.get("is_cancel") else (150, 150, 150)
            )

        if choice.get("escort") and self._world_encounter_target_victims:
            # A scenario can rescue more than one victim (e.g. Bandit_
            # Ambush.json's "victim_count": [1, 2]) -- escort all of them,
            # not just the first, so nobody's left standing around after
            # being "rescued". The choice's reward/travel-time describes
            # completing *this escort*, not each individual companion, so
            # only the first one recruited carries it; the rest are
            # recruited with an explicit empty reward (see
            # recruit_companion()'s reward_consequences=[] vs None
            # distinction) so try_deliver_companions() doesn't pay out
            # the same reward once per body delivered.
            for index, victim in enumerate(self._world_encounter_target_victims):
                self.recruit_companion(
                    victim,
                    escort_id=self._world_encounter_story_id,
                    reward_consequences=choice["consequences"] if index == 0 else [],
                    escort_hours=choice.get("hours", 0) if index == 0 else 0,
                )
        else:
            context = self.stories.execution_context
            executor = self.stories.story_manager.consequence_executor
            for consequence in choice["consequences"]:
                executor.execute(consequence, context)

            if choice.get("hours"):
                self.stories.world_time.advance(choice["hours"], TimeUnit.HOUR)

    def _resolve_world_encounter_aftermath_choice(self, choice):
        """
        Resolves a choice from a scenario's post-combat "aftermath" menu
        (see _offer_world_encounter_aftermath()) -- e.g. escorting Wolf_
        Pack.json's rescued child back to the innkeeper versus leaving
        her to find her own way home. Resolution itself (the outcome
        line, escort-vs-consequences) is shared with a non-combat
        scenario's "resolve" choice via _apply_world_encounter_outcome_
        choice(); this method only handles closing out the aftermath
        menu specifically afterward.

        The choice's "outcome" line (always present -- see
        _normalize_world_encounter_aftermath()) is shown as its own
        discovery prompt (see _show_world_encounter_discovery()) before
        the overworld takes back control.
        """
        self._apply_world_encounter_outcome_choice(choice)

        self._world_encounter_target_victims = []
        self._world_encounter_aftermath = None
        self._show_world_encounter_discovery(choice["outcome"], GameState.OVERWORLD)

    # --- Escort companions --------------------------------------------------
    # A companion is a rescued/recruited NPC who follows the player (see
    # entities/summons.py's EscortCompanion) until they're safely walked to
    # an inn and handed off to the innkeeper. Recruitment can come from
    # anywhere that already has a live NPC entity in hand -- right now that's
    # a world encounter's "escort" aftermath choice above, but an authored
    # story or a freed PrisonerNPC could call recruit_companion() the same
    # way without any changes here.

    def recruit_companion(self, source_entity, escort_id=None, reward_consequences=None, escort_hours=0, dialogue=None):
        """
        Turns a live NPC entity already in self.entities into a
        following EscortCompanion, at the same position and carrying
        over its name/char/color so the switch is invisible to the
        player -- only its behavior (follow instead of stand still)
        and its interface (get_dialogue() for the escort's own line)
        change.

        escort_id ties the companion back to whatever quest is tracking
        this escort (e.g. the world encounter story_id that spawned
        them), purely for bookkeeping -- try_deliver_companions() below
        currently completes every active escort at once regardless of
        id, since this game only has one inn destination for now.

        reward_consequences (Consequence objects, e.g. from a scenario's
        aftermath "consequences") and escort_hours are held on the
        companion and only applied once they're safely delivered -- see
        _grant_escort_reward(). Leaving reward_consequences as None falls
        back to a flat XP reward, so recruiting a companion from
        somewhere other than a JSON aftermath choice still pays out
        something on delivery without extra wiring. Pass an explicit
        empty list instead of None to recruit a companion with no reward
        of its own (e.g. the 2nd+ companion of a multi-victim escort,
        whose reward already rides on the first -- see
        _resolve_world_encounter_aftermath_choice()) without triggering
        that fallback.
        """
        if source_entity in self.entities:
            self.entities.remove(source_entity)
        if source_entity in self.turn_order:
            self.turn_order.remove(source_entity)

        companion = EscortCompanion(
            source_entity.x, source_entity.y,
            char=getattr(source_entity, "char", "c"),
            name=getattr(source_entity, "name", "Companion"),
            color=getattr(source_entity, "color", (200, 200, 150)),
            owner=self.player,
            escort_id=escort_id,
            # None means "caller didn't specify a reward" -> fall back to
            # a flat XP reward so recruiting from somewhere other than a
            # JSON aftermath choice still pays out something on delivery.
            # An explicit empty list means "this companion's reward is
            # tracked elsewhere" (see _resolve_world_encounter_aftermath_
            # choice()'s multi-victim escorts) and must NOT be swapped
            # for the default -- a falsy-value check here would silently
            # re-grant the default reward per extra companion.
            reward_consequences=[RewardXPConsequence(25)] if reward_consequences is None else reward_consequences,
            escort_hours=escort_hours,
            dialogue=dialogue,
        )
        self.entities.append(companion)
        self.turn_order.append(companion)
        self._resort_turn_order_preserving_current()
        self.companions.append(companion)

        self.message_log.add_message(
            f"{companion.name} will follow you now. Escort them to an inn and speak with the innkeeper.",
            (150, 220, 255)
        )
        return companion

    def try_deliver_companions(self, innkeeper):
        """
        Called when the player talks to an Innkeeper while escorting
        one or more companions (see check_overworld_npc_interaction()/
        the 'F to talk' handler). Completes every active escort at
        once: each companion is safely delivered, rewarded, and leaves
        the party. Returns True if at least one escort was completed,
        so the caller can skip the innkeeper's ordinary dialogue for
        that turn instead of talking over the escort's own message.
        """
        if not self.companions:
            return False

        self.message_log.add_message(
            f'{innkeeper.name}: "Ah, safe and sound! Welcome, friend."', (200, 200, 255)
        )
        for companion in list(self.companions):
            self._grant_escort_reward(companion)
            companion.complete_escort(self)

        return True

    def open_innkeeper_menu(self, innkeeper):
        """
        Open the Buy Food / Rest for the Night / Leave choice menu for
        an adjacent Innkeeper (see the 'F to talk' handler and
        GameState.INNKEEPER_MENU's key handling below). Mirrors the
        Shopkeeper.offer_trade()/CHEST_MENU pattern already used
        elsewhere: stash the target, remember what to return to, and
        switch game_state -- rendering and input handling pick it up
        from there (render_innkeeper_menu()/handle_innkeeper_menu_input()).

        `_innkeeper_menu_return_state` is tracked separately from the
        shared `_previous_game_state` field (rather than reusing it, as
        CHEST_MENU/SHOP_MENU do) because the Buy Food option below opens
        the shop overlay *on top of* this menu via Innkeeper.offer_trade(),
        which itself reassigns `_previous_game_state` to INNKEEPER_MENU so
        leaving the shop comes back here. Reusing that same field for "what
        the innkeeper menu itself returns to" would get clobbered by that
        nested trip to the shop, leaving no way back to the overworld.
        """
        self._previous_game_state = self.game_state
        self._innkeeper_menu_return_state = self.game_state
        self._innkeeper_menu_target = innkeeper
        self.game_state = GameState.INNKEEPER_MENU
        self.stories.fire_talk(innkeeper, instigator=self.player)

    def open_rest_menu(self):
        """Open the short rest / long rest choice menu."""
        if not self.player:
            return
        self._previous_game_state = self.game_state
        self._rest_menu_target = self.player
        self.game_state = GameState.REST_MENU

    def _grant_escort_reward(self, companion):
        """
        Runs a delivered companion's held-back reward Consequences
        through the same shared ConsequenceExecutor/ExecutionContext
        every other reward path in this module uses (see
        _wire_world_encounter_rewards()), then advances world time by
        however long the journey was meant to take (see
        recruit_companion()'s escort_hours) -- the travel the player
        just did on foot, made canonical the same way fire_rest() makes
        an inn stay canonical.
        """
        context = self.stories.execution_context
        executor = self.stories.story_manager.consequence_executor
        for consequence in companion.reward_consequences:
            executor.execute(consequence, context)

        if companion.escort_hours:
            self.stories.world_time.advance(companion.escort_hours, TimeUnit.HOUR)

    def _lineages_for_group(self, group_index):
        """Return the list of lineage instances for the given group index."""
        _, _, lineages = self.race_groups[group_index]
        return lineages
 
    def _selected_lineage(self):
        """Return the currently highlighted lineage object."""
        lineages = self._lineages_for_group(self.selected_group_index)
        idx = max(0, min(self.selected_lineage_index, len(lineages) - 1))
        return lineages[idx]

    def start_character_creation(self):
        self.game_state             = GameState.CHARACTER_CREATION
        self.selected_group_index   = 0
        self.selected_lineage_index = 0
        # Keep available_races / selected_race_index in sync for finalize
        self.available_races     = [r for _, _, rs in self.race_groups for r in rs]
        self.selected_race_index = 0
        self.message_log.add_message("─── CHARACTER CREATION ───", (240, 240, 240))
        self.message_log.add_message(
            "Choose your Race & Lineage, then press Enter.", (200, 200, 255)
        )

    def finalize_race_selection(self):
        """Called when player presses Enter on the race screen."""
        chosen = self._selected_lineage()
        self.message_log.add_message(
            f"Race chosen: {chosen.name}.", (0, 255, 0)
        )
 
        # Sync the flat index so finalize_character_creation can read it
        self.available_races = [r for _, _, rs in self.race_groups for r in rs]
        self.selected_race_index = self.available_races.index(chosen)
 
        # Move to class selection
        self.game_state             = GameState.CLASS_SELECTION
        self.selected_class_index   = 0
        self.message_log.add_message("─── CLASS SELECTION ───", (240, 240, 240))
        self.message_log.add_message(
            "Choose your Class (W/S navigate, Enter confirm).", (200, 200, 255)
        )
        pygame.event.clear()
        self.ignore_next_input = True

    def finalize_character_creation(self):
        """Build the player from the chosen race + class, then enter the tavern."""
        chosen_race  = self.available_races[self.selected_race_index]
        chosen_class = self.available_classes[self.selected_class_index]
 
        race_key  = chosen_race.name        # e.g. "Drow", "Hill Dwarf"
        class_key = chosen_class.__name__   # e.g. "Fighter"
 
        player_char, player_color = self.race_class_visuals.get(
            (race_key, class_key), ('@', (255, 255, 255))
        )
 
        self.player = chosen_class(0, 0, player_char, self.character_name, player_color)
        self.player.race = chosen_race
        self.player.race.apply_traits(self.player, self)
        self.player.inventory.game_instance = self
 
        # Merge racial bonuses (avoid duplicates already added by apply_traits)
        for res in chosen_race.damage_resistances:
            if res not in self.player.damage_resistances:
                self.player.damage_resistances.append(res)
        for sp in chosen_race.skill_proficiencies:
            if sp not in self.player.skill_proficiencies:
                self.player.skill_proficiencies.append(sp)
        for wp in chosen_race.weapon_proficiencies:
            if wp not in self.player.weapon_proficiencies:
                self.player.weapon_proficiencies.append(wp)
        for ap in chosen_race.armor_proficiencies:
            if ap not in self.player.armor_proficiencies:
                self.player.armor_proficiencies.append(ap)
 
        self.player.max_hp      = self.player._calculate_max_hp()
        self.player.hp          = self.player.max_hp
        self.player.armor_class = self.player._calculate_ac()
        self.player.spell_bonus = (
            self.player.get_spell_modifier() + self.player.proficiency_bonus
        )
        self.player.attack_power = (
            self.player.get_ability_modifier(self.player.dexterity)
            + self.player.equipped_weapon.damage_modifier
        )
        self.player.attack_bonus = (
            self.player.get_ability_modifier(self.player.dexterity)
            + self.player.proficiency_bonus
            + self.player.equipped_weapon.attack_bonus
        )
 
        self.message_log.add_message(
            f"You are a {chosen_race.name} {self.player.class_name} "
            f"named {self.player.name}!",
            (0, 255, 0),
        )
 
        pygame.event.clear()

        # The player used to start inside a dedicated GameState.TAVERN interior
        # map. That's scrapped now — the starting chunk (0, 0) always rolls a
        # town (see _place_town's "% 5 != 0" check), so instead we generate the
        # overworld and drop the player inside that town's tavern building.
        self.generate_overworld_map(chunk_coord=(0, -1)) 
        self._spawn_player_in_starting_tavern()

    def _spawn_player_in_starting_tavern(self):
        """
        Place a "tavern" building (structures.py's blueprint) directly on
        top of the player's overworld starting position, then drop the
        player inside it, in place of the old tavern-interior gamestate.

        This used to look for a tavern already placed by _place_town's
        per-chunk town roll, but that roll is probabilistic and often
        skipped the starting chunk entirely, so the player wouldn't always
        spawn in a tavern. Forcing the placement here guarantees one every
        time. Falls back to leaving the player at their regular overworld
        start position if the tavern footprint can't find clear ground
        nearby (see place_structure_at_anchor).

        This tavern is placed directly rather than through _place_town, so
        it also has to spawn its own population directly — via the same
        npcs_for_placement() helper create_town_npcs() uses internally —
        instead of getting NPCs for free from the town pipeline.
        """
        from world.structures import place_structure_at_anchor, npcs_for_placement

        anchor_x, anchor_y = self.player.x, self.player.y
        placed_tiles = place_structure_at_anchor(self.game_map, "tavern", anchor_x, anchor_y)
        tavern_tile = self._tavern_entrance_tile(placed_tiles) if placed_tiles else None

        if placed_tiles:
            tavern_npcs = npcs_for_placement("tavern", placed_tiles)
            self.entities.extend(tavern_npcs)
            chunk = self.overworld_chunks.get(self.overworld_chunk_coord)
            if chunk is not None:
                chunk["population"] = list(chunk.get("population", [])) + tavern_npcs

        if tavern_tile is not None:
            self.player.x, self.player.y = tavern_tile
            self.overworld_player_pos = tavern_tile

            ideal_x = max(0.0, min(
                float(self.player.x) - self.camera.viewport_width / 2.0,
                float(self.game_map.width - self.camera.viewport_width)
            ))
            ideal_y = max(0.0, min(
                float(self.player.y) - self.camera.viewport_height / 2.0,
                float(self.game_map.height - self.camera.viewport_height)
            ))
            self.camera.x        = ideal_x
            self.camera.y        = ideal_y
            self.camera.target_x = float(self.player.x)
            self.camera.target_y = float(self.player.y)

            self.update_fov()
            self.minimap_needs_redraw = True


    def _tavern_entrance_tile(self, placed_tiles):
        """
        Given the (x, y, tile) cells returned by placing the "tavern"
        blueprint, return an (x, y) walkable entrance tile — the first
        walkable_chars cell in structures.py's tavern tile_map, offset by
        the building's actual placed origin (place_structure_at_anchor may
        have nudged it a tile or two to find clear ground).
        """
        from world.structures import get_structure_blueprint

        tavern_blueprint = get_structure_blueprint("tavern")
        origin_x = min(x for x, y, tile in placed_tiles)
        origin_y = min(y for x, y, tile in placed_tiles)

        for dy, row in enumerate(tavern_blueprint.tile_map):
            for dx, char in enumerate(row):
                if char in tavern_blueprint.walkable_chars:
                    return origin_x + dx, origin_y + dy

        return None


    def _recalculate_dimensions(self, is_zoom_only=False):
        """Recalculate all dynamic dimensions based on current screen size."""
        config.SCREEN_WIDTH, config.SCREEN_HEIGHT = self.screen.get_size()
        
        config.UI_PANEL_WIDTH = int(config.SCREEN_WIDTH * config.UI_PANEL_WIDTH_RATIO)
        config.GAME_AREA_WIDTH = config.SCREEN_WIDTH - config.UI_PANEL_WIDTH
        config.MESSAGE_LOG_HEIGHT = int(config.SCREEN_HEIGHT * config.MESSAGE_LOG_HEIGHT_RATIO)
        
        effective_tile_pixel_size = int(config.TILE_SIZE * config.TARGET_EFFECTIVE_TILE_SCALE)
        if effective_tile_pixel_size < 1:
            effective_tile_pixel_size = 1

        new_internal_width_tiles = max(config.MIN_GAME_AREA_TILES_WIDTH, config.GAME_AREA_WIDTH // effective_tile_pixel_size)
        # Game area uses full screen height — message log overlays on top as transparent
        new_internal_height_tiles = max(config.MIN_GAME_AREA_TILES_HEIGHT, config.SCREEN_HEIGHT // effective_tile_pixel_size)
        
        config.INTERNAL_GAME_AREA_WIDTH_TILES = new_internal_width_tiles
        config.INTERNAL_GAME_AREA_HEIGHT_TILES = new_internal_height_tiles
        
        config.INTERNAL_GAME_AREA_PIXEL_WIDTH = config.INTERNAL_GAME_AREA_WIDTH_TILES * config.TILE_SIZE
        config.INTERNAL_GAME_AREA_PIXEL_HEIGHT = config.INTERNAL_GAME_AREA_HEIGHT_TILES * config.TILE_SIZE
        
        self.internal_surface = pygame.Surface((config.INTERNAL_GAME_AREA_PIXEL_WIDTH, config.INTERNAL_GAME_AREA_PIXEL_HEIGHT)).convert_alpha()
        
        self.inventory_ui_surface = pygame.Surface((config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT)).convert_alpha()
        self.inventory_ui_surface.fill((0,0,0,0))

        if self.camera is None:
            self.camera = Camera(config.GAME_AREA_WIDTH, config.SCREEN_HEIGHT, config.TILE_SIZE, 0)
        
        self.camera.tile_size = config.TILE_SIZE 
        self.camera.viewport_width = config.INTERNAL_GAME_AREA_WIDTH_TILES
        self.camera.viewport_height = config.INTERNAL_GAME_AREA_HEIGHT_TILES
        
        if self.message_log is not None: 
            self.message_log.rect.x = 0
            self.message_log.rect.y = config.SCREEN_HEIGHT - config.MESSAGE_LOG_HEIGHT
            self.message_log.rect.width = config.GAME_AREA_WIDTH
            self.message_log.rect.height = config.MESSAGE_LOG_HEIGHT
            
            # Only recalculate message log font on window resize, not on game zoom
            if not is_zoom_only:
                new_font_size = int(config.MESSAGE_LOG_FONT_BASE_SIZE * config.MESSAGE_LOG_FONT_SCALE_FACTOR)
                if new_font_size < 8: new_font_size = 8 
                self.message_log.font = pygame.font.SysFont('consolas', new_font_size)
                
                self.message_log.line_height = self.message_log.font.get_linesize()
                self.message_log.max_lines = self.message_log.rect.height // self.message_log.line_height
        
        graphics.setup_tile_mapping() 
        self._init_fonts() 

        # Recalculate minimap dimensions and surface
        self._recalculate_minimap_dimensions()

    def change_zoom(self, zoom_delta):
        """Adjust zoom level while keeping the game camera within bounds."""
        new_zoom = config.TARGET_EFFECTIVE_TILE_SCALE + zoom_delta
        new_zoom = max(config.MIN_ZOOM_SCALE, min(config.MAX_ZOOM_SCALE, new_zoom))
        if new_zoom == config.TARGET_EFFECTIVE_TILE_SCALE:
            return

        config.TARGET_EFFECTIVE_TILE_SCALE = new_zoom
        self._recalculate_dimensions(is_zoom_only=True)

        if self.camera is not None and hasattr(self, "game_map") and self.game_map is not None:
            self.camera.x = max(0.0, min(self.camera.x, float(self.game_map.width - self.camera.viewport_width)))
            self.camera.y = max(0.0, min(self.camera.y, float(self.game_map.height - self.camera.viewport_height)))
            self.camera.target_x = max(0.0, min(self.camera.target_x, float(self.game_map.width - self.camera.viewport_width)))
            self.camera.target_y = max(0.0, min(self.camera.target_y, float(self.game_map.height - self.camera.viewport_height)))

        if hasattr(self, "message_log") and self.message_log is not None:
            self.message_log.add_message(f"Zoom {'in' if zoom_delta > 0 else 'out'}: {new_zoom:.1f}x", (200, 200, 255))


    def _recalculate_minimap_dimensions(self):
        """Recalculates minimap surface and rect based on current screen size."""
        # Calculate minimap dimensions based on screen size ratios
        minimap_pixel_width = int(config.SCREEN_WIDTH * config.MINIMAP_WIDTH_RATIO)
        minimap_pixel_height = int(config.SCREEN_HEIGHT * config.MINIMAP_HEIGHT_RATIO)

        # Ensure minimap dimensions are at least 1x1
        minimap_pixel_width = max(1, minimap_pixel_width)
        minimap_pixel_height = max(1, minimap_pixel_height)

        self.minimap_surface = pygame.Surface((minimap_pixel_width, minimap_pixel_height), pygame.SRCALPHA)
        self.minimap_surface.set_alpha(config.MINIMAP_ALPHA)

        # Calculate margins based on screen dimensions
        minimap_margin_top = int(config.SCREEN_HEIGHT * config.MINIMAP_MARGIN_TOP_RATIO)
        minimap_margin_right = int(config.SCREEN_WIDTH * config.MINIMAP_MARGIN_RIGHT_RATIO)

        # Position the minimap in the top-right corner of the UI panel
        self.minimap_rect = pygame.Rect(
            config.GAME_AREA_WIDTH + config.UI_PANEL_WIDTH - minimap_pixel_width - minimap_margin_right,
            minimap_margin_top,
            minimap_pixel_width,
            minimap_pixel_height
        )
        self.minimap_needs_redraw = True  # Always redraw minimap after resize


    def _init_fonts(self):
        """Initializes or re-initializes fonts based on current TILE_SIZE and screen dimensions."""
        
        temp_tile_size = max(1, config.TILE_SIZE)
        self.font = pygame.font.SysFont('consolas', temp_tile_size)
        
        self.inventory_font_header = pygame.font.SysFont('consolas', 20, bold=True)
        self.inventory_font_section = pygame.font.SysFont('consolas', 16)
        self.inventory_font_info = pygame.font.SysFont('consolas', 14)
        self.inventory_font_small = pygame.font.SysFont('consolas', 14)

        self.font_header = pygame.font.SysFont('consolas', 18, bold=True)
        self.font_section = pygame.font.SysFont('consolas', 16)
        self.font_info = pygame.font.SysFont('consolas', 14)
        self.font_small = pygame.font.SysFont('consolas', 14)
        

    def generate_overworld_map(self, chunk_coord=None, spawn_pos=None):
        """
        Enter the overworld at the given chunk (defaulting to whichever chunk the
        player is currently in). Each chunk is only generated once — on repeat
        visits (e.g. climbing back out of a dungeon, or walking back the way you
        came) we just restore the cached map, the same way stepping out of a
        dungeon room doesn't regenerate that room.

        spawn_pos, if given, drops the player at that exact tile — used when
        walking off the edge of one chunk into the next. Otherwise the player
        is placed back wherever they last stood in this chunk (e.g. climbing
        out of a dungeon), or near the center of the map on a first visit.
        """
        self.game_state = GameState.OVERWORLD
        self._previous_game_state = GameState.OVERWORLD
        self._environment_state = GameState.OVERWORLD

        if chunk_coord is None:
            chunk_coord = self.overworld_chunk_coord
        entering_new_chunk = chunk_coord != self.overworld_chunk_coord
        self.overworld_chunk_coord = chunk_coord

        if chunk_coord not in self.overworld_chunks:
            # Sized to feel like a real overworld rather than another dungeon floor —
            # noticeably larger than a generate_level() dungeon map (120x100).
            chunk_map = GameMap(OVERWORLD_CHUNK_WIDTH, OVERWORLD_CHUNK_HEIGHT)
            biome = self.get_chunk_biome(chunk_coord)
            
            overworld_info = generate_overworld(
                chunk_map,
                chunk_coord=chunk_coord,
                world_seed=self.world_seed,
                biome=biome,
                world_map=self.world_map,
            )
            monster_population = self.spawn_overworld_monster_groups(
                chunk_map, biome, overworld_info["dungeon_entrances"]
            )
            self.overworld_chunks[chunk_coord] = {
                "map": chunk_map,
                "dungeon_entrances": overworld_info["dungeon_entrances"],
                "population": overworld_info["population"] + monster_population,
                # Its own FOV, cached alongside the map so revisiting this chunk
                # later restores what's already been explored instead of
                # resetting it (see the restore below).
                "fov": FOV(chunk_map),
            }

        chunk = self.overworld_chunks[chunk_coord]
        self.game_map = chunk["map"]
        self.dungeon_entrance_positions = chunk["dungeon_entrances"]
        self.fov = chunk["fov"]

        if spawn_pos is not None:
            self.overworld_player_pos = spawn_pos
        elif entering_new_chunk or self.overworld_player_pos is None:
            self.overworld_player_pos = self._find_overworld_start_position()

        self.player.x, self.player.y = self.overworld_player_pos

        # --- Initial camera snap ---
        ideal_x = float(self.player.x) - (self.camera.viewport_width / 2.0)
        ideal_y = float(self.player.y) - (self.camera.viewport_height / 2.0)
        ideal_x = max(0.0, min(ideal_x, float(self.game_map.width - self.camera.viewport_width)))
        ideal_y = max(0.0, min(ideal_y, float(self.game_map.height - self.camera.viewport_height)))
        self.camera.x = ideal_x
        self.camera.y = ideal_y
        self.camera.target_x = float(self.player.x)
        self.camera.target_y = float(self.player.y)

        # Escort companions (see recruit_companion(), entities/summons.py's
        # EscortCompanion) are mid-quest state that belongs to the player,
        # not to whichever chunk happens to be loaded -- they must survive
        # a chunk change the same way the player does. Without this, every
        # escort would be impossible to complete: the player is required
        # to walk a companion to an inn, which very often means crossing
        # at least one chunk boundary along the way, and self.entities is
        # normally rebuilt from scratch on every chunk load (see below).
        #
        # A companion's (x, y) belonged to the chunk just left -- chunk
        # coordinates are chunk-local and reset at every boundary (see
        # world_map.py's chunk_local_to_world_position()) -- so a carried-
        # over position would be meaningless (and likely out of bounds) on
        # the new map. Place each companion on its own open tile near the
        # player rather than all of them (and the player) sharing one --
        # see _find_open_tile_near_player() -- so a multi-victim escort
        # doesn't render as a single stacked sprite after every chunk
        # crossing. take_turn() has them fall in beside the player over
        # its next few turns regardless of exactly where they land here.
        taken_positions = {(self.player.x, self.player.y)}
        for companion in self.companions:
            companion.x, companion.y = self._find_open_tile_near_player(taken_positions)
            taken_positions.add((companion.x, companion.y))

        self.entities = [self.player] + list(chunk.get("population", [])) + list(self.companions)

        # Build the turn order from the populated entities (player + any
        # overworld monsters/NPCs, plus any escort companions carried over
        # above), the same way generate_level() does for dungeons —
        # previously this was left empty, so overworld monsters were never
        # given a turn to act.
        self.turn_order = [e for e in self.entities if not (isinstance(e, Mimic) and e.disguised)]
        for entity in self.turn_order:
            entity.roll_initiative()
        self.turn_order = sorted(self.turn_order, key=lambda e: e.initiative, reverse=True)
        self.current_turn_index = 0
        self.update_fov()
        self.bloodstains.clear()

        self.message_log.add_message("=== THE OVERWORLD ===", (240, 240, 240))
        self.message_log.add_message("Walk onto a dungeon entrance to descend, or off the map's edge to keep exploring.", (150, 150, 255))
        self.minimap_needs_redraw = True  # New map, redraw minimap

    def _find_open_tile_near_player(self, taken_positions, max_radius=4):
        """
        Find a walkable, non-water tile near the player that isn't
        already in `taken_positions` -- used by generate_overworld_map()
        to give each escort companion its own tile after a chunk
        transition instead of stacking them all on the player's tile.

        Searches outward ring by ring (Chebyshev distance) from the
        player so the closest available spot always wins, and always
        adds its own result to nothing -- the caller is responsible for
        adding the returned position to `taken_positions` before asking
        for the next one, so two calls in a row never collide.

        Falls back to the player's own tile if nothing suitable turns up
        within max_radius (e.g. a companion cornered against water or
        map edge) -- companions have blocks_movement=False, so sharing a
        tile for a moment is a harmless visual overlap rather than a
        stuck-entity bug, and take_turn() will spread them back out on
        its own over the next few turns as the player moves.
        """
        width, height = self.game_map.width, self.game_map.height
        for radius in range(1, max_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue  # only this ring -- smaller radii already tried
                    x, y = self.player.x + dx, self.player.y + dy
                    if not (0 <= x < width and 0 <= y < height):
                        continue
                    if (x, y) in taken_positions:
                        continue
                    if not self.game_map.is_walkable(x, y) or is_water_tile(self.game_map.tiles[y][x]):
                        continue
                    return (x, y)
        return (self.player.x, self.player.y)

    def _start_chunk_transition(self, chunk_coord, spawn_pos):
        """
        Kick off the fade-out/fade-in used when the player walks into a new
        overworld chunk. The actual chunk_coord/spawn_pos are stashed and only
        applied once the screen has fully faded to black (see update()), so the
        chunk generation work happens while the screen is hidden.
        """
        self.pending_chunk_transition = (chunk_coord, spawn_pos)
        self.chunk_transition_phase = "out"
        self.chunk_transition_alpha = 0

    def _find_overworld_start_position(self):
        """Find an open grass tile nearest the center of the current overworld chunk to spawn on."""
        from world.tile import grass

        width, height = self.game_map.width, self.game_map.height
        center_x, center_y = width // 2, height // 2

        for radius in range(max(width, height)):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    x, y = center_x + dx, center_y + dy
                    if 0 <= x < width and 0 <= y < height:
                        if self.game_map.tiles[y][x] is grass:
                            return x, y

        return center_x, center_y  # Fallback — shouldn't happen on a real map

    def get_chunk_biome(self, coord):
        """
        Look up this chunk's biome from the persistent world map, so
        neighboring chunks agree on terrain the same way they now agree on
        rivers, instead of each chunk's biome being a random walk from
        whichever neighbor happened to be generated first (the old
        BIOME_CONNECTIONS approach — kept below, now unused, in case we ever
        want chunk-local biome variation layered on top of the world map).
        """
        if coord in self.chunk_biomes:
            return self.chunk_biomes[coord]

        biome = self.world_map.biome_at(coord)
        self.chunk_biomes[coord] = biome

        return biome


    def is_point_in_room_interior(self, room, x, y):
        """Check if a point (x, y) is within the actual interior of a room."""
        from world.dungeon_generator import LShapedRoom
        
        if isinstance(room, LShapedRoom):
            # For L-shaped rooms, check if point is in either section's interior
            in_h = (room.h_x1 < x < room.h_x2) and (room.h_y1 < y < room.h_y2)
            in_v = (room.v_x1 < x < room.v_x2) and (room.v_y1 < y < room.v_y2)
            return in_h or in_v
        else:
            # For rectangular rooms
            return (room.x1 < x < room.x2) and (room.y1 < y < room.y2)

    def get_room_interior_area(self, room):
        """Calculate the area (number of interior tiles) of a room."""
        from world.dungeon_generator import LShapedRoom
        
        if isinstance(room, LShapedRoom):
            # For L-shaped rooms, count actual interior tiles
            h_area = max(0, (room.h_x2 - room.h_x1 - 2)) * max(0, (room.h_y2 - room.h_y1 - 2))
            v_area = max(0, (room.v_x2 - room.v_x1 - 2)) * max(0, (room.v_y2 - room.v_y1 - 2))
            # Subtract overlap (intersection area) to avoid double counting
            overlap_x = max(0, min(room.h_x2, room.v_x2) - max(room.h_x1, room.v_x1) - 2)
            overlap_y = max(0, min(room.h_y2, room.v_y2) - max(room.h_y1, room.v_y1) - 2)
            overlap_area = overlap_x * overlap_y
            return h_area + v_area - overlap_area
        else:
            # For rectangular rooms
            return max(0, (room.x2 - room.x1 - 2)) * max(0, (room.y2 - room.y1 - 2))

    def spawn_monsters_near_prison_alert(self, alert_x, alert_y, search_radius=8):
        """
        Spawns nearby monsters that hear a prison door alert.
        Searches within radius for walkable spawn locations.
        
        Args:
            alert_x, alert_y: Position of the prison door that was opened
            search_radius: How far away to search for spawn locations
        """
        # Get possible monsters for this level. self.current_level is this
        # dungeon's depth (1 .. DUNGEON_MAX_FLOORS); clamp defensively the
        # same way generate_level() does.
        monster_depth = max(1, min(self.current_level, max(self.MONSTER_SPAWN_TIERS)))
        possible_monsters = self.MONSTER_SPAWN_TIERS.get(monster_depth, [])

        if not possible_monsters:
            return
        
        # Find nearby valid spawn locations (not right next to door, give player breathing room)
        spawn_candidates = []
        for dy in range(-search_radius, search_radius + 1):
            for dx in range(-search_radius, search_radius + 1):
                # Don't spawn immediately adjacent to the door
                if abs(dx) <= 2 and abs(dy) <= 2:
                    continue
                
                check_x = alert_x + dx
                check_y = alert_y + dy
                
                # Bounds check
                if not (0 <= check_x < self.game_map.width and 0 <= check_y < self.game_map.height):
                    continue

                if is_crypt_position(self.game_map, check_x, check_y):
                    continue

                # Walkability and entity checks
                if not self.game_map.is_walkable(check_x, check_y):
                    continue
                if any(e.x == check_x and e.y == check_y and e.alive for e in self.entities):
                    continue
                if is_water_tile(self.game_map.tiles[check_y][check_x]):
                    continue
                
                spawn_candidates.append((check_x, check_y))
        
        if not spawn_candidates:
            return
        
        # Randomly select 1-2 spawn locations
        num_to_spawn = random.randint(1, min(2, len(spawn_candidates)))
        spawn_locations = random.sample(spawn_candidates, num_to_spawn)
        
        # Choose primary monster type for this group
        primary_monster_class = random.choice(possible_monsters)
        
        # Spawn monsters
        spawned_count = 0
        for spawn_x, spawn_y in spawn_locations:
            monster = primary_monster_class(spawn_x, spawn_y)
            self.entities.append(monster)
            self.turn_order.append(monster)
            monster.roll_initiative()
            
            monster_article = "An" if monster.name[0] in "AEIOUaeiou" else "A"
            self.message_log.add_message(
                f"{monster_article} {monster.name} hears the commotion and rushes in!",
                (255, 100, 100)
            )
            spawned_count += 1
        
        # Re-sort turn order by initiative
        if spawned_count > 0:
            self._resort_turn_order_preserving_current()

    def _handle_smash_chest(self, chest):
        """
        Player attempts to smash open a locked chest with brute force.

        Mechanics (D&D 5e flavour):
          - DC 14 Strength check to break it open.
          - Success:  chest opens, but one item is destroyed by the impact.
          - Failure:  player takes 1d4 bludgeoning damage from the rebound.
          - Either way the noise has a chance to trigger a monster ambush
            (60% on success because of the loud crack; 35% on failure from
            the repeated banging).
        """
        str_roll  = random.randint(1, 20)
        str_mod   = self.player.get_ability_modifier(self.player.strength)
        str_total = str_roll + str_mod
        SMASH_DC  = 14

        self.message_log.add_message(
            f"You heave your weight against the chest! "
            f"(STR {str_roll}{str_mod:+d} = {str_total} vs DC {SMASH_DC})",
            (200, 150, 80)
        )

        if str_total >= SMASH_DC:
            # --- Success ---
            self.message_log.add_message(
                "The chest splinters open with a CRACK!", (255, 200, 80)
            )
            chest.is_locked = False
            chest.opened    = True
            chest.char      = 'olc'

            if chest.contents:
                # Destroy one random item — it didn't survive the smash
                destroyed = random.choice(chest.contents)
                chest.contents.remove(destroyed)
                self.message_log.add_message(
                    f"The {destroyed.name} is crushed in the wreckage.", (180, 100, 60)
                )

            # Give remaining loot
            if chest.contents:
                items_given = []
                for item in list(chest.contents):
                    if self.player.inventory.add_item(item):
                        items_given.append(item.name)
                        chest.contents.remove(item)
                    else:
                        self.message_log.add_message(
                            f"Your inventory is full! You couldn't pick up the {item.name}.",
                            (255, 0, 0)
                        )
                if items_given:
                    self.message_log.add_message(
                        f"You salvage: {', '.join(items_given)}.", (0, 220, 100)
                    )
            else:
                self.message_log.add_message("Nothing survived the smash.", (150, 150, 150))

            ambush_chance = 0.60

        else:
            # --- Failure ---
            splinter_dmg = random.randint(1, 4)
            self.message_log.add_message(
                f"The chest holds! You recoil from the impact, taking {splinter_dmg} damage.",
                (220, 80, 80)
            )
            # Routed through take_damage() (rather than poking .hp directly)
            # so a chest that knocks the player to 0 hp triggers death saves
            # instead of an instant kill, same as every other damage source.
            self.player.take_damage(splinter_dmg, self, damage_type='bludgeoning')

            ambush_chance = 0.35

        # --- Noise check — may attract nearby monsters ---
        ambush_roll = random.random()
        if ambush_roll < ambush_chance:
            self.message_log.add_message(
                "The commotion draws unwanted attention...", (255, 80, 80)
            )
            self.spawn_monsters_near_prison_alert(chest.x, chest.y, search_radius=8)
        else:
            self.message_log.add_message(
                "The dungeon stays quiet... for now.", (120, 120, 120)
            )

    def get_valid_spawn_point_in_room(self, room, game_map, max_attempts=50):
        """Get a valid spawn point within a room's actual interior."""
        from world.dungeon_generator import LShapedRoom
        
        for _ in range(max_attempts):
            if isinstance(room, LShapedRoom):
                # Choose randomly between horizontal and vertical section
                if random.random() < 0.5:
                    x = random.randint(room.h_x1 + 1, room.h_x2 - 2)
                    y = random.randint(room.h_y1 + 1, room.h_y2 - 2)
                else:
                    x = random.randint(room.v_x1 + 1, room.v_x2 - 2)
                    y = random.randint(room.v_y1 + 1, room.v_y2 - 2)
            else:
                # For rectangular rooms
                x = random.randint(room.x1 + 1, room.x2 - 2)
                y = random.randint(room.y1 + 1, room.y2 - 2)
            
            if 0 <= x < game_map.width and 0 <= y < game_map.height:
                if game_map.is_walkable(x, y):
                    return x, y
        
        # Fallback to room center if all attempts fail
        return room.center()

    def _dungeon_level_key(self, level_number):
        """
        The self.dungeon_levels cache key for `level_number` of whichever
        dungeon the player is currently in (self.current_dungeon_id). Every
        entrance on the map gets its own dungeon_id (see
        handle_player_action()'s dungeon_entrance_positions check), so two
        different entrances' "level 1" are cached -- and generated -- as two
        entirely separate dungeons instead of colliding on a bare int key.
        """
        return (self.current_dungeon_id, level_number)

    def _snapshot_dungeon_level(self, level_number):
        """
        Save the currently-loaded dungeon level's live state into
        self.dungeon_levels, keyed by (dungeon_id, level_number), so
        returning to it later (via stairs, or leaving the dungeon and diving
        back in) restores it exactly as the player left it -- monsters that
        died stay dead, items that were picked up stay gone, remaining loot
        and lit torches stay put -- instead of generating a brand new
        layout. Mirrors generate_overworld_map()'s per-chunk caching of
        self.overworld_chunks.

        Call this right before self.game_map/self.entities/etc. get
        reassigned to a different level, while they still describe the level
        being left.
        """
        self.dungeon_levels[self._dungeon_level_key(level_number)] = {
            "map": self.game_map,
            "stairs_positions": self.stairs_positions,
            "torch_light_sources": self.torch_light_sources,
            "lit_wall_torches": set(self.lit_wall_torches),
            "fov": self.fov,
            # Every entity on this level except the player, who carries
            # over to whichever level (or the overworld) they move to next.
            "entities": [e for e in self.entities if e is not self.player],
        }

    def _restore_dungeon_level(self, level_number, spawn_on_stairs_up):
        """
        Reload a previously-visited dungeon level from self.dungeon_levels
        instead of generating a new one -- see _snapshot_dungeon_level().
        """
        cached = self.dungeon_levels[self._dungeon_level_key(level_number)]
        self.game_map = cached["map"]
        self.stairs_positions = cached["stairs_positions"]
        self.torch_light_sources = cached["torch_light_sources"]
        self.lit_wall_torches = cached["lit_wall_torches"]
        self.fov = cached["fov"]

        # Which staircase the player should reappear beside depends on which
        # direction they just traveled, not just "this level's entrance":
        #   - Descending into this level (spawn_on_stairs_up=False) means we
        #     arrived from the shallower level above via ITS 'down' stairs,
        #     so we land on THIS level's 'up' stairs -- the entry point
        #     generate_dungeon() places rooms[0] (and the player's very
        #     first spawn) around.
        #   - Climbing back up into this level (spawn_on_stairs_up=True)
        #     means we arrived from the deeper level below via ITS 'up'
        #     stairs, so we must land on THIS level's 'down' stairs -- the
        #     exact staircase the player originally descended through --
        #     not back at the level's entrance. Landing at 'up' here was
        #     the bug: it teleported the player back to the dungeon's start
        #     instead of to the stairs they actually climbed.
        # Each branch falls back to whichever stairs key IS present, in
        # case a level was generated without one (e.g. a single-staircase
        # or boss level), so we never silently no-op the spawn placement.
        if spawn_on_stairs_up:
            landing_stairs = self.stairs_positions.get('down', self.stairs_positions.get('up'))
        else:
            landing_stairs = self.stairs_positions.get('up', self.stairs_positions.get('down'))

        if landing_stairs is not None:
            self.player.x, self.player.y = landing_stairs

        self.entities = [self.player] + list(cached["entities"])

        self.turn_order = [e for e in self.entities if not (isinstance(e, Mimic) and e.disguised)]
        for entity in self.turn_order:
            entity.roll_initiative()
        self.turn_order = sorted(self.turn_order, key=lambda e: e.initiative, reverse=True)
        self.current_turn_index = 0

        ideal_x = self.player.x - self.camera.viewport_width // 2
        ideal_y = self.player.y - self.camera.viewport_height // 2
        ideal_x = max(0, min(ideal_x, self.game_map.width - self.camera.viewport_width))
        ideal_y = max(0, min(ideal_y, self.game_map.height - self.camera.viewport_height))
        self.camera.x = ideal_x
        self.camera.y = ideal_y
        self.camera.target_x = self.player.x
        self.camera.target_y = self.player.y

        self.update_fov()
        self.bloodstains.clear()
        self.floating_texts.clear()

        self.message_log.add_message(f"=== RETURNED TO DUNGEON LEVEL {level_number} ===", (0, 255, 255))
        self.minimap_needs_redraw = True

    def _dungeon_seed(self, level_number):
        """
        A deterministic seed for self.current_dungeon_id's `level_number`,
        derived from world_seed plus the dungeon's own global position (see
        current_dungeon_id -- it's set to the entrance tile's global world
        position, unique per entrance across the whole persistent map) and
        the level number itself. Different entrances -- or different levels
        of the same entrance -- almost never land on the same seed, so
        generate_dungeon() (see dungeon_generator.py's `seed` parameter)
        never rerolls the same layout twice, while revisiting the exact
        same entrance+level (e.g. after a save/reload with no cache) always
        reproduces the exact same dungeon.
        """
        dungeon_x, dungeon_y = self.current_dungeon_id
        return (
            self.world_seed * 1_000_003
            + dungeon_x * 92_821
            + dungeon_y * 68_927
            + level_number * 131
        ) & 0xFFFFFFFF

    def _dungeon_floor_count(self):
        """
        How many floors self.current_dungeon_id's dungeon has in total,
        in [DUNGEON_MIN_FLOORS, DUNGEON_MAX_FLOORS].

        Derived the same way _dungeon_seed() derives a level's layout
        seed -- from world_seed plus the dungeon entrance's own global
        position -- but deliberately through its own Random instance
        rather than reseeding the shared `random` module, since this can
        be (and is) called from generate_level() before any per-level
        random.seed(dungeon_seed) call happens. Deterministic per
        entrance, so re-entering the same entrance always finds the same
        total floor count, even after a save/reload with nothing cached.
        """
        dungeon_x, dungeon_y = self.current_dungeon_id
        seed = (
            self.world_seed * 486_187_739
            + dungeon_x * 92_821
            + dungeon_y * 68_927
        ) & 0xFFFFFFFF
        span = self.DUNGEON_MAX_FLOORS - self.DUNGEON_MIN_FLOORS + 1
        return self.DUNGEON_MIN_FLOORS + random.Random(seed).randrange(span)

    def generate_level(self, level_number, spawn_on_stairs_up=False):
        # Snapshot whichever dungeon level the player is currently standing
        # on -- if any -- before swapping away from it. Guarded on
        # game_state rather than unconditionally, since generate_level() is
        # also how the player first enters the dungeon from the tavern/
        # overworld, and there's nothing dungeon-side to save in that case.
        if self.game_state == GameState.DUNGEON:
            self._snapshot_dungeon_level(self.current_level)

        self.game_state = GameState.DUNGEON
        self._previous_game_state = GameState.DUNGEON
        self._environment_state = GameState.DUNGEON
        self.current_level = level_number
        self.max_level_reached = max(self.max_level_reached, level_number)

        if self._dungeon_level_key(level_number) in self.dungeon_levels:
            self._restore_dungeon_level(level_number, spawn_on_stairs_up=spawn_on_stairs_up)
            return

        # -- first visit to this level: generate it from scratch ----------
        self.lit_wall_torches = set()  # Reset lit torches for the new level 

        self.game_map = GameMap(120, 100)
        self.fov = FOV(self.game_map)

        # Deterministic per (dungeon entrance, level) seed -- see
        # current_dungeon_id's docstring -- so this exact entrance's exact
        # level always regenerates identically if it's ever rebuilt, while
        # a different entrance (or a different level) reliably gets a
        # different layout instead of every "level 1" on the map sharing
        # the same rooms.
        # This dungeon's total floor count (2-5, deterministic per
        # entrance -- see _dungeon_floor_count()) and whether this is the
        # last one. The final floor never gets downstairs -- there's
        # nowhere further down for this dungeon to go -- and always gets
        # a boss room instead (see is_boss_floor below).
        dungeon_floor_count = self._dungeon_floor_count()
        is_final_floor = level_number >= dungeon_floor_count

        dungeon_seed = self._dungeon_seed(level_number)
        rooms, self.stairs_positions, self.torch_light_sources, prison_prisoners = generate_dungeon(
            self.game_map, level_number, seed=dungeon_seed, spawn_downstairs=not is_final_floor
        )


        # Defensive path only: in normal play a level is always cached (see
        # _restore_dungeon_level above) by the time the player could climb
        # back up to it, so spawn_on_stairs_up=True never actually reaches
        # fresh generation. If it ever does, mirror the same direction
        # logic as the restore path: arriving from below lands on THIS
        # level's 'down' stairs, not its 'up' entrance.
        if spawn_on_stairs_up and 'down' in self.stairs_positions:
            start_x, start_y = self.stairs_positions['down']
        elif spawn_on_stairs_up and 'up' in self.stairs_positions:
            start_x, start_y = self.stairs_positions['up']
        else:
            start_x, start_y = rooms[0].center()
        
        self.player.x = start_x
        self.player.y = start_y


        ideal_x = self.player.x - self.camera.viewport_width // 2
        ideal_y = self.player.y - self.camera.viewport_height // 2
        # Clamp ideal position to map boundaries
        ideal_x = max(0, min(ideal_x, self.game_map.width - self.camera.viewport_width))
        ideal_y = max(0, min(ideal_y, self.game_map.height - self.camera.viewport_height))
        self.camera.x = ideal_x
        self.camera.y = ideal_y
        self.camera.target_x = self.player.x # Also set target_x/y so lerp starts correctly
        self.camera.target_y = self.player.y
        # No need to call self.camera.update here, as render will do it.

        # Altars are now generated exclusively in circular temple rooms via generate_circular_temple()
        # See: dungeon_generator.py _generate_circular_room() and temple_room.py generate_circular_temple()

        self.entities = [self.player]
        # Add any prison prisoners to the entity list
        for prisoner in prison_prisoners:
            self.entities.append(prisoner)        
        
        monsters_per_level = min(5 + level_number, len(rooms) - 2)
        monster_rooms = rooms[1:monsters_per_level + 2]

        # The final floor of THIS dungeon always gets a boss room --
        # see is_final_floor above -- regardless of whether this
        # particular dungeon turned out to be 2 floors or the full 5.
        is_boss_floor = is_final_floor
        boss_entity = None
        boss_room = None
        if rooms and is_boss_floor:
            # Choose the largest room by area, prefer not to use the player's start room
            candidate_rooms = rooms[1:] if len(rooms) > 1 else rooms
            if candidate_rooms:
                # NEW: Use get_room_interior_area to handle L-shaped rooms
                boss_room = max(
                    candidate_rooms,
                    key=lambda r: self.get_room_interior_area(r)
                )
                # Find a spawn point inside the boss room that is walkable and not on stairs or water
                preferred_spots = []
                center_x, center_y = boss_room.center()
                # Require a 1-tile margin from room walls to avoid spawning overlapping walls visually
                margin = 2  # ensures a 2x2 footprint plus 1 tile buffer from walls
                min_x = boss_room.x1 + margin
                max_x = boss_room.x2 - margin  # exclusive upper bound in range()
                min_y = boss_room.y1 + margin
                max_y = boss_room.y2 - margin

                # Prefer center if it satisfies margin
                if min_x <= center_x < max_x and min_y <= center_y < max_y:
                    preferred_spots.append((center_x, center_y))

                # Add fallback points strictly inside the margin box
                for y_coord in range(min_y, max_y):
                    for x_coord in range(min_x, max_x):
                        preferred_spots.append((x_coord, y_coord))

                spawn_x, spawn_y = None, None
                for sx, sy in preferred_spots:
                    # Require 2x2 walkable area for boss spawn AND ensure all 4 tiles are floor-like (not walls/doors/water)
                    size_ok = True
                    for ox in (0, 1):
                        for oy in (0, 1):
                            tx, ty = sx + ox, sy + oy
                            if not (0 <= tx < self.game_map.width and 0 <= ty < self.game_map.height):
                                size_ok = False
                                break
                            if not self.game_map.is_walkable(tx, ty):
                                size_ok = False
                                break
                            # Avoid stairs positions
                            if ('down' in self.stairs_positions and (tx, ty) == self.stairs_positions.get('down')):
                                size_ok = False
                                break
                            if ('up' in self.stairs_positions and (tx, ty) == self.stairs_positions.get('up')):
                                size_ok = False
                                break
                            # Ensure tile type is floor-ish (avoid walls/doors/water overlap). Use tile char check.
                            tile_obj = self.game_map.tiles[ty][tx]
                            if tile_obj.char in ['#', '+'] or is_water_tile(tile_obj): # NEW: Check for water tiles
                                size_ok = False
                                break
                        if not size_ok:
                            break
                    if size_ok:
                        spawn_x, spawn_y = sx, sy
                        break

                if spawn_x is not None:
                    # Pick a boss from this depth's pool. level_number is
                    # this dungeon's depth (1 .. DUNGEON_MAX_FLOORS), so it
                    # indexes BOSS_FLOORS directly; clamp defensively in
                    # case DUNGEON_MAX_FLOORS is ever raised past the pool's
                    # highest defined depth.
                    boss_depth = max(1, min(level_number, max(self.BOSS_FLOORS)))
                    boss_name = random.choice(self.BOSS_FLOORS[boss_depth])
                    # Map names to classes (fallback to Demogorgon if missing)
                    name_to_cls = {
                        'Ooze': Ooze,
                        'LizardfolkArcher': LizardfolkArcher,  # Example of a non-boss that could be added to the schedule
                        'MyconidAdult': MyconidAdult,
                        'Troll': Troll,  # TODO: replace with GoblinKing class when available
                        'Owlbear': Owlbear,
                        'Beholder': Beholder,
                        'TombTapper': TombTapper,
                        'DeathSlaad': DeathSlaad,
                        'Gauth': Gauth,
                        'AlphaGrick': AlphaGrick,
                        'MindFlayer': MindFlayer,
                        'RedDragon': RedDragon,  # TODO: replace with Red Dragon class when available
                        'Demogorgon': Demogorgon,
                        'Arasta': Arasta
                    }
                    boss_cls = name_to_cls.get(boss_name, Demogorgon)
                    boss_entity = boss_cls(spawn_x, spawn_y)
                    # Mark as boss for rendering/logic hooks
                    setattr(boss_entity, 'is_boss', True)
                    setattr(boss_entity, 'footprint_size', boss_entity.footprint_size)
                    self.entities.append(boss_entity)
                    # Don't spawn regular monsters in the boss room
                    monster_rooms = [r for r in monster_rooms if r is not boss_room]

        # Determine which monsters can spawn on this level based on
        # MONSTER_SPAWN_TIERS, keyed by depth (1 .. DUNGEON_MAX_FLOORS).
        # Clamp defensively for the same reason boss_depth does above.
        monster_depth = max(1, min(level_number, max(self.MONSTER_SPAWN_TIERS)))
        possible_monsters = self.MONSTER_SPAWN_TIERS.get(monster_depth, [GiantRat])

        for i, room in enumerate(monster_rooms):
            # NEW: Use get_valid_spawn_point_in_room to handle L-shaped rooms
            x, y = self.get_valid_spawn_point_in_room(room, self.game_map)
            # Ensure monster doesn't spawn on water or prison tiles
            if (0 <= x < self.game_map.width and 0 <= y < self.game_map.height and
                self.game_map.is_walkable(x, y) and not is_water_tile(self.game_map.tiles[y][x])
                and not is_prison_cell_position(self.game_map, x, y)):
                # Randomly choose a primary monster class from the possible_monsters list
                chosen_monster_class = random.choice(possible_monsters)

                # Mimic is handled separately as a special case in dungeon_generator.py
                if chosen_monster_class == Mimic:
                    continue 

                # Spawn a group of related monsters (1-4 per room)
                spawned = self.spawn_monster_group(room, chosen_monster_class, self.game_map, possible_monsters)

        if len(rooms) > 2 and random.random() < 0.2: # Healer spawnrate
            shuffled_healer_rooms = list(rooms[1:-1])
            random.shuffle(shuffled_healer_rooms)
            healer_spawned = False
            for healer_room in shuffled_healer_rooms:
                possible_spawn_points = []
                for y_coord in range(healer_room.y1 + 2, healer_room.y2 - 1):
                    for x_coord in range(healer_room.x1 + 2, healer_room.x2 - 1):
                        # NEW: Check if point is in actual room interior (handles L-shaped rooms)
                        if not self.is_point_in_room_interior(healer_room, x_coord, y_coord):
                            continue
                        # Check for water tiles and other blockers
                        if self.game_map.is_walkable(x_coord, y_coord) and \
                           not any(e.x == x_coord and e.y == y_coord for e in self.entities) and \
                           not is_water_tile(self.game_map.tiles[y_coord][x_coord]) and \
                           not is_prison_cell_position(self.game_map, x_coord, y_coord):
                            is_near_tunnel = False
                            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                                neighbor_x, neighbor_y = x_coord + dx, y_coord + dy
                                if self.game_map.tiles[neighbor_y][neighbor_x] == floor and \
                                   not self.is_point_in_room_interior(healer_room, neighbor_x, neighbor_y):
                                    is_near_tunnel = True
                                    break
                            if not is_near_tunnel:
                                possible_spawn_points.append((x_coord, y_coord))
                
                if possible_spawn_points:
                    healer_x, healer_y = random.choice(possible_spawn_points)
                    dungeon_healer = DungeonHealer(healer_x, healer_y)
                    self.entities.append(dungeon_healer)
                    healer_spawned = True
                    break
            
            if not healer_spawned:
                self.message_log.add_message("DEBUG: Dungeon Healer could not find a suitable spawn spot.", (100, 100, 100))

        elif len(rooms) > 2 and random.random() < 0.9:  # Merchant spawnrate
            shuffled_merchant_rooms = list(rooms[1:-1])
            random.shuffle(shuffled_merchant_rooms)
            merchant_spawned = False
            for merchant_room in shuffled_merchant_rooms:
            
                # Check if this room is a prison cell room. If so, replace one of
                # its prisoners with the merchant instead of spawning on open floor.
                room_has_prison = any(
                    is_prison_cell_position(self.game_map, x, y)
                    for y in range(merchant_room.y1 + 1, merchant_room.y2)
                    for x in range(merchant_room.x1 + 1, merchant_room.x2)
                    if self.is_point_in_room_interior(merchant_room, x, y)  # NEW: Check actual room interior
                )
                if room_has_prison:
                    prisoner_in_room = next(
                        (e for e in self.entities
                         if isinstance(e, PrisonerNPC)
                         and merchant_room.x1 < e.x < merchant_room.x2
                         and merchant_room.y1 < e.y < merchant_room.y2),
                        None
                    )
                    if prisoner_in_room:
                        self.entities.remove(prisoner_in_room)
                        self.dungeon_merchant = DungeonMerchant(prisoner_in_room.x, prisoner_in_room.y)
                        self.entities.append(self.dungeon_merchant)
                        self.message_log.add_message(
                            "A merchant is being held prisoner in one of the cells!", (200, 180, 100)
                        )
                        merchant_spawned = True
                        break
                    # No prisoner found in this prison room — fall through to normal logic.

                # Normal spawn: find an open floor tile not near a tunnel entrance.
                possible_spawn_points = []
                for y_coord in range(merchant_room.y1 + 2, merchant_room.y2 - 1):
                    for x_coord in range(merchant_room.x1 + 2, merchant_room.x2 - 1):
                        # NEW: Check if point is in actual room interior (handles L-shaped rooms)
                        if not self.is_point_in_room_interior(merchant_room, x_coord, y_coord):
                            continue
                        if self.game_map.is_walkable(x_coord, y_coord) and \
                           not any(e.x == x_coord and e.y == y_coord for e in self.entities) and \
                           not is_water_tile(self.game_map.tiles[y_coord][x_coord]) and \
                           not is_prison_cell_position(self.game_map, x_coord, y_coord):
                            is_near_tunnel = False
                            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                                neighbor_x, neighbor_y = x_coord + dx, y_coord + dy
                                if self.game_map.tiles[neighbor_y][neighbor_x] == floor and \
                                   not self.is_point_in_room_interior(merchant_room, neighbor_x, neighbor_y):
                                    is_near_tunnel = True
                                    break
                            if not is_near_tunnel:
                                possible_spawn_points.append((x_coord, y_coord))

                if possible_spawn_points:
                    merchant_x, merchant_y = random.choice(possible_spawn_points)
                    self.dungeon_merchant = DungeonMerchant(merchant_x, merchant_y)
                    self.entities.append(self.dungeon_merchant)
                    merchant_spawned = True
                    break
                
            if not merchant_spawned:
                self.message_log.add_message("DEBUG: Dungeon Merchant could not find a suitable spawn spot.", (100, 100, 100))
                
        item_templates = [
            lesser_healing_potion, greater_healing_potion, padded_armor, studded_leather_armor, chainmail_armor, half_plate_armor,
            robes, iron_dagger, silver_dagger, iron_short_sword, bronze_short_sword, iron_long_sword, steel_long_sword, oak_staff, 
            apprentices_staff, pole_arm, steel_battle_axe, steel_rapier, iron_hammer, steel_maul, steel_mace, dwarven_flail,
            round_shield, kite_shield, tower_shield, torch,
            leather_cap, iron_helmet, steel_helmet, great_helm, mages_circlet, hood_of_shadows,
            leather_boots, iron_greaves, boots_of_speed, boots_of_stealth, dwarven_stompers,
        ]

        item_spawn_chance = 0.5 + min(0.5, level_number * 0.02) # Scales from 30% to max 50% at level 10+

        for room in rooms:
            if random.random() < item_spawn_chance:
                # NEW: Use get_valid_spawn_point_in_room to handle L-shaped rooms
                item_x, item_y = self.get_valid_spawn_point_in_room(room, self.game_map)
                
                is_blocked_by_non_item_entity = False
                for e in self.entities:
                    if e.x == item_x and e.y == item_y and \
                       (isinstance(e, Monster) and not isinstance(e, Mimic) or isinstance(e, NPC)):
                        is_blocked_by_non_item_entity = True
                        break

                is_occupied_by_another_item = False
                for existing_item in self.game_map.items_on_ground:
                    if existing_item.x == item_x and existing_item.y == item_y:
                        is_occupied_by_another_item = True
                        break


                # is_decorative_tile = self.game_map.tiles[item_y][item_x] != floor                    
                # NEW: Check if the spot is a water tile
                is_water = is_water_tile(self.game_map.tiles[item_y][item_x])

                if (item_x, item_y) != (self.player.x, self.player.y) and \
                   (item_x, item_y) not in self.stairs_positions.values() and \
                   not is_blocked_by_non_item_entity and \
                   not is_occupied_by_another_item and \
                   not is_water and \
                   not is_prison_cell_position(self.game_map, item_x, item_y): # Don't spawn items on prison tiles
                    

                    chosen_template = random.choice(item_templates)
                    item_to_add = chosen_template.__class__(
                        name=chosen_template.name,
                        char=chosen_template.char,
                        color=chosen_template.color,
                        description=chosen_template.description,
                        **{k: v for k, v in chosen_template.__dict__.items() if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                    )

                    item_to_add.x = item_x
                    item_to_add.y = item_y
                    self.game_map.items_on_ground.append(item_to_add)

        self.turn_order = [e for e in self.entities if not (isinstance(e, Mimic) and e.disguised)]
        for entity in self.turn_order:
            entity.roll_initiative()
        
        self.turn_order = sorted(self.turn_order, key=lambda e: e.initiative, reverse=True)
        self.current_turn_index = 0
        self.update_fov()
        
        self.bloodstains.clear()
        self.floating_texts.clear()  

        self.message_log.add_message(f"=== ENTERED DUNGEON LEVEL {level_number} ===", (0, 255, 255))        
        if hasattr(self, 'stairs_positions'):
            self.message_log.add_message(f"Stairs down at {self.stairs_positions.get('down')}", (150, 150, 255))
        self.minimap_needs_redraw = True # New map, redraw minimap

        # Cache this freshly generated level immediately, not just when the
        # player eventually leaves it -- harmless if _snapshot_dungeon_level()
        # runs again later with updated (post-gameplay) state, since that
        # simply overwrites this entry.
        self._snapshot_dungeon_level(level_number)

    def get_player_hp_percentage(self):
        """Returns the player's current HP as a percentage."""
        if self.player.max_hp == 0:
            return 0.0
        return self.player.hp / self.player.max_hp


    def check_tavern_door_interaction(self):
        if self.game_state == GameState.TAVERN:
            player_pos = (self.player.x, self.player.y)
            return player_pos == self.door_position
        return False

    def check_npc_interaction(self):
        if self.game_state == GameState.TAVERN:
            for npc in self.npcs:
                if (abs(self.player.x - npc.x) <= 1 and
                    abs(self.player.y - npc.y) <= 1 and
                    (abs(self.player.x - npc.x) + abs(self.player.y - npc.y)) == 1):
                    return npc
        return None


    def check_dungeon_npc_interaction(self):
        if self.game_state == GameState.DUNGEON:
            for entity in self.entities:
                if isinstance(entity, (DungeonHealer, DungeonMerchant, PrisonerNPC)):
                    if (abs(self.player.x - entity.x) <= 1 and
                        abs(self.player.y - entity.y) <= 1 and
                        (abs(self.player.x - entity.x) + abs(self.player.y - entity.y)) == 1):
                        if isinstance(entity, DungeonMerchant):
                            self.dungeon_merchant = entity
                        elif isinstance(entity, PrisonerNPC) and entity.has_been_freed:
                            return entity
                        return entity
        return None

    def check_overworld_npc_interaction(self):
        if self.game_state == GameState.OVERWORLD:
            for entity in self.entities:
                if isinstance(entity, (NPC, Shopkeeper, Innkeeper, Townsfolk, Trader)) and entity is not self.player:
                    if (abs(self.player.x - entity.x) <= 1 and
                        abs(self.player.y - entity.y) <= 1 and
                        (abs(self.player.x - entity.x) + abs(self.player.y - entity.y)) == 1):
                        if isinstance(entity, Shopkeeper):
                            self.shopkeeper = entity
                        elif isinstance(entity, Trader):
                            self.trader = entity
                        return entity
        return None

    def check_overworld_landmark_interaction(self):
        """
        Adjacency check for non-NPC StoryObjects (shrine altars, journals,
        tracks, wagons, ...) -- the landmark counterpart to
        check_overworld_npc_interaction() above. Landmarks live in
        self.landmark_registry (see _register_story_landmarks()), keyed
        by id, with positions in the same *global* tile coordinate space
        world_map.chunk_local_to_world_position() converts the player
        into (see story_integration.py's StorySystems._player_position()).
        Only landmarks in the player's current chunk can be adjacent, so
        this converts each candidate back to chunk-local via
        world_position_to_chunk_local() rather than scanning every
        landmark in the game against a mismatched coordinate space.
        """
        if self.game_state != GameState.OVERWORLD:
            return None
        for landmark in self.landmark_registry.values():
            chunk_coord, (local_x, local_y) = world_position_to_chunk_local(landmark.position)
            if chunk_coord != self.overworld_chunk_coord:
                continue
            if (abs(self.player.x - local_x) <= 1 and
                abs(self.player.y - local_y) <= 1 and
                (abs(self.player.x - local_x) + abs(self.player.y - local_y)) == 1):
                return landmark
        return None

    def _pickpocket_dc_for(self, npc):
        """
        Difficulty of the Sleight of Hand check to pick this NPC's pocket
        (see _attempt_pickpocket()). Merchants and innkeepers handle coin
        all day and keep half an eye on their purse; ordinary townsfolk
        are easier marks. Falls back to that same easier DC for any NPC
        type not called out here, rather than refusing the attempt.
        """
        if isinstance(npc, (Shopkeeper, Trader, DungeonMerchant, Merchant, Innkeeper)):
            return 15
        return 12

    def _attempt_pickpocket(self, npc):
        """
        Resolve an F2 (InteractionMode.STEAL) interaction against an
        adjacent NPC: a DEX (Sleight of Hand) check against a flat,
        NPC-type-dependent DC (see _pickpocket_dc_for()). Mirrors the
        roll/log format _resolve_world_encounter_sneak() uses for its
        stealth check, so both read the same way in the message log.

        Success grants a small amount of gold (via the same
        RewardGoldConsequence/ConsequenceExecutor path world encounter
        rewards use) and marks this NPC as already picked
        (self._pickpocketed_npc_ids) so the same mark can't be robbed
        over and over. Failure doesn't lock the NPC out of future
        attempts -- instead, if the NPC declares a `faction` attribute,
        it dings the player's reputation with that faction, so getting
        caught still costs something without needing bespoke "alerted"/
        hostile wiring added to every NPC type.

        Always returns True (the calling KEYDOWN handler treats that as
        "event consumed"), whether or not the attempt actually happened.
        """
        if id(npc) in self._pickpocketed_npc_ids:
            self.message_log.add_message(f"There's nothing left to take from {npc.name}.", (150, 150, 150))
            return True

        dex_roll = random.randint(1, 20)
        dex_mod = self.player.get_ability_modifier(self.player.dexterity)
        if "sleight_of_hand" in self.player.skill_proficiencies:
            dex_mod += self.player.proficiency_bonus
        dex_total = dex_roll + dex_mod
        dc = self._pickpocket_dc_for(npc)

        self.message_log.add_message(
            f"You try to lift something off {npc.name}. "
            f"(Sleight of Hand {dex_roll}{dex_mod:+d} = {dex_total} vs DC {dc})",
            (150, 200, 220)
        )

        executor = self.stories.story_manager.consequence_executor
        context = self.stories.execution_context

        if dex_total >= dc:
            stolen_gold = random.randint(3, 12)
            executor.execute(RewardGoldConsequence(stolen_gold), context)
            self._pickpocketed_npc_ids.add(id(npc))
            self.message_log.add_message(f"{npc.name} doesn't notice a thing.", (150, 255, 180))
        else:
            faction = getattr(npc, "faction", None)
            if faction:
                executor.execute(ModifyReputationConsequence(faction, -2), context)
            self.message_log.add_message(
                f'{npc.name} catches your hand. "Watch yourself!"', (255, 120, 100)
            )

        return True

    def _describe_surroundings(self):
        """
        Build the F4 (InteractionMode.INFO) ambient status line: the
        current world time plus whatever's worth knowing about the
        player's present location -- biome and weather out in the world,
        floor number underground, nothing special in the tavern.

        Reuses the same WorldClock/period_for_hour()/get_chunk_biome()
        lookups render()'s HUD clock readout and the biome cache already
        use, so this line never drifts out of sync with what's actually
        shown on screen. Purely a readout -- like that HUD text, nothing
        here mutates game state.
        """
        clock = self.stories.world_time.clock
        time_part = (
            f"Day {clock.day}, {clock.hour_of_day:02d}:{clock.minute_of_hour:02d} "
            f"({period_for_hour(clock.hour_of_day)})"
        )

        if self.game_state == GameState.OVERWORLD:
            biome = self.get_chunk_biome(self.overworld_chunk_coord)
            place_part = f"You are standing in {biome.value.title()} terrain."
            weather = getattr(self, "weather", "clear")
            if weather and weather != "clear":
                place_part += f" The weather is {weather}."
        elif self.game_state == GameState.DUNGEON:
            place_part = f"You are on dungeon level {self.current_level}."
        else:
            place_part = "You take in your surroundings."

        return f"{time_part} -- {place_part}"

    def interact_with_landmark(self, landmark):
        """
        Handle the player interacting with an adjacent story landmark:
        advances the owning story via StoryObject.inspect() (per
        story_integration.py integration note 4), then notifies
        TriggerRules with the trigger type matching the object -- journals
        fire read_journal (see Hollow_Shrine.json's "journal_read" rule),
        everything else fires the generic inspect_object.
        """
        landmark.inspect(self.stories.story_manager)
        if landmark.object_type == "journal":
            self.stories.fire_read_journal(landmark, instigator=self.player)
        else:
            self.stories.fire_inspect(landmark, instigator=self.player)

    def try_light_wall_torch(self):
        """
        If the player is adjacent to a wall torch tile and has the 'Torchlight'
        (has_torchlight) status effect, light that torch so it emits light.
        Returns True if a torch was successfully lit, False otherwise.
        """
        from world.tile import torch as torch_tile

        has_torchlight = any(
            effect.name == "Torchlight" for effect in self.player.active_status_effects
        )
        if not has_torchlight:
            self.message_log.add_message(
                "You need a light source (Torchlight effect) to ignite the torch.",
                (150, 150, 150)
            )
            return False

        adjacents = [
            (self.player.x + dx, self.player.y + dy)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
        ]

        for tx, ty in adjacents:
            if not (0 <= tx < self.game_map.width and 0 <= ty < self.game_map.height):
                continue
            tile_at = self.game_map.tiles[ty][tx]
            # Match torch tile by char and name (avoids importing the singleton object)
            if tile_at.char == 'i' and tile_at.name == "Torch":
                if (tx, ty) in self.lit_wall_torches:
                    self.message_log.add_message("That torch is already burning.", (255, 165, 0))
                    return False
                # Light it up
                self.lit_wall_torches.add((tx, ty))
                self.update_fov()
                self.message_log.add_message(
                    "You touch your flame to the wall torch — it roars to life!",
                    (255, 165, 0)
                )
                return True

        self.message_log.add_message("No torch to light nearby.", (150, 150, 150))
        return False

    def check_stairs_interaction(self):
        if self.game_state == GameState.DUNGEON:
            player_pos = (self.player.x, self.player.y)
            if hasattr(self, 'stairs_positions'):
                if 'down' in self.stairs_positions and player_pos == self.stairs_positions['down']:
                    return 'down'
                elif 'up' in self.stairs_positions and player_pos == self.stairs_positions['up']:
                    return 'up'
        return None

    def handle_level_transition(self, direction):
        # Fire tiles, floating combat text, and bloodstains are transient,
        # per-visit effects, not part of a level's persistent layout -- clear
        # them same as before. Entities and items_on_ground are deliberately
        # NOT cleared here anymore: generate_level() (or generate_overworld_map()
        # for climbing out of level 1, below) now snapshots the level being
        # left -- including its current entities/items -- into
        # self.dungeon_levels before anything is swapped out, so clearing
        # them here first would just cache an empty level instead of
        # persisting it. See _snapshot_dungeon_level().
        self.active_fire_tiles.clear()  # Fire tiles belong to the old level; discard them
        if hasattr(self, "floating_texts"):
            self.floating_texts.clear()
        if hasattr(self, "bloodstains"):
            self.bloodstains.clear()

        if direction == 'down':
            new_level = self.current_level + 1
            self.message_log.add_message(f"Going down to level {new_level}...", (100, 200, 255))
            self.generate_level(new_level, spawn_on_stairs_up=False)
        elif direction == 'up' and self.current_level > 1:
            new_level = self.current_level - 1
            self.message_log.add_message(f"Going up to level {new_level}...", (100, 200, 255))
            self.generate_level(new_level, spawn_on_stairs_up=True)
        elif direction == 'up' and self.current_level == 1:
            # Leaving the dungeon entirely -- persist level 1's current state
            # (same as generate_level() does between levels) before switching
            # to the overworld map, so diving back in later restores it.
            self._snapshot_dungeon_level(self.current_level)
            if self.entered_dungeon_from_overworld:
                self.message_log.add_message("You climb back out into the open air...", (100, 200, 255))
                self.generate_overworld_map()
            else:
                # This used to return to the standalone tavern-interior gamestate.
                # That's gone now — the tavern lives in the overworld, so climbing
                # out just drops the player back onto the overworld map instead.
                self.message_log.add_message("You climb back out into the open air...", (100, 200, 255))
                self.generate_overworld_map()


    def update_fov(self):
        base_radius = getattr(self.player, 'vision_radius', 4)  # base vision radius

        # Open skies let the player see much farther than cramped dungeon corridors.
        if self.game_state == GameState.OVERWORLD:
            base_radius = max(base_radius, self.OVERWORLD_VISION_RADIUS)

        torch_bonus = 0
        has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)    
        
        if has_torchlight:
            torch_bonus = 1

        LIGHT_PRIORITY = {
            'torch': 3,
            'player': 2,
            'darkvision': 1
        }

        # Clear previous visibility sources but keep explored tiles.
        # NOTE: explored only ever grows, so comparing sizes before/after
        # is equivalent to a full set comparison but avoids copying and
        # diffing the entire (potentially huge) explored set every move.
        previous_explored_count = len(self.fov.explored)
        self.fov.visible_sources.clear()

        # Compute base FOV with 'player' light source and darkvision radius
        self.fov.compute_fov(
            self.player.x,
            self.player.y,
            radius=base_radius,
            light_source_type='player',
            player_darkvision_radius=max(getattr(self.player, 'darkvision_radius', 0), base_radius)
        )

        # If torchlight active, compute extended FOV with 'torch' light source
        if torch_bonus > 0:
            torch_fov = FOV(self.game_map)          

            torch_fov.compute_fov(
                self.player.x,
                self.player.y,
                radius=base_radius + torch_bonus,
                light_source_type='torch'
            )

            # Merge torchlight FOV into main FOV with priority
            for (x, y), source in torch_fov.visible_sources.items():
                existing_source = self.fov.visible_sources.get((x, y))
                if existing_source is None:
                    self.fov.visible_sources[(x, y)] = source
                    self.fov.explored.add((x, y))
                else:
                    # Replace only if torchlight has higher priority
                    if LIGHT_PRIORITY[source] > LIGHT_PRIORITY.get(existing_source, 0):
                        self.fov.visible_sources[(x, y)] = source
                        self.fov.explored.add((x, y))

        # Emit light from each lit wall torch (player-activated via 'F' key).
        # Torches sit on wall tiles, so casting FOV from the torch position itself
        # traps the light inside the wall.  Instead, find every open floor tile
        # adjacent to the torch and cast from there — the union of those passes
        # is the light that fans out into the room.
        WALL_TORCH_RADIUS = 3  # how far a lit wall torch illuminates
        for (wx, wy) in getattr(self, 'lit_wall_torches', set()):
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ox, oy = wx + dx, wy + dy
                if not (0 <= ox < self.game_map.width and 0 <= oy < self.game_map.height):
                    continue
                if self.game_map.tiles[oy][ox].blocked:
                    continue  # skip neighbours that are also walls
                wall_torch_fov = FOV(self.game_map)
                wall_torch_fov.compute_fov(
                    ox, oy,
                    radius=WALL_TORCH_RADIUS,
                    light_source_type='torch'
                )
                for (x, y), source in wall_torch_fov.visible_sources.items():
                    existing = self.fov.visible_sources.get((x, y))
                    if existing is None:
                        self.fov.visible_sources[(x, y)] = source
                        self.fov.explored.add((x, y))
                    elif LIGHT_PRIORITY[source] > LIGHT_PRIORITY.get(existing, 0):
                        self.fov.visible_sources[(x, y)] = source
                        self.fov.explored.add((x, y))

        # Check if new tiles were explored for minimap redraw
        if len(self.fov.explored) != previous_explored_count:
            self.minimap_needs_redraw = True

        # Existing monster activation logic...
        self.refresh_monster_wake_state()

    def _refresh_owned_blocking_entities_cache(self):
        """
        Recompute self._owned_blocking_entities: every alive, blocking
        entity owned by the player (summons, escorts, ...), for
        Monster.take_turn()'s target-priority check to consume.

        Called once per player action (see update()'s batch turn-
        processing block), not once per monster -- this is the same
        "compute once, let every consumer read it" idea as
        refresh_monster_wake_state(), applied to a scan that used to run
        from scratch, with three hasattr() checks per entity, at the top
        of *every single active monster's turn* -- including plain
        attack turns, not just movement. That made it a bigger cost
        during an actual fight than the FOV-recompute issue ever was,
        since a monster mid-melee never moves but still took this hit
        every turn.
        """
        self._owned_blocking_entities = [
            entity for entity in self.entities
            if getattr(entity, 'owner', None) is self.player
            and getattr(entity, 'alive', False)
            and getattr(entity, 'blocks_movement', False)
        ]

    def refresh_monster_wake_state(self):
        """
        Wake/sleep every Monster based on its distance to and visibility
        from the player, using whatever FOV grid is already computed.

        Split out of update_fov() on purpose: this loop only reads the
        player's *existing* self.fov (already-computed visibility/
        distance) -- it never recomputes it. update_fov() itself calls
        this right after it (re)computes FOV, following an actual player
        move. Monster/summon movement -- which doesn't change the
        player's position or anything sight-blocking -- should call this
        directly instead of update_fov(), since the player's FOV grid
        can't have changed just because a monster took a step. Calling
        the full update_fov() (a raycast from the player's position, a
        torch-light pass, and this same wake loop) after every single
        monster's move, once per monster, all within the same
        synchronous turn-processing batch (see game.py's `update()`), is
        what turned "several monsters acting in one player turn" into a
        visible freeze that got worse as monster count grew.
        """
        WAKE_RADIUS = 10  # Tiles within which monsters wake up regardless of visibility

        for entity in self.entities:
            if isinstance(entity, Monster):
                # World-encounter ambush groups (see _spawn_world_encounter_monsters)
                # stay asleep no matter how close or visible the player is -
                # only landing a hit on one of them wakes the group (see
                # Monster.take_damage). Once woken, encounter_group members
                # fall back under the normal wake/sleep rules below.
                if getattr(entity, 'encounter_group', None) is not None and not entity.is_active:
                    continue

                visibility_type = self.fov.get_visibility_type(entity.x, entity.y)
                distance_to_player = entity.distance_to(self.player.x, self.player.y)

                # Wake if visible OR within wake radius
                if visibility_type in ['player', 'torch', 'darkvision'] and distance_to_player <= WAKE_RADIUS:
                    if not entity.is_active:
                        entity.is_active = True
                        entity.sleep_cooldown = 0
                        self.message_log.add_message(f"You spot a {entity.name}!", entity.color)
                elif distance_to_player <= WAKE_RADIUS:
                    entity.is_active = True
                    entity.sleep_cooldown = 0
                elif visibility_type in ['player', 'torch', 'darkvision'] and distance_to_player >= WAKE_RADIUS:
                    if entity.is_active:
                        entity.is_active = False
                        entity.sleep_cooldown = random.randint(5, 15)
                        self.message_log.add_message(f"The {entity.name} seems to have fallen asleep.", (100, 100, 100))
                else:
                    if entity.is_active and entity.sleep_cooldown <= 10:
                        entity.is_active = False
                        entity.sleep_cooldown = random.randint(5, 15)

    def get_current_entity(self):
        if not self.turn_order or self.game_state == GameState.TAVERN:
            return self.player
        if self.current_turn_index >= len(self.turn_order):
            self.current_turn_index = 0
        return self.turn_order[self.current_turn_index]

    def _resort_turn_order_preserving_current(self):
        """
        Re-sort self.turn_order by initiative without losing track of
        whose turn self.current_turn_index currently points at.

        self.current_turn_index is just an integer -- it only means
        "the current entity" relative to turn_order's *existing* order.
        Any call site that inserts new entities (a wave of reinforcements,
        a prison alert, a newly-recruited companion, ...) and then
        re-sorts is effectively shuffling the list out from under that
        index. If this can happen mid-combat -- e.g. a monster's death
        during another entity's take_turn() triggers a new wave via a
        TriggerRule effect, synchronously, in the middle of the turn-
        processing loop in update() -- the index silently starts
        pointing at the wrong entity afterward, which can desync turn
        processing badly enough that it never cleanly lands on the
        player's turn again (the game appears to freeze).

        Always use this instead of calling turn_order.sort(...) directly
        whenever new entities might be inserted while a turn could
        already be in progress.
        """
        current_entity = (
            self.turn_order[self.current_turn_index]
            if self.turn_order and self.current_turn_index < len(self.turn_order)
            else None
        )
        self.turn_order.sort(key=lambda e: e.initiative, reverse=True)
        if current_entity is not None and current_entity in self.turn_order:
            self.current_turn_index = self.turn_order.index(current_entity)

    def next_turn(self):
        if self.game_state == GameState.TAVERN:
            if random.random() < 0.1:
                ambient_msgs = [
                    "The fire crackles in the hearth, filling the tavern with warmth...",
                    "Laughter erupts from a table of rowdy adventurers...",
                    "The bard plucks a lazy tune on a worn lute...",
                    "Mugs clink together as patrons cheer a victorious tale...",
                    "The innkeeper wipes down the counter with a knowing smile...",
                    "The smell of roasted meat drifts from the kitchen...",
                    "A pair of dice clatter across a wooden table, followed by groans...",
                    "Someone hums a forgotten ballad in the corner...",
                    "The tavern cat weaves between the legs of travelers, tail high...",
                    "A weary adventurer sighs, staring long into his ale..."
                ]
                self.message_log.add_message(random.choice(ambient_msgs), (200, 180, 140))
            return

        # Get the entity whose turn it *just was* or *is currently* before advancing the index
        current_acting_entity = self.get_current_entity()

        # Process status effects for the entity that just completed its turn (or was about to)
        if current_acting_entity:
            current_acting_entity.process_status_effects(self)
            if current_acting_entity == self.player:
                self.player.update_hunger(self)  # Decrease hunger each turn
                self.player.update_sanity(self)  # Update sanity (torch/darkness effect)
                self.stories.advance_turn()  # World time moves with player actions, not real time
                if self.player.hunger < self.player.hunger_threshold:
                    hunger_msgs = [
                        f"{self.player.name}'s stomach growls hungrily...",
                        f"{self.player.name} feels their strength waning from hunger.",
                        f"A hollow ache gnaws at {self.player.name}'s insides...",
                        f"Hunger claws at {self.player.name}, demanding to be fed.",
                        f"{self.player.name} feels faint — food is needed soon."
                    ]
                    self.message_log.add_message(random.choice(hunger_msgs), (255, 100, 0))
                
                if not self.player.alive:  # Check if the player has died from hunger
                    self.handle_game_over()
                    return  # End the turn if the player is dead

        if current_acting_entity == self.player and self.player.extra_turns > 0:
            self.player.extra_turns -= 1
            self.message_log.add_message("You take an extra action!", (255, 255, 0))
            self.player_has_acted = False # Reset for the next action
            return # IMPORTANT: Exit before advancing to the next entity

        if current_acting_entity == self.player and self.player.hidden_turns > 0:
            self.player.hidden_turns -= 1
            self.player_has_acted = False # Reset for the next action
            
            return # IMPORTANT: Exit before advancing to the next entity   

        self.cleanup_entities()

        # If after cleanup, there are no entities left (e.g., all monsters died)
        if not self.turn_order:
            if self.player and self.player.alive:
                self.turn_order = [self.player]  # Ensure player is in turn order
                self.current_turn_index = 0
                self.player_has_acted = False  # Reset for player's next turn
                self.update_fov()  # Update FOV for the player
            return  # No more turns to process if no entities

        # Advance the turn index to the next entity
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)

        # Get the entity whose turn it is now (after advancing the index)
        current = self.get_current_entity()

        # If it's the player's turn, reset their action flag and update FOV
        if current == self.player:
            self.update_fov()
            self.player_has_acted = False  # This is correctly reset for player's turn
            self.player_bonus_action_used = False  # Reset bonus action availability on a new player turn
            self.tick_fire_tiles()  # Advance fire tile durations and deal burn damage
            if random.random() < 0.1:
                place = GameState.OVERWORLD if self.game_state == GameState.OVERWORLD else GameState.DUNGEON
                hour_of_day = self.stories.world_time.clock.hour_of_day
                period = _ambient_time_period(hour_of_day)
                ambient_msgs = AMBIENT_MESSAGES_BY_PERIOD[place][period]
                tint = (180, 200, 160) if place == GameState.OVERWORLD else (180, 180, 180)
                self.message_log.add_message(random.choice(ambient_msgs), tint)


    def tick_fire_tiles(self):
        """
        Called once per player turn.  For every active FireElementalTile:
          - Deal 1d6 fire damage to any entity standing on it.
          - Decrement the tile's duration.
          - Restore the underlying tile when the fire burns out.
        """
        from entities.monster import Monster

        still_burning = []

        for (fx, fy) in self.active_fire_tiles:
            current_tile = self.game_map.tiles[fy][fx]

            # Safety check: something else may have replaced this tile already
            if not isinstance(current_tile, FireElementalTile):
                continue

            # Damage any living entity standing on the fire
            for entity in self.entities:
                if entity.x == fx and entity.y == fy and getattr(entity, 'alive', False):
                    fire_damage = random.randint(1, 6)
                    entity.take_damage(fire_damage, self, damage_type='fire')
                    self.message_log.add_message(
                        f"{entity.name} takes {fire_damage} fire damage from the burning ground!",
                        (255, 100, 0)
                    )
                    self.floating_texts.append(
                        FloatingText(entity.x, entity.y - 0.5, str(fire_damage), (255, 80, 0))
                    )

                    # Award XP if the fire kills a monster
                    if not entity.alive and isinstance(entity, Monster):
                        xp_gained = entity.die(self, killer=self.player)
                        self.player.gain_xp(xp_gained, self)
                        self._notify_monster_killed(entity, killer=self.player)

            # Advance the fire tile's duration counter
            expired = current_tile.tick()
            if expired:
                self.game_map.tiles[fy][fx] = current_tile.underlying_tile
                self.minimap_needs_redraw = True
            else:
                still_burning.append((fx, fy))

        self.active_fire_tiles = still_burning

    def _notify_monster_killed(self, entity, killer=None):
        """
        Reports a monster's death to the story engine exactly once,
        however it died. Both explicit combat-resolution kill sites in
        this file (a direct player hit, a burning tile) call this
        instead of self.stories.fire_kill() directly, and
        cleanup_entities() below also calls it as a catch-all safety net
        for every OTHER way a tagged monster can die that this file
        doesn't resolve itself -- an ally like GuardVictim finishing one
        off on its own turn, one monster killing another, a status
        effect ticking hp to 0 -- wherever that logic actually lives
        (monster.py's take_turn()/take_damage(), summons.py, abilities.py).

        This matters because _start_world_encounter_combat()/
        _advance_world_encounter_wave() count down a "remaining" flag
        that only decrements on a KILL_NPC trigger; a group member that
        dies without ever firing one is invisible to that count, so it
        never reaches zero and the next wave (or the aftermath menu)
        silently never comes -- indistinguishable from "waves just don't
        trigger." Sweeping every dead, group-tagged entity here, right
        before cleanup_entities() prunes it from self.entities, is a
        strictly cheaper and more robust guarantee than hunting down and
        patching every individual kill site by hand (see this file's
        STORY_NPC_MONSTER_CLASSES/spawn_story_npc() comment -- the same
        group_id tagging is shared by authored-story NPCs too, so this
        net catches those the same way).

        `_fire_kill_reported` is stamped directly on the entity rather
        than tracked in a separate set, so it needs no separate pruning
        as entities come and go, and stays correct independently across
        as many concurrent group_id-tagged encounters as happen to be
        live at once.
        """
        if getattr(entity, "_fire_kill_reported", False):
            return
        entity._fire_kill_reported = True
        self.stories.fire_kill(entity, instigator=killer or self.player, group_id=getattr(entity, "group_id", None))

    def cleanup_entities(self):
        """Remove dead or expired entities/items from the game world."""

        # Catch-all for any group_id-tagged monster that died without this
        # file's own combat code ever reporting it (see
        # _notify_monster_killed()) -- must run before the alive-filter
        # just below prunes the entity away, since fire_kill still needs
        # to see it (and its group_id) to attribute the kill correctly.
        for entity in self.entities:
            if not getattr(entity, "alive", True) and getattr(entity, "group_id", None):
                self._notify_monster_killed(entity)

        # Remove dead monsters/NPCs
        self.entities = [e for e in self.entities if getattr(e, "alive", True)]

        # self.companions (see recruit_companion()/EscortCompanion in
        # entities/summons.py) is a third list tracking the same escort
        # entities, separate from self.entities/self.turn_order above --
        # and unlike those two, nothing generically prunes it. Normally
        # that's fine: EscortCompanion.die()/complete_escort() call
        # _leave_party(), which removes the companion from all three
        # lists itself. But die() is only ever invoked automatically for
        # Monster instances (see tick_fire_tiles(), which checks
        # "isinstance(entity, Monster)" before calling entity.die()) --
        # a companion standing on a fire tile (or hit by any other damage
        # source that just sets alive=False directly, the way take_damage()
        # does, without going through Monster.die()) becomes dead without
        # _leave_party() ever running. It still gets filtered out of
        # self.entities/self.turn_order above (those only check "alive"),
        # but it stays in self.companions forever -- and that list being
        # non-empty permanently blocks the player from entering a dungeon
        # (see handle_player_action's "You can't take {names} down there"
        # check), so a companion dying this way silently soft-locks
        # dungeon descent for the rest of the playthrough. Routing through
        # the companion's own die() (rather than just filtering the list)
        # keeps the normal "has fallen" message and cleanup behavior even
        # for this indirect death path; it's a safe no-op for companions
        # that already left the party normally, since they're no longer
        # in self.companions by the time this runs.
        for companion in list(self.companions):
            if not getattr(companion, "alive", True):
                companion.die(self)

        # self.turn_order is a separate list from self.entities (see
        # generate_overworld_map()/generate_level()/recruit_companion()) and
        # was never being pruned here — every monster that ever died over a
        # play session stayed in turn_order permanently. Left unchecked, a
        # long fight or an extended chase made next_turn() cycle through an
        # ever-growing pile of stale, already-dead entries before reaching a
        # live one, so per-turn cost crept up the longer play went on instead
        # of staying flat. Track whichever entity's turn is currently in
        # progress before filtering, so removing dead entries can't shift
        # current_turn_index onto the wrong entity or skip/repeat a turn.
        if self.turn_order:
            current_entity = (
                self.turn_order[self.current_turn_index]
                if self.current_turn_index < len(self.turn_order)
                else None
            )
            # The player is deliberately exempted from this prune, even once
            # not .alive: dying no longer removes the player from turn_order
            # instantly (see Player.is_dying/take_damage() -- death saves
            # keep them "in the fight," unconscious, for several turns; and
            # even an outright death still needs one more lap through the
            # batch loop in update() to be recognized as "the player's turn"
            # so the top-of-update() game-over check can fire on the next
            # frame). Dropping the player here instead makes
            # get_current_entity() never equal self.player again, so the
            # batch loop's "break once it's the player's turn" condition can
            # never be satisfied -- it just spins through the remaining
            # monsters' turns forever. See the matching "if not
            # self.player.alive: break" guard in update()'s batch loop for
            # the other half of this fix.
            self.turn_order = [
                e for e in self.turn_order
                if e is self.player or getattr(e, "alive", True)
            ]

            if current_entity is not None and current_entity in self.turn_order:
                self.current_turn_index = self.turn_order.index(current_entity)
            elif self.turn_order:
                self.current_turn_index %= len(self.turn_order)
            else:
                self.current_turn_index = 0

        # Handle items (depends on your structure: game.items_on_ground or game.map.items_on_ground)
        if hasattr(self, "items_on_ground"):
            self.items_on_ground = [i for i in self.items_on_ground if getattr(i, "alive", True)]
        elif hasattr(self, "map") and hasattr(self.map, "items_on_ground"):
            self.map.items_on_ground = [i for i in self.map.items_on_ground if getattr(i, "alive", True)]

        # Clean up any dead entities left in tiles
        if hasattr(self, "map") and hasattr(self.map, "tiles"):
            for row in self.map.tiles:
                for tile in row:
                    if hasattr(tile, "entity") and tile.entity is not None:
                        if not getattr(tile.entity, "alive", True):
                            tile.entity = None

        # Clean up floating texts (remove expired ones)
        if hasattr(self, "floating_texts"):
            self.floating_texts = [t for t in self.floating_texts if not getattr(t, "expired", False)]

        # Cap message log size (prevents memory bloat)
        if hasattr(self, "message_log") and hasattr(self.message_log, "messages"):
            MAX_LOG_MESSAGES = 50
            if len(self.message_log.messages) > MAX_LOG_MESSAGES:
                self.message_log.messages = self.message_log.messages[-MAX_LOG_MESSAGES:]
    
    

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if self.ignore_next_input:
                # Ignore all keydown events once, then reset flag
                if event.type == pygame.KEYDOWN:
                    self.ignore_next_input = False
                    return True  # Consume this event and ignore it
                else:
                    continue  # Ignore other events until keydown resets flag

            # NEW: Handle input specifically for GAME_OVER state
            if self.game_state == GameState.GAME_OVER:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        # Restart the game: reset player, generate tavern or level 1
                        if self.death_screen_animation_phase == 3: # Only if initial animation is done
                            self.death_screen_animation_phase = 4 # NEW: Start fade-out phase
                            self.fade_out_alpha = 0 # Start fade-out from transparent
                            self.message_log.add_message("Initiating restart sequence...", (100, 200, 255))

                            pygame.event.clear()
                            self.ignore_next_input = True  # Set flag to ignore next input
                        return True
                    elif event.key == pygame.K_q:
                        # Quit the game
                        return False # Signal to quit
                continue  # Skip other event processing when game over

            if event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                self._recalculate_dimensions()
                self.render()            

            # NEW: Handle mouse wheel scrolling for message log and game zoom
            if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.MOUSEWHEEL:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = event.pos
                    wheel_delta = 0
                    if event.button == 4:
                        wheel_delta = 1
                    elif event.button == 5:
                        wheel_delta = -1
                else:
                    pos = pygame.mouse.get_pos()
                    wheel_delta = event.y

                message_log_hit = self.message_log.rect.collidepoint(pos)
                game_area_hit = (0 <= pos[0] < config.GAME_AREA_WIDTH and
                                 0 <= pos[1] < config.SCREEN_HEIGHT)

                if message_log_hit:
                    if wheel_delta > 0:
                        self.message_log.scroll_up()
                        return True
                    elif wheel_delta < 0:
                        self.message_log.scroll_down()
                        return True

                if game_area_hit and self.game_state in (GameState.DUNGEON, GameState.OVERWORLD, GameState.TAVERN, GameState.TARGETING):
                    if wheel_delta > 0:
                        self.change_zoom(config.ZOOM_STEP)
                        return True
                    elif wheel_delta < 0:
                        self.change_zoom(-config.ZOOM_STEP)
                        return True

                # Inventory mouse handling
                if (event.type == pygame.MOUSEBUTTONDOWN
                        and self.game_state == GameState.INVENTORY):

                    # Left-click on equipment slot → unequip to inventory
                    if event.button == 1 and hasattr(self, '_equip_slot_rects'):
                        for slot_key, rect in self._equip_slot_rects.items():
                            if rect.collidepoint(pos):
                                self._unequip_slot(slot_key)
                                return True

                    # Left-click on inventory grid slot → equip item immediately
                    # Right-click on inventory grid slot → open action popup
                    if event.button in (1, 3) and hasattr(self, '_inventory_slot_rects'):
                        for idx, rect in self._inventory_slot_rects.items():
                            if rect.collidepoint(pos):
                                items = self.player.inventory.items
                                if idx < len(items):
                                    self.selected_inventory_index = idx
                                    clicked_item = items[idx]
                                    if event.button == 1:  # left-click → equip
                                        self.player.equip_item(clicked_item, self)
                                    else:  # right-click → action popup
                                        self.selected_inventory_item = clicked_item
                                        self.game_state = GameState.INVENTORY_MENU
                                return True

            if event.type == pygame.KEYDOWN:

                # --- Trade Interaction ---
                if self.game_state == GameState.TRADE:
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_RETURN:  # Enter key to submit input
                            input_text = self.message_log.current_input  # Capture the input
                            self.handle_text_input(input_text.lower())  # Convert to lowercase when processing
                            self.message_log.clear_last_input()  # Clear the input after processing
                            self.message_log.show_input_area = False  # Hide input area after submission
                        elif event.key == pygame.K_ESCAPE:  # Cancel trade
                            self.message_log.add_message("Trade cancelled.", (255, 0, 0))
                            self.game_state = self._previous_game_state  # Return to previous state
                        elif event.key == pygame.K_BACKSPACE:  # Handle backspace
                            self.message_log.current_input = self.message_log.current_input[:-1]  # Remove the last character
                        else:
                            # Capture the input character
                            if event.unicode:  # Check if the event has a unicode character
                                self.message_log.current_input += event.unicode  # Append the character to the current input

                # --- Locked Chest Menu ---
                elif self.game_state == GameState.CHEST_MENU:
                    if event.key == pygame.K_1:
                        # Option 1: Pick the lock
                        self.game_state = self._previous_game_state
                        if self._chest_menu_target:
                            self._chest_menu_target.open(self.player, self)
                        self._chest_menu_target = None
                        action_taken = True
                    elif event.key == pygame.K_2:
                        # Option 2: Smash the chest
                        self.game_state = self._previous_game_state
                        if self._chest_menu_target:
                            self._handle_smash_chest(self._chest_menu_target)
                        self._chest_menu_target = None
                        action_taken = True
                    elif event.key in (pygame.K_3, pygame.K_ESCAPE):
                        # Option 3: Leave it alone
                        self.message_log.add_message("You step back from the chest.", (150, 150, 150))
                        self.game_state = self._previous_game_state
                        self._chest_menu_target = None
                    return True  # Consume all input while menu is open

                # --- Death Saving Throw Menu ---
                elif self.game_state == GameState.DEATH_SAVE_MENU:
                    self.handle_death_save_menu_input(event.key)
                    return True  # Consume all input while unconscious

                # --- World Encounter Discovery Prompt ---
                elif self.game_state == GameState.WORLD_ENCOUNTER_DISCOVERY:
                    if event.key in (pygame.K_1, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                        self._continue_past_world_encounter_discovery()
                    return True  # Consume all input while the prompt is open

                # --- World Encounter Menu ---
                elif self.game_state == GameState.WORLD_ENCOUNTER_MENU:
                    stage = self._current_world_encounter_stage()
                    choice = self._world_encounter_choice_for_key(event.key, stage["choices"])
                    if choice is not None:
                        self._resolve_world_encounter_choice(choice)
                        # Cancel-flagged choices (e.g. "Ignore") don't cost a
                        # turn, same as backing out of any other menu with ESC.
                        action_taken = not choice.get("is_cancel", False)
                    return True  # Consume all input while menu is open

                # --- World Encounter Aftermath Menu ---
                elif self.game_state == GameState.WORLD_ENCOUNTER_AFTERMATH_MENU:
                    choice = self._world_encounter_choice_for_key(event.key, self._world_encounter_aftermath["choices"])
                    if choice is not None:
                        self._resolve_world_encounter_aftermath_choice(choice)
                        action_taken = not choice.get("is_cancel", False)
                    return True  # Consume all input while menu is open

                # --- Shop Menu ---
                elif self.game_state == GameState.SHOP_MENU:
                    self.handle_shop_menu_input(event.key)
                    return True

                # --- Innkeeper Menu ---
                elif self.game_state == GameState.INNKEEPER_MENU:
                    self.handle_innkeeper_menu_input(event.key)
                    return True  # Consume all input while menu is open

                # --- Rest Menu ---
                elif self.game_state == GameState.REST_MENU:
                    self.handle_rest_menu_input(event.key)
                    return True  # Consume all input while menu is open

                else:
                    if event.key == pygame.K_SLASH:  # Enter key to submit input
                        if self.message_log.show_input_area:  # Check if input area is visible
                            input_text = self.message_log.current_input  # Capture the input
                            self.handle_text_input(input_text.lower())  # Process the input
                        else:
                            self.message_log.show_input_area = True  # Show input area if not already visible
                            self.message_log.current_input = ""  # Clear input when activating the input area
                    elif event.key == pygame.K_BACKSPACE:  # Handle backspace
                        if self.message_log.show_input_area:  # Only allow backspace if input area is visible
                            self.message_log.current_input = self.message_log.current_input[:-1]  # Remove the last character
                    elif event.key == pygame.K_RETURN:
                        self.message_log.clear_last_input()
                        self.message_log.show_input_area = False
                    else:
                        # Capture the input character only if the input area is visible
                        if self.message_log.show_input_area and event.unicode:  # Check if the event has a unicode character
                            self.message_log.current_input += event.unicode  # Append the character to the current input


                    # Handle other key events (like opening inventory) only if not in trade state
                    if event.key == pygame.K_i:
                        if self.game_state == GameState.TARGETING:
                            self.message_log.add_message("Targeting cancelled (Inventory opened).", (150, 150, 150))
                            self.ability_in_use = None # Clear the ability
                            self.player_has_acted = False # Player didn't act if cancelled
                            self.player.current_action_state = None # Clear any pending action state                        
                        
                        if self.game_state == GameState.INVENTORY:  # If already in inventory, close it
                            self.message_log.add_message("Closing Inventory.", (100, 200, 255))
                            self.selected_inventory_item = None
                            self.game_state = self._previous_game_state
                            print("Inventory closed.")  # Debugging statement
                        elif self.game_state == GameState.INVENTORY_MENU:  # If in inventory menu, go back to main inventory
                            self.game_state = GameState.INVENTORY
                            self.selected_inventory_item = None
                            self.message_log.add_message("Returning to Inventory.", (100, 200, 255))
                        else:  # If not in inventory, open it
                            self.game_state = GameState.INVENTORY  # Open inventory
                            self.message_log.add_message("Opening Inventory...", (100, 200, 255))
                        return True  # Consume event, don't process other game states          
 
                    # Handle the Campfire Kit usage
                    if self.game_state == GameState.INVENTORY_MENU:
                        self.handle_inventory_menu_input(event.key)
                        return True

                    # Handle resting
                    if event.key == pygame.K_r:
                        if self.player and self.game_state in (GameState.DUNGEON, GameState.OVERWORLD, GameState.TAVERN):
                            self.open_rest_menu()
                        return True  # Consume event 
                    

                    # --- Interaction mode switching (F1-F4) ---
                    # Lets the player choose what the interact key (F) does next,
                    # rather than it always trying every kind of interaction at
                    # once. Only meaningful out in the world -- ignored during
                    # character creation, menus, targeting, etc.
                    if self.game_state in (GameState.DUNGEON, GameState.OVERWORLD, GameState.TAVERN):
                        new_mode = None
                        if event.key == pygame.K_F1:
                            new_mode = InteractionMode.DIALOGUE
                        elif event.key == pygame.K_F2:
                            new_mode = InteractionMode.STEAL
                        elif event.key == pygame.K_F3:
                            new_mode = InteractionMode.INTERACT
                        elif event.key == pygame.K_F4:
                            new_mode = InteractionMode.INFO

                        if new_mode is not None:
                            self.interaction_mode = new_mode
                            self.message_log.add_message(
                                f"Interaction mode: {InteractionMode.LABELS[new_mode]}", (180, 220, 255)
                            )
                            return True  # Consume event, doesn't cost a turn

                    # --- Always accessible menus ---
                    if event.key == pygame.K_c:
                        if self.game_state == GameState.TARGETING:
                            self.message_log.add_message("Targeting cancelled (Character Menu opened).", (150, 150, 150))
                            self.ability_in_use = None # Clear the ability
                            self.player_has_acted = False # Player didn't act if cancelled
                            self.player.current_action_state = None # Clear any pending action state
                            # IMPORTANT: Do NOT set _previous_game_state here. It was already set above
                            # to the state *before* targeting. This ensures we return to DUNGEON/TAVERN.
                        if self.game_state == GameState.CHARACTER_MENU: # If already in character menu, close it
                            self.game_state = self._previous_game_state
                            self.message_log.add_message("Closing Character Menu.", (100, 200, 255))
                        else: # If not in character menu, open it
                            self.game_state = GameState.CHARACTER_MENU
                            self.message_log.add_message("Opening Character Menu...", (100, 200, 255))
                        return True # Consume event, don't process other game states  


                    # --- Overworld access (temporary: until a proper tavern exit exists) ---
                    if event.key == pygame.K_o and self.game_state == GameState.TAVERN:
                        self.message_log.add_message("You step outside into the overworld...", (100, 200, 255))
                        self.generate_overworld_map()
                        return True  # Consume event, don't process other game states

                    # --- Inventory Navigation ---
                    if self.game_state == GameState.INVENTORY:
                        GRID_COLS = 5  # Must match COLS in ui_screens.py
                        n = len(self.player.inventory.items)
                        if n > 0:
                            idx = self.selected_inventory_index
                            if event.key in (pygame.K_LEFT, pygame.K_a):
                                self.selected_inventory_index = (idx - 1) % n
                            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                                self.selected_inventory_index = (idx + 1) % n
                            elif event.key in (pygame.K_UP, pygame.K_w):
                                new_idx = idx - GRID_COLS
                                self.selected_inventory_index = new_idx if new_idx >= 0 else idx
                            elif event.key in (pygame.K_DOWN, pygame.K_s):
                                new_idx = idx + GRID_COLS
                                self.selected_inventory_index = new_idx if new_idx < n else idx
                        if event.key == pygame.K_RETURN:
                            if 0 <= self.selected_inventory_index < n:
                                self.selected_inventory_item = self.player.inventory.items[self.selected_inventory_index]
                                self.game_state = GameState.INVENTORY_MENU
                                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
                        return True  # Consume event

                # --- Trade Interaction --- 
                if self.game_state in (GameState.DUNGEON, GameState.OVERWORLD):
                    if event.key == pygame.K_f:
                        # --- Wall torch lighting (takes priority over NPC / quick-bar) ---
                        adjacent_has_torch = any(
                            (0 <= self.player.x + dx < self.game_map.width and
                             0 <= self.player.y + dy < self.game_map.height and
                             self.game_map.tiles[self.player.y + dy][self.player.x + dx].char == 'i' and
                             self.game_map.tiles[self.player.y + dy][self.player.x + dx].name == "Torch")
                            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
                        )
                        if adjacent_has_torch:
                            self.try_light_wall_torch()
                            return True  # Consume event regardless (don't fall to quick-bar)                    

                        if self.interaction_mode == InteractionMode.INFO:
                            # Location-based, not NPC-based, so this doesn't need
                            # check_overworld_npc_interaction()/check_dungeon_npc_interaction()
                            # at all -- one check covers both DUNGEON and OVERWORLD.
                            self.message_log.add_message(self._describe_surroundings(), (180, 220, 255))
                            return True

                        if self.game_state == GameState.OVERWORLD:
                            npc = self.check_overworld_npc_interaction()

                            if self.interaction_mode == InteractionMode.STEAL:
                                # Encounter victims are being rescued, not robbed --
                                # everyone else adjacent is fair game for a pickpocket attempt.
                                if npc and not isinstance(npc, EncounterVictim):
                                    return self._attempt_pickpocket(npc)
                                self.message_log.add_message("There's no one close enough to steal from.", (150, 150, 150))
                                return True

                            if self.interaction_mode == InteractionMode.INTERACT:
                                # Ground loot only -- NPCs (talk/trade/rescue) are not
                                # reachable through F while in Interact mode, same way they
                                # aren't reachable through Steal mode above.
                                if self.handle_item_pickup():
                                    return True
                                self.message_log.add_message("There's nothing here to grab.", (150, 150, 150))
                                return True

                            if isinstance(npc, EncounterVictim):
                                npc.interact(self.player, self)
                                return True
                            elif isinstance(npc, Innkeeper):
                                # An escort delivery takes priority over the
                                # innkeeper's own Rest/Buy Food menu -- walking
                                # up to them with companions in tow resolves
                                # the delivery instead of opening the menu.
                                if self.try_deliver_companions(npc):
                                    return True
                                self.open_innkeeper_menu(npc)
                                return True
                            elif isinstance(npc, (Shopkeeper, Trader)):
                                npc.offer_trade(self.player, self)  # Call the trade method for the Shopkeeper/Trader
                                return True
                            elif npc:
                                self.message_log.add_message(f'{npc.name}: "{npc.get_dialogue()}"', (200, 200, 255))
                                self.stories.fire_talk(npc, instigator=self.player)
                                return True

                            landmark = self.check_overworld_landmark_interaction()
                            if landmark:
                                self.interact_with_landmark(landmark)
                                return True

                        merchant = self.check_dungeon_npc_interaction()  # Check for adjacent NPC
                        if self.interaction_mode == InteractionMode.STEAL:
                            if merchant:
                                return self._attempt_pickpocket(merchant)
                            self.message_log.add_message("There's no one close enough to steal from.", (150, 150, 150))
                            return True
                        if self.interaction_mode == InteractionMode.INTERACT:
                            # Reached for GameState.DUNGEON (the OVERWORLD branch above
                            # already returned before getting here for that state).
                            if self.handle_item_pickup():
                                return True
                            self.message_log.add_message("There's nothing here to grab.", (150, 150, 150))
                            return True
                        if isinstance(merchant, DungeonMerchant):
                            merchant.offer_trade(self.player, self)  # Call the trade method for the Merchant
                            return True  # Consume event
                        elif isinstance(merchant, PrisonerNPC) and merchant.has_been_freed:
                            # Give the reward first (only fires once), then show dialogue.
                            merchant.give_reward(self.player, self)
                            self.message_log.add_message(
                                f'{merchant.name}: "{merchant.get_dialogue()}"', (220, 200, 140)
                            )
                            self.stories.fire_talk(merchant, instigator=self.player)
                            return True

                if self.game_state in GameState.TAVERN:
                    if event.key == pygame.K_f:  # Check if 'F' is pressed
                        if self.interaction_mode == InteractionMode.INFO:
                            self.message_log.add_message(self._describe_surroundings(), (180, 220, 255))
                            return True
                        npc = self.check_npc_interaction()  # Check for adjacent NPC
                        if self.interaction_mode == InteractionMode.STEAL:
                            if npc:
                                return self._attempt_pickpocket(npc)
                            self.message_log.add_message("There's no one close enough to steal from.", (150, 150, 150))
                            return True
                        if self.interaction_mode == InteractionMode.INTERACT:
                            if self.handle_item_pickup():
                                return True
                            self.message_log.add_message("There's nothing here to grab.", (150, 150, 150))
                            return True
                        if npc:
                            if isinstance(npc, Merchant):
                                npc.offer_trade(self.player, self)  # Call the trade method for the Merchant
                            else:
                                self.message_log.add_message(f"{npc.name}: {npc.get_dialogue()}", (200, 200, 255))
                                self.stories.fire_talk(npc, instigator=self.player)
                            return True  # Consume event

                # --- Quick Bar Key Presses ---
                if self.game_state not in [GameState.CHARACTER_CREATION, GameState.CLASS_SELECTION, GameState.GAME_OVER, GameState.TRADE, GameState.SHOP_MENU]:
                    if event.key == pygame.K_q:
                        if self.player.use_quick_bar_item('q', self):
                            action_taken = True
                        else:
                            # If use_quick_bar_item returns False, it means it couldn't be used,
                            # but it doesn't necessarily mean the player's turn is consumed.
                            # The message is already logged by use_quick_bar_item.
                            pass
                    elif event.key == pygame.K_e:
                        if self.player.use_quick_bar_item('e', self):
                            action_taken = True
                        else:
                            pass

                # ── Race / Lineage selection ──────────────────────────────
                if self.game_state == GameState.CHARACTER_CREATION:
                    group_lineages = self._lineages_for_group(self.selected_group_index)
                    max_group     = len(self.race_groups) - 1
                    max_lineage   = len(group_lineages) - 1
 
                    if event.key in (pygame.K_UP, pygame.K_w):
                        # Navigate groups upward
                        self.selected_group_index   = (self.selected_group_index - 1) % (max_group + 1)
                        self.selected_lineage_index = 0
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        # Navigate groups downward
                        self.selected_group_index   = (self.selected_group_index + 1) % (max_group + 1)
                        self.selected_lineage_index = 0
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        # Cycle lineages within the group
                        self.selected_lineage_index = (self.selected_lineage_index - 1) % (max_lineage + 1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        # Cycle lineages within the group
                        self.selected_lineage_index = (self.selected_lineage_index + 1) % (max_lineage + 1)
                    elif event.key == pygame.K_RETURN:
                        self.finalize_race_selection()
                        return True
 
                # ── Class selection ────────────────────────────────────────
                if self.game_state == GameState.CLASS_SELECTION:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        self.selected_class_index = (
                            (self.selected_class_index - 1) % len(self.available_classes)
                        )
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.selected_class_index = (
                            (self.selected_class_index + 1) % len(self.available_classes)
                        )
                    elif event.key == pygame.K_RETURN:
                        self.finalize_character_creation()
                        return True
                    elif event.key == pygame.K_BACKSPACE:
                        # Go back to race / lineage selection
                        self.game_state = GameState.CHARACTER_CREATION
                        self.message_log.add_message(
                            "Returned to race selection.", (200, 200, 255)
                        )
                        pygame.event.clear()
                        self.ignore_next_input = True
                        return True
                    


              
                # Swallow input while an overworld chunk transition is playing, so the
                # player can't act on the old chunk mid-fade or on the instant the new
                # one is generated.
                if self.chunk_transition_phase is not None:
                    continue

                # --- Handle input based on game state ---
                if self.game_state == GameState.INVENTORY:
                    self.handle_inventory_input(event.key)
                    return True
                elif self.game_state == GameState.INVENTORY_MENU:
                    self.handle_inventory_menu_input(event.key)
                    return True
                elif self.game_state == GameState.CHARACTER_MENU:
                    return True

                elif self.game_state == GameState.TARGETING: 
                    self.handle_targeting_input(event.key)
                    if self.game_state != GameState.TARGETING: 
                        pass 
                    else: # Still in TARGETING state (e.g., invalid target chosen)
                        return True # Consume event, stay in targeting mode                
                    
                
                if self.game_state not in [GameState.DUNGEON, GameState.TAVERN, GameState.OVERWORLD]:
                    continue

                # --- Player's turn logic (for Dungeon, Tavern, and Overworld) ---
                # This block will now be reached if TARGETING was cancelled and game_state reverted.
                can_player_act_this_turn = (self.game_state in (GameState.TAVERN, GameState.OVERWORLD)) or \
                                           (self.get_current_entity() == self.player and not self.player_has_acted)

                if not can_player_act_this_turn:
                    continue
                
                dx, dy = 0, 0
                action_taken = False
              

                # --- Rogue Skill ---
                if self.player.current_action_state == "cunning_action_dash":
                    # Determine the full intended dash vector
                    full_dx, full_dy = 0, 0
                    if event.key in (pygame.K_UP, pygame.K_w):
                        full_dy = -3
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        full_dy = 3
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        full_dx = -3
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        full_dx = 3
                    elif event.key == pygame.K_ESCAPE:
                        self.player.current_action_state = None
                        self.player.dash_active = False
                        self.message_log.add_message("Dash movement cancelled.", (150, 150, 150))
                        continue
                    else:
                        self.message_log.add_message("You are Dashing. Press a movement key or ESC to cancel.", (255, 150, 0))
                        continue

                    if full_dx != 0 or full_dy != 0:
                        moved_successfully = False
                        
                        # Determine step direction (e.g., -1, 0, 1)
                        step_dx = 0 if full_dx == 0 else (full_dx // abs(full_dx))
                        step_dy = 0 if full_dy == 0 else (full_dy // abs(full_dy))
                        
                        # Iterate step by step
                        for i in range(1, 4): # Dash is 3 tiles, so check 1, 2, 3 steps
                            check_x = self.player.x + step_dx * i
                            check_y = self.player.y + step_dy * i
                           
                            # Check if the next tile is walkable and not blocked by an entity
                            is_blocked_by_entity = False
                            for entity in self.entities:
                                if entity != self.player and entity.alive and entity.blocks_movement:
                                    if hasattr(entity, 'occupies_tile'):
                                        if entity.occupies_tile(check_x, check_y):
                                            is_blocked_by_entity = True
                                            break
                                    else:
                                        if entity.x == check_x and entity.y == check_y:
                                            is_blocked_by_entity = True
                                            break

                            if not self.game_map.is_walkable(check_x, check_y) or is_blocked_by_entity:
                                # Obstacle found, stop one tile before it if possible
                                if i > 1: # If we moved at least one tile before hitting obstacle
                                    self.player.x = self.player.x + step_dx * (i - 1)
                                    self.player.y = self.player.y + step_dy * (i - 1)
                                    self.message_log.add_message("You Dash forward and stop before an obstacle!", (100, 255, 100))
                                    moved_successfully = True
                                else: # Obstacle right next to player, cannot dash
                                    self.message_log.add_message("You cannot Dash forward due to an immediate obstacle!", (255, 150, 0))
                                    moved_successfully = False # No movement occurred
                                break # Stop checking further steps
                            else:
                                # If this is the last step and it's clear, move fully
                                if i == 3:
                                    self.player.x = check_x
                                    self.player.y = check_y
                                    self.message_log.add_message("You Dash forward!", (100, 255, 100))
                                    moved_successfully = True
                                    break # Full dash completed
                        # If the loop finishes without breaking (meaning full dash was possible)
                        # This case is handled by the 'if i == 3' inside the loop.
                        # If no movement occurred (e.g., blocked immediately), moved_successfully will be False.
                        if moved_successfully:
                            action_taken = True
                        else:
                            action_taken = False # No action taken if couldn't move at all
                        self.player.dash_active = False
                        self.player.current_action_state = None
                        continue # Consume the event and proceed to next turn if action_taken is True                                
                
                current_entity = self.get_current_entity()
                if current_entity == self.player and not self.player_has_acted:
                    if event.key in (pygame.K_a, pygame.K_LEFT):
                        self.player.set_facing_direction(True)  # Look left
                    elif event.key in (pygame.K_d, pygame.K_RIGHT):
                        self.player.set_facing_direction(False)   # Look right  

                # --- Normal Turn Handling (if no special action state is active) ---
                if self.player.current_action_state is None:
                    move_keys = (
                        pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
                        pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d,
                    )
                    if event.key in move_keys:
                        # Diagonal movement: rather than reacting only to the
                        # key that was just pressed, look at every movement
                        # key currently held down (e.g. W still held while D
                        # is tapped) and combine them into one diagonal step.
                        # Opposite keys held together (e.g. A+D) cancel out
                        # back to 0, same as no input on that axis.
                        keys_held = pygame.key.get_pressed()
                        if keys_held[pygame.K_UP] or keys_held[pygame.K_w]:
                            dy -= 1
                        if keys_held[pygame.K_DOWN] or keys_held[pygame.K_s]:
                            dy += 1
                        if keys_held[pygame.K_LEFT] or keys_held[pygame.K_a]:
                            dx -= 1
                        if keys_held[pygame.K_RIGHT] or keys_held[pygame.K_d]:
                            dx += 1

                    if event.key == pygame.K_t:
                        self.message_log.add_message("You skip a turn...", (200, 200, 255))
                        action_taken = True

                    if dx != 0 or dy != 0:
                        action_taken = self.handle_player_action(dx, dy)
                    elif event.key == pygame.K_SPACE:
                        if self.game_state == GameState.DUNGEON or self.game_state == GameState.OVERWORLD:
                            # --- MODIFIED START ---
                            # Prioritize picking up items at player's feet
                            if self.interaction_mode == InteractionMode.INTERACT:
                                if self.handle_item_pickup():
                                    return True
                                self.message_log.add_message("There's nothing here to grab.", (150, 150, 150))
                                return True
                            else:
                                # Check for Altar at player's position (before other interactions)
                                altar_at_pos = self.get_altar_at(self.player.x, self.player.y)
                                if altar_at_pos:
                                    altar_at_pos.interact(self.player, self)
                                    action_taken = True
                                else:
                                    # If no altar, check for adjacent interactables
                                    target = self.get_adjacent_target()
                                    if target:
                                        if isinstance(target, Mimic): # Mimics are entities, but also interactable
                                            target.reveal(self)
                                            action_taken = True
                                        elif isinstance(target, Monster): # If it's a monster, attack it
                                            self.handle_player_attack(target, self)
                                            action_taken = True
                                        else:
                                            self.message_log.add_message(f"You can't interact with {target.name} that way.", (150, 150, 150))
                                    else:
                                        # If no adjacent entity, check for chests at player's position
                                        chest_at_pos = self.get_chest_at(self.player.x, self.player.y)
                                        if chest_at_pos:
                                            if isinstance(chest_at_pos, LockedChest) and chest_at_pos.is_locked:
                                                # Show the interaction choice menu instead of opening directly
                                                self._chest_menu_target = chest_at_pos
                                                self._previous_game_state = self.game_state
                                                self.game_state = GameState.CHEST_MENU
                                            else:
                                                chest_at_pos.open(self.player, self)
                                            action_taken = True
                                        else:
                                            self.message_log.add_message("Nothing to interact with here.", (150, 150, 150))
                            # --- MODIFIED END ---
                            
                            # --- Prison door interaction ---
                            if handle_prison_door_interaction(self.player, self):
                                return True                                
                            # Check for tomb interaction (FIRST - highest priority)
                            if handle_tomb_interaction(self.player, self):
                                action_taken = True  # End player's turn after interacting with tomb

                    abilities_list = list(self.player.abilities.values())


                    # For abilities:
                    if pygame.K_1 <= event.key <= pygame.K_9:
                        ability_index = event.key - pygame.K_1
                        if 0 <= ability_index < len(abilities_list):
                            ability_to_use = abilities_list[ability_index]
                            if self.game_state == GameState.DUNGEON or self.game_state == GameState.OVERWORLD:
                                if getattr(ability_to_use, "is_bonus_action", False) and self.player_bonus_action_used:
                                    self.message_log.add_message(
                                        f"{ability_to_use.name} is a bonus action and you have already used your bonus action this turn.",
                                        (255, 150, 0)
                                    )
                                elif ability_to_use.use(self.player, self):
                                    if self.game_state != GameState.TARGETING:
                                        if getattr(ability_to_use, "is_bonus_action", False):
                                            self.player_bonus_action_used = True
                                        else:
                                            action_taken = True
                                else:
                                    pass # Debug print removed
                            else:
                                self.message_log.add_message("Abilities can only be used in the dungeon.", (150, 150, 150))
                        else:
                            self.message_log.add_message("No ability assigned to that hotkey.", (150, 150, 150)) 

                    elif event.key == pygame.K_F11:
                        flags = self.screen.get_flags()
                        if flags & pygame.FULLSCREEN:
                            info = pygame.display.Info()
                            self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
                        else:
                            self.screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.RESIZABLE)
                        self._recalculate_dimensions()
                        self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height) 
                        self.render()
                        return True
                
                if action_taken:
                    if self.game_state == GameState.DUNGEON or self.game_state == GameState.OVERWORLD:
                        self.player_has_acted = True
                    self.next_turn()
                    return True
        return True 


    def handle_targeting_input(self, key):
        """Handles input when in GameState.TARGETING (Mage Hand, etc.)"""
        dx, dy = 0, 0  # Cursor movement directions

        # Handle cursor movement
        if key in (pygame.K_UP, pygame.K_w, pygame.K_k):
            dy = -1
        elif key in (pygame.K_DOWN, pygame.K_s, pygame.K_j):
            dy = 1
        elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_h):
            dx = -1
        elif key in (pygame.K_RIGHT, pygame.K_d, pygame.K_l):
            dx = 1

        # Apply movement if possible
        if dx != 0 or dy != 0:
            new_x = self.targeting_cursor_x + dx
            new_y = self.targeting_cursor_y + dy

            # Keep cursor within map bounds and within ability range
            if (0 <= new_x < self.game_map.width and
                0 <= new_y < self.game_map.height and
                self.player.distance_to(new_x, new_y) <= self.targeting_ability_range):  # Check against ability range
                self.targeting_cursor_x = new_x
                self.targeting_cursor_y = new_y
                return  # Done, next frame will render cursor

        # Confirm target selection
        elif key == pygame.K_RETURN:
            print("DEBUG: K_RETURN pressed in TARGETING. Calling execute_targeted_ability.") # <--- ADD THIS
            self.execute_targeted_ability()  # Handle the ability effect
            return  # Exit targeting mode

        # Cancel targeting
        if key == pygame.K_ESCAPE:
            self.message_log.add_message("Targeting cancelled.", (150, 150, 150))
            self.game_state = self._previous_game_state # Return to previous state (DUNGEON)
            self.ability_in_use = None # Clear the ability
            self.missile_darts_remaining = 0  # Clear Magic Missile dart counter
            self.player_has_acted = False # Player didn't act if cancelled
            self.player.current_action_state = None # <--- THIS LINE MUST BE HERE
            return # Input handled 


    def handle_shop_menu_input(self, key):
        """Handles keyboard input while the shop overlay is open."""
        merchant = self._shop_menu_merchant
        if not merchant:
            self.game_state = self._previous_game_state
            return

        # Current item list depends on mode
        buy_items  = merchant.items_for_sale
        sell_items = self.player.inventory.items
        items      = buy_items if self._shop_mode == "buy" else sell_items

        if key in (pygame.K_UP, pygame.K_w):
            self._shop_selected_index = max(0, self._shop_selected_index - 1)

        elif key in (pygame.K_DOWN, pygame.K_s):
            self._shop_selected_index = min(len(items) - 1, self._shop_selected_index + 1)

        elif key == pygame.K_TAB:
            # Switch between buy and sell tabs
            self._shop_mode = "sell" if self._shop_mode == "buy" else "buy"
            self._shop_selected_index = 0

        elif key == pygame.K_RETURN:
            if not items or not (0 <= self._shop_selected_index < len(items)):
                return
            selected = items[self._shop_selected_index]
            if self._shop_mode == "buy":
                result = merchant.buy_item(self.player, selected.name)
                self.message_log.add_message(result, (255, 240, 160))
                # Clamp index if the list shrank after a purchase
                self._shop_selected_index = max(0, min(self._shop_selected_index, len(merchant.items_for_sale) - 1))
            else:
                result = merchant.sell_item(self.player, selected.name)
                self.message_log.add_message(result, (160, 240, 255))
                self._shop_selected_index = max(0, min(self._shop_selected_index, len(self.player.inventory.items) - 1))

        elif key in (pygame.K_ESCAPE, pygame.K_f):
            # Close the shop and return to the previous game state
            self.game_state = self._previous_game_state
            self._shop_menu_merchant = None
            self._shop_selected_index = 0
            self._shop_mode = "buy"

    def handle_innkeeper_menu_input(self, key):
        """
        Handles keyboard input while the Innkeeper's Rest/Buy Food/Leave
        overlay (GameState.INNKEEPER_MENU, see open_innkeeper_menu() and
        render_innkeeper_menu()) is open.

        Mirrors the numbered-choice convention CHEST_MENU already
        established (handle_input()'s "--- Locked Chest Menu ---" branch)
        rather than the arrow-key list navigation handle_shop_menu_input()
        uses -- with only two real actions plus "leave", a numbered choice
        is simpler for the player and for this method alike.

        [1] Rest for the Night -- resolves immediately (pay gold, restore
            HP/resources, advance world time) via Innkeeper.rest_player(),
            then closes the menu, exactly like CHEST_MENU's "pick the
            lock"/"smash it" choices resolve and close in one step.
        [2] Buy Food -- delegates to Innkeeper.offer_trade(), the same
            method Shopkeeper/Trader NPCs already use to open the shared
            shop overlay (see structures.py). offer_trade() stamps
            game._previous_game_state with whatever game_state is active
            when it's called -- since that's still INNKEEPER_MENU at this
            point, leaving the shop (ESC/F) returns here rather than to
            the overworld, so Buy Food -> Leave -> Rest is one continuous
            conversation with the innkeeper instead of three separate
            approaches.
        [3] / ESC / F -- leave, no purchase or rest.
        """
        innkeeper = self._innkeeper_menu_target
        if not innkeeper:
            self.game_state = self._innkeeper_menu_return_state or GameState.OVERWORLD
            return

        if key == pygame.K_1:
            result = innkeeper.rest_player(self.player, self)
            self.message_log.add_message(result, (255, 240, 160))
            self.game_state = self._innkeeper_menu_return_state or GameState.OVERWORLD
            self._innkeeper_menu_target = None

        elif key == pygame.K_2:
            innkeeper.offer_trade(self.player, self)  # Opens SHOP_MENU scoped to the innkeeper's food menu

        elif key in (pygame.K_3, pygame.K_ESCAPE, pygame.K_f):
            self.game_state = self._innkeeper_menu_return_state or GameState.OVERWORLD
            self._innkeeper_menu_target = None

    def handle_rest_menu_input(self, key):
        """Handle short rest / long rest choices from the rest menu."""
        if not self.player:
            self.game_state = self._previous_game_state or GameState.OVERWORLD
            self._rest_menu_target = None
            return

        if key == pygame.K_1:
            if self.player.rest(self, hours=1):
                self.next_turn()
            self.game_state = self._previous_game_state or GameState.OVERWORLD
            self._rest_menu_target = None
        elif key == pygame.K_2:
            if self.player.rest(self, hours=8):
                self.next_turn()
            self.game_state = self._previous_game_state or GameState.OVERWORLD
            self._rest_menu_target = None
        elif key in (pygame.K_3, pygame.K_ESCAPE, pygame.K_f):
            self.game_state = self._previous_game_state or GameState.OVERWORLD
            self._rest_menu_target = None

    def handle_text_input(self, input_text):        
        """Handles text input from the player."""
        input_text = input_text.lower()

        if self.game_state == GameState.TRADE:
            # Determine which merchant is active
            active_merchant = None
            if self._previous_game_state == GameState.TAVERN and self.merchant:
                active_merchant = self.merchant
            elif self._previous_game_state == GameState.DUNGEON and self.dungeon_merchant:
                active_merchant = self.dungeon_merchant
            elif self._previous_game_state == GameState.OVERWORLD and self.shopkeeper:
                active_merchant = self.shopkeeper
            elif self._previous_game_state == GameState.OVERWORLD and self.trader:
                active_merchant = self.trader

            if active_merchant:
                if input_text.startswith("buy "):
                    item_name = input_text[4:]
                    result = active_merchant.buy_item(self.player, item_name)
                    self.message_log.add_message(result, (255, 255, 255))
                elif input_text.startswith("sell "):
                    item_name = input_text[5:]
                    result = active_merchant.sell_item(self.player, item_name)
                    self.message_log.add_message(result, (255, 255, 255))
                else:
                    add_ambient_merchant_message = [
                        "The merchant squints at you: 'I only deal in proper trades. Say *buy <item>* or *sell <item>*.'",
                        "The trader frowns: 'That makes no sense to me, friend. Try *buy <item>* or *sell <item>* if you mean business.'",
                        "The merchant raises a brow: 'I’ll not play games. Speak plain: *buy <item>* or *sell <item>*.'",
                    ]
                    self.message_log.add_message(random.choice(add_ambient_merchant_message), (150, 150, 150))
            
            # After any trade attempt, revert state and hide input
            self.game_state = self._previous_game_state
            self.message_log.show_input_area = False
            self.message_log.current_input = ""
            return

        # Fallback for other states if needed
        self.message_log.show_input_area = False
        self.message_log.current_input = ""
        

    def execute_targeted_ability(self):
        """
        Confirms the target for the ability currently in use and executes its effect.
        """
        if not self.ability_in_use:
            self.message_log.add_message("Error: No ability in use for targeting.", (255, 0, 0))
            self._reset_targeting_state()
            return

        target_x = self.targeting_cursor_x
        target_y = self.targeting_cursor_y

        # Check range
        distance = self.player.distance_to(target_x, target_y)
        if distance > self.targeting_ability_range:
            self.message_log.add_message(f"{self.ability_in_use.name} target is out of range ({int(distance)} tiles away, max {self.targeting_ability_range}).", (255, 150, 0))
            return # Stay in targeting mode

        if not self.check_line_of_sight(self.player.x, self.player.y, target_x, target_y):
            self.message_log.add_message(f"Cannot target {self.ability_in_use.name}: No clear line of sight.", (255, 150, 0))
            return # Stay in targeting mode

        # Pass the confirmed target coordinates to the ability's execute_on_target method
        # This method will contain the specific logic for each ability.
        result = self.ability_in_use.execute_on_target(self.player, self, target_x, target_y)

        if result == "next_dart":
            # Magic Missile per-dart targeting: dart landed, more darts remain.
            # Stay in TARGETING so the player can aim the next dart.
            print("DEBUG: ability_in_use.execute_on_target returned 'next_dart'. Staying in TARGETING for next dart.")
            return  # Keep game_state as TARGETING, ability_in_use intact
        elif result:
            print("DEBUG: ability_in_use.execute_on_target returned True. Resetting state.")
            # If the ability successfully executed its effect, then reset targeting state.
            should_end_turn = not getattr(self.ability_in_use, "is_bonus_action", False)
            if not should_end_turn:
                self.player_bonus_action_used = True
            self._reset_targeting_state(end_turn=should_end_turn)
        else:
            print("DEBUG: ability_in_use.execute_on_target returned False. Staying in targeting mode.")
            # If execute_on_target returns False, it means the target was invalid for that ability
            # (e.g., Fire Bolt on empty tile, Misty Step on blocked tile). Stay in targeting mode.
            pass  # Message already handled by ability.execute_on_target

    def _reset_targeting_state(self, end_turn=True):
        """Cleans up targeting-related state vars and optionally ends the player's turn."""
        self.game_state = self._previous_game_state # Revert to previous game state (DUNGEON/TAVERN)
        self.ability_in_use = None # Clear the ability reference
        self.targeting_ability_range = 0
        self.targeting_cursor_x = 0 # Reset cursor position
        self.targeting_cursor_y = 0
        self.missile_darts_remaining = 0  # Clear Magic Missile dart counter
        self.player.current_action_state = None # <--- THIS IS THE CRITICAL FIX FOR MISTY STEP

        if end_turn:
            self.player_has_acted = True
            self.next_turn()


    def check_line_of_sight(self, x1, y1, x2, y2):
        """
        Bresenham's Line Algorithm for checking direct line of sight.
        Returns True if there are no sight-blocking tiles between (x1, y1) and (x2, y2) (exclusive of start, inclusive of end).
        """
        # If start or end is blocked, no LOS (unless it's the target itself)
        if self.game_map.tiles[y1][x1].block_sight:
            return False

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        current_x, current_y = x1, y1

        while True:
            # If we've reached the target, LOS is clear
            if current_x == x2 and current_y == y2:
                return True

            # Check if the current tile (excluding the start) blocks sight
            if (current_x != x1 or current_y != y1) and self.game_map.tiles[current_y][current_x].block_sight:
                return False

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                current_x += sx
            if e2 < dx:
                err += dx
                current_y += sy



    def get_interactable_item_at(self, x, y):
        """Checks if there's an interactable item (like a Potion or Chest) at the given coordinates."""
        for item in self.game_map.items_on_ground:
            # Check for any Item (including Potion, Weapon, Armor, Tools)
            # Exclude monsters, as they are not items
            if item.x == x and item.y == y and not isinstance(item, Monster):
                return item
        return None

    def get_chest_at(self, x, y):
        """Checks if there's a chest at the given coordinates."""
        for item in self.game_map.items_on_ground:
            if isinstance(item, Chest) and item.x == x and item.y == y:
                return item
        return None

    def get_altar_at(self, x, y):
        """Checks if there's an altar at the given coordinates."""
        for item in self.game_map.items_on_ground:
            if isinstance(item, Altar) and item.x == x and item.y == y:
                return item
        return None

    def _auto_equip_quick_bar(self, item):
        """After picking up a torch or potion, auto-place it in the matching quick bar slot if empty.
        
        Slot Q → Torch (OffHand with name 'Torch')
        Slot F → any Potion
        """
        is_torch  = isinstance(item, OffHand) and item.name == "Torch"
        is_potion = isinstance(item, Potion)

        if is_torch and self.player.quick_bar.get('q') is None:
            self.player.equip_to_quick_bar(item, 'q', self)
        elif is_potion and self.player.quick_bar.get('e') is None:
            self.player.equip_to_quick_bar(item, 'e', self)

    def handle_item_pickup(self):
        """Check for items at player's position and pick them up."""
        items_at_player_pos = [item for item in self.game_map.items_on_ground if item.x == self.player.x and item.y == self.player.y and not isinstance(item, Monster)]
        if items_at_player_pos:
            item_to_pick_up = items_at_player_pos[0]
            # Ensure it's not a Chest, as Chests are handled by their own 'open' method
            if isinstance(item_to_pick_up, Chest):
                return False # Let the chest opening logic handle this
            if isinstance(item_to_pick_up, Altar):
                return False # Altars are not picked up, they are interacted with in place
            if isinstance(item_to_pick_up, NPC):
                return False 
            
            if item_to_pick_up.on_pickup(self.player, self):
                # Remove the item from the ground after successful pickup
                self.game_map.items_on_ground.remove(item_to_pick_up)
                self.player.update_throw_knife_ability()
                self.player.update_spellbook_abilities()
                self.player.update_thieves_tools_ability()
                self.player.update_guard_ability()
                self.player.update_holy_symbol_abilities()
                # Auto-slot torches into Q and potions into E when those slots are free
                self._auto_equip_quick_bar(item_to_pick_up)
                self.update_fov() # Update FOV to reflect item removal
                return True
            else:
                return False
        else:
            # Removed "Nothing to pick up here." message here, as it will be handled by the broader interaction logic.
            return False
        

    def handle_inventory_input(self, key):
        """Handles input when in the inventory screen."""
        if pygame.K_1 <= key <= pygame.K_9:
            item_index = key - pygame.K_1
            if 0 <= item_index < len(self.player.inventory.items):
                self.selected_inventory_item = self.player.inventory.items[item_index]
                self.game_state = GameState.INVENTORY_MENU
                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
            else:
                self.message_log.add_message("No item at that slot.", (150, 150, 150))
        elif key == pygame.K_0:
            if len(self.player.inventory.items) == 10:
                self.selected_inventory_item = self.player.inventory.items[9]
                self.game_state = GameState.INVENTORY_MENU
                self.message_log.add_message(f"Selected: {self.selected_inventory_item.name}", self.selected_inventory_item.color)
            else:
                self.message_log.add_message("No item at that slot.", (150, 150, 150))
        elif key == pygame.K_ESCAPE or key == pygame.K_c:
            self.selected_inventory_item = None
            self.game_state = GameState.INVENTORY
            self.message_log.add_message("Selection cancelled.", (150, 150, 150))

    def handle_inventory_menu_input(self, key):
        """Handles input when an item is selected in the inventory menu (pop-up)."""
        if not self.selected_inventory_item:
            self.game_state = GameState.INVENTORY
            return

        action_taken_in_menu = False
        if key == pygame.K_u:
            # Check if the selected item is the Campfire Kit
            if isinstance(self.selected_inventory_item, CampfireKit):
                # Call the use method for the Campfire Kit
                if self.selected_inventory_item.use(self.player, self):
                    action_taken_in_menu = True
                    # Close the inventory menu
                    self.selected_inventory_item = None  # Reset selected item
                    # Optionally, you can log a message here if needed                         
            else:
                # Use the item normally
                if self.player.use_item(self.selected_inventory_item, self):
                    action_taken_in_menu = True
                else:
                    self.message_log.add_message(f"Cannot use {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_e:
            if self.player.equip_item(self.selected_inventory_item, self):
                action_taken_in_menu = True
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name}.", (255, 100, 100))
        elif key == pygame.K_d:
            self.player.inventory.remove_item(self.selected_inventory_item)
            self.player.update_throw_knife_ability()
            self.player.update_spellbook_abilities()
            self.player.update_thieves_tools_ability()
            self.player.update_guard_ability()
            self.player.update_holy_symbol_abilities()
            self.selected_inventory_item.x = self.player.x
            self.selected_inventory_item.y = self.player.y
            self.game_map.items_on_ground.append(self.selected_inventory_item)
            self.message_log.add_message(f"You drop the {self.selected_inventory_item.name}.", self.selected_inventory_item.color)
            action_taken_in_menu = True
        elif key == pygame.K_ESCAPE or key == pygame.K_c:
            self.message_log.add_message("Action cancelled.", (150, 150, 150))
            action_taken_in_menu = False
        elif key == pygame.K_q: # New key for quick bar slot 'q'
            if self.player.equip_to_quick_bar(self.selected_inventory_item, 'q', self):
                self.player.update_throw_knife_ability()
                self.player.update_spellbook_abilities()
                self.player.update_thieves_tools_ability()
                self.player.update_guard_ability()
                self.player.update_holy_symbol_abilities()
                action_taken_in_menu = False
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name} to Quick Bar (Q).", (255, 100, 100))
        elif key == pygame.K_e: # New key for quick bar slot 'e'
            if self.player.equip_to_quick_bar(self.selected_inventory_item, 'e', self):
                self.player.update_throw_knife_ability()
                self.player.update_spellbook_abilities()
                self.player.update_thieves_tools_ability()
                self.player.update_guard_ability()
                self.player.update_holy_symbol_abilities()
                action_taken_in_menu = False
            else:
                self.message_log.add_message(f"Cannot equip {self.selected_inventory_item.name} to Quick Bar (F).", (255, 100, 100))



        self.selected_inventory_item = None
        self.game_state = GameState.INVENTORY
        if action_taken_in_menu:
            self.player_has_acted = True
            self.next_turn()

    def get_target_at(self, x, y):
        for entity in self.entities:
            if entity != self.player and entity.alive:
                if hasattr(entity, 'occupies_tile'):
                    if entity.occupies_tile(x, y):
                        return entity
                elif entity.x == x and entity.y == y:
                    return entity
        return None

    def spawn_monster_group(self, room, primary_monster_class, game_map, possible_monsters):
        """
        Spawns a group of related monsters in a room.
        - Chooses the primary monster type
        - Spawns 1-4 monsters of compatible types
        - Ensures they don't overlap and are within walkable tiles
        """
        from entities.monster import MONSTER_GROUPS
        
        # Get the primary monster's name for group lookup
        primary_name = primary_monster_class.__name__
        compatible_types = MONSTER_GROUPS.get(primary_name, [primary_name])
        
        # Determine how many monsters to spawn (1-4)
        min_spawn = 1
        max_spawn = 4 if len(compatible_types) > 1 else 2  # Solo monsters spawn 1-2, packs 1-4
        num_to_spawn = random.randint(min_spawn, max_spawn)

        # Shared by every monster spawned into this room -- see
        # Monster.group_id/provoke(): attacking one PASSIVE/NEUTRAL member
        # of the pack alerts the rest of it at the same time.
        group_id = f"dungeon_pack:{uuid.uuid4().hex[:8]}"

        # Find all valid spawn positions within the room
        valid_positions = []
        for y in range(room.y1 + 1, room.y2):
            for x in range(room.x1 + 1, room.x2):
                if (0 <= x < game_map.width and 0 <= y < game_map.height and
                    game_map.is_walkable(x, y) and 
                    not is_water_tile(game_map.tiles[y][x]) and
                    not is_prison_cell_position(game_map, x, y) and
                    not any(e.x == x and e.y == y for e in self.entities)):
                    valid_positions.append((x, y))
        
        # Spawn monsters
        spawned_count = 0
        for i in range(num_to_spawn):
            if not valid_positions:
                break  # No more valid positions
            
            # Choose a compatible monster type
            monster_type_name = random.choice(compatible_types)
            
            # Find the class from possible_monsters list
            monster_class = None
            for cls in possible_monsters:
                if cls.__name__ == monster_type_name:
                    monster_class = cls
                    break
            
            if monster_class is None:
                continue  # Skip if class not found
            
            # Pick a random position from valid positions
            spawn_x, spawn_y = random.choice(valid_positions)
            valid_positions.remove((spawn_x, spawn_y))  # Remove to avoid overlap
            
            # Create and add the monster
            monster = monster_class(spawn_x, spawn_y)
            monster.group_id = group_id
            self.entities.append(monster)
            spawned_count += 1
        
        return spawned_count

    def get_adjacent_target(self):
        for dx, dy in [(0,1),(1,0),(0,-1),(-1,0),(-1,-1),(1,-1),(-1,1),(1,1)]:
            target = self.get_target_at(self.player.x + dx, self.player.y + dy)
            if target:
                return target
        return None

    def handle_player_action(self, dx, dy):
        new_x = self.player.x + dx
        new_y = self.player.y + dy

        # Add altar interaction check
        altar_at_pos = None
        for altar in self.game_map.altars:
            if altar.x == new_x and altar.y == new_y:
                altar_at_pos = altar
                break
            
        if altar_at_pos:
            interaction_result = altar_at_pos.interact(self.player, self)
            if interaction_result is True:
                self.player_has_acted = True
                return True
            elif interaction_result == 'already_used':
                pass
            else:
                return False

        if self.game_state == GameState.TAVERN:
            if (new_x, new_y) == self.door_position:
                self.entered_dungeon_from_overworld = False
                self.message_log.add_message("You enter the dark dungeon...", (100, 255, 100))
                self.generate_level(1)
                return True

            for npc in self.npcs:
                if npc.x == new_x and npc.y == new_y and npc.alive:
                    self.message_log.add_message(f"You can't move onto {npc.name}.", (255, 150, 0))
                    return False
            if self.game_map.is_walkable(new_x, new_y):
                self.player.x = new_x
                self.player.y = new_y
                self.update_fov()
                self.camera.target_x = float(self.player.x)
                self.camera.target_y = float(self.player.y)                
                return True
            self.message_log.add_message("You can't move there.", (255, 150, 0))
            return False

        elif self.game_state == GameState.DUNGEON or self.game_state == GameState.OVERWORLD:
            if self.game_state == GameState.OVERWORLD:
                if not (0 <= new_x < self.game_map.width and 0 <= new_y < self.game_map.height):
                    # Walked off the edge of this chunk — step into whichever neighboring
                    # chunk lies in that direction (generating it on first visit), entering
                    # from the matching opposite edge so the two chunks feel contiguous.
                    cx, cy = self.overworld_chunk_coord
                    if new_x < 0:
                        next_chunk = (cx - 1, cy)
                        spawn_pos = (OVERWORLD_CHUNK_WIDTH - 1, self.player.y)
                    elif new_x >= self.game_map.width:
                        next_chunk = (cx + 1, cy)
                        spawn_pos = (0, self.player.y)
                    elif new_y < 0:
                        next_chunk = (cx, cy - 1)
                        spawn_pos = (self.player.x, OVERWORLD_CHUNK_HEIGHT - 1)
                    else:
                        next_chunk = (cx, cy + 1)
                        spawn_pos = (self.player.x, 0)

                    self.message_log.add_message("You venture into uncharted territory...", (150, 200, 255))
                    self._start_chunk_transition(next_chunk, spawn_pos)
                    return True

                if (new_x, new_y) in self.dungeon_entrance_positions:
                    if self.companions:
                        # generate_level() below rebuilds self.entities from
                        # scratch with no idea escort companions exist, and
                        # companions have no attack stat and only 8 HP --
                        # they were never designed to survive dungeon
                        # combat. Rather than silently losing (or getting
                        # someone killed) mid-escort, refuse the descent
                        # and tell the player why, the same way the game
                        # already refuses other actions with a message
                        # instead of failing silently.
                        names = ", ".join(companion.name for companion in self.companions)
                        self.message_log.add_message(
                            f"You can't take {names} down there. Get them to an inn first.",
                            (255, 180, 120)
                        )
                        return True  # Consume the event -- stay put on the overworld

                    # Remember where the player stood so climbing back out drops them here.
                    self.overworld_player_pos = (self.player.x, self.player.y)
                    self.entered_dungeon_from_overworld = True
                    # Identify this dungeon by its entrance's global world
                    # position (see current_dungeon_id's docstring), not
                    # just "level 1" -- otherwise every entrance on the map
                    # would funnel into the same shared level 1 dungeon.
                    self.current_dungeon_id = chunk_local_to_world_position(
                        self.overworld_chunk_coord, (new_x, new_y)
                    )
                    self.message_log.add_message("You descend into the dungeon...", (100, 255, 100))
                    self.generate_level(1)
                    return True

            # Prevent out-of-bounds movement before accessing the tile grid.
            if not (0 <= new_x < self.game_map.width and 0 <= new_y < self.game_map.height):
                self.message_log.add_message("You can't move there.", (255, 150, 0))
                return False

            # --- Step 1: Identify potential targets at the new position ---
            target_at_new_pos = self.get_target_at(new_x, new_y)          
            
            # --- Step 2: Identify monsters adjacent to player *before* moving ---
            monsters_adjacent_before_move = []
            for entity in self.entities:
                # Ensure it's a monster, alive, and adjacent to the player
                if isinstance(entity, Monster) and entity.alive and self.player.is_adjacent_to(entity):
                    monsters_adjacent_before_move.append(entity)
            
            # --- Step 3: Handle interaction with an entity at the new position ---
            if target_at_new_pos:
                if isinstance(target_at_new_pos, Monster):
                    self.handle_player_attack(target_at_new_pos, self)  # Player attacks monster
                    return True  # Action taken
                elif isinstance(target_at_new_pos, DungeonHealer):
                    target_at_new_pos.offer_rest(self.player, self)
                    return True
                elif isinstance(target_at_new_pos, SummonedEntity) and target_at_new_pos.owner == self.player:
                    # Swap positions with player's own summoned entity
                    target_at_new_pos.x, self.player.x = self.player.x, target_at_new_pos.x
                    target_at_new_pos.y, self.player.y = self.player.y, target_at_new_pos.y
                    self.message_log.add_message(f"You swap places with the {target_at_new_pos.name}!", (100, 255, 200))
                    self.update_fov()
                    self.camera.target_x = float(self.player.x)
                    self.camera.target_y = float(self.player.y)
                    self.player_has_acted = True
                    return True
                else:
                    self.message_log.add_message(f"You can't attack {target_at_new_pos.name}.", (255, 150, 0))
                    return False

            # --- Step 4: Handle movement to an empty, walkable tile or TRAP ---
            if self.game_map.is_walkable(new_x, new_y):
                # Prevent moving into any tile occupied by a blocking entity (supports multi-tile)
                for entity in self.entities:
                    if entity is self.player or not getattr(entity, 'alive', True) or not getattr(entity, 'blocks_movement', False):
                        continue
                    if hasattr(entity, 'occupies_tile'):
                        if entity.occupies_tile(new_x, new_y):
                            # Check if it's a summoned entity - if so, swap positions
                            if isinstance(entity, SummonedEntity):
                                entity.x, self.player.x = self.player.x, entity.x
                                entity.y, self.player.y = self.player.y, entity.y
                                self.message_log.add_message(f"You swap places with the {entity.name}!", (100, 255, 200))
                                self.player_has_acted = True
                                self.update_fov()
                                self.camera.target_x = float(self.player.x)
                                self.camera.target_y = float(self.player.y)
                                return True
                            else:
                                self.message_log.add_message(f"You can't move onto {entity.name}.", (255, 150, 0))
                                return False
                    else:
                        if getattr(entity, 'x', None) == new_x and getattr(entity, 'y', None) == new_y:
                            # Check if it's a summoned entity - if so, swap positions
                            if isinstance(entity, SummonedEntity):
                                entity.x, self.player.x = self.player.x, entity.x
                                entity.y, self.player.y = self.player.y, entity.y
                                self.message_log.add_message(f"You swap places with the {entity.name}!", (100, 255, 200))
                                self.player_has_acted = True
                                self.update_fov()
                                self.camera.target_x = float(self.player.x)
                                self.camera.target_y = float(self.player.y)
                                return True
                            else:
                                self.message_log.add_message(f"You can't move onto {entity.name}.", (255, 150, 0))
                                return False
                # --- NEW: Trap Check BEFORE Movement ---
                target_tile_obj = self.game_map.tiles[new_y][new_x]
                if isinstance(target_tile_obj, TrapTile) and target_tile_obj.trap_instance.is_hidden:
                    # Attempt passive perception check
                    passive_perception_score = 10 + self.player.get_ability_modifier(self.player.wisdom)
                    if "perception" in self.player.skill_proficiencies:
                        passive_perception_score += self.player.proficiency_bonus
                    
                    if passive_perception_score >= target_tile_obj.trap_instance.detection_dc:
                        target_tile_obj.trap_instance.reveal(self, new_x, new_y)
                        self.message_log.add_message(f"Perception Check: You notice a hidden {target_tile_obj.trap_instance.name}!", (0, 255, 255))
                        return True # Action taken (noticed trap)
                    else:
                        self.message_log.add_message(f"Perception Check: You fail to notice anything unusual.", (150, 150, 150))
                        # Fall through to movement logic below, which will trigger the trap.
               
                original_player_x, original_player_y = self.player.x, self.player.y
                self.player.x = new_x
                self.player.y = new_y
                
                self.camera.target_x = float(self.player.x)
                self.camera.target_y = float(self.player.y)
                # --- NEW: Trigger Trap AFTER Movement (if not noticed/disarmed) ---
                if isinstance(target_tile_obj, TrapTile) and not target_tile_obj.trap_instance.is_disarmed and not target_tile_obj.trap_instance.is_triggered:
                    target_tile_obj.trap_instance.trigger(self.player, self, new_x, new_y)
                    return True # Action taken (triggered trap)

                # --- NEW: Random overworld encounter ---
                # A small per-step chance to interrupt travel with a narrative
                # choice menu instead of silently spawning a monster on the tile.
                # A staged scenario's queued next beat (see _resolve_world_
                # encounter_advance()) gets first say -- it's checked before
                # rolling a brand new, unrelated encounter.
                if self.game_state == GameState.OVERWORLD and self._maybe_advance_world_encounter_stage():
                    return True  # Next beat's menu now showing

                if self.game_state == GameState.OVERWORLD and self._maybe_trigger_world_encounter():
                    return True  # Menu now showing; resolve the encounter before anything else

                # --- Opportunity Attack Check ---
                # Iterate through monsters that were adjacent before the move.
                # Skip anything not currently AGGRESSIVE (see Disposition in
                # entities/monster.py): a PASSIVE/NEUTRAL monster -- e.g. a
                # Centaur_Crossing.json band spawned via WORLD_ENCOUNTER_
                # DISPOSITIONS -- does nothing at all until the player
                # actually attacks one of its members. Monster.provoke()
                # flips the attacker's disposition to AGGRESSIVE (and, via
                # _alert_group(), every other living monster sharing its
                # group_id) the instant that happens, so the very next time
                # the player steps away from any of them, this check sees
                # AGGRESSIVE and the opportunity attack fires as normal.
                for monster in monsters_adjacent_before_move:
                    if monster.disposition != Disposition.AGGRESSIVE:
                        continue

                    # Check if the monster is still adjacent to the player's *new* position
                    is_still_adjacent_to_monster = (abs(self.player.x - monster.x) <= 1 and abs(self.player.y - monster.y) <= 1)
                    
                    if self.player.alive and not is_still_adjacent_to_monster:
                        oa_msgs = [
                            f"The {monster.name} lashes out as you flee!",
                            f"{monster.name}'s reflexes are quick — an opportunity strike!",
                            f"A sudden slash from the {monster.name} catches you off guard!",
                            f"As you turn away, the {monster.name} seizes its chance to attack!",
                            f"The {monster.name} strikes swiftly at your exposed flank!"
                        ]
                        self.message_log.add_message(random.choice(oa_msgs), (255, 100, 0))
                        
                        monster.attack(self.player, self)  # Monster attacks the player
                        
                        # Important: If the player dies from an OA, the game state should reflect that.
                        if not self.player.alive:
                            self.handle_game_over()
                            return  # Player died, action taken, end turn.
                    
                
                self.update_fov()
                self.minimap_needs_redraw = True # Player moved, minimap needs redraw
                stairs_dir = self.check_stairs_interaction()
                if stairs_dir:
                    self.handle_level_transition(stairs_dir)
                return True  # Action taken

            # --- Step 5: Handle interaction with special tiles (MimicTile, Destructible) ---
            target_tile = self.game_map.tiles[new_y][new_x]
            if isinstance(target_tile, MimicTile):
                mimic_entity = target_tile.mimic_entity
                if mimic_entity.disguised or mimic_entity not in self.entities:
                    mimic_entity.reveal(self)
                    return True
                else:
                    self.message_log.add_message(f"The {mimic_entity.name} is already revealed.", (150, 150, 150))
                    return False
            elif target_tile.destructible:
                self.destroy_tile(new_x, new_y)
                return True
            else:
                self.message_log.add_message("You can't move there.", (255, 150, 0))
                return False
        return False


    def destroy_tile(self, x, y):
        """
        Attempts to destroy a destructible tile at (x, y) with a skill check.
        """
        target_tile = self.game_map.tiles[y][x]
        if not target_tile.destructible:
            self.message_log.add_message("That cannot be destroyed.", (150, 150, 150))
            return False
        destruction_dc = 12 
        
        str_modifier = self.player.get_ability_modifier(self.player.strength)
        athletics_bonus = str_modifier + self.player.proficiency_bonus
        d20_roll = random.randint(1, 20)
        skill_check_total = d20_roll + athletics_bonus
        self.message_log.add_message(
            f"Athletics Check: Rolled {d20_roll} + {athletics_bonus} = {skill_check_total} against DC {destruction_dc}.",
            (200, 200, 255)
        )
        
        if skill_check_total >= destruction_dc:
            self.message_log.add_message(f"You successfully smash the {target_tile.name}!", (0, 255, 0))
            if self.game_state == GameState.OVERWORLD:
                self.game_map.tiles[y][x] = ground
            elif self.game_state == GameState.DUNGEON:
                self.game_map.tiles[y][x] = floor
            self.minimap_needs_redraw = True # Map changed, redraw minimap
            
            # --- NEW: 10% chance to drop a Lesser Healing Potion ---
            if target_tile.name in ["Crate", "Barrel"]: # Check if it was a crate or barrel 
                if random.random() < 0.75:
                    new_junk = wood_plank.__class__(
                        name=wood_plank.name,
                        char=wood_plank.char,
                        color=wood_plank.color,
                        description=wood_plank.description
                    )
                    new_junk.x = x
                    new_junk.y = y
                    self.game_map.items_on_ground.append(new_junk)
                elif random.random() < 0.21:
                    new_potion = lesser_healing_potion.__class__(
                        name=lesser_healing_potion.name,
                        char=lesser_healing_potion.char,
                        color=lesser_healing_potion.color,
                        effect_type=lesser_healing_potion.effect_type,
                        effect_value=lesser_healing_potion.effect_value,
                        description=lesser_healing_potion.description,
                        price=lesser_healing_potion.price
                    )
                    new_potion.x = x
                    new_potion.y = y
                    self.game_map.items_on_ground.append(new_potion)
                    self.message_log.add_message(f"A {new_potion.name} drops from the {target_tile.name}!", new_potion.color)
                elif random.random() < 0.3:
                    new_torch = torch.__class__(
                        name=torch.name,
                        char=torch.char,
                        color=torch.color,
                        description=torch.description,
                        price=torch.price
                    )
                    new_torch.x = x
                    new_torch.y = y
                    self.game_map.items_on_ground.append(new_torch)
                    self.message_log.add_message(f"A {new_torch.name} drops from the {target_tile.name}!", new_torch.color)
                elif random.random() < 0.2:
                    new_food = meat.__class__(
                        name=meat.name,
                        char=meat.char,
                        color=meat.color,
                        description=meat.description,
                        healing_value=meat.healing_value,
                        price=meat.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.35:
                    new_food = green_apple.__class__(
                        name=green_apple.name,
                        char=green_apple.char,
                        color=green_apple.color,
                        description=green_apple.description,
                        healing_value=green_apple.healing_value,
                        price=green_apple.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color)
                elif random.random() < 0.27:
                    new_food = fromage.__class__(
                        name=fromage.name,
                        char=fromage.char,
                        color=fromage.color,
                        description=fromage.description,
                        healing_value=fromage.healing_value,
                        price=fromage.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.3:
                    new_food = bread.__class__(
                        name=bread.name,
                        char=bread.char,
                        color=bread.color,
                        description=bread.description,
                        healing_value=bread.healing_value,
                        price=bread.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
                elif random.random() < 0.5:
                    new_food = mushroom.__class__(
                        name=mushroom.name,
                        char=mushroom.char,
                        color=mushroom.color,
                        description=mushroom.description,
                        healing_value=mushroom.healing_value,
                        price=mushroom.price
                    )
                    new_food.x = x
                    new_food.y = y
                    self.game_map.items_on_ground.append(new_food)
                    self.message_log.add_message(f"A {new_food.name} drops from the {target_tile.name}!", new_food.color) 
            # --- END NEW DROP LOGIC ---

            return True
        else:
            self.message_log.add_message(f"You fail to smash the {target_tile.name}. It's tougher than it looks!", (255, 100, 100))      
            return False

    

    def handle_player_attack(self, target, game_instance, advantage=False, disadvantage=False):
        if not target.alive:
            return
        
        # Check if ANY tile of the target is in the player's FOV (supports multi-tile entities)
        visible_ok = False
        allowed_vis = ['player', 'torch', 'darkvision']
        footprint_size = getattr(target, 'footprint_size', 1)
        if footprint_size > 1:
            for oy in range(footprint_size):
                for ox in range(footprint_size):
                    tx, ty = target.x + ox, target.y + oy
                    if self.fov.get_visibility_type(tx, ty) in allowed_vis:
                        visible_ok = True
                        break
                if visible_ok:
                    break
        else:
            visible_ok = self.fov.get_visibility_type(target.x, target.y) in allowed_vis

        if not visible_ok:
            self.message_log.add_message(f"You cannot attack {target.name} because it is out of sight!", (255, 0, 0))
            return
    
        # Determine the actual d20 roll based on advantage/disadvantage
        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20) # Always roll a second for simplicity
        
        final_d20_roll = roll1
        roll_message_part = f"a d20: [{roll1}]"
        
        # Use final_d20_roll for the attack calculation
        attack_modifier = self.player.attack_bonus
    
        # --- Altar Blessings and Curses ---
        blessing_of_strength = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, BlessingOfStrength):
                blessing_of_strength = effect
                break

        curse_of_weakness = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, CurseOfWeakness):
                curse_of_weakness = effect
                break


        # --- Check for PowerAttackBuff ---
        power_attack_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, PowerAttackBuff):
                power_attack_buff = effect
                break
            
        if power_attack_buff:
            attack_modifier += power_attack_buff.attack_modifier # Apply accuracy penalty
            self.message_log.add_message(f"Power Attack: -{abs(power_attack_buff.attack_modifier)} to hit.", (255, 165, 0))



        # --- Check for DivineStrikeBuff ---
        divine_strike_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, DivineStrikeBuff):
                divine_strike_buff = effect
                break

        if divine_strike_buff:
            attack_modifier += divine_strike_buff.base_attack_bonus_modifier # Apply attack bonus
            self.message_log.add_message(f"Divine Strike: +{divine_strike_buff.base_attack_bonus_modifier} to hit.", (255, 255, 0))

        # --- Check for PreciseStrikeBuff ---
        precise_strike_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, PreciseStrikeBuff):
                precise_strike_buff = effect
                break
            
        if precise_strike_buff:
            attack_modifier += precise_strike_buff.attack_bonus_modifier # Apply attack bonus
            self.message_log.add_message(f"Precise Strike: +{precise_strike_buff.attack_bonus_modifier} to hit.", (0, 255, 255))

        prepared_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, Prepared):
                prepared_buff = effect
                break

        if prepared_buff:
            self.message_log.add_message(f"Prepared: +{prepared_buff.attack_power_modifier} attack power.", (0, 255, 255))

        applied_toxins_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, AppliedToxins):
                applied_toxins_buff = effect
                break

        # --- Check for Hidden Status Effect ---
        hidden_buff = None
        for effect in self.player.active_status_effects:
            if isinstance(effect, Hidden):
                hidden_buff = effect
                break

        if hidden_buff:
            self.message_log.add_message("Your attack from hiding deals extra damage!", (255, 215, 0))         

            sneak_dice_count = 0

            if self.player.level >= 1:
                # Sneak Attack always starts at 1d6
                sneak_dice_count = 1 + ((self.player.level - 1) // 2)
                # Cap at 10d6 (level 19+)
                sneak_dice_count = min(sneak_dice_count, 10)
              
            advantage = True       


        if advantage and disadvantage: # They cancel each other out
            self.message_log.add_message("Advantage and Disadvantage cancel out.", (150, 150, 150))
            # final_d20_roll remains roll1
        elif advantage:
            final_d20_roll = max(roll1, roll2)
            roll_message_part = f"2d20 (Advantage): {roll1}, {roll2} -> {final_d20_roll}"
            self.message_log.add_message("You roll with Advantage!", (100, 255, 100))
        elif disadvantage:
            final_d20_roll = min(roll1, roll2)
            roll_message_part = f"2d20 (Disadvantage): {roll1}, {roll2} -> {final_d20_roll}"
            self.message_log.add_message("You roll with Disadvantage!", (255, 100, 100))

        attack_roll_total = final_d20_roll + attack_modifier # Use final_d20_roll here
        self.message_log.add_message(
            f"You roll {roll_message_part} + [{attack_modifier}] (Attack Bonus) = {attack_roll_total} vs AC {target.armor_class}",
            (200, 200, 255)
        )

        # Critical hit/fumble based on the final_d20_roll
        is_critical_hit = (final_d20_roll == 20)
        is_critical_fumble = (final_d20_roll == 1)
    
        if is_critical_hit:
            self.message_log.add_message(
                "CRITICAL HIT! You strike a vital spot!",
                (255, 255, 0)
            )
            hit_successful = True
        elif is_critical_fumble:
            self.message_log.add_message(
                "CRITICAL FUMBLE! You trip over your own feet!",
                (255, 0, 0)
            )
            hit_successful = False
        elif attack_roll_total >= target.armor_class:
            hit_successful = True
        else:
            hit_successful = False
    
        if hit_successful:
            hit_messages = [
                f"Your attack {attack_roll_total} hits the {target.name} (AC {target.armor_class})!",
                f"You connect with the {target.name} (AC {target.armor_class})!",
                f"A solid blow lands on the {target.name} (AC {target.armor_class})!",
                f"The {target.name} recoils from your strike!"
            ]
            self.message_log.add_message(random.choice(hit_messages), (100, 255, 100))
    
            hit_text = FloatingText(target.x, target.y, "HIT!", (255, 255, 0), y_speed=0.4)
            self.floating_texts.append(hit_text)
    
    
            # Parse weapon damage dice (e.g., "1d6")
            dice_count_str, die_type_str = self.player.equipped_weapon.damage_dice.split('d')
            num_dice = int(dice_count_str)
            die_type = int(die_type_str)
    
            damage_rolls = []
            total_dice_rolled = num_dice
    
            if is_critical_hit:
                total_dice_rolled *= 2 # Double the number of dice rolled for critical hits
    
            for _ in range(total_dice_rolled):
                damage_rolls.append(random.randint(1, die_type))
    
            damage_dice_rolls_sum = sum(damage_rolls)
    
            # Construct the message part for dice rolls
            damage_message_dice_part = f"{total_dice_rolled}d{die_type} [{' + '.join(map(str, damage_rolls))}]"
    
            damage_modifier = self.player.attack_power
    
            if blessing_of_strength:
                damage_modifier += blessing_of_strength.damage_modifier
                self.message_log.add_message(f"Blessing of Strength: +{blessing_of_strength.damage_modifier} damage.", (0, 255, 255))

            if curse_of_weakness:
                damage_modifier += curse_of_weakness.damage_modifier # Note: This is negative
                self.message_log.add_message(f"Curse of Weakness: {curse_of_weakness.damage_modifier} damage.", (255, 0, 255))

            if power_attack_buff:
                damage_modifier += power_attack_buff.damage_modifier # Apply flat damage bonus
                self.message_log.add_message(f"Power Attack: +{power_attack_buff.damage_modifier} damage.", (255, 165, 0))
                if getattr(power_attack_buff, "extra_damage_dice", 0) > 0:
                    extra_dice_count = power_attack_buff.extra_damage_dice * (2 if is_critical_hit else 1)
                    extra_rolls = [random.randint(1, die_type) for _ in range(extra_dice_count)]
                    extra_sum = sum(extra_rolls)
                    damage_dice_rolls_sum += extra_sum
                    damage_message_dice_part += f" + {extra_dice_count}d{die_type} [{' + '.join(map(str, extra_rolls))}] (Power Attack)"
                    self.message_log.add_message(f"Power Attack adds {extra_dice_count}d{die_type} damage.", (255, 165, 0))
                # The buff should be consumed after one attack
                self.player.active_status_effects.remove(power_attack_buff) # Remove the buff
                self.message_log.add_message(f"Power Attack buff consumed.", (150, 150, 150))

            if divine_strike_buff:
                damage_modifier += divine_strike_buff.damage_modifier # Apply flat damage bonus
                self.message_log.add_message(f"Divine Strike: +{divine_strike_buff.damage_modifier} damage.", (255, 255, 0))
                if getattr(divine_strike_buff, "extra_damage_dice", 0) > 0:
                    extra_dice_count = divine_strike_buff.extra_damage_dice * (2 if is_critical_hit else 1)
                    extra_rolls = [random.randint(1, die_type) for _ in range(extra_dice_count)]
                    extra_sum = sum(extra_rolls)
                    damage_dice_rolls_sum += extra_sum
                    damage_message_dice_part += f" + {extra_dice_count}d{die_type} [{' + '.join(map(str, extra_rolls))}] (Divine Strike)"
                    self.message_log.add_message(f"Divine Strike adds {extra_dice_count}d{die_type} damage.", (255, 255, 0))
                # The buff should be consumed after one attack
                self.player.active_status_effects.remove(divine_strike_buff) # Remove the buff
                self.message_log.add_message(f"Divine Strike buff consumed.", (150, 150, 150))

            if prepared_buff:
                damage_modifier += prepared_buff.attack_power_modifier

            if applied_toxins_buff and hit_successful:
                poison_dice_count = applied_toxins_buff.poison_damage_dice * (2 if is_critical_hit else 1)
                poison_rolls = [random.randint(1, applied_toxins_buff.poison_die_type) for _ in range(poison_dice_count)]
                poison_sum = sum(poison_rolls)
                damage_dice_rolls_sum += poison_sum
                damage_message_dice_part += f" + {poison_dice_count}d{applied_toxins_buff.poison_die_type} [{' + '.join(map(str, poison_rolls))}] (Applied Toxins)"
                self.message_log.add_message(f"Applied Toxins deals +{poison_sum} poison damage.", (0, 255, 100))

            if hidden_buff:
                sneak_attack_rolls = []
                
                for _ in range(sneak_dice_count):
                    sneak_attack_rolls.append(random.randint(1, 6))
                sneak_attack_sum = sum(sneak_attack_rolls)
                damage_dice_rolls_sum += sneak_attack_sum
                damage_message_dice_part += f" + {sneak_dice_count}d6 [{' + '.join(map(str, sneak_attack_rolls))}] (Sneak Attack)"

                self.player.active_status_effects.remove(hidden_buff) # Remove the buff after one attack
                self.message_log.add_message(f"You are no longer hidden.", (150, 150, 150))


            damage_total = max(1, damage_dice_rolls_sum + damage_modifier)
    
            self.message_log.add_message(
                f"You roll {damage_message_dice_part} + [{damage_modifier}] (Attack Power) = {damage_total} damage!",
                (255, 200, 100)
            )
    
            damage_dealt = target.take_damage(damage_total, game_instance, damage_type='physical') 
    
            self.message_log.add_message(
                f"You hit the {target.name} for {damage_dealt} damage!",
                (255, 100, 100)
            )
    
            damage_text = FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0), y_speed=0.6)
            self.floating_texts.append(damage_text)
    
    
            if not target.alive:
                xp_gained = target.die(game_instance, killer=self.player)
                self.player.gain_xp(xp_gained, game_instance)  # Use 'self' (player) here
                self.message_log.add_message(f"You gain {xp_gained} XP!", (100, 255, 100))  # Log the XP gained
                self._notify_monster_killed(target, killer=self.player)
                if target.name == 'Arasta' and self.current_level == 20:
                    self.handle_victory()
                    return
                if random.random() < 0.7:
                    self.add_ambient_combat_message()
            else:
                self.message_log.add_message(
                    f"{target.name} has {target.hp}/{target.max_hp} HP",
                    (255, 255, 0)
                )

        # Reveal if hidden
        if self.player.hidden_turns > 0:
            self.player.hidden_turns = 0
            hidden_buff = next((e for e in self.player.active_status_effects if isinstance(e, Hidden)), None)
            if hidden_buff:
                self.player.active_status_effects.remove(hidden_buff)
                hidden_buff.on_end(self.player, self)

        if not hit_successful:
            miss_messages = [
                f"Your attack {attack_roll_total} misses the {target.name} (AC {target.armor_class})!",
                f"You swing wildly and miss the {target.name} (AC {target.armor_class})!",
                f"The {target.name} deftly dodges your attack!",
                f"Your weapon glances harmlessly off the {target.name} (AC {target.armor_class})!"
            ]
            self.message_log.add_message(random.choice(miss_messages), (200, 200, 200))
    
            miss_text = FloatingText(target.x, target.y, "MISS!", (150, 150, 150))
            self.floating_texts.append(miss_text)
    

    def add_ambient_combat_message(self):
        common_msgs = [
            "The smell of blood fills the air...",
            "Silence returns to the dungeon...",
            "Your weapon drips with monster blood...",
            "A death cry echoes, then fades into silence...",
            "The ground is slick with gore and ichor...",
            "Your heartbeat pounds in your ears, then slows...",
            "The dungeon grows eerily quiet, as if holding its breath...",
            "A faint metallic tang of blood lingers on your tongue...",
            "Your boots leave red stains across the stone floor...",
            "The corpse twitches once before lying still...",
            "Shadows seem to crowd closer after the violence...",
            "A rat scurries out, drawn to the fresh kill...",
            "The clash of steel still rings faintly in your mind...",
            "You wipe the blade clean, though the stain remains..."
        ]

        rare_msgs = [
            "Somewhere deeper, a guttural roar answers the bloodshed...",
            "The clash of battle carries far — something stirs in the dark...",
            "Your victory echoes like a beacon — but not all ears are friendly...",
            "A distant screech pierces the silence, hungry and aware...",
            "The dungeon shifts uneasily, as if the stone itself resents your triumph..."
        ]

        # 90% chance for common aftermath, 10% chance for rare narrative escalation
        if random.random() < 0.1:
            msg = random.choice(rare_msgs)
            color = (200, 100, 100)  # darker red for danger
        else:
            msg = random.choice(common_msgs)
            color = (170, 170, 170)  # neutral gray

        self.message_log.add_message(msg, color)

    def update(self, dt):
        self.clock.tick(60)  # Limit to 60 FPS
        self.fps = self.clock.get_fps()  # Get the current FPS
        self.stories.update(dt)

        # self._torch_flicker_frame += 1
        # if self._torch_flicker_frame % 12 == 0:
        #     import random as _r
        #     # ember / candlelit tones
        #     r = 235 + _r.randint(-16, 10)
        #     g = 168 + _r.randint(-20, 8)
        #     b = 92  + _r.randint(-12, 6)

        #     # subtle brightness fluctuation
        #     a = 235 + _r.randint(-18, 0)

        #     self._torch_flicker_tint = (
        #         max(80, min(255, r)),
        #         max(80, min(255, g)),
        #         max(80, min(255, b)),
        #         max(180, min(255, a)),
        #     )     

        self.floating_texts = [text for text in self.floating_texts if text.update()]

        # Overworld chunk transition — advance the fade and, once fully black,
        # generate/restore the new chunk before fading back in.
        if self.chunk_transition_phase == "out":
            self.chunk_transition_alpha = min(255, self.chunk_transition_alpha + self.chunk_transition_speed)
            if self.chunk_transition_alpha >= 255:
                next_chunk, spawn_pos = self.pending_chunk_transition
                self.pending_chunk_transition = None
                self.generate_overworld_map(chunk_coord=next_chunk, spawn_pos=spawn_pos)
                self.chunk_transition_phase = "in"
        elif self.chunk_transition_phase == "in":
            self.chunk_transition_alpha = max(0, self.chunk_transition_alpha - self.chunk_transition_speed)
            if self.chunk_transition_alpha <= 0:
                self.chunk_transition_phase = None

        # NEW: If player is dead and game is not yet in GAME_OVER state, handle game over
        if self.player and not self.player.alive and self.game_state != GameState.GAME_OVER:
            self.handle_game_over()
            return # Stop further updates if game over is triggered


        if self.game_state == GameState.CHARACTER_CREATION:
            if self.fade_in_alpha > 0:
                self.fade_in_alpha -= self.fade_in_speed
                if self.fade_in_alpha < 0:
                    self.fade_in_alpha = 0
        if self.game_state == GameState.CLASS_SELECTION:
            if self.fade_in_alpha > 0:
                self.fade_in_alpha -= self.fade_in_speed
                if self.fade_in_alpha < 0:
                    self.fade_in_alpha = 0                                    

        # NEW: If game is already in GAME_OVER state, simply return
        if self.game_state == GameState.GAME_OVER:
            if self.death_screen_animation_phase == 0:
                self.death_screen_alpha += self.death_screen_animation_speed
                if self.death_screen_alpha >= 255:
                    self.death_screen_alpha = 255
                    self.death_screen_animation_phase = 1
            elif self.death_screen_animation_phase == 1:
                self.death_screen_bg_alpha += self.death_screen_animation_speed
                if self.death_screen_bg_alpha >= 120:  # Max alpha for background overlay
                    self.death_screen_bg_alpha = 120
                    self.death_screen_animation_phase = 2
            elif self.death_screen_animation_phase == 2:
                self.death_screen_subtext_alpha += self.death_screen_animation_speed
                if self.death_screen_subtext_alpha >= 255:
                    self.death_screen_subtext_alpha = 255
                    self.death_screen_animation_phase = 3
            elif self.death_screen_animation_phase == 4: # Fade-out initiated by 'R' press
                self.fade_out_alpha += self.fade_out_speed
                if self.fade_out_alpha >= 255:
                    self.fade_out_alpha = 255
                    # Fade-out complete, now transition to character creation
                    self.entities.clear()
                    self.player = None
                    self._game_over_displayed = False
                    self.death_screen_animation_phase = 0 # Reset for next death
                    self.death_screen_alpha = 0 # Reset for next death
                    self.death_screen_bg_alpha = 0 # Reset for next death
                    self.death_screen_subtext_alpha = 0 # Reset for next death
                    
                    self.game_state = GameState.CHARACTER_CREATION
                    self.start_character_creation()
                    
                    self.fade_in_alpha = 255
                    self.message_log.add_message("Welcome, new adventurer!", (0, 255, 0))                    
            return

        if not self.player: # If player hasn't been created yet (e.g., in character creation)
            return # Do nothing else in update
        

        # --- NEW: Batch Monster Turn Processing ---
        if self.game_state == GameState.DUNGEON or self.game_state == GameState.OVERWORLD and self.player.alive:
            # Snapshot the player's owned, blocking entities (summons, escorts,
            # ...) once for this whole batch of monster turns, instead of every
            # monster re-scanning the full self.entities list from scratch (see
            # Monster.take_turn()'s target-priority check). This list only
            # changes when a summon spawns or dies -- rare compared to how many
            # monster turns get processed per player action -- and Monster.
            # take_turn() still re-checks .alive on each candidate itself, so a
            # summon dying mid-batch (to an earlier monster's attack) can't
            # produce a stale/invalid target, only briefly stale *ordering*.
            self._refresh_owned_blocking_entities_cache()
            # Loop to process turns until it's the player's turn or no more entities
            while True:
                self.cleanup_entities() # Always clean up before getting current entity
                if not self.turn_order: # If no entities left (e.g., all monsters died)
                    break # Exit turn processing loop
                current_entity = self.get_current_entity()
                if current_entity == self.player:
                    # It's the player's turn.
                    if not self.player_has_acted:
                        # Player's turn, waiting for input. Break the loop.
                        break
                    else:
                        # Player has acted, advance turn to next entity.
                        self.player_has_acted = False # Reset for player's next turn
                        self.next_turn() # This will call cleanup_entities again and advance index
                        # After next_turn, it might be a monster's turn or player's again.
                        # Continue the while loop to process the next entity.
                        continue # Go back to the start of the while loop
                elif current_entity.alive and hasattr(current_entity, 'take_turn'):
                    # Process entity's turn (Monster, SummonedEntity, NPC, etc.)
                    if isinstance(current_entity, Monster) and hasattr(current_entity, 'is_active'):
                        if not current_entity.is_active:
                            # Skip inactive monsters
                            self.next_turn()
                            continue
                    # Call take_turn for any entity that has it
                    current_entity.take_turn(self.player, self.game_map, self)

                    if not self.player.alive:
                        # That attack (or its death-save fallout -- see
                        # Player.take_damage()/_fail_death_saves()) just
                        # killed the player outright. Stop simulating the
                        # remaining monsters' turns against a corpse and
                        # let the top-of-update() game-over check handle
                        # the transition to GAME_OVER on the next frame.
                        break

                    # Entity has acted, advance turn.
                    self.next_turn() # This will call cleanup_entities again and advance index
                    # Continue the while loop to process the next entity.
                    continue # Go back to the start of the while loop
                else:
                    # If current_entity is not player, not a monster, or dead (should be caught by cleanup),
                    # just advance turn. This is a safeguard.
                    self.next_turn()
                    continue # Go back to the start of the while loop

            # The batch loop above broke because it's now the player's turn.
            # If they're unconscious at 0 hp (Player.is_dying), hand off to
            # the death-save menu instead of waiting on movement/action
            # input -- rolling the save, not moving, is what a downed
            # player's turn consists of.
            if self.player.is_dying and not self.player_has_acted and self.get_current_entity() == self.player:
                self._enter_death_save_menu()

        self.floating_texts = [text for text in self.floating_texts if text.update()]        
        
        # This condition was already here, but now it's after the player check
        if self.game_state == GameState.TAVERN or \
           self.game_state == GameState.INVENTORY or \
           self.game_state == GameState.INVENTORY_MENU or \
           self.game_state == GameState.CHARACTER_MENU or \
           self.game_state == GameState.TARGETING or \
           self.game_state == GameState.CHARACTER_CREATION or \
           self.game_state == GameState.CLASS_SELECTION: # Added CLASS_SELECTION
            return # <--- Keep this line as is
        
        current = self.get_current_entity()
        
        # --- NEW: Explicitly reset player_has_acted at the start of player's turn ---
        if current == self.player and self.player_has_acted:
            self.player_has_acted = False
            self.message_log.add_message("Your turn begins!", (100, 255, 100))
            self.update_fov()
        elif current == self.player and not self.player_has_acted:
            # Player's turn, waiting for input. Do nothing here.
            pass
        elif current and current != self.player and current.alive: # <--- THIS IS THE MONSTER'S TURN
            # Only allow entities within 10 tiles (Chebyshev distance) to act
            dist_x = abs(current.x - self.player.x)
            dist_y = abs(current.y - self.player.y)
            if max(dist_x, dist_y) <= 10:
                current.take_turn(self.player, self.game_map, self)
            # Even if it skipped acting, advance the turn to avoid stalling
            self.next_turn()
        else:
            pass # No active entity or entity is dead.


        # NEW: Only update camera and process turns if player exists and game is in an active state
        if self.player and (self.game_state == GameState.DUNGEON or self.game_state == GameState.TAVERN or self.game_state == GameState.OVERWORLD or self.game_state == GameState.TARGETING): # Include TARGETING
            # If in targeting mode for Mage Hand, camera should follow the cursor
            if self.game_state == GameState.TARGETING and self.ability_in_use and isinstance(self.ability_in_use, MageHand):
                self.camera.update(self.targeting_cursor_x, self.targeting_cursor_y, self.game_map.width, self.game_map.height)
            else:
                self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)        


    def _pick_death_save_ambient_message(self):
        """
        Choose one flavor line for the death-save menu: usually a generic
        "fading consciousness" line, but favors naming the last attacker
        (and how hard they hit) when Player.take_damage() has recorded one,
        so the menu reads as "who/what put you here" rather than being
        purely atmospheric.
        """
        attacker = self.player.last_attacker_name
        if not attacker:
            return random.choice(DEATH_SAVE_AMBIENT_MESSAGES)

        lines = list(DEATH_SAVE_AMBIENT_MESSAGES)
        lines.extend(
            template.format(attacker=attacker) for template in DEATH_SAVE_ATTACKER_MESSAGE_TEMPLATES
        )
        if self.player.last_damage_taken:
            lines.append(DEATH_SAVE_ATTACKER_DAMAGE_TEMPLATE.format(
                attacker=attacker,
                damage=self.player.last_damage_taken,
                damage_type=self.player.last_damage_type or "damage",
            ))
        return random.choice(lines)

    def _enter_death_save_menu(self):
        """
        Switch to GameState.DEATH_SAVE_MENU at the start of a turn where the
        player is unconscious at 0 hp (Player.is_dying). Remembers whatever
        state we should return to once the roll is resolved, and picks a
        fresh ambient line -- see handle_death_save_menu_input() for the
        actual roll, triggered by player input.
        """
        if self.game_state != GameState.DEATH_SAVE_MENU:
            self._death_save_return_state = self.game_state
        self.game_state = GameState.DEATH_SAVE_MENU
        self.death_save_ambient_message = self._pick_death_save_ambient_message()

    def handle_death_save_menu_input(self, key):
        """
        Resolve the DEATH_SAVE_MENU prompt: rolling the save consumes the
        player's turn, whatever the outcome, so this always hands control
        back to next_turn()'s usual machinery afterward -- monsters keep
        acting on their turns while the player lies unconscious.
        """
        if key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return

        self.player.roll_death_save(self)

        if not self.player.alive:
            self.handle_game_over()
            return

        # Whether the player stabilized, woke up, or is still down at 0
        # successes/failures, the turn is spent -- return to the map and
        # let the normal turn loop advance to whatever acts next.
        self.game_state = self._death_save_return_state
        self.player_has_acted = True

    def handle_game_over(self):
        if not self._game_over_displayed:
            death_messages = [
                "Your journey ends here, adventurer. The dungeon claims another soul.",
                "The light fades from your eyes. Darkness embraces you.",
                "You fought bravely, but the dungeon proved too strong. Rest now.",
                "The dungeon's embrace is cold and final. You have fallen."
            ]
            chosen_death_message = random.choice(death_messages)
            self.message_log.add_message(chosen_death_message, (255, 0, 0))
            self._game_over_displayed = True
            self.game_over_victory = False
            self.game_over_title = "YOU DIED"
            self.game_over_story_lines = []
            self.game_over_subtext = "Press R to Restart or Q to Quit"
            if self.player:
                self.player.die()

            self.death_screen_alpha = 0
            self.death_screen_bg_alpha = 0
            self.death_screen_subtext_alpha = 0
            self.death_screen_animation_phase = 0

        self.game_state = GameState.GAME_OVER

    def handle_victory(self):
        if not self._game_over_displayed:
            self._game_over_displayed = True
            self.game_over_victory = True
            self.game_over_title = "VICTORY"
            self.game_over_story_lines = [
                "Arasta collapses beneath your final strike, her webs unraveling into the cold air.",
                "You leave the dungeon as more than a desperate stranger — you leave as its breaker.",
                "The tavern's dim warmth was once a shelter from debt and curse; now it becomes a place of legend.",
                "Your name will be whispered by weary travelers as the one who toppled the spider queen."
            ]
            self.game_over_subtext = "Press R to Restart or Q to Quit"

            self.death_screen_alpha = 0
            self.death_screen_bg_alpha = 0
            self.death_screen_subtext_alpha = 0
            self.death_screen_animation_phase = 0

        self.game_state = GameState.GAME_OVER



    def handle_window_resize(self):
        old_scale = self.scale
        
        self.scale_x = self.screen.get_width() / INTERNAL_WIDTH
        self.scale_y = self.screen.get_height() / INTERNAL_HEIGHT
        self.scale = min(self.scale_x, self.scale_y)
        
        if abs(old_scale - self.scale) > 0.1:
            self.internal_surface = pygame.Surface((INTERNAL_WIDTH, INTERNAL_HEIGHT))
            self.font = pygame.font.SysFont('consolas', int(INTERNAL_HEIGHT/50))

        self._recalculate_minimap_dimensions()            


    def add_dirty_rect(self, x, y, width, height):
        """Adds a rectangle to the list of dirty rects, converting world to screen coords."""
        screen_x_float, screen_y_float = self.camera.world_to_screen(x, y)
        draw_x = int(screen_x_float * config.TILE_SIZE)
        draw_y = int(screen_y_float * config.TILE_SIZE)
        rect = pygame.Rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)
        self.dirty_rects.append(rect)


    def render(self):
        """Main render method - draws everything"""
        # Clear the entire screen at the start of each frame
        self.screen.fill((0, 0, 0, 0))

        # --- Render the main game area (dungeon/tavern) to internal_surface ---
        self.internal_surface.fill((0, 0, 0, 0)) # Clear internal surface

        # Render map, items, entities, highlights, floating texts to internal_surface
        if self.game_state == GameState.CHARACTER_CREATION:
            self.render_character_creation_screen()
            if self.fade_in_alpha > 0:
                fade_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                fade_surface.fill((0, 0, 0, self.fade_in_alpha))
                self.screen.blit(fade_surface, (0, 0))
        elif self.game_state == GameState.CLASS_SELECTION:
            self.render_class_selection_screen() 
            if self.fade_in_alpha > 0:
                fade_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
                fade_surface.fill((0, 0, 0, self.fade_in_alpha))
                self.screen.blit(fade_surface, (0, 0))                                 
        elif self.game_state == GameState.INVENTORY:
            self.render_inventory_screen()
            # Inventory also draws to inventory_ui_surface, which is then blitted to screen
            self.screen.blit(self.inventory_ui_surface, (0, 0)) # Blit inventory UI directly
        elif self.game_state == GameState.INVENTORY_MENU:
            self.render_inventory_screen()
            self.screen.blit(self.inventory_ui_surface, (0, 0))
            self.render_inventory_menu_popup() # Popup draws directly to screen
        elif self.game_state == GameState.CHARACTER_MENU:
            self.render_character_menu()
            self.screen.blit(self.inventory_ui_surface, (0, 0))
        else: # This block handles DUNGEON, TAVERN, and TARGETING (and will be drawn under GAME_OVER)
            # --- Camera Update Logic ---
            if self.game_state == GameState.TARGETING:
                self.camera.update(self.targeting_cursor_x, self.targeting_cursor_y, self.game_map.width, self.game_map.height)
            else:
                self.camera.update(self.player.x, self.player.y, self.game_map.width, self.game_map.height)

            self.render_map_with_fov()
            
            # Render altars
            if hasattr(self.game_map, 'altars'):
                for altar in self.game_map.altars:
                    if self.camera.is_in_viewport(altar.x, altar.y):
                        visibility_type = self.fov.get_visibility_type(altar.x, altar.y)

                        # Only render if visible or explored
                        if visibility_type in ['player', 'torch', 'darkvision', 'explored']:
                            screen_x_float, screen_y_float = self.camera.world_to_screen(altar.x, altar.y)
                            draw_x = screen_x_float * config.TILE_SIZE
                            draw_y = screen_y_float * config.TILE_SIZE

                            # Set color tint based on visibility
                            if visibility_type == 'player':
                                altar_color_tint = (255, 255, 255, 255)
                            elif visibility_type == 'torch':
                                altar_color_tint = (255, 190, 102, 255)
                            elif visibility_type == 'darkvision':
                                altar_color_tint = (82, 88, 96, 255)
                            elif visibility_type == 'explored':
                                altar_color_tint = (62, 56, 54, 255)
                            else:
                                continue  # Don't render if not visible
                            
                            graphics.draw_tile(self.internal_surface, draw_x, draw_y, altar.char, color_tint=altar_color_tint)            

            self.render_items_on_ground()
            self.render_tile_highlights()
            self.render_bloodstains()
            self.render_entities()

            for text_obj in self.floating_texts:
                text_obj.draw(self.internal_surface, self.camera)

            if self.game_state == GameState.TARGETING:
                screen_x, screen_y = self.camera.world_to_screen(
                    self.targeting_cursor_x,
                    self.targeting_cursor_y
                )
                target_type = None
                target_entity = self.get_target_at(self.targeting_cursor_x, self.targeting_cursor_y)
                if isinstance(target_entity, Monster):
                    target_type = "monster"
                elif (tile := self.game_map.tiles[self.targeting_cursor_y][self.targeting_cursor_x]) and tile.destructible:
                    target_type = "destructible"

                cursor_color = (
                    (255, 100, 100) if target_type == "monster" else
                    (255, 200, 100) if target_type == "destructible" else
                    (100, 100, 255)
                )

                if isinstance(self.ability_in_use, MageHand):
                    graphics.draw_tile(self.internal_surface, screen_x * config.TILE_SIZE, screen_y * config.TILE_SIZE, 'mh', color_tint=(150, 200, 255))
                else:
                    cursor_width = 3
                    pygame.draw.rect(
                        self.internal_surface,
                        cursor_color,
                        (screen_x * config.TILE_SIZE,
                         screen_y * config.TILE_SIZE,
                         config.TILE_SIZE,
                         config.TILE_SIZE),
                        cursor_width
                    )

                # Magic Missile: show which dart the player is currently aiming
                from core.abilities import MagicMissile as _MagicMissile
                if isinstance(self.ability_in_use, _MagicMissile) and self.missile_darts_remaining > 0:
                    darts_total = self.ability_in_use.number_of_missiles
                    current_dart = darts_total - self.missile_darts_remaining + 1
                    dart_label = f"Dart {current_dart}/{darts_total}"
                    font = pygame.font.SysFont(None, 18)
                    label_surf = font.render(dart_label, True, (220, 180, 255))
                    label_x = screen_x * config.TILE_SIZE
                    label_y = screen_y * config.TILE_SIZE - label_surf.get_height() - 2
                    self.internal_surface.blit(label_surf, (label_x, label_y))

            # Scale and blit the internal game area surface to the main screen
            available_width = config.GAME_AREA_WIDTH
            available_height = config.SCREEN_HEIGHT  # log is a transparent overlay

            scale_to_fit_width = available_width / config.INTERNAL_GAME_AREA_PIXEL_WIDTH
            scale_to_fit_height = available_height / config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
            actual_display_scale = min(scale_to_fit_width, scale_to_fit_height)

            scaled_width = int(config.INTERNAL_GAME_AREA_PIXEL_WIDTH * actual_display_scale)
            scaled_height = int(config.INTERNAL_GAME_AREA_PIXEL_HEIGHT * actual_display_scale)

            offset_x = (available_width - scaled_width) // 2
            offset_y = (available_height - scaled_height) // 2

            target_rect = pygame.Rect(offset_x, offset_y, scaled_width, scaled_height)
            scaled_game_area = pygame.transform.scale(self.internal_surface, target_rect.size)
            self.screen.blit(scaled_game_area, target_rect.topleft)


        # --- Always draw UI, Minimap, and Message Log directly to the screen ---
        # This ensures they are always fully redrawn and prevents flickering.
        if self.player: # Only draw UI if player exists (after character creation)
            self.draw_ui() # This method now draws directly to self.screen
            # Draw minimap if in dungeon or overworld state
            if self.game_state in [GameState.DUNGEON, GameState.OVERWORLD]:
                self.draw_minimap() # This method now draws directly to self.screen

        # Message log is also drawn directly to screen
        if self.game_state not in [GameState.CHARACTER_CREATION, GameState.CLASS_SELECTION]:
            self.message_log.render(self.screen)

        # Overworld chunk transition overlay — plain black fade drawn over everything
        # else so the (possibly slow) chunk generation happening mid-fade is invisible.
        if self.chunk_transition_phase is not None:
            transition_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            transition_surface.fill((0, 0, 0, self.chunk_transition_alpha))
            self.screen.blit(transition_surface, (0, 0))

        if self.game_state == GameState.GAME_OVER and self.death_screen_animation_phase == 4:
            fade_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            fade_surface.fill((0, 0, 0, self.fade_out_alpha)) # Black overlay, increasing alpha
            self.screen.blit(fade_surface, (0, 0))
            pygame.display.flip() # Ensure this is drawn over everything
            return # Exit render function early during fade-out to prevent drawing underlying game

        # Locked chest interaction menu — drawn over the dungeon, under nothing else
        if self.game_state == GameState.CHEST_MENU and self._chest_menu_target:
            self.render_chest_menu(self._chest_menu_target)

        # Death saving throw menu — drawn over the map, under nothing else
        if self.game_state == GameState.DEATH_SAVE_MENU:
            self.render_death_save_menu()

        # World encounter discovery prompt — the beat's narration by itself,
        # with a "Continue" option, before its choice menu opens
        if self.game_state == GameState.WORLD_ENCOUNTER_DISCOVERY and self._world_encounter_discovery_text:
            self.render_world_encounter_discovery_menu()

        # World encounter menu — drawn over the overworld, under nothing else
        if self.game_state == GameState.WORLD_ENCOUNTER_MENU and self._world_encounter_target:
            self.render_world_encounter_menu()

        # World encounter aftermath menu — same overlay, offered after combat
        if self.game_state == GameState.WORLD_ENCOUNTER_AFTERMATH_MENU and self._world_encounter_aftermath:
            self.render_world_encounter_aftermath_menu()

        # Merchant shop overlay — drawn over the dungeon, under nothing else
        if self.game_state == GameState.SHOP_MENU and self._shop_menu_merchant:
            self.render_shop_menu()

        # Innkeeper's Rest / Buy Food / Leave overlay — drawn over the overworld, under nothing else
        if self.game_state == GameState.INNKEEPER_MENU and self._innkeeper_menu_target:
            self.render_innkeeper_menu()

        # Short rest / long rest overlay — drawn over the world, under nothing else
        if self.game_state == GameState.REST_MENU and self._rest_menu_target:
            self.render_rest_menu()

        # NEW: Render game over screen if in GAME_OVER state
        if self.game_state == GameState.GAME_OVER:
            self.render_game_over_screen()
            pygame.display.flip() # Ensure the screen updates
            return # Exit render function early to prevent further drawing

        fps_text = f"FPS: {int(self.fps)}"
        fps_surface = self.fps_font.render(fps_text, True, (255, 255, 255))  # White color
        self.screen.blit(fps_surface, (10, 10))  # Position at (10, 10) pixels from top-left

        # World clock (world_time.py's WorldClock, via self.stories.world_time) --
        # "Day N, HH:00", drawn just below the FPS counter. Purely a readout;
        # nothing here mutates the clock. Only shown once the player exists --
        # self.player is None during CHARACTER_CREATION/LINEAGE_SELECTION/
        # CLASS_SELECTION (and briefly again after a death-screen reset), and
        # the clock would otherwise read as meaningless "Day 0, 00:00" noise
        # before the player has actually been spawned into the world.
        if self.player is not None:
            clock = self.stories.world_time.clock
            time_text = (
                f"Day {clock.day}, {clock.hour_of_day:02d}:{clock.minute_of_hour:02d} "
                f"({period_for_hour(clock.hour_of_day)})"
            )
            time_surface = self.fps_font.render(time_text, True, (230, 210, 160))  # Warm parchment color
            self.screen.blit(time_surface, (10, 30))

        
        # --- Final Display Update ---
        # flip() does a full screen update. dirty_rects is still populated by
        # add_dirty_rect() calls (full_redraw paths) in case a partial-update
        # path is reintroduced later, but it isn't used to gate the blit here.
        pygame.display.flip()

        self.dirty_rects.clear()


    def render_chest_menu(self, chest):
        """
        Draws a compact choice popup over the dungeon when the player examines a locked chest.
        Keys: [1] Pick the Lock  [2] Smash It  [3] / ESC  Leave it
        """
        try:
            font_title = pygame.font.SysFont("consolas", 16, bold=True)
            font_body  = pygame.font.SysFont("consolas", 14)
        except Exception:
            font_title = pygame.font.Font(None, 18)
            font_body  = pygame.font.Font(None, 16)

        # --- Layout ---
        PAD   = 14
        W     = 440
        H     = 180
        sx    = (config.GAME_AREA_WIDTH - W) // 2
        sy    = (config.SCREEN_HEIGHT   - H) // 2

        # Dark semi-transparent background
        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((10, 8, 14, 220))
        self.screen.blit(bg, (sx, sy))

        # Steel-gray border (matches LockedChest color)
        pygame.draw.rect(self.screen, (100, 110, 130), (sx, sy, W, H), 2, border_radius=4)

        # Title
        title_surf = font_title.render("  Locked Chest", True, (200, 180, 100))
        self.screen.blit(title_surf, (sx + PAD, sy + PAD))

        # Divider
        pygame.draw.line(
            self.screen, (60, 60, 75),
            (sx + PAD, sy + PAD + 22), (sx + W - PAD, sy + PAD + 22)
        )

        # Options
        options = [
            ("[1] Pick the Lock",  "DEX check  DC 12 (Thieves' Tools required)", (160, 200, 255)),
            ("[2] Smash It Open",  "STR check  DC 14 (Attracts monsters)", (255, 160, 100)),
            ("[3] Leave it Alone", "ESC also cancels",                     (150, 150, 150)),
        ]

        y = sy + PAD + 32
        for header, sub, color in options:
            h_surf = font_body.render(header, True, color)
            s_surf = font_body.render(f"    {sub}", True, (90, 90, 100))
            self.screen.blit(h_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 1
            self.screen.blit(s_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 6

    def render_death_save_menu(self):
        """
        Draws the death-saving-throw overlay while the player is unconscious
        at 0 hp: the running success/failure pips, an ambient flavor line
        (see Game._pick_death_save_ambient_message() -- names the last
        attacker when one is known), and the roll prompt. Visually mirrors
        render_chest_menu()'s overlay size/fonts so it reads as the same
        "popup over the map" language as every other menu here, rather than
        a bespoke death screen.
        """
        try:
            font_title = pygame.font.SysFont("consolas", 16, bold=True)
            font_body  = pygame.font.SysFont("consolas", 14)
            font_pips  = pygame.font.SysFont("consolas", 18, bold=True)
        except Exception:
            font_title = pygame.font.Font(None, 18)
            font_body  = pygame.font.Font(None, 16)
            font_pips  = pygame.font.Font(None, 20)

        # --- Layout ---
        PAD = 14
        W   = 440
        H   = 190
        sx  = (config.GAME_AREA_WIDTH - W) // 2
        sy  = (config.SCREEN_HEIGHT   - H) // 2

        # Dark, blood-tinted semi-transparent background
        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((16, 6, 8, 225))
        self.screen.blit(bg, (sx, sy))

        pygame.draw.rect(self.screen, (150, 40, 40), (sx, sy, W, H), 2, border_radius=4)

        title_surf = font_title.render("  Death Saving Throw", True, (220, 80, 80))
        self.screen.blit(title_surf, (sx + PAD, sy + PAD))

        pygame.draw.line(
            self.screen, (60, 30, 32),
            (sx + PAD, sy + PAD + 22), (sx + W - PAD, sy + PAD + 22)
        )

        y = sy + PAD + 32

        # Ambient flavor line, wrapped to the popup width.
        for line in self._wrap_text(self.death_save_ambient_message, font_body, W - PAD * 2):
            line_surf = font_body.render(line, True, (170, 150, 150))
            self.screen.blit(line_surf, (sx + PAD, y))
            y += font_body.get_linesize()
        y += 10

        # Success/failure pips -- filled circle for a resolved save, hollow
        # for one still pending, three of each per the 5e rule.
        successes = self.player.death_save_successes
        failures  = self.player.death_save_failures

        label_surf = font_body.render("Successes", True, (150, 220, 150))
        self.screen.blit(label_surf, (sx + PAD, y))
        pip_text = "".join("●" if i < successes else "○" for i in range(3))
        pip_surf = font_pips.render(pip_text, True, (120, 220, 120))
        self.screen.blit(pip_surf, (sx + PAD + 130, y - 2))

        y += font_body.get_linesize() + 6

        label_surf = font_body.render("Failures", True, (220, 150, 150))
        self.screen.blit(label_surf, (sx + PAD, y))
        pip_text = "".join("●" if i < failures else "○" for i in range(3))
        pip_surf = font_pips.render(pip_text, True, (220, 100, 100))
        self.screen.blit(pip_surf, (sx + PAD + 130, y - 2))

        y += font_body.get_linesize() + 14

        prompt_surf = font_body.render("[Space / Enter]  Roll", True, (200, 200, 200))
        self.screen.blit(prompt_surf, (sx + PAD, y))

    def render_innkeeper_menu(self):
        """
        Draws the Innkeeper's Rest for the Night / Buy Food / Leave choice
        popup over the overworld. Visually mirrors render_chest_menu() --
        same overlay size, fonts, and numbered-option layout -- so the two
        "adjacent NPC/object offers a short numbered choice" interactions
        read as one consistent UI language rather than two bespoke ones.

        Unlike render_chest_menu()'s hard-coded option text, the two real
        choices here are captioned from the live Innkeeper instance
        (self._innkeeper_menu_target) -- its rest_cost/rest_hours and
        current food stock -- so the popup never drifts out of sync with
        what selecting them will actually do.
        """
        innkeeper = self._innkeeper_menu_target
        if innkeeper is None:
            return

        try:
            font_title = pygame.font.SysFont("consolas", 16, bold=True)
            font_body  = pygame.font.SysFont("consolas", 14)
        except Exception:
            font_title = pygame.font.Font(None, 18)
            font_body  = pygame.font.Font(None, 16)

        # --- Layout (identical footprint to render_chest_menu) ---
        PAD   = 14
        W     = 440
        H     = 180
        sx    = (config.GAME_AREA_WIDTH - W) // 2
        sy    = (config.SCREEN_HEIGHT   - H) // 2

        # Dark semi-transparent background
        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((10, 8, 14, 220))
        self.screen.blit(bg, (sx, sy))

        # Warm gold border, matching the Innkeeper NPC's own tile color
        pygame.draw.rect(self.screen, (255, 215, 120), (sx, sy, W, H), 2, border_radius=4)

        # Title
        title_surf = font_title.render(f"  {innkeeper.name}", True, (255, 215, 120))
        self.screen.blit(title_surf, (sx + PAD, sy + PAD))

        # Divider
        pygame.draw.line(
            self.screen, (60, 60, 75),
            (sx + PAD, sy + PAD + 22), (sx + W - PAD, sy + PAD + 22)
        )

        food_count = len(innkeeper.items_for_sale)
        food_sub = (
            f"{food_count} item(s) available"
            if food_count else "Nothing left in stock right now"
        )

        options = [
            (
                "[1] Rest for the Night",
                f"{innkeeper.rest_cost} gold  --  restores HP, advances {innkeeper.rest_hours} hours",
                (160, 220, 160),
            ),
            (
                "[2] Buy Food",
                food_sub,
                (255, 220, 150),
            ),
            (
                "[3] Leave",
                "ESC / F also cancels",
                (150, 150, 150),
            ),
        ]

        y = sy + PAD + 32
        for header, sub, color in options:
            h_surf = font_body.render(header, True, color)
            s_surf = font_body.render(f"    {sub}", True, (90, 90, 100))
            self.screen.blit(h_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 1
            self.screen.blit(s_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 6

    def render_rest_menu(self):
        """Draw the short rest / long rest choice popup over the map."""
        if self._rest_menu_target is None:
            return

        try:
            font_title = pygame.font.SysFont("consolas", 16, bold=True)
            font_body = pygame.font.SysFont("consolas", 14)
        except Exception:
            font_title = pygame.font.Font(None, 18)
            font_body = pygame.font.Font(None, 16)

        PAD = 14
        W = 420
        H = 170
        sx = (config.GAME_AREA_WIDTH - W) // 2
        sy = (config.SCREEN_HEIGHT - H) // 2

        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((10, 8, 14, 220))
        self.screen.blit(bg, (sx, sy))

        pygame.draw.rect(self.screen, (150, 215, 170), (sx, sy, W, H), 2, border_radius=4)

        title_surf = font_title.render("  Rest", True, (150, 215, 170))
        self.screen.blit(title_surf, (sx + PAD, sy + PAD))

        pygame.draw.line(
            self.screen, (60, 60, 75),
            (sx + PAD, sy + PAD + 22), (sx + W - PAD, sy + PAD + 22)
        )

        options = [
            (
                "[1] Short Rest", 
                f"Spend 1 hour and recover a little", 
                (160, 220, 160)
            ),
            (
                "[2] Long Rest", 
                f"Spend 8 hours and recover more fully", 
                (255, 220, 150)
            ),
            (
                "[3] Cancel", 
                f"ESC / F also cancels", 
                (150, 150, 150)
            ),
        ]

        y = sy + PAD + 32
        for header, sub, color in options:
            h_surf = font_body.render(header, True, color)
            s_surf = font_body.render(f"    {sub}", True, (90, 90, 100))
            self.screen.blit(h_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 1
            self.screen.blit(s_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 6

    def render_world_encounter_discovery_menu(self):
        """
        Draws a beat's "discovery" text by itself, word-wrapped, with a
        single numbered "Continue" prompt underneath -- e.g.:

            "Smoke and chanting drift from a clearing off the trail,
            underscored by the crackle of torches at unnatural hours."

            1. Continue

        Shown before render_world_encounter_menu()/render_world_encounter_
        aftermath_menu() so the player reads what's happening before being
        asked to decide anything about it. Same box/border styling as
        _render_world_encounter_choice_popup(), but with wrapped body text
        in place of a list of choices, since there's only ever the one.
        """
        try:
            font_title = pygame.font.SysFont("consolas", 16, bold=True)
            font_body  = pygame.font.SysFont("consolas", 14)
        except Exception:
            font_title = pygame.font.Font(None, 18)
            font_body  = pygame.font.Font(None, 16)

        PAD         = 14
        W           = 440
        text_w      = W - PAD * 2
        lines       = self._wrap_text(self._world_encounter_discovery_text, font_body, text_w)
        LINE_H      = font_body.get_linesize()
        PROMPT_H    = font_title.get_linesize()
        DIVIDER_GAP = PAD // 2  # breathing room on each side of the divider

        # Top padding + wrapped narration + divider (with a gap on either
        # side) + the "[1] Continue" row + bottom padding -- exactly the
        # vertical space the drawing loop below actually fills.
        H  = PAD + LINE_H * len(lines) + DIVIDER_GAP * 2 + PROMPT_H + PAD
        sx = (config.GAME_AREA_WIDTH - W) // 2
        sy = (config.SCREEN_HEIGHT   - H) // 2

        # Dark semi-transparent background, same palette as the choice popup
        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((10, 8, 14, 220))
        self.screen.blit(bg, (sx, sy))

        pygame.draw.rect(self.screen, (150, 140, 190), (sx, sy, W, H), 2, border_radius=4)

        # Wrapped discovery text
        y = sy + PAD
        for line in lines:
            line_surf = font_body.render(line, True, (230, 220, 255))
            self.screen.blit(line_surf, (sx + PAD, y))
            y += LINE_H

        # Divider between the narration and the "Continue" prompt
        y += DIVIDER_GAP
        pygame.draw.line(self.screen, (60, 60, 75), (sx + PAD, y), (sx + W - PAD, y))
        y += DIVIDER_GAP

        # Continue prompt
        prompt_surf = font_title.render("[1] Continue", True, (200, 190, 230))
        self.screen.blit(prompt_surf, (sx + PAD, y))

    def render_world_encounter_menu(self):
        """
        Draws the textbox popup for the current stage of a (possibly
        staged) overworld encounter. Both the generic arrival hook
        ("You hear screams ahead.") and this stage's own "discovery"
        text are already in the message log by this point (see
        _maybe_trigger_world_encounter()/_enter_world_encounter_stage()),
        so this just shows the current stage's own choices (see
        _normalize_world_encounter_choices()/_current_world_encounter_
        stage()) -- which change as the player advances deeper into a
        staged scenario (wagon -> campfire -> goblin camp). Key bindings
        come from each choice's own "key" field; ESC always matches
        whichever choice is "is_cancel".
        """
        stage = self._current_world_encounter_stage()
        self._render_world_encounter_choice_popup("  What do you do?", stage["choices"])

    def render_world_encounter_aftermath_menu(self):
        """
        Draws the same popup style as render_world_encounter_menu(), for a
        scenario's post-combat "aftermath" choices instead of its initial
        discovery choices (see _offer_world_encounter_aftermath() and
        _resolve_world_encounter_aftermath_choice()). Kept as a separate
        method, rather than branching inside render_world_encounter_menu(),
        so each stays a simple one-line wrapper naming which state/target
        pair it draws for.
        """
        self._render_world_encounter_choice_popup("  What now?", self._world_encounter_aftermath["choices"])

    def _render_world_encounter_choice_popup(self, title, choices):
        """
        Shared layout/drawing for both the discovery menu and the
        aftermath menu -- identical box, divider, and per-choice rows,
        differing only in title text and which choices list is passed in.
        """
        try:
            font_title = pygame.font.SysFont("consolas", 16, bold=True)
            font_body  = pygame.font.SysFont("consolas", 14)
        except Exception:
            font_title = pygame.font.Font(None, 18)
            font_body  = pygame.font.Font(None, 16)

        # --- Layout ---
        PAD       = 14
        W         = 440
        ROW_H     = font_body.get_linesize() * 2 + 7  # header line + sub line + gap
        HEADER_H  = PAD + 22 + PAD                     # title + divider + breathing room
        H         = HEADER_H + ROW_H * len(choices)
        sx        = (config.GAME_AREA_WIDTH - W) // 2
        sy        = (config.SCREEN_HEIGHT   - H) // 2

        # Dark semi-transparent background
        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((10, 8, 14, 220))
        self.screen.blit(bg, (sx, sy))

        # Pale border, distinct from the chest menu's steel-gray
        pygame.draw.rect(self.screen, (150, 140, 190), (sx, sy, W, H), 2, border_radius=4)

        # Title
        title_surf = font_title.render(title, True, (200, 190, 230))
        self.screen.blit(title_surf, (sx + PAD, sy + PAD))

        # Divider
        pygame.draw.line(
            self.screen, (60, 60, 75),
            (sx + PAD, sy + PAD + 22), (sx + W - PAD, sy + PAD + 22)
        )

        # Choices, in whatever order/count the scenario's JSON declared them
        y = sy + PAD + 32
        for choice in choices:
            cancel_hint = " / ESC" if choice.get("is_cancel") else ""
            header = f"[{choice['key']}{cancel_hint}] {choice['label']}"
            h_surf = font_body.render(header, True, choice["color"])
            s_surf = font_body.render(f"    {choice['description']}", True, (90, 90, 100))
            self.screen.blit(h_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 1
            self.screen.blit(s_surf, (sx + PAD, y))
            y += font_body.get_linesize() + 6

    def render_shop_menu(self):
        """
        Draws the merchant shop overlay.
        ↑↓ navigate  TAB switch buy/sell  ENTER confirm  ESC / F close

        Layout is fully dynamic: the panel width fits the longest item name,
        and the row count scales to fill ~75 % of the screen height.
        """
        merchant = self._shop_menu_merchant
        if not merchant:
            return

        try:
            font_title = pygame.font.SysFont("consolas", 18, bold=True)
            font_body  = pygame.font.SysFont("consolas", 15)
            font_small = pygame.font.SysFont("consolas", 13)
        except Exception:
            font_title = pygame.font.Font(None, 20)
            font_body  = pygame.font.Font(None, 17)
            font_small = pygame.font.Font(None, 15)

        PAD   = 16
        ROW_H = font_body.get_linesize() + 5

        # ── Dynamic width ─────────────────────────────────────────────────
        # Measure the widest item name in both lists so the panel never clips.
        all_names = (
            [item.name for item in merchant.items_for_sale]
            + [item.name for item in self.player.inventory.items]
        )
        max_name_px = max(
            (font_body.size(f"  >  {n}")[0] for n in all_names),
            default=0
        )
        price_col_w  = font_body.size("9999 gp")[0] + PAD
        min_w        = font_title.size(f"  {merchant.name}")[0] + font_small.size("Gold: 99999 gp  ")[0] + PAD * 3
        W = max(560, min_w, max_name_px + price_col_w + PAD * 3)
        W = min(W, config.GAME_AREA_WIDTH - PAD * 4)   # never wider than the game area

        # ── Dynamic row count ─────────────────────────────────────────────
        # Fixed chrome: title-row + div + tab-row + div + footer-div + footer
        CHROME_H = (PAD                          # top padding
                    + font_title.get_linesize()  # title
                    + 6                          # divider gap
                    + font_body.get_linesize()   # tab row
                    + 8                          # divider gap
                    + 6                          # pre-footer divider gap
                    + font_small.get_linesize()  # footer
                    + PAD)                       # bottom padding
        available_h = int(config.SCREEN_HEIGHT * 0.80)
        MAX_ROWS    = max(6, (available_h - CHROME_H) // ROW_H)
        H           = CHROME_H + MAX_ROWS * ROW_H

        sx = (config.GAME_AREA_WIDTH - W) // 2
        sy = (config.SCREEN_HEIGHT   - H) // 2

        # ── Background + double border ────────────────────────────────────
        bg = pygame.Surface((W, H), pygame.SRCALPHA)
        bg.fill((12, 9, 18, 235))
        self.screen.blit(bg, (sx, sy))
        pygame.draw.rect(self.screen, (120, 100, 40), (sx, sy, W, H), 1, border_radius=6)
        pygame.draw.rect(self.screen, (200, 165, 70), (sx + 2, sy + 2, W - 4, H - 4), 1, border_radius=5)

        # ── Title row ─────────────────────────────────────────────────────
        cur_y      = sy + PAD
        title_surf = font_title.render(f"  {merchant.name}", True, (255, 220, 90))
        gold_text  = f"Gold: {self.player.gold} gp"
        gold_surf  = font_body.render(gold_text, True, (220, 190, 60))
        self.screen.blit(title_surf, (sx + PAD, cur_y))
        self.screen.blit(gold_surf,  (sx + W - gold_surf.get_width() - PAD, cur_y + 2))
        cur_y += font_title.get_linesize() + 4

        # ── Divider ───────────────────────────────────────────────────────
        pygame.draw.line(self.screen, (90, 75, 30), (sx + PAD, cur_y), (sx + W - PAD, cur_y))
        cur_y += 6

        # ── Mode tabs ─────────────────────────────────────────────────────
        is_buy   = self._shop_mode == "buy"
        buy_col  = (255, 220, 80) if is_buy  else (75, 75, 75)
        sell_col = (255, 220, 80) if not is_buy else (75, 75, 75)
        buy_surf  = font_body.render("[ BUY ]",  True, buy_col)
        sell_surf = font_body.render("[ SELL ]", True, sell_col)
        tab_hint  = font_small.render("TAB to switch", True, (65, 65, 65))

        # Underline the active tab
        active_surf = buy_surf if is_buy else sell_surf
        active_x    = sx + PAD if is_buy else sx + PAD + buy_surf.get_width() + 16
        pygame.draw.line(
            self.screen, (220, 180, 60),
            (active_x, cur_y + active_surf.get_height()),
            (active_x + active_surf.get_width(), cur_y + active_surf.get_height()),
            2
        )
        self.screen.blit(buy_surf,  (sx + PAD, cur_y))
        self.screen.blit(sell_surf, (sx + PAD + buy_surf.get_width() + 16, cur_y))
        self.screen.blit(tab_hint,  (sx + W - tab_hint.get_width() - PAD, cur_y + 3))
        cur_y += font_body.get_linesize() + 6

        # ── Divider ───────────────────────────────────────────────────────
        pygame.draw.line(self.screen, (90, 75, 30), (sx + PAD, cur_y), (sx + W - PAD, cur_y))
        cur_y += 4
        list_start_y = cur_y

        # ── Item list ─────────────────────────────────────────────────────
        items = merchant.items_for_sale if is_buy else self.player.inventory.items
        sel   = self._shop_selected_index

        scroll_top = max(0, sel - MAX_ROWS // 2)
        scroll_top = min(scroll_top, max(0, len(items) - MAX_ROWS))
        visible    = items[scroll_top : scroll_top + MAX_ROWS]

        for i, item in enumerate(visible):
            actual_idx = scroll_top + i
            is_sel     = (actual_idx == sel)
            row_y      = list_start_y + i * ROW_H

            # Highlighted row background
            if is_sel:
                row_bg = pygame.Surface((W - PAD * 2, ROW_H - 1), pygame.SRCALPHA)
                row_bg.fill((70, 55, 10, 200))
                self.screen.blit(row_bg, (sx + PAD, row_y))

            # Alternating subtle stripe for unselected rows
            elif i % 2 == 0:
                stripe = pygame.Surface((W - PAD * 2, ROW_H - 1), pygame.SRCALPHA)
                stripe.fill((255, 255, 255, 8))
                self.screen.blit(stripe, (sx + PAD, row_y))

            pointer  = ">" if is_sel else " "
            name_col = (255, 245, 160) if is_sel else (210, 210, 210)

            if is_buy:
                price_val = item.price
                price_str = f"{price_val} gp"
                price_col = (90, 210, 90) if self.player.gold >= price_val else (210, 70, 70)
            else:
                price_val = item.price // 2
                price_str = f"{price_val} gp"
                price_col = (90, 190, 255)

            # Scroll indicator arrows when list overflows
            if i == 0 and scroll_top > 0:
                arrow_surf = font_small.render("▲ more", True, (130, 130, 80))
                self.screen.blit(arrow_surf, (sx + W - arrow_surf.get_width() - PAD, row_y))
            elif i == len(visible) - 1 and (scroll_top + MAX_ROWS) < len(items):
                arrow_surf = font_small.render("▼ more", True, (130, 130, 80))
                self.screen.blit(arrow_surf, (sx + W - arrow_surf.get_width() - PAD, row_y + ROW_H // 2))

            name_surf  = font_body.render(f"  {pointer}  {item.name}", True, name_col)
            price_surf = font_body.render(price_str, True, price_col)
            self.screen.blit(name_surf,  (sx + PAD, row_y + 2))
            self.screen.blit(price_surf, (sx + W - price_surf.get_width() - PAD, row_y + 2))

        # Empty-list placeholder
        if not items:
            empty_msg  = "Nothing for sale." if is_buy else "Your inventory is empty."
            empty_surf = font_body.render(empty_msg, True, (80, 80, 80))
            self.screen.blit(empty_surf, (sx + PAD * 2, list_start_y + ROW_H))

        # ── Footer ────────────────────────────────────────────────────────
        footer_y = sy + H - font_small.get_linesize() - PAD
        pygame.draw.line(self.screen, (90, 75, 30), (sx + PAD, footer_y - 5), (sx + W - PAD, footer_y - 5))
        hint      = "↑↓ Navigate    ENTER Confirm    TAB Switch    ESC / F  Close"
        hint_surf = font_small.render(hint, True, (85, 85, 85))
        # Centre the hint
        self.screen.blit(hint_surf, (sx + (W - hint_surf.get_width()) // 2, footer_y))

    def render_game_over_screen(self):        # Render background overlay with fade-in alpha after the title text
        if self.death_screen_animation_phase >= 1:
            overlay_surface = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            overlay_surface.fill((0, 0, 0, self.death_screen_bg_alpha))
            self.screen.blit(overlay_surface, (0, 0))

        # Render title text with fade-in alpha
        font = pygame.font.SysFont('consolas', 72, bold=True)
        title_color = (0, 255, 0) if self.game_over_victory else (255, 0, 0)
        text_surface = font.render(self.game_over_title, True, title_color)
        text_surface.set_alpha(self.death_screen_alpha)
        text_rect = text_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 40))
        self.screen.blit(text_surface, text_rect)

        # Render story lines for victory after background is visible
        if self.death_screen_animation_phase >= 2 and self.game_over_victory:
            font_small = pygame.font.SysFont('consolas', 24)
            y_offset = text_rect.bottom + 20
            for line in self.game_over_story_lines:
                story_surface = font_small.render(line, True, (220, 220, 220))
                story_surface.set_alpha(self.death_screen_subtext_alpha)
                story_rect = story_surface.get_rect(center=(self.screen.get_width() // 2, y_offset))
                self.screen.blit(story_surface, story_rect)
                y_offset += story_surface.get_height() + 8

        # Render subtext with fade-in alpha after background is visible
        if self.death_screen_animation_phase >= 2:
            font_small = pygame.font.SysFont('consolas', 24)
            subtext = font_small.render(self.game_over_subtext, True, (255, 255, 255))
            subtext.set_alpha(self.death_screen_subtext_alpha)
            subtext_rect = subtext.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() - 80))
            self.screen.blit(subtext, subtext_rect)
            

    def _ambient_light_tint(self):
        """
        Current time-of-day ambient light tint (see world/lighting.py),
        or None where time of day shouldn't affect lighting at all.

        Only the OVERWORLD is lit by the sky -- the DUNGEON and TAVERN
        states keep their existing fixed, torch-lit mood regardless of
        the hour, since they're indoors/underground and have no window
        onto the world clock. A None here is exactly like any other
        stage in lighting.combine_tints()'s stack being skipped: it
        simply doesn't contribute.

        Checks `_environment_state`, not `game_state` directly: opening a
        menu (shop, chest, world encounter, ...) swaps game_state to that
        menu's own state without actually moving the player anywhere, so
        judging "am I outdoors" off game_state would flatten the sky's
        time-of-day tint the instant any menu opened and snap it back the
        instant the menu closed. _environment_state only changes when the
        player actually does move between overworld and dungeon, so the
        ambient tint stays exactly as it was underneath the menu.
        """
        if self._environment_state != GameState.OVERWORLD:
            return None
        clock = self.stories.world_time.clock
        return ambient_tint_for_time(clock.hour_of_day, clock.minute_of_hour)

    def _fov_tint(self, visibility_type, has_torchlight, ambient_tint=None):
        """
        The flat per-FOV-state tint every tile/entity/item renderer
        already used (player/torch/darkvision/explored/unexplored),
        stacked on top of `ambient_tint` (see world/lighting.py's module
        docstring for the intended ambient-light-under-local-light
        ordering). Callers are expected to have already screened out
        any visibility_type this doesn't recognize.
        """
        if visibility_type == 'player':
            base = self._torch_flicker_tint if has_torchlight else (142, 152, 165, 255)
        elif visibility_type == 'torch':
            base = self._torch_flicker_tint
        elif visibility_type == 'darkvision':
            base = (72, 78, 86, 255)
        elif visibility_type == 'explored':
            base = (36, 30, 34, 255)
        else:  # 'unexplored'
            base = (8, 6, 8, 255)
        return combine_tints(base, ambient_tint)

    def render_map_with_fov(self, full_redraw=False):
        if not hasattr(self, 'game_map') or self.game_map is None:
            return

        camera_x_int = int(self.camera.x)
        camera_y_int = int(self.camera.y)

        has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)          
        ambient_tint = self._ambient_light_tint()

        for y in range(camera_y_int, min(camera_y_int + self.camera.viewport_height + 1, self.game_map.height)):
            for x in range(camera_x_int, min(camera_x_int + self.camera.viewport_width + 1, self.game_map.width)):

                screen_x_float, screen_y_float = self.camera.world_to_screen(x, y)

                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE

                visibility_type = self.fov.get_visibility_type(x, y)

                tile = self.game_map.tiles[y][x]      

                # Set color tint based on visibility (applies to all tiles, including water)
                # change FOV, stacked underneath the current time-of-day ambient light
                # (see world/lighting.py -- None indoors/underground, where it's a no-op).
                if visibility_type == 'unexplored':
                    render_color_tint = self._fov_tint(visibility_type, has_torchlight, ambient_tint)
                    continue
                elif visibility_type not in ('player', 'torch', 'darkvision', 'explored'):
                    continue  # Don't render if truly invisible
                render_color_tint = self._fov_tint(visibility_type, has_torchlight, ambient_tint)

                # Draw the tile using the restored sprite-based draw_tile
                graphics.draw_tile(self.internal_surface, draw_x, draw_y, tile.char, color_tint=render_color_tint)

                # Handle special tiles (e.g., TrapTile, MimicTile - your existing logic)
                if isinstance(tile, TrapTile):
                    display_char = tile.get_display_char()
                    display_color = tile.get_display_color()
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, display_char, color_tint=render_color_tint) 

                # Add a subtle animated tint over the fire sprite (already drawn above via tile.char)
                if isinstance(tile, FireElementalTile):
                    # The fire sprite was drawn by the graphics.draw_tile call above.
                    # Just overlay a light flicker tint so the sprite stays visible.
                    fire_alpha = random.randint(30, 70)
                    fire_overlay = pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA)
                    fire_overlay.fill((0, 0, 0, fire_alpha))
                    self.internal_surface.blit(fire_overlay, (int(draw_x), int(draw_y)))

                if full_redraw:
                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)


    def render_tile_highlights(self):
        # --- Targeting cursor red tint ---
        # For AoE abilities (those with a 'radius' attribute), tint every tile
        # within that radius around the cursor.  For single-target abilities,
        # tint only the cursor tile itself.
        if self.game_state == GameState.TARGETING:
            cx, cy = self.targeting_cursor_x, self.targeting_cursor_y
            aoe_radius = getattr(self.ability_in_use, 'radius', 0)
            cursor_overlay = pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA)
            cursor_overlay.fill((180, 40, 40, 20))

            if aoe_radius > 0:
                # Tint all tiles within the AoE radius of the cursor
                for hy in range(cy - aoe_radius, cy + aoe_radius + 1):
                    for hx in range(cx - aoe_radius, cx + aoe_radius + 1):
                        if (hx - cx) ** 2 + (hy - cy) ** 2 > aoe_radius ** 2:
                            continue
                        if not self.camera.is_in_viewport(hx, hy):
                            continue
                        sx, sy = self.camera.world_to_screen(hx, hy)
                        self.internal_surface.blit(cursor_overlay, (int(sx * config.TILE_SIZE), int(sy * config.TILE_SIZE)))
            else:
                # Single-target: tint only the cursor tile
                if self.camera.is_in_viewport(cx, cy):
                    sx, sy = self.camera.world_to_screen(cx, cy)
                    self.internal_surface.blit(cursor_overlay, (int(sx * config.TILE_SIZE), int(sy * config.TILE_SIZE)))

        # Draw per-entity telegraphs every frame to avoid stale global state
        for entity in self.entities:
            tiles = getattr(entity, 'pending_telegraph_tiles', None)          
            if not tiles:
                continue
            color = getattr(entity, 'telegraph_color', (255, 0, 0, 100))
            for hx, hy in tiles:
                if not (0 <= hx < self.game_map.width and 0 <= hy < self.game_map.height):
                    continue
                vis = self.fov.get_visibility_type(hx, hy)
                if vis not in ['player', 'torch', 'darkvision', 'explored']:
                    continue
                sx, sy = self.camera.world_to_screen(hx, hy)
                px = sx * config.TILE_SIZE
                py = sy * config.TILE_SIZE
                r, g, b, a = color
                overlay = pygame.Surface((config.TILE_SIZE, config.TILE_SIZE), pygame.SRCALPHA)
                overlay.fill((r, g, b, a))
                self.internal_surface.blit(overlay, (px, py))


    def render_entities(self, full_redraw=False):
        if not hasattr(self, 'game_map') or self.game_map is None:
            return        
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for entity in self.entities:
            if isinstance(entity, Mimic) and entity.disguised:
                continue 
            visibility_type = self.fov.get_visibility_type(entity.x, entity.y)
    
            if entity.alive and self.camera.is_in_viewport(entity.x, entity.y) and \
               (visibility_type == 'player' or visibility_type == 'torch' or visibility_type == 'explored' or visibility_type == 'darkvision'):
    
                screen_x_float, screen_y_float = self.camera.world_to_screen(entity.x, entity.y)
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE
    
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= draw_y < map_render_height):
    
                    has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)
    
                    # KEPT: Visibility-based tinting (dimming for FOV effects), now
                    # stacked underneath the current time-of-day ambient light --
                    # see world/lighting.py and the shared _fov_tint() helper above.
                    entity_color_tint = self._fov_tint(visibility_type, has_torchlight, self._ambient_light_tint())
    
                    footprint_size = getattr(entity, 'footprint_size', 1)
                    tile_size_override = config.TILE_SIZE * footprint_size if footprint_size > 1 else None
    
                    # Determine flip_x only for player
                    flip_x = False
                    if entity == self.player:
                        flip_x = not self.player.facing_right
    
                    # Check for submersion (player or swimming monsters on water)
                    entity_tile = self.game_map.tiles[entity.y][entity.x]
                    is_submerged = (entity == self.player or (hasattr(entity, 'can_swim') and entity.can_swim)) and is_water_tile(entity_tile)
    
                    if is_submerged:
                        # Composited top-half-sprite + bottom-half-ripple surface is
                        # cached by graphics.draw_submerged_tile(), so this no longer
                        # rebuilds the sprite (copy/flip/tint/scale) every frame.
                        graphics.draw_submerged_tile(
                            self.internal_surface,
                            draw_x,
                            draw_y,
                            entity.char,
                            color_tint=entity_color_tint,
                            tile_size=tile_size_override,
                            flip_x=flip_x
                        )
                    else:
                        # Normal rendering for non-submerged entities
                        graphics.draw_tile(
                            self.internal_surface,
                            draw_x,
                            draw_y,
                            entity.char,
                            color_tint=entity_color_tint,
                            tile_size=tile_size_override,
                            flip_x=flip_x
                        )
    
                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)
        

    def render_bloodstains(self):
        """Renders bloodstains on the map."""
        if not hasattr(self, 'game_map') or self.game_map is None:
            return
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT
        for bloodstain in self.bloodstains:
            # Only render if within camera viewport
            if self.camera.is_in_viewport(bloodstain.x, bloodstain.y):
                screen_x_float, screen_y_float = self.camera.world_to_screen(bloodstain.x, bloodstain.y)
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= draw_y < map_render_height):
                    # Bloodstains should appear dimmer in explored areas. This is
                    # its own red "color tint" stage (see world/lighting.py's
                    # module docstring) -- ambient light still stacks on top of
                    # it via combine_tints(), same as every other tile/entity.
                    visibility_type = self.fov.get_visibility_type(bloodstain.x, bloodstain.y)
                    if visibility_type == 'player':
                        blood_tint = (235, 0, 0, 150) # Slightly transparent red
                    elif visibility_type == 'torch':
                        blood_tint = (185, 0, 0, 120)
                    elif visibility_type == 'darkvision':
                        blood_tint = (72, 0, 0, 100)
                    elif visibility_type == 'explored':
                        blood_tint = (36, 0, 0, 80) # Very dim in explored areas
                    else: # Unexplored, don't draw
                        continue
                    color_tint = combine_tints(blood_tint, self._ambient_light_tint())
                    # Draw a semi-transparent red square or a specific bloodstain character
                    # You can use a custom character like '.' or ',' for bloodstains
                    # Or draw a semi-transparent rectangle over the tile
                    graphics.draw_tile(
                        self.internal_surface,
                        draw_x,
                        draw_y,
                        bloodstain.char, # Use the bloodstain's character
                        color_tint=color_tint
                    )
                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)

    def render_items_on_ground(self, full_redraw=False):
        """Render items lying on the dungeon floor."""
        if not hasattr(self, 'game_map') or self.game_map is None:
            return             
        map_render_height = config.INTERNAL_GAME_AREA_PIXEL_HEIGHT 
        
        for item in self.game_map.items_on_ground:
            if isinstance(item, Mimic) and item.disguised:
                continue 
            
            visibility_type = self.fov.get_visibility_type(item.x, item.y)
            
            if self.camera.is_in_viewport(item.x, item.y) and \
               (visibility_type == 'player' or visibility_type == 'torch' or visibility_type == 'explored' or visibility_type == 'darkvision'):
                
                # --- MODIFIED: Get float screen coordinates ---
                screen_x_float, screen_y_float = self.camera.world_to_screen(item.x, item.y)
                
                # --- MODIFIED: Calculate pixel draw positions using floats ---
                draw_x = screen_x_float * config.TILE_SIZE
                draw_y = screen_y_float * config.TILE_SIZE
                
                if (0 <= draw_x < config.INTERNAL_GAME_AREA_PIXEL_WIDTH and
                    0 <= draw_y < map_render_height):
                    

                    has_torchlight = any(effect.name == "Torchlight" for effect in self.player.active_status_effects)

                    # Same FOV tint + ambient time-of-day stack as tiles/entities --
                    # see world/lighting.py and the shared _fov_tint() helper above.
                    item_color_tint = self._fov_tint(visibility_type, has_torchlight, self._ambient_light_tint())
                    
                    # Always draw floor under items, as map rendering might have drawn a decorative tile
                    # --- MODIFIED: Pass float draw_x, draw_y to graphics.draw_tile ---
                    # graphics.draw_tile(self.internal_surface, draw_x, draw_y, floor.char, color_tint=item_color_tint)
                    graphics.draw_tile(self.internal_surface, draw_x, draw_y, item.char, color_tint=item_color_tint)


                    self.add_dirty_rect(draw_x, draw_y, config.TILE_SIZE, config.TILE_SIZE)                    

   
    def render_character_creation_screen(self):
        surf = self.screen
        SW, SH = surf.get_width(), surf.get_height()
 
        # ── Palette ───────────────────────────────────────────────────────
        BG      = (10,   8,  10)
        PANEL   = (18,  14,  18)
        BORDER  = (52,  42,  46)
        GOLD    = (164, 124,  52)
        ACCENT  = (96,  38,  38)
        DIM     = (112, 102,  96)
        NORMAL  = (188, 178, 168)
        BRIGHT  = (232, 224, 210)
        GREEN   = (74,  122,  76)
        CYAN    = (72,  132, 136)
        RED     = (148,  42,  42)
 
        def ff(sz, bold=False):
            try:    return pygame.font.SysFont("consolas", sz, bold=bold)
            except: return pygame.font.Font(None, sz + 2)
 
        fTitle = ff(22, bold=True)
        fSec   = ff(18, bold=True)
        fN     = ff(16)
        fSm    = ff(14)
 
        surf.fill(BG)
 
        # Outer panel
        PAD   = 20
        panel = pygame.Rect(PAD, PAD, SW - PAD * 2, SH - PAD * 2)
        pygame.draw.rect(surf, PANEL, panel, border_radius=8)
        pygame.draw.rect(surf, BORDER, panel, 1, border_radius=8)
 
        # Title bar
        title_bar = pygame.Rect(PAD, PAD, SW - PAD * 2, 42)
        pygame.draw.rect(surf, (22, 18, 28), title_bar, border_radius=8)
        pygame.draw.rect(surf, ACCENT, title_bar, 1, border_radius=8)
        ts = fTitle.render("CHOOSE YOUR RACE & LINEAGE", True, GOLD)
        surf.blit(ts, (SW // 2 - ts.get_width() // 2, PAD + 10))
 
        content_y = PAD + 52
        content_h = SH - content_y - PAD - 36
 
        # Three equal columns
        COL_PAD = 10
        col_w   = (SW - PAD * 2 - COL_PAD * 4) // 3
        col1_x  = PAD + COL_PAD                    # race groups
        col2_x  = col1_x + col_w + COL_PAD         # lineages + preview
        col3_x  = col2_x + col_w + COL_PAD         # lineage details
 
        for cx in (col1_x, col2_x, col3_x):
            r = pygame.Rect(cx - 4, content_y, col_w + 8, content_h)
            pygame.draw.rect(surf, (20, 18, 26), r, border_radius=6)
            pygame.draw.rect(surf, BORDER, r, 1, border_radius=6)
 
        # Current selections
        sel_group   = self.selected_group_index
        sel_lineage = self.selected_lineage_index
        group_label, group_color, lineages = self.race_groups[sel_group]
        sel_lineage = max(0, min(sel_lineage, len(lineages) - 1))
        selected_race = lineages[sel_lineage]
 
        selected_class_cls = self.available_classes[self.selected_class_index]
        class_str  = selected_class_cls.__name__
        race_key   = selected_race.name
        player_char, player_color = self.race_class_visuals.get(
            (race_key, class_str), ('@', (200, 200, 200))
        )
 
        # ── COLUMN 1 : Race Groups ────────────────────────────────────────
        y1 = content_y + 10
        pygame.draw.rect(surf, ACCENT, (col1_x, y1 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render("RACES", True, BRIGHT), (col1_x + 8, y1))
        pygame.draw.line(surf, BORDER,
                         (col1_x, y1 + fSec.get_linesize() + 3),
                         (col1_x + col_w, y1 + fSec.get_linesize() + 3), 1)
        y1 += fSec.get_linesize() + 10
 
        for gi, (glabel, gcolor, glineages) in enumerate(self.race_groups):
            sel    = (gi == sel_group)
            row_h  = fN.get_linesize() + 10
            row_r  = pygame.Rect(col1_x - 2, y1, col_w + 4, row_h)
            if sel:
                pygame.draw.rect(surf, (28, 38, 55), row_r, border_radius=4)
                pygame.draw.rect(surf, ACCENT, row_r, 1, border_radius=4)
                pygame.draw.rect(surf, gcolor, (col1_x - 2, y1 + 4, 3, row_h - 8))
 
            label_color = gcolor if sel else NORMAL
            ns = fN.render(glabel, True, label_color)
            surf.blit(ns, (col1_x + 10, y1 + row_h // 2 - ns.get_height() // 2))
 
            # Sub-count badge
            badge = fSm.render(f"×{len(glineages)}", True, DIM)
            surf.blit(badge, (col1_x + col_w - badge.get_width() - 6,
                              y1 + row_h // 2 - badge.get_height() // 2))
            y1 += row_h + 4
 
        # Lineage picker hint inside col 1 footer
        hint = fSm.render("◄ ► cycle lineage", True, DIM)
        surf.blit(hint, (col1_x + col_w // 2 - hint.get_width() // 2,
                         content_y + content_h - fSm.get_linesize() - 8))
 
        # ── COLUMN 2 : Lineage list  +  avatar preview ────────────────────
        cx2 = col2_x + col_w // 2
        y2  = content_y + 10
 
        # Section header
        pygame.draw.rect(surf, ACCENT, (col2_x, y2 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render(group_label.upper() + " LINEAGES", True, BRIGHT),
                  (col2_x + 8, y2))
        pygame.draw.line(surf, BORDER,
                         (col2_x, y2 + fSec.get_linesize() + 3),
                         (col2_x + col_w, y2 + fSec.get_linesize() + 3), 1)
        y2 += fSec.get_linesize() + 10
 
        for li, lineage in enumerate(lineages):
            sel    = (li == sel_lineage)
            row_h  = fN.get_linesize() + 10
            row_r  = pygame.Rect(col2_x - 2, y2, col_w + 4, row_h)
            if sel:
                pygame.draw.rect(surf, (28, 38, 55), row_r, border_radius=4)
                pygame.draw.rect(surf, ACCENT, row_r, 1, border_radius=4)
                pygame.draw.rect(surf, group_color,
                                 (col2_x - 2, y2 + 4, 3, row_h - 8))
 
            lname  = lineage.name
            lcolor = group_color if sel else NORMAL
            ns = fN.render(lname, True, lcolor)
            surf.blit(ns, (col2_x + 10, y2 + row_h // 2 - ns.get_height() // 2))
 
            # Darkvision badge
            if lineage.darkvision_radius > 0:
                dv = fSm.render(f"DV {lineage.darkvision_radius}", True, CYAN)
                surf.blit(dv, (col2_x + col_w - dv.get_width() - 6,
                               y2 + row_h // 2 - dv.get_height() // 2))
            y2 += row_h + 4
 
        # Avatar preview (centred in remaining column 2 space)
        AVATAR = 72
        try:
            base   = graphics.get_tile_surface(player_char)
            avatar = pygame.transform.scale(base, (AVATAR, AVATAR)) if base else None
        except Exception:
            avatar = None
 
        av_y = content_y + content_h - AVATAR - 40
        av_x = cx2 - AVATAR // 2
        r2, g2, b2 = player_color
 
        glow_s = pygame.Surface((AVATAR + 16, AVATAR + 16), pygame.SRCALPHA)
        pygame.draw.rect(glow_s, (r2, g2, b2, 40),  (0, 0, AVATAR+16, AVATAR+16), border_radius=10)
        pygame.draw.rect(glow_s, (r2, g2, b2, 100), (0, 0, AVATAR+16, AVATAR+16), 2, border_radius=10)
        surf.blit(glow_s, (av_x - 8, av_y - 8))
        if avatar:
            surf.blit(avatar, (av_x, av_y))
        else:
            pygame.draw.rect(surf, player_color, (av_x, av_y, AVATAR, AVATAR), border_radius=6)
        pygame.draw.rect(surf, BORDER, (av_x - 3, av_y - 3, AVATAR + 6, AVATAR + 6), 1, border_radius=7)
 
        lbl = fSm.render(f"{selected_race.name}  ·  {class_str}", True, player_color)
        surf.blit(lbl, (cx2 - lbl.get_width() // 2, av_y + AVATAR + 6))
 
        # ── COLUMN 3 : Selected lineage details ───────────────────────────
        y3 = content_y + 10
 
        def hdr3(label, yy):
            pygame.draw.rect(surf, ACCENT, (col3_x, yy + 2, 3, fSec.get_linesize() - 2))
            surf.blit(fSec.render(label, True, BRIGHT), (col3_x + 8, yy))
            pygame.draw.line(surf, BORDER,
                             (col3_x, yy + fSec.get_linesize() + 3),
                             (col3_x + col_w, yy + fSec.get_linesize() + 3), 1)
            return yy + fSec.get_linesize() + 10
 
        def wrap3(text, color, yy):
            words = text.split()
            lines, cur = [], []
            for w in words:
                test = " ".join(cur + [w])
                if fSm.size(test)[0] <= col_w - 8:
                    cur.append(w)
                else:
                    if cur: lines.append(" ".join(cur))
                    cur = [w]
            if cur: lines.append(" ".join(cur))
            for line in lines:
                surf.blit(fSm.render(line, True, color), (col3_x + 4, yy))
                yy += fSm.get_linesize() + 2
            return yy + 4
 
        def trait_row(label, value, color, yy):
            surf.blit(fSm.render(label, True, DIM), (col3_x + 4, yy))
            vs = fSm.render(str(value), True, color)
            surf.blit(vs, (col3_x + col_w - vs.get_width() - 4, yy))
            pygame.draw.line(surf, BORDER,
                             (col3_x + 4,           yy + fSm.get_linesize() + 2),
                             (col3_x + col_w - 4,   yy + fSm.get_linesize() + 2), 1)
            return yy + fSm.get_linesize() + 6
 
        y3 = hdr3(f"{selected_race.name.upper()}  DETAILS", y3)
        y3 = wrap3(selected_race.description, NORMAL, y3)
        y3 += 6
        y3 = hdr3("TRAITS", y3)
 
        if selected_race.darkvision_radius > 0:
            label = "Superior Darkvision" if selected_race.darkvision_radius >= 12 else "Darkvision"
            y3 = trait_row(label, f"{selected_race.darkvision_radius} tiles", CYAN, y3)
        if selected_race.damage_resistances:
            y3 = trait_row("Resistances", ", ".join(selected_race.damage_resistances), GREEN, y3)
        if selected_race.skill_proficiencies:
            y3 = trait_row("Skill Prof.", ", ".join(selected_race.skill_proficiencies), NORMAL, y3)
        if selected_race.weapon_proficiencies:
            y3 = trait_row("Weapon Prof.", ", ".join(selected_race.weapon_proficiencies), NORMAL, y3)
        if selected_race.armor_proficiencies:
            y3 = trait_row("Armor Prof.", ", ".join(selected_race.armor_proficiencies), NORMAL, y3)
 
        if not any([selected_race.darkvision_radius, selected_race.damage_resistances,
                    selected_race.skill_proficiencies, selected_race.weapon_proficiencies,
                    selected_race.armor_proficiencies]):
            surf.blit(fSm.render("No special traits.", True, DIM), (col3_x + 4, y3))
 
        # ── Instructions bar ──────────────────────────────────────────────
        iy   = SH - PAD - fSm.get_linesize() - 8
        inst = fSm.render(
            "W/S  select race group     ◄/►  cycle lineage     Enter  confirm",
            True, DIM
        )
        surf.blit(inst, (SW // 2 - inst.get_width() // 2, iy))


    def _draw_wrapped_and_update_y_menu(self, surface, font, text, color, x, y_start, max_width):
        """Wraps text and draws it on the surface, updating the y position."""
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:  # Check if the line fits within the max width
                current_line.append(word)
            else:
                if current_line:  # If there's a current line, add it to lines
                    lines.append(' '.join(current_line))
                current_line = [word]  # Start a new line with the current word

        if current_line:  # Add the last line if it exists
            lines.append(' '.join(current_line))

        # Draw each line and update the y position
        y_offset = y_start
        for line in lines:
            self._draw_text(surface, font, line, color, x, y_offset)
            y_offset += font.get_linesize() + 2  # Add some spacing between lines

        return y_offset  # Return the new y position


    def render_class_selection_screen(self):
        surf = self.screen
        SW, SH = surf.get_width(), surf.get_height()

        _BG     = (10,   8,  10)   # abyss black
        _PANEL  = (18,  14,  18)   # obsidian stone

        _BORDER = (52,  42,  46)   # dark iron

        _GOLD   = (164, 124,  52)  # tarnished relic gold
        _ACCENT = (96,  38,  38)   # dried blood crimson

        _DIM    = (112, 102,  96)  # dusty parchment
        _NORMAL = (188, 178, 168)  # aged bone
        _BRIGHT = (232, 224, 210)  # candlelit ivory

        _GREEN  = (74, 122,  76)   # swamp herb green
        _CYAN   = (72, 132, 136)   # spectral teal
        _RED    = (148,  42,  42)  # coagulated blood

        _ORANGE = (176,  96,  42)  # ember flame

        def _ff(sz, bold=False):
            try:    return pygame.font.SysFont("consolas", sz, bold=bold)
            except: return pygame.font.Font(None, sz + 2)

        fTitle = _ff(22, bold=True)
        fSec   = _ff(18, bold=True)
        fN     = _ff(16)
        fSm    = _ff(14)

        surf.fill(_BG)

        PAD = 20
        panel = pygame.Rect(PAD, PAD, SW - PAD*2, SH - PAD*2)
        pygame.draw.rect(surf, _PANEL, panel, border_radius=8)
        pygame.draw.rect(surf, _BORDER, panel, 1, border_radius=8)

        title_bar = pygame.Rect(PAD, PAD, SW - PAD*2, 42)
        pygame.draw.rect(surf, (22, 18, 28), title_bar, border_radius=8)
        pygame.draw.rect(surf, _ACCENT, title_bar, 1, border_radius=8)
        ts = fTitle.render("CHOOSE YOUR CLASS", True, _GOLD)
        surf.blit(ts, (SW // 2 - ts.get_width() // 2, PAD + 10))

        content_y = PAD + 52
        content_h = SH - content_y - PAD - 36

        COL_PAD = 10
        col_w   = (SW - PAD*2 - COL_PAD*4) // 3
        col1_x  = PAD + COL_PAD
        col2_x  = col1_x + col_w + COL_PAD
        col3_x  = col2_x + col_w + COL_PAD

        for cx in (col1_x, col2_x, col3_x):
            r = pygame.Rect(cx - 4, content_y, col_w + 8, content_h)
            pygame.draw.rect(surf, (20, 18, 26), r, border_radius=6)
            pygame.draw.rect(surf, _BORDER, r, 1, border_radius=6)

        selected_race      = self.available_races[self.selected_race_index]
        selected_class_cls = self.available_classes[self.selected_class_index]
        race_str   = selected_race.name  # keep spaces to match race_class_visuals keys
        class_str  = selected_class_cls.__name__
        player_char, player_color = self.race_class_visuals.get(
            (race_str, class_str), ('@', (200, 200, 200))
        )
        class_info = self._get_class_details(selected_class_cls)

        # class colour theme per class
        class_color_map = {
            "Fighter": (180,  80,  80),
            "Rogue":   ( 80, 160,  80),
            "Wizard":  ( 80, 130, 220),
            "Cleric":  (220, 200,  60),
        }
        class_color = class_color_map.get(class_str, _GOLD)

        # ── COLUMN 1: Class list ─────────────────────────────────────────────
        y1 = content_y + 10
        pygame.draw.rect(surf, _ACCENT, (col1_x, y1 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render("CLASSES", True, _BRIGHT), (col1_x + 8, y1))
        pygame.draw.line(surf, _BORDER, (col1_x, y1 + fSec.get_linesize() + 3),
                         (col1_x + col_w, y1 + fSec.get_linesize() + 3), 1)
        y1 += fSec.get_linesize() + 10

        hit_die_map  = {"Fighter": 10, "Rogue": 8, "Wizard": 6, "Cleric": 8}
        for i, cls in enumerate(self.available_classes):
            sel   = (i == self.selected_class_index)
            cname = cls.__name__
            row_h = fN.get_linesize() + 10
            row_r = pygame.Rect(col1_x - 2, y1, col_w + 4, row_h)
            ccol  = class_color_map.get(cname, _GOLD)
            if sel:
                pygame.draw.rect(surf, (28, 38, 55), row_r, border_radius=4)
                pygame.draw.rect(surf, _ACCENT, row_r, 1, border_radius=4)
                pygame.draw.rect(surf, ccol, (col1_x - 2, y1 + 4, 3, row_h - 8))
            ns = fN.render(cname, True, ccol if sel else _NORMAL)
            surf.blit(ns, (col1_x + 10, y1 + row_h // 2 - ns.get_height() // 2))
            hd = fSm.render(f"d{hit_die_map.get(cname, 8)}", True, _DIM)
            surf.blit(hd, (col1_x + col_w - hd.get_width() - 6,
                           y1 + row_h // 2 - hd.get_height() // 2))
            y1 += row_h + 4

        # ── COLUMN 2: Character doll ─────────────────────────────────────────
        cx2 = col2_x + col_w // 2
        y2  = content_y + 18

        pygame.draw.rect(surf, _ACCENT, (col2_x, y2 + 2, 3, fSec.get_linesize() - 2))
        surf.blit(fSec.render("PREVIEW", True, _BRIGHT), (col2_x + 8, y2))
        pygame.draw.line(surf, _BORDER, (col2_x, y2 + fSec.get_linesize() + 3),
                         (col2_x + col_w, y2 + fSec.get_linesize() + 3), 1)
        y2 += fSec.get_linesize() + 14

        AVATAR = 96
        try:
            base   = graphics.get_tile_surface(player_char)
            avatar = pygame.transform.scale(base, (AVATAR, AVATAR)) if base else None
        except Exception:
            avatar = None

        av_x = cx2 - AVATAR // 2
        av_y = y2
        r2, g2, b2 = player_color

        glow_s = pygame.Surface((AVATAR + 16, AVATAR + 16), pygame.SRCALPHA)
        pygame.draw.rect(glow_s, (r2, g2, b2, 40), (0, 0, AVATAR+16, AVATAR+16), border_radius=10)
        pygame.draw.rect(glow_s, (r2, g2, b2, 100), (0, 0, AVATAR+16, AVATAR+16), 2, border_radius=10)
        surf.blit(glow_s, (av_x - 8, av_y - 8))

        if avatar:
            tinted = avatar.copy()
            surf.blit(tinted, (av_x, av_y))
        else:
            pygame.draw.rect(surf, player_color, (av_x, av_y, AVATAR, AVATAR), border_radius=6)

        pygame.draw.rect(surf, _BORDER, (av_x - 3, av_y - 3, AVATAR + 6, AVATAR + 6), 1, border_radius=7)
        y2 += AVATAR + 10

        # race · class label in class colour
        lbl = fN.render(f"{selected_race.name}  ·  {class_str}", True, class_color)
        surf.blit(lbl, (cx2 - lbl.get_width() // 2, y2))
        y2 += fN.get_linesize() + 12

        # starting weapon/armor icons
        icon_chars = {
            "Fighter": ["shs", "rsh"],
            "Rogue":   ["dgr", "pda"],
            "Wizard":  ["spb", "!"],
            "Cleric":  ["shs", "cha"],
        }
        icons = icon_chars.get(class_str, [])
        ICON  = 36
        ix    = cx2 - (len(icons) * (ICON + 6)) // 2
        for ic in icons:
            try:
                base2 = graphics.get_tile_surface(ic)
                if base2:
                    s2 = pygame.transform.scale(base2, (ICON, ICON))
                    surf.blit(s2, (ix, y2))
            except Exception:
                pass
            pygame.draw.rect(surf, _BORDER, (ix - 2, y2 - 2, ICON + 4, ICON + 4), 1, border_radius=3)
            ix += ICON + 8
        y2 += ICON + 10

        # stat bars
        est_hp = hit_die_map.get(class_str, 8) + 2
        BAR_W  = col_w - 20
        BAR_H  = 10
        bx     = col2_x + 10

        def _mini_bar(label, val, max_val, fc, yy):
            surf.blit(fSm.render(label, True, _DIM), (bx, yy))
            yy += fSm.get_linesize() + 3
            pygame.draw.rect(surf, (30, 30, 40), (bx, yy, BAR_W, BAR_H), border_radius=3)
            fw = max(0, int(BAR_W * min(val / max_val, 1.0)))
            if fw: pygame.draw.rect(surf, fc, (bx, yy, fw, BAR_H), border_radius=3)
            pygame.draw.rect(surf, _BORDER, (bx, yy, BAR_W, BAR_H), 1, border_radius=3)
            vs3 = fSm.render(str(val), True, _BRIGHT)
            surf.blit(vs3, (bx + BAR_W//2 - vs3.get_width()//2, yy + BAR_H//2 - vs3.get_height()//2))
            return yy + BAR_H + 8

        hp_col = _RED if est_hp < 7 else (_GOLD if est_hp < 10 else _GREEN)
        y2 = _mini_bar(f"Est. HP  ({class_info['hit_die']})", est_hp, 14, hp_col, y2)
        y2 = _mini_bar("Primary Ability", 1, 1, class_color, y2)
        # primary ability label
        pa = fSm.render(class_info["primary_ability"], True, class_color)
        surf.blit(pa, (cx2 - pa.get_width() // 2, y2))

        # ── COLUMN 3: Class details ───────────────────────────────────────────
        y3 = content_y + 10

        def _hdr3(label, yy):
            pygame.draw.rect(surf, _ACCENT, (col3_x, yy + 2, 3, fSec.get_linesize() - 2))
            surf.blit(fSec.render(label, True, _BRIGHT), (col3_x + 8, yy))
            pygame.draw.line(surf, _BORDER, (col3_x, yy + fSec.get_linesize() + 3),
                             (col3_x + col_w, yy + fSec.get_linesize() + 3), 1)
            return yy + fSec.get_linesize() + 10

        def _wrap3(text, color, yy):
            words = text.split()
            lines2, cur = [], []
            for w in words:
                test = " ".join(cur + [w])
                if fSm.size(test)[0] <= col_w - 8:
                    cur.append(w)
                else:
                    if cur: lines2.append(" ".join(cur))
                    cur = [w]
            if cur: lines2.append(" ".join(cur))
            for line in lines2:
                surf.blit(fSm.render(line, True, color), (col3_x + 4, yy))
                yy += fSm.get_linesize() + 2
            return yy + 4

        def _row3(label, value, color, yy):
            surf.blit(fSm.render(label, True, _DIM), (col3_x + 4, yy))
            vs4 = fSm.render(str(value), True, color)
            surf.blit(vs4, (col3_x + col_w - vs4.get_width() - 4, yy))
            pygame.draw.line(surf, _BORDER,
                             (col3_x + 4, yy + fSm.get_linesize() + 2),
                             (col3_x + col_w - 4, yy + fSm.get_linesize() + 2), 1)
            return yy + fSm.get_linesize() + 6

        y3 = _hdr3(f"{class_str.upper()}  DETAILS", y3)
        y3 = _wrap3(class_info["description"], _NORMAL, y3)
        y3 += 6
        y3 = _hdr3("KEY FEATURES", y3)
        y3 = _row3("Hit Die",          class_info["hit_die"],          class_color, y3)
        y3 = _row3("Primary Ability",  class_info["primary_ability"],  class_color, y3)
        if class_info["saving_throws"]:
            y3 = _row3("Saving Throws", ", ".join(class_info["saving_throws"]), _NORMAL, y3)
        if class_info["armor_proficiencies"]:
            y3 = _row3("Armor Prof.",   ", ".join(class_info["armor_proficiencies"]), _NORMAL, y3)
        if class_info["weapon_proficiencies"]:
            y3 = _row3("Weapon Prof.",  ", ".join(class_info["weapon_proficiencies"]), _NORMAL, y3)

        if class_info.get("starting_equipment"):
            y3 += 4
            y3 = _hdr3("STARTING GEAR", y3)
            for eq_item in class_info["starting_equipment"]:
                y3 = _wrap3(f"· {eq_item}", _DIM, y3)

        # ── Instructions ─────────────────────────────────────────────────────
        iy = SH - PAD - fSm.get_linesize() - 8
        inst = fSm.render("W / S  navigate      Enter  confirm      Backspace  back to race", True, _DIM)
        surf.blit(inst, (SW // 2 - inst.get_width() // 2, iy))

    def _get_class_details(self, class_constructor):
        """
        Returns a dictionary of details for a given class constructor.
        You will need to expand this with actual data for each class.
        """
        # Create a dummy instance to access class attributes
        dummy_instance = class_constructor(0, 0, '@', 'Dummy', (255, 255, 255))

        # Get the class name from the constructor
        selected_class_name = dummy_instance.class_name  # Assuming class_name is set in the class constructor

        details = {
            "Fighter": {
                "description": "A master of martial combat, skilled with a variety of weapons and armor. Fighters are versatile warriors who can specialize in offense or defense.",
                "hit_die": "1d10",
                "primary_ability": "Strength or Dexterity",
                "saving_throws": ["Strength", "Constitution"],
                "armor_proficiencies": ["Light", "Medium", "Heavy", "Shields"],
                "weapon_proficiencies": ["Simple", "Martial"],
                "starting_equipment": ["Chain mail", "A martial weapon and a shield", "A light crossbow and 20 bolts", "An explorer's pack"]
            },
            "Rogue": {
                "description": "A master of stealth, cunning, and trickery. Rogues excel at striking from the shadows and disarming traps.",
                "hit_die": "1d8",
                "primary_ability": "Dexterity",
                "saving_throws": ["Dexterity", "Intelligence"],
                "armor_proficiencies": ["Light"],
                "weapon_proficiencies": ["Simple", "Hand crossbows", "Longswords", "Rapiers", "Shortswords"],
                "starting_equipment": ["A rapier", "A shortbow and quiver of 20 arrows", "A burglar's pack", "Leather armor", "Two daggers", "Thieves' tools"]
            },
            "Wizard": {
                "description": "A scholarly magic-user capable of manipulating the fabric of reality. Wizards wield powerful spells learned from ancient tomes.",
                "hit_die": "1d6",
                "primary_ability": "Intelligence",
                "saving_throws": ["Intelligence", "Wisdom"],
                "armor_proficiencies": ["None"],
                "weapon_proficiencies": ["Daggers", "Darts", "Slings", "Quarterstaffs", "Light crossbows"],
                "starting_equipment": ["A quarterstaff", "A component pouch", "A scholar's pack", "A spellbook"]
            },
            "Cleric": {
                "description": "A priestly champion who wields divine magic in service of a higher power. Clerics can heal wounds, turn undead, and call down divine wrath.",
                "hit_die": "1d8",
                "primary_ability": "Wisdom",
                "saving_throws": ["Wisdom", "Charisma"],
                "armor_proficiencies": ["Light", "Medium", "Shields"],
                "weapon_proficiencies": ["Simple"],
                "starting_equipment": ["A mace", "Scale mail", "A light crossbow and 20 bolts", "A priest's pack", "A shield emblazoned with the symbol of their deity"]
            },
            "Sorcerer": {
                "description": "A spellcaster who draws on inherent magic from a powerful bloodline. Sorcerers have a limited number of spells but can cast them with great flexibility.",
                "hit_die": "1d6",
                "primary_ability": "Charisma",
                "saving_throws": ["Constitution", "Charisma"],
                "armor_proficiencies": ["None"],
                "weapon_proficiencies": ["Daggers", "Darts", "Slings", "Quarterstaffs", "Light crossbows"],
                "starting_equipment": ["A quarterstaff", "A component pouch", "A scholar's pack", "A spellbook"]
            }
        }
        # Return specific details for the class, or a generic message if not found
        return details.get(selected_class_name, {
            "description": "No detailed description available for this class.",
            "hit_die": "N/A",
            "primary_ability": "N/A",
            "saving_throws": [],
            "armor_proficiencies": [],
            "weapon_proficiencies": [],
            "starting_equipment": []
        })
    

    def render_inventory_screen(self):
        render_inventory_screen(self)
            
    def render_inventory_menu_popup(self):
        render_inventory_menu_popup(self)

    def render_character_menu(self):
        render_character_menu(self)


    def _draw_text(self, target_surface, font, text, color, x, y):
        text_surface = font.render(text, True, color)
        target_surface.blit(text_surface, (x, y))

    def _wrap_text(self, text, font, max_width):
        words = text.split(' ')
        lines = []
        
        if not words or (len(words) == 1 and not words[0]):
            return [""]

        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        return lines

    def _unequip_slot(self, slot_key):
        """Unequip item from the given slot key using the player's own unequip_item method."""
        slot_map = {
            "weapon":   "equipped_weapon",
            "armor":    "equipped_armor",
            "off_hand": "equipped_off_hand",
            "acc1":     "equipped_accessory1",
            "acc2":     "equipped_accessory2",
            "helmet":   "equipped_helmet",
            "boots":    "equipped_boots",
            "focus":    "equipped_focus",
        }
        attr = slot_map.get(slot_key)
        if not attr:
            return
        item = getattr(self.player, attr, None)
        if item is None:
            self.message_log.add_message("Nothing equipped in that slot.", (150, 150, 150))
            return
        self.player.unequip_item(item, self)




    def draw_ui(self):
        draw_sidebar(self)

    def draw_minimap(self):
        # Only rebuild the minimap surface when something relevant actually
        # changed (new tiles explored, map swapped, resize, etc). The player
        # marker moves every step though, so we still redraw when the
        # player's position has changed since the last rebuild, even if
        # minimap_needs_redraw itself wasn't set for that reason.
        player_pos = (self.player.x, self.player.y) if self.player else None
        needs_rebuild = (
            self.minimap_needs_redraw
            or player_pos != getattr(self, '_minimap_last_player_pos', None)
        )

        if needs_rebuild:
            self._rebuild_minimap_surface()
            self.minimap_needs_redraw = False
            self._minimap_last_player_pos = player_pos

        # Blit the (possibly cached) minimap surface to the screen every frame
        self.screen.blit(self.minimap_surface, self.minimap_rect.topleft)

    def _rebuild_minimap_surface(self):
        """Redraws self.minimap_surface from scratch. Only called when the
        minimap is actually dirty (see draw_minimap)."""

        # Fill with solid black background (opaque)
        self.minimap_surface.fill((0, 0, 0, 0))

        scale_x = self.minimap_surface.get_width() / self.game_map.width
        scale_y = self.minimap_surface.get_height() / self.game_map.height
        minimap_tile_scale = min(scale_x, scale_y)
        actual_minimap_tile_size = max(1, int(config.MINIMAP_TILE_SIZE * minimap_tile_scale))

        offset_x = (self.minimap_surface.get_width() - self.game_map.width * actual_minimap_tile_size) // 2
        offset_y = (self.minimap_surface.get_height() - self.game_map.height * actual_minimap_tile_size) // 2

        # Only iterate over explored tiles instead of the full map grid -
        # cheap early on, and stays cheap as explored area grows since this
        # now only runs when the minimap is dirty rather than every frame.
        for (x, y) in self.fov.explored:
            tile = self.game_map.tiles[y][x]
            color = tile.color if self.fov.get_visibility_type(x, y) in ['player', 'torch', 'darkvision'] else tile.dark_color
            pygame.draw.rect(
                self.minimap_surface,
                color,
                (offset_x + x * actual_minimap_tile_size,
                 offset_y + y * actual_minimap_tile_size,
                 actual_minimap_tile_size,
                 actual_minimap_tile_size)
            )

        for bloodstain in self.bloodstains:
            if (bloodstain.x, bloodstain.y) in self.fov.explored: # Only show on minimap if explored
                bloodstain_minimap_x = offset_x + bloodstain.x * actual_minimap_tile_size
                bloodstain_minimap_y = offset_y + bloodstain.y * actual_minimap_tile_size
                pygame.draw.rect(
                    self.minimap_surface,
                    (80, 10, 10), # Dark red for minimap bloodstains
                    (bloodstain_minimap_x, bloodstain_minimap_y, actual_minimap_tile_size, actual_minimap_tile_size)
                )

        if self.player:
            player_minimap_x = offset_x + self.player.x * actual_minimap_tile_size
            player_minimap_y = offset_y + self.player.y * actual_minimap_tile_size

            pygame.draw.rect(
                self.minimap_surface,
                (255, 178, 102),
                (player_minimap_x, player_minimap_y, actual_minimap_tile_size, actual_minimap_tile_size)
            )