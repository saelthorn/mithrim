import random
from world.tile import Tile, PrisonDoorTile, floor, wall, prison_bars
from entities.dungeon_npcs import PrisonerNPC
from world.water_features import is_water_tile


# ─────────────────────────────────────────────────────────────────────────────
#  Blueprint constants
# ─────────────────────────────────────────────────────────────────────────────

# Cell marker characters used in the stamp template
_W  = 'W'   # wall  (keep/overwrite with room wall)
_B  = 'B'   # prison_bars
_D  = 'D'   # prison door
_F  = 'F'   # floor (cell interior)
_R  = 'R'   # room floor (threshold row, already floor – leave as-is)

# SOUTH-orientation template:  rows run top→bottom, cols left→right.
# Row 0 = deepest inside the wall (against south room edge).
# Row 3 = threshold row inside the room (player stands here).
#
#   col:  0   1   2   3   4   5   6
#         ─── ─── ─── ─── ─── ─── ───
# row 0:  [W] [W] [W] [W] [W] [W] [W]   ← part of south room wall – skip
# row 1:  [W] [B] [B] [D] [B] [B] [W]   ← bars row
# row 2:  [W] [F] [F] [F] [F] [F] [W]   ← cell interior
# row 3:  [R] [R] [R] [R] [R] [R] [R]   ← threshold (normal floor, skip)
#
# We only write rows 1 and 2.  Row 0 (wall) and row 3 (floor) already exist.
# The side walls at col 0 and col 6 of rows 1-2 must be overwritten with wall
# so the cell sides are sealed.

_TEMPLATE_SOUTH = [
    # (col_offset, row_offset, marker)
    # row 1 — bars row (1 tile north of the south room wall)
    (0, 1, _W),  (1, 1, _B),  (2, 1, _B), (2, 1, _B),  (3, 1, _D),  (4, 1, _B),  (5, 1, _B),  (6, 1, _B), (6, 1, _W),
    # # row 2 — cell interior (against south wall)
    # (0, 2, _F),  (1, 2, _F),  (2, 2, _F),  (3, 2, _F),  (4, 2, _F),  (5, 2, _F),  (6, 2, _F), (6, 2, _F),
]

# Prisoner position relative to top-left origin of the stamp (row 2, col 3):
_PRISONER_REL_SOUTH = (3, 3)


def _rotate_south_to(orientation, stamp_w, stamp_h):
    """
    Take the SOUTH template entries (col_off, row_off, marker) and
    rotate/reflect them for the desired orientation.

    orientation is one of 'S', 'N', 'E', 'W'.
    stamp_w, stamp_h  are the dimensions of the SOUTH template bounding box
    (7 wide × 3 tall for the writable rows 0-2, but we pass the full 7×4).
    """
    W, H = stamp_w - 1, stamp_h - 1   # max indices

    def transform(c, r):
        if orientation == 'S':
            return c, r
        elif orientation == 'N':
            # Mirror vertically (flip row)
            return c, H - r
        elif orientation == 'E':
            # Rotate 90° clockwise: (c,r) → (H-r, c)   [using square assumption H==W]
            # We have a non-square stamp so use: new_col = H-r, new_row = c
            return H - r, c
        elif orientation == 'W':
            # Rotate 90° counter-clockwise: (c,r) → (r, W-c)
            return r, W - c

    result = []
    for c, r, marker in _TEMPLATE_SOUTH:
        nc, nr = transform(c, r)
        result.append((nc, nr, marker))
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Tile helper
# ─────────────────────────────────────────────────────────────────────────────

def _tile_for_marker(marker):
    """Return the actual Tile object or a new PrisonDoorTile for a marker."""
    if marker == _W:
        return wall
    elif marker == _B:
        return prison_bars
    elif marker == _D:
        return PrisonDoorTile()   # fresh instance so state is independent
    elif marker == _F:
        return floor
    return None   # _R → leave existing tile


# ─────────────────────────────────────────────────────────────────────────────
#  Main carver
# ─────────────────────────────────────────────────────────────────────────────

# Minimum room dimensions needed to fit the cell in any orientation.
# Blueprint is 7 wide × 4 tall (including threshold row).
_MIN_ROOM_W = 7   # 7 stamp + 1 margin each side
_MIN_ROOM_H = 4   # 4 stamp + at least 2 rows of open room in front


def generate_prison_cell(game_map, room, entities, stairs_positions):
    """
    Stamp a complete, enclosed prison cell into one edge of *room*.

    The orientation (which inner wall to use) is chosen randomly from
    whichever sides the room is large enough to accommodate.

    Parameters
    ----------
    game_map        : GameMap instance
    room            : RectRoom
    entities        : list – PrisonerNPC will be appended on success
    stairs_positions: dict  {'up': (x,y), 'down': (x,y)}

    Returns
    -------
    (PrisonerNPC, (door_x, door_y))   on success
    None                               if the room is too small or all positions blocked
    """

    room_w = room.x2 - room.x1   # includes outer walls (so inner width = room_w - 1)
    room_h = room.y2 - room.y1

    # Collect orientations this room can support
    possible = []
    if room_w >= _MIN_ROOM_W:
        possible += ['N', 'S']
    if room_h >= _MIN_ROOM_H:
        possible += ['E', 'W']

    # Further filter: need the perpendicular dimension to fit too
    final_possible = []
    for ori in possible:
        if ori in ('N', 'S') and room_h >= _MIN_ROOM_H:
            final_possible.append(ori)
        elif ori in ('E', 'W') and room_w >= _MIN_ROOM_W:
            final_possible.append(ori)

    if not final_possible:
        return None

    random.shuffle(final_possible)

    for orientation in final_possible:
        result = _try_stamp(game_map, room, entities, stairs_positions, orientation)
        if result is not None:
            return result

    return None   # no orientation worked


def _try_stamp(game_map, room, entities, stairs_positions, orientation):
    """
    Attempt to stamp the prison cell for one specific orientation.
    Returns (PrisonerNPC, door_pos) or None.

    Stamp origin (top-left of the 7×4 block in SOUTH reference):
      - SOUTH: anchored to the south inner wall, horizontally centred
      - NORTH: anchored to the north inner wall, horizontally centred
      - EAST : anchored to the east inner wall, vertically centred
      - WEST : anchored to the west inner wall, vertically centred
    """

    # ── Compute stamp origin in world coordinates ──────────────────────────
    inner_x1 = room.x1 + 2   # first walkable column
    inner_y1 = room.y1 + 2
    inner_x2 = room.x2 - 1   # last walkable column  (exclusive: room.x2 is wall)
    inner_y2 = room.y2 - 1

    inner_w = inner_x2 - inner_x1   # number of walkable columns
    inner_h = inner_y2 - inner_y1

    # The stamp bounding box in SOUTH reference is 7 cols × 4 rows.
    # For E/W orientations we swap dimensions.
    if orientation in ('N', 'S'):
        stamp_cols, stamp_rows = 7, 4
    else:
        stamp_cols, stamp_rows = 4, 7   # rotated

    # Centre the stamp along the wall it attaches to.
    if orientation == 'S':
        # Anchored at south inner wall:  origin_y = inner_y2 - (stamp_rows - 1)
        # Horizontally centred inside inner width
        origin_x = inner_x1 + (inner_w - stamp_cols) // 2
        origin_y = inner_y2 - (stamp_rows - 1)

    elif orientation == 'N':
        origin_x = inner_x1 + (inner_w - stamp_cols) // 2
        origin_y = inner_y1   # anchored at north inner wall

    elif orientation == 'E':
        # Anchored at east inner wall, vertically centred
        origin_x = inner_x2 - (stamp_cols - 1)
        origin_y = inner_y1 + (inner_h - stamp_rows) // 2

    elif orientation == 'W':
        origin_x = inner_x1   # anchored at west inner wall
        origin_y = inner_y1 + (inner_h - stamp_rows) // 2

    # ── Build rotated stamp entries with world coordinates ─────────────────
    # SOUTH template is 7×4; for rotation we pass its bounding box.
    rotated = _rotate_south_to(orientation, 7, 4)

    world_cells = []   # [(wx, wy, marker)]
    door_pos    = None
    prisoner_pos = None

    for (col_off, row_off, marker) in rotated:
        wx = origin_x + col_off
        wy = origin_y + row_off
        world_cells.append((wx, wy, marker))
        if marker == _D:
            door_pos = (wx, wy)

    # Prisoner is at the SOUTH-ref position (3,2) — transform the same way.
    pc, pr = _PRISONER_REL_SOUTH
    rotated_p = _rotate_south_to(orientation, 7, 4)
    # Find the entry that was originally at (3, 2) — it has marker _F at that pos;
    # instead just transform the coordinate directly.
    def _transform_coord(c, r, ori, W=6, H=3):
        if ori == 'S':  return c, r
        if ori == 'N':  return c, H - r
        if ori == 'E':  return H - r, c
        if ori == 'W':  return r, W - c
    tc, tr = _transform_coord(pc, pr, orientation)
    prisoner_pos = (origin_x + tc, origin_y + tr)

    # ── Validate all positions ──────────────────────────────────────────────
    for wx, wy, marker in world_cells:
        if not (0 <= wx < game_map.width and 0 <= wy < game_map.height):
            return None
        if stairs_positions and (wx, wy) in stairs_positions.values():
            return None
        if is_water_tile(game_map.tiles[wy][wx]):
            return None

    px, py = prisoner_pos
    if not (0 <= px < game_map.width and 0 <= py < game_map.height):
        return None
    if any(e.x == px and e.y == py for e in entities):
        return None

    # ── Stamp tiles ────────────────────────────────────────────────────────
    door_tile_instance = None
    for wx, wy, marker in world_cells:
        tile_obj = _tile_for_marker(marker)
        if tile_obj is None:
            continue   # _R — leave the existing floor
        if marker == _D:
            door_tile_instance = tile_obj
        game_map.tiles[wy][wx] = tile_obj

    # ── Place prisoner ─────────────────────────────────────────────────────
    prisoner = PrisonerNPC(px, py)
    entities.append(prisoner)

    return prisoner, door_pos


# ─────────────────────────────────────────────────────────────────────────────
#  Interaction handler  (called from game.py on 'F' key)
# ─────────────────────────────────────────────────────────────────────────────

def handle_prison_door_interaction(player, game_instance):
    """
    Checks all four cardinal neighbours of *player* for a PrisonDoorTile.
    Runs an Athletics / Thieves'-Tools check; opens the door on success.

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

        # ── Already open ──────────────────────────────────────────────────
        if tile.is_open:
            game_instance.message_log.add_message(
                "The prison door is already open.", (150, 150, 150)
            )
            return True

        # ── Skill check ───────────────────────────────────────────────────
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

        # ── Success ───────────────────────────────────────────────────────
        if total >= dc:
            tile.is_open   = True
            tile.is_locked = False
            tile.blocked   = False
            tile.char      = 'pdo'   # open-door graphic key (register in graphics.py)

            success_msgs = [
                "The prison door swings open with a groan of rusty hinges!",
                "With a sharp crack the lock gives way — the door is open!",
                "You wrench the door free; metal screeches against stone.",
                "The old lock shatters. The cell is open.",
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

        # ── Failure ───────────────────────────────────────────────────────
        fail_msgs = [
            "The door holds firm — you need more force or the right tools.",
            "The rusty lock refuses to budge.",
            "The hinges groan but the door doesn't move.",
            "Not enough. The door mocks your effort.",
            "You strain against the iron frame — it doesn't give.",
        ]
        game_instance.message_log.add_message(
            random.choice(fail_msgs), (255, 100, 100)
        )

        from core.floating_text import FloatingText
        game_instance.floating_texts.append(
            FloatingText(nx, ny, "LOCKED!", (255, 80, 80), y_speed=0.5)
        )
        return True   # event consumed even on failure

    return False   # no prison door adjacent