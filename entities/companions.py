import random

from entities.summons import SummonedEntity, _chebyshev_distance, SUMMON_PATHFINDING_MAX_EXPANSIONS
from entities.monster import Monster
from core.pathfinding import astar
from core.floating_text import FloatingText
from items.items import (
    iron_short_sword, leather_boots, padded_armor, short_bow,
    iron_dagger, oak_staff, steel_mace, studded_leather_armor,
    chainmail_armor, robes, round_shield, spell_book, holy_symbol,
)
from core.status_effects import (
    BlessingOfBloodlust, BlessingOfFortitude, CurseOfRot, ParryBuff, StatusEffect, DivineStrikeBuff, Poisoned, 
    AcidBurned, PowerAttackBuff, CunningActionDashBuff, EvasionBuff, Burning, Torchlight, ActionSurgeEffect, Hidden, 
    CurseOfWeakness, CurseOfBlindness, BlessingOfAgility, BlessingOfStrength, GuardBuff, PreciseStrikeBuff, Prepared, 
    FleetFooted, AppliedToxins, SpotTrapsEffect, DetectMagicEffect, HunterMarkBuff
)

# ---------------------------------------------------------------------------
# XP progression
# ---------------------------------------------------------------------------
# Same D&D 5e XP table player.py's XP_PROGRESSION uses, duplicated here
# rather than imported -- companions.py's own stat formulas (see
# CombatCompanion._recalculate_stats()'s docstring) are already kept
# independent of player.py on purpose, so a companion's leveling curve
# stays that way too.
COMPANION_XP_PROGRESSION = {
    1: 0,
    2: 300,
    3: 900,
    4: 2700,
    5: 6500,
    6: 14000,
    7: 23000,
    8: 34000,
    9: 48000,
    10: 64000,
    11: 85000,
    12: 100000,
    13: 120000,
    14: 140000,
    15: 165000,
    16: 195000,
    17: 225000,
    18: 265000,
    19: 305000,
    20: 355000,
}


# ---------------------------------------------------------------------------
# Ambient chatter
# ---------------------------------------------------------------------------
# Generic flavor lines a CombatCompanion occasionally chimes in with while
# following the player around -- see CombatCompanion.speak_ambient() below.
# Not tied to race/class on purpose: a per-class/per-race pool would mean
# touching every existing CompanionClass definition just for flavor text,
# not worth the coupling for a purely cosmetic feature.
COMPANION_AMBIENT_LINES = [
    "Quiet stretch, this. I don't trust it.",
    "You hear that? ...No? Must've been nothing.",
    "I've fought worse than this. Probably.",
    "Lead on. I'll watch your back.",
    "Remind me why we're doing this again?",
    "Something about this place gives me the chills.",
    "Could use a hot meal after this.",
    "Careful of your footing up ahead.",
    "I've got a good feeling about today.",
    "Just say the word and I'll cut them down.",
    "Doesn't hurt to keep your guard up here.",
    "Almost peaceful... for now.",
]

#: Player turns the whole party's ambient chatter is silenced after any
#: one companion speaks -- see Game._companion_ambient_cooldown (game.py)
#: and speak_ambient() below. Shared across every companion rather than
#: tracked per-companion, so recruiting a full party doesn't multiply how
#: often chatter interrupts play: only one line comes through per
#: interval, whichever companion's turn happens to roll it first.
COMPANION_AMBIENT_COOLDOWN_TURNS = 6

#: Rolled once per companion, per turn, only once the shared cooldown
#: above has cleared -- keeps chatter sounding occasional and organic
#: rather than firing like clockwork the instant the cooldown hits zero.
COMPANION_AMBIENT_CHANCE = 0.08


# ---------------------------------------------------------------------------
# CompanionStance
# ---------------------------------------------------------------------------

class CompanionStance:
    """
    Player-selectable combat orders for a CombatCompanion (set via
    game.py's COMPANION_MENU). Plain string constants, same style as
    story_framework.py's StoryEvent/FailureMode -- no behavior lives on
    these; they're just the vocabulary CombatCompanion._select_target()
    and take_turn() switch on.
    """
    WEAKEST = "weakest"     # lowest current HP among valid targets
    NEAREST = "nearest"     # closest to the companion (default)
    FARTHEST = "farthest"   # farthest valid target still in range/LOS
    PROTECT = "protect"     # closest to the owner, not to the companion
    PASSIVE = "passive"     # never initiates attacks


# ---------------------------------------------------------------------------
# CompanionClass
# ---------------------------------------------------------------------------

class CompanionClass:
    """
    Static description of one companion "class" -- the equivalent of a
    Player subclass (Fighter, Rogue, ...) in player.py, but plain data
    instead of a class hierarchy, since a companion never needs the
    inventory/leveling-UI machinery a playable class carries. Adding a
    new class means adding one more instance below; CombatCompanion
    itself never needs to change.
    """

    def __init__(
        self,
        name,
        hit_die,
        ability_scores,
        primary_stat,
        combat_style,
        weapon,
        armor=None,
        off_hand=None,
        boots=None,
        focus=None,
        saving_throw_proficiencies=None,
        weapon_proficiencies=None,
        armor_proficiencies=None,
        damage_type="slashing",
        attack_range=1,
        starting_ammo=None,
        abilities=None,
    ):
        self.name = name
        self.hit_die = hit_die
        #: {"strength": 15, "dexterity": 13, ...} -- same shape every
        #: Player subclass hardcodes in its own __init__.
        self.ability_scores = dict(ability_scores)
        self.primary_stat = primary_stat

        #: "melee" or "ranged" -- decides which half of the (upcoming)
        #: combat AI a companion of this class runs.
        self.combat_style = combat_style

        #: Real Weapon/Armor/Boots/FocusItem instances from items.items,
        #: so AC and attack bonuses come from the same equipment data the
        #: player uses -- no parallel item system for companions.
        self.weapon = weapon
        self.armor = armor
        self.off_hand = off_hand
        self.boots = boots
        #: A FocusItem (spell_book, holy_symbol, ...) for Wizard/Cleric-
        #: style classes -- see CombatCompanion._recalculate_stats() for
        #: how its spell_bonus factors in. Companions don't have a
        #: separate spellcasting system yet, so this is a stand-in:
        #: a "caster" companion still just swings its weapon (a staff,
        #: a mace), with the focus nudging its effectiveness rather than
        #: unlocking real spells.
        self.focus = focus

        self.saving_throw_proficiencies = {
            "STR": False, "DEX": False, "CON": False,
            "INT": False, "WIS": False, "CHA": False,
        }

        self.weapon_proficiencies = list(weapon_proficiencies or [])
        self.armor_proficiencies = list(armor_proficiencies or [])

        #: Damage type logged/passed to take_damage() on a hit -- items.py's
        #: Weapon doesn't carry one, so it lives on the class instead
        #: (e.g. a sword class is "slashing", a bow class is "piercing").
        self.damage_type = damage_type

        #: 1 for melee (adjacency); a real tile radius for ranged
        #: classes, to also be checked against game.check_line_of_sight().
        self.attack_range = attack_range
        #: None for melee (unlimited attacks); a starting shot count for
        #: ranged classes -- see CombatCompanion.ammo.
        self.starting_ammo = starting_ammo

        self.abilities = {}

    def __repr__(self):
        return f"CompanionClass({self.name!r}, style={self.combat_style!r})"


#: A companion Fighter: heavy melee, high HP/AC, unlimited attacks -- the
#: sword-and-board frontliner. Equipment mirrors player.py's own Fighter
#: as closely as a companion's (currently helmet-less, off-hand-less)
#: equipment slots allow.
FIGHTER = CompanionClass(
    name="Fighter",
    hit_die=10,
    ability_scores={
        "strength": 15, "dexterity": 13, "constitution": 14,
        "intelligence": 8, "wisdom": 12, "charisma": 10,
    },
    primary_stat="strength",
    combat_style="melee",
    weapon=iron_short_sword,
    armor=padded_armor,
    boots=leather_boots,
    saving_throw_proficiencies = {
        "STR": True, "CON": True,
        "DEX": False, "INT": False, 
        "WIS": False, "CHA": False,
    },    
    weapon_proficiencies=["Shortsword", "Longsword", "Dagger", "Mace"],
    armor_proficiencies=["Light", "Medium", "Heavy"],
    damage_type="slashing",
    attack_range=1,
    
    abilities = {}
)

#: A companion Ranger: ranged skirmisher, armed with a real Short Bow
#: (items.py) now that bows/arrows exist. attack_range is a tile radius
#: for the AI's range+line-of-sight check below -- a separate,
#: game-balance concern from the bow's own damage_dice/attack_bonus.
RANGER = CompanionClass(
    name="Ranger",
    hit_die=8,
    ability_scores={
        "strength": 10, "dexterity": 16, "constitution": 12,
        "intelligence": 10, "wisdom": 14, "charisma": 8,
    },
    primary_stat="dexterity",
    combat_style="ranged",
    weapon=short_bow,
    armor=padded_armor,
    boots=leather_boots,
    saving_throw_proficiencies = {
        "STR": True, "DEX": True,
        "CON": False, "INT": False, 
        "WIS": False, "CHA": False,
    },    
    weapon_proficiencies=["Shortbow", "Longbow", "Hand Crossbow", "Dagger"],
    armor_proficiencies=["Light"],
    damage_type="piercing",
    attack_range=6,
    starting_ammo=24,    
    abilities = {}
)

#: A companion Rogue: a fast, finesse-fighting duelist -- adjacent
#: combat (no ranged AI/ammo needed for a thrown or melee dagger) but
#: with Dexterity, not Strength, as the primary stat, and a lighter
#: hit die/armor than Fighter to match.
ROGUE = CompanionClass(
    name="Rogue",
    hit_die=8,
    ability_scores={
        "strength": 10, "dexterity": 16, "constitution": 12,
        "intelligence": 12, "wisdom": 10, "charisma": 12,
    },
    primary_stat="dexterity",
    combat_style="melee",
    weapon=iron_dagger,
    armor=studded_leather_armor,
    boots=leather_boots,
    saving_throw_proficiencies = {
        "DEX": True, "INT": True,
        "STR": False, "CON": False, 
        "WIS": False, "CHA": False,
    },    
    weapon_proficiencies=["Dagger", "Shortsword", "Rapier", "Shortbow"],
    armor_proficiencies=["Light"],
    damage_type="piercing",
    attack_range=1,    
    abilities = {}
)

#: A companion Wizard: squishy and Intelligence-driven, wielding a
#: quarterstaff (already carries its own spell_bonus/attack_bonus in
#: items.py) plus a spell_book focus for a further boost. Companions
#: don't have real spellcasting yet -- see CompanionClass.focus's
#: docstring -- so this is "a battle-mage swinging a staff, backed by
#: a grimoire" rather than an actual spellcaster, until that system
#: exists.
WIZARD = CompanionClass(
    name="Wizard",
    hit_die=6,
    ability_scores={
        "strength": 8, "dexterity": 12, "constitution": 12,
        "intelligence": 16, "wisdom": 10, "charisma": 10,
    },
    primary_stat="intelligence",
    combat_style="melee",
    weapon=oak_staff,
    armor=robes,
    boots=leather_boots,
    focus=spell_book,
    saving_throw_proficiencies = {
        "INT": True, "WIS": True,
        "STR": False, "DEX": False, 
        "CON": False, "CHA": False,
    },
    weapon_proficiencies=["Quarterstaff", "Dagger"],
    armor_proficiencies=["Light"],
    damage_type="bludgeoning",
    attack_range=1,    
    abilities = {}
)

#: A companion Cleric: a Wisdom-driven frontline healer/support
#: archetype -- mace and shield, medium armor, a holy_symbol focus.
#: The round_shield's ac_bonus (and any future off-hand attack_bonus
#: penalty on a heavier shield) is what motivated
#: CombatCompanion._recalculate_stats() picking up off_hand's own
#: attack_bonus, not just its ac_bonus.
CLERIC = CompanionClass(
    name="Cleric",
    hit_die=8,
    ability_scores={
        "strength": 13, "dexterity": 10, "constitution": 13,
        "intelligence": 10, "wisdom": 16, "charisma": 10,
    },
    primary_stat="wisdom",
    combat_style="melee",
    weapon=steel_mace,
    armor=chainmail_armor,
    off_hand=round_shield,
    boots=leather_boots,
    focus=holy_symbol,
    saving_throw_proficiencies = {
        "WIS": True, "CHA": True,
        "STR": False, "DEX": False, 
        "CON": False, "INT": False,
    },
    weapon_proficiencies=["Mace", "Hammer"],
    armor_proficiencies=["Light", "Medium"],
    damage_type="bludgeoning",
    attack_range=1,    
    abilities = {}
)


# ---------------------------------------------------------------------------
# RACE_CLASS_VISUALS
# ---------------------------------------------------------------------------

#: (race name, class name) -> (char, color) -- the shared "what does an
#: adventurer of this race+class look like" table. Lives here rather than
#: in game.py (its original home) because it's used by two independent
#: things that shouldn't have to import all of game.py to get at it:
#:   - game.py's own character creation, which sets self.race_class_visuals
#:     = RACE_CLASS_VISUALS and looks it up exactly as before.
#:   - world/structures.py's tavern patrons (see _spawn_tavern_patron()),
#:     which give a would-be CombatCompanion recruit the same race/class
#:     sprite the player themselves could have chosen, rather than a
#:     generic Townsfolk look -- tavern patrons ARE the recruitable pool.
#: race/class name strings match races.py's Race.name and each Player
#: subclass's __name__ (e.g. "Drow Elf" / "Fighter") -- not every
#: CompanionClass above has a matching entry yet (only Fighter/Rogue/
#: Wizard/Cleric are covered; Ranger's own visual entry is a follow-up),
#: since this table predates the CompanionClass catalogue and was only
#: ever driven by which Player subclasses exist.
RACE_CLASS_VISUALS = {
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

# Ranger doesn't have its own visuals yet -- reuse each race's Rogue
# sprite as a placeholder so a Ranger CombatCompanion/tavern patron
# still renders something sensible instead of falling back to the
# generic '@' white default. Swap in real Ranger entries above once
# they're designed; every consumer just does
# RACE_CLASS_VISUALS.get((race, class_name)), so nothing else needs to
# change when that happens -- this block can simply be deleted.
RACE_CLASS_VISUALS.update({
    (race, "Ranger"): visual
    for (race, class_name), visual in list(RACE_CLASS_VISUALS.items())
    if class_name == "Rogue"
})


# ---------------------------------------------------------------------------
# CombatCompanion
# ---------------------------------------------------------------------------

class CombatCompanion(SummonedEntity):
    """
    A recruited ally that actually fights -- built from a race
    (races.py) and a CompanionClass (above), the same two ingredients a
    player character is built from.

    Construction happens in two steps, mirroring character creation in
    game.py (start_game() sets up a fresh Player, *then* calls
    self.player.race.apply_traits(self.player, self) -- see game.py's
    apply_traits() call site):

        companion = CombatCompanion(x, y, name, color, owner, race, RANGER)
        companion.apply_race(game_instance)   # racial bonuses + logging

    Splitting it this way -- rather than requiring a Game instance up
    front in __init__ -- keeps a companion constructible before one
    exists (tests, tooling) and matches the existing player-creation
    call order exactly.
    """

    #: Same reasoning as EscortCompanion.FOLLOW_DISTANCE -- how close a
    #: companion tries to stay to its owner before pathfinding closer.
    FOLLOW_DISTANCE = 1

    #: How far (in tiles) a companion will voluntarily leave its owner
    #: to chase down a target -- mirrors Imp/Celestial's hardcoded 8.
    DETECTION_RADIUS = 6

    _ability_name_map = {
        "STR": "strength",
        "DEX": "dexterity",
        "CON": "constitution",
        "INT": "intelligence",
        "WIS": "wisdom",
        "CHA": "charisma",
    }

    def __init__(self, x, y, name, color, owner, race, companion_class, level=6, char=None):
        # `char` defaults to whatever RACE_CLASS_VISUALS says this
        # race+class combo looks like (the same table world/structures.py's
        # _spawn_tavern_patron() draws from) rather than a fixed 'C' --
        # a recruited patron should keep looking like the adventurer it
        # was in the tavern, not turn into a generic companion glyph.
        # Callers that already know the exact sprite (e.g. game.py's
        # recruit_combat_companion(), reusing the patron's own .char)
        # can still pass it through explicitly.
        if char is None:
            visual = RACE_CLASS_VISUALS.get((getattr(race, 'name', None), companion_class.name))
            char = visual[0] if visual else companion_class.name[0]

        # duration=0 -> permanent until dismissed or killed, same as
        # EscortCompanion; a recruited companion doesn't expire on a timer.
        super().__init__(x, y, char, name, color, owner, duration=0)

        # SummonedEntity.__init__ just set self.hp/self.max_hp to a
        # placeholder of 1, meant for stat-less summons that never call
        # _recalculate_stats() below. Clear it back to None here so that
        # first call sees old_hp=None and heals to the freshly computed
        # max_hp -- otherwise it reads the placeholder 1 as "real prior
        # damage to preserve" and clamps the companion to 1 HP forever,
        # even immediately after being recruited at full health.
        self.hp = None

        self.race = race
        self.companion_class = companion_class
        self.level = level
        self.current_xp = 0  # See gain_xp()/level_up() below
        self.blocks_movement = True  # Unlike EscortCompanion, a fighter takes up space
        self.can_swim = getattr(race, 'can_swim', False)
        self.active_status_effects = []  # AC/status-effect hooks expect this list to exist

        # Combat orders -- see CompanionStance. NEAREST matches
        # Imp/Celestial's existing hardcoded behavior, so a freshly
        # recruited companion behaves like every other combat summon
        # already does until the player changes it via COMPANION_MENU.
        self.stance = CompanionStance.NEAREST

        # -- Ability scores (base values; apply_race() below adds racial bonuses) --
        self.strength = companion_class.ability_scores["strength"]
        self.dexterity = companion_class.ability_scores["dexterity"]
        self.constitution = companion_class.ability_scores["constitution"]
        self.intelligence = companion_class.ability_scores["intelligence"]
        self.wisdom = companion_class.ability_scores["wisdom"]
        self.charisma = companion_class.ability_scores["charisma"]
        self.primary_stat = companion_class.primary_stat

        # -- Proficiencies / darkvision / resistances -- attributes
        # Race.apply_traits() writes to directly (see races.py); these
        # must exist before apply_race() runs, exactly like Player.__init__
        # sets them up before character creation calls apply_traits().
        self.class_weapon_proficiencies = list(companion_class.weapon_proficiencies)
        self.class_armor_proficiencies = list(companion_class.armor_proficiencies)
        self.weapon_proficiencies = self.class_weapon_proficiencies.copy()
        self.armor_proficiencies = self.class_armor_proficiencies.copy()
        self.darkvision_radius = 0
        self.damage_resistances = []
        # Race.apply_traits() writes racial cantrips (Fire Bolt, Mage Hand,
        # ...) directly into this dict (see races.py's HighElf/Mephistopheles
        # Tiefling) -- must exist before apply_race() runs, same reasoning
        # as the proficiency lists above. A companion has no way to cast
        # these yet (see CompanionClass.focus's docstring on spellcasting),
        # but apply_traits() still needs somewhere to record that the
        # companion knows them.
        self.abilities = {}

        # -- Equipment -- straight from the class definition, same slots
        # player.py's Fighter/Rogue equip directly onto self.
        self.equipped_weapon = companion_class.weapon
        self.equipped_armor = companion_class.armor
        self.equipped_off_hand = companion_class.off_hand
        self.equipped_boots = companion_class.boots
        self.equipped_helmet = None
        self.equipped_focus = companion_class.focus

        # -- Combat style / ranged-specific state --
        self.combat_style = companion_class.combat_style
        self.attack_range = companion_class.attack_range
        self.max_ammo = companion_class.starting_ammo  # None for melee -- unlimited
        self.ammo = self.max_ammo

        self.saving_throw_proficiencies = companion_class.saving_throw_proficiencies

        self.hit_die = companion_class.hit_die
        # Same +2-at-1/+1-per-4-levels progression Player's proficiency
        # bonus follows -- kept local rather than imported for the same
        # "no dependency on player.py" reasoning as the formulas below.
        self.proficiency_bonus = 2 + max(0, (self.level - 1) // 4)

        # HP/AC/attack derived below, once ability scores are final.
        self._recalculate_stats()

    # -- race application (see class docstring for call order) --------------

    def apply_race(self, game_instance):
        """
        Apply racial ability-score bonuses, resistances, darkvision, and
        proficiencies via the *same* Race.apply_traits() every playable
        character uses, then recompute derived stats since ability
        scores may have just changed.
        """
        self.race.apply_traits(self, game_instance)
        self._recalculate_stats()

    # -- derived stats ---------------------------------------------------
    # Small local copies of player.py's formulas, kept independent of
    # player.py on purpose -- see module docstring.

    def get_ability_modifier(self, score):
        return (score - 10) // 2

    def get_saving_throw_bonus(self, ability_name):
        attribute_name = self._ability_name_map.get(ability_name.upper())
        if not attribute_name:
            raise ValueError(f"Invalid ability name for saving throw: {ability_name}")
        ability_score = getattr(self, attribute_name)
        modifier = self.get_ability_modifier(ability_score)

        if self.saving_throw_proficiencies.get(ability_name.upper(), False):
            return modifier + self.proficiency_bonus
        return modifier

    def make_saving_throw(self, ability_name, dc, game_instance):
        d20_roll = random.randint(1, 20)
        save_bonus = self.get_saving_throw_bonus(ability_name)
        save_total = d20_roll + save_bonus
        print(f"DEBUG: {self.name} {ability_name} Save: Roll={d20_roll}, Bonus={save_bonus}, Total={save_total}, DC={dc}") # ADD THIS

        game_instance.message_log.add_message(
            f"{self.name} make a {ability_name} saving throw: {d20_roll} + {save_bonus} = {save_total} (DC {dc})",
            (150, 200, 255)
        )

        if save_total >= dc:
            game_instance.message_log.add_message(
                f"Your {ability_name} save succeeds!",
                (100, 255, 100)
            )
            return True
        else:
            game_instance.message_log.add_message(
                f"Your {ability_name} save fails!",
                (255, 100, 100)
            )
            return False

    def add_status_effect(self, effect_name, duration, game_instance, source=None):
        """Adds a status effect to the player."""
        new_effect = None
        
        if effect_name == "Poisoned":
            new_effect = Poisoned(duration, source)
        
        elif effect_name == "AcidBurned":
            new_effect = AcidBurned(duration, source)
        
        elif effect_name == "Burning":
            new_effect = Burning(duration, source)   
        
        elif effect_name == "CurseOfBlindness":
            new_effect = CurseOfBlindness(duration)  

        elif effect_name == "CurseOfRot":
            new_effect = CurseOfRot(duration)

        elif effect_name == "CurseOfWeakness":
            new_effect = CurseOfWeakness(duration)

        elif effect_name == "BlessingOfStrength":
            new_effect = BlessingOfStrength(duration)

        elif effect_name == "BlessingOfFortitude":
            new_effect = BlessingOfFortitude(duration)

        elif effect_name == "BlessingOfBloodlust":
            new_effect = BlessingOfBloodlust(duration)

        elif effect_name == "BlessingOfAgility":
            new_effect = BlessingOfAgility(duration)

        elif effect_name == "PowerAttackBuff":
            new_effect = PowerAttackBuff(duration)
        
        elif effect_name == "DivineStrikeBuff":
            new_effect = DivineStrikeBuff(duration)

        elif effect_name == "PreciseStrikeBuff":
            new_effect = PreciseStrikeBuff(duration)

        elif effect_name == "HunterMarkBuff":
            new_effect = HunterMarkBuff(duration)
        
        elif effect_name == "Prepared":
            new_effect = Prepared(duration)
        
        elif effect_name == "FleetFooted":
            new_effect = FleetFooted(duration)
        
        elif effect_name == "AppliedToxins":
            new_effect = AppliedToxins(duration)
        
        elif effect_name == "CunningActionDashBuff":
            new_effect = CunningActionDashBuff(duration)
        
        elif effect_name == "EvasionBuff":
            new_effect = EvasionBuff(duration)          

        elif effect_name == "Guard":
            guard_bonus = getattr(source, 'ac_bonus', 5)
            new_effect = GuardBuff(duration, ac_bonus=guard_bonus, source=source)
        
        elif effect_name == "ParryBuff":
            parry_bonus = getattr(source, 'ac_bonus', 3)
            new_effect = ParryBuff(duration, ac_bonus=parry_bonus, source=source)

        elif effect_name == "Torchlight":
            new_effect = Torchlight(duration)
        
        elif effect_name == "ActionSurgeEffect":
            new_effect = ActionSurgeEffect(duration)
        
        elif effect_name == "Hidden":
            new_effect = Hidden(duration)

        elif effect_name == "SpotTrapsEffect":
            new_effect = SpotTrapsEffect(duration)

        elif effect_name == "DetectMagicEffect":
            new_effect = DetectMagicEffect(duration)

        if new_effect:
            for existing_effect in self.active_status_effects:
                if type(existing_effect) is type(new_effect):
                    existing_effect.turns_left = new_effect.duration
                    game_instance.message_log.add_message(f"{self.name}'s {new_effect.name} effect is refreshed.", (200, 200, 255))
                    return
            self.active_status_effects.append(new_effect)
            print(f"DEBUG: {effect_name} successfully added to {self.name}.") # ADD THIS            
        else:
            game_instance.message_log.add_message(f"Warning: Attempted to add unknown status effect: {effect_name}", (255, 0, 0))
            print(f"Warning: Attempted to add unknown status effect: {effect_name}")


    def _recalculate_stats(self):
        """
        Recompute HP, AC, and attack/damage bonuses from current ability
        scores and equipment. Called once at construction and again
        after apply_race() changes ability scores.
        """
        con_modifier = self.get_ability_modifier(self.constitution)
        average_roll = (self.hit_die // 2) + 1
        max_hp = self.hit_die + con_modifier
        if self.level > 1:
            max_hp += (self.level - 1) * (average_roll + con_modifier)

        # Preserve current damage across a recalculation -- apply_race()
        # running mid-fight (it never does today, but nothing prevents a
        # future level-up call from reusing this) should never top a
        # companion back up to full just because max HP changed.
        old_hp = getattr(self, 'hp', None)
        self.max_hp = max(1, max_hp)
        self.hp = self.max_hp if old_hp is None else min(old_hp, self.max_hp)

        base_ac = 10 + self.get_ability_modifier(self.dexterity)
        if self.equipped_armor:
            base_ac += self.equipped_armor.ac_bonus
        if self.equipped_off_hand:
            base_ac += self.equipped_off_hand.ac_bonus
        if self.equipped_helmet:
            base_ac += self.equipped_helmet.ac_bonus
        if self.equipped_boots:
            base_ac += self.equipped_boots.ac_bonus
        self.armor_class = base_ac

        primary_score = getattr(self, self.primary_stat)
        primary_modifier = self.get_ability_modifier(primary_score)
        self.attack_power = primary_modifier
        self.attack_bonus = primary_modifier + self.proficiency_bonus
        if self.equipped_weapon:
            self.attack_power += self.equipped_weapon.damage_modifier
            self.attack_bonus += self.equipped_weapon.attack_bonus
        # Every equipment slot in items.py -- not just weapons -- carries
        # its own attack_bonus (a heavier shield or plate armor imposes a
        # penalty; studded leather grants a small bonus; see
        # round_shield/half_plate_armor/studded_leather_armor in
        # items.py). Folding all of them in here is what makes a Cleric's
        # round_shield, or a heavier armor choice, actually matter.
        for slot in (self.equipped_armor, self.equipped_off_hand, self.equipped_helmet, self.equipped_boots):
            if slot:
                self.attack_bonus += slot.attack_bonus
        # Companions don't have real spellcasting yet (see
        # CompanionClass.focus's docstring) -- a caster's focus item
        # still just nudges its ordinary weapon attack rather than
        # unlocking spells, until that system exists.
        if self.equipped_focus:
            self.attack_bonus += self.equipped_focus.spell_bonus

    # -- experience / leveling --------------------------------------------
    # Mirrors Player.get_next_level_xp_threshold()/gain_xp()/level_up()
    # (player.py) in shape, but stays a local, independent copy for the
    # same reason _recalculate_stats() does above -- a companion levels
    # up on its own XP total, earned from its own kills (see
    # _resolve_attack() below), not the player's.

    def get_next_level_xp_threshold(self):
        next_level = self.level + 1
        if next_level > 20:
            return float('inf')
        return COMPANION_XP_PROGRESSION.get(next_level, float('inf'))

    def gain_xp(self, amount, game_instance=None):
        self.current_xp += amount
        while self.level < 20 and self.current_xp >= self.get_next_level_xp_threshold():
            self.level_up(game_instance)

    def level_up(self, game_instance=None):
        if self.level >= 20:
            return

        self.level += 1
        self.proficiency_bonus = 2 + max(0, (self.level - 1) // 4)

        # HP/AC/attack all derive from level via proficiency_bonus and
        # the hit-die progression in _recalculate_stats() -- recomputing
        # there (rather than duplicating the formulas here) keeps this
        # in lockstep with __init__/apply_race()'s own calls to it.
        self._recalculate_stats()
        self.hp = self.max_hp  # Heal to full on level up, matching Player.level_up()

        if game_instance:
            game_instance.message_log.add_message(
                f"{self.name} reaches level {self.level}!", self.color
            )

    # -- combat orders (wired to the AI in the next pass) --------------------

    def set_stance(self, stance, game_instance):
        self.stance = stance
        game_instance.message_log.add_message(
            f"{self.name} readies to fight ({stance}).", self.color
        )

    def restock_ammo(self, amount, game_instance):
        """
        Refill ammo, capped at max_ammo. Intended to be called from the
        companion menu once the player is carrying arrows/bolts in
        inventory -- that inventory wiring is a follow-up; the plumbing
        lives here so the AI pass can call it as soon as it exists.
        """
        if self.max_ammo is None:
            return
        self.ammo = min(self.max_ammo, self.ammo + amount)
        game_instance.message_log.add_message(
            f"{self.name} restocks ammunition ({self.ammo}/{self.max_ammo}).", self.color
        )

    # -- turn AI: targeting -------------------------------------------------

    def _gather_enemies(self, game_instance, max_distance):
        """
        Every living Monster within `max_distance` tiles (Chebyshev,
        same as Imp/Celestial). Combat companions -- like every other
        combat summon in summons.py -- only ever fight Monster
        instances, never NPCs (shopkeepers, escort companions, other
        combat companions, ...), even if one happens to block movement.
        """
        enemies = []
        for entity in game_instance.entities:
            if entity is self or entity is self.owner or not getattr(entity, 'alive', False):
                continue
            if not isinstance(entity, Monster):
                continue
            if not getattr(entity, 'blocks_movement', False):
                continue
            if _chebyshev_distance(self.x, self.y, entity.x, entity.y) <= max_distance:
                enemies.append(entity)
        return enemies

    def _select_target(self, candidates):
        """
        Pick one enemy out of `candidates` according to the player's
        current order (see CompanionStance / game.py's COMPANION_MENU).
        Callers are responsible for not calling this under
        CompanionStance.PASSIVE, and for pre-filtering `candidates` to
        whatever range/LOS/ammo constraints matter for the situation
        (adjacency for melee, range+LOS+ammo for a ranged shot, ...).
        """
        if not candidates:
            return None
        if self.stance == CompanionStance.WEAKEST:
            return min(candidates, key=lambda e: e.hp)
        if self.stance == CompanionStance.FARTHEST:
            return max(candidates, key=lambda e: _chebyshev_distance(self.x, self.y, e.x, e.y))
        if self.stance == CompanionStance.PROTECT:
            return min(candidates, key=lambda e: _chebyshev_distance(self.owner.x, self.owner.y, e.x, e.y))
        # NEAREST is the default -- matches Imp/Celestial's existing
        # hardcoded tie-break, so a freshly recruited companion behaves
        # like every other combat summon until the player orders otherwise.
        return min(candidates, key=lambda e: _chebyshev_distance(self.x, self.y, e.x, e.y))

    # -- turn AI: movement --------------------------------------------------
    # Own copies of EscortCompanion's "steer first, path-find only if
    # that fails" split (see EscortCompanion._step_toward()'s docstring
    # for the performance reasoning) -- not inherited, since a combat
    # companion's collision rules differ (blocks_movement=True here, so
    # _is_free() doesn't need EscortCompanion's player/companion special
    # case; see that method's own docstring for why it needs one).

    def _is_free(self, x, y, game_map, game_instance):
        if not (0 <= x < game_map.width and 0 <= y < game_map.height):
            return False
        if not game_map.is_walkable(x, y):
            return False
        for entity in game_instance.entities:
            if entity is self:
                continue
            if entity.x == x and entity.y == y and getattr(entity, 'blocks_movement', False):
                return False
        return True

    def _step_toward(self, game_map, game_instance, target_x, target_y):
        """Cheap, search-free steering step toward (target_x, target_y),
        diagonal-first. Returns True if it moved. See
        EscortCompanion._step_toward() -- same algorithm."""
        dx = target_x - self.x
        dy = target_y - self.y
        step_x = (dx > 0) - (dx < 0)
        step_y = (dy > 0) - (dy < 0)

        cardinal_candidates = []
        if step_x != 0:
            cardinal_candidates.append((self.x + step_x, self.y))
        if step_y != 0:
            cardinal_candidates.append((self.x, self.y + step_y))
        if abs(dx) < abs(dy):
            cardinal_candidates.reverse()

        candidates = []
        if step_x != 0 and step_y != 0:
            candidates.append((self.x + step_x, self.y + step_y))
        candidates.extend(cardinal_candidates)

        for next_x, next_y in candidates:
            if self._is_free(next_x, next_y, game_map, game_instance):
                self.x, self.y = next_x, next_y
                return True
        return False

    def _pathfind_toward(self, game_map, game_instance, target_x, target_y):
        """A* fallback for when _step_toward() is blocked, reusing
        pathfinding.py's own entity-awareness (entities=/moving_entity=)
        rather than re-deriving blocked tiles by hand. Capped at
        SUMMON_PATHFINDING_MAX_EXPANSIONS like every other summon's
        search (see that constant's docstring in summons.py). Returns
        True if it moved."""
        path = astar(
            game_map, (self.x, self.y), (target_x, target_y),
            entities=game_instance.entities, moving_entity=self,
            max_expansions=SUMMON_PATHFINDING_MAX_EXPANSIONS,
        )
        if not path or len(path) < 2:
            return False
        next_x, next_y = path[1]
        if not self._is_free(next_x, next_y, game_map, game_instance):
            return False
        self.x, self.y = next_x, next_y
        return True

    def _approach(self, game_map, game_instance, target_x, target_y):
        """Close the distance to (target_x, target_y) by one tile this
        turn -- shared by melee's "chase the nearest enemy", ranged's
        "close in for a shot", and _follow_owner() below. Range/LOS is
        re-checked fresh every turn by the caller, so a ranged
        companion that comes into range mid-approach simply stops
        advancing and starts shooting on its next turn instead."""
        if self._step_toward(game_map, game_instance, target_x, target_y):
            return True
        return self._pathfind_toward(game_map, game_instance, target_x, target_y)

    def _kite_away_from(self, threat, game_map, game_instance):
        """Step away from an adjacent melee threat instead of standing
        still or closing in -- the one thing a ranged companion needs
        that melee never does. Implemented as _step_toward() aimed at
        the point directly opposite the threat, which reduces to
        "prefer whichever free tile increases the gap" without a
        separate steering algorithm."""
        mirror_x = self.x + (self.x - threat.x)
        mirror_y = self.y + (self.y - threat.y)
        return self._step_toward(game_map, game_instance, mirror_x, mirror_y)

    def _follow_owner(self, game_map, game_instance):
        """No enemies to fight -- catch up to the owner, same shape as
        EscortCompanion.take_turn()'s tail end."""
        if _chebyshev_distance(self.x, self.y, self.owner.x, self.owner.y) <= self.FOLLOW_DISTANCE:
            return
        self._approach(game_map, game_instance, self.owner.x, self.owner.y)

    # -- turn AI: attacks -------------------------------------------------

    @staticmethod
    def _roll_dice(dice_str):
        """Parse a weapon's 'NdM' damage_dice string (items.py, e.g.
        '1d8', '2d4') and return the rolled total. Falls back to a flat
        1 if it's missing/malformed, so a bad data entry degrades a
        companion's turn instead of crashing it."""
        try:
            count, sides = dice_str.lower().split('d')
            return sum(random.randint(1, int(sides)) for _ in range(int(count)))
        except (AttributeError, ValueError):
            return 1

    def _resolve_attack(self, target, game_instance, attack_bonus, attack_power,
                         dice, damage_type, verb, out_of_ammo_note=""):
        """
        Shared d20-vs-AC roll/damage/floating-text flow behind
        attack_enemy(), ranged_attack_enemy(), and melee_scuffle() --
        same shape as Imp.attack_enemy()/Celestial.attack_enemy(), just
        parameterized instead of copy-pasted three times.

        Unlike Imp/Celestial's own attack_enemy() (which adds
        attack_power to the *displayed* damage total without actually
        passing it to take_damage()), this applies the full
        dice-roll + attack_power to take_damage() so the number shown
        is the number actually taken.
        """
        d20_roll = random.randint(1, 20)
        attack_total = d20_roll + attack_bonus
        target_ac = getattr(target, 'armor_class', 10)

        game_instance.message_log.add_message(
            f"{self.name} {verb}: [{d20_roll}] + [{attack_bonus}] (Attack Bonus) "
            f"= {attack_total} vs AC {target_ac}!{out_of_ammo_note}", self.color
        )

        if attack_total >= target_ac:
            total_damage = self._roll_dice(dice) + attack_power
            damage_dealt = target.take_damage(total_damage, game_instance, damage_type=damage_type)
            game_instance.message_log.add_message(
                f"{self.name} hits {target.name} for {damage_dealt} damage!", self.color
            )
            game_instance.floating_texts.append(FloatingText(target.x, target.y, "HIT!", (255, 255, 0)))
            game_instance.floating_texts.append(FloatingText(target.x, target.y - 0.5, str(damage_dealt), (255, 0, 0)))

            if not target.alive:
                # Route through the same die()/_notify_monster_killed()
                # pipeline game.py's own player-attack site uses (see
                # handle_player_action()) -- loot, death messages, and
                # story kill triggers all still need to happen for a
                # kill landed by a companion, exactly as they do for one
                # landed by the player. `killer=self.owner` (the player)
                # keeps that attribution identical to every other kill
                # site in the game; the companion's own reward is
                # tracked separately via gain_xp() below.
                xp_gained = target.die(game_instance, killer=self.owner)
                self.gain_xp(xp_gained, game_instance)
                game_instance.message_log.add_message(
                    f"{self.name} gains {xp_gained} XP!", self.color
                )
                game_instance._notify_monster_killed(target, killer=self.owner)
        else:
            game_instance.message_log.add_message(f"{self.name} misses {target.name}!", (150, 150, 150))
            game_instance.floating_texts.append(FloatingText(target.x, target.y, "MISS!", (150, 150, 150)))

    def attack_enemy(self, target, game_instance):
        """Melee attack against an adjacent enemy, using this
        companion's own race/class-derived stats and equipped weapon."""
        dice = self.equipped_weapon.damage_dice if self.equipped_weapon else "1d4"
        self._resolve_attack(
            target, game_instance, self.attack_bonus, self.attack_power,
            dice, self.companion_class.damage_type, verb="swings",
        )

    def ranged_attack_enemy(self, target, game_instance):
        """Ranged attack against a target within attack_range and line
        of sight. Consumes one shot of ammo whether it hits or misses,
        same as a real quiver -- callers (see _take_ranged_turn) are
        expected to have already checked self.ammo > 0."""
        self.ammo -= 1
        note = f" ({self.ammo}/{self.max_ammo} ammo left)"
        dice = self.equipped_weapon.damage_dice if self.equipped_weapon else "1d4"
        self._resolve_attack(
            target, game_instance, self.attack_bonus, self.attack_power,
            dice, self.companion_class.damage_type, verb="looses a shot", out_of_ammo_note=note,
        )
        if self.ammo == 0:
            game_instance.message_log.add_message(f"{self.name} is out of ammunition!", (255, 150, 150))

    def melee_scuffle(self, target, game_instance):
        """Unarmed fallback for a ranged companion that's out of ammo
        and cornered by an adjacent enemy -- fights bare-handed rather
        than standing there doing nothing. Strips the equipped weapon's
        own attack_bonus/damage_modifier back out (they represent the
        bow, which isn't being used here), leaving just the companion's
        raw ability/proficiency numbers."""
        weapon = self.equipped_weapon
        unarmed_bonus = self.attack_bonus - (weapon.attack_bonus if weapon else 0)
        unarmed_power = max(0, self.attack_power - (weapon.damage_modifier if weapon else 0))
        self._resolve_attack(
            target, game_instance, unarmed_bonus, unarmed_power,
            "1d4", "bludgeoning", verb="throws a desperate punch",
        )

    # -- turn AI: top level -------------------------------------------------

    def take_turn(self, player, game_map, game_instance):
        """
        Stance-driven combat AI. Melee and ranged share the same
        targeting (_select_target) and movement (_approach/_follow_owner)
        helpers above; they differ only in when they're willing to
        attack and what they do when they can't yet.
        """
        self.tick_duration(game_instance)
        if not self.alive:
            return

        if self.stance != CompanionStance.PASSIVE:
            if self.combat_style == "ranged":
                if self._take_ranged_turn(game_map, game_instance):
                    return
            else:
                if self._take_melee_turn(game_map, game_instance):
                    return

        self._follow_owner(game_map, game_instance)
        # Only chime in on a quiet, non-combat turn (the two branches
        # above already returned early if there was a fight to attack or
        # close distance on) -- ambient flavor, not a battle bark.
        self.speak_ambient(game_instance)

    def speak_ambient(self, game_instance):
        """
        Occasionally drops a flavor line into the message log while
        following the player -- lighter-weight than monster.py's
        speak_ambient()/Game.show_monster_ambient_popup() (see that
        method's docstring), since a party member's aside doesn't need
        to interrupt play with a popup the way a spotted monster's line
        does.

        Gated by a cooldown shared across the whole party (see
        Game._companion_ambient_cooldown, ticked down once per player
        turn in next_turn()) rather than one cooldown per companion, so
        recruiting several companions doesn't multiply how often the
        party chatters -- only one line comes through per interval.
        """
        if getattr(game_instance, "_companion_ambient_cooldown", 0) > 0:
            return
        if random.random() > COMPANION_AMBIENT_CHANCE:
            return

        line = random.choice(COMPANION_AMBIENT_LINES)
        game_instance.message_log.add_message(f'{self.name}: "{line}"', self.color)
        game_instance._companion_ambient_cooldown = COMPANION_AMBIENT_COOLDOWN_TURNS

    def _take_melee_turn(self, game_map, game_instance):
        """Returns True if the companion attacked or moved toward a
        fight this turn (caller should not also follow), False if there
        was nothing to fight and the caller should fall through to
        _follow_owner()."""
        adjacent = self._gather_enemies(game_instance, max_distance=1)
        if adjacent:
            self.attack_enemy(self._select_target(adjacent), game_instance)
            return True

        nearby = self._gather_enemies(game_instance, max_distance=self.DETECTION_RADIUS)
        if nearby:
            target = self._select_target(nearby)
            return self._approach(game_map, game_instance, target.x, target.y)

        return False

    def _take_ranged_turn(self, game_map, game_instance):
        """Priority order: shoot anything already in range+LOS -> kite
        (or scuffle, if out of ammo) away from an adjacent threat ->
        close the distance on a farther enemy -> nothing to do. Returns
        True/False with the same meaning as _take_melee_turn()."""
        in_range = self._gather_enemies(game_instance, max_distance=self.attack_range)
        shootable = [
            enemy for enemy in in_range
            if game_instance.check_line_of_sight(self.x, self.y, enemy.x, enemy.y)
        ]
        if shootable and self.ammo:
            self.ranged_attack_enemy(self._select_target(shootable), game_instance)
            return True

        adjacent = self._gather_enemies(game_instance, max_distance=1)
        if adjacent:
            threat = self._select_target(adjacent)
            if self.ammo:
                if self._kite_away_from(threat, game_map, game_instance):
                    return True
                # Cornered with nowhere to retreat -- still better than
                # standing still and eating free hits.
                self.melee_scuffle(threat, game_instance)
                return True
            self.melee_scuffle(threat, game_instance)
            return True

        nearby = self._gather_enemies(game_instance, max_distance=self.DETECTION_RADIUS)
        if nearby:
            target = self._select_target(nearby)
            return self._approach(game_map, game_instance, target.x, target.y)

        return False

    # -- lifecycle --------------------------------------------------------

    def dismiss(self, game_instance):
        """
        Player-initiated leave, via the companion menu's Dismiss option
        -- distinct from die(): no death message, no combat implications,
        just parting ways. Mirrors die()'s entities/turn_order cleanup
        without the "fallen" flavor.
        """
        self.alive = False
        game_instance.message_log.add_message(f"{self.name} nods and departs.", self.color)
        self._leave_party(game_instance)

    def die(self, game_instance):
        """Handles the companion falling in battle."""
        self.alive = False
        game_instance.message_log.add_message(f"{self.name} has fallen!", (255, 80, 80))
        self._leave_party(game_instance)

    def _leave_party(self, game_instance):
        """Shared entities/turn_order/combat_companions cleanup for both
        dismiss() and die() -- see game.py's self.combat_companions
        (the CombatCompanion-only counterpart to self.companions, which
        stays reserved for EscortCompanion escort deliverables)."""
        if self in game_instance.entities:
            game_instance.entities.remove(self)
        if self in game_instance.turn_order:
            game_instance.turn_order.remove(self)
        if self in getattr(game_instance, 'combat_companions', []):
            game_instance.combat_companions.remove(self)
        game_instance.update_fov()

    def __repr__(self):
        return (
            f"CombatCompanion({self.name!r}, {self.companion_class.name}, "
            f"hp={self.hp}/{self.max_hp}, stance={self.stance})"
        )