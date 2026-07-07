# Mithrim

<img width="1621" height="985" alt="mithrim_bg" src="https://github.com/user-attachments/assets/aa4b1c03-84a8-4b92-9981-03bcaeea1d2e" />

Mithrim is a turn-based open-world roguelike RPG inspired by Dungeons & Dragons 5e, built from scratch in Python using Pygame.

Explore a procedurally generated world filled with forests, rivers, roads, dungeons, settlements, wandering monsters, merchants, and hidden secrets. Create a unique adventurer, build your character through race and class choices, uncover powerful equipment, and survive increasingly dangerous encounters in a world where every playthrough is different.

---

## 🚀 Features

### 🌍 Procedural Open World
Instead of isolated dungeon floors, Mithrim generates an expansive overworld containing:
- 🌲 Dense forests and grasslands
- 🌊 Rivers generated using procedural river carving
- 🛣️ Roads connecting settlements
- 🏡 Villages and taverns
- ⛰️ Multiple dungeon entrances
- 🐺 Wildlife and roaming monsters
- ⚡ Dynamic chunk loading for virtually unlimited exploration

*Every world is generated from a random seed, making each adventure unique.*

### ⚔️ Tactical D&D-inspired Combat
Combat follows a fully turn-based initiative system inspired by D&D 5e. Features include:
- **Initiative order** & **Tactical positioning**
- **Opportunity attacks** & **Critical hits/failures**
- **Saving throws** with **Advantage & disadvantage**
- **Status effects**, **Melee/ranged combat**, and **Spellcasting**

*Every creature has its own statistics including Armor Class, attack modifiers, proficiencies, resistances, movement speed, and AI behavior.*

### 🎭 Character Creation
Create a unique adventurer by choosing from multiple races, subraces, and classes.

#### **Races**
- Human, Elf, Dwarf, Dragonborn, Tiefling
- *Numerous subraces from Humans, Wood Elves, to Duergars providing unique:* Ability score bonuses, weapon proficiencies, resistances, movement traits, darkvision, and racial abilities.

#### **Classes**
- Fighter, Rogue, Wizard, Cleric
- *Each class includes exclusive abilities inspired by D&D 5e.*

### 👾 Massive Bestiary
Mithrim currently contains **50+ handcrafted entities**, including monsters, NPCs, wildlife, merchants, dungeon inhabitants, and bosses. Enemies range from common goblins and wolves to dragons, mind flayers, beholders, demons, and legendary bosses.
- 🧠 Unique AI & Combat abilities
- ⚔️ Different equipment & Status effects
- 💰 Loot tables & Spawn rules

### 🏙️ Living World
The world is populated by interactive NPCs that offer:
- 🤝 Trading & Dialogue
- 💤 Resting & Healing
- 🗺️ Quest hubs *(planned)*

*Players encounter wandering enemies, settlements, merchants, environmental hazards, and hidden encounters while exploring.*

### 🏰 Procedural Dungeon Generation
Every dungeon is generated on demand with:
- 🗺️ Unique room layouts & Corridors
- 💧 Rivers, Lakes, and Environmental hazards
- ⛩️ Hidden altars, Traps, and Mimics
- 💎 Loot rooms & Random monster populations

*No two dungeons are exactly alike.*

### 🕯️ Exploration
Explore using a dynamic visibility system featuring:
- 👁️ Shadowcasting Field of View (FoV)
- 🕶️ Darkvision, Torches, and Wall-mounted light sources
- 🌫️ Fog of war & Persistent explored areas

*Darkness is an important gameplay mechanic rather than simply an aesthetic choice.*

### 📈 Progression
- **Level 1–20** advancement
- **Gain experience** from combat
- **Unlock** new class abilities & improve proficiency bonus
- **Equip** increasingly powerful gear & discover magical equipment
- **Face** progressively stronger enemies

### 🛡️ Equipment System
Collect and equip a wide variety of equipment including:
- ⚔️ **Weapons & Armor:** Shields, Helmets, Boots
- 💍 **Magical Accessories:** Spellcasting focuses, Scrolls
- 🧪 **Consumables:** Potions, Food

*Equipment directly affects combat statistics and character builds.*

### 🧪 Status Effects
Combat features numerous temporary effects including:
- **Buffs:** Blessings, Divine Strike, Hidden, Prepared, Parry, Power Attack
- **Debuffs:** Poison, Burning, Acid Burn, Blindness, Rot, Weakness

---

## ⚙️ Performance & Optimization
Despite generating a large procedural world, Mithrim includes several optimization systems:
- 🧩 Chunk-based world streaming
- 🖼️ Surface caching & Dirty rectangle rendering
- 🎥 Camera interpolation
- 👁️ Efficient shadowcasting & Optimized A* pathfinding
- ⏳ Procedural generation performed only when needed

---

## 🛠️ Built With
- **Language:** Python
- **Framework:** Pygame
- **Core Systems:** Procedural Generation, A* Pathfinding, Chunk Streaming, Shadowcasting Field of View, Finite State Machine AI, D&D 5e-inspired Ruleset

---

## 📊 Project Status

### **Current Features**
- [x] Procedural overworld & Procedural dungeons
- [x] Chunk streaming & Dynamic rivers
- [x] NPC interactions & Merchant system
- [x] Inventory & Equipment systems
- [x] Turn-based combat & Initiative system
- [x] Status effects & Monster AI
- [x] Character progression (100+ entities)
- [x] Procedural loot, Traps, and Altars
- [x] Field of View & Zoomable camera

### **Planned Features**
- [ ] Quest system
- [ ] Additional towns and settlements
- [ ] More biome variety
- [ ] Additional classes & More bosses
- [ ] Unique monster abilities
- [ ] World events & Better NPC schedules
- [ ] Save/load system

---

## 🎯 Project Goals
Mithrim aims to combine traditional roguelikes, tabletop RPG mechanics, procedural world generation, and modern quality-of-life features into a replayable single-player adventure where exploration is just as important as combat.

---

## ⚖️ Disclaimer
Mithrim is an independent, non-commercial fan project inspired by tabletop role-playing games. It is not affiliated with or endorsed by Wizards of the Coast LLC. Dungeons & Dragons and all related trademarks remain the property of Wizards of the Coast LLC.