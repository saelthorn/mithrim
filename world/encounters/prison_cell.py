import random
from world.tile import PrisonDoorTile, floor, wall, prison_bars
from entities.dungeon_npcs import PrisonerNPC
from world.water_features import is_water_tile


# ─────────────────────────────────────────────────────────────────────────────
#  Geometry constants
# ─────────────────────────────────────────────────────────────────────────────

# Total height of the bar-and-door window (must be odd so the door sits centre).
# 5 = 2 bars above door + 1 door + 2 bars below.
# This keeps MIN_INNER_HEIGHT at 7, which every room satisfies since
# room_min_size=8 guarantees an inner height of at least 7.
BAR_WINDOW_HEIGHT = 7

# How many floor columns sit between the bars column and the room wall.
CELL_FLOOR_DEPTH  = 2

# Minimum inner dimensions for the cell to fit.
# inner = room interior excluding the outer wall tiles.
MIN_INNER_HEIGHT = BAR_WINDOW_HEIGHT + 2   # 5 + 2 = 7  (fits in every room >= size 9 total)
MIN_INNER_WIDTH  = 1 + 1 + CELL_FLOOR_DEPTH + 2   # seal + bars + floor + 2 open cols = 6


# ─────────────────────────────────────────────────────────────────────────────
#  Public query helper
# ─────────────────────────────────────────────────────────────────────────────

def is_prison_cell_position(game_map, tile_x, tile_y):
    """
    Return True if (tile_x, tile_y) belongs to any placed prison cell
    (includes bar tiles, the door tile, and cell-interior floor tiles).
    Spawners call this to avoid placing things inside the cell.
    """
    return (tile_x, tile_y) in getattr(game_map, 'prison_cell_tiles', set())


# ─────────────────────────────────────────────────────────────────────────────
#  Public carver
# ─────────────────────────────────────────────────────────────────────────────

def generate_prison_cell(game_map, room, entities, stairs_positions):
    """
    Carve a double-barred prison cell into the east OR west inner wall of *room*.

    Tries both orientations in random order.  On success:
      - stamps bar, door, wall and floor tiles onto game_map
      - registers every written tile in game_map.prison_cell_tiles
      - appends a PrisonerNPC to *entities*

    Parameters
    ----------
    game_map         : GameMap  — the active dungeon map
    room             : RectRoom — the room to carve into
    entities         : list     — PrisonerNPC is appended here on success
    stairs_positions : dict     — {'up': (x,y), 'down': (x,y)}

    Returns
    -------
    (PrisonerNPC, (door_col, door_row))   on success
    None                                   if the room is too small or blocked
    """
    if not hasattr(game_map, 'prison_cell_tiles'):
        game_map.prison_cell_tiles = set()

    # Inner extents: first and last walkable tile (room outer walls excluded).
    first_inner_col = room.x1 + 1
    first_inner_row = room.y1 + 1
    last_inner_col  = room.x2 - 1   # room.x2 itself is the east wall tile
    last_inner_row  = room.y2 - 1

    inner_width  = last_inner_col - first_inner_col + 1
    inner_height = last_inner_row - first_inner_row + 1

    if inner_width < MIN_INNER_WIDTH or inner_height < MIN_INNER_HEIGHT:
        return None

    orientations = ['east', 'west']
    random.shuffle(orientations)

    for orientation in orientations:
        result = _attempt_carve(
            game_map,
            orientation,
            first_inner_col,
            first_inner_row,
            last_inner_col,
            last_inner_row,
            inner_height,
            entities,
            stairs_positions,
        )
        if result is not None:
            return result

    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Internal carver
# ─────────────────────────────────────────────────────────────────────────────

def _attempt_carve(
    game_map,
    orientation,
    first_inner_col,
    first_inner_row,
    last_inner_col,
    last_inner_row,
    inner_height,
    entities,
    stairs_positions,
):
    """
    Try to carve the cell for one specific orientation ('east' or 'west').
    Returns (PrisonerNPC, (door_col, door_row)) or None.
    """

    # ── Assign the four working columns ───────────────────────────────────
    #
    # For EAST we work inward from the east room wall:
    #   cell_far_col  = last inner col  (floor, against east room wall)
    #   cell_near_col = one step inward (floor, prisoner stands here)
    #   bars_col      = two steps inward (bars / door)
    #   seal_col      = three steps inward (full-height wall facing the room)
    #
    # WEST is the mirror image working from the west room wall.

    if orientation == 'east':
        cell_far_col  = last_inner_col
        cell_near_col = last_inner_col  - 1
        bars_col      = last_inner_col  - 3
        seal_col      = last_inner_col  - 3
        if seal_col < first_inner_col:
            return None
        prisoner_col = cell_near_col

    else:   # 'west'
        cell_far_col  = first_inner_col
        cell_near_col = first_inner_col + 1
        bars_col      = first_inner_col + 3
        seal_col      = first_inner_col + 3
        if seal_col > last_inner_col:
            return None
        prisoner_col = cell_near_col

    # ── Centre the bar window vertically ──────────────────────────────────
    centre_row        = first_inner_row + inner_height // 2
    bar_window_half   = BAR_WINDOW_HEIGHT // 2      # = 3
    bar_window_top    = centre_row - bar_window_half
    bar_window_bottom = bar_window_top + BAR_WINDOW_HEIGHT - 1   # inclusive
    door_row          = centre_row

    # Safety clamp (only triggers in rooms smaller than MIN_INNER_HEIGHT)
    bar_window_top    = max(bar_window_top,    first_inner_row + 1)
    bar_window_bottom = min(bar_window_bottom, last_inner_row  - 1)
    door_row          = (bar_window_top + bar_window_bottom) // 2

    prisoner_row = door_row

    # ── Build complete list of positions we will write ────────────────────
    positions_to_write = []
    for row in range(first_inner_row, last_inner_row + 1):
        positions_to_write.append((seal_col,      row))
        positions_to_write.append((bars_col,      row))
        positions_to_write.append((cell_near_col, row))
        positions_to_write.append((cell_far_col,  row))

    # ── Validate every position before touching the map ───────────────────
    for write_col, write_row in positions_to_write:
        if not (0 <= write_col < game_map.width and 0 <= write_row < game_map.height):
            return None
        if stairs_positions and (write_col, write_row) in stairs_positions.values():
            return None
        if is_water_tile(game_map.tiles[write_row][write_col]):
            return None

    if not (0 <= prisoner_col < game_map.width and 0 <= prisoner_row < game_map.height):
        return None

    if any(entity.x == prisoner_col and entity.y == prisoner_row for entity in entities):
        return None

    # ── Stamp every tile ──────────────────────────────────────────────────
    for row in range(first_inner_row, last_inner_row + 1):
        row_is_in_bar_window = (bar_window_top <= row <= bar_window_bottom)


        # Bars column: bars or door inside the window, wall outside it.
        if row_is_in_bar_window:
            if row == door_row:
                game_map.tiles[row][bars_col] = PrisonDoorTile()
            else:
                game_map.tiles[row][bars_col] = prison_bars
        else:
            game_map.tiles[row][bars_col] = wall

        # Cell interior: always floor (prisoner walks here).
        game_map.tiles[row][cell_near_col] = floor
        game_map.tiles[row][cell_far_col]  = floor

    # ── Register cell footprint so spawners can avoid these tiles ─────────
    for written_col, written_row in positions_to_write:
        game_map.prison_cell_tiles.add((written_col, written_row))

    # ── Place the prisoner ─────────────────────────────────────────────────
    prisoner = PrisonerNPC(prisoner_col, prisoner_row)
    entities.append(prisoner)

    return prisoner, (bars_col, door_row)


# ─────────────────────────────────────────────────────────────────────────────
#  'F' key interaction handler  (called from game.py)
# ─────────────────────────────────────────────────────────────────────────────

def handle_prison_door_interaction(player, game_instance):
    """
    Check the four cardinal tiles adjacent to *player* for a PrisonDoorTile.
    If one is found, run an Athletics or Thieves'-Tools skill check to open it.

    Returns True if any interaction was handled (the caller should consume the
    key event regardless of success or failure so other handlers don't fire).
    """
    game_map = game_instance.game_map

    for delta_col, delta_row in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        neighbour_col = player.x + delta_col
        neighbour_row = player.y + delta_row

        if not (0 <= neighbour_col < game_map.width and
                0 <= neighbour_row < game_map.height):
            continue

        neighbour_tile = game_map.tiles[neighbour_row][neighbour_col]
        if not isinstance(neighbour_tile, PrisonDoorTile):
            continue

        # ── Door already open ─────────────────────────────────────────────
        if neighbour_tile.is_open:
            game_instance.message_log.add_message(
                "The prison door is already open.", (150, 150, 150)
            )
            return True

        # ── Build the skill check ─────────────────────────────────────────
        player_has_thieves_tools = (
            hasattr(player, 'has_thieves_tools') and player.has_thieves_tools()
        )

        if player_has_thieves_tools:
            skill_bonus = (
                player.get_ability_modifier(player.dexterity)
                + player.proficiency_bonus
            )
            skill_label    = "Thieves' Tools (DEX)"
            difficulty_class = 12
        else:
            skill_bonus = (
                player.get_ability_modifier(player.strength)
                + player.proficiency_bonus
            )
            skill_label    = "Athletics (STR)"
            difficulty_class = 15

        die_roll    = random.randint(1, 20)
        check_total = die_roll + skill_bonus

        game_instance.message_log.add_message(
            f"You try to force the prison door — {skill_label}: "
            f"[{die_roll}] + {skill_bonus} = {check_total} (DC {difficulty_class})",
            (200, 200, 255),
        )

        # ── Success ───────────────────────────────────────────────────────
        if check_total >= difficulty_class:
            neighbour_tile.is_open   = True
            neighbour_tile.is_locked = False
            neighbour_tile.blocked   = False
            neighbour_tile.char      = 'pdo'    # open-door graphic key in graphics.py

            success_messages = [
                "The prison door swings open with a groan of rusty hinges!",
                "With a sharp crack the lock gives way — the door is open!",
                "You wrench the door free; metal screeches against stone.",
                "The old lock shatters. The cell is open.",
            ]
            game_instance.message_log.add_message(
                random.choice(success_messages), (100, 255, 100)
            )

            from core.floating_text import FloatingText
            game_instance.floating_texts.append(
                FloatingText(
                    neighbour_col, neighbour_row,
                    "OPEN!", (100, 255, 100),
                    y_speed=0.5,
                )
            )

            # Free the nearest prisoner within 2 tiles of the door.
            for entity in game_instance.entities:
                if isinstance(entity, PrisonerNPC) and not entity.has_been_freed:
                    chebyshev_distance = max(
                        abs(entity.x - neighbour_col),
                        abs(entity.y - neighbour_row),
                    )
                    if chebyshev_distance <= 2:
                        entity.free(player, game_instance)
                        break

            game_instance.update_fov()
            return True

        # ── Failure ───────────────────────────────────────────────────────
        failure_messages = [
            "The door holds firm — you need more force or the right tools.",
            "The rusty lock refuses to budge.",
            "The hinges groan but the door doesn't move.",
            "Not enough. The door mocks your effort.",
            "You strain against the iron frame — it doesn't give.",
        ]
        game_instance.message_log.add_message(
            random.choice(failure_messages), (255, 100, 100)
        )

        from core.floating_text import FloatingText
        game_instance.floating_texts.append(
            FloatingText(
                neighbour_col, neighbour_row,
                "LOCKED!", (255, 80, 80),
                y_speed=0.5,
            )
        )
        return True     # event consumed even on failure

    return False        # no prison door was adjacent