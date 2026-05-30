# races.py
# ─────────────────────────────────────────────────────────────────────────────
# Race & Lineage system
#
# Hierarchy
#   Race  (abstract base)
#   ├─ Human
#   ├─ Elf  ──────────────── DrowElf | HighElf | WoodElf
#   ├─ Dwarf  ────────────── HillDwarf | MountainDwarf | Duergar
#   ├─ Tiefling  ──────────  ZarielTiefling | LevistusTiefling
#   │                        DispaterTiefling | MephistophelesTiefling
#   └─ Dragonborn  ────────  RedDragonborn | BlueDragonborn
#                            GoldDragonborn | GreenDragonborn
#
# Design rule: base classes NEVER pass their own default lists through
# **kwargs.  Instead they define class-level constants (BASE_RESISTANCES,
# BASE_SKILLS, etc.) that __init__ reads directly.  Subclasses override
# those constants — they never pass duplicate keyword arguments.
# ─────────────────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════
# BASE RACE
# ═══════════════════════════════════════════════════════════════════════════

class Race:
    """
    Abstract base for every playable race / lineage.

    Subclasses override `apply_traits` to grant bonuses, then call
    `super().apply_traits()` so the base syncs darkvision and proficiencies.
    """

    def __init__(
        self,
        name,
        description,
        darkvision_radius=0,
        damage_resistances=None,
        skill_proficiencies=None,
        weapon_proficiencies=None,
        armor_proficiencies=None,
    ):
        self.name               = name
        self.description        = description
        self.darkvision_radius  = darkvision_radius
        self.damage_resistances   = list(damage_resistances)   if damage_resistances   else []
        self.skill_proficiencies  = list(skill_proficiencies)  if skill_proficiencies  else []
        self.weapon_proficiencies = list(weapon_proficiencies) if weapon_proficiencies else []
        self.armor_proficiencies  = list(armor_proficiencies)  if armor_proficiencies  else []

    # ── Shared log helpers ────────────────────────────────────────────────

    def _grant_ability_scores(self, player, game, **deltas):
        """Apply {attribute: delta} pairs and log the result."""
        parts = []
        for attr, delta in deltas.items():
            setattr(player, attr, getattr(player, attr) + delta)
            sign = "+" if delta >= 0 else ""
            parts.append(f"{sign}{delta} {attr.capitalize()}")
        if parts:
            game.message_log.add_message(
                f"{player.name} gains {', '.join(parts)} ({self.name}).",
                (200, 200, 255),
            )

    def _log_darkvision(self, player, game):
        if self.darkvision_radius > 0:
            game.message_log.add_message(
                f"{player.name} gains Darkvision ({self.darkvision_radius} tiles).",
                (150, 200, 255),
            )

    def _log_resistances(self, player, game):
        if self.damage_resistances:
            game.message_log.add_message(
                f"{player.name} resists: {', '.join(self.damage_resistances)}.",
                (150, 200, 255),
            )

    def _log_proficiencies(self, player, game):
        if self.weapon_proficiencies:
            game.message_log.add_message(
                f"Weapon prof.: {', '.join(self.weapon_proficiencies)}.",
                (150, 200, 255),
            )
        if self.armor_proficiencies:
            game.message_log.add_message(
                f"Armor prof.: {', '.join(self.armor_proficiencies)}.",
                (150, 200, 255),
            )

    # ── Core hook ─────────────────────────────────────────────────────────

    def apply_traits(self, player, game):
        """
        Sync darkvision radius and append racial proficiencies.
        Always call super() first in subclass overrides.
        """
        game.message_log.add_message(
            f"Applying {self.name} traits to {player.name}.",
            (150, 150, 255),
        )
        player.darkvision_radius = self.darkvision_radius

        for wp in self.weapon_proficiencies:
            if wp not in player.weapon_proficiencies:
                player.weapon_proficiencies.append(wp)

        for ap in self.armor_proficiencies:
            if ap not in player.armor_proficiencies:
                player.armor_proficiencies.append(ap)


# ═══════════════════════════════════════════════════════════════════════════
# HUMAN
# ═══════════════════════════════════════════════════════════════════════════

class Human(Race):
    """
    Versatile and adaptable.
    Trait: +1 to every ability score.
    """

    def __init__(self):
        super().__init__(
            name="Human",
            description=(
                "Humans are the most adaptable of races, thriving in every corner "
                "of the world.  Their ambition and diversity grant a small boost to "
                "all of their abilities."
            ),
            darkvision_radius=5,
            skill_proficiencies=["Any Skill"],
            weapon_proficiencies=["Simple Weapons"],
            armor_proficiencies=["Light Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(
            player, game,
            strength=1, dexterity=1, constitution=1,
            intelligence=1, wisdom=1, charisma=1,
        )


# ═══════════════════════════════════════════════════════════════════════════
# ELF  (shared base — not directly selectable)
# ═══════════════════════════════════════════════════════════════════════════

class Elf(Race):
    """
    Shared elven foundation.
    All elves: +2 DEX, Keen Senses (Perception), Fey Ancestry (Magic resist).

    KEY: base lists are defined as class constants so subclasses can extend
    them by overriding the constant — never by passing duplicate kwargs.
    """

    # Subclasses may override these to add to the base lists.
    BASE_RESISTANCES = ["Magic"]
    BASE_SKILLS      = ["Perception"]

    def __init__(self, name, description, darkvision_radius=8,
                 extra_skills=None, extra_weapons=None, extra_armors=None):
        super().__init__(
            name=name,
            description=description,
            darkvision_radius=darkvision_radius,
            damage_resistances=self.BASE_RESISTANCES,
            skill_proficiencies=self.BASE_SKILLS + (extra_skills or []),
            weapon_proficiencies=extra_weapons or [],
            armor_proficiencies=extra_armors  or [],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, dexterity=2)
        self._log_darkvision(player, game)
        self._log_resistances(player, game)


class DrowElf(Elf):
    """Underdark lineage. +1 CHA, Superior Darkvision (12), Drow Weapon Training."""

    def __init__(self):
        super().__init__(
            name="Drow Elf",
            description=(
                "Born in lightless caverns, Drow elves are graceful and cunning, "
                "their silver eyes piercing the deepest dark.  They carry an innate "
                "talent for stealth and charm, and an affinity for the blade."
            ),
            darkvision_radius=12,
            extra_skills=["Stealth"],
            extra_weapons=["Rapiers", "Hand Crossbows", "Shortswords"],
            extra_armors=["Light Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, charisma=1)
        self._log_proficiencies(player, game)
        game.message_log.add_message(
            f"{player.name} has Superior Darkvision ({self.darkvision_radius} tiles).",
            (150, 200, 255),
        )


class HighElf(Elf):
    """Arcane lineage. +1 INT, free Fire Bolt cantrip, Elf Weapon Training."""

    def __init__(self):
        super().__init__(
            name="High Elf",
            description=(
                "High Elves have devoted millennia to mastering the arcane arts.  "
                "Their sharp intellect and innate magical sensitivity let them wield "
                "a cantrip even without formal training."
            ),
            darkvision_radius=8,
            extra_skills=["Arcana"],
            extra_weapons=["Longswords", "Shortswords", "Longbows", "Shortbows"],
            extra_armors=["Light Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, intelligence=1)
        self._log_proficiencies(player, game)

        from core.abilities import FireBolt
        if "Fire Bolt" not in player.abilities:
            ability = FireBolt()
            if hasattr(ability, "scale_with_level"):
                ability.scale_with_level(player.level)
            player.abilities["Fire Bolt"] = ability
            game.message_log.add_message(
                f"{player.name} knows Fire Bolt from their High Elf heritage.",
                (255, 150, 80),
            )


class WoodElf(Elf):
    """Sylvan lineage. +1 WIS, Fleet of Foot (+1 vision radius), Stealth."""

    def __init__(self):
        super().__init__(
            name="Wood Elf",
            description=(
                "Wood Elves are fleet-footed hunters who blend seamlessly into "
                "forest and shadow.  Their sharpened instincts make them deadly "
                "archers and tireless scouts."
            ),
            darkvision_radius=8,
            extra_skills=["Stealth", "Survival"],
            extra_weapons=["Longswords", "Shortswords", "Longbows", "Shortbows"],
            extra_armors=["Light Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, wisdom=1)
        self._log_proficiencies(player, game)

        player.vision_radius = getattr(player, "vision_radius", 4) + 1
        game.message_log.add_message(
            f"Fleet of Foot: vision radius → {player.vision_radius}.",
            (100, 220, 100),
        )


# ═══════════════════════════════════════════════════════════════════════════
# DWARF  (shared base — not directly selectable)
# ═══════════════════════════════════════════════════════════════════════════

class Dwarf(Race):
    """
    Shared dwarven foundation.
    All dwarves: +2 CON, Poison Resistance, Darkvision, axe/hammer proficiency.

    Subclasses that need extra resistances (e.g. Duergar adding Magic) set
    EXTRA_RESISTANCES at the class level — never pass damage_resistances
    through kwargs, which would collide with the base hardcoded value.
    """

    BASE_RESISTANCES = ["Poison"]
    BASE_SKILLS      = ["History", "Stonecunning"]
    BASE_WEAPONS     = ["Battleaxes", "Handaxes", "Warhammers", "Light Hammers"]

    # Subclasses override this to append extra resistances cleanly.
    EXTRA_RESISTANCES: list = []

    def __init__(self, name, description, darkvision_radius=6,
                 extra_armors=None, extra_skills=None):
        super().__init__(
            name=name,
            description=description,
            darkvision_radius=darkvision_radius,
            damage_resistances=self.BASE_RESISTANCES + self.EXTRA_RESISTANCES,
            skill_proficiencies=self.BASE_SKILLS + (extra_skills or []),
            weapon_proficiencies=self.BASE_WEAPONS,
            armor_proficiencies=extra_armors or [],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, constitution=2)
        self._log_darkvision(player, game)
        self._log_resistances(player, game)
        self._log_proficiencies(player, game)


class HillDwarf(Dwarf):
    """Endurance lineage. +1 WIS, Dwarven Toughness (+1 HP / level)."""

    def __init__(self):
        super().__init__(
            name="Hill Dwarf",
            description=(
                "Hill Dwarves are the most common of their kin, as tough as the "
                "stone they mine.  A lifetime of hardship has made them remarkably "
                "resilient, adding extra vitality to every level gained."
            ),
            extra_armors=["Light Armor", "Medium Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, wisdom=1)

        bonus_hp = player.level
        player.max_hp += bonus_hp
        player.hp    += bonus_hp
        game.message_log.add_message(
            f"Dwarven Toughness: +{bonus_hp} HP.",
            (200, 200, 255),
        )


class MountainDwarf(Dwarf):
    """Warrior lineage. +2 STR, medium-armor proficiency."""

    def __init__(self):
        super().__init__(
            name="Mountain Dwarf",
            description=(
                "Mountain Dwarves are born soldiers, their broad frames forged for "
                "war.  They are equally at home with a pickaxe or a greatsword, and "
                "can bear heavier armour than their hill kin."
            ),
            extra_armors=["Light Armor", "Medium Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, strength=2)


class Duergar(Dwarf):
    """
    Grey-dwarf lineage. +1 STR, Superior Darkvision (12),
    Poison + Magic resistance.
    """

    # Extend the base Poison resistance with Magic.
    EXTRA_RESISTANCES = ["Magic"]

    def __init__(self):
        super().__init__(
            name="Duergar",
            description=(
                "Duergar are grey-skinned dwarves who toiled as slaves in the "
                "Underdark before winning their freedom through iron will.  Their "
                "minds are hardened against magic and their eyes pierce any dark."
            ),
            darkvision_radius=12,
            extra_armors=["Light Armor", "Medium Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, strength=1)
        game.message_log.add_message(
            f"Superior Darkvision ({self.darkvision_radius} tiles) + illusion resistance.",
            (150, 200, 255),
        )


# ═══════════════════════════════════════════════════════════════════════════
# TIEFLING  (shared base — not directly selectable)
# ═══════════════════════════════════════════════════════════════════════════

class Tiefling(Race):
    """
    Shared tiefling foundation.
    All tieflings: +1 INT, +2 CHA, Fire Resistance, Darkvision (8),
    Intimidation & Arcana proficiency.

    Subclasses that need extra or different resistances set EXTRA_RESISTANCES
    at the class level.  They must NEVER pass damage_resistances through
    __init__ kwargs — that would collide with the base hardcoded value.
    """

    BASE_RESISTANCES = ["Fire"]
    BASE_SKILLS      = ["Intimidation", "Arcana"]
    PATRON           = "Asmodeus"

    # Subclasses append here to add resistances without duplicating "Fire".
    EXTRA_RESISTANCES: list = []

    def __init__(self, name, description, darkvision_radius=8,
                 extra_skills=None, extra_weapons=None, extra_armors=None):
        super().__init__(
            name=name,
            description=description,
            darkvision_radius=darkvision_radius,
            damage_resistances=self.BASE_RESISTANCES + self.EXTRA_RESISTANCES,
            skill_proficiencies=self.BASE_SKILLS + (extra_skills or []),
            weapon_proficiencies=["Simple Weapons"] + (extra_weapons or []),
            armor_proficiencies=["Light Armor"]     + (extra_armors  or []),
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, intelligence=1, charisma=2)
        self._log_darkvision(player, game)
        self._log_resistances(player, game)
        self._log_proficiencies(player, game)
        game.message_log.add_message(
            f"Infernal patron: {self.PATRON}.",
            (180, 60, 60),
        )


class ZarielTiefling(Tiefling):
    """
    Warrior lineage from Zariel, Archduchess of Avernus.
    +2 STR, +1 CHA (overrides base INT bonus), martial weapon proficiency.
    Resists: Fire.
    """
    PATRON = "Zariel"

    def __init__(self):
        super().__init__(
            name="Zariel Tiefling",
            description=(
                "Battle-scarred descendants of infernal warlords.  "
                "Their blood burns with hellfire and conquest."
            ),
            darkvision_radius=6,
            extra_weapons=["Martial Weapons"],
        )

    def apply_traits(self, player, game):
        # Call Race.apply_traits directly to skip the Tiefling base INT/CHA grant,
        # then apply Zariel's own stat spread.
        Race.apply_traits(self, player, game)
        self._grant_ability_scores(player, game, strength=2, charisma=1)
        self._log_darkvision(player, game)
        self._log_resistances(player, game)
        self._log_proficiencies(player, game)
        game.message_log.add_message(
            f"{player.name}'s infernal blood radiates hellfire fury.",
            (176, 96, 42),
        )
        game.message_log.add_message(f"Infernal patron: {self.PATRON}.", (180, 60, 60))


class LevistusTiefling(Tiefling):
    """
    Assassin lineage from Levistus, Lord of Stygia.
    +2 DEX, +1 CHA. Resists: Fire + Cold.
    """
    PATRON             = "Levistus"
    EXTRA_RESISTANCES  = ["Cold"]   # stacks on top of base Fire resistance

    def __init__(self):
        super().__init__(
            name="Levistus Tiefling",
            description=(
                "Tieflings touched by the frozen hells.  "
                "Cold mist follows their every step."
            ),
            darkvision_radius=6,
        )

    def apply_traits(self, player, game):
        Race.apply_traits(self, player, game)
        self._grant_ability_scores(player, game, dexterity=2, charisma=1)
        self._log_darkvision(player, game)
        self._log_resistances(player, game)
        self._log_proficiencies(player, game)
        game.message_log.add_message(
            f"{player.name}'s frozen infernal blood chills the air.",
            (72, 132, 136),
        )
        game.message_log.add_message(f"Infernal patron: {self.PATRON}.", (180, 60, 60))


class DispaterTiefling(Tiefling):
    """
    Infiltrator lineage from Dispater, Lord of Dis.
    +2 DEX, +1 INT. Resists: Shadow (no Fire override — kept from base).
    Extra skills: Deception, Survival.
    """
    PATRON = "Dispater"

    def __init__(self):
        super().__init__(
            name="Dispater Tiefling",
            description=(
                "Cunning infernal schemers gifted with shadow magic "
                "and unnatural perception."
            ),
            darkvision_radius=7,
            extra_skills=["Deception", "Survival"],
        )

    def apply_traits(self, player, game):
        Race.apply_traits(self, player, game)
        self._grant_ability_scores(player, game, dexterity=2, intelligence=1)
        self._log_darkvision(player, game)
        self._log_resistances(player, game)
        self._log_proficiencies(player, game)
        game.message_log.add_message(f"Infernal patron: {self.PATRON}.", (180, 60, 60))


class MephistophelesTiefling(Tiefling):
    """
    Arcanist lineage from Mephistopheles, Lord of Cania.
    +1 INT (+2 total), +2 CHA. Resists: Fire.
    Extra weapons: Daggers, Quarterstaffs.
    """
    PATRON = "Mephistopheles"

    def __init__(self):
        super().__init__(
            name="Mephistopheles Tiefling",
            description=(
                "Infernal descendants infused with unstable arcane flame "
                "and forbidden magical knowledge."
            ),
            darkvision_radius=6,
            extra_weapons=["Daggers", "Quarterstaffs"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)   # uses Tiefling base: +1 INT, +2 CHA
        self._grant_ability_scores(player, game, intelligence=1)  # extra +1 INT
        self._log_proficiencies(player, game)
        self._log_resistances(player, game)

        from core.abilities import MageHand
        if "Mage Hand" not in player.abilities:
            ability = MageHand()
            if hasattr(ability, "scale_with_level"):
                ability.scale_with_level(player.level)
            player.abilities["Mage Hand"] = ability
            game.message_log.add_message(
                f"{player.name} knows Mage Hand from their Mephistopheles heritage.",
                (160, 100, 220),
            )


# ═══════════════════════════════════════════════════════════════════════════
# DRAGONBORN  (shared base — not directly selectable)
# ═══════════════════════════════════════════════════════════════════════════

class Dragonborn(Race):
    """
    Shared dragonborn foundation.
    All dragonborn: +2 STR, +1 CHA, one elemental resistance, Darkvision (5).

    ELEMENT and DAMAGE_TYPE are class-level constants that each subclass
    declares.  The base __init__ reads DAMAGE_TYPE directly so no subclass
    ever needs to pass damage_resistances through kwargs.
    """

    ELEMENT     = "Elemental"
    DAMAGE_TYPE = "Elemental"

    def __init__(self, name, description):
        super().__init__(
            name=name,
            description=description,
            darkvision_radius=5,
            damage_resistances=[self.DAMAGE_TYPE],
            skill_proficiencies=["Intimidation", "Athletics"],
            weapon_proficiencies=["Simple Weapons", "Martial Weapons"],
            armor_proficiencies=["Light Armor", "Medium Armor"],
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, strength=2, charisma=1)
        self._log_resistances(player, game)
        self._log_proficiencies(player, game)
        game.message_log.add_message(
            f"Draconic ancestry grants {self.ELEMENT} mastery.",
            (200, 150, 80),
        )


class RedDragonborn(Dragonborn):
    """Fire lineage. Bold, aggressive. +1 STR (+3 total). Resists: Fire."""
    ELEMENT     = "Fire"
    DAMAGE_TYPE = "Fire"

    def __init__(self):
        super().__init__(
            name="Red Dragonborn",
            description=(
                "Red Dragonborn carry the fury of volcanic fire in their blood.  "
                "They are the most aggressive of their kind, and their rage burns "
                "as hot as their breath."
            ),
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, strength=1)


class BlueDragonborn(Dragonborn):
    """Lightning lineage. Calculating, proud. +1 INT. Resists: Lightning."""
    ELEMENT     = "Lightning"
    DAMAGE_TYPE = "Lightning"

    def __init__(self):
        super().__init__(
            name="Blue Dragonborn",
            description=(
                "Blue Dragonborn crackle with barely-contained lightning.  Cold "
                "and methodical, they analyse every battlefield before striking "
                "with overwhelming, electric precision."
            ),
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, intelligence=1)


class GoldDragonborn(Dragonborn):
    """Fire lineage. Wise, honourable. +1 WIS. Resists: Fire."""
    ELEMENT     = "Fire"
    DAMAGE_TYPE = "Fire"

    def __init__(self):
        super().__init__(
            name="Gold Dragonborn",
            description=(
                "Gold Dragonborn are the most revered of their race — paragons of "
                "honour and wisdom.  Their golden scales radiate warmth and their "
                "counsel is sought across kingdoms."
            ),
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, wisdom=1)


class GreenDragonborn(Dragonborn):
    """Poison lineage. Cunning, manipulative. +1 CHA (+2 total). Resists: Poison."""
    ELEMENT     = "Poison"
    DAMAGE_TYPE = "Poison"

    def __init__(self):
        super().__init__(
            name="Green Dragonborn",
            description=(
                "Green Dragonborn breathe noxious clouds and thrive in deception.  "
                "Their emerald scales conceal a razor-sharp mind that manipulates "
                "allies and enemies alike."
            ),
        )

    def apply_traits(self, player, game):
        super().apply_traits(player, game)
        self._grant_ability_scores(player, game, charisma=1)


# ═══════════════════════════════════════════════════════════════════════════
# LINEAGE CATALOGUE  (read by the character-creation screen)
# ═══════════════════════════════════════════════════════════════════════════
# Each entry: (group_label, group_colour, [lineage_instances])

RACE_GROUPS = [
    (
        "Human",
        (200, 180, 140),
        [Human()],
    ),
    (
        "Elf",
        (100, 200, 160),
        [DrowElf(), HighElf(), WoodElf()],
    ),
    (
        "Dwarf",
        (160, 120, 70),
        [HillDwarf(), MountainDwarf(), Duergar()],
    ),
    (
        "Tiefling",
        (180, 60, 60),
        [ZarielTiefling(), LevistusTiefling(), DispaterTiefling(), MephistophelesTiefling()],
    ),
    (
        "Dragonborn",
        (200, 100, 40),
        [RedDragonborn(), BlueDragonborn(), GoldDragonborn(), GreenDragonborn()],
    ),
]