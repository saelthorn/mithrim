# Mithrim

A turn-based dungeon crawler roguelike built in Python with Pygame. Create a character, explore procedurally-generated dungeons, and defeat the Spider Queen Arasta across 20 levels of increasing difficulty.

## Overview

Mithrim is a tactical RPG inspired by D&D 5e mechanics. The game features:

- Character customization with 15 races and 4 classes
- Turn-based tactical combat with status effects and special abilities
- Procedurally-generated dungeon levels with environmental hazards
- 40+ unique monsters with scaling difficulty
- Full inventory and equipment system
- NPC interactions, trading, and rest mechanics
- Field of View and light source management
- Monster pathfinding and intelligent AI behavior

## Core Systems

### Game States

The game operates through distinct states:

| State | Purpose |
|-------|---------|
| CHARACTER_CREATION | Select race and lineage |
| CLASS_SELECTION | Choose class (Fighter, Rogue, Wizard, Cleric) |
| TAVERN | Safe hub area with NPCs |
| DUNGEON | Main gameplay—exploration and combat |
| INVENTORY | Manage equipment and items |
| INVENTORY_MENU | Item actions (equip, use, drop, sell) |
| CHARACTER_MENU | View stats, abilities, and proficiencies |
| TARGETING | Active targeting for ranged abilities |
| TRADE | Buy/sell with merchants |
| GAME_OVER | Death/victory screen |

### Combat System

**Attack Resolution:**
1. Roll d20 + attack bonus vs target AC
2. Natural 20 = critical hit (double damage dice)
3. Natural 1 = critical miss (no damage)
4. Roll damage dice + modifiers on hit
5. Apply status effects (buffs, debuffs, resistances)
6. Reduce target HP; if ≤ 0, target dies

**Special Mechanics:**
- Sneak Attack (Rogue): Extra 1d6 per 2 levels from hiding
- Power Attack (Fighter): Trade accuracy for damage
- Opportunity Attack: Monsters attack when player moves away
- Healing Word (Cleric): Restore ally HP at range
- Fire Bolt (Wizard): Ranged spell attack 1d10

### Character Classes

| Class | Hit Die | Primary Stat | Key Ability |
|-------|---------|--------------|-------------|
| Fighter | d10 | Strength | Action Surge |
| Rogue | d8 | Dexterity | Cunning Action Dash |
| Wizard | d6 | Intelligence | Fire Bolt / Mage Hand |
| Cleric | d8 | Wisdom | Healing Word / Divine Strike |

### Playable Races

**Humans**: Versatile, balanced stats  
**Dwarves**: Mountain, Hill, Duergar variants—strong constitution  
**Elves**: Drow, High, Wood variants—high dexterity  
**Tieflings**: Zariel, Levistus, Dispater, Mephistopheles—infernal ancestry  
**Dragonborn**: Red, Blue, Gold, Green—draconic heritage  

Each race grants resistances, skill proficiencies, weapon proficiencies, and darkvision bonuses.

### Leveling & Progression

- Gain XP by defeating enemies
- Level 1-20, each level increases HP, attack bonuses, and ability slots
- New abilities unlock every 2-3 levels
- Proficiency bonus increases at levels 5, 9, 13, 17
- Final challenge: Defeat Arasta on level 20

### Field of View & Light

Three light sources contribute to visibility:

1. **Darkvision** — Base radius (usually 4 tiles)
2. **Torchlight** — Extended radius when carrying torch
3. **Wall Torches** — Lit by player (F key), illuminates rooms

Visibility types:
- `player` — Currently visible in FOV
- `torch` — Visible via torchlight
- `darkvision` — Visible via darkvision only
- `explored` — Visited but dark
- `unexplored` — Never seen

### Monster System

**Monster Attributes:**
- HP, armor class, attack bonus, damage dice
- Saving throw proficiencies
- Ranged attack capabilities (for archers)
- Special abilities (poison, acid burn, fire)
- Status effects (poisoned, burning, etc.)

**Monster AI States:**
- CHASING — Moving toward player
- FLEEING — Running from player (low HP)
- DESPERATE_FIGHT — Last stand behavior
- INVESTIGATE — Searching after player lost

Monsters wake when spotted or within 10-tile radius. They use pathfinding (A*) to navigate dungeons.

### Item System

**Equipment Slots:**
- Weapon, armor, off-hand, 2 accessories, helmet, boots, focus item

**Item Types:**

| Type | Purpose | Examples |
|------|---------|----------|
| Weapon | Melee/ranged damage | Dagger, longsword, rapier, staff |
| Armor | Defense | Leather, chain mail, half-plate |
| Shield | AC bonus | Round, kite, tower |
| Helmet | AC + special effects | Leather cap, iron helmet, mage's circlet |
| Boots | AC + special effects | Standard, boots of speed, boots of stealth |
| Potion | Consumable healing | Lesser/greater healing potion |
| Food | Hunger + healing | Meat, bread, mushrooms, cheese |
| Accessory | Special effects | Holy symbol, focus item |
| Off-hand | Shield/spellbook | Round shield, spellbook |

**Merchant Trading:**
- Buy equipment and consumables in tavern
- Sell items to merchants
- Prices scale with item rarity/power

### Dungeon Generation

Procedurally generates 60×40 tile levels:

- 8-10 rooms per level, connected by tunnels
- Room variants: large, medium, small
- Pillar placement for visual/tactical interest
- Destructible props (crates, barrels) with loot drops
- Trap placement increases with dungeon depth
- Water features (rivers, lakes, sewage) for environmental variety
- Chest placement with randomized loot
- Mimic disguises (crates/barrels/chests) for danger

### Status Effects

**Buffs:**
- ParryBuff: +2 AC until next turn
- PowerAttackBuff: -5 hit, +10 damage (one attack)
- DivineStrikeBuff: Add radiant damage to next attack
- Hidden: Invisible, grants advantage, breaks on attack
- BlessingOfStrength: +2 STR for 10 turns
- Prepared: +1 AC, +2 melee damage

**Debuffs:**
- CurseOfWeakness: -2 STR for 10 turns
- CurseOfBlindness: -4 AC for 5 turns
- Poisoned: Take poison damage over time
- AcidBurned: Take acid damage over time
- Burning: Take fire damage over time

### Trap System

Traps are hidden or revealed tiles. When stepping on trap:

1. Roll Perception check (DC varies by trap type)
2. If successful: Trap revealed, no damage
3. If failed: Trap springs, takes damage

**Trap Types:**
- Dart Trap: 1d4 piercing damage
- Spike Trap: 1d6 piercing damage
- Fire Trap: 2d6 fire damage (AoE)
- Explosive Trap: 3d6 force damage (AoE)
- Acid Spray Trap: 2d6 acid damage (AoE)

### Hunger System

- Player hunger decreases each turn
- Food restores hunger and health
- Starvation causes death
- Food sources: merchant, ground loot, monster drops

### Altars

Hidden altars spawn on dungeon levels. Interacting with unknown altar:
- 50% chance: Blessing of Strength (+2 STR, 10 turns)
- 50% chance: Curse of Weakness (-2 STR, 10 turns)

### Inventory Management

- Navigate with arrow keys / WASD
- Use items: U key
- Equip items: E key
- Drop items: D key
- Assign to quick-bar: Q or F key
- Sell items: Trade state with merchant

### Camera System

- Smooth following with linear interpolation (LERP)
- Float-based positioning for pixel-perfect movement
- Zoom support (0.5x to 2.5x) with mouse wheel
- Auto-centers on player with vertical offset for message log

## Controls

| Key | Action |
|-----|--------|
| Arrow Keys / WASD | Move |
| Space | Interact / Attack adjacent |
| 1-9 | Use ability (hotkey) |
| Q | Quick-bar slot Q |
| F | Quick-bar slot F |
| I | Open inventory |
| C | Open character menu |
| R | Rest (restore HP) |
| Mouse Wheel Up | Zoom in |
| Mouse Wheel Down | Zoom out |
| F11 | Toggle fullscreen |
| Esc | Close menu / Cancel action |

**In Inventory:**
| Key | Action |
|-----|--------|
| Arrow Keys / WASD | Navigate items |
| Enter | Select item |
| U | Use item |
| E | Equip item |
| D | Drop item |
| Q | Quick-bar (Q) |
| F | Quick-bar (F) |

**In Targeting:**
| Key | Action |
|-----|--------|
| Arrow Keys / HJKL | Move cursor |
| Enter | Confirm target |
| Esc | Cancel targeting |

## Monster Types by Level

| Levels | Monsters | Challenge |
|--------|----------|-----------|
| 1-2 | Goblins, Rats, Imps | Very weak |
| 3-4 | Skeletons, Oozes, Spiders | Weak |
| 5-9 | Centaurs, Werewolves, Grick | Moderate |
| 10-15 | Minotaurs, Mind Flayers, Beholders | Hard |
| 16-19 | Dragons, Demogorgon, Death Slaad | Very Hard |
| 20 | Arasta (Spider Queen) | Final Boss |

## Configuration

Edit `config.py` to customize:

```python
SCREEN_WIDTH = 1280             # Window width
SCREEN_HEIGHT = 720             # Window height
TILE_SIZE = 24                  # Pixels per tile
TARGET_EFFECTIVE_TILE_SCALE = 1.0  # Zoom level
MIN_ZOOM_SCALE = 0.5            # Min zoom
MAX_ZOOM_SCALE = 2.5            # Max zoom
MESSAGE_LOG_HEIGHT_RATIO = 0.26 # Message log size
```

## File Structure

```
mithrim/
├── game.py                      # Main game engine
├── graphics.py                  # Tileset rendering
├── config.py                    # Configuration constants
├── core/
│   ├── fov.py                   # Field of view calculation
│   ├── abilities.py             # Player abilities
│   ├── status_effects.py        # Buffs and debuffs
│   ├── message_log.py           # Event logging
│   ├── pathfinding.py           # A* pathfinding
│   └── inventory.py             # Inventory management
├── entities/
│   ├── player.py                # Player character base
│   ├── monster.py               # Monster base class
│   ├── races.py                 # Playable races
│   └── dungeon_npcs.py          # Merchants, healers
├── world/
│   ├── dungeon_generator.py     # Procedural generation
│   ├── tavern_generator.py      # Static tavern layout
│   ├── tile.py                  # Tile definitions
│   ├── water_features.py        # Water tiles
│   └── map.py                   # Map data structure
└── items/
    └── items.py                 # Item classes
```

## Game Flow

1. **Character Creation** — Choose race and lineage (apply racial bonuses)
2. **Class Selection** — Pick Fighter, Rogue, Wizard, or Cleric
3. **Tavern Hub** — Rest, buy equipment, interact with NPCs
4. **Dungeon Exploration** — Levels 1-20, increasing difficulty
5. **Combat** — Turn-based battles with monsters
6. **Loot & Progression** — Gain XP, level up, find better equipment
7. **Final Boss** — Defeat Arasta on level 20
8. **Game Over** — Death or victory

## Key Mechanics

**Proficiency Bonus:**
Applies to attack rolls, ability checks, and saving throws where proficient.  
Increases at levels 5, 9, 13, 17.

**Armor Class:**
Calculated from armor worn + dexterity modifier + shield bonus.  
Protects against incoming attacks.

**Ability Modifiers:**
Each ability score (STR, DEX, CON, INT, WIS, CHA) has a modifier.  
Modifier = (score - 10) / 2 (rounded down).

**Hit Dice:**
Used to restore HP during rests.  
Determine HP gain on level-up.

**Initiative:**
Rolled at start of combat.  
DEX modifier + proficiency for some classes.

**Saving Throws:**
Ability checks to resist effects.  
Some creatures proficient in specific saves.

## Advanced Features

**Procedural Generation:**
- Random room placement with padding to prevent overlap
- Tunnel generation with bend points
- Trap placement scaled by dungeon level
- Enemy spawning based on difficulty tier
- Chest placement with randomized loot

**Field of View Algorithm:**
Uses shadowcasting for efficient visibility calculation.  
Combines multiple light sources (darkvision, torchlight, wall torches).  
Tracks explored vs. currently visible tiles.

**Monster Pathfinding:**
A* algorithm finds shortest path to player.  
Avoids water and traps.  
Respects movement costs.

**Turn System:**
Initiative-based turn order.  
Inactive monsters skip turns.  
Status effects processed at turn end.

## Performance Notes

- Game runs at 60 FPS target
- Tile rendering uses sprite subsurface extraction
- Camera uses float positioning for smooth movement
- Message log capped at 50 entries to prevent memory bloat
- Memory profiling available via `tracemalloc`

## Known Limitations

- Single-threaded (brief pause on level generation)
- No persistent save system (permadeath only)
- Limited boss encounter variety
- AI uses basic FSM (no advanced tactics)
- Static tavern layout

## Debugging

- FPS counter displayed in top-left
- Message log scrollable with mouse wheel (reviews all events)
- Print statements throughout code for tracing control flow
- Memory tracking available via `tracemalloc` import