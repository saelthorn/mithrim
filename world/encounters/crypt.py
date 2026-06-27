import random
from world.tile import TombTile, DisturbedTombTile, floor, wall
from world.water_features import is_water_tile
from core.floating_text import FloatingText


# ─────────────────────────────────────────────────────────────────────────────
#  Public query helper
# ─────────────────────────────────────────────────────────────────────────────

def is_crypt_position(game_map, tile_x, tile_y):
    """
    Return True if (tile_x, tile_y) belongs to any placed crypt tomb.
    Other spawners call this to avoid placing items or monsters on tombs.
    """
    return (tile_x, tile_y) in getattr(game_map, 'crypt_tiles', set())


# ─────────────────────────────────────────────────────────────────────────────
#  Public carver
# ─────────────────────────────────────────────────────────────────────────────

def generate_crypt(game_map, room, stairs_positions):
    """
    Carve crypt tombs into a rectangular room.
    Spawns 2-4 tombs in a grid pattern within the room interior.
    
    On success:
      - Stamps tomb tiles onto game_map.
      - Registers every tomb tile in game_map.crypt_tiles.
    
    Returns a list of tomb positions [(x, y), ...] or None if the room is too small.
    """
    if not hasattr(game_map, 'crypt_tiles'):
        game_map.crypt_tiles = set()

    # Inner extents (room outer wall tiles excluded).
    first_inner_col = room.x1 + 1
    first_inner_row = room.y1 + 1
    last_inner_col  = room.x2 - 1
    last_inner_row  = room.y2 - 1

    inner_width  = last_inner_col - first_inner_col + 1
    inner_height = last_inner_row - first_inner_row + 1

    # Need at least a 5x5 interior to place tombs
    if inner_width < 5 or inner_height < 5:
        return None

    # Find potential tomb positions (avoiding room edges, spacing tombs 2+ apart)
    tomb_candidates = []
    for x in range(first_inner_col + 1, last_inner_col, 2):
        for y in range(first_inner_row + 1, last_inner_row, 2):
            if (0 <= x < game_map.width and 0 <= y < game_map.height and
                game_map.is_walkable(x, y) and not is_water_tile(game_map.tiles[y][x]) and
                (x, y) not in stairs_positions.values()):
                tomb_candidates.append((x, y))

    # Need at least 2 candidates to satisfy randint(2, ...)
    if len(tomb_candidates) < 2:
        return None

    # Place 2-4 tombs randomly
    num_tombs = random.randint(2, min(4, len(tomb_candidates)))
    tomb_positions = random.sample(tomb_candidates, num_tombs)

    # Stamp tomb tiles and register them
    for tomb_x, tomb_y in tomb_positions:
        game_map.tiles[tomb_y][tomb_x] = TombTile()
        game_map.crypt_tiles.add((tomb_x, tomb_y))

    return tomb_positions


# ─────────────────────────────────────────────────────────────────────────────
#  Space key interaction handler (called from game.py)
# ─────────────────────────────────────────────────────────────────────────────

def handle_tomb_interaction(player, game_instance):
    """
    Check the four cardinal tiles adjacent to *player* for a TombTile.
    If one is found, either spawn skeletons or drop items based on a roll.
    
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
        if not isinstance(neighbour_tile, TombTile):
            continue

        # ── Tomb already disturbed ──────────────────────────────────────────
        if neighbour_tile.is_disturbed:
            game_instance.message_log.add_message(
                "This tomb has already been disturbed.", (150, 150, 150)
            )
            return True


        die_roll = random.randint(1, 20)
        check_total = die_roll + player.get_ability_modifier(player.strength)

        game_instance.message_log.add_message(
            f"You open a heavy stone tomb — Athletics (STR): "
            f"[{die_roll}] + {player.get_ability_modifier(player.strength)} = {check_total}",
            (200, 200, 255)
        )

        if check_total >= 15:

            # ── Roll for skeleton spawn or item drop ────────────────────────────
            disturb_roll = random.random()
            is_skeleton_spawn = disturb_roll < 0.6  # 60% chance for skeleton, 40% for item

            neighbour_tile.is_disturbed = True
            game_map.tiles[neighbour_row][neighbour_col] = DisturbedTombTile()

            if is_skeleton_spawn:
                # ── Spawn skeleton ──────────────────────────────────────────────
                from entities.monster import Skeleton

                skeleton = Skeleton(neighbour_col, neighbour_row)
                skeleton.is_active = True
                game_instance.entities.append(skeleton)
                game_instance.turn_order.append(skeleton)
                skeleton.roll_initiative()
                game_instance.turn_order.sort(key=lambda e: e.initiative, reverse=True)

                game_instance.message_log.add_message(
                    "The tomb suddenly cracks open! A skeleton claws its way out!",
                    (200, 100, 100)
                )

                game_instance.floating_texts.append(
                    FloatingText(
                        neighbour_col - 0.5, neighbour_row,
                        "SKELETON!", (255, 255, 255), y_speed=0.5,
                    )
                )
            else:
                # ── Drop treasure ───────────────────────────────────────────────
                from items.items import (
                    lesser_healing_potion, greater_healing_potion,
                    iron_dagger, silver_dagger, bronze_short_sword,
                    torch
                )

                treasure_table = [
                    (lesser_healing_potion, 0.40),
                    (greater_healing_potion, 0.15),
                    (silver_dagger, 0.20),
                    (bronze_short_sword, 0.15),
                    (torch, 0.10),
                    (iron_dagger, 0.10)
                ]

                # Weighted random selection
                total_weight = sum(weight for _, weight in treasure_table)
                roll = random.uniform(0, total_weight)
                cumulative = 0
                chosen_template = treasure_table[0][0]

                for template, weight in treasure_table:
                    cumulative += weight
                    if roll <= cumulative:
                        chosen_template = template
                        break

                # Create item instance
                new_item = chosen_template.__class__(
                    name=chosen_template.name,
                    char=chosen_template.char,
                    color=chosen_template.color,
                    description=chosen_template.description,
                    **{k: v for k, v in chosen_template.__dict__.items() 
                       if k not in ['name', 'char', 'color', 'description', 'owner', 'x', 'y']}
                )
                new_item.x = neighbour_col
                new_item.y = neighbour_row
                game_map.items_on_ground.append(new_item)

                game_instance.message_log.add_message(
                    f"The tomb opens... revealing a {new_item.name}!",
                    (100, 200, 100)
                )

                game_instance.floating_texts.append(
                    FloatingText(
                        neighbour_col - 0.5, neighbour_row,
                        "TREASURE!", (255, 215, 0), y_speed=0.5,
                    )
                )
        else:
            game_instance.message_log.add_message(
                "You strain against the tomb, but it refuses to budge.",
                (200, 200, 200)
            )

            game_instance.floating_texts.append(
                FloatingText(
                    neighbour_col, neighbour_row,
                    "FAILED!", (255, 0, 0), y_speed=0.5,
                )
            )            

        game_instance.update_fov()
        return True

    return False