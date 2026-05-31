import random
from world.tile import PrisonDoorTile, floor, wall, prison_bars
from entities.dungeon_npcs import PrisonerNPC
from world.water_features import is_water_tile


# ─────────────────────────────────────────────────────────────────────────────
#  Geometry constants
# ─────────────────────────────────────────────────────────────────────────────

# Minimum rows each cell needs:  1 bar + 1 door + 1 bar  = 3 rows per cell.
# Plus 1 divider row between them  → MIN_INNER_HEIGHT = 3 + 1 + 3 = 7.
MIN_CELL_HEIGHT  = 3   # rows per individual cell (bars above + door + bars below)
MIN_INNER_HEIGHT = MIN_CELL_HEIGHT * 2 + 1   # 7  (two cells + divider row)

# Cell interior depth: columns between the bars column and the room wall.
CELL_FLOOR_DEPTH = 2

# Minimum inner width:  1 open corridor col + 1 bars col + CELL_FLOOR_DEPTH
MIN_INNER_WIDTH  = 1 + 1 + CELL_FLOOR_DEPTH   # = 4


# ─────────────────────────────────────────────────────────────────────────────
#  Layout (east orientation example)
# ─────────────────────────────────────────────────────────────────────────────
#
#   col →          open_cols  │  bars_col  │  floor_cols  │ (east room wall)
#                             │            │              │
#   row ↓   ...  open floor   │    bar     │  cell A      │
#           ...  open floor   │    door A  │  cell A      │   ← cell A
#           ...  open floor   │    bar     │  cell A      │
#           ...  open floor   │   (wall)   │  (wall)      │   ← divider row
#           ...  open floor   │    bar     │  cell B      │
#           ...  open floor   │    door B  │  cell B      │   ← cell B
#           ...  open floor   │    bar     │  cell B      │
#
#   WEST mirrors this horizontally (bars column near the west room wall).


# ─────────────────────────────────────────────────────────────────────────────
#  Public query helper
# ─────────────────────────────────────────────────────────────────────────────

def is_prison_cell_position(game_map, tile_x, tile_y):
    """
    Return True if (tile_x, tile_y) belongs to any placed prison cell.
    Other spawners call this to avoid placing items or monsters inside cells.
    """
    return (tile_x, tile_y) in getattr(game_map, 'prison_cell_tiles', set())


# ─────────────────────────────────────────────────────────────────────────────
#  Public carver
# ─────────────────────────────────────────────────────────────────────────────

def generate_prison_cell(game_map, room, entities, stairs_positions):
    """
    Carve two stacked (top/bottom) prison cells into the east or west wall
    of *room*.  Both cells share one bars column; a single wall row divides
    them horizontally.

    On success:
      - Stamps bar, door, wall, and floor tiles onto game_map.
      - Registers every written tile in game_map.prison_cell_tiles.
      - Appends two PrisonerNPC instances to *entities*.

    Returns a list of two (PrisonerNPC, (door_col, door_row)) pairs,
    or None if the room is too small or all orientations are blocked.
    """
    if not hasattr(game_map, 'prison_cell_tiles'):
        game_map.prison_cell_tiles = set()

    # Inner extents (room outer wall tiles excluded).
    first_inner_col = room.x1 + 1
    first_inner_row = room.y1 + 1
    last_inner_col  = room.x2 - 1
    last_inner_row  = room.y2 - 1

    inner_width  = last_inner_col - first_inner_col + 1
    inner_height = last_inner_row - first_inner_row + 1

    if inner_width < MIN_INNER_WIDTH or inner_height < MIN_INNER_HEIGHT:
        return None

    orientations = ['east', 'west']
    random.shuffle(orientations)

    for orientation in orientations:
        result = _attempt_carve(
            game_map, orientation,
            first_inner_col, first_inner_row,
            last_inner_col,  last_inner_row,
            inner_width,     inner_height,
            entities, stairs_positions,
        )
        if result is not None:
            return orientation, result   

    return None, None


# ─────────────────────────────────────────────────────────────────────────────
#  Internal carver
# ─────────────────────────────────────────────────────────────────────────────

def _attempt_carve(
    game_map, orientation,
    first_inner_col, first_inner_row,
    last_inner_col,  last_inner_row,
    inner_width,     inner_height,
    entities, stairs_positions,
):
    """
    Try to carve the stacked dual-cell for one orientation.
    Returns a list of two (PrisonerNPC, (door_col, door_row)) or None.
    """

    # ── Assign the bars column and cell floor columns ─────────────────────
    #
    # EAST: bars column is near the east room wall; floor columns are to its
    #       right (between bars and east wall).  The open corridor is to the
    #       left of the bars column.
    #
    # WEST: mirror image — bars near west wall, floor to its left.

    if orientation == 'east':
        bars_col   = last_inner_col - CELL_FLOOR_DEPTH
        floor_cols = list(range(bars_col + 1, last_inner_col + 1))
        if bars_col <= first_inner_col:   # no open corridor space left
            return None

    else:  # 'west'
        bars_col   = first_inner_col + CELL_FLOOR_DEPTH
        floor_cols = list(range(first_inner_col, bars_col))
        if bars_col >= last_inner_col:
            return None

    # ── Split inner rows into top cell / divider / bottom cell ───────────
    #
    # Give each cell as equal a height as possible; any leftover rows go to
    # the top cell.  Both cells need at least MIN_CELL_HEIGHT rows.

    usable_rows  = inner_height - 1          # subtract 1 for the divider row
    cell_a_height = usable_rows // 2
    cell_b_height = usable_rows - cell_a_height

    if cell_a_height < MIN_CELL_HEIGHT or cell_b_height < MIN_CELL_HEIGHT:
        return None

    cell_a_top    = first_inner_row
    cell_a_bottom = cell_a_top + cell_a_height - 1       # inclusive
    divider_row   = cell_a_bottom + 1
    cell_b_top    = divider_row + 1
    cell_b_bottom = last_inner_row

    # Door rows sit in the vertical centre of each cell.
    door_row_a = (cell_a_top + cell_a_bottom) // 2
    door_row_b = (cell_b_top + cell_b_bottom) // 2

    # Prisoners stand one tile inside (on the floor column nearest the bars).
    if orientation == 'east':
        prisoner_col = bars_col + 2
    else:
        prisoner_col = bars_col - 2

    # ── Collect every position we will overwrite ──────────────────────────
    all_rows      = list(range(first_inner_row, last_inner_row + 1))
    affected_cols = [bars_col] + floor_cols

    positions_to_write = [
        (col, row)
        for col in affected_cols
        for row in all_rows
    ]

    # ── Validate every position before touching the map ───────────────────
    for col, row in positions_to_write:
        if not (0 <= col < game_map.width and 0 <= row < game_map.height):
            return None
        if stairs_positions and (col, row) in stairs_positions.values():
            return None
        if is_water_tile(game_map.tiles[row][col]):
            return None

    for door_row in (door_row_a, door_row_b):
        if not (0 <= prisoner_col < game_map.width and
                0 <= door_row < game_map.height):
            return None
        if any(e.x == prisoner_col and e.y == door_row for e in entities):
            return None

    # ── Stamp tiles ───────────────────────────────────────────────────────
    for row in all_rows:

        if row == divider_row:
            # Full-width wall row separating the two cells.
            game_map.tiles[row][bars_col] = wall
            for col in floor_cols:
                game_map.tiles[row][col] = wall
            continue

        # Determine which cell this row belongs to.
        in_cell_a = (cell_a_top <= row <= cell_a_bottom)
        in_cell_b = (cell_b_top <= row <= cell_b_bottom)

        # Bars column — door at the cell's centre row, bars elsewhere.
        if in_cell_a:
            game_map.tiles[row][bars_col] = (
                PrisonDoorTile() if row == door_row_a else prison_bars
            )
        elif in_cell_b:
            game_map.tiles[row][bars_col] = (
                PrisonDoorTile() if row == door_row_b else prison_bars
            )

        # Cell interior — always floor.
        for col in floor_cols:
            game_map.tiles[row][col] = floor

    # ── Register the footprint so other spawners skip these tiles ─────────
    for col, row in positions_to_write:
        game_map.prison_cell_tiles.add((col, row))

    # ── Place the two prisoners (one per cell, near their door) ──────────
    prisoner_a = PrisonerNPC(prisoner_col, door_row_a)
    prisoner_b = PrisonerNPC(prisoner_col, door_row_b)
    entities.append(prisoner_a)
    entities.append(prisoner_b)

    return [
        (prisoner_a, (bars_col, door_row_a)),
        (prisoner_b, (bars_col, door_row_b)),
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  'F' key interaction handler  (called from game.py)
# ─────────────────────────────────────────────────────────────────────────────

def handle_prison_door_interaction(player, game_instance):
    """
    Check the four cardinal tiles adjacent to *player* for a PrisonDoorTile.
    If one is found, run an Athletics or Thieves'-Tools skill check to open it.

    Opening the door does NOT give any reward — the prisoner gives their
    reward when the player talks to them (F key while adjacent).

    Returns True if any interaction was handled (caller should consume the
    key event regardless of success or failure).
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

        # ── Skill check ───────────────────────────────────────────────────
        player_has_thieves_tools = (
            hasattr(player, 'has_thieves_tools') and player.has_thieves_tools()
        )

        if player_has_thieves_tools:
            skill_bonus      = (player.get_ability_modifier(player.dexterity)
                                + player.proficiency_bonus)
            skill_label      = "Thieves' Tools (DEX)"
            difficulty_class = 12
        else:
            skill_bonus      = (player.get_ability_modifier(player.strength)
                                + player.proficiency_bonus)
            skill_label      = "Athletics (STR)"
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
            neighbour_tile.char      = 'pdo'

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
                    "OPEN!", (100, 255, 100), y_speed=0.5,
                )
            )

            # Free the nearest unfreed prisoner within 3 tiles of this door.
            # No reward yet — that comes when the player talks to them.
            for entity in game_instance.entities:
                if isinstance(entity, PrisonerNPC) and not entity.has_been_freed:
                    chebyshev_dist = max(
                        abs(entity.x - neighbour_col),
                        abs(entity.y - neighbour_row),
                    )
                    if chebyshev_dist <= 3:
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
                "LOCKED!", (255, 80, 80), y_speed=0.5,
            )
        )
        return True     # event consumed even on failure

    return False        # no prison door was adjacent