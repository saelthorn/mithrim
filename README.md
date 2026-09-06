<div align="center">

# Mithrim

*Mithrim is a dark fantasy, turn-based roguelike where the world isn't just procedurally generated—it evolves through the adventures you create. Explore dangerous dungeons, wander a living overworld, and uncover narrative encounters that leave lasting marks on the land.*

<video src="assets/mithrim_gameplay.mp4" controls width="640"></video>

![Python](https://img.shields.io/badge/Python-3.x-blue)
![Status](https://img.shields.io/badge/Status-Active%20Development-orange)
![License](https://img.shields.io/badge/License-See%20LICENSE-lightgrey)

</div>

---

## About

**Mithrim** is a procedurally generated, turn-based dungeon crawler where every expedition tells a story.

Inspired by classic CRPGs such as **Daggerfall**, traditional roguelikes, and **Dungeons & Dragons 5th Edition**, Mithrim blends tactical combat, persistent world exploration, and dynamic narrative encounters into a single adventure.

Unlike traditional roguelikes that focus solely on randomized levels, Mithrim places equal emphasis on **the journey between dungeons**. The overworld is not merely a transition—it is a living canvas where encounters, landmarks, and your choices gradually shape the world around you.

Every expedition has the potential to become its own story.


---

# Features

## Character Creation

Create your own adventurer from a growing roster of races, lineages, and classes.

- Five lineage groups with 15 playable lineages: Human, Elf, Dwarf, Tiefling, and Dragonborn variants.
- Six class implementations: Fighter, Rogue, Wizard, Cleric, Ranger, and Sorcerer.
- Ability scores, saving throws, skill and equipment proficiencies, racial traits, darkvision, resistances, and class abilities.
- Level progression with experience, ability-score improvements, proficiency scaling, and ability scaling.

---

## Tactical Turn-Based Combat

Every battle rewards planning over speed.

- Initiative-based, turn-by-turn combat with movement, melee attacks, ranged attacks, line of sight, field of view, and opportunity attacks.
- Weapon, armor, helmet, boots, off-hand, focus, and accessory equipment.
- Spell-like and class abilities including Fire Bolt, Fireball, Ray of Frost, Magic Missile, Misty Step, Cure Wounds, Healing Word, Sacred Flame, Dragon Breath, and summon abilities.
- Monster abilities, ranged attacks, kiting, fleeing, investigation, patrols, group alerting, and passive or neutral dispositions.
- Conditions and effects including Poisoned, Burning, Acid Burned, Restrained, Frightened, Evasion, Guard, Parry, curses, blessings, and temporary combat buffs.
- Unconsciousness at zero HP with death saving throws, stabilization, and a dedicated death-save menu.

---

## Procedural Dungeon Generation

Every dungeon is generated from scratch.

Each expedition features unique layouts, encounters, and discoveries.

Current generation includes:

- Deterministic dungeon generation when a seed is supplied.
- Rectangular, L-shaped, circular, plus-shaped, and hub rooms connected by tunnels.
- Stairs, doors, torches, pillars, props, water features, traps, loot, locked chests, mimics, altars, prison cells, crypts, and temple rooms.
- Dungeon depth controls monster tiers, bosses, traps, and loot. Individual dungeons are short, self-contained descents rather than one global ladder.

No two delves are exactly alike.

---

## Chunked Overworld

The overworld is more than a world map.

It is a place where stories begin.

Current systems include:

- A persistent overworld made from generated chunks. Visited chunks are cached and restored instead of regenerated.
- Biomes including plains, forests, swamps, hills, mountains, deserts, and tundra.
- Rivers, lakes, roads, terrain decoration, dungeon entrances, towns, landmark structures, and biome-specific monster populations.
- Town structures such as taverns, shops, houses, stables, shrines, watchtowers, windmills, cabins, blacksmiths, and campsites.
- Town NPC schedules, workplaces, homes, wandering, socializing, alert behavior, trading, healing, recruiting, and rest services.
- A day/night cycle with ambient messages, lighting, visibility changes, torches, sanity, hunger, and natural regeneration.

Future updates will continue expanding the overworld into a persistent living world filled with evolving events and narrative-driven discoveries.

---

## Dynamic Encounter System

One of Mithrim's defining features.

Rather than spawning generic random battles, the overworld generates handcrafted encounter chains that unfold naturally as you explore.

Examples include:

- Abandoned caravans
- Missing merchants
- Goblin camps
- Strange ruins
- Traveling pilgrims
- Abandoned campsites
- Ancient shrines

Encounters can:

- Branch
- Be ignored
- Change the world
- Affect reputation
- Create persistent landmarks
- Lead into larger narrative arcs

No quest markers.

No hand-holding.

Only curiosity.

---

## Companions

Hire adventurers during your travels.
Build a small party around your playstyle.

- Recruit Fighter, Ranger, Rogue, Wizard, and Cleric companions from towns and taverns.
- Give companions combat orders such as targeting the nearest, weakest, or farthest enemy, protecting the player, or staying passive.
- Travel with allies who follow you through the world, join turn order, fight with melee or ranged tactics, and share experience from battles.
- Cleric companions can heal wounded or downed party members, while ranged companions use shared ammunition and kite enemies when threatened.
- Companions have race traits, equipment, personalities, ambient chatter, level-up lines, death saves, dismissal, and permanent death.

---

## Living World

The world remembers.

Actions have lasting consequences.

Examples include:

- Reputation with settlements
- Persistent landmarks
- World scars left by encounters
- Dynamic NPC interactions
- Day and night cycle
- Ambient storytelling
- World events

Exploration is driven by discovery rather than checklists.

---

## D&D Inspired Mechanics

Mithrim takes heavy inspiration from **Dungeons & Dragons 5th Edition**, adapting many of its systems into a single-player roguelike experience.

Including:

- Ability Checks
- Skill Checks
- Saving Throws
- Death Saving Throws
- Racial Traits
- Spellcasting
- Monster Abilities
- Equipment Proficiencies
- Damage Types
- Conditions

These mechanics have been adapted for a roguelike experience rather than directly copied.

---

# Philosophy

Mithrim is built around one central idea:

> **The player should remember the adventure—not the dungeon seed.**

Every system exists to support memorable stories.

Whether that story is surviving with a single hit point...

Escaping a collapsing dungeon...

Helping a ruined caravan...

Or simply watching the sun rise after surviving a long night in the wilderness...

The goal is always the same:

Create adventures worth telling.

---

# Roadmap

Some planned features include:

- Spell based encounters
- Character Perks & Flaws
- Improved UI
- Reputation system
- Procedural quests
- World events
- Lasting injuries
- Weather
- Additional classes
- Additional races
- More dungeons
- Boss encounters
- Improved AI
- Additional Biomes
- Procedural world history
- Custom Font

---

# Gallery

<div align="center">

<img width="1919" height="1002" alt="Image" src="https://github.com/user-attachments/assets/a2870322-aa2e-44e0-8ee7-2f2f7af61088" />

<img width="1919" height="1005" alt="Image" src="https://github.com/user-attachments/assets/89ede48c-5e1b-4ed2-802d-6f1375f75667" />

</div>
---

# Controls

| Key | Action |
| --- | --- |
| Arrow keys / `WASD` / numpad | Move, or attack an adjacent enemy by moving into it |
| `F1` | Set interaction mode to Dialogue |
| `F2` | Set interaction mode to Steal |
| `F3` | Set interaction mode to Interact, for ground items and loot |
| `F4` | Set interaction mode to Info, for surroundings and companion orders |
| `F` | Use the selected interaction mode; talk, trade, inspect, pick up, or interact |
| `I` | Open or close inventory |
| `C` | Open or close the character menu |
| `R` | Open the short-rest or long-rest menu |
| `Q` / `E` | Use quick-bar slots for a torch or potion |
| `Enter` / `Space` | Confirm menu choices, advance book pages, or continue prompts |
| `Escape` | Cancel, go back, or close the current overlay |
| Mouse wheel | Scroll the message log or zoom the game view |
| `R` / `Q` on the game-over screen | Restart / quit |

Some actions open their own numbered menus. Read the on-screen prompt before choosing an option.

## Project Structure

- `main.py` - Pygame application entry point and main loop.
- `core/` - Game state, rendering, combat, abilities, field of view, inventory, stories, and UI.
- `entities/` - Players, races, monsters, NPCs, summons, and combat companions.
- `world/` - Dungeon and overworld generation, tiles, structures, lighting, maps, encounters, and world time.
- `items/` - Equipment, consumables, books, chests, and loot generation.
- `content/` - JSON-authored books, encounters, and story campaigns.
- `assets/` - Tileset and logo resources.

## Development Notes

- The game is actively developed and does not currently include a save/load system.
- Procedural generation is deterministic where the relevant generator is given a seed, but a complete run still depends on gameplay choices and random rolls.
- Content is data-driven where practical: add books, encounters, and story material under `content/` rather than hardcoding narrative text into the game loop.

## Inspiration and Legal

Mithrim draws inspiration from Dungeons & Dragons, Daggerfall, Dungeon Crawl Stone Soup, Tales of Maj'Eyal, Caves of Qud, ADOM, Brogue, Baldur's Gate, and Pathfinder.

It is a fan project inspired by Dungeons & Dragons 5th Edition. See [LICENSE.md](LICENSE.md) and [CREDITS.md](CREDITS.md) for licensing and attribution information.

<div align="center">

### *Every road hides a story.*

</div>
