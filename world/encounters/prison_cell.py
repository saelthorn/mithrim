import random
from world.tile import Tile, PrisonDoorTile, floor, prison_bars
from entities. dungeon_npcs import PrisonerNPC




# ─────────────────────────────────────────────────────────────────
#  Room carver
# ─────────────────────────────────────────────────────────────────

def generate_prison_cell(game_map, room, entities, stairs_positions):
    """
    Carves a 3-wide prison cell into the south inner wall of *room*.

    Layout (south end of room, viewed from above):
        ── ── ──    ← normal floor
        pb pd pb   ← prison bars row  (bars left/right, door center)
        fl fl fl   ← cell interior (floor, prisoner inside)
        ## ## ##   ← south room wall

    Returns (PrisonerNPC, door_position) on success, or None.
    """
    from world.water_features import is_water_tile

    room_w = room.x2 - room.x1
    room_h = room.y2 - room.y1

    if room_w < 7 or room_h < 5:
        return None

    center_x = (room.x1 + room.x2) // 2
    bars_y   = room.y2 - 2   # one row above south wall
    cell_y   = room.y2 - 1   # the cell interior row (against south wall)

    needed = [
        (center_x - 1, bars_y), (center_x, bars_y), (center_x + 1, bars_y),
        (center_x - 1, cell_y), (center_x,  cell_y), (center_x + 1, cell_y),
    ]

    for px, py in needed:
        if not (0 <= px < game_map.width and 0 <= py < game_map.height):
            return None
        if stairs_positions and (px, py) in stairs_positions.values():
            return None
        if any(e.x == px and e.y == py for e in entities):
            return None
        if is_water_tile(game_map.tiles[py][px]):
            return None

    # ── Carve bars row ────────────────────────────────────────────
    game_map.tiles[bars_y][center_x - 1] = prison_bars
    door_tile = PrisonDoorTile()
    game_map.tiles[bars_y][center_x]     = door_tile
    game_map.tiles[bars_y][center_x + 1] = prison_bars

    # ── Carve cell interior ───────────────────────────────────────
    for ox in (-1, 0, 1):
        game_map.tiles[cell_y][center_x + ox] = floor

    # ── Place prisoner ────────────────────────────────────────────
    prisoner = PrisonerNPC(center_x, cell_y)
    entities.append(prisoner)

    return prisoner, (center_x, bars_y)


# ─────────────────────────────────────────────────────────────────
#  Interaction handler  (called from game.py on 'F' key)
# ─────────────────────────────────────────────────────────────────

def handle_prison_door_interaction(player, game_instance):
    """
    Checks all four cardinal neighbours of *player* for a PrisonDoorTile.
    If found, runs a skill check to open it.

    Returns True if an interaction was handled (caller should consume the event).
    """
    gm = game_instance.game_map

    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = player.x + dx, player.y + dy
        if not (0 <= nx < gm.width and 0 <= ny < gm.height):
            continue

        tile = gm.tiles[ny][nx]
        if not isinstance(tile, PrisonDoorTile):
            continue

        # ── Already open ─────────────────────────────────────────
        if tile.is_open:
            game_instance.message_log.add_message(
                "The prison door is already open.", (150, 150, 150)
            )
            return True

        # ── Skill check ──────────────────────────────────────────
        has_tools = (
            hasattr(player, 'has_thieves_tools') and player.has_thieves_tools()
        )
        if has_tools:
            bonus      = (player.get_ability_modifier(player.dexterity)
                          + player.proficiency_bonus)
            skill_name = "Thieves' Tools (DEX)"
            dc         = 12
        else:
            bonus      = (player.get_ability_modifier(player.strength)
                          + player.proficiency_bonus)
            skill_name = "Athletics (STR)"
            dc         = 15

        roll  = random.randint(1, 20)
        total = roll + bonus

        game_instance.message_log.add_message(
            f"You try to force the prison door — {skill_name}: "
            f"[{roll}] + {bonus} = {total} (DC {dc})",
            (200, 200, 255),
        )

        # ── Success ──────────────────────────────────────────────
        if total >= dc:
            tile.is_open   = True
            tile.is_locked = False
            tile.blocked   = False
            tile.char      = 'pdo'   # open-door graphic (add to graphics.py)

            success_msgs = [
                "The prison door swings open with a groan of rusty hinges!",
                "With a sharp crack the lock gives way — the door is open!",
                "You wrench the door free; metal screeches against stone.",
            ]
            game_instance.message_log.add_message(
                random.choice(success_msgs), (100, 255, 100)
            )
            from core.floating_text import FloatingText
            game_instance.floating_texts.append(
                FloatingText(nx, ny, "OPEN!", (100, 255, 100), y_speed=0.5)
            )

            # Free any prisoner within 2 tiles of the door
            for entity in game_instance.entities:
                if isinstance(entity, PrisonerNPC) and not entity.has_been_freed:
                    if max(abs(entity.x - nx), abs(entity.y - ny)) <= 2:
                        entity.free(player, game_instance)
                        break

            game_instance.update_fov()
            return True

        # ── Failure ──────────────────────────────────────────────
        fail_msgs = [
            "The door holds firm — you need more force or the right tools.",
            "The rusty lock refuses to budge.",
            "The hinges groan but the door doesn't move.",
            "Not enough. The door mocks your effort.",
        ]
        game_instance.message_log.add_message(
            random.choice(fail_msgs), (255, 100, 100)
        )
        game_instance.floating_texts.append(
            FloatingText(nx, ny, "LOCKED!", (255, 80, 80), y_speed=0.5)
        )
        return True   # event consumed even on failure

    return False   # no door adjacent